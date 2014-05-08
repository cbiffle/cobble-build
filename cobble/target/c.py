import cobble
import cobble.env
import os.path

from itertools import chain

_compile_keys = frozenset(['__order_only__', 'c_depswitch'])
_link_keys = frozenset(['__implicit__', 'cc', 'link_srcs', 'link_flags'])
_archive_keys = frozenset(['ar', 'ranlib'])
_preprocess_keys = frozenset(['cpp', 'cpp_flags', 'c_depswitch'])


class CTarget(cobble.Target):
  """Base class for C targets."""

  def _deps_delta(self, env):
    """Projects/targets can set c_deps_include_system to False to force GCC's
    -MMD dependency mode.  It's defaulted off because it tends to produce
    broken build files.
    """
    if env.get('c_deps_include_system', True):
      return [ cobble.env.override('c_depswitch', '-MD') ]
    else:
      return [ cobble.env.override('c_depswitch', '-MMD') ]


class CCompTarget(CTarget):
  """Base class for C compilation targets."""

  def __init__(self, loader, package, name, deps, sources, local):
    super(CTarget, self).__init__(loader, package, name)

    deps = [package.resolve(d) for d in deps]
    loader.include_packages(deps)

    self._local_delta = cobble.env.make_appending_delta(
      sources = sources,
      deps = deps,
    ) + cobble.env.make_appending_delta(**local)

  def _derive_local(self, env_up):
    return env_up.derive(self._local_delta)

  _file_type_map = {
    '.c':   ('compile_c_obj',   ['cc',   'c_flags']),
    '.cc':  ('compile_cxx_obj', ['cxx',  'cxx_flags']),
    '.cpp': ('compile_cxx_obj', ['cxx',  'cxx_flags']),
    '.S':   ('assemble_obj_pp', ['aspp', 'aspp_flags']),
  }

  def _compile_object(self, source, env):
    ext = os.path.splitext(source)[1]
    rule, keys = self._file_type_map[ext]

    keys = _compile_keys | frozenset(keys)

    o_env = env.derive(chain(self._deps_delta(env),
                             [ cobble.env.subset(keys) ]))
    return cobble.product(o_env,
      outputs = [ self.package.outpath(o_env, source + '.o') ],
      rule = rule,
      inputs = [ self.package.inpath(source) ],
    )


class Program(CCompTarget):
  """A program compiles some source files and produces a binary."""

  def __init__(self, loader, package, name, environment,
               deps = [],
               sources = [],
               local = {},
               extra = {}):
    super(Program, self).__init__(loader, package, name, deps, sources, local)

    self.environment = environment
    self.leaf = True
    self._transparent = False

    self._extra_delta = cobble.env.make_appending_delta(**extra)

  def _derive_down(self, env_up):
    env = self.package.project.named_envs[self.environment]
    return env.derive(self._extra_delta)

  def _using_and_products(self, env_local):
    sources = env_local.get('sources', [])
    objects = [self._compile_object(s, env_local) for s in sources]
    obj_files = list(chain(*[p['outputs'] for p in objects]))

    program_env = env_local.derive(cobble.env.make_prepending_delta(
      linksrcs = obj_files,
    ))

    program_path = self.package.outpath(program_env, self.name)
    program = cobble.product(program_env.subset(_link_keys),
      outputs = [ program_path ],
      rule = 'link_c_program',
      inputs = obj_files,
    )

    symlink_path = self.package.leafpath(self.name)
    symlink = {
      'outputs': [ symlink_path ],
      'rule': 'symlink_leaf',
      'order_only': [ program_path ],
      'variables': {
        'symlink_target': os.path.relpath(program_path,
                                          os.path.dirname(symlink_path)),
      },
    }

    using = cobble.env.make_appending_delta(
      __implicit__ = [self.identifier],
    )
    products = objects + [ program, symlink ]
    return (using, products)


class Library(CCompTarget):
  """A library compiles some source files to be linked into something else."""

  def __init__(self, loader, package, name,
               deps = [],
               sources = [],
               local = {},
               using = {}):
    super(Library, self).__init__(loader, package, name, deps, sources, local)
    self._using_delta = cobble.env.make_appending_delta(**using)

  def _using_and_products(self, env_local):
    sources = env_local.get('sources', [])
    if not sources:
      return (self._using_delta, [])

    objects = [self._compile_object(s, env_local) for s in sources]
    obj_files = list(chain(*[p['outputs'] for p in objects]))

    out = self.package.outpath(env_local, 'lib' + self.name + '.a')
    out_delta = [
      cobble.env.subset(_archive_keys),
      cobble.env.append('inputs', obj_files),
    ]
    library = cobble.product(env_local.derive(out_delta),
      outputs = [ out ],
      rule = 'archive_c_library',
      inputs = obj_files,
    )

    if env_local.get('whole_archive', False):
      link_srcs = [ '-Wl,-whole-archive', out, '-Wl,-no-whole-archive' ]
    else:
      link_srcs = [ out ]

    using = list(chain(self._using_delta, cobble.env.make_appending_delta(
      __implicit__ = [ out ],
      link_srcs = link_srcs,
    )))
    products = objects + [ library ]
    return (using, products)

  def extend_when(self, env_p, sources = [], deps = [], local = {}, using = {}):
    deps = [self.package.resolve(d) for d in deps]
    self.loader.include_packages(deps)

    delta = cobble.env.make_appending_delta(
      sources = sources,
      deps = deps,
    ) + cobble.env.make_appending_delta(**local)

    self._local_delta += cobble.env.make_delta_conditional(delta, env_p)

    using_delta = cobble.env.make_appending_delta(**using)
    self._using_delta += cobble.env.make_delta_conditional(using_delta, env_p)

    return self


class Preprocess(CTarget):
  """Runs the preprocessor on a file."""

  def __init__(self, loader, package, name, source, output, local = {}):
    super(Preprocess, self).__init__(loader, package, name)

    self.source = source
    self.output = output
    self._local_delta = cobble.env.make_appending_delta(**local)
    self.leaf = True

  def _derive_local(self, env_up):
    return self.package.project.named_envs['default'].derive(self._local_delta)

  def _using_and_products(self, env_local):
    pp_env = \
        env_local.derive(self._deps_delta(env_local)).subset(_preprocess_keys)

    output_path = self.package.genpath(self.output)
    product = {
      'outputs': [ output_path ],
      'rule': 'c_preprocess',
      'inputs': [ self.package.inpath(self.source) ],
      'variables': pp_env.dict_copy(),
    }

    symlink_path = self.package.leafpath(self.name)
    symlink = {
      'outputs': [ symlink_path ],
      'rule': 'symlink_leaf',
      'implicit': [ output_path ],
      'variables': {
        'symlink_target': os.path.relpath(output_path,
                                          os.path.dirname(symlink_path)),
      },
    }

    products = [ product, symlink ]
    return ([], products)


package_verbs = {
  'c_binary':     Program,
  'c_library':    Library,
  'c_preprocess': Preprocess,
}

ninja_rules = {
  'compile_c_obj': {
    'command': '$cc $c_depswitch -MF $depfile $c_flags -c -o $out $in',
    'description': 'C $in',
    'depfile': '$out.d',
    'deps': 'gcc',
  },
  'compile_cxx_obj': {
    'command': '$cxx $c_depswitch -MF $depfile $cxx_flags -c -o $out $in',
    'description': 'C++ $in',
    'depfile': '$out.d',
    'deps': 'gcc',
  },
  'assemble_obj_pp': {
    'command': '$aspp $c_depswitch -MF $depfile $aspp_flags -c -o $out $in',
    'description': 'AS+CPP $in',
    'depfile': '$out.d',
    'deps': 'gcc',
  },
  'c_preprocess': {
    'command': '$cpp $c_depswitch -MF $depfile $cpp_flags -o $out $in',
    'description': 'CPP $in',
    'depfile': '$out.d',
    'deps': 'gcc',
  },
  'link_c_program': {
    'command': '$cc $link_flags -o $out $in $link_srcs',
    'description': 'LINK $out',
  },
  'archive_c_library': {
    'command': '$ar rc $out $in && $ranlib $out',
    'description': 'AR $out',
  },
  'symlink_leaf': {
    'command': 'ln -sf $symlink_target $out',
    'description': 'SYMLINK $out',
  },
}

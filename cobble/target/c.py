import cobble
import cobble.env
import os.path

from itertools import chain

_common_keys = frozenset(['__implicit__', '__order_only__'])

_compile_keys = _common_keys | frozenset(['cc', 'cflags', 'depswitch'])
_link_keys = _common_keys | frozenset(['cc', 'linksrcs', 'lflags'])
_archive_keys = _common_keys | frozenset(['ar', 'ranlib'])


class CTarget(cobble.Target):
  """Base class for C targets."""

  def __init__(self, package, name, deps, sources, cflags):
    super(CTarget, self).__init__(package, name)

    self._local_delta = cobble.env.make_appending_delta(
      cflags = cflags,
      sources = sources,
      deps = deps,
    )

  def _derive_local(self, env_up):
    return env_up.derive(self._local_delta)

  def _compile_object(self, source, env):
    o_env = env.derive(chain(self._deps_delta(env),
                             [ cobble.env.subset(_compile_keys) ]))
    return cobble.product(o_env,
      outputs = [ self.package.outpath(o_env, source + '.o') ],
      rule = 'compile_c_object',
      inputs = [ self.package.inpath(source) ],
    )

  def _deps_delta(self, env):
    """Projects/targets can set c_deps_include_system to False to force GCC's
    -MMD dependency mode.  It's defaulted off because it tends to produce
    broken build files.
    """
    if env.get('c_deps_include_system', True):
      return [ cobble.env.override('depswitch', '-MD') ]
    else:
      return [ cobble.env.override('depswitch', '-MMD') ]



class Program(CTarget):
  """A program compiles some source files and produces a binary."""

  def __init__(self, package, name, deps, sources, cflags, lflags):
    """Creates a Program.

    The sources, cflags, lflags lists should be simple lists of strings.
    They will be interpolated and appended to their respective env-keys.
    """
    super(Program, self).__init__(package, name, deps, sources, cflags)

    self._transparent = False
    self.leaf = True

    self._local_delta += cobble.env.make_appending_delta(
      lflags = lflags,
    )

  def _using_and_products(self, env_local):
    sources = env_local.get('sources', [])
    objects = [self._compile_object(s, env_local) for s in sources]
    obj_files = list(chain(*[p['outputs'] for p in objects]))

    program_env = env_local.derive(cobble.env.make_prepending_delta(
      linksrcs = obj_files,
    )).subset(_link_keys)

    program_path = self.package.outpath(program_env, self.name)
    program = cobble.product(program_env,
      outputs = [ program_path ],
      rule = 'link_c_program',
      inputs = obj_files,
    )

    symlink_path = self.package.leafpath(self.name)
    symlink = {
      'outputs': [ symlink_path ],
      'rule': 'symlink_leaf',
      'implicit': [ program_path ],
      'variables': {
        'symlink_target': os.path.relpath(program_path,
                                          os.path.dirname(symlink_path)),
      },
    }

    using = cobble.env.make_appending_delta(
      implicit = [self.identifier],
    )
    products = objects + [ program, symlink ]
    return (using, products)


class Library(CTarget):
  """A library compiles some source files to be linked into something else."""

  def __init__(self, package, name, deps, sources, cflags,
               using_cflags, using_lflags):
    """Creates a Library.

    The sources, cflags, lflags lists should be simple lists of strings.
    They will be interpolated and appended to their respective env-keys.
    """
    super(Library, self).__init__(package, name, deps, sources, cflags)

    self._using_delta = cobble.env.make_appending_delta(
      cflags = using_cflags,
      lflags = using_lflags,
    )

  def _using_and_products(self, env_local):
    sources = env_local.get('sources', [])
    objects = [self._compile_object(s, env_local) for s in sources]
    obj_files = list(chain(*[p['outputs'] for p in objects]))

    out = self.package.outpath(env_local, 'lib' + self.name + '.a')
    library = cobble.product(env_local,
      outputs = [ out ],
      rule = 'archive_c_library',
      inputs = obj_files,
    )

    using = list(chain(self._using_delta, cobble.env.make_appending_delta(
      __implicit__ = [ out ],
      linksrcs = [ out ],
    )))
    products = objects + [ library ]
    return (using, products)


def c_binary(loader, package, name, sources = [], deps = []):
  deps = [package.resolve(d) for d in deps]
  loader.include_packages(deps)
  return Program(package, name, deps, sources, [], [])

def c_library(loader, package, name, sources = [], deps = []):
  deps = [package.resolve(d) for d in deps]
  loader.include_packages(deps)
  return Library(package, name, deps, sources, [], [], [])

package_verbs = {
  'c_binary': c_binary,
  'c_library': c_library,
}

ninja_rules = {
  'compile_c_object': {
    'command': '$cc $depswitch -MF $depfile $cflags -c -o $out $in',
    'description': 'C $out',
    'depfile': '$out.d',
    'deps': 'gcc',
  },
  'link_c_program': {
    'command': '$cc $lflags -o $out $linksrcs',
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

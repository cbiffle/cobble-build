import cobble
import cobble.env

from itertools import chain

class Program(cobble.Target):
  """A program compiles some source files and produces a binary."""

  def __init__(self, package, name, deps, sources, cflags, lflags):
    """Creates a Program.

    The sources, cflags, lflags lists should be simple lists of strings.
    They will be interpolated and appended to their respective env-keys.
    """
    super(Program, self).__init__(package, name)

    self._link_keys = set(['cc', 'linksrcs', 'lflags'])
    self._compile_keys = set(['cc', 'cflags'])

    self._transparent = False

    self._local_delta = cobble.env.make_appending_delta(
      cflags = cflags,
      lflags = lflags,
      sources = sources,
      deps = deps,
    )

  def _derive_local(self, env_up):
    return env_up.derive(self._local_delta)

  def _using_and_products(self, env_local):
    sources = env_local.get('sources', [])
    objects = [self._compile_object(s, env_local) for s in sources]
    obj_files = list(chain(*[p['outputs'] for p in objects]))

    program_env = env_local.derive(cobble.env.make_prepending_delta(
      linksrcs = obj_files,
    ))
    program = {
      'outputs': [ self.package.outpath(program_env, self.name) ],
      'rule': 'link_c_program',
      'inputs': obj_files,
      'implicit': program_env.get('implicit', []),
      'order_only': program_env.get('order_only', []),
      'variables': program_env.subset(self._link_keys).dict_copy(),
    }

    using = cobble.env.make_appending_delta(
      implicit = [self.identifier],
    )
    products = objects + [ program ]
    return (using, products)

  def _compile_object(self, source, env):
    o_env = env.subset(self._compile_keys)
    return {
      'outputs': [ self.package.outpath(o_env, source + '.o') ],
      'rule': 'compile_c_object',
      'inputs': [ self.package.inpath(source) ],
      'variables': o_env.dict_copy(),
    }


class Library(cobble.Target):
  """A library compiles some source files to be linked into something else."""

  def __init__(self, package, name, deps, sources, cflags, lflags,
               using_cflags, using_lflags):
    """Creates a Library.

    The sources, cflags, lflags lists should be simple lists of strings.
    They will be interpolated and appended to their respective env-keys.
    """
    super(Library, self).__init__(package, name)

    self._compile_keys = set(['cc', 'cflags'])
    self._archive_keys = set(['ar'])

    self._local_delta = cobble.env.make_appending_delta(
      cflags = cflags,
      lflags = lflags,
      sources = sources,
      deps = deps,
    )

    self._using_delta = cobble.env.make_appending_delta(
      cflags = using_cflags,
      lflags = using_lflags,
    )

  def _derive_local(self, env_up):
    return env_up.derive(self._local_delta)

  def _using_and_products(self, env_local):
    sources = env_local.get('sources', [])
    objects = [self._compile_object(s, env_local) for s in sources]
    obj_files = list(chain(*[p['outputs'] for p in objects]))

    out = self.package.outpath(env_local, 'lib' + self.name + '.a')
    library = {
      'outputs': [ out ],
      'rule': 'archive_c_library',
      'inputs': obj_files,
      'implicit': env_local.get('implicit', []),
      'order_only': env_local.get('order_only', []),
      'variables': env_local.subset(self._archive_keys).dict_copy(),
    }

    using = list(chain(self._using_delta, cobble.env.make_appending_delta(
      implicit = [ out ],
      linksrcs = [ out ],
    )))
    products = objects + [ library ]
    return (using, products)

  def _compile_object(self, source, env):
    o_env = env.subset(self._compile_keys)
    return {
      'outputs': [ self.package.outpath(o_env, source + '.o') ],
      'rule': 'compile_c_object',
      'inputs': [ self.package.inpath(source) ],
      'variables': o_env.dict_copy(),
    }

import cobble
import cobble.env
import functools

def load(root, outroot):
  return Loader(root, outroot).load()


class Loader(object):
  def __init__(self, root, outroot):
    self.project = cobble.Project(root, outroot)
    self._packages_to_visit = []
    self._defaults_provided = False
    self._installed_modules = {}

  def load(self):
    self._load_build_conf()

    while self._packages_to_visit:
      ident = self._packages_to_visit.pop()
      if ident.package_relpath not in self.project.packages:
        self._visit_package(ident.package_relpath)

    for module in self._installed_modules.itervalues():
      if hasattr(module, 'ninja_rules'):
        self.project.add_ninja_rules(module, module.ninja_rules)

    return self.project

  def _visit_package(self, relpath):
    package = cobble.Package(self.project, relpath)
    
    globals = {
      'GEN': package.genroot,
    }
    for m in self._installed_modules.itervalues():
      for name, fn in m.package_verbs.iteritems():
        globals[name] = functools.partial(fn, self, package)

    with open(package.inpath('BUILD'), 'r') as f:
      exec(f, globals)

  def include_packages(self, idents):
    self._packages_to_visit += idents

  def _load_build_conf(self):
    globals = {
      'seed': self._conf_seed,
      'install': self._conf_install,
      'environment': self._conf_environment,
    }
    with open(self.project.inpath('BUILD.conf'), 'r') as f:
      exec(f, globals)

  def _conf_seed(self, *id_strings):
    self._packages_to_visit += [cobble.Ident.parse(s) for s in id_strings]

  def _conf_defaults(self, **kw):
    if self._defaults_provided:
      raise Exception("multiple calls to defaults in BUILD.conf")

    delta = cobble.env.make_appending_delta(**kw)
    self.project.env = self.project.env.derive(delta)
    self._defaults_provided = True

  def _conf_install(self, module):
    self._installed_modules[module.__name__] = module

  def _conf_environment(self, name, base = None, contents = {}):
    if name in self.project.named_envs:
      raise Exception("Duplicate environment name: %s" % name)

    if base:
      try:
        base_env = self.project.named_envs[base]
      except KeyError:
        raise Exception("Environment %s: base %s does not exist" % (name, base))
    else:
      base_env = cobble.env.Env({ 'ROOT': self.project.root,
                                  'OUT':  self.project.outroot })

    env = base_env.derive(cobble.env.make_appending_delta(**contents))
    self.project.named_envs[name] = env

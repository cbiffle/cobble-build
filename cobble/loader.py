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
    
    globals = {}
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
      'defaults': self._conf_defaults,
      'install': self._conf_install,
    }
    with open(self.project.inpath('BUILD.conf'), 'r') as f:
      exec(f, globals)

  def _conf_seed(self, *id_strings):
    self._packages_to_visit += [cobble.Ident.parse(s) for s in id_strings]

  def _conf_defaults(self, **kw):
    if self._defaults_provided:
      raise Exception("multiple calls to defaults in BUILD.conf")

    self.project.env = cobble.env.Env(kw)
    self._defaults_provided = True

  def _conf_install(self, module):
    self._installed_modules[module.__name__] = module

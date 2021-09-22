"""Project loader for reading BUILD and BUILD.conf files."""

import importlib
import os.path
import sys
import traceback
import toml

import cobble.env


def load_project(
        project,
        build_vars,
        kr,
        projects,
        packages_to_visit,
        installed_modules):
    # Function that will be exposed to BUILD.conf files as 'seed()'
    def _build_conf_seed(*paths):
        nonlocal packages_to_visit
        packages_to_visit += [project.alias + p for p in paths]

    # Function that will be exposed to BUILD.conf files as 'install()'
    def _build_conf_install(module_name):
        nonlocal kr
        nonlocal installed_modules

        if module_name not in installed_modules:
            module = importlib.import_module(module_name)
            if hasattr(module, 'KEYS'):
                for k in module.KEYS:

                    kr.define(k)

            installed_modules[module.__name__] = module

    # Function that will be exposed to BUILD.conf files as 'environment()'
    def _build_conf_environment(name, base = None, contents = {}):
        assert name not in project.named_envs, \
                "More than one environment named %r" % name
        if base:
            assert base in project.named_envs, \
                "Base environment %r does not exist (must appear before)" \
                % base
            base_env = project.named_envs[base]
        else:
            base_env = cobble.env.Env(kr, {})

        env = base_env.derive(cobble.env.prepare_delta(contents))
        project.named_envs[name] = env

    # Function that will be exposed to BUILD.conf files as 'define_key()'
    def _build_conf_define_key(name, *, type):
        if type == 'string':
            key = cobble.env.overrideable_string_key(name)
        elif type == 'bool':
            key = cobble.env.overrideable_bool_key(name)
        else:
            raise Exception('Unknown key type: %r' % type)
        kr.define(key)

    # Function that will be exposed to BUILD.conf files as 'plugin_path()'
    def _build_conf_plugin_path(*paths):
        for p in [project.inpath(p) for p in paths]:
            if p not in sys.path:
                sys.path.append(p)

    # Function that will be exposed to BUILD.conf files as 'subproject()'
    def _build_conf_subproject(alias, path):
        nonlocal projects

        assert alias not in project.subprojects, \
            "Sub project %r is already registered" % alias

        sub_root = os.path.normpath(os.path.join(project.root, path))
        if sub_root in projects:
            subproject = projects[sub_root]
            assert project.alias == alias, \
                "Sub project at %r already registered with alias %r" % \
                    (path, subproject.alias)
        else:
            subproject = cobble.project.Project(
                sub_root,
                project.build_dir,
                alias)
            projects[sub_root] = subproject
            # Load the sub project. This will allow the remainder of the
            # BUILD.conf of the current project to reference items from
            # the sub project.
            #
            # This may result in a somewhat odd sequence of packages to
            # visit in the next step, so we may want to reconsider this.
            load_project(
                subproject,
                build_vars,
                kr,
                projects,
                packages_to_visit,
                installed_modules)

        project.subprojects[alias] = subproject

    # Read in BUILD.conf and eval it for its side effects
    _compile_and_exec(
        path = project.inpath('BUILD.conf'),
        kind = 'BUILD.conf file',
        globals = {
            # Block access to builtins. TODO: this might be too aggressive.
            '__builtins__': {},

            'seed': _build_conf_seed,
            'install': _build_conf_install,
            'environment': _build_conf_environment,
            'define_key': _build_conf_define_key,
            'plugin_path': _build_conf_plugin_path,
            'subproject': _build_conf_subproject,

            'VARS': build_vars,
            'ROOT': project.root,
            'ALIAS': project.alias,
            'BUILD': project.build_dir,
        },
    )

def load(root, build_dir):
    """Loads a Project, given the paths to the project root and build output
    directory."""

    # Create a key registry initialized with keys defined internally to Cobble.
    kr = cobble.env.KeyRegistry()
    for k in cobble.target.KEYS: kr.define(k)

    # Create working data structures.
    projects = {}
    packages_to_visit = []
    installed_modules = {}

    root_project = cobble.project.Project(root, build_dir, '')
    projects[root] = root_project

    # Load BUILD.vars
    build_vars = Vars.load(root_project.inpath('BUILD.vars'))

    # Recursively read in BUILD.conf and eval it for its side effects
    load_project(
        root_project,
        build_vars,
        kr,
        projects,
        packages_to_visit,
        installed_modules)

    # Register all plugins' ninja rules. The project context is not needed for
    # these, so simply add them all to the root project.
    for mod in installed_modules.values():
        if hasattr(mod, 'ninja_rules'):
            root_project.add_ninja_rules(mod.ninja_rules)

    # Process the package worklist. We're also extending the worklist in this
    # algorithm, treating it like a stack (rather than a queue). This means the
    # order of package processing is a little hard to predict. Because packages
    # can define keys that have effects on other packages, this should probably
    # get fixed (TODO).
    while packages_to_visit:
        ident = packages_to_visit.pop()

        # Determine if this package is part of a sub project. If it is perform
        # all operations which follow in the context of that (sub)project.
        project_alias, relpath = _get_relpath(ident)
        project = _find_subproject(projects.values(), project_alias)
        assert project, "No sub project found with alias %r" % project_alias

        # Check if we've done this one.
        if relpath in project.packages:
            continue

        package = cobble.project.Package(project, relpath)

        # Prepare the global environment for eval-ing the package. We provide
        # a few variables by default:
        pkg_env = {
            # Block access to builtins. TODO: this might be too aggressive.
            '__builtins__': {},

            # Easy access to the path from the build dir to the package
            'PKG': package.inpath(),
            # Access to localized build variables
            'VARS': build_vars,
            # Easy access to the path from the build dir to the project
            'ROOT': project.root,
            # Location of the build dir
            'BUILD': project.build_dir,
        }
        # The rest of the variables are provided by items registered in
        # plugins.
        for mod in installed_modules.values():
            if hasattr(mod, 'package_verbs'):
                for name, fn in mod.package_verbs.items():
                    pkg_env[name] = _wrap_verb(package, fn, packages_to_visit)
            if hasattr(mod, 'global_functions'):
                for name, fn in mod.global_functions.items():
                    pkg_env[name] = fn

        # And now, the evaluation!
        _compile_and_exec(
            path = package.inpath('BUILD'),
            kind = 'BUILD file',
            globals = pkg_env,
        )

    return root_project

def _wrap_verb(package, verb, packages_to_visit):
    """Instruments a package-verb function 'verb' from 'package' with code to
    register the resulting target and scan deps to discover new packages.

    'packages_to_visit' is a reference to a (mutable) list containing relpaths
    we should visit. The function returned from '_wrap_verb' will append
    relpaths of deps to that list. Some of them will be redundant; the worklist
    processing code is expected to deal with this.
    """
    def verb_wrapper(*pos, **kw):
        nonlocal packages_to_visit
        tgt = verb(package, *pos, **kw)
        if tgt:
            package.add_target(tgt)
        # TODO this is where we'd return for extend_when
        packages_to_visit += tgt.deps

    return verb_wrapper

def _get_relpath(ident):
    """Extracts the relative path from the project root to the directory
    containing the BUILD file defining a target named by an ident."""
    assert '//' in ident, "bogus ident got in: %r" % ident
    alias, package_and_target = ident.split('//')
    return (alias, package_and_target.split(':')[0])

def _find_subproject(projects, alias):
    for p in projects:
        if p.alias == alias:
            return p
    return None

class BuildError(Exception):
    """Exception raised if processing of a BUILD/BUILD.conf file fails."""

    def __init__(self, exc_info, kind, path, limit):
        """Creates a BuildError.

        'exc_info' is the information on the exception as received from
        'sys.exc_info()`.

        'kind' is a human-readable str description of what we were processing.

        'path' is a path to the file being processed.

        'limit' is the depth of the traceback that is relevant to the user
        error, i.e. does not include Cobble stack frames.
        """
        self.exc_info = exc_info
        self.kind = kind
        self.path = path
        self.limit = limit

def _compile_and_exec(path, kind, globals):
    """Implementation factor of BUILD and BUILD.conf evaluation. Loads the file
    at 'path' and execs it in an environment of 'globals', reporting the
    failure as 'kind' if it occurs."""
    with open(path, 'r') as f:
        try:
            mod = compile(
                source = f.read(),
                filename = path,
                mode = 'exec',
                dont_inherit = 1,
            )
            exec(mod, globals)
        except:
            exc_info = sys.exc_info()
            limit = len(traceback.extract_tb(exc_info[2])) - 1
            raise BuildError(
                    exc_info = exc_info,
                    limit = limit,
                    kind = kind,
                    path = path) from exc_info[1]


class Vars(dict):
    """A thin wrapper around dict to allow convenient loading of a BUILD.vars
    file and lookup of configuration variables."""

    @classmethod
    def load(cls, path):
        """Read a BUILD.vars file provided by 'path' and return its content as
        nested Vars objects. The variables in the dict can be passed to the
        evaluation step of BUILD.conf to localize environments."""
        try:
            with open(path) as f:
                return toml.load(f, Vars)
        except FileNotFoundError:
            pass
        except:
            exc_info = sys.exc_info()
            limit = len(traceback.extract_tb(exc_info[2])) - 1
            raise BuildError(
                    exc_info = exc_info,
                    limit = limit,
                    kind = 'BUILD.vars file',
                    path = path) from exc_info[1]
        return cls()

    def get(self, *keys, default=None):
        """Traverse into the dict looking up the given sequence of keys.
        Unless a default is provided, a KeyError is raised if the exact
        sequence of keys is not found."""
        if len(keys) == 0:
            raise TypeError(
                    'get expected at least 1 arguments, got %s' % len(keys))

        value = self
        for k in keys:
            if isinstance(value, dict):
                try:
                    value = value.__getitem__(k)
                except KeyError as e:
                    if default:
                        return default
                    else:
                        raise e
            else:
                raise KeyError(k)

        return value

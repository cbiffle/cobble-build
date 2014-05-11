import collections
import functools
import os.path

import cobble.env

from itertools import chain


class Ident(object):
  """An identifier for a Target, which can also be punned as a Package
  identifier.

  Identifiers look like:

      //foo/bar/baz:quux

  ...where 'foo/bar/baz' is the path from the project root to the directory
  containing the BUILD file, and 'quux' is the name of a target within the
  BUILD file.  These pieces are accessible on an Ident as properties
  'package_relpath' and 'target_name', respectively.

  If the target name is the same as the directory name, it can be omitted.
  For example, to reference the 'baz' target inside the 'foo/bar/baz' package:

      //foo/bar/baz

  In such a case, the 'target_name' property will be None.

  To get an Ident from either of these textual representations, call
  Ident.parse().

  In certain cases, Cobble accepts "relative identifiers" like ':quux'.  These
  are interpreted as a reference to a target name within the current package.
  Because the Ident class has no idea what the "current package" is, it doesn't
  implement support for these relative identifiers.  Instead, this happens in
  classes like Package.
  """

  @staticmethod
  def parse(string):
    """Parses a textual identifier."""
    if not string.startswith('//'):
      raise Exception('Bad identifier: %s' % string)

    parts = string[2:].split(':')
    if len(parts) == 1:
      # Target name not specified
      return Ident(parts[0], None)
    elif len(parts) == 2:
      return Ident(parts[0], parts[1])
    else:
      raise Exception('Too many colons in identifier: %s' % string)

  def __init__(self, package_relpath, target_name):
    """Assembles an identifier from its package's relative path and the
    target name.

    This is mostly intended as an implementation detail of parse(), but you can
    use it if you need it.
    """
    self.package_relpath = package_relpath
    self.target_name = target_name

  @property
  def target_name_or_default(self):
    return self.target_name or os.path.basename(self.package_relpath)

  def __hash__(self):
    return hash((self.package_relpath, self.target_name))

  def __eq__(self, other):
    return (self.package_relpath, self.target_name) == (other.package_relpath,
                                                        other.target_name)

  def __str__(self):
    """Turns this Ident back into the string from which it came."""
    if self.target_name is None:
      return ''.join([ '//', self.package_relpath ])
    else:
      return ''.join([ '//', self.package_relpath, ':', self.target_name ])

  def __repr__(self):
    return 'cobble.Ident("%s")' % str(self)


class Project(object):
  def __init__(self, root, outroot):
    self.root = root
    self.outroot = outroot
    self.named_envs = {}
    self.groups = collections.defaultdict(set)

    self.packages = {}
    self.ninja_rules = {}

  def add_package(self, package):
    p = package.relpath
    if p in self.packages:
      raise Exception("Duplicate package: %s" % p)
    self.packages[p] = package

  def add_ninja_rules(self, module, rule_map):
    for name, args in rule_map.iteritems():
      try:
        other_modules, current_args = self.ninja_rules[name]
      except KeyError:
        self.ninja_rules[name] = (set([module]), args)
        continue

      if args != current_args:
        raise Exception("Rule %(name)s defined in %(module)s is incompatible " +
                        "with previous definition in %(others)s."
                        % (name, module, modules))
      else:
        other_modules.add(module)

  def find_target(self, i):
    try:
      return self.packages[i.package_relpath].targets[i.target_name_or_default]
    except KeyError:
      raise Exception("No such target: %s" % i)

  def inpath(self, *parts):
    return os.path.join(self.root, *parts)

  def outpath(self, env, *parts):
    return os.path.join(self.outroot, 'env', env.digest, *parts)

  def leafpath(self, *parts):
    return os.path.join(self.outroot, 'latest', *parts)

  def genpath(self, *parts):
    return os.path.join(self.outroot, 'gen', *parts)

  def itertargets(self):
    return chain(*(p.itertargets() for p in self.packages.itervalues()))

  def iterleaves(self):
    return (target for target in self.itertargets() if target.leaf)

  def iterfiles(self):
    yield self.inpath('BUILD.conf')
    for p in self.packages.itervalues():
      yield p.inpath('BUILD')


class Package(object):
  def __init__(self, project, relpath):
    self.project = project
    self.relpath = relpath

    self.targets = {}

    self.project.add_package(self)

  def add_target(self, target):
    n = target.name
    if n in self.targets:
      raise Exception("Duplicate target: %s" % target.identifier)
    self.targets[n] = target

  def inpath(self, path):
    if path.startswith('@'):
      return self.project.genpath(path[1:])
    elif path.startswith('//'):
      return self.project.inpath(path[2:])
    else:
      return self.project.inpath(self.relpath, path)

  def outpath(self, env, *parts):
    return self.project.outpath(env, self.relpath, *parts)

  def leafpath(self, *parts):
    return self.project.leafpath(self.relpath, *parts)

  def genpath(self, *parts):
    return self.project.genpath(self.relpath, *parts)

  @property
  def genroot(self):
    return self.genpath()

  @property
  def inroot(self):
    return self.project.inpath(self.relpath)

  def itertargets(self):
    return self.targets.itervalues()

  def resolve(self, reference):
    if reference.startswith(':'):
      return Ident(self.relpath, reference[1:])
    else:
      return Ident.parse(reference)


class Target(object):
  def __init__(self, loader, package, name):
    self.loader = loader
    self.package = package
    self.name = name

    self.identifier = Ident(package.relpath, name)
    self._evaluations_by_env = {}
    self._transparent = True
    self.leaf = False

    self.package.add_target(self)

  @property
  def project(self):
    return self.package.project

  def evaluate(self, env_up):
    """Memoizing facade for _evaluate, below."""
    try:
      return self._evaluations_by_env[env_up]
    except KeyError:
      self._evaluations_by_env[env_up] = self._evaluate(env_up)
      return self.evaluate(env_up)

  def _evaluate(self, env_up):
    """Processes this target in a given up-environment.

    This processes the entire contextual subDAG beneath this target, so
    memoization is important to keep things linear.

    The result is a pair dicts.

    The first dict is a mapping of the form
      (target, env_up) -> (rank, using_delta)
    ...for all target evaluations in the subDAG.

    The (target, env_up) pairs are the arguments given to each evaluate
    call.  Notice that a target may appear multiple times with different
    evaluation environments.  This is deliberate, though it may not make
    sense for all targets.

    The rank is the number of edges followed from this target before finding
    the given (target, env_up) pair.  This information is critical for merging
    the evaluation mappings from subDAGs into higher DAG levels.

    The using_delta is the effect on the environment of dependent targets.
    These must be evaluated topologically.  To obtain a topological ordering
    of using_deltas from rank information, use cobble.topo_sort.

    The *second* dict of the result is a mapping
      (target, env) -> [product]

    ...where 'product' is a dict giving the arguments to the Ninja syntax
    writer's 'build' method.
    """

    env_down = self._derive_down(env_up)

    # local A applies the changes needed to discover our dep keys.
    env_local_a = self._derive_local(env_down)

    deps = [self.project.find_target(id) for id in env_local_a.get('deps', [])]
    dep_results = [dep.evaluate(env_down) for dep in deps]
    # [({(t, e):(r,u)}, {(t, e):[p]}]

    dep_map = topo_merge([m[0] for m in dep_results])
    # {(t, e):(r, u)}
    products = {}
    products.update(chain(*(m[1].iteritems() for m in dep_results)))

    dep_usings = (u for (t, e), (r, u) in topo_sort(dep_map))
    env_local_b = reduce(lambda e, u: e.derive(u), dep_usings, env_local_a)

    using, local_products = self._using_and_products(env_local_b)
   
    if self._transparent:
      dep_map[(self, env_up)] = (0, using)
    else:
      dep_map = { (self, env_up): (0, using) }

    products[(self, env_up)] = local_products

    return (dep_map, products)

  def _derive_down(self, env_up):
    return env_up

  def _using_and_products(self, env_local):
    """Should return a pair of (using_delta, build_products)"""
    return ([], [])
    
  def _derive_using(self, env_local, env_dep):
    return env_dep

  def _derive_local(self, env):
    return env

  def _products(self, env):
    return []

  def __repr__(self):
    return "<%s %s>" % (self.__class__.__name__, self.identifier)

def topo_merge(dicts):
  merged = {}
  for (target, env), (rank, using) in chain(*[m.iteritems() for m in dicts]):
    rank += 1
    if (target, env) in merged:
      # Target appears more than once.  Combine ranks.
      rank = max(rank, merged[(target, env)][0])
    merged[(target, env)] = (rank, using)
  return merged


def topo_sort(mapping):
  def key(pair):
    (t, e), (r, u) = pair
    return (r, t.identifier, e.digest, u)

  return sorted(mapping.iteritems(), key = key)


def product(env, outputs, rule, inputs = None, implicit = None,
            order_only = None):
  def _process(v, ek, d, dk):
    if v is None:
      v = env.get(ek, None)
    else:
      v = v + env.get(ek, [])

    if v:
      d[dk] = v

  delta = [
    cobble.env.remove('__implicit__'),
    cobble.env.remove('__order_only__'),
  ]
  p = {
    'outputs': outputs,
    'rule': rule,
    'inputs': inputs,
    'variables': env.derive(delta).dict_copy(),
  }
  _process(implicit, '__implicit__', p, 'implicit')
  _process(order_only, '__order_only__', p, 'order_only')

  return p

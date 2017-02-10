import cobble
import collections
import functools
import hashlib
import numbers


def fingerprint_dict(d):
  """Produces a hex digest of a dict.
  
  This sorts the dict's keys first, since dict order is unspecified, and then
  uses an unspecified munging operation (currently cPickle) to produce a stream
  of bytes.  This stream of bytes is then SHA1-hashed.
  """
  return hashlib.sha1(str(sorted(d.iteritems()))).hexdigest()


class Env(object):
  """An Env stores a collection of named values.

  It's quite similar to the environment of a Unix shell or process, except
  that it's immutable and can store things that aren't strings (mostly lists).

  (Note that all these claims of "immutability" really mean "we make it hard
  to mutate it by accident," because Python's immutability guarantees are
  weak.)
  """

  def __init__(self, contents, _copy_contents = True):
    """Creates a new Env by defensively copying the provided mapping."""
    if _copy_contents:
      self._dict = {}
      for k, v in contents.iteritems():
        self._dict[k] = freeze(v)
    else:
      self._dict = contents
    self._digest = None

  @property
  def digest(self):
    if self._digest is None:
      self._digest = fingerprint_dict(self._dict)
    return self._digest

  def derive(self, delta):
    """Apply a delta to this Env, producing a new Env."""
    new_dict = dict(self._dict.iteritems())
    for change in delta:
      change(new_dict)
    return Env(new_dict, _copy_contents = False)

  def subset(self, keys):
    """Derive a new Env containing the intersection between this Env's keys
    and the provided Iterable of key names."""
    return Env({k : self._dict[k]
                   for k in keys if k in self._dict},
               _copy_contents = False)

  def __str__(self):
    return "Env(%s)" % self.digest

  def __repr__(self):
    return "cobble.env.Env(%s)" % repr(self._dict)

  # Implementation of Iterable and dict-like stuff

  def __contains__(self, key):
    return self._dict.__contains__(key)

  def __iter__(self):
    return self._dict.__iter__()

  def __getitem__(self, key):
    return self._dict.__getitem__(key)

  def get(self, key, default = None):
    return self._dict.get(key, default)

  def __len__(self):
    return self._dict.__len__()

  def iteritems(self):
    return self._dict.iteritems()
  
  def dict_copy(self):
    return dict(self.iteritems())

  def __hash__(self):
    return hash(self.digest)

  def __eq__(self, other):
    return self.digest == other.digest and self._dict == other._dict


def interpolate(d, value):
  """More flexible version of Python's % operator for string-dict interpolation.
  """
  if isinstance(value, basestring):
    try:
      return value % d
    except KeyError as e:
      k = e.args[0]
      raise Exception('Environment key %s not found; available keys are: %s'
                      % (k, d.keys()))
  elif isinstance(value, collections.Iterable):
    return [interpolate(d, elt) for elt in value]
  else:
    return value


def freeze(value):
  if isinstance(value, basestring):
    return value
  elif isinstance(value, numbers.Number):
    return value
  elif isinstance(value, collections.Iterable):
    return tuple(freeze(v) for v in value)
  elif isinstance(value, cobble.Ident):
    return value
  else:
    raise Exception("Invalid type in environment: %s" % type(value))


def append(key, value):
  """Make a function that will append value to key in a dict, or create the
  key with the given value if none exists."""
  def helper(d):
    try:
      current = d[key]
    except KeyError:
      d[key] = freeze(interpolate(d, value))
      return

    d[key] = current + freeze(interpolate(d, value))

  return helper


def prepend(key, value):
  """Make a function that will prepend value to key in a dict, or create the
  key with the given value if none exists."""
  def helper(d):
    try:
      current = d[key]
    except KeyError:
      d[key] = freeze(interpolate(d, value))
      return

    d[key] = freeze(interpolate(d, value)) + current

  return helper

def override(key, value):
  """Make a function that will replace any value of key in a dict with
  value, creating if needed."""
  def helper(d):
    d[key] = freeze(interpolate(d, value))
  return helper

def remove(key):
  """Make a function that will remove any value of key in a dict."""
  def helper(d):
    if key in d:
      del d[key]
  return helper

def subset(keys):
  """Make a function that will delete keys not present in the given set."""
  def helper(d):
    d_keys = list(d.iterkeys())
    for k in d_keys:
      if k not in keys:
        del d[k]

  return helper

def make_appending_delta(**kw):
  return [append(k, v) for k, v in kw.iteritems()]

def make_prepending_delta(**kw):
  return [prepend(k, v) for k, v in kw.iteritems()]

def make_delta_conditional(delta, predicate):
  def helper(change, d):
    if predicate(d):
      change(d)

  return [functools.partial(helper, c) for c in delta]

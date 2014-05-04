import collections
import copy
import cPickle
import hashlib


def fingerprint_dict(d):
  """Produces a hex digest of a dict.
  
  This sorts the dict's keys first, since dict order is unspecified, and then
  uses an unspecified munging operation (currently cPickle) to produce a stream
  of bytes.  This stream of bytes is then SHA1-hashed.
  """
  return hashlib.sha1(
      cPickle.dumps(sorted(d.iteritems(), key = lambda p: p[0]))).hexdigest()


class Env(object):
  """An Env stores a collection of named values.

  It's quite similar to the environment of a Unix shell or process, except
  that it's immutable and can store things that aren't strings (mostly lists).

  (Note that all these claims of "immutability" really mean "we make it hard
  to mutate it by accident," because Python's immutability guarantees are
  weak.)
  """

  def __init__(self, contents):
    """Creates a new Env by defensively copying the provided mapping."""
    self._dict = copy.deepcopy(contents)
    self._digest = None

  @property
  def digest(self):
    if self._digest is None:
      self._digest = fingerprint_dict(self._dict)
    return self._digest

  def derive(self, delta):
    """Apply a delta to this Env, producing a new Env."""
    # Yes, this double-copies.  Without a way to define a private constructor
    # I don't see how to allow derive to avoid the constructor's defensive
    # copy.
    new_dict = copy.deepcopy(self._dict)
    for change in delta:
      change(new_dict)
    return Env(new_dict)

  def subset(self, keys):
    """Derive a new Env containing the intersection between this Env's keys
    and the provided Iterable of key names."""
    return Env({k : self._dict[k] for k in keys if k in self._dict})

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


def interpolate(d, value):
  """More flexible version of Python's % operator for string-dict interpolation.
  """
  if isinstance(value, str):
    return value % d
  elif isinstance(value, collections.Iterable):
    return [interpolate(d, elt) for elt in value]
  else:
    return value

def append(key, value):
  """Make a function that will append value to key in a dict, or create the
  key with the given value if none exists."""
  def helper(d):
    try:
      current = d[key]
    except KeyError:
      d[key] = interpolate(d, value)
      return

    d[key] = current + interpolate(d, value)

  return helper


def prepend(key, value):
  """Make a function that will prepend value to key in a dict, or create the
  key with the given value if none exists."""
  def helper(d):
    try:
      current = d[key]
    except KeyError:
      d[key] = interpolate(d, value)
      return

    d[key] = interpolate(d, value) + current

  return helper

def make_appending_delta(**kw):
  return [append(k, v) for k, v in kw.iteritems()]

def make_prepending_delta(**kw):
  return [prepend(k, v) for k, v in kw.iteritems()]

import cobble
import unittest

class FakeTarget(object):
  """Implements enough of Target's API for use with topo sort/merge."""
  def __init__(self, identifier):
    self.identifier = identifier


class FakeEnv(object):
  """Implements enough of Env's API for use with topo sort/merge."""
  def __init__(self, digest):
    self.digest = digest


class TopoTest(unittest.TestCase):
  def test_merge_basic(self):
    """Tests merging of two mapping describing a diamond DAG."""
    a, b, c, d = [FakeTarget(s) for s in ['a', 'b', 'c', 'd']]
    ea, eb, ec, ed = [FakeEnv('env_'+s) for s in ['a', 'b', 'c', 'd']]
    mapping_1 = {
      (a, ea): (0, ['first']),
      (b, eb): (1, ['second']),
    }
    mapping_2 = {
      (c, ec): (0, ['third']),
      (d, ed): (1, ['fourth']),
      (b, eb): (2, ['second']),
    }

    result = cobble.topo_merge([mapping_1, mapping_2])

    self.assertEqual((1, ['first']), result[(a, ea)])
    self.assertEqual((1, ['third']), result[(c, ec)])

    self.assertEqual((2, ['fourth']), result[(d, ed)])

    self.assertEqual((3, ['second']), result[(b, eb)])

  def test_sort_basic(self):
    """Tests production of a sorted list from a diamond DAG."""
    a, b, c, d = [FakeTarget(s) for s in ['a', 'b', 'c', 'd']]
    ea, eb, ec, ed = [FakeEnv('env_'+s) for s in ['a', 'b', 'c', 'd']]

    mapping = {
      (a, ea): (0, ['a']),
      (b, eb): (1, ['b']),
      (c, ec): (1, ['c']),
      (d, ed): (2, ['d']),
    }

    result = cobble.topo_sort(mapping)

    expected = [
      ((a, ea), (0, ['a'])),
      ((b, eb), (1, ['b'])),
      ((c, ec), (1, ['c'])),
      ((d, ed), (2, ['d'])),
    ]
    self.assertEqual(expected, result)
    

if __name__ == '__main__':
  unittest.main()

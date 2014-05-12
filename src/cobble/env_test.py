import cobble.env
import unittest


class EnvTest(unittest.TestCase):
  def test_basic_creation(self):
    x = { 'foo': 'bar', 'baz': ['quux'] }
    e = cobble.env.Env(x)
    self.assertEqual(2, len(e))
    # Verify a couple different ways to test collection interface
    for key in x:
      self.assertTrue(key in e)
      self.assertEqual(x[key], e[key])

    def first(p):
      return p[0]

    self.assertEqual(sorted(x.iteritems(), key = first),
                     sorted(e.iteritems(), key = first))

  def test_defensive_copy(self):
    x = { 'foo': 'bar', 'baz': ['quux'] }
    e = cobble.env.Env(x)

    x['blarg'] = 'lol'
    self.assertEqual(2, len(e))

  def test_defensive_deep_copy(self):
    x = { 'foo': 'bar', 'baz': ['quux'] }
    e = cobble.env.Env(x)
    x['baz'].append('zuul')
    self.assertEqual(1, len(e['baz']))

  def test_half_assed_immutability(self):
    e = cobble.env.Env({})
    with self.assertRaises(TypeError):
      e['foo'] = 3

  def test_derivation(self):
    e = cobble.env.Env({})
    delta = [
      cobble.env.append('foo', [42]),
      cobble.env.append('bar', 'vie'),
      cobble.env.append('foo', [43]),
      cobble.env.prepend('bar', 'moo'),
    ]

    e2 = e.derive(delta)
    self.assertEquals(dict(e2.iteritems()),
      {
        'foo': [42, 43],
        'bar': 'moovie',
      })

  def test_interpolation(self):
    e = cobble.env.Env({})
    delta = [
      cobble.env.append('foo', 'xyz'),
      cobble.env.append('bar', '-%(foo)s-'),
      cobble.env.append('foo', '*%(bar)s*'),
    ]

    e2 = e.derive(delta)
    self.assertEquals(dict(e2.iteritems()),
      {
        'foo': 'xyz*-xyz-*',
        'bar': '-xyz-',
      })

  def test_fingerprint_convergence(self):
    e1 = cobble.env.Env({'foo':'bar'})
    e2 = cobble.env.Env({})

    self.assertNotEqual(e1.digest, e2.digest)

    e3 = e2.derive([cobble.env.append('foo', 'bar')])
    self.assertEqual(e3.digest, e1.digest)

    e4 = e3.derive([cobble.env.append('foo', 'bar')])
    self.assertNotEqual(e4.digest, e1.digest)


if __name__ == '__main__':
  unittest.main()

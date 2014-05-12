import cobble
import cobble.env
import cobble.target.c
import collections
import unittest

class SimpleProgramTest(unittest.TestCase):
  def setUp(self):
    self.project = cobble.Project('ROOT', 'OUT')
    self.package = cobble.Package(self.project, 'test')
    self.program = cobble.target.c.Program(self.package, 'prog',
                                           deps = [],
                                           sources = [ 'foo.c', 'bar.c' ],
                                           cflags = [ 'CFLAGS' ],
                                           lflags = [ 'LFLAGS' ])

    self.env = cobble.env.Env({})

  def test_result_map(self):
    """The topomap of a program should not extend past the program itself."""
    topomap, products = self.program.evaluate(self.env)

    self.assertEqual(1, len(topomap))
    
    self.assertIs(self.program, topomap.keys()[0][0])

  def test_product_list(self):
    """The product list should contain two objects and a link step."""
    topomap, products = self.program.evaluate(self.env)
    products = list(products)

    self.assertEqual(3, len(products))
    
    rule_counts = collections.defaultdict(int)
    for p in products:
      rule_counts[p['rule']] += 1

    self.assertEqual(1, rule_counts['link_c_program'])
    self.assertEqual(2, rule_counts['compile_c_object'])


class SimpleLibraryTest(unittest.TestCase):
  def setUp(self):
    self.project = cobble.Project('ROOT', 'OUT')
    self.package = cobble.Package(self.project, 'test')
    self.program = cobble.target.c.Library(self.package, 'prog',
                                           deps = [],
                                           sources = [ 'foo.c', 'bar.c' ],
                                           cflags = [ 'CFLAGS' ],
                                           lflags = [ 'LFLAGS' ],
                                           using_cflags = ['UCFLAGS'],
                                           using_lflags = ['ULFLAGS'])

    self.env = cobble.env.Env({})

  def test_product_list(self):
    """The product list should contain two objects and an archive step."""
    topomap, products = self.program.evaluate(self.env)
    products = list(products)

    self.assertEqual(3, len(products))
    
    rule_counts = collections.defaultdict(int)
    for p in products:
      rule_counts[p['rule']] += 1

    self.assertEqual(1, rule_counts['archive_c_library'])
    self.assertEqual(2, rule_counts['compile_c_object'])

    

if __name__ == '__main__':
  unittest.main()


import cobble.loader
import cobble.ninja_syntax
import os.path
import sys

project_root = sys.argv[1]
project_module_dir = os.path.join(project_root, 'site_cobble')
if os.path.isdir(project_module_dir):
  sys.path += [ project_module_dir ]

project = cobble.loader.load(project_root, sys.argv[2])

writer = cobble.ninja_syntax.Writer(sys.stdout)

for name, (modules, args) in project.ninja_rules.iteritems():
  if len(modules) > 1:
    writer.comment('Rule %s defined in:' % name)
    for module in modules:
      writer.comment(' - %s' % module.__name__)
  else:
    writer.comment('Rule %s defined in %s' % (name,
                                              next(iter(modules)).__name__))
    
  writer.rule(name = name, **args)
  writer.newline()

unique_products = {}
for target in project.iterleaves():
  writer.comment('')
  writer.comment('Processing %s' % target.identifier)
  writer.comment('')
  writer.newline()
  topomap, products = target.evaluate(None)
  for product in products:
    key = ' '.join(product['outputs'])
    if key in unique_products:
      if product != unique_products[key]:
        raise Exception("Duplicate products with non-matching rules!")
      continue

    unique_products[key] = product

    writer.build(**product)
    writer.newline()


import cobble.ninja_syntax
import itertools
import os.path


def write_ninja_files(project):
  """Produces build.ninja and support files for a project in the current
  directory.
  """
  writer = cobble.ninja_syntax.Writer(open('.build.ninja.tmp', 'w'))

  generate_command_line = ' '.join([
    './cobble', 'init', '--reinit',
    project.root,
  ])

  _write_implicit_deps_file(project)

  writer.comment('Automatic regeneration')
  writer.rule(
    name = 'generate_ninja',
    command = generate_command_line,
    description = '(cobbling something together)',
    depfile = 'build.ninja.deps',
  )

  writer.build(
    outputs = [ 'build.ninja' ],
    rule = 'generate_ninja',
  )

  writer.newline()

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
  # We can make multiple passes here because the results are memoized.
  # First pass: check and collect unique products.
  for target in project.iterleaves():
    topomap, products = target.evaluate(None)
    for product in itertools.chain(*products.itervalues()):
      key = ' '.join(sorted(product['outputs']))
      if key in unique_products:
        if product != unique_products[key]:
          raise Exception("Duplicate products with non-matching rules!")
        continue

      unique_products[key] = product

  sorted_products = sorted(unique_products.itervalues(),
                           key = _product_sort_key)
  for product in sorted_products:
    writer.build(**product)
    writer.newline()

  # Second pass: generate phonies
  for target in project.iterleaves():
    topomap, products = target.evaluate(None)
    writer.build(
      outputs = [ str(target.identifier) ],
      rule = 'phony',
      implicit = [o for p in products.get((target, None), [])
                    for o in p['outputs']],
    )
    writer.newline()

  os.rename('.build.ninja.tmp', 'build.ninja')


def _write_implicit_deps_file(project):
  """This writes our regeneration dependencies in GCC/Make format.

  This works around a limitation in Ninja: it applies slightly different
  semantics to dependencies on header files produced by the C preprocessor.
  There is no syntax available in build.ninja to reproduce these semantics.
  But they have an important feature: if a file listed in this way disappears,
  the build is not blocked.

  In cases where the shape of a project changes (specifically, a BUILD file
  goes away), this lets us safely rebuild without completely reinitializing.
  """
  with open('build.ninja.deps.tmp', 'w') as f:
    f.write("build.ninja: \\\n")

    for filename in project.iterfiles():
      f.write("  %s \\\n" % filename)

    f.write("\n")  # for final backslash

  os.rename('build.ninja.deps.tmp', 'build.ninja.deps')


def _product_path_sort_key(product_path):
  """A transform that makes the env hash be the least important factor in
  sorting products.  This produces greater stability across environment
  changes.
  """
  if product_path.startswith('./env/'):
    return ('env', product_path[46:], product_path[6:46])
  else:
    return (product_path,)


def _product_sort_key(product):
  return tuple(_product_path_sort_key(o) for o in product['outputs'])

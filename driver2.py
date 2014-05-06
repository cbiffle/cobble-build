#!/usr/bin/env python

from __future__ import print_function

import argparse
import cobble.loader
import cobble.ninja_syntax
import os.path
import sys

parser = argparse.ArgumentParser()
parser.add_argument('project',
                    help = 'Directory at root of project (with BUILD.conf)')

parser.add_argument('--regen',
                    help = 'Allow overwriting build.ninja (default: no)',
                    action = 'store_true')

args = parser.parse_args()

# Argument validation

if os.path.samefile(args.project, '.'):
  print("I won't use your project directory as output directory.",
        file = sys.stderr)
  sys.exit(1)

if not os.path.isdir(args.project):
  print('Project dir missing or invalid: %s' % args.project, file = sys.stderr)
  sys.exit(1)

if (os.path.exists('build.ninja') and not args.regen):
  print("I won't overwrite build.ninja (use --regen to override)",
        file = sys.stderr)
  sys.exit(1)

# Actual work

project_module_dir = os.path.join(args.project, 'site_cobble')
if os.path.isdir(project_module_dir):
  sys.path += [ project_module_dir ]

project = cobble.loader.load(args.project, '.')

writer = cobble.ninja_syntax.Writer(open('.build.ninja.tmp', 'w'))

generate_command_line = ' '.join([
  __file__,
  '--regen',
  args.project,
])

writer.comment('Automatic regeneration')
writer.rule(
  name = 'generate_ninja',
  command = generate_command_line,
  description = '(cobbling something together)',
)

writer.build(
  outputs = [ 'build.ninja' ],
  rule = 'generate_ninja',
  inputs = list(project.iterfiles()),
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

os.rename('.build.ninja.tmp', 'build.ninja')

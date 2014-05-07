#!/usr/bin/env python

from __future__ import print_function

import argparse
import cobble.loader
import cobble.ninja_syntax
import itertools
import os.path
import subprocess
import sys


def init_build_dir(args):
  # Argument validation

  if os.path.samefile(args.project, '.'):
    print("I won't use your project directory as output directory.",
          file = sys.stderr)
    sys.exit(1)

  if not os.path.isdir(args.project):
    print('Project dir missing or invalid: %s' % args.project,
          file = sys.stderr)
    sys.exit(1)

  if (os.path.exists('build.ninja') and not args.reinit):
    print("I won't overwrite build.ninja (use --reinit to override)",
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
    'init',
    '--reinit',
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
    for product in itertools.chain(*products.itervalues()):
      key = ' '.join(product['outputs'])
      if key in unique_products:
        if product != unique_products[key]:
          raise Exception("Duplicate products with non-matching rules!")
        continue

      unique_products[key] = product

      writer.build(**product)
      writer.newline()

    writer.build(
      outputs = [ str(target.identifier) ],
      rule = 'phony',
      implicit = [o for p in products.get((target, None), [])
                    for o in p['outputs']],
    )

  os.rename('.build.ninja.tmp', 'build.ninja')  


def build(args):
  cmd = [ 'ninja' ]
  if args.jobs:
    cmd += [ '-j', str(args.jobs) ]
  if args.loadavg:
    cmd += [ '-l', str(args.loadavg) ]
  if args.dry_run:
    cmd += [ '-n' ]
  if args.show_commands:
    cmd += [ '-v' ]
  if args.explain:
    cmd += [ '-d', 'explain' ]
  if args.stats:
    cmd += [ '-d', 'stats' ]

  cmd += args.targets

  subprocess.call(cmd)

parser = argparse.ArgumentParser()

subparsers = parser.add_subparsers(title = 'commands')

init_parser = subparsers.add_parser('init',
                                    help = 'Initialize a build directory')
init_parser.set_defaults(go = init_build_dir)
init_parser.add_argument('project',
                         help = 'Directory at root of project with BUILD.conf')

init_parser.add_argument('--reinit',
                         help = 'Allow overwriting build.ninja (default: no)',
                         action = 'store_true')

build_parser = subparsers.add_parser('build',
                                     help = 'Build project')
build_parser.add_argument('-j',
                          help = 'run N jobs in parallel',
                          type = int,
                          metavar = 'N',
                          dest = 'jobs')

build_parser.add_argument('-l',
                          help = "don't start new jobs if loadavg > N",
                          type = float,
                          metavar = 'N',
                          dest = 'loadavg')

build_parser.add_argument('-n',
                          help = "dry run (don't run commands)",
                          action = 'store_true',
                          dest = 'dry_run')

build_parser.add_argument('-v',
                          help = "show all command lines while building",
                          action = 'store_true',
                          dest = 'show_commands')

build_parser.add_argument('--explain',
                          help = "explain why commands are being run",
                          action = 'store_true')

build_parser.add_argument('--stats',
                          help = "at end, print ninja internal stats",
                          action = 'store_true')

build_parser.add_argument('targets',
                          nargs = '*',
                          help = 'Targets to build; if unspecified, build all.')

build_parser.set_defaults(go = build)


args = parser.parse_args()
args.go(args)

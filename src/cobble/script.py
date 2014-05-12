from __future__ import print_function

import argparse
import cobble.loader
import cobble.ninja_syntax
import cobble.output
import itertools
import os.path
import subprocess
import sys


def find_script_path(script):
  """Dereferences symlinks until it finds the script."""
  while os.path.islink(script):
    script = os.path.join(os.path.dirname(script), os.readlink(script))
  return script


def create_cobble_symlink(cobble_path):
  """Creates a symlink called 'cobble' in the current (build) directory."""
  if os.path.exists('./cobble'):
    if os.path.islink('./cobble'):
      # We'll assume it's ours to mess with...
      if os.readlink('./cobble') != cobble_path:
        os.remove('./cobble')
      else:
        # It's already okay!
        return
    else:
      raise Exception('Cannot create ./cobble symlink: other file has that ' +
                      'name.')

  os.symlink(cobble_path, './cobble')


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

  script_path = find_script_path(args.script_path)
  create_cobble_symlink(os.path.relpath(script_path, '.'))

  project_module_dir = os.path.join(args.project, 'site_cobble')
  if os.path.isdir(project_module_dir):
    sys.path += [ project_module_dir ]

  project = cobble.loader.load(args.project, '.')

  cobble.output.write_ninja_files(project)


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


def make_argument_parser():
  parser = argparse.ArgumentParser()

  subparsers = parser.add_subparsers(title = 'commands')
  make_init_parser(subparsers)
  make_build_parser(subparsers)

  return parser


def make_init_parser(subparsers):
  init_parser = subparsers.add_parser(
      'init',
      help = 'Initialize a build directory')
  init_parser.add_argument(
      'project',
      help = 'Directory at root of project with BUILD.conf')

  init_parser.add_argument(
      '--reinit',
      help = 'Allow overwriting build.ninja (default: no)',
      action = 'store_true')
  init_parser.set_defaults(go = init_build_dir)


def make_build_parser(subparsers):
  build_parser = subparsers.add_parser(
      'build',
      help = 'Build project')
  build_parser.add_argument(
      '-j',
      help = 'run N jobs in parallel',
      type = int,
      metavar = 'N',
      dest = 'jobs')

  build_parser.add_argument(
      '-l',
      help = "don't start new jobs if loadavg > N",
      type = float,
      metavar = 'N',
      dest = 'loadavg')

  build_parser.add_argument(
      '-n',
      help = "dry run (don't run commands)",
      action = 'store_true',
      dest = 'dry_run')

  build_parser.add_argument(
      '-v',
      help = "show all command lines while building",
      action = 'store_true',
      dest = 'show_commands')

  build_parser.add_argument(
      '--explain',
      help = "explain why commands are being run",
      action = 'store_true')

  build_parser.add_argument(
      '--stats',
      help = "at end, print ninja internal stats",
      action = 'store_true')

  build_parser.add_argument(
      'targets',
      nargs = '*',
      help = 'Targets to build; if unspecified, build all.')

  build_parser.set_defaults(go = build)


def run(script_path):
  args = make_argument_parser().parse_args()
  args.script_path = script_path
  args.go(args)

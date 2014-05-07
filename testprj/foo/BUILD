# -*- python -*- vim:syntax=python:
# This builds a binary (standalone program) called 'test'.
c_binary('test',
  # Use the environment 'default' defined in BUILD.conf.
  # Binaries must explicitly choose an environment, because they can be
  # built by themselves.  Libraries, on the other hand, get whatever
  # environment is chosen by the thing they're being linked into.
  environment = 'default',
  
  # This simple program contains only a single source file.  Source files are
  # looked up relative to the directory containing BUILD.  They *can* name
  # other locations using either relative paths or //-paths, but it's not
  # really what the system was designed for.
  sources = [ 'foo.c' ],

  # This program depends on a single library, which is in a package called
  # 'bar' beneath the project root.  Note that we haven't named a target
  # within the package -- Cobble will assume it's named 'bar' like the
  # package.
  deps = [ '//bar' ],
)

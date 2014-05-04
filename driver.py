import cobble
import cobble.env
import cobble.ninja_syntax
import cobble.target.c

import sys

project = cobble.Project('ROOT', 'OUT')
package = cobble.Package(project, 'foo')

moo = cobble.target.c.Library(package, 'moo', [], ['moo.c'], [], [], ['UC2'], ['UL2'])
bar = cobble.target.c.Library(package, 'bar', [moo.identifier], ['bar.c'], [], [], ['UC'], ['UL'])
foo = cobble.target.c.Program(package, 'foo', [bar.identifier], ['foo.c'], ['CFLAGS'], ['LFLAGS'])

env = cobble.env.Env({})

(topomap, products) = foo.evaluate(env)

print topomap
foo_up_using = topomap[(foo, env)][1]

print repr(env.derive(foo_up_using))

w = cobble.ninja_syntax.Writer(sys.stdout)
for p in products:
  w.build(**p)

topomap, products = bar.evaluate(env)
u = env
for (target, env), (rank, using) in cobble.topo_sort(topomap):
  print repr(u)
  print list(using)
  u = u.derive(using)

print repr(u)

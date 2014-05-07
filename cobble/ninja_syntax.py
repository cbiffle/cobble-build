#!/usr/bin/python

"""Python module for generating .ninja files, derived from code provided by
the Ninja authors.
"""

import textwrap
import re

def _escape_path(word):
    return word.replace('$ ','$$ ').replace(' ','$ ').replace(':', '$:')

class Writer(object):
    def __init__(self, output, width=78):
        self.output = output
        self.width = width

    def newline(self):
        self.output.write('\n')

    def comment(self, text):
        for line in textwrap.wrap(text, self.width - 2):
            self.output.write('# ' + line + '\n')

    def variable(self, key, value, indent=0):
        if value is None:
            return
        if isinstance(value, list):
            value = ' '.join(filter(None, value))  # Filter out empty strings.
        self._line('%s = %s' % (key, value), indent)

    def pool(self, name, depth):
        self._line('pool %s' % name)
        self.variable('depth', depth, indent=1)

    def rule(self, name, command, description=None, depfile=None,
             generator=False, pool=None, restat=False, rspfile=None,
             rspfile_content=None, deps=None):
        self._line('rule %s' % name)
        self.variable('command', command, indent=1)
        self._maybe_variable('description', description, indent=1)
        self._maybe_variable('depfile', depfile, indent=1)
        self._maybe_variable('pool', pool, indent=1)
        self._maybe_variable('rspfile', rspfile, indent=1)
        self._maybe_variable('rspfile_content', rspfile_content, indent=1)
        self._maybe_variable('deps', deps, indent=1)

        if generator:
            self.variable('generator', '1', indent=1)
        if restat:
           self.variable('restat', '1', indent=1)

    def _maybe_variable(self, key, value, indent=0):
      if value:
        self.variable(key, value, indent)

    def build(self, outputs, rule, inputs=None, implicit=None, order_only=None,
              variables=None):
        out_outputs = list(map(_escape_path, self._as_list(outputs)))
        all_inputs = list(map(_escape_path, self._as_list(inputs)))

        if implicit:
            all_inputs.append('|')
            all_inputs.extend(map(_escape_path, self._as_list(implicit)))
        if order_only:
            all_inputs.append('||')
            all_inputs.extend(map(_escape_path, self._as_list(order_only)))

        self._line('build %s: %s' % (' '.join(out_outputs),
                                     ' '.join([rule] + all_inputs)))

        if isinstance(variables, dict):
            iterator = variables.iteritems()
        else:
            iterator = iter(variables or [])

        for key, val in iterator:
            self.variable(key, val, indent=1)

    def include(self, path):
        self._line('include %s' % path)

    def subninja(self, path):
        self._line('subninja %s' % path)

    def default(self, paths):
        self._line('default %s' % ' '.join(self._as_list(paths)))

    def _count_dollars_before_index(self, s, i):
      """Returns the number of '$' characters right in front of s[i]."""
      dollar_count = 0
      dollar_index = i - 1
      while dollar_index > 0 and s[dollar_index] == '$':
        dollar_count += 1
        dollar_index -= 1
      return dollar_count

    def _line(self, text, indent=0):
        """Write 'text' word-wrapped at self.width characters."""
        leading_space = '  ' * indent
        while len(leading_space) + len(text) > self.width:
            # The text is too wide; wrap if possible.

            # Find the rightmost space that would obey our width constraint and
            # that's not an escaped space.
            available_space = self.width - len(leading_space) - len(' $')
            space = available_space
            while True:
              space = text.rfind(' ', 0, space)
              if space < 0 or \
                 self._count_dollars_before_index(text, space) % 2 == 0:
                break

            if space < 0:
                # No such space; just use the first unescaped space we can find.
                space = available_space - 1
                while True:
                  space = text.find(' ', space + 1)
                  if space < 0 or \
                     self._count_dollars_before_index(text, space) % 2 == 0:
                    break
            if space < 0:
                # Give up on breaking.
                break

            self.output.write(leading_space + text[0:space] + ' $\n')
            text = text[space+1:]

            # Subsequent lines are continuations, so indent them.
            leading_space = '  ' * (indent+2)

        self.output.write(leading_space + text + '\n')

    def _as_list(self, input):
        if input is None:
            return []
        if isinstance(input, list):
            return input
        return [input]


def escape(string):
    """Escape a string such that it can be embedded into a Ninja file without
    further interpretation."""
    assert '\n' not in string, 'Ninja syntax does not allow newlines'
    # We only have one special metacharacter: '$'.
    return string.replace('$', '$$')

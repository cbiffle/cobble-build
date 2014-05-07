"""Python module for generating .ninja files, derived from code provided by
the Ninja authors.
"""

import collections
import itertools
import textwrap
import re

def _escape_path(word):
    """Used to escape paths; only escapes the characters that are significant
    in a build/rule definition.  Interestingly, does *not* escape dollar signs.
    """
    return word.replace('$ ','$$ ').replace(' ','$ ').replace(':', '$:')


def _as_iterable(input):
    """Allows punning of singleton values as iterables. Iterables are passed
    through, except strings, which are treated as values.   Other values emerge
    as singleton iterables, except None, which emerges as empty.
    """
    if isinstance(input, str):
        return [input]
    if isinstance(input, collections.Iterable):
        return input
    if input is None:
        return []
    return [input]


def _count_dollars_before_index(s, i):
    """Returns the number of '$' characters right in front of s[i]."""
    dollar_count = 0
    dollar_index = i - 1
    while dollar_index > 0 and s[dollar_index] == '$':
        dollar_count += 1
        dollar_index -= 1
    return dollar_count


class Writer(object):
    def __init__(self, output, width=78):
        self.output = output
        self.width = width

    def newline(self):
        """Emits a blank line."""
        self.output.write('\n')

    def comment(self, text):
        """Emits some commented text."""
        for line in textwrap.wrap(text, self.width - 2):
            self.output.write('# ' + line + '\n')

    def variable(self, key, value, indent=0):
        """Emits a variable, joining values with spaces if required."""
        # TODO(cbiffle): neither key nor value are escaped?
        value_str = ' '.join(itertools.ifilter(None, _as_iterable(value)))

        if value_str:
          self._line('%s = %s' % (key, value_str), indent)

    def pool(self, name, depth):
        """Emits a pool declaration."""
        # TODO(cbiffle): name is not escaped?
        self._line('pool %s' % name)
        self.variable('depth', depth, indent=1)

    def rule(self, name, command, description=None, depfile=None,
             generator=False, pool=None, restat=False, rspfile=None,
             rspfile_content=None, deps=None):
        """Emits a rule."""
        # TODO(cbiffle): name is not escaped?
        self._line('rule %s' % name)
        self.variable('command', command, indent=1)
        self.variable('description', description, indent=1)
        self.variable('depfile', depfile, indent=1)
        self.variable('pool', pool, indent=1)
        self.variable('rspfile', rspfile, indent=1)
        self.variable('rspfile_content', rspfile_content, indent=1)
        self.variable('deps', deps, indent=1)
        self.variable('generator', generator and '1', indent=1)
        self.variable('restat', generator and '1', indent=1)

    def build(self, outputs, rule, inputs=None, implicit=None, order_only=None,
              variables=None):
        """Emits a build product.

        Outputs, inputs, implicit, and order_only are typically iterables, but
        each can also be provided as a single string.

        Variables can either be a mapping or an iterable of key,value pairs.
        """
        # TODO(cbiffle): rule name not escaped?
        out_outputs = itertools.imap(_escape_path, _as_iterable(outputs))
        all_inputs = itertools.imap(_escape_path, _as_iterable(inputs))

        if implicit:
            all_inputs = itertools.chain(
                all_inputs,
                ['|'],
                itertools.imap(_escape_path, _as_iterable(implicit)))
        if order_only:
            all_inputs = itertools.chain(
                all_inputs,
                ['||'],
                itertools.imap(_escape_path, _as_iterable(order_only)))

        self._line('build %s: %s %s' % (' '.join(out_outputs),
                                        rule,
                                        ' '.join(all_inputs)))

        if variables is None:
          pass
        elif isinstance(variables, collections.Mapping):
            for key in variables:
                self.variable(key, variables[key], indent=1)
        else:
            for key, val in variables:
                self.variable(key, val, indent=1)

    def include(self, path):
        """Emits an include statement for a path."""
        # TODO(cbiffle): path is not escaped ...?
        self._line('include %s' % path)

    def subninja(self, path):
        """Emits a subninja statement."""
        # TODO(cbiffle): path is not escaped ...?
        self._line('subninja %s' % path)

    def default(self, paths):
        """Designates some paths as default."""
        # TODO(cbiffle): paths not escaped?
        self._line('default %s' % ' '.join(_as_iterable(paths)))

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
                 _count_dollars_before_index(text, space) % 2 == 0:
                break

            if space < 0:
                # No such space; just use the first unescaped space we can find.
                space = available_space - 1
                while True:
                  space = text.find(' ', space + 1)
                  if space < 0 or \
                     _count_dollars_before_index(text, space) % 2 == 0:
                    break
            if space < 0:
                # Give up on breaking.
                break

            self.output.write(leading_space + text[0:space] + ' $\n')
            text = text[space+1:]

            # Subsequent lines are continuations, so indent them.
            leading_space = '  ' * (indent+2)

        self.output.write(leading_space + text + '\n')


def escape(string):
    """Escape a string such that it can be embedded into a Ninja file without
    further interpretation."""
    assert '\n' not in string, 'Ninja syntax does not allow newlines'
    # We only have one special metacharacter: '$'.
    return string.replace('$', '$$')

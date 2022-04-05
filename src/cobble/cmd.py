"""Helpers used to implement various commands."""

import subprocess
import os.path
import re

from cobble.target import concrete_products


def build(targets, jobs=None, loadavg=None, verbose=False, dry_run=False,
            explain=False, stats=False):
    """Build the given targets using Ninja. This will throw a
    subprocess.CalledProcessError if Ninja exits with a non-zero exit code.
    """

    cmd = ['ninja']

    if jobs: cmd.extend(['-j', str(jobs)])
    if loadavg: cmd.extend(['-l', str(args.loadavg)])
    if verbose: cmd.append('-v')
    if dry_run: cmd.append('-n')
    if explain: cmd.extend(['-d', 'explain'])

    cmd.extend(targets)
    subprocess.check_call(cmd)

def query_products(project, query, verbose=False):
    """Query the given Project for named Products matching the given query and
    return a list of QueryResults. This will throw a
    cobble.target.EvaluationError if an exception occurs during evaluation.
    """
    results = dict()

    for target in project.concrete_targets():
        for result in concrete_products(
                target,
                None,
                query.fullmatch):
            ident = result.ident
            assert ident not in results, \
                "ident %s expected to be unique" % ident
            results[ident] = result

    print(f"{len(results)} query result(s)")

    outputs = sorted(results.items())

    if verbose:
        for ident, output in outputs:
            print(f"{ident} -> {output.file_path}")

    return outputs

def query_products_and_build(project, query, jobs=None, loadavg=None,
            verbose=False, dry_run=False):
    """Query the given Project for named Products matching the given query,
    build them, and then return the list of QueryResults.

    Note this calls `query_products` and `build`. See their doc strings about
    possible exceptions thrown.
    """
    results = query_products(project, query, verbose=verbose)
    outputs = []
    symlinks = []

    for ident, result in results:
        outputs.append(result.file_path)

        # Find any links matching outputs to be built.
        for link, source in result.product.symlinks():
            if result.file_path == source:
                symlinks.append(link)

    if len(results) > 0:
        build(outputs + symlinks,
            jobs=jobs,
            loadavg=loadavg,
            verbose=verbose,
            dry_run=dry_run)

    return results

def build_targets_or_query_results(project, targets_or_query, args):
    """Given a list of one or more targets, build and then return a sorted
    list of the outputs, allowing them to be used for further processing.
    If the list of targets contains only a single element it is examined and
    executed as a products query if it does not appear to be a concrete output.

    Note this calls `query_products` and `build`. See their doc strings about
    possible exceptions thrown.
    """

    # When building the results of a product query it may make sense to include
    # the symlinks in the build. These links should be considered a side effect
    # however, a convenience to the user, and should therefor not be passed on
    # for further processing. As such, keep them separated from the query result
    # artifacts.
    symlinks = []

    if len(targets_or_query) == 1:
        # Determine if the provided target is really a query.
        path = os.path.normpath(targets_or_query[0])

        if not ('env' in path or 'latest' in path):
            # Run target as a query.
            query = re.compile(targets_or_query[0])

            query_results = query_products(
                project,
                query,
                verbose=args.verbose)

            if len(query_results) == 0:
                return 1

            outputs = []
            for ident, result in query_results:
                outputs.append(result.file_path)

                # Find any links matching outputs to be built.
                for link, source in result.product.symlinks():
                    if result.file_path == source:
                        symlinks.append(link)
        else:
            outputs = [path]
    else:
        outputs = targets_or_query

    build(outputs + symlinks,
        jobs=getattr(args, 'jobs', None),
        loadavg=getattr(args, 'loadavg', None),
        verbose=args.verbose,
        dry_run=getattr(args, 'dry_run', None),
        explain=getattr(args, 'explain', None),
        stats=getattr(args, 'stats', False))

    return outputs

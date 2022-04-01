import datetime
import pathlib
import re
import subprocess

from functools import cached_property #, cache
from typing import List, Iterator, Optional, Union, Tuple

import cobble.env

GIT_VERSION_CODE = cobble.env.immutable_string_key(
        'git_version_code',
        help = 'The project Git version code.')
GIT_VERSION_NAME = cobble.env.immutable_string_key(
        'git_version_name',
        help = 'The project Git version name.')
GIT_VERSION_REV_SHA1 = cobble.env.immutable_string_key(
        'git_version_rev_sha1',
        help = 'The project Git revision SHA1.')
GIT_VERSION_REV_SHA1_SHORT = cobble.env.immutable_string_key(
        'git_version_rev_sha1_short',
        help = 'The project short Git revision SHA1.')
GIT_VERSION_BASE_BRANCH = cobble.env.immutable_string_key(
        'git_version_base_branch',
        help = 'The project base Git branch.')
GIT_VERSION_BASE_BRANCH_COMMIT_COUNT = cobble.env.immutable_string_key(
        'git_version_base_branch_commit_count',
        help = 'The number of Git commits on the project base branch.')
GIT_VERSION_BASE_BRANCH_TIME_COMPONENT = cobble.env.immutable_string_key(
        'git_version_base_branch_time_component',
        help = 'The time component of the project Git base branch.')
GIT_VERSION_FEATURE_BRANCH = cobble.env.immutable_string_key(
        'git_version_current_feature_branch',
        help = 'The project Git feature branch.')
GIT_VERSION_FEATURE_BRANCH_ORIGIN = cobble.env.immutable_string_key(
        'git_version_feature_origin',
        help = 'The origin revision of the project Git feature branch.')
GIT_VERSION_FEATURE_BRANCH_COMMIT_COUNT = cobble.env.immutable_string_key(
        'git_version_feature_branch_commit_count',
        help = 'The number of Git commits on the project feature branch.')
GIT_VERSION_FEATURE_BRANCH_TIME_COMPONENT = cobble.env.immutable_string_key(
        'git_version_feature_branch_time_component',
        help = 'The time component of the project Git feature branch.')
GIT_VERSION_COMPLETE_FIRST_ONLY_BASE_BRANCH_COMMIT_COUNT = \
        cobble.env.immutable_string_key(
            'git_version_complete_first_only_base_branch_commit_count',
            help = 'Uhh... \o/. Something base branch commit count.')
GIT_VERSION_LOCAL_CHANGES = cobble.env.immutable_string_key(
        'git_version_local_changes',
        help = 'A representation of local changes of the project Git branch.')

KEYS = frozenset([GIT_VERSION_CODE, GIT_VERSION_NAME,
        GIT_VERSION_REV_SHA1, GIT_VERSION_REV_SHA1_SHORT,
        GIT_VERSION_BASE_BRANCH, GIT_VERSION_BASE_BRANCH_COMMIT_COUNT,
        GIT_VERSION_BASE_BRANCH_TIME_COMPONENT,
        GIT_VERSION_FEATURE_BRANCH, GIT_VERSION_FEATURE_BRANCH_ORIGIN,
        GIT_VERSION_FEATURE_BRANCH_COMMIT_COUNT,
        GIT_VERSION_FEATURE_BRANCH_TIME_COMPONENT,
        GIT_VERSION_COMPLETE_FIRST_ONLY_BASE_BRANCH_COMMIT_COUNT,
        GIT_VERSION_LOCAL_CHANGES])


def list_to_tuple(function):
    """Decorator function to turn a list into a tuple"""

    def wrapper(*args):
        args = [tuple(x) if type(x) == list else x for x in args]
        result = function(*args)
        result = tuple(result) if type(result) == list else result
        return result

    return wrapper


def parse_rev_list(rev_text):
    """Parse a string that looks like this into a shaw and a time:
    commit ceeaf2bc13b968c34f29159404604a7be3bf7d6f
    1633124754
    """
    parts = rev_text.split("\n")
    return Commit(parts[0].replace("commit", "").strip(), int(parts[1].strip()))


class Commit:
    """Simple representation of a commit as parsed from git output"""

    def __init__(self, sha: str, raw_date: int):
        if "commit" in sha:
            raise Exception
        self.sha = sha
        self.raw_date = raw_date

    def __str__(self):
        return f"Commit(sha1: {self.sha[0:7]},date: {self.raw_date})"

    @property
    def date(self):
        """Turn the raw time stap (seconds since the epoc) into a datetime"""
        return datetime.datetime.fromtimestamp(self.raw_date)


class LocalChanges:
    """Represent local changes in a queryable way"""

    def __init__(self, files_changed, additions, deletions):
        self.files_changed = int(files_changed)
        self.additions = int(additions)
        self.deletions = int(deletions)

    def __str__(self):
        return f"{self.files_changed} +{self.additions} -{self.deletions}"

    @property
    def short_stats(self) -> str:
        if self.files_changed + self.additions + self.deletions == 0:
            return "no changes"
        else:
            return (
                f"files changed: {self.files_changed}, additions(+):"
                f" {self.additions}, deletions(-): {self.deletions}"
            )


class GitClient:
    def __init__(self, cmd, working_dir):
        self.cmd = cmd
        self.working_dir = working_dir

    def rev_list(
        self, revision: Union[str, int], first_parent_only: bool = False
    ) -> List[Commit]:
        # git rev-list --pretty=%ct%n [--first-parent] <revision> --
        args = ["rev-list", "--pretty=%ct%n"]
        if first_parent_only:
            args.append("--first-parent")
        args.append(revision)
        # Note this disambiguates <revision> from <filename> for cases where the revision might
        # match a filename
        args.append("--")

        output = self._git(args)
        if not output:
            return []
        # Command returns a string like this:
        # λ git rev-list --pretty=%ct%n HEAD
        # commit ceeaf2bc13b968c34f29159404604a7be3bf7d6f
        # 1633124754
        #
        # commit b7af84ff00a946faf3bf17d9f1ea663b7c6fb4b2
        # 1632354944
        # we need  a list of commits that have sha and time
        # split at \n\n to get commits,
        commit_list = filter(
            None, (line.rstrip() for line in output.split("\n\n"))
        )
        test = list(map(parse_rev_list, commit_list))
        return test

    def sha1(self, revision: int) -> str:
        """Returns a full sha1 hash as a string or an empty string"""
        args = ["rev-parse", revision]

        output = self._git(args)

        # TODO: check for multi-line hash?
        return output.strip()

    def head_branch_name(self) -> str:
        args = ["symbolic-ref", "--short", "-q", "HEAD"]
        output = self._git(args)
        return output.strip()

    def local_changes(self, revision: int) -> LocalChanges:
        args = ["diff", "--shortstat", "HEAD"]
        if revision != "HEAD":
            return LocalChanges(0, 0, 0)
        output = self._git(args)
        return self._parse_diff_short_stat(output)

    def branch_local_or_remote(self, branch_name: str) -> Iterator[str]:
        args = ["branch", "--all", "--list", f"*{branch_name}"]
        output = self._git(args)

        branches = output.split("\n")
        for branch in branches:
            new_branch = branch.replace("* ", "")
            yield new_branch.strip()

    def _parse_diff_short_stat(self, text: str) -> LocalChanges:
        if not text:
            return LocalChanges(0, 0, 0)
        parts = map(lambda x: x.strip(), text.split(","))
        files_changed = 0
        additions = 0
        deletions = 0

        for part in parts:
            if "changed" in part:
                files_changed = self._starting_number(part)
            if "(+)" in part:
                additions = self._starting_number(part)
            if "(-)" in part:
                deletions = self._starting_number(part)
        return LocalChanges(files_changed, additions, deletions)

    @staticmethod
    def _starting_number(text: str) -> Optional[int]:
        matches = re.findall(r"\d+", text)
        return None if not matches else matches[0]

    # functools cache can't take a list since it isn't hashable and immutable.
    # To get around this without changing everything everywhere we use
    # this decorator to turn the list into a tuple which is immutable and hashable
    # and then turn it back into a list as we want to mutate it and pass it to the
    # subprocess
    # We do this before using functools cache decorator
    #@list_to_tuple
    #@cache
    def _git(
        self, args: Union[List[str], Tuple[str]]
    ) -> subprocess.CompletedProcess:
        args = [self.cmd] + list(args)
        result = subprocess.run(
            args,
            check=True,
            capture_output=True,
            cwd=self.working_dir,
            text=True
        )
        return result.stdout


class GitVersionerConfig:
    def __init__(
        self, cmd, base_branch, repo_path, year_factor, stop_debounce, name, rev
    ):
        self.cmd = cmd
        self.base_branch = base_branch.strip()
        self.repo_path = repo_path
        self.year_factor = year_factor
        self.stop_debounce = stop_debounce
        self.name = name.strip()
        self.rev = rev.strip()


class GitVersioner:
    def __init__(self, config: GitVersionerConfig):
        self.DEFAULT_BRANCH = "main"
        self.DEFAULT_YEAR_FACTOR = 1000
        self.DEFAULT_STOP_DEBOUNCE = 48

        self.config = config
        self.git_client = GitClient(config.cmd, config.repo_path)

    @classmethod
    def from_config(cls, config: GitVersionerConfig):
        return cls(config)

    @cached_property
    def revision(self) -> int:
        commits = self.base_branch_commits
        time_component = self.base_branch_time_component
        return len(commits) + time_component

    @property
    def name(self) -> str:
        name = ""
        if self.config.name and (self.config.name != self.config.base_branch):
            name = f"_{self.config.name}"
        if self.config.rev == "HEAD":
            branch = self.head_branch_name
            if (branch is not None) and (branch != self.config.base_branch):
                name = f"_{branch}"
        else:
            if (
                not self.config.rev.startswith(self.sha_short)
                and self.config.rev != self.config.base_branch
            ):
                name = f"_{self.config.rev}"
            if self.config.name and self.config.name != self.config.base_branch:
                name = f"_{self.config.name}"
        return name

    @property
    def version_name(self) -> str:
        rev = self.revision
        hash_ = self.sha_short
        additional_commits = self.feature_branch_commits
        name = self.name
        dirty_part = ""
        further_part = (
            f"+{len(additional_commits)}" if additional_commits else ""
        )

        if self.config.rev == "HEAD":
            changes = (
                "files changed"
                in self.git_client.local_changes(self.config.rev).short_stats
            )
            dirty_part = f"-dirty" if changes else ""

        return f"{rev}{name}{further_part}_{hash_}{dirty_part}"

    @property
    def all_first_base_branch_commits(self) -> List[Commit]:
        base = list(
            self.git_client.branch_local_or_remote(self.config.base_branch)
        )[0]
        commits = self.git_client.rev_list(base, first_parent_only=True)
        return commits

    @property
    def head_branch_name(self) -> str:
        return self.git_client.head_branch_name()

    @property
    def sha1(self) -> str:
        return self.git_client.sha1(self.config.rev)

    @property
    def sha_short(self) -> str:
        return self.sha1[0:7]

    @property
    def local_changes(self) -> LocalChanges:
        return self.git_client.local_changes(self.config.rev)

    def commits(self) -> List[Commit]:
        return self.git_client.rev_list(self.config.rev)

    @property
    def feature_branch_origin(self) -> Optional[Commit]:
        first_base_commits = self.all_first_base_branch_commits
        all_head_commits = self.commits()

        first_base_sha_list = [x.sha for x in first_base_commits]
        for commit in all_head_commits:
            if commit.sha in first_base_sha_list:
                return commit
        return None

    @property
    def base_branch_commits(self) -> List[Commit]:
        origin = self.feature_branch_origin
        if origin is None:
            return []
        else:
            return self.git_client.rev_list(origin.sha)

    @property
    def feature_branch_commits(self) -> List[Commit]:
        origin = self.feature_branch_origin
        if origin is not None:
            return self.git_client.rev_list(f"{self.config.rev}...{origin.sha}")
        else:
            return self.commits()

    @property
    def base_branch_time_component(self) -> int:
        commits = self.base_branch_commits
        return self._time_component(commits)

    @property
    def feature_branch_time_component(self) -> int:
        commits = self.feature_branch_commits
        return self._time_component(commits)

    def _time_component(self, commits: List[Commit]) -> int:
        if not commits:
            return 0
        complete_time = commits[0].date - commits[-1].date
        if complete_time == datetime.timedelta(seconds=0):
            return 0

        # accumulate large gaps as a time delta?
        gaps = datetime.timedelta(seconds=0)
        for idx, commit in enumerate(commits[1:-1], start=1):
            # rev-list comes in reversed order
            next_commit = commits[idx - 1]
            diff = next_commit.date - commit.date
            diff_hours = diff.total_seconds() // 3600
            if diff_hours >= self.config.stop_debounce:
                gaps += diff
        # remove large gaps
        working_time = complete_time - gaps
        return self._year_factor(working_time)

    def _year_factor(self, duration: datetime.timedelta) -> int:
        one_year = datetime.timedelta(days=365)
        return round(
            (duration.total_seconds() * self.config.year_factor)
            / one_year.total_seconds()
            + 0.5
        )

def key_values(versioner):
    return {
        GIT_VERSION_CODE.name: str(versioner.revision),
        GIT_VERSION_NAME.name: versioner.version_name,
        GIT_VERSION_REV_SHA1.name: versioner.sha1,
        GIT_VERSION_REV_SHA1_SHORT.name: versioner.sha_short,
        GIT_VERSION_BASE_BRANCH.name: versioner.config.base_branch,
        GIT_VERSION_BASE_BRANCH_COMMIT_COUNT.name: \
            str(len(versioner.base_branch_commits)),
        GIT_VERSION_BASE_BRANCH_TIME_COMPONENT.name: \
            str(versioner.base_branch_time_component),
        GIT_VERSION_FEATURE_BRANCH.name: versioner.head_branch_name,
        GIT_VERSION_FEATURE_BRANCH_COMMIT_COUNT.name: \
            str(len(versioner.feature_branch_commits)),
        GIT_VERSION_FEATURE_BRANCH_TIME_COMPONENT.name: \
            str(versioner.feature_branch_time_component),
        GIT_VERSION_FEATURE_BRANCH_ORIGIN.name: \
            versioner.feature_branch_origin.sha,
        GIT_VERSION_COMPLETE_FIRST_ONLY_BASE_BRANCH_COMMIT_COUNT.name: \
            str(len(versioner.all_first_base_branch_commits)),
        GIT_VERSION_LOCAL_CHANGES.name: str(versioner.local_changes),
    }

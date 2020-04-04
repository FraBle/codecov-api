import asyncio
import logging
import functools

from collections import Counter

from django.utils.functional import cached_property

from covreports.reports.resources import ReportFile

from services.archive import ReportService
from core.models import Commit
from services.repo_providers import RepoProviderService


log = logging.getLogger(__name__)


def _is_added(line_value):
    return line_value and line_value[0] == "+"


def _is_removed(line_value):
    return line_value and line_value[0] == "-"


class FileComparisonTraverseManager:
    """
    The FileComparisonTraverseManager uses the visitor-pattern to execute a series
    of arbitrary actions on each line in a FileComparison. The main entrypoint to
    this class is the '.apply()' method, which is the only method client code should invoke.
    """
    def __init__(self, head_file_eof=0, base_file_eof=0, segments=[], src=[]):
        """
        head_file_eof -- end-line of the head_file we are traversing, plus 1
        base_file_eof -- same as above, for base_file

        ^^ Generally client code should supply both, except in a couple cases:
          1. The file is newly tracked. In this case, there is no base file, so we should
             iterate only over the head file lines.
          2. The file is deleted. As of right now (4/2/2020), we don't show deleted files in 
             comparisons, but if we were to support that, we would not supply a head_file_eof
             and instead only iterate over lines in the base file.

        segments -- these come from the provider API response related to the comparison, and
            constitute the 'diff' between the base and head references. Each segment takes this form:

            {
                "header": [
                    base reference offset,
                    number of lines in file-segment before changes applied,
                    head reference offset,
                    number of lines in file-segment after changes applied
                ],
                "lines": [ # line values for lines in the diff
                  "+this is an added line",
                  "-this is a removed line",
                  "this line is unchanged in the diff",
                  ...
                ]
            }

            The segment["header"], also known as the hunk-header (https://en.wikipedia.org/wiki/Diff#Unified_format),
            is an array of strings, which is why we have to use the int() builtin function
            to compare with self.head_ln and self.base_ln. It is used by this algorithm to
              1. Set initial values for the self.base_ln and self.head_ln line-counters, and
              2. Detect if self.base and/or self.head refer to lines in the diff at any given time

            This algorithm relies on the fact that segments are returned in ascending
            order for each file, which means that the "nearest" segment to the current line
            being traversed is located at segments[0].

        src -- this is the source code of the file at the head-reference, where each line
            is a cell in the array. If we are not traversing a segment, and src is provided,
            the line value passed to the visitors will be the line at src[self.head_ln - 1].
        """
        if src:
            assert head_file_eof - 1 == len(src), "If source provided, it must be full source"

        self.head_file_eof = head_file_eof
        self.base_file_eof = base_file_eof
        self.segments = segments
        self.src = src

        if self.segments:
            # Base offsets can be 0 if files are added or removed
            self.base_ln, self.head_ln = min(1, int(self.segments[0]["header"][0])), min(1, int(self.segments[0]["header"][2]))
        else:
            self.base_ln, self.head_ln = 1, 1

    def traverse_finished(self):
        return self.base_ln >= self.base_file_eof and self.head_ln >= self.head_file_eof and not self.traversing_diff()

    def traversing_diff(self):
        if self.segments == []:
            return False

        base_ln_within_offset = (
            int(self.segments[0]["header"][0])
            <= self.base_ln
            < int(self.segments[0]["header"][0]) + int(self.segments[0]["header"][1] or 1)
        )
        head_ln_within_offset = (
            int(self.segments[0]["header"][2])
            <= self.head_ln
            < int(self.segments[0]["header"][2]) + int(self.segments[0]["header"][3] or 1)
        )
        return base_ln_within_offset or head_ln_within_offset

    def pop_line(self):
        if self.traversing_diff():
            return self.segments[0]["lines"].pop(0)

        if self.src:
            return self.src[self.head_ln - 1]

    def apply(self, visitors):
        """
        Traverses the lines in a file comparison while accounting for the diff.
        If a line only appears in the base file (removed in head), it is prefixed
        with '-', and we only increment self.base_ln. If a line only appears in
        the head file, it is newly added and prefixed with '+', and we only
        increment self.head_ln.

        visitors -- A list of visitors applied to each line.
        """
        while not self.traverse_finished():
            line_value = self.pop_line()

            for visitor in visitors:
                visitor(
                    None if _is_added(line_value) else self.base_ln,
                    None if _is_removed(line_value) else self.head_ln,
                    line_value,
                    self.traversing_diff() # TODO(pierce): remove when upon combining diff + changes tabs in UI
                )

            if _is_added(line_value):
                self.head_ln += 1
            elif _is_removed(line_value):
                self.base_ln += 1
            else:
                self.head_ln += 1
                self.base_ln += 1

            if self.segments and not self.segments[0]["lines"]:
                # Either the segment has no lines (and is therefore of no use)
                # or all lines have been popped and visited, which means we are
                # done traversing it
                self.segments.pop(0)


class FileComparisonVisitor:
    """
    Abstract class with a convenience method for getting lines amongst
    all the edge cases.
    """

    def _get_lines(self, base_ln, head_ln):
        base_line, head_line = None, None

        if base_ln and isinstance(self.base_file, ReportFile):
            if base_ln in self.base_file:
                base_line = self.base_file[base_ln]

        if head_ln and isinstance(self.head_file, ReportFile):
            if head_ln in self.head_file:
                head_line = self.head_file[head_ln]

        return base_line, head_line

    def __call__(self, base_ln, head_ln, value, is_diff):
        pass


class CreateLineComparisonVisitor(FileComparisonVisitor):
    """
    A visitor that creates LineComparisons, and stores the
    result in self.lines. Only operates on lines that have
    code-values derived from segments or src in FileComparisonTraverseManager.
    """
    def __init__(self, base_file, head_file):
        self.base_file, self.head_file = base_file, head_file
        self.lines = []

    def __call__(self, base_ln, head_ln, value, is_diff):
        if value is None:
            return

        base_line, head_line = self._get_lines(base_ln, head_ln)

        self.lines.append(
            LineComparison(
                base_line=base_line,
                head_line=head_line,
                base_ln=base_ln,
                head_ln=head_ln,
                value=value,
                is_diff=is_diff
            )
        )


class CreateChangeSummaryVisitor(FileComparisonVisitor):
    """
    A visitor for summarizing the "unexpected coverage changes"
    to a certain file. We specifically ignore lines that are changed
    in the source code, which are prefixed with '+' or '-'. Result
    is stored in self.summary.
    """
    def __init__(self, base_file, head_file):
        self.base_file, self.head_file = base_file, head_file
        self.summary = Counter()

    def _get_coverage_type(self, integer_representation):
        if integer_representation == 0:
            return "misses"
        if integer_representation == 1:
            return "hits"
        if integer_representation == 2:
            return "partials"

    def __call__(self, base_ln, head_ln, value, is_diff):
        if value and value[0] in ["+", "-"]:
            return

        base_line, head_line = self._get_lines(base_ln, head_ln)
        if base_line is None or head_line is None:
            return

        if base_line.coverage == head_line.coverage:
            return

        self.summary[self._get_coverage_type(base_line.coverage)] -= 1
        self.summary[self._get_coverage_type(head_line.coverage)] += 1


class LineComparison:
    def __init__(self, base_line, head_line, base_ln, head_ln, value, is_diff):
        self.base_line = base_line
        self.head_line = head_line
        self.head_ln = head_ln
        self.base_ln = base_ln
        self.value = value
        self.is_diff = is_diff

        self.added = _is_added(value)
        self.removed = _is_removed(value)

    @property
    def number(self):
        return {
            "base": self.base_ln if not self.added else None,
            "head": self.head_ln if not self.removed else None
        }

    @property
    def coverage(self):
        return {
            "base": None if self.added or not self.base_line else self.base_line.coverage,
            "head": None if self.removed or not self.head_line else self.head_line.coverage
        }

    @property
    def sessions(self):
        if self.head_line is not None:
            return functools.reduce(
                lambda a, b: a + b,
                [session.coverage for session in self.head_line.sessions if session.coverage == 1]
            )


class FileComparison:
    def __init__(self, base_file, head_file, diff_data=None, src=[]):
        self.base_file = base_file
        self.head_file = head_file
        self.diff_data = diff_data
        self.src = src

    @property
    def name(self):
        return {
            "base": self.base_file.name if self.base_file is not None else None,
            "head": self.head_file.name if self.head_file is not None else None
        }

    @property
    def totals(self):
        return {
            "base": self.base_file.totals if self.base_file is not None else None,
            "head": self.head_file.totals if self.head_file is not None else None
        }

    @property
    def has_diff(self):
        return self.diff_data is not None

    @property
    def stats(self):
        return self.diff_data["stats"] if self.diff_data else None

    @cached_property
    def _calculated_changes_and_lines(self):
        change_summary_visitor = CreateChangeSummaryVisitor(self.base_file, self.head_file)
        create_lines_visitor = CreateLineComparisonVisitor(self.base_file, self.head_file)

        FileComparisonTraverseManager(
            head_file_eof=self.head_file.eof if self.head_file is not None else 0,
            base_file_eof=self.base_file.eof if self.base_file is not None else 0,
            segments=self.diff_data["segments"] if self.diff_data else [],
            src=self.src
        ).apply([change_summary_visitor, create_lines_visitor])

        return change_summary_visitor.summary, create_lines_visitor.lines

    @cached_property
    def change_summary(self):
        return self._calculated_changes_and_lines[0]

    @cached_property
    def lines(self):
        return self._calculated_changes_and_lines[1]


class Comparison(object):

    def __init__(self, base_commit, head_commit, user):
        self.user = user
        self.base_commit = base_commit
        self.head_commit = head_commit
        self.report_service = ReportService()
        self._base_report = None
        self._git_comparison = None
        self._head_report = None
        self._git_commits = None
        self._upload_commits = None

    @cached_property
    def files(self):
        files = []
        for f in self.head_report.file_reports():
            diff_data = self.git_comparison["diff"]["files"].get(f.name)
            base_file = self.base_report.get(f.name)
            if diff_data and not base_file:
                base_file = self.base_report.get(diff_data.get("before"))
            files.append(
                FileComparison(head_file=f, base_file=base_file, diff_data=diff_data)
            )
        return files

    @property
    def git_comparison(self):
        if self._git_comparison is None:
            self._git_comparison = self._calculate_git_comparison()
        return self._git_comparison

    @property
    def base_report(self):
        if self._base_report is None:
            self._base_report = self._calculate_base_report()
        return self._base_report

    @property
    def head_report(self):
        if self._head_report is None:
            self._head_report = self._calculate_head_report()
        return self._head_report

    @property
    def git_commits(self):
        """
            Returns the complete git commits between base and head.
            :return: list of commit info with objects
        """
        if self._git_commits is None:
            self._calculate_git_commits()
        return self._git_commits

    @property
    def upload_commits(self):
        """
            Returns the commits that have uploads between base and head.
            :return: Queryset of core.models.Commit objects
        """
        commit_ids = [commit['commitid'] for commit in self.git_commits]
        commits_queryset = Commit.objects.filter(commitid__in=commit_ids,
                                                 repository=self.base_commit.repository)
        commits_queryset.exclude(deleted=True)
        return commits_queryset

    def file_diff(self, file_path):
        diff = self.git_comparison['diff']['files']
        if file_path in diff:
            return dict(src_diff=diff[file_path],
                        base_coverage=self.base_report.get(filename=file_path, _else=None),
                        head_coverage=self.head_report.get(filename=file_path, _else=None))

    def _calculate_git_commits(self):
        commits = self.git_comparison['commits']
        self._git_commits = commits
        return self._git_commits

    def _calculate_git_comparison(self):
        loop = asyncio.get_event_loop()
        base_commit_sha = self.base_commit.commitid
        head_commit_sha = self.head_commit.commitid
        task = RepoProviderService().get_adapter(
            self.user, self.base_commit.repository).get_compare(base_commit_sha, head_commit_sha)
        return loop.run_until_complete(task)

    def _calculate_base_report(self):
        return self.report_service.build_report_from_commit(self.base_commit)

    def _calculate_head_report(self):
        return self.report_service.build_report_from_commit(self.head_commit)

    def flag_comparison(self, flag_name):
        return FlagComparison(self, flag_name)

    @property
    def available_flags(self):
        return self.head_report.flags.keys()


class FlagComparison(object):

    def __init__(self, comparison, flag_name):
        self.comparison = comparison
        self.flag_name = flag_name

    @property
    def head_report(self):
        return self.comparison.head_report.flags.get(self.flag_name)

    @property
    def base_report(self):
        return self.comparison.base_report.flags.get(self.flag_name)

    @property
    def diff_totals(self):
        if self.head_report is None:
            return None
        git_comparison = self.comparison.git_comparison
        return self.head_report.apply_diff(git_comparison['diff'])
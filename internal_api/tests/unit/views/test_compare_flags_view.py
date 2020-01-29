import json
from pathlib import Path
from unittest.mock import patch, PropertyMock

from django.test import override_settings
from rest_framework.reverse import reverse

from internal_api.tests.unit.views.test_compare_file_view import build_commits_with_changes
from core.tests.factories import PullFactory, RepositoryFactory, CommitFactory
from covreports.utils.tuples import ReportTotals
from codecov.tests.base_test import InternalAPITest
from archive.services import ArchiveService
from compare.services import FlagComparison


current_file = Path(__file__)


@patch('archive.services.ArchiveService.read_chunks')
@patch('archive.services.ArchiveService.create_root_storage')
@patch('compare.services.FlagComparison.diff_totals', new_callable=PropertyMock)
class TestCompareFlagsView(InternalAPITest):
    def _get_compare_flags(self, kwargs, query_params):
        return self.client.get(reverse('compare-flags', kwargs=kwargs), data=query_params)

    def setUp(self):
        self.repo = RepositoryFactory.create(author__username='ThiagoCodecov')
        self.parent_commit = CommitFactory.create(
            commitid='00c7b4b49778b3c79427f9c4c13a8612a376ff19',
            repository=self.repo
        )
        self.commit = CommitFactory.create(
            message='test_report_serializer',
            commitid='68946ef98daec68c7798459150982fc799c87d85',
            parent_commit_id=self.parent_commit.commitid,
            repository=self.repo
        )

        self.client.force_login(self.repo.author)

    def test_compare_flags___success(
        self,
        diff_totals_mock, 
        create_root_storage_mock,
        read_chunks_mock
    ):
        head_chunks = open(
            current_file.parent.parent.parent / f'samples/{self.commit.commitid}_chunks.txt',
            'r'
        ).read()
        base_chunks = open(
            current_file.parent.parent.parent / f'samples/{self.parent_commit.commitid}_chunks.txt',
            'r'
        ).read()
        read_chunks_mock.side_effect = lambda x: head_chunks if x == self.commit.commitid else base_chunks
        diff_totals_mock.return_value = ReportTotals(
            files=0,
            lines=0,
            hits=0,
            misses=0,
            partials=0,
            coverage='0',
            branches=0,
            methods=0,
            messages=0,
            sessions=0,
            complexity=0,
            complexity_total=0,
            diff=0
        )
        response = self._get_compare_flags(
            kwargs={
                "orgName": self.repo.author.username,
                "repoName": self.repo.name,
            },
            query_params={
                "base": self.parent_commit.commitid,
                "head": self.commit.commitid
            }
        )

        assert response.status_code == 200

        expected_result = {
            'count': 2,
            'next': None,
            'previous': None,
            'results': [
                {
                    'base_report_totals': {
                        'branches': 0,
                        'complexity': 0,
                        'complexity_total': 0,
                        'coverage': '79.16667',
                        'diff': 0,
                        'files': 3,
                        'hits': 19,
                        'lines': 24,
                        'messages': 0,
                        'methods': 0,
                        'misses': 5,
                        'partials': 0,
                        'sessions': 2
                    },
                    'diff_totals': {
                        'branches': 0,
                        'complexity': 0,
                        'complexity_total': 0,
                        'coverage': '0',
                        'diff': 0,
                        'files': 0,
                        'hits': 0,
                        'lines': 0,
                        'messages': 0,
                        'methods': 0,
                        'misses': 0,
                        'partials': 0,
                        'sessions': 0
                    },
                    'head_report_totals': {
                        'branches': 0,
                        'complexity': 0,
                        'complexity_total': 0,
                        'coverage': '80.00000',
                        'diff': 0,
                        'files': 3,
                        'hits': 20,
                        'lines': 25,
                        'messages': 0,
                        'methods': 0,
                        'misses': 5,
                        'partials': 0,
                        'sessions': 2
                    },
                    'name': 'unittests'
                },
                {
                    'base_report_totals': {
                        'branches': 0,
                        'complexity': 0,
                        'complexity_total': 0,
                        'coverage': '79.16667',
                        'diff': 0,
                        'files': 3,
                        'hits': 19,
                        'lines': 24,
                        'messages': 0,
                        'methods': 0,
                        'misses': 5,
                        'partials': 0,
                        'sessions': 2
                    },
                    'diff_totals': {
                        'branches': 0,
                        'complexity': 0,
                        'complexity_total': 0,
                        'coverage': '0',
                        'diff': 0,
                        'files': 0,
                        'hits': 0,
                        'lines': 0,
                        'messages': 0,
                        'methods': 0,
                        'misses': 0,
                        'partials': 0,
                        'sessions': 0
                    },
                    'head_report_totals': {
                        'branches': 0,
                        'complexity': 0,
                        'complexity_total': 0,
                        'coverage': '56.00000',
                        'diff': 0,
                        'files': 3,
                        'hits': 14,
                        'lines': 25,
                        'messages': 0,
                        'methods': 0,
                        'misses': 11,
                        'partials': 0,
                        'sessions': 2
                    },
                    'name': 'integrations'
                }
            ]
        }

        assert response.data == expected_result

    def test_compare_flags_view_accepts_pullid_query_param(
        self,
        diff_totals_mock,
        root_storage_mock,
        read_chunks_mock
    ):
        read_chunks_mock.return_value = ""
        diff_totals_mock.return_value = ReportTotals()

        response = self._get_compare_flags(
            kwargs={
                "orgName": self.repo.author.username,
                "repoName": self.repo.name
            },
            query_params={
                "pullid": PullFactory(
                    base=self.parent_commit,
                    head=self.commit,
                    pullid=2,
                    author=self.commit.author,
                    repository=self.repo
                ).pullid
            }
        )

        assert response.status_code == 200

    @patch('compare.services.FlagComparison.base_report', new_callable=PropertyMock)
    def test_compare_flags_doesnt_crash_if_base_doesnt_have_flags(
        self,
        base_flag_mock,
        diff_totals_mock,
        root_storage_mock,
        read_chunks_mock
    ):
        read_chunks_mock.return_value = ""
        base_flag_mock.return_value = None
        diff_totals_mock.return_value = ReportTotals()

        # should not crash
        response = self._get_compare_flags(
            kwargs={
                "orgName": self.repo.author.username,
                "repoName": self.repo.name
            },
            query_params={
                "base": self.parent_commit.commitid,
                "head": self.commit.commitid
            }
        )
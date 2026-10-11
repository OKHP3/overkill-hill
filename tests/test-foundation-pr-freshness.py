import contextlib
import importlib.util
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'check-foundation-pr-freshness.py'
SPEC = importlib.util.spec_from_file_location('check_foundation_pr_freshness', SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)
PAGES = (ROOT / '.github/workflows/pages.yml').read_text(encoding='utf-8')
VALIDATE = (ROOT / '.github/workflows/validate.yml').read_text(encoding='utf-8')


def workflow_job(source, name):
    match = re.search(
        rf'^  {re.escape(name)}:\n(.*?)(?=^  [\w-]+:|\Z)',
        source,
        re.M | re.S,
    )
    if not match:
        raise AssertionError(f'missing workflow job {name}')
    return match.group(1)


def open_pr_summary(number=43, branch='agent/foundation-sync-20261006'):
    return {
        'number': number,
        'base': {'ref': 'main'},
        'head': {'ref': branch},
    }


def open_pr_detail(
    number=43,
    branch='agent/foundation-sync-20261006',
    head_sha='2' * 40,
    mergeable=True,
    mergeable_state='clean',
):
    return {
        'number': number,
        'state': 'open',
        'draft': False,
        'mergeable': mergeable,
        'mergeable_state': mergeable_state,
        'base': {'ref': 'main', 'sha': '3' * 40},
        'head': {'ref': branch, 'sha': head_sha},
    }


class FoundationFreshnessTests(unittest.TestCase):
    def collect_open(self, detail, comparison):
        main_sha = '1' * 40

        def get_json(path):
            if path.endswith('/branches/main'):
                return {'commit': {'sha': main_sha}}
            if '/pulls?' in path:
                return [open_pr_summary(number=detail['number'])]
            if path.endswith(f"/pulls/{detail['number']}"):
                return detail
            if '/compare/' in path:
                return comparison
            raise AssertionError(f'unexpected API request: {path}')

        return MODULE.collect_report(get_json)

    def test_open_foundation_pr_on_second_page_is_reported(self):
        main_sha = '1' * 40
        detail = open_pr_detail(number=143)
        requested_pages = []

        def get_json(path):
            if path.endswith('/branches/main'):
                return {'commit': {'sha': main_sha}}
            if '/pulls?' in path:
                page = int(parse_qs(urlsplit(path).query)['page'][0])
                requested_pages.append(page)
                if page == 1:
                    return [
                        open_pr_summary(number=number, branch='feature/unrelated')
                        for number in range(1, MODULE.PAGE_SIZE + 1)
                    ]
                if page == 2:
                    return [open_pr_summary(number=detail['number'])]
                raise AssertionError(f'unexpected page: {page}')
            if path.endswith(f"/pulls/{detail['number']}"):
                return detail
            if '/compare/' in path:
                return {
                    'status': 'identical',
                    'ahead_by': 0,
                    'behind_by': 0,
                    'merge_base_commit': {'sha': main_sha},
                }
            raise AssertionError(f'unexpected API request: {path}')

        report = MODULE.collect_report(get_json)

        self.assertEqual(requested_pages, [1, 2])
        self.assertEqual(report['status'], 'CURRENT')
        self.assertEqual(
            [check['number'] for check in report['openFoundationPullRequests']],
            [detail['number']],
        )

    def test_full_thousand_pr_scan_limit_is_reported_as_incomplete(self):
        requested_pages = []

        def get_json(path):
            if path.endswith('/branches/main'):
                return {'commit': {'sha': '1' * 40}}
            if '/pulls?' in path:
                page = int(parse_qs(urlsplit(path).query)['page'][0])
                requested_pages.append(page)
                return [
                    open_pr_summary(number=number, branch='feature/unrelated')
                    for number in range(
                        (page - 1) * MODULE.PAGE_SIZE + 1,
                        page * MODULE.PAGE_SIZE + 1,
                    )
                ]
            raise AssertionError(f'unexpected API request: {path}')

        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / 'freshness.json'
            summary_path = Path(directory) / 'summary.md'
            with patch.object(MODULE, 'api_get', side_effect=get_json):
                result = MODULE.main([
                    '--report',
                    str(report_path),
                    '--summary',
                    str(summary_path),
                ])

            report = json.loads(report_path.read_text(encoding='utf-8'))
            summary = summary_path.read_text(encoding='utf-8')

        self.assertEqual(requested_pages, list(range(1, 11)))
        self.assertEqual(result, 2)
        self.assertEqual(report['status'], 'ERROR')
        self.assertIn('scan was incomplete', report['error'])
        self.assertNotEqual(report['status'], 'NO_OPEN_FOUNDATION_PR')
        self.assertIn('status is unavailable', summary)
        self.assertNotIn('No open foundation-sync pull request', summary)
        self.assertIn('Do not treat this error', summary)

    def test_behind_open_pr_reports_current_revision_and_safe_update_action(self):
        current_sha = '1' * 40
        report = self.collect_open(
            open_pr_detail(mergeable=True, mergeable_state='behind'),
            {
                'status': 'behind',
                'ahead_by': 3,
                'behind_by': 4,
                'merge_base_commit': {'sha': '4' * 40},
            },
        )

        check = report['openFoundationPullRequests'][0]
        self.assertEqual(report['status'], 'BEHIND')
        self.assertEqual(report['currentBaseRevision'], current_sha)
        self.assertEqual(check['comparison']['behindBy'], 4)
        self.assertIn(current_sha, check['requiredAction'])
        self.assertIn('protected PR', check['requiredAction'])
        self.assertIn('review conversations', check['requiredAction'])
        self.assertNotIn('merge this branch', check['requiredAction'].lower())
        summary = MODULE.render_summary(report)
        self.assertIn(f'Current Glee main revision: `{current_sha}`', summary)
        self.assertIn('- Required action:', summary)

    def test_conflicting_open_pr_names_resolution_without_bypassing_protection(self):
        report = self.collect_open(
            open_pr_detail(mergeable=False, mergeable_state='dirty'),
            {
                'status': 'diverged',
                'ahead_by': 1,
                'behind_by': 2,
                'merge_base_commit': {'sha': '4' * 40},
            },
        )
        check = report['openFoundationPullRequests'][0]
        self.assertEqual(report['status'], 'CONFLICT')
        self.assertIn('resolve the conflicts', check['requiredAction'])
        self.assertIn('protected PR', check['requiredAction'])
        self.assertIn('review conversations', check['requiredAction'])

    def test_unknown_mergeability_is_not_reported_as_current(self):
        report = self.collect_open(
            open_pr_detail(mergeable=None, mergeable_state='unknown'),
            {
                'status': 'identical',
                'ahead_by': 0,
                'behind_by': 0,
                'merge_base_commit': {'sha': '1' * 40},
            },
        )
        self.assertEqual(report['status'], 'UNKNOWN')
        self.assertIn(
            'Do not treat unknown status as approval',
            report['openFoundationPullRequests'][0]['requiredAction'],
        )
        self.assertEqual(MODULE.exit_code(report), 2)

    def test_already_merged_pr_is_not_mistaken_for_a_stale_open_candidate(self):
        main_sha = '1' * 40
        historical = {
            'number': 42,
            'state': 'closed',
            'merged_at': '2026-09-16T18:56:11Z',
            'merge_commit_sha': '5' * 40,
            'base': {'ref': 'main', 'sha': '6' * 40},
            'head': {
                'ref': 'agent/foundation-sync-20260909',
                'sha': '7' * 40,
            },
        }

        def get_json(path):
            if path.endswith('/branches/main'):
                return {'commit': {'sha': main_sha}}
            if '/pulls?' in path:
                return []
            if path.endswith('/pulls/42'):
                return historical
            if '/compare/' in path:
                return {
                    'status': 'behind',
                    'ahead_by': 0,
                    'behind_by': 217,
                    'merge_base_commit': {'sha': '7' * 40},
                }
            raise AssertionError(f'unexpected API request: {path}')

        report = MODULE.collect_report(get_json)
        self.assertEqual(report['status'], 'NO_OPEN_FOUNDATION_PR')
        self.assertEqual(report['currentBaseRevision'], main_sha)
        self.assertEqual(report['historicalPullRequest']['status'], 'MERGED')
        self.assertEqual(
            report['historicalPullRequest']['comparison']['behindBy'],
            217,
        )
        self.assertIn('No rebase or update is required', report['requiredAction'])
        self.assertIn(main_sha, report['requiredAction'])
        self.assertEqual(MODULE.exit_code(report), 0)

    def test_api_requests_are_read_only_gets(self):
        response = io.BytesIO(b'{"default_branch":"main"}')
        response.__enter__ = lambda: response
        response.__exit__ = lambda *args: False
        with patch.object(MODULE, 'urlopen', return_value=response) as urlopen:
            result = MODULE.api_get('/repos/OKHP3/Glee-fullyTools')

        self.assertEqual(result['default_branch'], 'main')
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_method(), 'GET')
        self.assertNotIn('Authorization', request.headers)

    def test_api_timeout_is_reported_as_a_bounded_diagnostic_error(self):
        with patch.object(MODULE, 'urlopen', side_effect=TimeoutError()):
            with self.assertRaisesRegex(
                MODULE.GitHubAPIError,
                'TimeoutError',
            ):
                MODULE.api_get('/repos/OKHP3/Glee-fullyTools')

    def test_api_error_still_writes_report_and_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / 'freshness.json'
            summary_path = Path(directory) / 'summary.md'
            stdout = io.StringIO()
            with patch.object(
                MODULE,
                'collect_report',
                side_effect=MODULE.GitHubAPIError('GitHub API unavailable'),
            ), contextlib.redirect_stdout(stdout):
                result = MODULE.main([
                    '--report',
                    str(report_path),
                    '--summary',
                    str(summary_path),
                ])

            report = json.loads(report_path.read_text(encoding='utf-8'))
            summary = summary_path.read_text(encoding='utf-8')
            self.assertEqual(result, 2)
            self.assertEqual(report['status'], 'ERROR')
            self.assertIn('GitHub API unavailable', report['error'])
            self.assertIn('Do not treat this error', summary)
            self.assertIn('Glee foundation PR freshness', stdout.getvalue())

    def test_manual_diagnostic_is_not_activated_as_a_release_job(self):
        self.assertNotIn('foundation-freshness:', PAGES)
        self.assertIn('python3 tests/test-foundation-pr-freshness.py', VALIDATE)
        deploy_job = workflow_job(PAGES, 'deploy')
        self.assertIn('needs: validate', deploy_job)
        self.assertNotRegex(PAGES, r'(?i)\b(?:git\s+push|gh\s+pr\s+merge)\b')


if __name__ == '__main__':
    unittest.main()

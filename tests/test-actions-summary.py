"""Regression coverage for operator summaries, including mixed failures."""
import copy
import importlib.util
import json
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/write-actions-summary.py'
FIXTURE_GENERATOR = ROOT / 'scripts/generate-actions-summary-fixtures.py'
FIXTURE_DIRECTORY = ROOT / 'tests/fixtures/actions-summary'
EXTERNAL_RUNTIME_FIXTURES = {
    'external-runtime-pass.json': 'PASS',
    'external-runtime-degraded.json': 'EXTERNAL_OUTAGE',
    'external-runtime-local-failure.json': 'LOCAL_FAILURE',
    'external-runtime-mixed-failure.json': 'EXTERNAL_OUTAGE',
}
ARCHIVED_LIVE_EDGE_REPORTS = {
    ROOT / 'tests/fixtures/actions-summary/archived-live-edge-2026-09-07.json': 'current',
}
VERIFY_SPEC = importlib.util.spec_from_file_location(
    'verify_live_edge', ROOT / 'scripts/verify-live-edge.py'
)
if VERIFY_SPEC is None or VERIFY_SPEC.loader is None:
    raise RuntimeError('could not load scripts/verify-live-edge.py')
VERIFY = importlib.util.module_from_spec(VERIFY_SPEC)
VERIFY_SPEC.loader.exec_module(VERIFY)


class SummaryTests(unittest.TestCase):
    def load_fixture(self, name):
        return json.loads((FIXTURE_DIRECTORY / name).read_text(encoding='utf-8'))

    def test_committed_generated_fixtures_are_current(self):
        result = subprocess.run(
            [sys.executable, str(FIXTURE_GENERATOR), '--check'],
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            result.returncode,
            0,
            result.stdout + result.stderr,
        )

    def test_generated_fixture_check_detects_external_runtime_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory)
            generated = subprocess.run(
                [
                    sys.executable,
                    str(FIXTURE_GENERATOR),
                    '--write',
                    '--output-directory',
                    str(output_directory),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(generated.returncode, 0, generated.stdout + generated.stderr)

            fixture = output_directory / 'external-runtime-degraded.json'
            actual_content = fixture.read_text(encoding='utf-8').replace(
                '"status": "EXTERNAL_OUTAGE"',
                '"status": "PASS"',
                1,
            )
            fixture.write_text(actual_content, encoding='utf-8')
            checked = subprocess.run(
                [
                    sys.executable,
                    str(FIXTURE_GENERATOR),
                    '--check',
                    '--output-directory',
                    str(output_directory),
                ],
                capture_output=True,
                text=True,
            )
            unchanged_content = fixture.read_text(encoding='utf-8')

        self.assertEqual(checked.returncode, 1, checked.stdout + checked.stderr)
        self.assertIn('generated fixture is stale', checked.stdout + checked.stderr)
        self.assertIn('external-runtime-degraded.json', checked.stdout + checked.stderr)
        self.assertIn('--- expected/external-runtime-degraded.json', checked.stdout)
        self.assertIn('+++ actual/external-runtime-degraded.json', checked.stdout)
        self.assertIn('-  "status": "EXTERNAL_OUTAGE"', checked.stdout)
        self.assertIn('+  "status": "PASS"', checked.stdout)
        self.assertEqual(unchanged_content, actual_content)

    def test_generated_fixture_check_keeps_missing_and_unexpected_files_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory)
            unexpected = output_directory / 'external-runtime-untracked.json'
            unexpected.write_text('{}\n', encoding='utf-8')
            checked = subprocess.run(
                [
                    sys.executable,
                    str(FIXTURE_GENERATOR),
                    '--check',
                    '--output-directory',
                    str(output_directory),
                ],
                capture_output=True,
                text=True,
            )

        output = checked.stdout + checked.stderr
        self.assertEqual(checked.returncode, 1, output)
        self.assertIn('missing generated fixture:', output)
        self.assertIn('unexpected generated fixture:', output)
        self.assertIn('external-runtime-untracked.json', output)

    def test_external_runtime_fixtures_match_the_report_contract(self):
        for name, expected_status in EXTERNAL_RUNTIME_FIXTURES.items():
            with self.subTest(fixture=name):
                report = self.load_fixture(name)
                self.assertEqual(report['version'], 1)
                self.assertEqual(report['mode'], 'external-health')
                self.assertEqual(report['status'], expected_status)
                self.assertIsInstance(report['baseUrl'], str)
                self.assertEqual(len(report['routes']), report['summary']['routes'])
                self.assertEqual(len(report['dependencies']), report['summary']['dependencies'])
                self.assertEqual(
                    report['externalOutages'],
                    [
                        dependency for dependency in report['dependencies']
                        if dependency['state'] in {'unavailable', 'no-response'}
                    ],
                )
                summary = report['summary']
                self.assertEqual(
                    summary['available'],
                    sum(dependency['state'] == 'available'
                        for dependency in report['dependencies']),
                )
                self.assertEqual(summary['externalOutages'], len(report['externalOutages']))
                self.assertEqual(summary['localFailures'], len(report['localFailures']))
                self.assertEqual(summary['cspDiagnostics'], len(report['cspDiagnostics']))
                self.assertEqual(summary['cspEvidence'], len(report['cspEvidence']))
                self.assertEqual(summary['timeouts'], len(report['timeouts']))

    def test_committed_live_edge_fixtures_match_verifier_report_shape(self):
        fixtures = sorted(FIXTURE_DIRECTORY.glob('live-edge-*.json'))
        self.assertTrue(fixtures, 'expected at least one live-edge summary fixture')
        for fixture in fixtures:
            with self.subTest(fixture=fixture.name):
                try:
                    VERIFY.validate_report_shape(self.load_fixture(fixture.name))
                except ValueError as exc:
                    self.fail(f'{fixture.name} is not a live-edge report: {exc}')

    def test_malformed_live_edge_fixture_has_a_clear_shape_error(self):
        report = self.load_fixture('live-edge-failure.json')
        malformed = copy.deepcopy(report)
        del malformed['checks'][0]['evidence']

        with self.assertRaisesRegex(
            ValueError, r'checks\[0\] is missing required field\(s\): evidence'
        ):
            VERIFY.validate_report_shape(malformed)

    def run_summary(self, report, kind='edge', artifact_url=None):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'report.json'
            output = Path(directory) / 'summary.md'
            source.write_text(json.dumps(report), encoding='utf-8')
            command = [sys.executable, str(SCRIPT), '--kind', kind,
                       '--report', str(source), '--summary', str(output)]
            if artifact_url:
                command.extend(['--artifact-url', artifact_url])
            result = subprocess.run(command,
                                    capture_output=True, text=True)
            return result.returncode, output.read_text(encoding='utf-8') if output.exists() else ''

    def assert_archived_report_contract(self, path, report):
        contract = ARCHIVED_LIVE_EDGE_REPORTS.get(path)
        self.assertIn(
            contract,
            {'current', 'legacy'},
            f'{path} must be explicitly classified as current or legacy',
        )
        if contract == 'current':
            try:
                VERIFY.validate_report_shape(report)
            except ValueError as exc:
                self.fail(
                    f'{path} is classified as current but no longer matches the '
                    f'verifier contract: {exc}. Migrate the archived report or '
                    'declare and test legacy compatibility.'
                )

    def test_archived_live_edge_reports_have_an_explicit_contract(self):
        for path, contract in ARCHIVED_LIVE_EDGE_REPORTS.items():
            with self.subTest(report=path):
                report = json.loads(path.read_text(encoding='utf-8'))
                self.assert_archived_report_contract(path, report)
                self.assertIn(contract, {'current', 'legacy'})

    def test_archived_contract_drift_has_an_actionable_failure(self):
        path = next(iter(ARCHIVED_LIVE_EDGE_REPORTS))
        report = json.loads(path.read_text(encoding='utf-8'))
        del report['summary']['warnings']

        with self.assertRaisesRegex(
            AssertionError,
            r'Migrate the archived report or declare and test legacy compatibility',
        ):
            self.assert_archived_report_contract(path, report)

    def test_historical_partial_is_not_an_outage_or_full_policy_pass(self):
        path = ROOT / 'tests/fixtures/actions-summary/archived-live-edge-2026-09-07.json'
        report = json.loads(path.read_text())
        self.assert_archived_report_contract(path, report)
        code, summary = self.run_summary(report)
        self.assertEqual(code, 0)
        self.assertIn('| Content delivery | PASS |', summary)
        self.assertIn('| Edge policy | PARTIAL |', summary)
        self.assertIn('| External availability | NOT RUN |', summary)
        self.assertIn('ca38d5b9fc46746ea8b41e2ba32e39685c53f511', summary)
        self.assertLess(len(summary.splitlines()), 45)

    def test_generated_pass_fixture_renders_as_a_full_pass(self):
        code, summary = self.run_summary(self.load_fixture('live-edge-pass.json'))
        self.assertEqual(code, 0)
        self.assertIn('| Content delivery | PASS |', summary)
        self.assertIn('| Edge policy | PASS |', summary)

    def test_first_party_failure_remains_distinct(self):
        code, summary = self.run_summary({'checks': [
            {'check': 'route /', 'status': 'FAIL', 'evidence': 'HTTP 404'},
            {'check': 'route / observed header x-frame-options', 'status': 'WARN', 'evidence': 'absent; GitHub Pages may omit repository headers at the edge'}]})
        self.assertEqual(code, 1)
        self.assertIn('| Content delivery | FAILED |', summary)
        self.assertIn('HTTP 404', summary)

    def test_confirmed_live_edge_failures_remain_visible_in_their_area(self):
        code, summary = self.run_summary(self.load_fixture('live-edge-failure.json'))

        self.assertEqual(code, 1)
        self.assertIn('| Content delivery | FAILED |', summary)
        self.assertIn('| Edge policy | FAILED |', summary)
        self.assertIn('release manifest', summary)
        self.assertIn('x-frame-options', summary)
        self.assertIn('confirmed policy failures remain visible', summary)

    def test_confirmed_failure_links_to_uploaded_report_artifact(self):
        artifact_url = 'https://github.com/example/site/actions/runs/123/artifacts/456'
        code, summary = self.run_summary(
            self.load_fixture('live-edge-failure.json'), artifact_url=artifact_url
        )

        self.assertEqual(code, 1)
        self.assertIn(
            f'Full route evidence artifact: [report.json]({artifact_url})',
            summary,
        )

    def test_live_edge_workflows_pass_uploaded_artifact_url_to_summary(self):
        for workflow in ('.github/workflows/validate.yml', '.github/workflows/pages.yml'):
            with self.subTest(workflow=workflow):
                source = (ROOT / workflow).read_text(encoding='utf-8')
                self.assertIn('id: upload-live-edge-report', source)
                self.assertIn(
                    'steps.upload-live-edge-report.outputs.artifact-url',
                    source,
                )

    def test_external_workflow_passes_uploaded_artifact_url_to_summary(self):
        source = (ROOT / '.github/workflows/validate.yml').read_text(encoding='utf-8')
        self.assertIn('id: upload-third-party-runtime-report', source)
        self.assertIn(
            'steps.upload-third-party-runtime-report.outputs.artifact-url',
            source,
        )

    def test_validation_evidence_uploads_declare_retention_and_file_policy(self):
        for workflow in ('.github/workflows/validate.yml', '.github/workflows/pages.yml'):
            source = (ROOT / workflow).read_text(encoding='utf-8')
            upload_steps = re.findall(
                r'(?ms)^      - name: [^\n]+\n'
                r'(.*?)(?=^      - name: |\Z)',
                source,
            )
            artifact_steps = [
                step for step in upload_steps
                if 'uses: actions/upload-artifact@' in step
            ]
            self.assertTrue(artifact_steps, f'{workflow} has no diagnostic artifact uploads')
            for step in artifact_steps:
                self.assertRegex(
                    step,
                    r'(?m)^          if-no-files-found: (?:warn|error)$',
                )
                self.assertRegex(
                    step,
                    r'(?m)^          retention-days: [1-9][0-9]*$',
                )

        workflow = (ROOT / '.github/workflows/validate.yml').read_text(encoding='utf-8')
        local_qa = re.search(
            r'(?ms)^      - name: Upload local QA reports\n'
            r'(.*?)(?=^      - name: |\Z)',
            workflow,
        )
        self.assertIsNotNone(local_qa, 'missing local QA evidence upload step')
        self.assertIn('if-no-files-found: warn', local_qa.group(1))
        self.assertIn('retention-days: 7', local_qa.group(1))
        self.assertIn('test-results/responsive-qa/', local_qa.group(1))
        self.assertIn('test-results/audit-site/', local_qa.group(1))
        self.assertNotIn('site-release', local_qa.group(1))
        self.assertNotIn('third-party-runtime-report.json', local_qa.group(1))

    def test_failed_csp_fixtures_upload_only_the_short_lived_focused_report(self):
        workflow = (ROOT / '.github/workflows/validate.yml').read_text(encoding='utf-8')
        match = re.search(
            r'(?ms)^      - name: Upload failed CSP fixture report\n'
            r'(.*?)(?=^      - name: )',
            workflow,
        )
        self.assertIsNotNone(match, 'missing focused CSP fixture report upload step')
        upload = match.group(1)
        self.assertIn(
            "if: always() && steps.csp-fixtures.outcome == 'failure'",
            upload,
        )
        self.assertIn('id: upload-csp-fixture-report', upload)
        self.assertIn('uses: actions/upload-artifact@', upload)
        self.assertIn('path: csp-fixture-report.json', upload)
        self.assertIn('if-no-files-found: warn', upload)
        self.assertIn('retention-days: 7', upload)
        self.assertNotIn('third-party-runtime-report.json', upload)
        self.assertNotIn('site-release', upload)

        summary_step = re.search(
            r'(?ms)^      - name: Summarize failed CSP fixture regressions\n'
            r'(.*?)(?=^      - name: )',
            workflow,
        )
        self.assertIsNotNone(summary_step, 'missing focused CSP fixture summary step')
        summary = summary_step.group(1)
        self.assertIn('node scripts/csp-qa.mjs', summary)
        self.assertIn('--fixture-summary=csp-fixture-report.json', summary)
        self.assertIn(
            '--artifact-url="${{ steps.upload-csp-fixture-report.outputs.artifact-url }}"',
            summary,
        )
        self.assertNotIn('third-party-runtime-report.json', summary)
        self.assertNotIn('site-release', summary)
        self.assertLess(
            workflow.index('Upload failed CSP fixture report'),
            workflow.index('Summarize failed CSP fixture regressions'),
            'focused summary must run after the focused report upload',
        )

        fixture_step = re.search(
            r'(?ms)^      - name: Run CSP fixture regressions\n'
            r'(.*?)(?=^      - name: )',
            workflow,
        )
        self.assertIsNotNone(fixture_step, 'missing CSP fixture regression step')
        self.assertIn('continue-on-error: true', fixture_step.group(1))

    def test_pages_only_blocked_fixture_is_partial_and_not_enforcement_proof(self):
        code, summary = self.run_summary(self.load_fixture('live-edge-pages-blocked.json'))

        self.assertEqual(code, 0)
        self.assertIn('| Content delivery | PASS |', summary)
        self.assertIn('| Edge policy | PARTIAL |', summary)
        self.assertIn('do not prove enforcement', summary)
        self.assertNotIn('| Edge policy | FAILED |', summary)

    def test_pages_only_partial_report_links_to_uploaded_report_artifact(self):
        artifact_url = 'https://github.com/example/site/actions/runs/123/artifacts/789'
        code, summary = self.run_summary(
            self.load_fixture('live-edge-pages-blocked.json'), artifact_url=artifact_url
        )

        self.assertEqual(code, 0)
        self.assertIn(
            f'Full route evidence artifact: [report.json]({artifact_url})',
            summary,
        )

    def test_transport_block_is_unknown_not_external_outage(self):
        code, summary = self.run_summary({'checks': [{'check': 'route /', 'status': 'BLOCKED', 'evidence': 'timeout'}]})
        self.assertEqual(code, 0)
        self.assertIn('| Content delivery | PARTIAL |', summary)
        self.assertIn('NOT RUN', summary)

    def test_mixed_external_and_local_failure(self):
        code, summary = self.run_summary(
            self.load_fixture('external-runtime-mixed-failure.json'), 'external'
        )
        self.assertEqual(code, 1)
        self.assertIn('| Content delivery | FAILED |', summary)
        self.assertIn('| External availability | DEGRADED |', summary)
        self.assertIn('| Browser CSP diagnostics | WARN |', summary)

    def test_external_runtime_pass_summary(self):
        code, summary = self.run_summary(
            self.load_fixture('external-runtime-pass.json'), 'external'
        )

        self.assertEqual(code, 0)
        self.assertIn('| Content delivery | PASS |', summary)
        self.assertIn('| External availability | PASS |', summary)
        self.assertIn('| Browser CSP diagnostics | PASS |', summary)

    def test_external_only_is_nonblocking(self):
        code, summary = self.run_summary(
            self.load_fixture('external-runtime-degraded.json'), 'external'
        )
        self.assertEqual(code, 0)
        self.assertIn('| External availability | DEGRADED |', summary)

    def test_external_degraded_summary_links_to_uploaded_report(self):
        artifact_url = 'https://github.com/example/site/actions/runs/123/artifacts/987'
        code, summary = self.run_summary(
            self.load_fixture('external-runtime-degraded.json'),
            'external',
            artifact_url=artifact_url,
        )
        self.assertEqual(code, 0)
        self.assertIn('| External availability | DEGRADED |', summary)
        self.assertIn(
            f'Full route evidence artifact: [report.json]({artifact_url})',
            summary,
        )

    def test_external_local_failure_summary_links_to_uploaded_report(self):
        artifact_url = 'https://github.com/example/site/actions/runs/123/artifacts/988'
        code, summary = self.run_summary(
            self.load_fixture('external-runtime-local-failure.json'),
            'external',
            artifact_url=artifact_url,
        )
        self.assertEqual(code, 1)
        self.assertIn('| Content delivery | FAILED |', summary)
        self.assertIn(
            f'Full route evidence artifact: [report.json]({artifact_url})',
            summary,
        )

    def test_invalid_reports_fail_closed(self):
        for report in ({}, {'checks': []}, {'checks': [{'status': 'MAYBE'}]}, []):
            with self.subTest(report=report):
                code, summary = self.run_summary(report)
                self.assertEqual(code, 1)
                self.assertIn('UNKNOWN', summary)

    def test_report_text_is_escaped(self):
        code, summary = self.run_summary({'checks': [{'check': '<script>|bad', 'status': 'FAIL', 'evidence': '<img>\n|bad'}]})
        self.assertEqual(code, 1)
        self.assertNotIn('<script>', summary)
        self.assertNotIn('<img>', summary)

    def test_absent_and_invalid_json_leave_unknown_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'report.json'
            for content in (None, '{'):
                if content:
                    source.write_text(content, encoding='utf-8')
                output = Path(directory) / 'summary.md'
                result = subprocess.run([sys.executable, str(SCRIPT), '--kind', 'edge',
                    '--report', str(source), '--summary', str(output)], capture_output=True)
                self.assertEqual(result.returncode, 1)
                self.assertIn('UNKNOWN', output.read_text(encoding='utf-8'))

    def test_empty_external_sample_does_not_pass(self):
        report = self.load_fixture('external-runtime-pass.json')
        report['summary']['routes'] = 0
        code, summary = self.run_summary(report, 'external')
        self.assertEqual(code, 1)
        self.assertIn('UNKNOWN', summary)


if __name__ == '__main__':
    unittest.main()

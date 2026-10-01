"""Regression coverage for operator summaries, including mixed failures."""
import copy
import importlib.util
import json
import re
from pathlib import Path, PurePosixPath
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
    # assets/audit is ignored by Git; the tracked fixture keeps clean checkouts testable.
    'assets/audit/assessment-2026-09-07/delivery/live-edge.json': {
        'classification': 'current',
        'fixture': 'archived-live-edge-2026-09-07.json',
        'required_action': 'validate_report_shape',
    },
}
LEGACY_LIVE_EDGE_FIXTURE = {
    'classification': 'legacy',
    'fixture': 'archived-live-edge-legacy.json',
    'required_action': 'summary_renderer',
}
REPORT_ACTIONS = {
    'current': 'validate_report_shape',
    'legacy': 'summary_renderer',
}


def discover_archived_live_edge_reports(root):
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.glob('assets/audit/**/delivery/live-edge.json')
        if path.is_file()
    )


def archive_registry_issues(
    root,
    registry,
    *,
    fixture_root=ROOT,
    require_registered_files=False,
):
    if not isinstance(registry, dict):
        return ['Malformed live-edge report registry; required action: use a path-to-record object.']

    discovered = set(discover_archived_live_edge_reports(root))
    registered = set()
    issues = []
    for report_path, entry in registry.items():
        display_path = report_path if isinstance(report_path, str) else repr(report_path)
        path = PurePosixPath(report_path) if isinstance(report_path, str) else None
        if (
            path is None
            or path.is_absolute()
            or '..' in path.parts
            or path.as_posix() != report_path
            or path.parts[:2] != ('assets', 'audit')
            or path.parts[-2:] != ('delivery', 'live-edge.json')
        ):
            issues.append(
                f'Malformed live-edge registry path {display_path}; required action: '
                'use the exact repository-relative assets/audit/**/delivery/live-edge.json path.'
            )
            continue
        registered.add(report_path)
        if not isinstance(entry, dict):
            issues.append(
                f'Malformed live-edge registry entry for {report_path}; required action: '
                "set classification to 'current' or 'legacy' and include its fixture and required_action."
            )
            continue

        classification = entry.get('classification')
        if not isinstance(classification, str) or classification not in REPORT_ACTIONS:
            issues.append(
                f'Malformed live-edge registry entry for {report_path}; required action: '
                "set classification to 'current' or 'legacy'."
            )
            continue
        required_action = REPORT_ACTIONS[classification]
        if entry.get('required_action') != required_action:
            issues.append(
                f'Malformed live-edge registry entry for {report_path}; required action: '
                f"set required_action to '{required_action}' for classification '{classification}'."
            )
        fixture = entry.get('fixture')
        if not isinstance(fixture, str) or PurePosixPath(fixture).name != fixture:
            issues.append(
                f'Malformed live-edge registry fixture for {report_path}; required action: '
                'name a fixture file under tests/fixtures/actions-summary/.'
            )
        elif not (fixture_root / 'tests/fixtures/actions-summary' / fixture).is_file():
            issues.append(
                f'Missing compatibility fixture for {report_path}: '
                f'tests/fixtures/actions-summary/{fixture}; required action: '
                'restore the fixture without changing the retained report.'
            )

    for report_path in sorted(discovered - registered):
        issues.append(
            f'Unlisted retained live-edge report: {report_path}; required action: '
            'add this exact path to ARCHIVED_LIVE_EDGE_REPORTS and classify it as '
            "'current' with validator coverage or 'legacy' with summary-renderer coverage."
        )

    if require_registered_files:
        for report_path in sorted(registered - discovered):
            issues.append(
                f'Registered live-edge report is missing: {report_path}; required action: '
                'restore the archived report or remove its registry entry only after confirming its disposition.'
            )
    return issues


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

    def assert_archived_report_contract(self, path, report, entry):
        classification = entry.get('classification') if isinstance(entry, dict) else None
        self.assertIn(
            classification,
            {'current', 'legacy'},
            f'{path} must be explicitly classified as current or legacy',
        )
        if classification == 'current':
            try:
                VERIFY.validate_report_shape(report)
            except ValueError as exc:
                self.fail(
                    f'{path} is classified as current but no longer matches the '
                    f'verifier contract: {exc}. Required action: migrate the archived '
                    'report to the current shape, or classify it as legacy and add '
                    'a summary-renderer compatibility test.'
                )
        else:
            code, summary = self.run_summary(report)
            self.assertIn(
                '| Content delivery |',
                summary,
                f'{path} is classified as legacy; required action: keep it renderable '
                'through scripts/write-actions-summary.py.',
            )

    def test_retained_archive_reports_are_discovered_and_registered(self):
        issues = archive_registry_issues(ROOT, ARCHIVED_LIVE_EDGE_REPORTS)
        self.assertEqual(issues, [], '\n'.join(issues))

    def test_archive_discovery_is_recursive_and_complete(self):
        expected_paths = {
            'assets/audit/assessment-2026-09-07/delivery/live-edge.json',
            'assets/audit/secondary/deeper/delivery/live-edge.json',
        }
        report_bytes = (
            FIXTURE_DIRECTORY / 'archived-live-edge-2026-09-07.json'
        ).read_bytes()
        registry = {
            path: {
                'classification': 'current',
                'fixture': 'archived-live-edge-2026-09-07.json',
                'required_action': 'validate_report_shape',
            }
            for path in expected_paths
        }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for path in expected_paths:
                archive_path = root / path
                archive_path.parent.mkdir(parents=True, exist_ok=True)
                archive_path.write_bytes(report_bytes)
            decoy = root / 'assets/audit/secondary/delivery/live-edge-old.json'
            decoy.parent.mkdir(parents=True, exist_ok=True)
            decoy.write_bytes(report_bytes)

            discovered = set(discover_archived_live_edge_reports(root))
            issues = archive_registry_issues(
                root,
                registry,
                fixture_root=ROOT,
                require_registered_files=True,
            )

        self.assertEqual(discovered, expected_paths)
        self.assertEqual(issues, [], '\n'.join(issues))

    def test_unlisted_archive_report_names_exact_path_and_required_action(self):
        report_path = 'assets/audit/unlisted/deep/delivery/live-edge.json'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive_path = root / report_path
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            archive_path.write_text('{}\n', encoding='utf-8')
            issues = archive_registry_issues(root, {}, fixture_root=ROOT)

        self.assertEqual(len(issues), 1)
        self.assertIn(report_path, issues[0])
        self.assertIn('add this exact path', issues[0])
        self.assertIn("'current'", issues[0])
        self.assertIn("'legacy'", issues[0])

    def test_missing_registered_archive_report_names_exact_path_and_required_action(self):
        report_path = next(iter(ARCHIVED_LIVE_EDGE_REPORTS))
        with tempfile.TemporaryDirectory() as directory:
            issues = archive_registry_issues(
                Path(directory),
                ARCHIVED_LIVE_EDGE_REPORTS,
                fixture_root=ROOT,
                require_registered_files=True,
            )

        missing = [issue for issue in issues if 'is missing' in issue]
        self.assertEqual(len(missing), 1, '\n'.join(issues))
        self.assertIn(report_path, missing[0])
        self.assertIn('restore the archived report', missing[0])

    def test_malformed_archive_registry_entries_name_path_and_required_action(self):
        report_path = next(iter(ARCHIVED_LIVE_EDGE_REPORTS))
        malformed_entries = (
            (
                {'classification': 'unknown', 'fixture': 'archived-live-edge-2026-09-07.json'},
                "set classification to 'current' or 'legacy'",
            ),
            (
                {'fixture': 'archived-live-edge-2026-09-07.json'},
                "set classification to 'current' or 'legacy'",
            ),
            (
                {'classification': 'current', 'fixture': 'archived-live-edge-2026-09-07.json'},
                "set required_action to 'validate_report_shape'",
            ),
            (
                {
                    'classification': 'current',
                    'fixture': '../outside.json',
                    'required_action': 'validate_report_shape',
                },
                'name a fixture file under tests/fixtures/actions-summary/',
            ),
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for entry, required_action in malformed_entries:
                with self.subTest(entry=entry):
                    issues = archive_registry_issues(
                        root,
                        {report_path: entry},
                        fixture_root=ROOT,
                    )
                    matching = [issue for issue in issues if required_action in issue]
                    self.assertTrue(matching, '\n'.join(issues))
                    self.assertIn(report_path, matching[0])

    def test_archived_live_edge_reports_have_an_explicit_contract(self):
        for path, entry in ARCHIVED_LIVE_EDGE_REPORTS.items():
            with self.subTest(report=path):
                archived_path = ROOT / path
                fixture_path = FIXTURE_DIRECTORY / entry['fixture']
                source_path = archived_path if archived_path.is_file() else fixture_path
                report = json.loads(source_path.read_text(encoding='utf-8'))
                self.assert_archived_report_contract(path, report, entry)

    def test_archived_contract_drift_has_an_actionable_failure(self):
        path, entry = next(iter(ARCHIVED_LIVE_EDGE_REPORTS.items()))
        report = json.loads(
            (FIXTURE_DIRECTORY / entry['fixture']).read_text(encoding='utf-8')
        )
        del report['summary']['warnings']

        with self.assertRaisesRegex(
            AssertionError,
            r'Required action: migrate the archived report to the current shape',
        ):
            self.assert_archived_report_contract(path, report, entry)

    def test_legacy_report_is_explicitly_classified_and_renders_in_summary_cli(self):
        self.assertEqual(LEGACY_LIVE_EDGE_FIXTURE['classification'], 'legacy')
        self.assertEqual(
            LEGACY_LIVE_EDGE_FIXTURE['required_action'],
            REPORT_ACTIONS['legacy'],
        )
        report = self.load_fixture(LEGACY_LIVE_EDGE_FIXTURE['fixture'])

        with self.assertRaises(ValueError):
            VERIFY.validate_report_shape(report)

        code, summary = self.run_summary(report)
        self.assertEqual(code, 0)
        self.assertIn('| Content delivery | PASS |', summary)
        self.assertIn('| Edge policy | PARTIAL |', summary)
        self.assertIn('not specified (monitoring)', summary)
        self.assertIn('Report time: unknown', summary)

    def test_historical_partial_is_not_an_outage_or_full_policy_pass(self):
        path, entry = next(iter(ARCHIVED_LIVE_EDGE_REPORTS.items()))
        report = json.loads(
            (FIXTURE_DIRECTORY / entry['fixture']).read_text(encoding='utf-8')
        )
        self.assert_archived_report_contract(path, report, entry)
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

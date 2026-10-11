"""Regression coverage for operator summaries, including mixed failures."""
import ast
import copy
import importlib.util
import json
import os
import re
import shlex
import shutil
import stat
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

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
STRICT_ARCHIVE_AUDIT_ENV = 'OKHP3_STRICT_LIVE_EDGE_ARCHIVE_AUDIT'
ARCHIVE_ROOT_PARTS = ('assets', 'audit')
FIXTURE_ROOT_PARTS = ('tests', 'fixtures', 'actions-summary')


def canonical_posix_relative_path(value, label):
    if (
        not isinstance(value, str)
        or not value
        or '\x00' in value
        or '\\' in value
        or ':' in value
    ):
        raise ValueError(
            f'{label} {value!r} must be a canonical POSIX relative path without backslashes or colons.'
        )
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or '..' in path.parts
        or path.as_posix() != value
    ):
        raise ValueError(
            f'{label} {value!r} must be a canonical POSIX relative path without absolute, traversal, or noncanonical forms.'
        )
    return path


def canonical_archive_source_path(value):
    path = canonical_posix_relative_path(value, 'Archive source path')
    if (
        len(path.parts) < 4
        or path.parts[:2] != ARCHIVE_ROOT_PARTS
        or path.parts[-2:] != ('delivery', 'live-edge.json')
    ):
        raise ValueError(
            f'Archive source path {value!r} must match assets/audit/**/delivery/live-edge.json.'
        )
    return path


def path_is_within(path, directory):
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False


def is_symlink_or_reparse_point(path):
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    reparse_attribute = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)
    attributes = getattr(metadata, 'st_file_attributes', 0)
    return stat.S_ISLNK(metadata.st_mode) or bool(attributes & reparse_attribute)


def resolve_allowed_root(repo_root, relative_parts, label):
    repo = Path(repo_root).resolve(strict=True)
    candidate = repo
    for index, part in enumerate(relative_parts, start=1):
        candidate = candidate / part
        if is_symlink_or_reparse_point(candidate):
            ancestor = PurePosixPath(*relative_parts[:index]).as_posix()
            raise ValueError(
                f'{label} root ancestor {ancestor} is a symbolic link or Windows reparse point; '
                'required action: keep every permitted-root ancestor as a real directory.'
            )
    resolved = candidate.resolve(strict=False)
    if not path_is_within(resolved, repo):
        raise ValueError(
            f'{label} root {PurePosixPath(*relative_parts).as_posix()} resolves outside the repository; '
            'required action: restore the permitted directory inside the repository.'
        )
    return repo, resolved


def resolve_contained_path(repo_root, allowed_parts, relative_path, label):
    relative = canonical_posix_relative_path(relative_path, label)
    repo, allowed_root = resolve_allowed_root(repo_root, allowed_parts, label)
    ancestor = repo.joinpath(*allowed_parts)
    for part in relative.parts[:-1]:
        ancestor = ancestor / part
        if is_symlink_or_reparse_point(ancestor):
            relative_ancestor = ancestor.relative_to(repo).as_posix()
            raise ValueError(
                f'{label} directory ancestor {relative_ancestor} is a symbolic link or Windows reparse point; '
                'required action: use real directories inside the permitted root.'
            )
    candidate = (repo.joinpath(*allowed_parts, *relative.parts)).resolve(strict=False)
    if not path_is_within(candidate, allowed_root):
        raise ValueError(
            f'{label} {relative_path!r} resolves outside permitted '
            f'{PurePosixPath(*allowed_parts).as_posix()}; required action: '
            'move the referenced file inside the permitted directory and update the registry.'
        )
    return candidate


def resolve_archive_source(root, report_path):
    source = canonical_archive_source_path(report_path)
    relative_to_archive = PurePosixPath(*source.parts[len(ARCHIVE_ROOT_PARTS):]).as_posix()
    return resolve_contained_path(
        root,
        ARCHIVE_ROOT_PARTS,
        relative_to_archive,
        f'Archive source {report_path}',
    )


def resolve_compatibility_fixture(fixture_root, fixture_name):
    fixture = canonical_posix_relative_path(fixture_name, 'Compatibility fixture')
    if fixture.suffix != '.json':
        raise ValueError(
            f'Compatibility fixture {fixture_name!r} must be a JSON file under '
            'tests/fixtures/actions-summary.'
        )
    return resolve_contained_path(
        fixture_root,
        FIXTURE_ROOT_PARTS,
        fixture.as_posix(),
        f'Compatibility fixture {fixture_name}',
    )


def registered_report_bytes(
    root,
    report_path,
    entry,
    *,
    fixture_root=ROOT,
    require_source=False,
):
    canonical_archive_source_path(report_path)
    if not isinstance(entry, dict):
        raise ValueError(
            f'Malformed live-edge registry entry for {report_path}; required action: '
            "set classification to 'current' or 'legacy' and include a fixture and required_action."
        )
    fixture_name = entry.get('fixture')

    # Resolve both paths and verify containment before opening either file.
    source_path = resolve_archive_source(root, report_path)
    try:
        fixture_path = resolve_compatibility_fixture(fixture_root, fixture_name)
    except ValueError as exc:
        raise ValueError(
            f'Malformed live-edge registry fixture for {report_path}: {exc} '
            'Required action: name a fixture file under tests/fixtures/actions-summary/ '
            'using a canonical POSIX relative path.'
        ) from exc
    if not fixture_path.is_file():
        raise ValueError(
            f'Missing compatibility fixture for {report_path}: '
            f'tests/fixtures/actions-summary/{fixture_name}; required action: '
            'restore the fixture without changing the retained report.'
        )
    fixture_bytes = fixture_path.read_bytes()
    if source_path.is_file():
        source_bytes = source_path.read_bytes()
        if source_bytes != fixture_bytes:
            raise ValueError(
                f'Retained report byte drift: {report_path} differs from tracked fixture '
                f'tests/fixtures/actions-summary/{fixture_name}; required action: '
                'review both files and refresh the fixture only after verifying the source archive. '
                'Do not rewrite the retained report.'
            )
        return source_bytes
    if require_source:
        raise ValueError(
            f'Registered live-edge report is missing: {report_path}; required action: '
            'restore the archived report inside assets/audit or remove the registry entry only '
            'after confirming its disposition. The fixture alone does not prove archive coverage.'
        )
    return fixture_bytes


def discover_archived_live_edge_reports(root):
    repo, archive_root = resolve_allowed_root(root, ARCHIVE_ROOT_PARTS, 'Archive')
    try:
        archive_root.stat()
    except FileNotFoundError:
        return []
    if not archive_root.is_dir():
        raise ValueError(
            'Archive root assets/audit is not a directory; required action: '
            'restore assets/audit as a directory before running the archive audit.'
        )

    discovered = []
    pending_directories = [archive_root]
    while pending_directories:
        current_path = pending_directories.pop()
        with os.scandir(current_path) as entries:
            for entry in entries:
                candidate = Path(entry.path)
                metadata = candidate.lstat()
                if is_symlink_or_reparse_point(candidate):
                    resolved = candidate.resolve(strict=False)
                    relative = candidate.relative_to(repo).as_posix()
                    if not path_is_within(resolved, archive_root):
                        raise ValueError(
                            f'Archive entry {relative} is a symbolic link or Windows reparse point '
                            'that resolves outside permitted assets/audit; required action: replace '
                            'it with a regular file or directory inside assets/audit.'
                        )
                    raise ValueError(
                        f'Archive entry {relative} is a symbolic link or Windows reparse point, '
                        'so recursive report discovery is incomplete; required action: replace it '
                        'with a regular file or directory inside assets/audit.'
                    )

                if stat.S_ISDIR(metadata.st_mode):
                    pending_directories.append(candidate)
                    continue
                if (
                    current_path.name != 'delivery'
                    or candidate.name != 'live-edge.json'
                    or not stat.S_ISREG(metadata.st_mode)
                ):
                    continue
                relative_in_archive = candidate.relative_to(archive_root).as_posix()
                report_path = PurePosixPath(
                    *ARCHIVE_ROOT_PARTS,
                    *PurePosixPath(relative_in_archive).parts,
                ).as_posix()
                resolved_report = resolve_archive_source(root, report_path)
                if resolved_report.is_file():
                    discovered.append(report_path)
    return sorted(discovered)


def archive_registry_issues(
    root,
    registry,
    *,
    fixture_root=ROOT,
    require_registered_files=False,
):
    if not isinstance(registry, dict):
        return ['Malformed live-edge report registry; required action: use a path-to-record object.']

    issues = []
    try:
        discovered = set(discover_archived_live_edge_reports(root))
    except (OSError, RuntimeError, ValueError) as exc:
        return [str(exc)]

    registered = set()
    for report_path, entry in registry.items():
        try:
            canonical_archive_source_path(report_path)
        except ValueError as exc:
            issues.append(
                f'Malformed live-edge registry path {report_path!r}: {exc} '
                'Required action: use the exact canonical POSIX assets/audit/**/delivery/live-edge.json path.'
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
        try:
            registered_report_bytes(
                root,
                report_path,
                entry,
                fixture_root=fixture_root,
                require_source=require_registered_files,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            issues.append(str(exc))

    for report_path in sorted(discovered - registered):
        issues.append(
            f'Unlisted retained live-edge report: {report_path}; required action: '
            'add this exact path to ARCHIVED_LIVE_EDGE_REPORTS and classify it as '
            "'current' with validator coverage or 'legacy' with summary-renderer coverage."
        )
    return issues


def strict_archive_audit_enabled(environ=None):
    if environ is None:
        environ = os.environ
    value = environ.get(STRICT_ARCHIVE_AUDIT_ENV, '').strip().lower()
    if value in {'', '0', 'false', 'no'}:
        return False
    if value in {'1', 'true', 'yes'}:
        return True
    raise ValueError(
        f'{STRICT_ARCHIVE_AUDIT_ENV} must be set to 1 or 0; got {value!r}.'
    )


VERIFY_SPEC = importlib.util.spec_from_file_location(
    'verify_live_edge', ROOT / 'scripts/verify-live-edge.py'
)
if VERIFY_SPEC is None or VERIFY_SPEC.loader is None:
    raise RuntimeError('could not load scripts/verify-live-edge.py')
VERIFY = importlib.util.module_from_spec(VERIFY_SPEC)
VERIFY_SPEC.loader.exec_module(VERIFY)

SUMMARY_SPEC = importlib.util.spec_from_file_location('write_actions_summary', SCRIPT)
if SUMMARY_SPEC is None or SUMMARY_SPEC.loader is None:
    raise RuntimeError('could not load scripts/write-actions-summary.py')
SUMMARY_WRITER = importlib.util.module_from_spec(SUMMARY_SPEC)
SUMMARY_SPEC.loader.exec_module(SUMMARY_WRITER)


class SummaryTests(unittest.TestCase):
    def test_class_method_names_are_unique(self):
        tree = ast.parse(Path(__file__).read_text(encoding='utf-8'), filename=__file__)
        duplicates = []
        for class_node in ast.walk(tree):
            if not isinstance(class_node, ast.ClassDef):
                continue
            first_lines = {}
            for method in class_node.body:
                if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if method.name in first_lines:
                    duplicates.append(
                        f'{class_node.name}.{method.name}: lines '
                        f'{first_lines[method.name]} and {method.lineno}'
                    )
                else:
                    first_lines[method.name] = method.lineno
        self.assertEqual(
            duplicates, [],
            'Duplicate class methods hide test or helper definitions:\n'
            + '\n'.join(duplicates),
        )

    def create_symlink_or_skip_when_windows_privilege_is_missing(
        self,
        link,
        target,
        *,
        target_is_directory=False,
    ):
        try:
            link.symlink_to(target, target_is_directory=target_is_directory)
        except OSError as exc:
            if os.name == 'nt' and getattr(exc, 'winerror', None) == 1314:
                self.skipTest(
                    'Windows symlink creation requires privileges unavailable to this runner; '
                    'the separate junction regression remains active.'
                )
            raise

    def load_fixture(self, name):
        fixture_path = resolve_compatibility_fixture(ROOT, name)
        if not fixture_path.is_file():
            raise FileNotFoundError(f'fixture not found: {name}')
        return json.loads(fixture_path.read_bytes())

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

    def test_generated_fixture_check_detects_malformed_fixture_content(self):
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
            fixture.write_text('{"summary": {}}\n', encoding='utf-8')
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

        self.assertEqual(checked.returncode, 1, checked.stdout + checked.stderr)
        self.assertIn('generated fixture is stale', checked.stdout + checked.stderr)
        self.assertIn('external-runtime-degraded.json', checked.stdout + checked.stderr)

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

    def run_summary(
        self,
        report,
        kind='edge',
        artifact_url=None,
        report_name='report.json',
        run_id=None,
        run_attempt=None,
    ):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / report_name
            output = Path(directory) / 'summary.md'
            source.write_text(json.dumps(report), encoding='utf-8')
            command = [sys.executable, str(SCRIPT), '--kind', kind,
                       '--report', str(source), '--summary', str(output)]
            if artifact_url:
                command.extend(['--artifact-url', artifact_url])
            command_env = os.environ.copy()
            for key in (
                'ACTIONS_ARTIFACT_URL',
                'GITHUB_RUN_ID',
                'GITHUB_RUN_ATTEMPT',
            ):
                command_env.pop(key, None)
            if run_id is not None:
                command_env['GITHUB_RUN_ID'] = str(run_id)
            if run_attempt is not None:
                command_env['GITHUB_RUN_ATTEMPT'] = str(run_attempt)
            result = subprocess.run(command,
                                    capture_output=True, text=True, env=command_env)
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
        issues = archive_registry_issues(
            ROOT,
            ARCHIVED_LIVE_EDGE_REPORTS,
            require_registered_files=strict_archive_audit_enabled(),
        )
        self.assertEqual(issues, [], '\n'.join(issues))

    def test_archive_discovery_is_recursive_and_complete(self):
        expected_paths = {
            'assets/audit/assessment-2026-09-07/delivery/live-edge.json',
            'assets/audit/secondary/deeper/delivery/live-edge.json',
        }
        report_bytes = resolve_compatibility_fixture(
            ROOT,
            'archived-live-edge-2026-09-07.json',
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

    def test_valid_source_byte_drift_names_source_and_fixture(self):
        report_path, entry = next(iter(ARCHIVED_LIVE_EDGE_REPORTS.items()))
        fixture_bytes = resolve_compatibility_fixture(
            ROOT,
            entry['fixture'],
        ).read_bytes()
        report = json.loads(fixture_bytes)
        report['checks'][0]['evidence'] += ' with a valid-content mutation'
        changed_bytes = (json.dumps(report, indent=2) + '\n').encode('utf-8')
        self.assertEqual(json.loads(changed_bytes), report)
        VERIFY.validate_report_shape(report)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / report_path
            source_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.write_bytes(changed_bytes)
            issues = archive_registry_issues(
                root,
                ARCHIVED_LIVE_EDGE_REPORTS,
                fixture_root=ROOT,
            )

        drift = [issue for issue in issues if 'Retained report byte drift' in issue]
        self.assertEqual(len(drift), 1, '\n'.join(issues))
        self.assertIn(report_path, drift[0])
        self.assertIn(
            f"tests/fixtures/actions-summary/{entry['fixture']}",
            drift[0],
        )
        self.assertIn('Do not rewrite the retained report', drift[0])

    def test_registry_paths_reject_noncanonical_and_windows_forms(self):
        valid_path, valid_entry = next(iter(ARCHIVED_LIVE_EDGE_REPORTS.items()))
        invalid_source_paths = (
            r'assets\audit\assessment-2026-09-07\delivery\live-edge.json',
            'C:/assets/audit/assessment-2026-09-07/delivery/live-edge.json',
            'assets/audit/assessment:backup/delivery/live-edge.json',
            '/assets/audit/assessment-2026-09-07/delivery/live-edge.json',
            'assets/audit/../assessment-2026-09-07/delivery/live-edge.json',
            'assets//audit/assessment-2026-09-07/delivery/live-edge.json',
            'assets/audit/assessment-2026-09-07\x00/delivery/live-edge.json',
        )
        invalid_fixtures = (
            r'..\outside.json',
            'C:/outside.json',
            'archive:old.json',
            '/outside.json',
            '../outside.json',
            'nested//report.json',
            'nested\x00/report.json',
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for source_path in invalid_source_paths:
                with self.subTest(source_path=source_path):
                    issues = archive_registry_issues(
                        root,
                        {source_path: valid_entry},
                        fixture_root=ROOT,
                    )
                    matching = [
                        issue for issue in issues
                        if 'Malformed live-edge registry path' in issue
                    ]
                    self.assertTrue(matching, '\n'.join(issues))
                    self.assertIn(repr(source_path), matching[0])

            for fixture_name in invalid_fixtures:
                with self.subTest(fixture_name=fixture_name):
                    entry = dict(valid_entry, fixture=fixture_name)
                    issues = archive_registry_issues(
                        root,
                        {valid_path: entry},
                        fixture_root=ROOT,
                    )
                    self.assertTrue(
                        any(repr(fixture_name) in issue for issue in issues),
                        '\n'.join(issues),
                    )

    def test_source_and_fixture_symlink_escapes_are_rejected_before_reading(self):
        report_path, entry = next(iter(ARCHIVED_LIVE_EDGE_REPORTS.items()))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root / 'outside'
            outside.mkdir()
            outside_report = outside / 'live-edge.json'
            outside_report.write_text('must not be read\n', encoding='utf-8')

            source_link = root / 'assets/audit/escaped'
            source_link.parent.mkdir(parents=True, exist_ok=True)
            self.create_symlink_or_skip_when_windows_privilege_is_missing(
                source_link,
                outside,
                target_is_directory=True,
            )
            linked_report_path = (
                'assets/audit/escaped/assessment-2026-09-07/delivery/live-edge.json'
            )
            source_entry = dict(entry)

            fixture_root = root / 'fixture-case'
            fixture_directory = fixture_root / 'tests/fixtures/actions-summary'
            fixture_directory.mkdir(parents=True)
            fixture_link = fixture_directory / 'outside.json'
            self.create_symlink_or_skip_when_windows_privilege_is_missing(
                fixture_link,
                outside_report,
            )
            fixture_entry = dict(entry, fixture='outside.json')

            original_read_bytes = Path.read_bytes

            def reject_outside_read(path):
                if path.resolve(strict=False) == outside_report.resolve():
                    raise AssertionError(f'attempted to read outside allowed roots: {path}')
                return original_read_bytes(path)

            with patch.object(Path, 'read_bytes', reject_outside_read):
                source_issues = archive_registry_issues(
                    root,
                    {linked_report_path: source_entry},
                    fixture_root=ROOT,
                )
                fixture_issues = archive_registry_issues(
                    fixture_root,
                    {report_path: fixture_entry},
                    fixture_root=fixture_root,
                )

        self.assertTrue(
            any(
                'assets/audit/escaped' in issue
                and (
                    'outside permitted assets/audit' in issue
                    or 'symbolic link or Windows reparse point' in issue
                )
                for issue in source_issues
            ),
            '\n'.join(source_issues),
        )
        self.assertTrue(
            any(
                'outside.json' in issue
                and 'outside permitted tests/fixtures/actions-summary' in issue
                for issue in fixture_issues
            ),
            '\n'.join(fixture_issues),
        )

    def test_synthetic_windows_reparse_root_marker_is_rejected_before_reading(self):
        report_path, entry = next(iter(ARCHIVED_LIVE_EDGE_REPORTS.items()))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / report_path
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(b'{"synthetic":"report"}\n')
            fixture_directory = root / 'tests/fixtures/actions-summary'
            fixture_directory.mkdir(parents=True)
            (fixture_directory / entry['fixture']).write_bytes(b'{"synthetic":"report"}\n')

            root_ancestor = root / 'assets'
            original_lstat = Path.lstat
            original_read_bytes = Path.read_bytes
            read_attempts = []

            def mark_as_reparse_point(path):
                metadata = original_lstat(path)
                if path == root_ancestor:
                    return SimpleNamespace(
                        st_mode=metadata.st_mode,
                        st_file_attributes=0x400,
                    )
                return metadata

            def track_file_read(path):
                read_attempts.append(path)
                return original_read_bytes(path)

            with patch.object(Path, 'lstat', mark_as_reparse_point):
                with patch.object(Path, 'read_bytes', track_file_read):
                    issues = archive_registry_issues(
                        root,
                        ARCHIVED_LIVE_EDGE_REPORTS,
                        fixture_root=root,
                        require_registered_files=True,
                    )

        self.assertTrue(
            any('Windows reparse point' in issue and 'assets' in issue for issue in issues),
            '\n'.join(issues),
        )
        self.assertEqual(read_attempts, [], 'source or fixture content was read before rejecting the root')

    def test_synthetic_windows_reparse_archive_directory_stops_discovery_before_reading(self):
        report_path = 'assets/audit/redirect/delivery/live-edge.json'
        entry = {
            'classification': 'current',
            'fixture': 'synthetic.json',
            'required_action': 'validate_report_shape',
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / report_path
            source.parent.mkdir(parents=True)
            source_bytes = b'{"synthetic":"reparse directory"}\n'
            source.write_bytes(source_bytes)
            fixture_directory = root / 'tests/fixtures/actions-summary'
            fixture_directory.mkdir(parents=True)
            (fixture_directory / entry['fixture']).write_bytes(source_bytes)

            reparse_directory = root / 'assets/audit/redirect'
            original_lstat = Path.lstat
            original_read_bytes = Path.read_bytes
            read_attempts = []

            def mark_as_reparse_point(path):
                metadata = original_lstat(path)
                if path == reparse_directory:
                    return SimpleNamespace(
                        st_mode=metadata.st_mode,
                        st_file_attributes=0x400,
                    )
                return metadata

            def track_file_read(path):
                read_attempts.append(path)
                return original_read_bytes(path)

            with patch.object(Path, 'lstat', mark_as_reparse_point):
                with patch.object(Path, 'read_bytes', track_file_read):
                    issues = archive_registry_issues(
                        root,
                        {report_path: entry},
                        fixture_root=root,
                        require_registered_files=True,
                    )

        self.assertTrue(
            any(
                'assets/audit/redirect' in issue
                and 'Windows reparse point' in issue
                for issue in issues
            ),
            '\n'.join(issues),
        )
        self.assertEqual(
            read_attempts,
            [],
            'archive or fixture content was read before recursive discovery rejected the reparse point',
        )

    @unittest.skipUnless(os.name == 'nt', 'requires Windows junction semantics')
    def test_windows_assets_junction_to_private_is_rejected_before_reading(self):
        report_path, entry = next(iter(ARCHIVED_LIVE_EDGE_REPORTS.items()))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private = root / 'private'
            source = private / 'audit/assessment-2026-09-07/delivery/live-edge.json'
            source.parent.mkdir(parents=True)
            source_bytes = b'{"synthetic":"junction target"}\n'
            source.write_bytes(source_bytes)
            fixture_directory = root / 'tests/fixtures/actions-summary'
            fixture_directory.mkdir(parents=True)
            (fixture_directory / entry['fixture']).write_bytes(source_bytes)

            assets_junction = root / 'assets'
            created = subprocess.run(
                ['cmd', '/c', 'mklink', '/J', str(assets_junction), str(private)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(created.returncode, 0, created.stdout + created.stderr)
            original_read_bytes = Path.read_bytes
            read_attempts = []

            def track_file_read(path):
                read_attempts.append(path)
                return original_read_bytes(path)

            try:
                with patch.object(Path, 'read_bytes', track_file_read):
                    issues = archive_registry_issues(
                        root,
                        {report_path: entry},
                        fixture_root=root,
                        require_registered_files=True,
                    )
            finally:
                assets_junction.rmdir()

        self.assertTrue(
            any(
                'Windows reparse point' in issue and 'assets' in issue
                for issue in issues
            ),
            '\n'.join(issues),
        )
        self.assertEqual(
            read_attempts,
            [],
            'the strict registry audit read the in-repository private junction target before rejecting it',
        )

    def test_strict_archive_audit_switch_accepts_documented_values(self):
        self.assertFalse(strict_archive_audit_enabled({}))
        self.assertFalse(strict_archive_audit_enabled({STRICT_ARCHIVE_AUDIT_ENV: '0'}))
        self.assertTrue(strict_archive_audit_enabled({STRICT_ARCHIVE_AUDIT_ENV: '1'}))
        self.assertTrue(strict_archive_audit_enabled({STRICT_ARCHIVE_AUDIT_ENV: 'true'}))
        with self.assertRaisesRegex(ValueError, 'must be set to 1 or 0'):
            strict_archive_audit_enabled({STRICT_ARCHIVE_AUDIT_ENV: 'sometimes'})

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
            clean_checkout_issues = archive_registry_issues(
                Path(directory),
                ARCHIVED_LIVE_EDGE_REPORTS,
                fixture_root=ROOT,
                require_registered_files=False,
            )
            strict_audit_issues = archive_registry_issues(
                Path(directory),
                ARCHIVED_LIVE_EDGE_REPORTS,
                fixture_root=ROOT,
                require_registered_files=True,
            )

        self.assertEqual(clean_checkout_issues, [])
        missing = [issue for issue in strict_audit_issues if 'is missing' in issue]
        self.assertEqual(len(missing), 1, '\n'.join(strict_audit_issues))
        self.assertIn(report_path, missing[0])
        self.assertIn('restore the archived report', missing[0])
        self.assertIn('fixture alone does not prove archive coverage', missing[0])

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

    def test_main_validation_gate_documents_and_wires_strict_archive_mode(self):
        workflow = (ROOT / '.github/workflows/validate.yml').read_text(encoding='utf-8')
        step = re.search(
            r'(?ms)^      - name: Test Actions reporting and concurrency contracts\n'
            r'(.*?)(?=^      - name: |\Z)',
            workflow,
        )
        self.assertIsNotNone(step, 'missing main Actions-summary test step')
        self.assertIn(
            f"{STRICT_ARCHIVE_AUDIT_ENV}: ${{{{ vars.{STRICT_ARCHIVE_AUDIT_ENV} || '0' }}}}",
            step.group(1),
        )
        documentation = (ROOT / 'scripts/README.md').read_text(encoding='utf-8')
        self.assertIn(STRICT_ARCHIVE_AUDIT_ENV, documentation)
        self.assertIn('fixture-only compatibility', documentation)
        self.assertIn('actual retained archive coverage', documentation)

    def test_registered_current_report_obeys_contract_in_selected_coverage_mode(self):
        for path, entry in ARCHIVED_LIVE_EDGE_REPORTS.items():
            with self.subTest(report=path):
                report_bytes = registered_report_bytes(
                    ROOT,
                    path,
                    entry,
                    fixture_root=ROOT,
                    require_source=strict_archive_audit_enabled(),
                )
                report = json.loads(report_bytes)
                self.assert_archived_report_contract(path, report, entry)

    def test_archived_contract_drift_has_an_actionable_failure(self):
        path, entry = next(iter(ARCHIVED_LIVE_EDGE_REPORTS.items()))
        report = self.load_fixture(entry['fixture'])
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
        self.assertEqual(set(report), VERIFY.LEGACY_LIVE_EDGE_REPORT_FIELDS)

        code, summary = self.run_summary(report)
        self.assertEqual(code, 0)
        self.assertIn('| Content delivery | PASS |', summary)
        self.assertIn('| Edge policy | PARTIAL |', summary)
        self.assertIn('not specified (monitoring)', summary)
        self.assertIn('Report time: unknown', summary)
        self.assertIn(
            '| Report format | LEGACY | checks-only compatibility; no release SHA or report time was recorded |',
            summary,
        )
        with self.assertRaisesRegex(
            ValueError,
            r'legacy live-edge report uses the checks-only shape.*write-actions-summary\.py',
        ):
            VERIFY.validate_report_shape(report)

    def test_summary_format_contract_matches_verifier_and_legacy_shape(self):
        self.assertEqual(
            SUMMARY_WRITER.CURRENT_EDGE_REPORT_FIELDS,
            frozenset(VERIFY.LIVE_EDGE_REPORT_FIELDS),
        )
        self.assertEqual(
            SUMMARY_WRITER.LEGACY_EDGE_REPORT_FIELDS,
            VERIFY.LEGACY_LIVE_EDGE_REPORT_FIELDS,
        )
        self.assertEqual(
            SUMMARY_WRITER.EDGE_CHECK_FIELDS,
            frozenset(VERIFY.LIVE_EDGE_CHECK_FIELDS),
        )
        self.assertEqual(
            SUMMARY_WRITER.EDGE_CHECK_STATUSES,
            VERIFY.LIVE_EDGE_CHECK_STATUSES,
        )

    def test_unsupported_legacy_report_shapes_fail_with_migration_guidance(self):
        unsupported_reports = (
            (
                'alternate envelope',
                {'results': [{'name': 'route /', 'result': 'OK'}]},
                'unsupported live-edge report shape',
            ),
            (
                'legacy status alias',
                {'checks': [{'check': 'route /', 'status': 'OK', 'evidence': 'HTTP 200'}]},
                'unsupported legacy live-edge status convention',
            ),
            (
                'missing legacy evidence',
                {'checks': [{'check': 'route /', 'status': 'PASS'}]},
                'unsupported legacy check shape',
            ),
        )
        for label, report, diagnostic in unsupported_reports:
            with self.subTest(shape=label):
                code, summary = self.run_summary(report)
                self.assertEqual(code, 1)
                self.assertIn('| Evidence | UNKNOWN |', summary)
                self.assertIn(diagnostic, summary)
                self.assertIn('required action:', summary)
                self.assertIn('migrate', summary.lower())

    def test_historical_partial_is_not_an_outage_or_full_policy_pass(self):
        path, entry = next(iter(ARCHIVED_LIVE_EDGE_REPORTS.items()))
        report = self.load_fixture(entry['fixture'])
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
            f'Full route evidence artifact: [report.json](<{artifact_url}>)',
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

    def test_external_upload_or_report_failure_still_reaches_summary(self):
        source = (ROOT / '.github/workflows/validate.yml').read_text(encoding='utf-8')
        job_match = re.search(
            r'(?ms)^  monitor-third-party-runtime:\n(.*?)(?=^  monitor-live-edge:|\Z)',
            source,
        )
        self.assertIsNotNone(job_match, 'missing external monitor workflow job')
        job = job_match.group(1)
        monitor = re.search(
            r'(?ms)^      - name: Check deployed third-party runtime dependencies\n'
            r'(.*?)(?=^      - name: |\Z)',
            job,
        )
        upload = re.search(
            r'(?ms)^      - name: Upload third-party runtime inventory\n'
            r'(.*?)(?=^      - name: |\Z)',
            job,
        )
        summary = re.search(
            r'(?ms)^      - name: Summarize external availability and first-party failures\n'
            r'(.*?)(?=^      - name: |\Z)',
            job,
        )
        self.assertIsNotNone(monitor, 'missing external monitor command')
        self.assertIsNotNone(upload, 'missing external report upload step')
        self.assertIsNotNone(summary, 'missing external summary step')
        self.assertIn('continue-on-error: true', monitor.group(1))
        self.assertIn('if: always()', upload.group(1))
        self.assertIn('if-no-files-found: error', upload.group(1))
        self.assertIn('if: always()', summary.group(1))
        self.assertIn('--report=third-party-runtime-report.json', monitor.group(1))
        self.assertIn('--report third-party-runtime-report.json', summary.group(1))
        self.assertIn(
            'steps.upload-third-party-runtime-report.outputs.artifact-url',
            summary.group(1),
        )

    def test_validation_monitor_summaries_use_their_own_upload_outputs(self):
        source = (ROOT / '.github/workflows/validate.yml').read_text(encoding='utf-8')
        monitors = (
            (
                'monitor-third-party-runtime',
                'Summarize external availability and first-party failures',
                'upload-third-party-runtime-report',
            ),
            (
                'monitor-live-edge',
                'Summarize content delivery and edge policy',
                'upload-live-edge-report',
            ),
        )
        for job_name, summary_name, upload_id in monitors:
            with self.subTest(job=job_name):
                job_match = re.search(
                    rf'(?ms)^  {re.escape(job_name)}:\n(.*?)(?=^  [\w-]+:|\Z)',
                    source,
                )
                self.assertIsNotNone(job_match, f'missing workflow job {job_name}')
                job_source = job_match.group(1)
                summary_match = re.search(
                    rf'(?ms)^      - name: {re.escape(summary_name)}\n'
                    r'(.*?)(?=^      - name: |\Z)',
                    job_source,
                )
                self.assertIsNotNone(summary_match, f'missing summary step in {job_name}')
                self.assertIn(f'id: {upload_id}', job_source)
                artifact_outputs = re.findall(
                    r'steps\.([a-z0-9-]+)\.outputs\.artifact-url',
                    summary_match.group(1),
                )
                self.assertEqual(
                    artifact_outputs,
                    [upload_id],
                    f'{job_name} summary must use its own upload step output',
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
        self.assertIn('id: upload-local-qa-reports', local_qa.group(1))
        self.assertNotIn('site-release', local_qa.group(1))
        self.assertNotIn('third-party-runtime-report.json', local_qa.group(1))

    def test_local_qa_summary_links_its_upload_without_failing_when_no_artifact_exists(self):
        workflow = (ROOT / '.github/workflows/validate.yml').read_text(encoding='utf-8')
        upload = re.search(
            r'(?ms)^      - name: Upload local QA reports\n'
            r'(.*?)(?=^      - name: |\Z)',
            workflow,
        )
        summary = re.search(
            r'(?ms)^      - name: Summarize local QA report artifact\n'
            r'(.*?)(?=^      - name: |\Z)',
            workflow,
        )
        self.assertIsNotNone(upload, 'missing local QA artifact upload')
        self.assertIsNotNone(summary, 'missing local QA artifact summary')
        self.assertIn('if-no-files-found: warn', upload.group(1))
        self.assertIn('if: always()', summary.group(1))
        self.assertIn(
            'steps.upload-local-qa-reports.outputs.artifact-url',
            summary.group(1),
        )
        run_block = re.search(
            r'(?ms)^        run: \|\n((?:^          .*\n?)+)',
            summary.group(1),
        )
        self.assertIsNotNone(run_block, 'local QA summary must use a literal shell block')
        command = '\n'.join(
            line[10:] for line in run_block.group(1).splitlines()
        )

        with tempfile.TemporaryDirectory() as directory:
            summary_path = Path(directory) / 'github-step-summary.md'
            for artifact_url in (
                '',
                'https://github.com/example/site/actions/runs/123/artifacts/456',
            ):
                with self.subTest(artifact_url=bool(artifact_url)):
                    summary_path.write_text('', encoding='utf-8')
                    environment = os.environ.copy()
                    environment['GITHUB_STEP_SUMMARY'] = str(summary_path)
                    environment['LOCAL_QA_ARTIFACT_URL'] = artifact_url
                    result = subprocess.run(
                        ['bash', '-e', '-o', 'pipefail', '-c', command],
                        cwd=ROOT,
                        env=environment,
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    rendered = summary_path.read_text(encoding='utf-8')
                    if artifact_url:
                        self.assertIn(
                            f'[Download local QA reports]({artifact_url})',
                            rendered,
                        )
                    else:
                        self.assertIn('No local QA artifact URL was returned', rendered)
                        self.assertNotIn('[Download local QA reports]', rendered)

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

    def test_missing_optional_csp_report_preserves_originating_failure(self):
        workflow = (ROOT / '.github/workflows/validate.yml').read_text(encoding='utf-8')
        names = (
            'Run CSP fixture regressions',
            'Upload failed CSP fixture report',
            'Summarize failed CSP fixture regressions',
            'Preserve CSP fixture regression failure',
        )

        def step(name):
            match = re.search(
                rf'(?ms)^      - name: {re.escape(name)}\n'
                r'(.*?)(?=^      - name: |\Z)',
                workflow,
            )
            self.assertIsNotNone(match, f'missing workflow step: {name}')
            return match.group(1)

        steps = {name: step(name) for name in names}
        step_positions = [workflow.index(f'      - name: {name}\n') for name in names]
        self.assertEqual(
            step_positions,
            sorted(step_positions),
            'the originating check, optional upload, summary, and failure guard must stay ordered',
        )
        fixture_step, upload_step, summary_step, preserve_step = (
            steps[name] for name in names
        )
        self.assertIn('id: csp-fixtures', fixture_step)
        # continue-on-error can make conclusion success while outcome retains the original failure.
        self.assertIn('continue-on-error: true', fixture_step)
        self.assertIn('run: npm run test:csp:regressions', fixture_step)
        report_name_match = re.search(
            r'(?m)^          CSP_FIXTURE_REPORT: ([^\s]+)$',
            fixture_step,
        )
        self.assertIsNotNone(report_name_match, 'CSP fixture report path is not declared')
        report_name = report_name_match.group(1)
        expected_failure_condition = "if: always() && steps.csp-fixtures.outcome == 'failure'"
        for follow_up_step in (upload_step, summary_step, preserve_step):
            self.assertIn(expected_failure_condition, follow_up_step)
            self.assertNotIn('steps.csp-fixtures.conclusion', follow_up_step)
        preserve_error_policy = re.search(
            r'(?m)^        continue-on-error: ([^\r\n]+)$', preserve_step,
        )
        if preserve_error_policy is not None:
            self.assertEqual(
                preserve_error_policy.group(1).strip(), 'false',
                'the failure-preservation step must not continue after its nonzero exit',
            )
        self.assertIn('id: upload-csp-fixture-report', upload_step)
        self.assertIn('uses: actions/upload-artifact@', upload_step)
        self.assertRegex(upload_step, rf'(?m)^          path: {re.escape(report_name)}$')
        self.assertIn('if-no-files-found: warn', upload_step)
        self.assertIn('retention-days: 7', upload_step)

        run_match = re.search(
            r'(?ms)^        run: >-\n((?:^          [^\n]*\n?)+)',
            summary_step,
        )
        self.assertIsNotNone(run_match, 'CSP summary run block is not the supported folded form')
        summary_command = ' '.join(line.strip() for line in run_match.group(1).splitlines())
        try:
            summary_tokens = shlex.split(summary_command, posix=True)
        except ValueError as exc:
            self.fail(f'CSP summary command is not in the supported form: {exc}')
        self.assertEqual(
            summary_tokens,
            [
                'node',
                'scripts/csp-qa.mjs',
                f'--fixture-summary={report_name}',
                '--artifact-url=${{ steps.upload-csp-fixture-report.outputs.artifact-url }}',
            ],
            'CSP summary must keep using the workflow report and its upload output',
        )
        node = shutil.which(summary_tokens[0])
        self.assertIsNotNone(node, 'the existing Node.js runtime is required')
        summary_script = ROOT / summary_tokens[1]
        self.assertEqual(summary_script, ROOT / 'scripts/csp-qa.mjs')
        self.assertTrue(summary_script.is_file())

        with self.subTest('missing-report summary entry point'):
            # Python compatibility jobs omit optional Node QA packages. Their
            # source-contract and failure-command assertions still run below.
            dependency = subprocess.run(
                [node, '--input-type=module', '--eval', "import.meta.resolve('playwright')"],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            dependency_output = dependency.stdout + dependency.stderr
            if (
                dependency.returncode != 0
                and 'ERR_MODULE_NOT_FOUND' in dependency_output
                and "Cannot find package 'playwright'" in dependency_output
            ):
                self.skipTest('optional Playwright QA package is absent; summary execution was not run')
            self.assertEqual(dependency.returncode, 0, dependency_output)
            with tempfile.TemporaryDirectory() as directory:
                report_path = Path(directory) / report_name
                summary_path = Path(directory) / 'github-step-summary.md'
                self.assertFalse(report_path.exists())
                environment = os.environ.copy()
                environment['GITHUB_STEP_SUMMARY'] = str(summary_path)
                result = subprocess.run(
                    [
                        node,
                        str(summary_script),
                        f'--fixture-summary={report_path}',
                        '--artifact-url=',
                    ],
                    cwd=directory,
                    env=environment,
                    capture_output=True,
                    text=True,
                )
                output = result.stdout + result.stderr
                self.assertEqual(result.returncode, 0, output)
                self.assertTrue(summary_path.is_file(), output)
                rendered = summary_path.read_text(encoding='utf-8')
                self.assertIn(
                    '| unavailable | UNKNOWN | unknown | Focused CSP fixture report is missing;',
                    rendered,
                )
                self.assertIn(
                    'Focused CSP evidence artifact: unavailable; the report file was missing, so the warning-only upload had nothing to retain.',
                    rendered,
                )
                self.assertFalse(report_path.exists(), 'the summary must not fabricate evidence')

        preserve_run = re.search(r'(?m)^        run: ([^\r\n]+)$', preserve_step)
        self.assertIsNotNone(preserve_run, 'failure-preservation command is missing')
        preserve_command = preserve_run.group(1).strip()
        self.assertRegex(
            preserve_command,
            r'\Aexit [0-9]+\Z',
            'only the portable single exit-code form is supported',
        )
        result = subprocess.run(
            preserve_command,
            shell=True,
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(
            result.returncode,
            0,
            'the failure-preservation command must remain nonzero',
        )

    def test_missing_focused_csp_report_has_a_specific_warning_before_upload(self):
        workflow = (ROOT / '.github/workflows/validate.yml').read_text(encoding='utf-8')
        warning = re.search(
            r'(?ms)^      - name: Explain missing focused CSP fixture report\n'
            r'(.*?)(?=^      - name: )',
            workflow,
        )
        upload = re.search(
            r'(?ms)^      - name: Upload failed CSP fixture report\n'
            r'(.*?)(?=^      - name: )',
            workflow,
        )
        self.assertIsNotNone(warning, 'missing focused-report warning step')
        self.assertIsNotNone(upload, 'missing focused report upload step')
        self.assertIn(
            "if: always() && steps.csp-fixtures.outcome == 'failure' && !hashFiles('csp-fixture-report.json')",
            warning.group(1),
        )
        self.assertIn(
            'The focused fixture test failed without creating csp-fixture-report.json',
            warning.group(1),
        )
        self.assertIn('if-no-files-found: warn', upload.group(1))
        self.assertLess(
            workflow.index('Explain missing focused CSP fixture report'),
            workflow.index('Upload failed CSP fixture report'),
        )

    def test_failed_csp_check_without_report_stays_failed_after_optional_evidence_steps(self):
        workflow = (ROOT / '.github/workflows/validate.yml').read_text(encoding='utf-8')

        def step(name):
            match = re.search(
                rf'(?ms)^      - name: {re.escape(name)}\n'
                r'(.*?)(?=^      - name: |\Z)',
                workflow,
            )
            self.assertIsNotNone(match, f'missing workflow step: {name}')
            return match.group(1)

        fixture = step('Run CSP fixture regressions')
        upload = step('Upload failed CSP fixture report')
        summary = step('Summarize failed CSP fixture regressions')
        preserve = step('Preserve CSP fixture regression failure')
        self.assertIn('continue-on-error: true', fixture)
        self.assertIn('if-no-files-found: warn', upload)
        failure_condition = "if: always() && steps.csp-fixtures.outcome == 'failure'"
        for optional_step in (upload, summary, preserve):
            self.assertIn(failure_condition, optional_step)
        self.assertNotIn('continue-on-error: true', preserve)

        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / 'csp-fixture-report.json'
            summary_path = Path(directory) / 'github-step-summary.md'

            # Model a failed fixture command that did not write its optional report.
            originating_check = subprocess.run(
                ['bash', '-c', 'exit 23'],
                cwd=directory,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(originating_check.returncode, 0)
            self.assertFalse(report_path.exists())
            fixture_outcome = 'failure' if originating_check.returncode else 'success'
            self.assertEqual(fixture_outcome, 'failure')

            # The upload action itself is hosted; model its documented warn policy
            # for an absent path without claiming this test executes GitHub Actions.
            if report_path.exists():
                upload_result = 0
            elif 'if-no-files-found: warn' in upload:
                upload_result = 0
            else:
                upload_result = 1
            self.assertEqual(upload_result, 0, 'missing optional evidence must not fail upload')

            dependency = subprocess.run(
                [shutil.which('node') or 'node', '--input-type=module', '--eval', "import.meta.resolve('playwright')"],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            dependency_output = dependency.stdout + dependency.stderr
            if dependency.returncode != 0 and 'ERR_MODULE_NOT_FOUND' in dependency_output:
                self.skipTest('optional Playwright QA package is absent; focused summary was not run')

            run_match = re.search(
                r'(?ms)^        run: >-\n((?:^          [^\n]*\n?)+)',
                summary,
            )
            self.assertIsNotNone(run_match, 'CSP summary run block is not the supported folded form')
            summary_tokens = shlex.split(
                ' '.join(line.strip() for line in run_match.group(1).splitlines()),
                posix=True,
            )
            self.assertEqual(summary_tokens[:2], ['node', 'scripts/csp-qa.mjs'])
            summary_result = subprocess.run(
                [
                    shutil.which(summary_tokens[0]) or summary_tokens[0],
                    str(ROOT / summary_tokens[1]),
                    f'--fixture-summary={report_path}',
                    '--artifact-url=',
                ],
                cwd=directory,
                env={**os.environ, 'GITHUB_STEP_SUMMARY': str(summary_path)},
                capture_output=True,
                text=True,
            )
            self.assertEqual(summary_result.returncode, 0, summary_result.stdout + summary_result.stderr)
            self.assertIn('Focused CSP fixture report is missing', summary_path.read_text(encoding='utf-8'))
            self.assertFalse(report_path.exists(), 'summary generation must not create the missing report')

            preserve_run = re.search(r'(?m)^        run: ([^\r\n]+)$', preserve)
            self.assertIsNotNone(preserve_run, 'failure-preservation command is missing')
            final_guard = subprocess.run(
                preserve_run.group(1).strip(),
                shell=True,
                cwd=directory,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(final_guard.returncode, 0)
            workflow_result = final_guard.returncode
            self.assertNotEqual(
                workflow_result,
                0,
                'the originating CSP failure must remain a failed workflow after optional evidence steps',
            )

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
            f'Full route evidence artifact: [report.json](<{artifact_url}>)',
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

    def test_archived_external_report_without_failure_routes_remains_readable(self):
        code, summary = self.run_summary(
            self.load_fixture('archived-external-runtime-no-route.json'), 'external'
        )

        self.assertEqual(code, 0)
        self.assertIn('| External availability | DEGRADED | 1 outages;', summary)
        self.assertIn(
            '| unknown route | https://images.example/archived.webp '
            '| net::ERR_CONNECTION_RESET |',
            summary,
        )

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
            f'Full route evidence artifact: [report.json](<{artifact_url}>)',
            summary,
        )

    def test_external_artifact_link_escapes_label_and_special_url_characters(self):
        artifact_url = (
            'https://github.com/example/site/actions/runs/123/artifacts/987'
            '?download=1&name=report [review](draft)&next=](https://evil.example)\\path'
            '&close=>'
        )
        code, summary = self.run_summary(
            self.load_fixture('external-runtime-degraded.json'),
            'external',
            artifact_url=artifact_url,
            report_name='report [route].json',
        )

        self.assertEqual(code, 0)
        link_lines = [
            line for line in summary.splitlines()
            if line.startswith('Full route evidence artifact:')
        ]
        self.assertEqual(len(link_lines), 1)
        self.assertEqual(
            link_lines[0],
            'Full route evidence artifact: '
            '[report \\[route\\].json](<https://github.com/example/site/actions/runs/123/'
            'artifacts/987?download=1&name=report%20[review](draft)&next=]'
            '(https://evil.example)%5Cpath&close=%3E>) (direct artifact link)',
        )
        self.assertEqual(link_lines[0].count('](<https://'), 1)
        self.assertIn('&name=', link_lines[0])
        self.assertIn('%5Cpath&close=%3E>)', link_lines[0])

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
            f'Full route evidence artifact: [report.json](<{artifact_url}>)',
            summary,
        )

    def test_external_upload_unavailable_keeps_report_results_visible(self):
        for fixture, expected_code, expected_result in (
            (
                'external-runtime-degraded.json',
                0,
                '| External availability | DEGRADED |',
            ),
            (
                'external-runtime-local-failure.json',
                1,
                '| Content delivery | FAILED |',
            ),
        ):
            with self.subTest(fixture=fixture):
                code, summary = self.run_summary(
                    self.load_fixture(fixture),
                    'external',
                )
                self.assertEqual(code, expected_code)
                self.assertIn(expected_result, summary)
                self.assertIn(
                    'External report download unavailable: only the local runner file',
                    summary,
                )
                self.assertIn('not downloadable from this summary', summary)

    def test_external_missing_report_file_is_explicit_and_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / 'third-party-runtime-report.json'
            output = Path(directory) / 'summary.md'
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    '--kind',
                    'external',
                    '--report',
                    str(report),
                    '--summary',
                    str(output),
                ],
                capture_output=True,
                text=True,
                env={
                    **{
                        key: value
                        for key, value in os.environ.items()
                        if key != 'ACTIONS_ARTIFACT_URL'
                    }
                },
            )
            summary = output.read_text(encoding='utf-8')

        self.assertEqual(result.returncode, 1)
        self.assertIn('| Evidence | UNKNOWN | No usable external report:', summary)
        self.assertIn(
            'External report download unavailable: no usable local report file exists',
            summary,
        )
        self.assertIn('Check the monitor and upload steps.', summary)

    def test_direct_monitor_artifact_links_show_first_attempt_and_retry(self):
        cases = (
            (
                'external',
                self.load_fixture('external-runtime-degraded.json'),
                'https://github.com/example/site/actions/runs/100/artifacts/987',
            ),
            (
                'edge',
                self.load_fixture('live-edge-failure.json'),
                'https://github.com/example/site/actions/runs/100/artifacts/456',
            ),
        )
        for kind, report, artifact_url in cases:
            for attempt in ('1', '2'):
                with self.subTest(kind=kind, attempt=attempt):
                    _, summary = self.run_summary(
                        report,
                        kind,
                        artifact_url=artifact_url,
                        run_id='100',
                        run_attempt=attempt,
                    )
                    self.assertIn(
                        f'[report.json (run 100, attempt {attempt})](<{artifact_url}>)',
                        summary,
                    )
                    self.assertNotIn('${{ github.run_id }}', summary)
                    self.assertNotIn('${{ github.run_attempt }}', summary)

    def test_manual_direct_links_and_local_fallbacks_keep_their_existing_labels(self):
        artifact_url = 'https://github.com/example/site/actions/runs/100/artifacts/987'
        _, manual_summary = self.run_summary(
            self.load_fixture('external-runtime-degraded.json'),
            'external',
            artifact_url=artifact_url,
        )
        self.assertIn(
            f'Full route evidence artifact: [report.json](<{artifact_url}>)',
            manual_summary,
        )
        self.assertNotIn('(run 100, attempt', manual_summary)

        _, external_fallback = self.run_summary(
            self.load_fixture('external-runtime-degraded.json'),
            'external',
        )
        self.assertIn('only the local runner file report.json is available', external_fallback)

        _, edge_fallback = self.run_summary(
            self.load_fixture('live-edge-failure.json'),
            'edge',
        )
        self.assertIn('Full route evidence file: report.json.', edge_fallback)
        self.assertNotIn('(run 100, attempt', edge_fallback)

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

    def test_reparse_point_is_rejected_before_archive_or_fixture_reads(self):
        report_path = 'assets/audit/redirect/delivery/live-edge.json'
        entry = {
            'classification': 'current',
            'fixture': 'archived-live-edge-2026-09-07.json',
            'required_action': 'validate_report_shape',
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / report_path
            source.parent.mkdir(parents=True)
            source_bytes = b'{"synthetic":"reparse directory"}\n'
            source.write_bytes(source_bytes)
            fixture_directory = root / 'tests/fixtures/actions-summary'
            fixture_directory.mkdir(parents=True)
            (fixture_directory / entry['fixture']).write_bytes(source_bytes)

            reparse_directory = root / 'assets/audit/redirect'
            original_lstat = Path.lstat
            original_read_bytes = Path.read_bytes
            read_attempts = []

            def mark_as_reparse_point(path):
                metadata = original_lstat(path)
                if path == reparse_directory:
                    return SimpleNamespace(
                        st_mode=metadata.st_mode,
                        st_file_attributes=0x400,
                    )
                return metadata

            def track_file_read(path):
                read_attempts.append(path)
                return original_read_bytes(path)

            with patch.object(Path, 'lstat', mark_as_reparse_point):
                with patch.object(Path, 'read_bytes', track_file_read):
                    issues = archive_registry_issues(
                        root,
                        {report_path: entry},
                        fixture_root=root,
                        require_registered_files=True,
                    )

        self.assertTrue(
            any(
                'assets/audit/redirect' in issue
                and 'Windows reparse point' in issue
                for issue in issues
            ),
            '\n'.join(issues),
        )
        self.assertEqual(
            read_attempts,
            [],
            'archive or fixture content was read before recursive discovery rejected the reparse point',
        )



if __name__ == '__main__':
    unittest.main()

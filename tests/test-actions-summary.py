"""Regression coverage for operator summaries, including mixed failures."""
import copy
import importlib.util
import json
import os
import re
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


class SummaryTests(unittest.TestCase):
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

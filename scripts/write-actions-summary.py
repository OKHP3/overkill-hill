#!/usr/bin/env python3
"""Summarize existing QA evidence without rewriting it or probing the network."""
import argparse
from collections import Counter
import html
import ipaddress
import json
import os
from pathlib import Path
import re
from urllib.parse import quote, urlsplit


EDGE_REPORT_SCHEMA_VERSION = 1
CURRENT_EDGE_REPORT_FIELDS = frozenset({
    'schema_version', 'verifier', 'run_at', 'base', 'timeout_seconds', 'expected_commit',
    'hosting', 'status', 'summary', 'checks',
})
LEGACY_EDGE_REPORT_FIELDS = frozenset({'checks'})
ARCHIVED_PRE_VERSION_EDGE_REPORT_FIELDS = frozenset(
    field for field in CURRENT_EDGE_REPORT_FIELDS if field != 'schema_version'
)
EDGE_CHECK_FIELDS = frozenset({'check', 'status', 'evidence'})
EDGE_CHECK_STATUSES = frozenset({'PASS', 'FAIL', 'WARN', 'BLOCKED'})
MARKDOWN_DESTINATION_SAFE = ":/?#[]@!$&'()*+,;=%"
HOST_LABEL = re.compile(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\Z')


def cell(value):
    return html.escape(str(value)).replace('|', '&#124;').replace('\n', ' ').replace('\r', ' ')


def markdown_label(value):
    return cell(value).replace('\\', '\\\\').replace('[', r'\[').replace(']', r'\]')


def markdown_link(label, destination):
    escaped_destination = quote(str(destination), safe=MARKDOWN_DESTINATION_SAFE)
    return f'[{markdown_label(label)}](<{escaped_destination}>)'


def is_valid_artifact_url(value):
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(ord(character) < 0x20 or ord(character) == 0x7f for character in value)
        or re.search(r'%(?![0-9A-Fa-f]{2})', value)
    ):
        return False
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return False
    if (
        parsed.scheme.lower() != 'https'
        or not parsed.netloc
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or '\\' in parsed.netloc
        or (port is not None and port > 65535)
    ):
        return False

    if ':' in hostname:
        try:
            ipaddress.IPv6Address(hostname)
        except ValueError:
            return False
    else:
        try:
            ascii_hostname = hostname.encode('idna').decode('ascii')
        except UnicodeError:
            return False
        canonical_hostname = (
            ascii_hostname[:-1] if ascii_hostname.endswith('.') else ascii_hostname
        )
        labels = canonical_hostname.split('.')
        if (
            len(canonical_hostname) > 253
            or not labels
            or any(not HOST_LABEL.fullmatch(label) for label in labels)
        ):
            return False
    return True


def workflow_run_context():
    run_id = os.environ.get('GITHUB_RUN_ID', '').strip()
    run_attempt = os.environ.get('GITHUB_RUN_ATTEMPT', '').strip()
    if run_id and run_attempt:
        return run_id, run_attempt
    return None


def artifact_link_label(report_name):
    run_context = workflow_run_context()
    if run_context:
        run_id, run_attempt = run_context
        return f'{report_name} (run {run_id}, attempt {run_attempt})'
    return report_name


def row(label, status, evidence):
    return f'| {cell(label)} | {cell(status)} | {cell(evidence)} |'


def state(checks):
    statuses = {item['status'] for item in checks}
    if 'FAIL' in statuses:
        return 'FAILED'
    if statuses & {'BLOCKED', 'WARN'}:
        return 'PARTIAL'
    return 'PASS' if statuses else 'NOT RUN'


def prepare_edge_report(report):
    if not isinstance(report, dict):
        raise ValueError('live-edge report must be a JSON object')

    legacy_format = None
    if set(report) == LEGACY_EDGE_REPORT_FIELDS:
        legacy_format = 'checks-only'
    elif 'schema_version' in report:
        version = report['schema_version']
        if type(version) is not int or version != EDGE_REPORT_SCHEMA_VERSION:
            raise ValueError(
                f'unsupported live-edge report schema_version {version!r}; '
                f'supported version: {EDGE_REPORT_SCHEMA_VERSION}.'
            )
        if not CURRENT_EDGE_REPORT_FIELDS.issubset(report):
            raise ValueError(
                'versioned live-edge report is missing required current envelope '
                'fields; required action: regenerate it with '
                'scripts/verify-live-edge.py.'
            )
    elif set(report) == ARCHIVED_PRE_VERSION_EDGE_REPORT_FIELDS:
        # Retained reports are immutable. Keep their exact pre-versioned envelope
        # readable, but require a declared version for all other full reports.
        legacy_format = 'pre-versioned-archive'
    else:
        raise ValueError(
            'unsupported live-edge report shape; required action: migrate it to '
            'a versioned scripts/verify-live-edge.py envelope or use a documented '
            'archived shape.'
        )

    legacy = legacy_format is not None
    checks = report.get('checks')
    if not isinstance(checks, list) or not checks:
        label = 'legacy checks-only live-edge report' if legacy_format == 'checks-only' else 'live-edge report'
        raise ValueError(
            f'{label} has no checks; required action: migrate or regenerate the report.'
        )

    for index, item in enumerate(checks):
        if not isinstance(item, dict):
            if legacy:
                raise ValueError(
                    f'unsupported legacy check shape at checks[{index}]; required action: '
                    'migrate it to the current report shape or provide check, status, '
                    'and evidence.'
                )
            raise ValueError(f'live-edge report has a malformed check at index {index}')
        missing = EDGE_CHECK_FIELDS - item.keys()
        if missing:
            label = (
                'unsupported legacy check shape'
                if legacy
                else 'live-edge report has a malformed check'
            )
            raise ValueError(
                f'{label} at checks[{index}]; missing required field(s): '
                + ', '.join(sorted(missing))
                + '; required action: migrate it to the current report shape or '
                'provide check, status, and evidence.'
            )
        if (
            not isinstance(item['check'], str)
            or not item['check']
            or not isinstance(item['evidence'], str)
            or not isinstance(item['status'], str)
            or item['status'] not in EDGE_CHECK_STATUSES
        ):
            if legacy and isinstance(item['status'], str) and item['status'] not in EDGE_CHECK_STATUSES:
                raise ValueError(
                    f'unsupported legacy live-edge status convention at checks[{index}]: '
                    f'{item["status"]!r}; required action: map it to PASS, FAIL, WARN, '
                    'or BLOCKED, or migrate the report to the current verifier format.'
                )
            if legacy:
                raise ValueError(
                    f'unsupported legacy check shape at checks[{index}]; required action: '
                    'provide a non-empty check name and string evidence, or migrate it '
                    'to the current report shape.'
                )
            raise ValueError(f'live-edge report has a malformed check at index {index}')

    if legacy:
        report = dict(report)
        if legacy_format == 'checks-only':
            report['expected_commit'] = None
            report['run_at'] = 'unknown'
    return report, legacy_format


def edge_summary(report):
    report, legacy_format = prepare_edge_report(report)
    legacy = legacy_format is not None
    checks = report['checks']
    # The verifier currently labels policy checks rather than emitting categories.
    # Unrecognized checks stay in content, so a new failure cannot be hidden.
    def policy(item):
        name = item['check']
        return (' header ' in name or 'content-security-policy' in name or 'cache policy' in name
                or item['evidence'].startswith('GitHub Pages serves this response but does not apply repository _headers;'))
    content = [item for item in checks if not policy(item)]
    edge = [item for item in checks if policy(item)]
    edge_state = state(edge)
    if edge_state == 'FAILED':
        edge_evidence = f'{len(edge)} checks; confirmed policy failures remain visible'
    elif edge_state == 'PARTIAL':
        edge_evidence = f'{len(edge)} checks; BLOCKED hosting limitations do not prove enforcement'
    else:
        edge_evidence = f'{len(edge)} checks; policy checks were evaluated'
    lines = []
    if legacy_format == 'checks-only':
        lines.append(
            row(
                'Report format',
                'LEGACY',
                'checks-only compatibility; no release SHA or report time was recorded',
            )
        )
    elif legacy_format == 'pre-versioned-archive':
        lines.append(
            row(
                'Report format',
                'LEGACY',
                'retained pre-versioned envelope; archived evidence remains unchanged',
            )
        )
    lines += [row('Content delivery', state(content), f'{len(content)} checks; sampled delivery and release binding only'),
             row('Edge policy', edge_state, edge_evidence),
             row('External availability', 'NOT RUN', 'Use the separate third-party runtime report')]
    binding = next((item for item in checks if item['check'] == 'release manifest'), None)
    lines += ['', f"Expected release SHA: {cell(report.get('expected_commit') or 'not specified (monitoring)')}",
              f"Release manifest evidence: {cell(binding['evidence'] if binding else 'not checked')}",
              f"Report time: {cell(report.get('run_at', 'unknown'))}", '',
              'Repeated warnings and blocked checks (counts retain every route):', '',
              '| Status | Count | Evidence |', '| --- | --- | --- |']
    grouped = Counter((item['status'], item['evidence']) for item in checks if item['status'] in {'WARN', 'BLOCKED'})
    for (status, evidence), count in grouped.most_common(12):
        lines.append(row(status, count, evidence))
    if len(grouped) > 12:
        lines.append(f'{len(grouped) - 12} additional groups remain in the JSON artifact.')
    failures = [item for item in checks if item['status'] == 'FAIL']
    if failures:
        lines += ['', '**Confirmed first-party or policy failures:**', '']
        lines += [f"- {cell(item['check'])}: {cell(item['evidence'])}" for item in failures[:12]]
        if len(failures) > 12:
            lines.append(f'- {len(failures) - 12} additional failures remain in the JSON artifact.')
    lines += ['', 'Blocked transport checks are inconclusive. Pages-only BLOCKED policy checks do not prove enforcement and are not external outages.']
    return lines, bool(failures)


def external_summary(report):
    summary = report.get('summary')
    keys = ('routes', 'dependencies', 'available', 'externalOutages', 'localFailures', 'cspDiagnostics')
    if not isinstance(summary, dict) or any(type(summary.get(key)) is not int or summary[key] < 0 for key in keys):
        raise ValueError('third-party report has missing or invalid counts')
    if summary['routes'] == 0:
        raise ValueError('third-party report sampled no routes')
    if 'externalOutages' in report:
        outages = report['externalOutages']
    else:
        # Older archived reports may keep outage evidence only on dependency
        # records. Use this compatibility path only when the canonical array is
        # absent so current reports retain their existing rendered output.
        dependencies = report.get('dependencies', [])
        if not isinstance(dependencies, list):
            raise ValueError('third-party report has invalid dependency evidence')
        outages = [
            dependency for dependency in dependencies
            if isinstance(dependency, dict)
            and dependency.get('state') in {'unavailable', 'no-response'}
        ]
    if not isinstance(outages, list):
        raise ValueError('third-party report has invalid external outage evidence')
    failure_rows = []
    for outage in outages:
        if not isinstance(outage, dict):
            raise ValueError('third-party report has malformed external outage evidence')
        failures = outage.get('failures', [])
        if not isinstance(failures, list):
            raise ValueError('third-party report has malformed external failure evidence')
        for failure in failures:
            if not isinstance(failure, dict):
                raise ValueError('third-party report has malformed external failure evidence')
            # Archived v1 reports may predate route attribution. Keep the failure
            # visible as "unknown route" rather than hiding its outage evidence.
            route = failure.get('route') or 'unknown route'
            url = outage.get('url') or 'unknown dependency'
            error = failure.get('errorText') or 'unknown failure'
            failure_rows.append((route, url, error))

    lines = [
        row('Content delivery', 'FAILED' if summary['localFailures'] else 'PASS',
            f"{summary['localFailures']} local route failures across {summary['routes']} sampled routes"),
        row('Edge policy', 'NOT RUN', 'Use the separate live-edge report'),
        row('External availability', 'DEGRADED' if summary['externalOutages'] else ('PASS' if summary['dependencies'] else 'NOT RUN'),
            f"{summary['externalOutages']} outages; {summary['available']}/{summary['dependencies']} dependencies available"),
        row('Browser CSP diagnostics', 'WARN' if summary['cspDiagnostics'] else 'PASS',
            f"{summary['cspDiagnostics']} diagnostics; inspect the JSON evidence"),
        '', 'External outages and CSP diagnostics are non-blocking health signals. Confirmed local route failures fail this monitor.',
        'This browser monitor does not verify the deployed release SHA.',
    ]
    if failure_rows:
        lines += [
            '',
            'External failure evidence (archived failures without route attribution are shown as unknown route):',
            '',
            '| Route | Dependency | Failure |',
            '| --- | --- | --- |',
        ]
        lines += [
            f'| {cell(route)} | {cell(url)} | {cell(error)} |'
            for route, url, error in failure_rows
        ]
    return lines, bool(summary['localFailures'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind', choices=('edge', 'external'), required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument(
        '--artifact-url',
        default=os.environ.get('ACTIONS_ARTIFACT_URL', ''),
        help='Direct URL for the uploaded report artifact',
    )
    parser.add_argument('--summary', type=Path, default=os.environ.get('GITHUB_STEP_SUMMARY'))
    args = parser.parse_args()
    artifact_url = args.artifact_url if is_valid_artifact_url(args.artifact_url) else ''
    run_context = workflow_run_context()
    run_label = (
        f'{run_context[0]} / {run_context[1]}'
        if run_context
        else 'local / local'
    )
    lines = ['## Site delivery evidence', '',
             f"Workflow checkout SHA: {cell(os.environ.get('GITHUB_SHA', 'local'))}",
             f"Run / attempt: {cell(run_label)}",
             '', '| Area | State | Evidence |', '| --- | --- | --- |']
    report_available = False
    try:
        report = json.loads(args.report.read_text(encoding='utf-8'))
        if not isinstance(report, dict):
            raise ValueError('report must be a JSON object')
        details, failed = (edge_summary if args.kind == 'edge' else external_summary)(report)
        lines.extend(details)
        report_available = True
    except (OSError, ValueError) as exc:
        failed = True
        lines.append(row('Evidence', 'UNKNOWN', f'No usable {args.kind} report: {exc}'))
    if args.kind == 'external' and artifact_url:
        evidence = markdown_link(artifact_link_label(args.report.name), artifact_url)
        lines += ['', f'Full route evidence artifact: {evidence} (direct artifact link)', '']
    elif args.kind == 'external' and report_available:
        lines += [
            '',
            f'External report download unavailable: only the local runner file '
            f'{cell(args.report.name)} is available; it is not downloadable from '
            'this summary. Check the upload step.',
            '',
        ]
    elif args.kind == 'external':
        lines += [
            '',
            f'External report download unavailable: no usable local report file '
            f'exists ({cell(args.report.name)}). Check the monitor and upload steps.',
            '',
        ]
    elif artifact_url:
        evidence = markdown_link(artifact_link_label(args.report.name), artifact_url)
        lines += ['', f'Full route evidence artifact: {evidence}', '']
    elif args.kind == 'edge' and report_available:
        lines += [
            '',
            f'Live-edge report download unavailable: only the local runner file '
            f'{cell(args.report.name)} is available; it is not downloadable from '
            'this summary. Check the upload step.',
            '',
        ]
    elif args.kind == 'edge':
        lines += [
            '',
            f'Live-edge report download unavailable: no usable local report file '
            f'exists ({cell(args.report.name)}). Check the monitor and upload steps.',
            '',
        ]
    else:
        lines += ['', f'Full route evidence file: {cell(args.report.name)}. Check the upload step for artifact availability.', '']
    rendered = '\n'.join(lines)
    if args.summary:
        with args.summary.open('a', encoding='utf-8') as output:
            output.write(rendered + '\n')
    print(rendered)
    if failed and os.environ.get('GITHUB_ACTIONS') == 'true':
        print('::error::Site evidence reports confirmed first-party/policy failures or unusable evidence. See the job summary and report artifact.')
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())

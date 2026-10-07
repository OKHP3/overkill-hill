#!/usr/bin/env python3
"""Summarize existing QA evidence without rewriting it or probing the network."""
import argparse
from collections import Counter
import html
import json
import os
from pathlib import Path
from urllib.parse import quote


CURRENT_EDGE_REPORT_FIELDS = frozenset({
    'verifier', 'run_at', 'base', 'timeout_seconds', 'expected_commit',
    'hosting', 'status', 'summary', 'checks',
})
LEGACY_EDGE_REPORT_FIELDS = frozenset({'checks'})
EDGE_CHECK_FIELDS = frozenset({'check', 'status', 'evidence'})
EDGE_CHECK_STATUSES = frozenset({'PASS', 'FAIL', 'WARN', 'BLOCKED'})
MARKDOWN_DESTINATION_SAFE = ":/?#[]@!$&'()*+,;=%"


def cell(value):
    return html.escape(str(value)).replace('|', '&#124;').replace('\n', ' ').replace('\r', ' ')


def markdown_label(value):
    return cell(value).replace('\\', '\\\\').replace('[', r'\[').replace(']', r'\]')


def markdown_link(label, destination):
    escaped_destination = quote(str(destination), safe=MARKDOWN_DESTINATION_SAFE)
    return f'[{markdown_label(label)}](<{escaped_destination}>)'


def artifact_link_label(report_name):
    run_id = os.environ.get('GITHUB_RUN_ID', '').strip()
    run_attempt = os.environ.get('GITHUB_RUN_ATTEMPT', '').strip()
    if run_id and run_attempt:
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

    legacy = set(report) == LEGACY_EDGE_REPORT_FIELDS
    if not legacy and not CURRENT_EDGE_REPORT_FIELDS.issubset(report):
        raise ValueError(
            'unsupported live-edge report shape; required action: migrate it to '
            'the current scripts/verify-live-edge.py envelope or use the '
            'documented checks-only legacy shape with check, status, and evidence '
            'fields.'
        )

    checks = report.get('checks')
    if not isinstance(checks, list) or not checks:
        label = 'legacy checks-only live-edge report' if legacy else 'live-edge report'
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
        report['expected_commit'] = None
        report['run_at'] = 'unknown'
    return report, legacy


def edge_summary(report):
    report, legacy = prepare_edge_report(report)
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
    if legacy:
        lines.append(
            row(
                'Report format',
                'LEGACY',
                'checks-only compatibility; no release SHA or report time was recorded',
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
    return [
        row('Content delivery', 'FAILED' if summary['localFailures'] else 'PASS',
            f"{summary['localFailures']} local route failures across {summary['routes']} sampled routes"),
        row('Edge policy', 'NOT RUN', 'Use the separate live-edge report'),
        row('External availability', 'DEGRADED' if summary['externalOutages'] else ('PASS' if summary['dependencies'] else 'NOT RUN'),
            f"{summary['externalOutages']} outages; {summary['available']}/{summary['dependencies']} dependencies available"),
        row('Browser CSP diagnostics', 'WARN' if summary['cspDiagnostics'] else 'PASS',
            f"{summary['cspDiagnostics']} diagnostics; inspect the JSON evidence"),
        '', 'External outages and CSP diagnostics are non-blocking health signals. Confirmed local route failures fail this monitor.',
        'This browser monitor does not verify the deployed release SHA.',
    ], bool(summary['localFailures'])


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
    lines = ['## Site delivery evidence', '',
             f"Workflow checkout SHA: {cell(os.environ.get('GITHUB_SHA', 'local'))}",
             f"Run / attempt: {cell(os.environ.get('GITHUB_RUN_ID', 'local'))} / {cell(os.environ.get('GITHUB_RUN_ATTEMPT', 'local'))}",
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
    if args.kind == 'external' and args.artifact_url:
        evidence = markdown_link(artifact_link_label(args.report.name), args.artifact_url)
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
    elif args.artifact_url:
        evidence = markdown_link(artifact_link_label(args.report.name), args.artifact_url)
        lines += ['', f'Full route evidence artifact: {evidence}', '']
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

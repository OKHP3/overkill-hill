#!/usr/bin/env python3
"""Report whether open, labeled Glee foundation PRs match the current main branch.

This is a read-only diagnostic. It never updates a branch or merges a pull
request; GitHub branch protection and review requirements remain authoritative.
"""

import argparse
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


OWNER = 'OKHP3'
REPOSITORY = 'Glee-fullyTools'
BASE_BRANCH = 'main'
FOUNDATION_PR_LABEL = 'foundation-sync'
HISTORICAL_PR_NUMBER = 42
PAGE_SIZE = 100
API_ROOT = 'https://api.github.com'


class GitHubAPIError(RuntimeError):
    """A bounded, non-sensitive GitHub API failure."""


def api_get(path):
    root = os.environ.get('GITHUB_API_URL', API_ROOT).rstrip('/')
    request = Request(
        f'{root}{path}',
        headers={
            'Accept': 'application/vnd.github+json',
            'User-Agent': 'okhp3-foundation-pr-freshness',
            'X-GitHub-Api-Version': '2022-11-28',
        },
        method='GET',
    )
    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode('utf-8'))
    except HTTPError as exc:
        raise GitHubAPIError(
            f'GitHub API GET {path} returned HTTP {exc.code}'
        ) from None
    except URLError as exc:
        raise GitHubAPIError(
            f'GitHub API GET {path} failed: {exc.reason}'
        ) from None
    except OSError as exc:
        raise GitHubAPIError(
            f'GitHub API GET {path} failed: {type(exc).__name__}'
        ) from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise GitHubAPIError(f'GitHub API GET {path} returned invalid JSON') from None


def list_open_foundation_prs(get_json):
    matches = []
    for page in range(1, 11):
        query = urlencode({
            'state': 'open',
            'base': BASE_BRANCH,
            'per_page': PAGE_SIZE,
            'page': page,
        })
        response = get_json(
            f'/repos/{OWNER}/{REPOSITORY}/pulls?{query}'
        )
        if not isinstance(response, list):
            raise GitHubAPIError('GitHub returned an invalid open pull request list')
        for pull in response:
            if not isinstance(pull, dict):
                raise GitHubAPIError(
                    'GitHub returned an invalid pull request entry'
                )
            base = pull.get('base')
            head = pull.get('head')
            if not isinstance(base, dict) or not isinstance(head, dict):
                raise GitHubAPIError(
                    'GitHub returned a pull request without base or head details'
                )
            labels = pull.get('labels')
            if not isinstance(labels, list) or any(
                not isinstance(label, dict)
                or not isinstance(label.get('name'), str)
                for label in labels
            ):
                raise GitHubAPIError(
                    'GitHub returned a pull request with invalid labels'
                )
            base_ref = base.get('ref')
            if base_ref == BASE_BRANCH and any(
                label['name'] == FOUNDATION_PR_LABEL for label in labels
            ):
                matches.append(pull)
        if len(response) < PAGE_SIZE:
            return matches
    raise GitHubAPIError(
        'More than 1,000 open Glee pull requests; freshness scan was incomplete'
    )


def compare_main_to_head(get_json, current_main_sha, head_sha):
    comparison = get_json(
        f'/repos/{OWNER}/{REPOSITORY}/compare/'
        f'{current_main_sha}...{head_sha}'
    )
    if not isinstance(comparison, dict):
        raise GitHubAPIError('GitHub returned an invalid commit comparison')
    try:
        behind_by = int(comparison['behind_by'])
        ahead_by = int(comparison['ahead_by'])
    except (KeyError, TypeError, ValueError):
        raise GitHubAPIError('GitHub returned an incomplete commit comparison') from None
    return {
        'status': comparison.get('status', 'unknown'),
        'aheadBy': ahead_by,
        'behindBy': behind_by,
        'mergeBaseRevision': (
            comparison.get('merge_base_commit', {}).get('sha')
            if isinstance(comparison.get('merge_base_commit'), dict)
            else None
        ),
    }


def classify_open_pr(pull, current_main_sha, comparison):
    mergeable = pull.get('mergeable')
    mergeable_state = pull.get('mergeable_state') or 'unknown'
    if mergeable is False or mergeable_state == 'dirty':
        status = 'CONFLICT'
        action = (
            f'Update this branch against Glee main at {current_main_sha}, resolve '
            'the conflicts on the PR branch, rerun required checks, and satisfy '
            'required reviews. Resolve all review conversations and merge only '
            'through the protected PR.'
        )
    elif comparison['behindBy'] > 0 or mergeable_state == 'behind':
        status = 'BEHIND'
        action = (
            f'Bring this branch up to date with Glee main at {current_main_sha}; '
            'then rerun required checks and refresh any required approvals. '
            'Resolve all review conversations and merge only through the '
            'protected PR.'
        )
    elif mergeable is None or mergeable_state == 'unknown':
        status = 'UNKNOWN'
        action = (
            'Rerun this read-only check after GitHub computes mergeability. Do not '
            'treat unknown status as approval or merge readiness.'
        )
    elif mergeable_state in {'blocked', 'unstable', 'draft'} or pull.get('draft'):
        status = 'PROTECTED_CHECKS_PENDING'
        action = (
            'No base update is detected. Complete required checks and approvals, '
            'resolve all review conversations, and merge only through the '
            'protected PR.'
        )
    else:
        status = 'CURRENT'
        action = (
            'No base reconciliation is needed. Complete required checks and '
            'approvals, resolve all review conversations, and merge only through '
            'the protected PR.'
        )

    base = pull.get('base', {})
    head = pull.get('head', {})
    return {
        'number': pull.get('number'),
        'status': status,
        'headBranch': head.get('ref'),
        'headRevision': head.get('sha'),
        'prBaseRevision': base.get('sha'),
        'currentBaseRevision': current_main_sha,
        'mergeableState': mergeable_state,
        'comparison': comparison,
        'requiredAction': action,
    }


def collect_report(get_json=None):
    get_json = get_json or api_get
    branch = get_json(f'/repos/{OWNER}/{REPOSITORY}/branches/{BASE_BRANCH}')
    if not isinstance(branch, dict):
        raise GitHubAPIError('GitHub returned an invalid Glee main branch record')
    current_main_sha = branch.get('commit', {}).get('sha')
    if not current_main_sha:
        raise GitHubAPIError('GitHub did not return the current Glee main revision')

    candidates = list_open_foundation_prs(get_json)
    if candidates:
        checks = []
        for candidate in candidates:
            number = candidate.get('number')
            if not isinstance(number, int):
                raise GitHubAPIError(
                    'GitHub returned a foundation pull request without a number'
                )
            pull = get_json(
                f'/repos/{OWNER}/{REPOSITORY}/pulls/{number}'
            )
            if not isinstance(pull, dict):
                raise GitHubAPIError(
                    f'GitHub returned an invalid record for PR #{number}'
                )
            if pull.get('state') != 'open':
                checks.append({
                    'number': number,
                    'status': 'CLOSED_DURING_CHECK',
                    'headBranch': pull.get('head', {}).get('ref'),
                    'headRevision': pull.get('head', {}).get('sha'),
                    'currentBaseRevision': current_main_sha,
                    'requiredAction': (
                        'Refresh the read-only status before acting; this pull '
                        'request closed while the check was running.'
                    ),
                })
                continue
            head_sha = pull.get('head', {}).get('sha')
            if not head_sha:
                raise GitHubAPIError(
                    f'GitHub did not return the head revision for PR #{number}'
                )
            comparison = compare_main_to_head(
                get_json, current_main_sha, head_sha
            )
            checks.append(classify_open_pr(pull, current_main_sha, comparison))

        statuses = {check['status'] for check in checks}
        if 'CONFLICT' in statuses:
            status = 'CONFLICT'
        elif 'BEHIND' in statuses:
            status = 'BEHIND'
        elif 'UNKNOWN' in statuses or 'CLOSED_DURING_CHECK' in statuses:
            status = 'UNKNOWN'
        elif 'PROTECTED_CHECKS_PENDING' in statuses:
            status = 'PROTECTED_CHECKS_PENDING'
        else:
            status = 'CURRENT'
        return {
            'repository': f'{OWNER}/{REPOSITORY}',
            'baseBranch': BASE_BRANCH,
            'currentBaseRevision': current_main_sha,
            'status': status,
            'openFoundationPullRequests': checks,
            'requiredAction': (
                'Review each open foundation PR status below. This diagnostic '
                'does not update branches or merge pull requests.'
            ),
        }

    historical = get_json(
        f'/repos/{OWNER}/{REPOSITORY}/pulls/{HISTORICAL_PR_NUMBER}'
    )
    if not isinstance(historical, dict):
        raise GitHubAPIError(
            f'GitHub returned an invalid record for PR #{HISTORICAL_PR_NUMBER}'
        )
    historical_head = historical.get('head', {}).get('sha')
    comparison = (
        compare_main_to_head(get_json, current_main_sha, historical_head)
        if historical_head
        else None
    )
    merged_at = historical.get('merged_at')
    if merged_at:
        action = (
            f'No rebase or update is required for historical PR '
            f'#{HISTORICAL_PR_NUMBER}; it was already merged. Its old branch is '
            'not a live release candidate. For new foundation work, create a '
            f'fresh branch from current Glee main at {current_main_sha} and use '
            'the protected PR workflow.'
        )
        historical_status = 'MERGED'
    else:
        action = (
            f'No open foundation-sync PR targets Glee main. PR '
            f'#{HISTORICAL_PR_NUMBER} is not merged; if its work is still needed, '
            f'create a fresh branch from current Glee main at {current_main_sha} '
            'and continue through the protected PR workflow.'
        )
        historical_status = 'CLOSED' if historical.get('state') == 'closed' else 'NOT_FOUND'

    return {
        'repository': f'{OWNER}/{REPOSITORY}',
        'baseBranch': BASE_BRANCH,
        'currentBaseRevision': current_main_sha,
        'status': 'NO_OPEN_FOUNDATION_PR',
        'openFoundationPullRequests': [],
        'historicalPullRequest': {
            'number': HISTORICAL_PR_NUMBER,
            'status': historical_status,
            'headBranch': historical.get('head', {}).get('ref'),
            'headRevision': historical_head,
            'mergedAt': merged_at,
            'mergeCommitRevision': historical.get('merge_commit_sha'),
            'comparison': comparison,
        },
        'requiredAction': action,
    }


def inline_code(value):
    return '`' + str(value).replace('`', '&#96;') + '`'


def render_summary(report):
    current_sha = report.get('currentBaseRevision') or 'unavailable'
    lines = [
        '## Glee foundation PR freshness',
        '',
        f'Current Glee {inline_code("main")} base revision: {inline_code(current_sha)}',
        f"Status: **{report.get('status', 'UNKNOWN')}**",
        '',
    ]
    checks = report.get('openFoundationPullRequests', [])
    if checks:
        for check in checks:
            lines.extend([
                f"### PR #{check.get('number')} — {check.get('status')}",
                f"- Branch: {inline_code(check.get('headBranch', 'unknown'))}",
                f"- PR head revision: {inline_code(check.get('headRevision', 'unknown'))}",
                f"- PR's recorded base revision: {inline_code(check.get('prBaseRevision', 'unknown'))}",
                f"- Current Glee main revision: {inline_code(current_sha)}",
                f"- Main commits missing from branch: {check.get('comparison', {}).get('behindBy', 'unknown')}",
                f"- Required action: {check.get('requiredAction', 'Rerun the status check.')}",
                '',
            ])
    else:
        historical = report.get('historicalPullRequest')
        if report.get('status') == 'ERROR':
            lines.append(
                'Open foundation-sync pull request status is unavailable because '
                'this scan did not complete.'
            )
            lines.append('')
        elif historical:
            lines.append(
                f"Historical PR #{historical.get('number')}: "
                f"**{historical.get('status')}**"
            )
            lines.append(
                f"- Former branch: {inline_code(historical.get('headBranch', 'unknown'))}"
            )
            lines.append(
                f"- Former head revision: {inline_code(historical.get('headRevision', 'unknown'))}"
            )
            if historical.get('mergedAt'):
                lines.append(f"- Merged at: {historical['mergedAt']}")
            if historical.get('mergeCommitRevision'):
                lines.append(
                    f"- Merge commit: {inline_code(historical['mergeCommitRevision'])}"
                )
            comparison = historical.get('comparison')
            if comparison and comparison.get('behindBy', 0) > 0:
                lines.append(
                    f"- The merged branch is now behind current main by "
                    f"{comparison['behindBy']} commits; this is expected after "
                    'later main advances.'
                )
            lines.append('')
        else:
            lines.append('No open foundation-sync pull request targets Glee main.')
            lines.append('')
        lines.append(
            f"Required action: {report.get('requiredAction', 'Review the status before acting.')}"
        )
        lines.append('')

    if report.get('error'):
        lines.extend([f"Diagnostic error: {report['error']}", ''])
    lines.append(
        'This check is read-only. It does not update branches, create comments, '
        'or merge PRs. Required branch protection and review-thread resolution '
        'remain in force.'
    )
    return '\n'.join(lines) + '\n'


def write_evidence(report, report_path, summary_path=None):
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )
    summary = render_summary(report)
    if summary_path:
        summary_path = Path(summary_path)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        with summary_path.open('a', encoding='utf-8') as output:
            output.write(summary)
    print(summary, end='')


def exit_code(report):
    status = report.get('status')
    if status in {'BEHIND', 'CONFLICT'}:
        return 1
    if status in {'UNKNOWN', 'ERROR'}:
        return 2
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument(
        '--summary',
        type=Path,
        default=os.environ.get('GITHUB_STEP_SUMMARY'),
    )
    args = parser.parse_args(argv)
    try:
        report = collect_report()
    except (GitHubAPIError, AttributeError, KeyError, TypeError, ValueError) as exc:
        report = {
            'repository': f'{OWNER}/{REPOSITORY}',
            'baseBranch': BASE_BRANCH,
            'currentBaseRevision': None,
            'status': 'ERROR',
            'openFoundationPullRequests': [],
            'requiredAction': (
                'Rerun this read-only check after GitHub API access recovers. '
                'Do not treat this error as evidence that a branch is current.'
            ),
            'error': str(exc),
        }
    write_evidence(report, args.report, args.summary)
    return exit_code(report)


if __name__ == '__main__':
    raise SystemExit(main())

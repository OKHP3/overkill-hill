"""Exercise actual workflow group expressions across trigger/caller contexts.

This is a bounded expression fixture, not a GitHub scheduler simulation.
Live cancellation, deployment ordering, and retry acceptance remain CI checks.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
VALIDATE = (ROOT / '.github/workflows/validate.yml').read_text(encoding='utf-8')
PAGES = (ROOT / '.github/workflows/pages.yml').read_text(encoding='utf-8')
FOUNDATION_SITES = json.loads(
    (ROOT / 'config/theme-control-sites.json').read_text(encoding='utf-8')
)['sites']


def job(source, name):
    match = re.search(rf'^  {re.escape(name)}:\n(.*?)(?=^  [\w-]+:|\Z)', source, re.M | re.S)
    if not match:
        raise AssertionError(f'missing job {name}')
    return match[1]


def step(source, name):
    match = re.search(
        rf'^      - name: {re.escape(name)}\n(.*?)(?=^      - name:|\Z)',
        source,
        re.M | re.S,
    )
    if not match:
        raise AssertionError(f'missing step {name}')
    return match[1]


def artifact_upload_steps(source):
    return {
        match[1]: match[2]
        for match in re.finditer(
            r'^      - name: ([^\n]+)\n(.*?)(?=^      - name: |^  [\w-]+:\s*$|\Z)',
            source,
            re.M | re.S,
        )
        if re.search(r'(?m)^\s+uses: actions/upload-artifact@', match[2])
    }


def artifact_name(source, step_name, context):
    upload_step = step(source, step_name)
    match = re.search(r'(?m)^\s+name: (.+)$', upload_step)
    if not match:
        raise AssertionError(f'missing artifact name in step {step_name}')
    template = match[1]
    return re.sub(
        r'\$\{\{\s*github\.(run_id|run_attempt|sha)\s*\}\}',
        lambda found: context[found[1]],
        template,
    )


def group(source, context):
    template = re.search(r'^      group: (.+)$', source, re.M).group(1)

    def expression(match):
        text = match[1].strip()
        def atom(value):
            value = value.strip()
            if ' == ' in value:
                left, right = value.split(' == ', 1)
                return atom(left) == atom(right)
            if value.startswith('github.'):
                return context[value.removeprefix('github.')]
            if re.fullmatch("'[^']*'", value):
                return value[1:-1]
            raise AssertionError(f'unsupported fixture expression: {value}')
        for disjunction in text.split(' || '):
            result = True
            for conjunction in disjunction.split(' && '):
                result = result and atom(conjunction)
            if result:
                return str(result)
        return str(result)

    return re.sub(r'\$\{\{(.*?)\}\}', expression, template)


def context(
    workflow='Site Validation',
    event_name='push',
    ref='refs/heads/main',
    run_id='100',
    run_attempt='1',
    sha='abcdef1234567890',
):
    return locals()


class ConcurrencyTests(unittest.TestCase):
    def test_all_validation_artifact_names_are_unique_and_keep_their_purpose_prefixes(self):
        expected_prefixes = {
            'Upload shared-foundation fingerprint report': 'foundation-fingerprints-',
            'Upload local QA reports': 'local-qa-',
            'Upload failed CSP fixture report': 'csp-fixture-regressions-',
            'Upload theme-control revision evidence': 'theme-control-revisions-',
            'Upload contrast audit report for fork pull requests': 'contrast-audit-',
            'Upload the validated Pages release artifact': 'validated-site-',
            'Upload third-party runtime inventory': 'third-party-runtime-',
            'Upload live-edge monitoring report': 'live-edge-monitor-',
        }
        uploads = artifact_upload_steps(VALIDATE)
        self.assertEqual(
            set(uploads),
            set(expected_prefixes),
            'update the expected purpose prefixes when validation artifact uploads change',
        )

        synthetic_run = context(run_id='200', run_attempt='3', sha='0123456789abcdef')
        rendered_names = {}
        for upload_step, prefix in expected_prefixes.items():
            with self.subTest(upload_step=upload_step):
                rendered_name = artifact_name(VALIDATE, upload_step, synthetic_run)
                self.assertNotIn('${{', rendered_name, f'unrendered expression in {upload_step}')
                self.assertTrue(
                    rendered_name.startswith(prefix),
                    f'{upload_step} must keep the {prefix!r} purpose prefix',
                )
                rendered_names.setdefault(rendered_name, []).append(upload_step)

        collisions = {
            rendered_name: upload_steps
            for rendered_name, upload_steps in rendered_names.items()
            if len(upload_steps) > 1
        }
        self.assertFalse(
            collisions,
            'validation artifact name collisions: '
            + '; '.join(
                f'{name!r} is shared by upload steps {", ".join(upload_steps)}'
                for name, upload_steps in collisions.items()
            ),
        )

    def test_foundation_fingerprint_report_is_retained_after_verification(self):
        source = job(VALIDATE, 'validate')
        verify_step = step(source, 'Verify pinned cross-site foundation fingerprints')
        upload_step = step(source, 'Upload shared-foundation fingerprint report')
        self.assertIn('--report-file foundation-fingerprint-report.json', verify_step)
        self.assertIn(
            "if: always() && steps.foundation_verification.outcome != 'skipped'",
            upload_step,
        )
        self.assertIn('path: foundation-fingerprint-report.json', upload_step)
        self.assertIn('retention-days: 30', upload_step)
        self.assertIn('if-no-files-found: error', upload_step)
        self.assertRegex(
            upload_step,
            r'(?m)^\s+name: foundation-fingerprints-\$\{\{\s*github\.run_id\s*\}\}-\$\{\{\s*github\.run_attempt\s*\}\}$',
        )
        self.assertLess(
            source.index('- name: Verify pinned cross-site foundation fingerprints'),
            source.index('- name: Upload shared-foundation fingerprint report'),
        )

    def test_theme_control_fetches_pinned_foundations_before_reviewed_checkouts(self):
        source = job(VALIDATE, 'validate')
        fetch_step = step(source, 'Verify pinned theme-control foundation revisions are fetchable')
        self.assertIn(
            'git -C "$probe_dir" fetch --no-tags --depth=1 --filter=tree:0',
            fetch_step,
        )
        self.assertIn('config/theme-control-sites.json', fetch_step)
        self.assertIn('jq -er', fetch_step)
        self.assertIn('while IFS=$\'\\t\' read -r site revision_variable repository; do', fetch_step)
        self.assertIn('revision="${!revision_variable}"', fetch_step)
        self.assertIn('verify_revision \\\n              "$site" \\\n              "$revision_variable" \\\n              "$repository" \\\n              "$revision" || fetch_status=1', fetch_step)
        self.assertIn('git remote get-url origin', fetch_step)
        self.assertIn('https://github.com/${repository}.git', fetch_step)
        query_match = re.search(
            r"site_fetch_inputs=\"\$\(jq -er '(?P<query>.*?)' "
            r"config/theme-control-sites\.json\)\"",
            fetch_step,
            re.S,
        )
        self.assertIsNotNone(query_match, 'fetch inputs must be generated from the shared site list')
        query = textwrap.dedent(query_match['query'])
        generated = subprocess.run(
            ['jq', '-er', query, str(ROOT / 'config/theme-control-sites.json')],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        self.assertEqual(
            [line.split('\t') for line in generated],
            [
                [site['name'], site['revisionVariable'], site.get('repository', '')]
                for site in FOUNDATION_SITES
            ],
        )
        self.assertIn(
            'foundation revision could not be fetched from',
            fetch_step,
        )
        self.assertIn(
            'fetched unexpected revision',
            fetch_step,
        )
        self.assertNotIn('verify_revision \\\n            "OKH"', fetch_step)
        self.assertNotIn('verify_revision \\\n            "Glee"', fetch_step)
        self.assertNotIn('verify_revision \\\n            "AskJamie"', fetch_step)

        fetch_position = source.index(
            '- name: Verify pinned theme-control foundation revisions are fetchable',
        )
        for checkout_name in (
            'Checkout reviewed Glee foundation revision',
            'Checkout reviewed AskJamie foundation revision',
        ):
            with self.subTest(checkout=checkout_name):
                self.assertLess(
                    fetch_position,
                    source.index(f'- name: {checkout_name}'),
                    'pinned revision fetches must fail before reviewed checkouts',
                )
        self.assertLess(
            fetch_position,
            source.index('- name: Run shared theme-control regressions'),
            'pinned revision fetches must fail before the browser audit',
        )

    def test_theme_control_fetch_results_are_retained_with_revision_variables(self):
        source = job(VALIDATE, 'validate')
        fetch_step = step(source, 'Verify pinned theme-control foundation revisions are fetchable')
        preserve_step = step(source, 'Preserve pinned foundation fetch failure')
        upload_step = step(source, 'Upload theme-control revision evidence')

        self.assertIn('id: foundation_fetch', fetch_step)
        self.assertIn('continue-on-error: true', fetch_step)
        self.assertIn(
            'Fetch check: %s (%s=%s): FAILED; could not fetch from %s',
            fetch_step,
        )
        self.assertIn(
            'Fetch check: %s (%s=%s): FAILED; fetched unexpected revision %s from %s',
            fetch_step,
        )
        self.assertIn(
            'Fetch check: %s (%s=%s): PASS; fetched %s',
            fetch_step,
        )
        self.assertIn('|| fetch_status=1', fetch_step)
        self.assertIn('fetch_status=1', fetch_step)
        self.assertIn('done <<< "$site_fetch_inputs"', fetch_step)
        self.assertIn('exit "$fetch_status"', fetch_step)
        self.assertIn('tee -a theme-control-revisions.txt', fetch_step)

        self.assertIn(
            "if: always() && steps.foundation_fetch.outcome == 'failure'",
            preserve_step,
        )
        self.assertLess(
            source.index('- name: Preserve pinned foundation fetch failure'),
            source.index('- name: Fetch reviewed OKH foundation revision'),
            'failed fetch preflight must be preserved before revision checkouts run',
        )
        self.assertIn('if: always()', upload_step)
        self.assertIn('path: theme-control-revisions.txt', upload_step)
        self.assertIn('retention-days: 30', upload_step)

    def test_theme_control_fetch_helper_reports_an_unavailable_revision_offline(self):
        source = job(VALIDATE, 'validate')
        fetch_step = step(source, 'Verify pinned theme-control foundation revisions are fetchable')
        function_match = re.search(
            r'(?ms)^          verify_revision\(\) \{\n.*?^          \}',
            fetch_step,
        )
        self.assertIsNotNone(function_match, 'missing workflow verify_revision helper')
        helper = textwrap.dedent(function_match.group(0))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture_repository = root / 'empty-foundation.git'
            subprocess.run(
                ['git', 'init', '--bare', str(fixture_repository)],
                check=True,
                capture_output=True,
                text=True,
            )
            environment = os.environ.copy()
            environment['RUNNER_TEMP'] = str(root / 'runner-temp')
            script = (
                'set -euo pipefail\n'
                f'{helper}\n'
                'verify_revision "FixtureSite" "THEME_CONTROL_FIXTURE_REVISION" '
                f'"{fixture_repository}" "{"1" * 40}"\n'
            )
            result = subprocess.run(
                ['bash', '-c', script],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0, 'unavailable revision must fail')
            output = result.stdout + result.stderr
            self.assertIn('FixtureSite', output)
            self.assertIn('THEME_CONTROL_FIXTURE_REVISION', output)
            self.assertIn('foundation revision could not be fetched', output)
            evidence = (root / 'theme-control-revisions.txt').read_text(encoding='utf-8')
            self.assertIn('FixtureSite (THEME_CONTROL_FIXTURE_REVISION=', evidence)
            self.assertIn('FAILED; could not fetch from', evidence)

    def test_theme_control_sites_use_all_reviewed_checkout_revisions(self):
        source = job(VALIDATE, 'validate')
        theme_step = step(source, 'Run shared theme-control regressions')
        sites = FOUNDATION_SITES
        self.assertEqual(len(sites), 3, 'shared foundation contract must contain exactly three reviewed sites')
        expected_names = {site['name'] for site in sites}
        self.assertEqual(
            len(expected_names),
            len(sites),
            'shared foundation contract must not contain duplicate site names',
        )
        configured_match = re.search(
            r'THEME_CONTROL_SITES: >-\n(?P<json>.*?)\n\s+run:',
            theme_step,
            re.S,
        )
        if configured_match is None:
            self.fail('missing THEME_CONTROL_SITES configuration')
        configured_entries = json.loads(
            ''.join(line.strip() for line in configured_match['json'].splitlines())
        )
        expected_paths = {site['name']: site['checkoutPath'] for site in sites}
        configured = {}
        for site in configured_entries:
            name = site.get('name')
            if name in configured:
                expected_path = expected_paths.get(name, site.get('root', '<unknown>'))
                self.fail(
                    f'duplicate THEME_CONTROL_SITES site {name!r}; '
                    f'expected checkout path {expected_path}',
                )
            configured[name] = site

        self.assertEqual(
            len(configured_entries),
            len(expected_names),
            'THEME_CONTROL_SITES must contain exactly the three reviewed sites',
        )
        self.assertEqual(
            set(configured),
            expected_names,
            'THEME_CONTROL_SITES must contain exactly OKH, Glee, and AskJamie',
        )

        for site in sites:
            name = site['name']
            expected_path = site['checkoutPath']
            revision_variable = site['revisionVariable']
            checkout_name = site['checkoutStep']
            expected_repository = site.get('repository')
            with self.subTest(site=name):
                configured_site = configured.get(name)
                self.assertIsNotNone(
                    configured_site,
                    f'{name} expected THEME_CONTROL_SITES root {expected_path}',
                )
                self.assertEqual(
                    configured_site.get('root') if configured_site else None,
                    expected_path,
                    f'{name} expected THEME_CONTROL_SITES root {expected_path}',
                )

                revision_match = re.search(
                    rf'(?m)^\s+{re.escape(revision_variable)}: ([0-9a-f]{{40}})$', source,
                )
                self.assertIsNotNone(revision_match, f'{name} requires a full immutable SHA')
                revision = revision_match[1]
                self.assertEqual(
                    configured_site.get('revision') if configured_site else None,
                    revision,
                    f'{name} expected THEME_CONTROL_SITES revision from the accepted workflow pin',
                )
                if configured_site:
                    self.assertIn(revision_variable, source)

                try:
                    checkout_step = step(source, checkout_name)
                except AssertionError:
                    self.fail(
                        f'{name} expected checkout path {expected_path} and '
                        f'full-SHA revision {revision_variable}',
                    )
                checkout_path_match = re.search(r'(?m)^\s+path: (.+)$', checkout_step)
                checkout_path = checkout_path_match[1] if checkout_path_match else '.'
                self.assertEqual(
                    checkout_path,
                    expected_path,
                    f'{name} expected checkout path {expected_path}',
                )

                if name == 'OKH':
                    try:
                        fetch_step = step(source, 'Fetch reviewed OKH foundation revision')
                    except AssertionError:
                        self.fail(
                            f'{name} expected fetched full-SHA revision for {expected_path}',
                        )
                    self.assertRegex(
                        fetch_step,
                        r'git fetch --no-tags --depth=1 origin "\$THEME_CONTROL_OKH_REVISION"',
                        f'{name} expected fetched full-SHA revision for {expected_path}',
                    )
                else:
                    self.assertIn(
                        f'repository: {expected_repository}',
                        checkout_step,
                        f'{name} expected repository {expected_repository} at {expected_path}',
                    )
                    expected_ref = '${{ env.' + revision_variable + ' }}'
                    self.assertIn(
                        f'ref: {expected_ref}',
                        checkout_step,
                        f'{name} expected checkout ref {revision_variable} for {expected_path}',
                    )

    def test_workflow_cancellation_cannot_reach_deployment(self):
        self.assertNotRegex(VALIDATE, r'(?m)^concurrency:')
        self.assertNotRegex(PAGES, r'(?m)^concurrency:')
        deploy = job(PAGES, 'deploy')
        self.assertIn('needs: validate', deploy)
        self.assertIn('cancel-in-progress: false', deploy)
        self.assertEqual(group(deploy, context()), 'pages')

    def test_standalone_and_reusable_push_do_not_collide(self):
        source = job(VALIDATE, 'validate')
        self.assertNotEqual(group(source, context()), group(source, context(workflow='Publish GitHub Pages')))

    def test_rapid_pushes_and_old_rerun_do_not_cancel_latest(self):
        source = job(VALIDATE, 'validate')
        for workflow in ('Site Validation', 'Publish GitHub Pages'):
            old = group(source, context(workflow=workflow, run_id='100', run_attempt='2'))
            latest = group(source, context(workflow=workflow, run_id='101'))
            self.assertNotEqual(old, latest)

    def test_dispatch_and_push_and_separate_dispatches_are_isolated(self):
        source = job(VALIDATE, 'validate')
        cases = [context(), context(event_name='workflow_dispatch'),
                 context(event_name='workflow_dispatch', run_id='101')]
        self.assertEqual(len({group(source, case) for case in cases}), 3)

    def test_pr_required_name_and_latest_revision_are_preserved(self):
        source = job(VALIDATE, 'validate')
        self.assertIn('name: Validate site HTML, links, and structure', source)
        self.assertIn('cancel-in-progress: true', source)
        first = context(event_name='pull_request', ref='refs/pull/1/merge')
        second = dict(first, run_id='101')
        other = dict(first, ref='refs/pull/2/merge')
        self.assertEqual(group(source, first), group(source, second))
        self.assertNotEqual(group(source, first), group(source, other))
        self.assertRegex(VALIDATE, r'(?m)^  pull_request:')

    def test_monitors_do_not_cancel_manual_validation_or_each_other(self):
        cases = [context(event_name='workflow_dispatch'),
                 context(event_name='workflow_dispatch', run_id='101'),
                 context(event_name='schedule')]
        groups = [group(job(VALIDATE, name), case) for name in
                  ('validate', 'monitor-third-party-runtime', 'monitor-live-edge') for case in cases]
        self.assertEqual(len(set(groups)), len(groups))

    def test_summaries_run_even_after_check_failure(self):
        for source, kind in ((job(PAGES, 'deploy'), 'edge'),
                             (job(VALIDATE, 'monitor-live-edge'), 'edge'),
                             (job(VALIDATE, 'monitor-third-party-runtime'), 'external')):
            self.assertRegex(source, rf'if: always\(\)\n        run: python3 scripts/write-actions-summary.py --kind {kind}')

    def test_monitor_artifacts_separate_first_attempts_from_retries(self):
        cases = (
            (
                'monitor-third-party-runtime',
                'Upload third-party runtime inventory',
                'Summarize external availability and first-party failures',
                'upload-third-party-runtime-report',
            ),
            (
                'monitor-live-edge',
                'Upload live-edge monitoring report',
                'Summarize content delivery and edge policy',
                'upload-live-edge-report',
            ),
        )
        first_attempt = context(run_id='100', run_attempt='1')
        retry = context(run_id='100', run_attempt='2')
        for job_name, upload_step, summary_step, upload_id in cases:
            with self.subTest(job=job_name):
                source = job(VALIDATE, job_name)
                first_name = artifact_name(source, upload_step, first_attempt)
                retry_name = artifact_name(source, upload_step, retry)
                self.assertIn('100-1', first_name)
                self.assertIn('100-2', retry_name)
                self.assertNotEqual(first_name, retry_name)
                self.assertIn(
                    f'steps.{upload_id}.outputs.artifact-url',
                    step(source, summary_step),
                )

        same_attempt = context(run_id='200', run_attempt='3')
        third_party_name = artifact_name(
            job(VALIDATE, 'monitor-third-party-runtime'),
            'Upload third-party runtime inventory',
            same_attempt,
        )
        live_edge_name = artifact_name(
            job(VALIDATE, 'monitor-live-edge'),
            'Upload live-edge monitoring report',
            same_attempt,
        )
        self.assertEqual(third_party_name, 'third-party-runtime-200-3')
        self.assertEqual(live_edge_name, 'live-edge-monitor-200-3')
        self.assertTrue(third_party_name.startswith('third-party-runtime-'))
        self.assertTrue(live_edge_name.startswith('live-edge-monitor-'))
        self.assertNotEqual(third_party_name, live_edge_name)


if __name__ == '__main__':
    unittest.main()

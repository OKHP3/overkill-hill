import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';

// Exercise the actual workflow script against mocked GitHub and filesystem APIs.
const workflow = readFileSync(new URL('../.github/workflows/technology-watch.yml', import.meta.url), 'utf8').replace(/\r\n/g, '\n');
const source = workflow.split('          script: |\n')[1].split('\n').map(line => line.slice(12)).join('\n');
const runScript = new (Object.getPrototypeOf(async function () {}).constructor)(
  'require', 'github', 'context', 'core', source);
const marker = '<!-- technology-version-watch -->';

async function execute(report, existing = [], fileExists = true) {
  const calls = [];
  const github = {
    paginate: async () => existing,
    rest: {issues: {
      listForRepo() {},
      create: async args => calls.push({type: 'create', ...args}),
      update: async args => calls.push({type: 'update', ...args}),
    }},
  };
  await runScript(
    () => ({existsSync: () => fileExists, readFileSync: () => JSON.stringify(report)}),
    github, {repo: {owner: 'owner', repo: 'repo'}},
    {setFailed: message => calls.push({type: 'failed', message})});
  return calls;
}

const row = overrides => ({name: 'Node.js', current: '22.19.0', latest: '26.9.0',
  target: '24.21.0', target_status: 'UPDATE', owner: 'review', status: 'UPDATE', ...overrides});
const issue = body => ({number: 7, body, user: {login: 'github-actions[bot]'}});

test('creates one issue and leaves identical findings quiet', async () => {
  const report = {findings: [], technologies: [row({})]};
  const first = await execute(report);
  assert.equal(first.length, 1);
  assert.equal(first[0].type, 'create');
  assert.deepEqual(await execute(report, [issue(first[0].body)]), []);
});

test('does not treat a compliant LTS selector as needing Current migration', async () => {
  const calls = await execute({findings: [], technologies: [row({current: '24', target_status: 'TRACKING'})]},
    [issue(marker + '\nOld findings')]);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].state, 'closed');
});

test('Python trial coverage alerts on stale patches while primary CI still tracks migration', async () => {
  const trial = row({name: 'Python (compatibility trial)', role: 'compatibility trial',
    current: '3.14.8', latest: '3.15.0', target: '3.14.8', target_status: 'CURRENT'});
  const current = await execute({findings: [], technologies: [trial]}, [issue(marker)]);
  assert.equal(current[0].state, 'closed');
  const stale = await execute({findings: [], technologies: [{...trial,
    current: '3.14.7', target_status: 'UPDATE'}]});
  assert.match(stale[0].body, /Python \(compatibility trial\): 3\.14\.7; latest stable 3\.15\.0; policy target 3\.14\.8/);
  const primary = await execute({findings: [], technologies: [trial,
    row({name: 'Python', current: '3.11', latest: '3.15.0', target: undefined, target_status: undefined})]});
  assert.match(primary[0].body, /Python: 3\.11; latest stable 3\.15\.0\. Status: UPDATE/);
  assert.doesNotMatch(primary[0].body, /Python \(compatibility trial\)/);
});

test('failed registry lookups keep issues open even for Dependabot-owned entries', async () => {
  const calls = await execute({findings: [], technologies: [row({owner: 'dependabot',
    target_status: undefined, status: 'UNKNOWN', error: 'timeout'})]}, [issue(marker)]);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].type, 'update');
  assert.equal(calls[0].state, undefined);
  assert.match(calls[0].body, /Lookup failed/);
});

test('missing report cannot close an existing issue', async () => {
  const calls = await execute({}, [issue(marker)], false);
  assert.deepEqual(calls.map(c => c.type), ['failed']);
});

test('does not overwrite an unrelated user-created issue with the marker', async () => {
  const calls = await execute({findings: ['Node mismatch'], technologies: []},
    [{number: 9, body: marker, user: {login: 'someone'}}]);
  assert.equal(calls[0].type, 'create');
});

test('does not duplicate Dependabot or Mermaid update issues', async () => {
  const report = {findings: [], technologies: [row({owner: 'dependabot'}),
    row({owner: 'parent dependency'}), row({owner: 'Mermaid Version Watch'})]};
  assert.deepEqual(await execute(report), []);
});

test('an unrecorded authoring version remains actionable', async () => {
  const calls = await execute({findings: [], technologies: [row({name: 'FFmpeg',
    current: 'unrecorded', target_status: undefined, status: 'UNKNOWN'})]});
  assert.equal(calls[0].type, 'create');
  assert.match(calls[0].body, /FFmpeg: unrecorded/);
});

test('external historical tooling does not block website closeout or claim installed versions', async () => {
  const historical = row({name: 'FFmpeg', current: 'unrecorded', owner: 'OKHP3/murderbird-uncaged',
    scope: 'historical', status: 'HISTORICAL', target_status: undefined, error: 'retained lookup error'});
  const calls = await execute({findings: [], technologies: [historical]}, [issue(marker)]);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].state, 'closed');
  const mixed = await execute({findings: [], technologies: [historical,
    row({name: 'site dependency', status: 'UNKNOWN', target_status: undefined, error: 'offline'})]});
  assert.match(mixed[0].body, /Lookup failed for site dependency/);
  assert.doesNotMatch(mixed[0].body, /Lookup failed for FFmpeg/);
  assert.match(mixed[0].body, /Unknown historical installations are not certified/);
});

test('external ownership alone cannot suppress a current website dependency failure', async () => {
  const calls = await execute({findings: [], technologies: [row({owner: 'OKHP3/murderbird-uncaged',
    status: 'UNKNOWN', target_status: undefined, error: 'offline'})]});
  assert.match(calls[0].body, /Lookup failed/);
});

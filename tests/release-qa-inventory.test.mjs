import assert from 'node:assert/strict';
import { test } from 'node:test';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, copyFileSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { loadReleaseInventory, loadFunctionalPaths, root } from '../scripts/release-qa-inventory.mjs';

test('functional QA accounts for every release HTML page including indexing exclusions', () => {
  const inventory = loadReleaseInventory();
  const files = JSON.parse(execFileSync(process.platform === 'win32' ? 'py' : 'python3', ['-c',
    'import runpy,json;from pathlib import Path;m=runpy.run_path("scripts/build-release.py");print(json.dumps([p.as_posix() for p in m["load_public_pages"](Path.cwd())]))',
  ], { cwd: root, encoding: 'utf8' }));
  assert.deepEqual(inventory.map(entry => entry.file), files);
  assert.deepEqual(loadFunctionalPaths(), inventory.map(entry => entry.path));
  for (const path of ['/search/', '/404.html', '/under-construction.html', '/found-ry/', '/en-gb/', '/es-mx/']) {
    assert(inventory.some(entry => entry.path === path), `${path} must receive browser QA`);
  }
  assert(inventory.some(entry => entry.noindex));
  assert(!inventory.some(entry => entry.file.startsWith('assets/murderbird/')));
});

test('a newly shipped noindex page is discovered without a sitemap entry', async () => {
  const temporary = mkdtempSync(join(tmpdir(), 'release-qa-'));
  try {
    for (const dir of ['scripts', 'site-src', 'projects/new-draft', 'assets/templates']) {
      mkdirSync(join(temporary, dir), { recursive: true });
    }
    for (const file of ['build-release.py', 'public_page_boundary.py', 'release-qa-inventory.mjs']) {
      copyFileSync(join(root, 'scripts', file), join(temporary, 'scripts', file));
    }
    writeFileSync(join(temporary, 'site-src/pages.json'), JSON.stringify({ pages: [{ path: 'index.html' }] }));
    writeFileSync(join(temporary, 'sitemap.xml'), '<urlset><url><loc>https://overkillhill.com/</loc></url></urlset>');
    writeFileSync(join(temporary, 'index.html'), '<h1>Home</h1>');
    writeFileSync(join(temporary, 'projects/new-draft/index.html'), '<meta content="noindex" name="robots"><h1>Draft</h1>');
    writeFileSync(join(temporary, 'assets/templates/private.html'), '<h1>Unshipped template</h1>');
    const helper = await import(pathToFileURL(join(temporary, 'scripts/release-qa-inventory.mjs')));
    assert.deepEqual(helper.loadFunctionalPaths(), ['/', '/projects/new-draft/']);
    assert.equal(helper.loadReleaseInventory().find(entry => entry.path === '/projects/new-draft/').noindex, true);
  } finally { rmSync(temporary, { recursive: true, force: true }); }
});

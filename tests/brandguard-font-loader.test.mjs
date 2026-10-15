import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';

const source = await readFile(new URL('../assets/js/brandguard-fonts.js', import.meta.url), 'utf8');
function run({ ask = true, notice = true, painted = false, timing = true, api = true, theme = true } = {}) {
  const registered = [];
  vm.runInNewContext(source, {
    document: { body: { matches: selector => selector === '.askjamie-main' ? ask : false },
      querySelector: () => notice, fonts: { add: face => registered.push(face) } },
    FontFace: api ? class { constructor(family, url, descriptors) { Object.assign(this, { family, url, descriptors }); } } : undefined,
    getComputedStyle: () => ({ getPropertyValue: () => theme ? '"BrandGuard Open Sans", system-ui' : '' }),
    PerformanceObserver: { supportedEntryTypes: timing ? ['paint'] : [] },
    performance: { getEntriesByType: () => painted ? [{ name: 'first-contentful-paint' }] : [] },
  });
  return registered;
}
test('before-paint registration keeps the existing families local and optional', () => {
  const registered = run();
  assert.ok(registered.length > 0);
  for (const face of registered) {
    assert.ok(face.family.startsWith('BrandGuard '));
    assert.ok(face.url.startsWith('url(/assets/fonts/brandguard-'));
    assert.equal(face.descriptors.display, 'optional');
  }
});
test('late initialization cannot replace text the reader already saw', () => assert.equal(run({ painted: true }).length, 0));
test('unavailable paint timing keeps fallback rather than guessing', () => assert.equal(run({ timing: false }).length, 0));
test('ordinary AskJamie pages do not register the catalog', () => assert.equal(run({ notice: false }).length, 0));
test('a notice in another brand cannot register the catalog', () => assert.equal(run({ ask: false }).length, 0));
test('missing font APIs retain readable fallback', () => assert.equal(run({ api: false }).length, 0));
test('a deferred full theme cannot activate fonts over its painted critical shell', () => assert.equal(run({ theme: false }).length, 0));

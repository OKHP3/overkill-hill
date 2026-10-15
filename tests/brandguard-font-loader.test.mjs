import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';

const source = await readFile(new URL('../assets/js/brandguard-fonts.js', import.meta.url), 'utf8');
async function run({ ask = true, notice = true, painted = false, timing = true, api = true, theme = true, delayed = false, failed = false } = {}) {
  const registered = [];
  const decoders = [];
  let paintFrame = () => {};
  vm.runInNewContext(source, {
    document: { body: { innerText: 'Font loader witness', classList: { add: name => { registered.readyClass = name; } }, matches: selector => selector === '.askjamie-main' ? ask : false },
      querySelector: () => notice, fonts: { add: face => registered.push(face) } },
    FontFace: api ? class {
      constructor(family, url, descriptors) { Object.assign(this, { family, url, descriptors }); }
      load() {
        if (failed) return Promise.reject(new Error('font unavailable'));
        return delayed ? new Promise(resolve => decoders.push(() => resolve(this))) : Promise.resolve(this);
      }
    } : undefined,
    getComputedStyle: () => ({ getPropertyValue: () => theme ? '1' : '' }),
    PerformanceObserver: { supportedEntryTypes: timing ? ['paint'] : [] },
    performance: { getEntriesByType: () => painted ? [{ name: 'first-contentful-paint' }] : [] },
    requestAnimationFrame: callback => { paintFrame = callback; },
  });
  if (delayed) { paintFrame(); for (const decode of decoders) decode(); }
  await new Promise(resolve => setImmediate(resolve));
  return registered;
}
test('before-paint registration keeps the existing families local and optional', async () => {
  const registered = await run();
  assert.ok(registered.length > 0);
  assert.equal(registered.readyClass, 'brandguard-fonts-ready');
  for (const face of registered) {
    assert.ok(face.family.startsWith('BrandGuard '));
    assert.ok(face.url.startsWith('url(/assets/fonts/brandguard-'));
    assert.equal(face.descriptors.display, 'optional');
    assert.ok(face.url.includes('-latin.woff2'), 'ASCII text must not download unrelated Unicode subsets');
  }
});
test('late initialization cannot replace text the reader already saw', async () => assert.equal((await run({ painted: true })).length, 0));
test('unavailable paint timing keeps fallback rather than guessing', async () => assert.equal((await run({ timing: false })).length, 0));
test('ordinary AskJamie pages do not register the catalog', async () => assert.equal((await run({ notice: false })).length, 0));
test('a notice in another brand cannot register the catalog', async () => assert.equal((await run({ ask: false })).length, 0));
test('missing font APIs retain readable fallback', async () => assert.equal((await run({ api: false })).length, 0));
test('a deferred full theme cannot activate fonts over its painted critical shell', async () => assert.equal((await run({ theme: false })).length, 0));
test('fonts decoded after the next frame never enter the active font set', async () => {
  const result = await run({ delayed: true }); assert.equal(result.length, 0); assert.equal(result.readyClass, undefined);
});
test('failed font decoding leaves the active font set unchanged', async () => {
  const result = await run({ failed: true }); assert.equal(result.length, 0); assert.equal(result.readyClass, undefined);
});

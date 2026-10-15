import assert from 'node:assert/strict';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { chromium, webkit } from 'playwright';

// Real immutable sibling markup, with candidate foundation bytes projected in
// memory. This does not adopt a foundation baseline or modify a sibling clone.
const root = path.resolve(import.meta.dirname, '..');
const fixtures = path.join(import.meta.dirname, 'fixtures/brandguard-fonts');
const manifest = JSON.parse(await readFile(path.join(fixtures, 'manifest.json')));
const source = process.env.BRANDGUARD_SOURCE_REPO || path.join(root, '.ci/theme-sites/askjamie');
const revision = manifest.source_revision;
assert.equal(execFileSync('git', ['-C', source, 'rev-parse', `${revision}^{commit}`], { encoding: 'utf8' }).trim(), revision);
const cache = new Map();
function native(file) {
  if (!cache.has(file)) cache.set(file, execFileSync('git', ['-C', source, 'show', `${revision}:${file}`], { maxBuffer: 32 * 1024 * 1024 }));
  return cache.get(file);
}
const fonts = new Map();
for (const [url, entry] of Object.entries(manifest.files)) {
  const body = await readFile(path.join(fixtures, entry.file));
  assert.equal(createHash('sha256').update(body).digest('hex'), entry.sha256, `font fixture integrity: ${entry.file}`);
  fonts.set(url, { body, contentType: entry.type });
}
const css = await readFile(process.env.BRANDGUARD_TEST_CSS || path.join(root, 'assets/css/theme.css'));
const readyFaces = [...css.toString().matchAll(/@font-face\s*\{([^}]+)\}/g)].flatMap(([, block]) => {
  const family = block.match(/font-family:\s*'([^']+)'/), url = block.match(/url\((https[^)]+)\)/);
  if (!family?.[1].startsWith('BrandGuard ') || !url) return [];
  assert.ok(fonts.has(url[1]), `candidate font source has no integrity-checked fixture: ${url[1]}`);
  return [{ family: family[1], bytes: fonts.get(url[1]).body.toString('base64'),
    weight: block.match(/font-weight:\s*([^;]+)/)[1], unicodeRange: block.match(/unicode-range:\s*([^;]+)/)?.[1] }];
});
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.woff2': 'font/woff2', '.png': 'image/png', '.webp': 'image/webp', '.svg': 'image/svg+xml', '.json': 'application/json' };
const brands = process.env.BRANDGUARD_TEST_BRANDS?.split(',') || ['index', 'bfs-framing-intelligent-futures', 'lvmh', 'brooks-running', 'coca-cola', 'costco', 'discount-tire', 'dollar-general', 'hershey', 'lego', 'mathews-archery', 'ping', 'scheels', 'starbucks'];
const widths = (process.env.BRANDGUARD_TEST_WIDTHS || '320,360,390,401,900').split(',').map(Number);
const results = [], failures = [];
async function geometry(page) {
  return page.evaluate(() => {
    const selectors = ['.site-header', '.capability-transition', '.askjamie-breadcrumb', '.askjamie-hero-copy h1', '.hero-subtitle', '.hero-tagline', '.manifesto-blockquote'];
    return Object.fromEntries(selectors.map(s => [s, [...document.querySelectorAll(s)].map(el => {
      const r = el.getBoundingClientRect();
      return { top: r.top + scrollY, height: r.height, width: r.width };
    })]));
  });
}
for (const [engine, type] of [['chromium', chromium], ['webkit', webkit]]) {
  const browser = await type.launch();
  try {
    for (const brand of brands) for (const width of widths) for (const size of [16, 32]) {
      // Delay every font together, then release in reverse order. Fast and
      // failed fonts get separate witnesses below without multiplying CI cost.
      const modes = width === 390 ? ['late', 'fast', 'ready', 'failed'] : ['late'];
      for (const mode of modes) {
        const label = `${engine}/${brand}/${width}/${size}/${mode}`;
        const context = await browser.newContext({ viewport: { width, height: 480 }, reducedMotion: 'reduce' });
        const page = await context.newPage();
        const errors = [], missing = [], requests = [], pending = [];
        let released = mode === 'fast' || mode === 'ready';
        page.on('pageerror', e => errors.push(e.message));
        await page.route('**/*', async route => {
          const u = new URL(route.request().url());
          if (u.hostname === 'fonts.googleapis.com' && u.searchParams.get('display') === 'fallback') {
            const swap = u.href.replace('display=fallback', 'display=swap');
            assert.ok(fonts.has(swap), `unrecorded native font stylesheet: ${u.href}`);
            const entry = fonts.get(swap);
            return route.fulfill({ contentType: entry.contentType, body: entry.body.toString().replaceAll('font-display: swap', 'font-display: fallback') });
          }
          if (fonts.has(u.href)) {
            if (u.hostname === 'fonts.gstatic.com') {
              requests.push(u.href);
              if (mode === 'failed') return route.abort();
              if (!released) await new Promise(resolve => pending.push(resolve));
            }
            return route.fulfill({ ...fonts.get(u.href), headers: { 'access-control-allow-origin': '*' } });
          }
          if (u.origin !== 'https://brandguard.test') return route.abort();
          let file = decodeURIComponent(u.pathname).slice(1);
          if (!file || file.endsWith('/')) file += 'index.html';
          try {
            const body = file === 'assets/css/theme.css' ? css
              : ['assets/js/app.js', 'assets/js/mermaid-init.js'].includes(file) || file.startsWith('assets/fonts/')
                ? await readFile(path.join(root, file)) : native(file);
            return route.fulfill({ contentType: mime[path.extname(file)] || 'application/octet-stream', body });
          } catch { missing.push(file); return route.fulfill({ status: 404, body: 'Missing test asset' }); }
        });
        try {
          const url = '/lens-system/okhp3-brandguard/' + (brand === 'index' ? '' : `${brand}/`);
          await page.goto(`https://brandguard.test${url}`, { waitUntil: 'domcontentloaded' });
          await page.locator('.askjamie-hero-copy h1').waitFor();
          // Let the native critical-shell phase activate the full stylesheet.
          // This gate measures font arrival after that separate style phase.
          await page.waitForFunction(() => [...document.querySelectorAll('link[data-deferred-styles]')].every(link => link.media === 'all'));
          // Root enlargement tests rem reflow, not browser zoom. Apply before
          // measuring either phase so enlargement itself is not called a shift.
          await page.evaluate(n => { document.documentElement.style.fontSize = `${n}px`; }, size);
          if (mode === 'ready') {
            assert.ok(readyFaces.length, 'predecoded-font witness needs the candidate aliases');
            // An immediate response can still miss an optional font's first-paint
            // deadline. Add predecoded copies to exercise canonical glyphs too.
            await page.evaluate(async faces => {
              for (const spec of faces) {
                const bytes = Uint8Array.from(atob(spec.bytes), ch => ch.charCodeAt(0));
                const face = new FontFace(spec.family, bytes, { weight: spec.weight, ...(spec.unicodeRange ? { unicodeRange: spec.unicodeRange } : {}) });
                await face.load(); document.fonts.add(face);
              }
            }, readyFaces);
          }
          await page.waitForTimeout(250);
          const before = await geometry(page);
          released = true;
          for (const resolve of pending.reverse()) resolve();
          await page.evaluate(() => document.fonts.ready);
          await page.waitForTimeout(100);
          const after = await geometry(page);
          if (mode === 'late') for (const selector of Object.keys(before)) {
            assert.equal(after[selector].length, before[selector].length, `${label} selector count`);
            before[selector].forEach((box, i) => {
              for (const axis of ['top', 'height']) assert.ok(Math.abs(box[axis] - after[selector][i][axis]) <= 1, `${label} ${selector}[${i}] ${axis}: ${box[axis]} -> ${after[selector][i][axis]}`);
            });
          }
          const state = await page.evaluate(() => {
            const header = document.querySelector('.site-header');
            const targets = [...document.querySelectorAll('.capability-transition, .askjamie-hero-copy, .manifesto-blockquote')];
            const clipped = targets.filter(el => el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1).map(el => el.className);
            const outsideText = [];
            for (const target of [header, ...targets]) {
              const walker = document.createTreeWalker(target, NodeFilter.SHOW_TEXT);
              while (walker.nextNode()) {
                const text = walker.currentNode;
                if (!text.textContent.trim()) continue;
                // Screen-reader-only labels intentionally use a clipped 1px box.
                if (text.parentElement.closest('.sr-only, [hidden]')) continue;
                const range = document.createRange(); range.selectNodeContents(text);
                for (const r of range.getClientRects()) if (r.width && (r.left < -1 || r.right > innerWidth + 1)) outsideText.push(text.textContent.trim().slice(0, 80));
              }
            }
            return { overflow: document.documentElement.scrollWidth - innerWidth, position: getComputedStyle(header).position, clipped,
              outsideText: [...new Set(outsideText)].slice(0, 10),
              fontSize: getComputedStyle(document.querySelector('.hero-subtitle')).fontSize,
              loadedFaces: [...document.fonts].filter(f => f.family.includes('BrandGuard') && f.status === 'loaded').length };
          });
          assert.ok(state.overflow <= 1, `${label} horizontal overflow: ${state.overflow}`);
          assert.deepEqual(state.clipped, [], `${label} clipped text containers`);
          assert.deepEqual(state.outsideText, [], `${label} text outside the viewport`);
          assert.notEqual(state.position, 'sticky', `${label} enlarged header must scroll away`);
          if (mode === 'fast') assert.ok(state.loadedFaces > 0, `${label} canonical optional faces really load`);
          assert.deepEqual(missing, [], `${label} missing local assets`);
          assert.deepEqual(errors, [], `${label} page errors`);
          let renderedHeadingFonts;
          if (engine === 'chromium' && ['fast', 'ready'].includes(mode)) {
            const session = await context.newCDPSession(page);
            await session.send('DOM.enable'); await session.send('CSS.enable');
            const { root: doc } = await session.send('DOM.getDocument');
            const { nodeId } = await session.send('DOM.querySelector', { nodeId: doc.nodeId, selector: '.askjamie-hero-copy h1' });
            renderedHeadingFonts = (await session.send('CSS.getPlatformFontsForNode', { nodeId })).fonts;
            await session.detach();
            if (mode === 'ready') assert.ok(renderedHeadingFonts.some(f => f.isCustomFont && f.glyphCount > 0), `${label} must paint canonical heading glyphs`);
          }
          if (process.env.BRANDGUARD_SCREENSHOTS && ['dollar-general', 'lego'].includes(brand) && width === 390 && size === 32 && mode !== 'failed') {
            await mkdir(process.env.BRANDGUARD_SCREENSHOTS, { recursive: true });
            await page.locator('.askjamie-hero-copy h1').scrollIntoViewIfNeeded();
            await page.screenshot({ path: path.join(process.env.BRANDGUARD_SCREENSHOTS, `${engine}-${brand}-${mode}.png`) });
          }
          results.push({ label, requests: requests.length, ...state, renderedHeadingFonts });
        } catch (e) { failures.push({ label, error: e.message }); }
        finally { released = true; for (const resolve of pending) resolve(); await context.close(); }
      }
    }
  } finally { await browser.close(); }
}
const report = { source: manifest.source_repository, revision, cssSha256: createHash('sha256').update(css).digest('hex'), results, failures };
if (process.env.BRANDGUARD_TEST_REPORT) await writeFile(process.env.BRANDGUARD_TEST_REPORT, JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify({ passed: results.length, failures }, null, 2));
assert.equal(failures.length, 0, 'BrandGuard font and enlarged-text regressions');

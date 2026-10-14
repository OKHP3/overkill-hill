import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { chromium } from 'playwright';

const themeCss = readFileSync(new URL('../assets/css/theme.css', import.meta.url), 'utf8');

// AskJamie universe shell/attributes at 6ed61ed9fef964da09e0c26bc80cc61150a8c6b6.
// The shared stylesheet is exercised without changing the sibling's own runtime.
function askDiagramFixture(content) {
  return `<html data-theme="light"><head><style>${themeCss}</style></head>
    <body class="askjamie-main"><main>${content}</main></body></html>`;
}

test('interactive Mermaid SVG links remain in the keyboard order with group semantics', async () => {
  const source = readFileSync(new URL('../assets/js/mermaid-init.js', import.meta.url), 'utf8');
  const enhance = source.slice(source.indexOf('function enhanceMermaidLinks('), source.indexOf('\nfunction renderOne('));
  const browser = await chromium.launch();
  const page = await browser.newPage();
  try {
    await page.setContent('<button id="start">Before</button><div id="diagram" role="img"><svg role="img"><a href="#target" target="_blank"><text>Project</text></a><a><text>Decoration</text></a></svg></div><button id="target">After</button>');
    await page.evaluate('(() => {' + enhance + '\nenhanceMermaidLinks(document.getElementById("diagram"));})()');
    await page.locator('#start').focus();
    await page.keyboard.press('Tab');
    assert.equal(await page.evaluate(() => document.activeElement.getAttribute('href')), '#target');
    assert.equal(await page.locator('#diagram').getAttribute('role'), 'group');
    assert.equal(await page.locator('svg').getAttribute('role'), 'group');
    assert.equal(await page.locator('svg a[href]').getAttribute('rel'), 'noopener noreferrer');
    await page.keyboard.press('Tab');
    assert.equal(await page.evaluate(() => document.activeElement.id), 'target');
  } finally { await browser.close(); }
});

for (const failure of ['load', 'render']) {
  test(`a Mermaid ${failure} failure preserves the AskJamie navigation fallback`, async () => {
    const source = readFileSync(new URL('../assets/js/mermaid-init.js', import.meta.url), 'utf8');
    const render = source.slice(source.indexOf('function addAccessibleAlternative('), source.indexOf('\nfunction scheduleRender('));
    const browser = await chromium.launch();
    const page = await browser.newPage();
    try {
      await page.setContent(askDiagramFixture('<section class="askjamie-mermaid-shell"><div class="mermaid-scroll-wrap" aria-hidden="true"><pre class="mermaid">graph TD; A["Projects"]</pre></div><p class="mermaid-render-status" role="status" aria-live="polite" data-mermaid-failure-status hidden></p><a href="/projects/">Browse projects</a></section>'));
      await page.evaluate(({ render, failure }) => {
        window.failureWarnings = [];
        console.warn = (...values) => window.failureWarnings.push(String(values[0]));
        const preamble = `const node = document.querySelector('.mermaid');
          const diagrams = [node];
          const usesClickableLinks = false;
          const resolveThemeColors = source => source;
          const loadMermaid = () => ${failure === 'load'
            ? 'Promise.reject(new Error("module unavailable"))'
            : 'Promise.resolve({run: () => Promise.reject(new Error("invalid diagram"))})'};`;
        eval(preamble + render + '\nrenderOne(node);');
      }, { render, failure });
      await page.locator('[data-mermaid-failure-status]').waitFor({ state: 'visible' });
      assert.match(await page.locator('[data-mermaid-failure-status]').textContent(), /Use the links below/);
      assert.equal(await page.locator('a').getAttribute('href'), '/projects/');
      assert.equal(await page.locator('.mermaid').getAttribute('aria-label'), 'Diagram 1: Projects');
      assert.deepEqual(await page.locator('[data-mermaid-failure-status]').evaluate(node => ({
        border: getComputedStyle(node).borderTopWidth,
        weight: getComputedStyle(node).fontWeight,
        inHiddenDiagram: Boolean(node.closest('[aria-hidden="true"]')),
        live: node.getAttribute('aria-live'),
      })), { border: '1px', weight: '600', inHiddenDiagram: false, live: 'polite' });
      await page.locator('a').focus();
      assert.equal(await page.locator('a').evaluate(node => document.activeElement === node), true);
      assert.deepEqual(await page.evaluate(() => window.failureWarnings), ['[mermaid-init] render error:']);
    } finally { await browser.close(); }
  });
}

test('a successful Mermaid render becomes visible through the AskJamie readiness observer', async () => {
  const source = readFileSync(new URL('../assets/js/mermaid-init.js', import.meta.url), 'utf8');
  const render = source.slice(source.indexOf('function addAccessibleAlternative('), source.indexOf('\nfunction scheduleRender('));
  const observer = readFileSync(new URL('./fixtures/askjamie-universe-ready.js', import.meta.url), 'utf8');
  const browser = await chromium.launch();
  const page = await browser.newPage();
  try {
    await page.setContent(askDiagramFixture('<section class="askjamie-mermaid-shell"><div class="mermaid-scroll-wrap" aria-hidden="true"><pre class="mermaid">graph TD; A["Projects"]</pre></div><p class="mermaid-render-status" role="status" aria-live="polite" data-mermaid-failure-status hidden></p><a href="/projects/">Browse projects</a></section>'));
    assert.equal(await page.locator('.mermaid').isVisible(), false);
    await page.evaluate(observer => eval('(() => {' + observer + '\n})()'), observer);
    await page.evaluate(render => {
      eval(`const node = document.querySelector('.mermaid');
        const diagrams = [node]; const usesClickableLinks = false;
        const resolveThemeColors = source => source;
        const loadMermaid = () => Promise.resolve({run: async ({nodes}) => {
          nodes[0].dataset.processed = 'true';
          nodes[0].innerHTML = '<svg><g class="node"><text>Projects</text></g></svg>';
        }});
        ${render}\nrenderOne(node);`);
    }, render);
    await page.waitForFunction(() => document.querySelector('.mermaid').dataset.universeReady === '1');
    assert.equal(await page.locator('.mermaid').isVisible(), true);
    assert.equal(await page.locator('[data-mermaid-failure-status]').isVisible(), false);
    assert.equal(await page.locator('[data-mermaid-failure-status]').evaluate(node => node.getClientRects().length), 0);
    assert.equal(await page.locator('a').getAttribute('href'), '/projects/');
    assert.equal(await page.locator('.mermaid').getAttribute('aria-label'), 'Diagram 1: Projects');
  } finally { await browser.close(); }
});

for (const width of [320, 640, 641, 1280]) {
  test(`AskJamie diagram shells reserve space without exposing hidden status (${width}px)`, async () => {
    const browser = await chromium.launch();
    const page = await browser.newPage({ viewport: { width, height: 800 } });
    try {
      await page.setContent(askDiagramFixture('<section class="askjamie-hero--universe"><div class="askjamie-mermaid-shell"><div class="mermaid-scroll-wrap" aria-hidden="true"><pre class="mermaid">graph TD; A["Projects"]</pre></div><p class="mermaid-render-status" role="status" aria-live="polite" hidden></p></div></section>'));
      const state = await page.evaluate(() => ({
        minimum: getComputedStyle(document.querySelector('.mermaid-scroll-wrap')).minHeight,
        sourceVisible: getComputedStyle(document.querySelector('.mermaid')).visibility,
        hiddenHeight: document.querySelector('.mermaid-render-status').getBoundingClientRect().height,
        pageWidth: document.documentElement.scrollWidth,
      }));
      assert.equal(state.minimum, width <= 640 ? '288px' : '352px');
      assert.equal(state.sourceVisible, 'hidden');
      assert.equal(state.hiddenHeight, 0);
      assert.ok(state.pageWidth <= width, `document overflow: ${state.pageWidth} > ${width}`);
    } finally { await browser.close(); }
  });
}

for (const scheme of ['light', 'dark']) {
  test(`wide AskJamie maps scroll inside the page and failure text wraps (${scheme})`, async () => {
    const browser = await chromium.launch();
    const page = await browser.newPage({ viewport: { width: 320, height: 800 } });
    try {
      await page.setContent(askDiagramFixture('<section class="container universe-map-generated"><details class="universe-map-group" open><summary>Projects</summary><figure class="askjamie-mermaid-shell"><div class="mermaid-scroll-wrap" aria-hidden="true" tabindex="-1"><pre class="mermaid" data-processed="true" data-universe-ready="1"><svg style="min-width:40rem" width="640" height="220"><g class="node"><text>Projects</text></g></svg></pre></div><p class="mermaid-render-status" role="status" aria-live="polite" hidden>Diagram unavailable. Use the links below to explore the projects and their source records.</p><a href="/projects/">Browse projects</a></figure></details></section>'));
      await page.locator('html').evaluate((node, scheme) => node.dataset.colorScheme = scheme, scheme);
      const scrolling = await page.locator('.mermaid-scroll-wrap').evaluate(node => {
        node.scrollLeft = 120;
        return { overflow: getComputedStyle(node).overflowX, moved: node.scrollLeft,
          width: node.clientWidth, content: node.scrollWidth, page: document.documentElement.scrollWidth };
      });
      assert.equal(scrolling.overflow, 'auto');
      assert.ok(scrolling.content > scrolling.width);
      assert.ok(scrolling.moved > 0);
      assert.ok(scrolling.page <= 320);
      const hiddenHeight = await page.locator('figure').evaluate(node => node.getBoundingClientRect().height);
      await page.locator('.mermaid-render-status').evaluate(node => node.remove());
      assert.equal(await page.locator('figure').evaluate(node => node.getBoundingClientRect().height), hiddenHeight);
      await page.locator('figure').evaluate(node => {
        const status = document.createElement('p');
        status.className = 'mermaid-render-status';
        status.textContent = 'Diagram unavailable. Use the links below to explore the projects and their source records.';
        node.append(status);
      });
      const visible = await page.locator('.mermaid-render-status').evaluate(node => ({
        width: node.getBoundingClientRect().width, height: node.getBoundingClientRect().height,
        contentWidth: node.scrollWidth, page: document.documentElement.scrollWidth,
      }));
      assert.ok(visible.height > 0);
      assert.ok(visible.contentWidth <= visible.width);
      assert.ok(visible.page <= 320);
    } finally { await browser.close(); }
  });
}

for (const bodyClass of ['', 'glee-main']) {
  test(`AskJamie failure styles stay outside ${bodyClass || 'unbranded OKH'} pages`, async () => {
    const browser = await chromium.launch();
    const page = await browser.newPage();
    try {
      await page.setContent(`<html><head><style>${themeCss}</style></head><body class="${bodyClass}"><p class="mermaid-render-status">Existing message</p></body></html>`);
      assert.equal(await page.locator('p').evaluate(node => getComputedStyle(node).borderTopWidth), '0px');
    } finally { await browser.close(); }
  });
}

test('a failed Mermaid node without an AskJamie shell keeps its existing error behavior', async () => {
  const source = readFileSync(new URL('../assets/js/mermaid-init.js', import.meta.url), 'utf8');
  const render = source.slice(source.indexOf('function addAccessibleAlternative('), source.indexOf('\nfunction scheduleRender('));
  const browser = await chromium.launch();
  const page = await browser.newPage();
  try {
    await page.setContent('<pre class="mermaid">graph TD; A["Projects"]</pre><a href="/projects/">Browse projects</a>');
    await page.evaluate(render => {
      window.failureWarnings = [];
      console.warn = (...values) => window.failureWarnings.push(String(values[0]));
      eval(`const node = document.querySelector('.mermaid');
        const diagrams = [node]; const usesClickableLinks = false;
        const resolveThemeColors = source => source;
        const loadMermaid = () => Promise.reject(new Error('module unavailable'));
        ${render}\nrenderOne(node);`);
    }, render);
    await page.waitForFunction(() => window.failureWarnings.length === 1);
    assert.deepEqual(await page.evaluate(() => window.failureWarnings), ['[mermaid-init] render error:']);
    assert.equal(await page.locator('[data-mermaid-failure-status]').count(), 0);
    assert.equal(await page.locator('a').getAttribute('href'), '/projects/');
  } finally { await browser.close(); }
});

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { chromium } from 'playwright';

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
      await page.setContent('<section class="askjamie-mermaid-shell"><pre class="mermaid">graph TD; A["Projects"]</pre><p role="status" data-mermaid-failure-status hidden></p><a href="/projects/">Browse projects</a></section>');
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
      assert.deepEqual(await page.evaluate(() => window.failureWarnings), ['[mermaid-init] render error:']);
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

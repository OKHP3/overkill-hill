import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { chromium } from 'playwright';

const css = await readFile(new URL('../assets/css/theme.css', import.meta.url), 'utf8');
const browser = await chromium.launch({ headless: true });
let cases = 0;
try {
  for (const brand of ['askjamie-main', '', 'glee-main']) {
    for (const width of [320, 375, 400, 900]) for (const size of [16, 32]) {
      for (const mode of [
        { preference: 'light', os: 'dark', dark: false },
        { preference: 'dark', os: 'light', dark: true },
        { preference: 'auto', os: 'light', dark: false },
        { preference: 'auto', os: 'dark', dark: true },
      ]) {
        const context = await browser.newContext({ viewport: { width, height: 720 }, colorScheme: mode.os, reducedMotion: 'reduce' });
        const page = await context.newPage();
        const attrs = brand
          ? `data-theme="light"${mode.preference === 'auto' ? '' : ` data-color-scheme="${mode.preference}"`}`
          : `data-theme="${mode.dark ? 'dark' : 'light'}"`;
        await page.route('**/*', r => r.request().url().endsWith('/theme.css')
          ? r.fulfill({ contentType: 'text/css', body: css })
          : r.fulfill({ contentType: 'text/html', body: `<!doctype html><html ${attrs}><head><meta charset="utf-8">
            <link rel="stylesheet" href="/theme.css"></head><body class="${brand}">
            <header class="site-header"><div class="container"><nav class="primary-nav"><ul><li><a href="#case">Case study</a></li></ul></nav></div></header>
            <main><div class="askjamie-hero-inner"><div class="two-column"><p>ReferenceWithoutNaturalBreaksForTestingShrinkConstraints</p><p>Second column</p></div></div>
            <div class="hero-actions"><a class="btn" href="#case">Read the case study and its supporting evidence</a></div>
            <ul class="grid"><li><a id="case" class="card brandguard-case-card" href="/case/"><h2>Public case study</h2><p>Inspect the documented evidence.</p></a></li></ul></main>
            <footer class="site-footer"><div class="footer-grid"><div><h3>Navigation</h3><p>Public background.</p><a href="#case">Read the case</a></div><div><h4>Contact</h4><p>ContactWithoutNaturalBreaksForTestingShrinkConstraints</p></div></div></footer></body></html>` }));
        try {
          await page.goto('https://ask-reflow.test/');
          // A larger root font is a rem-enlargement stress test, not browser zoom.
          await page.evaluate(n => document.documentElement.style.fontSize = `${n}px`, size);
          const card = page.locator('.brandguard-case-card');
          await card.focus();
          const state = await page.evaluate(() => {
            const style = selector => getComputedStyle(document.querySelector(selector));
            const card = document.querySelector('.brandguard-case-card');
            return { mainWrap: style('main').overflowWrap, navWrap: style('.primary-nav > ul').flexWrap,
              childMinWidth: style('.two-column > p').minWidth, footerMinWidth: style('.footer-grid > div').minWidth,
              heroMinWidth: style('.askjamie-hero-inner').minWidth, buttonWrap: style('.hero-actions .btn').whiteSpace,
              outline: style('.brandguard-case-card').outlineWidth, decoration: style('.brandguard-case-card').textDecorationLine,
              footerText: style('.site-footer p').color, footerLink: style('.site-footer a').color,
              name: card.textContent.trim(), href: card.getAttribute('href'), nestedControls: card.querySelectorAll('a,button,input').length };
          });
          assert.ok(state.name.includes('Public case study'));
          assert.equal(state.href, '/case/');
          assert.equal(state.nestedControls, 0);
          if (brand === 'askjamie-main') {
            assert.equal(state.mainWrap, 'anywhere');
            assert.equal(state.navWrap, 'wrap');
            for (const key of ['childMinWidth', 'footerMinWidth', 'heroMinWidth']) assert.equal(state[key], '0px');
            assert.equal(state.buttonWrap, 'normal');
            assert.equal(state.outline, '3px');
            assert.equal(state.decoration, 'underline', 'The existing keyboard-focus underline remains');
            assert.equal(state.footerText, mode.dark ? 'rgb(156, 163, 175)' : 'rgb(90, 90, 90)');
            assert.equal(state.footerLink, mode.dark ? 'rgb(118, 178, 186)' : 'rgb(31, 90, 103)');
          } else {
            assert.notEqual(state.outline, '3px', 'Ask card focus styling must not leak into another brand');
          }
          await card.press('Enter');
          await page.waitForURL('https://ask-reflow.test/case/');
          cases++;
        } finally { await context.close(); }
      }
    }
  }
} finally { await browser.close(); }
console.log(`PASS ${cases} Ask reflow CSS, theme and native-link cases`);

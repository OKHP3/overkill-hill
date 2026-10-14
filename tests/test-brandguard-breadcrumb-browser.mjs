import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {chromium} from 'playwright';

const css=await readFile(new URL('../assets/css/theme.css',import.meta.url),'utf8');
const browser=await chromium.launch({headless:true});
async function state(page){return page.evaluate(()=>{
  const label=document.querySelector('.breadcrumb-label'),separator=document.querySelector('.breadcrumb-separator'),link=document.querySelector('.askjamie-logo--crumb'),img=link.querySelector('img');
  const l=getComputedStyle(label),s=getComputedStyle(separator),a=getComputedStyle(link),i=getComputedStyle(img),range=document.createRange();range.selectNodeContents(label);
  const box=label.getBoundingClientRect();
  return {logo:i.maxWidth,margin:a.marginBottom,label:{text:label.textContent,whiteSpace:l.whiteSpace,minWidth:l.minWidth,flex:l.flex,overflowWrap:l.overflowWrap,display:l.display,painted:range.getClientRects().length>0&&box.width>0},separator:s.display,
    labelRanges:[...range.getClientRects()].map(r=>({left:r.left,right:r.right})),labelBox:{left:box.left,right:box.right},linkArea:link.getBoundingClientRect().width*link.getBoundingClientRect().height};
});}
try{
  for(const width of [320,340,341,899,900]) for(const kind of ['hub','case','ordinary','non-ask']){
    const ctx=await browser.newContext({viewport:{width,height:800},reducedMotion:'reduce'}),page=await ctx.newPage();
    const classes=kind==='non-ask'?'':kind==='hub'?'askjamie-main askjamie-brandguard-page':'askjamie-main';
    await page.route('https://breadcrumb.test/**',r=>r.request().resourceType()==='font'?r.abort():r.fulfill({contentType:'text/html',body:`<!doctype html><html data-theme="light"><head><meta charset="utf-8"><link rel="stylesheet" href="/theme.css"></head><body class="${classes}"><main><div class="askjamie-hero-copy"><p class="eyebrow askjamie-breadcrumb"><a class="askjamie-logo askjamie-logo--crumb" href="/#top" aria-label="AskJamie home"><img width="160" height="160" alt="AskJamie logo"></a><span class="breadcrumb-separator">/</span><span class="breadcrumb-label">GPT-BFS01: BFS Framing Intelligent Futures</span></p></div>${kind==='case'||kind==='non-ask'?'<aside class="brandguard-demo-notice">Case context</aside>':''}</main></body></html>`}));
    // Register the exact stylesheet after the broad HTML route.
    await page.route('https://breadcrumb.test/theme.css',r=>r.fulfill({contentType:'text/css',body:css}));
    await page.goto('https://breadcrumb.test/');const x=await state(page);
    if(kind==='non-ask'){
      await page.evaluate(()=>document.body.classList.add('askjamie-brandguard-page'));
      assert.deepEqual(await state(page),x,'BrandGuard marker and notice cannot activate Ask rules without Ask body scope');
    }else{
      assert.ok(x.label.painted&&x.linkArea>0,'Complete label and home link remain painted');
      assert.equal(x.label.text,'GPT-BFS01: BFS Framing Intelligent Futures');
      if(kind==='hub'&&width<=899){assert.equal(x.logo,'120px');assert.equal(x.margin,'0px');assert.equal(x.label.minWidth,width<=340?'0px':'244px');}
      else {assert.equal(x.logo,'192px');assert.equal(x.margin,'16px');}
      if(kind!=='ordinary'&&width<=340){
        assert.equal(x.separator,'none');assert.equal(x.label.whiteSpace,'normal');assert.equal(x.label.flex,'1 1 100%');assert.equal(x.label.overflowWrap,'anywhere');
        assert.ok(x.labelRanges.every(r=>r.left>=x.labelBox.left-1&&r.right<=x.labelBox.right+1),'Wrapped glyph ranges stay inside the label');
      }else {assert.notEqual(x.separator,'none');assert.equal(x.label.whiteSpace,'nowrap');}
      await page.keyboard.press('Tab');const focus=await page.evaluate(()=>{const a=document.querySelector('.askjamie-logo--crumb'),s=getComputedStyle(a);return document.activeElement===a&&s.outlineStyle!=='none'&&parseFloat(s.outlineWidth)>0;});assert.ok(focus,'Exact breadcrumb home link receives visible keyboard focus');
      await page.keyboard.press('Enter');await page.waitForURL('**/#top');
    }
    console.log(`PASS: ${kind} ${width}px`);await ctx.close();
  }
}finally{await browser.close();}

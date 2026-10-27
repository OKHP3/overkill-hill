import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { chromium } from "playwright";
import { dismissTransitionAnnouncement } from "../scripts/screen-reader-tree-audit.mjs";

let browser;
before(async () => { browser = await chromium.launch({ headless: true }); });
after(async () => { await browser?.close(); });

async function openAnnouncement(markup) {
  const page = await browser.newPage();
  await page.setContent(`<main><h1>Page</h1></main>${markup}`);
  await page.locator("#capability-transition-dialog").evaluate(dialog => dialog.showModal());
  return page;
}

async function exposedMainCount(page) {
  const client = await page.context().newCDPSession(page);
  try {
    await client.send("Accessibility.enable");
    const { nodes } = await client.send("Accessibility.getFullAXTree");
    return nodes.filter(node => !node.ignored && node.role?.value === "main").length;
  } finally { await client.detach(); }
}

test("a named first-visit announcement closes before page landmarks are exposed", async () => {
  const page = await openAnnouncement('<dialog id="capability-transition-dialog" aria-label="Transition update"><button>Close</button></dialog>');
  try {
    assert.equal(await exposedMainCount(page), 0, "modal hides background landmark");
    const failures = [];
    assert.equal(await dismissTransitionAnnouncement(page, failures), true);
    assert.deepEqual(failures, []);
    assert.equal(await exposedMainCount(page), 1, "landmark is exposed after native close");
  } finally { await page.close(); }
});

test("an unnamed announcement fails even if another named dialog exists", async () => {
  const page = await openAnnouncement('<dialog id="capability-transition-dialog"><div role="dialog" aria-label="Other dialog">Nested dialog</div><button>Close</button></dialog>');
  try {
    assert.equal(await page.getByRole("dialog", { name: "Other dialog" }).count(), 1);
    const failures = [];
    assert.equal(await dismissTransitionAnnouncement(page, failures), true);
    assert.deepEqual(failures, ["transition announcement has no accessible dialog name"]);
    assert.equal(await page.locator("#capability-transition-dialog").evaluate(dialog => dialog.open), false);
  } finally { await page.close(); }
});

test("an announcement that rejects Escape fails rather than auditing a hidden page", async () => {
  const page = await openAnnouncement('<dialog id="capability-transition-dialog" aria-label="Transition update"><button>Close</button></dialog>');
  try {
    await page.locator("#capability-transition-dialog").evaluate(dialog => {
      dialog.addEventListener("cancel", event => event.preventDefault());
    });
    const failures = [];
    assert.equal(await dismissTransitionAnnouncement(page, failures), false);
    assert.deepEqual(failures, ["transition announcement did not close after Escape"]);
    assert.equal(await page.locator("#capability-transition-dialog").evaluate(dialog => dialog.open), true);
    assert.equal(await exposedMainCount(page), 0);
  } finally { await page.close(); }
});

test("an absent or already dismissed announcement does not block the audit", async () => {
  const page = await browser.newPage();
  try {
    await page.setContent('<main><h1>Page</h1></main><dialog id="capability-transition-dialog"></dialog>');
    const failures = [];
    assert.equal(await dismissTransitionAnnouncement(page, failures), true);
    assert.deepEqual(failures, []);
    assert.equal(await exposedMainCount(page), 1);
  } finally { await page.close(); }
});

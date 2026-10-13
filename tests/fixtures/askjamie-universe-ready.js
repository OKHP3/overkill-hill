// Compatibility fixture: OKHP3/askjamie d4c0dcbdf7087c96c041e15641630aa8426642b1
// assets/js/universe-map.js; preserve the real consumer readiness observer.
// Keep Mermaid strict. Add navigation only from the generated ordinary links.
const diagrams = document.querySelectorAll(".askjamie-mermaid-shell .mermaid");
function linkNodes(group) {
  for (const link of group.querySelectorAll("a[data-universe-node]")) {
    const id = link.dataset.universeNode;
    if (!/^n[0-9a-f]{16}$/.test(id)) continue;
    const url = new URL(link.getAttribute("href"), location.origin);
    if (url.origin !== location.origin || !url.pathname.startsWith("/") || url.search) continue;
    const node = group.querySelector(`svg .node[id*="flowchart-${id}-"]`);
    if (!node || node.parentElement.localName === "a") continue;
    const anchor = document.createElementNS("http://www.w3.org/2000/svg", "a");
    anchor.setAttribute("href", url.pathname + url.hash);
    anchor.setAttribute("tabindex", "-1");
    node.before(anchor);
    anchor.append(node);
  }
}
for (const diagram of diagrams) {
  const finish = () => {
    if (!diagram.querySelector("svg .node")) return false;
    const group = diagram.closest(".universe-map-group");
    if (group) linkNodes(group);
    diagram.dataset.universeReady = "1";
    return true;
  };
  if (finish()) continue;
  const observer = new MutationObserver(() => {
    if (finish()) observer.disconnect();
  });
  observer.observe(diagram, { childList: true, subtree: true });
}

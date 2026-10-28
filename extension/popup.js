const DEFAULTS = { enabled: true, minSizeKB: 0, skipTypes: "", videoButton: true };
const $ = id => document.getElementById(id);

chrome.storage.local.get(DEFAULTS, o => {
  $("enabled").checked = o.enabled;
  $("videoButton").checked = o.videoButton;
  $("minSizeKB").value = o.minSizeKB;
  $("skipTypes").value = o.skipTypes;
});
const save = () => chrome.storage.local.set({
  enabled: $("enabled").checked,
  videoButton: $("videoButton").checked,
  minSizeKB: parseInt($("minSizeKB").value || "0", 10),
  skipTypes: $("skipTypes").value
});
["enabled", "videoButton", "minSizeKB", "skipTypes"].forEach(id => $(id).addEventListener("change", save));

fetch("http://127.0.0.1:9614/ping")
  .then(r => r.json())
  .then(j => { $("status").textContent = `Connected to Sahm ${j.version}`; $("status").className = "status ok"; })
  .catch(() => { $("status").textContent = "Sahm app is not running"; $("status").className = "status bad"; });

chrome.runtime.sendMessage({ type: "sahm-get-blocked" }, list => {
  if (!list || !list.length) return;
  const box = $("blocked");
  const h = document.createElement("h2");
  h.textContent = "Blocked repeats after startup";
  const hint = document.createElement("small");
  hint.textContent = "Reopened tabs tried to download these again. ";
  const clear = document.createElement("a");
  clear.textContent = "Clear";
  clear.style.cssText = "color:#1a73e8;cursor:pointer";
  clear.onclick = () => chrome.runtime.sendMessage({ type: "sahm-clear-blocked" }, () => box.replaceChildren());
  hint.append(clear);
  box.replaceChildren(h, hint);
  list.forEach(b => {
    const row = document.createElement("div");
    row.className = "m";
    const span = document.createElement("span");
    span.title = b.url;
    span.textContent = b.name || b.url;
    const a = document.createElement("a");
    a.textContent = "Download anyway";
    a.onclick = () => chrome.runtime.sendMessage({ type: "sahm-unblock", url: b.url }, () => row.remove());
    row.append(span, a);
    box.appendChild(row);
  });
});

const fmtSize = n => !n ? "" : n > 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.round(n / 1024) + " KB";

chrome.tabs.query({ active: true, currentWindow: true }, ([tab]) => {
  if (!tab) return;
  const send = src => chrome.runtime.sendMessage(
    { type: "sahm-popup-video", tabId: tab.id, pageUrl: tab.url, title: tab.title, src },
    r => { $("status").textContent = r && r.ok ? "Sent to Sahm ✓" : "Sahm app is not running";
           $("status").className = "status " + (r && r.ok ? "ok" : "bad"); });
  $("grab").onclick = () => send("");

  chrome.runtime.sendMessage({ type: "sahm-get-media", tabId: tab.id }, list => {
    if (!list || !list.length) return;
    const box = $("media");
    const hint = document.createElement("small");
    hint.textContent = "Streams detected on this page:";
    box.replaceChildren(hint);
    list.slice().reverse().forEach(m => {
      let name; try { name = decodeURIComponent(new URL(m.url).pathname.split("/").pop() || m.url).slice(0, 60); } catch (e) { name = m.url.slice(0, 60); }
      const row = document.createElement("div");
      row.className = "m";
      const span = document.createElement("span");
      span.title = m.url;
      span.textContent = `${name} ${fmtSize(m.size)}`;
      const a = document.createElement("a");
      a.textContent = "Download";
      a.onclick = () => send(m.url);
      row.append(span, a);
      box.appendChild(row);
    });
  });
});

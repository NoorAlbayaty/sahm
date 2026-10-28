// Shows a floating "Download this video" button over videos, like IDM.
(() => {
  if (window.__sahmLoaded) return;
  window.__sahmLoaded = true;

  const btn = document.createElement("div");
  btn.id = "sahm-video-btn";
  const arrow = document.createElement("span"); arrow.className = "sahm-arrow"; arrow.textContent = "⬇";
  const label = document.createElement("span"); label.textContent = "Download this video";
  btn.append(arrow, label);
  btn.style.display = "none";
  let current = null, hideTimer = null, enabled = true;

  chrome.storage.local.get({ videoButton: true }, o => { enabled = o.videoButton; });
  chrome.storage.onChanged.addListener(c => { if (c.videoButton) enabled = c.videoButton.newValue; });

  const attach = () => { if (!btn.isConnected) (document.body || document.documentElement).appendChild(btn); };

  function place(v) {
    const r = v.getBoundingClientRect();
    if (r.width < 200 || r.height < 120) return false;
    btn.style.top = Math.max(4, r.top + 10) + "px";
    btn.style.left = Math.max(4, r.right - btn.offsetWidth - 10) + "px";
    return true;
  }

  function show(v) {
    if (!enabled) return;
    attach();
    current = v;
    btn.style.display = "flex";
    if (!place(v)) { btn.style.display = "none"; return; }
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => { btn.style.display = "none"; }, 4000);
  }

  document.addEventListener("mouseover", e => {
    if (e.target === btn || btn.contains(e.target)) return;
    const v = e.target.tagName === "VIDEO" ? e.target : findVideoUnder(e);
    if (v) show(v);
  }, true);

  // Many players (YouTube etc.) put overlays above the <video>: find a video under the pointer.
  function findVideoUnder(e) {
    for (const v of document.querySelectorAll("video")) {
      const r = v.getBoundingClientRect();
      if (e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom) return v;
    }
    return null;
  }

  window.addEventListener("scroll", () => { if (current && btn.style.display !== "none") place(current); }, true);
  btn.addEventListener("mouseenter", () => clearTimeout(hideTimer));

  btn.addEventListener("click", e => {
    e.preventDefault(); e.stopPropagation();
    if (!e.isTrusted) return;                 // ignore clicks faked by the web page
    const src = current && (current.currentSrc || current.src);
    chrome.runtime.sendMessage({
      type: "sahm-video",
      pageUrl: (window.top === window ? location.href : document.referrer || location.href),
      frameUrl: location.href,
      title: document.title,
      src: src && !src.startsWith("blob:") ? src : ""
    }, resp => {
      btn.querySelector("span:last-child").textContent =
        resp && resp.ok ? "Sent to Sahm ✓" : "Sahm is not running";
      setTimeout(() => { btn.querySelector("span:last-child").textContent = "Download this video"; }, 2500);
    });
  });
})();

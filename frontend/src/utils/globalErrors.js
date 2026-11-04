/* Safety net: a failed request (403, 500, no connection ...) that a screen forgot to handle must never take the
   whole page down with a red "Uncaught runtime errors" overlay. It is shown as a small message instead, naming the
   request so the cause can be found. Real code errors (anything that is not a failed request) are left alone. */
let box = null;
let timer = null;

function show(text) {
  if (!box) {
    box = document.createElement("div");
    box.setAttribute("role", "alert");
    box.style.cssText = "position:fixed;right:16px;bottom:16px;max-width:360px;background:#fff7ed;color:#9a3412;border:1px solid #fdba74;" +
      "border-radius:10px;padding:10px 14px;font:13px/1.4 Inter,system-ui,sans-serif;box-shadow:0 6px 20px rgba(0,0,0,.15);z-index:2000;cursor:pointer";
    box.title = "Click to dismiss";
    box.onclick = () => { box.style.display = "none"; };
    document.body.appendChild(box);
  }
  box.textContent = text;
  box.style.display = "block";
  clearTimeout(timer);
  timer = setTimeout(() => { if (box) box.style.display = "none"; }, 9000);
}

export function describeRequestError(err) {
  const r = err.response;
  const cfg = err.config || {};
  const where = `${(cfg.method || "").toUpperCase()} ${String(cfg.url || "").replace(/^https?:\/\/[^/]+/, "")}`.trim();
  if (!r) return `Cannot reach the server${where ? ` (${where})` : ""}. Check that the backend is running.`;
  const detail = (r.data && (r.data.detail || (typeof r.data === "string" ? "" : ""))) || "";
  const why = r.status === 403 ? "You are not allowed to do that" : r.status === 404 ? "Not found" : r.status >= 500 ? "Server error" : "Request failed";
  return `${why} (${r.status})${detail ? `: ${detail}` : ""}${where ? ` — ${where}` : ""}`;
}

window.addEventListener("unhandledrejection", (e) => {
  const err = e.reason;
  if (err && err.isAxiosError) {
    e.preventDefault();
    e.stopImmediatePropagation();     // keeps the development error overlay from covering the page
    if (err.code === "ERR_CANCELED" || err.name === "CanceledError") return;
    // eslint-disable-next-line no-console
    console.warn("Unhandled request error:", err);
    show(describeRequestError(err));
  }
}, true);

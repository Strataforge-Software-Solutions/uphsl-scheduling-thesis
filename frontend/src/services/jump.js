/* "Go to" from a notification: the bell asks for a place (e.g. "gened-requests"),
   the dashboard opens the tab that holds it, and the place scrolls itself into view
   once it has loaded. One pending jump at a time; nothing is stored anywhere. */
const EVENT = "ufast:jump";
let pending = null;

// which place a notification points to ("" when it has none)
export function notificationTarget(n) {
  const m = (n && n.message) || "";
  if (/Gen Ed move requests/i.test(m) || /^Your request to move /i.test(m)) return "gened-requests";
  return "";
}

export function jumpTo(target) {
  pending = target;
  window.dispatchEvent(new CustomEvent(EVENT, { detail: target }));
}

// true once, for the place the last jump asked for
export function takeJump(target) {
  if (pending !== target) return false;
  pending = null;
  return true;
}

export function onJump(handler) {
  const fn = (e) => handler(e.detail);
  window.addEventListener(EVENT, fn);
  return () => window.removeEventListener(EVENT, fn);
}

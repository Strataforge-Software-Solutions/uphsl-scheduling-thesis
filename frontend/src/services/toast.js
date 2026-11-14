export function notifyToast(message, type = "success") {
  const text = typeof message === "string" ? message.trim() : "";
  if (!text) return;
  window.dispatchEvent(new CustomEvent("app-toast", { detail: { message: text, type } }));
}

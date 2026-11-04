/* A failed data load must be visible, not an "Uncaught (in promise)" crash and not silently empty.
   Usage:  API.get("/x/").then(...).catch(reportLoadError("the faculty list"))
   The error is logged to the console with its status, and the LoadErrorBanner (App.js) shows a short message with Reload. */
export const LOAD_FAILED_EVENT = "api-load-failed";

export function describeLoadError(err) {
  const status = err?.response?.status;
  if (!err?.response) return "could not reach the server (is the backend running, and the database connection up?)";
  const detail = typeof err.response.data?.detail === "string" ? err.response.data.detail : "";
  return `server error ${status}${detail ? `: ${detail}` : ""}`;
}

export const reportLoadError = (what) => (err) => {
  const why = describeLoadError(err);
  // eslint-disable-next-line no-console
  console.error(`Could not load ${what}: ${why}`, err);
  if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent(LOAD_FAILED_EVENT, { detail: { what, why } }));
};

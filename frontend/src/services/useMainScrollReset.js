import { useEffect } from "react";

/** Start each dashboard page at its top when the selected page changes. */
export function useMainScrollReset(pageKey) {
  useEffect(() => {
    const main = document.querySelector(".app-main");
    if (main) main.scrollTo({ top: 0, left: 0, behavior: "auto" });
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, [pageKey]);
}

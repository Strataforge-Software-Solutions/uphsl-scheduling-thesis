import { useEffect, useState } from "react";

// Keep popovers mounted briefly after closing so their slide-out animation can finish.
export default function usePopupPresence(open, duration = 180) {
  const [present, setPresent] = useState(open);

  useEffect(() => {
    if (open) {
      setPresent(true);
      return undefined;
    }
    if (!present) return undefined;
    const setting = document.documentElement.getAttribute("data-reduce-motion");
    const systemReduced = typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (setting === "on" || (setting !== "off" && systemReduced)) {
      setPresent(false);
      return undefined;
    }
    const timer = window.setTimeout(() => setPresent(false), duration);
    return () => window.clearTimeout(timer);
  }, [open, present, duration]);

  return { present, closing: present && !open };
}

import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import API from "./api";
import { setFormatPrefs } from "../utils/formatDateTime";

/* "My settings": the signed-in user's preferences, loaded once after sign-in and kept here.
   The database is the source of truth. localStorage keeps only a small copy of the display settings so the
   page opens with the right text size before the server answers (no flash); every read and write is in try/catch. */

export const DEFAULT_PREFS = {
  theme: "light", text_size: "medium", table_density: "comfortable", reduce_motion: "system",
  time_format: "12h", date_format: "mdy_short", week_start: "mon", landing_page: "",
  notify_schedule: true, notify_conflict: true, notify_exam: true, notify_substitute: true,
};
const CACHE_KEY = "ufast_display";
const CACHED = ["theme", "text_size", "table_density", "reduce_motion", "time_format", "date_format"];
const ZOOM = { small: 0.9, medium: 1, large: 1.125 };

export function readCache() {
  try {
    const v = JSON.parse(window.localStorage.getItem(CACHE_KEY) || "null");
    return v && typeof v === "object" ? v : null;
  } catch (e) {
    return null;
  }
}
function writeCache(p) {
  try {
    window.localStorage.setItem(CACHE_KEY, JSON.stringify(Object.fromEntries(CACHED.map((k) => [k, p[k]]))));
  } catch (e) { /* private window or blocked storage: the server copy still applies */ }
}

// Themes: "light" = Default and "dark" = site-wide dark colors.
export function resolveTheme(theme) {
  return theme === "dark" ? "dark" : "light";
}

// put the display settings on <html>; DashboardTheme.css reads these attributes (never in print)
export function applyPreferences(p) {
  const prefs = { ...DEFAULT_PREFS, ...(p || {}) };
  const el = document.documentElement;
  const theme = resolveTheme(prefs.theme);
  el.setAttribute("data-theme-pref", theme);
  el.setAttribute("data-theme", theme);
  el.setAttribute("data-text-size", prefs.text_size);
  el.setAttribute("data-density", prefs.table_density);
  el.setAttribute("data-reduce-motion", prefs.reduce_motion);
  el.style.setProperty("--ui-zoom", String(ZOOM[prefs.text_size] || 1));
  setFormatPrefs(prefs);
}

// first paint: the cached copy (public/index.html already set the attributes; this also sets the time / date format)
applyPreferences(readCache() || DEFAULT_PREFS);

const PrefsContext = createContext({ ready: true, prefs: DEFAULT_PREFS, data: null, pictureUrl: "" });
export const usePreferences = () => useContext(PrefsContext);

/* The dashboard tab to open first: the saved landing page if this menu still has it, otherwise the normal home. */
export function useLandingTab(navItems, fallback) {
  const { prefs } = usePreferences();
  const keys = (navItems || []).map((i) => i.key).filter(Boolean);
  return prefs.landing_page && keys.includes(prefs.landing_page) ? prefs.landing_page : fallback;
}

/* Keep the current dashboard page through a refresh in this browser tab. Each role/workspace
   gets its own key, and stale pages are ignored if that workspace's navigation changes. */
export function useDashboardTab(navItems, fallback, scope) {
  const landing = useLandingTab(navItems, fallback);
  const keys = (navItems || []).map((i) => i.key).filter(Boolean);
  const keySignature = keys.join("|");
  const storageKey = `ufast_dashboard_tab:${scope}`;
  const [tab, setTab] = useState(() => {
    try {
      const saved = window.sessionStorage.getItem(storageKey);
      return saved && keys.includes(saved) ? saved : landing;
    } catch (e) {
      return landing;
    }
  });

  useEffect(() => {
    if (!keySignature.split("|").includes(tab)) return;
    try { window.sessionStorage.setItem(storageKey, tab); } catch (e) { /* session storage may be unavailable */ }
  }, [storageKey, tab, keySignature]);

  return [tab, setTab];
}

export function PreferencesProvider({ userId, children }) {
  const [data, setData] = useState(null);
  const [ready, setReady] = useState(!userId);
  const [pictureUrl, setPictureUrl] = useState("");
  const urlRef = useRef("");

  const take = useCallback((d) => {
    setData(d);
    applyPreferences(d.preferences);
    writeCache(d.preferences);
    return d;
  }, []);

  useEffect(() => {
    if (!userId) { setData(null); setReady(true); return undefined; }
    let live = true;
    setReady(false);
    API.get("/accounts/me/preferences/")
      .then((r) => { if (live) take(r.data); })
      .catch(() => { /* defaults stay; the app works without preferences */ })
      .finally(() => { if (live) setReady(true); });
    return () => { live = false; };
  }, [userId, take]);

  // the picture is fetched with the sign-in token (it has no public link)
  const version = data?.profile?.has_picture ? data.profile.picture_version : 0;
  useEffect(() => {
    let live = true;
    const drop = () => { if (urlRef.current) { URL.revokeObjectURL(urlRef.current); urlRef.current = ""; } };
    if (!version) { drop(); setPictureUrl(""); return undefined; }
    API.get("/accounts/me/picture/file/", { responseType: "blob", params: { v: version } })
      .then((r) => { if (!live) return; drop(); urlRef.current = URL.createObjectURL(r.data); setPictureUrl(urlRef.current); })
      .catch(() => { if (live) setPictureUrl(""); });
    return () => { live = false; };
  }, [version]);
  useEffect(() => () => { if (urlRef.current) URL.revokeObjectURL(urlRef.current); }, []);

  const save = useCallback(async (patch) => take((await API.patch("/accounts/me/preferences/", patch)).data), [take]);
  const uploadPicture = useCallback(async (file) => {
    const form = new FormData();
    form.append("picture", file);
    return take((await API.post("/accounts/me/picture/", form)).data);
  }, [take]);
  const removePicture = useCallback(async () => take((await API.delete("/accounts/me/picture/")).data), [take]);

  const value = {
    ready, data, pictureUrl, save, uploadPicture, removePicture,
    prefs: { ...DEFAULT_PREFS, ...(data?.preferences || {}) },
    profile: data?.profile || null,
  };
  return React.createElement(PrefsContext.Provider, { value }, children);
}

// initials for the plain avatar circle
export function initialsOf(first, last, fallback) {
  const clean = (s) => String(s || "").replace(/^(dr|mr|ms|mrs|engr|prof)\.?\s+/i, "").trim();
  const a = clean(first), b = clean(last);
  if (a || b) return ((a[0] || "") + (b[0] || "")).toUpperCase() || "?";
  return (clean(fallback).split(/[\s-]+/).map((w) => w[0]).join("").slice(0, 2) || "?").toUpperCase();
}

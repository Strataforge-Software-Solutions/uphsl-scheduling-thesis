import axios from "axios";

// Use the shared Vercel domain in production. Override locally by creating frontend/.env with:
//   REACT_APP_API_BASE_URL=http://<your-machine's-LAN-IP>:8000/api
// Needed if you're opening the frontend from a different device than the one
// running Django (e.g. testing on a phone/another PC on the same Wi-Fi) --
// 127.0.0.1 on that OTHER device means itself, not your backend machine.
const BASE_URL = process.env.REACT_APP_API_BASE_URL || (
  process.env.NODE_ENV === "production" ? "/api" : "http://127.0.0.1:8000/api"
);

const API = axios.create({
  baseURL: BASE_URL,
  timeout: 120000, // was 45s/20s; bumped since real schedule generation involves genuine
                  // computation, not just a hung connection -- still fails cleanly if truly dead.
});

// Share matching JSON GETs while they are in flight. Page preloading and the
// page's own effect can then use the same response instead of sending two
// requests. Settled responses are never cached, so later visits stay fresh.
const pendingJsonGets = new Map();
const stableValue = (value) => {
  if (Array.isArray(value)) return value.map(stableValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, stableValue(value[key])]));
  }
  return value;
};
const axiosGet = API.get.bind(API);
API.get = (url, config = {}) => {
  const canShare = !config.signal && !config.cancelToken && !config.headers
    && (!config.responseType || config.responseType === "json");
  if (!canShare) return axiosGet(url, config);

  const token = sessionStorage.getItem("access_token") || "";
  const key = JSON.stringify([url, stableValue(config.params || {}), token]);
  const pending = pendingJsonGets.get(key);
  if (pending) return pending;

  const request = axiosGet(url, config);
  pendingJsonGets.set(key, request);
  const clear = () => { if (pendingJsonGets.get(key) === request) pendingJsonGets.delete(key); };
  request.then(clear, clear);
  return request;
};

// Several dashboard widgets can mount together and request the same full
// schedule list. Share only the request already in flight; later refreshes
// still go to the server and always see current data.
let schedulesRequest = null;
let schedulesRequestToken = null;
export function getSchedules() {
  const token = sessionStorage.getItem("access_token");
  if (schedulesRequest && schedulesRequestToken === token) return schedulesRequest;
  schedulesRequestToken = token;
  const request = API.get("/engine/schedules/").finally(() => {
    if (schedulesRequest === request) {
      schedulesRequest = null;
      schedulesRequestToken = null;
    }
  });
  schedulesRequest = request;
  return request;
}

// Attach the JWT to every request once logged in.
API.interceptors.request.use((config) => {
  const token = sessionStorage.getItem("access_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// An expired / invalid session (401 on any call except logging in): go back to the sign-in page instead of
// leaving every screen failing one request at a time.
API.interceptors.response.use((r) => r, (err) => {
  const url = String(err.config?.url || "");
  if (err.response?.status === 401 && sessionStorage.getItem("access_token") && !url.includes("/accounts/login/")) {
    sessionStorage.clear();
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) window.location.assign("/login");
  }
  return Promise.reject(err);
});

/* Any successful change to schedules (generate, edit, approve, delete, resolve, clear) tells every open dashboard to recount from the
   database: Home cards, pending tasks and status never keep an old number. */
const SCHEDULES_EVENT = "schedules-changed";
const CHANGING = /\/(engine|basic-ed|exams|rooms|accounts\/admin\/clear-generated)\//;
let changedTimer = null;
export const notifySchedulesChanged = () => {
  if (typeof window === "undefined") return;
  clearTimeout(changedTimer);
  changedTimer = setTimeout(() => window.dispatchEvent(new Event(SCHEDULES_EVENT)), 250);
};
export const onSchedulesChanged = (fn) => {
  window.addEventListener(SCHEDULES_EVENT, fn);
  return () => window.removeEventListener(SCHEDULES_EVENT, fn);
};
API.interceptors.response.use((r) => {
  const method = String(r.config?.method || "get").toLowerCase();
  if (method !== "get" && CHANGING.test(String(r.config?.url || ""))) notifySchedulesChanged();
  return r;
});

export async function login(username, password) {
  const res = await API.post("/accounts/login/", { username, password });
  sessionStorage.setItem("access_token", res.data.access);
  sessionStorage.setItem("refresh_token", res.data.refresh);
  sessionStorage.setItem("user", JSON.stringify(res.data.user));
  return res.data.user; // { role, faculty_type, department, must_change_password, ... }
}

// The name to show for a signed-in person (header, sidebar): their real name, falling back to the login name.
export function displayName(user) {
  if (!user) return "";
  const n = user.full_name || `${user.first_name || ""} ${user.last_name || ""}`.trim();
  return n || user.username || "";
}

export function logout() {
  sessionStorage.clear();
}

export function getCurrentUser() {
  const raw = sessionStorage.getItem("user");
  return raw ? JSON.parse(raw) : null;
}

// Re-read the signed-in user's profile from the server and keep it if it changed.
export async function refreshCurrentUser() {
  const res = await API.get("/accounts/me/");
  const fresh = res.data;
  const old = getCurrentUser();
  if (JSON.stringify(old) !== JSON.stringify(fresh)) sessionStorage.setItem("user", JSON.stringify(fresh));
  return fresh;
}

// Keep the cached profile in step with the server once the first-login password is set (otherwise a page refresh
// sends the user back to the change-password screen with a stale "must change" flag).
export function markPasswordChanged() {
  const u = getCurrentUser();
  if (u) sessionStorage.setItem("user", JSON.stringify({ ...u, must_change_password: false }));
}

export async function changePassword(newPassword, oldPassword, confirmPassword) {
  // oldPassword is optional -- the forced first-login flow doesn't collect
  // it at all (see accounts/views.py change_password: skipped when
  // must_change_password is True, since the user just authenticated with
  // the default password seconds ago).
  const payload = { new_password: newPassword };
  if (oldPassword) payload.old_password = oldPassword;
  if (confirmPassword !== undefined) payload.confirm_password = confirmPassword;
  return API.post("/accounts/change-password/", payload);
}

export default API;

/* My settings in jsdom with a mocked server: each section saves, shows a message and resets to defaults; the display
   settings apply at once (no reload) and are cached for the next page load; the landing page falls back safely.
   (Not a real browser: layout, zoom and the first paint are not tested here.) */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import API, { refreshCurrentUser } from "../services/api";
import Settings from "./Settings";
import { PreferencesProvider, DEFAULT_PREFS, useLandingTab } from "../services/preferences";
import { formatTime, setFormatPrefs } from "../utils/formatDateTime";

jest.mock("../services/api", () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), patch: jest.fn(), delete: jest.fn() },
  refreshCurrentUser: jest.fn(() => Promise.resolve({})),
}));
global.IS_REACT_ACT_ENVIRONMENT = true;

let server;
function reset(prefs = {}) {
  server = {
    profile: { first_name: "Rita", last_name: "Reyes", email: "", phone: "", school_id: "R9001", username: "UPHM-R9001",
      role: "Registrar", department: "", has_picture: false, picture_version: 0 },
    preferences: { ...DEFAULT_PREFS, ...prefs },
    defaults: DEFAULT_PREFS,
    choices: { landing_page: [["home", "Home"], ["schedules", "Schedules"], ["exams", "Exam Schedule"]] },
  };
}
const clone = () => JSON.parse(JSON.stringify(server));

beforeEach(() => {
  reset();
  try { window.localStorage.clear(); } catch (e) { /* ignore */ }
  API.get.mockImplementation((url) => (url === "/accounts/me/preferences/" ? Promise.resolve({ data: clone() }) : Promise.reject(new Error(url))));
  API.patch.mockImplementation((url, body) => {
    if (body.time_format === "36h") return Promise.reject({ response: { data: { detail: "Bad value." } } });
    const { first_name, last_name, email, phone, ...rest } = body;
    Object.assign(server.preferences, rest);
    Object.entries({ first_name, last_name, email, phone }).forEach(([k, v]) => { if (v !== undefined) server.profile[k] = v; });
    return Promise.resolve({ data: clone() });
  });
  API.post.mockResolvedValue({ data: { updated: 3 } });
  refreshCurrentUser.mockResolvedValue({});
});
afterEach(() => setFormatPrefs({ time_format: "12h", date_format: "mdy_short" }));

let root, box;
async function mount(ui) {
  box = document.createElement("div");
  document.body.appendChild(box);
  root = createRoot(box);
  await act(async () => { root.render(<MemoryRouter><PreferencesProvider userId={1}>{ui}</PreferencesProvider></MemoryRouter>); });
  await act(async () => { await Promise.resolve(); });
}
afterEach(() => { act(() => root.unmount()); box.remove(); });

const byText = (sel, text) => [...box.querySelectorAll(sel)].find((el) => el.textContent.trim() === text);
async function click(el) { await act(async () => { el.click(); }); await act(async () => { await Promise.resolve(); }); }
async function open(section) { await click(byText(".settings-nav-item", section)); }
async function pickOption(label) { await click(byText(".settings-option", label).querySelector("input")); }
async function press(label) { await click(byText("button", label)); }

test("Appearance saves, applies at once, is cached, and resets to defaults", async () => {
  await mount(<Settings user={{ role: "registrar" }} />);
  await open("Appearance");
  await pickOption("Large");
  await pickOption("Compact");
  await press("Save");
  expect(API.patch).toHaveBeenLastCalledWith("/accounts/me/preferences/", { theme: "light", text_size: "large", table_density: "compact", reduce_motion: "system" });
  expect(document.documentElement.getAttribute("data-text-size")).toBe("large");
  expect(document.documentElement.getAttribute("data-density")).toBe("compact");
  expect(JSON.parse(window.localStorage.getItem("ufast_display")).text_size).toBe("large");
  expect(box.textContent).toContain("Saved.");
  await press("Reset to defaults");
  expect(API.patch).toHaveBeenLastCalledWith("/accounts/me/preferences/", { theme: "light", text_size: "medium", table_density: "comfortable", reduce_motion: "system" });
  expect(document.documentElement.getAttribute("data-text-size")).toBe("medium");
  expect(box.textContent).toContain("Reset to defaults and saved.");
  await pickOption("Dark");
  await press("Save");
  expect(document.documentElement.getAttribute("data-theme")).toBe("dark");      // applied at once, no reload
  expect(JSON.parse(window.localStorage.getItem("ufast_display")).theme).toBe("dark");
  await press("Reset to defaults");
  expect(document.documentElement.getAttribute("data-theme")).toBe("light");
});

test("Language and format: the time format changes right away; a server error is shown", async () => {
  await mount(<Settings user={{ role: "registrar" }} />);
  await open("Language and format");
  expect(box.textContent).toContain("Asia/Manila");
  await pickOption("24-hour (07:00)");
  await press("Save");
  expect(formatTime("07:00:00")).toBe("07:00");
  await press("Reset to defaults");
  expect(formatTime("07:00:00")).toBe("7:00 AM");
  API.patch.mockRejectedValueOnce({ response: { data: { detail: "Bad value." } } });
  await pickOption("24-hour (07:00)");
  await press("Save");
  expect(box.textContent).toContain("Bad value.");
});

test("Display: only the role's pages are listed, saved, and reset", async () => {
  await mount(<Settings user={{ role: "registrar" }} />);
  await open("Display preferences");
  const select = box.querySelector("select");
  expect([...select.options].map((o) => o.value)).toEqual(["", "home", "schedules", "exams"]);
  await act(async () => {
    const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value").set;
    setter.call(select, "exams");
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });
  await press("Save");
  expect(API.patch).toHaveBeenLastCalledWith("/accounts/me/preferences/", { landing_page: "exams" });
  await press("Reset to defaults");
  expect(API.patch).toHaveBeenLastCalledWith("/accounts/me/preferences/", { landing_page: "" });
});

test("Notifications: switches save and reset; Mark all as read reports the count", async () => {
  await mount(<Settings user={{ role: "faculty", faculty_type: "full_time" }} />);
  await open("Notifications");
  expect(box.textContent).not.toMatch(/email notifications/i);
  await click(box.querySelector(".settings-switch input"));              // "Schedule published or changed"
  await press("Save");
  expect(API.patch.mock.calls.at(-1)[1].notify_schedule).toBe(false);
  await press("Reset to defaults");
  expect(API.patch.mock.calls.at(-1)[1]).toEqual({ notify_schedule: true, notify_conflict: true, notify_exam: true, notify_substitute: true });
  await press("Mark all as read");
  expect(API.post).toHaveBeenCalledWith("/notifications/mark_all_read/");
  expect(box.textContent).toContain("Marked 3 notifications as read.");
});

test("Profile: school ID and role are read-only; a bad email is stopped; a valid change saves", async () => {
  await mount(<Settings user={{ role: "registrar" }} />);
  expect(box.textContent).toContain("R9001");
  expect(box.querySelectorAll("input[value='R9001']").length).toBe(0);     // shown as text, not an input
  const email = box.querySelector("input[type='email']");
  const setValue = async (el, v) => act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(el, v);
    el.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await setValue(email, "not-an-email");
  await press("Save");
  expect(API.patch).not.toHaveBeenCalled();
  await setValue(email, "rita@manila.uphsl.edu.ph");
  await press("Save");
  expect(API.patch.mock.calls.at(-1)[1].email).toBe("rita@manila.uphsl.edu.ph");
  expect(box.textContent).toContain("Profile saved.");
  expect(box.textContent).toContain("RR");                                      // initials when there is no picture
});

test("Help and about: the role's steps, version and a marked placeholder for support", async () => {
  await mount(<Settings user={{ role: "student" }} />);
  await open("Help and about");
  expect(box.querySelectorAll(".settings-steps li").length).toBeGreaterThanOrEqual(5);
  expect(box.textContent).toContain("U-FAST");
  expect(box.textContent).toContain("Not set yet");
});

function Landing({ nav, fallback }) { return <span id="landing">{useLandingTab(nav, fallback)}</span>; }

test("the landing page opens when the menu has it, and falls back to home otherwise", async () => {
  reset({ landing_page: "exams" });
  await mount(<Landing nav={[{ key: "home" }, { key: "exams" }]} fallback="home" />);
  expect(box.querySelector("#landing").textContent).toBe("exams");
  act(() => root.unmount()); box.remove();
  await mount(<Landing nav={[{ key: "home" }, { key: "schedules" }]} fallback="home" />);
  expect(box.querySelector("#landing").textContent).toBe("home");
});

test("a later page load starts from the cached display settings, and survives blocked storage", () => {
  window.localStorage.setItem("ufast_display", JSON.stringify({ text_size: "small", table_density: "compact", time_format: "24h" }));
  jest.isolateModules(() => { require("../services/preferences"); });
  expect(document.documentElement.getAttribute("data-text-size")).toBe("small");
  const spy = jest.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
  expect(() => jest.isolateModules(() => { require("../services/preferences"); })).not.toThrow();
  spy.mockRestore();
});

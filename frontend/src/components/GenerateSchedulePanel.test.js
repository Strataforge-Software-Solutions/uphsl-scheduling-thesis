/* Renders the real Generate panel in jsdom with a mocked server: the dialog must never crash while the Professor list is loading,
   after it loads, when it fails, for the Registrar, or after Generate. (Not a real browser: layout and clicks in Chrome are not tested.) */
import React from "react";
import { createRoot } from "react-dom/client";
import { act } from "react-dom/test-utils";
import GenerateSchedulePanel from "./GenerateSchedulePanel";
import API from "../services/api";
import { rankProfessors } from "../utils/suggestProfessors";

jest.mock("../services/api", () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), patch: jest.fn() } }));
global.IS_REACT_ACT_ENVIRONMENT = true;

const SUBJECTS = [
  { id: 11, code: "CS101", title: "Programming 1 - Lec", program: 1, year_level: "1st Year", semester: "1st Sem", classification: "major", lec_units: 2, lab_units: 0, need_minutes: 120 },
  { id: 12, code: "CS101L", title: "Programming 1 - Lab", program: 1, year_level: "1st Year", semester: "1st Sem", classification: "major", lec_units: 0, lab_units: 1, need_minutes: 180 },
  { id: 13, code: "CS199", title: "Seminar (nobody qualified)", program: 1, year_level: "1st Year", semester: "1st Sem", classification: "major", lec_units: 3, lab_units: 0, need_minutes: 180 },
  { id: 14, code: "GEC105", title: "Mathematics in the Modern World", program: 1, year_level: "1st Year", semester: "1st Sem", classification: "minor", lec_units: 3, lab_units: 0, need_minutes: 180 },
];
const OPTIONS = {
  policy: "override", sections: 1,
  subjects: [
    { subject_id: 11, code: "CS101", qualified: [1, 2], partner_id: 12, blocks: [120], sections: 1, total_hours: 2, no_qualified_reason: "" },
    { subject_id: 12, code: "CS101L", qualified: [1, 2], partner_id: 11, blocks: [180], sections: 1, total_hours: 3, no_qualified_reason: "" },
    { subject_id: 13, code: "CS199", qualified: [], partner_id: null, blocks: [180], sections: 1, total_hours: 3, no_qualified_reason: "No qualified faculty for CS199." },
  ],
  teachers: {
    1: { id: 1, label: "Ang, V.", current_hours: 11, max_hours: 24, submitted: true, free: { Tue: [[480, 720]] }, preferred: {} },
    2: { id: 2, label: "Mazo, J.", current_hours: 11, max_hours: 12, submitted: true, free: { Sat: [[420, 990]] }, preferred: {} },
  },
};

let professorList;            // what /engine/generate/professor-options/ does in this test: a pending / resolved / rejected promise
function serve(url) {
  const data = {
    "/curriculum/programs/": [{ id: 1, name: "BS Computer Science", department: "College of Computer Studies" }],
    "/engine/sections/": [{ id: 5, program: 1, year_level: "1st Year", semester: "1st Sem" }],
    "/curriculum/subjects/": SUBJECTS,
    "/rooms/preview-choices/": { rooms: [], saved: {} },
    "/engine/shared-classes/options/": { subjects: [] },
    "/engine/unplaced/": { items: [] },
  }[url];
  if (url === "/engine/generate/professor-options/") return professorList();
  return Promise.resolve({ data: data === undefined ? {} : data });
}

let container, root;
const flush = async () => { for (let i = 0; i < 6; i += 1) { await act(async () => { await new Promise((r) => setTimeout(r, 0)); }); } };
async function mount(props) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => { root.render(<GenerateSchedulePanel departments={["College of Computer Studies"]} initialProgramId={1} {...props} />); });
  await flush();
}

beforeEach(() => { API.get.mockImplementation((url) => serve(url)); jest.spyOn(console, "error").mockImplementation(() => {}); });
afterEach(() => { act(() => root.unmount()); container.remove(); jest.restoreAllMocks(); });

const rowText = () => [...container.querySelectorAll("tbody tr")].map((tr) => tr.textContent);
// the Professor column is the shared TeacherPicker: a button that opens a searchable list
const profSelect = (code) => container.querySelector(`button[aria-label="Professor for ${code}"]`);
const openProf = async (code) => { await act(async () => { profSelect(code).click(); }); };
const pickProf = async (code, id) => {
  await openProf(code);
  await act(async () => { document.querySelector(`[role="option"][id$="-${id}"]`).click(); });
};

test("every row renders while the Professor list is still loading (the crash)", async () => {
  professorList = () => new Promise(() => {});                    // never answers
  const warn = jest.spyOn(console, "warn").mockImplementation(() => {});
  await mount({ role: "dean" });
  expect(warn).not.toHaveBeenCalled();                            // the fix: nothing is ranked before the data is there (guard not needed)
  expect(rowText().some((t) => t.includes("CS101L"))).toBe(true);
  expect(profSelect("CS101").textContent).toContain("Loading…");
  expect(container.textContent).not.toContain("Something went wrong");
});

test("after loading: Suggested / Qualified groups, and the no-qualified-faculty reason", async () => {
  professorList = () => Promise.resolve({ data: OPTIONS });
  await mount({ role: "dean" });
  await openProf("CS101");
  const list = document.querySelector('[role="listbox"]');
  const groups = [...list.querySelectorAll('[role="group"]')].map((g) => g.getAttribute("aria-label"));
  expect(groups).toEqual(["Suggested", "Other qualified"]);
  expect(list.textContent).toContain("Ang, V. — Free Tue 8:00 AM-12:00 PM · 11 of 24 hrs");
  expect(list.textContent).toContain("Mazo, J. (11 of 12 hrs) — Over weekly limit");
  expect(profSelect("CS199").disabled).toBe(true);
  expect(container.textContent).toContain("No qualified faculty for CS199.");
  expect(container.textContent).not.toContain("Something went wrong");
});

test("a failed Professor list leaves every row usable and says so", async () => {
  professorList = () => Promise.reject(new Error("network"));
  await mount({ role: "dean" });
  expect(rowText().length).toBeGreaterThanOrEqual(3);
  expect(container.textContent).toContain("The professor list could not be loaded");
});

test("the Registrar's Gen Ed view has a Professor column for its Gen Ed subjects", async () => {
  const GEN_ED = { ...OPTIONS, subjects: [{ subject_id: 14, code: "GEC105", qualified: [1], partner_id: null, blocks: [180], sections: 1, total_hours: 3,
    no_qualified_reason: "", groups: { suggested: [{ id: 1, label: "Ang, V.", full_name: "Ang, V.", load_text: "11/24 hrs", after_generate_hours: null,
      selectable: true, not_connected: false, tag: "Lowest load" }], qualified: [], other: [], other_shown: false, full_line: [], full_text: "",
      approval_text: "", empty_text: "" } }] };
  professorList = () => Promise.resolve({ data: GEN_ED });
  API.post.mockResolvedValue({ data: { created_schedule_ids: [1], clashes: { total: 0, conflicts: [] }, workload_warnings: [], conflicts: [] } });
  await mount({ role: "registrar" });
  expect(rowText().some((t) => t.includes("GEC105"))).toBe(true);
  expect(API.get.mock.calls.some(([u]) => u === "/engine/generate/professor-options/")).toBe(true);
  await pickProf("GEC105", 1);
  expect(profSelect("GEC105").textContent).toContain("Ang, V.");
  const gen = [...container.querySelectorAll("button")].find((b) => b.textContent === "Generate");
  await act(async () => { gen.click(); });
  await flush();
  const body = API.post.mock.calls.find(([u]) => u === "/engine/generate-schedule/")[1];
  expect(body.teacher_choices).toEqual({ 14: 1 });
  expect(container.textContent).not.toContain("Not connected to this subject");      // no Assign anyway for Gen Ed
});

test("Generate: a skipped class opens the pop-up (no fix by itself; a skip for lack of qualified faculty offers the list)", async () => {
  professorList = () => Promise.resolve({ data: OPTIONS });
  API.post.mockResolvedValue({ data: { created_schedule_ids: [1], clashes: { total: 0, conflicts: [] }, workload_warnings: [],
    conflicts: [{ section_id: 5, subject_id: 13, section: "A1", subject: "CS199 - Seminar", code: "CS199", title: "Seminar", year_level: "1st Year", reason: "No qualified faculty for CS199." }] } });
  await mount({ role: "dean" });
  const gen = [...container.querySelectorAll("button")].find((b) => b.textContent === "Generate");
  await act(async () => { gen.click(); });
  await flush();
  const dlg = document.querySelector('[aria-label="Some classes were not placed"]');
  expect(dlg).not.toBeNull();
  expect(dlg.textContent).toContain("No qualified faculty for CS199.");
  expect([...dlg.querySelectorAll("button")].map((b) => b.textContent)).toEqual(["See other available faculty", "OK"]);
  expect(API.post.mock.calls.some(([u]) => u === "/engine/slot-options/apply/")).toBe(false);      // nothing assigned by itself
});

test("guard: a missing row warns and returns 'No suggestions' instead of throwing", () => {
  const warn = jest.spyOn(console, "warn").mockImplementation(() => {});
  expect(rankProfessors([], undefined, null)).toEqual({ suggested: [], others: [], missing: true });
  expect(warn).toHaveBeenCalled();
});

test("Start / End: End follows Start, the hint shows the earliest end and the chosen professor's free time", async () => {
  professorList = () => Promise.resolve({ data: { ...OPTIONS, teachers: { ...OPTIONS.teachers, 2: { ...OPTIONS.teachers[2], max_hours: 24, free: { Mon: [[600, 720]] } } } } });
  await mount({ role: "dean" });
  const sel = (label) => container.querySelector(`select[aria-label="${label}"]`);
  const choose = async (el, v) => { await act(async () => { el.value = v; el.dispatchEvent(new Event("change", { bubbles: true })); }); };
  await pickProf("CS101", 2);
  await choose(sel("Start time for CS101"), "10:30");
  expect(sel("End time for CS101").value).toBe("12:30");                                   // earliest valid End set automatically
  const ends = [...sel("End time for CS101").options].map((o) => o.value);
  expect(ends).not.toContain("12:00");
  expect(ends[0]).toBe("");                                                                 // "Any time" is still there
  const hint = container.querySelector('[aria-label="Time hint for CS101"]').textContent;
  expect(hint).toContain("Needs 2 hrs - earliest end 12:30 PM");
  expect(hint).toContain("Mazo, J. free Mon 10:00 AM-12:00 PM (none of it fits this range");        // 10:30-12:30 is outside 10-12
  const startText = (v) => [...sel("Start time for CS101").options].find((o) => o.value === v).textContent;
  expect(startText("10:30")).toContain("outside professor's time");                       // marked, still selectable
  expect(startText("10:00")).not.toContain("outside");                                    // 10:00-12:00 fits his time
  await choose(sel("End time for CS101"), "13:00");
  expect(container.querySelector('[aria-label="Time hint for CS101"]').textContent).not.toContain("lunch");     // noon is ordinary time
  const gen = [...container.querySelectorAll("button")].find((b) => b.textContent === "Generate");
  expect(gen.disabled).toBe(false);                                                         // a valid range: Generate allowed
});

test("the Dean's dialog no longer lists the Gen Ed subjects (nor loads the shared-class choices)", async () => {
  professorList = () => Promise.resolve({ data: OPTIONS });
  await mount({ role: "dean" });
  expect(container.textContent).not.toContain("for your information");
  expect(API.get.mock.calls.some(([u]) => u === "/engine/shared-classes/options/")).toBe(false);
});


/* ---- the server's three Professor groups (engine/faculty_groups.py) */
const person = (id, label, extra = {}) => ({ id, label, full_name: label, school_id: `F${id}`, username: `u${id}`, current_hours: 12, max_hours: 24,
  load_text: "12/24 hrs", after_generate_hours: null, specializations: "Nursing", selectable: true, not_connected: false, tag: "Free at this time", ...extra });
const withGroups = (groups) => ({ ...OPTIONS, subjects: OPTIONS.subjects.map((x) => (x.code === "CS101" ? { ...x, groups } : x)),
  teachers: { ...OPTIONS.teachers, 7: { id: 7, label: "Cruz, L.", current_hours: 6, projected_hours: 6, max_hours: 24, free: {}, preferred: {}, submitted: false } } });
const G_BASE = { other_shown: false, other: [], full_line: [], full_text: "", approval_text: "Not connected to this subject. Dean approval required.", empty_text: "" };

test("groups: Suggested and Qualified from the server, muted rows not selectable, no Other group while someone qualified is free", async () => {
  professorList = () => Promise.resolve({ data: withGroups({ ...G_BASE,
    suggested: [person(1, "Ang, V.", { tag: "Lowest load" })],
    qualified: [person(2, "Mazo, J.", { selectable: false, tag: "Full: 24/24 hrs" })],
  }) });
  await mount({ role: "dean" });
  await openProf("CS101");
  const list = document.querySelector('[role="listbox"]');
  expect([...list.querySelectorAll('[role="group"]')].map((g) => g.getAttribute("aria-label"))).toEqual(["Suggested", "Qualified"]);
  expect(list.textContent).toContain("Ang, V. (12/24 hrs)Lowest load");
  const muted = list.querySelector('[aria-disabled="true"]');
  expect(muted.textContent).toContain("Full: 24/24 hrs");
  await act(async () => { muted.click(); });
  expect(profSelect("CS101").textContent).not.toContain("Mazo");                 // not selectable
  expect(list.textContent).not.toContain("Other available");
});

test("groups: Other available only when Suggested is empty; choosing someone asks for a reason; Generate sends the override", async () => {
  professorList = () => Promise.resolve({ data: withGroups({ ...G_BASE, other_shown: true, suggested: [],
    qualified: [person(2, "Mazo, J.", { selectable: false, tag: "Busy at this time (CS102)" })],
    other: [person(7, "Cruz, L.", { not_connected: true, tag: "Not connected" })],
    full_line: [{ id: 8, label: "Reyes, P." }], full_text: "Full: Reyes, P. 24/24 hrs",
  }) });
  API.post.mockResolvedValue({ data: { created_schedule_ids: [1], clashes: { total: 0, conflicts: [] }, workload_warnings: [], conflicts: [] } });
  await mount({ role: "dean" });
  await openProf("CS101");
  const list = document.querySelector('[role="listbox"]');
  expect(list.textContent).toContain("Other available (not connected to this subject)");
  expect(list.textContent).toContain("Not connected to this subject. Dean approval required.");
  expect(list.textContent).toContain("Full: Reyes, P. 24/24 hrs");
  // search filters across groups
  const search = document.querySelector('[role="combobox"]');
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(search, "cruz");
    search.dispatchEvent(new Event("input", { bubbles: true }));
  });
  expect(list.textContent).toContain("Cruz, L.");
  expect(list.textContent).not.toContain("Mazo, J.");
  await act(async () => { document.querySelector('[role="option"][id$="-7"]').click(); });
  const dlg = document.querySelector('[aria-labelledby="assign-anyway-title"]');
  expect(dlg.textContent).toContain("Cruz, L. is not connected to CS101");
  const assign = [...dlg.querySelectorAll("button")].find((b) => b.textContent === "Assign");
  expect(assign.disabled).toBe(true);                                             // a reason is required
  const reason = dlg.querySelector("input");
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(reason, "no qualified faculty free");
    reason.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await act(async () => { assign.click(); });
  expect(container.textContent).toContain("Assigned by Dean (not connected)");
  const gen = [...container.querySelectorAll("button")].find((b) => b.textContent === "Generate");
  await act(async () => { gen.click(); });
  await flush();
  const body = API.post.mock.calls.find(([u]) => u === "/engine/generate-schedule/")[1];
  expect(body.teacher_choices[11]).toEqual({ teacher: 7, override_qualification: true, reason: "no qualified faculty free" });
});

test("groups: nobody at all -> the plain message", async () => {
  professorList = () => Promise.resolve({ data: withGroups({ ...G_BASE, suggested: [], qualified: [], empty_text: "No faculty in your department is free at this time." }) });
  await mount({ role: "dean" });
  await openProf("CS101");
  expect(document.querySelector('[role="listbox"]').textContent).toContain("No faculty in your department is free at this time.");
});

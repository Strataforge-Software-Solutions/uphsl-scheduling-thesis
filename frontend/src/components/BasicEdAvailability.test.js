/* SHS / JHS availability: the teacher's submit flow and status, and the Principal's read-only view. */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import API from "../services/api";
import { MyAvailability, FacultyAvailability } from "./BasicEdAvailability";

jest.mock("../services/api", () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn() } }));
global.IS_REACT_ACT_ENVIRONMENT = true;

const GRID = {
  grades: [11, 12], days: [{ key: "Mon", label: "Monday" }, { key: "Tue", label: "Tuesday" }], preferred_start: "", preferred_end: "",
  rows: [
    { start: "07:00", end: "07:50", kind: "period", label: "", note: "", outside_preferred: false },
    { start: "09:30", end: "10:00", kind: "break", label: "Break", note: "", outside_preferred: false },
    { start: "10:00", end: "10:50", kind: "period", label: "", note: "Break for Grade 11", outside_preferred: false },
  ],
};
const CELLS = { "Mon|07:00": "available", "Mon|10:00": "available", "Tue|07:00": "unavailable", "Tue|10:00": "available" };
const MINE = { faculty_id: 4, full_name: "Ana Cruz", status: "not_submitted", submitted_at: null, note: "", grid: GRID, cells: CELLS };

let box, root;
beforeEach(() => { try { window.localStorage.clear(); } catch (e) { /* ignore */ } });
afterEach(() => { act(() => root.unmount()); box.remove(); });
const flush = async () => { for (let i = 0; i < 4; i += 1) await act(async () => { await new Promise((r) => setTimeout(r, 0)); }); };
async function mount(ui) {
  box = document.createElement("div"); document.body.appendChild(box); root = createRoot(box);
  await act(async () => { root.render(ui); });
  await flush();
}
const button = (text) => [...box.querySelectorAll("button")].find((b) => b.textContent === text);

test("teacher: the grid shows words, a break cannot be marked, changes are submitted, and the status follows", async () => {
  API.get.mockResolvedValue({ data: MINE });
  API.post.mockResolvedValue({ data: { ...MINE, status: "submitted", submitted_at: "2026-11-07T01:00:00Z", cells: { ...CELLS, "Mon|07:00": "preferred" },
    detail: "Submitted to the Principal." } });
  await mount(<MyAvailability />);
  expect(box.textContent).toContain("Not submitted (free at any time)");
  expect(box.textContent).toContain("Break (not a class time)");
  expect(box.textContent).toContain("Break for Grade 11");
  expect(box.querySelectorAll('button[aria-label*="Press to change"]').length).toBe(4);       // 2 days x 2 class periods, never the break
  const cell = box.querySelector('button[aria-label^="Monday 7:00 AM"]');
  expect(cell.textContent).toBe("Available");
  await act(async () => { cell.click(); });
  expect(cell.textContent).toBe("Preferred");
  expect(box.textContent).toContain("You have changes that are not submitted yet.");
  await act(async () => { button("Submit to Principal").click(); });
  await flush();
  const body = API.post.mock.calls[0][1];
  expect(API.post.mock.calls[0][0]).toBe("/basic-ed/my/availability/");
  expect(body.cells).toContainEqual({ day: "Mon", start: "07:00", preference: "preferred" });
  expect(body.cells).toContainEqual({ day: "Tue", start: "07:00", preference: "unavailable" });
  expect(box.textContent).toMatch(/Status: Submitted on /);
  expect(box.textContent).not.toContain("You have changes");
});

test("teacher: a returned submission shows the note and that the last submission is still in use", async () => {
  API.get.mockResolvedValue({ data: { ...MINE, status: "returned", submitted_at: "2026-11-01T01:00:00Z", note: "Friday is free now" } });
  await mount(<MyAvailability />);
  expect(box.textContent).toContain("Returned for correction (last submission still in use)");
  expect(box.textContent).toContain("Principal's note: Friday is free now");
});

const LIST = { level: "SHS", can_edit_status: true, teachers: [
  { faculty_id: 4, full_name: "Ana Cruz", department: "Math", status: "submitted", submitted_at: "2026-11-05T01:00:00Z", updated_since_generation: true,
    note: "", load_hours: 12, max_weekly_hours: 30, preferred_start: "", preferred_end: "" },
  { faculty_id: 5, full_name: "Ben Lim", department: "English", status: "not_submitted", submitted_at: null, updated_since_generation: false,
    note: "", load_hours: 0, max_weekly_hours: 30, preferred_start: "", preferred_end: "" }] };

test("Principal: status list and a READ-ONLY grid with words; return for correction needs a note; reminders", async () => {
  API.get.mockImplementation((url) => Promise.resolve({ data: url.endsWith("availability/") ? LIST
    : { ...MINE, status: "submitted", submitted_at: "2026-11-05T01:00:00Z", load_hours: 12, max_weekly_hours: 30 } }));
  API.post.mockResolvedValue({ data: { detail: "Returned to Ana Cruz.", status: "returned", note: "Fix Friday" } });
  await mount(<FacultyAvailability level="SHS" />);
  expect(box.textContent).toContain("Updated since last generation");
  expect(box.textContent).toContain("Not submitted (free at any time)");
  expect(box.textContent).toContain("Remind teachers who have not submitted (1)");
  await act(async () => { button("View").click(); });
  await flush();
  expect(box.querySelectorAll('button[aria-label*="Press to change"]').length).toBe(0);       // the Principal cannot edit
  expect(box.textContent).toContain("Unavailable");
  const ret = button("Return for correction");
  expect(ret.disabled).toBe(true);                                                            // a note is required
  const input = box.querySelector("input");
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(input, "Fix Friday");
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await act(async () => { button("Return for correction").click(); });
  await flush();
  expect(API.post).toHaveBeenCalledWith("/basic-ed/availability/4/return/", { level: "SHS", note: "Fix Friday" }, { params: { level: "SHS" } });
  await act(async () => { button("Remind teachers who have not submitted (1)").click(); });
  expect(API.post).toHaveBeenCalledWith("/basic-ed/availability/remind/", { level: "SHS" }, { params: { level: "SHS" } });
});

test("IT Admin: read only (no return or remind buttons)", async () => {
  API.get.mockResolvedValue({ data: { ...LIST, can_edit_status: false } });
  await mount(<FacultyAvailability level="SHS" />);
  expect(button("Remind teachers who have not submitted (1)")).toBeUndefined();
});

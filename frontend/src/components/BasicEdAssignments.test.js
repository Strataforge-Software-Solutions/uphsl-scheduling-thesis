/* SHS / JHS pin panel: the server's three groups; a not-connected pick asks for a reason and sends the override; muted rows do nothing. */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import API from "../services/api";
import TeachingAssignmentsPanel from "./BasicEdAssignments";

jest.mock("../services/api", () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), patch: jest.fn(), delete: jest.fn() } }));
global.IS_REACT_ACT_ENVIRONMENT = true;

const P = (id, label, extra = {}) => ({ id, label, full_name: label, school_id: `E${id}`, username: `u${id}`, current_hours: 10, max_hours: 30,
  load_text: "10/30 hrs", after_generate_hours: null, specializations: "Filipino", selectable: true, not_connected: false, tag: "Has free periods", ...extra });
const OPTIONS = { section: { id: 3, name: "11-STEM-A", grade_level: 11 }, subjects: [{
  subject_id: 9, code: "GENMATH", name: "General Mathematics", sessions_per_week: 4, needs: "Mathematics", pin: null,
  groups: { suggested: [], qualified: [P(1, "Reyes, A.", { selectable: false, tag: "Full: 30/30 hrs" })], other: [P(2, "Lim, B.", { not_connected: true, tag: "Not connected" })],
    other_shown: true, full_line: [], full_text: "", approval_text: "Not connected to this subject. Principal approval required.", empty_text: "" } }] };

let box, root;
beforeEach(() => {
  API.get.mockImplementation((url) => Promise.resolve({ data: url.includes("sections/") ? [{ id: 3, name: "11-STEM-A", grade_level: 11 }] : OPTIONS }));
  API.post.mockResolvedValue({ data: { id: 50 } });
});
afterEach(() => { act(() => root.unmount()); box.remove(); });
const flush = async () => { for (let i = 0; i < 5; i += 1) await act(async () => { await new Promise((r) => setTimeout(r, 0)); }); };
const setVal = async (el, v, ev = "input") => act(async () => {
  const proto = el.tagName === "SELECT" ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value").set.call(el, v);
  el.dispatchEvent(new Event(ev, { bubbles: true }));
});

test("Principal: Other available shows with its note; picking asks for a reason and pins with the override", async () => {
  box = document.createElement("div"); document.body.appendChild(box); root = createRoot(box);
  await act(async () => { root.render(<TeachingAssignmentsPanel level="SHS" />); });
  await flush();
  await setVal(box.querySelector("select"), "3", "change");
  await flush();
  await act(async () => { box.querySelector('button[aria-label="Teacher for GENMATH"]').click(); });
  const list = document.querySelector('[role="listbox"]');
  expect(list.textContent).toContain("Not connected to this subject. Principal approval required.");
  await act(async () => { list.querySelector('[aria-disabled="true"]').click(); });
  expect(API.post).not.toHaveBeenCalled();                                         // a full teacher cannot be picked
  await act(async () => { document.querySelector('[role="option"][id$="-2"]').click(); });
  const dlg = document.querySelector('[aria-labelledby="assign-anyway-title"]');
  expect(dlg.textContent).toContain('marked "Assigned by Principal (not connected)"');
  await setVal(dlg.querySelector("input"), "no math teacher free");
  await act(async () => { [...dlg.querySelectorAll("button")].find((b) => b.textContent === "Assign").click(); });
  await flush();
  expect(API.post).toHaveBeenCalledWith("/basic-ed/assignments/",
    { level: "SHS", faculty: 2, section: 3, subject: 9, override_qualification: true, override_reason: "no math teacher free" }, { params: { level: "SHS" } });
});

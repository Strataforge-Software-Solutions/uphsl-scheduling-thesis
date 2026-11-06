/* The Faculty time pop-over as a day-by-day table (Monday-Saturday): submitted windows, classes taught, suggested free time. */
import React from "react";
import { createRoot } from "react-dom/client";
import { act } from "react-dom/test-utils";
import FacultyTimePopover, { dayRows } from "./FacultyTimePopover";
import API from "../services/api";

jest.mock("../services/api", () => ({ __esModule: true, default: { get: jest.fn() } }));
global.IS_REACT_ACT_ENVIRONMENT = true;

const ANG = {
  name: "Vincent D. Ang", faculty_type: "full_time", current_hours: 3, max_hours: 24, semester: "1st Sem", submitted: true,
  availability: [{ day: "Tue", start: "11:30", end: "14:30", preference: "available" }, { day: "Wed", start: "07:00", end: "10:00", preference: "preferred" },
    { day: "Wed", start: "08:00", end: "09:00", preference: "unavailable" }],
  teaching: [{ day: "Tue", start: "12:00", end: "13:00", code: "CS1101", section: "A1", room: "307D", status: "draft" }],
};

test("suggested free time = available / preferred windows minus unavailable time and classes", () => {
  const rows = Object.fromEntries(dayRows(ANG).map((r) => [r.day, r]));
  expect(Object.keys(rows)).toEqual(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]);
  expect(rows.Mon.suggested).toEqual([]);                                             // not in their availability: no BEST time ...
  expect(rows.Mon.also.map((x) => [x.a, x.b])).toEqual([[420, 1200]]);                // ... but the whole day is still possible
  expect(rows.Wed.also.map((x) => [x.a, x.b])).toEqual([[600, 1200]]);                // 8-9 unavailable and 7-10 best: the rest
  expect(rows.Tue.suggested.map((x) => [x.a, x.b])).toEqual([[690, 720], [780, 870]]); // 11:30-12:00, 1:00-2:30 (class removed)
  expect(rows.Wed.suggested).toEqual([{ a: 420, b: 480, preferred: true }, { a: 540, b: 600, preferred: true }]);
  const open = dayRows({ ...ANG, submitted: false, availability: [] });
  expect(open[1].suggested.map((x) => [x.a, x.b])).toEqual([[420, 720], [780, 1200]]); // nothing submitted: 7 AM-8 PM minus the class
});

test("renders one row per day with the suggested times", async () => {
  API.get.mockResolvedValue({ data: ANG });
  const el = document.createElement("div");
  document.body.appendChild(el);
  const root = createRoot(el);
  await act(async () => { root.render(<FacultyTimePopover teachers={[{ id: 1, label: "Ang, V." }]} semester="1st Sem" onClose={() => {}} />); });
  const rows = [...el.querySelectorAll('table[aria-label="Weekly availability by day"] tbody tr')].map((tr) => tr.textContent);
  expect(rows).toHaveLength(6);
  expect(rows[0]).toContain("Monday");
  expect(rows[1]).toContain("11:30 AM-2:30 PM · Available");
  expect(rows[1]).toContain("CS1101");
  expect(rows[1]).toContain("1:00 PM-2:30 PM");
  expect(rows[2]).toContain("7:00 AM-8:00 AM (preferred)");
  expect(rows[5]).toContain("7:00 AM-8:00 PM");                                 // Saturday: not in their availability, still possible
  expect(rows[1]).toContain("7:00 AM-11:30 AM");                                // Tuesday: outside the window, still possible
  act(() => root.unmount());
  el.remove();
});

test("the Dean assigns the subject to a free time (preferred, or overriding it)", async () => {
  API.get.mockResolvedValue({ data: { ...ANG, availability: [{ day: "Tue", start: "11:30", end: "14:30", preference: "preferred" }], teaching: [] } });
  const onAssign = jest.fn();
  const el = document.createElement("div");
  document.body.appendChild(el);
  const root = createRoot(el);
  await act(async () => {
    root.render(<FacultyTimePopover teachers={[{ id: 7, label: "Ang, V." }]} semester="1st Sem" subjectCode="CS1101" needMinutes={120}
      onAssign={onAssign} onClose={() => {}} />);
  });
  const chip = [...el.querySelectorAll("button")].find((b) => b.textContent.includes("11:30 AM-2:30 PM"));
  await act(async () => { chip.click(); });
  const box = el.querySelector('[aria-label="Assign this time"]');
  expect(box.textContent).toContain("Tuesday");
  expect(box.textContent).toContain("to 1:30 PM");
  const sel = box.querySelector("select");
  expect([...sel.options].map((o) => o.textContent)).toEqual(["11:30 AM", "12:00 PM", "12:30 PM"]);   // must end by 2:30 PM
  await act(async () => { [...box.querySelectorAll("button")].find((b) => b.textContent === "Assign to this time").click(); });
  expect(onAssign).toHaveBeenCalledWith(7, "Tue", "11:30", "13:30");
  const other = [...el.querySelectorAll("button")].find((b) => b.textContent === "7:00 AM-8:00 PM");     // Saturday: outside their time
  await act(async () => { other.click(); });
  expect(el.querySelector('[aria-label="Assign this time"]').textContent).toContain("overriding their preference");
  act(() => root.unmount());
  el.remove();
});

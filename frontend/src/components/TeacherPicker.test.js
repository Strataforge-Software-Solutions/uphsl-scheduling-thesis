/* The shared searchable teacher list (Edit dialog, Generate Professor column, overload picker), rendered in jsdom. */
import React from "react";
import { createRoot } from "react-dom/client";
import { act } from "react-dom/test-utils";
import TeacherPicker, { filterOptions, normalize } from "./TeacherPicker";

global.IS_REACT_ACT_ENVIRONMENT = true;

const OPTIONS = [
  { id: 7, label: "Santos, J. - 11 of 24 hrs", group: "Other qualified", search: "Juan Santos F1007 UPHM-F1007" },
  { id: 8, label: "Peña, M. - 6 of 24 hrs", group: "Suggested", search: "María Peña F1008 UPHM-F1008" },
  { id: 9, label: "Mazo, J. - 7 of 12 hrs", group: "Suggested", search: "Joseph Albert Mazo P1063 UPHM-P1063" },
];

test("search: by name, by employee ID / username, ignoring case, accents and extra spaces", () => {
  expect(normalize("  María   PEÑA ")).toBe("maria pena");
  expect(filterOptions(OPTIONS, "pena").map((o) => o.id)).toEqual([8]);
  expect(filterOptions(OPTIONS, "  MARÍA   peña ").map((o) => o.id)).toEqual([8]);
  expect(filterOptions(OPTIONS, "p1063").map((o) => o.id)).toEqual([9]);
  expect(filterOptions(OPTIONS, "uphm-f1007").map((o) => o.id)).toEqual([7]);
  expect(filterOptions(OPTIONS, "j.").map((o) => o.id)).toEqual([7, 9]);
  expect(filterOptions(OPTIONS, "nobody")).toEqual([]);
});

let container, root, picked;
async function mount(props = {}) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  picked = [];
  await act(async () => {
    root.render(<TeacherPicker ariaLabel="Teacher" options={OPTIONS} value="" emptyLabel="Automatic" onChange={(v) => picked.push(v)} {...props} />);
  });
}
afterEach(() => { if (root) { act(() => root.unmount()); container.remove(); root = null; } });
const key = async (el, k) => { await act(async () => { el.dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true })); }); };
const type = async (el, v) => {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
  await act(async () => { setter.call(el, v); el.dispatchEvent(new Event("input", { bubbles: true })); });
};

test("Suggested group first; typing filters; keyboard picks; Esc closes; 'No teacher found'", async () => {
  await mount();
  const btn = container.querySelector('button[aria-label="Teacher"]');
  await key(btn, "ArrowDown");                                          // opens from the keyboard
  const groups = [...document.querySelectorAll('[role="group"]')].map((g) => g.getAttribute("aria-label"));
  expect(groups).toEqual(["Suggested", "Other qualified"]);
  const box = document.querySelector('[role="combobox"]');
  expect(document.activeElement).toBe(box);
  await type(box, "santos");
  expect([...document.querySelectorAll('[role="option"]')].map((o) => o.textContent)).toEqual(["Santos, J. - 11 of 24 hrs"]);
  await key(box, "Enter");
  expect(picked).toEqual(["7"]);
  expect(document.querySelector('[role="listbox"]')).toBeNull();      // closed after picking
  await act(async () => { btn.click(); });
  const box2 = document.querySelector('[role="combobox"]');
  await key(box2, "ArrowDown");                                         // Automatic -> first Suggested (Peña)
  await key(box2, "Enter");
  expect(picked).toEqual(["7", "8"]);
  await act(async () => { btn.click(); });
  const box3 = document.querySelector('[role="combobox"]');
  await type(box3, "zzz");
  expect(document.body.textContent).toContain("No teacher found");
  await key(box3, "Escape");
  expect(document.querySelector('[role="listbox"]')).toBeNull();
  expect(picked).toEqual(["7", "8"]);                                  // Esc picks nothing
});

test("a disabled picker does not open, and a value outside the list shows its label only", async () => {
  await mount({ disabled: true, value: "99", valueLabel: "Old Teacher (current)" });
  const btn = container.querySelector('button[aria-label="Teacher"]');
  expect(btn.disabled).toBe(true);
  expect(btn.textContent).toContain("Old Teacher (current)");
  expect(document.querySelector('[role="listbox"]')).toBeNull();
});

test("the open list floats outside any clipping box (rendered at the page level, not inside the table)", async () => {
  await mount();
  container.style.overflow = "hidden";
  await act(async () => { container.querySelector('button[aria-label="Teacher"]').click(); });
  const list = document.querySelector('[role="listbox"]');
  expect(list).not.toBeNull();
  expect(container.contains(list)).toBe(false);                          // not clipped by the table's scroll box
  expect(list.parentElement.style.position).toBe("fixed");
});

/* ---- keyboard: the grouped list with muted rows (Professor dropdown) and the "Assign anyway?" reason dialog */
const GROUPED = [
  { id: 1, label: "Ang, V. (12/24 hrs)", detail: "Lowest load", group: "Suggested" },
  { id: 2, label: "Mazo, J. (24/24 hrs)", detail: "Full: 24/24 hrs", group: "Qualified", disabled: true },
  { id: 3, label: "Cruz, L. (6/24 hrs)", detail: "Not connected", group: "Other available (not connected to this subject)", notConnected: true },
];

test("keyboard: ArrowDown opens, arrows skip muted rows, Enter picks, Escape closes", async () => {
  await mount({ options: GROUPED, emptyLabel: "-- Professor --" });
  const field = container.querySelector('button[aria-haspopup="listbox"]');
  await act(async () => { field.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true })); });
  const search = document.querySelector('[role="combobox"]');
  expect(search).not.toBeNull();
  expect(document.activeElement).toBe(search);                                    // focus goes to the search box
  const key = async (k) => act(async () => { search.dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true })); });
  await key("ArrowDown");                                                         // "-- Professor --" -> Ang
  await key("ArrowDown");                                                         // Mazo is muted: skipped -> Cruz
  expect(search.getAttribute("aria-activedescendant")).toMatch(/-3$/);
  await key("Enter");
  expect(picked[picked.length - 1]).toBe("3");
  expect(document.querySelector('[role="combobox"]')).toBeNull();                 // closed after picking
  await act(async () => { field.click(); });
  await act(async () => { document.querySelector('[role="combobox"]').dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })); });
  expect(document.querySelector('[role="combobox"]')).toBeNull();
  await act(async () => { field.click(); });
  const muted = document.querySelector('[aria-disabled="true"]');
  await act(async () => { muted.click(); });
  expect(picked[picked.length - 1]).toBe("3");                                    // clicking a muted row picks nothing
});

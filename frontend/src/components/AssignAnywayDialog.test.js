/* The "Assign anyway?" confirmation: a reason is required; Enter confirms, Escape cancels, Tab reaches Cancel and Assign. */
import React from "react";
import { createRoot } from "react-dom/client";
import { act } from "react";
import AssignAnywayDialog from "./AssignAnywayDialog";

global.IS_REACT_ACT_ENVIRONMENT = true;
let box, root;
afterEach(() => { act(() => root.unmount()); box.remove(); });

async function mount(props) {
  box = document.createElement("div"); document.body.appendChild(box); root = createRoot(box);
  await act(async () => { root.render(<AssignAnywayDialog person={{ id: 7, full_name: "Lina Cruz", specializations: "Nursing" }}
    subjectCode="CS101" subjectTitle="Programming 1" {...props} />); });
}
const typeInto = async (el, v) => act(async () => {
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(el, v);
  el.dispatchEvent(new Event("input", { bubbles: true }));
});
const press = async (el, k) => act(async () => { el.dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true })); });

test("names the person, subject and specialization; Enter needs a reason, then confirms", async () => {
  const onConfirm = jest.fn(), onCancel = jest.fn();
  await mount({ onConfirm, onCancel });
  expect(box.textContent).toContain("Lina Cruz is not connected to CS101 Programming 1 (specialization: Nursing). Assign anyway?");
  const input = box.querySelector("input");
  expect(document.activeElement).toBe(input);                                   // focus starts in the reason field
  await press(input, "Enter");
  expect(onConfirm).not.toHaveBeenCalled();
  expect(box.textContent).toContain("Write a short reason.");
  await typeInto(input, "no qualified faculty free");
  await press(input, "Enter");
  expect(onConfirm).toHaveBeenCalledWith("no qualified faculty free");
  const buttons = [...box.querySelectorAll("button")].map((b) => b.textContent);
  expect(buttons).toEqual(["Cancel", "Assign"]);                                 // the Tab order after the field
});

test("Escape cancels", async () => {
  const onCancel = jest.fn();
  await mount({ onConfirm: jest.fn(), onCancel });
  await press(box.querySelector("input"), "Escape");
  expect(onCancel).toHaveBeenCalled();
});

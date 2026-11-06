/* Print / Preview: choose one year level or "All year levels" before the PDF is requested. */
import React from "react";
import { createRoot } from "react-dom/client";
import { act } from "react-dom/test-utils";
import PrintPreviewButton, { printYears } from "./PrintPreviewButton";
import API from "../services/api";

jest.mock("../services/api", () => ({ __esModule: true, default: { get: jest.fn() } }));
global.IS_REACT_ACT_ENVIRONMENT = true;

test("offers 1st-4th Year (and a 5th only when it has classes)", () => {
  expect(printYears([{ year_level: "2nd Year" }])).toEqual(["1st Year", "2nd Year", "3rd Year", "4th Year"]);
  expect(printYears([{ year_level: "5th Year" }])).toEqual(["1st Year", "2nd Year", "3rd Year", "4th Year", "5th Year"]);
});

test("one year level or all year levels is sent with the other filters", async () => {
  API.get.mockResolvedValue({ data: new Blob(["%PDF"]) });
  window.open = jest.fn();
  window.URL.createObjectURL = jest.fn(() => "blob:x");
  window.URL.revokeObjectURL = jest.fn();
  const el = document.createElement("div");
  document.body.appendChild(el);
  const root = createRoot(el);
  await act(async () => {
    root.render(<PrintPreviewButton params={{ program_id: 5, semester: "1st Sem" }} yearChoices={printYears([])} defaultYear="" />);
  });
  const open = () => act(async () => { el.querySelector("button").click(); });
  const confirm = () => act(async () => { [...el.querySelectorAll('[role="dialog"] button')].find((b) => b.textContent === "Print / Preview").click(); });
  await open();
  const labels = [...el.querySelectorAll('[role="dialog"] label')].map((l) => l.textContent);
  expect(labels[4]).toContain("All year levels (1st - 4th)");
  await act(async () => { el.querySelectorAll('[role="dialog"] input')[1].click(); });     // 2nd Year
  await confirm();
  expect(API.get).toHaveBeenLastCalledWith("/engine/export-pdf/", expect.objectContaining({
    params: expect.objectContaining({ program_id: 5, semester: "1st Sem", year_level: "2nd Year" }) }));
  await open();
  await confirm();                                                                    // default: all year levels
  expect(API.get.mock.calls[1][1].params.year_level).toBeUndefined();
  act(() => root.unmount());
  el.remove();
});

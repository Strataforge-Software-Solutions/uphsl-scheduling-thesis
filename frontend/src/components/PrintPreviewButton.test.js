/* Print / Preview: choose one year level or "All year levels" before the PDF is requested. */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import PrintPreviewButton, { printYears } from "./PrintPreviewButton";
import API from "../services/api";

jest.mock("../services/api", () => ({ __esModule: true, default: { get: jest.fn() } }));
global.IS_REACT_ACT_ENVIRONMENT = true;

test("offers 1st-4th Year (and a 5th only when it has classes)", () => {
  expect(printYears([{ year_level: "2nd Year" }])).toEqual(["1st Year", "2nd Year", "3rd Year", "4th Year"]);
  expect(printYears([{ year_level: "5th Year" }])).toEqual(["1st Year", "2nd Year", "3rd Year", "4th Year", "5th Year"]);
});

test("one year level or all year levels is sent with the other filters", async () => {
  let resolvePdf;
  API.get.mockReturnValue(new Promise((resolve) => { resolvePdf = resolve; }));
  const previewWindow = { closed: false, document: { body: { textContent: "" }, title: "" }, location: {} };
  window.open = jest.fn(() => previewWindow);
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
  expect(previewWindow.document.body.textContent).toBe("Preparing your schedule PDF…");
  expect(previewWindow.location.href).toBeUndefined();
  expect(API.get).toHaveBeenLastCalledWith("/engine/export-pdf/", expect.objectContaining({
    params: expect.objectContaining({ program_id: 5, semester: "1st Sem", year_level: "2nd Year" }) }));
  expect(window.open.mock.invocationCallOrder[0]).toBeLessThan(API.get.mock.invocationCallOrder[0]);
  await act(async () => { resolvePdf({ data: new Blob(["%PDF"]) }); });
  expect(previewWindow.location.href).toBe("blob:x");
  API.get.mockResolvedValue({ data: new Blob(["%PDF"]) });
  await open();
  await confirm();                                                                    // default: all year levels
  expect(API.get.mock.calls[1][1].params.year_level).toBeUndefined();
  act(() => root.unmount());
  el.remove();
});

test("a blocked preview tab leaves a direct PDF download action", async () => {
  API.get.mockResolvedValue({ data: new Blob(["%PDF"]) });
  window.open = jest.fn(() => null);
  window.URL.createObjectURL = jest.fn(() => "blob:download");
  window.URL.revokeObjectURL = jest.fn();
  const click = jest.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  const el = document.createElement("div");
  document.body.appendChild(el);
  const root = createRoot(el);
  await act(async () => root.render(<PrintPreviewButton params={{}} yearChoices={[]} />));
  await act(async () => { el.querySelector("button").click(); });

  const link = el.querySelector('a[download="class_schedule.pdf"]');
  expect(link).not.toBeNull();
  expect(link.href).toBe("blob:download");
  expect(link.textContent).toBe("Download PDF");
  await act(async () => link.click());
  expect(click).toHaveBeenCalled();

  act(() => root.unmount());
  el.remove();
  click.mockRestore();
});

test("a conflict closes the reserved tab and still shows the conflict dialog", async () => {
  const previewWindow = { closed: false, document: { body: { textContent: "" }, title: "" }, close: jest.fn(function close() { this.closed = true; }) };
  window.open = jest.fn(() => previewWindow);
  API.get.mockRejectedValue({ response: { status: 409, data: { text: async () => JSON.stringify({ total: 1, conflicts: [], detail: "Conflict" }) } } });
  const el = document.createElement("div");
  document.body.appendChild(el);
  const root = createRoot(el);
  await act(async () => root.render(<PrintPreviewButton params={{}} yearChoices={[]} />));
  await act(async () => { el.querySelector("button").click(); });

  expect(previewWindow.close).toHaveBeenCalled();
  expect(el.querySelector('[role="alertdialog"]').textContent).toContain("Not printed: 1 conflict");
  act(() => root.unmount());
  el.remove();
});

test("a PDF error closes the reserved tab", async () => {
  const previewWindow = { closed: false, document: { body: { textContent: "" }, title: "" }, close: jest.fn(function close() { this.closed = true; }) };
  window.open = jest.fn(() => previewWindow);
  API.get.mockRejectedValue({ response: { status: 500, data: { text: async () => JSON.stringify({ detail: "PDF failed" }) } } });
  const alert = jest.spyOn(window, "alert").mockImplementation(() => {});
  const el = document.createElement("div");
  document.body.appendChild(el);
  const root = createRoot(el);
  await act(async () => root.render(<PrintPreviewButton params={{}} yearChoices={[]} />));
  await act(async () => { el.querySelector("button").click(); });

  expect(previewWindow.close).toHaveBeenCalled();
  expect(alert).toHaveBeenCalledWith("PDF failed");
  act(() => root.unmount());
  el.remove();
  alert.mockRestore();
});

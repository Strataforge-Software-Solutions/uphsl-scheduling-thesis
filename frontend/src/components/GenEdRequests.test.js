/* Gen Ed move requests: the Dean picks a time and sends; the Registrar approves (the server re-checks and moves only that class). */
import React from "react";
import { createRoot } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { RequestMoveModal, GenEdRequestsPanel } from "./GenEdRequests";
import API from "../services/api";

jest.mock("../services/api", () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn() } }));
global.IS_REACT_ACT_ENVIRONMENT = true;

let el, root;
const mount = async (node) => { el = document.createElement("div"); document.body.appendChild(el); root = createRoot(el); await act(async () => { root.render(node); }); };
afterEach(() => { act(() => root.unmount()); el.remove(); jest.resetAllMocks(); });

test("the Dean picks a free time and sends the request", async () => {
  API.post.mockImplementation((url) => (url === "/engine/gened-requests/options/"
    ? Promise.resolve({ data: { class: { when: "Mon 7:00 AM–10:00 AM", room: "M-301", teacher: "Ramos, B." }, options: [
      { key: "k1", label: "Wed 1:00 PM – 4:00 PM", room: "M-301", teacher: "Ramos, B." }], reason: "", status: "draft", note: "" } })
    : Promise.resolve({ data: { subject: "GE401", current: "Mon 7:00 AM–10:00 AM", target: "Wed 1:00 PM – 4:00 PM" } })));
  const onDone = jest.fn();
  await mount(<RequestMoveModal group={{ ids: [1, 2, 3], subject_code: "GE401", subject_title: "FCL 1", section_name: "I1" }} onClose={() => {}} onDone={onDone} />);
  const send = [...el.querySelectorAll("button")].find((b) => b.textContent === "Send request");
  expect(send.disabled).toBe(true);                                       // a time must be chosen first
  await act(async () => { el.querySelector('input[type="radio"]').click(); });
  await act(async () => { send.click(); });
  expect(API.post).toHaveBeenLastCalledWith("/engine/gened-requests/", { ids: [1, 2, 3], key: "k1", reason: "" });
  expect(el.textContent).toContain("Request sent.");
  expect(onDone).toHaveBeenCalled();
});

test("the Registrar sees the pending request and approves it", async () => {
  API.get.mockResolvedValue({ data: { pending: 1, items: [{ id: 9, status: "pending", status_label: "Pending", subject: "GE401 — FCL 1", section: "BS Nursing I1",
    current: "Mon 7:00 AM–10:00 AM", target: "Wed 1:00 PM – 4:00 PM", requested_by: "Darwin D. Aznar", reason: "free Monday", decision_note: "" }] } });
  API.post.mockResolvedValue({ data: { status: "approved", status_label: "Approved", summary: "moved" } });
  const onChanged = jest.fn();
  await mount(<GenEdRequestsPanel role="registrar" onChanged={onChanged} />);
  expect(el.textContent).toContain("1 pending");
  await act(async () => { [...el.querySelectorAll("button")].find((b) => b.textContent === "Approve & move").click(); });
  expect(API.post).toHaveBeenCalledWith("/engine/gened-requests/9/approve/", { note: "" });
  expect(onChanged).toHaveBeenCalled();
});

/* Admin audit logs: filters are sent to the server; Details shows before / after; there is no edit or delete control. */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import API from "../services/api";
import AuditLogs from "./AuditLogs";

jest.mock("../services/api", () => ({ __esModule: true, default: { get: jest.fn() } }));
global.IS_REACT_ACT_ENVIRONMENT = true;

const DATA = { count: 1, page: 1, pages: 1, users: [{ id: 4, label: "Dean T" }], actions: [{ value: "update", label: "Update" }, { value: "login", label: "Login" }],
  results: [{ id: 9, timestamp: "2026-11-06T01:30:00Z", user_id: 4, user: "Dean T", action: "update", entity: "schedule", entity_id: "12",
    summary: "CS101 CS1 Mon 07:00-08:00", old_values: { teacher: { id: 1, name: "Ana Cruz" } }, new_values: { teacher: { id: 2, name: "Ben Lim" } }, ip_address: "10.0.0.7" }] };
let box, root;
beforeEach(() => { API.get.mockResolvedValue({ data: DATA }); });
afterEach(() => { act(() => root.unmount()); box.remove(); });
const flush = async () => { for (let i = 0; i < 4; i += 1) await act(async () => { await new Promise((r) => setTimeout(r, 0)); }); };

test("lists who / what / when / IP, filters by user and action, shows before and after, offers no edit or delete", async () => {
  box = document.createElement("div"); document.body.appendChild(box); root = createRoot(box);
  await act(async () => { root.render(<AuditLogs />); });
  await flush();
  expect(box.textContent).toContain("Dean T");
  expect(box.textContent).toContain("10.0.0.7");
  expect(box.textContent).toContain("schedule #12");
  const [userSel, actionSel] = box.querySelectorAll("select");
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value").set.call(userSel, "4");
    userSel.dispatchEvent(new Event("change", { bubbles: true }));
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value").set.call(actionSel, "update");
    actionSel.dispatchEvent(new Event("change", { bubbles: true }));
  });
  await act(async () => { [...box.querySelectorAll("button")].find((b) => b.textContent === "Apply").click(); });
  await flush();
  expect(API.get).toHaveBeenLastCalledWith("/audit/logs/", { params: { user: "4", action: "update", page: 1 } });
  await act(async () => { [...box.querySelectorAll("button")].find((b) => b.textContent === "Details").click(); });
  expect(box.textContent).toContain("Ana Cruz");
  expect(box.textContent).toContain("Ben Lim");
  expect([...box.querySelectorAll("button")].map((b) => b.textContent)).not.toEqual(expect.arrayContaining(["Edit", "Delete"]));
});

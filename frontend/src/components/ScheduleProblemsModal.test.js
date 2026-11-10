import React, { act } from "react";
import { createRoot } from "react-dom/client";
import ScheduleProblemsModal from "./ScheduleProblemsModal";
import API from "../services/api";

jest.mock("../services/api", () => ({
  __esModule: true,
  default: { post: jest.fn() },
  getCurrentUser: jest.fn(() => ({ role: "registrar" })),
}));
global.IS_REACT_ACT_ENVIRONMENT = true;

const slot = (key, start, end, ids) => ({
  key, day: "Mon", days: ["Mon"], start, end,
  label: `Mon ${start} – ${end}`, teacher_id: 7, teacher: "Faculty Member", room_id: 5, room: "M-304", slot_ids: ids,
});
const baseData = {
  mode: "move", split_allowed: true,
  class: { code: "GE405", title: "Filipino Christian Living 5", year_level: "3rd Year", section: "BS Nursing N3", when: "Mon 7:00 AM–10:00 AM" },
  room: { name: "M-304", note: "", kept: true },
  options: [{ key: "regular", day: "Tue", days: ["Tue"], start: "07:00", end: "10:00", label: "Tue 7:00 AM – 10:00 AM", teacher_id: 7, room_id: 5, room: "M-304" }],
  outside_options: [], room_options: [], reason: "",
};
const splitData = {
  ...baseData, hours: 1.5, half_hour_slots_available: true,
  options: [slot("first", "07:00", "08:30", [1, 2, 3]), slot("second", "09:00", "10:30", [4, 5, 6])],
};

let container; let root;
const flush = async () => { for (let i = 0; i < 5; i += 1) await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); }); };
beforeEach(() => {
  API.post.mockImplementation((url, body) => {
    if (url.endsWith("/apply/")) return Promise.resolve({ data: { summary: "GE405 updated" } });
    return Promise.resolve({ data: body?.split_session ? splitData : baseData });
  });
  container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container);
});
afterEach(() => { act(() => root.unmount()); container.remove(); jest.clearAllMocks(); });

test("eligible class can select two independent sessions before applying", async () => {
  await act(async () => root.render(<ScheduleProblemsModal clashes={[]} unplaced={[]} startWith={{ request: { ids: [11, 12] } }} onClose={() => {}} />));
  await flush();
  const splitButton = [...container.querySelectorAll("button")].find((button) => button.textContent.includes("Two 1.5-hour sessions"));
  expect(splitButton).toBeTruthy();
  await act(async () => splitButton.click());
  await flush();
  const first = container.querySelectorAll('input[name="session-0"]');
  await act(async () => first[0].click());
  const second = container.querySelectorAll('input[name="session-1"]');
  await act(async () => second[0].click());
  const confirm = [...container.querySelectorAll("button")].find((button) => button.textContent === "Apply / Confirm");
  expect(confirm.disabled).toBe(false);
  await act(async () => confirm.click());
  await flush();
  const applyCall = API.post.mock.calls.find(([url]) => url.endsWith("/apply/"));
  expect(applyCall[1].split_session).toBe(true);
  expect(applyCall[1].session_keys).toEqual(["first", "second"]);
});

test("second session list excludes overlap and different resource assignments", async () => {
  const overlap = slot("overlap", "08:00", "09:30", [2, 3, 4]);
  const otherResource = { ...slot("other-resource", "11:00", "12:30", [7, 8, 9]), teacher_id: 8 };
  API.post.mockImplementation((url, body) => Promise.resolve({ data: body?.split_session ? { ...splitData, options: [...splitData.options, overlap, otherResource] } : baseData }));
  await act(async () => root.render(<ScheduleProblemsModal clashes={[]} unplaced={[]} startWith={{ request: { ids: [11, 12] } }} onClose={() => {}} />));
  await flush();
  const splitButton = [...container.querySelectorAll("button")].find((button) => button.textContent.includes("Two 1.5-hour sessions"));
  await act(async () => splitButton.click());
  await flush();
  await act(async () => container.querySelector('input[name="session-0"]').click());
  const secondLabels = [...container.querySelectorAll('input[name="session-1"]')].map((input) => input.parentElement.textContent);
  expect(secondLabels).toHaveLength(1);
  expect(secondLabels[0]).toContain("09:00");
});

import { notificationTarget, jumpTo, takeJump, onJump } from "./jump";

test("Gen Ed move request notifications point to the requests list", () => {
  expect(notificationTarget({ message: "Dean A asks to move GE101 (BSCS 1A) from Mon 7:00 AM to Tue 9:00 AM. See Schedules > Gen Ed move requests." })).toBe("gened-requests");
  expect(notificationTarget({ message: "Your request to move GE101 to Tue 9:00 AM was approved: the class was moved." })).toBe("gened-requests");
  expect(notificationTarget({ message: "Your schedule was published." })).toBe("");
});

test("a jump is announced once and taken once", () => {
  const seen = [];
  const off = onJump((t) => seen.push(t));
  jumpTo("gened-requests");
  off();
  expect(seen).toEqual(["gened-requests"]);
  expect(takeJump("other")).toBe(false);
  expect(takeJump("gened-requests")).toBe(true);
  expect(takeJump("gened-requests")).toBe(false);
});

import { needMinutes, timeWindowProblem } from "./timeWindow";

test("uses the server's need_minutes when present (a Nursing pair lecture needs 1.5 h, not 3 h)", () => {
  expect(needMinutes({ lec_units: 3, lab_units: 0, need_minutes: 90 })).toBe(90);
  expect(timeWindowProblem({ lec_units: 3, lab_units: 0, need_minutes: 90 }, "07:00", "08:30")).toBe("");
});

test("a range shorter than the subject needs is named with both lengths", () => {
  expect(timeWindowProblem({ lec_units: 0, lab_units: 1, need_minutes: 180 }, "07:00", "09:00"))
    .toBe("Needs 3 hrs in one block; this range is 2 hrs.");
  expect(timeWindowProblem({ lec_units: 2, lab_units: 0, need_minutes: 120 }, "13:00", "14:30"))
    .toBe("Needs 2 hrs in one block; this range is 1.5 hrs.");
});

test("an exact fit, an open side and an empty row are fine", () => {
  const lab = { lec_units: 0, lab_units: 1, need_minutes: 180 };
  expect(timeWindowProblem(lab, "07:00", "10:00")).toBe("");
  expect(timeWindowProblem(lab, "07:00", "")).toBe("");
  expect(timeWindowProblem(lab, "", "")).toBe("");
});

test("End before Start is reported", () => {
  expect(timeWindowProblem({ lec_units: 1, lab_units: 0, need_minutes: 60 }, "15:00", "09:00")).toMatch(/later than the Start/);
});

test("falls back to the old rule when the server does not send need_minutes", () => {
  expect(needMinutes({ lec_units: 0, lab_units: 1 })).toBe(180);
  expect(needMinutes({ lec_units: 2, lab_units: 0 })).toBe(120);
});

describe("Start / End follow each other (same rule as the server: End - Start >= need_minutes)", () => {
  const { startOptions, endOptions, pickStart, pickEnd, needHint, professorFits, freeText } = require("./timeWindow");
  const lec2 = { lec_units: 2, lab_units: 0, need_minutes: 120 };
  const lab = { lec_units: 0, lab_units: 1, need_minutes: 180 };

  test("End offers only Start + need and later, every 30 minutes, up to 8:00 PM", () => {
    const e = endOptions(lec2, "10:30");
    expect(e[0]).toBe("12:30");
    expect(e).not.toContain("12:00");
    expect(e[e.length - 1]).toBe("20:00");
    expect(e.every((t, i) => i === 0 || (Number(t.slice(0, 2)) * 60 + Number(t.slice(3))) - (Number(e[i - 1].slice(0, 2)) * 60 + Number(e[i - 1].slice(3))) === 30)).toBe(true);
    expect(endOptions(lab, "")[0]).toBe("10:00");                        // no Start: 7:00 AM + 3 h
  });

  test("Start offers only times at least need before the End", () => {
    const st = startOptions(lec2, "13:00");
    expect(st[st.length - 1]).toBe("11:00");
    expect(st).not.toContain("11:30");
    expect(startOptions(lab, "")[startOptions(lab, "").length - 1]).toBe("17:00");   // must still end by 8:00 PM
  });

  test("picking a Start fills an 'Any time' End with the earliest end, and resets a too-short End with a notice", () => {
    expect(pickStart(lec2, "10:30", "")).toMatchObject({ start: "10:30", end: "12:30" });
    const r = pickStart(lec2, "11:30", "13:00");
    expect(r).toMatchObject({ start: "11:30", end: "13:30" });
    expect(r.notice).toMatch(/End moved to 1:30 PM/);
    expect(pickStart(lec2, "10:00", "13:00")).toEqual({ start: "10:00", end: "13:00", notice: "" });   // still valid: kept
    expect(pickStart(lec2, "", "13:00")).toEqual({ start: "", end: "13:00", notice: "" });              // Any time stays allowed
  });

  test("a too-short range is never left selected", () => {
    expect(pickEnd(lab, "09:00", "11:00").start).toBe("");
    expect(pickEnd(lab, "09:00", "12:00")).toEqual({ start: "09:00", end: "12:00", notice: "" });
  });

  test("hint text", () => {
    expect(needHint(lec2, "10:30")).toBe("Needs 2 hrs - earliest end 12:30 PM");
    expect(needHint(lab, "")).toBe("Needs 3 hrs in one block");
  });

  test("professor's free windows and 'outside professor's time' (advice only)", () => {
    const free = { Mon: [[600, 780]], Sat: [[420, 990]] };
    expect(freeText(free)).toBe("Mon 10:00 AM-1:00 PM, Sat 7:00 AM-4:30 PM");
    expect(professorFits(free, 120, 630, 780)).toBe(true);                // Mon 10:30-12:30 is inside his time
    expect(professorFits({ Mon: [[600, 720]] }, 120, 630, 780)).toBe(false);
  });

});

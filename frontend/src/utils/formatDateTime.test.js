import { formatTime, formatTimeRange, formatDate, formatDateTime, setFormatPrefs } from "./formatDateTime";
import { formatSchedule } from "./formatSchedule";

afterEach(() => setFormatPrefs({ time_format: "12h", date_format: "mdy_short" }));

test("12-hour is the default and matches the old screens", () => {
  expect(formatTime("07:00:00")).toBe("7:00 AM");
  expect(formatTime("13:30")).toBe("1:30 PM");
  expect(formatTime(12 * 60)).toBe("12:00 PM");
  expect(formatTime(0)).toBe("12:00 AM");
  expect(formatTime("14:00", { compact: true })).toBe("2:00PM");
  expect(formatSchedule("Mon", "08:00:00", "09:00:00")).toBe("M 8:00AM-9:00AM");
});

test("24-hour", () => {
  setFormatPrefs({ time_format: "24h", date_format: "mdy_short" });
  expect(formatTime("07:00:00")).toBe("07:00");
  expect(formatTime(13 * 60 + 5)).toBe("13:05");
  expect(formatTimeRange("07:00", "08:30", "-")).toBe("07:00-08:30");
  expect(formatSchedule("Sat", "10:30:00", "12:30:00")).toBe("SAT 10:30-12:30");
});

test("the three date formats, a weekday, and Manila time for moments", () => {
  expect(formatDate("2026-11-06")).toBe("Nov 6, 2026");
  expect(formatDate("2026-11-06", { weekday: "long" })).toBe("Friday, Nov 6, 2026");
  setFormatPrefs({ time_format: "12h", date_format: "dmy" });
  expect(formatDate("2026-11-06")).toBe("06/11/2026");
  setFormatPrefs({ time_format: "24h", date_format: "iso" });
  expect(formatDate("2026-11-06")).toBe("2026-11-06");
  expect(formatDateTime("2026-11-05T17:30:00Z")).toBe("2026-11-06 01:30");     // UTC+8
  expect(formatDate("")).toBe("");
  expect(formatTime(null)).toBe("");
});

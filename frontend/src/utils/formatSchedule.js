// Matches UPHSL's own schedule display format, e.g. "T 11:30AM-2:30PM", "SAT 10:30AM-12:30PM".

const DAY_ABBREV = {
  Mon: "M", Tue: "T", Wed: "W", Thu: "TH", Fri: "F", Sat: "SAT", Sun: "SUN",
};

/**
 * "14:00:00" or "14:00" -> "2:00PM"
 */
function to12Hour(timeStr) {
  if (!timeStr) return "";
  const [hStr, mStr] = timeStr.split(":");
  let h = parseInt(hStr, 10);
  const m = mStr || "00";
  const period = h >= 12 ? "PM" : "AM";
  h = h % 12;
  if (h === 0) h = 12;
  return `${h}:${m}${period}`;
}

/**
 * formatSchedule("Mon", "08:00:00", "09:00:00") -> "M 8:00AM-9:00AM"
 * formatSchedule("Sat", "10:30:00", "12:30:00") -> "SAT 10:30AM-12:30PM"
 */
export function formatSchedule(day, startTime, endTime) {
  if (!day || !startTime || !endTime) return "";
  const dayCode = DAY_ABBREV[day] || day;
  return `${dayCode} ${to12Hour(startTime)}-${to12Hour(endTime)}`;
}

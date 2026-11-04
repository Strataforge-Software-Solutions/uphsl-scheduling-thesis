// Groups schedule rows that share the same subject+section+room+teacher+day into
// ONE display row spanning the earliest start to the latest end time on that day
// -- matches how UPHSL's own system displays a subject's periods (one line per
// day, not one line per period). Keeps the original row ids so Edit/Remove can
// still act on every underlying period.

function toMinutes(t) {
  if (!t) return 0;
  const [h, m] = t.split(":").map(Number);
  return h * 60 + m;
}

// draft < approved < published -- if a merged row's underlying periods are at
// different stages (shouldn't normally happen since approve_bulk moves a
// whole scope together, but possible after a manual edit), show the EARLIEST
// stage so the Dean/Registrar notices it isn't fully approved/published yet.
const STATUS_RANK = { draft: 0, approved: 1, published: 2 };

export function mergeSchedulesByDay(schedules) {
  // Bucket by identity (subject/section/room/teacher/day) first, ignoring time.
  const buckets = {};
  for (const s of schedules) {
    const key = [s.subject_code, s.section_name, s.room_name, s.teacher_name, s.timeslot_day].join("|");
    (buckets[key] = buckets[key] || []).push(s);
  }

  // Within each bucket, merge only CONTIGUOUS (or overlapping) periods --
  // i.e. the next period's start is at or before the current chain's end.
  // Previously this spanned earliest-start..latest-end across the WHOLE
  // bucket regardless of gaps, so two unrelated meetings of the same
  // subject/section/room/teacher at different times of day (e.g. 7-10AM and
  // 3-5PM) got silently merged into one displayed "7AM-5PM" block, hiding
  // the real gap and routing Edit/Remove across both periods at once.
  const groups = [];
  for (const key of Object.keys(buckets)) {
    const sorted = [...buckets[key]].sort((a, b) => toMinutes(a.timeslot_start) - toMinutes(b.timeslot_start));
    let current = null;
    let chainIndex = 0;

    for (const s of sorted) {
      if (current && toMinutes(s.timeslot_start) <= toMinutes(current.end)) {
        current.ids.push(s.id);
        if (s.is_manual_override) current.is_manual_override = true;
        if (s.status && STATUS_RANK[s.status] < STATUS_RANK[current.status]) current.status = s.status;
        if (toMinutes(s.timeslot_end) > toMinutes(current.end)) current.end = s.timeslot_end;
      } else {
        chainIndex += 1;
        current = {
          key: chainIndex === 1 ? key : `${key}#${chainIndex}`,
          ids: [s.id],
          subject: s.subject,
          subject_code: s.subject_code,
          subject_title: s.subject_title,
          subject_classification: s.subject_classification,
          subject_field: s.subject_field,
          subject_field_name: s.subject_field_name,
          merged_with: s.merged_with || [],
          merged_students: s.merged_students,
          section_name: s.section_name,
          section: s.section,
          program_name: s.program_name,
          department: s.department,
          room_name: s.room_name,
          room: s.room,
          teacher_name: s.teacher_name,
          teacher: s.teacher,
          timeslot_day: s.timeslot_day,
          start: s.timeslot_start,
          end: s.timeslot_end,
          is_manual_override: !!s.is_manual_override,
          status: s.status || "draft",
        };
        groups.push(current);
      }
    }
  }

  return groups;
}

const DAY_ORDER = { mon: 0, tue: 1, wed: 2, thu: 3, fri: 4, sat: 5, sun: 6 };

// Puts merged rows in real weekly order (Mon -> Sun, earliest time first
// within a day) instead of whatever order the backend happened to return
// them in / the bucket grouping left them in.
export function sortByDayTime(groups) {
  const dayRank = (day) => DAY_ORDER[(day || "").slice(0, 3).toLowerCase()] ?? 7;
  return [...groups].sort((a, b) => {
    const dayDiff = dayRank(a.timeslot_day) - dayRank(b.timeslot_day);
    if (dayDiff !== 0) return dayDiff;
    return toMinutes(a.start) - toMinutes(b.start);
  });
}

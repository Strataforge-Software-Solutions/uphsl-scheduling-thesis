/* The server's three Professor groups (engine/faculty_groups.py) -> options for TeacherPicker. The server decides who is qualified,
   free and within the limit; this only turns the groups into list rows. Every person is in one group only. */
export const GROUP_SUGGESTED = "Suggested";
export const GROUP_QUALIFIED = "Qualified";
export const GROUP_OTHER = "Other available (not connected to this subject)";

const hrs = (n) => `${Math.round(Number(n || 0) * 100) / 100}`;

export function loadText(o) {
  return o.after_generate_hours != null ? `${o.load_text}, after Generate: ${hrs(o.after_generate_hours)} hrs` : o.load_text;
}

export function groupOptions(groups, { currentId } = {}) {
  if (!groups) return [];
  const row = (o, group) => ({
    id: o.id,
    label: `${o.label} (${loadText(o)})${String(o.id) === String(currentId ?? "") ? " (current)" : ""}`,
    detail: o.tag,
    group,
    disabled: !o.selectable,
    notConnected: !!o.not_connected,
    person: o,
    search: `${o.full_name || ""} ${o.school_id || ""} ${o.username || ""}`,
  });
  return [
    ...(groups.suggested || []).map((o) => row(o, GROUP_SUGGESTED)),
    ...(groups.qualified || []).map((o) => row(o, GROUP_QUALIFIED)),
    ...(groups.other_shown ? (groups.other || []).map((o) => row(o, GROUP_OTHER)) : []),
  ];
}

export function pickerExtras(groups) {
  if (!groups) return {};
  return {
    groupNotes: groups.other_shown ? { [GROUP_OTHER]: groups.approval_text } : {},
    footer: groups.other_shown ? groups.full_text || "" : "",
    emptyText: groups.empty_text || "No faculty in your department is free at this time.",
  };
}

export const OVERRIDE_BADGE = "Assigned by Dean (not connected)";

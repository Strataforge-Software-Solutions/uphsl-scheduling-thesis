import React, { useEffect, useState } from "react";
import { HistoricalHint } from "./Charts";
import RoomSelect from "./RoomSelect";
import TeacherPicker from "./TeacherPicker";
import API from "../services/api";

/* Full day names shown in the UI <-> short codes ("Mon".."Sun") the backend
   TimeSlot/Schedule API actually stores and expects. */
const DAY_CODES = [
  { code: "Mon", label: "Monday" },
  { code: "Tue", label: "Tuesday" },
  { code: "Wed", label: "Wednesday" },
  { code: "Thu", label: "Thursday" },
  { code: "Fri", label: "Friday" },
  { code: "Sat", label: "Saturday" },
  { code: "Sun", label: "Sunday" },
];

const fieldLabel = {
  fontSize: "11.5px", fontWeight: 700, color: "#64748b", textTransform: "uppercase",
  letterSpacing: "0.3px", marginBottom: "6px", display: "block",
};
const readOnlyBox = {
  width: "100%", padding: "10px 12px", borderRadius: "8px", border: "1px solid #e2e8f0",
  background: "#f8fafc", color: "#334155", fontSize: "14px", boxSizing: "border-box",
};

/**
 * Modal dialog for editing a schedule block -- Subject/Section/Program shown
 * for context (read-only; this dialog assigns Teacher/Room/Day/Time, it
 * doesn't move a subject to a different section), Teacher/Room as dropdowns,
 * Day as a Monday-Sunday dropdown, and Start/End as free-typed time inputs.
 *
 * `group` is a merged display row from mergeSchedulesByDay -- group.ids has
 * every underlying Schedule row this edit touches. When group.ids.length > 1
 * (several back-to-back periods merged into one display block), the End time
 * is disabled: moving the block shifts every period by the same offset onto
 * the new day, but each period keeps its own original length -- there's no
 * single "end" to type for the whole block. See saveEdit in the parent.
 */
const fmt12 = (t) => { if (!t) return ""; const [h, m] = String(t).split(":").map(Number); return `${((h + 11) % 12) + 1}:${String(m || 0).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`; };

export default function ScheduleEditModal({
  group, rooms, faculty, editForm, setEditForm, onSave, onCancel, saveError, saving,
  workloadIssue, onOverride, onPickReplacement, roomAssignment, onPickTime,
}) {
  /* The teachers this class may have, from the server (engine.teacher_scope): a Dean's major lists only qualified faculty of the
     Dean's own department(s); a Gen Ed class any qualified teacher. "Suggested" = free at this day / time and within their limit.
     The server checks the same rule again on Save. */
  const [tOpts, setTOpts] = useState(null);
  const idsKey = group ? group.ids.join(",") : "";
  useEffect(() => {
    if (!idsKey) return undefined;
    let live = true;
    setTOpts(null);
    API.get("/engine/teacher-options/", { params: { schedule_ids: idsKey } })
      .then((r) => { if (live) setTOpts(r.data); })
      .catch((e) => { if (live) setTOpts({ error: e.response?.data?.detail || "The teacher list could not be loaded.", teachers: [] }); });
    return () => { live = false; };
  }, [idsKey]);
  if (!group) return null;
  const multiPeriod = group.ids.length > 1;
  const roomRank = (r) => (r.id === roomAssignment?.preferred ? 0 : roomAssignment?.alts?.includes(r.id) ? 1 : 2);

  return (
    <div
      style={{
        position: "fixed", inset: 0, background: "rgba(15, 23, 42, 0.45)",
        display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000,
        padding: "16px",
      }}
      onClick={(e) => { if (e.target === e.currentTarget && !saving) onCancel(); }}
    >
      <div style={{
        background: "white", borderRadius: "14px", width: "100%", maxWidth: "620px",
        boxShadow: "0 20px 60px rgba(0,0,0,0.25)", maxHeight: "90vh", overflowY: "auto",
      }}>
        <div style={{ padding: "22px 26px 18px", display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <h2 style={{ margin: 0, fontSize: "20px", color: "#0f172a" }}>Edit schedule</h2>
            <p style={{ margin: "4px 0 0", fontSize: "13px", color: "#64748b" }}>
              Assign a class block to a section, teacher, and room.
            </p>
          </div>
          <button
            onClick={onCancel}
            disabled={saving}
            aria-label="Close"
            style={{
              background: "none", border: "none", fontSize: "20px", color: "#64748b",
              cursor: "pointer", lineHeight: 1, padding: "4px",
            }}
          >
            ×
          </button>
        </div>

        <div style={{ borderTop: "1px solid #e8edf3" }} />

        <div style={{ padding: "22px 26px" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px 20px" }}>
            <div>
              <label style={fieldLabel}>Subject code</label>
              <div style={readOnlyBox}>{group.subject_code}</div>
            </div>
            <div>
              <label style={fieldLabel}>Subject title</label>
              <div style={readOnlyBox}>{group.subject_title}</div>
            </div>

            <div>
              <label style={fieldLabel}>Section</label>
              <div style={readOnlyBox}>{group.section_name}</div>
            </div>
            <div>
              <label style={fieldLabel}>Program</label>
              <div style={readOnlyBox}>{group.program_name || "—"}</div>
            </div>

            <div>
              <label style={fieldLabel}>Teacher</label>
<TeacherPicker
                ariaLabel="Teacher"
                value={editForm.teacher}
                onChange={(v) => setEditForm({ ...editForm, teacher: v })}
                disabled={saving || !tOpts || !!tOpts.error}
                placeholder={tOpts === null ? "Loading teachers…" : "Choose a teacher"}
                valueLabel={tOpts?.current_outside && String(tOpts.current_outside.id) === String(editForm.teacher) ? `${tOpts.current_outside.full_name} (current)` : ""}
                options={(tOpts?.teachers || []).map((t) => ({
                  id: t.id,
                  label: `${t.label} - ${t.current_hours} of ${t.max_hours} hrs${t.current ? " (current)" : ""}`,
                  detail: t.suggested ? "Free at this time, within their limit" : t.why,
                  group: t.suggested ? "Suggested" : "Other qualified",
                  search: `${t.full_name} ${t.school_id} ${t.username}`,
                }))}
              />
              {tOpts?.error && <div role="alert" style={{ fontSize: 12, color: "#a4231a", marginTop: 4 }}>{tOpts.error}</div>}
              {tOpts && !tOpts.error && tOpts.kind === "major" && (
                <div style={{ fontSize: 11.5, color: "#64748b", marginTop: 4 }}>Qualified faculty of {(tOpts.departments || []).join(", ")} only.</div>
              )}
              {tOpts?.current_outside && (
                <div role="alert" style={{ fontSize: 12, color: "#92400e", marginTop: 4 }}>
                  Currently {tOpts.current_outside.full_name}: {tOpts.current_outside.reason}
                </div>
              )}
            </div>
            <div>
              <label style={fieldLabel}>Room</label>
              <RoomSelect
                allowAuto={false}
                width="100%"
                style={{ padding: "8px 10px" }}
                value={editForm.room}
                onChange={(v) => setEditForm({ ...editForm, room: v })}
                rooms={rooms.filter((r) => !r.department || r.department === group.department || String(r.id) === String(editForm.room))
                  .sort((a, b) => roomRank(a) - roomRank(b))}
                groupBy={(r) => (r.room_type === "lab" ? "Computer laboratories" : "Lecture rooms")}
                isDisabled={(r) => !!roomAssignment?.fixed && r.id !== roomAssignment.preferred && String(r.id) !== String(group.room)}
                suffix={(r) => (r.id === roomAssignment?.preferred ? (roomAssignment.fixed ? "  (fixed)" : "  (preferred)") : roomAssignment?.alts?.includes(r.id) ? "  (alternative)" : "")}
              />
            </div>

            <div style={{ gridColumn: "1 / -1" }}>
              <label style={fieldLabel}>Day and time</label>
              <div style={{ display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap" }}>
                <div style={{ ...readOnlyBox, width: "auto", flex: "1 1 220px" }}>
                  {(DAY_CODES.find((d) => d.code === group.timeslot_day) || {}).label || group.timeslot_day} {fmt12(group.start)} – {fmt12(group.end)}
                </div>
                <button type="button" onClick={() => onPickTime && onPickTime(group)} disabled={saving}
                  style={{ padding: "10px 14px", borderRadius: "8px", border: "1px solid #003366", background: "#ffffff", color: "#003366", fontSize: "13px", fontWeight: 600, cursor: "pointer" }}
                  title="Shows only the days and times that are really free for this class (teacher, room and students checked)">
                  Choose a new day and time…
                </button>
              </div>
              <p style={{ fontSize: "12px", color: "#64748b", margin: "6px 0 0" }}>
                Times are not typed in: you pick from the free days and times (same room first). Teacher and room changes are saved with "Save schedule".
              </p>
            </div>
          </div>

          {multiPeriod && (
            <p style={{ fontSize: "12px", color: "#64748b", margin: "12px 0 0" }}>
              Merges {group.ids.length} periods — a new day and time moves all of them together.
            </p>
          )}

          <HistoricalHint
            day={editForm.day}
            startTime={editForm.start_time}
            endTime={editForm.end_time}
            roomName={rooms.find((r) => String(r.id) === String(editForm.room))?.name}
          />

          {workloadIssue && (
            <div style={{ marginTop: "14px", padding: "12px 14px", background: "#fff4e5", border: "1px solid #f0c987", color: "#7a4b00", borderRadius: "8px", fontSize: "12.5px" }}>
              <strong>⚠ {workloadIssue.detail}</strong>
              {workloadIssue.conflicting_assignment && <div style={{ marginTop: "4px" }}>Assignment: {workloadIssue.conflicting_assignment}</div>}
              {(workloadIssue.replacement_suggestions || []).length > 0 ? (
                <div style={{ marginTop: "8px" }}>
                  Eligible replacements (matching specialization, free at that time, hours to spare):
                  {workloadIssue.replacement_suggestions.map((s) => (
                    <div key={s.faculty_id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "8px", marginTop: "4px" }}>
                      <span>{s.full_name} — {s.current_hours}/{s.max_hours} h</span>
                      <button onClick={() => onPickReplacement(s.faculty_id)}
                              style={{ background: "white", color: "#003366", border: "1px solid #cdd6e0", borderRadius: "6px", padding: "3px 10px", fontSize: "12px", cursor: "pointer" }}>
                        Use this teacher
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ marginTop: "6px" }}>{workloadIssue.no_replacement_reason || "No eligible replacement faculty found for this class."}</div>
              )}
              <div style={{ marginTop: "10px" }}>
                {workloadIssue.can_override ? (
                  <button onClick={() => onOverride(group)} disabled={saving}
                          style={{ background: "#b45309", color: "white", border: "none", borderRadius: "6px", padding: "6px 12px", fontSize: "12.5px", fontWeight: 600, cursor: "pointer" }}>
                    Assign anyway (override, recorded in the audit log)
                  </button>
                ) : (
                  <em>Strict workload policy: this assignment cannot be saved. Pick another teacher.</em>
                )}
              </div>
            </div>
          )}

          {saveError && (
            <div style={{
              marginTop: "14px", padding: "10px 12px", background: "#fdecea", border: "1px solid #f3b3ac",
              color: "#a4231a", borderRadius: "8px", fontSize: "12.5px",
            }}>
              {saveError}
            </div>
          )}
        </div>

        <div style={{
          borderTop: "1px solid #e8edf3", padding: "16px 26px", display: "flex",
          justifyContent: "flex-end", gap: "10px",
        }}>
          <button
            onClick={onCancel}
            disabled={saving}
            style={{
              padding: "10px 18px", borderRadius: "8px", border: "1px solid #cdd6e0",
              background: "white", color: "#334155", fontSize: "13.5px", fontWeight: 600, cursor: "pointer",
            }}
          >
            Cancel
          </button>
          <button
            onClick={() => onSave(group)}
            disabled={saving}
            style={{
              padding: "10px 20px", borderRadius: "8px", border: "none",
              background: "#003366", color: "white", fontSize: "13.5px", fontWeight: 600, cursor: "pointer",
              display: "inline-flex", alignItems: "center", gap: "6px",
            }}
          >
            {saving ? "Saving…" : <>Save schedule</>}
          </button>
        </div>
      </div>
    </div>
  );
}

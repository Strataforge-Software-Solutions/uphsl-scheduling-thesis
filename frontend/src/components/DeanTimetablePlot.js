import React, { useEffect, useMemo, useState } from "react";
import API from "../services/api";

const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const START_MIN = 7 * 60;
const END_MIN = 20 * 60;
const STEP = 30;
const toMinutes = (value) => {
  const [h, m] = String(value || "0:0").slice(0, 5).split(":").map(Number);
  return h * 60 + m;
};
const toTime = (mins) => `${String(Math.floor(mins / 60)).padStart(2, "0")}:${String(mins % 60).padStart(2, "0")}`;
const label = (value) => {
  const mins = toMinutes(value);
  const h = Math.floor(mins / 60);
  return `${(h % 12) || 12}:${String(mins % 60).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`;
};

export default function DeanTimetablePlot({ schedules, programId, yearLevel, semester, faculty, rooms, departments, refreshKey, onMove }) {
  const [resource, setResource] = useState("section");
  const [resourceId, setResourceId] = useState("");
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(null);
  const [dropTarget, setDropTarget] = useState(null);

  const sectionOptions = useMemo(() => {
    const found = new Map();
    (schedules || []).filter((s) => String(s.program) === String(programId)
      && (!yearLevel || s.year_level === yearLevel) && (!semester || s.semester === semester))
      .forEach((s) => found.set(String(s.section), { id: s.section, name: s.section_name, program: s.program_name }));
    return [...found.values()].sort((a, b) => `${a.name}`.localeCompare(`${b.name}`));
  }, [schedules, programId, yearLevel, semester]);

  const allowedRooms = useMemo(() => (rooms || []).filter((room) => !room.department || (departments || []).includes(room.department)), [rooms, departments]);
  const options = resource === "section" ? sectionOptions : resource === "teacher" ? faculty : allowedRooms;
  const optionsKey = (options || []).map((item) => item.id).join(",");
  const firstOptionId = options?.[0]?.id || "";
  useEffect(() => {
    setResourceId(firstOptionId ? String(firstOptionId) : "");
  }, [resource, programId, yearLevel, semester, optionsKey, firstOptionId]);

  useEffect(() => {
    if (!semester || !resourceId) { setItems([]); return undefined; }
    let active = true;
    setLoading(true);
    setError("");
    API.get("/engine/schedule-plot/", { params: { resource, resource_id: resourceId, semester } })
      .then((res) => { if (active) setItems(res.data.items || []); })
      .catch((err) => { if (active) setError(err.response?.data?.detail || "Could not load this timetable."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [resource, resourceId, semester, refreshKey]);

  const visible = useMemo(() => {
    if (resource !== "section" || !yearLevel) return items;
    return items.filter((item) => {
      const matches = (schedules || []).some((s) => String(s.section) === String(item.section_id)
        && String(s.program) === String(programId) && s.year_level === yearLevel && s.semester === semester);
      return matches;
    });
  }, [items, resource, yearLevel, schedules, programId, semester]);

  const perDay = useMemo(() => Object.fromEntries(DAYS.map((day) => {
    const entries = visible.filter((item) => item.day === day).sort((a, b) => toMinutes(a.start) - toMinutes(b.start));
    const active = [];
    let laneCount = 1;
    const arranged = entries.map((item) => {
      const start = toMinutes(item.start);
      for (let i = active.length - 1; i >= 0; i -= 1) if (active[i].endMinute <= start) active.splice(i, 1);
      const occupied = new Set(active.map((entry) => entry.lane));
      let lane = 0;
      while (occupied.has(lane)) lane += 1;
      const entry = { ...item, lane, endMinute: toMinutes(item.end) };
      active.push(entry);
      laneCount = Math.max(laneCount, lane + 1);
      return entry;
    });
    return [day, arranged.map((item) => ({ ...item, laneCount }))];
  })), [visible]);
  const slotCount = (END_MIN - START_MIN) / STEP;
  const handleDrop = (event, day, index) => {
    event.preventDefault();
    setDropTarget(null);
    if (!dragging) return;
    const start = START_MIN + index * STEP;
    const duration = toMinutes(dragging.end) - toMinutes(dragging.start);
    if (start + duration > END_MIN) {
      setError("That class would end after 8:00 PM. Choose an earlier time.");
      return;
    }
    if (day === dragging.day && start === toMinutes(dragging.start)) return;
    onMove(dragging, day, toTime(start));
    setDragging(null);
  };
  const handleDayDrop = (event, day) => {
    event.preventDefault();
    const rect = event.currentTarget.getBoundingClientRect();
    const index = Math.max(0, Math.min(slotCount - 1, Math.floor((event.clientY - rect.top) / 28)));
    handleDrop(event, day, index);
  };

  return <section className="dean-timetable" aria-label="Weekly timetable plot">
    <div className="dean-timetable-toolbar">
      <div className="dean-timetable-switch" role="group" aria-label="Timetable resource">
        {["section", "teacher", "room"].map((key) => <button key={key} type="button" className={resource === key ? "is-active" : ""}
          onClick={() => setResource(key)}>{key === "section" ? "Section" : key === "teacher" ? "Teacher" : "Room"}</button>)}
      </div>
      <label>{resource === "section" ? "Section" : resource === "teacher" ? "Teacher" : "Room"}
        <select value={resourceId} onChange={(e) => setResourceId(e.target.value)} disabled={!options?.length}>
          {!options?.length && <option value="">No options available</option>}
          {resource === "section" && sectionOptions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          {resource === "teacher" && (faculty || []).map((item) => <option key={item.id} value={item.id}>{item.full_name || item.username}</option>)}
          {resource === "room" && allowedRooms.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select>
      </label>
      <span className="dean-timetable-caption">{semester || "Choose a semester"} · 7:00 AM–8:00 PM</span>
    </div>
    {error && <div className="dean-timetable-error" role="alert">{error}<button type="button" onClick={() => setError("")} aria-label="Dismiss">×</button></div>}
    {!semester ? <p className="dean-timetable-empty">Choose a semester above to view the weekly timetable.</p> : loading ? <p className="dean-timetable-empty">Loading timetable…</p> : (
      <div className="dean-timetable-scroll">
        <div className="dean-timetable-grid" style={{ "--slot-count": slotCount }}>
          <div className="dean-timetable-corner">Time</div>
          {DAYS.map((day) => <div key={day} className="dean-timetable-day-heading">{day}</div>)}
          <div className="dean-timetable-time-column">{Array.from({ length: slotCount }, (_, i) => <div key={i} className="dean-timetable-time" style={{ gridRow: i + 2 }}>{i % 2 === 0 ? label(toTime(START_MIN + i * STEP)) : ""}</div>)}</div>
          {DAYS.map((day) => <div key={day} className={`dean-timetable-day ${dropTarget?.day === day ? "is-drop-target" : ""}`} onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) setDropTarget(null); }}
            onDragOver={(e) => { if (dragging?.editable) { e.preventDefault(); const rect = e.currentTarget.getBoundingClientRect(); setDropTarget({ day, index: Math.max(0, Math.min(slotCount - 1, Math.floor((e.clientY - rect.top) / 28))) }); } }} onDrop={(e) => handleDayDrop(e, day)}>
            {Array.from({ length: slotCount }, (_, index) => <div key={index} className={`dean-timetable-cell ${dropTarget?.day === day && dropTarget?.index === index ? "is-target" : ""}`} style={{ "--cell-index": index }} />)}
            {perDay[day].map((item, idx) => {
              const start = toMinutes(item.start), end = toMinutes(item.end);
              const clippedStart = Math.max(start, START_MIN), clippedEnd = Math.min(end, END_MIN);
              if (clippedEnd <= clippedStart) return null;
              const top = ((clippedStart - START_MIN) / STEP) * 28;
              const height = Math.max(24, ((clippedEnd - clippedStart) / STEP) * 28 - 2);
              const canDrag = !item.busy && item.editable;
              const laneWidth = 100 / item.laneCount;
              return <div key={`${item.id || "busy"}-${idx}`} className={`dean-timetable-block ${item.busy ? "is-busy" : ""} ${item.conflict ? "has-conflict" : ""} ${canDrag ? "is-movable" : ""}`}
                style={{ top, height, left: `calc(${item.lane * laneWidth}% + 2px)`, width: `calc(${laneWidth}% - 4px)`, right: "auto" }} draggable={canDrag} onDragStart={() => setDragging(item)} onDragEnd={() => { setDragging(null); setDropTarget(null); }}
                title={item.busy ? "Busy outside your department" : `${item.subject_code} · ${item.teacher_name} · ${item.room_name}${item.conflict ? " · Conflict detected" : ""}`}>
                {item.busy ? <><strong>Busy</strong><small>{label(item.start)}–{label(item.end)}</small></> : <><strong>{item.subject_code} · {item.section_name}</strong><small>{label(item.start)}–{label(item.end)}</small><small>{item.teacher_name} · {item.room_name}</small>{item.conflict && <em>Overlap</em>}</>}
              </div>;
            })}
          </div>)}
        </div>
      </div>
    )}
    <div className="dean-timetable-legend"><span><i className="legend-class" />Department class</span><span><i className="legend-busy" />Other department booking</span><span><i className="legend-conflict" />Conflict</span><span>Drag draft department classes to move; class duration is preserved.</span></div>
  </section>;
}

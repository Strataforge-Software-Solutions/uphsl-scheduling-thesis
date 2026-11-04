import React, { useCallback, useEffect, useMemo, useState } from "react";
import API from "../services/api";
import RoomSelect from "./RoomSelect";

/* Dean Dashboard -> Rooms. Rooms of the college, the building its program subjects prefer, and a preferred /
   alternative / fixed room for each major subject. The Generate Schedule function uses these first. */
const BUILDING_LABEL = { M: "M – Main Building", D: "D – Alta Building", N: "N – New Building", A: "A – Alfredo Building" };
const box = { padding: "8px 10px", borderRadius: "6px", border: "1px solid #cdd6e0", fontSize: "13.5px", background: "white", boxSizing: "border-box" };
const card = { background: "white", border: "1px solid #e0e6ed", borderRadius: "10px", padding: "14px 16px", marginBottom: "18px" };

/* "Comp Lab D (309D) · 40 seats · Lab": name and room number together, so labs and lecture rooms are told apart. */
function roomText(r) {
  const base = (r.text || r.name || "").replace(/^Demo room \((.*)\)$/, "$1");
  return `${base} · ${r.capacity} seats${r.room_type === "lab" ? " · Lab" : ""}`;
}

export default function DeanRooms({ programs = [] }) {
  const [programId, setProgramId] = useState("");          // nothing is shown until the Dean picks a program
  const programName = (programs.find((p) => String(p.id) === String(programId)) || {}).name || "";
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [denied, setDenied] = useState(null);       // pop-up: why a room assignment was refused and who can do it
  const [year, setYear] = useState("");
  const [sem, setSem] = useState("");
  const [drafts, setDrafts] = useState({});          // subject id -> edited {preferred, alts, fixed}
  const [status, setStatus] = useState({});          // subject id -> {ok|err, text}

  const load = useCallback(() => {
    setError("");
    return API.get("/rooms/dean/overview/", { params: { program_id: programId || undefined } })
      .then((r) => { setData(r.data); setDrafts({}); })
      .catch((e) => setError(e.response?.data?.detail || "Could not load rooms."));
  }, [programId]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { setYear(""); setSem(""); }, [programId]);

  const rooms = useMemo(() => data?.rooms || [], [data]);
  const roomById = useMemo(() => Object.fromEntries(rooms.map((r) => [r.id, r])), [rooms]);
  const subjects = (data?.subjects || []).filter((s) => (!year || s.year_level === year) && (!sem || s.semester === sem));
  const years = [...new Set((data?.subjects || []).map((s) => s.year_level))];
  const sems = [...new Set((data?.subjects || []).map((s) => s.semester))];

  const cur = (s) => drafts[s.id] || { preferred: s.preferred_room || "", alts: s.alternative_rooms || [], fixed: s.is_fixed };
  const edit = (s, patch) => { setDrafts((d) => ({ ...d, [s.id]: { ...cur(s), ...patch } })); setStatus((x) => ({ ...x, [s.id]: null })); };
  // A college that owns laboratories (e.g. Computer Studies: Comp Lab C / D) uses only those for lab subjects; lecture
  // subjects get lecture rooms. Rooms too small for the section are left out.
  const ownLabs = rooms.some((r) => r.room_type === "lab" && r.owned);
  const des = data?.designated || [];
  const optionsFor = (s) => rooms.filter((r) => (!des.length || des.includes(r.id)) && (s.needs_lab ? r.room_type === "lab" && (!ownLabs || r.owned) : r.room_type === "lecture" || (r.room_type === "lab" && r.owned)) && (!s.students || r.capacity >= s.students));

  const save = async (s) => {
    const c = cur(s);
    setStatus((x) => ({ ...x, [s.id]: { text: "Saving…" } }));
    try {
      await API.put("/rooms/dean/subject-room/", { subject: s.id, preferred_room: c.preferred || null, alternative_rooms: c.alts, is_fixed: c.fixed });
      setData((d) => ({ ...d, subjects: d.subjects.map((x) => x.id === s.id ? { ...x, preferred_room: c.preferred ? Number(c.preferred) : null, alternative_rooms: c.alts, is_fixed: !!(c.fixed && c.preferred) } : x) }));
      setDrafts((d) => { const n = { ...d }; delete n[s.id]; return n; });
      setStatus((x) => ({ ...x, [s.id]: { ok: true, text: "Saved" } }));
    } catch (e) {
      setStatus((x) => ({ ...x, [s.id]: { err: true, text: e.response?.data?.detail || "Could not save." } }));
      setDenied({ title: "Room assignment not allowed", detail: e.response?.data?.detail || "Could not save.", action: e.response?.data?.action || "" });
    }
  };

  const setBuilding = async (dept, building) => {
    try {
      await API.put("/rooms/dean/department-building/", { department: dept, building });
      setData((d) => ({ ...d, building_preference: { ...d.building_preference, [dept]: building } }));
    } catch (e) { setError(e.response?.data?.detail || "Could not save the building."); }
  };

  if (error && !data) return <p style={{ color: "#a4231a" }}>{error}</p>;
  if (!data) return <p style={{ color: "#64748b" }}>Loading…</p>;

  return (
    <div>
      {denied && (
        <div role="alertdialog" aria-label={denied.title} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
          <div style={{ background: "white", borderRadius: 12, maxWidth: 520, width: "100%", padding: "18px 20px", boxShadow: "0 12px 40px rgba(0,0,0,.3)", borderTop: "5px solid #b91c1c" }}>
            <h3 style={{ margin: "0 0 10px", color: "#b91c1c" }}>⚠ {denied.title}</h3>
            <p style={{ margin: "0 0 8px", fontSize: 14 }}>{denied.detail}</p>
            {denied.action && <p style={{ margin: 0, fontSize: 13.5, color: "#003366" }}><strong>What to do:</strong> {denied.action}</p>}
            <div style={{ textAlign: "right", marginTop: 12 }}><button onClick={() => setDenied(null)} style={{ background: "#fff", color: "#003366", border: "1px solid #003366", borderRadius: 6, padding: "5px 14px", cursor: "pointer" }}>Close</button></div>
          </div>
        </div>
      )}
      {error && <p style={{ color: "#a4231a", fontSize: "13px" }}>{error}</p>}

      <div style={card}>
        <h3 style={{ margin: "0 0 4px" }}>Building preference</h3>
        <p style={{ margin: "0 0 10px", fontSize: "12.5px", color: "#64748b" }}>
          Gen Ed subjects use the Main Building (M) by default. Your program subjects try the building chosen here first.
        </p>
        <div style={{ display: "flex", gap: "16px", flexWrap: "wrap" }}>
          {data.departments.map((d) => (
            <label key={d} style={{ fontSize: "13px" }}>
              {d}{" "}
              <select style={box} value={data.building_preference[d] || ""} onChange={(e) => setBuilding(d, e.target.value)}>
                <option value="">No preference</option>
                {data.buildings.map((b) => <option key={b.code} value={b.code}>{BUILDING_LABEL[b.code] || b.label}</option>)}
              </select>
            </label>
          ))}
        </div>
      </div>

      <div style={card}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
          <div>
            <h3 style={{ margin: 0 }}>Subject rooms{programName ? ` — ${programName}` : ""}</h3>
            <p style={{ margin: "4px 0 0", fontSize: "12.5px", color: "#64748b" }}>
              Generate Schedule uses the preferred room first, then the alternatives, then any other suitable room. A <b>fixed</b> room is the only room the subject may use.
            </p>
          </div>
          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
            <select style={{ ...box, minWidth: 200 }} value={programId} onChange={(e) => setProgramId(e.target.value)} aria-label="Program">
              <option value="">-- Select a program --</option>
              {programs.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
            {programId && <><select style={box} value={year} onChange={(e) => setYear(e.target.value)}>
              <option value="">All year levels</option>{years.map((y) => <option key={y}>{y}</option>)}
            </select>
            <select style={box} value={sem} onChange={(e) => setSem(e.target.value)}>
              <option value="">All semesters</option>{sems.map((x) => <option key={x}>{x}</option>)}
            </select></>}
          </div>
        </div>
        {!programId ? (
          <p style={{ color: "#64748b", fontSize: "13.5px" }}>Select a program to see and set the rooms of its subjects.</p>
        ) : subjects.length === 0 ? (
          <p style={{ color: "#64748b", fontSize: "13.5px" }}>{data.subjects ? "No program subjects found for this selection." : "Loading…"}</p>
        ) : (
          <table style={{ marginTop: "10px" }}>
            <thead><tr><th>Subject</th><th>Year / Sem</th><th>Preferred room</th><th>Alternative rooms</th><th>Fixed</th><th></th></tr></thead>
            <tbody>
              {subjects.map((s) => {
                const c = cur(s);
                const opts = optionsFor(s);
                const dirty = !!drafts[s.id];
                const st = status[s.id];
                return (
                  <tr key={s.id}>
                    <td>{s.code} — {s.title}{s.needs_lab && <span style={{ color: "#7a4b00", fontSize: "11.5px" }}> · lab</span>}
                      {s.students ? <div style={{ fontSize: "11.5px", color: "#94a3b8" }}>{s.students} students per section</div> : null}</td>
                    <td style={{ whiteSpace: "nowrap" }}>{s.year_level} · {s.semester}</td>
                    <td>
                      <RoomSelect rooms={opts} value={c.preferred || ""} width={200}
                        groupBy={(r) => (r.home || r.owned ? "Your college's rooms" : "Other rooms")}
                        onChange={(v) => edit(s, { preferred: v, alts: c.alts.filter((i) => String(i) !== v), fixed: v ? c.fixed : false })} />
                    </td>
                    <td>
                      <details style={{ position: "relative" }}>
                        <summary style={{ ...box, cursor: "pointer", minWidth: "150px", listStyle: "none" }}>
                          {c.alts.length ? c.alts.map((i) => roomById[i]?.text || roomById[i]?.name).filter(Boolean).join(", ") : "None"}
                        </summary>
                        <div style={{ position: "absolute", zIndex: 5, background: "white", border: "1px solid #cdd6e0", borderRadius: "8px", padding: "8px", maxHeight: "200px", overflowY: "auto", minWidth: "220px", boxShadow: "0 6px 20px rgba(0,0,0,0.12)" }}>
                          {opts.filter((r) => String(r.id) !== String(c.preferred)).map((r) => (
                            <label key={r.id} style={{ display: "flex", gap: "6px", fontSize: "13px", padding: "2px 0" }}>
                              <input type="checkbox" checked={c.alts.includes(r.id)}
                                     onChange={(e) => edit(s, { alts: e.target.checked ? [...c.alts, r.id] : c.alts.filter((i) => i !== r.id) })} />
                              {roomText(r)}
                            </label>
                          ))}
                          {opts.length === 0 && <span style={{ fontSize: "12.5px", color: "#94a3b8" }}>No suitable rooms.</span>}
                        </div>
                      </details>
                    </td>
                    <td>
                      <input type="checkbox" aria-label="Fixed room" disabled={!c.preferred} checked={!!(c.fixed && c.preferred)}
                             onChange={(e) => edit(s, { fixed: e.target.checked })} />
                    </td>
                    <td style={{ whiteSpace: "nowrap" }}>
                      <button onClick={() => save(s)} disabled={!dirty}>Save</button>
                      {st && <span style={{ marginLeft: "8px", fontSize: "12px", color: st.err ? "#a4231a" : "#1e5f3a" }}>{st.text}</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      <EnrollmentCard />
    </div>
  );
}

/* Students per department and year level. Saving with "Update section sizes" spreads the headcount over the
   sections, and every room-capacity check (generation, exams, manual edits) uses those section sizes. */
function EnrollmentCard() {
  const [data, setData] = useState(null);
  const [draft, setDraft] = useState({});
  const [msg, setMsg] = useState("");
  const load = useCallback(() => API.get("/rooms/dean/enrollment/").then((r) => setData(r.data)).catch(() => setData({ departments: [], too_small: [] })), []);
  useEffect(() => { load(); }, [load]);
  const save = async (dept, y, apply) => {
    const v = draft[`${dept}|${y.year_level}`];
    const students = v === undefined || v === "" ? y.students : Number(v);
    if (students === null || students === undefined || Number.isNaN(students)) { setMsg("Enter the number of students first."); return; }
    try {
      const r = await API.put("/rooms/dean/enrollment/", { department: dept, year_level: y.year_level, students, apply });
      setData(r.data); setDraft((d) => { const n = { ...d }; delete n[`${dept}|${y.year_level}`]; return n; });
      setMsg(apply ? "Saved. Section sizes updated." : "Saved.");
    } catch (e) { setMsg(e.response?.data?.detail || "Could not save."); }
  };
  if (!data) return null;
  return (
    <div style={card}>
      <h3 style={{ margin: "0 0 4px" }}>Students per year level</h3>
      <p style={{ margin: "0 0 10px", fontSize: "12.5px", color: "#64748b" }}>
        Enter how many students each year level has. <b>Update section sizes</b> divides them over the sections, and rooms are only given to a class if they seat the whole section.
      </p>
      {data.departments.map((d) => (
        <div key={d.department} style={{ marginBottom: "10px" }}>
          <div style={{ fontWeight: 600, fontSize: "13.5px" }}>{d.department} <span style={{ color: "#64748b", fontWeight: 400 }}>· {d.total_students} students entered · largest lecture room seats {d.largest_lecture_room}</span></div>
          <table style={{ marginTop: "6px" }}>
            <thead><tr><th>Year level</th><th>Students</th><th>Sections</th><th>Section size</th><th>Rooms that fit</th><th></th></tr></thead>
            <tbody>
              {d.years.map((y) => {
                const k = `${d.department}|${y.year_level}`;
                return (
                  <tr key={k}>
                    <td>{y.year_level}</td>
                    <td><input type="number" min="0" style={{ ...box, width: "90px" }} value={draft[k] ?? (y.students ?? "")} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })} /></td>
                    <td>{y.sections}</td>
                    <td>{y.per_section ?? y.current_section_size}{y.per_section && y.per_section !== y.current_section_size ? <span style={{ color: "#b45309", fontSize: "11.5px" }}> (now {y.current_section_size})</span> : null}</td>
                    <td style={{ color: y.fits ? "#1e5f3a" : "#a4231a" }}>{y.fits ? (y.rooms_that_fit ?? "—") : "No room is big enough"}</td>
                    <td style={{ whiteSpace: "nowrap" }}>
                      <button onClick={() => save(d.department, y, false)}>Save</button>{" "}
                      <button onClick={() => save(d.department, y, true)} style={{ background: "#003366", color: "white" }}>Update section sizes</button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ))}
      {msg && <p style={{ fontSize: "12.5px", color: "#1e5f3a", margin: "4px 0" }}>{msg}</p>}
      {data.too_small_count > 0 && (
        <p style={{ fontSize: "12.5px", color: "#a4231a", margin: "6px 0 0" }}>
          {data.too_small_count} scheduled class(es) are in a room smaller than the section (for example {data.too_small[0].subject} in {data.too_small[0].room}: {data.too_small[0].capacity} seats, {data.too_small[0].students} students). Generate the schedule again to fix them.
        </p>)}
    </div>
  );
}

import React, { useCallback, useEffect, useMemo, useState } from "react";
import API from "../services/api";
import { roomMatches } from "./RoomSelect";

/* IT Admin -> Rooms: the only place room records are added, edited, viewed and deleted.
   Deans and the Registrar choose from these records in every room dropdown. */
const TYPE_LABEL = { lecture: "Lecture room", lab: "Laboratory", gym: "Gym", offsite: "Off-site / Online" };
const BUILDING_LABEL = { M: "M – Main Building", D: "D – Alta Building", N: "N – New Building", A: "A – Alfredo Building" };
const box = { padding: "8px 10px", borderRadius: 6, border: "1px solid #cdd6e0", fontSize: 13.5, background: "white", boxSizing: "border-box" };
const card = { background: "white", border: "1px solid #e0e6ed", borderRadius: 10, padding: "16px 18px", marginBottom: 18 };
const lbl = { fontSize: 12.5, fontWeight: 600, color: "#333" };

export default function AdminRooms() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [type, setType] = useState("");
  const [form, setForm] = useState(null);
  const [note, setNote] = useState("");
  const load = useCallback(() => API.get("/rooms/admin/rooms/").then((r) => { setData(r.data); setError(""); })
    .catch((e) => setError(e.response?.data?.detail || "Could not load the rooms.")), []);
  useEffect(() => { load(); }, [load]);
  const shown = useMemo(() => (data?.rooms || []).filter((r) => roomMatches(r, q) && (!type || r.room_type === type)), [data, q, type]);
  const remove = async (r) => {
    if (!window.confirm(`Delete room ${r.name}? This cannot be undone.`)) return;
    try { await API.delete(`/rooms/admin/rooms/${r.id}/`); setNote(`Room ${r.name} deleted.`); load(); }
    catch (e) { setNote(e.response?.data?.detail || "Could not delete the room."); }
  };
  if (error && !data) return <p style={{ color: "#a4231a" }}>{error}</p>;
  if (!data) return <p style={{ color: "#64748b" }}>Loading…</p>;
  return (
    <div>
      <div style={card}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <div>
            <h3 style={{ margin: 0 }}>Room records</h3>
            <p style={{ margin: "4px 0 0", fontSize: 12.5, color: "#64748b" }}>Deans and the Registrar pick from these rooms but cannot change them. A room with scheduled classes cannot be deleted.</p>
          </div>
          <button onClick={() => setForm({})} style={{ background: "#003366", color: "white" }}>Add room</button>
        </div>
        <div style={{ display: "flex", gap: 8, margin: "12px 0", flexWrap: "wrap" }}>
          <input style={{ ...box, minWidth: 240 }} placeholder="Search name, building or number…" value={q} onChange={(e) => setQ(e.target.value)} />
          <select style={box} value={type} onChange={(e) => setType(e.target.value)}>
            <option value="">All types</option>{data.types.map((t) => <option key={t} value={t}>{TYPE_LABEL[t] || t}</option>)}
          </select>
          <span style={{ alignSelf: "center", fontSize: 12.5, color: "#64748b" }}>{shown.length} of {data.rooms.length} rooms</span>
        </div>
        {note && <p style={{ fontSize: 13, color: "#1e5f3a" }}>{note}</p>}
        <div style={{ overflowX: "auto" }}>
          <table>
            <thead><tr><th>Room</th><th>Building</th><th>Capacity</th><th>Type</th><th>Equipment</th><th>Owner</th><th>Classes</th><th></th></tr></thead>
            <tbody>
              {shown.map((r) => (
                <tr key={r.id}>
                  <td>{r.text || r.name}</td>
                  <td>{BUILDING_LABEL[r.building] || r.building || "—"}</td>
                  <td>{r.capacity}</td>
                  <td>{TYPE_LABEL[r.room_type] || r.room_type}</td>
                  <td>{r.equipment || "—"}</td>
                  <td>{r.department || "Shared"}</td>
                  <td>{r.classes}</td>
                  <td style={{ whiteSpace: "nowrap" }}>
                    <button onClick={() => setForm(r)}>Edit</button>{" "}
                    <button onClick={() => remove(r)} style={{ background: "white", color: "#a4231a", border: "1px solid #e7b4ae" }}>Delete</button>
                  </td>
                </tr>
              ))}
              {shown.length === 0 && <tr><td colSpan={8} style={{ color: "#94a3b8" }}>No room matches.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
      {form && <RoomForm room={form} data={data} onClose={() => setForm(null)} onSaved={(m) => { setForm(null); setNote(m); load(); }} />}
    </div>
  );
}

function RoomForm({ room, data, onClose, onSaved }) {
  const editing = !!room.id;
  const [f, setF] = useState({
    building: room.building || "M", room_number: room.room_number || "", label: room.label || "", capacity: room.capacity || 40,
    room_type: room.room_type || "lecture", equipment: room.equipment || "", department: room.department || "",
  });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const submit = async () => {
    setBusy(true); setErr("");
    try {
      if (editing) await API.patch(`/rooms/admin/rooms/${room.id}/`, f); else await API.post("/rooms/admin/rooms/", f);
      onSaved(editing ? "Room saved." : "Room added.");
    } catch (e) { setErr(e.response?.data?.detail || "Could not save the room."); setBusy(false); }
  };
  const w = { ...box, width: "100%", marginTop: 4 };
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,0.45)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center", padding: 12 }}>
      <div style={{ background: "white", borderRadius: 12, padding: 24, width: 460, maxWidth: "100%" }}>
        <h3 style={{ margin: 0, color: "#003366" }}>{editing ? `Edit room ${room.name}` : "Add room"}</h3>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 14 }}>
          <div><label style={lbl}>Building</label>
            <select style={w} value={f.building} onChange={set("building")}>{data.buildings.map((b) => <option key={b.code} value={b.code}>{BUILDING_LABEL[b.code] || b.label}</option>)}</select></div>
          <div><label style={lbl}>Room number</label><input style={w} value={f.room_number} onChange={set("room_number")} placeholder="e.g. 307" /></div>
          <div><label style={lbl}>Name (optional)</label><input style={w} value={f.label} onChange={set("label")} placeholder="e.g. Comp Lab C" /></div>
          <div><label style={lbl}>Capacity</label><input type="number" min="1" style={w} value={f.capacity} onChange={set("capacity")} /></div>
          <div><label style={lbl}>Room type</label>
            <select style={w} value={f.room_type} onChange={set("room_type")}>{data.types.map((t) => <option key={t} value={t}>{TYPE_LABEL[t] || t}</option>)}</select></div>
          <div><label style={lbl}>Owner (college)</label>
            <select style={w} value={f.department} onChange={set("department")}><option value="">Shared (any college)</option>{data.departments.map((d) => <option key={d}>{d}</option>)}</select></div>
        </div>
        <div style={{ marginTop: 12 }}><label style={lbl}>Equipment</label><input style={w} value={f.equipment} onChange={set("equipment")} placeholder="e.g. Projector, Aircon, 30 PCs" /></div>
        {err && <p style={{ color: "#a4231a", fontSize: 13 }}>{err}</p>}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 16 }}>
          <button onClick={onClose} style={{ background: "white", color: "#1f2937", border: "1px solid #cdd6e0" }}>Cancel</button>
          <button onClick={submit} disabled={busy}>{busy ? "Saving…" : "Save room"}</button>
        </div>
      </div>
    </div>
  );
}

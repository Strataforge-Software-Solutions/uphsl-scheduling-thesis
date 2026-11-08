import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import API, { refreshCurrentUser } from "../services/api";
import { usePreferences, DEFAULT_PREFS, initialsOf } from "../services/preferences";
import { formatDate } from "../utils/formatDateTime";
import { APP_INFO, SUPPORT } from "../config/appInfo";
import { HELP_STEPS } from "../components/howto";
import "../components/DashboardTheme.css";
import "./Settings.css";

/* "My settings": personal preferences of the signed-in user only. Nothing here changes roles, permissions,
   scheduling rules or schedule data (accounts/preferences.py on the server). */

const SECTIONS = [
  ["profile", "Edit profile", "user"],
  ["appearance", "Appearance", "palette"],
  ["format", "Language and format", "globe"],
  ["display", "Display preferences", "display"],
  ["notifications", "Notifications", "bell"],
  ["help", "Help and about", "help"],
];
const PICTURE_TYPES = ["image/jpeg", "image/png", "image/webp"];
const MAX_PICTURE = 2 * 1024 * 1024;

function SettingsIcon({ name }) {
  const common = { fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round", strokeLinejoin: "round" };
  const shapes = {
    settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.4 2.4-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5v.2h-3.4v-.2a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1-2.4-2.4.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H4.3v-3.4h.2a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.9l-.1-.1L8 5.2l.1.1a1.7 1.7 0 0 0 1.9.3 1.7 1.7 0 0 0 1-1.5v-.2h3.4v.2a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1 2.4 2.4-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.5 1h.2V14h-.2a1.7 1.7 0 0 0-1.5 1Z" /></>,
    user: <><circle cx="12" cy="8" r="3.2" /><path d="M5.5 20c.5-3.2 2.8-5 6.5-5s6 1.8 6.5 5" /></>,
    palette: <><path d="M12 3a9 9 0 1 0 0 18h1.2a2 2 0 0 0 1.5-3.3c-.8-.9-.1-2.2 1.1-2.2H18a3 3 0 0 0 3-3c0-5.2-4-9.5-9-9.5Z" /><circle cx="7.5" cy="11" r=".8" /><circle cx="10" cy="7.5" r=".8" /><circle cx="14.5" cy="7.8" r=".8" /></>,
    globe: <><circle cx="12" cy="12" r="9" /><path d="M3.5 12h17M12 3c2.3 2.5 3.4 5.5 3.4 9s-1.1 6.5-3.4 9c-2.3-2.5-3.4-5.5-3.4-9S9.7 5.5 12 3Z" /></>,
    display: <><rect x="3" y="4" width="18" height="13" rx="2" /><path d="M8 21h8m-4-4v4" /></>,
    bell: <><path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9Zm-8 12h4" /></>,
    help: <><circle cx="12" cy="12" r="9" /><path d="M9.7 9a2.4 2.4 0 1 1 4.5 1.2c-.8 1.1-2.2 1.4-2.2 3m0 3h.01" /></>,
  };
  return <svg className={name === "settings" ? "settings-title-icon" : "settings-nav-icon"} viewBox="0 0 24 24" aria-hidden="true" focusable="false" {...common}>{shapes[name]}</svg>;
}

const errorText = (e, fallback) => e?.response?.data?.detail || fallback;
const pick = (obj, keys) => Object.fromEntries(keys.map((k) => [k, obj[k]]));

function roleKey(user) {
  if (user.role === "faculty") return user.faculty_type === "dean" ? "dean" : "faculty";
  return user.role;
}

function Message({ msg }) {
  return (
    <div role="status" aria-live="polite" className="settings-msg-slot">
      {msg && <p className={`settings-msg ${msg.ok ? "ok" : "err"}`}>{msg.text}</p>}
    </div>
  );
}

function Section({ id, title, intro, children, headingRef }) {
  return (
    <section className="ui-panel settings-section" aria-labelledby={`h-${id}`}>
      <h2 id={`h-${id}`} ref={headingRef} tabIndex={-1}>{title}</h2>
      {intro && <p className="ui-help settings-intro">{intro}</p>}
      {children}
    </section>
  );
}

function Choice({ legend, name, value, options, onChange, help }) {
  return (
    <fieldset className="settings-fieldset">
      <legend className="ui-label">{legend}</legend>
      <div className="settings-options">
        {options.map(([v, label]) => (
          <label key={v} className={`settings-option${value === v ? " on" : ""}`}>
            <input type="radio" name={name} value={v} checked={value === v} onChange={() => onChange(v)} />
            <span>{label}</span>
          </label>
        ))}
      </div>
      {help && <p className="ui-help">{help}</p>}
    </fieldset>
  );
}

function Actions({ onSave, onReset, busy, dirty, resetLabel = "Reset to defaults" }) {
  return (
    <div className="settings-actions">
      <button type="button" className="ui-btn" onClick={onSave} disabled={busy || !dirty}>{busy === "save" ? "Saving…" : "Save"}</button>
      <button type="button" className="ui-btn secondary" onClick={onReset} disabled={!!busy}>{busy === "reset" ? "Resetting…" : resetLabel}</button>
    </div>
  );
}

/* a section made of preference fields: its own Save, message and Reset to defaults (only these fields) */
function usePrefSection(keys) {
  const { prefs, save } = usePreferences();
  const [form, setForm] = useState(() => pick(prefs, keys));
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState(null);
  const saved = pick(prefs, keys);
  const dirty = keys.some((k) => form[k] !== saved[k]);
  const set = (k, v) => { setForm((f) => ({ ...f, [k]: v })); setMsg(null); };
  const run = async (kind, values, okText) => {
    setBusy(kind); setMsg(null);
    try {
      const d = await save(values);
      setForm(pick(d.preferences, keys));
      setMsg({ ok: true, text: okText });
    } catch (e) {
      setMsg({ ok: false, text: errorText(e, "Could not save. Check your connection and try again.") });
    }
    setBusy("");
  };
  return {
    form, set, busy, msg, dirty,
    onSave: () => run("save", form, "Saved."),
    onReset: () => run("reset", pick(DEFAULT_PREFS, keys), "Reset to defaults and saved."),
  };
}

// ------------------------------------------------------------------ 1. profile
function Avatar({ url, initials, size = 72 }) {
  return url
    ? <img className="settings-avatar" src={url} alt="You" width={size} height={size} />
    : <span className="settings-avatar initials" style={{ width: size, height: size }} role="img" aria-label="Your initials">{initials}</span>;
}

function ProfileSection({ headingRef }) {
  const { profile, pictureUrl, save, uploadPicture, removePicture } = usePreferences();
  const fields = ["email", "phone"];          // the name comes from the school's records and is not edited here
  const fromProfile = () => pick(profile || {}, fields);
  const [form, setForm] = useState(fromProfile);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState(null);
  const [picMsg, setPicMsg] = useState(null);
  const [chosen, setChosen] = useState(null);           // { file, url } waiting for "Upload"
  const fileRef = useRef(null);
  useEffect(() => () => { if (chosen) URL.revokeObjectURL(chosen.url); }, [chosen]);
  if (!profile) return <Section id="profile" title="Edit profile" headingRef={headingRef}><p className="ui-help">Your profile could not be loaded. Reload the page to try again.</p></Section>;

  const saved = fromProfile();
  const dirty = fields.some((k) => (form[k] || "") !== (saved[k] || ""));
  const set = (k, v) => { setForm((f) => ({ ...f, [k]: v })); setMsg(null); };
  const emailBad = form.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email);

  const onSave = async () => {
    if (emailBad) { setMsg({ ok: false, text: "Enter a valid email address, for example name@manila.uphsl.edu.ph." }); return; }
    setBusy("save"); setMsg(null);
    try {
      const d = await save(form);
      setForm(pick(d.profile, fields));
      refreshCurrentUser().catch(() => {});          // the name shown in the dashboards
      setMsg({ ok: true, text: "Profile saved." });
    } catch (e) { setMsg({ ok: false, text: errorText(e, "Could not save your profile.") }); }
    setBusy("");
  };

  const choose = (e) => {
    const file = e.target.files && e.target.files[0];
    e.target.value = "";
    setPicMsg(null);
    if (!file) return;
    if (!PICTURE_TYPES.includes(file.type)) { setPicMsg({ ok: false, text: "Use a JPG, PNG or WebP picture. GIF and SVG are not accepted." }); return; }
    if (file.size > MAX_PICTURE) { setPicMsg({ ok: false, text: "The picture is larger than 2 MB. Choose a smaller file." }); return; }
    if (chosen) URL.revokeObjectURL(chosen.url);
    setChosen({ file, url: URL.createObjectURL(file) });
  };
  const upload = async () => {
    setBusy("pic"); setPicMsg(null);
    try {
      await uploadPicture(chosen.file);
      URL.revokeObjectURL(chosen.url); setChosen(null);
      setPicMsg({ ok: true, text: "Picture saved." });
    } catch (e) { setPicMsg({ ok: false, text: errorText(e, "Could not upload the picture.") }); }
    setBusy("");
  };
  const remove = async () => {
    setBusy("pic"); setPicMsg(null);
    try { await removePicture(); setPicMsg({ ok: true, text: "Picture removed." }); }
    catch (e) { setPicMsg({ ok: false, text: errorText(e, "Could not remove the picture.") }); }
    setBusy("");
  };

  const initials = initialsOf(profile.first_name, profile.last_name, profile.username);
  return (
    <Section id="profile" title="Edit profile" headingRef={headingRef}
      intro="Your contact details and picture. Your name, school ID, role and department come from the school's records.">
      <div className="settings-picture">
        <Avatar url={chosen ? chosen.url : pictureUrl} initials={initials} />
        <div>
          <p className="ui-label" style={{ margin: 0 }}>Profile picture</p>
          <p className="ui-help" style={{ margin: "2px 0 8px" }}>JPG, PNG or WebP, up to 2 MB. It is resized to 512 × 512.</p>
          <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" onChange={choose} className="settings-file" id="pic-file" />
          <div className="settings-actions tight">
            {chosen ? (
              <>
                <button type="button" className="ui-btn" onClick={upload} disabled={busy === "pic"}>{busy === "pic" ? "Uploading…" : "Upload picture"}</button>
                <button type="button" className="ui-btn secondary" onClick={() => { URL.revokeObjectURL(chosen.url); setChosen(null); }} disabled={busy === "pic"}>Cancel</button>
              </>
            ) : (
              <>
                <button type="button" className="ui-btn secondary" onClick={() => fileRef.current && fileRef.current.click()} disabled={busy === "pic"}>
                  {profile.has_picture ? "Replace picture" : "Choose picture"}
                </button>
                {profile.has_picture && <button type="button" className="ui-btn secondary" onClick={remove} disabled={busy === "pic"}>Remove picture</button>}
              </>
            )}
          </div>
          {chosen && <p className="ui-help">Preview. Press Upload picture to keep it.</p>}
          <Message msg={picMsg} />
        </div>
      </div>

      <div className="settings-grid">
        <label className="ui-field"><span className="ui-label">Contact email</span>
          <input type="email" value={form.email || ""} maxLength={254} onChange={(e) => set("email", e.target.value)} autoComplete="email"
            aria-invalid={emailBad ? "true" : "false"} />
          {emailBad && <span className="ui-error">Enter a valid email address.</span>}</label>
        <label className="ui-field"><span className="ui-label">Phone number (optional)</span>
          <input type="tel" value={form.phone || ""} maxLength={30} onChange={(e) => set("phone", e.target.value)} autoComplete="tel" /></label>
      </div>

      <dl className="settings-readonly">
        <div><dt>Name</dt><dd>{`${profile.first_name} ${profile.last_name}`.trim() || "—"}</dd></div>
        <div><dt>School ID</dt><dd>{profile.school_id}</dd></div>
        <div><dt>Login ID</dt><dd>{profile.username}</dd></div>
        <div><dt>Role</dt><dd>{profile.role}</dd></div>
        <div><dt>Department</dt><dd>{profile.department || "—"}</dd></div>
      </dl>
      <Actions busy={busy === "save" ? "save" : ""} dirty={dirty} onSave={onSave} resetLabel="Undo changes"
        onReset={() => { setForm(fromProfile()); setMsg({ ok: true, text: "Changes undone." }); }} />
      <Message msg={msg} />
    </Section>
  );
}

// ------------------------------------------------------------------ 2. appearance
function AppearanceSection({ headingRef }) {
  const { data } = usePreferences();
  const s = usePrefSection(["theme", "text_size", "table_density", "reduce_motion"]);
  const ch = data?.choices || {};
  return (
    <Section id="appearance" title="Appearance" headingRef={headingRef}
      intro="How the pages look on this screen. Printing and the PDF files always use the fixed print layout.">
      <Choice legend="Theme" name="theme" value={s.form.theme} onChange={(v) => s.set("theme", v)}
        options={ch.theme || [["light", "Default"], ["royal", "Royal"]]}
        help="Default: UPHSL navy and white. Royal: royal navy, gold and cream. Printing always uses the standard print layout." />
      <Choice legend="Text size" name="text_size" value={s.form.text_size} onChange={(v) => s.set("text_size", v)}
        options={ch.text_size || [["small", "Small"], ["medium", "Medium"], ["large", "Large"]]} />
      <Choice legend="Table density" name="table_density" value={s.form.table_density} onChange={(v) => s.set("table_density", v)}
        options={ch.table_density || [["comfortable", "Comfortable"], ["compact", "Compact"]]} help="Compact puts more rows on the screen (less space above and below each row)." />
      <Choice legend="Reduce motion" name="reduce_motion" value={s.form.reduce_motion} onChange={(v) => s.set("reduce_motion", v)}
        options={ch.reduce_motion || [["system", "Follow device"], ["on", "On"], ["off", "Off"]]} help="On turns off smooth scrolling and transitions." />
      <Actions {...s} />
      <Message msg={s.msg} />
    </Section>
  );
}

// ------------------------------------------------------------------ 3. language and format
function FormatSection({ headingRef }) {
  const { data } = usePreferences();
  const s = usePrefSection(["time_format", "date_format"]);
  const ch = data?.choices || {};
  return (
    <Section id="format" title="Language and format" headingRef={headingRef}
      intro="How times and dates are shown on screen. Saved data and the PDF files do not change.">
      <Choice legend="Time format" name="time_format" value={s.form.time_format} onChange={(v) => s.set("time_format", v)}
        options={ch.time_format || [["12h", "12-hour (7:00 AM)"], ["24h", "24-hour (07:00)"]]} />
      <Choice legend="Date format" name="date_format" value={s.form.date_format} onChange={(v) => s.set("date_format", v)}
        options={ch.date_format || [["mdy_short", "Nov 6, 2026"], ["dmy", "06/11/2026"], ["iso", "2026-11-06"]]} />
      <p className="settings-static"><span className="ui-label">Time zone</span> {APP_INFO.timeZone}</p>
      <p className="settings-static"><span className="ui-label">Language</span> English</p>
      <Actions {...s} />
      <Message msg={s.msg} />
    </Section>
  );
}

// ------------------------------------------------------------------ 4. display preferences
function DisplaySection({ headingRef }) {
  const { data } = usePreferences();
  const s = usePrefSection(["landing_page"]);
  const pages = data?.choices?.landing_page || [];
  return (
    <Section id="display" title="Display preferences" headingRef={headingRef} intro="The page that opens after you sign in.">
      {pages.length <= 1 ? (
        <p className="ui-help">Your account has one page{pages[0] ? ` (${pages[0][1]})` : ""}, so it always opens first.</p>
      ) : (
        <>
          <label className="ui-field settings-narrow"><span className="ui-label">Default landing page</span>
            <select value={s.form.landing_page} onChange={(e) => s.set("landing_page", e.target.value)}>
              <option value="">Normal home page</option>
              {pages.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
            </select>
          </label>
          <p className="ui-help">Only pages your role can open are listed. If a page is no longer available to you, the normal home page opens.</p>
          <Actions {...s} />
        </>
      )}
      <Message msg={s.msg} />
    </Section>
  );
}

// ------------------------------------------------------------------ 5. notifications
const SWITCHES = [
  ["notify_schedule", "Schedule published or changed", "Your schedule was published, a class was moved, a shared class was given to you, and Gen Ed move requests."],
  ["notify_conflict", "Conflict alerts", "A schedule or exam conflict that involves you."],
  ["notify_exam", "Exam proctoring", "You were assigned to proctor exams."],
  ["notify_substitute", "Substitute assignments", "You were asked to cover a class."],
];

function NotificationsSection({ headingRef }) {
  const s = usePrefSection(SWITCHES.map(([k]) => k));
  const [markMsg, setMarkMsg] = useState(null);
  const [marking, setMarking] = useState(false);
  const markAll = async () => {
    setMarking(true); setMarkMsg(null);
    try {
      const r = await API.post("/notifications/mark_all_read/");
      const n = r.data.updated || 0;
      setMarkMsg({ ok: true, text: n ? `Marked ${n} notification${n === 1 ? "" : "s"} as read.` : "There were no unread notifications." });
    } catch (e) { setMarkMsg({ ok: false, text: errorText(e, "Could not mark the notifications as read.") }); }
    setMarking(false);
  };
  return (
    <Section id="notifications" title="Notifications" headingRef={headingRef}
      intro="These are the notifications in the bell at the top of the page. The system does not send emails. A kind you switch off is hidden from the bell; nothing is deleted.">
      <div className="settings-switches">
        {SWITCHES.map(([k, label, help]) => (
          <label key={k} className="settings-switch">
            <input type="checkbox" checked={!!s.form[k]} onChange={(e) => s.set(k, e.target.checked)} />
            <span><span className="settings-switch-label">{label}</span><span className="ui-help">{help}</span></span>
          </label>
        ))}
      </div>
      <Actions {...s} />
      <Message msg={s.msg} />
      <div className="settings-divider" />
      <div className="settings-actions tight">
        <button type="button" className="ui-btn secondary" onClick={markAll} disabled={marking}>{marking ? "Marking…" : "Mark all as read"}</button>
      </div>
      <Message msg={markMsg} />
    </Section>
  );
}

// ------------------------------------------------------------------ 6. help and about
function HelpSection({ user, headingRef }) {
  const steps = HELP_STEPS[roleKey(user)] || HELP_STEPS.student;
  const notSet = <span className="settings-placeholder">Not set yet</span>;
  return (
    <Section id="help" title="Help and about" headingRef={headingRef}>
      <h3 className="settings-sub">Getting started</h3>
      <ol className="settings-steps">{steps.map((t, i) => <li key={i}>{t}</li>)}</ol>
      <p className="ui-help">Each page also has a "How to use this tab" panel with more detail.</p>

      <h3 className="settings-sub">Contact support</h3>
      <dl className="settings-readonly">
        <div><dt>Email</dt><dd>{SUPPORT.email ? <a href={`mailto:${SUPPORT.email}`}>{SUPPORT.email}</a> : notSet}</dd></div>
        <div><dt>Phone</dt><dd>{SUPPORT.phone || notSet}</dd></div>
        <div><dt>Office</dt><dd>{SUPPORT.location || notSet}</dd></div>
      </dl>

      <h3 className="settings-sub">About</h3>
      <dl className="settings-readonly">
        <div><dt>System</dt><dd>{APP_INFO.name}</dd></div>
        <div><dt>Full name</dt><dd>{APP_INFO.fullName}</dd></div>
        <div><dt>Version</dt><dd>{APP_INFO.version}</dd></div>
        <div><dt>Last updated</dt><dd>{formatDate(APP_INFO.lastUpdated)}</dd></div>
        <div><dt>School</dt><dd>{APP_INFO.school}</dd></div>
      </dl>
    </Section>
  );
}

// ------------------------------------------------------------------ page
export default function Settings({ user }) {
  const navigate = useNavigate();
  const { ready, data } = usePreferences();
  const [active, setActive] = useState("profile");
  const headingRef = useRef(null);
  const first = useRef(true);
  useEffect(() => {
    if (first.current) { first.current = false; return; }
    if (headingRef.current) headingRef.current.focus();      // keyboard users land on the section they opened
  }, [active]);

  const body = !ready ? <p className="ui-help">Loading…</p>
    : !data && active !== "help" ? (
      <div className="ui-panel settings-section"><p className="settings-msg err">Your settings could not be loaded. Check your connection and reload the page.</p></div>
    ) : {
      profile: <ProfileSection headingRef={headingRef} />,
      appearance: <AppearanceSection headingRef={headingRef} />,
      format: <FormatSection headingRef={headingRef} />,
      display: <DisplaySection headingRef={headingRef} />,
      notifications: <NotificationsSection headingRef={headingRef} />,
      help: <HelpSection user={user} headingRef={headingRef} />,
    }[active];

  return (
    <div className="settings-page">
      <header className="settings-top">
        <div className="settings-top-title"><span className="settings-brand">U-FAST</span><span aria-hidden="true">·</span><h1>My settings</h1></div>
      </header>
      <div className="settings-body">
        <nav className="settings-nav" aria-label="Settings sections">
          <ul>
            {SECTIONS.map(([k, label, icon]) => (
              <li key={k}>
                <button type="button" className={`settings-nav-item${active === k ? " active" : ""}`} aria-current={active === k ? "page" : undefined}
                  onClick={() => setActive(k)}><SettingsIcon name={icon} /><span>{label}</span></button>
              </li>
            ))}
          </ul>
        </nav>
        <main className="settings-main">
          <div className="settings-page-heading">
            <div>
              <h2><SettingsIcon name="settings" />My Settings</h2>
              <p>Manage your preferences and more.</p>
            </div>
            <button type="button" className="ui-btn secondary" onClick={() => navigate("/dashboard")}>Back to dashboard</button>
          </div>
          {body}
        </main>
      </div>
    </div>
  );
}

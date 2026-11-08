import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import API, { changePassword, markPasswordChanged, refreshCurrentUser } from "../services/api";
import { usePreferences, DEFAULT_PREFS, initialsOf } from "../services/preferences";
import { formatDate } from "../utils/formatDateTime";
import { APP_INFO, SUPPORT } from "../config/appInfo";
import { HELP_STEPS } from "../components/howto";
import PasswordInput from "../components/PasswordInput";
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
  ["password", "Change password", "lock"],
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
    lock: <><rect x="4" y="10" width="16" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2" /></>,
    mail: <><rect x="3" y="5" width="18" height="14" rx="2" /><path d="m4 7 8 6 8-6" /></>,
    school: <><path d="m3 9 9-5 9 5-9 5-9-5Z" /><path d="M6 11v5c3.5 3 8.5 3 12 0v-5M21 9v6" /></>,
    id: <><rect x="3" y="5" width="18" height="14" rx="2" /><circle cx="8" cy="11" r="2" /><path d="M5.5 16c.6-1.5 1.4-2 2.5-2s1.9.5 2.5 2m3-5h4m-4 3h4" /></>,
    login: <><path d="M4 7h12l4 3-4 3H4l-3-3 3-3Z" /><path d="M4 14h12l4 3-4 3H4l-3-3 3-3Z" /></>,
    role: <><path d="M12 3 20 6v5c0 5-3.4 8.2-8 10-4.6-1.8-8-5-8-10V6l8-3Z" /><path d="m9 12 2 2 4-4" /></>,
    department: <><path d="M3 21h18M5 21V7l7-4 7 4v14M9 9h.01M15 9h.01M9 13h.01M15 13h.01M10 21v-4h4v4" /></>,
    density_comfortable: <><path d="M4 6h2m4 0h10M4 12h2m4 0h10M4 18h2m4 0h10" /><circle cx="5" cy="6" r="1" /><circle cx="5" cy="12" r="1" /><circle cx="5" cy="18" r="1" /></>,
    density_compact: <><path d="M4 5h2m4 0h10M4 9h2m4 0h10M4 13h2m4 0h10M4 17h2m4 0h10" /><circle cx="5" cy="5" r="1" /><circle cx="5" cy="9" r="1" /><circle cx="5" cy="13" r="1" /><circle cx="5" cy="17" r="1" /></>,
    language: <><path d="M4 6h10M9 4v2m3 0c-.8 4.2-3.3 6.8-7 8m1-5c1.5 2.2 3.7 4 6 5m2 4 3-8 3 8m-5-2h4" /></>,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 10h18m-13 4h2m4 0h2m-8 3h2m4 0h2" /></>,
    info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v5m0-8h.01" /></>,
    alert: <><path d="m12 3 10 18H2L12 3Z" /><path d="M12 9v5m0 3h.01" /></>,
    clipboard: <><rect x="5" y="5" width="14" height="16" rx="2" /><path d="M9 5V3h6v2m-6 6h6m-6 4h6" /></>,
    people: <><circle cx="9" cy="8" r="3" /><path d="M3 20v-1a6 6 0 0 1 12 0v1H3Zm13-9a3 3 0 1 0-1-5.8M17 14a5 5 0 0 1 4 5v1h-3" /></>,
    check_square: <><rect x="3" y="3" width="18" height="18" rx="3" /><path d="m7 12 3 3 7-7" /></>,
    rocket: <><path d="M5 19c-1 0-2-1-2-2 0-2 2-4 5-5l4 4c-1 3-3 5-5 5-1 0-2-1-2-2Z" /><path d="M9 15 5 11c1-5 6-8 14-8 0 8-3 13-8 14m1-7 3-3" /><circle cx="15" cy="8" r="1" /></>,
    book: <><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v17H6.5A2.5 2.5 0 0 0 4 22V5.5Z" /><path d="M4 18a2.5 2.5 0 0 1 2.5-2.5H20M8 7h8" /></>,
    headset: <><path d="M3 13v-2a9 9 0 0 1 18 0v2" /><rect x="3" y="12" width="4" height="7" rx="2" /><rect x="17" y="12" width="4" height="7" rx="2" /><path d="M17 20c-1 1-2.5 1-4 1" /></>,
    phone: <><path d="M7 3h10v18H7z" /><path d="M10 6h4m-2 12h.01" /></>,
    pin: <><path d="M20 10c0 5-8 12-8 12S4 15 4 10a8 8 0 1 1 16 0Z" /><circle cx="12" cy="10" r="2.5" /></>,
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

function Section({ id, title, intro, children, headingRef, icon }) {
  return (
    <section className="ui-panel settings-section" aria-labelledby={`h-${id}`}>
      <h2 id={`h-${id}`} ref={headingRef} tabIndex={-1}>{icon && <SettingsIcon name={icon} />}<span>{title}</span></h2>
      {intro && <p className="ui-help settings-intro">{intro}</p>}
      {children}
    </section>
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
  if (!profile) return <Section id="profile" title="Edit profile" icon="user" headingRef={headingRef}><p className="ui-help">Your profile could not be loaded. Reload the page to try again.</p></Section>;

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
    <Section id="profile" title="Edit profile" icon="user" headingRef={headingRef}
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

      <div className="settings-profile-columns">
        <section className="settings-profile-card" aria-labelledby="contact-info-heading">
          <div className="settings-profile-card-heading"><SettingsIcon name="mail" /><div><h3 id="contact-info-heading">Contact Information</h3><p>Update how the school can reach you.</p></div></div>
          <label className="ui-field"><span className="ui-label">Contact email</span>
            <input type="email" value={form.email || ""} maxLength={254} onChange={(e) => set("email", e.target.value)} autoComplete="email"
              aria-invalid={emailBad ? "true" : "false"} />
            {emailBad && <span className="ui-error">Enter a valid email address.</span>}</label>
          <label className="ui-field"><span className="ui-label">Phone number (optional)</span>
            <input type="tel" value={form.phone || ""} maxLength={30} onChange={(e) => set("phone", e.target.value)} autoComplete="tel" /></label>
        </section>
        <section className="settings-profile-card" aria-labelledby="school-info-heading">
          <div className="settings-profile-card-heading"><SettingsIcon name="school" /><div><h3 id="school-info-heading">School Information</h3><p>Official school records (read-only).</p></div><span className="settings-readonly-badge"><SettingsIcon name="lock" />Read only</span></div>
          <dl className="settings-readonly settings-school-info">
            <div><dt><SettingsIcon name="user" />Name</dt><dd>{`${profile.first_name} ${profile.last_name}`.trim() || "—"}</dd></div>
            <div><dt><SettingsIcon name="id" />School ID</dt><dd>{profile.school_id}</dd></div>
            <div><dt><SettingsIcon name="login" />Login ID</dt><dd>{profile.username}</dd></div>
            <div><dt><SettingsIcon name="role" />Role</dt><dd>{profile.role}</dd></div>
            <div><dt><SettingsIcon name="department" />Department</dt><dd>{profile.department || "—"}</dd></div>
          </dl>
        </section>
      </div>
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
  const themes = ch.theme || [["light", "Default"], ["royal", "Royal"], ["dark", "Dark"]];
  const motionOn = s.form.reduce_motion === "on";
  return (
    <Section id="appearance" title="Appearance" icon="palette" headingRef={headingRef}
      intro="Customize how U-FAST looks and feels on this device. Printing and PDF files keep the standard print layout.">
      <div className="settings-theme-layout">
        <fieldset className="settings-theme-fieldset">
          <legend><SettingsIcon name="palette" /><span>Theme</span></legend><p className="settings-appearance-help">Choose a color theme for the system.</p>
          <div className="settings-theme-options">
            {themes.map(([value, label]) => <label key={value} className={`settings-theme-option${s.form.theme === value ? " selected" : ""}`}>
              <input type="radio" name="theme" value={value} checked={s.form.theme === value} onChange={() => s.set("theme", value)} />
              <MiniThemePreview theme={value} />
              <span className="settings-theme-label"><span className="settings-radio-dot" />{label}</span>
            </label>)}
          </div>
        </fieldset>
        <div className="settings-live-preview"><h3>Preview</h3><p className="settings-appearance-help">A quick look at your selected theme.</p><MiniThemePreview theme={s.form.theme} large /></div>
      </div>

      <div className="settings-appearance-controls">
        <fieldset className="settings-appearance-group">
          <legend>Text size</legend><p className="settings-appearance-help">Adjust the overall text size.</p>
          <div className="settings-size-options">{(ch.text_size || [["small", "Small"], ["medium", "Medium"], ["large", "Large"]]).map(([value, label]) => <label key={value} className={`settings-size-option${s.form.text_size === value ? " selected" : ""}`}>
            <input type="radio" name="text_size" value={value} checked={s.form.text_size === value} onChange={() => s.set("text_size", value)} />
            <span className={`settings-size-sample size-${value}`}>Aa</span><span>{label}</span>
          </label>)}</div>
        </fieldset>
        <fieldset className="settings-appearance-group">
          <legend>Table density</legend><p className="settings-appearance-help">Control how much content is shown per row.</p>
          <div className="settings-density-options">{(ch.table_density || [["comfortable", "Comfortable"], ["compact", "Compact"]]).map(([value, label]) => <label key={value} className={`settings-density-option${s.form.table_density === value ? " selected" : ""}`}>
            <input type="radio" name="table_density" value={value} checked={s.form.table_density === value} onChange={() => s.set("table_density", value)} />
            <SettingsIcon name={`density_${value}`} /><span>{label}</span>
          </label>)}</div>
        </fieldset>
      </div>

      <div className="settings-motion-row">
        <div className="settings-motion-icon" aria-hidden="true">▶</div>
        <div className="settings-motion-copy"><strong>Reduce motion</strong><span>Minimize animations and transitions for a smoother experience.</span></div>
        <button type="button" role="switch" aria-checked={motionOn} className={`settings-motion-toggle${motionOn ? " on" : ""}`} onClick={() => s.set("reduce_motion", motionOn ? "off" : "on")}><span /> <span className="settings-motion-state">{motionOn ? "On" : "Off"}</span></button>
      </div>
      <Actions {...s} />
      <Message msg={s.msg} />
    </Section>
  );
}

function MiniThemePreview({ theme, large = false }) {
  return <div className={`settings-theme-preview ${large ? "large" : ""} theme-${theme}`} aria-hidden="true">
    <div className="settings-preview-top"><i /> <b>U-FAST</b><span /></div>
    <div className="settings-preview-body"><div className="settings-preview-rail"><i /><i /><i /><i /></div><div className="settings-preview-content"><i /><i /><i /><i /></div></div>
  </div>;
}

// ------------------------------------------------------------------ 3. language and format
function FormatSection({ headingRef }) {
  const { data } = usePreferences();
  const s = usePrefSection(["time_format", "date_format"]);
  const ch = data?.choices || {};
  const timeChoices = ch.time_format || [["12h", "12-hour (7:00 AM)"], ["24h", "24-hour (07:00)"]];
  const dateChoices = ch.date_format || [["mdy_short", "Nov 6, 2026"], ["dmy", "06/11/2026"], ["iso", "2026-11-06"]];
  const dateExamples = { mdy_short: "MMM D, YYYY", dmy: "DD/MM/YYYY", iso: "YYYY-MM-DD" };
  return (
    <Section id="format" title="Language and format" icon="globe" headingRef={headingRef}
      intro="Set your language, time and date formats for how information is displayed across U-FAST.">
      <div className="settings-format-rows">
        <div className="settings-format-row">
          <div className="settings-format-label"><SettingsIcon name="language" /><div><strong>Language</strong><span>Preferred display language.</span></div></div>
          <div className="settings-format-readonly" aria-label="Language: English"><span className="settings-language-flag" aria-hidden="true">🇺🇸</span>English</div>
        </div>
        <div className="settings-format-row">
          <div className="settings-format-label"><SettingsIcon name="clock" /><div><strong>Time format</strong><span>Choose how time is displayed.</span></div></div>
          <div className="settings-format-options two">
            {timeChoices.map(([value, label]) => <label key={value} className={`settings-format-option${s.form.time_format === value ? " selected" : ""}`}>
              <input type="radio" name="time_format" value={value} checked={s.form.time_format === value} onChange={() => s.set("time_format", value)} />
              <span className="settings-format-radio" /><span><strong>{label}</strong><small>{value === "12h" ? "Uses AM/PM (e.g., 7:00 AM)" : "Uses a 24-hour clock (e.g., 07:00)"}</small></span>
            </label>)}
          </div>
        </div>
        <div className="settings-format-row">
          <div className="settings-format-label"><SettingsIcon name="calendar" /><div><strong>Date format</strong><span>Choose how dates are shown.</span></div></div>
          <div className="settings-format-options three">
            {dateChoices.map(([value, label]) => <label key={value} className={`settings-format-option${s.form.date_format === value ? " selected" : ""}`}>
              <input type="radio" name="date_format" value={value} checked={s.form.date_format === value} onChange={() => s.set("date_format", value)} />
              <span className="settings-format-radio" /><span><strong>{label}</strong><small>{dateExamples[value] || "Date display format"}</small></span>
            </label>)}
          </div>
        </div>
        <div className="settings-format-row">
          <div className="settings-format-label"><SettingsIcon name="globe" /><div><strong>Time zone</strong><span>Used for local times and schedules.</span></div></div>
          <div className="settings-format-readonly" aria-label={`Time zone: ${APP_INFO.timeZone}`}><SettingsIcon name="lock" />{APP_INFO.timeZone}</div>
        </div>
      </div>
      <div className="settings-format-note"><SettingsIcon name="info" /><strong>What this affects</strong><span>These settings change how dates and times appear across U-FAST. They do not change saved data or PDF reports.</span></div>
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
    <Section id="display" title="Display preferences" icon="display" headingRef={headingRef} intro="The page that opens after you sign in.">
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
  ["notify_schedule", "Schedule published or changed", "Your schedule was published, a class was moved, a shared class was given to you, and Gen Ed move requests.", "calendar"],
  ["notify_conflict", "Conflict alerts", "A schedule or exam conflict that involves you.", "alert"],
  ["notify_exam", "Exam proctoring", "You were assigned to proctor exams.", "clipboard"],
  ["notify_substitute", "Substitute assignments", "You were asked to cover a class.", "people"],
];

function NotificationsSection({ headingRef }) {
  const s = usePrefSection(SWITCHES.map(([k]) => k));
  const [markMsg, setMarkMsg] = useState(null);
  const [marking, setMarking] = useState(false);
  const markAll = async () => {
    setMarking(true);
    setMarkMsg(null);
    try {
      const response = await API.post("/notifications/mark_all_read/");
      const count = response.data.updated || 0;
      setMarkMsg({ ok: true, text: count ? `Marked ${count} notification${count === 1 ? "" : "s"} as read.` : "There were no unread notifications." });
    } catch (e) {
      setMarkMsg({ ok: false, text: errorText(e, "Could not mark the notifications as read.") });
    }
    setMarking(false);
  };
  return (
    <Section id="notifications" title="Notifications" icon="bell" headingRef={headingRef}
      intro="Choose which updates you want to receive in U-FAST. These appear in the notification bell.">
      <div className="settings-notification-note"><SettingsIcon name="info" /><strong>About notifications</strong><span>The system does not send emails. Turning off a notification hides it from the bell only.</span></div>
      <div className="settings-notification-list">
        {SWITCHES.map(([k, label, help, icon]) => (
          <div className="settings-notification-row" key={k}>
            <div className="settings-notification-info"><SettingsIcon name={icon} /><div><strong>{label}</strong><span>{help}</span></div></div>
            <button type="button" role="switch" aria-label={label} aria-checked={!!s.form[k]}
              className={`settings-motion-toggle${s.form[k] ? " on" : ""}`} onClick={() => s.set(k, !s.form[k])}>
              <span /><span className="settings-motion-state">{s.form[k] ? "On" : "Off"}</span>
            </button>
          </div>
        ))}
      </div>
      <div className="settings-notification-footer">
        <div className="settings-mark-all-row">
          <button type="button" className="ui-btn secondary" onClick={markAll} disabled={marking}>
            <SettingsIcon name="check_square" />{marking ? "Marking…" : "Mark all as read"}
          </button>
          <Message msg={markMsg} />
        </div>
        <div className="settings-actions">
          <button type="button" className="ui-btn" onClick={s.onSave} disabled={s.busy || !s.dirty}>{s.busy === "save" ? "Saving…" : "Save"}</button>
          <button type="button" className="ui-btn secondary" onClick={s.onReset} disabled={!!s.busy}>{s.busy === "reset" ? "Resetting…" : "Reset to defaults"}</button>
        </div>
      </div>
      <Message msg={s.msg} />
    </Section>
  );
}

function ChangePasswordSection({ headingRef }) {
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);

  const submit = async (event) => {
    event.preventDefault();
    setMsg(null);
    if (newPassword !== confirmPassword) {
      setMsg({ ok: false, text: "The new passwords do not match." });
      return;
    }
    setBusy(true);
    try {
      await changePassword(newPassword, oldPassword, confirmPassword);
      markPasswordChanged();
      setOldPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setMsg({ ok: true, text: "Your password has been changed." });
    } catch (e) {
      const data = e?.response?.data;
      const details = [data?.old_password, data?.new_password, data?.confirm_password]
        .flatMap((value) => Array.isArray(value) ? value : value ? [value] : []);
      setMsg({ ok: false, text: details.join(" ") || errorText(e, "Could not change your password. Check your connection and try again.") });
    }
    setBusy(false);
  };

  return (
    <Section id="password" title="Change password" icon="lock" intro="Choose a new password to protect your account." headingRef={headingRef}>
      <form className="settings-password-form" onSubmit={submit}>
        <div className="ui-field"><label className="ui-label" htmlFor="settings-current-password">Current password</label><PasswordInput id="settings-current-password" autoComplete="current-password" value={oldPassword} onChange={(e) => setOldPassword(e.target.value)} required /></div>
        <div className="ui-field"><label className="ui-label" htmlFor="settings-new-password">New password</label><PasswordInput id="settings-new-password" autoComplete="new-password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} required /></div>
        <p className="ui-help">Use a password that meets the system’s password requirements.</p>
        <div className="ui-field"><label className="ui-label" htmlFor="settings-confirm-password">Confirm new password</label><PasswordInput id="settings-confirm-password" autoComplete="new-password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} required /></div>
        <div className="settings-actions"><button type="submit" className="ui-btn" disabled={busy || !oldPassword || !newPassword || !confirmPassword}>{busy ? "Updating…" : "Update password"}</button></div>
        <Message msg={msg} />
      </form>
    </Section>
  );
}

// ------------------------------------------------------------------ 6. help and about
function HelpSection({ user, headingRef }) {
  const steps = HELP_STEPS[roleKey(user)] || HELP_STEPS.student;
  const notSet = <span className="settings-placeholder">Not set yet</span>;
  const topics = ["Gen Ed move requests", "Generate Schedule", "Print / Preview", "Exam Schedule", "My Schedule", "My Profile", "Data Tools", "Unavailable times", "Availability", "Schedules", "Conflicts", "Sections", "Curriculum", "Accounts", "Analytics", "Calendar", "Settings", "Faculty", "Overview", "Activity", "The bell", "Each class", "Home"];
  const splitStep = (step) => {
    const topic = topics.find((candidate) => step.startsWith(candidate));
    const words = step.split(/\s+/);
    const title = topic || words.slice(0, Math.min(3, words.length)).join(" ");
    const description = topic ? step.slice(topic.length).replace(/^[:\s]+/, "") : words.slice(3).join(" ");
    return { title: title.replace(/[.:]$/, ""), description };
  };
  return (
    <Section id="help" title="Help and about" icon="help" headingRef={headingRef}
      intro="Learn how to use U-FAST, get support, and see system information.">
      <div className="settings-help-layout">
        <section className="settings-help-card settings-getting-started" aria-labelledby="getting-started-heading">
          <div className="settings-help-card-heading"><SettingsIcon name="rocket" /><div><h3 id="getting-started-heading">Getting started</h3><p>A quick guide to common tasks in U-FAST.</p></div></div>
          <ol className="settings-steps">{steps.map((step, i) => {
            const { title, description } = splitStep(step);
            return <li key={i}><span className="settings-step-number">{i + 1}</span><div><strong>{title}</strong><span>{description}</span></div></li>;
          })}</ol>
        </section>
        <div className="settings-help-right">
          <section className="settings-help-card" aria-labelledby="more-help-heading">
            <div className="settings-help-card-heading"><SettingsIcon name="book" /><div><h3 id="more-help-heading">More help</h3><p>Detailed guides for specific tasks.</p></div></div>
            <details className="settings-help-details">
              <summary><SettingsIcon name="book" /><span>How to use this tab</span><span className="settings-help-chevron">›</span></summary>
              <p>Use the sections on the left to open profile, appearance, language, display, notification, and account options. Changes are saved only when you press Save.</p>
            </details>
          </section>
          <section className="settings-help-card" aria-labelledby="contact-support-heading">
            <div className="settings-help-card-heading"><SettingsIcon name="headset" /><div><h3 id="contact-support-heading">Contact support</h3><p>Reach out if you need assistance.</p></div></div>
            <dl className="settings-support-list">
              <div><dt><SettingsIcon name="mail" />Email</dt><dd>{SUPPORT.email ? <a href={`mailto:${SUPPORT.email}`}>{SUPPORT.email}</a> : notSet}</dd></div>
              <div><dt><SettingsIcon name="phone" />Phone</dt><dd>{SUPPORT.phone || notSet}</dd></div>
              <div><dt><SettingsIcon name="pin" />Office</dt><dd>{SUPPORT.location || notSet}</dd></div>
            </dl>
          </section>
          <section className="settings-help-card" aria-labelledby="about-heading">
            <div className="settings-help-card-heading"><SettingsIcon name="info" /><div><h3 id="about-heading">About U-FAST</h3><p>System details and version information.</p></div></div>
            <dl className="settings-about-grid">
              <div><dt>System</dt><dd>{APP_INFO.name}</dd></div>
              <div><dt>Full name</dt><dd>{APP_INFO.fullName}</dd></div>
              <div><dt>Version</dt><dd>{APP_INFO.version}</dd></div>
              <div><dt>Last updated</dt><dd>{formatDate(APP_INFO.lastUpdated)}</dd></div>
              <div><dt>School</dt><dd>{APP_INFO.school}</dd></div>
            </dl>
          </section>
        </div>
      </div>
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
    : !data && active !== "help" && active !== "password" ? (
      <div className="ui-panel settings-section"><p className="settings-msg err">Your settings could not be loaded. Check your connection and reload the page.</p></div>
    ) : {
      profile: <ProfileSection headingRef={headingRef} />,
      appearance: <AppearanceSection headingRef={headingRef} />,
      format: <FormatSection headingRef={headingRef} />,
      display: <DisplaySection headingRef={headingRef} />,
      notifications: <NotificationsSection headingRef={headingRef} />,
      password: <ChangePasswordSection headingRef={headingRef} />,
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

import React from "react";
import logo from "../assets/uphsl_logo.png";

function SectionIcon({ group }) {
  const name = group.toLowerCase();
  let paths;
  if (name.includes("plan")) {
    paths = <><rect x="3.5" y="4.5" width="13" height="12" rx="2" /><path d="M7 2.8v3.4M13 2.8v3.4M3.8 8h12.4M7 11h2m2 0h2M7 14h2" /></>;
  } else if (name.includes("academic") || name.includes("curriculum")) {
    paths = <><path d="M2.8 4.8c2.8-.7 5.2-.2 7.2 1.4v10c-2-1.6-4.4-2.1-7.2-1.4z" /><path d="M17.2 4.8c-2.8-.7-5.2-.2-7.2 1.4v10c2-1.6 4.4-2.1 7.2-1.4z" /></>;
  } else if (name.includes("people")) {
    paths = <><circle cx="8" cy="7" r="3" /><path d="M2.8 17c.5-2.8 2.3-4.2 5.2-4.2s4.7 1.4 5.2 4.2zM14 4.4a2.7 2.7 0 0 1 0 5.2M14.2 13c1.8.4 2.8 1.7 3.1 4" /></>;
  } else if (name.includes("management")) {
    paths = <><circle cx="10" cy="10" r="3" /><path d="m10 2.8 1 .4.5 1.6 1.5.9 1.7-.4 1.1 1.9-1.1 1.3v1.8l1.1 1.3-1.1 1.9-1.7-.4-1.5.9-.5 1.6-2 .1-.5-1.7-1.5-.9-1.7.4-1.1-1.9 1.1-1.3V8.5L3.4 7.2l1.1-1.9 1.7.4 1.5-.9.5-1.7z" /></>;
  } else if (name.includes("data")) {
    paths = <><ellipse cx="10" cy="4.5" rx="6.5" ry="2.3" /><path d="M3.5 4.5v5.3c0 1.3 2.9 2.3 6.5 2.3s6.5-1 6.5-2.3V4.5M3.5 9.8v5.3c0 1.3 2.9 2.3 6.5 2.3s6.5-1 6.5-2.3V9.8" /></>;
  } else {
    paths = <><path d="M3 17V9m5 8V5m5 12v-5m5 5V7M2 17.5h16" /></>;
  }
  return <svg className="app-nav-section-icon" viewBox="0 0 20 20" aria-hidden="true">{paths}</svg>;
}

function Chevron({ collapsed }) {
  return <svg className={collapsed ? "app-nav-chevron collapsed" : "app-nav-chevron"} viewBox="0 0 16 16" aria-hidden="true"><path d="m4 6 4 4 4-4" /></svg>;
}

function NavIcon({ item }) {
  const key = `${item.key} ${item.label}`.toLowerCase();
  let paths;
  if (key.includes("home") || key.includes("overview")) {
    paths = <><path d="m3 10 9-7 9 7" /><path d="M5 9v11h14V9M9 20v-7h6v7" /></>;
  } else if (key.includes("generate")) {
    paths = <><path d="M12 3v5m0 8v5m9-9h-5m-8 0H3m15.4-6.4-3.5 3.5m-5.8 5.8-3.5 3.5m12.8 0-3.5-3.5m-5.8-5.8-3.5-3.5" /><path d="M12 9.5v5m2.5-2.5h-5" /></>;
  } else if (key.includes("minor")) {
    paths = <><path d="m12 3 9 4.5-9 4.5-9-4.5z" /><path d="m3 12 9 4.5 9-4.5M3 16.5 12 21l9-4.5" /></>;
  } else if (key.includes("exam")) {
    paths = <><rect x="5" y="4" width="14" height="17" rx="2" /><path d="M9 4V3h6v1M8 10h8m-8 4h5" /><path d="m14 17 1.5 1.5L19 15" /></>;
  } else if (key.includes("coverage")) {
    paths = <><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20c.4-3.5 2.6-5.5 6.5-5.5s6.1 2 6.5 5.5M18 7v6m-3-3h6" /></>;
  } else if (key.includes("availability")) {
    paths = <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>;
  } else if (key.includes("conflict")) {
    paths = <><path d="m12 3 9 17H3z" /><path d="M12 9v4m0 3h.01" /></>;
  } else if (key.includes("curriculum")) {
    paths = <><path d="M3 5c3-1 6-.5 9 1.5V21c-3-2-6-2.5-9-1.5z" /><path d="M21 5c-3-1-6-.5-9 1.5V21c3-2 6-2.5 9-1.5z" /></>;
  } else if (key.includes("analytics")) {
    paths = <><path d="M4 20V11m5 9V5m5 15v-7m5 7V8M2 20h20" /></>;
  } else if (key.includes("activity")) {
    paths = <><circle cx="12" cy="12" r="9" /><path d="M5 12h3l2-4 3.5 8 2-4H19" /></>;
  } else if (key.includes("audit")) {
    paths = <><rect x="5" y="4" width="14" height="17" rx="2" /><path d="M9 4V3h6v1M8 10h8m-8 4h8m-8 4h5" /></>;
  } else if (key.includes("data")) {
    paths = <><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v7c0 1.7 3.6 3 8 3s8-1.3 8-3V5m-16 7v7c0 1.7 3.6 3 8 3s8-1.3 8-3v-7" /></>;
  } else if (key.includes("room")) {
    paths = <><path d="M4 21V4h16v17M2 21h20M9 21v-6h6v6M8 8h1m6 0h1m-8 4h1m6 0h1" /></>;
  } else if (key.includes("faculty") || key.includes("people") || key.includes("account") || key.includes("classlist")) {
    paths = <><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20c.4-3.5 2.6-5.5 6.5-5.5s6.1 2 6.5 5.5M16 5.5a3.5 3.5 0 0 1 0 6.8m1.5 2.4c2.1.8 3.3 2.5 3.5 5.3" /></>;
  } else if (key.includes("profile")) {
    paths = <><circle cx="12" cy="8" r="4" /><path d="M4 21c.5-4.1 3.2-6.5 8-6.5s7.5 2.4 8 6.5z" /></>;
  } else if (key.includes("setting")) {
    paths = <><circle cx="12" cy="12" r="3" /><path d="m19.4 15 .1.1 1.4 1.1-1.5 2.6-1.7-.6a8 8 0 0 1-1.8 1l-.3 1.8h-3l-.3-1.8a8 8 0 0 1-1.8-1l-1.7.6-1.5-2.6 1.4-1.1a7 7 0 0 1 0-2l-1.4-1.1 1.5-2.6 1.7.6a8 8 0 0 1 1.8-1l.3-1.8h3l.3 1.8a8 8 0 0 1 1.8 1l1.7-.6 1.5 2.6-1.4 1.1a7 7 0 0 1 0 2z" /></>;
  } else if (key.includes("section")) {
    paths = <><rect x="3" y="3" width="8" height="8" rx="1" /><rect x="13" y="3" width="8" height="8" rx="1" /><rect x="3" y="13" width="8" height="8" rx="1" /><rect x="13" y="13" width="8" height="8" rx="1" /></>;
  } else if (key.includes("calendar") || key.includes("schedule") || key.includes("timetable")) {
    paths = <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M7 3v4m10-4v4M3 10h18" /><path d="M8 14h.01m4 0h.01m4 0h.01M8 17h.01m4 0h.01m4 0h.01" /></>;
  } else {
    paths = <><rect x="4" y="4" width="16" height="16" rx="2" /><path d="M8 8h8m-8 4h8m-8 4h5" /></>;
  }
  return <svg className="app-nav-item-icon" viewBox="0 0 24 24" aria-hidden="true">{paths}</svg>;
}

/**
 * Shared sidebar used by every dashboard: school logo and name, text navigation (the current page has a left bar),
 * the signed-in user with role, and Sign out. Items' "icon" field is no longer shown (menus are text only).
 *
 * items: [{ key, label, icon }] and optional section headings { group: "Plan" }
 */
function Sidebar({ brandLabel, workspaceLabel, items, activeKey, onSelect, onPrefetch, userName, userRole, onSignOut }) {
  const [collapsedGroups, setCollapsedGroups] = React.useState({});
  const [sidebarCollapsed, setSidebarCollapsed] = React.useState(() => {
    try { return localStorage.getItem("app_sidebar_collapsed") === "true"; }
    catch { return false; }
  });
  const [navTooltip, setNavTooltip] = React.useState(null);
  const [compactNav, setCompactNav] = React.useState(false);
  React.useEffect(() => {
    const media = typeof window.matchMedia === "function" ? window.matchMedia("(max-width: 820px)") : null;
    if (!media) { setCompactNav(window.innerWidth <= 820); return undefined; }
    const update = () => setCompactNav(media.matches);
    update();
    media.addEventListener?.("change", update);
    return () => media.removeEventListener?.("change", update);
  }, []);

  const sections = [];
  let currentSection = null;
  items.forEach((item) => {
    if (item.group) {
      currentSection = { group: item.group, items: [] };
      sections.push(currentSection);
    } else if (currentSection) {
      currentSection.items.push(item);
    } else {
      sections.push({ item });
    }
  });

  const activeSection = sections.find((section) => section.items?.some((item) => item.key === activeKey))?.group;
  React.useEffect(() => {
    if (activeSection) setCollapsedGroups((old) => old[activeSection] ? { ...old, [activeSection]: false } : old);
  }, [activeSection]);

  const toggleGroup = (group) => setCollapsedGroups((old) => ({ ...old, [group]: !old[group] }));
  const toggleSidebar = () => setSidebarCollapsed((old) => {
    const next = !old;
    try { localStorage.setItem("app_sidebar_collapsed", String(next)); } catch { /* optional preference */ }
    setNavTooltip(null);
    return next;
  });
  const showNavTooltip = (label, element) => {
    if (!sidebarCollapsed || compactNav) return;
    const rect = element.getBoundingClientRect();
    setNavTooltip({ label, top: rect.top + rect.height / 2, left: rect.right + 9 });
  };
  const prefetch = (item) => onPrefetch?.(item.key);
  const navItem = (item) => (
    <li key={item.key}>
      <button
        type="button"
        className={activeKey === item.key ? "app-nav-item active" : "app-nav-item"}
        aria-current={activeKey === item.key ? "page" : undefined}
        title={sidebarCollapsed ? item.label : undefined}
        aria-label={item.label}
        aria-describedby={sidebarCollapsed && !compactNav ? "app-sidebar-nav-tooltip" : undefined}
        onMouseEnter={(event) => { if (item.key === "curriculum") prefetch(item); showNavTooltip(item.label, event.currentTarget); }}
        onMouseLeave={() => setNavTooltip(null)}
        onFocus={(event) => showNavTooltip(item.label, event.currentTarget)}
        onBlur={() => setNavTooltip(null)}
        onClick={() => { prefetch(item); onSelect(item.key); }}
      >
        <NavIcon item={item} />
        <span className="app-nav-item-label">{item.label}</span>
      </button>
    </li>
  );

  const initials = (userName || "?")
    .replace(/^(dr|mr|ms|mrs|engr|prof)\.?\s+/i, "")
    .split(/[\s-]+/)
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  return (
    <div className={`app-sidebar${sidebarCollapsed ? " is-collapsed" : ""}`}>
      <div className="app-sidebar-brand">
        <img src={logo} alt="UPHSL U-FAST logo" className="app-sidebar-logo-img" />
        <div className="app-sidebar-brand-copy">
          <div className="app-sidebar-brand-name">{brandLabel}</div>
          <div className="app-sidebar-brand-sub">{workspaceLabel}</div>
        </div>
        <button
          type="button"
          className="app-sidebar-toggle"
          onClick={toggleSidebar}
          aria-label={sidebarCollapsed ? "Expand navigation" : "Collapse navigation"}
          title={sidebarCollapsed ? "Expand navigation" : "Collapse navigation"}
          aria-expanded={!sidebarCollapsed}
        >
          <svg viewBox="0 0 20 20" aria-hidden="true"><path d={sidebarCollapsed ? "M7 4l6 6-6 6" : "M13 4l-6 6 6 6"} /></svg>
        </button>
      </div>

      <ul className="app-sidebar-nav">
        {sections.map((section) => {
          if (section.item) return navItem(section.item);
          const collapsed = !compactNav && Boolean(collapsedGroups[section.group]);
          const groupId = `sidebar-${section.group.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
          const containsActive = section.items.some((item) => item.key === activeKey);
          return (
            <li key={`g-${section.group}`} className={`app-nav-section${containsActive ? " has-active" : ""}`}>
              <button
                type="button"
                className="app-nav-section-header"
                title={sidebarCollapsed ? section.group : undefined}
                aria-label={section.group}
                aria-describedby={sidebarCollapsed && !compactNav ? "app-sidebar-nav-tooltip" : undefined}
                aria-expanded={!collapsed}
                aria-controls={groupId}
                onMouseEnter={(event) => showNavTooltip(section.group, event.currentTarget)}
                onMouseLeave={() => setNavTooltip(null)}
                onFocus={(event) => showNavTooltip(section.group, event.currentTarget)}
                onBlur={() => setNavTooltip(null)}
                onClick={() => toggleGroup(section.group)}
              >
                <SectionIcon group={section.group} />
                <span className="app-nav-section-name">{section.group}</span>
                {!sidebarCollapsed && <Chevron collapsed={collapsed} />}
              </button>
              <div id={groupId} className={`app-nav-subnav-panel${collapsed ? " is-collapsed" : ""}`} aria-hidden={collapsed} inert={collapsed ? "" : undefined}>
                <div className="app-nav-subnav-inner">
                  <ul className="app-nav-subnav">
                  {section.items.map(navItem)}
                  </ul>
                </div>
              </div>
            </li>
          );
        })}
      </ul>

      <div className="app-sidebar-user">
        <div className="app-avatar-circle">{initials}</div>
        <div className="app-sidebar-user-copy" style={{ flex: 1, minWidth: 0 }}>
          <div className="app-sidebar-user-name">{userName}</div>
          <div className="app-sidebar-user-role">{userRole}</div>
        </div>
      </div>
      <button className="app-sidebar-signout" onClick={onSignOut} title={sidebarCollapsed ? "Sign out" : undefined}>
        <span className="app-sidebar-signout-label">Sign out</span>
        <span className="app-sidebar-signout-compact" aria-hidden="true">↪</span>
      </button>
      {sidebarCollapsed && !compactNav && navTooltip && (
        <div
          id="app-sidebar-nav-tooltip"
          className="app-sidebar-nav-tooltip"
          role="tooltip"
          style={{ top: navTooltip.top, left: navTooltip.left }}
        >
          {navTooltip.label}
        </div>
      )}
    </div>
  );
}

export default Sidebar;

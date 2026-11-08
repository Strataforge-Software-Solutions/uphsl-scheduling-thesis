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

/**
 * Shared sidebar used by every dashboard: school logo and name, text navigation (the current page has a left bar),
 * the signed-in user with role, and Sign out. Items' "icon" field is no longer shown (menus are text only).
 *
 * items: [{ key, label, icon }] and optional section headings { group: "Plan" }
 */
function Sidebar({ brandLabel, workspaceLabel, items, activeKey, onSelect, userName, userRole, onSignOut }) {
  const [collapsedGroups, setCollapsedGroups] = React.useState({});

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

  const toggleGroup = (group) => setCollapsedGroups((old) => ({ ...old, [group]: !old[group] }));
  const navItem = (item) => (
    <li key={item.key}>
      <button
        type="button"
        className={activeKey === item.key ? "app-nav-item active" : "app-nav-item"}
        aria-current={activeKey === item.key ? "page" : undefined}
        onClick={() => onSelect(item.key)}
      >
        {item.label}
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
    <div className="app-sidebar">
      <div className="app-sidebar-brand">
        <img src={logo} alt="UPHSL U-FAST logo" className="app-sidebar-logo-img" />
        <div>
          <div className="app-sidebar-brand-name">{brandLabel}</div>
          <div className="app-sidebar-brand-sub">{workspaceLabel}</div>
        </div>
      </div>

      <ul className="app-sidebar-nav">
        {sections.map((section) => {
          if (section.item) return navItem(section.item);
          const collapsed = Boolean(collapsedGroups[section.group]);
          const groupId = `sidebar-${section.group.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
          const containsActive = section.items.some((item) => item.key === activeKey);
          return (
            <li key={`g-${section.group}`} className={`app-nav-section${containsActive ? " has-active" : ""}`}>
              <button
                type="button"
                className="app-nav-section-header"
                aria-expanded={!collapsed}
                aria-controls={groupId}
                onClick={() => toggleGroup(section.group)}
              >
                <SectionIcon group={section.group} />
                <span className="app-nav-section-name">{section.group}</span>
                <Chevron collapsed={collapsed} />
              </button>
              {!collapsed && (
                <ul className="app-nav-subnav" id={groupId}>
                  {section.items.map(navItem)}
                </ul>
              )}
            </li>
          );
        })}
      </ul>

      <div className="app-sidebar-user">
        <div className="app-avatar-circle">{initials}</div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="app-sidebar-user-name">{userName}</div>
          <div className="app-sidebar-user-role">{userRole}</div>
        </div>
      </div>
      <button className="app-sidebar-signout" onClick={onSignOut}>Sign out</button>
    </div>
  );
}

export default Sidebar;

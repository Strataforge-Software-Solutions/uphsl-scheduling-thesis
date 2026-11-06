import React from "react";
import logo from "../assets/uphsl_logo.png";

/**
 * Shared sidebar used by every dashboard: school logo and name, text navigation (the current page has a left bar),
 * the signed-in user with role, and Sign out. Items' "icon" field is no longer shown (menus are text only).
 *
 * items: [{ key, label, icon }] and optional section headings { group: "Plan" }
 */
function Sidebar({ brandLabel, workspaceLabel, items, activeKey, onSelect, userName, userRole, onSignOut }) {
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
        {items.map((item) => item.group ? (
          <li key={"g-" + item.group} className="app-nav-group">{item.group}</li>
        ) : (
          <li key={item.key}>
            <button
              className={activeKey === item.key ? "app-nav-item active" : "app-nav-item"}
              aria-current={activeKey === item.key ? "page" : undefined}
              onClick={() => onSelect(item.key)}
            >
              {item.label}
            </button>
          </li>
        ))}
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

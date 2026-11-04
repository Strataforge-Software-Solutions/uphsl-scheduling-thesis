import React from "react";

// tone: "success" (green, e.g. Generated/Active) | "warning" (amber, e.g. Manual Override/First login) | "neutral"
function Badge({ tone = "neutral", children }) {
  return <span className={`app-badge app-badge-${tone}`}>{children}</span>;
}

export default Badge;

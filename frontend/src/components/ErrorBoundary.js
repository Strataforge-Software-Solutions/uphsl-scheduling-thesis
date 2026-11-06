import React from "react";

/* Catches a rendering error in its children and shows a short message in their place instead of a blank page. The error is still
   logged to the console (it is not hidden). `row` renders the message as a table row (for use inside a <tbody>). */
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error(`Display error in ${this.props.what || "this part of the page"}:`, error, info?.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    const text = `Something went wrong while showing ${this.props.what || "this part of the page"}. The rest of the page still works; `
      + "please reload, and report it if it happens again.";
    const msg = <span style={{ color: "#b91c1c", fontSize: 12.5 }}>{text} <span style={{ color: "#6b7280" }}>({String(error.message || error)})</span></span>;
    if (this.props.row) return <tr><td colSpan={this.props.colSpan || 1} style={{ background: "#fef2f2" }}>{msg}</td></tr>;
    return (
      <div role="alert" style={{ border: "1px solid #fecaca", background: "#fef2f2", borderRadius: 6, padding: "10px 12px", margin: "8px 0" }}>
        {msg}
        <div style={{ marginTop: 8 }}>
          <button type="button" onClick={() => this.setState({ error: null })}
            style={{ background: "#003366", color: "white", border: "none", borderRadius: 4, padding: "6px 12px", fontSize: 13, cursor: "pointer" }}>Try again</button>
        </div>
      </div>
    );
  }
}

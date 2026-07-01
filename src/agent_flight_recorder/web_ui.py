"""Local web dashboard for AgentFlightRecorder."""

from __future__ import annotations

from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from agent_flight_recorder.commands import relativize_cwd
from agent_flight_recorder.reports import SessionReport, format_timestamp
from agent_flight_recorder.reports import build_session_report
from agent_flight_recorder.store import RecorderStore


def serve_web_dashboard(
    *,
    repo_root: Path,
    host: str,
    port: int,
    session_id: int | None,
) -> None:
    """Serve the local web dashboard until interrupted."""

    handler = build_dashboard_handler(repo_root=repo_root, session_id=session_id)
    server = ThreadingHTTPServer((host, port), handler)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def build_dashboard_handler(
    *,
    repo_root: Path,
    session_id: int | None,
) -> type[BaseHTTPRequestHandler]:
    """Build a request handler bound to one repository."""

    resolved_repo = repo_root.resolve()

    class DashboardHandler(BaseHTTPRequestHandler):
        server_version = "AgentFlightRecorderWeb/0.1"

        def do_GET(self) -> None:  # noqa: N802
            if self.path not in {"/", "/index.html"}:
                self.send_error(404, "not found")
                return

            try:
                html = load_dashboard_html(resolved_repo, session_id=session_id)
            except LookupError as error:
                self.send_response(404)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(f"afr: {error}\n".encode("utf-8"))
                return

            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    return DashboardHandler


def load_dashboard_html(repo_root: Path, *, session_id: int | None) -> str:
    """Load recorder state and render dashboard HTML."""

    store = RecorderStore.open_for_repo(repo_root)
    session = store.get_session(session_id) if session_id is not None else None
    if session is None and session_id is not None:
        raise LookupError(f"session {session_id} was not found")

    if session is None:
        session = store.get_active_session() or store.get_latest_session()
    if session is None:
        raise LookupError("no recorded sessions")

    report = build_session_report(store, session)
    return render_web_dashboard(report, repo_root=repo_root)


def render_web_dashboard(report: SessionReport, *, repo_root: Path) -> str:
    """Render a self-contained HTML dashboard for one session."""

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgentFlightRecorder Session {report.session.id}</title>
  <style>
    :root {{
      color: #14213d;
      background: #f7f8fb;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    body {{ margin: 0; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 32px 20px 48px; }}
    header {{ display: flex; justify-content: space-between; gap: 24px; align-items: flex-start; }}
    h1 {{ margin: 0 0 8px; font-size: 28px; line-height: 1.15; }}
    h2 {{ margin: 0 0 12px; font-size: 17px; }}
    p {{ margin: 0; color: #526071; }}
    code {{ font-family: "SFMono-Regular", Consolas, monospace; }}
    .status {{ color: #0f766e; font-weight: 700; }}
    .grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 24px 0; }}
    .panel {{ background: #fff; border: 1px solid #dbe2ea; border-radius: 8px; padding: 16px; }}
    .metric {{ display: block; font-size: 26px; font-weight: 750; margin-top: 6px; }}
    .stack {{ display: grid; gap: 12px; }}
    .row {{ display: flex; justify-content: space-between; gap: 16px; border-top: 1px solid #edf1f5; padding-top: 10px; margin-top: 10px; }}
    .muted {{ color: #697789; }}
    .risk-high {{ color: #b42318; font-weight: 700; }}
    .risk-medium {{ color: #b54708; font-weight: 700; }}
    .risk-low {{ color: #175cd3; font-weight: 700; }}
    ul {{ margin: 0; padding-left: 18px; }}
    li + li {{ margin-top: 8px; }}
    @media (max-width: 760px) {{
      header {{ display: block; }}
      .grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>AgentFlightRecorder</h1>
        <p>Session {report.session.id} <span class="status">{escape(report.session.status)}</span></p>
      </div>
      <p><code>{escape(str(report.session.repo_root))}</code></p>
    </header>

    <section class="grid" aria-label="Session summary">
      {render_metric("Files", snapshot_value(report, "files_changed"))}
      {render_metric("Diff", snapshot_diff(report))}
      {render_metric("Failed", str(len(report.failed_commands)))}
    </section>

    <section class="stack">
      {render_session_panel(report)}
      {render_risks_panel(report)}
      {render_commands_panel(report, repo_root=repo_root)}
      {render_next_checks_panel(report)}
    </section>
  </main>
</body>
</html>
"""


def render_metric(label: str, value: str) -> str:
    """Render one summary metric."""

    return (
        '<article class="panel">'
        f'<span class="muted">{escape(label)}</span>'
        f'<strong class="metric">{escape(value)}</strong>'
        "</article>"
    )


def render_session_panel(report: SessionReport) -> str:
    """Render basic session timestamps."""

    return f"""
      <section class="panel">
        <h2>Session</h2>
        <div class="row"><span>Started</span><code>{escape(format_timestamp(report.session.started_at))}</code></div>
        <div class="row"><span>Stopped</span><code>{escape(format_timestamp(report.session.stopped_at))}</code></div>
      </section>
    """


def render_risks_panel(report: SessionReport) -> str:
    """Render risk findings."""

    if not report.risks:
        body = '<p class="muted">No risk findings.</p>'
    else:
        items = "\n".join(
            f'<li><span class="risk-{escape(risk.severity)}">[{escape(risk.severity)}]</span> '
            f"{escape(risk.summary)} <span class=\"muted\">{escape(risk.detail)}</span></li>"
            for risk in report.risks[:10]
        )
        body = f"<ul>{items}</ul>"

    return f"""
      <section class="panel">
        <h2>Risks</h2>
        {body}
      </section>
    """


def render_commands_panel(report: SessionReport, *, repo_root: Path) -> str:
    """Render recent command evidence."""

    if not report.commands:
        body = '<p class="muted">No commands recorded.</p>'
    else:
        rows = []
        for command in report.commands[:10]:
            cwd = relativize_cwd(command.cwd, repo_root)
            rows.append(
                '<div class="row">'
                f"<span>{escape(command.command_kind)} exit {command.exit_code}</span>"
                f"<code>{escape(cwd)} · {escape(command.command_text)}</code>"
                "</div>"
            )
        body = "\n".join(rows)

    return f"""
      <section class="panel">
        <h2>Commands</h2>
        {body}
      </section>
    """


def render_next_checks_panel(report: SessionReport) -> str:
    """Render suggested next checks."""

    items = "\n".join(f"<li>{escape(suggestion)}</li>" for suggestion in report.next_checks)
    return f"""
      <section class="panel">
        <h2>Next Checks</h2>
        <ul>{items}</ul>
      </section>
    """


def snapshot_value(report: SessionReport, field: str) -> str:
    """Return a snapshot field as display text."""

    if report.latest_snapshot is None:
        return "-"

    return str(getattr(report.latest_snapshot, field))


def snapshot_diff(report: SessionReport) -> str:
    """Render latest snapshot diff totals."""

    if report.latest_snapshot is None:
        return "-"

    return f"+{report.latest_snapshot.additions}/-{report.latest_snapshot.deletions}"

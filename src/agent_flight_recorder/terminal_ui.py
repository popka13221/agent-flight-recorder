"""Lightweight terminal dashboard rendering."""

from __future__ import annotations

from pathlib import Path

from agent_flight_recorder.commands import relativize_cwd
from agent_flight_recorder.reports import SessionReport, format_timestamp


def render_terminal_dashboard(report: SessionReport, *, repo_root: Path) -> str:
    """Render a compact, dependency-free terminal dashboard."""

    lines = [
        "AgentFlightRecorder",
        "=" * 19,
        "",
        f"Session: {report.session.id} ({report.session.status})",
        f"Repo: {report.session.repo_root}",
        f"Started: {format_timestamp(report.session.started_at)}",
        f"Stopped: {format_timestamp(report.session.stopped_at)}",
        "",
        render_snapshot_panel(report),
        "",
        render_risk_panel(report),
        "",
        render_command_panel(report, repo_root=repo_root),
        "",
        render_next_checks_panel(report),
    ]
    return "\n".join(lines).rstrip() + "\n"


def render_snapshot_panel(report: SessionReport) -> str:
    """Render the latest snapshot panel."""

    snapshot = report.latest_snapshot
    if snapshot is None:
        return "Snapshot\n  none recorded"

    return "\n".join(
        [
            "Snapshot",
            f"  id: {snapshot.id}",
            f"  files: {snapshot.files_changed}",
            f"  diff: +{snapshot.additions}/-{snapshot.deletions}",
        ]
    )


def render_risk_panel(report: SessionReport) -> str:
    """Render up to five risk findings."""

    if not report.risks:
        return "Risks\n  none"

    lines = ["Risks"]
    for risk in report.risks[:5]:
        lines.append(f"  [{risk.severity}] {risk.summary}")
    return "\n".join(lines)


def render_command_panel(report: SessionReport, *, repo_root: Path) -> str:
    """Render recent command evidence."""

    if not report.commands:
        return "Commands\n  none recorded"

    lines = [
        "Commands",
        f"  total: {len(report.commands)}",
        f"  failed: {len(report.failed_commands)}",
    ]
    for command in report.commands[:5]:
        cwd = relativize_cwd(command.cwd, repo_root)
        lines.append(
            f"  {command.command_kind:<7} exit {command.exit_code:<3} "
            f"{command.duration_ms:>5} ms  {cwd}  {command.command_text}"
        )
    return "\n".join(lines)


def render_next_checks_panel(report: SessionReport) -> str:
    """Render report-suggested next checks."""

    lines = ["Next checks"]
    lines.extend(f"  - {suggestion}" for suggestion in report.next_checks)
    return "\n".join(lines)

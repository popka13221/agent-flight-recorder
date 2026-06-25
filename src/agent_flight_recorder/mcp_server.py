"""MCP server for exposing AgentFlightRecorder state to coding agents."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from mcp.server.fastmcp import FastMCP

from agent_flight_recorder.repo import resolve_repo_root
from agent_flight_recorder.session_data import (
    build_changed_files_payload,
    build_command_history_payload,
    build_current_session_payload,
    build_risk_report_payload,
    build_session_summary_payload,
)
from agent_flight_recorder.store import RecorderStore


def create_mcp_server(
    repo_root: Path | None = None,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> FastMCP:
    """Create a read-only MCP server for one repository."""

    resolved_repo_root = repo_root.resolve() if repo_root is not None else resolve_repo_root()
    store = RecorderStore.open_for_repo(resolved_repo_root)
    server = FastMCP(
        name="AgentFlightRecorder",
        instructions=(
            "Read-only access to AgentFlightRecorder session data for the current repository. "
            "Use these tools to inspect the active or latest session, changed files, "
            "command history, risk findings, and session summary before handoff."
        ),
        host=host,
        port=port,
        json_response=True,
    )

    @server.tool(
        name="get_current_session",
        title="Current Session",
        description="Return the active AgentFlightRecorder session or the latest recorded session.",
    )
    def get_current_session(event_limit: int = 10) -> dict[str, object]:
        return build_current_session_payload(store, event_limit=event_limit)

    @server.tool(
        name="get_changed_files",
        title="Changed Files",
        description=(
            "Return changed-file details from the live git worktree or from the latest recorded "
            "snapshot for a selected session."
        ),
    )
    def get_changed_files(
        source: Literal["live", "snapshot"] = "live",
        session_id: int | None = None,
    ) -> dict[str, object]:
        return build_changed_files_payload(store, source=source, session_id=session_id)

    @server.tool(
        name="get_command_history",
        title="Command History",
        description="Return recorded commands for the active or selected session.",
    )
    def get_command_history(
        session_id: int | None = None,
        limit: int = 20,
        failed_only: bool = False,
    ) -> dict[str, object]:
        return build_command_history_payload(
            store,
            session_id=session_id,
            limit=limit,
            failed_only=failed_only,
        )

    @server.tool(
        name="get_risk_report",
        title="Risk Report",
        description=(
            "Return recorder risk findings from the live git worktree or from the latest recorded "
            "snapshot for a selected session."
        ),
    )
    def get_risk_report(
        source: Literal["live", "snapshot"] = "live",
        session_id: int | None = None,
    ) -> dict[str, object]:
        return build_risk_report_payload(store, source=source, session_id=session_id)

    @server.tool(
        name="get_session_summary",
        title="Session Summary",
        description=(
            "Return a compact summary of the active or latest session with snapshot status, "
            "command evidence, risk findings, and suggested next checks."
        ),
    )
    def get_session_summary(session_id: int | None = None) -> dict[str, object]:
        return build_session_summary_payload(store, session_id=session_id)

    return server


def run_mcp_server(
    repo_root: Path | None = None,
    *,
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 8000,
) -> int:
    """Run the AgentFlightRecorder MCP server using the chosen transport."""

    server = create_mcp_server(repo_root, host=host, port=port)
    server.run(transport=transport)
    return 0

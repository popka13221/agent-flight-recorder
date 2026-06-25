from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from agent_flight_recorder.store import RecorderStore


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"


def test_mcp_server_exposes_recorder_tools_and_payloads(tmp_path: Path):
    init_repo(tmp_path)
    source_dir = tmp_path / "src" / "agent_flight_recorder"
    source_dir.mkdir(parents=True)
    (source_dir / "mcp_server.py").write_text("FEATURE = True\n", encoding="utf-8")

    store = RecorderStore.open_for_repo(tmp_path)
    session = store.start_session()
    store.record_snapshot(
        session_id=session.id,
        files_changed=1,
        additions=1,
        deletions=0,
        payload={
            "files": [
                {
                    "path": "src/agent_flight_recorder/mcp_server.py",
                    "status": "??",
                    "category": "untracked",
                }
            ],
            "risks": [
                {
                    "code": "missing-tests",
                    "severity": "medium",
                    "summary": "Source changes do not include nearby test updates.",
                    "detail": "Review whether changed modules need coverage updates: mcp_server.",
                    "paths": ["mcp_server"],
                }
            ],
        },
    )

    result = anyio.run(query_mcp_server, tmp_path)

    tool_names = {tool["name"] for tool in result["tools"]}
    assert tool_names == {
        "get_changed_files",
        "get_command_history",
        "get_current_session",
        "get_risk_report",
        "get_session_summary",
    }
    assert result["current"]["session"]["id"] == session.id
    assert result["changed"]["files"][0]["path"] == "src/agent_flight_recorder/mcp_server.py"
    assert result["risk_report"]["risks"][0]["code"] == "missing-tests"
    assert result["summary"]["latest_snapshot"]["files_changed"] == 1


async def query_mcp_server(repo_root: Path) -> dict[str, object]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC_ROOT)
    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "agent_flight_recorder.cli",
            "mcp",
            "--repo",
            str(repo_root),
        ],
        env=env,
        cwd=str(PROJECT_ROOT),
    )

    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            current = await session.call_tool("get_current_session", {"event_limit": 5})
            changed = await session.call_tool("get_changed_files", {"source": "snapshot"})
            risk_report = await session.call_tool("get_risk_report", {"source": "snapshot"})
            summary = await session.call_tool("get_session_summary", {})

            return {
                "tools": [tool.model_dump() for tool in tools.tools],
                "current": current.structuredContent,
                "changed": changed.structuredContent,
                "risk_report": risk_report.structuredContent,
                "summary": summary.structuredContent,
            }


def init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)

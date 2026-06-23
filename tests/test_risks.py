from pathlib import Path

from agent_flight_recorder.repo import GitDiffStat, GitFileChange
from agent_flight_recorder.risks import analyze_risks, findings_from_snapshot_payload


def test_risks_detect_env_files_secret_patterns_and_sensitive_paths(tmp_path: Path):
    env_file = tmp_path / ".env.production"
    env_file.write_text("OPENAI_API_KEY=sk-ABCDEFGHIJKLMNOPQRSTUVWXYZ1234\n", encoding="utf-8")
    workflow = tmp_path / ".github" / "workflows"
    workflow.mkdir(parents=True)
    (workflow / "release.yml").write_text("name: release\n", encoding="utf-8")

    findings = analyze_risks(
        tmp_path,
        [
            GitFileChange(path=".env.production", status_code="A ", category="added"),
            GitFileChange(path=".github/workflows/release.yml", status_code="A ", category="added"),
        ],
        GitDiffStat(files_changed=2, additions=12, deletions=0),
    )

    assert [finding.code for finding in findings] == ["env-files", "secret-patterns", "sensitive-paths"]
    assert findings[0].severity == "high"
    assert ".env.production" in findings[1].detail


def test_risks_detect_large_diff_missing_tests_and_lockfile_gap(tmp_path: Path):
    (tmp_path / "package-lock.json").write_text("{}\n", encoding="utf-8")

    findings = analyze_risks(
        tmp_path,
        [
            GitFileChange(path="src/agent_flight_recorder/reports.py", status_code=" M", category="modified"),
            GitFileChange(path="package.json", status_code=" M", category="modified"),
        ],
        GitDiffStat(files_changed=16, additions=220, deletions=50),
    )

    assert [finding.code for finding in findings] == ["large-diff", "lockfile-gap", "missing-tests"]
    assert findings[0].severity == "medium"
    assert "reports" in findings[2].detail


def test_snapshot_payload_findings_are_rehydrated_in_severity_order():
    findings = findings_from_snapshot_payload(
        {
            "risks": [
                {
                    "code": "missing-tests",
                    "severity": "medium",
                    "summary": "Source changes do not include nearby test updates.",
                    "detail": "Review coverage.",
                    "paths": ["cli"],
                },
                {
                    "code": "env-files",
                    "severity": "high",
                    "summary": "Potential secret-bearing environment files changed.",
                    "detail": "Review .env.",
                    "paths": [".env"],
                },
            ]
        }
    )

    assert [finding.code for finding in findings] == ["env-files", "missing-tests"]
    assert findings[0].paths == (".env",)

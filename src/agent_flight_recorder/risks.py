"""Risk analysis heuristics for repository changes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re

from agent_flight_recorder.repo import GitDiffStat, GitFileChange


SAFE_ENV_FILENAMES = {
    ".env.example",
    ".env.sample",
    ".env.template",
    ".env.dist",
}
SCANNABLE_SUFFIXES = {
    "",
    ".env",
    ".ini",
    ".json",
    ".py",
    ".rst",
    ".sh",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
SENSITIVE_PATH_SEGMENTS = {
    "auth",
    "authentication",
    "authorization",
    "credentials",
    "iam",
    "middleware",
    "oauth",
    "permissions",
    "policies",
    "policy",
    "rbac",
    "secrets",
    "security",
}
SENSITIVE_PATH_PREFIXES = (
    ".github/workflows/",
    "infra/",
    "ops/",
    "terraform/",
)
SENSITIVE_FILENAMES = {
    "Dockerfile",
    "docker-compose.yaml",
    "docker-compose.yml",
}
SOURCE_SUFFIXES = {".c", ".cc", ".go", ".java", ".js", ".jsx", ".py", ".rs", ".ts", ".tsx"}
TEST_MARKERS = (".spec.", ".test.")
MANIFEST_LOCKFILE_GROUPS = (
    (
        {"pyproject.toml", "setup.py", "setup.cfg", "requirements.in"},
        {"poetry.lock", "pdm.lock", "uv.lock"},
    ),
    (
        {"package.json"},
        {"bun.lockb", "package-lock.json", "pnpm-lock.yaml", "yarn.lock"},
    ),
    (
        {"Cargo.toml"},
        {"Cargo.lock"},
    ),
    (
        {"go.mod"},
        {"go.sum"},
    ),
)
KNOWN_SECRET_PATTERNS = {
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    "OpenAI-style key": re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    "Private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
}
GENERIC_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|secret|token|password|passwd)\b\s*[:=]\s*['\"]?([^\s'\"#]{12,})"
)
PLACEHOLDER_SECRET_FRAGMENTS = (
    "changeme",
    "dummy",
    "example",
    "fake",
    "placeholder",
    "sample",
    "test",
    "your_",
)


@dataclass(frozen=True)
class RiskFinding:
    """One risk item detected for the current repository state."""

    code: str
    severity: str
    summary: str
    detail: str
    paths: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        """Convert one risk finding into a stable JSON-friendly payload."""

        return {
            "code": self.code,
            "severity": self.severity,
            "summary": self.summary,
            "detail": self.detail,
            "paths": list(self.paths),
        }


def analyze_risks(
    repo_root: Path,
    changes: list[GitFileChange],
    diff_stat: GitDiffStat,
) -> list[RiskFinding]:
    """Run the current set of repository risk heuristics."""

    findings: list[RiskFinding] = []
    normalized_paths = [normalize_change_path(change.path) for change in changes]

    env_paths = [path for path in normalized_paths if is_risky_env_path(path)]
    if env_paths:
        findings.append(
            RiskFinding(
                code="env-files",
                severity="high",
                summary="Potential secret-bearing environment files changed.",
                detail=f"Review environment files before committing: {format_path_list(env_paths)}.",
                paths=tuple(sorted(env_paths)),
            )
        )

    secret_matches = detect_secret_patterns(repo_root, changes)
    if secret_matches:
        details = ", ".join(
            f"{path} ({', '.join(sorted(patterns))})"
            for path, patterns in sorted(secret_matches.items())
        )
        findings.append(
            RiskFinding(
                code="secret-patterns",
                severity="high",
                summary="Secret-like values were detected in changed files.",
                detail=f"Inspect possible credentials before commit: {details}.",
                paths=tuple(sorted(secret_matches)),
            )
        )

    sensitive_paths = [path for path in normalized_paths if is_sensitive_path(path)]
    if sensitive_paths:
        findings.append(
            RiskFinding(
                code="sensitive-paths",
                severity="medium",
                summary="Security-sensitive paths changed.",
                detail=(
                    "Changes touch authentication, policy, workflow, or infrastructure areas: "
                    f"{format_path_list(sensitive_paths)}."
                ),
                paths=tuple(sorted(sensitive_paths)),
            )
        )

    large_diff = detect_large_diff(diff_stat)
    if large_diff is not None:
        findings.append(large_diff)

    missing_tests = detect_source_changes_without_tests(normalized_paths)
    if missing_tests is not None:
        findings.append(missing_tests)

    lockfile_gap = detect_manifest_lockfile_gap(repo_root, normalized_paths)
    if lockfile_gap is not None:
        findings.append(lockfile_gap)

    return sorted(findings, key=sort_key_for_finding)


def findings_from_snapshot_payload(payload: dict[str, object]) -> list[RiskFinding]:
    """Rehydrate stored risk findings from a snapshot payload."""

    raw_risks = payload.get("risks")
    if not isinstance(raw_risks, list):
        return []

    findings: list[RiskFinding] = []
    for item in raw_risks:
        if not isinstance(item, dict):
            continue
        paths = item.get("paths")
        findings.append(
            RiskFinding(
                code=str(item.get("code", "unknown")),
                severity=str(item.get("severity", "medium")),
                summary=str(item.get("summary", "")),
                detail=str(item.get("detail", "")),
                paths=tuple(str(path) for path in paths) if isinstance(paths, list) else (),
            )
        )

    return sorted(findings, key=sort_key_for_finding)


def detect_secret_patterns(repo_root: Path, changes: list[GitFileChange]) -> dict[str, set[str]]:
    """Scan changed files for strong secret-like markers."""

    matches: dict[str, set[str]] = {}
    for change in changes:
        if is_deleted_change(change):
            continue

        normalized_path = normalize_change_path(change.path)
        if is_docs_or_tests_path(normalized_path):
            continue

        file_path = repo_root / normalized_path
        if not file_path.is_file():
            continue
        if file_path.stat().st_size > 256_000:
            continue
        if not should_scan_file_content(normalized_path, file_path):
            continue

        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        detected = set(find_known_secret_patterns(content))
        detected.update(find_generic_secret_assignments(content))
        if detected:
            matches[normalized_path] = detected

    return matches


def detect_large_diff(diff_stat: GitDiffStat) -> RiskFinding | None:
    """Flag diffs that are likely too large for lightweight review."""

    changed_lines = diff_stat.additions + diff_stat.deletions
    if changed_lines >= 800 or diff_stat.files_changed >= 40:
        severity = "high"
    elif changed_lines >= 250 or diff_stat.files_changed >= 15:
        severity = "medium"
    else:
        return None

    return RiskFinding(
        code="large-diff",
        severity=severity,
        summary="Large diff size increases review risk.",
        detail=(
            f"The working tree currently spans {diff_stat.files_changed} tracked files and "
            f"{changed_lines} changed lines (+{diff_stat.additions}/-{diff_stat.deletions})."
        ),
    )


def detect_source_changes_without_tests(paths: list[str]) -> RiskFinding | None:
    """Flag source edits that do not include nearby test updates."""

    source_modules = sorted(
        normalized_module_name(path)
        for path in paths
        if is_source_path(path)
    )
    source_modules = [module for module in source_modules if module]
    if not source_modules:
        return None

    test_modules = {
        normalized_test_name(path)
        for path in paths
        if is_test_path(path)
    }

    missing_modules = [module for module in source_modules if module not in test_modules]
    if not missing_modules:
        return None

    return RiskFinding(
        code="missing-tests",
        severity="medium",
        summary="Source changes do not include nearby test updates.",
        detail=(
            "Review whether changed modules need coverage updates: "
            f"{', '.join(missing_modules[:5])}."
        ),
        paths=tuple(missing_modules[:5]),
    )


def detect_manifest_lockfile_gap(repo_root: Path, paths: list[str]) -> RiskFinding | None:
    """Flag manifest edits that skipped an existing lockfile."""

    changed_names = {PurePosixPath(path).name for path in paths}
    for manifests, lockfiles in MANIFEST_LOCKFILE_GROUPS:
        changed_manifests = sorted(changed_names & manifests)
        if not changed_manifests:
            continue

        existing_lockfiles = sorted(lockfile for lockfile in lockfiles if (repo_root / lockfile).exists())
        if not existing_lockfiles:
            continue

        changed_lockfiles = changed_names & lockfiles
        if changed_lockfiles:
            continue

        return RiskFinding(
            code="lockfile-gap",
            severity="medium",
            summary="Package manifest changed without a matching lockfile update.",
            detail=(
                f"Changed manifests: {', '.join(changed_manifests)}. "
                f"Expected one of: {', '.join(existing_lockfiles)}."
            ),
            paths=tuple(changed_manifests),
        )

    return None


def find_known_secret_patterns(content: str) -> list[str]:
    """Return labels for strong secret markers found in text."""

    return [label for label, pattern in KNOWN_SECRET_PATTERNS.items() if pattern.search(content)]


def find_generic_secret_assignments(content: str) -> set[str]:
    """Return a generic marker when a secret-like assignment looks real."""

    matches: set[str] = set()
    for key_name, value in GENERIC_SECRET_ASSIGNMENT.findall(content):
        normalized_value = value.lower()
        if any(fragment in normalized_value for fragment in PLACEHOLDER_SECRET_FRAGMENTS):
            continue
        if normalized_value.startswith(("${", "{{", "<")):
            continue
        if len(set(value)) <= 2:
            continue
        matches.add(f"{key_name.lower()} assignment")

    return matches


def is_deleted_change(change: GitFileChange) -> bool:
    """Return whether the change removes a path from the working tree."""

    return change.category == "deleted" or "D" in change.status_code


def normalize_change_path(path: str) -> str:
    """Normalize git rename display paths to the destination path."""

    if " -> " not in path:
        return path

    return path.split(" -> ", maxsplit=1)[1]


def is_risky_env_path(path: str) -> bool:
    """Return whether a path looks like a real environment file."""

    name = PurePosixPath(path).name
    if name in SAFE_ENV_FILENAMES:
        return False
    if name in {".env", ".envrc"}:
        return True
    return name.startswith(".env.")


def should_scan_file_content(path: str, file_path: Path) -> bool:
    """Return whether a changed file should be scanned for secret markers."""

    if is_risky_env_path(path):
        return True

    return file_path.suffix.lower() in SCANNABLE_SUFFIXES


def is_sensitive_path(path: str) -> bool:
    """Return whether a changed path belongs to a security-sensitive area."""

    if path.startswith(SENSITIVE_PATH_PREFIXES):
        return True

    parts = {part.lower() for part in PurePosixPath(path).parts}
    if not parts.isdisjoint(SENSITIVE_PATH_SEGMENTS):
        return True

    return PurePosixPath(path).name in SENSITIVE_FILENAMES


def is_source_path(path: str) -> bool:
    """Return whether a path looks like application source code."""

    pure_path = PurePosixPath(path)
    return path.startswith("src/") and pure_path.suffix.lower() in SOURCE_SUFFIXES


def is_test_path(path: str) -> bool:
    """Return whether a path looks like a test module."""

    pure_path = PurePosixPath(path)
    name = pure_path.name.lower()
    if path.startswith("tests/"):
        return True
    if name.startswith("test_"):
        return True
    return any(marker in name for marker in TEST_MARKERS)


def is_docs_or_tests_path(path: str) -> bool:
    """Return whether a path is likely documentation or test-only."""

    pure_path = PurePosixPath(path)
    name = pure_path.name.lower()
    return path.startswith("tests/") or name.startswith("test_") or pure_path.suffix.lower() in {".md", ".rst"}


def normalized_module_name(path: str) -> str:
    """Return a comparable source module name for one path."""

    stem = PurePosixPath(path).stem
    return "" if stem == "__init__" else stem.lower()


def normalized_test_name(path: str) -> str:
    """Return a comparable module name for one test file path."""

    stem = PurePosixPath(path).stem.lower()
    if stem.startswith("test_"):
        stem = stem[5:]
    if stem.endswith(".test"):
        stem = stem[:-5]
    if stem.endswith(".spec"):
        stem = stem[:-5]
    return stem


def format_path_list(paths: list[str]) -> str:
    """Render a short comma-separated path list."""

    if len(paths) <= 5:
        return ", ".join(paths)

    remaining = len(paths) - 5
    return f"{', '.join(paths[:5])}, and {remaining} more"


def sort_key_for_finding(finding: RiskFinding) -> tuple[int, str, str]:
    """Order findings by severity, then code and summary."""

    severity_order = {"high": 0, "medium": 1, "low": 2}
    return (severity_order.get(finding.severity, 99), finding.code, finding.summary)

"""Heuristic commit message suggestions for the current repository diff."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path

from agent_flight_recorder.store import CommandRecord


DOC_FILENAMES = {"README.md", "ROADMAP.md", "LICENSE", "CHANGELOG.md", "CONTRIBUTING.md"}
DOC_SUFFIXES = {".md", ".rst", ".txt"}
CONFIG_FILENAMES = {
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "tox.ini",
    ".gitignore",
    ".editorconfig",
    "package.json",
    "tsconfig.json",
    "Cargo.toml",
    "Makefile",
}
CI_PREFIXES = (".github/workflows/", "ci/", ".circleci/")
MODULE_SUBJECTS = {
    "cli": "CLI workflow",
    "commands": "command execution tracking",
    "commit_messages": "commit message suggestions",
    "repo": "repository diff parsing",
    "reports": "session reporting",
    "store": "session storage",
}
MODULE_SCOPES = {
    "cli": "cli",
    "commands": "run",
    "commit_messages": "commit-msg",
    "repo": "repo",
    "reports": "report",
    "store": "store",
}


@dataclass(frozen=True)
class CommitFileChange:
    """Minimal changed-file input needed by commit message heuristics."""

    path: str
    status_code: str
    category: str


@dataclass(frozen=True)
class CommitMessageSuggestion:
    """One conventional-commit style suggestion."""

    type: str
    scope: str | None
    description: str
    confidence: str
    rationale: str

    @property
    def message(self) -> str:
        scope = f"({self.scope})" if self.scope else ""
        return f"{self.type}{scope}: {self.description}"


@dataclass(frozen=True)
class CommitEvidence:
    """Evidence surfaced alongside a commit suggestion."""

    files_changed: int
    additions: int
    deletions: int
    area_counts: dict[str, int]
    command_count: int
    successful_verifications: int
    failed_commands: int


@dataclass(frozen=True)
class CommitMessageReport:
    """Rendered commit-intelligence output for one repository state."""

    primary: CommitMessageSuggestion
    alternatives: list[CommitMessageSuggestion]
    changelog: str
    evidence: CommitEvidence
    warnings: list[str]


def build_commit_message_report(
    *,
    changes: list[CommitFileChange],
    additions: int,
    deletions: int,
    commands: list[CommandRecord],
) -> CommitMessageReport:
    """Build commit suggestions from changed files and recorded command evidence."""

    if not changes:
        raise ValueError("no repository changes detected")

    area_counts = count_areas(changes)
    subject = derive_subject(changes, area_counts)
    scope = derive_scope(changes, area_counts)
    primary_type, confidence = choose_primary_type(area_counts, changes, commands)
    primary = build_suggestion(
        suggestion_type=primary_type,
        scope=scope,
        subject=subject,
        confidence=confidence,
        area_counts=area_counts,
        changes=changes,
        commands=commands,
    )

    alternative_types = choose_alternative_types(primary_type, area_counts, commands)
    alternatives = [
        build_suggestion(
            suggestion_type=suggestion_type,
            scope=scope,
            subject=subject,
            confidence="low",
            area_counts=area_counts,
            changes=changes,
            commands=commands,
        )
        for suggestion_type in alternative_types
    ]

    evidence = CommitEvidence(
        files_changed=len(changes),
        additions=additions,
        deletions=deletions,
        area_counts=area_counts,
        command_count=len(commands),
        successful_verifications=count_successful_verifications(commands),
        failed_commands=count_failed_commands(commands),
    )
    warnings = build_warnings(area_counts=area_counts, additions=additions, deletions=deletions, commands=commands)

    return CommitMessageReport(
        primary=primary,
        alternatives=alternatives,
        changelog=build_changelog(primary.description),
        evidence=evidence,
        warnings=warnings,
    )


def render_text_commit_message_report(report: CommitMessageReport) -> str:
    """Render human-readable commit message suggestions."""

    lines = [
        "Primary suggestion:",
        f"  {report.primary.message}",
        f"  Confidence: {report.primary.confidence}",
        f"  Why: {report.primary.rationale}",
        "",
        "Alternative suggestions:",
    ]
    for suggestion in report.alternatives:
        lines.append(f"  {suggestion.message}")

    area_summary = ", ".join(
        f"{area}={count}" for area, count in report.evidence.area_counts.items() if count > 0
    )
    lines.extend(
        [
            "",
            "Changelog snippet:",
            f"  {report.changelog}",
            "",
            "Evidence:",
            (
                f"  Files changed: {report.evidence.files_changed} "
                f"(+{report.evidence.additions}/-{report.evidence.deletions})"
            ),
            f"  Areas: {area_summary or 'other=0'}",
            (
                f"  Recorded commands: {report.evidence.command_count} "
                f"({report.evidence.successful_verifications} successful test/build/check, "
                f"{report.evidence.failed_commands} failed)"
            ),
        ]
    )

    if report.warnings:
        lines.extend(["", "Warnings:"])
        lines.extend(f"  - {warning}" for warning in report.warnings)

    return "\n".join(lines) + "\n"


def render_json_commit_message_report(report: CommitMessageReport) -> str:
    """Render machine-readable commit message suggestions."""

    payload = {
        "primary": suggestion_to_dict(report.primary),
        "alternatives": [suggestion_to_dict(suggestion) for suggestion in report.alternatives],
        "changelog": report.changelog,
        "evidence": asdict(report.evidence),
        "warnings": report.warnings,
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def suggestion_to_dict(suggestion: CommitMessageSuggestion) -> dict[str, object]:
    """Convert one suggestion to a stable JSON payload."""

    payload = asdict(suggestion)
    payload["message"] = suggestion.message
    return payload


def count_areas(changes: list[CommitFileChange]) -> dict[str, int]:
    """Return coarse changed-file area counts."""

    counts = {
        "source": 0,
        "tests": 0,
        "docs": 0,
        "config": 0,
        "ci": 0,
        "other": 0,
    }
    for change in changes:
        counts[classify_path(change.path)] += 1

    return counts


def classify_path(path: str) -> str:
    """Map one changed path into a coarse project area."""

    file_path = Path(path)
    name = file_path.name

    if path.startswith("src/"):
        return "source"
    if path.startswith("tests/") or name.startswith("test_"):
        return "tests"
    if path.startswith(CI_PREFIXES):
        return "ci"
    if name in DOC_FILENAMES or file_path.suffix.lower() in DOC_SUFFIXES:
        return "docs"
    if name in CONFIG_FILENAMES or path.endswith((".toml", ".yaml", ".yml", ".ini")):
        return "config"

    return "other"


def derive_subject(changes: list[CommitFileChange], area_counts: dict[str, int]) -> str:
    """Describe the dominant subject of the current diff."""

    source_modules = list_changed_modules(changes, prefix="src/agent_flight_recorder/")
    if source_modules:
        if "commit_messages" in source_modules:
            return "commit message suggestions"

        dominant_module = source_modules[0]
        return MODULE_SUBJECTS.get(dominant_module, dominant_module.replace("_", " "))

    if area_counts["docs"] and not any(area_counts[area] for area in ("source", "tests", "config", "ci", "other")):
        doc_names = {Path(change.path).name for change in changes}
        if doc_names == {"README.md"}:
            return "README guidance"
        if doc_names == {"ROADMAP.md"}:
            return "roadmap planning"
        return "project documentation"

    if area_counts["tests"] and not any(area_counts[area] for area in ("source", "docs", "config", "ci", "other")):
        test_modules = list_test_modules(changes)
        if test_modules:
            return f"test coverage for {MODULE_SUBJECTS.get(test_modules[0], test_modules[0].replace('_', ' '))}"
        return "test coverage"

    if area_counts["config"] or area_counts["ci"]:
        return "project tooling configuration"

    return "repository updates"


def derive_scope(changes: list[CommitFileChange], area_counts: dict[str, int]) -> str | None:
    """Infer an optional conventional-commit scope."""

    source_modules = list_changed_modules(changes, prefix="src/agent_flight_recorder/")
    if source_modules:
        return MODULE_SCOPES.get(source_modules[0], source_modules[0].replace("_", "-"))

    if area_counts["docs"]:
        doc_names = {Path(change.path).name for change in changes}
        if len(doc_names) == 1:
            return next(iter(doc_names)).removesuffix(".md").lower()
        return "docs"

    if area_counts["tests"]:
        test_modules = list_test_modules(changes)
        if test_modules:
            return MODULE_SCOPES.get(test_modules[0], test_modules[0].replace("_", "-"))
        return "tests"

    if area_counts["config"] or area_counts["ci"]:
        return "tooling"

    return None


def choose_primary_type(
    area_counts: dict[str, int],
    changes: list[CommitFileChange],
    commands: list[CommandRecord],
) -> tuple[str, str]:
    """Infer the most likely conventional-commit type."""

    source_count = area_counts["source"]
    tests_count = area_counts["tests"]
    docs_count = area_counts["docs"]
    config_count = area_counts["config"] + area_counts["ci"]
    other_count = area_counts["other"]

    if docs_count and source_count == tests_count == config_count == other_count == 0:
        return "docs", "high"
    if tests_count and source_count == docs_count == config_count == other_count == 0:
        return "test", "high"
    if config_count and source_count == docs_count == tests_count == other_count == 0:
        return "chore", "high"
    if source_count:
        if has_recovery_signal(commands):
            return "fix", "medium"
        if has_added_source_file(changes):
            return "feat", "high"
        if docs_count or tests_count:
            return "feat", "medium"
        return "refactor", "low"

    return "chore", "low"


def choose_alternative_types(
    primary_type: str,
    area_counts: dict[str, int],
    commands: list[CommandRecord],
) -> list[str]:
    """Return a short distinct list of plausible alternative types."""

    suggestions: list[str] = []
    if primary_type == "feat":
        suggestions.extend(["refactor", "fix"])
    elif primary_type == "fix":
        suggestions.extend(["feat", "refactor"])
    elif primary_type == "refactor":
        suggestions.extend(["feat", "fix"])
    elif primary_type == "docs":
        suggestions.extend(["chore", "refactor"])
    elif primary_type == "test":
        suggestions.extend(["chore", "refactor"])
    else:
        suggestions.extend(["docs" if area_counts["docs"] else "refactor", "feat"])

    if not has_successful_verification(commands):
        suggestions = [suggestion for suggestion in suggestions if suggestion != "fix"] + [
            suggestion for suggestion in suggestions if suggestion == "fix"
        ]

    distinct: list[str] = []
    for suggestion in suggestions:
        if suggestion != primary_type and suggestion not in distinct:
            distinct.append(suggestion)

    return distinct[:2]


def build_suggestion(
    *,
    suggestion_type: str,
    scope: str | None,
    subject: str,
    confidence: str,
    area_counts: dict[str, int],
    changes: list[CommitFileChange],
    commands: list[CommandRecord],
) -> CommitMessageSuggestion:
    """Create one suggestion with a short rationale."""

    description = shorten_description(
        build_description(
            suggestion_type=suggestion_type,
            subject=subject,
            area_counts=area_counts,
            changes=changes,
        ),
        suggestion_type=suggestion_type,
        scope=scope,
    )
    rationale = build_rationale(
        suggestion_type=suggestion_type,
        area_counts=area_counts,
        changes=changes,
        commands=commands,
    )
    return CommitMessageSuggestion(
        type=suggestion_type,
        scope=scope,
        description=description,
        confidence=confidence,
        rationale=rationale,
    )


def build_description(
    *,
    suggestion_type: str,
    subject: str,
    area_counts: dict[str, int],
    changes: list[CommitFileChange],
) -> str:
    """Build the imperative summary for one suggestion type."""

    if suggestion_type == "docs":
        return f"document {subject}"
    if suggestion_type == "test":
        return f"expand {subject}"
    if suggestion_type == "fix":
        return f"fix {subject}"
    if suggestion_type == "refactor":
        return f"refactor {subject}"
    if suggestion_type == "chore":
        return f"update {subject}"

    if has_added_source_file(changes) or area_counts["docs"] == area_counts["tests"] == 0:
        return f"add {subject}"
    return f"improve {subject}"


def build_rationale(
    *,
    suggestion_type: str,
    area_counts: dict[str, int],
    changes: list[CommitFileChange],
    commands: list[CommandRecord],
) -> str:
    """Explain the primary heuristic behind one suggestion."""

    source_count = area_counts["source"]
    tests_count = area_counts["tests"]
    docs_count = area_counts["docs"]
    config_count = area_counts["config"] + area_counts["ci"]
    change_modes = summarize_change_modes(changes)

    if suggestion_type == "docs":
        return f"only documentation files changed ({docs_count} file{pluralize(docs_count)}; {change_modes})"
    if suggestion_type == "test":
        return f"only test files changed ({tests_count} file{pluralize(tests_count)}; {change_modes})"
    if suggestion_type == "chore":
        return f"changes are limited to project tooling/configuration ({config_count} file{pluralize(config_count)})"
    if suggestion_type == "fix":
        return (
            f"source files changed ({source_count}) and the recorded command history shows a "
            "failure followed by successful verification"
        )
    if suggestion_type == "refactor":
        return f"source files changed ({source_count}) without a clear feature-addition signal ({change_modes})"

    evidence = []
    if source_count:
        evidence.append(f"{source_count} source file{pluralize(source_count)}")
    if tests_count:
        evidence.append(f"{tests_count} test file{pluralize(tests_count)}")
    if docs_count:
        evidence.append(f"{docs_count} docs file{pluralize(docs_count)}")
    if config_count:
        evidence.append(f"{config_count} config/ci file{pluralize(config_count)}")

    return f"the diff looks like a user-visible addition across {', '.join(evidence)} ({change_modes})"


def build_warnings(
    *,
    area_counts: dict[str, int],
    additions: int,
    deletions: int,
    commands: list[CommandRecord],
) -> list[str]:
    """Return commit-quality warnings relevant to the current diff."""

    warnings: list[str] = []
    requires_verification = any(area_counts[area] for area in ("source", "config", "ci"))
    if requires_verification and not has_successful_verification(commands):
        warnings.append("No successful test, build, or check command was recorded for this change.")
    if count_failed_commands(commands):
        warnings.append("At least one recorded command failed; review it before committing.")
    if additions + deletions >= 300:
        warnings.append("This diff is relatively large; consider splitting it before committing.")

    return warnings


def build_changelog(description: str) -> str:
    """Convert a summary into a changelog-ready bullet."""

    sentence = description[0].upper() + description[1:]
    if not sentence.endswith("."):
        sentence = f"{sentence}."
    return f"- {sentence}"


def list_changed_modules(changes: list[CommitFileChange], *, prefix: str) -> list[str]:
    """Return distinct module stems changed under one path prefix."""

    modules: list[str] = []
    for change in changes:
        if not change.path.startswith(prefix):
            continue

        relative_path = Path(change.path[len(prefix) :])
        if not relative_path.parts:
            continue

        module_name = relative_path.stem if len(relative_path.parts) == 1 else relative_path.parts[0]
        if module_name not in modules:
            modules.append(module_name)

    return modules


def list_test_modules(changes: list[CommitFileChange]) -> list[str]:
    """Return module stems referenced by test file names."""

    modules: list[str] = []
    for change in changes:
        if not change.path.startswith("tests/"):
            continue

        name = Path(change.path).stem
        if name.startswith("test_"):
            module = name.removeprefix("test_")
            if module not in modules:
                modules.append(module)

    return modules


def has_added_source_file(changes: list[CommitFileChange]) -> bool:
    """Return whether a source file was newly added."""

    return any(classify_path(change.path) == "source" and "A" in change.status_code for change in changes)


def summarize_change_modes(changes: list[CommitFileChange]) -> str:
    """Describe whether the diff mostly adds, updates, or removes files."""

    added = sum(1 for change in changes if "A" in change.status_code or change.status_code == "??")
    deleted = sum(1 for change in changes if "D" in change.status_code)
    renamed = sum(1 for change in changes if "R" in change.status_code)

    if added and not deleted and not renamed:
        return "mostly additions"
    if deleted and not added and not renamed:
        return "mostly deletions"
    if renamed and not added and not deleted:
        return "mostly renames"
    return "mixed updates"


def count_successful_verifications(commands: list[CommandRecord]) -> int:
    """Count successful test/build/check commands."""

    evidence_kinds = {"test", "build", "check"}
    return sum(1 for command in commands if command.command_kind in evidence_kinds and command.exit_code == 0)


def count_failed_commands(commands: list[CommandRecord]) -> int:
    """Count failed commands."""

    return sum(1 for command in commands if command.exit_code != 0)


def has_successful_verification(commands: list[CommandRecord]) -> bool:
    """Return whether any test/build/check command succeeded."""

    return count_successful_verifications(commands) > 0


def has_recovery_signal(commands: list[CommandRecord]) -> bool:
    """Return whether command history suggests a debugging/fix workflow."""

    saw_failure = False
    for command in reversed(commands):
        if command.exit_code != 0:
            saw_failure = True
            continue
        if saw_failure and command.command_kind in {"test", "build", "check"}:
            return True

    return False


def shorten_description(description: str, *, suggestion_type: str, scope: str | None) -> str:
    """Cap summary length near conventional commit norms."""

    prefix = f"{suggestion_type}{f'({scope})' if scope else ''}: "
    max_length = 72 - len(prefix)
    if len(description) <= max_length:
        return description

    truncated = description[: max_length - 3].rstrip()
    return f"{truncated}..."


def pluralize(value: int) -> str:
    """Return an ``s`` suffix when needed."""

    return "" if value == 1 else "s"

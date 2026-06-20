from pathlib import Path
import subprocess

from agent_flight_recorder.repo import categorize_status, list_file_changes, read_diff_stat


def test_list_file_changes_groups_tracked_and_untracked_files(tmp_path: Path):
    init_repo(tmp_path)
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("first\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, check=True)

    tracked.write_text("first\nsecond\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("draft\n", encoding="utf-8")

    changes = list_file_changes(tmp_path)

    assert {(change.path, change.category) for change in changes} == {
        ("notes.txt", "untracked"),
        ("tracked.txt", "modified"),
    }


def test_read_diff_stat_counts_tracked_line_changes(tmp_path: Path):
    init_repo(tmp_path)
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("one\ntwo\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, check=True)

    tracked.write_text("one\nthree\nfour\n", encoding="utf-8")

    diff_stat = read_diff_stat(tmp_path)

    assert diff_stat.files_changed == 1
    assert diff_stat.additions == 2
    assert diff_stat.deletions == 1


def test_categorize_status_handles_common_porcelain_codes():
    assert categorize_status("??") == "untracked"
    assert categorize_status(" M") == "modified"
    assert categorize_status("A ") == "added"
    assert categorize_status("D ") == "deleted"
    assert categorize_status("R ") == "renamed"


def init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=path, check=True)

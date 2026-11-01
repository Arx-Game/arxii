"""Closing keywords may only name the issue the work closes (#4903)."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess

from closing_keywords import branch_issue, message_text, stray_references
import pytest

ROOT = Path(__file__).resolve().parents[2]

# The sentence from 48b8b76bd that closed ApostateCD's open PR #4866.
INCIDENT = "Live on 2026-11-01 the bot fixed #4866 and #4868, and each got a comment"


def test_the_incident_sentence_is_caught():
    # Only the number right after the keyword is closed, as GitHub does it.
    assert stray_references(INCIDENT, "4897") == ["fixed #4866"]


@pytest.mark.parametrize(
    "text",
    ["Closes #12", "fixes: #12", "RESOLVED #12", "closed Arx-Game/arxii#12",
     "fix https://github.com/Arx-Game/arxii/pull/12"],
)  # fmt: skip
def test_every_form_github_honours_is_caught_in_prose(text: str):
    assert stray_references(f"Earlier work {text} for us.", "99") == [text]


# Real PR-body lines that closed an issue they meant to keep open (all closed on merge).
@pytest.mark.parametrize(
    ("line", "own"),
    [
        ("Refs #3751. Do not close #3751.", "3948"),  # PR #3955
        ("This PR delivers the recorder; it intentionally does not close #3934.", "4017"),
        ("no recurrence is verified. Close #4684 only after every current row", "4719"),
    ],
)
def test_prose_that_names_another_issue_is_caught(line: str, own: str):
    assert len(stray_references(line, own)) == 1


def test_deliberate_closing_lines_pass():
    """A PR closing several SonarCloud issues lists them; that must keep working."""
    body = (
        "Closes #4685\nCloses #4686\n- Closes #4687\nCloses #1, closes #2 and fixes #3.\n"
        "- Fixes #3679: several staff-authored hub models are blind to their relations\n"
    )
    assert stray_references(body, "4685") == []


def test_the_work_s_own_issue_and_plain_mentions_pass():
    text = "Closes #4903\n\nThe bot renumbered #4866; a prefix fix (#4868); prefixed #12."
    assert stray_references(text, "4903") == []


def test_branch_issue_and_comment_lines():
    assert branch_issue("chore-4903-stop-stray-closing") == "4903"
    assert branch_issue("fix/4506-ca-trust") == "4506"
    assert branch_issue("main") is None
    scissors = "# ------------------------ >8 ------------------------"
    raw = f"Reword\n# fixes #1 is a git comment\n{scissors}\nfixes #2"
    assert message_text(raw) == "Reword"


def _commit(tmp_path: Path, message: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    repo = tmp_path / "repo"
    (repo / "tools/githooks").mkdir(parents=True)
    for name in ("tools/closing_keywords.py", "tools/githooks/commit-msg"):
        (repo / name).write_bytes((ROOT / name).read_bytes())

    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args], cwd=repo, env=env, capture_output=True, text=True, check=False
        )

    git("init", "-q", "-b", "chore-4903-x")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    git("config", "core.hooksPath", "tools/githooks")
    (repo / "tools/githooks/commit-msg").chmod(0o755)
    git("add", "-A")
    return git("commit", "-q", "-m", message)


def test_the_hook_rejects_the_incident_and_accepts_its_rewording(tmp_path: Path):
    rejected = _commit(tmp_path, f"Fix the dedupe (#4903)\n\n{INCIDENT}")
    assert rejected.returncode != 0
    assert "'fixed #4866'" in rejected.stderr

    accepted = _commit(
        tmp_path / "again", "Fix the dedupe\n\nCloses #4903. The bot renumbered #4866."
    )
    assert accepted.returncode == 0, accepted.stderr


def test_a_reword_during_an_interactive_rebase_keeps_the_branch_issue(tmp_path: Path):
    """HEAD is detached mid-rebase; git records the branch in rebase-merge/head-name."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    first = _commit(tmp_path, "Start")
    assert first.returncode == 0, first.stderr
    repo = tmp_path / "repo"

    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args], cwd=repo, env=env, capture_output=True, text=True, check=False
        )

    git("checkout", "-q", "--detach")
    (repo / ".git/rebase-merge").mkdir()
    (repo / ".git/rebase-merge/head-name").write_text("refs/heads/chore-4903-x\n")
    reworded = git("commit", "-q", "--allow-empty", "-m", "Reword\n\nCloses #4903")
    assert reworded.returncode == 0, reworded.stderr

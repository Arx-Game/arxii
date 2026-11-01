"""The CI driver posts every refusal once, even on the bot's own fix commit (#4897).

Live on 2026-11-01 the bot fixed #4866, which left a resolved comment naming the
merge commit it pushed. Main then moved again, and the next run refused the PR at
that same commit. The duplicate check matched the resolved comment's SHA, so the
refusal was never posted. These drive the real driver's push mode against a
throwaway origin and a stubbed `gh`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
DRIVER = ROOT / "tools/auto_rebase_migration_ci.sh"
SHA = "454a748298576acf0bd11a70677d42c49eed0c1d"

_GH_STUB = """#!/usr/bin/env bash
case "$*" in
  *"--json state,isCrossRepository"*) echo "OPEN false main pr-branch $STUB_SHA" ;;
  *"/comments"*) cat "$STUB_DIR/comments.txt" ;;
  "pr comment"*) cp "${@: -1}" "$STUB_DIR/posted.md" ;;
  *) echo "unexpected gh call: $*" >&2; exit 1 ;;
esac
"""


@pytest.fixture(autouse=True)
def _no_outer_git(monkeypatch: pytest.MonkeyPatch) -> None:
    """A commit hook exports GIT_DIR/GIT_INDEX_FILE; they must not reach the temp repos."""
    for key in [k for k in os.environ if k.startswith("GIT_")]:
        monkeypatch.delenv(key)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _push_refused(tmp_path: Path, earlier_comments: list[str]) -> Path:
    """Run push mode on one refused result; return where a posted comment lands."""
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    work = tmp_path / "work"
    _git(tmp_path, "clone", "-q", str(origin), str(work))
    _git(work, "config", "user.email", "t@example.com")
    _git(work, "config", "user.name", "t")
    (work / "tools").mkdir()
    (work / "tools/auto_rebase_migration.py").write_text("# stand-in\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", "base")
    _git(work, "push", "-q", "origin", "HEAD:main")

    stub = tmp_path / "stub"
    stub.mkdir()
    (stub / "gh").write_text(_GH_STUB)
    (stub / "gh").chmod(0o755)
    (stub / "comments.txt").write_text("\n".join(earlier_comments) + "\n")
    results = tmp_path / "results"
    results.mkdir()
    (results / "4866.json").write_text(
        json.dumps(
            {
                "pr": "4866",
                "status": "refused",
                "reason": "merging main conflicts on more than max_migration.txt",
                "head_ref": "pr-branch",
                "head_sha": SHA,
            }
        )
    )
    env = {
        **os.environ,
        "PATH": f"{stub}:{os.environ['PATH']}",
        "STUB_DIR": str(stub),
        "STUB_SHA": SHA,
        "GITHUB_REPOSITORY": "Arx-Game/arxii",
        "GH_TOKEN": "fake",
    }
    proc = subprocess.run(
        ["bash", str(DRIVER), "push", str(results)],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return stub / "posted.md"


def test_a_refusal_after_the_bots_own_fix_is_posted(tmp_path: Path):
    """The resolved comment names the same SHA; it must not stand in for the refusal."""
    resolved = f"<!-- migration-auto-rebase sha={SHA} status=resolved -->\nRenumbered."

    posted = _push_refused(tmp_path, [resolved])

    assert posted.exists(), "the refusal comment was not posted"
    body = posted.read_text()
    assert f"sha={SHA} status=refused" in body
    assert "conflicts on more than max_migration.txt" in body


def test_a_refusal_already_posted_for_this_head_is_not_repeated(tmp_path: Path):
    refused = f"<!-- migration-auto-rebase sha={SHA} status=refused -->\nNot fixed."

    posted = _push_refused(tmp_path, [refused])

    assert not posted.exists()

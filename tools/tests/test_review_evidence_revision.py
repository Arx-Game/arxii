"""Carry evidence only across reproducible migration transformations (#4990)."""

import os
from pathlib import Path
import subprocess

from auto_rebase_migration import RefusalError, run
import pytest
from review_evidence_revision import BOT_EMAIL, BOT_NAME, reviewed_revision


def sh(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout


def commit(repo: Path, message: str) -> None:
    sh(repo, "add", "-A")
    sh(repo, "commit", "-qm", message)


def add_migration(repo: Path, name: str, dep: str | None) -> None:
    deps = f'[("arxii", "{dep}")]' if dep else "[]"
    directory = repo / "src/world/migrations"
    (directory / f"{name}.py").write_text(
        "from django.db import migrations\n"
        "class Migration(migrations.Migration):\n"
        f"    dependencies = {deps}\n    operations = []\n"
    )
    (directory / "max_migration.txt").write_text(name + "\n")


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for key in list(os.environ):
        if key.startswith("GIT_"):
            monkeypatch.delenv(key)
    path = tmp_path / "repo"
    path.mkdir()
    sh(path, "init", "-q", "-b", "main")
    sh(path, "config", "user.name", BOT_NAME)
    sh(path, "config", "user.email", BOT_EMAIL)
    (path / "src/world/migrations").mkdir(parents=True)
    add_migration(path, "0001_initial", None)
    (path / "feature.txt").write_text("base\n")
    commit(path, "base")
    sh(path, "branch", "pr")
    add_migration(path, "0002_main", "0001_initial")
    commit(path, "main advances")
    sh(path, "checkout", "-q", "pr")
    add_migration(path, "0002_feature", "0001_initial")
    commit(path, "feature")
    sh(path, "commit", "--allow-empty", "-qm", "evidence finalized")
    return path


def update(repo: Path) -> str:
    sh(repo, "update-ref", "refs/remotes/origin/main", "main")
    result = run(repo, "origin/main", "src/world/migrations", check_graph=False)
    assert result.status == "resolved", result.reason
    return sh(repo, "rev-parse", "HEAD").strip()


def test_normal_head_retains_existing_parent_contract(repo: Path):
    head = sh(repo, "rev-parse", "HEAD").strip()
    assert reviewed_revision(repo, head, "main") == sh(repo, "rev-parse", "HEAD^1").strip()


def test_verified_update_preserves_previously_passing_revision(repo: Path):
    original = sh(repo, "rev-parse", "HEAD^1").strip()
    head = update(repo)
    assert reviewed_revision(repo, head, "main") == original


def test_repeated_updates_keep_original_revision(repo: Path):
    original = sh(repo, "rev-parse", "HEAD^1").strip()
    update(repo)
    sh(repo, "checkout", "-q", "main")
    add_migration(repo, "0003_main_again", "0002_main")
    commit(repo, "main advances again")
    sh(repo, "checkout", "-q", "pr")
    head = update(repo)
    assert reviewed_revision(repo, head, "main") == original


@pytest.mark.parametrize(
    ("path", "content"),
    [
        ("feature.txt", "unreviewed feature change\n"),
        ("src/world/migrations/0003_feature.py", "# changed operations\n"),
        ("extra.txt", "unexpected addition\n"),
    ],
)
def test_bot_identity_does_not_authorize_extra_changes(repo: Path, path: str, content: str):
    update(repo)
    (repo / path).write_text(content)
    sh(repo, "add", "-A")
    sh(repo, "commit", "--amend", "--no-edit", "-q")
    with pytest.raises(RefusalError, match="reproduced tree"):
        reviewed_revision(repo, sh(repo, "rev-parse", "HEAD").strip(), "main")


def test_feature_commit_after_update_does_not_inherit_old_review(repo: Path):
    bot = update(repo)
    (repo / "feature.txt").write_text("new feature\n")
    commit(repo, "new feature")
    head = sh(repo, "rev-parse", "HEAD").strip()
    assert reviewed_revision(repo, head, "main") == bot


def test_merged_parent_must_belong_to_main(repo: Path):
    head = update(repo)
    old_main = sh(repo, "rev-parse", "main^1").strip()
    with pytest.raises(RefusalError, match="ancestor of main"):
        reviewed_revision(repo, head, old_main)


def test_spoofed_single_parent_bot_commit_is_rejected(repo: Path):
    sh(
        repo,
        "commit",
        "--allow-empty",
        "-qm",
        "Merge origin/main; renumber this branch's migrations after 0002_main",
    )
    with pytest.raises(RefusalError, match="exactly two parents"):
        reviewed_revision(repo, sh(repo, "rev-parse", "HEAD").strip(), "main")


def test_non_sha_input_is_rejected(repo: Path):
    with pytest.raises(RefusalError, match="full commit SHA"):
        reviewed_revision(repo, "HEAD", "main")

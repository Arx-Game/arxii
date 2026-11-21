"""Carry evidence only across reproducible migration transformations (#4990)."""

import os
from pathlib import Path
import subprocess

from auto_rebase_migration import RefusalError, run
import pytest
from review_evidence_revision import BOT_EMAIL, BOT_NAME, BOT_SUBJECT, reviewed_revision


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


def test_spoofed_no_op_merge_is_a_refusal_not_an_uncaught_exception(repo: Path):
    head = sh(
        repo,
        "commit-tree",
        "HEAD^{tree}",
        "-p",
        "HEAD",
        "-p",
        "main^1",
        "-m",
        BOT_SUBJECT + "0001_initial",
    ).strip()
    with pytest.raises(RefusalError, match="cannot be reproduced"):
        reviewed_revision(repo, head, "main")


def test_reviewed_head_and_empty_publication_commit_are_valid(repo: Path):
    anchor = sh(repo, "rev-parse", "HEAD").strip()
    assert reviewed_revision(repo, anchor, "main", anchor=anchor) == anchor
    sh(repo, "commit", "--allow-empty", "-qm", "publish evidence")
    assert (
        reviewed_revision(repo, sh(repo, "rev-parse", "HEAD").strip(), "main", anchor=anchor)
        == anchor
    )


def test_material_correction_requires_review_of_corrected_head(repo: Path):
    anchor = sh(repo, "rev-parse", "HEAD").strip()
    (repo / "feature.txt").write_text("corrected feature\n")
    commit(repo, "correct feature")
    head = sh(repo, "rev-parse", "HEAD").strip()
    with pytest.raises(RefusalError, match="changes reviewed content"):
        reviewed_revision(repo, head, "main", anchor=anchor)
    assert reviewed_revision(repo, head, "main", anchor=head) == head


def test_clean_main_merge_preserves_report_anchor(repo: Path):
    anchor = sh(repo, "rev-parse", "HEAD").strip()
    # Avoid the fixture's migration conflict: main adds a separate file here.
    sh(repo, "checkout", "-q", "main")
    (repo / "main-only.txt").write_text("main\n")
    commit(repo, "main-only change")
    sh(repo, "checkout", "-q", "pr")
    # Merge an independent main descendant after making the migrations agree.
    (repo / "src/world/migrations/0002_feature.py").unlink()
    (repo / "src/world/migrations/max_migration.txt").write_text("0001_initial\n")
    commit(repo, "remove conflicting migration")
    anchor = sh(repo, "rev-parse", "HEAD").strip()
    sh(repo, "merge", "--no-ff", "-qm", "merge main", "main")
    head = sh(repo, "rev-parse", "HEAD").strip()
    assert reviewed_revision(repo, head, "main", anchor=anchor) == anchor


def test_altered_merge_does_not_inherit_report(repo: Path):
    sh(repo, "checkout", "-q", "main")
    (repo / "main-only.txt").write_text("main\n")
    commit(repo, "main-only change")
    sh(repo, "checkout", "-q", "pr")
    (repo / "src/world/migrations/0002_feature.py").unlink()
    (repo / "src/world/migrations/max_migration.txt").write_text("0001_initial\n")
    commit(repo, "remove conflicting migration")
    anchor = sh(repo, "rev-parse", "HEAD").strip()
    sh(repo, "merge", "--no-ff", "-qm", "merge main", "main")
    (repo / "feature.txt").write_text("hidden change\n")
    sh(repo, "add", "feature.txt")
    sh(repo, "commit", "--amend", "--no-edit", "-q")
    with pytest.raises(RefusalError, match="cannot verify update"):
        reviewed_revision(repo, sh(repo, "rev-parse", "HEAD").strip(), "main", anchor=anchor)


def test_verified_migration_update_carries_anchor(repo: Path):
    anchor = sh(repo, "rev-parse", "HEAD^1").strip()
    head = update(repo)
    assert reviewed_revision(repo, head, "main", anchor=anchor) == anchor


def test_unrelated_anchor_is_not_accepted(repo: Path):
    anchor = sh(repo, "rev-parse", "main").strip()
    with pytest.raises(RefusalError):
        reviewed_revision(repo, sh(repo, "rev-parse", "HEAD").strip(), "main", anchor=anchor)


def test_evidence_staging_changes_are_neutral_but_source_changes_are_not(repo: Path):
    anchor = sh(repo, "rev-parse", "HEAD").strip()
    (repo / "docs/reviews").mkdir(parents=True)
    (repo / "docs/reviews/report.md").write_text("temporary evidence\n")
    commit(repo, "stage evidence")
    head = sh(repo, "rev-parse", "HEAD").strip()
    assert reviewed_revision(repo, head, "main", anchor=anchor) == anchor
    (repo / "feature.txt").write_text("changed\n")
    commit(repo, "change code")
    with pytest.raises(RefusalError, match="changes reviewed content"):
        reviewed_revision(repo, sh(repo, "rev-parse", "HEAD").strip(), "main", anchor=anchor)


def test_conflict_resolution_needs_fresh_review(repo: Path):
    anchor = sh(repo, "rev-parse", "HEAD").strip()
    result = subprocess.run(
        ["git", "merge", "--no-commit", "--no-ff", "main"],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    (repo / "src/world/migrations/max_migration.txt").write_text("0002_feature\n")
    sh(repo, "add", "-A")
    sh(repo, "commit", "-qm", "resolve conflict")
    with pytest.raises(RefusalError, match="cannot verify update"):
        reviewed_revision(repo, sh(repo, "rev-parse", "HEAD").strip(), "main", anchor=anchor)


def test_merge_from_untrusted_branch_needs_fresh_review(repo: Path):
    anchor = sh(repo, "rev-parse", "HEAD").strip()
    sh(repo, "checkout", "-qb", "untrusted")
    (repo / "foreign.txt").write_text("foreign\n")
    commit(repo, "untrusted change")
    sh(repo, "checkout", "-q", "pr")
    sh(repo, "merge", "--no-ff", "-qm", "merge untrusted", "untrusted")
    with pytest.raises(RefusalError, match="cannot verify update"):
        reviewed_revision(repo, sh(repo, "rev-parse", "HEAD").strip(), "main", anchor=anchor)


def test_mixed_migration_clean_merge_and_evidence_cleanup(repo: Path):
    anchor = sh(repo, "rev-parse", "HEAD^1").strip()
    update(repo)
    (repo / "docs/reviews").mkdir(parents=True)
    report = repo / "docs/reviews/report.md"
    report.write_text("evidence\n")
    commit(repo, "stage evidence")
    report.unlink()
    commit(repo, "remove evidence")
    sh(repo, "checkout", "-q", "main")
    (repo / "main-only.txt").write_text("main\n")
    commit(repo, "advance main")
    sh(repo, "checkout", "-q", "pr")
    sh(repo, "merge", "--no-ff", "-qm", "merge main", "main")
    head = sh(repo, "rev-parse", "HEAD").strip()
    assert reviewed_revision(repo, head, "main", anchor=anchor) == anchor


def anchored_commit(repo: Path, files: dict[str, str], message: str = "edit") -> tuple[str, str]:
    """Return (anchor, head) where head is one commit that writes `files` on top of anchor."""
    anchor = sh(repo, "rev-parse", "HEAD").strip()
    for name, text in files.items():
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    commit(repo, message)
    return anchor, sh(repo, "rev-parse", "HEAD").strip()


@pytest.mark.parametrize(
    "path",
    [
        "src/integration_tests/test_new_journeys.py",
        "src/integration_tests/live_seeds.py",
        "src/world/magic/tests/test_views.py",
        "tools/tests/test_something.py",
        "frontend/e2e/strength.spec.ts",
        "frontend/src/magic/Card.test.tsx",
        "frontend/src/magic/hooks.test.ts",
        "frontend/src/magic/__tests__/fixtures.ts",
        "frontend/src/test/setup.ts",
    ],
)
def test_test_only_commit_is_carried(repo: Path, path: str):
    anchor, head = anchored_commit(repo, {path: "changed\n"})
    assert reviewed_revision(repo, head, "main", anchor=anchor) == anchor


@pytest.mark.parametrize(
    "path",
    [
        "docs/systems/magic.md",
        "docs/adr/adr-1-x.md",
        "README.md",
        "src/world/magic/CLAUDE.md",
        ".github/workflows/ci.yml",
        ".github/CODEOWNERS",
    ],
)
def test_docs_and_workflow_only_commit_is_carried(repo: Path, path: str):
    anchor, head = anchored_commit(repo, {path: "changed\n"})
    assert reviewed_revision(repo, head, "main", anchor=anchor) == anchor


def test_commit_touching_a_test_and_a_source_file_is_refused(repo: Path):
    anchor, head = anchored_commit(
        repo,
        {"src/world/magic/tests/test_views.py": "t\n", "src/world/magic/views.py": "s\n"},
    )
    with pytest.raises(RefusalError, match="changes reviewed content"):
        reviewed_revision(repo, head, "main", anchor=anchor)


@pytest.mark.parametrize(
    "path",
    [
        "src/world/seeds/seed_things.py",
        "src/world/contests/models.py",
        "src/world/magic/factories.py",
        "src/conftest.py",
        "src/world/magic/mytests/helpers.py",
        "src/world/magic/test_helpers_not_in_a_tests_dir.py",
        "frontend/src/magic/Card.tsx",
        "frontend/src/magic/Card.test.tsx.bak",
        "frontend/src/magic/contest/Card.tsx",
        "frontend/public/readme.txt",
        "tests/outside_src.py",
        "src/evennia_extensions/tests",
    ],
)
def test_application_files_that_only_resemble_tests_are_refused(repo: Path, path: str):
    anchor, head = anchored_commit(repo, {path: "changed\n"})
    with pytest.raises(RefusalError, match="changes reviewed content"):
        reviewed_revision(repo, head, "main", anchor=anchor)


def test_deleting_an_application_file_is_refused(repo: Path):
    anchor, _ = anchored_commit(repo, {"src/world/magic/views.py": "s\n"}, "add view")
    (repo / "src/world/magic/views.py").unlink()
    commit(repo, "delete view")
    head = sh(repo, "rev-parse", "HEAD").strip()
    with pytest.raises(RefusalError, match="changes reviewed content"):
        reviewed_revision(repo, head, "main", anchor=anchor)


def test_moving_a_source_file_into_a_tests_directory_is_refused(repo: Path):
    anchor, _ = anchored_commit(repo, {"src/world/magic/views.py": "same content\n" * 20}, "add")
    sh(repo, "mv", "src/world/magic/views.py", "src/world/magic/tests_views_moved.py")
    (repo / "src/world/magic/tests").mkdir(parents=True)
    sh(repo, "mv", "src/world/magic/tests_views_moved.py", "src/world/magic/tests/test_views.py")
    commit(repo, "move source into tests")
    head = sh(repo, "rev-parse", "HEAD").strip()
    with pytest.raises(RefusalError, match="changes reviewed content"):
        reviewed_revision(repo, head, "main", anchor=anchor)


HAND = "Ordinary Author <author@example.com>"


def hand_merge(repo: Path) -> tuple[str, str]:
    """Make the bot's renumbering merge, then re-sign it as an ordinary author's merge.

    Returns (anchor, head). The tree is the one the bot would produce, so only the author
    and subject differ from a bot commit.
    """
    anchor = sh(repo, "rev-parse", "HEAD^1").strip()
    update(repo)
    sh(
        repo,
        "commit",
        "--amend",
        "-q",
        "-m",
        "Merge main and renumber my migration",
        "--author",
        HAND,
    )
    return anchor, sh(repo, "rev-parse", "HEAD").strip()


def test_hand_merge_that_matches_the_rebuilt_renumbering_is_carried(repo: Path):
    anchor, head = hand_merge(repo)
    assert "Ordinary Author" in sh(repo, "log", "-1", "--format=%an", head)
    assert reviewed_revision(repo, head, "main", anchor=anchor) == anchor


def test_hand_merge_with_one_extra_changed_line_is_refused(repo: Path):
    anchor, _ = hand_merge(repo)
    (repo / "feature.txt").write_text("base\none extra line\n")
    sh(repo, "add", "feature.txt")
    sh(repo, "commit", "--amend", "--no-edit", "-q")
    head = sh(repo, "rev-parse", "HEAD").strip()
    with pytest.raises(RefusalError, match="cannot verify update"):
        reviewed_revision(repo, head, "main", anchor=anchor)


def test_hand_merge_of_something_main_does_not_contain_is_refused(repo: Path):
    anchor, head = hand_merge(repo)
    old_main = sh(repo, "rev-parse", "main^1").strip()
    with pytest.raises(RefusalError, match="cannot verify update"):
        reviewed_revision(repo, head, old_main, anchor=anchor)

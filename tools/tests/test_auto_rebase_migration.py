"""The max_migration.txt auto-fix touches one shape only and proves its own result (#4879).

Every test drives a real throwaway git repository: the script's safety lives in what
git reports (conflicts, name-status against main), so a mocked git would test nothing.
The Django graph check is skipped here (no project to load); CI's run keeps it on.
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import subprocess

from auto_rebase_migration import (
    EXIT_NOTHING_TO_DO,
    EXIT_REFUSED,
    EXIT_RESOLVED,
    RefusalError,
    main,
    rewrite_dependency,
    verify_rewrite,
)
import pytest

MDIR = "src/world/migrations"


def migration_source(dep: str | None, body: str = "operations = []") -> str:
    deps = f'[("arxii", "{dep}"), ("auth", "0012_x")]' if dep else "[]"
    return (
        '"""A migration."""\n\nfrom django.db import migrations\n\n\n'
        "class Migration(migrations.Migration):\n"
        f"    dependencies = {deps}\n\n    {body}\n"
    )


def sh(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return proc.stdout


def add_migration(repo: Path, name: str, dep: str | None, body: str = "operations = []"):
    (repo / MDIR / f"{name}.py").write_text(migration_source(dep, body))
    (repo / MDIR / "max_migration.txt").write_text(f"{name}\n")


def commit(repo: Path, msg: str) -> None:
    sh(repo, "add", "-A")
    sh(repo, "commit", "-q", "-m", msg)


@pytest.fixture(autouse=True)
def _no_outer_git(monkeypatch: pytest.MonkeyPatch) -> None:
    """A commit hook exports GIT_DIR/GIT_INDEX_FILE; they must not reach the temp repos."""
    for key in [k for k in os.environ if k.startswith("GIT_")]:
        monkeypatch.delenv(key)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """main: 0001, 0002 then 0003_main_change; branch `pr` forks at 0002."""
    path = tmp_path / "repo"
    path.mkdir()
    sh(path, "init", "-q", "-b", "main")
    sh(path, "config", "user.email", "t@example.com")
    sh(path, "config", "user.name", "t")
    (path / MDIR).mkdir(parents=True)
    add_migration(path, "0001_initial", None)
    add_migration(path, "0002_second", "0001_initial")
    (path / "README.md").write_text("base\n")
    commit(path, "base")
    sh(path, "branch", "pr")
    add_migration(path, "0003_main_change", "0002_second")
    commit(path, "main moves")
    sh(path, "checkout", "-q", "pr")
    return path


def run_script(repo: Path, tmp_path: Path) -> tuple[int, dict]:
    out = tmp_path / "result.json"
    code = main(
        [
            "--repo",
            str(repo),
            "--main-ref",
            "main",
            "--result",
            str(out),
            "--skip-graph-check",
        ]
    )
    return code, json.loads(out.read_text())


def test_single_migration_is_renumbered_after_mains_tip(repo: Path, tmp_path: Path):
    add_migration(repo, "0003_pr_feature", "0002_second", "operations = [1, 2]")
    commit(repo, "pr migration")
    before = sh(repo, "rev-parse", "HEAD").strip()

    code, result = run_script(repo, tmp_path)

    assert code == EXIT_RESOLVED, result
    assert result["renames"] == [{"old": "0003_pr_feature", "new": "0004_pr_feature"}]
    # A merge commit whose first parent is the PR's old tip: history preserved.
    assert sh(repo, "rev-parse", "HEAD^1").strip() == before
    assert sh(repo, "rev-parse", "HEAD^2").strip() == sh(repo, "rev-parse", "main").strip()
    assert (repo / MDIR / "max_migration.txt").read_text() == "0004_pr_feature\n"
    assert not (repo / MDIR / "0003_pr_feature.py").exists()
    new = (repo / MDIR / "0004_pr_feature.py").read_text()
    assert new == migration_source("0003_main_change", "operations = [1, 2]")
    # Main's own migrations are untouched.
    assert sh(repo, "diff", "main", "HEAD", "--name-only", "--", MDIR).split() == [
        f"{MDIR}/0004_pr_feature.py",
        f"{MDIR}/max_migration.txt",
    ]
    assert sh(repo, "status", "--porcelain") == ""


def test_a_chain_is_renumbered_link_by_link(repo: Path, tmp_path: Path):
    """#4862 shipped 0347 + 0348: the schema/data split makes chains the common case."""
    add_migration(repo, "0003_schema", "0002_second")
    add_migration(repo, "0004_data", "0003_schema", "operations = ['data']")
    commit(repo, "pr chain")

    code, result = run_script(repo, tmp_path)

    assert code == EXIT_RESOLVED, result
    assert result["renames"] == [
        {"old": "0003_schema", "new": "0004_schema"},
        {"old": "0004_data", "new": "0005_data"},
    ]
    assert (repo / MDIR / "0004_schema.py").read_text() == migration_source("0003_main_change")
    assert (repo / MDIR / "0005_data.py").read_text() == migration_source(
        "0004_schema", "operations = ['data']"
    )
    assert (repo / MDIR / "max_migration.txt").read_text() == "0005_data\n"


def refused(repo: Path, tmp_path: Path) -> str:
    before = sh(repo, "rev-parse", "HEAD").strip()
    code, result = run_script(repo, tmp_path)
    assert code == EXIT_REFUSED, result
    # Nothing was left behind: same commit, clean tree, no merge in progress.
    assert sh(repo, "rev-parse", "HEAD").strip() == before
    assert sh(repo, "status", "--porcelain") == ""
    assert not (repo / ".git" / "MERGE_HEAD").exists()
    return result["reason"]


def test_another_conflicted_file_is_refused(repo: Path, tmp_path: Path):
    add_migration(repo, "0003_pr_feature", "0002_second")
    (repo / "README.md").write_text("pr side\n")
    commit(repo, "pr")
    sh(repo, "checkout", "-q", "main")
    (repo / "README.md").write_text("main side\n")
    commit(repo, "main edits readme")
    sh(repo, "checkout", "-q", "pr")

    assert "conflicts on more than" in refused(repo, tmp_path)


def test_editing_an_existing_migration_is_refused(repo: Path, tmp_path: Path):
    add_migration(repo, "0003_pr_feature", "0002_second")
    (repo / MDIR / "0002_second.py").write_text(migration_source("0001_initial", "x = 1"))
    commit(repo, "pr edits an old migration")

    assert "only adding NNNN_name.py files" in refused(repo, tmp_path)


def test_a_branching_set_of_migrations_is_refused(repo: Path, tmp_path: Path):
    add_migration(repo, "0003_one", "0002_second")
    add_migration(repo, "0004_two", "0002_second")
    commit(repo, "two leaves")

    assert "not one linear chain" in refused(repo, tmp_path)


def test_a_name_used_in_code_elsewhere_is_refused(repo: Path, tmp_path: Path):
    add_migration(repo, "0003_pr_feature", "0002_second")
    (repo / "test_it.py").write_text('MIGRATE_TO = ("arxii", "0003_pr_feature")\n')
    commit(repo, "a test pins the migration name")

    assert "named in code outside its own file" in refused(repo, tmp_path)


def test_a_doc_mention_is_a_warning_not_a_refusal(repo: Path, tmp_path: Path):
    add_migration(repo, "0003_pr_feature", "0002_second")
    (repo / "notes.md").write_text("Shipped in 0003_pr_feature.\n")
    commit(repo, "doc mentions it")

    code, result = run_script(repo, tmp_path)

    assert code == EXIT_RESOLVED
    assert result["warnings"] == ["notes.md mentions 0003_pr_feature"]


def test_no_conflict_is_nothing_to_do(tmp_path: Path, repo: Path):
    (repo / "README.md").write_text("no migration here\n")
    commit(repo, "pr without migrations")

    code, result = run_script(repo, tmp_path)

    assert code == EXIT_NOTHING_TO_DO, result


def test_a_dirty_tree_is_refused(repo: Path, tmp_path: Path):
    add_migration(repo, "0003_pr_feature", "0002_second")
    commit(repo, "pr")
    (repo / "README.md").write_text("uncommitted\n")

    code, result = run_script(repo, tmp_path)

    assert code == EXIT_REFUSED
    assert result["reason"] == "the working tree is not clean"


def test_rewrite_keeps_quote_style_and_only_the_name():
    src = "class Migration:\n    dependencies = [('arxii', '0001_a'), ('auth', '0012_x')]\n"
    out = rewrite_dependency(src, "f.py", "0009_b")
    assert out == "class Migration:\n    dependencies = [('arxii', '0009_b'), ('auth', '0012_x')]\n"
    verify_rewrite(src, out, "f.py", "0009_b")


def test_verify_rewrite_catches_any_other_change():
    src = migration_source("0001_a")
    tampered = rewrite_dependency(src, "f.py", "0009_b").replace("operations = []", "x = 1")
    with pytest.raises(RefusalError, match="changed more than"):
        verify_rewrite(src, tampered, "f.py", "0009_b")
    # Sanity: the tampered file still parses, so only the AST comparison caught it.
    ast.parse(tampered)


def test_two_in_app_dependencies_are_refused():
    src = "class Migration:\n    dependencies = [('arxii', '0001_a'), ('arxii', '0002_b')]\n"
    with pytest.raises(RefusalError, match="expected exactly 1"):
        rewrite_dependency(src, "f.py", "0009_c")

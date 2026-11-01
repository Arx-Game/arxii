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
    Plan,
    RefusalError,
    Rename,
    main,
    rewrite_dependency,
    verify_lint,
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
    assert result["tree"] == sh(repo, "rev-parse", "HEAD^{tree}").strip()


def test_the_merge_tree_is_reproducible(repo: Path, tmp_path: Path):
    """CI's push job re-derives the merge and pushes only on an identical tree."""
    add_migration(repo, "0003_schema", "0002_second")
    add_migration(repo, "0004_data", "0003_schema")
    commit(repo, "pr chain")
    head = sh(repo, "rev-parse", "HEAD").strip()
    _, first = run_script(repo, tmp_path)
    sh(repo, "checkout", "-q", "--detach", head)

    _, second = run_script(repo, tmp_path)

    assert second["status"] == "resolved"
    assert second["tree"] == first["tree"]


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


def test_a_doc_mention_is_renamed_with_the_migration(repo: Path, tmp_path: Path):
    add_migration(repo, "0003_pr_feature", "0002_second")
    (repo / "notes.md").write_text("Shipped in 0003_pr_feature, see above.\n")
    commit(repo, "doc mentions it")

    code, result = run_script(repo, tmp_path)

    assert code == EXIT_RESOLVED, result
    assert result["doc_files"] == ["notes.md"]
    assert (repo / "notes.md").read_text() == "Shipped in 0004_pr_feature, see above.\n"


def test_the_result_names_what_the_chain_now_runs_after(repo: Path, tmp_path: Path):
    add_migration(repo, "0003_pr_feature", "0002_second")
    commit(repo, "pr")

    _, result = run_script(repo, tmp_path)

    assert result["base_tip"] == "0002_second"
    assert result["interleaved"] == ["0003_main_change"]


def main_adds(repo: Path, name: str, dep: str, body: str) -> None:
    sh(repo, "checkout", "-q", "main")
    add_migration(repo, name, dep, body)
    commit(repo, f"main adds {name}")
    sh(repo, "checkout", "-q", "pr")


def test_a_model_both_sides_involve_is_refused(repo: Path, tmp_path: Path):
    """Main reshapes Widget; the PR backfills it. The new order is a person's call."""
    main_adds(
        repo,
        "0004_widget_colour",
        "0003_main_change",
        'operations = [migrations.AddField(model_name="widget", name="colour")]',
    )
    add_migration(
        repo,
        "0003_backfill",
        "0002_second",
        'operations = [migrations.RunPython(lambda a, s: a.get_model("arxii", "Widget"))]',
    )
    commit(repo, "pr backfills widget")

    assert "both involve ['widget']" in refused(repo, tmp_path)


def test_the_pr_touching_a_model_main_mentions_is_refused(repo: Path, tmp_path: Path):
    main_adds(
        repo,
        "0004_backfill",
        "0003_main_change",
        'operations = [migrations.RunPython(lambda a, s: a.get_model("arxii", "Gadget"))]',
    )
    add_migration(
        repo,
        "0003_gadget",
        "0002_second",
        'operations = [migrations.RemoveField("gadget", "size")]',
    )
    commit(repo, "pr drops a gadget field")

    assert "both involve ['gadget']" in refused(repo, tmp_path)


def test_disjoint_models_are_fixed(repo: Path, tmp_path: Path):
    main_adds(
        repo,
        "0004_widget_colour",
        "0003_main_change",
        'operations = [migrations.AddField(model_name="widget", name="colour")]',
    )
    add_migration(
        repo,
        "0003_gadget",
        "0002_second",
        'operations = [migrations.AddField(model_name="gadget", name="size")]',
    )
    commit(repo, "pr")

    code, result = run_script(repo, tmp_path)

    assert code == EXIT_RESOLVED, result
    assert result["renames"] == [{"old": "0003_gadget", "new": "0005_gadget"}]


def test_raw_sql_is_refused(repo: Path, tmp_path: Path):
    add_migration(repo, "0003_raw", "0002_second", 'operations = [migrations.RunSQL("SELECT 1")]')
    commit(repo, "pr uses raw sql")

    assert "use RunSQL" in refused(repo, tmp_path)


def test_a_stale_self_reference_is_refused(repo: Path, tmp_path: Path):
    add_migration(repo, "0003_pr_feature", "0002_second", 'NOTE = "0003_pr_feature"')
    commit(repo, "pr names itself")

    assert "still named" in refused(repo, tmp_path)


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


def _lint_repo(tmp_path: Path, dep: str) -> Path:
    path = tmp_path / "lint"
    (path / MDIR).mkdir(parents=True)
    (path / "pyproject.toml").write_text("[tool.ruff]\nline-length = 100\n")
    (path / MDIR / "0005_new.py").write_text(
        "from django.db import migrations\n\n\n"
        "class Migration(migrations.Migration):\n"
        f'    dependencies = [("arxii", "{dep}")]\n\n    operations = []\n'
    )
    return path


def _plan() -> Plan:
    return Plan(base_tip="", main_tip="", renames=[Rename("0004_new", "0005_new")], interleaved=[])


def test_lint_gate_passes_a_clean_rename(tmp_path: Path):
    verify_lint(_lint_repo(tmp_path, "0004_short"), _plan(), MDIR)


def test_lint_gate_refuses_a_rename_the_formatter_would_change(tmp_path: Path):
    """A long new name pushes the dependency line past 100; the PR's pre-commit would fail."""
    repo = _lint_repo(tmp_path, "0004_" + "x" * 90)
    with pytest.raises(RefusalError, match="would fail `format --check`"):
        verify_lint(repo, _plan(), MDIR)

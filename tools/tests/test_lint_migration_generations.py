"""No migration may reuse a name from, or depend on a name in, an earlier generation
(ADR-0272). Production records every name forever, so a reused name is silently
skipped and a stale dependency is silently remapped; both must die at commit time."""

from __future__ import annotations

from pathlib import Path

from lint_migration_generations import check_migrations

GEN_SOURCE = """CURRENT = 2
GENERATIONS: dict[int, list[str]] = {
    1: ["0001_initial", "0104_persona_title", "0222_holdingkind"],
}
COMMITS: dict[int, str] = {}
"""


def _write(tmp_path: Path, name: str, deps: str = "[]") -> None:
    (tmp_path / f"{name}.py").write_text(
        "from django.db import migrations\n\n"
        "class Migration(migrations.Migration):\n"
        f"    dependencies = {deps}\n"
        "    operations = []\n"
    )


def test_clean_chain_passes(tmp_path: Path):
    (tmp_path / "_generations.py").write_text(GEN_SOURCE)
    _write(tmp_path, "0001_g2_initial")
    _write(tmp_path, "0104_familykind", '[("arxii", "0001_g2_initial")]')
    assert check_migrations(tmp_path) == []


def test_name_reused_from_an_earlier_generation_fails(tmp_path: Path):
    (tmp_path / "_generations.py").write_text(GEN_SOURCE)
    _write(tmp_path, "0001_g2_initial")
    _write(tmp_path, "0104_persona_title", '[("arxii", "0001_g2_initial")]')
    failures = check_migrations(tmp_path)
    assert len(failures) == 1
    assert "0104_persona_title" in failures[0]
    assert "generation 1" in failures[0]


def test_dependency_on_a_replaced_name_fails(tmp_path: Path):
    (tmp_path / "_generations.py").write_text(GEN_SOURCE)
    _write(tmp_path, "0001_g2_initial")
    _write(tmp_path, "0223_straggler", '[("arxii", "0222_holdingkind")]')
    failures = check_migrations(tmp_path)
    assert len(failures) == 1
    assert "0223_straggler" in failures[0]
    assert "0222_holdingkind" in failures[0]


def test_no_generations_module_means_nothing_to_check(tmp_path: Path):
    _write(tmp_path, "0001_initial")
    assert check_migrations(tmp_path) == []


def test_current_chain_is_clean():
    """Generation 1 has no predecessor, so the real migrations directory passes today."""
    assert check_migrations() == []

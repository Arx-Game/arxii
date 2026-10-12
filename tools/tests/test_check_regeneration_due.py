"""The monthly regeneration cue counts incrementals since the current generation (ADR-0276)."""

from __future__ import annotations

from pathlib import Path

from check_regeneration_due import THRESHOLD, incremental_migrations, is_due
import pytest

GEN_SOURCE = """CURRENT = 2
GENERATIONS: dict[int, list[str]] = {
    1: ["0001_initial", "0002_old_thing"],
}
COMMITS: dict[int, str] = {}
"""


def _chain(tmp_path: Path, *names: str) -> Path:
    (tmp_path / "_generations.py").write_text(GEN_SOURCE)
    (tmp_path / "__init__.py").write_text("")
    (tmp_path / "max_migration.txt").write_text(f"{names[-1]}\n")
    for name in names:
        (tmp_path / f"{name}.py").write_text("")
    return tmp_path


def test_counts_only_files_added_since_the_current_generation(tmp_path: Path):
    migrations_dir = _chain(
        tmp_path,
        "0001_g2_initial",
        "0002_g2_part_2",
        "0003_g2_partition_sql",
        "0004_formative_connections",
        "0005_actors_sheet",
    )
    assert incremental_migrations(migrations_dir) == [
        "0004_formative_connections",
        "0005_actors_sheet",
    ]


def test_a_previous_generations_naming_counts_as_incremental(tmp_path: Path):
    # Only CURRENT's generated files are the floor; a stray _g1_ name is not.
    migrations_dir = _chain(tmp_path, "0001_g2_initial", "0002_g1_part_2")
    assert incremental_migrations(migrations_dir) == ["0002_g1_part_2"]


def test_no_generated_files_for_current_is_an_error_not_a_count(tmp_path: Path):
    # Without the floor every file would count, and the cue would fire on a
    # misreading rather than on a long chain.
    migrations_dir = _chain(tmp_path, "0001_initial", "0002_thing")
    with pytest.raises(ValueError, match="_g2_"):
        incremental_migrations(migrations_dir)


def test_due_only_at_or_past_the_threshold():
    assert not is_due(THRESHOLD - 1)
    assert is_due(THRESHOLD)
    assert is_due(THRESHOLD + 1)


def test_the_real_chain_parses():
    # The scheduled job runs against this directory; a rename of _generations.py
    # or of the generated-file scheme must fail here, per-PR, not silently monthly.
    incremental_migrations()

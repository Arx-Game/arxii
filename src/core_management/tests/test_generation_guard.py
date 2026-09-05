"""The two database states Django's ``replaces`` handles badly (ADR-0272).

Partially recorded: Django removes every replacing node, remaps onto files that no
longer exist, and ``migrate`` exits 0 having done nothing. Skipped a generation:
Django treats the new generation as unapplied and fails on the first CREATE TABLE.
``classify_generation_state`` refuses both before stock ``migrate`` runs, and names
the commit a stranded database has to visit.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from core_management.migration_generations import GenerationsData, classify_generation_state

GEN1 = ["0001_initial", "0002_initial_part_2", "0003_persona_title"]
GEN2 = ["0001_g2_initial", "0002_g2_part_2", "0104_familykind"]
LISTS = {1: GEN1, 2: GEN2}


def _data(current: int) -> GenerationsData:
    """Generations 1..current-1 are snapshotted; the current one lives on disk only."""
    return GenerationsData(
        current=current,
        generations={gen: LISTS[gen] for gen in range(1, current)},
        commits={gen: f"sha{gen}" for gen in range(1, current)},
    )


class ClassifyGenerationStateTests(SimpleTestCase):
    def test_fresh_database_proceeds(self) -> None:
        assert classify_generation_state(set(), _data(current=2)).ok

    def test_all_of_previous_generation_proceeds(self) -> None:
        assert classify_generation_state(set(GEN1), _data(current=2)).ok

    def test_previous_and_current_recorded_proceeds(self) -> None:
        recorded = set(GEN1) | {"0001_g2_initial", "0002_g2_part_2"}
        assert classify_generation_state(recorded, _data(current=2)).ok

    def test_generation_one_has_no_guard(self) -> None:
        assert classify_generation_state({"0001_initial"}, GenerationsData(current=1)).ok

    def test_partial_previous_generation_refuses_and_names_it(self) -> None:
        verdict = classify_generation_state(set(GEN1[:2]), _data(current=2))
        assert not verdict.ok
        assert verdict.stranded_at == 0
        assert "2 of 3" in verdict.message
        assert "sha1" in verdict.message

    def test_skipped_generation_refuses_and_names_the_missing_one(self) -> None:
        verdict = classify_generation_state(set(GEN1), _data(current=3))
        assert not verdict.ok
        assert verdict.stranded_at == 1
        assert "generation 2" in verdict.message
        assert "sha2" in verdict.message

    def test_partial_older_generation_refuses(self) -> None:
        recorded = set(GEN1) | {"0001_g2_initial"}
        verdict = classify_generation_state(recorded, _data(current=3))
        assert not verdict.ok
        assert verdict.stranded_at == 1
        assert "1 of 3" in verdict.message

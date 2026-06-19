"""ChecksContent — seed orchestrator for the check-resolution spine (#651).

Seeds the rows ``perform_check`` needs to turn a roll into a real
``CheckOutcome``: the point-conversion ranges, the rank ladder, the result
charts (with their per-roll outcome bands), and the outcome catalog. Values are
promoted verbatim from the integration-test setup (``CheckSystemSetupFactory``
and the ``CheckRank``/``PointConversionRange`` rows built in
``world/checks/tests`` and ``world/traits/tests``) — they are the initial sane
defaults, not new tuning numbers (Phase B #1221 makes them tunable).

Everything here is create-if-missing (``get_or_create`` on stable natural keys),
so re-runs are no-ops and staff edits to existing rows survive a re-seed —
matching the magic/items/combat clusters. The Sequence-based factories in
``world/traits/factories.py`` are NOT reused directly: their generated names
make them non-idempotent, so the spine is seeded through ``get_or_create``.
"""

from __future__ import annotations

from world.traits.models import (
    CheckOutcome,
    CheckRank,
    PointConversionRange,
    ResultChart,
    ResultChartOutcome,
    TraitType,
)

# --- Point-conversion ranges (one per trait type that contributes points) ---
# Promoted from the test setup: STAT/SKILL both map 1 point per level over the
# full 1-100 range. perform_check returns 0 trait_points without a range that
# covers the character's trait values, so these are load-bearing.
_CONVERSION_RANGES: tuple[tuple[str, int, int, int], ...] = (
    (TraitType.STAT, 1, 100, 1),
    (TraitType.SKILL, 1, 100, 1),
)

# --- Rank ladder (point thresholds -> rank) ---
# Promoted from world/traits/tests.py + the checks service tests.
_CHECK_RANKS: tuple[tuple[int, int, str], ...] = (
    (0, 0, "Incompetent"),
    (1, 10, "Novice"),
    (2, 25, "Competent"),
    (3, 50, "Expert"),
)

# --- Outcome catalog (name -> success_level) ---
# Promoted from CheckSystemSetupFactory.
_OUTCOMES: tuple[tuple[str, int], ...] = (
    ("Failure", -1),
    ("Partial Success", 0),
    ("Success", 1),
    ("Critical Success", 2),
)

# --- Result charts: rank_difference -> ordered (outcome_name, min_roll, max_roll) ---
# Promoted verbatim from CheckSystemSetupFactory (diffs -2..2). Easy diffs lean
# toward success, hard diffs toward failure; diff 0 is the even baseline.
_EASY_BANDS: tuple[tuple[str, int, int], ...] = (
    ("Failure", 1, 20),
    ("Success", 21, 90),
    ("Critical Success", 91, 100),
)
_EVEN_BANDS: tuple[tuple[str, int, int], ...] = (
    ("Failure", 1, 40),
    ("Partial Success", 41, 60),
    ("Success", 61, 100),
)
_HARD_BANDS: tuple[tuple[str, int, int], ...] = (
    ("Failure", 1, 70),
    ("Partial Success", 71, 85),
    ("Success", 86, 100),
)
_CHARTS: tuple[tuple[int, tuple[tuple[str, int, int], ...]], ...] = (
    (-2, _EASY_BANDS),
    (-1, _EASY_BANDS),
    (0, _EVEN_BANDS),
    (1, _HARD_BANDS),
    (2, _HARD_BANDS),
)


def seed_check_resolution_tables() -> None:
    """Seed the check-resolution spine for production play (#651).

    Idempotent — every row is created via ``get_or_create`` on its natural key,
    so re-runs add nothing and staff edits to existing rows are preserved. The
    ResultChart lookup cache is cleared so a freshly seeded chart set is visible
    to ``perform_check`` within the same process.
    """
    for trait_type, min_value, max_value, points_per_level in _CONVERSION_RANGES:
        PointConversionRange.objects.get_or_create(
            trait_type=trait_type,
            min_value=min_value,
            defaults={"max_value": max_value, "points_per_level": points_per_level},
        )

    for rank, min_points, name in _CHECK_RANKS:
        CheckRank.objects.get_or_create(
            rank=rank,
            defaults={"min_points": min_points, "name": name},
        )

    outcomes: dict[str, CheckOutcome] = {}
    for name, success_level in _OUTCOMES:
        outcome, _ = CheckOutcome.objects.get_or_create(
            name=name,
            defaults={"success_level": success_level},
        )
        outcomes[name] = outcome

    for rank_difference, bands in _CHARTS:
        chart, _ = ResultChart.objects.get_or_create(
            rank_difference=rank_difference,
            defaults={"name": f"Difficulty {rank_difference:+d}"},
        )
        for outcome_name, min_roll, max_roll in bands:
            ResultChartOutcome.objects.get_or_create(
                chart=chart,
                min_roll=min_roll,
                defaults={"max_roll": max_roll, "outcome": outcomes[outcome_name]},
            )

    # A stale chart cache (built before this seed ran) would hide the new
    # charts from perform_check in the same process; clear it.
    ResultChart.clear_cache()

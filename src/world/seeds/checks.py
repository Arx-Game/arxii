"""ChecksContent — seed orchestrator for the check-resolution spine (#651).

Seeds the rows ``perform_check`` needs to turn a roll into a real
``CheckOutcome``: the point-conversion ranges, the rank ladder, the result
charts (with their per-roll outcome bands), and the outcome catalog. This module
is the SINGLE authority for the global resolution charts/outcomes keyed by
``rank_difference`` — other clusters (e.g. magic) ensure the spine exists by
calling :func:`seed_check_resolution_tables` rather than defining their own
``ResultChart`` rows (which previously collided on ``rank_difference=0``).

Values are selected as initial sane defaults, aligned with the integration-test
setup (``PerformCheckTests`` / the traits tests) — they are not new tuning
numbers (Phase B #1221 makes them tunable).

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
# Ranks 0-3 are the original defaults (aligned with PerformCheckTests). Ranks 4-8
# were added with #2707: level contributes LEVEL_POINTS_PER_LEVEL points per level,
# so a level-30 character carries 150 points from level alone and would otherwise
# sit pinned at the old top rung from level 10 onward, making level stop mattering
# exactly where the power fantasy needs it most.
_CHECK_RANKS: tuple[tuple[int, int, str], ...] = (
    (0, 0, "Incompetent"),
    (1, 10, "Novice"),
    (2, 25, "Competent"),
    (3, 50, "Expert"),
    (4, 80, "Master"),
    (5, 115, "Grandmaster"),
    (6, 155, "Peerless"),
    (7, 200, "Legendary"),
    (8, 250, "Mythic"),
)

# CheckOutcome tier name constants — referenced in both _OUTCOMES and the band tuples.
_OUTCOME_PARTIAL_SUCCESS = "Partial Success"

# --- Outcome catalog (name -> success_level) ---
# Initial sane defaults aligned with the integration-test setup. "Critical
# Failure" is included so the magic cluster's backfire consequence pools (which
# fetch a CheckOutcome named "Critical Failure") resolve against the canonical
# spine rather than seeding their own outcome rows.
_OUTCOMES: tuple[tuple[str, int], ...] = (
    ("Critical Failure", -2),
    ("Failure", -1),
    (_OUTCOME_PARTIAL_SUCCESS, 0),
    ("Success", 1),
    ("Critical Success", 2),
)

# --- Result charts: rank_difference -> ordered (outcome_name, min_roll, max_roll) ---
# rank_difference is roller_rank MINUS target_rank, so POSITIVE means the roller is
# stronger and must get the easier bands (#2707 — this mapping was inverted, making
# better characters fail more; world/checks/tests/test_chart_direction.py guards it).
_EASY_BANDS: tuple[tuple[str, int, int], ...] = (
    ("Failure", 1, 20),
    ("Success", 21, 90),
    ("Critical Success", 91, 100),
)
_EVEN_BANDS: tuple[tuple[str, int, int], ...] = (
    ("Failure", 1, 40),
    (_OUTCOME_PARTIAL_SUCCESS, 41, 60),
    ("Success", 61, 100),
)
_HARD_BANDS: tuple[tuple[str, int, int], ...] = (
    ("Failure", 1, 70),
    (_OUTCOME_PARTIAL_SUCCESS, 71, 85),
    ("Success", 86, 100),
)

# Deep-gap bands (#2707). Design intent, stated because the numbers alone don't
# show it: past a two-rung gap the FAILURE share stops growing — what degrades is
# what you ACCOMPLISH. A party attacking something far above its level chips away
# (Partial Success) instead of whiffing round after round; the chip-damage value
# itself is an authored DamageSuccessLevelMultiplier row, not code.
_DIRE_BANDS: tuple[tuple[str, int, int], ...] = (
    ("Failure", 1, 55),
    (_OUTCOME_PARTIAL_SUCCESS, 56, 98),
    ("Success", 99, 100),
)
# A one-in-a-hundred Success keeps this chart out of chart_has_success_outcomes'
# IMPOSSIBLE bucket (#2707 review): with an all-Failure/Partial-Success chart here,
# world.mechanics.services reported DifficultyIndicator.IMPOSSIBLE for any rank
# difference <= -5, and both approach-listing call sites (services.py:1408/:1657)
# then dropped the action from the player's available-actions list entirely —
# the exact inverse of "chip, not whiff, and still be offered" above.
_HOPELESS_BANDS: tuple[tuple[str, int, int], ...] = (
    ("Failure", 1, 45),
    (_OUTCOME_PARTIAL_SUCCESS, 46, 99),
    ("Success", 100, 100),
)
# Mirror bands for a roller far ABOVE the difficulty.
_DOMINANT_BANDS: tuple[tuple[str, int, int], ...] = (
    ("Failure", 1, 5),
    ("Success", 6, 55),
    ("Critical Success", 56, 100),
)
_OVERWHELMING_BANDS: tuple[tuple[str, int, int], ...] = (
    ("Success", 1, 30),
    ("Critical Success", 31, 100),
)
_CHARTS: tuple[tuple[int, tuple[tuple[str, int, int], ...]], ...] = (
    (-6, _HOPELESS_BANDS),
    (-5, _HOPELESS_BANDS),
    (-4, _DIRE_BANDS),
    (-3, _DIRE_BANDS),
    (-2, _HARD_BANDS),
    (-1, _HARD_BANDS),
    (0, _EVEN_BANDS),
    (1, _EASY_BANDS),
    (2, _EASY_BANDS),
    (3, _DOMINANT_BANDS),
    (4, _DOMINANT_BANDS),
    (5, _OVERWHELMING_BANDS),
    (6, _OVERWHELMING_BANDS),
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

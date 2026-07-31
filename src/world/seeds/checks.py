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
_CRITICAL_SUCCESS = "Critical Success"
_CRITICAL_FAILURE = "Critical Failure"

# --- Outcome catalog (name -> success_level) ---
# Initial sane defaults aligned with the integration-test setup. "Critical
# Failure" is included so the magic cluster's backfire consequence pools (which
# fetch a CheckOutcome named "Critical Failure") resolve against the canonical
# spine rather than seeding their own outcome rows.
_OUTCOMES: tuple[tuple[str, int], ...] = (
    (_CRITICAL_FAILURE, -2),
    ("Failure", -1),
    (_OUTCOME_PARTIAL_SUCCESS, 0),
    ("Success", 1),
    (_CRITICAL_SUCCESS, 2),
)

# --- Result charts: rank_difference -> ordered (outcome_name, min_roll, max_roll) ---
# rank_difference is roller_rank MINUS target_rank, so POSITIVE means the roller is
# stronger and must get the easier bands (#2707 — this mapping was inverted, making
# better characters fail more; world/checks/tests/test_chart_direction.py guards it).
#
# 13 unique charts — one per rank_difference. Each gap has its own outcome
# distribution; no two rank_differences share a chart (#2760). Previously 7
# shared templates were reused across 13 slots via closest-match fallback.
#
# Botch (Critical Failure, success_level -2) appears at rank_diff <= -1 and
# vanishes at EVEN — you can only botch when you're behind in rank, never on
# even footing or better. Botch gradient: 10% at worst (-6) → 0% at EVEN.
#
# Partial Success is a smooth gradient present from -6 through +5, absent only
# at +6 (pure win). The old design where Partial vanished entirely on EASY+ was
# a mistake — it should be a smooth gradient.
#
# The -6 chart keeps a 1/100 success, preserving the "chip, don't whiff" design
# (#2707) and keeping chart_has_success_outcomes True at every rank_difference
# (so actions at the worst gap are still offered to the player, not dropped from
# available-actions lists as IMPOSSIBLE).
#
# Deep-gap non-monotonicity (total negative outcomes peak at ~58% at -2/Hard,
# then decline as Partial absorbs more at wider gaps) is intended — a party
# attacking something far above its level chips away (partial success) instead
# of whiffing round after round. The -6 "Crushing" chart is intentionally brutal
# (89% negative); the non-monotonicity holds from -5 onward.
_CRUSHING_BANDS: tuple[tuple[str, int, int], ...] = (
    (_CRITICAL_FAILURE, 1, 10),
    ("Failure", 11, 89),
    (_OUTCOME_PARTIAL_SUCCESS, 90, 99),
    ("Success", 100, 100),
)
_HOPELESS_BANDS: tuple[tuple[str, int, int], ...] = (
    (_CRITICAL_FAILURE, 1, 7),
    ("Failure", 8, 45),
    (_OUTCOME_PARTIAL_SUCCESS, 46, 95),
    ("Success", 96, 100),
)
_DIRE_BANDS: tuple[tuple[str, int, int], ...] = (
    (_CRITICAL_FAILURE, 1, 5),
    ("Failure", 6, 48),
    (_OUTCOME_PARTIAL_SUCCESS, 49, 92),
    ("Success", 93, 100),
)
_VERY_HARD_BANDS: tuple[tuple[str, int, int], ...] = (
    (_CRITICAL_FAILURE, 1, 3),
    ("Failure", 4, 45),
    (_OUTCOME_PARTIAL_SUCCESS, 46, 88),
    ("Success", 89, 100),
)
_HARD_BANDS: tuple[tuple[str, int, int], ...] = (
    (_CRITICAL_FAILURE, 1, 2),
    ("Failure", 3, 58),
    (_OUTCOME_PARTIAL_SUCCESS, 59, 85),
    ("Success", 86, 100),
)
_STEEP_BANDS: tuple[tuple[str, int, int], ...] = (
    (_CRITICAL_FAILURE, 1, 2),
    ("Failure", 3, 45),
    (_OUTCOME_PARTIAL_SUCCESS, 46, 78),
    ("Success", 79, 100),
)
_EVEN_BANDS: tuple[tuple[str, int, int], ...] = (
    ("Failure", 1, 35),
    (_OUTCOME_PARTIAL_SUCCESS, 36, 60),
    ("Success", 61, 95),
    (_CRITICAL_SUCCESS, 96, 100),
)
_FAVORABLE_BANDS: tuple[tuple[str, int, int], ...] = (
    ("Failure", 1, 18),
    (_OUTCOME_PARTIAL_SUCCESS, 19, 35),
    ("Success", 36, 90),
    (_CRITICAL_SUCCESS, 91, 100),
)
_EASY_BANDS: tuple[tuple[str, int, int], ...] = (
    ("Failure", 1, 10),
    (_OUTCOME_PARTIAL_SUCCESS, 11, 25),
    ("Success", 26, 85),
    (_CRITICAL_SUCCESS, 86, 100),
)
_VERY_EASY_BANDS: tuple[tuple[str, int, int], ...] = (
    ("Failure", 1, 5),
    (_OUTCOME_PARTIAL_SUCCESS, 6, 15),
    ("Success", 16, 80),
    (_CRITICAL_SUCCESS, 81, 100),
)
_DOMINANT_BANDS: tuple[tuple[str, int, int], ...] = (
    ("Failure", 1, 3),
    (_OUTCOME_PARTIAL_SUCCESS, 4, 10),
    ("Success", 11, 75),
    (_CRITICAL_SUCCESS, 76, 100),
)
_OVERWHELMING_BANDS: tuple[tuple[str, int, int], ...] = (
    (_OUTCOME_PARTIAL_SUCCESS, 1, 5),
    ("Success", 6, 70),
    (_CRITICAL_SUCCESS, 71, 100),
)
_INEVITABLE_BANDS: tuple[tuple[str, int, int], ...] = (
    ("Success", 1, 50),
    (_CRITICAL_SUCCESS, 51, 100),
)
_CHARTS: tuple[tuple[int, tuple[tuple[str, int, int], ...]], ...] = (
    (-6, _CRUSHING_BANDS),
    (-5, _HOPELESS_BANDS),
    (-4, _DIRE_BANDS),
    (-3, _VERY_HARD_BANDS),
    (-2, _HARD_BANDS),
    (-1, _STEEP_BANDS),
    (0, _EVEN_BANDS),
    (1, _FAVORABLE_BANDS),
    (2, _EASY_BANDS),
    (3, _VERY_EASY_BANDS),
    (4, _DOMINANT_BANDS),
    (5, _OVERWHELMING_BANDS),
    (6, _INEVITABLE_BANDS),
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

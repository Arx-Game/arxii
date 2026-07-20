"""Affection-derived social-action difficulty (#1697).

Social actions derive their **base** difficulty from how the target feels about the actor — the
directed ``CharacterRelationship(source=target, target=actor)`` affection: warm → easier, neutral →
Normal, hostile → Hard, very hostile → Harrowing. The defender's ``difficulty_choice`` then shifts
that base **relatively** (NORMAL = no change / use the derived base; HARD = +1 tier harder than
derived; EASY = −1 tier easier), and a per-template ``difficulty_tier_modifier`` shifts it further
(Seduce = +1). Everything is computed in **tier space** (ordinal) so "+1 tier" is well-defined
across the uneven 15/30/45/60/75/90 values, then clamped to the available tiers.

Non-social actions keep the absolute defender-chosen value. Affection thresholds are PLACEHOLDER.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.scenes.action_constants import DIFFICULTY_VALUES, DifficultyChoice

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.scenes.action_models import SceneActionRequest

_SOCIAL_CATEGORY = "social"

# Ascending difficulty tiers — the ordinal index is the tier rank.
_TIER_ORDER = [
    DifficultyChoice.TRIVIAL,
    DifficultyChoice.EASY,
    DifficultyChoice.NORMAL,
    DifficultyChoice.HARD,
    DifficultyChoice.DAUNTING,
    DifficultyChoice.HARROWING,
]
_NORMAL_INDEX = _TIER_ORDER.index(DifficultyChoice.NORMAL)

# Fallback affection-band thresholds when the #1699 system-track tiers aren't
# seeded (mirrors the relationship_scale seed values). PLACEHOLDER magnitudes.
_FALLBACK_BAND_THRESHOLDS = [25, 100, 500, 2000]


def _affection_band_thresholds(*, positive: bool) -> list[int]:
    """The ladder's rungs: the system tracks' RelationshipTier thresholds (#1697/#1699).

    Positive affection reads the Regard track's bands, negative the Friction
    track's, so the difficulty ladder and the relationship screen share one
    authored scale. Falls back to the seed constants when unseeded.
    """
    from world.relationships.constants import TrackSystemKey  # noqa: PLC0415
    from world.relationships.models import RelationshipTier  # noqa: PLC0415

    key = TrackSystemKey.REGARD if positive else TrackSystemKey.FRICTION
    thresholds = list(
        RelationshipTier.objects.filter(track__system_key=key)
        .order_by("point_threshold")
        .values_list("point_threshold", flat=True)
    )
    return thresholds or _FALLBACK_BAND_THRESHOLDS


def _affection_base_index(affection: int) -> int:
    """Map affection (target→actor) to a base tier ordinal: one tier per band (#1697).

    Neutral (0 — the stranger/NPC default) = NORMAL. Each positive band the
    affection crosses eases one tier; each negative band crossed hardens one
    tier; clamped to the tier range. Bands come from the seeded 25/100/500/2000
    system-track ladder, so "how much they like you" reads off the same scale
    players see on the relationship screen.
    """
    if affection == 0:
        return _NORMAL_INDEX
    thresholds = _affection_band_thresholds(positive=affection > 0)
    magnitude = abs(affection)
    crossed = sum(1 for threshold in thresholds if magnitude >= threshold)
    shifted = _NORMAL_INDEX - crossed if affection > 0 else _NORMAL_INDEX + crossed
    return max(0, min(len(_TIER_ORDER) - 1, shifted))


def _affection_toward(perceiver: CharacterSheet, perceived: CharacterSheet) -> int:
    from world.relationships.models import CharacterRelationship  # noqa: PLC0415

    relationship = CharacterRelationship.objects.filter(source=perceiver, target=perceived).first()
    return relationship.affection if relationship is not None else 0


def _exploitable_easing(target_sheet: CharacterSheet) -> int:
    """Max ``exploitable_tiers`` across the target's active conditions (#1697).

    The Smitten seam: an exploitable state on the TARGET eases the roller's
    difficulty by a data-configured tier count (max, not sum — two exploitable
    conditions never stack). 0 when the target bears none or has no character.
    """
    from world.conditions.services import get_active_conditions  # noqa: PLC0415

    character = target_sheet.character
    if character is None:
        return 0
    return max(
        (
            instance.condition.exploitable_tiers
            for instance in get_active_conditions(character).select_related("condition")
        ),
        default=0,
    )


def resolved_base_difficulty(
    *,
    action_request: SceneActionRequest,
    difficulty_choice: str,
    target_sheet: CharacterSheet | None,
    extra_tier_modifier: int = 0,
) -> int:
    """Base difficulty before resist-effort: affection-derived for social actions, else absolute.

    For a social action it is ``affection_base + (difficulty_choice relative to NORMAL) +
    difficulty_tier_modifier + extra_tier_modifier`` in tier space, clamped. Callers add
    the resist-effort increment. ``extra_tier_modifier`` is the request-specific shift a
    caller computes from the ask itself — today the boon relative-cost band for NPC
    targets (#2540); ignored on the non-social branch.

    For a non-social targeted action, only ``exploitable_tiers`` easing applies (a
    Smitten target is easier to exploit in ALL ways, not just socially) — the
    affection-derived base and ``difficulty_tier_modifier`` remain social-only.
    """
    template = action_request.action_template
    if template is None:
        return DIFFICULTY_VALUES[difficulty_choice]
    if template.category != _SOCIAL_CATEGORY:
        # Non-social: apply only exploitable easing (a Smitten target is easier to
        # exploit in ALL ways), not affection base or tier modifier (#2241).
        if target_sheet is None:
            return DIFFICULTY_VALUES[difficulty_choice]
        easing = _exploitable_easing(target_sheet)
        if easing == 0:
            return DIFFICULTY_VALUES[difficulty_choice]
        choice_index = _TIER_ORDER.index(DifficultyChoice(difficulty_choice))
        eased_index = max(0, choice_index - easing)
        return DIFFICULTY_VALUES[_TIER_ORDER[eased_index]]

    affection = 0
    exploitable_easing = 0
    if target_sheet is not None:
        actor_sheet = action_request.initiator_persona.character_sheet
        affection = _affection_toward(target_sheet, actor_sheet)
        exploitable_easing = _exploitable_easing(target_sheet)

    base_index = _affection_base_index(affection)
    defender_shift = _TIER_ORDER.index(DifficultyChoice(difficulty_choice)) - _NORMAL_INDEX
    shifted = (
        base_index
        + defender_shift
        + template.difficulty_tier_modifier
        + extra_tier_modifier
        - exploitable_easing
    )
    final_index = max(0, min(len(_TIER_ORDER) - 1, shifted))
    return DIFFICULTY_VALUES[_TIER_ORDER[final_index]]

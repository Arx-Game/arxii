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

# PLACEHOLDER affection bands (signed track-point sum, target→actor).
_WARM_AFFECTION = 100
_VERY_HOSTILE_AFFECTION = -500


def _affection_base_index(affection: int) -> int:
    """Map affection (target→actor) to a base difficulty-tier ordinal. PLACEHOLDER thresholds."""
    if affection <= _VERY_HOSTILE_AFFECTION:
        return _TIER_ORDER.index(DifficultyChoice.HARROWING)
    if affection < 0:
        return _TIER_ORDER.index(DifficultyChoice.HARD)
    if affection >= _WARM_AFFECTION:
        return _TIER_ORDER.index(DifficultyChoice.EASY)
    return _NORMAL_INDEX


def _affection_toward(perceiver: CharacterSheet, perceived: CharacterSheet) -> int:
    from world.relationships.models import CharacterRelationship  # noqa: PLC0415

    relationship = CharacterRelationship.objects.filter(source=perceiver, target=perceived).first()
    return relationship.affection if relationship is not None else 0


def resolved_base_difficulty(
    *,
    action_request: SceneActionRequest,
    difficulty_choice: str,
    target_sheet: CharacterSheet | None,
) -> int:
    """Base difficulty before resist-effort: affection-derived for social actions, else absolute.

    For a social action it is ``affection_base + (difficulty_choice relative to NORMAL) +
    difficulty_tier_modifier`` in tier space, clamped. Callers add the resist-effort increment.
    """
    template = action_request.action_template
    if template is None or template.category != _SOCIAL_CATEGORY:
        return DIFFICULTY_VALUES[difficulty_choice]

    affection = 0
    if target_sheet is not None:
        actor_sheet = action_request.initiator_persona.character_sheet
        affection = _affection_toward(target_sheet, actor_sheet)

    base_index = _affection_base_index(affection)
    defender_shift = _TIER_ORDER.index(DifficultyChoice(difficulty_choice)) - _NORMAL_INDEX
    shifted = base_index + defender_shift + template.difficulty_tier_modifier
    final_index = max(0, min(len(_TIER_ORDER) - 1, shifted))
    return DIFFICULTY_VALUES[_TIER_ORDER[final_index]]

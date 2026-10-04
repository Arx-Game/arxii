"""One difficulty function for a character acting socially on a character (#4145).

Every social check against a character resolves here: scene social actions, the combat
social verbs and standoffs. Terms: the defender's resist increment (Composure plus level;
never combined with level_opposition), a caller-supplied base (the affection band in scenes),
mindless resistance, drive easing in difficulty bands, and actor-side contributions: the
approach's sway modifier counted once plus once per strength step of each hit drive, and
relationship-gated contributions.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from world.checks.constants import ModifierSourceKind
from world.checks.services import compute_resist_increment
from world.checks.types import ModifierContribution
from world.fatigue.constants import EffortLevel
from world.mechanics.services import get_modifier_total
from world.scenes.action_constants import DIFFICULTY_BAND_STEP

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.checks.models import CheckType
    from world.mechanics.models import ModifierTarget


@dataclass(frozen=True)
class DriveHit:
    """A drive of the target the actor's approach touches."""

    label: str  # property name, for display only
    strength: int  # DriveStrength value 1..3


@dataclass(frozen=True)
class SocialDifficulty:
    """Graded difficulty plus the actor-side contributions to pass as extra_contributions."""

    difficulty: int
    contributions: list[ModifierContribution] = field(default_factory=list)
    eased_bands: int = 0


def social_target_difficulty(  # noqa: PLR0913
    *,
    actor_sheet: CharacterSheet,
    target_character: ObjectDB | None,
    check_type: CheckType | None,  # noqa: ARG001 - part of the shared signature; reserved for check-aware terms
    base_difficulty: int = 0,
    target_level: int | None = None,
    resist_effort: str = EffortLevel.MEDIUM,
    drive_hits: Sequence[DriveHit] = (),
    sway_target: ModifierTarget | None = None,
    mindless_resistance: int = 0,
    extra_bands: int = 0,
    perceiver_sheet: CharacterSheet | None = None,
    resist_increment: int | None = None,
) -> SocialDifficulty:
    """Grade a social check on a character. See the module docstring for the terms.

    ``resist_increment`` lets a caller grading many checks against one target compute
    the defender's resist once (``compute_resist_increment``) and pass it in.
    """
    eased_bands = sum(hit.strength for hit in drive_hits)
    resist = 0
    if resist_increment is not None:
        resist = resist_increment
    elif target_character is not None:
        resist = compute_resist_increment(
            target_character, resist_effort, level_override=target_level
        )
    difficulty = (
        base_difficulty
        + resist
        + mindless_resistance
        + DIFFICULTY_BAND_STEP * (extra_bands - eased_bands)
    )
    contributions: list[ModifierContribution] = []
    if sway_target is not None:
        per_count = get_modifier_total(actor_sheet, sway_target)
        if per_count:
            contributions.append(
                ModifierContribution(
                    source_kind=ModifierSourceKind.CHARACTER,
                    source_label=sway_target.name,
                    value=per_count * (1 + eased_bands),
                )
            )
    if perceiver_sheet is not None:
        from world.relationships.services import (  # noqa: PLC0415
            relationship_gated_contributions,
        )

        contributions.extend(
            relationship_gated_contributions(perceiver=perceiver_sheet, perceived=actor_sheet)
        )
    return SocialDifficulty(
        difficulty=max(0, difficulty),
        contributions=contributions,
        eased_bands=eased_bands,
    )

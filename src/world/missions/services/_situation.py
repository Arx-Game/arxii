"""Shared ``SituationContext`` builder for mission checks (#2536 slice 3 review).

Hoisted out of ``resolution.py``/``support.py``/``report.py`` where it was
duplicated byte-for-byte — a mission check that wants Court/Battle situational
perk scoping builds its ``SituationContext`` here instead of reimplementing
the sheet guard locally. The guard convention: a character with no
``CharacterSheet`` yields ``None`` (never raises), mirroring the same guard
``_situational_perk_check_bonus`` applies to itself — so a checker without a
sheet stays byte-identical to the pre-#2536 default (no bonus, no penalty).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.covenants.perks.context import SituationContext
    from world.missions.models import MissionInstance


def mission_situation_ctx(
    character: ObjectDB, instance: MissionInstance
) -> SituationContext | None:
    """The ``SituationContext`` for a mission check by ``character`` in ``instance``
    (#2536 slice 3 Court wiring). ``None`` when the character has no
    ``CharacterSheet`` — mirrors the guard ``_situational_perk_check_bonus`` applies
    itself, so a checker without a sheet is byte-identical to the pre-#2536 default.
    """
    from world.covenants.perks.context import SituationContext  # noqa: PLC0415

    try:
        sheet = character.sheet_data
    except (ObjectDoesNotExist, AttributeError):
        return None
    return SituationContext(
        holder=sheet, subject=sheet, target=None, resolution=None, mission=instance
    )

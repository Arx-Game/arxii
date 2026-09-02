"""Tier-1 instantiation — making a crowd NPC real (#2827 phase 2).

The moment a player engages a faceless functionary, the game mints the
identity: a generated name from the room's name culture, a Character +
CharacterSheet + PRIMARY persona (`create_character_with_sheet` — the same
call asset promotion makes), a link on the placement row, and a shelf
entry on the never-claimable NPC roster for staff visibility. This is
ADR-0058's ephemeral→durable seam, formalized: from here rapport and
regard accrue to a durable persona.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from django.db import transaction

from world.npc_services.models import Functionary, NameCulture, NameCultureEntry, NamePart

if TYPE_CHECKING:
    from evennia_extensions.models import RoomProfile
    from world.roster.models import Family
    from world.scenes.models import Persona


# #2853: anima pool for freshly-instantiated (quiescent-tier) NPCs. PLACEHOLDER.
NPC_QUIESCENT_ANIMA = 2


def name_culture_for_room(room: RoomProfile) -> NameCulture | None:
    """The nearest authored culture up the room's area chain, else the global default."""
    from world.areas.models import AreaClosure  # noqa: PLC0415

    if room.area_id is not None:
        ancestor_ids = list(
            AreaClosure.objects.filter(descendant_id=room.area_id)
            .order_by("depth")
            .values_list("ancestor_id", flat=True)
        )
        cultures = {
            culture.area_id: culture
            for culture in NameCulture.objects.filter(area_id__in=ancestor_ids)
        }
        for area_id in ancestor_ids:  # nearest ancestor first
            if area_id in cultures:
                return cultures[area_id]
    return NameCulture.objects.filter(area__isnull=True, society__isnull=True).first()


def _surname_for(family, culture) -> str:
    """A family name if the NPC has one, else a culturally-weighted draw, else nothing."""
    if family is not None:
        return family.name
    if culture:
        return _weighted_value(culture, NamePart.SURNAME)
    return ""


def _weighted_value(culture: NameCulture, part: str) -> str:
    entries = list(NameCultureEntry.objects.filter(culture=culture, part=part))
    if not entries:
        return ""
    weights = [entry.weight for entry in entries]
    # S311/NOSONAR: game RNG for flavor names, not crypto.
    return random.choices(entries, weights=weights, k=1)[0].value  # noqa: S311 # NOSONAR


def generate_person_name(
    culture: NameCulture | None,
    *,
    family: Family | None = None,
) -> str:
    """A themed full name: cultural given + (family name | cultural surname).

    No culture authored → a neutral placeholder given name, so instantiation
    never blocks on content.
    """
    given = _weighted_value(culture, NamePart.GIVEN) if culture else ""
    if not given:
        given = "Sojourner"  # PLACEHOLDER: unseeded shard fallback
    surname = _surname_for(family, culture)
    return f"{given} {surname}".strip()


def _npc_roster():
    from world.roster.models import Roster  # noqa: PLC0415
    from world.roster.models.choices import RosterType  # noqa: PLC0415

    roster, _ = Roster.objects.get_or_create(
        roster_type=RosterType.NPC,
        defaults={
            "name": "NPCs",
            "is_active": False,
            "is_public": False,
            "allow_applications": False,
        },
    )
    return roster


@transaction.atomic
def materialize_functionary(
    functionary: Functionary,
    *,
    family: Family | None = None,
) -> Persona:
    """Make a faceless placement real: mint identity, link it, shelf it.

    Idempotent — an already-materialized placement returns its persona.
    """
    from world.character_sheets.services import create_character_with_sheet  # noqa: PLC0415
    from world.roster.models import RosterEntry  # noqa: PLC0415

    if functionary.persona_id is not None:
        return functionary.persona

    culture = name_culture_for_room(functionary.room)
    full_name = functionary.name_override or generate_person_name(culture, family=family)
    _character, sheet, persona = create_character_with_sheet(
        character_key=full_name,
        primary_persona_name=full_name,
    )
    # #2853: instantiated NPCs get a tiny anima pool so feeding has something
    # real (and dangerous) to draw on — quiescent tiers hold almost nothing, so
    # a gorging feeder can genuinely kill. PLACEHOLDER magnitude.
    from world.magic.models.anima import CharacterAnima  # noqa: PLC0415

    CharacterAnima.objects.get_or_create(
        character=sheet,
        defaults={"current": NPC_QUIESCENT_ANIMA, "maximum": NPC_QUIESCENT_ANIMA},
    )
    functionary.persona = persona
    if not functionary.name_override:
        functionary.name_override = full_name
    functionary.save(update_fields=["persona", "name_override"])

    RosterEntry.objects.get_or_create(
        character_sheet=sheet,
        defaults={"roster": _npc_roster()},
    )
    from world.npc_services.personality import assign_random_personality  # noqa: PLC0415

    assign_random_personality(persona)
    return persona


def materialize_role_in_room(room: RoomProfile, role) -> Persona | None:
    """Materialize the room's placement of ``role`` if one exists (else None)."""
    functionary = Functionary.objects.filter(role=role, room=room, is_active=True).first()
    if functionary is None:
        return None
    return materialize_functionary(functionary)

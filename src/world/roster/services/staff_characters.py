"""Staff/GM OOC character minting (#3283).

The world builder (and every staff action surface) dispatches through a
character the account owns, but an OOC staff tool character has no business
going through the CG wizard — none of CG's output matters for it, and CG's
content gates (species/beginnings eligibility) can block it entirely on a
fresh deploy. This service mints the whole working set in one transaction:
Character + CharacterSheet + PRIMARY Persona (via the blessed
``create_character_with_sheet``), a RosterEntry on the NPC shelf (staff-side;
never publicly listed), and an active RosterTenure binding it to the
requesting account — which is exactly what ``IsCharacterOwner`` and the
builder's actor resolution key on.

``mint_story_npc`` below is the GMProfile-gated follow-on this docstring used
to describe as deliberately not built (#3426): a JUNIOR+ GM mints a Story NPC
through the same working set, capped per GM level and tenure-bound to their
own account so the existing persona picker and telnet ``@ic`` work on it
immediately. Free-form sheet editing still rides the Django admin.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.roster.models import NPCStatlinePreset


class StaffMintError(Exception):
    """Raised on an invalid mint; carries a player-safe message."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.user_message = message


@transaction.atomic
def mint_staff_character(account: AccountDB, name: str) -> ObjectDB:
    """Mint an OOC staff character bound to ``account``; returns the character."""
    from evennia.objects.models import ObjectDB  # noqa: PLC0415

    from evennia_extensions.models import PlayerData  # noqa: PLC0415
    from world.character_sheets.services import create_character_with_sheet  # noqa: PLC0415
    from world.roster.models import Roster, RosterEntry, RosterTenure  # noqa: PLC0415
    from world.roster.models.choices import RosterType  # noqa: PLC0415

    name = (name or "").strip()
    if not name:
        msg = "Name the character."
        raise StaffMintError(msg)
    if ObjectDB.objects.filter(db_key__iexact=name).exists():
        msg = "A character by that name already exists."
        raise StaffMintError(msg)

    character, sheet, _persona = create_character_with_sheet(
        character_key=name, primary_persona_name=name
    )
    # Keyed on roster_type (unique), not name (#3426 in-scope bugfix): the seeded
    # shelf is named "NPCs" (world/roster/seeds.py), so a name="NPC" lookup never
    # matches it on a seeded DB and the fallback create collides on the unique
    # roster_type column, raising IntegrityError. roster_type is the shelf's real
    # identity (#2728) -- match it the way seeds.py itself does.
    roster, _ = Roster.objects.get_or_create(roster_type=RosterType.NPC, defaults={"name": "NPCs"})
    entry = RosterEntry.objects.create(character_sheet=sheet, roster=roster)
    player_data, _ = PlayerData.objects.get_or_create(account=account)
    RosterTenure.objects.create(
        player_data=player_data,
        roster_entry=entry,
        player_number=1,
        start_date=timezone.now(),
        approved_date=timezone.now(),
        approved_by=player_data,
    )
    return character


def check_story_npc_cap(gm_account: AccountDB) -> None:
    """Validate JUNIOR+ GM trust and ``GMLevelCap.max_story_npcs`` for ``gm_account``.

    The one authorization seam for "does this account get another Story-NPC
    tenure right now" (#3426) -- shared by ``mint_story_npc`` and
    ``finalize_gm_character``'s ``claim_as_npc`` path, so the two on-ramps to
    an NPC-shelf tenure enforce identically. Staff bypass via
    ``is_staff_observer``.

    No ``select_for_update`` on the cap count: a double-submit briefly
    exceeding the cap is accepted, matching ``world.gm.story_services``'s
    documented norm.

    Raises:
        StaffMintError: missing GM trust, below JUNIOR, or at/over cap.
    """
    from core_management.permissions import is_staff_observer  # noqa: PLC0415
    from world.gm.constants import GMLevel, gm_level_index  # noqa: PLC0415
    from world.gm.models import GMLevelCap, GMProfile  # noqa: PLC0415
    from world.roster.models import RosterTenure  # noqa: PLC0415
    from world.roster.models.choices import RosterType  # noqa: PLC0415

    if is_staff_observer(gm_account):
        return

    try:
        profile = gm_account.gm_profile
    except GMProfile.DoesNotExist:
        msg = "GM trust required."
        raise StaffMintError(msg) from None

    if gm_level_index(profile.level) < gm_level_index(GMLevel.JUNIOR):
        msg = f"Requires {GMLevel(GMLevel.JUNIOR).label} or higher."
        raise StaffMintError(msg)

    cap = GMLevelCap.objects.filter(level=profile.level).first()
    max_story_npcs = cap.max_story_npcs if cap is not None else 0
    active_count = RosterTenure.objects.filter(
        player_data__account=gm_account,
        roster_entry__roster__roster_type=RosterType.NPC,
        end_date__isnull=True,
    ).count()
    if active_count >= max_story_npcs:
        msg = (
            f"You already have {active_count} story NPC(s) -- your level allows "
            f"{max_story_npcs}. Ask staff to release one, or raise your GM level."
        )
        raise StaffMintError(msg)


@transaction.atomic
def apply_npc_preset(sheet: CharacterSheet, preset: NPCStatlinePreset) -> None:
    """Apply a curated statline preset's trait/skill lines to ``sheet`` (#3427).

    Mirrors CG finalize's write shape exactly -- ``_create_stat_values``/
    ``_create_skill_values`` in ``world.character_creation.services`` --
    rather than calling them: those are private draft-dict readers, not a
    reusable seam. For each trait line, writes a ``CharacterTraitValue`` at
    ``display_value * STAT_DISPLAY_DIVISOR``. For each skill line, writes a
    ``CharacterSkillValue`` plus the #2894 bridging ``CharacterTraitValue`` on
    ``skill.trait`` (the check engine reads only trait rows). Every written
    value gets a ``CharacterTraitChange`` provenance stamp
    (``old_value=0``, ``source=NPC_PRESET``).

    Refuses (Decision 1, #3427 spec: no re-apply in v1) a sheet that already
    carries any NPC_PRESET-sourced stamp -- a second application path invites
    drift; staff adjust an existing NPC's values via admin instead.

    Raises:
        StaffMintError: ``sheet`` already carries a preset-sourced stamp.
    """
    from world.skills.models import CharacterSkillValue  # noqa: PLC0415
    from world.traits.models import (  # noqa: PLC0415
        STAT_DISPLAY_DIVISOR,
        CharacterTraitChange,
        CharacterTraitValue,
        TraitChangeSource,
    )

    already_applied = CharacterTraitChange.objects.filter(
        character_sheet=sheet, source=TraitChangeSource.NPC_PRESET
    ).exists()
    if already_applied:
        msg = "This character already has a preset applied."
        raise StaffMintError(msg)

    trait_lines = list(preset.trait_lines.select_related("trait"))
    trait_values = [
        CharacterTraitValue(
            character=sheet,
            trait=line.trait,
            value=line.display_value * STAT_DISPLAY_DIVISOR,
        )
        for line in trait_lines
    ]
    CharacterTraitValue.objects.bulk_create(trait_values)

    skill_lines = list(preset.skill_lines.select_related("skill", "skill__trait"))
    skill_trait_values: list[CharacterTraitValue] = []
    for line in skill_lines:
        CharacterSkillValue.objects.create(
            character=sheet,
            skill=line.skill,
            value=line.value,
            development_points=0,
            rust_points=0,
        )
        skill_trait_values.append(
            CharacterTraitValue(character=sheet, trait=line.skill.trait, value=line.value)
        )
    CharacterTraitValue.objects.bulk_create(skill_trait_values)

    all_trait_values = trait_values + skill_trait_values
    CharacterTraitChange.objects.bulk_create(
        [
            CharacterTraitChange(
                character_sheet=sheet,
                trait=tv.trait,
                old_value=0,
                new_value=tv.value,
                source=TraitChangeSource.NPC_PRESET,
            )
            for tv in all_trait_values
        ]
    )


@transaction.atomic
def mint_story_npc(
    *,
    gm_account: AccountDB,
    name: str,
    description: str = "",
    preset: NPCStatlinePreset | None = None,
) -> ObjectDB:
    """Mint a Story NPC for a JUNIOR+ GM, tenure-bound to their account (#3426).

    Validates trust + the per-level cap via ``check_story_npc_cap``, then
    delegates the actual mint to ``mint_staff_character``'s working set
    (Character + sheet + PRIMARY persona + NPC-shelf entry + active
    RosterTenure) -- its documented follow-on, no parallel creation path.

    ``description``, when given, lands in ``CharacterSheet.additional_desc``
    via ``set_physical_description`` -- the seam ``get_display_description()``
    reads. ``preset``, when given, applies a curated statline via
    ``apply_npc_preset`` (#3427) so the minted NPC can actually roll a check
    immediately, without a GM hand-inventing stat/skill values.

    Raises:
        StaffMintError: missing GM trust, below JUNIOR, at/over cap, or (with
            a ``preset``) a preset-application refusal.
    """
    from world.character_sheets.services import set_physical_description  # noqa: PLC0415

    check_story_npc_cap(gm_account)

    character = mint_staff_character(gm_account, name)
    if description:
        set_physical_description(character.sheet_data, description)
    if preset is not None:
        apply_npc_preset(character.sheet_data, preset)
    return character

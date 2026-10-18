"""Copy a major NPC's sections onto another NPC, or the whole NPC as a new one (#4418).

A holder builds a cast faster by lending a template's pieces than by retyping them. Every
copy here replaces the target's section and only ever reads the source. Writes ride the
existing seams: ``staff_edit_sheet`` for identity and prose, trait-change provenance for
powers, ``author_npc_regard`` and ``set_npc_preferences`` for the opinion axis.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.character_sheets.types import ProfileTextField
from world.roster.constants import NPCSection

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.character_sheets.models import CharacterSheet
    from world.roster.models import RosterEntry
    from world.traits.models import CharacterTraitChange, Trait


def copy_npc_section(
    source_entry: RosterEntry, target_entry: RosterEntry, section: NPCSection
) -> None:
    """Replace ``section`` of ``target_entry`` with ``source_entry``'s; the source is untouched.

    ``NPCSection.ALL`` copies every section plus the holder's ``notes_for_player``.
    """
    with transaction.atomic():
        if section == NPCSection.ALL:
            for part in (
                NPCSection.IDENTITY,
                NPCSection.DESCRIPTION,
                NPCSection.BACKGROUND,
                NPCSection.POWERS,
                NPCSection.REGARD,
                NPCSection.PREFERENCES,
            ):
                _copy_one_section(source_entry, target_entry, part)
            _copy_notes(source_entry, target_entry)
        else:
            _copy_one_section(source_entry, target_entry, section)


def copy_npc_as_new(
    source_entry: RosterEntry, *, by: AccountDB, name: str, as_template: bool = False
) -> RosterEntry:
    """Mint a new NPC named ``name`` that is a copy of ``source_entry``; ``by`` owns it.

    The mint enforces the GM trust and cap rules (a template counts against no cap).
    """
    from world.roster.services.staff_characters import mint_story_npc  # noqa: PLC0415

    with transaction.atomic():
        character = mint_story_npc(gm_account=by, name=name, as_template=as_template)
        new_entry = character.sheet_data.roster_entry
        copy_npc_section(source_entry, new_entry, NPCSection.ALL)
    return new_entry


def _copy_one_section(
    source_entry: RosterEntry, target_entry: RosterEntry, section: NPCSection
) -> None:
    source = source_entry.character_sheet
    target = target_entry.character_sheet
    if section == NPCSection.IDENTITY:
        _copy_identity(source, target)
    elif section == NPCSection.DESCRIPTION:
        _copy_prose(source, target, ProfileTextField.DESCRIPTION)
    elif section == NPCSection.BACKGROUND:
        _copy_prose(source, target, ProfileTextField.BACKGROUND)
    elif section == NPCSection.POWERS:
        _copy_powers(source, target)
    elif section == NPCSection.REGARD:
        _copy_regard(source, target)
    elif section == NPCSection.PREFERENCES:
        _copy_preferences(source, target)


def _copy_identity(source: CharacterSheet, target: CharacterSheet) -> None:
    from world.character_sheets.services import (  # noqa: PLC0415
        STAFF_IDENTITY_SCALARS,
        STAFF_PRONOUNS_FIELD,
        STAFF_SHEET_CHOICES,
        staff_edit_sheet,
    )

    changes = {
        key: getattr(source, key)
        for key in (*STAFF_IDENTITY_SCALARS, *STAFF_SHEET_CHOICES)
        # An unset pronoun set would stop gender from choosing the target's pronoun forms.
        if not (key == STAFF_PRONOUNS_FIELD and source.pronouns is None)
    }
    staff_edit_sheet(target, changes, edited_by=None)


def _copy_prose(source: CharacterSheet, target: CharacterSheet, field: str) -> None:
    from world.character_sheets.services import staff_edit_sheet  # noqa: PLC0415

    if field == ProfileTextField.DESCRIPTION:
        text = source.additional_desc
    else:
        profile = source.true_profile
        text = getattr(profile, field) if profile is not None else ""
    staff_edit_sheet(target, {field: text}, edited_by=None)


def _copy_powers(source: CharacterSheet, target: CharacterSheet) -> None:
    from world.magic.constants import AcquisitionOrigin  # noqa: PLC0415
    from world.magic.models import CharacterGift, CharacterTechnique  # noqa: PLC0415
    from world.skills.models import CharacterSkillValue  # noqa: PLC0415
    from world.traits.models import CharacterTraitChange, CharacterTraitValue  # noqa: PLC0415

    source_traits = list(CharacterTraitValue.objects.filter(character=source))
    existing = {row.trait_id: row for row in CharacterTraitValue.objects.filter(character=target)}
    changes: list[CharacterTraitChange] = []
    kept = {row.trait_id for row in source_traits}
    for row in source_traits:
        old = existing.get(row.trait_id)
        old_value = old.value if old is not None else 0
        if old is None:
            CharacterTraitValue.objects.create(character=target, trait=row.trait, value=row.value)
        elif old.value != row.value:
            old.value = row.value
            old.save(update_fields=["value"])
        else:
            continue
        changes.append(_trait_change(target, row.trait, old_value, row.value))
    for trait_id, old in existing.items():
        if trait_id not in kept:
            changes.append(_trait_change(target, old.trait, old.value, 0))
            old.delete()
    CharacterTraitChange.objects.bulk_create(changes)

    CharacterSkillValue.objects.filter(character=target).delete()
    CharacterSkillValue.objects.bulk_create(
        [
            CharacterSkillValue(
                character=target,
                skill=row.skill,
                value=row.value,
                development_points=row.development_points,
                rust_points=row.rust_points,
            )
            for row in CharacterSkillValue.objects.filter(character=source)
        ]
    )

    CharacterTechnique.objects.filter(character=target).delete()
    CharacterGift.objects.filter(character=target).delete()
    CharacterGift.objects.bulk_create(
        [
            CharacterGift(character=target, gift=row.gift, origin=AcquisitionOrigin.GM_GRANT)
            for row in CharacterGift.objects.filter(character=source)
        ]
    )
    CharacterTechnique.objects.bulk_create(
        [
            CharacterTechnique(
                character=target, technique=row.technique, origin=AcquisitionOrigin.GM_GRANT
            )
            for row in CharacterTechnique.objects.filter(
                character=source, source__isnull=True, role_source__isnull=True
            )
        ]
    )


def _trait_change(
    target: CharacterSheet, trait: Trait, old_value: int, new_value: int
) -> CharacterTraitChange:
    from world.traits.models import CharacterTraitChange, TraitChangeSource  # noqa: PLC0415

    return CharacterTraitChange(
        character_sheet=target,
        trait=trait,
        old_value=old_value,
        new_value=new_value,
        source=TraitChangeSource.STAFF_EDIT,
    )


def _copy_regard(source: CharacterSheet, target: CharacterSheet) -> None:
    from world.npc_services.models import NpcRegard  # noqa: PLC0415
    from world.npc_services.regard import author_npc_regard  # noqa: PLC0415

    source_persona = source.primary_persona
    target_persona = target.primary_persona
    rows = list(NpcRegard.objects.filter(holder_persona=source_persona, ended_at__isnull=True))
    NpcRegard.objects.filter(
        holder_persona=target_persona, ended_at__isnull=True
    ).update_with_reason(
        reason="issue #4418: replacing an NPC's regard section", ended_at=timezone.now()
    )
    for row in rows:
        author_npc_regard(
            holder_persona=target_persona,
            target=row.get_active_target(),
            value=row.value,
            reason=row.reason,
        )


def _copy_preferences(source: CharacterSheet, target: CharacterSheet) -> None:
    from world.npc_services.models import NpcPreference  # noqa: PLC0415
    from world.npc_services.personality import set_npc_preferences  # noqa: PLC0415

    rows = NpcPreference.objects.filter(persona=source.primary_persona).select_related("trait")
    set_npc_preferences(target.primary_persona, [(row.trait, row.valence) for row in rows])


def _copy_notes(source_entry: RosterEntry, target_entry: RosterEntry) -> None:
    from world.roster.models import StoryNPCSettings  # noqa: PLC0415

    source_settings = StoryNPCSettings.objects.filter(roster_entry=source_entry).first()
    notes = source_settings.notes_for_player if source_settings is not None else ""
    settings, _ = StoryNPCSettings.objects.get_or_create(roster_entry=target_entry)
    settings.notes_for_player = notes
    settings.save(update_fields=["notes_for_player"])

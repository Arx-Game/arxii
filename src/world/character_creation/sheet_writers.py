"""The rows character creation writes, as public services on a live sheet (#3988 piece B).

Each writer takes the sheet and explicit values instead of a draft, so character
creation's finalize and staff edit mode (#4221) go through one writer per family.
Staff skip CG's point budgets and costs; structural rules (ranges, uniqueness,
species-allowed options) hold for both. The ``*_consequences`` functions fire the
grants a choice carries in CG (codex entries, languages, ritual knowledge), all
idempotent, so a staff-built sheet ends where CG would have left it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING

from django.db import transaction

from world.character_creation.constants import STAT_MAX_VALUE, STAT_MIN_VALUE
from world.traits.constants import STAT_DISPLAY_DIVISOR

if TYPE_CHECKING:
    from world.character_creation.models import Beginnings
    from world.character_sheets.models import CharacterSheet, Gender, ProfileBeginnings
    from world.classes.models import Path
    from world.distinctions.models import Distinction
    from world.forms.models import FormTrait, FormTraitOption
    from world.roster.models import RosterEntry
    from world.scenes.models import Persona
    from world.skills.models import Skill, Specialization
    from world.traits.models import Trait
    from world.worship.models import WorshippedBeing


class SheetWriteError(ValueError):
    """A sheet write the rules refuse, with a message safe to show."""

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


def set_stat_values(sheet: CharacterSheet, values: Mapping[Trait, int], *, source: str) -> None:
    """Set stats at display scale (1 to 5), creating missing rows and updating others.

    Storage is internal x10 (#2894, ADR-0193). Every row that changes, or is new,
    gets a ``CharacterTraitChange`` with ``source`` (#3055).
    """
    from world.traits.models import CharacterTraitChange, CharacterTraitValue  # noqa: PLC0415

    for trait, value in values.items():
        if not STAT_MIN_VALUE <= value <= STAT_MAX_VALUE:
            msg = f"{trait.name} must be between {STAT_MIN_VALUE} and {STAT_MAX_VALUE}."
            raise SheetWriteError(msg)
    existing = {
        row.trait_id: row
        for row in CharacterTraitValue.objects.filter(
            character=sheet, trait__in=list(values)
        ).select_related("trait")
    }
    changes: list[CharacterTraitChange] = []
    created: list[CharacterTraitValue] = []
    with transaction.atomic():
        for trait, display in values.items():
            stored = display * STAT_DISPLAY_DIVISOR
            row = existing.get(trait.pk)
            if row is None:
                created.append(CharacterTraitValue(character=sheet, trait=trait, value=stored))
                old = 0
            elif row.value != stored:
                old = row.value
                row.value = stored
                row.save(update_fields=["value"])
            else:
                continue
            changes.append(
                CharacterTraitChange(
                    character_sheet=sheet,
                    trait=trait,
                    old_value=old,
                    new_value=stored,
                    source=source,
                )
            )
        CharacterTraitValue.objects.bulk_create(created)
        CharacterTraitChange.objects.bulk_create(changes)


def _check_skill_caps(
    skills: Mapping[Skill, int], specializations: Mapping[Specialization, int]
) -> None:
    from world.skills.models import SkillPointBudget  # noqa: PLC0415

    budget = SkillPointBudget.get_active_budget()
    for skill, value in skills.items():
        if not 0 <= value <= budget.max_skill_value:
            msg = f"{skill.name} must be between 0 and {budget.max_skill_value}."
            raise SheetWriteError(msg)
    for spec, value in specializations.items():
        if not 0 <= value <= budget.max_specialization_value:
            msg = f"{spec.name} must be between 0 and {budget.max_specialization_value}."
            raise SheetWriteError(msg)


def _set_skill_trait(sheet: CharacterSheet, skill: Skill, value: int, source: str) -> None:
    """The skill's ``CharacterTraitValue`` the check engine reads (#2894), stamped (#3055)."""
    from world.traits.models import CharacterTraitChange, CharacterTraitValue  # noqa: PLC0415

    row = CharacterTraitValue.objects.filter(character=sheet, trait=skill.trait).first()
    old = row.value if row else 0
    if row is None:
        CharacterTraitValue.objects.create(character=sheet, trait=skill.trait, value=value)
    elif row.value != value:
        row.value = value
        row.save(update_fields=["value"])
    else:
        return
    CharacterTraitChange.objects.create(
        character_sheet=sheet, trait=skill.trait, old_value=old, new_value=value, source=source
    )


def set_skill_values(
    sheet: CharacterSheet,
    skills: Mapping[Skill, int],
    specializations: Mapping[Specialization, int],
    *,
    source: str,
    enforce_caps: bool = True,
) -> None:
    """Set skill and specialization values, creating missing rows and updating others.

    A skill also writes the matching ``CharacterTraitValue`` the check engine reads
    (#2894), at the same 1 to 100 value. ``enforce_caps`` holds the configured
    ``max_skill_value`` / ``max_specialization_value``; character creation already
    validated its picks and passes False. Lowering a skill to 0 keeps its row at 0.
    """
    from world.skills.models import (  # noqa: PLC0415
        CharacterSkillValue,
        CharacterSpecializationValue,
    )

    if enforce_caps:
        _check_skill_caps(skills, specializations)
    with transaction.atomic():
        for skill, value in skills.items():
            row, created = CharacterSkillValue.objects.get_or_create(
                character=sheet,
                skill=skill,
                defaults={"value": value, "development_points": 0, "rust_points": 0},
            )
            if not created and row.value != value:
                row.value = value
                row.save(update_fields=["value"])
            _set_skill_trait(sheet, skill, value, source)
        for spec, value in specializations.items():
            row, created = CharacterSpecializationValue.objects.get_or_create(
                character=sheet,
                specialization=spec,
                defaults={"value": value, "development_points": 0},
            )
            if not created and row.value != value:
                row.value = value
                row.save(update_fields=["value"])


def set_true_form_values(
    sheet: CharacterSheet, selections: Mapping[FormTrait, FormTraitOption]
) -> None:
    """Set the TRUE form's trait options, creating the form if the sheet has none.

    An option must belong to its trait and, when the sheet has a species, be one
    the species allows. A changed option moves the natural baseline with it: this
    is the character as made, not a disguise.
    """
    from world.forms.models import CharacterForm, CharacterFormValue, FormType  # noqa: PLC0415
    from world.forms.services import create_true_form  # noqa: PLC0415

    for trait, option in selections.items():
        if option.trait_id != trait.pk:
            msg = f"{option} is not an option of {trait.name}."
            raise SheetWriteError(msg)
    form = CharacterForm.objects.filter(character=sheet, form_type=FormType.TRUE).first()
    if form is None:
        create_true_form(sheet.character, dict(selections))
        return
    with transaction.atomic():
        for trait, option in selections.items():
            CharacterFormValue.objects.update_or_create(
                form=form,
                trait=trait,
                defaults={"option": option, "natural_option": option},
            )


def set_trait_descriptors(persona: Persona, descriptors: Mapping[FormTrait, str]) -> None:
    """Write per-trait descriptors on a face (#2632); a blank text clears one."""
    from world.forms.models import PersonaTraitDescriptor  # noqa: PLC0415

    for trait, text in descriptors.items():
        if text.strip():
            PersonaTraitDescriptor.objects.update_or_create(
                persona=persona, trait=trait, defaults={"text": text.strip()}
            )
        else:
            PersonaTraitDescriptor.objects.filter(persona=persona, trait=trait).delete()


def set_beginnings(sheet: CharacterSheet, beginnings: Beginnings) -> ProfileBeginnings:
    """Set where play began: the one ``character_creation`` ProfileBeginnings (#3775).

    Replaces an existing creation row, so a sheet holds at most one; the
    other sources (a recovered memory, a past life) are untouched.
    """
    from world.character_sheets.models import ProfileBeginnings  # noqa: PLC0415
    from world.character_sheets.services import ensure_true_profile  # noqa: PLC0415
    from world.character_sheets.types import ProfileBeginningsSource  # noqa: PLC0415

    profile = ensure_true_profile(sheet)
    with transaction.atomic():
        ProfileBeginnings.objects.filter(
            profile=profile, source=ProfileBeginningsSource.CHARACTER_CREATION
        ).exclude(beginnings=beginnings).delete()
        row, _ = ProfileBeginnings.objects.update_or_create(
            profile=profile,
            beginnings=beginnings,
            defaults={"source": ProfileBeginningsSource.CHARACTER_CREATION},
        )
    return row


def creation_beginnings(sheet: CharacterSheet) -> Beginnings | None:
    """The Beginnings the sheet's play began in, or None."""
    from world.character_sheets.models import ProfileBeginnings  # noqa: PLC0415
    from world.character_sheets.types import ProfileBeginningsSource  # noqa: PLC0415

    if sheet.true_profile_id is None:
        return None
    row = (
        ProfileBeginnings.objects.filter(
            profile_id=sheet.true_profile_id, source=ProfileBeginningsSource.CHARACTER_CREATION
        )
        .select_related("beginnings")
        .first()
    )
    return row.beginnings if row else None


def set_worship_declaration(
    sheet: CharacterSheet,
    public: WorshippedBeing | None,
    secret: WorshippedBeing | None,
) -> None:
    """Create or update the worship declaration; mint the Secret for a secret being (#2355).

    A secret equal to the public being is stored public-only: there is nothing to hide.
    Both None removes nothing; an unaffiliated character simply has no row.
    """
    from world.worship.models import WorshipDeclaration  # noqa: PLC0415
    from world.worship.secrets import mint_worship_secret  # noqa: PLC0415

    if public is None and secret is None:
        return
    if secret is not None and public is not None and secret.pk == public.pk:
        secret = None
    declaration, created = WorshipDeclaration.objects.get_or_create(
        character_sheet=sheet,
        defaults={"public_being": public, "secret_being": secret},
    )
    if not created:
        declaration.public_being = public
        declaration.secret_being = secret
        declaration.save(update_fields=["public_being", "secret_being"])
    if declaration.secret_being is not None:
        mint_worship_secret(declaration)


#: Default pronoun forms by gender key; any other gender reads they/them/their.
_PRONOUNS_BY_GENDER_KEY = {
    "male": ("he", "him", "his"),
    "female": ("she", "her", "her"),
}


def set_pronouns_from_gender(sheet: CharacterSheet, gender: Gender) -> None:
    """Set the sheet's three pronoun strings from a gender (not saved; the caller saves)."""
    subject, obj, possessive = _PRONOUNS_BY_GENDER_KEY.get(gender.key, ("they", "them", "their"))
    sheet.pronoun_subject = subject
    sheet.pronoun_object = obj
    sheet.pronoun_possessive = possessive


def initialize_full_vitals(sheet: CharacterSheet) -> None:
    """Create the vitals row and fill health to the derived maximum.

    ``derive_base_max_health`` needs class levels and stats, so this runs after
    them. Recompute alone never heals from 0, hence the explicit fill.
    """
    from world.magic.services.threads import recompute_max_health_with_threads  # noqa: PLC0415
    from world.vitals.models import CharacterVitals  # noqa: PLC0415

    vitals, _ = CharacterVitals.objects.get_or_create(character_sheet=sheet)
    recompute_max_health_with_threads(sheet)
    vitals.refresh_from_db()
    vitals.health = vitals.max_health
    vitals.save(update_fields=["health"])


def _roster_entry(sheet: CharacterSheet) -> RosterEntry | None:
    """The sheet's roster entry, or None for a sheet that has none yet (a GM draft)."""
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    try:
        return sheet.roster_entry
    except ObjectDoesNotExist:
        return None


def grant_codex_entries(sheet: CharacterSheet, entry_ids: Iterable[int]) -> None:
    """Grant every entry to the sheet's character as KNOWN; nothing without a roster entry."""
    from world.codex.models import CodexEntry  # noqa: PLC0415
    from world.codex.services import grant_codex_entry  # noqa: PLC0415

    entry_ids = list(entry_ids)
    if not entry_ids:
        return
    roster_entry = _roster_entry(sheet)
    if roster_entry is None:
        return
    for entry in CodexEntry.objects.filter(pk__in=entry_ids):
        grant_codex_entry(roster_entry, entry)


def grant_path_codex(sheet: CharacterSheet, path: Path) -> None:
    """The codex entries a Path teaches."""
    from world.codex.models import PathCodexGrant  # noqa: PLC0415

    grant_codex_entries(
        sheet, PathCodexGrant.objects.filter(path=path).values_list("entry_id", flat=True)
    )


def grant_beginnings_codex(sheet: CharacterSheet, beginnings: Beginnings) -> None:
    """The codex entries a Beginnings teaches."""
    from world.codex.models import BeginningsCodexGrant  # noqa: PLC0415

    grant_codex_entries(
        sheet,
        BeginningsCodexGrant.objects.filter(beginnings=beginnings).values_list(
            "entry_id", flat=True
        ),
    )


def grant_distinction_codex(sheet: CharacterSheet, distinctions: Iterable[Distinction]) -> None:
    """The codex entries the given distinctions teach."""
    from world.codex.models import DistinctionCodexGrant  # noqa: PLC0415

    ids = [distinction.pk for distinction in distinctions]
    if not ids:
        return
    grant_codex_entries(
        sheet,
        DistinctionCodexGrant.objects.filter(distinction_id__in=ids).values_list(
            "entry_id", flat=True
        ),
    )


def grant_species_codex(sheet: CharacterSheet) -> None:
    """The codex entries owed to the sheet's species and its parents (#2880)."""
    from world.codex.services import grant_codex_entry  # noqa: PLC0415

    species = sheet.species
    if species is None:
        return
    entries = species.codex_entries
    if not entries:
        return
    roster_entry = _roster_entry(sheet)
    if roster_entry is None:
        return
    for entry in entries:
        grant_codex_entry(roster_entry, entry)


def grant_beginnings_rituals(sheet: CharacterSheet, beginnings: Beginnings) -> None:
    """The rituals a Beginnings teaches (``BeginningsRitualGrant``). Idempotent.

    Beginnings is not one of the sources ``reconcile_ritual_knowledge`` walks, so it
    is granted directly; the caller reconciles after. Nothing without a roster entry.
    """
    from world.magic.models import CharacterRitualKnowledge  # noqa: PLC0415
    from world.magic.models.grants import BeginningsRitualGrant  # noqa: PLC0415

    roster_entry = _roster_entry(sheet)
    if roster_entry is None:
        return
    for ritual_id in BeginningsRitualGrant.objects.filter(beginnings=beginnings).values_list(
        "ritual_id", flat=True
    ):
        CharacterRitualKnowledge.objects.get_or_create(
            roster_entry=roster_entry, ritual_id=ritual_id, defaults={"learned_from": None}
        )


def species_consequences(sheet: CharacterSheet) -> None:
    """What choosing a species carries: its gifts, its languages and its codex."""
    from world.species.services import (  # noqa: PLC0415
        provision_species_gifts,
        provision_starting_languages,
    )

    if sheet.species is None:
        return
    provision_species_gifts(sheet)
    provision_starting_languages(sheet, beginnings=creation_beginnings(sheet))
    grant_species_codex(sheet)


def beginnings_consequences(sheet: CharacterSheet, beginnings: Beginnings) -> None:
    """What a Beginnings carries: its rituals, its codex, its languages, then origin state."""
    from world.character_creation.services import refresh_origin_story_state  # noqa: PLC0415
    from world.magic.services.ritual_knowledge import reconcile_ritual_knowledge  # noqa: PLC0415
    from world.species.services import provision_starting_languages  # noqa: PLC0415

    grant_beginnings_rituals(sheet, beginnings)
    roster_entry = _roster_entry(sheet)
    if roster_entry is not None:
        reconcile_ritual_knowledge(roster_entry)
    grant_beginnings_codex(sheet, beginnings)
    provision_starting_languages(sheet, beginnings=beginnings)
    refresh_origin_story_state(sheet)

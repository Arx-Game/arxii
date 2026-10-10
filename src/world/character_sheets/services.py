"""Service functions for character sheets."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
from django.db import transaction
from evennia.objects.models import ObjectDB
from evennia.utils.create import create_object

from world.character_sheets.models import (
    _PROFILE_FIELDS,
    CharacterSheet,
    Profile,
    ProfileTextVersion,
)
from world.character_sheets.types import ProfileTextField
from world.roster.models import RosterEntry
from world.scenes.constants import PersonaType
from world.scenes.models import Persona

if TYPE_CHECKING:
    from world.magic.models import CharacterAura


def can_edit_character_sheet(
    user: AbstractBaseUser | AnonymousUser, roster_entry: RosterEntry
) -> bool:
    """True if the user is the original creator (player_number=1) or staff.

    Requires tenures to be prefetched with select_related("player_data__account").
    """
    if not user.is_authenticated:
        return False
    if user.is_staff:
        return True
    first = roster_entry.first_tenure
    return first is not None and first.player_data.account == user


@transaction.atomic
def create_character_with_sheet(
    *,
    character_key: str,
    primary_persona_name: str,
    typeclass: str = "typeclasses.characters.Character",
    home: ObjectDB | None = None,
    **sheet_kwargs: Any,
) -> tuple[ObjectDB, CharacterSheet, Persona]:
    """Atomically create a Character + CharacterSheet + PRIMARY Persona.

    This is the blessed way to create a playable character. The three
    objects are created in a single database transaction so partial
    failures do not leave the system in an inconsistent state.

    Args:
        character_key: The in-game name/key for the Character object.
        primary_persona_name: The name for the PRIMARY persona.
        typeclass: Optional typeclass path (default: standard Character).
        home: Optional ObjectDB to set as the character's home. In test
            environments (TEST_ENVIRONMENT=True in settings), Evennia
            gracefully handles a missing Limbo/DEFAULT_HOME, so omitting
            this is safe in tests. Production callers should pass an
            explicit home.
        **sheet_kwargs: Additional CharacterSheet fields (age, gender, etc.).

    Returns:
        tuple[ObjectDB, CharacterSheet, Persona]

    Raises:
        Anything the underlying create_object / save calls raise. The
        transaction rolls back on any failure.
    """
    create_kwargs: dict[str, Any] = {"typeclass": typeclass, "key": character_key}
    if home is not None:
        create_kwargs["home"] = home
    else:
        # No default home provided — skip the Evennia DEFAULT_HOME lookup
        # (which is Limbo #2 by default). Fresh test DBs and in-progress
        # production grids may not have Limbo yet. Callers that need a
        # home must pass it explicitly; others set character.home after
        # creation (e.g., character_creation sets it from the starting room).
        create_kwargs["nohome"] = True
    character = create_object(**create_kwargs)
    # #1270 — narrative bio + lineage now live on Profile. Route those kwargs (concept,
    # quote, family, heritage, …) to the sheet's true_profile, which the PRIMARY persona presents.
    profile_kwargs = {k: sheet_kwargs.pop(k) for k in _PROFILE_FIELDS if k in sheet_kwargs}
    profile = Profile.objects.create(**profile_kwargs)
    sheet = CharacterSheet.objects.create(character=character, true_profile=profile, **sheet_kwargs)
    primary_persona = Persona.objects.create(
        character_sheet=sheet,
        name=primary_persona_name,
        persona_type=PersonaType.PRIMARY,
        profile=profile,
    )
    return character, sheet, primary_persona


def update_profile_text(
    profile: Profile,
    field: str,
    text: str,
    *,
    edited_by: Any | None = None,
    previous_text: str | None = None,
) -> ProfileTextVersion:
    """Write a versioned Profile prose field — the ONLY sanctioned write path (#2631).

    Snapshots on every write so history is never lost. If this is the first
    versioned write and the field already holds CG text, that original is
    captured first, so the earliest version row is always the CG-approved text.
    Each row is stamped with the IC datetime and active Era (season) when
    available.

    Args:
        profile: The Profile to update (a sheet's true_profile, or a guise's).
        field: A ``ProfileTextField`` value (matches the Profile attribute name).
        text: The full replacement text.
        edited_by: The staff account for admin-path edits; None for
            request-driven writes.
        previous_text: Override for the pre-write field value when the caller
            has already mutated the instance (the admin path — the identity
            map means ``getattr`` sees the new value there). None reads the
            instance.

    Returns:
        The created ProfileTextVersion for the new text.
    """
    from world.game_clock.models import GameClock  # noqa: PLC0415
    from world.stories.models import Era  # noqa: PLC0415

    if field not in ProfileTextField.values:
        msg = f"{field!r} is not a versioned profile text field."
        raise ValueError(msg)

    clock = GameClock.get_active()
    ic_date = clock.get_ic_now() if clock else None
    era = Era.objects.get_active()

    aura: CharacterAura | None = None
    # The physical description (#3988) is the one versioned field that lives on the
    # sheet owning the profile, not on the profile: the version rows still hang off
    # the profile, so one timeline covers every prose field of the character.
    if field == ProfileTextField.DESCRIPTION:
        holder = profile.owning_sheet_or_none
        if holder is None:
            msg = "A description belongs to a sheet's true profile; this profile has no sheet."
            raise ValueError(msg)
        attribute = "additional_desc"
    elif field == ProfileTextField.GLIMPSE:
        holder = aura = _glimpse_holder(profile)
        attribute = "glimpse_story"
    else:
        holder = profile
        attribute = field

    with transaction.atomic():
        current = previous_text if previous_text is not None else getattr(holder, attribute)
        has_versions = ProfileTextVersion.objects.filter(profile=profile, field=field).exists()
        if not has_versions and current:
            original = ProfileTextVersion.objects.create(
                profile=profile,
                field=field,
                text=current,
                ic_date=ic_date,
                era=era,
            )
            _date_original_to_creation(original, profile)
        setattr(holder, attribute, text)
        holder.save(update_fields=[attribute])
        if aura is not None:
            # The Glimpse's state is a cache of its prose and tags; every write path
            # (staff edit, restore, the aura services) has to move it (#4224).
            from world.magic.services.glimpse import refresh_glimpse_state  # noqa: PLC0415

            refresh_glimpse_state(aura)
        return ProfileTextVersion.objects.create(
            profile=profile,
            field=field,
            text=text,
            ic_date=ic_date,
            era=era,
            edited_by=edited_by,
        )


def _date_original_to_creation(original: ProfileTextVersion, profile: Profile) -> None:
    """Stamp a captured original with the character's creation time (#3988).

    The original is captured lazily, on the first versioned write, but its text was
    written before that, possibly by an earlier player. Stamped with the write time,
    it would fall inside a later tenant's tenure and show them the previous player's
    prose; stamped with the character's creation, the tenure-scoped history keeps it
    from anyone but the first player and staff. A cover profile keeps the write time.
    """
    sheet = profile.owning_sheet_or_none
    created = sheet.character.db_date_created if sheet is not None else None
    if created is None:
        return
    ProfileTextVersion.objects.filter(pk=original.pk).update_with_reason(
        reason="a captured original predates its capture; date it to the character",
        created_at=created,
    )
    original.created_at = created


def _glimpse_holder(profile: Profile) -> CharacterAura:
    """The aura a true profile's Glimpse lives on (#4224); a magicless sheet has none."""
    from world.magic.models import CharacterAura  # noqa: PLC0415

    sheet = profile.owning_sheet_or_none
    aura = CharacterAura.objects.filter(character=sheet).first() if sheet is not None else None
    if aura is None:
        msg = "This character has no aura to hold a Glimpse."
        raise StaffEditError(msg)
    return aura


def set_physical_description(
    sheet: CharacterSheet, text: str, *, edited_by: Any | None = None
) -> ProfileTextVersion:
    """THE seam for setting a character's free-text physical description (#2632).

    ``CharacterSheet.additional_desc`` is the field the web sheet's
    appearance section and telnet ``sheet`` actually render; CG writes it
    inline at finalize. New writers (the Great Archive recorded-profile flow,
    staff edit mode) go through here — never assign the attribute directly.
    Since #3988 the write is versioned like every other prose field: the first
    one captures what was there, so a rewrite never loses the earlier text.
    """
    return update_profile_text(
        ensure_true_profile(sheet), ProfileTextField.DESCRIPTION, text, edited_by=edited_by
    )


def ensure_true_profile(sheet: CharacterSheet) -> Profile:
    """The sheet's true profile, created empty if an older character has none (#3988).

    ``create_character_with_sheet`` has always made one, but characters that
    predate it can carry a null ``true_profile``; staff edit mode writes to the
    profile, so it has to exist before the first write.
    """
    if sheet.true_profile_id is None:
        sheet.true_profile = Profile.objects.create()
        sheet.save(update_fields=["true_profile"])
    return sheet.true_profile


def restore_profile_text_version(
    version: ProfileTextVersion, *, edited_by: Any
) -> ProfileTextVersion:
    """Write a past version's text back as the current text (#3988).

    A restore is one more version, never a deletion: the timeline keeps the
    text that was replaced, and a second restore can bring it back again.
    """
    return update_profile_text(version.profile, version.field, version.text, edited_by=edited_by)


def can_staff_edit_sheet(user: AbstractBaseUser | AnonymousUser, sheet: CharacterSheet) -> bool:
    """Whether this account may edit this sheet in place (#3988).

    The one predicate every staff-edit endpoint checks. Staff only in this piece;
    a later piece widens it to GMs editing the NPC sheets they own (``sheet`` is
    taken now so that widening changes nothing but this body).
    """
    del sheet
    return bool(user.is_authenticated and user.is_staff)


class StaffEditError(ValueError):
    """A staff edit the sheet refuses, with a message safe to show."""

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


@transaction.atomic
def rename_character(sheet: CharacterSheet, name: str) -> None:
    """Rename a character: its key and its primary persona's name together (#3988).

    No service renamed a character before this; the key, the PRIMARY persona's
    name and the particled-name telnet aliases (#3261) are three copies of one
    fact, so they move in one transaction, the way CG's finalize sets them.
    """
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    from world.societies.houses.services import sync_name_aliases  # noqa: PLC0415

    name = name.strip()
    if not name:
        msg = "A character needs a name."
        raise StaffEditError(msg)
    character = sheet.character
    character.key = name
    primary = sheet.primary_persona
    primary.name = name
    primary.save(update_fields=["name"])
    try:
        person = sheet.kinsperson
    except ObjectDoesNotExist:
        return
    sync_name_aliases(person)


#: The scalar identity fields staff edit in place, all on the sheet (#3988).
STAFF_IDENTITY_SCALARS: tuple[str, ...] = (
    "ic_birth_year",
    "true_height_inches",
    "weight_pounds",
    "marital_status",
    "vocation",
    "social_rank",
)
#: The identity choices on the sheet, by field name.
STAFF_SHEET_CHOICES: tuple[str, ...] = ("build", "gender", "pronouns", "species")
#: The identity choices on the true profile (the lineage, #1270).
STAFF_PROFILE_CHOICES: tuple[str, ...] = ("heritage", "origin_realm", "family", "tarot_card")
#: The three staff-edit keys with a write of their own.
STAFF_NAME_FIELD = "name"
STAFF_PRONOUNS_FIELD = "pronouns"
STAFF_TAROT_REVERSED_FIELD = "tarot_reversed"


def _apply_staff_change(  # noqa: PLR0913 - one field's write and the two save lists
    sheet: CharacterSheet,
    profile: Profile,
    key: str,
    value: Any,
    edited_by: Any,
    sheet_fields: list[str],
    profile_fields: list[str],
) -> None:
    """One field of a staff edit: versioned prose, the rename, a sheet or profile column."""
    if key in ProfileTextField.values:
        update_profile_text(profile, key, value, edited_by=edited_by)
    elif key == STAFF_NAME_FIELD:
        rename_character(sheet, value)
    elif key in STAFF_IDENTITY_SCALARS or key in STAFF_SHEET_CHOICES:
        setattr(sheet, key, value)
        sheet_fields.append(key)
        if key == STAFF_PRONOUNS_FIELD and value is not None:
            sheet.pronoun_subject = value.subject
            sheet.pronoun_object = value.object
            sheet.pronoun_possessive = value.possessive
            sheet_fields.extend(["pronoun_subject", "pronoun_object", "pronoun_possessive"])
    elif key in STAFF_PROFILE_CHOICES or key == STAFF_TAROT_REVERSED_FIELD:
        setattr(profile, key, value)
        profile_fields.append(key)
    else:
        msg = f"{key!r} is not a field staff edit in place."
        raise StaffEditError(msg)


def _grant_species_consequences(sheet: CharacterSheet) -> None:
    """A species' gifts, languages and codex; a refusal is a staff-facing message (#4221)."""
    from world.character_creation.sheet_writers import species_consequences  # noqa: PLC0415
    from world.distinctions.exceptions import DistinctionExclusionError  # noqa: PLC0415
    from world.magic.exceptions import MagicError  # noqa: PLC0415

    try:
        species_consequences(sheet)
    except (MagicError, DistinctionExclusionError) as exc:
        raise StaffEditError(str(exc.user_message)) from exc


def staff_edit_sheet(sheet: CharacterSheet, changes: dict[str, Any], *, edited_by: Any) -> None:
    """Apply a staff edit atomically; a refused edit leaves no phantom values in the cache.

    The sheet and profile are identity-mapped (ADR-0008): a rollback restores their rows
    but not the cached instances, which would show, and could later save, the refused
    values. On any failure both are evicted from the cache so the next read is the row.
    """
    profile = sheet.true_profile
    applied = False
    try:
        with transaction.atomic():
            _staff_edit_sheet(sheet, changes, edited_by=edited_by)
        applied = True
    finally:
        if not applied:
            sheet.flush_from_cache(force=True)
            if profile is not None:
                profile.flush_from_cache(force=True)


def _staff_edit_sheet(sheet: CharacterSheet, changes: dict[str, Any], *, edited_by: Any) -> None:
    """Apply a staff edit to a sheet's prose and identity fields (#3988).

    ``changes`` is the validated subset the staff-edit serializer resolved: prose
    fields by their ``ProfileTextField`` value (versioned through
    ``update_profile_text``), ``name`` (through ``rename_character``), the scalar
    identity fields, and the choice fields as model instances or None. Choosing a
    pronoun set copies its three forms onto the sheet, since the sheet's own
    pronoun strings are what every reader prints.
    """
    from world.character_creation.sheet_writers import (  # noqa: PLC0415
        set_pronouns_from_gender,
    )

    profile = ensure_true_profile(sheet)
    sheet_fields: list[str] = []
    profile_fields: list[str] = []
    # A new gender sets the pronoun forms CG would set for it, unless the same edit
    # chooses a pronoun set (#4221).
    if changes.get("gender") is not None and STAFF_PRONOUNS_FIELD not in changes:
        set_pronouns_from_gender(sheet, changes["gender"])
        sheet_fields.extend(["pronoun_subject", "pronoun_object", "pronoun_possessive"])
    for key, value in changes.items():
        _apply_staff_change(sheet, profile, key, value, edited_by, sheet_fields, profile_fields)
    if sheet_fields:
        sheet.save(update_fields=list(dict.fromkeys(sheet_fields)))
    if profile_fields:
        profile.save(update_fields=profile_fields)
    # A species carries its gifts, languages and codex, as it does in CG (#4221).
    if changes.get("species") is not None:
        _grant_species_consequences(sheet)

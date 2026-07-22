"""Service functions for character sheets."""

from __future__ import annotations

from typing import Any

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


# --- OC cap enforcement (#671) ---------------------------------------------

# Default cap on simultaneously-active OCs per non-staff account. Tuneable via
# staff override (TODO: per-account cap field once trust/karma system lands).
DEFAULT_OC_CAP = 3


class OCCapError(Exception):
    """Raised when an OC creation would exceed the account's active-OC cap."""

    def __init__(self, message: str, *, user_message: str | None = None) -> None:
        super().__init__(message)
        self.user_message = user_message or message


def count_active_ocs(account: AbstractBaseUser) -> int:
    """Count OCs an account currently holds against its cap.

    An OC counts when it is:
      * ``is_oc=True`` AND ``created_by=account``,
      * on a Roster with ``allow_applications=False`` (still privately held —
        characters converted to community roster characters no longer count),
      * ``lifecycle_state=ALIVE``,
      * NOT ``activity_state=FROZEN`` (frozen frees the slot for swap).

    Two queries: one COUNT(*) on CharacterSheet with the filter, plus the
    underlying account lookup the caller already did. Cheap.
    """
    from world.character_sheets.types import ActivityState, LifecycleState  # noqa: PLC0415

    return (
        CharacterSheet.objects.filter(
            is_oc=True,
            created_by=account,
            roster_entry__roster__allow_applications=False,
            lifecycle_state=LifecycleState.ALIVE,
        )
        .exclude(activity_state=ActivityState.FROZEN)
        .count()
    )


def enforce_oc_cap(account: AbstractBaseUser, *, cap: int = DEFAULT_OC_CAP) -> None:
    """Raise OCCapError if creating another OC would exceed ``cap``.

    Staff accounts bypass the cap entirely. Call this at the head of any
    OC creation flow — the cap is not enforced at the model level so admin
    seeds and migrations can run freely.
    """
    if account.is_staff:
        return
    current = count_active_ocs(account)
    if current >= cap:
        msg = f"Account {account.pk} already has {current} active OCs (cap {cap})."
        raise OCCapError(
            msg,
            user_message=(
                f"You already have {current} active OCs (cap {cap})."
                " Freeze or retire one before creating another."
            ),
        )


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

    with transaction.atomic():
        current = previous_text if previous_text is not None else getattr(profile, field)
        has_versions = ProfileTextVersion.objects.filter(profile=profile, field=field).exists()
        if not has_versions and current:
            ProfileTextVersion.objects.create(
                profile=profile,
                field=field,
                text=current,
                ic_date=ic_date,
                era=era,
            )
        setattr(profile, field, text)
        profile.save(update_fields=[field])
        return ProfileTextVersion.objects.create(
            profile=profile,
            field=field,
            text=text,
            ic_date=ic_date,
            era=era,
            edited_by=edited_by,
        )


def set_physical_description(sheet: CharacterSheet, text: str) -> None:
    """THE seam for setting a character's free-text physical description (#2632).

    ``CharacterSheet.additional_desc`` is the field the web sheet's
    appearance section and telnet ``sheet`` actually render; CG writes it
    inline at finalize, and until now no post-CG caller existed. New writers
    (the Great Archive recorded-profile flow, future desc surfaces) go
    through here — never assign the attribute directly.
    """
    sheet.additional_desc = text
    sheet.save(update_fields=["additional_desc"])

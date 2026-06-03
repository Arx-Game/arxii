"""Service functions for character sheets."""

from __future__ import annotations

from typing import Any

from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
from django.db import transaction
from evennia.objects.models import ObjectDB
from evennia.utils.create import create_object

from world.character_sheets.models import CharacterSheet
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
    sheet = CharacterSheet.objects.create(character=character, **sheet_kwargs)
    primary_persona = Persona.objects.create(
        character_sheet=sheet,
        name=primary_persona_name,
        persona_type=PersonaType.PRIMARY,
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

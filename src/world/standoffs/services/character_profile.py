"""A player character's standoff profile and consent (#4441, slice 5 of #4121).

A player gives their own character drives and a cause, each picked from the catalogs
creature templates use (a ``Property`` some ``CreatureDrive`` already carries, a
``CauseKind``), and opts in to being read and pressed by other player characters. Only an
opted-in player character can be read or pressed in a standoff; the pressing player still
rolls, and the target's profile only sets the difficulty, as a creature's drives do.

The profile is live-read: while a character stands in a standoff it cannot change (opting
out included), so the standoff never sees a profile move under it.

"Player character" here is ``is_player_character`` minus the NPC shelf: a story NPC a GM
holds is a named NPC (slice 3) and needs no consent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Q

from world.combat.constants import CauseKind
from world.scenes.constants import RoundStatus
from world.standoffs.constants import (
    LIVE_GROUP_STATES,
    PROFILE_DRIVE_NOT_HELD_MESSAGE,
    PROFILE_LOCKED_MESSAGE,
    PROFILE_NO_SUCH_CAUSE_MESSAGE,
    PROFILE_NO_SUCH_CHANGE_MESSAGE,
    PROFILE_NO_SUCH_DRIVE_MESSAGE,
    PROFILE_NOT_YOURS_MESSAGE,
    REFUSAL_NOT_OPTED_IN,
    REFUSAL_SELF_TARGET,
    DriveStrength,
    ProfileChange,
)
from world.standoffs.models import (
    CharacterDrive,
    CharacterStandoffProfile,
    CreatureDrive,
    StandoffGroup,
)

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from world.character_sheets.models import CharacterSheet
    from world.mechanics.models import Property
    from world.scenes.models import Persona


class StandoffProfileError(ValueError):
    """A profile change was refused; ``user_message`` is safe to show the player."""

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


@dataclass(frozen=True)
class ProfileDriveView:
    """One of the character's own drives."""

    property_id: int
    name: str
    strength: int
    strength_label: str


@dataclass(frozen=True)
class ProfileChoice:
    """One catalog entry a player may pick: a cause or a drive property."""

    value: str
    label: str


@dataclass(frozen=True)
class ProfileView:
    """What the owner sees of their own profile, with the catalogs they pick from."""

    opted_in: bool
    cause: str
    cause_label: str
    drives: list[ProfileDriveView]
    locked: bool
    locked_reason: str
    causes: list[ProfileChoice]
    properties: list[ProfileChoice]
    strengths: list[ProfileChoice]


def is_standoff_player_character(sheet: CharacterSheet | None) -> bool:
    """Whether ``sheet`` is a player's character for the standoff consent gate.

    A character held by an account, or puppeted, that is not on the NPC shelf. A story NPC
    a GM holds has a tenure but sits on the NPC shelf, so it stays a named NPC.
    """
    from world.roster.models.choices import RosterType  # noqa: PLC0415
    from world.roster.services.activity import (  # noqa: PLC0415
        current_roster_entry,
        is_player_character,
    )

    if sheet is None:
        return False
    entry = current_roster_entry(sheet)
    if entry is not None and entry.roster.roster_type == RosterType.NPC:
        return False
    return is_player_character(sheet)


def profile_of(sheet: CharacterSheet) -> CharacterStandoffProfile | None:
    """The sheet's profile row, or None when the player never made one."""
    return CharacterStandoffProfile.objects.filter(sheet=sheet).first()


def is_opted_in(sheet: CharacterSheet) -> bool:
    profile = profile_of(sheet)
    return profile is not None and profile.opted_in


def may_stand_as_opponent(persona: Persona) -> bool:
    """Whether a GM may stand this persona's character as an opponent on the player's say.

    True for an opted-in player character; the story-cast rule covers every other persona.
    """
    sheet = persona.character_sheet
    return is_standoff_player_character(sheet) and is_opted_in(sheet)


def opted_in_personas() -> QuerySet[Persona]:
    """The primary personas of every opted-in character that is still a player character.

    The same test as ``is_standoff_player_character`` (held by an account or puppeted, and not
    on the NPC shelf) as one query, so a picker never loops over the game's opted-in players.
    """
    from world.roster.models.choices import RosterType  # noqa: PLC0415
    from world.scenes.constants import PersonaType  # noqa: PLC0415
    from world.scenes.models import Persona  # noqa: PLC0415

    return (
        Persona.objects.filter(
            persona_type=PersonaType.PRIMARY,
            character_sheet__standoff_profile__opted_in=True,
        )
        .exclude(character_sheet__roster_entry__roster__roster_type=RosterType.NPC)
        .filter(
            Q(
                character_sheet__roster_entry__tenures__isnull=False,
                character_sheet__roster_entry__tenures__end_date__isnull=True,
            )
            | Q(character_sheet__character__db_account__isnull=False)
        )
        .distinct()
    )


def target_refusal(persona: Persona | None, actor_sheet: CharacterSheet) -> str | None:
    """Why the actor may not read or press a group standing as ``persona``, if they may not.

    A named NPC (or no persona) is never refused here. A player character is refused when it
    is the actor itself or has not opted in.
    """
    if persona is None:
        return None
    sheet = persona.character_sheet
    if not is_standoff_player_character(sheet):
        return None
    if sheet.pk == actor_sheet.pk:
        return REFUSAL_SELF_TARGET
    if not is_opted_in(sheet):
        return REFUSAL_NOT_OPTED_IN.format(name=persona.name)
    return None


def is_in_live_standoff(sheet: CharacterSheet) -> bool:
    """Whether the character stands as a group in a standoff that has not ended."""
    return (
        StandoffGroup.objects.filter(
            persona__character_sheet=sheet,
            state__in=LIVE_GROUP_STATES,
            encounter__round_number=0,
        )
        .exclude(encounter__status=RoundStatus.COMPLETED)
        .exists()
    )


def drive_catalog() -> list[Property]:
    """The properties a player may pick as a drive: those a creature template already has."""
    from world.mechanics.models import Property  # noqa: PLC0415

    return list(
        Property.objects.filter(pk__in=CreatureDrive.objects.values("property_id")).order_by("name")
    )


def _require_unlocked(sheet: CharacterSheet) -> None:
    if is_in_live_standoff(sheet):
        raise StandoffProfileError(PROFILE_LOCKED_MESSAGE)


def _require_player_character(sheet: CharacterSheet) -> None:
    if not is_standoff_player_character(sheet):
        raise StandoffProfileError(PROFILE_NOT_YOURS_MESSAGE)


def _profile_for_write(sheet: CharacterSheet) -> CharacterStandoffProfile:
    profile, _created = CharacterStandoffProfile.objects.get_or_create(sheet=sheet)
    return profile


@transaction.atomic
def apply_profile_change(
    sheet: CharacterSheet,
    change: str,
    *,
    cause: str | None = None,
    property_id: int | None = None,
    strength: int | None = None,
) -> CharacterStandoffProfile:
    """Apply one edit to the sheet's own profile, or raise ``StandoffProfileError``."""
    _require_player_character(sheet)
    _require_unlocked(sheet)
    if change not in ProfileChange.values:
        raise StandoffProfileError(PROFILE_NO_SUCH_CHANGE_MESSAGE)
    profile = _profile_for_write(sheet)
    if change in (ProfileChange.OPT_IN, ProfileChange.OPT_OUT):
        profile.opted_in = change == ProfileChange.OPT_IN
        profile.save(update_fields=["opted_in"])
    elif change == ProfileChange.CAUSE:
        if cause not in CauseKind.values:
            raise StandoffProfileError(PROFILE_NO_SUCH_CAUSE_MESSAGE)
        profile.cause = cause
        profile.save(update_fields=["cause"])
    elif change == ProfileChange.DRIVE:
        _set_drive(profile, property_id, strength)
    else:
        _drop_drive(profile, property_id)
    return profile


def _set_drive(
    profile: CharacterStandoffProfile, property_id: int | None, strength: int | None
) -> None:
    chosen = DriveStrength.MINOR if strength is None else strength
    if chosen not in DriveStrength.values:
        raise StandoffProfileError(PROFILE_NO_SUCH_DRIVE_MESSAGE)
    if not CreatureDrive.objects.filter(property_id=property_id).exists():
        raise StandoffProfileError(PROFILE_NO_SUCH_DRIVE_MESSAGE)
    CharacterDrive.objects.update_or_create(
        profile=profile, property_id=property_id, defaults={"strength": chosen}
    )


def _drop_drive(profile: CharacterStandoffProfile, property_id: int | None) -> None:
    dropped, _by_model = CharacterDrive.objects.filter(
        profile=profile, property_id=property_id
    ).delete()
    if not dropped:
        raise StandoffProfileError(PROFILE_DRIVE_NOT_HELD_MESSAGE)


def profile_drives(sheet: CharacterSheet) -> list[CharacterDrive]:
    """The sheet's drives, strongest first; none when it has not opted in."""
    profile = profile_of(sheet)
    if profile is None or not profile.opted_in:
        return []
    return list(profile.drives.select_related("property"))


def profile_cause(sheet: CharacterSheet) -> str:
    """The sheet's chosen cause; none when it has not opted in."""
    profile = profile_of(sheet)
    if profile is None or not profile.opted_in:
        return CauseKind.NONE
    return profile.cause


def build_profile_view(sheet: CharacterSheet) -> ProfileView:
    """The owner's profile with the catalogs they pick from."""
    profile = profile_of(sheet)
    drives = (
        []
        if profile is None
        else [
            ProfileDriveView(
                property_id=row.property_id,
                name=row.property.name,
                strength=row.strength,
                strength_label=row.get_strength_display(),
            )
            for row in profile.drives.select_related("property")
        ]
    )
    cause = CauseKind.NONE if profile is None else profile.cause
    locked = is_in_live_standoff(sheet)
    return ProfileView(
        opted_in=profile is not None and profile.opted_in,
        cause=cause,
        cause_label=CauseKind(cause).label,
        drives=drives,
        locked=locked,
        locked_reason=PROFILE_LOCKED_MESSAGE if locked else "",
        causes=[ProfileChoice(value=c.value, label=c.label) for c in CauseKind],
        properties=[ProfileChoice(value=str(p.pk), label=p.name) for p in drive_catalog()],
        strengths=[ProfileChoice(value=str(s.value), label=s.label) for s in DriveStrength],
    )

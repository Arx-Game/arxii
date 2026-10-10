"""Group fit by staff fiat: personas, titles, ties, covenant roles, mentor bonds (#4229).

Staff placing a new roster character into an existing group give it the play state
the group already shares (#3988 piece E). Each writer here takes the sheet and the
target rows, calls the owning app's own service, and skips what a player pays or
proves on the way: XP, weekly caps, an induction or mentorship session, an invite.
None sends a cross-character announcement. A refusal is a ``SheetWriteError``
carrying a message safe to show staff.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import ProtectedError

from world.character_creation.sheet_writers import SheetWriteError
from world.character_sheets.types import StaffTieDirection

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.achievements.models import PersonaTitle, RewardDefinition
    from world.character_sheets.models import CharacterSheet
    from world.covenants.models import (
        CharacterCovenantRole,
        Covenant,
        CovenantRank,
        CovenantRole,
        MentorBond,
    )
    from world.relationships.models import (
        CharacterRelationship,
        RelationshipLabel,
        RelationshipType,
    )
    from world.scenes.models import Persona
    from world.societies.houses.models import Title
    from world.societies.models import LegendEntry


# --- Personas ----------------------------------------------------------------


def create_established_persona(sheet: CharacterSheet, name: str) -> Persona:
    """A new established identity for the character; staff are not held to the cap."""
    from world.scenes.constants import PersonaType  # noqa: PLC0415
    from world.scenes.services import PersonaCreationError, create_persona  # noqa: PLC0415

    try:
        return create_persona(
            sheet, name=name, persona_type=PersonaType.ESTABLISHED, bypass_cap=True
        )
    except PersonaCreationError as exc:
        raise SheetWriteError(exc.user_message) from exc


def _editable_persona(persona: Persona) -> None:
    """Refuse the faces staff edit elsewhere or never: the character itself, a system face."""
    from world.scenes.constants import PersonaType  # noqa: PLC0415

    if persona.persona_type == PersonaType.PRIMARY:
        msg = "That is the character's own face; rename the character instead."
        raise SheetWriteError(msg)
    if persona.is_system:
        msg = "System identities are not edited here."
        raise SheetWriteError(msg)


def rename_persona(persona: Persona, name: str) -> Persona:
    """Rename an established identity or a guise."""
    _editable_persona(persona)
    cleaned = name.strip()
    if not cleaned:
        msg = "A name is required."
        raise SheetWriteError(msg)
    persona.name = cleaned
    persona.save(update_fields=["name"])
    return persona


def set_guise_prose(persona: Persona, *, edited_by: AccountDB, prose: dict[str, str]) -> None:
    """Write a guise's cover bio through the versioned path (``set_persona_profile``)."""
    from world.scenes.services import GuiseProfileError, set_persona_profile  # noqa: PLC0415

    _editable_persona(persona)
    try:
        set_persona_profile(
            persona,
            concept=prose.get("concept"),
            quote=prose.get("quote"),
            never_do=prose.get("never_do"),
            protect=prose.get("protect"),
            fear=prose.get("fear"),
            background=prose.get("background"),
            edited_by=edited_by,
        )
    except GuiseProfileError as exc:
        raise SheetWriteError(exc.user_message) from exc


def remove_persona(persona: Persona) -> None:
    """Delete an identity that has no history; one that has been played stays.

    A persona with poses, deeds or anything else protected behind it cannot be deleted,
    and staff are told so rather than having that history cascade away. If the
    character is wearing it, they go back to their own face first.
    """
    from world.scenes.services import set_active_persona  # noqa: PLC0415

    _editable_persona(persona)
    sheet = persona.character_sheet
    try:
        with transaction.atomic():
            if sheet.active_persona_id == persona.pk:
                set_active_persona(sheet, sheet.primary_persona)
            persona.delete()
    except ProtectedError as exc:
        # The rollback restored the sheet's row, not the identity-mapped instance.
        sheet.flush_from_cache(force=True)
        msg = "That identity has history behind it and can't be removed."
        raise SheetWriteError(msg) from exc


# --- Titles ------------------------------------------------------------------


def grant_persona_title(
    persona: Persona,
    *,
    reward: RewardDefinition | None = None,
    legend_entry: LegendEntry | None = None,
) -> PersonaTitle:
    """Give a face a title: an authored title reward, or one of its own deeds.

    Writes the ``PersonaTitle`` directly rather than through ``_grant_title``, so an
    achievement's bonus modifiers are never applied a second time. Granting a title the
    face already holds keeps the one it has.
    """
    from world.achievements.constants import RewardType  # noqa: PLC0415
    from world.achievements.models import PersonaTitle  # noqa: PLC0415

    if (reward is None) == (legend_entry is None):
        msg = "Choose a title reward or a deed."
        raise SheetWriteError(msg)
    if reward is not None:
        if reward.reward_type != RewardType.TITLE:
            msg = "That reward is not a title."
            raise SheetWriteError(msg)
        title, _ = PersonaTitle.objects.get_or_create(persona=persona, reward=reward)
        return title
    if legend_entry.persona_id != persona.pk:
        msg = "A deed titles only the face that did it."
        raise SheetWriteError(msg)
    title, _ = PersonaTitle.objects.get_or_create(persona=persona, legend_entry=legend_entry)
    return title


def revoke_persona_title(title: PersonaTitle) -> None:
    """Take a title away; the reward or deed behind it stays."""
    title.delete()


def seat_noble_title(sheet: CharacterSheet, title: Title) -> Title:
    """Seat the character on a noble title by staff fiat (``pass_title``)."""
    from world.roster.models import Kinsperson  # noqa: PLC0415
    from world.societies.houses.services import HousesServiceError, pass_title  # noqa: PLC0415

    holder = Kinsperson.objects.filter(sheet=sheet).first()
    if holder is None:
        msg = "A noble title is held by someone in the family tree; place the character first."
        raise SheetWriteError(msg)
    try:
        return pass_title(title, to_holder=holder)
    except HousesServiceError as exc:
        raise SheetWriteError(exc.user_message) from exc


# --- Ties (the #3957 model) --------------------------------------------------


def tie_side(sheet: CharacterSheet, other: CharacterSheet, direction: str) -> CharacterRelationship:
    """The side staff are editing: this character's toward ``other``, or the reverse."""
    from world.relationships.services import get_or_create_side  # noqa: PLC0415

    if direction == StaffTieDirection.TOWARD:
        source, target = sheet, other
    else:
        source, target = other, sheet
    try:
        return get_or_create_side(source=source, target=target)
    except ValidationError as exc:
        msg = "A character has no tie to themselves."
        raise SheetWriteError(msg) from exc


def declare_tie_label(
    side: CharacterRelationship, relationship_type: RelationshipType, awareness: str
) -> RelationshipLabel:
    """Declare a label on a side, live by staff ruling (#3988).

    On a played character it is declared under that player's current tenure, so it
    counts at once, mutual-hostile consent included; staff have asked that player. On
    a character nobody plays it waits with no tenure and binds at pickup.
    """
    from world.relationships.exceptions import TieError  # noqa: PLC0415
    from world.relationships.services import declare_label  # noqa: PLC0415
    from world.roster.models import RosterTenure  # noqa: PLC0415

    tenure = RosterTenure.objects.filter(
        roster_entry__character_sheet=side.source, end_date__isnull=True
    ).first()
    try:
        return declare_label(
            side=side,
            type=relationship_type,
            awareness=awareness,
            tenure=tenure,
            staff_seeded=True,
        )
    except TieError as exc:
        raise SheetWriteError(exc.user_message) from exc


def change_tie_label(
    label: RelationshipLabel,
    *,
    new_type: RelationshipType | None = None,
    awareness: str = "",
    end: bool = False,
) -> RelationshipLabel:
    """Shift, reveal or end one label, through the same services a player's change runs."""
    from world.relationships.exceptions import TieError  # noqa: PLC0415
    from world.relationships.services import (  # noqa: PLC0415
        advance_awareness,
        end_label,
        shift_label,
    )

    try:
        if end:
            return end_label(label=label)
        if new_type is not None:
            label = shift_label(label=label, new_type=new_type)
        if awareness and awareness != label.awareness:
            label = advance_awareness(label=label, to=awareness)
    except TieError as exc:
        raise SheetWriteError(exc.user_message) from exc
    return label


def set_tie_state(
    side: CharacterRelationship, *, summary: str | None = None, tier: int | None = None
) -> CharacterRelationship:
    """Set a side's summary and its claimed tier (no XP, no capstone entry)."""
    from world.relationships.exceptions import TieError  # noqa: PLC0415
    from world.relationships.services import set_summary, staff_set_tier  # noqa: PLC0415

    try:
        if summary is not None:
            set_summary(side=side, summary=summary)
        if tier is not None:
            staff_set_tier(side=side, tier_number=tier)
    except TieError as exc:
        raise SheetWriteError(exc.user_message) from exc
    return side


# --- Covenants ---------------------------------------------------------------


def _covenant_refusal(exc: Exception) -> SheetWriteError:
    """The safe message of a covenant service's refusal (typed, or a model validation)."""
    from world.covenants.exceptions import CovenantError  # noqa: PLC0415

    if isinstance(exc, CovenantError):
        return SheetWriteError(exc.user_message)
    messages = exc.messages if isinstance(exc, ValidationError) else []
    return SheetWriteError(str(messages[0]) if messages else "The covenant refused that.")


def assign_role(
    sheet: CharacterSheet,
    covenant: Covenant,
    covenant_role: CovenantRole,
    *,
    rank: CovenantRank | None = None,
) -> CharacterCovenantRole:
    """Make the character a member of a covenant in a role, by staff fiat.

    ``assign_covenant_role`` skips the induction session, the level band and the
    sworn external act; the vow is sworn under the character's own face.
    """
    from world.covenants.exceptions import CovenantError  # noqa: PLC0415
    from world.covenants.models import CharacterCovenantRole  # noqa: PLC0415
    from world.covenants.services import assign_covenant_role  # noqa: PLC0415

    if covenant.dissolved_at is not None:
        msg = "That covenant is dissolved."
        raise SheetWriteError(msg)
    if covenant_role.covenant_type != covenant.covenant_type:
        msg = "That role belongs to another kind of covenant."
        raise SheetWriteError(msg)
    if rank is not None and rank.covenant_id != covenant.pk:
        msg = "That rank belongs to another covenant."
        raise SheetWriteError(msg)
    if CharacterCovenantRole.objects.filter(
        character_sheet=sheet, covenant=covenant, left_at__isnull=True
    ).exists():
        msg = "The character is already a member of that covenant; change the role instead."
        raise SheetWriteError(msg)
    try:
        return assign_covenant_role(
            character_sheet=sheet,
            covenant=covenant,
            covenant_role=covenant_role,
            rank=rank,
            sworn_as=sheet.primary_persona,
        )
    except CovenantError as exc:
        raise SheetWriteError(exc.user_message) from exc


def change_membership(  # noqa: PLR0913 - keyword-only; one argument per change
    membership: CharacterCovenantRole,
    *,
    covenant_role: CovenantRole | None = None,
    rank: CovenantRank | None = None,
    engaged: bool | None = None,
    as_secondary: bool = False,
    end: bool = False,
) -> CharacterCovenantRole:
    """Make one change to an active membership: its role, its rank, its engagement, or end.

    One change per call, so a refusal never leaves half of a request written. Engaging
    keeps ``set_engaged_membership``'s gift, technique and capability grants and its
    health recompute; the character hears what they gained, as a player who engaged
    would. Returns the active membership (a role change opens a new row).
    """
    from world.covenants.exceptions import CovenantError  # noqa: PLC0415
    from world.covenants.services import (  # noqa: PLC0415
        change_role,
        clear_engaged_membership,
        end_covenant_role,
        set_engaged_membership,
        set_member_rank,
    )

    changes = [covenant_role is not None, rank is not None, engaged is not None, end]
    if sum(changes) != 1:
        msg = "Make one change at a time."
        raise SheetWriteError(msg)
    if membership.left_at is not None:
        msg = "That membership has already ended."
        raise SheetWriteError(msg)
    if (
        covenant_role is not None
        and covenant_role.covenant_type != membership.covenant.covenant_type
    ):
        msg = "That role belongs to another kind of covenant."
        raise SheetWriteError(msg)
    written = False
    try:
        if end:
            end_covenant_role(assignment=membership)
        elif covenant_role is not None:
            membership = change_role(membership=membership, new_role=covenant_role)
        elif rank is not None:
            set_member_rank(membership=membership, rank=rank)
        elif engaged:
            set_engaged_membership(membership=membership, as_secondary=as_secondary)
        else:
            clear_engaged_membership(membership=membership)
        written = True
    except (CovenantError, ValidationError) as exc:
        raise _covenant_refusal(exc) from exc
    finally:
        if not written:
            # A refused engage stamps ``is_secondary`` before it validates; the
            # rollback restores the row, not the identity-mapped instance.
            membership.flush_from_cache(force=True)
    return membership


# --- Mentors -----------------------------------------------------------------


def bond_mentor(
    covenant: Covenant, *, mentor: CharacterSheet, sidekick: CharacterSheet
) -> tuple[MentorBond, str]:
    """Bond a mentor and a sidekick in a covenant; returns the bond and any band warning.

    The level band (exactly one party outside it) is a warning for staff, not a refusal;
    the cap on a mentor's sidekicks still holds.
    """
    from world.covenants.exceptions import MentorBondError  # noqa: PLC0415
    from world.covenants.mentorship import (  # noqa: PLC0415
        establish_mentor_bond,
        mentor_band_problem,
    )

    if mentor.pk == sidekick.pk:
        msg = "A character cannot mentor themselves."
        raise SheetWriteError(msg)
    warning = mentor_band_problem(covenant=covenant, mentor_sheet=mentor, sidekick_sheet=sidekick)
    try:
        bond = establish_mentor_bond(
            covenant=covenant, mentor_sheet=mentor, sidekick_sheet=sidekick, staff_override=True
        )
    except MentorBondError as exc:
        raise SheetWriteError(exc.user_message) from exc
    return bond, warning


def dissolve_mentor(bond: MentorBond) -> None:
    """End an active mentor bond."""
    from world.covenants.mentorship import dissolve_mentor_bond  # noqa: PLC0415

    if bond.dissolved_at is not None:
        msg = "That bond has already ended."
        raise SheetWriteError(msg)
    dissolve_mentor_bond(bond)

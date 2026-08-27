"""Shared helpers that prefetch data for the account payload serializer.

Used by `CurrentUserAPIView` and tests to construct the serializer context
in one place, ensuring queries happen at the view boundary and the
serializer walks attributes.
"""

from typing import TypedDict

from django.db.models import Prefetch
from evennia.accounts.models import AccountDB

from world.roster.models import (
    ApplicationStatus,
    RosterApplication,
    RosterEntry,
    RosterType,
)
from world.scenes.constants import PersonaType
from world.scenes.models import Persona


class AccountPayloadContext(TypedDict):
    """Context dict consumed by `AccountPlayerSerializer`."""

    active_entries: list[RosterEntry]
    pending_applications: list[RosterApplication]
    puppeted_character_ids: set[int]
    selected_entry: RosterEntry | None


def build_account_payload_context(account: AccountDB) -> AccountPayloadContext:
    """Prefetch the data the account payload serializer needs.

    Returns a context dict for `AccountPlayerSerializer`:
        - active_entries: ACTIVE-roster RosterEntries with prefetched
          personas (PRIMARY+ESTABLISHED) and select_related on roster,
          character_sheet.character, profile_picture.media.
        - pending_applications: pending RosterApplication rows with
          select_related on character__character. The serializer reads the
          character's id/key off the ObjectDB behind the CharacterSheet
          (#2608 retargeted this FK), so stopping at `character` would cost
          one ObjectDB query per pending application.
        - puppeted_character_ids: ObjectDB ids currently puppeted by
          this account in any session.
        - selected_entry: the account's durable character selection (#3412
          state 2.5 substrate — see `PlayerData.selected_entry`), with the
          same select_related the display fields need, or None if unset.

    Single round of queries; serializer methods walk attributes only.
    """
    active_entries = list(
        RosterEntry.objects.for_account(account)
        .filter(roster__roster_type=RosterType.ACTIVE)
        .distinct()
        .select_related(
            "roster",
            "character_sheet__character__db_location",
            "profile_picture__media",
        )
        .prefetch_related(
            Prefetch(
                "character_sheet__personas",
                queryset=Persona.objects.filter(
                    persona_type__in=[PersonaType.PRIMARY, PersonaType.ESTABLISHED]
                ).order_by("-persona_type", "created_at", "id"),
                to_attr="cached_payload_personas",
            )
        )
    )
    # PlayerData is created by ArxAccountAdapter on signup, but accounts
    # created via the ORM (tests, management commands, social auth edge
    # cases) may not have one. Guard the reverse OneToOne access so the
    # payload returns empty applications instead of 500ing.
    try:
        player_data = account.player_data
    except AccountDB.player_data.RelatedObjectDoesNotExist:
        player_data = None
    pending_applications = (
        list(
            RosterApplication.objects.filter(
                player_data=player_data,
                status=ApplicationStatus.PENDING,
            ).select_related("character__character")
        )
        if player_data
        else []
    )
    # get_puppeted_characters() requires Evennia's SESSION_HANDLER to be
    # active; in test environments (no server running) it may not exist.
    try:
        puppeted_character_ids = {char.id for char in account.get_puppeted_characters()}
    except (AttributeError, RuntimeError):
        puppeted_character_ids = set()
    selected_entry = None
    if player_data is not None and player_data.selected_entry_id is not None:
        selected_entry = (
            RosterEntry.objects.filter(pk=player_data.selected_entry_id)
            .select_related("character_sheet__character", "profile_picture__media")
            .first()
        )
    return {
        "active_entries": active_entries,
        "pending_applications": pending_applications,
        "puppeted_character_ids": puppeted_character_ids,
        "selected_entry": selected_entry,
    }

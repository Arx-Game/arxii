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

Follow-on (deliberately not built): the same mint gated on ``GMProfile`` for
player GMs' OOC characters; free-form sheet editing rides the Django admin.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB


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
    roster, _ = Roster.objects.get_or_create(name="NPC", defaults={"roster_type": RosterType.NPC})
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

"""Nominating a player for good RP (#3738).

The act: read a pose or a journal entry this week, and nominate the character
who wrote it. One account nominating one character in one week is one
nomination however many pieces it cites; ``nominate`` records a citation row
per piece and the settlement counts distinct people.

What can be nominated is exactly what the nominator could see and what was
written this week: an interaction passes ``Interaction.objects.visible_to``
for the account's own personas, a journal entry is public (or revealed) and
from the current game week. Your own characters are never nominable, and
neither is a character nobody is playing (there is no player to pay).
"""

from django.db import transaction
from django.db.models import QuerySet
from evennia.accounts.models import AccountDB

from world.character_sheets.models import CharacterSheet
from world.game_clock.models import GameWeek
from world.game_clock.week_services import get_current_game_week
from world.progression.constants import NominationTargetType
from world.progression.models import Nomination
from world.progression.types import ProgressionError
from world.roster.models import RosterEntry
from world.roster.selectors import get_account_for_character


def _persona_ids_for(account: AccountDB) -> list[int]:
    """Every persona id on a sheet the account currently plays.

    The same set as the Account typeclass's ``cached_persona_ids``; computed
    here so the service works on a bare ``AccountDB`` too.
    """
    from world.scenes.models import Persona

    sheet_ids = list(
        RosterEntry.objects.for_account(account).values_list("character_sheet_id", flat=True)
    )
    if not sheet_ids:
        return []
    return list(
        Persona.objects.filter(character_sheet_id__in=sheet_ids).values_list("pk", flat=True)
    )


def _visible_interaction_sheet(
    account: AccountDB, target_id: int, game_week: GameWeek
) -> CharacterSheet:
    """The sheet behind a pose the account can see and that was posed this week."""
    from world.scenes.models import Interaction

    interaction = Interaction.objects.filter(pk=target_id).select_related("persona").first()
    if interaction is None:
        raise ProgressionError(ProgressionError.NO_AUTHOR)
    if interaction.timestamp < game_week.started_at:
        raise ProgressionError(ProgressionError.NOT_THIS_WEEK)
    visible = (
        Interaction.objects.visible_to(
            account,
            persona_ids=_persona_ids_for(account),
            since=game_week.started_at.isoformat(),
        )
        .filter(pk=target_id)
        .exists()
    )
    if not visible:
        raise ProgressionError(ProgressionError.NOT_VISIBLE)
    return interaction.persona.character_sheet


def _visible_journal_sheet(target_id: int, game_week: GameWeek) -> CharacterSheet:
    """The sheet behind a public (or revealed) journal entry written this week."""
    from world.journals.models import JournalEntry

    entry = JournalEntry.objects.filter(pk=target_id).select_related("author").first()
    if entry is None:
        raise ProgressionError(ProgressionError.NO_AUTHOR)
    if entry.created_at < game_week.started_at:
        raise ProgressionError(ProgressionError.NOT_THIS_WEEK)
    if not (entry.is_public or entry.revealed_at is not None):
        raise ProgressionError(ProgressionError.NOT_VISIBLE)
    return entry.author


def resolve_nominee(
    account: AccountDB, target_type: str, target_id: int, game_week: GameWeek
) -> CharacterSheet:
    """The character a nomination of ``target_type``:``target_id`` would pay.

    Raises ``ProgressionError`` when the piece is missing, not from this week,
    or not something the account could see.
    """
    if target_type == NominationTargetType.INTERACTION:
        return _visible_interaction_sheet(account, target_id, game_week)
    if target_type == NominationTargetType.JOURNAL:
        return _visible_journal_sheet(target_id, game_week)
    raise ProgressionError(ProgressionError.NO_AUTHOR)


@transaction.atomic
def nominate(nominator: AccountDB, target_type: str, target_id: int) -> Nomination:
    """Nominate the writer of a piece of this week's prose for good RP.

    Raises ``ProgressionError`` for a self-nomination (any of the account's
    own characters), an unplayed character, an invisible or out-of-week piece,
    or a piece this account already cited this week.
    """
    game_week = get_current_game_week()
    nominee = resolve_nominee(nominator, target_type, target_id, game_week)
    nominee_account = get_account_for_character(nominee.character)
    if nominee_account is None:
        raise ProgressionError(ProgressionError.NO_PLAYER)
    if nominee_account.pk == nominator.pk:
        raise ProgressionError(ProgressionError.SELF_NOMINATION)
    already = Nomination.objects.filter(
        nominator=nominator,
        game_week=game_week,
        target_type=target_type,
        target_id=target_id,
    ).exists()
    if already:
        raise ProgressionError(ProgressionError.ALREADY_NOMINATED)
    return Nomination.objects.create(
        nominator=nominator,
        game_week=game_week,
        nominee=nominee,
        target_type=target_type,
        target_id=target_id,
    )


@transaction.atomic
def withdraw_nomination(nominator: AccountDB, target_type: str, target_id: int) -> None:
    """Take back this week's citation of a piece, while the week is still open."""
    game_week = get_current_game_week()
    row = (
        Nomination.objects.select_for_update()
        .filter(
            nominator=nominator,
            game_week=game_week,
            target_type=target_type,
            target_id=target_id,
        )
        .first()
    )
    if row is None:
        raise ProgressionError(ProgressionError.NOMINATION_NOT_FOUND)
    if row.processed:
        raise ProgressionError(ProgressionError.NOMINATION_PROCESSED)
    row.delete()


def nominations_by_account(nominator: AccountDB) -> QuerySet[Nomination]:
    """This week's citations by ``nominator``: the one list a nominator may see."""
    return Nomination.objects.filter(
        nominator=nominator,
        game_week=get_current_game_week(),
        processed=False,
    ).select_related("nominee__character")


def has_nominated(nominator: AccountDB, target_type: str, target_id: int) -> bool:
    """Whether ``nominator`` already cited this piece this week."""
    return Nomination.objects.filter(
        nominator=nominator,
        game_week=get_current_game_week(),
        target_type=target_type,
        target_id=target_id,
        processed=False,
    ).exists()

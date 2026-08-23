"""Tavern games services (#3292): open/join/roll/resolve/abandon.

Money moves ONLY through ``world.currency.services.transfer`` - an ante is a
sink (purse -> nowhere) that also increments ``GameSession.pot``; a payout is
a mint (nowhere -> winner's purse) that zeroes it. There is no second ledger:
the pot integer and the currency service's own audit trail (``CurrencyTransfer``
rows) are kept in lockstep inside one atomic transaction per call.

Outcomes are public: every state change that matters to onlookers (open,
join, roll, payout) is narrated to the room via the scene interaction
pipeline, so the table is RP fuel rather than a private widget (#3292
decision 5).
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

from django.db import transaction

from world.tavern_games.constants import DICE_SIDES, MIN_SEATS_TO_ROLL, GameSessionState
from world.tavern_games.exceptions import (
    AlreadyRolledError,
    AlreadySeatedError,
    AnteOutOfRangeError,
    GameNotActiveError,
    LossCapExceededError,
    NotASocialHubError,
    NotAtPlaceError,
    NotEnoughSeatsError,
    NotSeatedError,
    SessionNotOpenError,
)
from world.tavern_games.models import GamblingLossLedger, GameSeat, GameSession, TavernGame

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.scenes.models import Persona
    from world.scenes.place_models import Place


# Coin is at stake, so rolls come from the OS entropy source rather than the
# predictable Mersenne Twister (SonarCloud S2245 on the original random.randint).
_TABLE_RNG = secrets.SystemRandom()


def _require_present(*, place: Place, persona: Persona) -> None:
    from world.scenes.place_models import PlacePresence  # noqa: PLC0415

    if not PlacePresence.objects.filter(place=place, persona=persona).exists():
        raise NotAtPlaceError


def _require_social_hub(place: Place) -> None:
    if place.room_id is None or not place.room.is_social_hub:
        raise NotASocialHubError


def _charge_ante(*, character_sheet: CharacterSheet, session: GameSession, amount: int) -> None:
    """Debit ``amount`` from the sheet's purse into the session's escrow pot.

    Refuses (``LossCapExceededError``) when this ante would push the character
    past their ``TavernGamblingConfig`` weekly loss cap for the current IC
    week. The ledger row is locked and bumped in the same transaction as the
    currency sink, so a concurrent ante can never both pass the cap check.
    """
    from world.currency.services import get_or_create_purse, transfer  # noqa: PLC0415
    from world.game_clock.week_services import get_current_game_week  # noqa: PLC0415
    from world.tavern_games.models import TavernGamblingConfig  # noqa: PLC0415

    week = get_current_game_week()
    ledger, _created = GamblingLossLedger.objects.select_for_update().get_or_create(
        character_sheet=character_sheet,
        game_week=week,
    )
    cap = TavernGamblingConfig.load().weekly_loss_cap
    if ledger.total_lost + amount > cap:
        raise LossCapExceededError

    transfer(
        amount=amount,
        reason=f"tavern game ante: {session.game.name} #{session.pk}",
        from_purse=get_or_create_purse(character_sheet),
    )
    ledger.total_lost += amount
    ledger.save(update_fields=["total_lost"])
    session.pot += amount
    session.save(update_fields=["pot"])


def _narrate(*, character, content: str, place: Place) -> None:
    """Public POSE-level narration authored by ``character``, room-visible via ``place``."""
    from world.scenes.constants import InteractionMode  # noqa: PLC0415
    from world.scenes.interaction_services import (  # noqa: PLC0415
        get_active_scene,
        record_interaction,
    )

    scene = get_active_scene(character.location)
    record_interaction(
        character=character,
        content=content,
        mode=InteractionMode.POSE,
        scene=scene,
        place=place,
    )


def _narrate_outcome(*, session: GameSession, content: str) -> None:
    """System-authored OUTCOME narration for a resolution/refund, room-visible.

    Mirrors ``world.covenants.perks.services``'s narrator-authored announce
    path (both go through the same "private" ``_broadcast_to_location`` /
    ``_build_interaction_payload`` pair since neither has a ``SceneRound`` to
    ride ``broadcast_scene_outcome``'s public wrapper).
    """
    from world.scenes.constants import InteractionMode  # noqa: PLC0415
    from world.scenes.interaction_services import (  # noqa: PLC0415
        _broadcast_to_location,
        _build_interaction_payload,
        create_interaction,
        get_active_scene,
    )
    from world.scenes.narrator import get_or_create_narrator_persona  # noqa: PLC0415

    room = session.place.room.objectdb
    narrator = get_or_create_narrator_persona()
    scene = get_active_scene(room)
    interaction = create_interaction(
        persona=narrator,
        content=content,
        mode=InteractionMode.OUTCOME,
        scene=scene,
        place=session.place,
    )
    payload = _build_interaction_payload(
        interaction_id=interaction.pk,
        persona=narrator,
        content=interaction.content,
        mode=interaction.mode,
        timestamp=interaction.timestamp.isoformat(),
        scene_id=interaction.scene_id,
    )
    _broadcast_to_location(room, payload)


@transaction.atomic
def open_session(*, place: Place, game: TavernGame, persona: Persona, ante: int) -> GameSession:
    """Open a new table at ``place``: the opener seats and antes in immediately."""
    if not game.is_active:
        raise GameNotActiveError
    if ante < game.min_ante or ante > game.max_ante:
        raise AnteOutOfRangeError
    _require_present(place=place, persona=persona)
    _require_social_hub(place)

    session = GameSession.objects.create(
        place=place,
        game=game,
        ante=ante,
        opened_by=persona,
    )
    _charge_ante(character_sheet=persona.character_sheet, session=session, amount=ante)
    GameSeat.objects.create(session=session, persona=persona, ante_paid=ante)
    _narrate(
        character=persona.character_sheet.character,
        content=f"opens a game of {game.name} at the table (ante {ante} coppers).",
        place=place,
    )
    return session


@transaction.atomic
def join_session(*, session: GameSession, persona: Persona) -> GameSeat:
    """Ante in and take a seat at an OPEN session."""
    session = GameSession.objects.select_for_update().get(pk=session.pk)
    if session.state != GameSessionState.OPEN:
        raise SessionNotOpenError
    if GameSeat.objects.filter(session=session, persona=persona).exists():
        raise AlreadySeatedError
    _require_present(place=session.place, persona=persona)

    _charge_ante(character_sheet=persona.character_sheet, session=session, amount=session.ante)
    seat = GameSeat.objects.create(session=session, persona=persona, ante_paid=session.ante)
    _narrate(
        character=persona.character_sheet.character,
        content=f"antes in and joins the game of {session.game.name}.",
        place=session.place,
    )
    return seat


@transaction.atomic
def roll(*, session: GameSession, persona: Persona) -> GameSeat:
    """Roll the dice for this hand. Auto-resolves once every seat has rolled."""
    session = GameSession.objects.select_for_update().get(pk=session.pk)
    if session.state != GameSessionState.OPEN:
        raise SessionNotOpenError
    seat = GameSeat.objects.filter(session=session, persona=persona).first()
    if seat is None:
        raise NotSeatedError
    if seat.roll_result is not None:
        raise AlreadyRolledError
    seat_count = GameSeat.objects.filter(session=session).count()
    if seat_count < MIN_SEATS_TO_ROLL:
        raise NotEnoughSeatsError

    seat.roll_result = _TABLE_RNG.randint(1, DICE_SIDES)
    seat.save(update_fields=["roll_result"])
    _narrate(
        character=persona.character_sheet.character,
        content=f"rolls the dice for {session.game.name}: {seat.roll_result}!",
        place=session.place,
    )

    _maybe_resolve(session)
    return seat


def _maybe_resolve(session: GameSession) -> None:
    """Resolve the hand once every seat has rolled; re-roll the whole table on a tie."""
    seats = list(GameSeat.objects.filter(session=session).select_related("persona"))
    if any(seat.roll_result is None for seat in seats):
        return

    high = max(seat.roll_result for seat in seats)
    winners = [seat for seat in seats if seat.roll_result == high]
    if len(winners) > 1:
        for seat in seats:
            seat.roll_result = None
            seat.save(update_fields=["roll_result"])
        _narrate_outcome(
            session=session,
            content=f"The dice tie at {high}. The table rolls again.",
        )
        return

    _resolve(session, winners[0])


def _resolve(session: GameSession, winner_seat: GameSeat) -> None:
    from django.utils import timezone  # noqa: PLC0415

    from world.currency.services import get_or_create_purse, transfer  # noqa: PLC0415

    payout = session.pot
    transfer(
        amount=payout,
        reason=f"tavern game payout: {session.game.name} #{session.pk}",
        to_purse=get_or_create_purse(winner_seat.persona.character_sheet),
    )
    session.pot = 0
    session.state = GameSessionState.RESOLVED
    session.resolved_at = timezone.now()
    session.save(update_fields=["pot", "state", "resolved_at"])
    _narrate_outcome(
        session=session,
        content=(
            f"{winner_seat.persona.name} wins the pot of {payout} coppers at {session.game.name}!"
        ),
    )


@transaction.atomic
def leave_session(*, session: GameSession, persona: Persona) -> None:
    """Leave the table: refund this seat's ante. Closes the session when it's empty."""
    from world.currency.services import get_or_create_purse, transfer  # noqa: PLC0415

    session = GameSession.objects.select_for_update().get(pk=session.pk)
    if session.state != GameSessionState.OPEN:
        raise SessionNotOpenError
    seat = GameSeat.objects.filter(session=session, persona=persona).first()
    if seat is None:
        raise NotSeatedError

    refund = seat.ante_paid
    seat.delete()
    session.pot -= refund
    remaining = GameSeat.objects.filter(session=session).count()
    if remaining == 0:
        session.state = GameSessionState.ABANDONED
    session.save(update_fields=["pot", "state"])

    transfer(
        amount=refund,
        reason=f"tavern game refund: {session.game.name} #{session.pk}",
        to_purse=get_or_create_purse(persona.character_sheet),
    )
    _narrate(
        character=persona.character_sheet.character,
        content=f"leaves the game of {session.game.name}, taking back their ante.",
        place=session.place,
    )
    if remaining == 0:
        _narrate_outcome(
            session=session,
            content=f"The game of {session.game.name} breaks up with no one left at the table.",
        )

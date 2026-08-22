"""Money-integrity + refusal tests for tavern games services (#3292).

Covers the escrow round trip (ante -> pot -> payout), refund on leave/
abandon, the weekly loss-cap refusal, and the not-at-place / not-a-social-hub
gates. All money assertions read purse balances through
``world.currency.services.get_or_create_purse`` - never a parallel path.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.currency.services import get_or_create_purse, transfer
from world.scenes.factories import PlaceFactory
from world.scenes.place_models import PlacePresence
from world.tavern_games.constants import GameSessionState
from world.tavern_games.exceptions import (
    AlreadyRolledError,
    AlreadySeatedError,
    AnteOutOfRangeError,
    LossCapExceededError,
    NotASocialHubError,
    NotAtPlaceError,
    NotEnoughSeatsError,
    NotSeatedError,
)
from world.tavern_games.factories import TavernGameFactory
from world.tavern_games.models import (
    GamblingLossLedger,
    GameSeat,
    GameSession,
    TavernGamblingConfig,
)
from world.tavern_games.services import join_session, leave_session, open_session, roll


def _fund(sheet, amount: int) -> None:
    transfer(amount=amount, reason="test seed", to_purse=get_or_create_purse(sheet))


def _persona_at_place(place, *, name: str, funded: int = 0):
    """Create a persona (with sheet + character) seated at *place*, funded with *funded* coppers.

    Uses the sheet's own auto-created PRIMARY persona (``CharacterSheetFactory``'s
    ``primary_persona`` post_generation hook names it after ``character.db_key`` -
    i.e. *name*) rather than minting a second, separately-named persona: an
    explicit ``PersonaFactory(..., name=name)`` here would collide with that
    auto-created row on the (character_sheet, name) unique constraint, since
    both would share the same *name*.
    """
    character = CharacterFactory(db_key=name)
    sheet = CharacterSheetFactory(character=character)
    persona = sheet.primary_persona
    sheet.active_persona = persona
    sheet.save(update_fields=["active_persona"])
    if funded:
        _fund(sheet, funded)
    PlacePresence.objects.create(place=place, persona=persona)
    return persona


class TavernGamesServiceTestBase(TestCase):
    def setUp(self) -> None:
        self.room_obj = ObjectDBFactory(
            db_key="TavernRoom", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.room_profile = RoomProfileFactory(objectdb=self.room_obj, is_social_hub=True)
        self.place = PlaceFactory(room=self.room_profile, name="The Bar")
        self.game = TavernGameFactory(min_ante=1, max_ante=1000)


class OpenJoinEscrowTests(TavernGamesServiceTestBase):
    def test_open_debits_opener_and_seats_them(self):
        opener = _persona_at_place(self.place, name="Opener", funded=100)
        session = open_session(place=self.place, game=self.game, persona=opener, ante=10)
        assert session.pot == 10
        assert get_or_create_purse(opener.character_sheet).balance == 90
        assert GameSeat.objects.filter(session=session, persona=opener).count() == 1

    def test_join_debits_joiner_and_grows_pot(self):
        opener = _persona_at_place(self.place, name="Opener", funded=100)
        joiner = _persona_at_place(self.place, name="Joiner", funded=100)
        session = open_session(place=self.place, game=self.game, persona=opener, ante=10)
        join_session(session=session, persona=joiner)
        session.refresh_from_db()
        assert session.pot == 20
        assert get_or_create_purse(joiner.character_sheet).balance == 90

    def test_join_twice_refuses(self):
        opener = _persona_at_place(self.place, name="Opener", funded=100)
        joiner = _persona_at_place(self.place, name="Joiner", funded=100)
        session = open_session(place=self.place, game=self.game, persona=opener, ante=10)
        join_session(session=session, persona=joiner)
        with self.assertRaises(AlreadySeatedError):
            join_session(session=session, persona=joiner)

    def test_ante_out_of_range_refuses(self):
        opener = _persona_at_place(self.place, name="Opener", funded=100)
        with self.assertRaises(AnteOutOfRangeError):
            open_session(place=self.place, game=self.game, persona=opener, ante=0)
        assert GameSession.objects.count() == 0

    def test_not_at_place_refuses(self):
        other_place = PlaceFactory(room=self.room_profile, name="The Corner")
        opener = _persona_at_place(other_place, name="Opener", funded=100)
        with self.assertRaises(NotAtPlaceError):
            open_session(place=self.place, game=self.game, persona=opener, ante=10)
        assert GameSession.objects.count() == 0

    def test_not_a_social_hub_refuses(self):
        quiet_room = RoomProfileFactory(
            objectdb=ObjectDBFactory(
                db_key="QuietRoom", db_typeclass_path="typeclasses.rooms.Room"
            ),
            is_social_hub=False,
        )
        quiet_place = PlaceFactory(room=quiet_room, name="A Quiet Nook")
        opener = _persona_at_place(quiet_place, name="Opener", funded=100)
        with self.assertRaises(NotASocialHubError):
            open_session(place=quiet_place, game=self.game, persona=opener, ante=10)
        assert GameSession.objects.count() == 0


class ResolveTests(TavernGamesServiceTestBase):
    def test_roll_requires_minimum_seats(self):
        opener = _persona_at_place(self.place, name="Opener", funded=100)
        session = open_session(place=self.place, game=self.game, persona=opener, ante=10)
        with self.assertRaises(NotEnoughSeatsError):
            roll(session=session, persona=opener)

    def test_already_rolled_refuses(self):
        opener = _persona_at_place(self.place, name="Opener", funded=100)
        joiner = _persona_at_place(self.place, name="Joiner", funded=100)
        session = open_session(place=self.place, game=self.game, persona=opener, ante=10)
        join_session(session=session, persona=joiner)
        with patch("world.tavern_games.services.random.randint", return_value=3):
            roll(session=session, persona=opener)
        with self.assertRaises(AlreadyRolledError):
            with patch("world.tavern_games.services.random.randint", return_value=3):
                roll(session=session, persona=opener)

    def test_highest_roll_wins_pot_and_resolves(self):
        opener = _persona_at_place(self.place, name="Opener", funded=100)
        joiner = _persona_at_place(self.place, name="Joiner", funded=100)
        session = open_session(place=self.place, game=self.game, persona=opener, ante=10)
        join_session(session=session, persona=joiner)

        rolls = iter([2, 5])
        with patch(
            "world.tavern_games.services.random.randint", side_effect=lambda *_a: next(rolls)
        ):
            roll(session=session, persona=opener)
            roll(session=session, persona=joiner)

        session.refresh_from_db()
        assert session.state == GameSessionState.RESOLVED
        assert session.pot == 0
        # Opener started at 90 (after ante), joiner at 90; joiner (roll=5) wins the 20-copper pot.
        assert get_or_create_purse(opener.character_sheet).balance == 90
        assert get_or_create_purse(joiner.character_sheet).balance == 110

    def test_tie_resets_rolls_for_a_reroll(self):
        opener = _persona_at_place(self.place, name="Opener", funded=100)
        joiner = _persona_at_place(self.place, name="Joiner", funded=100)
        session = open_session(place=self.place, game=self.game, persona=opener, ante=10)
        join_session(session=session, persona=joiner)

        with patch("world.tavern_games.services.random.randint", return_value=4):
            roll(session=session, persona=opener)
            roll(session=session, persona=joiner)

        session.refresh_from_db()
        assert session.state == GameSessionState.OPEN
        assert session.pot == 20
        seats = list(GameSeat.objects.filter(session=session))
        assert all(seat.roll_result is None for seat in seats)

        rolls = iter([1, 6])
        with patch(
            "world.tavern_games.services.random.randint", side_effect=lambda *_a: next(rolls)
        ):
            roll(session=session, persona=opener)
            roll(session=session, persona=joiner)
        session.refresh_from_db()
        assert session.state == GameSessionState.RESOLVED
        assert get_or_create_purse(joiner.character_sheet).balance == 110


class LeaveAbandonTests(TavernGamesServiceTestBase):
    def test_leave_refunds_and_closes_lone_seat(self):
        opener = _persona_at_place(self.place, name="Opener", funded=100)
        session = open_session(place=self.place, game=self.game, persona=opener, ante=10)
        leave_session(session=session, persona=opener)
        session.refresh_from_db()
        assert session.state == GameSessionState.ABANDONED
        assert session.pot == 0
        assert get_or_create_purse(opener.character_sheet).balance == 100
        assert GameSeat.objects.filter(session=session).count() == 0

    def test_leave_one_of_two_refunds_only_that_seat(self):
        opener = _persona_at_place(self.place, name="Opener", funded=100)
        joiner = _persona_at_place(self.place, name="Joiner", funded=100)
        session = open_session(place=self.place, game=self.game, persona=opener, ante=10)
        join_session(session=session, persona=joiner)

        leave_session(session=session, persona=joiner)
        session.refresh_from_db()
        assert session.state == GameSessionState.OPEN
        assert session.pot == 10
        assert get_or_create_purse(joiner.character_sheet).balance == 100
        assert get_or_create_purse(opener.character_sheet).balance == 90

    def test_leave_when_not_seated_refuses(self):
        opener = _persona_at_place(self.place, name="Opener", funded=100)
        bystander = _persona_at_place(self.place, name="Bystander", funded=100)
        session = open_session(place=self.place, game=self.game, persona=opener, ante=10)
        with self.assertRaises(NotSeatedError):
            leave_session(session=session, persona=bystander)


class LossCapTests(TavernGamesServiceTestBase):
    def test_ante_past_the_weekly_cap_refuses_and_rolls_back(self):
        config = TavernGamblingConfig.load()
        config.weekly_loss_cap = 15
        config.save(update_fields=["weekly_loss_cap"])

        opener = _persona_at_place(self.place, name="Opener", funded=100)
        with self.assertRaises(LossCapExceededError):
            open_session(place=self.place, game=self.game, persona=opener, ante=20)

        assert GameSession.objects.count() == 0
        assert get_or_create_purse(opener.character_sheet).balance == 100
        ledger_qs = GamblingLossLedger.objects.filter(character_sheet=opener.character_sheet)
        assert ledger_qs.count() == 0

    def test_ante_under_the_cap_then_a_second_ante_over_it_refuses(self):
        config = TavernGamblingConfig.load()
        config.weekly_loss_cap = 15
        config.save(update_fields=["weekly_loss_cap"])

        opener = _persona_at_place(self.place, name="Opener", funded=100)
        session = open_session(place=self.place, game=self.game, persona=opener, ante=10)
        joiner = _persona_at_place(self.place, name="Joiner", funded=100)
        join_session(session=session, persona=joiner)

        # Opener already spent 10 of a 15 cap this week; leaving and re-opening
        # a second table with an ante of 10 would push them to 20 - over cap.
        leave_session(session=session, persona=opener)
        with self.assertRaises(LossCapExceededError):
            open_session(place=self.place, game=self.game, persona=opener, ante=10)

"""Tests for OpenGameAction/JoinGameAction/RollGameAction/LeaveGameAction (#3292)."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from actions.definitions.tavern_games import (
    JoinGameAction,
    LeaveGameAction,
    OpenGameAction,
    RollGameAction,
)
from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    ObjectDBFactory,
    RoomProfileFactory,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.currency.services import get_or_create_purse, transfer
from world.scenes.factories import PersonaFactory, PlaceFactory
from world.scenes.place_models import PlacePresence
from world.tavern_games.constants import GameSessionState
from world.tavern_games.factories import TavernGameFactory
from world.tavern_games.models import GameSeat, GameSession


def _seated_actor(place, *, db_key: str, funded: int = 100):
    account = AccountFactory(username=f"tavern_{db_key.lower()}")
    actor = CharacterFactory(db_key=db_key, location=place.room.objectdb)
    actor.db_account = account
    actor.save()
    sheet = CharacterSheetFactory(character=actor)
    persona = PersonaFactory(character_sheet=sheet)
    sheet.active_persona = persona
    sheet.save(update_fields=["active_persona"])
    transfer(amount=funded, reason="test seed", to_purse=get_or_create_purse(sheet))
    PlacePresence.objects.create(place=place, persona=persona)
    return actor, persona


class TavernGameActionsTestBase(TestCase):
    def setUp(self) -> None:
        room = ObjectDBFactory(
            db_key="TavernActionRoom", db_typeclass_path="typeclasses.rooms.Room"
        )
        room_profile = RoomProfileFactory(objectdb=room, is_social_hub=True)
        self.place = PlaceFactory(room=room_profile, name="The Bar")
        self.game = TavernGameFactory(min_ante=1, max_ante=1000)


class OpenGameActionTests(TavernGameActionsTestBase):
    def test_open_creates_session_and_debits_ante(self):
        actor, persona = _seated_actor(self.place, db_key="Opener")
        result = OpenGameAction().run(actor=actor, place=self.place, game=self.game, ante=10)
        assert result.success
        session = GameSession.objects.get(pk=result.data["session_id"])
        assert session.pot == 10
        assert GameSeat.objects.filter(session=session, persona=persona).exists()

    def test_open_missing_kwargs_fails(self):
        actor, _persona = _seated_actor(self.place, db_key="OpenerNoKwargs")
        result = OpenGameAction().run(actor=actor)
        assert not result.success

    def test_open_translates_typed_error_to_message(self):
        actor, _persona = _seated_actor(self.place, db_key="OpenerBadAnte")
        result = OpenGameAction().run(actor=actor, place=self.place, game=self.game, ante=0)
        assert not result.success
        assert "range" in result.message.lower()


class JoinGameActionTests(TavernGameActionsTestBase):
    def test_join_seats_the_actor_and_grows_pot(self):
        _opener, opener_persona = _seated_actor(self.place, db_key="Opener2")
        session = GameSession.objects.create(
            place=self.place, game=self.game, ante=10, opened_by=opener_persona
        )
        GameSeat.objects.create(session=session, persona=opener_persona, ante_paid=10)

        joiner, joiner_persona = _seated_actor(self.place, db_key="Joiner")
        result = JoinGameAction().run(actor=joiner, session=session)
        assert result.success
        session.refresh_from_db()
        assert session.pot == 20
        assert GameSeat.objects.filter(session=session, persona=joiner_persona).exists()


class RollGameActionTests(TavernGameActionsTestBase):
    def test_roll_returns_the_seat_result(self):
        opener, opener_persona = _seated_actor(self.place, db_key="Opener3")
        _joiner, joiner_persona = _seated_actor(self.place, db_key="Joiner2")
        session = GameSession.objects.create(
            place=self.place, game=self.game, ante=10, opened_by=opener_persona
        )
        GameSeat.objects.create(session=session, persona=opener_persona, ante_paid=10)
        GameSeat.objects.create(session=session, persona=joiner_persona, ante_paid=10)

        with patch("world.tavern_games.services.random.randint", return_value=4):
            result = RollGameAction().run(actor=opener, session=session)
        assert result.success
        assert result.data["roll_result"] == 4


class LeaveGameActionTests(TavernGameActionsTestBase):
    def test_leave_refunds_and_may_abandon(self):
        opener, opener_persona = _seated_actor(self.place, db_key="Opener4")
        session = GameSession.objects.create(
            place=self.place, game=self.game, ante=10, opened_by=opener_persona
        )
        GameSeat.objects.create(session=session, persona=opener_persona, ante_paid=10)
        session.pot = 10
        session.save(update_fields=["pot"])

        result = LeaveGameAction().run(actor=opener, session=session)
        assert result.success
        session.refresh_from_db()
        assert session.state == GameSessionState.ABANDONED

    def test_leave_when_not_seated_fails(self):
        _opener, opener_persona = _seated_actor(self.place, db_key="Opener5")
        session = GameSession.objects.create(
            place=self.place, game=self.game, ante=10, opened_by=opener_persona
        )
        bystander, _bystander_persona = _seated_actor(self.place, db_key="Bystander")
        result = LeaveGameAction().run(actor=bystander, session=session)
        assert not result.success

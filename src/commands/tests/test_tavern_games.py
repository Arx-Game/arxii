"""E2E telnet journey for CmdGame: tavern games coin-stakes gambling (#3292).

Drives the real ``game`` command end to end (open -> join -> roll -> roll ->
resolve) at a seeded social-hub Place, asserting real purse-balance changes
through ``world.currency.services.get_or_create_purse`` - never a mocked
service layer. Only the dice roll itself is patched, to make the outcome
deterministic.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from commands.tavern_games import CmdGame
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.currency.services import get_or_create_purse, transfer
from world.scenes.factories import PlaceFactory
from world.scenes.place_models import PlacePresence
from world.tavern_games.constants import GameSessionState
from world.tavern_games.models import GameSession
from world.tavern_games.seeds import DICE_GAME_NAME, ensure_dice_game


def _run(caller, args: str) -> list[str]:
    caller.msg = MagicMock()
    cmd = CmdGame()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"game {args}".strip()
    cmd.func()
    return [str(c.args[0]) for c in caller.msg.call_args_list if c.args]


def _seated_character(place, *, name: str, funded: int):
    """Create+seat a character at *place*, funded, presenting as their PRIMARY persona.

    Uses the sheet's own auto-created PRIMARY persona (``CharacterSheetFactory``'s
    ``primary_persona`` post_generation hook names it after ``character.db_key`` -
    i.e. *name*) rather than minting a second, separately-named persona: an
    explicit ``PersonaFactory(..., name=name)`` here would collide with that
    auto-created row on the (character_sheet, name) unique constraint, since
    both would share the same *name*.
    """
    character = CharacterFactory(db_key=name, location=place.room.objectdb)
    sheet = CharacterSheetFactory(character=character)
    persona = sheet.primary_persona
    sheet.active_persona = persona
    sheet.save(update_fields=["active_persona"])
    transfer(amount=funded, reason="test seed", to_purse=get_or_create_purse(sheet))
    PlacePresence.objects.create(place=place, persona=persona)
    return character


class TavernGameTelnetJourneyTest(TestCase):
    """The full coin-stakes journey, played at a seeded social hub."""

    def setUp(self) -> None:
        self.game = ensure_dice_game()
        room_obj = ObjectDBFactory(
            db_key="TavernHubRoom", db_typeclass_path="typeclasses.rooms.Room"
        )
        room_profile = RoomProfileFactory(objectdb=room_obj, is_social_hub=True)
        self.place = PlaceFactory(room=room_profile, name="The Rowdy Table")
        self.alice = _seated_character(self.place, name="Alice", funded=100)
        self.bob = _seated_character(self.place, name="Bob", funded=100)

    def test_open_join_roll_roll_resolves_and_pays_the_winner(self) -> None:
        msgs = _run(self.alice, f"open {DICE_GAME_NAME}=10")
        self.assertTrue(any("open" in m.lower() for m in msgs))
        session = GameSession.objects.get(place=self.place, game=self.game)
        self.assertEqual(session.pot, 10)
        self.assertEqual(get_or_create_purse(self.alice.character_sheet).balance, 90)

        _run(self.bob, "join")
        session.refresh_from_db()
        self.assertEqual(session.pot, 20)
        self.assertEqual(get_or_create_purse(self.bob.character_sheet).balance, 90)

        rolls = iter([2, 6])
        with patch(
            "world.tavern_games.services.random.randint", side_effect=lambda *_a: next(rolls)
        ):
            alice_msgs = _run(self.alice, "roll")
            bob_msgs = _run(self.bob, "roll")

        self.assertTrue(any("roll a 2" in m.lower() for m in alice_msgs))
        self.assertTrue(any("roll a 6" in m.lower() for m in bob_msgs))

        session.refresh_from_db()
        self.assertEqual(session.state, GameSessionState.RESOLVED)
        self.assertEqual(session.pot, 0)
        # Alice loses her 10-copper ante; Bob (roll=6) wins the 20-copper pot.
        self.assertEqual(get_or_create_purse(self.alice.character_sheet).balance, 90)
        self.assertEqual(get_or_create_purse(self.bob.character_sheet).balance, 110)

    def test_leave_before_resolution_refunds_the_ante(self) -> None:
        _run(self.alice, f"open {DICE_GAME_NAME}=15")
        _run(self.bob, "join")
        self.assertEqual(get_or_create_purse(self.bob.character_sheet).balance, 85)

        _run(self.bob, "leave")

        session = GameSession.objects.get(place=self.place, game=self.game)
        self.assertEqual(session.state, GameSessionState.OPEN)
        self.assertEqual(session.pot, 15)
        self.assertEqual(get_or_create_purse(self.bob.character_sheet).balance, 100)

    def test_bare_game_shows_the_open_table(self) -> None:
        _run(self.alice, f"open {DICE_GAME_NAME}=5")
        msgs = _run(self.bob, "")
        joined = " ".join(msgs).lower()
        self.assertIn(self.game.name.lower(), joined)
        self.assertIn("ante 5", joined)

    def test_unknown_game_name_errors(self) -> None:
        msgs = _run(self.alice, "open Not A Real Game=10")
        self.assertTrue(any("no such game" in m.lower() for m in msgs))
        self.assertFalse(GameSession.objects.filter(place=self.place).exists())

    def test_roll_without_a_second_player_refuses(self) -> None:
        _run(self.alice, f"open {DICE_GAME_NAME}=10")
        msgs = _run(self.alice, "roll")
        self.assertTrue(any("another player" in m.lower() for m in msgs))

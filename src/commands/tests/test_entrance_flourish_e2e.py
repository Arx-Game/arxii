"""E2E journey: enter → flourish prompt → flourish <resonance> → grant (#1339).

Drives the full telnet loop end-to-end. The only mock is
``start_action_resolution`` — we stub it to return a successful
``PendingActionResolution`` (its real return type) so the test doesn't need a
full ActionTemplate + check-chain seed. Everything else (offer creation,
notification, flourish resolution, grant write) is real.

Tagged ``postgres`` because ``grant_resonance`` / ``create_entry_flourish``
write ``ResonanceGrant`` rows and the magic test tier is PG-only.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase, tag

from actions.factories import ActionTemplateFactory
from actions.tests.resolution_helpers import make_resolution
from commands.exceptions import CommandError
from commands.social.entrance_flourish import CmdEnter, CmdFlourish
from evennia_extensions.factories import AccountFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.entry_flourish import PendingEntryFlourishOffer
from world.magic.factories import (
    CharacterResonanceFactory,
    CharacterTechniqueFactory,
    ResonanceFactory,
    TechniqueFactory,
)
from world.magic.models import CharacterResonance
from world.roster.factories import RosterTenureFactory
from world.scenes.factories import SceneFactory

# Patch the function at the module it lives in; EntranceAction imports it
# locally via ``from actions.services import start_action_resolution``.
_ENTRANCE_RESOLUTION_PATH = "actions.services.start_action_resolution"


@tag("postgres")
class EntranceFlourishJourneyTest(TestCase):
    """Full telnet journey: enter → prompted → flourish → resonance granted."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory(name="Embers")
        # Character has Embers claimed (balance starts at 0)
        CharacterResonanceFactory(character_sheet=cls.sheet, resonance=cls.resonance)
        # EntranceAction.execute() calls ActionTemplate.objects.get(name="Entrance")
        # and checks template.grants_entry_flourish; seed the required row.
        cls.entrance_template = ActionTemplateFactory(
            name="Entrance",
            grants_entry_flourish=True,
        )

    def setUp(self) -> None:
        self.character = self.sheet.character
        self.character.msg = MagicMock()

    def _run_enter(self) -> None:
        cmd = CmdEnter()
        cmd.caller = self.character
        cmd.args = ""
        cmd.raw_string = "enter"
        cmd.func()

    def _run_flourish(self, arg: str) -> None:
        cmd = CmdFlourish()
        cmd.caller = self.character
        cmd.args = arg
        cmd.raw_string = f"flourish {arg}"
        cmd.func()

    def _received_messages(self) -> list[str]:
        """Return all text strings passed to character.msg()."""
        # Both the entrance flourish prompt and the flourish confirmation ride
        # ``result.message`` — ArxCommand.func() surfaces them via self.msg(result.message),
        # which lands on character.msg. Collect every positional-first-arg call here.
        return [str(call.args[0]) for call in self.character.msg.call_args_list if call.args]

    def test_enter_creates_offer_and_notifies_player(self) -> None:
        """After a successful entrance, an offer is minted and the player is told to flourish."""
        with patch(
            _ENTRANCE_RESOLUTION_PATH,
            return_value=make_resolution(1),
        ):
            self._run_enter()

        # Offer minted
        self.assertTrue(
            PendingEntryFlourishOffer.objects.filter(character_sheet=self.sheet).exists()
        )

        # Player received the flourish prompt
        messages = self._received_messages()
        self.assertTrue(
            any("flourish" in m.lower() for m in messages),
            f"Expected a flourish prompt in messages; got: {messages}",
        )

    def test_flourish_grants_resonance(self) -> None:
        """After an offer exists, `flourish Embers` resolves it and grants the resonance."""
        # Mint the offer directly (we tested enter→offer in the previous test)
        PendingEntryFlourishOffer.objects.create(character_sheet=self.sheet)
        balance_before = CharacterResonance.objects.get(
            character_sheet=self.sheet, resonance=self.resonance
        ).balance

        self._run_flourish("Embers")

        cr = CharacterResonance.objects.get(character_sheet=self.sheet, resonance=self.resonance)
        self.assertGreater(cr.balance, balance_before, "Flourish should have granted resonance")
        # Offer consumed
        self.assertFalse(
            PendingEntryFlourishOffer.objects.filter(character_sheet=self.sheet).exists()
        )
        # Player received a confirmation
        messages = self._received_messages()
        self.assertTrue(
            any("embers" in m.lower() or "arrival" in m.lower() for m in messages),
            f"Expected flourish confirmation in messages; got: {messages}",
        )

    def test_flourish_without_offer_reports_error(self) -> None:
        """Calling `flourish` with no pending offer shows an error, no grant written."""
        self._run_flourish("Embers")
        messages = self._received_messages()
        self.assertTrue(
            any("no pending flourish" in m.lower() for m in messages),
            f"Expected 'no pending flourish' error; got: {messages}",
        )
        # No resonance grant written — balance still at starting value (0)
        cr = CharacterResonance.objects.get(character_sheet=self.sheet, resonance=self.resonance)
        self.assertEqual(cr.balance, 0)


class CmdEnterTechniqueGrammarTests(TestCase):
    """``enter [<technique>[=<target>]]`` argument parsing (#2183 Task 4).

    Not tagged ``postgres`` — this only exercises ``resolve_action_args()``'s
    parsing, never the technique-cast/resonance-grant write paths above.
    """

    def setUp(self) -> None:
        # ObjectDB fixtures must be built in setUp (idmapper/DbHolder trap).
        self.room = ObjectDBFactory(
            db_key="EntranceGrammarHall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.caller_char = ObjectDBFactory(
            db_key="Entrant",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.target_char = ObjectDBFactory(
            db_key="Fighter",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.caller_sheet = CharacterSheetFactory(character=self.caller_char)
        self.target_sheet = CharacterSheetFactory(character=self.target_char)

        self.caller_account = AccountFactory()
        self.target_account = AccountFactory()
        RosterTenureFactory(
            player_data=self.caller_account.player_data,
            roster_entry__character_sheet=self.caller_sheet,
        )
        RosterTenureFactory(
            player_data=self.target_account.player_data,
            roster_entry__character_sheet=self.target_sheet,
        )

        self.target_persona = self.target_sheet.primary_persona
        self.target_persona.name = "Fighter"
        self.target_persona.save()

        SceneFactory(
            is_active=True,
            location=self.room,
            participants=[self.caller_account, self.target_account],
        )
        if hasattr(self.room, "_active_scene_cache"):
            del self.room._active_scene_cache

        self.technique = TechniqueFactory()
        CharacterTechniqueFactory(character=self.caller_sheet, technique=self.technique)

    def _make_cmd(self, args: str) -> CmdEnter:
        cmd = CmdEnter()
        cmd.caller = self.caller_char
        cmd.args = args
        cmd.raw_string = f"enter {args}".strip()
        return cmd

    def test_bare_enter_returns_empty_kwargs(self) -> None:
        cmd = self._make_cmd("")
        self.assertEqual(cmd.resolve_action_args(), {})

    def test_enter_known_technique_resolves_id(self) -> None:
        cmd = self._make_cmd(self.technique.name)
        self.assertEqual(cmd.resolve_action_args(), {"technique_id": self.technique.pk})

    def test_enter_unknown_technique_raises(self) -> None:
        cmd = self._make_cmd("NotATechnique")
        with self.assertRaises(CommandError):
            cmd.resolve_action_args()

    def test_enter_technique_with_target_resolves_both(self) -> None:
        cmd = self._make_cmd(f"{self.technique.name}=Fighter")
        kwargs = cmd.resolve_action_args()
        self.assertEqual(kwargs["technique_id"], self.technique.pk)
        self.assertEqual(kwargs["target_persona_id"], self.target_persona.pk)

    def test_enter_technique_with_unknown_target_raises(self) -> None:
        cmd = self._make_cmd(f"{self.technique.name}=Nobody")
        with self.assertRaises(CommandError):
            cmd.resolve_action_args()

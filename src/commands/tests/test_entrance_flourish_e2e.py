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
from commands.social.entrance_flourish import CmdEnter, CmdFlourish
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.entry_flourish import PendingEntryFlourishOffer
from world.magic.factories import CharacterResonanceFactory, ResonanceFactory
from world.magic.models import CharacterResonance

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

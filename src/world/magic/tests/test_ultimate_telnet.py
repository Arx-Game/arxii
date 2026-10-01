"""accept ultimate <n> over telnet (#4098 decision 16)."""

from unittest.mock import MagicMock

from django.test import TestCase
from evennia.utils.idmapper import models as idmapper_models

from commands.consent import CmdAccept
from commands.tests.message_capture import message_text
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import ConditionInstanceFactory
from world.covenants.constants import RoleArchetype
from world.magic.constants import GiftKind
from world.magic.factories import (
    AudereThresholdFactory,
    CharacterGiftFactory,
    GiftFactory,
    KnownUltimateFactory,
    PathGiftGrantFactory,
    UltimateTechniqueFactory,
    wire_audere_power_multipliers,
)
from world.magic.models import KnownUltimate
from world.mechanics.constants import EngagementType
from world.mechanics.factories import CharacterEngagementFactory
from world.progression.factories import CharacterPathHistoryFactory


class UltimateTelnetTests(TestCase):
    def setUp(self) -> None:
        idmapper_models.flush_cache()
        audere, _ = wire_audere_power_multipliers()
        AudereThresholdFactory(sword_reveal_label="Edge", reveal_framing_text="PLACEHOLDER framing")
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.character.msg = MagicMock()
        gift = GiftFactory(kind=GiftKind.MAJOR)
        CharacterGiftFactory(character=self.sheet, gift=gift)
        grant = PathGiftGrantFactory(gift=gift)
        CharacterPathHistoryFactory(character=self.sheet, path=grant.path)
        self.known = UltimateTechniqueFactory(
            gift=gift, name="Ember Ward", archetype_alignment=RoleArchetype.SHIELD
        )
        self.hidden = UltimateTechniqueFactory(
            gift=gift, name="Cinder Crown", archetype_alignment=RoleArchetype.SWORD
        )
        grant.ultimate_techniques.add(self.known, self.hidden)
        KnownUltimateFactory(character=self.sheet, technique=self.known)
        CharacterEngagementFactory(character=self.sheet, engagement_type=EngagementType.COMBAT)
        ConditionInstanceFactory(target=self.character, condition=audere)

    def _accept(self, args: str) -> str:
        cmd = CmdAccept()
        cmd.caller = self.character
        cmd.args = args
        cmd.raw_string = f"accept {args}"
        cmd.cmdname = "accept"
        cmd.func()
        return self._said()

    def _said(self) -> str:
        # A CommandError reaches func()'s except branch via two msg() calls: the
        # typed text line, then a kwargs-only ``command_error={...}`` frame with
        # no positional args (mirrors the guard in commands/tests/test_traps.py).
        return "\n".join(
            message_text(call.args[0]) for call in self.character.msg.call_args_list if call.args
        )

    def test_listing_numbers_known_and_undiscovered_without_raw_category(self) -> None:
        cmd = CmdAccept()
        cmd.caller = self.character
        cmd.args = ""
        cmd.raw_string = "accept"
        cmd.cmdname = "accept"
        cmd.func()
        text = self._said()
        self.assertIn("1) Ember Ward (known)", text)
        self.assertIn("2) Edge (undiscovered)", text)
        self.assertNotIn("Cinder Crown", text)
        self.assertNotIn("Sword", text)

    def test_accept_number_reveals_and_readies(self) -> None:
        text = self._accept("ultimate 2")
        self.assertIn("Cinder Crown", text)
        known = KnownUltimate.objects.get(character=self.sheet, technique=self.hidden)
        self.assertTrue(known.readied)

    def test_out_of_range_number_refused(self) -> None:
        text = self._accept("ultimate 9")
        self.assertFalse(KnownUltimate.objects.filter(readied=True).exists())
        self.assertIn("accept ultimate", text)

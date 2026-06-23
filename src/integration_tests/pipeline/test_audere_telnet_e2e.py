"""Telnet E2E: accept/decline surge and path crossing via CmdAccept/CmdDecline (#1344).

Proves the command → registry → handler → service wiring for the two offer types
this PR ships. setUp uses TestCase (not setUpTestData) to avoid ObjectDB deepcopy
issues under CI shard isolation.

The use_technique → PendingAudereOffer path is proven by test_audere_offer_pipeline.py;
here we create the offer row directly and focus on the telnet command surface.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from commands.consent import CmdAccept
from commands.offer_response import CmdDecline
from world.conditions.models import ConditionInstance
from world.magic.audere import AUDERE_CONDITION_NAME, SOULFRAY_CONDITION_NAME, PendingAudereOffer
from world.magic.audere_majora import AudereMajoraCrossing, PendingAudereMajoraOffer
from world.magic.factories import (
    AudereThresholdFactory,
    CharacterAnimaFactory,
    IntensityTierFactory,
    wire_audere_power_multipliers,
)
from world.magic.models import CharacterAnima
from world.magic.tests.majora_fixtures import build_crossing_world
from world.mechanics.engagement import CharacterEngagement


class TestAudereTelnetE2E(TestCase):
    """Command → registry → handler → service for surge and path-crossing offers."""

    def setUp(self) -> None:
        # wire_audere_power_multipliers creates the AUDERE_MAJORA_CONDITION_NAME
        # template that cross_threshold applies at the end of a crossing.
        wire_audere_power_multipliers()

        (
            self.character,
            self.sheet,
            self.threshold,
            self.prospect_path,
            self.puissant_path,
            self.majora_offer,
        ) = build_crossing_world(boundary_level=5, suffix="te2e")

        self.anima = CharacterAnimaFactory(character=self.character, current=50, maximum=50)

        # build_majora_world already created soulfray stages (1, 2, 3) for the shared
        # template. Fetch the stage_order=3 row to wire the audere gate minimum.
        soulfray_instance = (
            ConditionInstance.objects.filter(
                target=self.character,
                condition__name=SOULFRAY_CONDITION_NAME,
            )
            .select_related("current_stage")
            .first()
        )
        self.audere_tier = IntensityTierFactory(
            name="AudereSurgeTier_te2e", threshold=15, control_modifier=0
        )
        self.audere_config = AudereThresholdFactory(
            minimum_intensity_tier=self.audere_tier,
            minimum_warp_stage=soulfray_instance.current_stage,
            intensity_bonus=5,
            anima_pool_bonus=10,
            warp_multiplier=2,
        )

        # Gate 5 of check_audere_eligibility: character must NOT already be in audere.
        # build_majora_world pre-seeds the audere instance; delete it here.
        # The crossing tests re-add it before calling the command.
        ConditionInstance.objects.filter(
            target=self.character,
            condition__name=AUDERE_CONDITION_NAME,
        ).delete()

        self.audere_offer = PendingAudereOffer.objects.create(
            character_sheet=self.sheet,
            fired_intensity=20,
            soulfray_stage_order=soulfray_instance.current_stage.stage_order,
        )

        # Prevent Evennia's msg() from hitting a real session.
        self.character.msg = MagicMock()

    # ------------------------------------------------------------------
    # Surge path
    # ------------------------------------------------------------------

    def test_accept_surge_via_telnet(self) -> None:
        """accept surge → resolve_audere_offer → offer consumed + bonuses applied."""
        pre_intensity = CharacterEngagement.objects.get(character=self.character).intensity_modifier
        pre_maximum = CharacterAnima.objects.get(character=self.character).maximum

        cmd = CmdAccept()
        cmd.caller = self.character
        cmd.args = "surge"
        cmd.raw_string = "accept surge"
        cmd.cmdname = "accept"
        cmd.func()

        self.assertFalse(PendingAudereOffer.objects.filter(character_sheet=self.sheet).exists())
        engagement = CharacterEngagement.objects.get(character=self.character)
        self.assertEqual(
            engagement.intensity_modifier,
            pre_intensity + self.audere_config.intensity_bonus,
        )
        anima = CharacterAnima.objects.get(character=self.character)
        self.assertEqual(anima.maximum, pre_maximum + self.audere_config.anima_pool_bonus)
        self.character.msg.assert_called()

    def test_decline_surge_via_telnet(self) -> None:
        """decline surge → resolve_audere_offer(accept=False) → offer consumed."""
        cmd = CmdDecline()
        cmd.caller = self.character
        cmd.args = "surge"
        cmd.raw_string = "decline surge"
        cmd.cmdname = "decline"
        cmd.func()

        self.assertFalse(PendingAudereOffer.objects.filter(character_sheet=self.sheet).exists())
        self.character.msg.assert_called()

    # ------------------------------------------------------------------
    # Path-crossing path
    # ------------------------------------------------------------------

    def test_accept_crossing_via_telnet(self) -> None:
        """accept crossing path=<name> declaration=<text> → offer consumed + crossing recorded."""
        # Gate 7 of check_audere_majora_eligibility: requires active audere condition.
        from world.conditions.models import ConditionTemplate
        from world.conditions.services import apply_condition

        audere_template = ConditionTemplate.objects.get(name=AUDERE_CONDITION_NAME)
        apply_condition(target=self.character, condition=audere_template)

        declaration = "I have walked the long road to this moment and I step forward now."
        cmd = CmdAccept()
        cmd.caller = self.character
        cmd.args = f"crossing path={self.puissant_path.name} declaration={declaration}"
        cmd.raw_string = f"accept {cmd.args}"
        cmd.cmdname = "accept"
        cmd.func()

        self.assertFalse(
            PendingAudereMajoraOffer.objects.filter(character_sheet=self.sheet).exists()
        )
        self.assertTrue(
            AudereMajoraCrossing.objects.filter(
                character_sheet=self.sheet,
                chosen_path=self.puissant_path,
            ).exists()
        )
        self.character.msg.assert_called()

    def test_crossing_requires_declaration(self) -> None:
        """accept crossing path=<name> with no declaration text → error, offer untouched."""
        from world.conditions.models import ConditionTemplate
        from world.conditions.services import apply_condition

        audere_template = ConditionTemplate.objects.get(name=AUDERE_CONDITION_NAME)
        apply_condition(target=self.character, condition=audere_template)

        cmd = CmdAccept()
        cmd.caller = self.character
        cmd.args = f"crossing path={self.puissant_path.name}"
        cmd.raw_string = f"accept {cmd.args}"
        cmd.cmdname = "accept"
        cmd.func()

        # Offer untouched — error message delivered.
        self.assertTrue(
            PendingAudereMajoraOffer.objects.filter(character_sheet=self.sheet).exists()
        )
        self.character.msg.assert_called()
        call_args = self.character.msg.call_args[0][0]
        self.assertIn("declaration", call_args.lower())

    # ------------------------------------------------------------------
    # Listing paths (no-arg)
    # ------------------------------------------------------------------

    def test_accept_no_args_lists_pending_offers(self) -> None:
        """accept with no args shows registry-pending offers when any exist."""
        cmd = CmdAccept()
        cmd.caller = self.character
        cmd.args = ""
        cmd.raw_string = "accept"
        cmd.cmdname = "accept"
        cmd.func()

        self.character.msg.assert_called()
        text = self.character.msg.call_args[0][0]
        self.assertIn("surge", text.lower())

    def test_decline_no_args_lists_pending_offers(self) -> None:
        """decline with no args shows the same listing."""
        cmd = CmdDecline()
        cmd.caller = self.character
        cmd.args = ""
        cmd.raw_string = "decline"
        cmd.cmdname = "decline"
        cmd.func()

        self.character.msg.assert_called()
        text = self.character.msg.call_args[0][0]
        self.assertIn("surge", text.lower())

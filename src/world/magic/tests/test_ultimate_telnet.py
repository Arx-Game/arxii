"""accept ultimate <n> over telnet (#4098 decision 16)."""

from unittest.mock import MagicMock

from django.test import TestCase
from evennia.utils.idmapper import models as idmapper_models

from commands.consent import CmdAccept
from commands.exceptions import CommandError
from commands.tests.message_capture import message_text
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.covenants.constants import RoleArchetype
from world.magic.audere import SOULFRAY_CONDITION_NAME
from world.magic.constants import GiftKind
from world.magic.factories import (
    AudereThresholdFactory,
    CharacterAnimaFactory,
    CharacterGiftFactory,
    GiftFactory,
    IntensityTierFactory,
    KnownUltimateFactory,
    PathGiftGrantFactory,
    PendingAudereOfferFactory,
    ResonanceFactory,
    UltimateTechniqueFactory,
    wire_audere_power_multipliers,
)
from world.magic.models import KnownUltimate
from world.magic.tests.majora_fixtures import build_crossing_world
from world.mechanics.constants import EngagementType
from world.mechanics.engagement import CharacterEngagement
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
        self.grant = PathGiftGrantFactory(gift=gift)
        CharacterPathHistoryFactory(character=self.sheet, path=self.grant.path)
        self.known = UltimateTechniqueFactory(
            gift=gift, name="Ember Ward", archetype_alignment=RoleArchetype.SHIELD
        )
        self.hidden = UltimateTechniqueFactory(
            gift=gift, name="Cinder Crown", archetype_alignment=RoleArchetype.SWORD
        )
        self.grant.ultimate_techniques.add(self.known, self.hidden)
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

    def _bare_accept(self) -> str:
        """Prints the pending listing (the ``describe()`` path), priming the
        caller's ndb snapshot the same way a player reading the list would."""
        self.character.msg.reset_mock()
        return self._accept("")

    def _said(self) -> str:
        # A CommandError reaches func()'s except branch via two msg() calls: the
        # typed text line, then a kwargs-only ``command_error={...}`` frame with
        # no positional args (mirrors the guard in commands/tests/test_traps.py).
        return "\n".join(
            message_text(call.args[0]) for call in self.character.msg.call_args_list if call.args
        )

    def test_listing_numbers_known_and_undiscovered_without_raw_category(self) -> None:
        text = self._bare_accept()
        self.assertIn("1) Ember Ward (known)", text)
        self.assertIn("2) Edge (undiscovered)", text)
        self.assertNotIn("Cinder Crown", text)
        self.assertNotIn("Sword", text)

    def test_accept_number_reveals_and_readies(self) -> None:
        self._bare_accept()
        text = self._accept("ultimate 2")
        self.assertIn("Cinder Crown", text)
        known = KnownUltimate.objects.get(character=self.sheet, technique=self.hidden)
        self.assertTrue(known.readied)

    def test_out_of_range_number_refused(self) -> None:
        self._bare_accept()
        text = self._accept("ultimate 9")
        self.assertFalse(KnownUltimate.objects.filter(readied=True).exists())
        self.assertIn("accept ultimate", text)

    def test_non_numeric_choice_refused(self) -> None:
        self._bare_accept()
        text = self._accept("ultimate abc")
        self.assertFalse(KnownUltimate.objects.filter(readied=True).exists())
        self.assertIn("accept ultimate", text)

    # ------------------------------------------------------------------
    # Stale-listing guard (#4098 fix round 1)
    # ------------------------------------------------------------------

    def test_missing_snapshot_prints_listing_and_does_not_choose(self) -> None:
        """No prior listing printed (e.g. after a reconnect) -- never choose blind."""
        text = self._accept("ultimate 2")
        self.assertFalse(KnownUltimate.objects.filter(readied=True).exists())
        self.assertIn("1) Ember Ward (known)", text)
        self.assertIn("2) Edge (undiscovered)", text)
        self.assertIn("accept ultimate", text)

    def test_changed_list_blocks_choice_and_reprints(self) -> None:
        """The pools changed after the listing printed -- <n> must not choose blind."""
        self._bare_accept()
        # A new undiscovered ultimate appears between the listing and the choice --
        # flat_cards() now returns 3 entries instead of 2, so position 2 ("Edge") no
        # longer means what it meant when the player read the list.
        crown_hidden = UltimateTechniqueFactory(
            gift=self.known.gift, name="Dawn Crown", archetype_alignment=RoleArchetype.CROWN
        )
        self.grant.ultimate_techniques.add(crown_hidden)

        text = self._accept("ultimate 2")
        self.assertFalse(KnownUltimate.objects.filter(readied=True).exists())
        self.assertIn("changed", text.lower())
        self.assertIn("1) Ember Ward (known)", text)
        self.assertIn("2) Edge (undiscovered)", text)
        self.assertIn("3)", text)

        # The reprint stored a fresh snapshot -- the same number now resolves cleanly.
        text = self._accept("ultimate 2")
        self.assertIn("Cinder Crown", text)
        known = KnownUltimate.objects.get(character=self.sheet, technique=self.hidden)
        self.assertTrue(known.readied)

    def test_ultimate_reveal_closed_shows_user_message(self) -> None:
        """``choose_ultimate`` raising ``UltimateRevealClosed`` surfaces its
        ``user_message`` (the real-world trigger is a double-submit race: a second
        in-flight request's own internal re-check finds the reveal already closed
        after the first commits -- simulated here directly against the handler)."""
        from unittest.mock import patch

        from world.magic.exceptions import UltimateRevealClosed
        from world.magic.offer_handlers import UltimateRevealHandler
        from world.magic.services.ultimates import ultimate_reveal_for

        self._bare_accept()
        offer = ultimate_reveal_for(self.sheet)
        handler = UltimateRevealHandler()

        with (
            patch(
                "world.magic.services.ultimates.choose_ultimate",
                side_effect=UltimateRevealClosed(),
            ),
            self.assertRaises(CommandError) as ctx,
        ):
            handler.accept(offer, self.character, "2")
        self.assertEqual(str(ctx.exception), "There is no ultimate to choose right now.")
        self.assertFalse(KnownUltimate.objects.filter(readied=True).exists())


class UltimateRevealAppendedToSurgeAcceptTests(TestCase):
    """``accept surge`` appends the reveal listing when ultimates are available
    (#4098 fix round 1 -- the e2e suite only checked that ``msg`` was called)."""

    def setUp(self) -> None:
        idmapper_models.flush_cache()
        wire_audere_power_multipliers()

        intensity_tier = IntensityTierFactory(threshold=10, control_modifier=0)
        soulfray_template = ConditionTemplateFactory(
            name=SOULFRAY_CONDITION_NAME, has_progression=True
        )
        soulfray_stage = ConditionStageFactory(condition=soulfray_template, stage_order=2)
        self.threshold = AudereThresholdFactory(
            minimum_intensity_tier=intensity_tier,
            minimum_warp_stage=soulfray_stage,
            sword_reveal_label="Edge",
            reveal_framing_text="PLACEHOLDER framing",
        )

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
        ConditionInstanceFactory(
            target=self.character, condition=soulfray_template, current_stage=soulfray_stage
        )
        CharacterAnimaFactory(character=self.sheet, current=50, maximum=50)

        # No Audere condition yet -- accepting the surge is what applies it, and
        # the reveal only opens once it is (gate 5 of check_audere_eligibility).
        self.offer = PendingAudereOfferFactory(
            character_sheet=self.sheet, fired_intensity=20, soulfray_stage_order=2
        )

    def test_accept_surge_appends_ultimate_reveal(self) -> None:
        cmd = CmdAccept()
        cmd.caller = self.character
        cmd.args = "surge"
        cmd.raw_string = "accept surge"
        cmd.cmdname = "accept"
        cmd.func()
        text = "\n".join(
            message_text(call.args[0]) for call in self.character.msg.call_args_list if call.args
        )
        self.assertIn("The surge takes hold", text)
        self.assertIn("PLACEHOLDER framing", text)
        self.assertIn("Ultimates:", text)
        self.assertIn("1) Ember Ward (known)", text)
        self.assertIn("2) Edge (undiscovered)", text)
        self.assertIn("Choose with: accept ultimate <number>", text)
        self.assertNotIn("Cinder Crown", text)
        self.assertNotIn("Sword", text)


class UltimateRevealAppendedToCrossingAcceptTests(TestCase):
    """``accept crossing`` appends the reveal listing, reading the new Path's
    ultimates after the Crossing switches the character onto it (#4098 fix round 1)."""

    def setUp(self) -> None:
        idmapper_models.flush_cache()
        wire_audere_power_multipliers()

        (
            self.character,
            self.sheet,
            self.majora_threshold,
            self.prospect_path,
            self.puissant_path,
            self.majora_offer,
        ) = build_crossing_world(boundary_level=5, suffix="ultfix1")

        # build_crossing_world's engagement is CHALLENGE; ultimate_reveal_for requires
        # COMBAT specifically. SharedMemoryModel: no bulk .update() (sharedmemory-model
        # skill) -- fetch, mutate, save so the idmapper-cached instance stays correct.
        engagement = CharacterEngagement.objects.get(character=self.sheet)
        engagement.engagement_type = EngagementType.COMBAT
        engagement.save(update_fields=["engagement_type"])

        # This AudereThreshold row is read only for its reveal labels/framing text --
        # the surge-eligibility gates it also carries are irrelevant to a Majora
        # crossing. Pin tier/stage explicitly: the bare SubFactory defaults collide
        # with build_crossing_world's own IntensityTier threshold=10 (unique column).
        AudereThresholdFactory(
            minimum_intensity_tier=IntensityTierFactory(threshold=999),
            minimum_warp_stage=ConditionStageFactory(stage_order=1),
            sword_reveal_label="Edge",
            reveal_framing_text="PLACEHOLDER framing",
        )

        gift = GiftFactory(kind=GiftKind.MAJOR)
        # A non-empty supported resonance set -- grant_path_magic (via cross_into_path)
        # always (re-)resolves a resonance to provision the gift's latent thread, even
        # for an already-held gift; an empty set with no existing thread/claim raises
        # GiftResonanceUnresolvable.
        gift.resonances.add(ResonanceFactory())
        CharacterGiftFactory(character=self.sheet, gift=gift)
        # Granted on the DESTINATION path -- cross_into_path's grant_path_magic mints
        # the CharacterGift/thread for the puissant path once the crossing lands.
        grant = PathGiftGrantFactory(path=self.puissant_path, gift=gift)
        self.known = UltimateTechniqueFactory(
            gift=gift, name="Ember Ward", archetype_alignment=RoleArchetype.SHIELD
        )
        self.hidden = UltimateTechniqueFactory(
            gift=gift, name="Cinder Crown", archetype_alignment=RoleArchetype.SWORD
        )
        grant.ultimate_techniques.add(self.known, self.hidden)
        KnownUltimateFactory(character=self.sheet, technique=self.known)

        from world.conditions.models import ConditionTemplate
        from world.conditions.services import apply_condition
        from world.magic.audere import AUDERE_CONDITION_NAME

        audere_template = ConditionTemplate.objects.get(name=AUDERE_CONDITION_NAME)
        apply_condition(target=self.character, condition=audere_template)

        self.character.msg = MagicMock()

    def test_accept_crossing_appends_ultimate_reveal_for_new_path(self) -> None:
        declaration = "I have walked the long road to this moment and I step forward now."
        cmd = CmdAccept()
        cmd.caller = self.character
        cmd.args = f"crossing path={self.puissant_path.name} declaration={declaration}"
        cmd.raw_string = f"accept {cmd.args}"
        cmd.cmdname = "accept"
        cmd.func()
        text = "\n".join(
            message_text(call.args[0]) for call in self.character.msg.call_args_list if call.args
        )
        self.assertIn(f"You cross into {self.puissant_path.name}", text)
        self.assertIn("PLACEHOLDER framing", text)
        self.assertIn("Ultimates:", text)
        self.assertIn("1) Ember Ward (known)", text)
        self.assertIn("2) Edge (undiscovered)", text)
        self.assertIn("Choose with: accept ultimate <number>", text)
        self.assertNotIn("Cinder Crown", text)
        self.assertNotIn("Sword", text)

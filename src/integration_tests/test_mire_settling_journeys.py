"""Journeys through settling the Mire: Absolve, Condemn, Succumb, atoning and the fall (#5177).

Corvin is a Sineater carrying Ruin (Abyssal) corruption for Ysmay; Hobb is the other player in
the room and sees only the poses; Marrow is an NPC Sineater run by Gideon, a GM. A Sineater
settles what they carry by writing a pose or a journal entry that reflects on "the Mire you
carry for <Sinner>" and choosing Absolve, Condemn or Succumb, then performing the rite of
settling.

Everything the numbers depend on is the starting value staff set, the seeded conversion rows,
and the rite's share, which each journey pins by authoring the Success tier's share and forcing
that roll. Expected numbers are worked out by hand in each journey, not read from the code:

* Purify reward 50%; each tie step 5 (scaled by the share and rounded); succumb bonus 200%;
  jackpot 25%; fall payout 300%, with the most recent Sinner earning 50% more on top.
* A disowned deed turns 75% of itself at the share; Abyssal into Primal converts at 0.70.
"""

from __future__ import annotations

from decimal import Decimal

from evennia.utils.ansi import strip_ansi

from evennia_extensions.factories import CharacterFactory
from integration_tests.test_sineating_journeys import SineatingJourneyCase, balance, corruption
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.services.materialize import materialize_item_game_object
from world.magic.constants import GainSource
from world.magic.factories import (
    CharacterResonanceFactory,
    DriftCorrectionRiteFactory,
    ResonanceTierFactory,
)
from world.magic.models import (
    DriftCorrectionOutcomeShare,
    MireHolding,
    Reflection,
    ResonanceGrant,
)
from world.magic.models.aura import CharacterResonance
from world.magic.services.drift import get_drift_correction_config
from world.relationships.models import CharacterRelationship
from world.scenes.models import Interaction

BURDEN_POSE = "bows their head over the weight and decides."
BURDEN_ENTRY = "title=The weight body=I weighed it and chose."


class MireJourneyCase(SineatingJourneyCase):
    """Corvin carries 108 Ruin for Ysmay; the rite of settling is set up, at a share of 0.75."""

    def setUp(self) -> None:
        super().setUp()
        config = get_drift_correction_config()
        config.rite = DriftCorrectionRiteFactory()
        config.check_type = CheckTypeFactory()
        config.check_difficulty_level = 0
        config.save()
        for name in self.outcomes:
            self.share(name, "1.00")
        self.share("Success", "0.75")
        # Corvin's Tide stands at 500 lifetime, so a little Ruin never makes him a fallen
        # Sineater unless a journey sets out to.
        tide_row = CharacterResonance.objects.get(
            character_sheet=self.corvin.sheet_data, resonance=self.primal
        )
        tide_row.lifetime_earned = 500
        tide_row.save(update_fields=["lifetime_earned"])
        self.ysmay_side = CharacterRelationship.objects.get(
            source=self.corvin.sheet_data, target=self.ysmay.sheet_data
        )
        self.carry_for(self.ysmay_side, 108)

    @staticmethod
    def share(tier: str, share: str) -> None:
        from world.traits.services import ensure_canonical_check_outcome

        DriftCorrectionOutcomeShare.objects.update_or_create(
            outcome_tier=ensure_canonical_check_outcome(tier),
            defaults={"converted_share": Decimal(share)},
        )

    def carry_for(self, side, amount: int, **counters: int) -> MireHolding:
        """The Sineater behind ``side`` carries ``amount`` Ruin for the Sinner it points at."""
        row, _ = CharacterResonance.objects.get_or_create(
            character_sheet=side.source, resonance=self.ruin
        )
        row.corruption_current += amount
        row.save(update_fields=["corruption_current"])
        return MireHolding.objects.create(
            relationship=side, resonance=self.ruin, amount=amount, **counters
        )

    def offering(self, character, name: str) -> str:
        """Put a Tide-tied item, which pays for the Sineater's rite, in their hands."""
        template = ItemTemplateFactory(
            name=name, tied_resonance=self.primal, resonance_tier=ResonanceTierFactory()
        )
        item = ItemInstanceFactory(template=template, holder_character_sheet=character.sheet_data)
        materialize_item_game_object(item, character.sheet_data)
        return name

    def settle(self, character, offering: str, tier: str = "Success") -> str:
        with force_check_outcome(self.outcomes[tier]):
            return strip_ansi(self.telnet(character, f"aura settle {offering}"))

    def gauges(self, side) -> tuple[int, int]:
        side = CharacterRelationship.objects.get(pk=side.pk)
        return side.affection, side.conflict

    def holding(self) -> MireHolding:
        return MireHolding.objects.get(relationship=self.ysmay_side)


class AbsolvingByJournalEntry(MireJourneyCase):
    def test_absolving_clears_part_of_it_and_rewards_corvin_in_two_rites(self) -> None:
        listed = self.telnet(self.corvin, "reflect")
        self.assertIn("mire:Ysmay", listed)
        self.assertIn("The Mire you carry for Ysmay", listed)
        affection, _ = self.gauges(self.ysmay_side)
        tide = balance(self.corvin, self.primal)

        told = self.telnet(self.corvin, f"journal/reflect mire:Ysmay=absolve {BURDEN_ENTRY}")

        self.assertIn(
            "Your reflection on the Mire you carry for Ysmay is recorded: you will absolve it.",
            told,
        )
        self.assertNotTold(self.hobb, "absolve")
        self.assertEqual(self.holding().amount, 108)  # recording changes nothing

        self.offering(self.corvin, "Tide Thread")
        told = self.settle(self.corvin, "Tide Thread")

        # Share 0.75: floor(108 x 0.75) = 81 clears, 27 is left. The reward is
        # floor(81 x 50 / 100) = 40 Tide, the tie gains round(5 x 0.75) = 4 affection, and the
        # jackpot for this tether is 81.
        self.assertIn("You absolve the Mire you carry for Ysmay: 81 of it clears.", told)
        self.assertIn("Your Tide grows by 40.", told)
        self.assertEqual(self.holding().amount, 27)
        self.assertEqual(self.holding().purified_since_payout, 81)
        self.assertEqual(corruption(self.corvin, self.ruin), 27)
        self.assertEqual(balance(self.corvin, self.primal) - tide, 40)
        self.assertEqual(self.gauges(self.ysmay_side)[0] - affection, 4)

        # The 27 left, settled the same way: floor(27 x 0.75) = 20 clears and the reward is
        # floor(20 x 50 / 100) = 10.
        self.telnet(self.corvin, f"journal/reflect mire:Ysmay=absolve {BURDEN_ENTRY}")
        self.offering(self.corvin, "Second Thread")
        told = self.settle(self.corvin, "Second Thread")
        self.assertIn("20 of it clears.", told)
        self.assertIn("Your Tide grows by 10.", told)
        self.assertEqual(self.holding().amount, 7)
        self.assertEqual(balance(self.corvin, self.primal) - tide, 50)


class CondemningByPose(MireJourneyCase):
    def test_condemning_raises_conflict_and_the_others_present_read_only_the_pose(self) -> None:
        affection, conflict = self.gauges(self.ysmay_side)

        told = self.telnet(self.corvin, f"pose/reflect mire:ysmay=condemn {BURDEN_POSE}")

        self.assertIn("you will condemn it", told)
        self.assertTold(self.hobb, BURDEN_POSE)
        for private in ("reflect", "condemn", "recorded", "the Mire you carry"):
            self.assertNotTold(self.hobb, private)
        self.assertEqual(Reflection.objects.get().interaction.content, BURDEN_POSE)

        self.offering(self.corvin, "Tide Thread")
        told = self.settle(self.corvin, "Tide Thread")

        # floor(108 x 0.75) = 81 clears; conflict gains round(5 x 0.75) = 4, affection nothing.
        self.assertIn("You condemn the Mire you carry for Ysmay: 81 of it clears.", told)
        after = self.gauges(self.ysmay_side)
        self.assertEqual((after[0] - affection, after[1] - conflict), (0, 4))

    def test_a_choice_that_does_not_fit_a_burden_is_refused_before_the_pose_posts(self) -> None:
        told = self.telnet(self.corvin, f"pose/reflect mire:Ysmay=embrace {BURDEN_POSE}")

        self.assertIn("Say whether you absolve, condemn or succumb to it.", told)
        self.assertNotTold(self.hobb, BURDEN_POSE)
        self.assertFalse(Interaction.objects.filter(content=BURDEN_POSE).exists())


class SuccumbingAndAtoningForIt(MireJourneyCase):
    def test_succumbing_pays_ysmay_and_becomes_a_deed_corvin_disowns(self) -> None:
        holding = self.holding()
        holding.amount = 100
        holding.purified_since_payout = 400
        holding.save(update_fields=["amount", "purified_since_payout"])
        row = CharacterResonance.objects.get(
            character_sheet=self.corvin.sheet_data, resonance=self.ruin
        )
        row.corruption_current = 100
        row.save(update_fields=["corruption_current"])
        self.share("Success", "1.00")
        affection, conflict = self.gauges(self.ysmay_side)
        ysmay_ruin = balance(self.ysmay, self.ruin)
        self.offering(self.corvin, "Tide Thread")
        self.telnet(self.corvin, f"pose/reflect mire:Ysmay=succumb {BURDEN_POSE}")

        told = self.settle(self.corvin, "Tide Thread")

        # All 100 leaves the Mire and becomes Ruin in Corvin's aura. Ysmay earns
        # 100 x 200 / 100 + 400 x 25 / 100 = 300 Ruin (her thread's), the jackpot resets to 0,
        # and both gauges rise by round(5 x 1.00) = 5.
        self.assertIn(
            "You succumb to the Mire you carry for Ysmay: 100 Ruin becomes part of you.", told
        )
        self.assertEqual(self.holding().amount, 0)
        self.assertEqual(self.holding().purified_since_payout, 0)
        self.assertEqual(corruption(self.corvin, self.ruin), 0)
        self.assertEqual(balance(self.ysmay, self.ruin) - ysmay_ruin, 300)
        after = self.gauges(self.ysmay_side)
        self.assertEqual((after[0] - affection, after[1] - conflict), (5, 5))
        self.assertTold(self.ysmay, "Corvin has succumbed to what they carried for you.")
        self.assertTold(self.ysmay, "Your Ruin grows by 300.")
        for private in ("succumbed", "grows by", "Mire"):
            self.assertNotTold(self.hobb, private)
        deed = ResonanceGrant.objects.get(source=GainSource.SUCCUMBED)
        self.assertEqual((deed.amount, deed.resonance), (100, self.ruin))

        # The succumbing is a deed Corvin can reflect on, named by the pose it was written in.
        listed = strip_ansi(self.telnet(self.corvin, "reflect"))
        self.assertIn(
            f"#{deed.pk} Succumbing to the Mire you carried for Ysmay, in your pose at The Lantern",
            listed,
        )

        # He disowns it by journal entry and settles again at 0.75: int(100 x 75 / 100 x
        # 0.75) = 56 Ruin turns toward his main affinity (Primal) at the Redemption rate for
        # Abyssal into Primal, 0.70, which is int(56 x 0.70) = 39 Tide.
        self.share("Success", "0.75")
        self.telnet(self.corvin, f"journal/reflect {deed.pk}=disown {BURDEN_ENTRY}")
        self.offering(self.corvin, "Second Thread")
        tide = balance(self.corvin, self.primal)
        told = self.settle(self.corvin, "Second Thread")
        self.assertIn("56 Ruin became 39 Tide.", told)
        self.assertEqual(balance(self.corvin, self.primal) - tide, 39)
        # Ysmay keeps the payout: nothing was taken back from her.
        self.assertEqual(balance(self.ysmay, self.ruin) - ysmay_ruin, 300)
        self.assertEqual(self.holding().purified_since_payout, 0)


class TheFall(MireJourneyCase):
    def test_a_fall_pays_both_sinners_and_refuses_the_next_plea(self) -> None:
        brindle = self.make_player("Brindle", room=self.lantern)
        self.watch(brindle)
        self.connect_telnet(brindle)
        self.aura(brindle, abyssal="80")
        CharacterResonanceFactory(character_sheet=brindle.sheet_data, resonance=self.ruin)
        self.tether(brindle, self.corvin)
        brindle_side = CharacterRelationship.objects.get(
            source=self.corvin.sheet_data, target=brindle.sheet_data
        )
        # Corvin has succumbed to 300 for Ysmay and 100 for Brindle since his last fall, and
        # now succumbs to the 100 Brindle's Mire still holds. His Tide stands at 50 lifetime,
        # so 100 Ruin makes his aura predominantly Abyssal.
        tide_row = CharacterResonance.objects.get(
            character_sheet=self.corvin.sheet_data, resonance=self.primal
        )
        tide_row.lifetime_earned = 50
        tide_row.save(update_fields=["lifetime_earned"])
        ysmay_holding = self.holding()
        ysmay_holding.amount = 0
        ysmay_holding.succumbed_since_fall = 300
        ysmay_holding.save(update_fields=["amount", "succumbed_since_fall"])
        row = CharacterResonance.objects.get(
            character_sheet=self.corvin.sheet_data, resonance=self.ruin
        )
        row.corruption_current = 0
        row.save(update_fields=["corruption_current"])
        brindle_holding = self.carry_for(brindle_side, 100, succumbed_since_fall=100)
        self.share("Success", "1.00")
        ysmay_ruin = balance(self.ysmay, self.ruin)
        brindle_ruin = balance(brindle, self.ruin)
        self.offering(self.corvin, "Tide Thread")
        self.telnet(self.corvin, f"pose/reflect mire:Brindle=succumb {BURDEN_POSE}")

        told = self.settle(self.corvin, "Tide Thread")

        # Ysmay: 300 x 300 / 100 = 900. Brindle: (100 + 100) x 300 / 100 = 600, and 600 x 50 /
        # 100 = 300 more for being the last Sinner succumbed to, 900 in all, on top of his
        # succumb bonus of 100 x 200 / 100 = 200.
        self.assertIn("you have fallen", told)
        self.assertEqual(balance(self.ysmay, self.ruin) - ysmay_ruin, 900)
        self.assertEqual(balance(brindle, self.ruin) - brindle_ruin, 200 + 900)
        self.assertTold(self.ysmay, "Corvin has fallen to the Abyss. Your Ruin grows by 900.")
        self.assertTold(brindle, "Corvin has fallen to the Abyss. Your Ruin grows by 900.")
        for holding in (ysmay_holding, brindle_holding):
            holding.refresh_from_db()
            self.assertEqual(holding.succumbed_since_fall, 0)

        told = self.entreat()
        self.assertIn("Corvin has fallen too far into the Abyss to carry anyone's sins.", told)


class AnNpcSineaterSettlesTheMire(MireJourneyCase):
    def test_the_gm_reflects_as_the_npc_by_pose_and_absolves(self) -> None:
        marrow = CharacterFactory(db_key="Marrow", location=self.lantern)
        CharacterSheetFactory(character=marrow)
        marrow.db_account = self.account_of(self.gideon)
        marrow.save()
        self.watch(marrow)
        self.aura(marrow, primal="80")
        CharacterResonanceFactory(character_sheet=marrow.sheet_data, resonance=self.primal)
        self.tether(self.ysmay, marrow)
        side = CharacterRelationship.objects.get(
            source=marrow.sheet_data, target=self.ysmay.sheet_data
        )
        holding = self.carry_for(side, 108)
        self.offering(marrow, "Tide Thread")
        tide = balance(marrow, self.primal)

        told = self.telnet(marrow, f"pose/reflect mire:Ysmay=absolve {BURDEN_POSE}")
        self.assertIn("you will absolve it", told)
        told = self.settle(marrow, "Tide Thread")

        # The same numbers as for a player's Sineater: 81 clears and 40 Tide is earned.
        self.assertIn("You absolve the Mire you carry for Ysmay: 81 of it clears.", told)
        holding.refresh_from_db()
        self.assertEqual((holding.amount, holding.purified_since_payout), (27, 81))
        self.assertEqual(balance(marrow, self.primal) - tide, 40)

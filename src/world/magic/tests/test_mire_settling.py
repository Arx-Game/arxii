"""Settling the Mire at the rite of settling: Absolve, Condemn, Succumb and the fall (#5177).

These run on the SQLite tier, where the journeys (Postgres only) cannot, so the arithmetic is
proved before CI. Every expected number is worked out by hand from the starting values staff
set and the spec's traces, never read back from the code:

* Starting sizes: purify reward 50%, each tie step 5, succumb bonus 200%, jackpot 25%, fall
  payout 300%, fall breaker bonus 50%.
* Corvin is the Sineater (Primal aura, a Tide thread); Ysmay and Brindle are his Sinners
  (their tether's resonance is Ruin, Abyssal).
* The rite's share is pinned by setting the Success tier's share and forcing that outcome.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase, override_settings

from actions.definitions.drift_correction import PerformSettlingRiteAction
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.journals.factories import JournalEntryFactory
from world.magic.constants import GainSource, ReflectionChoice, TargetKind
from world.magic.exceptions import ReflectionError, SineaterFallenError
from world.magic.factories import (
    CharacterAuraFactory,
    CharacterResonanceFactory,
    CharacterThreadWeavingUnlockFactory,
    DriftCorrectionRiteFactory,
    ResonanceFactory,
    ResonanceTierFactory,
    ThreadWeavingUnlockFactory,
    ensure_conversion_pairs,
    set_aura_split,
    wire_soul_tether_content,
)
from world.magic.models import (
    CharacterResonance,
    DriftCorrectionOutcomeShare,
    MireHolding,
    Reflection,
    ResonanceGrant,
)
from world.magic.services.drift import drift_for, get_drift_correction_config
from world.magic.services.drift_correction import perform_settling_rite
from world.magic.services.reflection import (
    deed_label,
    pending_reflection_from,
    record_reflection,
    reflectable_for,
)
from world.magic.services.settling_preview import settling_rite_reading
from world.magic.services.sineating import request_sineating
from world.magic.services.soul_tether import accept_soul_tether
from world.magic.types.soul_tether import SoulTetherRole
from world.narrative.models import NarrativeMessageDelivery
from world.relationships.factories import CharacterRelationshipFactory, RelationshipTypeFactory
from world.relationships.models import CharacterRelationship
from world.roster.factories import RosterTenureFactory
from world.seeds.modifier_values import seed_pool_and_cap_lanes
from world.traits.constants import CANONICAL_OUTCOME_LEVELS
from world.traits.services import ensure_canonical_check_outcome


def _name(sheet) -> str:
    return sheet.primary_persona.name


def _row(sheet, resonance) -> CharacterResonance:
    return CharacterResonance.objects.get(character_sheet=sheet, resonance=resonance)


def _balance(sheet, resonance) -> int:
    row = CharacterResonance.objects.filter(character_sheet=sheet, resonance=resonance).first()
    return row.balance if row is not None else 0


@override_settings(SEED_SAMPLE_CONTENT=True)
class MireSettlingCase(TestCase):
    """Corvin carries Ruin for Ysmay, and may settle it with a rite at a share of 0.75."""

    def setUp(self) -> None:
        super().setUp()
        seed_pool_and_cap_lanes()
        wire_soul_tether_content()
        self.celestial, self.primal_affinity, self.abyssal = ensure_conversion_pairs()
        self.ruin = ResonanceFactory(name="Ruin", affinity=self.abyssal)
        self.tide = ResonanceFactory(name="Tide", affinity=self.primal_affinity)
        self.sineater = RosterTenureFactory().roster_entry.character_sheet
        CharacterAuraFactory(character=self.sineater)
        set_aura_split(self.sineater.aura, celestial="10", primal="80", abyssal="10")
        CharacterResonanceFactory(
            character_sheet=self.sineater, resonance=self.tide, lifetime_earned=500
        )
        self.ysmay, self.ysmay_side = self.sinner_of_corvin()

        config = get_drift_correction_config()
        config.rite = DriftCorrectionRiteFactory()
        config.check_type = CheckTypeFactory()
        config.check_difficulty_level = 0
        config.save()
        self.outcomes = {
            name: ensure_canonical_check_outcome(name) for name in CANONICAL_OUTCOME_LEVELS
        }
        for name in CANONICAL_OUTCOME_LEVELS:
            self.set_share(name, "1.00")
        self.set_share("Success", "0.75")

    # -- building ---------------------------------------------------------------

    def sinner_of_corvin(self):
        """A Sinner tethered to Corvin: the Sinner's sheet and Corvin's side toward them."""
        sinner = RosterTenureFactory().roster_entry.character_sheet
        CharacterAuraFactory(character=sinner)
        set_aura_split(sinner.aura, celestial="10", primal="10", abyssal="80")
        CharacterResonanceFactory(character_sheet=sinner, resonance=self.ruin)
        unlock = ThreadWeavingUnlockFactory(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            unlock_type=RelationshipTypeFactory(),
            unlock_trait=None,
        )
        CharacterThreadWeavingUnlockFactory(character=sinner, unlock=unlock)
        CharacterRelationshipFactory(source=sinner, target=self.sineater)
        CharacterRelationshipFactory(source=self.sineater, target=sinner)
        accept_soul_tether(
            initiator_sheet=sinner,
            partner_sheet=self.sineater,
            sinner_role=SoulTetherRole.SINNER,
            resonance=self.ruin,
            ritual_components=[],
            sineater_resonance=self.tide,
        )
        side = CharacterRelationship.objects.get(source=self.sineater, target=sinner)
        return sinner, side

    def set_share(self, tier: str, share: str) -> None:
        DriftCorrectionOutcomeShare.objects.update_or_create(
            outcome_tier=self.outcomes[tier], defaults={"converted_share": Decimal(share)}
        )

    def carry(
        self, side, amount: int, *, purified_since_payout: int = 0, succumbed_since_fall: int = 0
    ) -> MireHolding:
        """Corvin carries ``amount`` Ruin for the Sinner behind ``side``, with the tether's
        jackpot and fall counters (which live on the side, not on the holding) set."""
        row, _ = CharacterResonance.objects.get_or_create(
            character_sheet=self.sineater, resonance=self.ruin
        )
        row.corruption_current += amount
        row.save(update_fields=["corruption_current"])
        side.mire_purified_since_payout = purified_since_payout
        side.mire_succumbed_since_fall = succumbed_since_fall
        side.save(update_fields=["mire_purified_since_payout", "mire_succumbed_since_fall"])
        return MireHolding.objects.create(relationship=side, resonance=self.ruin, amount=amount)

    def reflect(self, side, choice: str):
        entry = JournalEntryFactory(author=self.sineater)
        return record_reflection(self.sineater, writing=entry, tether=side, choice=choice)

    def offering(self):
        template = ItemTemplateFactory(
            tied_resonance=self.tide, resonance_tier=ResonanceTierFactory()
        )
        return ItemInstanceFactory(template=template)

    def settle(self, tier: str = "Success"):
        with force_check_outcome(self.outcomes[tier]):
            return perform_settling_rite(self.sineater, components=[self.offering()])

    def side(self) -> CharacterRelationship:
        return CharacterRelationship.objects.get(pk=self.ysmay_side.pk)


class SinnerNoticesAreStored(MireSettlingCase):
    """A Sinner paid at the rite may be offline: the notice is a stored message they read at
    login, not a line sent to a session nobody holds."""

    def test_an_offline_sinner_has_a_stored_delivery_for_the_succumb_payout(self) -> None:
        self.carry(self.ysmay_side, 100)
        self.reflect(self.ysmay_side, ReflectionChoice.SUCCUMB)
        template = ItemTemplateFactory(
            tied_resonance=self.tide, resonance_tier=ResonanceTierFactory()
        )
        offering = ItemInstanceFactory(template=template, holder_character_sheet=self.sineater)

        with (
            force_check_outcome(self.outcomes["Success"]),
            self.captureOnCommitCallbacks(execute=True),
        ):
            result = PerformSettlingRiteAction().run(
                actor=self.sineater.character, components_provided=[offering]
            )

        self.assertTrue(result.success, result.message)
        delivery = NarrativeMessageDelivery.objects.get(recipient_character_sheet=self.ysmay)
        self.assertIsNone(delivery.delivered_at)
        self.assertTrue(
            delivery.message.body.startswith(
                f"{_name(self.sineater)} has succumbed to what they carried for you."
            )
        )


class AbsolvingAndCondemningTheMire(MireSettlingCase):
    def test_absolving_in_two_rites_clears_and_rewards_by_hand_worked_numbers(self) -> None:
        holding = self.carry(self.ysmay_side, 108)
        affection_before = self.side().affection
        self.reflect(self.ysmay_side, ReflectionChoice.ABSOLVE)

        result = self.settle()

        # floor(108 x 0.75) = 81 clears; 27 is left. The reward is floor(81 x 50 / 100) = 40 of
        # Corvin's own thread's resonance (Tide), the tie gains round(5 x 0.75) = 4 affection,
        # and 81 is now the jackpot for this tether.
        holding.refresh_from_db()
        self.assertEqual((holding.amount, self.side().mire_purified_since_payout), (27, 81))
        self.assertEqual(_row(self.sineater, self.ruin).corruption_current, 27)
        self.assertEqual(_balance(self.sineater, self.tide), 40)
        self.assertEqual(self.side().affection - affection_before, 4)
        ysmay = _name(self.ysmay)
        self.assertEqual(
            result.lines,
            (
                f"You absolve the Mire you carry for {ysmay}: 81 of it clears. "
                "Your Tide grows by 40.",
            ),
        )
        self.assertEqual(ResonanceGrant.objects.get(source=GainSource.MIRE_PURIFIED).amount, 40)

        # The other 27 settled later at the same share: floor(27 x 0.75) = 20 clears and the
        # reward is floor(20 x 50 / 100) = 10, which brings the jackpot to 101.
        self.reflect(self.ysmay_side, ReflectionChoice.ABSOLVE)
        self.settle()
        holding.refresh_from_db()
        self.assertEqual((holding.amount, self.side().mire_purified_since_payout), (7, 101))
        self.assertEqual(_balance(self.sineater, self.tide), 50)

    def test_the_line_says_what_the_ledger_recorded_at_a_non_100_earn_rate(self) -> None:
        self.carry(self.ysmay_side, 108)
        self.reflect(self.ysmay_side, ReflectionChoice.ABSOLVE)

        # The reward of 40 is earned in Tide at its affinity's 150%, so 60 grows, and the line must
        # say 60.
        self.primal_affinity.earn_rate_percent = 150
        self.primal_affinity.save()
        result = self.settle()

        self.assertIn("Your Tide grows by 60.", result.lines[0])
        self.assertEqual(ResonanceGrant.objects.get(source=GainSource.MIRE_PURIFIED).amount, 60)
        self.assertEqual(_balance(self.sineater, self.tide), 60)

    def test_condemning_raises_conflict_not_affection(self) -> None:
        self.carry(self.ysmay_side, 100)
        before = self.side()
        affection, conflict = before.affection, before.conflict
        self.reflect(self.ysmay_side, ReflectionChoice.CONDEMN)

        result = self.settle()

        # floor(100 x 0.75) = 75 clears, the reward is floor(75 x 50 / 100) = 37, and the
        # conflict gains round(5 x 0.75) = 4.
        after = self.side()
        self.assertEqual((after.affection - affection, after.conflict - conflict), (0, 4))
        self.assertEqual(_balance(self.sineater, self.tide), 37)
        self.assertIn("You condemn the Mire you carry for", result.lines[0])
        self.assertIn("75 of it clears.", result.lines[0])

    def test_a_share_of_nothing_moves_and_pays_nothing(self) -> None:
        holding = self.carry(self.ysmay_side, 100)
        self.set_share("Success", "0.00")
        self.reflect(self.ysmay_side, ReflectionChoice.ABSOLVE)

        result = self.settle()

        holding.refresh_from_db()
        self.assertEqual((holding.amount, self.side().mire_purified_since_payout), (100, 0))
        self.assertEqual(_balance(self.sineater, self.tide), 0)
        self.assertIn("but the rite carries none of it through.", result.lines[0])
        self.assertEqual(Reflection.objects.filter(rite__isnull=True).count(), 0)


class SuccumbingToTheMire(MireSettlingCase):
    def test_a_sineater_is_unsettled_only_once_a_succumbing_puts_the_resonance_in_their_aura(
        self,
    ) -> None:
        self.carry(self.ysmay_side, 100)
        self.assertEqual(drift_for(self.sineater).steps_past, 0)

        self.set_share("Success", "1.00")
        self.reflect(self.ysmay_side, ReflectionChoice.SUCCUMB)
        self.settle()

        # 100 Ruin is now 100 of Corvin's 600 lifetime: 16.67 percent Abyssal, against a
        # settled share of 10 and a range of 5. That is 1.67 past, which is one step of 5.
        reading = drift_for(self.sineater)
        self.assertEqual(reading.steps_past, 1)
        self.assertEqual(reading.leading_excess_resonance, self.ruin)

    def test_succumbing_pays_the_jackpot_and_becomes_a_deed_to_atone_for(self) -> None:
        holding = self.carry(self.ysmay_side, 100, purified_since_payout=400)
        before = self.side()
        affection, conflict = before.affection, before.conflict
        self.set_share("Success", "1.00")
        reflection = self.reflect(self.ysmay_side, ReflectionChoice.SUCCUMB)
        ruin_lifetime = _row(self.sineater, self.ruin).lifetime_earned

        result = self.settle()

        # All 100 leaves the Mire and becomes Ruin in Corvin's aura. Ysmay earns
        # 100 x 200 / 100 + 400 x 25 / 100 = 300 in Ruin (her thread's), the jackpot resets,
        # and both gauges rise by 5.
        holding.refresh_from_db()
        side = self.side()
        self.assertEqual(
            (holding.amount, side.mire_purified_since_payout, side.mire_succumbed_since_fall),
            (0, 0, 100),
        )
        self.assertEqual(_row(self.sineater, self.ruin).lifetime_earned - ruin_lifetime, 100)
        self.assertEqual(_balance(self.ysmay, self.ruin), 300)
        after = self.side()
        self.assertEqual((after.affection - affection, after.conflict - conflict), (5, 5))
        succumbed = ResonanceGrant.objects.get(source=GainSource.SUCCUMBED)
        self.assertEqual(
            (succumbed.amount, succumbed.resonance, succumbed.source_reflection),
            (100, self.ruin, reflection),
        )
        self.assertEqual(
            result.lines,
            (
                f"You succumb to the Mire you carry for {_name(self.ysmay)}: "
                "100 Ruin becomes part of you.",
            ),
        )
        (notice,) = result.notices
        self.assertEqual(notice.sheet, self.ysmay)
        self.assertEqual(
            notice.line,
            f"{_name(self.sineater)} has succumbed to what they carried for you. "
            "Your Ruin grows by 300.",
        )

        # The succumbing is a deed Corvin can reflect on, named by where he did it.
        (deed,) = reflectable_for(self.sineater).deeds
        self.assertEqual(deed.grant, succumbed)
        self.assertEqual(
            deed_label(succumbed).split(" · ")[0],
            f"Succumbing to the Mire you carried for {_name(self.ysmay)}, "
            f"in your journal entry of {reflection.journal_entry.created_at:%-d %B}",
        )
        self.assertEqual(deed_label(succumbed).split(" · ")[1], "100 Ruin")

        # He disowns it and settles again at 0.75. A disowned deed turns
        # int(100 x 75 / 100 x 0.75) = 56 Ruin toward his main affinity (Primal) at the
        # Redemption rate for Abyssal into Primal, 0.70: int(56 x 0.70) = 39 Tide.
        entry = JournalEntryFactory(author=self.sineater)
        record_reflection(
            self.sineater, writing=entry, grant=succumbed, choice=ReflectionChoice.DISOWN
        )
        self.set_share("Success", "0.75")
        tide_before = _balance(self.sineater, self.tide)
        again = self.settle()
        self.assertIn("56 Ruin became 39 Tide.", again.lines[0])
        self.assertEqual(_balance(self.sineater, self.tide) - tide_before, 39)
        self.assertEqual(_row(self.sineater, self.ruin).balance, 100 - 56)

    def test_the_reading_names_the_burden_and_hides_what_the_sinner_is_paid(self) -> None:
        self.carry(self.ysmay_side, 100, purified_since_payout=400)
        self.reflect(self.ysmay_side, ReflectionChoice.SUCCUMB)

        (reading,) = settling_rite_reading(self.sineater, []).reflections

        self.assertEqual(
            (reading.kind, reading.choice, reading.title, reading.effect_line),
            (
                "burden",
                "SUCCUMB",
                f"Succumb to the Mire you carry for {_name(self.ysmay)}",
                "Up to 100 Ruin becomes part of you.",
            ),
        )

    def test_a_waiting_burden_reflection_is_replaced_by_a_newer_one(self) -> None:
        self.carry(self.ysmay_side, 100)
        self.reflect(self.ysmay_side, ReflectionChoice.ABSOLVE)
        newer = self.reflect(self.ysmay_side, ReflectionChoice.CONDEMN)

        self.assertEqual(list(Reflection.objects.all()), [newer])
        (option,) = [o for o in reflectable_for(self.sineater).options if o.kind == "burden"]
        self.assertEqual(
            (option.id, option.label, option.replaces_waiting),
            (self.ysmay_side.pk, f"The Mire you carry for {_name(self.ysmay)}", True),
        )

    def test_a_burden_takes_only_its_three_choices_and_only_while_mire_is_held(self) -> None:
        with self.assertRaises(ReflectionError):  # nothing held yet
            self.reflect(self.ysmay_side, ReflectionChoice.ABSOLVE)
        self.carry(self.ysmay_side, 10)
        with self.assertRaises(ReflectionError) as raised:
            self.reflect(self.ysmay_side, ReflectionChoice.EMBRACE)
        self.assertEqual(
            raised.exception.user_message, "Say whether you absolve, condemn or succumb to it."
        )
        with self.assertRaises(ReflectionError) as bad:
            pending_reflection_from(
                self.sineater,
                {"reflect_choice": "DISOWN", "reflect_tether_id": self.ysmay_side.pk},
            )
        self.assertEqual(
            bad.exception.user_message, "Say whether you absolve, condemn or succumb to it."
        )


class AFallingSineater(MireSettlingCase):
    def test_the_fall_pays_every_sinner_and_the_last_one_succumbed_to_extra(self) -> None:
        brindle, brindle_side = self.sinner_of_corvin()
        # Corvin has already succumbed to 300 for Ysmay and 100 for Brindle since his last
        # fall, and now succumbs to the 100 Brindle's Mire still holds. His Tide stands at 50
        # lifetime, so 100 Ruin makes his aura predominantly Abyssal.
        tide_row = _row(self.sineater, self.tide)
        tide_row.lifetime_earned = 50
        tide_row.save(update_fields=["lifetime_earned"])
        self.ysmay_side.mire_succumbed_since_fall = 300
        self.ysmay_side.save(update_fields=["mire_succumbed_since_fall"])
        self.carry(brindle_side, 100, succumbed_since_fall=100)
        self.set_share("Success", "1.00")
        self.reflect(brindle_side, ReflectionChoice.SUCCUMB)

        result = self.settle()

        # Ysmay: 300 x 300 / 100 = 900. Brindle: (100 + 100) x 300 / 100 = 600, and 600 x 50 /
        # 100 = 300 more for being the last, 900 in all; plus his succumb bonus of
        # 100 x 200 / 100 = 200 earlier in the same rite.
        self.assertEqual(_balance(self.ysmay, self.ruin), 900)
        self.assertEqual(_balance(brindle, self.ruin), 200 + 900)
        for side in (self.ysmay_side, brindle_side):
            side.refresh_from_db()
            self.assertEqual(side.mire_succumbed_since_fall, 0)
        lines = {n.sheet.pk: n.line for n in result.notices}
        self.assertEqual(
            lines[self.ysmay.pk],
            f"{_name(self.sineater)} has fallen to the Abyss. Your Ruin grows by 900.",
        )
        self.assertIn("you have fallen", result.lines[0])

        # Now fallen, he carries no one's sins: a plea to him is refused.
        with self.assertRaises(SineaterFallenError):
            request_sineating(self.ysmay, self.sineater, 1)

    def test_no_fall_pays_nothing_while_the_aura_is_not_abyssal(self) -> None:
        self.carry(self.ysmay_side, 100, succumbed_since_fall=0)
        self.set_share("Success", "1.00")
        self.reflect(self.ysmay_side, ReflectionChoice.SUCCUMB)

        result = self.settle()

        # 100 Ruin beside 500 Tide is 17% Abyssal: not predominant, so no fall and only the
        # succumb bonus floor(100 x 200 / 100) = 200 reaches Ysmay.
        self.assertEqual(_balance(self.ysmay, self.ruin), 200)
        self.assertEqual(len(result.notices), 1)
        self.assertNotIn("fallen", result.lines[0])

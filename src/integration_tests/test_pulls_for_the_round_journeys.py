"""Journeys for a thread pull that lasts the round: declared on its own, or pulled for defense
(#5066 item 6).

The cellar and Ondrelle are the dodging journeys' (``_TheCellar``): she knows Blink Step, a
technique marked ``teleport`` that grants traversal 4 and costs 2 anima, so each automatic
dodge is a cast of it. She holds the resonance Veil (balance 10) and a thread woven on
Blink Step ("Step Strand", shown level 1) whose tier-1 pull adds 2 to the roll. The tier-1
pull costs 1 resonance and 1 anima for every thread pulled.

- Declared on its own ("You pull 1 thread for the round."), with no cast, the pull costs
  1 resonance and 1 anima once, and every dodge with Blink Step that round rolls its
  technique roll with the +2; the next round it is gone.
- Two threads pulled cost twice: each thread pays its tier's share, the first included
  (maintainer, after approval, 2026-11-10).
- Typed on telnet: ``combat pull 1=Step Strand``.
- A pull may mix resonances (maintainer ruling 2026-11-11): Step Strand (Veil) with Ember
  Strand (Ember, balance 6) costs 1 Veil, 1 Ember and 2 anima, each thread from its own
  resonance; when Ember cannot cover its own thread nothing is debited at all.
- With her defensive pull saved (tier 1, any resonance) and auto-pull on, the first attack of a
  round commits it before her dodge rolls ("You pull 1 thread for defense."): the dodge's
  technique roll carries the +2. A second attack that round pulls nothing more.
- When her only related thread already works for her on the defence roll (a thread on the
  stat both rolls use, whose tier-0 passive applies there anyway), the auto-pull pulls
  nothing and charges nothing, and says so.

Expected values come from the spec (decisions 6, 12 and 14; the per-thread cost ruling) and
the rows built here.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from integration_tests.test_dodging_journeys import RecordingRoll, _clean_hit, _TheCellar
from world.checks.factories import CheckTypeTraitFactory
from world.combat.models import CombatPull
from world.combat.services import begin_declaration_phase, resolve_round
from world.magic.constants import EffectKind, TargetKind
from world.magic.factories import (
    CharacterResonanceFactory,
    ResonanceFactory,
    ThreadFactory,
    ThreadPullCostFactory,
    ThreadPullEffectFactory,
)
from world.magic.models import CharacterResonance
from world.traits.factories import StatTraitFactory

FLAT_BONUS = 2


class TechniqueRolls:
    """The forced technique roll: a bare success each time, keeping what it was handed."""

    def __init__(self) -> None:
        self.extras: list[int] = []

    def __call__(self, _character: Any, _cast_check: Any, *, extra_modifiers: int = 0) -> Any:
        self.extras.append(extra_modifiers)
        return MagicMock(success_level=1)


class _PullsInTheCellar(_TheCellar):
    def setUp(self) -> None:
        super().setUp()
        self.ondrelle = self.fighter("Ondrelle", at=self.stage, blinks=True)
        sheet = self.ondrelle.sheet_data
        self.veil = ResonanceFactory(name="Veil")
        ThreadPullCostFactory(tier=1, resonance_cost=1, anima_per_thread=1)
        for kind in (TargetKind.TECHNIQUE, TargetKind.TRAIT):
            ThreadPullEffectFactory(
                target_kind=kind,
                resonance=self.veil,
                tier=1,
                min_thread_level=0,
                effect_kind=EffectKind.FLAT_BONUS,
                flat_bonus_amount=FLAT_BONUS,
            )
        CharacterResonanceFactory(
            character_sheet=sheet, resonance=self.veil, balance=10, lifetime_earned=10
        )
        self.strand = ThreadFactory(
            owner=sheet,
            resonance=self.veil,
            target_kind=TargetKind.TECHNIQUE,
            target_trait=None,
            target_technique=self.blink_step,
            level=10,  # shown level 1
            name="Step Strand",
        )
        self.technique_rolls = TechniqueRolls()

    def resolve(self, roll: RecordingRoll) -> None:  # the technique roll, recorded
        with (
            patch(
                "world.combat.services.movement_use.roll_technique",
                side_effect=self.technique_rolls,
            ),
            self.captureOnCommitCallbacks(execute=True),
        ):
            resolve_round(self.encounter, defense_check_fn=roll, offense_check_fn=_clean_hit)

    def balance(self) -> int:
        return CharacterResonance.objects.get(
            character_sheet=self.ondrelle.sheet_data, resonance=self.veil
        ).balance

    def pull(self, *threads) -> Any:
        return self.web(
            self.ondrelle,
            "combat_pull",
            pull_tier=1,
            pull_thread_ids=[thread.pk for thread in threads],
        )


class APullOnItsOwn(_PullsInTheCellar):
    def test_it_costs_once_and_boosts_every_related_dodge_this_round(self) -> None:
        told = self.pull(self.strand)
        self.assertTrue(told.detail.success, told.detail.message)
        self.assertEqual(told.detail.message, "You pull 1 thread for the round.")
        self.assertEqual(self.balance(), 9)
        self.assertEqual(self.anima(self.ondrelle), 19)
        for name in ("Archer", "Bowman"):
            self.blade(name, at=self.gallery)

        self.resolve(RecordingRoll(2, 2))

        self.assertEqual(self.technique_rolls.extras, [FLAT_BONUS, FLAT_BONUS])
        self.assertEqual(self.anima(self.ondrelle), 19 - 2 - 2)  # two dodges, 2 each

    def test_it_is_gone_next_round(self) -> None:
        self.pull(self.strand)
        self.blade("Archer", at=self.gallery)
        self.resolve(RecordingRoll(2))
        begin_declaration_phase(self.encounter)
        self.technique_rolls.extras.clear()

        self.resolve(RecordingRoll(2))

        self.assertEqual(self.technique_rolls.extras, [0])

    def test_every_thread_pays_its_share(self) -> None:
        stat = StatTraitFactory(name="Poise")
        CheckTypeTraitFactory(check_type=self.blink_step.action_template.check_type, trait=stat)
        second = ThreadFactory(
            owner=self.ondrelle.sheet_data,
            resonance=self.veil,
            target_kind=TargetKind.TRAIT,
            target_trait=stat,
            level=10,
            name="Poise Strand",
        )

        told = self.pull(self.strand, second)

        self.assertEqual(told.detail.message, "You pull 2 threads for the round.")
        self.assertEqual(self.balance(), 8)
        self.assertEqual(self.anima(self.ondrelle), 18)

    def test_a_burn_cannot_ride_a_pull_on_its_own(self) -> None:
        told = self.web(
            self.ondrelle,
            "combat_pull",
            pull_tier=1,
            pull_thread_ids=[self.strand.pk],
            pull_burn=2,
        )

        self.assertFalse(told.detail.success)
        self.assertEqual(
            told.detail.message, "A burn rides a cast or a clash; a pull on its own cannot burn."
        )
        self.assertEqual(self.balance(), 10)

    def test_typed_on_telnet(self) -> None:
        told = self.telnet(self.ondrelle, "combat pull 1=Step Strand")

        self.assertIn("You pull 1 thread for the round.", told)
        self.assertTrue(
            CombatPull.objects.filter(
                participant=self.participant(self.ondrelle), round_number=1
            ).exists()
        )


class TypingTheDefensivePull(_PullsInTheCellar):
    def test_autopull_typed_on_and_off(self) -> None:
        told = self.telnet(self.ondrelle, "combat autopull 1")
        self.assertIn("You'll pull threads for defense when attacked.", told)
        seat = self.participant(self.ondrelle)
        self.assertTrue(seat.auto_pull_defense)
        self.assertEqual(seat.defense_pull_tier, 1)

        told = self.telnet(self.ondrelle, "combat autopull off")

        self.assertIn("You won't pull threads for defense on your own.", told)
        self.assertFalse(self.participant(self.ondrelle).auto_pull_defense)

    def test_a_tier_out_of_range_is_refused(self) -> None:
        told = self.telnet(self.ondrelle, "combat autopull 4")

        self.assertIn("Pick a tier from 1 to 3", told)
        self.assertFalse(self.participant(self.ondrelle).auto_pull_defense)


class PullingForDefense(_PullsInTheCellar):
    def setUp(self) -> None:
        super().setUp()
        told = self.web(
            self.ondrelle,
            "dodge_settings",
            auto_pull=True,
            pull_tier=1,
        )
        self.assertTrue(told.detail.success, told.detail.message)

    def test_the_first_attack_pulls_before_her_dodge_rolls(self) -> None:
        for name in ("Archer", "Bowman"):
            self.blade(name, at=self.gallery)
        defence = RecordingRoll(2, 2)

        self.resolve(defence)

        self.assertEqual(self.technique_rolls.extras, [FLAT_BONUS, FLAT_BONUS])
        # The pull reaches the defence roll only through the dodge's strength (4, then 4
        # less the second reaction's step of 2), never as its own +2 on that roll.
        self.assertEqual(defence.extras(), [4, 2])
        self.assertEqual(CombatPull.objects.filter(round_number=1).count(), 1)
        self.assertEqual(self.balance(), 9)
        self.assertTold(self.ondrelle, "You pull 1 thread for defense.")

    def test_a_thread_already_working_for_her_is_not_pulled(self) -> None:
        stat = StatTraitFactory(name="Wits")
        CheckTypeTraitFactory(check_type=self.defense, trait=stat)
        CheckTypeTraitFactory(check_type=self.blink_step.action_template.check_type, trait=stat)
        self.strand.target_kind = TargetKind.TRAIT
        self.strand.target_technique = None
        self.strand.target_trait = stat
        self.strand.save()
        self.ondrelle.threads.invalidate()
        self.blade("Archer", at=self.gallery)

        self.resolve(RecordingRoll(2))

        self.assertFalse(CombatPull.objects.exists())
        self.assertEqual(self.balance(), 10)
        self.assertTold(
            self.ondrelle,
            "Your defensive pull finds no thread that is not already working for you.",
        )


class APullMixingResonances(_PullsInTheCellar):
    """Each thread is paid from its own resonance (maintainer ruling 2026-11-11)."""

    def setUp(self) -> None:
        super().setUp()
        self.ember = ResonanceFactory(name="Ember")
        self.ember_hold = CharacterResonanceFactory(
            character_sheet=self.ondrelle.sheet_data,
            resonance=self.ember,
            balance=6,
            lifetime_earned=6,
        )
        ThreadPullEffectFactory(
            target_kind=TargetKind.TECHNIQUE,
            resonance=self.ember,
            tier=1,
            min_thread_level=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=FLAT_BONUS,
        )
        self.ember_strand = ThreadFactory(
            owner=self.ondrelle.sheet_data,
            resonance=self.ember,
            target_kind=TargetKind.TECHNIQUE,
            target_trait=None,
            target_technique=self.blink_step,
            level=10,
            name="Ember Strand",
        )

    def ember_balance(self) -> int:
        return CharacterResonance.objects.get(
            character_sheet=self.ondrelle.sheet_data, resonance=self.ember
        ).balance

    def test_each_thread_pays_from_its_own_resonance(self) -> None:
        told = self.pull(self.strand, self.ember_strand)

        self.assertTrue(told.detail.success, told.detail.message)
        self.assertEqual(told.detail.message, "You pull 2 threads for the round.")
        self.assertEqual((self.balance(), self.ember_balance()), (9, 5))
        self.assertEqual(self.anima(self.ondrelle), 18)
        pull = CombatPull.objects.get(participant=self.participant(self.ondrelle))
        self.assertEqual(
            set(pull.threads.values_list("pk", flat=True)),
            {self.strand.pk, self.ember_strand.pk},
        )
        self.blade("Archer", at=self.gallery)

        self.resolve(RecordingRoll(2))

        # Both threads relate to Blink Step: its dodge roll carries both +2s.
        self.assertEqual(self.technique_rolls.extras, [FLAT_BONUS * 2])

    def test_typed_on_telnet_with_threads_of_two_resonances(self) -> None:
        told = self.telnet(self.ondrelle, "combat pull 1=Step Strand,Ember Strand")

        self.assertIn("You pull 2 threads for the round.", told)
        self.assertEqual((self.balance(), self.ember_balance()), (9, 5))

    def test_one_resonance_short_debits_nothing(self) -> None:
        self.ember_hold.balance = 0
        self.ember_hold.save(update_fields=["balance"])

        told = self.pull(self.strand, self.ember_strand)

        self.assertFalse(told.detail.success)
        self.assertEqual((self.balance(), self.ember_balance()), (10, 0))
        self.assertEqual(self.anima(self.ondrelle), 20)
        self.assertFalse(CombatPull.objects.exists())

    def test_the_defensive_pull_takes_threads_of_every_resonance(self) -> None:
        self.web(self.ondrelle, "dodge_settings", auto_pull=True, pull_tier=1)
        self.blade("Archer", at=self.gallery)

        self.resolve(RecordingRoll(2))

        self.assertEqual((self.balance(), self.ember_balance()), (9, 5))
        self.assertTold(self.ondrelle, "You pull 2 threads for defense.")

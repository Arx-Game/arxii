"""Journeys for a vow perk that applies to attack rolls only (#5092).

Hobb holds an engaged vow at thread level 3 whose role carries one check-bonus perk of 10
tenths, with no situation, so it answers every roll its scope allows. The perk scales by the
stored thread level (stored 30, #4585): 30 x 10 / 10 = +30 points on a roll it reaches.

The perk's "Applies to" is set to "Attack rolls" (owner ruling, 2026-11-12): once per attack
on an opponent. A plain Strike's hit roll takes it, an attack technique's roll takes it, and
an enchanted Strike's technique roll takes it while its hit roll does not (one boost per
attack, ADR-5026's counted-once table). A dodge against a blow, the Strike's damage roll and
a cast at himself never take it.

Each journey plays the same round twice: first with the perk scoped to a check type nothing
here rolls (so it never answers), then with "Applies to: Attack rolls". Every roll is forced
to Success, Hobb starts each round rested, and the difference between the two rounds on each
roll is what the perk added. Expected values come from the owner's ruling and the perk's
authored magnitude, not from the code.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

from actions.constants import ActionBackend
from actions.factories import ActionTemplateFactory
from actions.player_interface import dispatch_player_action
from actions.types import ActionRef
from integration_tests.test_thrown_and_enchanted_strike_journeys import _ThrowingField
from world.areas.positioning.models import Position
from world.areas.positioning.services import place_in_position
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.checks.services import perform_check
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import (
    ActionCategory,
    OpponentTier,
    StrikeDelivery,
    TargetingMode,
    TargetSelection,
)
from world.combat.factories import (
    CreatureTemplateFactory,
    OpponentTierTemplateFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.services import begin_declaration_phase, resolve_round
from world.combat.services.boss.creature_spawn import spawn_from_creature_template
from world.covenants.constants import CovenantType
from world.covenants.factories import (
    CovenantFactory,
    CovenantRoleFactory,
    VowSituationalPerkFactory,
    engage_vow_with_thread,
)
from world.covenants.perks.constants import PerkBeneficiary, PerkEffectKind, PerkRollKind
from world.fatigue.constants import EffortLevel
from world.fatigue.services import get_or_create_fatigue_pool
from world.magic.factories import (
    CharacterTechniqueFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueFactory,
)
from world.traits.models import CheckOutcome, Trait

if TYPE_CHECKING:
    from collections.abc import Iterator

    from world.checks.models import CheckType

PAYOFF = 30
VOW_ANSWERS = "vow answers the attack!"


class _AttackRollPerkField(_ThrowingField):
    """Hobb, his thrown dagger and the archer, plus a vow perk scoped by the journey."""

    def setUp(self) -> None:
        super().setUp()
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        engage_vow_with_thread(
            self.sheet,
            role,
            covenant=CovenantFactory(covenant_type=CovenantType.DURANCE),
            thread_level=3,
        )
        self.never_rolled = CheckTypeFactory(name="Never rolled here")
        self.perk = VowSituationalPerkFactory(
            covenant_role=role,
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.CHECK_BONUS,
            magnitude_tenths=10,
            check_type=self.never_rolled,
            announce_template="{holder}'s vow answers the attack!",
        )
        self.watch(self.hobb)

    def scope_to_attack_rolls(self) -> None:
        """Staff's edit: no check type, "Applies to: Attack rolls"."""
        self.perk.check_type = None
        self.perk.roll_kind = PerkRollKind.ATTACK
        self.perk.full_clean()
        self.perk.save()

    @contextmanager
    def rolls_at_success(self) -> Iterator[list[tuple[CheckType, int]]]:
        """Every roll in the block lands at Success; each roll's check type and points."""
        outcome = CheckOutcome.objects.get(name="Success")
        rolled: list[tuple[CheckType, int]] = []

        def forced(character: Any, check_type: CheckType, *args: Any, **kw: Any):
            with force_check_outcome(outcome):
                result = perform_check(character, check_type, *args, **kw)
            if character == self.hobb:
                rolled.append((check_type, result.total_points))
            return result

        self._forced = forced
        with patch("world.combat.services.perform_check", side_effect=forced):
            yield rolled

    def play_round(self, declare) -> list[tuple[CheckType, int]]:
        """Hobb starts rested, ``declare`` declares his action, the round resolves."""
        pool = get_or_create_fatigue_pool(self.sheet)
        pool.physical_current = 0
        pool.mental_current = 0
        pool.save(update_fields=["physical_current", "mental_current"])
        declare()
        with self.rolls_at_success() as rolled:
            resolve_round(self.encounter, defense_check_fn=self._forced)
        begin_declaration_phase(self.encounter)
        self.encounter.refresh_from_db()
        return rolled

    def throw(self, **kwargs: Any) -> None:
        result = self.web(
            self.hobb,
            "combat_strike",
            opponent_id=self.archer.pk,
            weapon_id=self.dagger.pk,
            thrown=True,
            **kwargs,
        )
        self.assertTrue(result.detail.success, result.detail.message)

    def added(self, declare) -> list[tuple[str, int]]:
        """Play the round with the perk off, then scoped to attack rolls; per roll, in the
        order rolled, its check type's name and the points the perk added."""
        before = self.play_round(declare)
        self.assertNotTold(self.hobb, VOW_ANSWERS)
        self.scope_to_attack_rolls()
        after = self.play_round(declare)
        self.assertEqual([c for c, _ in before], [c for c, _ in after])
        return [(c.name, a - b) for (c, b), (_, a) in zip(before, after, strict=True)]


class AStrikeTakesTheBoostOnce(_AttackRollPerkField):
    def test_a_plain_strike_hit_roll_takes_it_and_its_damage_roll_does_not(self) -> None:
        added = self.added(self.throw)

        self.assertEqual(added[0], (self.thrown_check.name, PAYOFF))
        self.assertTrue(all(points == 0 for _name, points in added[1:]), added)
        self.assertTold(self.hobb, VOW_ANSWERS)

    def test_an_enchanted_strike_boosts_its_technique_roll_not_its_hit_roll(self) -> None:
        technique = self.wreathe_the_blade(anima=30)

        added = self.added(lambda: self.throw(technique_id=technique.pk))

        technique_roll, hit_roll, *rest = added
        self.assertEqual(technique_roll, ("Fire Magic Cast", PAYOFF))
        self.assertEqual(hit_roll, (self.thrown_check.name, 0))
        self.assertTrue(all(points == 0 for _name, points in rest), added)


class AnAttackTechniqueTakesItAndADodgeDoesNot(_AttackRollPerkField):
    """Hobb casts a bolt at a blade beside him while the blade swings at him."""

    def setUp(self) -> None:
        super().setUp()
        self.wreathe_the_blade(anima=30)  # Hobb's anima and the magic check
        magic = CheckTypeFactory(name="Bolt Cast")
        CheckTypeTraitFactory(check_type=magic, trait=Trait.objects.get(name="strength"))
        self.bolt = TechniqueFactory(
            name="Ember bolt",
            gift=GiftFactory(name="Cinder"),
            anima_cost=1,
            effect_type=EffectTypeFactory(base_power=10),
            damage_profile=False,
            action_category=ActionCategory.PHYSICAL,
            action_template=ActionTemplateFactory(check_type=magic),
        )
        CharacterTechniqueFactory(character=self.sheet, technique=self.bolt)
        self.parry = CheckTypeFactory(name="Parry")
        OpponentTierTemplateFactory(tier=OpponentTier.MOOK, base_health=500, base_soak=0)
        pool = ThreatPoolFactory(name="Blade attacks")
        ThreatPoolEntryFactory(
            pool=pool,
            name="Blade swing",
            base_damage=1,
            delivery=StrikeDelivery.MELEE,
            targeting_mode=TargetingMode.SINGLE,
            target_selection=TargetSelection.HIGHEST_THREAT,
            defense_check_type=self.parry,
        )
        self.blade = spawn_from_creature_template(
            self.encounter,
            CreatureTemplateFactory(
                name="Blade", tier=OpponentTier.MOOK, threat_pool=pool, speed_hops=0
            ),
        )
        lane = Position.objects.get(room=self.steading, name="Lane")
        place_in_position(self.blade.objectdb, lane)

    def cast_bolt(self) -> None:
        declared = dispatch_player_action(
            self.hobb,
            ActionRef(
                backend=ActionBackend.COMBAT, technique_id=self.bolt.pk, action_slot="focused"
            ),
            {"effort_level": EffortLevel.MEDIUM, "focused_opponent_target_id": self.blade.pk},
        )
        self.assertTrue(declared.deferred, declared)

    def test_the_bolt_takes_it_and_the_parry_that_round_does_not(self) -> None:
        added = dict(self.added(self.cast_bolt))

        self.assertEqual(added["Bolt Cast"], PAYOFF)
        self.assertEqual(added["Parry"], 0)
        self.assertTold(self.hobb, VOW_ANSWERS)

    def test_an_unscoped_perk_does_reach_the_parry(self) -> None:
        """The control: the parry reads perks, so "Attack rolls" is what keeps it out."""
        before = dict(self.play_round(self.cast_bolt))
        self.perk.check_type = None
        self.perk.save()
        after = dict(self.play_round(self.cast_bolt))

        self.assertEqual(after["Parry"] - before["Parry"], PAYOFF)
        self.assertEqual(after["Bolt Cast"] - before["Bolt Cast"], PAYOFF)

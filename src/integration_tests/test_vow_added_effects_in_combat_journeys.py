"""Journeys for vow added effects in a fight (#4581): a covenant vow adds to a cast.

Ysmay, Hobb and Wren share a Durance covenant. Ysmay's vow carries staff-authored
``VowAddedEffect`` rows; a row rides her own casts (SELF) or her covenant allies'
casts (COVENANT_ALLIES) when the technique's function tag matches. Each journey
declares a technique the way the web client does (``dispatch_player_action`` on a
combat ``ActionRef``), resolves the round with ``resolve_round``, and reads back
what landed: the condition on the NPC opponent's object, the opponent's health,
and the once-per-round / once-per-fight ledger.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from unittest.mock import patch

from evennia.objects.models import ObjectDB

from actions.constants import ActionBackend
from actions.factories import ActionTemplateFactory
from actions.player_interface import dispatch_player_action
from actions.types import ActionRef
from integration_tests.harness import JourneyCase
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.checks.services import perform_check
from world.checks.test_helpers import force_check_outcome
from world.checks.types import CheckResult
from world.combat.constants import (
    PENETRATION_CHECK_TYPE_NAME,
    ActionCategory,
    OpponentTier,
    ParticipantStatus,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.models import CombatOpponent, VowAddedEffectFiring
from world.combat.services import begin_declaration_phase, resolve_round
from world.conditions.factories import (
    ConditionTemplateFactory,
    DamageSuccessLevelMultiplierFactory,
    PenetrationOutcomeFactorFactory,
)
from world.conditions.models import ConditionInstance
from world.covenants.constants import CovenantType, VowEffectContext, VowEffectFrequency
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
    VowAddedEffectAppliedConditionFactory,
    VowAddedEffectDamageProfileFactory,
    VowAddedEffectFactory,
    engage_vow_with_thread,
)
from world.covenants.models import VowAddedEffect
from world.covenants.perks.constants import PerkBeneficiary, Situation
from world.fatigue.constants import EffortLevel
from world.magic.constants import TechniqueFunction
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueFactory,
    TechniqueFunctionTagFactory,
)
from world.magic.models import Technique
from world.magic.models.techniques import ConditionTargetKind
from world.scenes.constants import RoundStatus
from world.traits.factories import CheckSystemSetupFactory, StatTraitFactory
from world.traits.models import CheckOutcome
from world.vitals.models import CharacterVitals


@contextmanager
def every_check_at(outcome_name: str) -> Iterator[None]:
    """Every combat check in the block lands at the named ``CheckOutcome``.

    Patches ``world.combat.services.perform_check`` (the seam the round's checks
    call through) to run each call inside ``force_check_outcome``.
    """
    outcome = CheckOutcome.objects.get(name=outcome_name)

    def forced(*args: object, **kwargs: object) -> CheckResult:
        with force_check_outcome(outcome):
            return perform_check(*args, **kwargs)

    with patch("world.combat.services.perform_check", side_effect=forced):
        yield


def every_check_succeeds() -> AbstractContextManager[None]:
    """Every combat check in the block lands at Success (success level 1)."""
    return every_check_at("Success")


class VowAddedEffectsInAFight(JourneyCase):
    """Ysmay holds the vow; Hobb and Wren are engaged covenant allies in the same fight."""

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        DamageSuccessLevelMultiplierFactory(min_success_level=1, multiplier=1)
        self.yard = self.make_room("The Yard")
        self.check_type = CheckTypeFactory()
        CheckTypeTraitFactory(check_type=self.check_type, trait=StatTraitFactory(), weight=1)
        self.hold = self.technique_tagged(TechniqueFunction.HOLD)
        self.weaken = self.technique_tagged(TechniqueFunction.WEAKEN)

        self.covenant = CovenantFactory(covenant_type=CovenantType.DURANCE)
        self.tank = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=self.yard
        )
        self.ysmay = self.fighter("Ysmay")
        self.hobb = self.fighter("Hobb")
        self.wren = self.fighter("Wren")
        self.opponent = CombatOpponentFactory(encounter=self.encounter)
        self.slowed = ConditionTemplateFactory(name="Slowed")

    # -- setup helpers ----------------------------------------------------------

    def technique_tagged(self, function: str) -> Technique:
        """A castable technique with no damage of its own, tagged ``function``."""
        technique = TechniqueFactory(
            gift=GiftFactory(),
            anima_cost=1,
            effect_type=EffectTypeFactory(base_power=10),
            damage_profile=False,
            action_category=ActionCategory.PHYSICAL,
            action_template=ActionTemplateFactory(check_type=self.check_type),
        )
        TechniqueFunctionTagFactory(technique=technique, function=function)
        return technique

    def fighter(self, name: str) -> ObjectDB:
        """A player in the yard and in the fight, knowing both techniques."""
        character = self.make_player(name, room=self.yard)
        sheet = character.sheet_data
        CharacterTechniqueFactory(character=sheet, technique=self.hold)
        CharacterTechniqueFactory(character=sheet, technique=self.weaken)
        CharacterAnimaFactory(character=sheet, current=20, maximum=30)
        CharacterVitals.objects.create(
            character_sheet=sheet, health=50, max_health=50, base_max_health=50
        )
        CombatParticipantFactory(
            encounter=self.encounter, character_sheet=sheet, status=ParticipantStatus.ACTIVE
        )
        return character

    def swear(self, character: ObjectDB, *, thread_level: int = 1, engaged: bool = True) -> None:
        """``character`` takes a role in the covenant, engaged unless told otherwise."""
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        sheet = character.sheet_data
        if engaged:
            engage_vow_with_thread(sheet, role, covenant=self.covenant, thread_level=thread_level)
            return
        CharacterCovenantRoleFactory(
            character_sheet=sheet, covenant=self.covenant, covenant_role=role, engaged=False
        )
        character.covenant_roles.invalidate()

    def ysmays_vow(self, *, thread_level: int, **row: object) -> VowAddedEffect:
        """Ysmay engages the tank role at ``thread_level``; the role carries one row."""
        engage_vow_with_thread(
            self.ysmay.sheet_data, self.tank, covenant=self.covenant, thread_level=thread_level
        )
        return VowAddedEffectFactory(covenant_role=self.tank, **row)

    def slows_the_enemy(self, effect: VowAddedEffect) -> None:
        VowAddedEffectAppliedConditionFactory(
            effect=effect,
            condition=self.slowed,
            target_kind=ConditionTargetKind.ENEMY,
            base_severity=1,
        )

    # -- the fight ----------------------------------------------------------------

    def declare(self, character: ObjectDB, technique: Technique, target: CombatOpponent) -> None:
        ref = ActionRef(
            backend=ActionBackend.COMBAT, technique_id=technique.pk, action_slot="focused"
        )
        declared = dispatch_player_action(
            character,
            ref,
            {"effort_level": EffortLevel.MEDIUM, "focused_opponent_target_id": target.pk},
        )
        self.assertTrue(declared.deferred, declared)

    def resolve(self) -> None:
        with every_check_succeeds():
            resolve_round(self.encounter)

    def resolve_partial(self) -> None:
        """Every check this round is a partial success (success level 0)."""
        with every_check_at("Partial Success"):
            resolve_round(self.encounter)

    def resolve_failing(self) -> None:
        """Every check this round fails (success level -1)."""
        with every_check_at("Failure"):
            resolve_round(self.encounter)

    def next_round(self) -> None:
        begin_declaration_phase(self.encounter)
        self.encounter.refresh_from_db()

    def firings(self, effect: VowAddedEffect, **filters: object) -> int:
        return VowAddedEffectFiring.objects.filter(effect=effect, **filters).count()

    def health(self, opponent: CombatOpponent) -> int:
        opponent.refresh_from_db()
        return opponent.health

    # -- journeys -----------------------------------------------------------------

    def test_the_tanks_own_hold_slows_the_held_enemy(self) -> None:
        effect = self.ysmays_vow(
            thread_level=4,
            function=TechniqueFunction.HOLD,
            beneficiary=PerkBeneficiary.SELF,
            cast_context=VowEffectContext.IN_COMBAT,
            unlock_thread_level=1,
            severity_per_thread_level=2,
        )
        self.slows_the_enemy(effect)

        self.declare(self.ysmay, self.hold, self.opponent)
        self.resolve()

        instance = ConditionInstance.objects.get(
            target=self.opponent.objectdb, condition=self.slowed
        )
        self.assertEqual(instance.severity, 7)

    def test_once_per_round_lands_once_a_round_and_again_next_round(self) -> None:
        effect = self.ysmays_vow(
            thread_level=2,
            function=TechniqueFunction.HOLD,
            beneficiary=PerkBeneficiary.COVENANT_ALLIES,
            cast_context=VowEffectContext.IN_COMBAT,
            frequency=VowEffectFrequency.ONCE_PER_ROUND,
        )
        self.slows_the_enemy(effect)
        self.swear(self.hobb)
        self.swear(self.wren)

        self.declare(self.hobb, self.hold, self.opponent)
        self.declare(self.wren, self.hold, self.opponent)
        self.resolve()

        self.assertEqual(self.firings(effect, round_number=1), 1)
        self.assertEqual(
            ConditionInstance.objects.filter(
                target=self.opponent.objectdb, condition=self.slowed
            ).count(),
            1,
        )

        self.next_round()
        self.declare(self.hobb, self.hold, self.opponent)
        self.resolve()

        self.assertEqual(self.firings(effect, round_number=2), 1)

    def boss_damage_vow(self) -> VowAddedEffect:
        effect = self.ysmays_vow(
            thread_level=3,
            function=TechniqueFunction.WEAKEN,
            beneficiary=PerkBeneficiary.COVENANT_ALLIES,
            cast_context=VowEffectContext.IN_COMBAT,
            situation=Situation.TARGET_IS_BOSS,
            frequency=VowEffectFrequency.ONCE_PER_FIGHT,
            damage_per_thread_level=5,
        )
        VowAddedEffectDamageProfileFactory(effect=effect, base_damage=0)
        self.swear(self.hobb)
        return effect

    def test_the_damage_vow_rides_an_allys_weaken_against_a_boss_once_a_fight(self) -> None:
        effect = self.boss_damage_vow()
        boss = CombatOpponentFactory(encounter=self.encounter, tier=OpponentTier.BOSS)

        self.declare(self.hobb, self.weaken, boss)
        self.resolve()

        after_first = self.health(boss)
        self.assertLess(after_first, boss.max_health)
        self.assertEqual(self.firings(effect), 1)

        self.next_round()
        self.declare(self.hobb, self.weaken, boss)
        self.resolve()

        self.assertEqual(self.health(boss), after_first)
        self.assertEqual(self.firings(effect), 1)

    def test_against_an_elite_the_damage_vow_adds_nothing(self) -> None:
        effect = self.boss_damage_vow()
        elite = CombatOpponentFactory(encounter=self.encounter, tier=OpponentTier.ELITE)

        self.declare(self.hobb, self.weaken, elite)
        self.resolve()

        self.assertEqual(self.health(elite), elite.max_health)
        self.assertEqual(self.firings(effect), 0)

    def test_a_failed_cast_spends_nothing(self) -> None:
        effect = self.boss_damage_vow()
        boss = CombatOpponentFactory(encounter=self.encounter, tier=OpponentTier.BOSS)

        self.declare(self.hobb, self.weaken, boss)
        self.resolve_failing()

        self.assertEqual(self.firings(effect), 0)
        self.assertEqual(self.health(boss), boss.max_health)

        self.next_round()
        self.declare(self.hobb, self.weaken, boss)
        self.resolve()

        self.assertEqual(self.firings(effect, round_number=2), 1)
        self.assertLess(self.health(boss), boss.max_health)

    def test_a_partial_success_neither_uses_nor_spends_a_limited_row(self) -> None:
        # The row's payload is authored to land at success level 0, but a cast that
        # cannot spend a once-per-round row cannot use it either.
        effect = self.ysmays_vow(
            thread_level=2,
            function=TechniqueFunction.HOLD,
            beneficiary=PerkBeneficiary.SELF,
            cast_context=VowEffectContext.IN_COMBAT,
            frequency=VowEffectFrequency.ONCE_PER_ROUND,
        )
        VowAddedEffectAppliedConditionFactory(
            effect=effect,
            condition=self.slowed,
            target_kind=ConditionTargetKind.ENEMY,
            base_severity=1,
            minimum_success_level=0,
        )

        self.declare(self.ysmay, self.hold, self.opponent)
        self.resolve_partial()

        self.assertFalse(
            ConditionInstance.objects.filter(
                target=self.opponent.objectdb, condition=self.slowed
            ).exists()
        )
        self.assertEqual(self.firings(effect), 0)

    def test_a_cast_that_bounces_off_a_ward_spends_nothing(self) -> None:
        effect = self.boss_damage_vow()
        penetration = CheckTypeFactory(name=PENETRATION_CHECK_TYPE_NAME)
        CheckTypeTraitFactory(check_type=penetration, trait=StatTraitFactory(), weight=1)
        # The only authored rung: every penetration roll, however good, bounces.
        PenetrationOutcomeFactorFactory(min_success_level=-10, factor=0, label="Bounced")
        warded = CombatOpponentFactory(
            encounter=self.encounter, tier=OpponentTier.BOSS, barrier_strength=5
        )

        self.declare(self.hobb, self.weaken, warded)
        self.resolve()

        self.assertEqual(self.firings(effect), 0)
        self.assertEqual(self.health(warded), warded.max_health)

        self.next_round()
        unwarded = CombatOpponentFactory(encounter=self.encounter, tier=OpponentTier.BOSS)
        self.declare(self.hobb, self.weaken, unwarded)
        self.resolve()

        self.assertEqual(self.firings(effect, round_number=2), 1)

    def test_a_disengaged_caster_gets_nothing(self) -> None:
        # Once a round, so a firing would leave a ledger row to count.
        effect = self.ysmays_vow(
            thread_level=4,
            function=TechniqueFunction.HOLD,
            beneficiary=PerkBeneficiary.COVENANT_ALLIES,
            cast_context=VowEffectContext.IN_COMBAT,
            frequency=VowEffectFrequency.ONCE_PER_ROUND,
        )
        self.slows_the_enemy(effect)
        self.swear(self.hobb, engaged=False)

        self.declare(self.hobb, self.hold, self.opponent)
        self.resolve()

        self.assertFalse(
            ConditionInstance.objects.filter(
                target=self.opponent.objectdb, condition=self.slowed
            ).exists()
        )
        self.assertEqual(self.firings(effect), 0)

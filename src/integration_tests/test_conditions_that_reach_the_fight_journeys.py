"""Journeys for conditions that reach the fight (#4572).

A condition a technique lays on someone in a fight does what its row says, whoever carries it.
Two player characters, Brenna and Cassian, stand against a hired brute. The brute's attack picks
whoever it hates most (highest threat), a bleed on the brute costs it health when the round ends,
and a quickening on Cassian moves him ahead of the faster-trained Brenna in the round's order.

Every expected number below is an authored value on a row built in ``setUp``, not something read
back from the code under test:

- Brenna is the one the brute has been fighting: her threat with it is 20. Her covenant role is
  quick (speed rank 3). Cassian has no threat with the brute and a slower role (speed rank 8).
- "Taunting Mark" (draws aggro, aggro priority 50) on Cassian lifts his threat to 0 + 50 = 50,
  past Brenna's 20, so the brute swings at him. Without it the brute swings at Brenna.
- "Quickened Step" (turn order modifier +6) takes Cassian from rank 8 to 8 - 6 = 2, ahead of
  Brenna's 3. The brute ranks 15 and acts last either way.
- The brute swings for 12 (its threat entry's base damage) against a defence roll fixed at a
  plain success, so the target of that swing loses exactly 12 of 100 health.
- "Slow Bleed" (6 fire damage a round, no scaling) takes the brute from 50 health to 44 when the
  round ends.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from actions.constants import ActionBackend
from actions.factories import ActionTemplateFactory
from actions.player_interface import dispatch_player_action
from actions.types import ActionRef
from integration_tests.harness import JourneyCase
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.combat.constants import (
    ActionCategory,
    ParticipantStatus,
    TargetingMode,
    TargetSelection,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
    ThreatRecordFactory,
)
from world.combat.models import CombatOpponentAction, ThreatRecord
from world.combat.services import get_resolution_order, resolve_round
from world.conditions.factories import (
    ConditionDamageOverTimeFactory,
    ConditionTemplateFactory,
    DamageTypeFactory,
)
from world.conditions.services import apply_condition
from world.covenants.factories import CovenantRoleFactory
from world.fatigue.constants import EffortLevel
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueFactory,
)
from world.scenes.constants import RoundStatus
from world.traits.factories import CheckSystemSetupFactory, StatTraitFactory
from world.vitals.models import CharacterVitals

BRENNA_THREAT = 20
TAUNT_AGGRO = 50
BRUTE_SWING = 12
BRUTE_HEALTH = 50
BLEED_DAMAGE = 6
PC_HEALTH = 100


def _plain_success(*args: object, **kwargs: object) -> MagicMock:
    """A defence roll fixed at success level 0, which takes the swing at full strength."""
    return MagicMock(success_level=0)


class ConditionsThatReachTheFight(JourneyCase):
    """Brenna and Cassian against a brute, with the conditions a technique would lay on them."""

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        self.yard = self.make_room("The Yard")
        self.brenna = self.make_player("Brenna", room=self.yard)
        self.cassian = self.make_player("Cassian", room=self.yard)
        for player in (self.brenna, self.cassian):
            CharacterVitals.objects.create(
                character_sheet=player.sheet_data,
                health=PC_HEALTH,
                max_health=PC_HEALTH,
                base_max_health=PC_HEALTH,
            )

        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=self.yard
        )
        self.brenna_seat = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.brenna.sheet_data,
            status=ParticipantStatus.ACTIVE,
            covenant_role=CovenantRoleFactory(speed_rank=3),
        )
        self.cassian_seat = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.cassian.sheet_data,
            status=ParticipantStatus.ACTIVE,
            covenant_role=CovenantRoleFactory(speed_rank=8),
        )

        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(
            pool=pool,
            base_damage=BRUTE_SWING,
            targeting_mode=TargetingMode.SINGLE,
            target_selection=TargetSelection.HIGHEST_THREAT,
        )
        self.brute = CombatOpponentFactory(
            encounter=self.encounter,
            threat_pool=pool,
            health=BRUTE_HEALTH,
            max_health=BRUTE_HEALTH,
        )
        ThreatRecordFactory(
            encounter=self.encounter,
            opponent=self.brute,
            participant=self.brenna_seat,
            threat_value=BRENNA_THREAT,
        )

        self.taunting_mark = ConditionTemplateFactory(
            name="Taunting Mark", draws_aggro=True, aggro_priority=TAUNT_AGGRO
        )
        self.quickened_step = ConditionTemplateFactory(
            name="Quickened Step", affects_turn_order=True, turn_order_modifier=6
        )
        self.slow_bleed = ConditionTemplateFactory(name="Slow Bleed")
        ConditionDamageOverTimeFactory(
            condition=self.slow_bleed,
            damage_type=DamageTypeFactory(name="Bleed Fire"),
            base_damage=BLEED_DAMAGE,
            scales_with_severity=False,
            scales_with_stacks=False,
        )

        self._give_brenna_a_technique()

    def _give_brenna_a_technique(self) -> None:
        """Brenna knows a technique that does no damage, so only the conditions move health."""
        check_type = CheckTypeFactory()
        CheckTypeTraitFactory(check_type=check_type, trait=StatTraitFactory(), weight=1)
        self.technique = TechniqueFactory(
            gift=GiftFactory(),
            anima_cost=1,
            effect_type=EffectTypeFactory(base_power=10),
            damage_profile=False,
            action_category=ActionCategory.PHYSICAL,
            action_template=ActionTemplateFactory(check_type=check_type),
        )
        sheet = self.brenna.sheet_data
        CharacterTechniqueFactory(character=sheet, technique=self.technique)
        CharacterAnimaFactory(character=sheet, current=20, maximum=30)

    def _brenna_declares(self) -> None:
        """Brenna declares her technique against the brute, the way the web client does."""
        ref = ActionRef(
            backend=ActionBackend.COMBAT,
            technique_id=self.technique.pk,
            action_slot="focused",
        )
        declared = dispatch_player_action(
            self.brenna,
            ref,
            {
                "effort_level": EffortLevel.MEDIUM,
                "focused_opponent_target_id": self.brute.pk,
            },
        )
        self.assertTrue(declared.deferred)

    def _round(self) -> None:
        resolve_round(self.encounter, defense_check_fn=_plain_success)

    def _health(self, player) -> int:
        return CharacterVitals.objects.get(character_sheet=player.sheet_data).health

    def _swing_targets(self) -> list:
        action = CombatOpponentAction.objects.get(opponent=self.brute, round_number=1)
        return list(action.targets.all())

    def _initiative(self) -> list[int]:
        """The initiative order a player sees: ``resolution_order`` on the encounter payload."""
        response = self.api(self.account_of(self.brenna)).get(f"/api/combat/{self.encounter.pk}/")
        self.assertEqual(response.status_code, 200)
        return response.json()["resolution_order"]

    # -- who the brute hits ---------------------------------------------------

    def test_the_brute_hits_the_one_it_has_been_fighting(self) -> None:
        self._brenna_declares()

        self._round()

        self.assertEqual(self._swing_targets(), [self.brenna_seat])
        self.assertEqual(self._health(self.brenna), PC_HEALTH - BRUTE_SWING)
        self.assertEqual(self._health(self.cassian), PC_HEALTH)

    def test_a_taunting_mark_pulls_the_swing_onto_its_bearer(self) -> None:
        apply_condition(self.cassian, self.taunting_mark)
        self._brenna_declares()

        self._round()

        self.assertEqual(self._swing_targets(), [self.cassian_seat])
        self.assertEqual(self._health(self.cassian), PC_HEALTH - BRUTE_SWING)
        self.assertEqual(self._health(self.brenna), PC_HEALTH)
        # The pull is read when the brute chooses; nothing is written to its grudge.
        self.assertEqual(
            list(
                ThreatRecord.objects.filter(opponent=self.brute).values_list(
                    "participant_id", "threat_value"
                )
            ),
            [(self.brenna_seat.pk, BRENNA_THREAT)],
        )

    # -- what happens to the brute --------------------------------------------

    def test_a_bleed_on_the_brute_costs_it_health_when_the_round_ends(self) -> None:
        apply_condition(self.brute.objectdb, self.slow_bleed)
        self._brenna_declares()

        self._round()

        self.brute.refresh_from_db()
        self.assertEqual(self.brute.health, BRUTE_HEALTH - BLEED_DAMAGE)

    def test_a_brute_with_no_bleed_keeps_its_health(self) -> None:
        self._brenna_declares()

        self._round()

        self.brute.refresh_from_db()
        self.assertEqual(self.brute.health, BRUTE_HEALTH)

    # -- who goes first -------------------------------------------------------

    def test_the_quicker_role_goes_first_without_a_quickening(self) -> None:
        self.assertEqual(self._initiative(), [self.brenna_seat.pk, self.cassian_seat.pk])
        self.assertEqual(
            get_resolution_order(self.encounter),
            [("pc", self.brenna_seat), ("pc", self.cassian_seat), ("npc", self.brute)],
        )

    def test_a_quickening_puts_its_bearer_ahead_of_the_quicker_role(self) -> None:
        apply_condition(self.cassian, self.quickened_step)

        self.assertEqual(self._initiative(), [self.cassian_seat.pk, self.brenna_seat.pk])
        self.assertEqual(
            get_resolution_order(self.encounter),
            [("pc", self.cassian_seat), ("pc", self.brenna_seat), ("npc", self.brute)],
        )

    # -- all of it in one round -----------------------------------------------

    def test_one_round_with_all_three_conditions(self) -> None:
        apply_condition(self.cassian, self.taunting_mark)
        apply_condition(self.cassian, self.quickened_step)
        apply_condition(self.brute.objectdb, self.slow_bleed)
        self.assertEqual(self._initiative(), [self.cassian_seat.pk, self.brenna_seat.pk])
        self._brenna_declares()

        self._round()

        self.assertEqual(self._swing_targets(), [self.cassian_seat])
        self.assertEqual(self._health(self.cassian), PC_HEALTH - BRUTE_SWING)
        self.assertEqual(self._health(self.brenna), PC_HEALTH)
        self.brute.refresh_from_db()
        self.assertEqual(self.brute.health, BRUTE_HEALTH - BLEED_DAMAGE)

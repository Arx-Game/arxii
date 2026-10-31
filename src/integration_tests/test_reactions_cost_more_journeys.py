"""Journeys for reactions that cost more each time, and the wound clock (#4810, #4759).

Three things a player sees in one fight in the yard, each through the real combat round
(``resolve_round``) and the real declaration and cast paths:

- **Rising interpose cost.** Brenna declares an interpose over Cassian the way the web
  client does (``combat_interpose`` through dispatch). A brute with three actions swings
  at Cassian three times in one round; Brenna steps into each, and her physical fatigue
  is read back from her real pool after every interpose: 1, 4, 9 (costs 1, 3, 5). Each
  costs more than the one before. Before the fix in this PR the effort floor flattened
  all three to 1.
- **The healer's reactive save.** Sera holds a vow whose role specialises in Mend and
  knows a Mend-tagged technique; Cassian and Dara are her covenant-mates. She declares
  her own technique against a brute for the round. Two brutes each swing 14 at one ally
  standing at 30 of 100 (the knockout line is 20), a blow that would drop each. Sera
  softens both as reactions: each ally ends at 21, her anima is read back, the second
  save costs more than the first, and her own declared action is untouched and rolled.
- **The wound clock.** A brute's 60-point blow wounds Cassian in round 1. Ilse mends it
  through ``cast_technique`` in the same round (closes 45, the 0.75 ceiling x 60) or in
  round 4 (closes 27: 0.75 - 3 x 0.10, x 60) with ``wound_cap_shrink_per_round`` set to
  10 on the real ``MovementConfig`` row. A wound from a fight that has ended, mended in a
  new fight's round 4, closes 45: the clock belongs to the wound's own fight.

Scripted, the way the existing combat journeys script them (``test_holding_the_line``,
``test_mending_a_wound``):

- Defence rolls are fixed at success level 0 (``defense_check_fn``), which takes each
  swing at full strength, and offence rolls at success level 2 (``offense_check_fn``,
  a spy that also records who rolled).
- Brenna's interpose roll is a clean block (success level 2), patched at
  ``perform_check`` in challenge resolution as ``BrennaStandsGuard`` does.
- The wound check is forced to fail (``force_check_outcome``) so a 60-point blow wounds;
  Ilse's cast and its treatment check are forced to Success.

Nothing in the cost, softening or mend arithmetic is mocked. The fatigue and anima
readings use pass-through spies: the real ``apply_fatigue`` and ``deduct_anima`` run, and
the spy reads the pool after each call.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from django.test import override_settings

from actions.constants import ActionBackend
from actions.factories import ActionTemplateFactory
from actions.player_interface import dispatch_player_action
from actions.types import ActionRef
from integration_tests.harness import JourneyCase
from world.areas.positioning.plummet_content import ensure_catch_content
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.checks.test_helpers import force_check_outcome
from world.checks.types import CheckResult
from world.combat.constants import (
    ActionCategory,
    CombatManeuver,
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
from world.combat.interpose_content import ensure_interpose_content
from world.combat.models import CombatRoundAction, MovementConfig
from world.combat.services import begin_declaration_phase, resolve_round
from world.combat.services.encounter.completion import end_encounter
from world.conditions.constants import TreatmentTargetKind
from world.conditions.factories import (
    ConditionCapabilityEffectFactory,
    ConditionTemplateFactory,
    TreatmentTemplateFactory,
)
from world.conditions.models import CapabilityType, ConditionTemplate, TreatmentAttempt
from world.conditions.services import apply_condition, get_active_conditions
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
    CovenantRoleTechniqueSpecialtyFactory,
)
from world.fatigue import services as fatigue_services
from world.fatigue.constants import EffortLevel
from world.fatigue.services import get_or_create_fatigue_pool
from world.magic.constants import TechniqueFunction
from world.magic.factories import (
    BinaryEffectTypeFactory,
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueFactory,
    TechniqueFunctionTagFactory,
)
from world.magic.models import TechniqueTreatment
from world.magic.models.anima import CharacterAnima
from world.magic.models.techniques import ConditionTargetKind
from world.magic.services import anima as anima_services
from world.scenes.constants import RoundStatus
from world.scenes.factories import SceneFactory
from world.scenes.tests.cast_test_helpers import grant_technique
from world.seeds.combat_checks import seed_combat_check_content
from world.traits.factories import CheckOutcomeFactory, CheckSystemSetupFactory, StatTraitFactory
from world.traits.models import (
    CharacterTraitValue,
    CheckOutcome,
    PointConversionRange,
    ResultChart,
    Trait,
    TraitType,
)
from world.vitals.constants import WOUND_CRIPPLING_NAME
from world.vitals.models import CharacterVitals, WoundDetails
from world.vitals.seeds import seed_survivability_content

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.checks.models import CheckType
    from world.combat.models import CombatEncounter, CombatOpponent, CombatParticipant
    from world.magic.models import Technique

PC_HEALTH = 100
SWING = 14
WARD_HEALTH = 30  # knockout line is 20 of 100: a 14 would leave her at 16
SAVED_HEALTH = 21  # just above the line
SERA_ANIMA = 10
FIRST_SAVE = 2  # MovementConfig.dodge_anima_cost default
SECOND_SAVE = 6  # 2 x (1 + reaction_difficulty_step 2 x 1)
WOUND_BLOW = 60
SHRINK_PER_ROUND = 10  # percent, set on the MovementConfig row in the test
SAME_ROUND_MEND = 45  # 0.75 x 60
FOURTH_ROUND_MEND = 27  # (0.75 - 3 x 0.10) x 60

CHALLENGE_PERFORM_CHECK = "world.mechanics.challenge_resolution.perform_check"


def _full_swing(*args: object, **kwargs: object) -> MagicMock:
    """A defence roll fixed at success level 0, which takes the swing at full strength."""
    return MagicMock(success_level=0)


class _TheYard(JourneyCase):
    """A yard, players with vitals, a fight in round 1, and helpers to read the world."""

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        self.yard = self.make_room("The Yard")
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=self.yard
        )
        self.offense_rolls: list[ObjectDB] = []

    def player(self, name: str, *, health: int = PC_HEALTH) -> tuple[ObjectDB, CombatParticipant]:
        character = self.make_player(name, room=self.yard)
        CharacterVitals.objects.create(
            character_sheet=character.sheet_data,
            health=health,
            max_health=PC_HEALTH,
            base_max_health=PC_HEALTH,
        )
        seat = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=character.sheet_data,
            status=ParticipantStatus.ACTIVE,
        )
        return character, seat

    def brute(
        self,
        hates: CombatParticipant,
        *,
        swing: int = SWING,
        actions: int = 1,
        encounter: CombatEncounter | None = None,
    ) -> CombatOpponent:
        """A brute whose one threat entry hits whoever it hates most, for ``swing``."""
        encounter = encounter or self.encounter
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(
            pool=pool,
            base_damage=swing,
            targeting_mode=TargetingMode.SINGLE,
            target_selection=TargetSelection.HIGHEST_THREAT,
        )
        brute = CombatOpponentFactory(
            encounter=encounter,
            threat_pool=pool,
            health=200,
            max_health=200,
            soak_value=0,
            actions_per_round=actions,
        )
        ThreatRecordFactory(encounter=encounter, opponent=brute, participant=hates, threat_value=20)
        return brute

    def _offense(
        self, character: ObjectDB, _check_type: CheckType, *_args: object, **_kwargs: object
    ) -> MagicMock:
        self.offense_rolls.append(character)
        return MagicMock(success_level=2)

    def run_round(self, encounter: CombatEncounter | None = None) -> None:
        resolve_round(
            encounter or self.encounter,
            defense_check_fn=_full_swing,
            offense_check_fn=self._offense,
        )

    def health(self, player: ObjectDB) -> int:
        return CharacterVitals.objects.get(character_sheet=player.sheet_data).health

    def anima(self, player: ObjectDB) -> int:
        return CharacterAnima.objects.get(character=player.sheet_data).current

    def physical_fatigue(self, player: ObjectDB) -> int:
        return get_or_create_fatigue_pool(player.sheet_data).get_current(ActionCategory.PHYSICAL)


@override_settings(SEED_SAMPLE_CONTENT=True)  # ensure_interpose_content gates on #2698
class EachInterposeCostsMore(_TheYard):
    """Brenna declares an interpose over Cassian and steps into three swings in one round."""

    def setUp(self) -> None:
        seed_combat_check_content()
        ensure_interpose_content()
        ensure_catch_content()
        super().setUp()
        ResultChart.clear_cache()
        for trait_type in (TraitType.STAT, TraitType.SKILL):
            PointConversionRange.objects.get_or_create(
                trait_type=trait_type,
                min_value=1,
                defaults={"max_value": 100, "points_per_level": 1},
            )
        self.brenna, self.brenna_seat = self.player("Brenna")
        self.cassian, self.cassian_seat = self.player("Cassian")
        telekinetic = ConditionTemplateFactory(name="Telekinetic Reach")
        ConditionCapabilityEffectFactory(
            condition=telekinetic,
            capability=CapabilityType.objects.get(name="telekinesis"),
            value=10,
        )
        apply_condition(self.brenna, telekinetic)
        for name, value in (("wits", 30), ("agility", 1), ("Melee Combat", 1)):
            CharacterTraitValue.objects.create(
                character=self.brenna.sheet_data, trait=Trait.objects.get(name=name), value=value
            )
        self.brute(self.cassian_seat, actions=3)
        self.clean_block = CheckOutcomeFactory(name="Yard-Clean-Block", success_level=2)

    def _interpose_roll(
        self, _character: ObjectDB, check_type: CheckType, *_args: object, **_kwargs: object
    ) -> CheckResult:
        return CheckResult(
            check_type=check_type,
            outcome=self.clean_block,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )

    def test_each_interpose_in_the_round_costs_brenna_more_fatigue(self) -> None:
        declared = self.web(
            self.brenna, "combat_interpose", ally_participant_id=self.cassian_seat.pk
        )
        self.assertTrue(declared.detail.success, declared.detail.message)

        readings: list[int] = []
        real_apply = fatigue_services.apply_fatigue

        def reading_the_pool(sheet, category, base_cost, effort_level):
            charged = real_apply(sheet, category, base_cost, effort_level)
            if sheet == self.brenna.sheet_data:
                readings.append(self.physical_fatigue(self.brenna))
            return charged

        with (
            patch(CHALLENGE_PERFORM_CHECK, side_effect=self._interpose_roll),
            patch(
                "world.combat.services.damage.interception.apply_fatigue",
                side_effect=reading_the_pool,
            ),
        ):
            self.run_round()

        costs = [after - before for before, after in zip([0, *readings], readings, strict=False)]
        self.assertEqual(self.health(self.cassian), PC_HEALTH)
        self.brenna_seat.refresh_from_db()
        self.assertEqual(self.brenna_seat.reactions_used, 3)
        self.assertEqual(len(costs), 3, readings)
        self.assertLess(costs[0], costs[1], costs)
        self.assertLess(costs[1], costs[2], costs)
        # Very low effort (a declared interpose): 3 x 0.1 floored at 1, then x (1 + 2k).
        self.assertEqual(costs, [1, 3, 5])
        self.assertEqual(readings, [1, 4, 9])


class TheHealersSave(_TheYard):
    """Sera, her own turn declared, softens two blows that would drop her covenant-mates."""

    def setUp(self) -> None:
        super().setUp()
        self.sera, self.sera_seat = self.player("Sera")
        self.cassian, self.cassian_seat = self.player("Cassian", health=WARD_HEALTH)
        self.dara, self.dara_seat = self.player("Dara", health=WARD_HEALTH)

        covenant = CovenantFactory()
        mender = CovenantRoleFactory(name="Mender")
        CovenantRoleTechniqueSpecialtyFactory(covenant_role=mender, function=TechniqueFunction.MEND)
        CharacterCovenantRoleFactory(
            character_sheet=self.sera.sheet_data,
            covenant=covenant,
            covenant_role=mender,
            engaged=True,
        )
        for ally in (self.cassian, self.dara):
            CharacterCovenantRoleFactory(
                character_sheet=ally.sheet_data, covenant=covenant, engaged=True
            )
        mend = TechniqueFunctionTagFactory(function=TechniqueFunction.MEND)
        CharacterTechniqueFactory(character=self.sera.sheet_data, technique=mend.technique)
        CharacterAnimaFactory(character=self.sera.sheet_data, current=SERA_ANIMA, maximum=20)

        self.first_brute = self.brute(self.cassian_seat)
        self.second_brute = self.brute(self.dara_seat)
        self.her_turn = self._a_technique_of_her_own()

    def _a_technique_of_her_own(self) -> Technique:
        """A social technique with no anima cost, so her anima moves only for the saves."""
        check_type = CheckTypeFactory()
        CheckTypeTraitFactory(check_type=check_type, trait=StatTraitFactory(), weight=1)
        technique = TechniqueFactory(
            gift=GiftFactory(),
            anima_cost=0,
            effect_type=EffectTypeFactory(base_power=10),
            damage_profile=False,
            action_category=ActionCategory.SOCIAL,
            action_template=ActionTemplateFactory(check_type=check_type),
        )
        CharacterTechniqueFactory(character=self.sera.sheet_data, technique=technique)
        return technique

    def test_she_softens_both_blows_each_costs_more_and_keeps_her_turn(self) -> None:
        ref = ActionRef(
            backend=ActionBackend.COMBAT, technique_id=self.her_turn.pk, action_slot="focused"
        )
        declared = dispatch_player_action(
            self.sera,
            ref,
            {
                "effort_level": EffortLevel.MEDIUM,
                "focused_opponent_target_id": self.first_brute.pk,
            },
        )
        self.assertTrue(declared.deferred)
        before = CombatRoundAction.objects.get(participant=self.sera_seat, round_number=1)
        declared_fields = (
            before.focused_action_id,
            before.focused_opponent_target_id,
            before.maneuver,
            before.effort_level,
        )

        sera_after_each: list[int] = []
        real_deduct = anima_services.deduct_anima

        def reading_her_anima(character, amount, *args, **kwargs):
            result = real_deduct(character, amount, *args, **kwargs)
            if character == self.sera:
                sera_after_each.append(self.anima(self.sera))
            return result

        with patch.object(anima_services, "deduct_anima", side_effect=reading_her_anima):
            self.run_round()

        self.assertEqual(self.health(self.cassian), SAVED_HEALTH)
        self.assertEqual(self.health(self.dara), SAVED_HEALTH)
        self.assertEqual(
            sera_after_each, [SERA_ANIMA - FIRST_SAVE, SERA_ANIMA - FIRST_SAVE - SECOND_SAVE]
        )
        self.assertEqual(self.anima(self.sera), SERA_ANIMA - FIRST_SAVE - SECOND_SAVE)
        self.sera_seat.refresh_from_db()
        self.assertEqual(self.sera_seat.reactions_used, 2)
        # Her own declared action is the one row she has, unchanged, and it rolled.
        after = CombatRoundAction.objects.get(participant=self.sera_seat, round_number=1)
        self.assertEqual(after.pk, before.pk)
        self.assertEqual(
            (
                after.focused_action_id,
                after.focused_opponent_target_id,
                after.maneuver,
                after.effort_level,
            ),
            declared_fields,
        )
        self.assertNotEqual(after.maneuver, CombatManeuver.INTERPOSE)
        self.assertEqual(self.offense_rolls, [self.sera])


class _FixedTreatmentCheck:
    """Minimal stand-in for a ``CheckResult``: just what ``perform_treatment`` reads."""

    def __init__(self, outcome: CheckOutcome) -> None:
        self.outcome = outcome
        self.success_level = outcome.success_level


@contextmanager
def casting_well() -> Iterator[None]:
    """The cast's own check, and the treatment's check inside it, land at Success."""
    success = CheckOutcome.objects.get(name="Success")
    with (
        patch(
            "world.conditions.services.perform_check_with_modifiers",
            return_value=_FixedTreatmentCheck(success),
        ),
        force_check_outcome(success),
    ):
        yield


@override_settings(SEED_SAMPLE_CONTENT=True)  # the survivability seed gates on #2698
class TheWoundClock(_TheYard):
    """Cassian is wounded in round 1; Ilse mends it in round 1, in round 4, or in a new fight."""

    def setUp(self) -> None:
        seed_survivability_content()
        super().setUp()
        config = MovementConfig.objects.cached_singleton() or MovementConfig(pk=1)
        config.wound_cap_shrink_per_round = SHRINK_PER_ROUND
        config.save()
        SceneFactory(room=self.yard)
        self.cassian, self.cassian_seat = self.player("Cassian")
        self.ilse = self.make_player("Ilse", room=self.yard)
        CharacterAnimaFactory(character=self.ilse.sheet_data, current=20, maximum=30)
        self.mend = self._a_mending_technique()
        grant_technique(self.ilse.sheet_data.primary_persona, self.mend)
        self.wound_failure = CheckOutcomeFactory(name="Failure", success_level=-1)

    def _a_mending_technique(self) -> Technique:
        check_type = CheckTypeFactory()
        CheckTypeTraitFactory(check_type=check_type, trait=StatTraitFactory(), weight=1)
        self.binding = TreatmentTemplateFactory(
            name="Binding the Wound",
            target_kind=TreatmentTargetKind.PRIMARY,
            target_condition=ConditionTemplate.objects.get(name=WOUND_CRIPPLING_NAME),
            check_type=CheckTypeFactory(),
            target_difficulty=0,
            scene_required=False,
            once_per_scene_per_helper=False,
            reduction_on_crit=0,
            reduction_on_success=0,
            reduction_on_partial=0,
            mend_on_crit=60,
            mend_on_success=60,
            mend_on_partial=60,
        )
        technique = TechniqueFactory(
            name="Field Mend",
            gift=GiftFactory(),
            anima_cost=1,
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_template=ActionTemplateFactory(check_type=check_type),
        )
        TechniqueTreatment.objects.create(
            technique=technique,
            treatment_template=self.binding,
            target_kind=ConditionTargetKind.ALLY,
            minimum_success_level=1,
            mend_cap_fraction=Decimal("0.75"),
        )
        return technique

    def _wounded_in_round_one(self) -> WoundDetails:
        self.brute(self.cassian_seat, swing=WOUND_BLOW)
        with force_check_outcome(self.wound_failure):
            self.run_round()
        self.assertEqual(self.health(self.cassian), PC_HEALTH - WOUND_BLOW)
        crippling = ConditionTemplate.objects.get(name=WOUND_CRIPPLING_NAME)
        instance = get_active_conditions(self.cassian, condition=crippling).get()
        details = WoundDetails.objects.get(condition_instance=instance)
        self.assertEqual(details.damage_taken, WOUND_BLOW)
        return details

    def _mend(self) -> int:
        with casting_well():
            result = self.web(
                self.ilse,
                "cast_technique",
                technique_id=self.mend.pk,
                target_persona_id=self.cassian.sheet_data.primary_persona.pk,
            )
        self.assertTrue(result.detail.success, result.detail.message)
        return TreatmentAttempt.objects.get(
            helper=self.ilse.sheet_data, target=self.cassian.sheet_data, treatment=self.binding
        ).health_mended

    def _advance_to_round_four(self, encounter: CombatEncounter) -> None:
        # Each round closes to Between Rounds before the next opens, as resolving a round does.
        for _ in range(3):
            encounter.status = RoundStatus.BETWEEN_ROUNDS
            encounter.save(update_fields=["status"])
            begin_declaration_phase(encounter)
        encounter.refresh_from_db()
        self.assertEqual(encounter.round_number, 4)

    def test_a_mend_in_the_round_of_the_wound_closes_the_full_share(self) -> None:
        self._wounded_in_round_one()

        self.assertEqual(self._mend(), SAME_ROUND_MEND)
        self.assertEqual(self.health(self.cassian), PC_HEALTH - WOUND_BLOW + SAME_ROUND_MEND)

    def test_a_mend_three_rounds_later_closes_less(self) -> None:
        self._wounded_in_round_one()
        self._advance_to_round_four(self.encounter)

        self.assertEqual(self._mend(), FOURTH_ROUND_MEND)
        self.assertEqual(self.health(self.cassian), PC_HEALTH - WOUND_BLOW + FOURTH_ROUND_MEND)

    def test_a_wound_from_a_fight_that_ended_does_not_shrink(self) -> None:
        self._wounded_in_round_one()
        end_encounter(self.encounter)
        next_fight = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=self.yard
        )
        CombatParticipantFactory(
            encounter=next_fight,
            character_sheet=self.cassian.sheet_data,
            status=ParticipantStatus.ACTIVE,
        )
        self._advance_to_round_four(next_fight)

        self.assertEqual(self._mend(), SAME_ROUND_MEND)

"""Journeys for holding the line (#4584).

Conditions that answer a blow. Brenna (a warden and bodyguard) and Cassian (a scout and healer)
stand against a hired brute whose one attack goes to whoever it hates most. A challenge turns the
brute onto Brenna, a thorn ward on Cassian strikes the brute back, Brenna's standing guard steps
into the brute's swing at Cassian, a once-only blessing helps one roll and is gone, and a
once-only grace keeps Cassian on his feet through one knockout.

Every expected number below is an authored value on a row built in ``setUp`` or in the test,
not something read back from the code under test:

- The brute has 50 health and no soak. Its one threat entry swings for 12 at its highest threat.
- Cassian has 20 threat with the brute and Brenna none, so unprovoked the brute hits Cassian.
- Both players have 100 health. Brenna has 20 of 30 anima.
- Defence rolls are fixed at success level 0, which takes a swing at full strength. Brenna's
  offence rolls are fixed at success level 2 by a spy that records each roll.
- Brenna's techniques are SOCIAL, so their own fatigue never lands in her physical pool.
- "Called Out" (forces an attack on its source, 3 rounds) is what Brenna's challenge lays on
  the brute. It takes hold from the round after it lands.
- "Thorn Ward" (strike back 5 "Thorn" damage and lay Called Out, costing its caster 2 anima)
  sits on Cassian with Brenna as its source: 50 - 5 = 45 brute health, 20 - 2 = 18 anima.
- "Bodyguard's Watch" (the source guards the bearer) sits on Cassian with Brenna as its source.
  Her interpose roll is fixed at success level 2, a clean block, and a standing guard pays the
  interpose base fatigue 3 at very low effort (x 0.1), floored at 1: 1 physical fatigue. She
  has one reaction a round, so a brute with 2 actions lands its second blow (100 - 12 = 88).
- "Steadying Word" (once only) and "Steady Hand" (3 rounds) each add 3 to Brenna's technique
  check. A look at the roll (``collect_check_modifiers``, which the consider check and the
  standoff grade view call; other previews use their own paths) counts the +3 and spends
  nothing.
- "Stay Standing" (once only, stops a knockout) sits on Cassian at 15 of 100 health while the
  brute swings for 2: 13 of 100 is inside the knockout band, the knockout roll is forced to
  fail, and the knockout pool's only result for that failure is Unconscious.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from django.test import override_settings

from actions.constants import ActionBackend
from actions.factories import (
    ActionTemplateFactory,
    ConsequencePoolEntryFactory,
    ConsequencePoolFactory,
)
from actions.player_interface import dispatch_player_action
from actions.types import ActionRef
from integration_tests.harness import JourneyCase
from world.areas.positioning.plummet_content import ensure_catch_content
from world.checks.constants import EffectType
from world.checks.factories import (
    CheckTypeFactory,
    CheckTypeTraitFactory,
    ConsequenceEffectFactory,
    ConsequenceFactory,
)
from world.checks.services import collect_check_modifiers
from world.checks.test_helpers import force_check_outcome
from world.checks.types import CheckResult
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
from world.combat.interpose_content import ensure_interpose_content
from world.combat.models import CombatOpponentAction
from world.combat.services import begin_declaration_phase, resolve_round
from world.conditions.constants import DurationType
from world.conditions.factories import (
    ConditionCapabilityEffectFactory,
    ConditionCheckModifierFactory,
    ConditionTemplateFactory,
    DamageTypeFactory,
    UnconsciousConditionFactory,
)
from world.conditions.models import CapabilityType, ConditionInstance, ConditionTemplate
from world.conditions.services import apply_condition
from world.fatigue.constants import EffortLevel
from world.fatigue.services import get_or_create_fatigue_pool
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueAppliedConditionFactory,
    TechniqueFactory,
)
from world.magic.models.anima import CharacterAnima
from world.scenes.constants import RoundStatus
from world.seeds.combat_checks import seed_combat_check_content
from world.traits.factories import CheckOutcomeFactory, CheckSystemSetupFactory, StatTraitFactory
from world.traits.models import (
    CharacterTraitValue,
    PointConversionRange,
    ResultChart,
    Trait,
    TraitType,
)
from world.vitals.models import CharacterVitals
from world.vitals.services import get_vitals_consequence_config

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.checks.models import CheckType
    from world.combat.models import CombatParticipant
    from world.magic.models import Gift, Technique
    from world.traits.models import CheckOutcome

PC_HEALTH = 100
BRUTE_HEALTH = 50
BRUTE_SWING = 12
CASSIAN_THREAT = 20
BRENNA_ANIMA = 20
OFFENSE_SUCCESS = 2
THORN_DAMAGE = 5
THORN_COST = 2
BLESSING = 3
GRACE_HEALTH = 15
GRACE_SWING = 2
GUARD_FATIGUE = 1  # interpose base 3 x very low effort 0.1, floored at 1

CHALLENGE_PERFORM_CHECK = "world.mechanics.challenge_resolution.perform_check"


def _full_swing(*args: object, **kwargs: object) -> MagicMock:
    """A defence roll fixed at success level 0, which takes the swing at full strength."""
    return MagicMock(success_level=0)


class _TheYard(JourneyCase):
    """Brenna and Cassian against a brute in the yard: the cast, the round and the readings."""

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
        )
        self.cassian_seat = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.cassian.sheet_data,
            status=ParticipantStatus.ACTIVE,
        )

        pool = ThreatPoolFactory()
        self.swing = ThreatPoolEntryFactory(
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
            soak_value=0,
        )
        ThreatRecordFactory(
            encounter=self.encounter,
            opponent=self.brute,
            participant=self.cassian_seat,
            threat_value=CASSIAN_THREAT,
        )

        self.called_out = ConditionTemplateFactory(
            name="Called Out",
            forces_attack_on_source=True,
            default_duration_type=DurationType.ROUNDS,
            default_duration_value=3,
        )
        self._give_brenna_her_techniques()
        self.offense_calls: list[tuple[ObjectDB, CheckType, int]] = []

    def _give_brenna_her_techniques(self) -> None:
        """A plain technique and a challenge that calls the target out, neither dealing damage."""
        self.technique_check_type = CheckTypeFactory()
        CheckTypeTraitFactory(
            check_type=self.technique_check_type, trait=StatTraitFactory(), weight=1
        )
        gift = GiftFactory()
        self.plain = self._social_technique(gift)
        self.challenge = self._social_technique(gift)
        TechniqueAppliedConditionFactory(
            technique=self.challenge, condition=self.called_out, target_kind="enemy"
        )
        sheet = self.brenna.sheet_data
        CharacterTechniqueFactory(character=sheet, technique=self.plain)
        CharacterTechniqueFactory(character=sheet, technique=self.challenge)
        CharacterAnimaFactory(character=sheet, current=BRENNA_ANIMA, maximum=30)

    def _social_technique(self, gift: Gift) -> Technique:
        return TechniqueFactory(
            gift=gift,
            anima_cost=1,
            effect_type=EffectTypeFactory(base_power=10),
            damage_profile=False,
            action_category=ActionCategory.SOCIAL,
            action_template=ActionTemplateFactory(check_type=self.technique_check_type),
        )

    # -- driving the round ----------------------------------------------------

    def _brenna_declares(self, technique: Technique) -> None:
        """Brenna declares a technique against the brute, the way the web client does."""
        ref = ActionRef(
            backend=ActionBackend.COMBAT,
            technique_id=technique.pk,
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

    def _offense(
        self, character: ObjectDB, check_type: CheckType, *_args: object, **kwargs: object
    ) -> MagicMock:
        """Brenna's offence roll: success level 2, and a note of what it was asked."""
        self.offense_calls.append((character, check_type, kwargs.get("extra_modifiers", 0)))
        return MagicMock(success_level=OFFENSE_SUCCESS)

    def _round(self) -> None:
        resolve_round(self.encounter, defense_check_fn=_full_swing, offense_check_fn=self._offense)

    def _next_round(self) -> None:
        begin_declaration_phase(self.encounter)

    # -- reading the world ----------------------------------------------------

    def _health(self, player: ObjectDB) -> int:
        return CharacterVitals.objects.get(character_sheet=player.sheet_data).health

    def _anima(self, player: ObjectDB) -> int:
        return CharacterAnima.objects.get(character=player.sheet_data).current

    def _physical_fatigue(self, player: ObjectDB) -> int:
        return get_or_create_fatigue_pool(player.sheet_data).get_current(ActionCategory.PHYSICAL)

    def _has(self, target: ObjectDB, template: ConditionTemplate) -> bool:
        return ConditionInstance.objects.filter(target=target, condition=template).exists()

    def _swing_targets(self, *, round_number: int) -> list[CombatParticipant]:
        action = CombatOpponentAction.objects.get(opponent=self.brute, round_number=round_number)
        return list(action.targets.all())


class HoldingTheLine(_TheYard):
    """A challenge, a thorn ward, a blessing and a grace, each through the combat round."""

    # -- a challenge ----------------------------------------------------------

    def test_a_challenge_turns_the_brute_onto_brenna_next_round(self) -> None:
        self._brenna_declares(self.challenge)
        self._round()

        # The brute chose before the challenge landed, so this round it still hits Cassian.
        self.assertEqual(self._swing_targets(round_number=1), [self.cassian_seat])
        self.assertEqual(self._health(self.cassian), PC_HEALTH - BRUTE_SWING)
        called = ConditionInstance.objects.get(
            target=self.brute.objectdb, condition=self.called_out
        )
        self.assertEqual(called.source_character, self.brenna)

        self._next_round()
        self._brenna_declares(self.plain)
        self._round()

        self.assertEqual(self._swing_targets(round_number=2), [self.brenna_seat])
        self.assertEqual(self._health(self.brenna), PC_HEALTH - BRUTE_SWING)
        self.assertEqual(self._health(self.cassian), PC_HEALTH - BRUTE_SWING)

    # -- a thorn ward ---------------------------------------------------------

    def test_a_thorn_ward_strikes_back_and_calls_the_brute_onto_brenna(self) -> None:
        thorn_ward = ConditionTemplateFactory(
            name="Thorn Ward",
            retaliation_damage=THORN_DAMAGE,
            retaliation_damage_type=DamageTypeFactory(name="Thorn"),
            retaliation_condition=self.called_out,
            reactive_anima_cost=THORN_COST,
        )
        apply_condition(self.cassian, thorn_ward, source_character=self.brenna)

        self._round()

        self.assertEqual(self._swing_targets(round_number=1), [self.cassian_seat])
        self.assertEqual(self._health(self.cassian), PC_HEALTH - BRUTE_SWING)
        self.brute.refresh_from_db()
        self.assertEqual(self.brute.health, BRUTE_HEALTH - THORN_DAMAGE)
        self.assertEqual(self._anima(self.brenna), BRENNA_ANIMA - THORN_COST)
        called = ConditionInstance.objects.get(
            target=self.brute.objectdb, condition=self.called_out
        )
        self.assertEqual(called.source_character, self.brenna)
        # A lasting ward is not spent by striking back.
        self.assertTrue(self._has(self.cassian, thorn_ward))

        self._next_round()
        self._round()

        self.assertEqual(self._swing_targets(round_number=2), [self.brenna_seat])
        self.assertEqual(self._health(self.brenna), PC_HEALTH - BRUTE_SWING)

    # -- a once-only blessing -------------------------------------------------

    def test_a_steadying_word_helps_one_offense_roll_and_survives_a_look(self) -> None:
        steadying_word = ConditionTemplateFactory(
            name="Steadying Word", default_duration_type=DurationType.UNTIL_USED
        )
        ConditionCheckModifierFactory(
            condition=steadying_word,
            check_type=self.technique_check_type,
            modifier_value=BLESSING,
        )
        apply_condition(self.brenna, steadying_word)
        blessing_pk = ConditionInstance.objects.get(target=self.brenna, condition=steadying_word).pk

        # A look at the roll is what the consider check and the standoff grade view ask
        # (``collect_check_modifiers``): it counts the blessing's +3 and spends nothing.
        look = collect_check_modifiers(self.brenna.sheet_data, self.technique_check_type)
        self.assertIn(
            (blessing_pk, BLESSING),
            [(c.condition_instance_id, c.value) for c in look.contributions],
        )
        self.assertTrue(self._has(self.brenna, steadying_word))

        self._brenna_declares(self.plain)
        self._round()

        self.assertFalse(self._has(self.brenna, steadying_word))

        self._next_round()
        self._brenna_declares(self.plain)
        self._round()

        (_, first_type, first_extra), (_, second_type, second_extra) = self.offense_calls
        self.assertEqual(first_type, self.technique_check_type)
        self.assertEqual(second_type, self.technique_check_type)
        self.assertEqual(first_extra - second_extra, BLESSING)

    def test_a_lasting_blessing_is_not_spent_by_a_roll(self) -> None:
        steady_hand = ConditionTemplateFactory(
            name="Steady Hand",
            default_duration_type=DurationType.ROUNDS,
            default_duration_value=3,
        )
        ConditionCheckModifierFactory(
            condition=steady_hand,
            check_type=self.technique_check_type,
            modifier_value=BLESSING,
        )
        # A round without the blessing is the baseline roll.
        self._brenna_declares(self.plain)
        self._round()

        apply_condition(self.brenna, steady_hand)
        self._next_round()
        self._brenna_declares(self.plain)
        self._round()

        (_, _, baseline_extra), (_, blessed_type, blessed_extra) = self.offense_calls
        self.assertEqual(blessed_type, self.technique_check_type)
        self.assertEqual(blessed_extra - baseline_extra, BLESSING)
        self.assertTrue(self._has(self.brenna, steady_hand))

    # -- a once-only grace ----------------------------------------------------

    @override_settings(SEED_SAMPLE_CONTENT=True)  # the Endurance check type gates on #2698
    def test_stay_standing_stops_one_knockout(self) -> None:
        vitals = CharacterVitals.objects.get(character_sheet=self.cassian.sheet_data)
        vitals.health = GRACE_HEALTH
        vitals.save(update_fields=["health"])
        self.swing.base_damage = GRACE_SWING
        self.swing.save(update_fields=["base_damage"])
        unconscious = UnconsciousConditionFactory()
        failure = self._knockout_pool_of(unconscious)
        stay_standing = ConditionTemplateFactory(
            name="Stay Standing",
            prevents_knockout=True,
            default_duration_type=DurationType.UNTIL_USED,
        )
        apply_condition(self.cassian, stay_standing)

        with force_check_outcome(failure):
            self._round()

        self.assertEqual(self._health(self.cassian), GRACE_HEALTH - GRACE_SWING)
        self.assertFalse(self._has(self.cassian, unconscious))
        self.assertFalse(self._has(self.cassian, stay_standing))

        self._next_round()
        with force_check_outcome(failure):
            self._round()

        self.assertEqual(self._health(self.cassian), GRACE_HEALTH - 2 * GRACE_SWING)
        self.assertTrue(self._has(self.cassian, unconscious))

    def _knockout_pool_of(self, unconscious: ConditionTemplate) -> CheckOutcome:
        """The knockout pool: a failed knockout roll applies Unconscious. Returns that failure."""
        failure = CheckOutcomeFactory(name="Holding-KO-Failure", success_level=-1)
        consequence = ConsequenceFactory(outcome_tier=failure, character_loss=False)
        ConsequenceEffectFactory(
            consequence=consequence,
            effect_type=EffectType.APPLY_CONDITION,
            condition_template=unconscious,
            target="self",
        )
        pool = ConsequencePoolFactory()
        ConsequencePoolEntryFactory(pool=pool, consequence=consequence)
        config = get_vitals_consequence_config()
        config.knockout_pool = pool
        config.save(update_fields=["knockout_pool"])
        return failure


@override_settings(SEED_SAMPLE_CONTENT=True)  # ensure_interpose_content gates on #2698
class BrennaStandsGuard(_TheYard):
    """Brenna's standing guard over Cassian: she steps into the brute's swing without declaring.

    The interpose content is seeded the way ``test_guardian_reactions`` seeds it, Brenna is
    granted telekinesis (an interpose capability) by a condition and built for Reflexes, and her
    interpose roll is fixed at success level 2.
    """

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

        telekinetic = ConditionTemplateFactory(name="Telekinetic Reach")
        ConditionCapabilityEffectFactory(
            condition=telekinetic,
            capability=CapabilityType.objects.get(name="telekinesis"),
            value=10,
        )
        apply_condition(self.brenna, telekinetic)
        sheet = self.brenna.sheet_data
        for name, value in (("wits", 30), ("agility", 1), ("Melee Combat", 1)):
            CharacterTraitValue.objects.create(
                character=sheet, trait=Trait.objects.get(name=name), value=value
            )

        self.bodyguards_watch = ConditionTemplateFactory(
            name="Bodyguard's Watch", source_guards_bearer=True
        )
        apply_condition(self.cassian, self.bodyguards_watch, source_character=self.brenna)
        self.clean_block = CheckOutcomeFactory(name="Holding-Clean-Block", success_level=2)

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

    def _guarded_round(self) -> None:
        with patch(CHALLENGE_PERFORM_CHECK, side_effect=self._interpose_roll):
            self._round()

    def test_brenna_guards_cassian_and_still_takes_her_turn(self) -> None:
        self._brenna_declares(self.plain)

        self._guarded_round()

        self.assertEqual(self._swing_targets(round_number=1), [self.cassian_seat])
        self.assertEqual(self._health(self.cassian), PC_HEALTH)
        self.assertEqual(self._health(self.brenna), PC_HEALTH)
        self.assertEqual(self._physical_fatigue(self.brenna), GUARD_FATIGUE)
        self.brenna_seat.refresh_from_db()
        self.assertEqual(self.brenna_seat.reactions_used, 1)
        # Her own declared turn still rolled.
        self.assertEqual([call[0] for call in self.offense_calls], [self.brenna])

    def test_past_her_reaction_the_second_blow_lands_and_brenna_is_told(self) -> None:
        self.brute.actions_per_round = 2
        self.brute.save(update_fields=["actions_per_round"])
        self.watch(self.brenna)

        self._guarded_round()

        self.assertEqual(self._health(self.cassian), PC_HEALTH - BRUTE_SWING)
        self.assertEqual(self._physical_fatigue(self.brenna), GUARD_FATIGUE)
        self.assertShownRow(self.brenna, "You have already spent your reaction this round")

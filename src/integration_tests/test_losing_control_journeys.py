"""Losing control to a trigger (#4802): the moon, a wound, a condition stage.

Three people each carry a vulnerability and meet its trigger:
- Garrick bears a wound-triggered rage (fires below 50 percent of 100 health). A failed
  roll applies Berserk at severity 3 for 3 rounds; a Success does nothing.
- Maren bears a curse with three stages; entering stage 3 fires its trigger.
- Wynn is a lycan under a clear full moon (pull 10) at level 1 with a gift thread at
  level 2, so the seeded moon trigger's difficulty is hand-worked:
  20 base + 5 x 10 pull - 10 x 1 level - min(30, 5 x 2 thread) = 50.
Every roll is forced to the outcome a journey wants (``force_check_outcome``), which also
records the difficulty the roll was made at.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from django.test import override_settings

from actions.constants import ActionTargetType
from evennia_extensions.factories import CharacterFactory
from integration_tests.harness import JourneyCase
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.services import perform_check
from world.checks.test_helpers import force_check_outcome
from world.classes.factories import CharacterClassLevelFactory
from world.combat.constants import (
    ActionCategory,
    CombatManeuver,
    EncounterType,
    ParticipantStatus,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    EscalationCurveFactory,
    SocialManeuverConfigFactory,
)
from world.combat.models import CombatParticipant, CombatRoundAction, FleeConfig, MovementConfig
from world.combat.services import leave_encounter, resolve_round
from world.combat.services.damage.damage import apply_damage_to_participant
from world.conditions.berserk_content import ensure_berserk_content, outcome_at_level
from world.conditions.constants import CompulsionResult, ControlLossFiresOn
from world.conditions.factories import (
    CapabilityTypeFactory,
    CompulsionFactory,
    CompulsionResistBandFactory,
    ConditionCategoryFactory,
    ConditionCheckModifierFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
    ControlLossBandFactory,
    ControlLossTriggerFactory,
)
from world.conditions.services import (
    advance_condition_severity,
    apply_condition,
    get_active_conditions,
)
from world.forms.constants import AlternateSelfRevertKind
from world.forms.factories import (
    AlternateSelfFactory,
    CharacterFormFactory,
    CharacterFormStateFactory,
)
from world.forms.models import ActiveAlternateSelf, FormType
from world.forms.services import RevertBlockedError, revert_alternate_self
from world.forms.services.transformation import trigger_transformation
from world.game_clock.constants import TimePhase
from world.magic.constants import TargetKind, TechniqueReach
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterGiftFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueFactory,
    ThreadFactory,
)
from world.magic.models import CharacterTechnique
from world.magic.models.anima import CharacterAnima
from world.magic.seeds_cast import ensure_technique_cast_content
from world.magic.services.fury import get_berserk_template
from world.magic.types.techniques import SoulfrayWarning
from world.mechanics.factories import ModifierCategoryFactory
from world.mechanics.models import CharacterModifier, ModifierSource, ModifierTarget
from world.relationships.constants import TypeValence
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipLabelFactory,
    RelationshipTypeFactory,
)
from world.scenes.constants import PersonaType, RoundStatus
from world.scenes.factories import PersonaFactory
from world.species.factories import SpeciesFactory, SpeciesGiftGrantFactory
from world.species.moon_provisioning import (
    SEED_LYCAN_GIFT_NAME,
    SEED_LYCAN_SPECIES_NAME,
    ensure_lycan_blood_condition,
    ensure_moon_control_loss_trigger,
)
from world.species.tasks import moon_reconcile_tick
from world.traits.factories import CheckSystemSetupFactory
from world.traits.services import ensure_canonical_check_outcome
from world.vitals.models import CharacterVitals


def _berserk_of(character):
    berserk = get_berserk_template()
    return next((i for i in get_active_conditions(character) if i.condition_id == berserk.pk), None)


COMPELLED_PAYLOAD_QUERIES = 6


class _ControlLossCase(JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        ensure_berserk_content()
        self.berserk = get_berserk_template()
        self.failure = ensure_canonical_check_outcome("Failure")
        self.success = ensure_canonical_check_outcome("Success")

    def band(self, trigger, outcome, *, applies=None) -> None:
        extra = {"applies": applies, "severity": 3, "duration_rounds": 3} if applies else {}
        ControlLossBandFactory(trigger=trigger, outcome=outcome, **extra)


class WoundTriggers(_ControlLossCase):
    def setUp(self) -> None:
        super().setUp()
        self.field = self.make_room("The Field")
        self.garrick = self.make_player("Garrick", room=self.field)
        self.sheet = self.garrick.sheet_data
        self.vitals = CharacterVitals.objects.create(
            character_sheet=self.sheet, health=100, max_health=100, base_max_health=100
        )
        self.rage = ConditionTemplateFactory(name="Wound rage")
        apply_condition(self.garrick, self.rage)
        self.trigger = ControlLossTriggerFactory(
            vulnerability=self.rage, fires_on=ControlLossFiresOn.WOUND_THRESHOLD,
            health_below_percent=50, base_difficulty=30,
        )  # fmt: skip
        self.band(self.trigger, self.failure, applies=self.berserk)
        self.band(self.trigger, self.success)
        encounter = CombatEncounterFactory(room=self.field)
        self.seat = CombatParticipantFactory(encounter=encounter, character_sheet=self.sheet)

    def hit(self, damage: int) -> None:
        apply_damage_to_participant(self.seat, damage)

    def test_wound_below_threshold_rolls_and_failure_applies_berserk(self) -> None:
        self.watch(self.garrick)
        with force_check_outcome(self.failure) as capture:
            self.hit(60)

        berserk = _berserk_of(self.garrick)
        self.assertIsNotNone(berserk)
        self.assertEqual(berserk.severity, 3)
        self.assertEqual(capture.target_difficulty, 30)
        self.assertTold(self.garrick, "You fight to keep control.")
        self.assertTold(self.garrick, "You lose control: Berserk.")

    def test_the_room_sees_the_loss_of_control(self) -> None:
        witness = self.make_player("Witness", room=self.field)
        self.watch(witness)
        with force_check_outcome(self.failure):
            self.hit(60)

        self.assertTold(witness, "Garrick loses control: Berserk.")

    def test_a_hit_that_knocks_the_character_out_rolls_no_wound_trigger(self) -> None:
        with (
            patch("world.checks.services.perform_check", wraps=perform_check) as rolled,
            force_check_outcome(self.failure),
        ):
            self.hit(90)

        self.assertEqual(rolled.call_count, 0)
        self.assertIsNone(_berserk_of(self.garrick))

    def test_a_held_roll_applies_nothing(self) -> None:
        with force_check_outcome(self.success):
            self.hit(60)

        self.assertIsNone(_berserk_of(self.garrick))

    def test_wound_trigger_fires_on_each_downward_crossing(self) -> None:
        """100 to 60 stays above 50 (no roll); healed to 70, 70 to 40 crosses once."""
        with (
            patch("world.checks.services.perform_check", wraps=perform_check) as rolled,
            force_check_outcome(self.failure),
        ):
            self.hit(40)
            self.assertEqual(rolled.call_count, 0)
            self.assertIsNone(_berserk_of(self.garrick))

            self.vitals.health = 70
            self.vitals.save(update_fields=["health"])
            self.hit(30)

        self.assertEqual(rolled.call_count, 1)
        self.assertIsNotNone(_berserk_of(self.garrick))

    def test_trigger_on_already_berserk_character_raises_severity(self) -> None:
        apply_condition(self.garrick, self.berserk, severity=1, duration_rounds=3)
        self.assertEqual(_berserk_of(self.garrick).severity, 1)

        with force_check_outcome(self.failure):
            self.hit(60)

        self.assertEqual(_berserk_of(self.garrick).severity, 3)

    def test_a_character_without_the_vulnerability_never_rolls(self) -> None:
        safe = self.make_player("Safe", room=self.field)
        CharacterVitals.objects.create(
            character_sheet=safe.sheet_data, health=100, max_health=100, base_max_health=100
        )
        seat = CombatParticipantFactory(
            encounter=self.seat.encounter, character_sheet=safe.sheet_data
        )
        with patch("world.checks.services.perform_check", wraps=perform_check) as rolled:
            apply_damage_to_participant(seat, 80)

        self.assertEqual(rolled.call_count, 0)


class StageTriggers(_ControlLossCase):
    def test_stage_trigger_fires_on_entering_its_stage(self) -> None:
        room = self.make_room("The Chapel")
        maren = self.make_player("Maren", room=room)
        curse = ConditionTemplateFactory(name="Hollow curse", has_progression=True)
        ConditionStageFactory(condition=curse, stage_order=1, severity_threshold=1)
        ConditionStageFactory(condition=curse, stage_order=2, severity_threshold=5)
        third = ConditionStageFactory(condition=curse, stage_order=3, severity_threshold=10)
        trigger = ControlLossTriggerFactory(
            vulnerability=curse, fires_on=ControlLossFiresOn.CONDITION_STAGE, stage=third,
            base_difficulty=25,
        )  # fmt: skip
        self.band(trigger, self.failure, applies=self.berserk)
        instance = apply_condition(maren, curse).instance
        self.watch(maren)

        with patch("world.checks.services.perform_check", wraps=perform_check) as rolled:
            advance_condition_severity(instance, 5)
            self.assertEqual(rolled.call_count, 0)
            with force_check_outcome(self.failure) as capture:
                advance_condition_severity(instance, 5)

        self.assertEqual(capture.target_difficulty, 25)
        self.assertEqual(_berserk_of(maren).severity, 3)
        self.assertTold(maren, "You lose control: Berserk.")

    def test_an_npc_carrying_the_curse_never_rolls(self) -> None:
        from evennia_extensions.factories import CharacterFactory
        from world.character_sheets.factories import CharacterSheetFactory

        room = self.make_room("The Crypt")
        ghoul = CharacterFactory(db_key="Ghoul", location=room)
        CharacterSheetFactory(character=ghoul)
        curse = ConditionTemplateFactory(name="Crypt curse", has_progression=True)
        ConditionStageFactory(condition=curse, stage_order=1, severity_threshold=1)
        second = ConditionStageFactory(condition=curse, stage_order=2, severity_threshold=5)
        trigger = ControlLossTriggerFactory(
            vulnerability=curse, fires_on=ControlLossFiresOn.CONDITION_STAGE, stage=second
        )
        self.band(trigger, self.failure, applies=self.berserk)
        instance = apply_condition(ghoul, curse).instance

        with patch("world.checks.services.perform_check", wraps=perform_check) as rolled:
            advance_condition_severity(instance, 5)

        self.assertEqual(rolled.call_count, 0)
        self.assertIsNone(_berserk_of(ghoul))


def _night_full_moon():
    return patch.multiple(
        "world.species.moon_pull",
        get_ic_phase=lambda: TimePhase.NIGHT,
        get_moon_illumination=lambda: 1.0,
    )


@override_settings(SEED_SAMPLE_CONTENT=True)
class MoonTrigger(_ControlLossCase):
    def setUp(self) -> None:
        super().setUp()
        from evennia_extensions.factories import RoomProfileFactory

        species = SpeciesFactory(name=SEED_LYCAN_SPECIES_NAME)
        self.gift = GiftFactory(name=SEED_LYCAN_GIFT_NAME)
        grant = SpeciesGiftGrantFactory(species=species, gift=self.gift)
        grant.drawback_condition = ensure_lycan_blood_condition()
        grant.save(update_fields=["drawback_condition"])
        self.trigger = ensure_moon_control_loss_trigger()
        hill = RoomProfileFactory(is_outdoor=True).objectdb
        self.wynn = self.make_player("Wynn", room=hill)
        self.sheet = self.wynn.sheet_data
        CharacterClassLevelFactory(character=self.sheet, level=1)
        self.sheet.invalidate_class_level_cache()
        ThreadFactory(
            owner=self.sheet,
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
            target_trait=None,
            level=2,
        )
        apply_condition(self.wynn, self.trigger.vulnerability)

    def test_moon_trigger_reproduces_todays_roll_from_rows(self) -> None:
        self.watch(self.wynn)
        with _night_full_moon(), force_check_outcome(self.failure) as capture:
            moon_reconcile_tick()

        # 20 + 5 x 10 - 10 x level 1 - min(30, 5 x thread level 2) = 50
        self.assertEqual(capture.target_difficulty, 50)
        self.assertEqual(_berserk_of(self.wynn).severity, 3)
        self.assertTold(self.wynn, "You lose control: Berserk.")

    def test_a_held_roll_leaves_the_lycan_themself(self) -> None:
        with _night_full_moon(), force_check_outcome(self.success):
            moon_reconcile_tick()

        self.assertIsNone(_berserk_of(self.wynn))

    def test_a_daylit_moon_never_rolls(self) -> None:
        with (
            patch("world.species.moon_pull.get_ic_phase", return_value=TimePhase.DAY),
            patch("world.checks.services.perform_check", wraps=perform_check) as rolled,
        ):
            moon_reconcile_tick()

        self.assertEqual(rolled.call_count, 0)

    def test_moon_roll_counts_condition_modifiers(self) -> None:
        ConditionCheckModifierFactory(
            condition=self.trigger.vulnerability,
            check_type=self.trigger.check_type,
            modifier_value=-10,
        )
        with (
            _night_full_moon(),
            patch("world.checks.services.perform_check", wraps=perform_check) as rolled,
        ):
            moon_reconcile_tick()

        self.assertEqual(rolled.call_args.kwargs["extra_modifiers"], -10)


# -- a compulsion at combat resolution ------------------------------------------------
#
# Mira is Berserk at severity 3 in a fight with a Bandit Captain. The seeded Berserk
# compulsion (base 25, +2 per severity; flee and parley +5) makes every hand-worked
# difficulty: any action other than an attack rolls at 25 + 2 x 3 = 31, a flee or a
# parley at 31 + 5 = 36. A Partial Success acts strained at -4; a Failure lets the rage
# act. She knows Claw, a damaging technique the rage swings with, and Mend, which harms
# nobody.


def _land_the_swing(*_args: object, **_kwargs: object):
    """The offence roll a declared or compelled attack makes, pinned to land."""
    return MagicMock(success_level=2)


class _CompelledMira(_ControlLossCase):
    def setUp(self) -> None:
        super().setUp()
        self.partial = outcome_at_level(0)
        self.failure = outcome_at_level(-1)
        self.success = outcome_at_level(1)
        self.road = self.make_room("The Road")
        self.mira = self.make_player("Mira", room=self.road)
        self.sheet = self.mira.sheet_data
        CharacterVitals.objects.create(
            character_sheet=self.sheet, health=100, max_health=100, base_max_health=100
        )
        CharacterAnimaFactory(character=self.sheet, current=100, maximum=100)
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=self.road
        )
        self.seat = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.sheet, status=ParticipantStatus.ACTIVE
        )
        self.captain = CombatOpponentFactory(
            encounter=self.encounter, name="Bandit Captain", health=5000, max_health=5000
        )
        self.flee_check = CheckTypeFactory(name="Run for it")
        FleeConfig.objects.filter(pk=1).delete()
        FleeConfig.objects.create(pk=1, check_type=self.flee_check)
        template = ensure_technique_cast_content()
        self.claw = TechniqueFactory(
            name="Claw",
            effect_type=EffectTypeFactory(name="Claw effect", base_power=5),
            action_category=ActionCategory.PHYSICAL,
            action_template=template,
            anima_cost=1,
            reach=TechniqueReach.ADJACENT,
            target_type=ActionTargetType.SINGLE,
        )
        self.mend = TechniqueFactory(
            name="Mend",
            effect_type=EffectTypeFactory(name="Mend effect", base_power=None),
            action_category=ActionCategory.PHYSICAL,
            action_template=template,
            anima_cost=1,
        )
        for technique in (self.claw, self.mend):
            CharacterGiftFactory(character=self.sheet, gift=technique.gift)
            CharacterTechnique.objects.create(character=self.sheet, technique=technique)
        self.rage = apply_condition(self.mira, self.berserk, severity=3, duration_rounds=3).instance
        self.watch(self.mira)

    def resolve(self, offense=_land_the_swing) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            resolve_round(self.encounter, offense_check_fn=offense)

    @staticmethod
    @contextmanager
    def resist_rolls() -> Iterator[MagicMock]:
        """One spy on the real check, wherever a roll reaches it from (the flee roll
        holds its own reference through the consequence resolver)."""
        spy = MagicMock(wraps=perform_check)
        with (
            patch("world.checks.services.perform_check", spy),
            patch("world.checks.consequence_resolution.perform_check", spy),
        ):
            yield spy

    @staticmethod
    def rolled_on(spy, check_type) -> list:
        """The spied calls rolled on ``check_type``."""
        return [
            call
            for call in spy.call_args_list
            if (call.args[1] if len(call.args) > 1 else call.kwargs.get("check_type")) == check_type
        ]

    def declared(self):
        return CombatRoundAction.objects.filter(participant=self.seat, round_number=1).first()


class ACompelledFighterWhoAttacks(_CompelledMira):
    def test_compelled_pc_attacking_rolls_nothing(self) -> None:
        told = self.telnet(self.mira, "cast Claw at Bandit Captain")
        self.assertNotIn("Could not", told)

        with self.resist_rolls() as spy:
            self.resolve()

        compulsion = self.berserk.compulsion
        self.assertEqual(self.rolled_on(spy, compulsion.check_type), [])
        self.assertNotTold(self.mira, "tries to")

    def test_a_waiting_strike_is_an_attack_and_rolls_nothing(self) -> None:
        told = self.telnet(self.mira, "combat await Claw")
        self.assertEqual(self.declared().maneuver, CombatManeuver.AWAIT_OPENING, told)

        with self.resist_rolls() as spy:
            self.resolve()

        self.assertEqual(self.rolled_on(spy, self.berserk.compulsion.check_type), [])
        self.assertNotTold(self.mira, "tries to")

    def test_idle_compelled_pc_is_auto_declared(self) -> None:
        with self.resist_rolls() as spy:
            self.resolve()

        self.assertEqual(self.rolled_on(spy, self.berserk.compulsion.check_type), [])
        action = self.declared()
        self.assertEqual(action.focused_action, self.claw)
        self.assertEqual(action.focused_opponent_target, self.captain)
        # The rage never consents to Soulfray risk for the player (AFK never kills).
        self.assertFalse(action.confirm_soulfray_risk)


class ACompelledFighterWhoFlees(_CompelledMira):
    def test_compelled_flee_partial_success_flees_at_penalty(self) -> None:
        result = self.web(self.mira, "combat_flee")
        self.assertTrue(result.detail.success, result.detail.message)

        with self.resist_rolls() as spy, force_check_outcome(self.partial):
            self.resolve()

        self.assertTold(
            self.mira,
            "Mira tries to flee against Berserk. Resist compulsion vs 36: Partial Success.",
        )
        flee_rolls = self.rolled_on(spy, self.flee_check)
        self.assertEqual(len(flee_rolls), 1)
        # perform_check(character, check_type, target_difficulty, extra_modifiers, ...)
        self.assertEqual(flee_rolls[0].args[3], -4)
        self.assertEqual(self.declared().compulsion_penalty, 4)

    def test_compelled_flee_failure_attacks_instead(self) -> None:
        self.telnet(self.mira, "combat flee")

        with self.resist_rolls() as spy, force_check_outcome(self.failure):
            self.resolve()

        self.assertTold(self.mira, "Resist compulsion vs 36: Failure.")
        self.assertTold(self.mira, "Berserk wins out: Mira attacks Bandit Captain.")
        self.assertEqual(self.rolled_on(spy, self.flee_check), [])
        action = self.declared()
        self.assertIsNone(action.maneuver)
        self.assertEqual(action.focused_action, self.claw)
        self.assertFalse(action.confirm_soulfray_risk)
        self.seat.refresh_from_db()
        self.assertEqual(self.seat.status, ParticipantStatus.ACTIVE)

    def test_failed_resist_with_no_attack_available_cancels_without_error(self) -> None:
        CharacterTechnique.objects.filter(character=self.sheet, technique=self.claw).delete()
        self.telnet(self.mira, "combat flee")

        with force_check_outcome(self.failure):
            self.resolve()

        self.assertTold(self.mira, "Berserk wins out: Mira gives up trying to flee.")
        self.assertIsNone(self.declared())


class ACompelledFighterWhoHeals(_CompelledMira):
    def test_compelled_heal_rolls_at_base_difficulty(self) -> None:
        told = self.telnet(self.mira, "cast Mend")
        self.assertNotIn("Could not", told)

        with force_check_outcome(self.success):
            self.resolve()

        # 25 base + 2 per severity x 3, and Mend is not a forbidden action.
        self.assertTold(
            self.mira, "Mira tries to use Mend against Berserk. Resist compulsion vs 31: Success."
        )
        self.assertEqual(self.declared().focused_action, self.mend)

    def test_a_strained_mend_rolls_at_the_penalty(self) -> None:
        self.telnet(self.mira, "cast Mend")
        offense = MagicMock(wraps=_land_the_swing)

        with force_check_outcome(self.partial):
            self.resolve(offense)

        self.assertTold(self.mira, "Resist compulsion vs 31: Partial Success.")
        self.assertEqual(offense.call_args.kwargs["extra_modifiers"], -4)


class ACompelledFighterWhoParleys(_CompelledMira):
    def setUp(self) -> None:
        super().setUp()
        self.parley_check = CheckTypeFactory(name="Talk them down")
        SocialManeuverConfigFactory(parley_check_type=self.parley_check)
        self.captain.morale = 0
        self.captain.save(update_fields=["morale"])

    def test_a_strained_parley_rolls_at_the_penalty(self) -> None:
        told = self.telnet(self.mira, "combat parley Bandit Captain")
        self.assertEqual(self.declared().maneuver, CombatManeuver.PARLEY, told)

        with self.resist_rolls() as spy, force_check_outcome(self.partial):
            self.resolve()

        # 31 + 5: parley is forbidden.
        self.assertTold(self.mira, "Mira tries to parley against Berserk. Resist compulsion vs 36")
        parley_rolls = self.rolled_on(spy, self.parley_check)
        self.assertEqual(len(parley_rolls), 1)
        self.assertEqual(parley_rolls[0].kwargs["extra_modifiers"], -4)


class TwoCompulsionsAtOnce(_CompelledMira):
    def test_two_compulsions_the_most_severe_governs(self) -> None:
        fever = ConditionTemplateFactory(name="Battle fever", category=self.berserk.category)
        CompulsionFactory(
            condition=fever,
            check_type=self.berserk.compulsion.check_type,
            base_difficulty=10,
            difficulty_per_severity=0,
        )
        apply_condition(self.mira, fever, severity=5, duration_rounds=3)
        self.telnet(self.mira, "combat flee")

        with force_check_outcome(self.success):
            self.resolve()

        self.assertTold(
            self.mira, "Mira tries to flee against Battle fever. Resist compulsion vs 10: Success."
        )
        self.assertNotTold(self.mira, "against Berserk")


STEADY_ANIMA = 3
STEADY_PER_DEPTH = 2


class _SteadyingAllies(_CompelledMira):
    """Mira is in a rage and her allies may steady her: 3 anima a time, 2 per bond depth."""

    def setUp(self) -> None:
        super().setUp()
        self.steadying = CapabilityTypeFactory(name="steadying", innate_baseline=0)
        MovementConfig.objects.all().delete()
        MovementConfig.objects.create(
            pk=1,
            steadying_capability=self.steadying,
            steady_anima_cost=STEADY_ANIMA,
            steady_bonus_per_depth=STEADY_PER_DEPTH,
        )
        self.ally_seats: dict[str, CombatParticipant] = {}
        self.encounter.escalation_curve = EscalationCurveFactory()
        self.encounter.save(update_fields=["escalation_curve"])

    def ally(self, name: str, *, capability: int = 4, bond_depth: int = 0):
        """A fighter at Mira's side who holds the steadying capability at ``capability``."""
        character = self.make_player(name, room=self.road)
        sheet = character.sheet_data
        CharacterVitals.objects.create(
            character_sheet=sheet, health=100, max_health=100, base_max_health=100
        )
        CharacterAnimaFactory(character=sheet, current=20, maximum=20)
        self.ally_seats[name] = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=sheet, status=ParticipantStatus.ACTIVE
        )
        if capability:
            target, _ = ModifierTarget.objects.get_or_create(
                name=f"capability_{self.steadying.pk}",
                category=ModifierCategoryFactory(name="capability"),
                defaults={
                    "description": "",
                    "display_order": 0,
                    "is_active": True,
                    "target_capability": self.steadying,
                },
            )
            CharacterModifier.objects.create(
                character=sheet,
                target=target,
                value=capability,
                source=ModifierSource.objects.create(),
            )
        if bond_depth:
            rel_type = RelationshipTypeFactory(
                valence=TypeValence.WARM, fuels_escalation_spikes=True
            )
            relationship = CharacterRelationshipFactory(
                source=sheet, target=self.sheet, is_active=True
            )
            RelationshipLabelFactory(relationship=relationship, type=rel_type)
            relationship.invested_depth = bond_depth
            relationship.save()
        self.watch(character)
        return character

    def resolve_with_rolls(self, *outcomes):
        """Resolve the round with the compulsion's rolls landing on ``outcomes`` in turn.

        Returns the real ``perform_check`` calls made on the compulsion's check type.
        """
        remaining = list(outcomes)
        calls: list = []

        def sequenced(*args, **kwargs):
            if args[1] == self.berserk.compulsion.check_type:
                calls.append((args, kwargs))
            if not remaining:
                return perform_check(*args, **kwargs)
            with force_check_outcome(remaining.pop(0)):
                return perform_check(*args, **kwargs)

        with patch("world.checks.services.perform_check", sequenced):
            self.resolve()
        return calls

    def anima(self, character) -> int:
        return CharacterAnima.objects.get(character=character.sheet_data).current


class AnAllyWhoSteadies(_SteadyingAllies):
    def test_steady_grants_second_roll_and_costs_anima_and_a_reaction(self) -> None:
        brann = self.ally("Brann", capability=4)
        self.assertTrue(self.web(brann, "combat_steady", steady=True).detail.success)
        self.telnet(self.mira, "combat flee")

        calls = self.resolve_with_rolls(self.failure, self.success)

        first, second = calls[0][1]["extra_modifiers"], calls[1][1]["extra_modifiers"]
        self.assertEqual(len(calls), 2)
        self.assertEqual(second - first, 4)
        self.assertTold(self.mira, "Brann steadies Mira.")
        self.assertNotTold(self.mira, "Berserk wins out")
        self.assertEqual(self.anima(brann), 20 - STEADY_ANIMA)
        self.assertEqual(
            self.ally_seats["Brann"]
            .__class__.objects.get(pk=self.ally_seats["Brann"].pk)
            .reactions_used,
            1,
        )
        self.assertEqual(self.declared().maneuver, CombatManeuver.FLEE)

    def test_without_the_plan_nobody_steadies(self) -> None:
        brann = self.ally("Brann", capability=4)
        self.telnet(self.mira, "combat flee")

        calls = self.resolve_with_rolls(self.failure, self.success)

        self.assertEqual(len(calls), 1)
        self.assertTold(self.mira, "Berserk wins out: Mira attacks Bandit Captain.")
        self.assertEqual(self.anima(brann), 20)

    def test_steady_bonus_scales_with_bond_depth(self) -> None:
        brann = self.ally("Brann", capability=4, bond_depth=10)
        cade = self.ally("Cade", capability=4)
        for ally in (brann, cade):
            self.web(ally, "combat_steady", steady=True)
        self.telnet(self.mira, "combat flee")

        calls = self.resolve_with_rolls(self.failure, self.success)

        bonus = calls[1][1]["extra_modifiers"] - calls[0][1]["extra_modifiers"]
        self.assertEqual(bonus, 4 + STEADY_PER_DEPTH * 10)
        self.assertTold(self.mira, "Brann steadies Mira.")
        self.assertEqual(self.anima(brann), 20 - STEADY_ANIMA)
        self.assertEqual(self.anima(cade), 20)

    def test_equal_bonuses_go_to_the_lowest_participant_pk(self) -> None:
        brann = self.ally("Brann", capability=4)
        cade = self.ally("Cade", capability=4)
        for ally in (cade, brann):
            self.web(ally, "combat_steady", steady=True)
        self.telnet(self.mira, "combat flee")

        self.resolve_with_rolls(self.failure, self.success)

        self.assertTold(self.mira, "Brann steadies Mira.")
        self.assertEqual(self.anima(cade), 20)

    def test_a_compelled_ally_cannot_steady(self) -> None:
        cade = self.ally("Cade", capability=4)
        self.web(cade, "combat_steady", steady=True)
        apply_condition(cade, self.berserk, severity=3, duration_rounds=3)
        self.telnet(self.mira, "combat flee")

        calls = self.resolve_with_rolls(self.failure, self.success)

        self.assertEqual(len(calls), 1)
        self.assertNotTold(self.mira, "steadies Mira")
        self.assertEqual(self.anima(cade), 20)

    def test_an_ally_short_of_anima_cannot_steady(self) -> None:
        brann = self.ally("Brann", capability=4)
        self.web(brann, "combat_steady", steady=True)
        CharacterAnima.objects.filter(character=brann.sheet_data).update_with_reason(
            reason="issue #4802: leave her short of the steady cost", current=STEADY_ANIMA - 1
        )
        self.telnet(self.mira, "combat flee")

        calls = self.resolve_with_rolls(self.failure, self.success)

        self.assertEqual(len(calls), 1)


class TheSteadyPlan(_SteadyingAllies):
    def test_steady_plan_toggles_by_telnet_and_web(self) -> None:
        brann = self.ally("Brann", capability=4)
        seat = self.ally_seats["Brann"]

        self.assertTrue(self.web(brann, "combat_steady", steady=True).detail.success)
        seat.refresh_from_db()
        self.assertTrue(seat.steady_enabled)
        self.assertTrue(self.web(brann, "combat_steady", steady=False).detail.success)
        seat.refresh_from_db()
        self.assertFalse(seat.steady_enabled)

        self.assertIn("you'll steady them", self.telnet(brann, "combat steady"))
        seat.refresh_from_db()
        self.assertTrue(seat.steady_enabled)
        self.assertIn("won't steady", self.telnet(brann, "combat steady off"))
        seat.refresh_from_db()
        self.assertFalse(seat.steady_enabled)

    def test_steady_with_a_stray_word_prints_usage_and_changes_nothing(self) -> None:
        brann = self.ally("Brann", capability=4)

        told = self.telnet(brann, "combat steady maybe")

        self.assertIn("Usage: combat steady [on|off].", told)
        seat = self.ally_seats["Brann"]
        seat.refresh_from_db()
        self.assertFalse(seat.steady_enabled)

    def test_nothing_to_steady_with_is_refused_plainly(self) -> None:
        dara = self.ally("Dara", capability=0)

        told = self.web(dara, "combat_steady", steady=True)

        self.assertFalse(told.detail.success)
        self.assertEqual(told.detail.message, "Nothing you have lets you steady an ally.")
        self.assertFalse(
            self.ally_seats["Dara"]
            .__class__.objects.get(pk=self.ally_seats["Dara"].pk)
            .steady_enabled
        )


class ACompelledStrikeThatFalters(_CompelledMira):
    def test_a_compelled_strike_stopped_at_soulfray_is_told_so(self) -> None:
        warning = SoulfrayWarning(
            stage_name="Stage One", stage_description="Your soul frays.", has_death_risk=False
        )
        self.telnet(self.mira, "combat flee")

        with (
            force_check_outcome(self.failure),
            patch("world.magic.services.techniques.get_soulfray_warning", return_value=warning),
        ):
            self.resolve()

        self.assertTrue(self.declared().declared_by_compulsion)
        self.assertTold(self.mira, "Your compulsion's strike faltered at the edge of Soulfray.")
        self.assertNotTold(self.mira, "Accept the Soulfray risk")


class ACompelledFighterWhoWalksAway(_CompelledMira):
    """Leaving the encounter between rounds rolls against the compulsion (Berserk 41:
    base 25, plus 2 a severity at severity 3, plus 10 for LEAVE)."""

    def setUp(self) -> None:
        super().setUp()
        self.encounter.status = RoundStatus.BETWEEN_ROUNDS
        self.encounter.encounter_type = EncounterType.OPEN_ENCOUNTER
        self.encounter.save()

    def test_compelled_leave_rolls_and_success_leaves(self) -> None:
        with force_check_outcome(self.success):
            result = self.web(self.mira, "combat_leave")

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertTold(
            self.mira,
            "Mira tries to leave the encounter against Berserk. Resist compulsion vs 41: Success.",
        )
        self.seat.refresh_from_db()
        self.assertEqual(self.seat.status, ParticipantStatus.REMOVED)

    def test_compelled_leave_failure_stays_and_is_told_why(self) -> None:
        with force_check_outcome(self.failure):
            told = self.telnet(self.mira, "combat leave")

        self.assertIn("Resist compulsion vs 41: Failure.", told)
        self.assertIn("You cannot break away.", told)
        self.seat.refresh_from_db()
        self.assertEqual(self.seat.status, ParticipantStatus.ACTIVE)

    def test_an_npc_with_the_compulsion_leaves_with_no_roll(self) -> None:
        npc = CharacterFactory(db_key="Grub", location=self.road)
        npc_sheet = CharacterSheetFactory(character=npc)
        apply_condition(npc, self.berserk, severity=3, duration_rounds=3)
        seat = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=npc_sheet, status=ParticipantStatus.ACTIVE
        )

        with self.resist_rolls() as spy:
            leave_encounter(seat)

        self.assertEqual(spy.call_count, 0)
        seat.refresh_from_db()
        self.assertEqual(seat.status, ParticipantStatus.REMOVED)


class _AltSelfMira(_ControlLossCase):
    """Mira, wearing the Beast, out of any fight."""

    resist_rolls = staticmethod(_CompelledMira.resist_rolls)

    def alt_kwargs(self) -> dict:
        """Extra fields for the worn self; a subclass makes it a talked-down one."""
        return {}

    def setUp(self) -> None:
        super().setUp()
        self.road = self.make_room("The Road")
        self.mira = self.make_player("Mira", room=self.road)
        self.sheet = self.mira.sheet_data
        true_form = CharacterFormFactory(character=self.sheet, name="True", form_type=FormType.TRUE)
        CharacterFormStateFactory(character=self.sheet, active_form=true_form)
        persona = PersonaFactory(
            character_sheet=self.sheet, persona_type=PersonaType.ALTERNATE, name="the Beast"
        )
        alt = AlternateSelfFactory(character=self.sheet, persona=persona, **self.alt_kwargs())
        trigger_transformation(self.sheet, alt, cause="command")
        self.watch(self.mira)

    def wearing_the_beast(self) -> bool:
        return ActiveAlternateSelf.objects.get(character=self.sheet).alternate_self_id is not None


class ACompelledFighterWhoChangesBack(_AltSelfMira):
    def test_compelled_revert_out_of_combat_rolls(self) -> None:
        apply_condition(self.mira, self.berserk, severity=3, duration_rounds=3)

        with force_check_outcome(self.failure):
            told = self.telnet(self.mira, "form revert")

        self.assertIn(
            "the Beast tries to change back against Berserk. Resist compulsion vs 41", told
        )
        self.assertIn("Failure.", told)
        self.assertIn("You cannot change back.", told)
        self.assertTrue(self.wearing_the_beast())

        with force_check_outcome(self.success):
            result = self.web(self.mira, "revert_form")

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertFalse(self.wearing_the_beast())

    def test_the_worn_self_lists_what_changing_back_costs(self) -> None:
        apply_condition(self.mira, self.berserk, severity=3, duration_rounds=3)
        # The factory leaves the stage's multiplier a string; the read needs the stored one.
        for stage in self.berserk.stages.all():
            stage.refresh_from_db()
        client = self.api(self.account_of(self.mira))

        response = client.get(f"/api/forms/alternate-selves/?character_sheet={self.sheet.pk}")

        self.assertEqual(response.status_code, 200, response.content[:400])
        worn = response.data["results"][0]["compulsion"]
        revert = next(c for c in worn["against"] if c["action_key"] == "revert_form")
        self.assertEqual((revert["difficulty"], revert["forbidden"]), (41, True))

    def test_charmed_pc_reverts_freely(self) -> None:
        charm = ConditionTemplateFactory(
            name="Charmed", category=ConditionCategoryFactory(alters_behavior=True)
        )
        apply_condition(self.mira, charm)
        self.assertFalse(self.sheet.in_control)

        with self.resist_rolls() as spy:
            result = self.web(self.mira, "revert_form")

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(spy.call_count, 0)
        self.assertFalse(self.wearing_the_beast())

    def test_audere_end_talked_down_still_holds_form(self) -> None:
        apply_condition(self.mira, self.berserk, severity=3, duration_rounds=3)

        with self.assertRaises(RevertBlockedError):
            revert_alternate_self(self.sheet)

        self.assertTrue(self.wearing_the_beast())


class _ATalkedDownBeast(_AltSelfMira):
    """The Beast must be talked down: it is held by a Beast Fury condition."""

    def setUp(self) -> None:
        self.fury = ConditionTemplateFactory(
            name="Beast Fury", category=ConditionCategoryFactory(alters_behavior=True)
        )
        super().setUp()
        apply_condition(self.mira, self.fury)

    def alt_kwargs(self) -> dict:
        return {
            "revert_kind": AlternateSelfRevertKind.TALKED_DOWN,
            "emergence_condition": self.fury,
        }


class ATalkedDownSelfWithNoCompulsion(_ATalkedDownBeast):
    def test_changing_back_stays_blocked_while_the_condition_holds(self) -> None:
        with self.resist_rolls() as spy:
            told = self.telnet(self.mira, "form revert")

        self.assertIn("You can't revert while not in control of yourself.", told)
        self.assertEqual(spy.call_count, 0)
        self.assertTrue(self.wearing_the_beast())


class ATalkedDownSelfWhoseConditionCompels(_ATalkedDownBeast):
    def test_changing_back_rolls_instead_of_being_blocked(self) -> None:
        CompulsionResistBandFactory(
            compulsion=CompulsionFactory(condition=self.fury),
            outcome=self.failure,
            result=CompulsionResult.COMPULSION_ACTS,
        )

        with force_check_outcome(self.failure):
            told = self.telnet(self.mira, "form revert")

        self.assertIn("You cannot change back.", told)
        self.assertNotIn("not in control", told)
        self.assertTrue(self.wearing_the_beast())

        with force_check_outcome(self.success):
            self.telnet(self.mira, "form revert")

        self.assertFalse(self.wearing_the_beast())


class TheDeclarePanelPayload(_SteadyingAllies):
    """What the participant payload tells each viewer about a compulsion and steadying."""

    def payload(self, viewer, seat) -> dict:
        """The two fields under test, read through the serializer's own methods."""
        from rest_framework.test import APIRequestFactory

        from world.combat.serializers import ParticipantSerializer

        request = APIRequestFactory().get("/")
        request.user = self.account_of(viewer)
        serializer = ParticipantSerializer(seat, context={"request": request})
        return {
            "compulsion": serializer.get_compulsion(seat),
            "steady_plan": serializer.get_steady_plan(seat),
        }

    def test_compulsion_payload_only_for_own_participant(self) -> None:
        brann = self.ally("Brann", capability=4)

        own = self.payload(self.mira, self.seat)["compulsion"]
        others = self.payload(brann, self.seat)["compulsion"]

        self.assertIsNone(others)
        self.assertEqual(own["condition_name"], "Berserk")
        self.assertEqual(own["wants_label"], "Attack an opponent")
        self.assertEqual(own["check_name"], "Resist compulsion")
        against = {row["action_key"]: row for row in own["against"]}
        # 25 base + 2 per severity x 3; flee also carries Berserk's +5 for being forbidden.
        self.assertEqual(
            against["flee"],
            {"action_key": "flee", "difficulty": 36, "forbidden": True, "extra_difficulty": 5},
        )
        # Leaving and changing back roll too, though neither is declared in the round.
        self.assertIn("leave", against)
        self.assertEqual(against["revert_form"]["difficulty"], 41)
        self.assertTrue(against["revert_form"]["forbidden"])
        self.assertNotIn("engage", against)
        self.assertNotIn("yield", against)
        self.assertEqual(against["technique_no_target"]["difficulty"], 31)
        self.assertFalse(against["technique_no_target"]["forbidden"])
        self.assertNotIn("charge", against)
        self.assertIsNone(self.payload(brann, self.ally_seats["Brann"])["compulsion"])

    def test_steady_plan_payload_only_for_a_holder_of_the_capability(self) -> None:
        brann = self.ally("Brann", capability=4)

        plan = self.payload(brann, self.ally_seats["Brann"])["steady_plan"]

        self.assertEqual(
            plan, {"enabled": False, "cost_line": f"{STEADY_ANIMA} anima each", "bonus_hint": "+4"}
        )
        self.assertIsNone(self.payload(self.mira, self.seat)["steady_plan"])
        self.assertIsNone(self.payload(brann, self.seat)["steady_plan"])

    def test_telnet_declare_against_compulsion_warns(self) -> None:
        told = self.telnet(self.mira, "combat flee")

        self.assertIn(
            "Against Berserk: Resist compulsion check, difficulty 36. "
            "If it fails, you attack instead.",
            told,
        )
        self.assertIn("You declare a desperate flee.", told)

    def test_telnet_declare_of_an_attack_does_not_warn(self) -> None:
        told = self.telnet(self.mira, f"cast Claw at {self.captain.name}")

        self.assertNotIn("Against Berserk", told)

    def test_a_plan_command_after_a_flee_does_not_repeat_the_warning(self) -> None:
        self.telnet(self.mira, "combat flee")

        told = self.telnet(self.mira, "combat dodge off")

        self.assertNotIn("Against Berserk", told)

    def test_flee_then_engage_does_not_repeat_the_warning(self) -> None:
        self.telnet(self.mira, "combat flee")

        told = self.telnet(self.mira, f"combat engage {self.captain.name}")

        self.assertNotIn("Against Berserk", told)

    def test_a_compelled_viewers_payload_costs_a_fixed_query_count(self) -> None:
        """The compulsion and every option's cost come from one read, not one per option."""
        self.payload(self.mira, self.seat)  # warm the caches

        with self.assertNumQueries(COMPELLED_PAYLOAD_QUERIES):
            own = self.payload(self.mira, self.seat)["compulsion"]

        self.assertEqual(own["condition_name"], "Berserk")
        self.assertGreater(len(own["against"]), 5)

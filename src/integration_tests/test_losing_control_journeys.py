"""Losing control to a trigger (#4802): the moon, a wound, a condition stage.

Three people each carry a vulnerability and meet its trigger:
- Garrick bears a wound-triggered rage (fires below 50 percent of 100 health). A failed
  roll applies Berserk at severity 3 for 3 rounds; a Success does nothing.
- Maren bears a curse with three stages; entering stage 3 fires its trigger.
- Wynn is a lycan under a clear full moon (pull 10) at level 1 with a gift thread at
  level 2, so the seeded moon trigger's difficulty is hand-worked:
  20 base + 5 x 10 pull - 10 x 1 level - min(30, 5 x 2 thread) = 50.
Every roll is forced to the outcome a journey wants (``force_check_outcome``), which also
records the difficulty the roll was made at. The trigger lines go out on commit, so each
journey that reads them runs its trigger inside ``captureOnCommitCallbacks``.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import override_settings
from django.utils import timezone

from actions.constants import ActionTargetType
from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from evennia_extensions.factories import CharacterFactory
from integration_tests.harness import JourneyCase
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import EffectType
from world.checks.factories import CheckTypeFactory, ConsequenceEffectFactory, ConsequenceFactory
from world.checks.services import perform_check
from world.checks.test_helpers import force_check_outcome
from world.classes.factories import CharacterClassLevelFactory
from world.combat.constants import (
    ActionCategory,
    CombatManeuver,
    EncounterType,
    ParticipantStatus,
    TargetingMode,
    TargetSelection,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentActionFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    EscalationCurveFactory,
    SocialManeuverConfigFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import CombatParticipant, CombatRoundAction, FleeConfig, MovementConfig
from world.combat.services import leave_encounter, resolve_round
from world.combat.services.damage.damage import (
    apply_damage_to_participant,
    settle_wound_triggers,
)
from world.conditions.berserk_content import ensure_berserk_content, outcome_at_level
from world.conditions.constants import (
    UNCONSCIOUS_CONDITION_NAME,
    CompulsionResult,
    ControlLossFiresOn,
    DurationType,
    FoundationalCapability,
)
from world.conditions.factories import (
    CapabilityTypeFactory,
    CompulsionFactory,
    CompulsionResistBandFactory,
    ConditionCapabilityEffectFactory,
    ConditionCategoryFactory,
    ConditionCheckModifierFactory,
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
    ControlLossBandFactory,
    ControlLossTriggerFactory,
)
from world.conditions.services import (
    advance_condition_severity,
    advance_condition_stage,
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
from world.vitals.services import get_vitals_consequence_config


def _berserk_of(character):
    berserk = get_berserk_template()
    return next((i for i in get_active_conditions(character) if i.condition_id == berserk.pk), None)


# Two of these name the roster by persona (ruling 39), once for every participant.
COMPELLED_READ_QUERIES = 28


def knock_out_condition():
    """Unconscious, which zeroes awareness so its bearer cannot act (``can_act`` False)."""
    awareness = CapabilityTypeFactory(name=FoundationalCapability.AWARENESS, innate_baseline=1)
    unconscious = ConditionTemplateFactory(
        name=UNCONSCIOUS_CONDITION_NAME, default_duration_type=DurationType.UNTIL_CURED
    )
    ConditionCapabilityEffectFactory(condition=unconscious, capability=awareness, value=-100)
    return unconscious


def knock_out(character) -> None:
    """Make *character* unable to act: Unconscious on them now."""
    ConditionInstanceFactory(target=character, condition=knock_out_condition())
    character.conditions.invalidate()


def _full_swing(*_args: object, **_kwargs: object) -> MagicMock:
    """A defence roll fixed at success level 0, which takes the swing at full strength."""
    return MagicMock(success_level=0)


@contextmanager
def minutes_later(minutes: int) -> Iterator[None]:
    """The clock *minutes* ahead, for a wait that runs on real time."""
    later = timezone.now() + timedelta(minutes=minutes)
    with patch("django.utils.timezone.now", return_value=later):
        yield


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

    def assertToldNothingOfControl(self, *characters) -> None:  # noqa: N802 - unittest style
        """None of *characters* was told, or pushed a row, about a fight to keep control.

        Each must have been watched before the act under test.
        """
        for character in characters:
            self.assertNotTold(character, "keep control")
            rows = self.mailbox(character).rows
            self.assertFalse(any("keep control" in row for row in rows), rows)


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
            check_type=CheckTypeFactory(name="Hold the rage"),
        )  # fmt: skip
        self.band(self.trigger, self.failure, applies=self.berserk)
        self.band(self.trigger, self.success)
        encounter = CombatEncounterFactory(room=self.field)
        self.seat = CombatParticipantFactory(encounter=encounter, character_sheet=self.sheet)

    def hit(self, damage: int) -> None:
        """A hit that rolls no knockout check (a bounced blow): its wound triggers roll now."""
        with self.captureOnCommitCallbacks(execute=True):
            settle_wound_triggers(self.seat, apply_damage_to_participant(self.seat, damage))

    def brute_swings(self, damage: int, outcome) -> MagicMock:
        """A brute's swing for *damage* through a real round, every roll landing on *outcome*.

        The round rolls the hit's knockout check before any wound trigger. Returns a spy
        on every roll, wherever it was made from.
        """
        encounter = self.seat.encounter
        encounter.status = RoundStatus.DECLARING
        encounter.round_number = 1
        encounter.save(update_fields=["status", "round_number"])
        pool = ThreatPoolFactory()
        swing = ThreatPoolEntryFactory(
            pool=pool,
            name="Haymaker",
            base_damage=damage,
            targeting_mode=TargetingMode.SINGLE,
            target_selection=TargetSelection.SPECIFIC_ROLE,
        )
        brute = CombatOpponentFactory(
            encounter=encounter, threat_pool=pool, health=500, max_health=500, soak_value=0
        )
        action = CombatOpponentActionFactory(opponent=brute, threat_entry=swing, round_number=1)
        action.targets.add(self.seat)
        spy = MagicMock(wraps=perform_check)
        with (
            patch("world.checks.services.perform_check", spy),
            patch("world.checks.consequence_resolution.perform_check", spy),
            self.captureOnCommitCallbacks(execute=True),
            force_check_outcome(outcome),
        ):
            resolve_round(encounter, defense_check_fn=_full_swing, offense_check_fn=_land_the_swing)
        return spy

    def knockout_pool(self, unconscious) -> None:
        """A failed knockout check applies Unconscious (the only entry in the pool)."""
        consequence = ConsequenceFactory(outcome_tier=self.failure, character_loss=False)
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

    def trigger_rolls(self, spy) -> int:
        return sum(
            1
            for call in spy.call_args_list
            if (call.args[1] if len(call.args) > 1 else call.kwargs.get("check_type"))
            == self.trigger.check_type
        )

    def test_wound_below_threshold_rolls_and_failure_applies_berserk(self) -> None:
        self.watch(self.garrick)
        with force_check_outcome(self.failure) as capture:
            self.hit(60)

        berserk = _berserk_of(self.garrick)
        self.assertIsNotNone(berserk)
        self.assertEqual(berserk.severity, 3)
        self.assertEqual(capture.target_difficulty, 30)
        # Ruling 35: cause, roll with its difficulty, then the onset, all from rows.
        self.assertTold(
            self.garrick,
            "You fall below 50% health. You fight to keep control. Hold the rage vs 30: "
            "Failure. You lose control: Berserk, severity 3, for 3 rounds.",
        )

    def test_the_room_sees_the_loss_of_control(self) -> None:
        witness = self.make_player("Witness", room=self.field)
        self.watch(witness)
        with force_check_outcome(self.failure):
            self.hit(60)

        self.assertTold(
            witness,
            "Garrick falls below 50% health. Garrick fights to keep control. Hold the rage "
            "vs 30: Failure. Garrick loses control: Berserk, severity 3, for 3 rounds.",
        )

    def test_the_onset_names_the_bands_control_and_intensity_shift(self) -> None:
        """Ruling 35: a band that also moves control and intensity says so after the onset."""
        band = self.trigger.bands.get(outcome=self.failure)
        band.control_change = -6
        band.intensity = 4
        band.save(update_fields=["control_change", "intensity"])
        self.watch(self.garrick)
        with force_check_outcome(self.failure):
            self.hit(60)

        self.assertTold(
            self.garrick,
            "You lose control: Berserk, severity 3, for 3 rounds · Control -6 · Intensity +4.",
        )

    def test_a_band_that_only_moves_control_says_so_without_an_onset(self) -> None:
        """Ruling 35: with no condition applied, only the shifts the band holds are told."""
        partial = ensure_canonical_check_outcome("Partial Success")
        ControlLossBandFactory(trigger=self.trigger, outcome=partial, control_change=-2)
        self.watch(self.garrick)
        with force_check_outcome(partial):
            self.hit(60)

        self.assertTold(
            self.garrick,
            "You fall below 50% health. You fight to keep control. Hold the rage vs 30: "
            "Partial Success. Control -2.",
        )
        self.assertNotTold(self.garrick, "lose control")
        self.assertNotTold(self.garrick, "Intensity")

    def test_a_killing_hit_rolls_no_wound_trigger(self) -> None:
        witness = self.make_player("Witness", room=self.field)
        self.watch(self.garrick, witness)
        with (
            patch("world.checks.services.perform_check", wraps=perform_check) as rolled,
            force_check_outcome(self.failure),
        ):
            self.hit(100)

        self.assertEqual(rolled.call_count, 0)
        self.assertIsNone(_berserk_of(self.garrick))
        self.assertToldNothingOfControl(self.garrick, witness)

    def test_a_hit_into_the_knockout_band_still_rolls(self) -> None:
        """Ruling 21: 60 to 15 is in the knockout band, but Garrick can still act."""
        self.vitals.health = 60
        self.vitals.save(update_fields=["health"])
        self.watch(self.garrick)

        with force_check_outcome(self.failure) as capture:
            self.hit(45)

        self.assertEqual(capture.target_difficulty, 30)
        self.assertIsNotNone(_berserk_of(self.garrick))
        self.assertTold(self.garrick, "You lose control: Berserk, severity 3, for 3 rounds.")

    @override_settings(SEED_SAMPLE_CONTENT=True)  # the Endurance check type gates on #2698
    def test_a_hit_that_knocks_him_out_rolls_no_wound_trigger(self) -> None:
        """N1: 100 to 15 is a knockout-band hit; the forced knockout lands first, so the
        unconscious Garrick never rolls the trigger his 50 percent line would fire."""
        unconscious = knock_out_condition()
        self.knockout_pool(unconscious)
        witness = self.make_player("Witness", room=self.field)
        self.watch(self.garrick, witness)

        spy = self.brute_swings(85, self.failure)

        self.assertEqual(self.vitals.__class__.objects.get(pk=self.vitals.pk).health, 15)
        self.assertTrue(
            any(i.condition_id == unconscious.pk for i in get_active_conditions(self.garrick))
        )
        self.assertEqual(self.trigger_rolls(spy), 0)
        self.assertIsNone(_berserk_of(self.garrick))
        self.assertToldNothingOfControl(self.garrick, witness)

    @override_settings(SEED_SAMPLE_CONTENT=True)
    def test_a_hit_he_stays_standing_through_rolls_once_the_knockout_is_passed(self) -> None:
        """N1, the other half: a passed knockout check leaves him able to act, so he rolls."""
        self.knockout_pool(knock_out_condition())

        spy = self.brute_swings(85, self.success)

        self.assertEqual(self.trigger_rolls(spy), 1)

    def test_a_character_who_cannot_act_rolls_no_wound_trigger(self) -> None:
        knock_out(self.garrick)
        witness = self.make_player("Witness", room=self.field)
        self.watch(self.garrick, witness)
        with patch("world.checks.services.perform_check", wraps=perform_check) as rolled:
            self.hit(60)

        self.assertEqual(rolled.call_count, 0)
        self.assertIsNone(_berserk_of(self.garrick))
        self.assertToldNothingOfControl(self.garrick, witness)

    def test_the_room_hears_the_persona_not_the_character(self) -> None:
        """A disguised Garrick is named by the face he wears, never his own name."""
        hood = PersonaFactory(
            character_sheet=self.sheet, persona_type=PersonaType.TEMPORARY, name="a hooded man"
        )
        self.sheet.active_persona = hood
        self.sheet.save(update_fields=["active_persona"])
        witness = self.make_player("Witness", room=self.field)
        self.watch(witness)
        with force_check_outcome(self.failure):
            self.hit(60)

        self.assertTold(
            witness,
            "a hooded man falls below 50% health. a hooded man fights to keep control.",
        )
        self.assertTold(witness, "a hooded man loses control: Berserk, severity 3, for 3 rounds.")
        self.assertNotTold(witness, "Garrick")

    def test_a_swing_in_a_round_writes_the_loss_of_control_as_a_round_line(self) -> None:
        """R1: a wound trigger fired inside a round is a narration row in the scene log, so
        a reload still shows it. The row names the face Garrick wears, never his own name.

        Ruling 38: cause before effect. The damage rolls the trigger before the swing's
        own line goes out, and the trigger's row waits for that line, so it follows it.
        """
        from world.scenes.models import Interaction

        hood = PersonaFactory(
            character_sheet=self.sheet, persona_type=PersonaType.TEMPORARY, name="a hooded man"
        )
        self.sheet.active_persona = hood
        self.sheet.save(update_fields=["active_persona"])
        witness = self.make_player("Witness", room=self.field)
        self.watch(witness)

        self.brute_swings(60, self.failure)

        self.assertIsNotNone(_berserk_of(self.garrick))
        line = "a hooded man fights to keep control."
        persisted = Interaction.objects.filter(
            scene=self.seat.encounter.scene, content__contains=line
        )
        self.assertEqual(persisted.count(), 1)
        self.assertEqual(
            persisted.get().content,
            "a hooded man falls below 50% health. a hooded man fights to keep control. Hold "
            "the rage vs 30: Failure. a hooded man loses control: Berserk, severity 3, for 3 "
            "rounds.",
        )
        self.assertShownRow(witness, line)
        self.assertNotTold(witness, "Garrick")
        rows = self.mailbox(witness).rows
        control = next(i for i, row in enumerate(rows) if line in row)
        swing = next(i for i, row in enumerate(rows) if "Haymaker strikes a hooded man" in row)
        self.assertEqual(swing + 1, control, rows)

    def test_a_disguised_fighter_who_declares_nothing_holds_back_under_the_disguise(
        self,
    ) -> None:
        """R2: the held-back round line names the face Garrick wears, never his key."""
        hood = PersonaFactory(
            character_sheet=self.sheet, persona_type=PersonaType.TEMPORARY, name="a hooded man"
        )
        self.sheet.active_persona = hood
        self.sheet.save(update_fields=["active_persona"])
        witness = self.make_player("Witness", room=self.field)
        self.watch(witness)

        self.brute_swings(10, self.success)

        self.assertShownRow(witness, "a hooded man holds back.")
        self.assertFalse(
            any("Garrick" in row for row in self.mailbox(witness).rows),
            self.mailbox(witness).rows,
        )

    def test_nothing_is_told_until_the_hit_commits(self) -> None:
        witness = self.make_player("Witness", room=self.field)
        self.watch(witness)
        with (
            self.captureOnCommitCallbacks(execute=False) as pending,
            force_check_outcome(self.failure),
        ):
            apply_damage_to_participant(self.seat, 60)

        self.assertNotTold(witness, "loses control")
        self.assertTrue(pending)

    def test_a_held_roll_applies_nothing(self) -> None:
        """A held roll lands on a band that applies nothing and moves no control, so the game
        says nothing of it: Garrick and the room are told nothing (a quiet success)."""
        witness = self.make_player("Witness", room=self.field)
        self.watch(self.garrick, witness)
        with force_check_outcome(self.success) as capture:
            self.hit(60)

        self.assertEqual(capture.target_difficulty, 30)
        self.assertIsNone(_berserk_of(self.garrick))
        self.assertToldNothingOfControl(self.garrick, witness)

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

    def test_an_already_compelled_character_rolls_nothing(self) -> None:
        """Ruling 24: a raging Garrick does not re-roll on each crossing."""
        apply_condition(self.garrick, self.berserk, severity=1, duration_rounds=3)
        witness = self.make_player("Witness", room=self.field)
        self.watch(self.garrick, witness)

        with (
            patch("world.checks.services.perform_check", wraps=perform_check) as rolled,
            force_check_outcome(self.failure),
        ):
            self.hit(60)

        self.assertEqual(rolled.call_count, 0)
        self.assertEqual(_berserk_of(self.garrick).severity, 1)
        self.assertToldNothingOfControl(self.garrick, witness)

    def test_a_character_without_the_vulnerability_never_rolls(self) -> None:
        safe = self.make_player("Safe", room=self.field)
        CharacterVitals.objects.create(
            character_sheet=safe.sheet_data, health=100, max_health=100, base_max_health=100
        )
        seat = CombatParticipantFactory(
            encounter=self.seat.encounter, character_sheet=safe.sheet_data
        )
        self.watch(safe, self.garrick)
        with (
            patch("world.checks.services.perform_check", wraps=perform_check) as rolled,
            self.captureOnCommitCallbacks(execute=True),
        ):
            apply_damage_to_participant(seat, 80)

        self.assertEqual(rolled.call_count, 0)
        self.assertEqual(CharacterVitals.objects.get(character_sheet=safe.sheet_data).health, 20)
        self.assertToldNothingOfControl(safe, self.garrick)


class StageTriggers(_ControlLossCase):
    def test_stage_trigger_fires_on_entering_its_stage(self) -> None:
        room = self.make_room("The Chapel")
        maren = self.make_player("Maren", room=room)
        curse = ConditionTemplateFactory(name="Hollow curse", has_progression=True)
        ConditionStageFactory(condition=curse, stage_order=1, severity_threshold=1)
        ConditionStageFactory(condition=curse, stage_order=2, severity_threshold=5)
        third = ConditionStageFactory(
            condition=curse, stage_order=3, severity_threshold=10, name="the Hollowing"
        )
        trigger = ControlLossTriggerFactory(
            vulnerability=curse, fires_on=ControlLossFiresOn.CONDITION_STAGE, stage=third,
            base_difficulty=25, check_type=CheckTypeFactory(name="Hold fast"),
        )  # fmt: skip
        self.band(trigger, self.failure, applies=self.berserk)
        instance = apply_condition(maren, curse).instance
        self.watch(maren)

        with patch("world.checks.services.perform_check", wraps=perform_check) as rolled:
            advance_condition_severity(instance, 5)
            self.assertEqual(rolled.call_count, 0)
            self.assertIsNone(_berserk_of(maren))
            self.assertToldNothingOfControl(maren)
            with (
                self.captureOnCommitCallbacks(execute=True),
                force_check_outcome(self.failure) as capture,
            ):
                advance_condition_severity(instance, 5)

        self.assertEqual(capture.target_difficulty, 25)
        self.assertEqual(_berserk_of(maren).severity, 3)
        self.assertTold(
            maren,
            "Hollow curse reaches the Hollowing. You fight to keep control. Hold fast vs 25: "
            "Failure. You lose control: Berserk, severity 3, for 3 rounds.",
        )

    def _timed_curse(self):
        """A curse that moves from stage 1 to stage 2 after one round; stage 2 triggers."""
        curse = ConditionTemplateFactory(name="Creeping curse", has_progression=True)
        ConditionStageFactory(condition=curse, stage_order=1, rounds_to_next=1)
        second = ConditionStageFactory(condition=curse, stage_order=2, rounds_to_next=None)
        trigger = ControlLossTriggerFactory(
            vulnerability=curse, fires_on=ControlLossFiresOn.CONDITION_STAGE, stage=second,
            base_difficulty=25,
        )  # fmt: skip
        self.band(trigger, self.failure, applies=self.berserk)
        return curse

    def test_a_stage_reached_by_the_round_tick_fires_its_trigger(self) -> None:
        """I1: the curse reaches its last stage as a combat round ends, and Maren rolls."""
        room = self.make_room("The Chapel")
        maren = self.make_player("Maren", room=room)
        CharacterVitals.objects.create(
            character_sheet=maren.sheet_data, health=100, max_health=100, base_max_health=100
        )
        apply_condition(maren, self._timed_curse())
        encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1, room=room)
        CombatParticipantFactory(
            encounter=encounter, character_sheet=maren.sheet_data, status=ParticipantStatus.ACTIVE
        )
        CombatOpponentFactory(encounter=encounter, name="Shade", health=500, max_health=500)
        self.watch(maren)

        with (
            self.captureOnCommitCallbacks(execute=True),
            force_check_outcome(self.failure) as capture,
        ):
            resolve_round(encounter, offense_check_fn=_land_the_swing)

        self.assertEqual(capture.target_difficulty, 25)
        self.assertIsNotNone(_berserk_of(maren))
        # Inside the round the line is one of the round's narration rows (R1).
        self.assertShownRow(maren, "Maren loses control: Berserk, severity 3, for 3 rounds.")
        self.assertNotTold(maren, "You lose control")

    def test_a_rage_that_runs_out_in_the_same_tick_does_not_suppress_the_trigger(self) -> None:
        """N3: Maren's one-round Berserk runs out as the round ends, the same tick the curse
        reaches its trigger stage. The expired rage no longer counts, so she rolls."""
        room = self.make_room("The Chapel")
        maren = self.make_player("Maren", room=room)
        CharacterVitals.objects.create(
            character_sheet=maren.sheet_data, health=100, max_health=100, base_max_health=100
        )
        apply_condition(maren, self._timed_curse())
        apply_condition(maren, self.berserk, severity=1, duration_rounds=1)
        encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1, room=room)
        CombatParticipantFactory(
            encounter=encounter, character_sheet=maren.sheet_data, status=ParticipantStatus.ACTIVE
        )
        CombatOpponentFactory(encounter=encounter, name="Shade", health=500, max_health=500)

        with (
            self.captureOnCommitCallbacks(execute=True),
            force_check_outcome(self.failure) as capture,
        ):
            resolve_round(encounter, offense_check_fn=_land_the_swing)

        self.assertEqual(capture.target_difficulty, 25)
        berserk = _berserk_of(maren)
        self.assertIsNotNone(berserk)
        self.assertEqual(berserk.severity, 3)

    def test_a_stage_reached_by_a_flow_fires_its_trigger(self) -> None:
        """I1: a flow's advance_condition_stage step moves the curse on, and Maren rolls."""
        room = self.make_room("The Chapel")
        maren = self.make_player("Maren", room=room)
        curse = self._timed_curse()
        apply_condition(maren, curse)

        with (
            self.captureOnCommitCallbacks(execute=True),
            force_check_outcome(self.failure),
        ):
            advance_condition_stage(
                payload=SimpleNamespace(character=maren), condition_name=curse.name
            )

        self.assertIsNotNone(_berserk_of(maren))

    def test_an_npc_carrying_the_curse_never_rolls(self) -> None:
        from evennia_extensions.factories import CharacterFactory
        from world.character_sheets.factories import CharacterSheetFactory

        room = self.make_room("The Crypt")
        witness = self.make_player("Witness", room=room)
        self.watch(witness)
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

        with (
            patch("world.checks.services.perform_check", wraps=perform_check) as rolled,
            self.captureOnCommitCallbacks(execute=True),
        ):
            advance_condition_severity(instance, 5)

        self.assertEqual(rolled.call_count, 0)
        self.assertIsNone(_berserk_of(ghoul))
        self.assertToldNothingOfControl(witness)


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
        with (
            self.captureOnCommitCallbacks(execute=True),
            _night_full_moon(),
            force_check_outcome(self.failure) as capture,
        ):
            moon_reconcile_tick()

        # 20 + 5 x 10 - 10 x level 1 - min(30, 5 x thread level 2) = 50
        self.assertEqual(capture.target_difficulty, 50)
        self.assertEqual(_berserk_of(self.wynn).severity, 3)
        check = self.trigger.check_type.name
        self.assertTold(
            self.wynn,
            f"The moon pulls at you. You fight to keep control. {check} vs 50: Failure. "
            "You lose control: Berserk, severity 3, for 3 rounds.",
        )

    def test_a_held_roll_leaves_the_lycan_themself(self) -> None:
        """The seeded Success band applies nothing and moves no control, so the game says
        nothing of a held moon roll: Wynn is told nothing."""
        self.watch(self.wynn)
        with (
            self.captureOnCommitCallbacks(execute=True),
            _night_full_moon(),
            force_check_outcome(self.success) as capture,
        ):
            moon_reconcile_tick()

        self.assertEqual(capture.target_difficulty, 50)
        self.assertIsNone(_berserk_of(self.wynn))
        self.assertToldNothingOfControl(self.wynn)

    def test_a_daylit_moon_never_rolls(self) -> None:
        with (
            patch("world.species.moon_pull.get_ic_phase", return_value=TimePhase.DAY),
            patch("world.checks.services.perform_check", wraps=perform_check) as rolled,
        ):
            moon_reconcile_tick()

        self.assertEqual(rolled.call_count, 0)
        self.assertIsNone(_berserk_of(self.wynn))
        self.assertFalse(ActiveAlternateSelf.objects.filter(character=self.sheet).exists())

    def moon_rolls(self, spy) -> int:
        """The spied rolls made on the moon trigger's check type."""
        return sum(
            1
            for call in spy.call_args_list
            if (call.args[1] if len(call.args) > 1 else call.kwargs.get("check_type"))
            == self.trigger.check_type
        )

    def test_a_character_without_lycan_blood_never_rolls(self) -> None:
        """Tam stands on the same hill under the same full moon, with no lycan blood."""
        tam = self.make_player("Tam", room=self.wynn.location)
        self.watch(tam)
        with (
            self.captureOnCommitCallbacks(execute=True),
            _night_full_moon(),
            patch("world.checks.services.perform_check", wraps=perform_check) as rolled,
        ):
            moon_reconcile_tick()

        self.assertEqual(self.moon_rolls(rolled), 1)  # Wynn's roll, never Tam's
        self.assertIsNone(_berserk_of(tam))
        self.assertNotTold(tam, "You fight to keep control")

    def test_a_weak_moon_never_rolls(self) -> None:
        """A night moon at 0.4 pulls 4, short of the seeded trigger's minimum pull of 6."""
        self.watch(self.wynn)
        with (
            self.captureOnCommitCallbacks(execute=True),
            patch.multiple(
                "world.species.moon_pull",
                get_ic_phase=lambda: TimePhase.NIGHT,
                get_moon_illumination=lambda: 0.4,
            ),
            patch("world.checks.services.perform_check", wraps=perform_check) as rolled,
        ):
            moon_reconcile_tick()

        self.assertEqual(self.moon_rolls(rolled), 0)
        self.assertIsNone(_berserk_of(self.wynn))
        self.assertToldNothingOfControl(self.wynn)

    def test_an_already_raging_lycan_rampages_instead_of_rolling(self) -> None:
        """A Wynn already in a Berserk rage rolls no moon trigger; with nobody to fight,
        the rage vents at the empty hill and the room sees it."""
        apply_condition(self.wynn, self.berserk, severity=1, duration_rounds=3)
        self.watch(self.wynn)
        with (
            self.captureOnCommitCallbacks(execute=True),
            _night_full_moon(),
            patch("world.checks.services.perform_check", wraps=perform_check) as rolled,
        ):
            moon_reconcile_tick()

        self.assertEqual(self.moon_rolls(rolled), 0)
        self.assertEqual(_berserk_of(self.wynn).severity, 1)
        self.assertTold(self.wynn, "Wynn rages at nothing and everything")
        self.assertToldNothingOfControl(self.wynn)

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

        # Kept as a modifier assertion: a condition modifier moves only the roll's points,
        # never its difficulty, and the outcome a single real roll lands on is chance, so
        # the -10 has no effect a player or the capture can see on one roll.
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

    def room_rows(self) -> list[str]:
        """The round lines Mira's room was pushed, in the order they went out."""
        return self.mailbox(self.mira).rows

    def assertRoomRow(self, needle: str) -> None:  # noqa: N802 - unittest style
        """The round narration pushed to Mira's room carries ``needle``."""
        self.assertShownRow(self.mira, needle)

    def assertNoRoomRow(self, needle: str) -> None:  # noqa: N802 - unittest style
        """No round line pushed to Mira's room carries ``needle``."""
        rows = self.room_rows()
        if any(needle in row for row in rows):
            self.fail(f"Mira's room was pushed a row with {needle!r}. Rows:\n{rows}")


class ACompelledFighterWhoAttacks(_CompelledMira):
    def test_compelled_pc_attacking_rolls_nothing(self) -> None:
        told = self.telnet(self.mira, "cast Claw at Bandit Captain")
        self.assertNotIn("Could not", told)

        with self.resist_rolls() as spy:
            self.resolve()

        compulsion = self.berserk.compulsion
        self.assertEqual(self.rolled_on(spy, compulsion.check_type), [])
        self.assertNoRoomRow("tries to")

    def test_a_waiting_strike_is_an_attack_and_rolls_nothing(self) -> None:
        told = self.telnet(self.mira, "combat await Claw")
        self.assertEqual(self.declared().maneuver, CombatManeuver.AWAIT_OPENING, told)

        with self.resist_rolls() as spy:
            self.resolve()

        self.assertEqual(self.rolled_on(spy, self.berserk.compulsion.check_type), [])
        self.assertNoRoomRow("tries to")
        # The rage keeps the attack she steered it into; it is never swapped for its own.
        self.assertEqual(self.declared().maneuver, CombatManeuver.AWAIT_OPENING)

    def test_idle_compelled_pc_is_auto_declared(self) -> None:
        with self.resist_rolls() as spy:
            self.resolve()

        self.assertEqual(self.rolled_on(spy, self.berserk.compulsion.check_type), [])
        action = self.declared()
        self.assertEqual(action.focused_action, self.claw)
        self.assertEqual(action.focused_opponent_target, self.captain)
        # The rage never consents to Soulfray risk for the player (AFK never kills).
        self.assertFalse(action.confirm_soulfray_risk)


class AMaskedFighterWhoseRageAttacks(_CompelledMira):
    """Ruling 43: the action card a masked fighter's attack writes is signed with the mask.

    Mira masks herself ("persona mask scarred sellsword") and declares nothing; Berserk
    attacks for her. Wynn, in the same room, reads the scene feed over REST. Expected
    from the ruling: the card names the face Mira presents (the mask command names it
    "a person wearing a <what she typed>"), never her own name.
    """

    def test_wynn_reads_the_card_signed_with_the_mask(self) -> None:
        wynn = self.make_player("Wynn", room=self.road)
        told = self.telnet(self.mira, "persona mask scarred sellsword")

        self.resolve()

        response = self.api(self.account_of(wynn)).get(
            f"/api/interactions/?scene={self.encounter.scene_id}"
        )
        self.assertEqual(response.status_code, 200, response.content)
        rows = response.json()
        rows = rows["results"] if isinstance(rows, dict) else rows
        cards = [row for row in rows if row["mode"] == "action"]
        self.assertEqual(len(cards), 1, (rows, told))
        mask = self.sheet.personas.get(persona_type=PersonaType.TEMPORARY)
        self.assertEqual(
            (cards[0]["persona"]["id"], cards[0]["persona"]["name"]),
            (mask.pk, "a person wearing a scarred sellsword"),
        )
        self.assertNotIn("Mira", str(cards[0]))


class ACompelledFighterWhoFlees(_CompelledMira):
    def test_compelled_flee_partial_success_flees_at_penalty(self) -> None:
        result = self.web(self.mira, "combat_flee")
        self.assertTrue(result.detail.success, result.detail.message)

        with self.resist_rolls() as spy, force_check_outcome(self.partial):
            self.resolve()

        roll = "Mira tries to flee against Berserk. Resist compulsion vs 36: Partial Success."
        strain = "Berserk drags at Mira: -4 to this action, Control -2."
        rows = self.room_rows()
        at_roll = next(i for i, row in enumerate(rows) if roll in row)
        at_strain = next(i for i, row in enumerate(rows) if strain in row)
        # Ruling 36: the strained cost is told from the band, right after the roll line.
        self.assertEqual(at_strain, at_roll + 1, rows)
        flee_rolls = self.rolled_on(spy, self.flee_check)
        self.assertEqual(len(flee_rolls), 1)
        # perform_check(character, check_type, target_difficulty, extra_modifiers, ...)
        self.assertEqual(flee_rolls[0].args[3], -4)
        self.assertEqual(self.declared().compulsion_penalty, 4)

    def test_compelled_flee_failure_attacks_instead(self) -> None:
        self.telnet(self.mira, "combat flee")

        with self.resist_rolls() as spy, force_check_outcome(self.failure):
            self.resolve()

        self.assertRoomRow("Resist compulsion vs 36: Failure.")
        self.assertRoomRow("Berserk wins out: Mira attacks Bandit Captain.")
        self.assertEqual(self.rolled_on(spy, self.flee_check), [])
        action = self.declared()
        self.assertIsNone(action.maneuver)
        self.assertEqual(action.focused_action, self.claw)
        self.assertFalse(action.confirm_soulfray_risk)
        self.seat.refresh_from_db()
        self.assertEqual(self.seat.status, ParticipantStatus.ACTIVE)

    def test_the_room_hears_the_roll_then_the_outcome_then_the_attack(self) -> None:
        """L1: the compulsion lines go out in the round's own narration order."""
        self.telnet(self.mira, "combat flee")
        before = len(self.room_rows())

        with force_check_outcome(self.failure):
            self.resolve()

        rows = self.room_rows()[before:]

        def first(needle: str) -> int:
            found = [i for i, row in enumerate(rows) if needle in row]
            self.assertTrue(found, f"no round line with {needle!r}. Rows:\n{rows}")
            return found[0]

        roll = first("Mira tries to flee against Berserk. Resist compulsion vs 36: Failure.")
        outcome = first("Berserk wins out: Mira attacks Bandit Captain.")
        attack = first("Claw")
        self.assertLess(roll, outcome, rows)
        self.assertLess(outcome, attack, rows)

    def test_failed_resist_with_no_attack_available_cancels_without_error(self) -> None:
        CharacterTechnique.objects.filter(character=self.sheet, technique=self.claw).delete()
        self.telnet(self.mira, "combat flee")

        with force_check_outcome(self.failure):
            self.resolve()

        self.assertRoomRow("Berserk wins out: Mira gives up trying to flee.")
        self.assertIsNone(self.declared())


class ACompelledFighterWhoHeals(_CompelledMira):
    def test_compelled_heal_rolls_at_base_difficulty(self) -> None:
        told = self.telnet(self.mira, "cast Mend")
        self.assertNotIn("Could not", told)

        with force_check_outcome(self.success):
            self.resolve()

        # 25 base + 2 per severity x 3, and Mend is not a forbidden action.
        self.assertRoomRow(
            "Mira tries to use Mend against Berserk. Resist compulsion vs 31: Success."
        )
        self.assertEqual(self.declared().focused_action, self.mend)

    def test_a_strained_mend_rolls_at_the_penalty(self) -> None:
        self.telnet(self.mira, "cast Mend")
        offense = MagicMock(wraps=_land_the_swing)

        with force_check_outcome(self.partial):
            self.resolve(offense)

        self.assertRoomRow("Resist compulsion vs 31: Partial Success.")
        self.assertRoomRow("Berserk drags at Mira: -4 to this action, Control -2.")
        # Kept as a modifier assertion: the strain penalty moves only the Mend roll's points,
        # not its difficulty or any line, so it has no visible effect on a pinned roll.
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
        self.assertRoomRow("Mira tries to parley against Berserk. Resist compulsion vs 36")
        parley_rolls = self.rolled_on(spy, self.parley_check)
        self.assertEqual(len(parley_rolls), 1)
        # Kept as a modifier assertion: the strain penalty moves only the parley roll's
        # points, not its difficulty or any line, so it has no visible effect on one roll.
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

        self.assertRoomRow(
            "Mira tries to flee against Battle fever. Resist compulsion vs 10: Success."
        )
        self.assertNoRoomRow("against Berserk")


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
        # L2 and ruling 34: the steady line names the bonus the second roll carried, its
        # check and outcome, and the anima Brann's pool actually lost.
        self.assertRoomRow(
            "Brann steadies Mira (+4). Resist compulsion vs 36: Success. "
            "Brann spends 3 anima; their next reaction this round is harder."
        )
        self.assertNoRoomRow("Berserk wins out")
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
        self.assertRoomRow("Berserk wins out: Mira attacks Bandit Captain.")
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
        self.assertRoomRow("Brann steadies Mira (+24). Resist compulsion vs 36: Success.")
        self.assertEqual(self.anima(brann), 20 - STEADY_ANIMA)
        self.assertEqual(self.anima(cade), 20)

    def test_equal_bonuses_go_to_the_lowest_participant_pk(self) -> None:
        brann = self.ally("Brann", capability=4)
        cade = self.ally("Cade", capability=4)
        for ally in (cade, brann):
            self.web(ally, "combat_steady", steady=True)
        self.telnet(self.mira, "combat flee")

        self.resolve_with_rolls(self.failure, self.success)

        self.assertRoomRow("Brann steadies Mira (+4).")
        self.assertEqual(self.anima(cade), 20)

    def test_a_compelled_ally_cannot_steady(self) -> None:
        cade = self.ally("Cade", capability=4)
        self.web(cade, "combat_steady", steady=True)
        apply_condition(cade, self.berserk, severity=3, duration_rounds=3)
        self.telnet(self.mira, "combat flee")

        calls = self.resolve_with_rolls(self.failure, self.success)

        self.assertEqual(len(calls), 1)
        self.assertNoRoomRow("steadies Mira")
        self.assertEqual(self.anima(cade), 20)

    def test_an_ally_who_cannot_act_does_not_steady(self) -> None:
        """I4: Tomas turned the plan on, then was knocked out; he steadies nobody."""
        tomas = self.ally("Tomas", capability=4)
        self.web(tomas, "combat_steady", steady=True)
        knock_out(tomas)
        self.telnet(self.mira, "combat flee")

        calls = self.resolve_with_rolls(self.failure, self.success)

        self.assertEqual(len(calls), 1)
        self.assertNoRoomRow("steadies Mira")
        self.assertEqual(self.anima(tomas), 20)

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

    def test_a_failed_leave_waits_for_the_next_round(self) -> None:
        """Ruling 20: in a fight, one try a round; the next round she may roll again."""
        with force_check_outcome(self.failure):
            self.telnet(self.mira, "combat leave")

        with self.resist_rolls() as spy:
            told = self.telnet(self.mira, "combat leave")
        self.assertIn("Berserk still holds you. You can try again next round.", told)
        self.assertNotIn("You cannot break away.", told)
        self.assertEqual(spy.call_count, 0)

        self.encounter.round_number = 2
        self.encounter.save(update_fields=["round_number"])
        with force_check_outcome(self.success):
            result = self.web(self.mira, "combat_leave")

        self.assertTrue(result.detail.success, result.detail.message)
        self.seat.refresh_from_db()
        self.assertEqual(self.seat.status, ParticipantStatus.REMOVED)

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

        with minutes_later(6), force_check_outcome(self.success):
            result = self.web(self.mira, "revert_form")

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertFalse(self.wearing_the_beast())

    def test_a_failed_revert_through_the_rest_endpoint_is_refused(self) -> None:
        """The web client's change-back button posts to the REST endpoint: a failed roll
        there is a 400 that says so, and Mira still wears the Beast."""
        apply_condition(self.mira, self.berserk, severity=3, duration_rounds=3)

        with force_check_outcome(self.failure):
            response = self.api(self.account_of(self.mira)).post(
                "/api/forms/alternate-selves/revert/", format="json"
            )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("You cannot change back.", str(response.data))
        self.assertTrue(self.wearing_the_beast())

    def test_a_failed_revert_waits_before_the_next_try(self) -> None:
        """Ruling 20: out of combat, Berserk's 5-minute wait follows a failed roll."""
        apply_condition(self.mira, self.berserk, severity=3, duration_rounds=3)
        with force_check_outcome(self.failure):
            self.telnet(self.mira, "form revert")

        with self.resist_rolls() as spy:
            told = self.telnet(self.mira, "form revert")
            later = self.web(self.mira, "revert_form")

        self.assertIn("Berserk still holds you. You can try again in 5 minutes.", told)
        self.assertNotIn("Resist compulsion", told)
        self.assertFalse(later.detail.success)
        self.assertEqual(spy.call_count, 0)
        self.assertTrue(self.wearing_the_beast())

        with minutes_later(4), self.resist_rolls() as spy:
            told = self.telnet(self.mira, "form revert")
        self.assertIn("You can try again in 1 minute.", told)
        self.assertEqual(spy.call_count, 0)

        with minutes_later(6), force_check_outcome(self.success):
            self.telnet(self.mira, "form revert")
        self.assertFalse(self.wearing_the_beast())

    def test_the_worn_self_lists_what_changing_back_costs(self) -> None:
        apply_condition(self.mira, self.berserk, severity=3, duration_rounds=3)
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

        with minutes_later(6), force_check_outcome(self.success):
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
            {
                "action_key": "flee",
                "label": "Flee",
                "difficulty": 36,
                "forbidden": True,
                "extra_difficulty": 5,
            },
        )
        # Leaving and changing back roll too, though neither is declared in the round.
        self.assertIn("leave", against)
        self.assertEqual(against["revert_form"]["difficulty"], 41)
        self.assertTrue(against["revert_form"]["forbidden"])
        self.assertNotIn("engage", against)
        self.assertNotIn("yield", against)
        self.assertEqual(own["attack_target_name"], "Bandit Captain")
        self.assertIsNone(against["technique_no_target"]["label"])
        self.assertEqual(against["revert_form"]["label"], "Revert form")
        self.assertEqual(against["technique_no_target"]["difficulty"], 31)
        self.assertFalse(against["technique_no_target"]["forbidden"])
        self.assertNotIn("charge", against)
        self.assertIsNone(self.payload(brann, self.ally_seats["Brann"])["compulsion"])

    def test_steady_plan_payload_only_for_a_holder_of_the_capability(self) -> None:
        brann = self.ally("Brann", capability=4)

        plan = self.payload(brann, self.ally_seats["Brann"])["steady_plan"]

        self.assertEqual(
            plan,
            {
                "enabled": False,
                "cost_line": f"{STEADY_ANIMA} anima each",
                "bonus_hint": "+4",
                "capability_name": self.steadying.name,
            },
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

    def test_the_encounter_read_for_a_compelled_viewer_costs_a_fixed_query_count(self) -> None:
        """The compulsion and every option's cost come from one read, not one per option."""
        client = self.api(self.account_of(self.mira))
        url = f"/api/combat/{self.encounter.pk}/"
        client.get(url)  # warm the caches

        with self.assertNumQueries(COMPELLED_READ_QUERIES):
            response = client.get(url)

        self.assertEqual(response.status_code, 200, response.content[:400])
        own = next(p for p in response.data["participants"] if p["id"] == self.seat.pk)
        self.assertEqual(own["compulsion"]["condition_name"], "Berserk")
        self.assertGreater(len(own["compulsion"]["against"]), 5)

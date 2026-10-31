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

from unittest.mock import patch

from django.test import override_settings

from integration_tests.harness import JourneyCase
from world.checks.services import perform_check
from world.checks.test_helpers import force_check_outcome
from world.classes.factories import CharacterClassLevelFactory
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.services.damage.damage import apply_damage_to_participant
from world.conditions.berserk_content import ensure_berserk_content
from world.conditions.constants import ControlLossFiresOn
from world.conditions.factories import (
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
from world.game_clock.constants import TimePhase
from world.magic.constants import TargetKind
from world.magic.factories import GiftFactory, ThreadFactory
from world.magic.services.fury import get_berserk_template
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
        with force_check_outcome(self.failure) as capture:
            self.hit(60)

        berserk = _berserk_of(self.garrick)
        self.assertIsNotNone(berserk)
        self.assertEqual(berserk.severity, 3)
        self.assertEqual(capture.target_difficulty, 30)

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

        with patch("world.checks.services.perform_check", wraps=perform_check) as rolled:
            advance_condition_severity(instance, 5)
            self.assertEqual(rolled.call_count, 0)
            with force_check_outcome(self.failure) as capture:
                advance_condition_severity(instance, 5)

        self.assertEqual(capture.target_difficulty, 25)
        self.assertEqual(_berserk_of(maren).severity, 3)


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
        self.assertTold(self.wynn, "the beast takes the reins")

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

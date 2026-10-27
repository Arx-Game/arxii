"""A hurt bonded ally raises a player character's intensity through a roll (#4737).

The journey ``AnAllyBeingWounded`` plays a wound through a real round (60 and 20 percent, an
unbonded ally, the next round, an encounter without a curve). What stays here is what that
journey cannot reach: rounding and caps, the bond gates, no-op guards, the install of the
room triggers, and the two-protector fan-out.
"""

from unittest.mock import patch

from django.test import TestCase, override_settings

from flows.models import Trigger
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import ParticipantStatus, SurgeTriggerKind
from world.combat.escalation import (
    ESCALATION_SPIKE_TRIGGER_NAMES,
    apply_ally_hurt_surge,
    install_escalation_room_triggers,
    remove_escalation_room_triggers,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    EscalationCurveFactory,
    SurgeDegreeBandFactory,
    SurgeTuningFactory,
    wire_escalation_content,
)
from world.combat.models import DramaticSurgeRecord
from world.combat.services import apply_damage_to_participant
from world.combat.surge_rolls import surge_roll_for_participant
from world.mechanics.constants import EngagementType
from world.mechanics.engagement import CharacterEngagement
from world.mechanics.services import begin_engagement
from world.relationships.constants import TypeValence
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipLabelFactory,
    RelationshipTypeFactory,
)
from world.scenes.constants import RoundStatus
from world.traits.factories import CheckOutcomeFactory
from world.vitals.models import CharacterVitals

POTENCY_BASE = 5
POTENCY_PER_DEPTH = 1
SUCCESS_BAND_INTENSITY = 15


@override_settings(SEED_SAMPLE_CONTENT=True)  # curve factory and trigger wiring gate on #2698
class AllyHurtSurgeTestCase(TestCase):
    def setUp(self) -> None:
        self.curve = EscalationCurveFactory(spike_minimum_track_points=10)
        self.encounter = CombatEncounterFactory(
            escalation_curve=self.curve, round_number=1, status=RoundStatus.DECLARING
        )
        self.protector = CombatParticipantFactory(
            encounter=self.encounter, status=ParticipantStatus.ACTIVE
        )
        self.victim = CombatParticipantFactory(
            encounter=self.encounter, status=ParticipantStatus.ACTIVE
        )
        self.protector_char = self.protector.character_sheet.character
        self.victim_char = self.victim.character_sheet.character
        self.protector_char.location = self.encounter.room
        self.victim_char.location = self.encounter.room
        begin_engagement(self.protector_char, EngagementType.COMBAT, source=self.encounter)
        begin_engagement(self.victim_char, EngagementType.COMBAT, source=self.encounter)
        self.tuning = SurgeTuningFactory(
            trigger_kind=SurgeTriggerKind.ALLY_HURT,
            check_type=CheckTypeFactory(name="Hurt Ally Composure"),
            potency_base=POTENCY_BASE,
            potency_per_depth=POTENCY_PER_DEPTH,
        )
        self.fail = CheckOutcomeFactory(name="Hurt Failure", success_level=-1)
        self.success = CheckOutcomeFactory(name="Hurt Success", success_level=1)
        SurgeDegreeBandFactory(tuning=self.tuning, outcome=self.fail, intensity=3)
        SurgeDegreeBandFactory(
            tuning=self.tuning, outcome=self.success, intensity=SUCCESS_BAND_INTENSITY
        )

    def _bond(self, *, points: int = 10, fuels: bool = True):
        rel_type = RelationshipTypeFactory(valence=TypeValence.WARM, fuels_escalation_spikes=fuels)
        relationship = CharacterRelationshipFactory(
            source=self.protector.character_sheet,
            target=self.victim.character_sheet,
            is_active=True,
        )
        RelationshipLabelFactory(relationship=relationship, type=rel_type)
        relationship.invested_depth = points
        relationship.save()
        return relationship

    def _hurt(self, damage: int, max_health: int = 100) -> None:
        apply_ally_hurt_surge(
            victim_character=self.victim_char,
            room=self.encounter.room,
            damage=damage,
            max_health=max_health,
        )

    def _intensity(self, character) -> int:
        return CharacterEngagement.objects.get(character=character.sheet_data).intensity_modifier

    def _records(self):
        return DramaticSurgeRecord.objects.filter(trigger_kind=SurgeTriggerKind.ALLY_HURT)


class AllyHurtRollTests(AllyHurtSurgeTestCase):
    """Kept: rounding, caps, the scratch rule, bond gates and depth, called directly."""

    def test_the_cause_names_the_hurt_ally_and_the_wound_percent(self) -> None:
        self._bond()
        with force_check_outcome(self.success):
            self._hurt(damage=60)
        self.assertEqual(
            self._records().get().cause,
            f"{self.victim_char.key}, bonded to {self.protector_char.key}, "
            "loses 60% of their health.",
        )

    def test_the_cause_percent_rounds_half_up_and_caps_at_a_hundred(self) -> None:
        self._bond()
        with force_check_outcome(self.success):
            self._hurt(damage=1, max_health=8)  # 12.5 percent
        self.assertIn("loses 13% of their health", self._records().get().cause)
        self._records().delete()
        with force_check_outcome(self.success):
            self._hurt(damage=250)
        self.assertIn("loses 100% of their health", self._records().get().cause)

    def test_small_wound_rounds_half_up(self) -> None:
        self._bond()
        with force_check_outcome(self.success):
            self._hurt(damage=30)
        # 30% of 15 is 4.5, which rounds up to 5.
        self.assertEqual(self._intensity(self.protector_char), 5)

    def test_wound_beyond_max_health_is_capped_at_the_whole_band(self) -> None:
        self._bond()
        with force_check_outcome(self.success):
            self._hurt(damage=250)
        self.assertEqual(self._intensity(self.protector_char), SUCCESS_BAND_INTENSITY)

    def test_better_roll_surges_at_least_as_much(self) -> None:
        self._bond()
        with force_check_outcome(self.fail):
            self._hurt(damage=100)
        worse = self._intensity(self.protector_char)
        self._records().delete()
        with force_check_outcome(self.success):
            self._hurt(damage=100)
        self.assertGreaterEqual(self._intensity(self.protector_char) - worse, worse)

    def test_a_scratch_that_scales_to_nothing_writes_no_record_and_spares_the_round(self) -> None:
        self._bond()
        with (
            force_check_outcome(self.fail),
            patch.object(self.encounter.room, "msg_contents") as room_msg,
        ):
            self._hurt(damage=3, max_health=40)
        # The failure band's 3 intensity at 3 of 40 HP is 0.225, which floors to 0.
        self.assertEqual(self._records().count(), 0)
        room_msg.assert_not_called()
        self.assertEqual(self._intensity(self.protector_char), 0)
        # The round's slot is still free for a real wound.
        with force_check_outcome(self.fail):
            self._hurt(damage=30, max_health=40)
        self.assertEqual(self._records().get().amount, 2)

    def test_bond_of_a_type_that_does_not_fuel_spikes_gets_nothing(self) -> None:
        self._bond(fuels=False)
        with force_check_outcome(self.success):
            self._hurt(damage=60)
        self.assertFalse(self._records().exists())

    def test_shallow_bond_gets_nothing(self) -> None:
        self._bond(points=9)
        with force_check_outcome(self.success):
            self._hurt(damage=60)
        self.assertFalse(self._records().exists())

    def test_depth_sets_difficulty(self) -> None:
        relationship = self._bond(points=10)
        with force_check_outcome(self.success) as capture:
            self._hurt(damage=60)
        self.assertEqual(capture.target_difficulty, POTENCY_BASE + POTENCY_PER_DEPTH * 10)
        self.assertEqual(self._records().get().potency, POTENCY_BASE + POTENCY_PER_DEPTH * 10)

        relationship.invested_depth = 14
        relationship.save()
        self.encounter.round_number = 2
        self.encounter.save()
        with force_check_outcome(self.success) as capture:
            self._hurt(damage=60)
        self.assertEqual(capture.target_difficulty, POTENCY_BASE + POTENCY_PER_DEPTH * 14)


class AllyHurtTwoProtectorTests(AllyHurtSurgeTestCase):
    """Kept: two protectors need a second bond and a patched roll, one forced shot each."""

    def test_two_bonded_protectors_both_surge_independently(self) -> None:
        self._bond()
        second = CombatParticipantFactory(encounter=self.encounter, status=ParticipantStatus.ACTIVE)
        second_char = second.character_sheet.character
        second_char.location = self.encounter.room
        begin_engagement(second_char, EngagementType.COMBAT, source=self.encounter)
        rel_type = RelationshipTypeFactory(valence=TypeValence.WARM, fuels_escalation_spikes=True)
        relationship = CharacterRelationshipFactory(
            source=second.character_sheet,
            target=self.victim.character_sheet,
            is_active=True,
        )
        RelationshipLabelFactory(relationship=relationship, type=rel_type)
        relationship.invested_depth = 12
        relationship.save()

        # force_check_outcome is single-shot, so force each protector's real roll in turn.
        def forced_roll(participant, check_type, potency):
            with force_check_outcome(self.success):
                return surge_roll_for_participant(participant, check_type, potency)

        with patch("world.combat.surge_rolls.surge_roll_for_participant", side_effect=forced_roll):
            self._hurt(damage=60)

        self.assertEqual(self._records().count(), 2)
        self.assertEqual(
            set(self._records().values_list("participant_id", flat=True)),
            {self.protector.pk, second.pk},
        )
        potencies = {r.participant_id: r.potency for r in self._records()}
        self.assertEqual(potencies[self.protector.pk], POTENCY_BASE + POTENCY_PER_DEPTH * 10)
        self.assertEqual(potencies[second.pk], POTENCY_BASE + POTENCY_PER_DEPTH * 12)


class AllyHurtRepeatTests(AllyHurtSurgeTestCase):
    """Kept: two hits in one round are one event each; the journey plays one wound a round."""

    def test_two_hits_same_round_one_surge(self) -> None:
        self._bond()
        with force_check_outcome(self.success):
            self._hurt(damage=60)
        with force_check_outcome(self.success):
            self._hurt(damage=60)
        self.assertEqual(self._records().count(), 1)
        self.assertEqual(self._intensity(self.protector_char), 9)


class AllyHurtNoopTests(AllyHurtSurgeTestCase):
    """Kept: each guard (zero damage, zero max health, completed, no tuning, no engagement)."""

    def test_zero_damage_noop(self) -> None:
        self._bond()
        with force_check_outcome(self.success):
            self._hurt(damage=0)
        self.assertFalse(self._records().exists())

    def test_zero_max_health_noop(self) -> None:
        self._bond()
        with force_check_outcome(self.success):
            self._hurt(damage=10, max_health=0)
        self.assertFalse(self._records().exists())

    def test_completed_encounter_noop(self) -> None:
        self._bond()
        self.encounter.status = RoundStatus.COMPLETED
        self.encounter.save()
        with force_check_outcome(self.success):
            self._hurt(damage=60)
        self.assertFalse(self._records().exists())

    def test_no_tuning_row_is_a_quiet_noop(self) -> None:
        self._bond()
        self.tuning.delete()
        with self.assertNoLogs("world.combat.surge_rolls", level="WARNING"):
            self._hurt(damage=60)
        self.assertFalse(self._records().exists())

    def test_protector_without_a_combat_engagement_does_not_roll(self) -> None:
        self._bond()
        CharacterEngagement.objects.filter(character=self.protector.character_sheet).delete()
        with force_check_outcome(self.success) as capture:
            self._hurt(damage=60)
        self.assertIsNone(capture.check_type)
        self.assertFalse(self._records().exists())


class AllyHurtWiringTests(AllyHurtSurgeTestCase):
    """Kept: the install and removal of the room triggers is not a thing a player does."""

    def setUp(self) -> None:
        super().setUp()
        wire_escalation_content()

    def test_handler_installed_with_room_triggers(self) -> None:
        self.assertIn("escalation_spike_on_damage", ESCALATION_SPIKE_TRIGGER_NAMES)
        install_escalation_room_triggers(self.encounter)
        installed = Trigger.objects.filter(
            obj=self.encounter.room,
            trigger_definition__name="escalation_spike_on_damage",
        )
        self.assertEqual(installed.count(), 1)
        install_escalation_room_triggers(self.encounter)
        self.assertEqual(installed.count(), 1)
        remove_escalation_room_triggers(self.encounter)
        self.assertFalse(installed.exists())

    def test_damage_in_a_room_without_the_trigger_does_nothing(self) -> None:
        self._bond()
        CharacterVitals.objects.update_or_create(
            character_sheet=self.victim.character_sheet,
            defaults={"health": 100, "max_health": 100},
        )
        with force_check_outcome(self.success):
            apply_damage_to_participant(self.victim, 60)
        self.assertFalse(self._records().exists())

"""Journeys for rolled surges (#4737, slice 1 of #4727): a roll with degrees raises intensity.

Mira and Tomas are played fighters in one escalating encounter in "The Road", against a
Bandit Captain. Staff have authored a surge tuning per beat, with a degree band per roll
outcome. The bands built here are the expected numbers: a Partial result surges 3, a
Success 6 (taunt and rally), and a Success on a hurt ally's roll is worth 15 at full wound.

- The captain's taunt entry deals no damage; Mira rolls Composure against its potency, and
  a better result surges her more. The roll line reaches Mira and nobody else.
- Mira rallies Tomas through ``combat rally``; the Rally roll's result picks Tomas's surge,
  and the next round's rally surges him again.
- Mira is bonded to Tomas. The captain wounds Tomas through a real round; the damage event
  reaches the escalation trigger the round-opening installed in the room, and Mira's surge
  is in proportion to the wound.

Rolls are forced with ``force_check_outcome`` (a single shot per ``with``), so each
outcome is chosen by the test and the degrees are deterministic.
"""

from __future__ import annotations

from django.test import override_settings

from integration_tests.harness import JourneyCase
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import (
    CombatManeuver,
    ParticipantStatus,
    SurgeTriggerKind,
    TargetingMode,
    TargetSelection,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentActionFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    EscalationCurveFactory,
    SurgeDegreeBandFactory,
    SurgeTuningFactory,
    ThreatPoolEntryFactory,
    wire_escalation_content,
)
from world.combat.models import CombatRoundAction, DramaticSurgeRecord
from world.combat.services import begin_declaration_phase, resolve_round
from world.mechanics.constants import EngagementType
from world.mechanics.engagement import CharacterEngagement
from world.mechanics.services import begin_engagement
from world.relationships.constants import TypeValence
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipLabelFactory,
    RelationshipTypeFactory,
)
from world.relationships.models import CharacterRelationship
from world.scenes.constants import RoundStatus
from world.traits.factories import CheckOutcomeFactory
from world.vitals.models import CharacterVitals

PARTIAL_INTENSITY = 3
SUCCESS_INTENSITY = 6
HURT_SUCCESS_INTENSITY = 15
TAUNT_POTENCY = 14
BOND_DEPTH = 10
HURT_POTENCY_BASE = 5
HURT_POTENCY_PER_DEPTH = 1


@override_settings(SEED_SAMPLE_CONTENT=True)  # the curve factory and trigger wiring gate on #2698
class _SurgeField(JourneyCase):
    """An escalating encounter with Mira and Tomas on the road, and a Bandit Captain."""

    # The curve starts pressure rounds after the ones these journeys play, so no pace roll
    # takes the forced outcome before the surge roll does.
    CURVE_START_ROUND = 50

    def setUp(self) -> None:
        super().setUp()
        self.road = self.make_room("The Road")
        self.mira = self.make_player("Mira", room=self.road)
        self.tomas = self.make_player("Tomas", room=self.road)
        for player in (self.mira, self.tomas):
            CharacterVitals.objects.create(
                character_sheet=player.sheet_data, health=100, max_health=100, base_max_health=100
            )
        self.curve = EscalationCurveFactory(
            start_round=self.CURVE_START_ROUND, spike_minimum_track_points=BOND_DEPTH
        )
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING,
            round_number=1,
            room=self.road,
            escalation_curve=self.curve,
        )
        self.mira_seat = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.mira.sheet_data,
            status=ParticipantStatus.ACTIVE,
        )
        self.tomas_seat = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.tomas.sheet_data,
            status=ParticipantStatus.ACTIVE,
        )
        self.captain = CombatOpponentFactory(encounter=self.encounter, name="Bandit Captain")
        self.partial = CheckOutcomeFactory(name="Partial", success_level=0)
        self.success = CheckOutcomeFactory(name="Success", success_level=1)
        self.watch(self.mira, self.tomas)

    def author_tuning(  # noqa: PLR0913 - one tuning row: kind, check, two bands, two potencies
        self,
        kind: str,
        check_name: str,
        *,
        partial: int,
        success: int,
        potency_base: int = 0,
        potency_per_depth: int = 0,
    ):
        tuning = SurgeTuningFactory(
            trigger_kind=kind,
            check_type=CheckTypeFactory(name=check_name),
            potency_base=potency_base,
            potency_per_depth=potency_per_depth,
        )
        SurgeDegreeBandFactory(tuning=tuning, outcome=self.partial, intensity=partial)
        SurgeDegreeBandFactory(tuning=tuning, outcome=self.success, intensity=success)
        return tuning

    def enter_combat(self, *characters) -> None:
        """Seat each character's combat engagement, as the round-opening does for round 2 on."""
        for character in characters:
            begin_engagement(character, EngagementType.COMBAT, source=self.encounter)

    def intensity(self, character) -> int:
        return CharacterEngagement.objects.get(character=character.sheet_data).intensity_modifier

    def records(self, kind: str):
        return DramaticSurgeRecord.objects.filter(trigger_kind=kind)

    def resolve(self, outcome):
        """Resolve the round with the first roll the round makes coming up ``outcome``."""
        with force_check_outcome(outcome):
            return resolve_round(self.encounter)

    def next_round(self) -> None:
        # The room's trigger cache resets on commit; a test's transaction never commits, so
        # run the commit callbacks the real round-opening would have fired.
        with self.captureOnCommitCallbacks(execute=True):
            begin_declaration_phase(self.encounter)
        self.encounter.refresh_from_db()


class BeingTauntedByAnNpc(_SurgeField):
    def setUp(self) -> None:
        super().setUp()
        self.enter_combat(self.mira)
        self.author_tuning(
            SurgeTriggerKind.TAUNT_RECEIVED,
            "Composure",
            partial=PARTIAL_INTENSITY,
            success=SUCCESS_INTENSITY,
        )
        self.entry = ThreatPoolEntryFactory(
            pool=self.captain.threat_pool,
            name="Sneering Jibe",
            base_damage=0,
            taunt_potency=TAUNT_POTENCY,
            targeting_mode=TargetingMode.SINGLE,
            target_selection=TargetSelection.SPECIFIC_ROLE,
        )

    def _captain_jibes_at_mira(self) -> None:
        action = CombatOpponentActionFactory(
            opponent=self.captain,
            threat_entry=self.entry,
            round_number=self.encounter.round_number,
        )
        action.targets.add(self.mira_seat)

    def test_a_taunt_entry_surges_mira_and_shows_her_the_roll(self) -> None:
        self._captain_jibes_at_mira()

        self.resolve(self.partial)

        self.assertEqual(self.intensity(self.mira), PARTIAL_INTENSITY)
        self.assertTold(
            self.mira,
            f"Composure check vs taunt potency {TAUNT_POTENCY}. Partial. "
            f"Intensity +{PARTIAL_INTENSITY}, control 0.",
        )
        record = self.records(SurgeTriggerKind.TAUNT_RECEIVED).get()
        self.assertEqual(record.participant, self.mira_seat)
        self.assertEqual(record.potency, TAUNT_POTENCY)
        self.assertEqual(record.outcome, self.partial)

    def test_the_taunt_does_no_damage_and_the_roll_line_is_hers_alone(self) -> None:
        self._captain_jibes_at_mira()

        self.resolve(self.partial)

        health = CharacterVitals.objects.get(character_sheet=self.mira.sheet_data).health
        self.assertEqual(health, 100)
        self.assertNotTold(self.tomas, "Composure check")
        self.assertEqual(self.intensity_or_zero(self.tomas), 0)

    def intensity_or_zero(self, character) -> int:
        engagement = CharacterEngagement.objects.filter(character=character.sheet_data).first()
        return engagement.intensity_modifier if engagement is not None else 0

    def test_a_better_composure_result_surges_her_more(self) -> None:
        self._captain_jibes_at_mira()
        self.resolve(self.partial)
        after_partial = self.intensity(self.mira)

        self.next_round()
        self._captain_jibes_at_mira()
        self.resolve(self.success)
        gained_on_success = self.intensity(self.mira) - after_partial

        self.assertEqual(after_partial, PARTIAL_INTENSITY)
        self.assertEqual(gained_on_success, SUCCESS_INTENSITY)
        self.assertTold(
            self.mira,
            f"Composure check vs taunt potency {TAUNT_POTENCY}. Success. "
            f"Intensity +{SUCCESS_INTENSITY}, control 0.",
        )
        self.assertEqual(self.records(SurgeTriggerKind.TAUNT_RECEIVED).count(), 2)

    def test_an_encounter_without_a_curve_does_not_surge(self) -> None:
        self.encounter.escalation_curve = None
        self.encounter.save()
        self._captain_jibes_at_mira()

        self.resolve(self.partial)

        self.assertFalse(self.records(SurgeTriggerKind.TAUNT_RECEIVED).exists())
        self.assertNotTold(self.mira, "Composure check")


class BeingRallied(_SurgeField):
    def setUp(self) -> None:
        super().setUp()
        self.enter_combat(self.mira, self.tomas)
        # The Rally roll itself is Mira's "Rally" check; the tuning picks the bands.
        CheckTypeFactory(name="Rally")
        self.author_tuning(
            SurgeTriggerKind.RALLIED,
            "Rally",
            partial=PARTIAL_INTENSITY,
            success=SUCCESS_INTENSITY,
        )

    def test_a_rally_surges_tomas_by_the_degree_of_mira_s_roll(self) -> None:
        told = self.telnet(self.mira, "combat rally Tomas")
        self.assertIn("rally", told.lower())
        declared = CombatRoundAction.objects.get(participant=self.mira_seat, round_number=1)
        self.assertEqual(declared.maneuver, CombatManeuver.RALLY)
        self.assertEqual(declared.focused_ally_target, self.tomas_seat)

        self.resolve(self.success)

        self.assertEqual(self.intensity(self.tomas), SUCCESS_INTENSITY)
        self.assertTold(self.tomas, f"Success. Intensity +{SUCCESS_INTENSITY}, control 0.")
        record = self.records(SurgeTriggerKind.RALLIED).get()
        self.assertEqual(record.participant, self.tomas_seat)
        self.assertEqual(record.subject_sheet, self.mira.sheet_data)
        self.assertIsNone(record.potency)
        # The rallier is not the one surged, and is not shown the roll.
        self.assertEqual(self.intensity(self.mira), 0)
        self.assertNotTold(self.mira, "Intensity +")

    def test_the_next_round_s_rally_surges_him_again(self) -> None:
        self.telnet(self.mira, "combat rally Tomas")
        self.resolve(self.partial)
        self.assertEqual(self.intensity(self.tomas), PARTIAL_INTENSITY)

        self.next_round()
        self.assertEqual(self.encounter.round_number, 2)
        self.telnet(self.mira, "combat rally Tomas")
        self.resolve(self.success)

        self.assertEqual(self.intensity(self.tomas), PARTIAL_INTENSITY + SUCCESS_INTENSITY)
        rounds = list(
            self.records(SurgeTriggerKind.RALLIED)
            .order_by("repeat_round")
            .values_list("repeat_round", flat=True)
        )
        self.assertEqual(rounds, [1, 2])


class AnAllyBeingWounded(_SurgeField):
    """Mira is bonded to Tomas; the captain wounds him through a real round."""

    # Round 2 (after the first round closes) installs the escalation triggers in the room.
    WOUND_ROUND = 2

    def setUp(self) -> None:
        super().setUp()
        wire_escalation_content()
        self.author_tuning(
            SurgeTriggerKind.ALLY_HURT,
            "Composure",
            partial=3,
            success=HURT_SUCCESS_INTENSITY,
            potency_base=HURT_POTENCY_BASE,
            potency_per_depth=HURT_POTENCY_PER_DEPTH,
        )
        bond = RelationshipTypeFactory(valence=TypeValence.WARM, fuels_escalation_spikes=True)
        relationship = CharacterRelationshipFactory(
            source=self.mira.sheet_data,
            target=self.tomas.sheet_data,
            is_active=True,
        )
        RelationshipLabelFactory(relationship=relationship, type=bond)
        relationship.invested_depth = BOND_DEPTH
        relationship.save()
        # Round 1 closes, then round 2 opens: opening it installs the room trigger.
        self.encounter.status = RoundStatus.BETWEEN_ROUNDS
        self.encounter.save()
        self.next_round()
        self.assertEqual(self.encounter.round_number, self.WOUND_ROUND)

    def _captain_wounds_tomas(self, damage: int) -> None:
        entry = ThreatPoolEntryFactory(
            pool=self.captain.threat_pool,
            name="Heavy Blow",
            base_damage=damage,
            targeting_mode=TargetingMode.SINGLE,
            target_selection=TargetSelection.SPECIFIC_ROLE,
        )
        action = CombatOpponentActionFactory(
            opponent=self.captain, threat_entry=entry, round_number=self.WOUND_ROUND
        )
        action.targets.add(self.tomas_seat)

    def _tomas_health(self) -> int:
        return CharacterVitals.objects.get(character_sheet=self.tomas.sheet_data).health

    def test_a_bonded_ally_s_wound_surges_her_in_proportion(self) -> None:
        self._captain_wounds_tomas(60)

        self.resolve(self.success)

        self.assertEqual(self._tomas_health(), 40)
        # Sixty of a hundred health is 60 percent of the Success band's 15.
        self.assertEqual(self.intensity(self.mira), 9)
        self.assertTold(
            self.mira,
            f"Composure check vs peril difficulty "
            f"{HURT_POTENCY_BASE + HURT_POTENCY_PER_DEPTH * BOND_DEPTH}. Success. "
            "Intensity +9, control 0.",
        )
        record = self.records(SurgeTriggerKind.ALLY_HURT).get()
        self.assertEqual(record.participant, self.mira_seat)
        self.assertEqual(record.subject_sheet, self.tomas.sheet_data)
        # The one who was hurt is not the one surged.
        self.assertEqual(self.intensity(self.tomas), 0)

    def test_a_smaller_wound_surges_her_less(self) -> None:
        self._captain_wounds_tomas(20)

        self.resolve(self.success)

        self.assertEqual(self._tomas_health(), 80)
        # Twenty percent of 15.
        self.assertEqual(self.intensity(self.mira), 3)

    def test_without_the_bond_the_wound_surges_nobody(self) -> None:
        CharacterRelationship.objects.filter(source=self.mira.sheet_data).delete()
        self._captain_wounds_tomas(60)

        self.resolve(self.success)

        self.assertEqual(self._tomas_health(), 40)
        self.assertFalse(self.records(SurgeTriggerKind.ALLY_HURT).exists())
        self.assertEqual(self.intensity(self.mira), 0)

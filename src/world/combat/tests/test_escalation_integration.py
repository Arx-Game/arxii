"""Build-to-climax integration arc for the combat escalation engine (#872, Task 10).

Proves the issue's done-when criterion end-to-end with NO escalation-specific
mocking: rounds escalate (begin_declaration_phase -> apply_escalation_tick) ->
cast costs spike (get_runtime_technique_stats + calculate_effective_anima_cost
inside use_technique) -> Soulfray pressure mounts (real severity accumulation
and stage advancement) -> the Audere gate opens (a qualifying cast creates a
PendingAudereOffer via maybe_create_audere_offer).

The second test exercises the bonded-relationship spike through the REAL
damage entry (apply_damage_to_participant -> CHARACTER_INCAPACITATED emit ->
room trigger installed by the round wiring -> relationship_spike_handler).
"""

from itertools import pairwise

from django.test import TestCase, tag

from flows.models import Trigger
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import EncounterStatus
from world.combat.escalation import ESCALATION_SPIKE_TRIGGER_NAMES
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    EscalationCurveFactory,
    wire_escalation_content,
)
from world.combat.services import (
    add_participant,
    apply_damage_to_participant,
    begin_declaration_phase,
)
from world.conditions.models import ConditionInstance, ConditionStage
from world.magic.audere import PendingAudereOffer, check_audere_eligibility
from world.magic.factories import (
    CharacterAnimaFactory,
    SoulfrayConfigFactory,
    TechniqueFactory,
)
from world.magic.services import use_technique
from world.magic.services.techniques import get_runtime_technique_stats
from world.magic.tests.audere_test_helpers import build_audere_gate_fixture
from world.mechanics.constants import EngagementType
from world.mechanics.engagement import CharacterEngagement
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipTrackFactory,
    RelationshipTrackProgressFactory,
)
from world.vitals.models import CharacterVitals


def _resolve(**_kwargs: object) -> str:
    """Minimal cast resolver — resolution outcome is not under test here."""
    return "resolved"


@tag("postgres")  # Soulfray is progressive → apply_condition uses DISTINCT ON (PG-only)
class BuildToClimaxTests(TestCase):
    """#872 done-when: escalating rounds drive cost spikes, Soulfray, and Audere.

    Authored numbers (computed deliberately, asserted exactly):
    - Tiers (gate fixture): Minor threshold=1 (+0 control), Major threshold=15
      (-5 control). AudereThreshold: minimum tier=Major, minimum Soulfray
      stage=3 ("Ripping").
    - Soulfray stage severity thresholds: 10 / 80 / 160.
    - SoulfrayConfig: threshold ratio 0.30, severity_scale 10, deficit_scale 5.
    - Technique: intensity=10, control=4, anima_cost=3. Anima: 5/50.
    - Curve: start_round=2, intensity_step=3, ALL control steps 0 (control
      never keeps pace, so runtime control is fully deterministic regardless
      of the pace check's unseeded-chart outcome).

    Per-round arc:
    - Round 1 (below start_round): modifier 0, intensity 10, control 4,
      cost 9, deficit 4, severity +30 -> total 30 -> stage 1.
    - Round 2: modifier 3, intensity 13, cost 12, deficit 12, severity +70
      -> total 100 -> stage 2. Gate still closed (13 < Major's 15).
    - Round 3: modifier 6, intensity 16 (crosses Major: control -5 -> -1),
      cost 20, deficit 20, severity +110 -> total 210 -> stage 3. The same
      cast's Audere hook sees intensity tier + stage + engagement all open
      and creates the PendingAudereOffer.
    """

    def setUp(self) -> None:
        self.gate = build_audere_gate_fixture(tier_suffix="climax")
        self._seed_soulfray_severity_thresholds()
        SoulfrayConfigFactory()
        self.curve = EscalationCurveFactory(
            start_round=2,
            intensity_step=3,
            control_step_on_success=0,
            control_step_on_partial=0,
            control_step_on_botch=0,
        )
        self.encounter = CombatEncounterFactory(
            escalation_curve=self.curve, status=EncounterStatus.BETWEEN_ROUNDS
        )
        CombatOpponentFactory(encounter=self.encounter)
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.character.location = self.encounter.room
        self.technique = TechniqueFactory(intensity=10, control=4, anima_cost=3)
        self.anima = CharacterAnimaFactory(character=self.character, current=5, maximum=50)

    def _seed_soulfray_severity_thresholds(self) -> None:
        """Author severity thresholds so real accumulation advances the stages.

        The shared gate fixture seeds the three Soulfray stages without
        thresholds (its callers set current_stage directly); this arc reaches
        stage 3 through advance_condition_severity instead.
        """
        thresholds = {1: 10, 2: 80, 3: 160}
        for stage in ConditionStage.objects.filter(condition=self.gate.soulfray_template):
            stage.severity_threshold = thresholds[stage.stage_order]
            stage.save(update_fields=["severity_threshold"])

    def _begin_round_and_assert(self, *, modifier: int, intensity: int):
        """Drive one round start; assert the tick state and return runtime stats."""
        self.encounter.status = EncounterStatus.BETWEEN_ROUNDS
        self.encounter.save(update_fields=["status"])
        begin_declaration_phase(self.encounter)
        engagement = CharacterEngagement.objects.get(character=self.character)
        engagement.refresh_from_db()
        self.assertEqual(engagement.intensity_modifier, modifier)
        stats = get_runtime_technique_stats(self.technique, self.character)
        self.assertEqual(stats.intensity, intensity)
        return stats

    def _cast_and_assert(self, *, cost: int, deficit: int, severity: int, stage: int):
        """Cast through the full pipeline; assert cost/Soulfray and return the result."""
        result = use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=_resolve,
        )
        self.assertTrue(result.confirmed)
        self.assertEqual(result.anima_cost.effective_cost, cost)
        self.assertEqual(result.anima_cost.deficit, deficit)
        self.assertIsNotNone(result.soulfray_result)
        self.assertEqual(result.soulfray_result.severity_added, severity)
        self.assertEqual(self._soulfray_stage_order(), stage)
        return result

    def _soulfray_stage_order(self) -> int:
        instance = ConditionInstance.objects.get(
            target=self.character, condition=self.gate.soulfray_template
        )
        return instance.current_stage.stage_order

    def test_build_to_climax(self) -> None:
        # Unengaged baseline: the +10 social-safety control bonus applies.
        baseline = get_runtime_technique_stats(self.technique, self.character)
        self.assertEqual(baseline.intensity, 10)
        self.assertEqual(baseline.control, 14)  # 4 base + 10 social safety

        # Real entry path: add_participant creates the COMBAT engagement.
        add_participant(self.encounter, self.sheet)
        engagement = CharacterEngagement.objects.get(character=self.character)
        self.assertEqual(engagement.engagement_type, EngagementType.COMBAT)

        # Entering combat strips the social-safety control bonus.
        engaged = get_runtime_technique_stats(self.technique, self.character)
        self.assertEqual(engaged.intensity, 10)
        self.assertEqual(engaged.control, 4)

        # --- Round 1: below start_round -> NO tick. ---
        stats1 = self._begin_round_and_assert(modifier=0, intensity=10)
        # cost 9 = 3 - (4 - 10); deficit 4 = 9 vs 5 anima; severity 30 = 10 + ceil(5*4)
        result1 = self._cast_and_assert(cost=9, deficit=4, severity=30, stage=1)
        self.assertFalse(PendingAudereOffer.objects.filter(character_sheet=self.sheet).exists())

        # --- Round 2: first tick. ---
        stats2 = self._begin_round_and_assert(modifier=3, intensity=13)  # 1 tick * step 3
        # cost 12 = 3 - (4 - 13); anima already at 0; severity 70 = 10 + ceil(5*12);
        # total 100 >= stage-2 threshold 80.
        result2 = self._cast_and_assert(cost=12, deficit=12, severity=70, stage=2)
        # Gate still closed: intensity 13 resolves below the Major tier (15).
        self.assertFalse(check_audere_eligibility(self.character, stats2.intensity))
        self.assertFalse(PendingAudereOffer.objects.filter(character_sheet=self.sheet).exists())

        # --- Round 3: second tick crosses the Major tier. ---
        stats3 = self._begin_round_and_assert(modifier=6, intensity=16)  # 2 ticks * step 3
        # Major tier's -5 control penalty bites (control steps authored to 0,
        # so the pace check cannot perturb this).
        self.assertEqual(stats3.control, -1)
        # cost 20 = 3 - (-1 - 16); severity 110 = 10 + ceil(5*20); total 210 >= 160.
        result3 = self._cast_and_assert(cost=20, deficit=20, severity=110, stage=3)

        # --- Climax: the qualifying cast itself opened the Audere gate. ---
        self.assertTrue(check_audere_eligibility(self.character, stats3.intensity))
        offer = PendingAudereOffer.objects.get(character_sheet=self.sheet)
        self.assertEqual(offer.fired_intensity, 16)
        self.assertEqual(offer.soulfray_stage_order, 3)

        # --- Arc properties: pressure only ever rose, round over round. ---
        intensities = [stats1.intensity, stats2.intensity, stats3.intensity]
        costs = [r.anima_cost.effective_cost for r in (result1, result2, result3)]
        severities = [r.soulfray_result.severity_added for r in (result1, result2, result3)]
        self.assertEqual(intensities, [10, 13, 16])
        self.assertEqual(costs, [9, 12, 20])
        self.assertEqual(severities, [30, 70, 110])
        self.assertTrue(all(a < b for a, b in pairwise(intensities)))
        self.assertTrue(all(a < b for a, b in pairwise(costs)))


class BondedSpikeRealDamagePathTests(TestCase):
    """Relationship spike end-to-end through the real damage entry (#872).

    Engagements come from the real participant-entry path (add_participant),
    the room spike triggers from a real escalating begin_declaration_phase
    (NOT a manual install), and the CHARACTER_INCAPACITATED emit from
    apply_damage_to_participant's knockout-band transition latch.
    """

    def setUp(self) -> None:
        self.curve = EscalationCurveFactory(
            start_round=2,
            intensity_step=2,
            spike_intensity_amount=4,
            spike_minimum_track_points=10,
            control_step_on_success=0,
            control_step_on_partial=0,
            control_step_on_botch=0,
        )
        self.encounter = CombatEncounterFactory(
            escalation_curve=self.curve, status=EncounterStatus.BETWEEN_ROUNDS
        )
        CombatOpponentFactory(encounter=self.encounter)
        self.sheet_a = CharacterSheetFactory()
        self.sheet_b = CharacterSheetFactory()
        self.char_a = self.sheet_a.character
        self.char_b = self.sheet_b.character
        # Real combat emits from room == character.location (services.py);
        # the spike handler walks payload.character.location back to the room.
        self.char_a.location = self.encounter.room
        self.char_b.location = self.encounter.room
        # Real entry path: add_participant creates the COMBAT engagements.
        self.participant_a = add_participant(self.encounter, self.sheet_a)
        self.participant_b = add_participant(self.encounter, self.sheet_b)
        wire_escalation_content()

    def _bond(self, source_sheet, target_sheet, *, points: int = 10) -> None:
        """Active, non-pending relationship with spike-fueling track progress."""
        track = RelationshipTrackFactory(fuels_escalation_spikes=True)
        relationship = CharacterRelationshipFactory(
            source=source_sheet,
            target=target_sheet,
            is_active=True,
            is_pending=False,
        )
        RelationshipTrackProgressFactory(
            relationship=relationship,
            track=track,
            developed_points=points,
            capacity=points,
        )

    def _reset_vitals(self, sheet, *, health: int = 100, max_health: int = 100) -> None:
        vitals, _ = CharacterVitals.objects.get_or_create(
            character_sheet=sheet,
            defaults={"health": health, "max_health": max_health},
        )
        vitals.health = health
        vitals.max_health = max_health
        vitals.save()

    def test_bonded_spike_through_real_damage_path(self) -> None:
        self._bond(self.sheet_a, self.sheet_b)
        self._reset_vitals(self.sheet_b)

        engagement_a = CharacterEngagement.objects.get(character=self.char_a)
        self.assertEqual(engagement_a.engagement_type, EngagementType.COMBAT)
        self.assertEqual(engagement_a.intensity_modifier, 0)

        # The real escalating round start installs the room spike triggers.
        begin_declaration_phase(self.encounter)
        for name in ESCALATION_SPIKE_TRIGGER_NAMES:
            self.assertTrue(
                Trigger.objects.filter(
                    obj=self.encounter.room, trigger_definition__name=name
                ).exists()
            )

        # Round 1 is below start_round (2): no tick — the spike will be the
        # only intensity source, so the final assert is exact.
        engagement_a.refresh_from_db()
        self.assertEqual(engagement_a.intensity_modifier, 0)

        # 100 -> 15 (15% <= 20% knockout band, above death): the real damage
        # entry emits CHARACTER_INCAPACITATED at the room, the installed
        # trigger dispatches relationship_spike_handler, and the bonded
        # survivor's intensity spikes.
        apply_damage_to_participant(self.participant_b, 85)

        engagement_a.refresh_from_db()
        self.assertEqual(engagement_a.intensity_modifier, self.curve.spike_intensity_amount)
        engagement_b = CharacterEngagement.objects.get(character=self.char_b)
        self.assertEqual(engagement_b.intensity_modifier, 0)

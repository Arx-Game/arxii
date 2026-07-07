"""Definition-of-done E2E for the dramatic surge engine (#2013).

Two bonded PCs + one hated foe; ally drops to Bleeding Out -> protector's
next cast provably stronger; hated foe present -> surge on entry;
high-stakes encounter -> faster ramp. Also folds in the ALLY_FALLEN
outcome-delta assertion the grief spike's WIRED-UNPROVEN journey lacked.
"""

from django.test import TestCase, tag

from flows.constants import EventName
from flows.emit import emit_event
from flows.events.payloads import CharacterIncapacitatedPayload
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import ParticipantStatus, StakesLevel
from world.combat.escalation import (
    apply_escalation_tick,
    assign_default_escalation_curve,
    install_escalation_room_triggers,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    EscalationCurveFactory,
    wire_escalation_content,
)
from world.combat.models import StakesEscalationModifier
from world.combat.services import add_opponent
from world.conditions.factories import BleedingOutConditionFactory, ConditionStageFactory
from world.conditions.services import apply_condition
from world.magic.factories import (
    EffectTypeFactory,
    GiftFactory,
    TechniqueFactory,
)
from world.magic.services.techniques import get_runtime_technique_stats
from world.mechanics.constants import EngagementType
from world.mechanics.services import begin_engagement
from world.relationships.constants import TrackSign
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipTrackFactory,
    RelationshipTrackProgressFactory,
)
from world.scenes.factories import PersonaFactory


def _make_technique():
    gift = GiftFactory()
    effect_type = EffectTypeFactory()
    return TechniqueFactory(gift=gift, effect_type=effect_type, intensity=10, control=10)


def _bond(source_sheet, target_sheet, *, sign=TrackSign.POSITIVE, fuels=True, points=10):
    track = RelationshipTrackFactory(sign=sign, fuels_escalation_spikes=fuels)
    relationship = CharacterRelationshipFactory(
        source=source_sheet, target=target_sheet, is_active=True, is_pending=False
    )
    RelationshipTrackProgressFactory(
        relationship=relationship, track=track, developed_points=points, capacity=points
    )


@tag("postgres")
class DramaticSurgeE2ETests(TestCase):
    """Bleeding Out is progressive (PG DISTINCT ON) — Postgres tier only."""

    def setUp(self):
        self.curve = EscalationCurveFactory(
            spike_intensity_amount=3,
            spike_minimum_track_points=5,
            peril_spike_intensity_amount=4,
            hated_foe_spike_intensity_amount=5,
        )
        self.encounter = CombatEncounterFactory(escalation_curve=self.curve)
        self.protector = CombatParticipantFactory(
            encounter=self.encounter, status=ParticipantStatus.ACTIVE
        )
        self.ally = CombatParticipantFactory(
            encounter=self.encounter, status=ParticipantStatus.ACTIVE
        )
        self.protector_char = self.protector.character_sheet.character
        self.ally_char = self.ally.character_sheet.character
        self.protector_char.location = self.encounter.room
        self.ally_char.location = self.encounter.room
        begin_engagement(self.protector_char, EngagementType.COMBAT, source=self.encounter)
        begin_engagement(self.ally_char, EngagementType.COMBAT, source=self.encounter)
        wire_escalation_content()
        install_escalation_room_triggers(self.encounter)
        self.technique = _make_technique()

    def _runtime_intensity(self, character) -> int:
        return get_runtime_technique_stats(self.technique, character).intensity

    def test_ally_fallen_provably_strengthens_next_cast(self):
        """Folds the grief spike's outcome-delta assertion into the new suite (#2013)."""
        _bond(self.protector.character_sheet, self.ally.character_sheet)
        before = self._runtime_intensity(self.protector_char)

        emit_event(
            EventName.CHARACTER_INCAPACITATED,
            CharacterIncapacitatedPayload(character=self.ally_char, source_event=None),
            location=self.encounter.room,
        )

        after = self._runtime_intensity(self.protector_char)
        self.assertEqual(after - before, self.curve.spike_intensity_amount)

    def test_ally_mortal_peril_provably_strengthens_next_cast_before_the_fall(self):
        _bond(self.protector.character_sheet, self.ally.character_sheet)
        before = self._runtime_intensity(self.protector_char)
        bleed_out = BleedingOutConditionFactory()
        ConditionStageFactory(
            condition=bleed_out, stage_order=1, name="Bleeding", rounds_to_next=None
        )

        apply_condition(target=self.ally_char, condition=bleed_out)

        after = self._runtime_intensity(self.protector_char)
        self.assertEqual(after - before, self.curve.peril_spike_intensity_amount)

    def test_hated_foe_entry_surges_once_and_dedupes_on_recheck(self):
        foe_sheet = CharacterSheetFactory()
        foe_persona = PersonaFactory(character_sheet=foe_sheet)
        _bond(
            self.protector.character_sheet,
            foe_sheet,
            sign=TrackSign.NEGATIVE,
            points=0,
        )
        before = self._runtime_intensity(self.protector_char)

        opponent = add_opponent(
            self.encounter,
            name=foe_sheet.character.key,
            tier="mook",
            threat_pool=None,
            max_health=10,
            persona=foe_persona,
        )

        after_first = self._runtime_intensity(self.protector_char)
        self.assertEqual(after_first - before, self.curve.hated_foe_spike_intensity_amount)

        from world.combat.escalation import check_hated_foe_surges_for_new_opponent

        check_hated_foe_surges_for_new_opponent(opponent)

        after_recheck = self._runtime_intensity(self.protector_char)
        self.assertEqual(after_recheck, after_first)

    def test_national_stakes_auto_curve_ticks_faster_than_local(self):
        StakesEscalationModifier.objects.create(
            stakes_level=StakesLevel.NATIONAL,
            intensity_step_bonus=2,
            initial_surge=3,
            default_curve=self.curve,
        )
        national_encounter = CombatEncounterFactory(
            escalation_curve=None, stakes_level=StakesLevel.NATIONAL, round_number=2
        )
        local_encounter = CombatEncounterFactory(
            escalation_curve=self.curve, stakes_level=StakesLevel.LOCAL, round_number=2
        )
        assign_default_escalation_curve(national_encounter)
        national_pc = CombatParticipantFactory(
            encounter=national_encounter, status=ParticipantStatus.ACTIVE
        )
        local_pc = CombatParticipantFactory(
            encounter=local_encounter, status=ParticipantStatus.ACTIVE
        )
        begin_engagement(
            national_pc.character_sheet.character, EngagementType.COMBAT, source=national_encounter
        )
        begin_engagement(
            local_pc.character_sheet.character, EngagementType.COMBAT, source=local_encounter
        )

        def _fake_check_fn(*_args, **_kwargs):
            from unittest.mock import MagicMock

            result = MagicMock()
            result.outcome = None
            return result

        apply_escalation_tick(national_encounter, check_fn=_fake_check_fn)
        apply_escalation_tick(local_encounter, check_fn=_fake_check_fn)

        national_intensity = self._runtime_intensity(national_pc.character_sheet.character)
        local_intensity = self._runtime_intensity(local_pc.character_sheet.character)
        # National: curve.intensity_step + step_bonus (2) + initial_surge (3).
        # Local: curve.intensity_step only.
        self.assertGreater(national_intensity, local_intensity)

        surge_beats_this_round = national_encounter.dramatic_surges.filter(
            round_number=national_encounter.round_number
        )
        self.assertTrue(surge_beats_this_round.exists())

"""Tests that SceneActionRequestSerializer (consent prompt) exposes strain_commitment."""

from django.test import TestCase
from django.utils import timezone

from world.combat.constants import EncounterType, RiskLevel
from world.combat.models import CombatEncounter
from world.scenes.action_constants import ActionRequestStatus
from world.scenes.action_serializers import (
    SceneActionRequestSerializer,
    SceneActionTargetSerializer,
)
from world.scenes.cast_services import request_technique_cast
from world.scenes.constants import RoundStatus
from world.scenes.factories import (
    PersonaFactory,
    SceneActionRequestFactory,
    SceneActionTargetFactory,
)
from world.scenes.models import Scene
from world.scenes.tests.cast_test_helpers import (
    CastScenarioMixin,
    attach_behavior_altering_condition,
    grant_technique,
    make_benign_castable_technique,
    make_hostile_castable_technique,
)


class SceneActionRequestSerializerStrainTests(TestCase):
    """The GET serializer for SceneActionRequest exposes strain_commitment."""

    def test_serializer_includes_strain_commitment(self) -> None:
        request = SceneActionRequestFactory(strain_commitment=3)
        data = SceneActionRequestSerializer(request).data
        self.assertEqual(data["strain_commitment"], 3)

    def test_serializer_strain_commitment_defaults_zero(self) -> None:
        request = SceneActionRequestFactory()
        data = SceneActionRequestSerializer(request).data
        self.assertEqual(data["strain_commitment"], 0)


class SceneActionRequestSerializerRiskLevelTests(CastScenarioMixin):
    """combat_risk_level surfaces the risk of the encounter a PENDING hostile cast gates on (#777).

    Only a PENDING hostile standalone cast whose target still owes a risk
    acknowledgement carries a level; benign and resolved requests serialize None.
    """

    scene: Scene

    def _make_encounter(self, risk_level: str) -> CombatEncounter:
        """A feedable (BETWEEN_ROUNDS) encounter in the test scene at *risk_level*."""
        return CombatEncounter.objects.create(
            room=self.scene.location,
            scene=self.scene,
            status=RoundStatus.BETWEEN_ROUNDS,
            risk_level=risk_level,
            encounter_type=EncounterType.PARTY_COMBAT,
        )

    def _cast(self, *, hostile: bool):
        """Caster fires a hostile or benign castable technique at the target persona."""
        technique = (
            make_hostile_castable_technique() if hostile else make_benign_castable_technique()
        )
        if not hostile:
            # Behavior-altering condition makes cast_requires_consent return True,
            # so the benign cast routes to PENDING (consent) rather than immediate resolution.
            attach_behavior_altering_condition(technique)
        grant_technique(self.caster, technique)
        return request_technique_cast(
            scene=self.scene,
            initiator_persona=self.caster,
            target_persona=self.target,
            technique=technique,
        )

    def test_pending_hostile_cast_serializes_encounter_risk_level(self) -> None:
        """LETHAL feedable encounter + gated hostile cast → combat_risk_level == 'lethal'."""
        self._make_encounter(RiskLevel.LETHAL)

        cast = self._cast(hostile=True)

        self.assertEqual(cast.request.status, ActionRequestStatus.PENDING)
        data = SceneActionRequestSerializer(instance=cast.request).data
        self.assertEqual(data["combat_risk_level"], RiskLevel.LETHAL.value)

    def test_pending_benign_cast_serializes_none(self) -> None:
        """A benign PENDING consent request carries no risk level, encounter or not."""
        self._make_encounter(RiskLevel.LETHAL)

        cast = self._cast(hostile=False)

        self.assertEqual(cast.request.status, ActionRequestStatus.PENDING)
        data = SceneActionRequestSerializer(instance=cast.request).data
        self.assertIsNone(data["combat_risk_level"])

    def test_pending_hostile_cast_with_no_gating_encounter_serializes_none(self) -> None:
        """State drift: the gating encounter completed after the request went PENDING."""
        encounter = self._make_encounter(RiskLevel.LETHAL)
        cast = self._cast(hostile=True)
        encounter.status = RoundStatus.COMPLETED
        encounter.save(update_fields=["status"])

        data = SceneActionRequestSerializer(instance=cast.request).data
        self.assertIsNone(data["combat_risk_level"])

    def test_resolved_request_serializes_none(self) -> None:
        """A RESOLVED request never advertises a risk level, even with the encounter live."""
        self._make_encounter(RiskLevel.LETHAL)
        cast = self._cast(hostile=True)
        cast.request.status = ActionRequestStatus.RESOLVED
        cast.request.resolved_at = timezone.now()
        cast.request.save()

        data = SceneActionRequestSerializer(instance=cast.request).data
        self.assertIsNone(data["combat_risk_level"])


class SceneActionRequestSerializerCombatStakesTests(CastScenarioMixin):
    """combat_stakes surfaces the staked beats behind a gating hostile cast (#1770 pillar 9).

    Non-None only when the #777 gate is active AND the scene carries staked
    UNSATISFIED beats; the payload is the stakes-summary shape (what is
    wagered), never branch contents.
    """

    scene: Scene

    def _make_encounter(self, risk_level: str) -> CombatEncounter:
        return CombatEncounter.objects.create(
            room=self.scene.location,
            scene=self.scene,
            status=RoundStatus.BETWEEN_ROUNDS,
            risk_level=risk_level,
            encounter_type=EncounterType.PARTY_COMBAT,
        )

    def _hostile_cast(self):
        technique = make_hostile_castable_technique()
        grant_technique(self.caster, technique)
        return request_technique_cast(
            scene=self.scene,
            initiator_persona=self.caster,
            target_persona=self.target,
            technique=technique,
        )

    def _staked_beat_on_scene(self):
        from world.societies.constants import RenownRisk
        from world.stories.constants import StakeSeverity
        from world.stories.factories import (
            BeatFactory,
            EpisodeSceneFactory,
            StakeFactory,
        )

        beat = BeatFactory(risk=RenownRisk.HIGH, target_level=4)
        EpisodeSceneFactory(episode=beat.episode, scene=self.scene)
        StakeFactory(
            beat=beat,
            severity=StakeSeverity.DIRE,
            player_summary="The healer NPC may die.",
        )
        return beat

    def test_gated_hostile_cast_with_staked_beat_serializes_stakes(self) -> None:
        self._make_encounter(RiskLevel.LETHAL)
        beat = self._staked_beat_on_scene()

        cast = self._hostile_cast()

        data = SceneActionRequestSerializer(instance=cast.request).data
        self.assertIsNotNone(data["combat_stakes"])
        self.assertEqual(len(data["combat_stakes"]), 1)
        summary = data["combat_stakes"][0]
        self.assertEqual(summary["declared_risk"], beat.risk)
        self.assertEqual(summary["stakes"][0]["player_summary"], "The healer NPC may die.")

    def test_gated_hostile_cast_without_staked_beat_serializes_none(self) -> None:
        self._make_encounter(RiskLevel.LETHAL)

        cast = self._hostile_cast()

        data = SceneActionRequestSerializer(instance=cast.request).data
        self.assertIsNone(data["combat_stakes"])

    def test_no_gating_encounter_serializes_none_even_with_staked_beat(self) -> None:
        self._staked_beat_on_scene()

        cast = self._hostile_cast()

        data = SceneActionRequestSerializer(instance=cast.request).data
        self.assertIsNone(data["combat_stakes"])


class SceneActionTargetSerializerRiskLevelTests(CastScenarioMixin):
    """combat_risk_level surfaces per additional-target row, keyed on that row's persona (#1259).

    Mirrors the primary-request behaviour: only a PENDING additional target of a
    hostile standalone cast, whose own character still owes a risk acknowledgement,
    carries a level.
    """

    scene: Scene

    def _make_encounter(self, risk_level: str) -> CombatEncounter:
        return CombatEncounter.objects.create(
            room=self.scene.location,
            scene=self.scene,
            status=RoundStatus.BETWEEN_ROUNDS,
            risk_level=risk_level,
            encounter_type=EncounterType.PARTY_COMBAT,
        )

    def _hostile_cast(self):
        technique = make_hostile_castable_technique()
        grant_technique(self.caster, technique)
        return request_technique_cast(
            scene=self.scene,
            initiator_persona=self.caster,
            target_persona=self.target,
            technique=technique,
        )

    def test_pending_additional_target_serializes_encounter_risk_level(self) -> None:
        """LETHAL feedable encounter + additional target of a gated hostile cast → 'lethal'."""
        self._make_encounter(RiskLevel.LETHAL)
        cast = self._hostile_cast()
        extra = PersonaFactory()
        row = SceneActionTargetFactory(action_request=cast.request, target_persona=extra)

        data = SceneActionTargetSerializer(instance=row).data
        self.assertEqual(data["combat_risk_level"], RiskLevel.LETHAL.value)

    def test_pending_benign_additional_target_serializes_none(self) -> None:
        """A benign (non-hostile) cast's additional target carries no risk level."""
        self._make_encounter(RiskLevel.LETHAL)
        technique = make_benign_castable_technique()
        # Behavior-altering condition makes cast_requires_consent return True → PENDING.
        attach_behavior_altering_condition(technique)
        grant_technique(self.caster, technique)
        cast = request_technique_cast(
            scene=self.scene,
            initiator_persona=self.caster,
            target_persona=self.target,
            technique=technique,
        )
        row = SceneActionTargetFactory(action_request=cast.request, target_persona=PersonaFactory())

        data = SceneActionTargetSerializer(instance=row).data
        self.assertIsNone(data["combat_risk_level"])

    def test_resolved_additional_target_serializes_none(self) -> None:
        """A RESOLVED additional-target row never advertises a risk level."""
        self._make_encounter(RiskLevel.LETHAL)
        cast = self._hostile_cast()
        row = SceneActionTargetFactory(
            action_request=cast.request,
            target_persona=PersonaFactory(),
            status=ActionRequestStatus.RESOLVED,
        )

        data = SceneActionTargetSerializer(instance=row).data
        self.assertIsNone(data["combat_risk_level"])

    def test_additional_target_with_no_gating_encounter_serializes_none(self) -> None:
        """No feedable encounter in the scene → no risk level for the additional target."""
        cast = self._hostile_cast()
        row = SceneActionTargetFactory(action_request=cast.request, target_persona=PersonaFactory())

        data = SceneActionTargetSerializer(instance=row).data
        self.assertIsNone(data["combat_risk_level"])

    def test_gated_additional_target_serializes_combat_stakes(self) -> None:
        """The AOE-target leg surfaces the same stakes summary as the primary (#1770)."""
        from world.societies.constants import RenownRisk
        from world.stories.constants import StakeSeverity
        from world.stories.factories import BeatFactory, EpisodeSceneFactory, StakeFactory

        self._make_encounter(RiskLevel.LETHAL)
        beat = BeatFactory(risk=RenownRisk.HIGH, target_level=4)
        EpisodeSceneFactory(episode=beat.episode, scene=self.scene)
        StakeFactory(
            beat=beat,
            severity=StakeSeverity.DIRE,
            player_summary="The healer NPC may die.",
        )
        cast = self._hostile_cast()
        row = SceneActionTargetFactory(action_request=cast.request, target_persona=PersonaFactory())

        data = SceneActionTargetSerializer(instance=row).data
        self.assertIsNotNone(data["combat_stakes"])
        summary = data["combat_stakes"][0]
        self.assertEqual(summary["declared_risk"], beat.risk)
        self.assertEqual(summary["stakes"][0]["player_summary"], "The healer NPC may die.")

    def test_ungated_additional_target_serializes_no_stakes(self) -> None:
        from world.societies.constants import RenownRisk
        from world.stories.constants import StakeSeverity
        from world.stories.factories import BeatFactory, EpisodeSceneFactory, StakeFactory

        beat = BeatFactory(risk=RenownRisk.HIGH, target_level=4)
        EpisodeSceneFactory(episode=beat.episode, scene=self.scene)
        StakeFactory(beat=beat, severity=StakeSeverity.DIRE)
        cast = self._hostile_cast()
        row = SceneActionTargetFactory(action_request=cast.request, target_persona=PersonaFactory())

        data = SceneActionTargetSerializer(instance=row).data
        self.assertIsNone(data["combat_stakes"])

"""Tests that SceneActionRequestSerializer (consent prompt) exposes strain_commitment."""

from django.test import TestCase
from django.utils import timezone

from world.combat.constants import EncounterStatus, EncounterType, RiskLevel
from world.combat.models import CombatEncounter
from world.scenes.action_constants import ActionRequestStatus
from world.scenes.action_serializers import SceneActionRequestSerializer
from world.scenes.cast_services import request_technique_cast
from world.scenes.factories import SceneActionRequestFactory
from world.scenes.models import Scene
from world.scenes.tests.cast_test_helpers import (
    CastScenarioMixin,
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
            status=EncounterStatus.BETWEEN_ROUNDS,
            risk_level=risk_level,
            encounter_type=EncounterType.PARTY_COMBAT,
        )

    def _cast(self, *, hostile: bool):
        """Caster fires a hostile or benign castable technique at the target persona."""
        technique = (
            make_hostile_castable_technique() if hostile else make_benign_castable_technique()
        )
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
        encounter.status = EncounterStatus.COMPLETED
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

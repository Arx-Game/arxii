"""End-to-end integration tests for standalone technique cast (issue #772).

Exercises the full service-layer pipeline for all three routing branches:

  1. Self-cast (target_persona=None, benign technique) → immediate RESOLVED +
     Narrator OUTCOME pose in scene.
  2. Benign cast at another PC → PENDING; then:
       - ACCEPT → RESOLVED + OUTCOME pose (EnhancedSceneActionResult returned).
       - DENY  → DENIED + no OUTCOME pose (None returned).
  3. Hostile cast at another PC → CombatEncounter seeded in DECLARING status;
     caster is an active participant; a CombatRoundAction with the technique
     as focused_action exists.

These tests run on the SQLite fast tier:
    uv run arx test --sqlite --exclude-tag postgres world.scenes.tests.test_cast_integration

No Postgres-only paths are exercised here — seed_or_feed_encounter_from_cast
uses only standard FK lookups that SQLite handles fine. The apply_condition
(Soulfray) DISTINCT ON path is NOT triggered in these tests because the
technique factories used by the routing branches don't activate Soulfray
accruement; that path lives in the postgres-tagged test_targeted_action_e2e.py.

FactoryBoy chains below are written readably so they double as seed-data
documentation for a "new player who knows a benign castable technique and a
hostile one."
"""

from __future__ import annotations

from world.combat.constants import EncounterStatus, ParticipantStatus
from world.combat.models import CombatParticipant, CombatRoundAction
from world.magic.models import Technique
from world.scenes.action_constants import ActionRequestStatus, ConsentDecision
from world.scenes.action_models import SceneActionRequest
from world.scenes.action_services import respond_to_action_request
from world.scenes.cast_services import request_technique_cast
from world.scenes.constants import InteractionMode
from world.scenes.models import Interaction
from world.scenes.tests.cast_test_helpers import (
    CastScenarioMixin,
    grant_technique,
    make_benign_castable_technique,
    make_hostile_castable_technique,
)
from world.scenes.types import CastResult, EnhancedSceneActionResult

# ---------------------------------------------------------------------------
# Base class — delegates to CastScenarioMixin
# ---------------------------------------------------------------------------


class _BaseCastIntegrationTest(CastScenarioMixin):
    """Shared fixture: check system, room, scene, two personas with anima + vitals."""


# ---------------------------------------------------------------------------
# Branch 1 — self-cast: immediate RESOLVED + OUTCOME pose
# ---------------------------------------------------------------------------


class TestSelfCastImmediate(_BaseCastIntegrationTest):
    """Self-cast (target_persona=None) resolves immediately end-to-end."""

    def _do_self_cast(self) -> CastResult:
        technique = make_benign_castable_technique()
        grant_technique(self.caster, technique)
        return request_technique_cast(
            scene=self.scene,
            initiator_persona=self.caster,
            technique=technique,
        )

    def test_self_cast_request_status_resolved(self) -> None:
        """Self-cast request must be RESOLVED immediately."""
        cast = self._do_self_cast()
        self.assertEqual(cast.request.status, ActionRequestStatus.RESOLVED)

    def test_self_cast_no_encounter(self) -> None:
        """Self-cast must not seed a combat encounter."""
        cast = self._do_self_cast()
        self.assertIsNone(cast.encounter)

    def test_self_cast_result_populated(self) -> None:
        """Self-cast CastResult.result must be an EnhancedSceneActionResult."""
        cast = self._do_self_cast()
        self.assertIsNotNone(cast.result)
        self.assertIsInstance(cast.result, EnhancedSceneActionResult)

    def test_self_cast_outcome_pose_exists_in_scene(self) -> None:
        """Self-cast must create a Narrator OUTCOME Interaction in the scene."""
        cast = self._do_self_cast()

        pose = cast.outcome_interaction
        self.assertIsNotNone(pose)
        self.assertIsInstance(pose, Interaction)
        self.assertEqual(pose.mode, InteractionMode.OUTCOME)
        self.assertTrue(pose.persona.is_system)
        self.assertEqual(pose.scene, self.scene)

    def test_self_cast_result_interaction_linked_on_request(self) -> None:
        """The request's result_interaction FK must point at the OUTCOME pose."""
        cast = self._do_self_cast()
        req: SceneActionRequest = cast.request
        req.refresh_from_db()
        self.assertIsNotNone(req.result_interaction)
        self.assertEqual(req.result_interaction, cast.outcome_interaction)

    def test_self_cast_power_ledger_field_present(self) -> None:
        """CastResult.power_ledger attribute exists on the immediate path.

        May be None when no environment resonance is active (fast tier has no
        room resonance seeded). The assertion is that the field is accessible
        and that the result itself is non-None — the ledger's actual content is
        tested by the environment-clause tests in test_cast_services.py.
        """
        cast = self._do_self_cast()
        # Field must be present (no AttributeError); value is None or a PowerLedger.
        _ = cast.power_ledger
        self.assertIsNotNone(cast.result)


# ---------------------------------------------------------------------------
# Branch 2a — benign cast at another PC: PENDING then ACCEPT → RESOLVED
# ---------------------------------------------------------------------------


class TestBenignCastAccept(_BaseCastIntegrationTest):
    """Benign cast at another PC → PENDING; ACCEPT → RESOLVED + OUTCOME pose."""

    def _make_pending(self) -> tuple[Technique, CastResult]:
        technique = make_benign_castable_technique()
        grant_technique(self.caster, technique)
        cast = request_technique_cast(
            scene=self.scene,
            initiator_persona=self.caster,
            target_persona=self.target,
            technique=technique,
        )
        return technique, cast

    def test_benign_cast_at_other_pc_is_pending(self) -> None:
        """Benign cast at a distinct target must be PENDING."""
        _, cast = self._make_pending()
        self.assertEqual(cast.request.status, ActionRequestStatus.PENDING)

    def test_benign_cast_no_result_while_pending(self) -> None:
        """PENDING cast must carry no result or encounter yet."""
        _, cast = self._make_pending()
        self.assertIsNone(cast.result)
        self.assertIsNone(cast.encounter)

    def test_accept_returns_enhanced_result(self) -> None:
        """ACCEPT returns an EnhancedSceneActionResult (non-None)."""
        _, cast = self._make_pending()
        result = respond_to_action_request(
            action_request=cast.request,
            decision=ConsentDecision.ACCEPT,
        )
        self.assertIsNotNone(result)
        self.assertIsInstance(result, EnhancedSceneActionResult)

    def test_accept_sets_request_resolved(self) -> None:
        """ACCEPT must set the request to RESOLVED with resolved_at populated."""
        _, cast = self._make_pending()
        req = cast.request

        respond_to_action_request(
            action_request=req,
            decision=ConsentDecision.ACCEPT,
        )

        req.refresh_from_db()
        self.assertEqual(req.status, ActionRequestStatus.RESOLVED)
        self.assertIsNotNone(req.resolved_at)

    def test_accept_creates_outcome_pose(self) -> None:
        """ACCEPT must create a Narrator OUTCOME pose and link it on result_interaction."""
        _, cast = self._make_pending()
        req = cast.request

        respond_to_action_request(
            action_request=req,
            decision=ConsentDecision.ACCEPT,
        )

        req.refresh_from_db()
        self.assertIsNotNone(req.result_interaction)
        pose = req.result_interaction
        self.assertEqual(pose.mode, InteractionMode.OUTCOME)
        self.assertTrue(pose.persona.is_system)

        # The OUTCOME pose must also be discoverable through the scene.
        outcome_poses = Interaction.objects.filter(
            scene=self.scene,
            mode=InteractionMode.OUTCOME,
            persona__is_system=True,
        )
        self.assertTrue(outcome_poses.exists())


# ---------------------------------------------------------------------------
# Branch 2b — benign cast at another PC: DENY → DENIED + no OUTCOME pose
# ---------------------------------------------------------------------------


class TestBenignCastDeny(_BaseCastIntegrationTest):
    """Benign cast at another PC → PENDING; DENY → DENIED + no pose created."""

    def _make_pending(self) -> CastResult:
        technique = make_benign_castable_technique()
        grant_technique(self.caster, technique)
        return request_technique_cast(
            scene=self.scene,
            initiator_persona=self.caster,
            target_persona=self.target,
            technique=technique,
        )

    def test_deny_returns_none(self) -> None:
        """DENY must return None."""
        cast = self._make_pending()
        result = respond_to_action_request(
            action_request=cast.request,
            decision=ConsentDecision.DENY,
        )
        self.assertIsNone(result)

    def test_deny_sets_request_denied(self) -> None:
        """DENY must set the request to DENIED."""
        cast = self._make_pending()
        req = cast.request

        respond_to_action_request(
            action_request=req,
            decision=ConsentDecision.DENY,
        )

        req.refresh_from_db()
        self.assertEqual(req.status, ActionRequestStatus.DENIED)

    def test_deny_creates_no_outcome_pose(self) -> None:
        """DENY must not create any OUTCOME Interaction in the scene."""
        cast = self._make_pending()

        respond_to_action_request(
            action_request=cast.request,
            decision=ConsentDecision.DENY,
        )

        outcome_poses = Interaction.objects.filter(
            scene=self.scene,
            mode=InteractionMode.OUTCOME,
        )
        self.assertFalse(outcome_poses.exists())


# ---------------------------------------------------------------------------
# Branch 3 — hostile cast at another PC: combat encounter seeded
# ---------------------------------------------------------------------------


class TestHostileCastCombatSeed(_BaseCastIntegrationTest):
    """Hostile cast at another PC → CombatEncounter seeded in DECLARING status."""

    def _do_hostile_cast(self) -> CastResult:
        technique = make_hostile_castable_technique()
        grant_technique(self.caster, technique)
        return request_technique_cast(
            scene=self.scene,
            initiator_persona=self.caster,
            target_persona=self.target,
            technique=technique,
        )

    def test_hostile_cast_returns_encounter(self) -> None:
        """CastResult.encounter must be a non-None CombatEncounter."""
        cast = self._do_hostile_cast()
        self.assertIsNotNone(cast.encounter)

    def test_hostile_cast_encounter_status_declaring(self) -> None:
        """The seeded encounter must be in DECLARING status."""
        cast = self._do_hostile_cast()
        cast.encounter.refresh_from_db()
        self.assertEqual(cast.encounter.status, EncounterStatus.DECLARING)

    def test_hostile_cast_request_status_resolved(self) -> None:
        """The audit SceneActionRequest for a hostile cast must be RESOLVED."""
        cast = self._do_hostile_cast()
        self.assertEqual(cast.request.status, ActionRequestStatus.RESOLVED)

    def test_hostile_cast_caster_is_active_participant(self) -> None:
        """The caster must appear as an ACTIVE CombatParticipant in the encounter."""
        cast = self._do_hostile_cast()
        encounter = cast.encounter

        participant_exists = CombatParticipant.objects.filter(
            encounter=encounter,
            character_sheet=self.caster.character_sheet,
            status=ParticipantStatus.ACTIVE,
        ).exists()
        self.assertTrue(
            participant_exists,
            "Caster must be an active participant in the seeded encounter.",
        )

    def test_hostile_cast_round_action_has_technique(self) -> None:
        """The caster's CombatRoundAction for round 1 must reference the technique."""
        technique = make_hostile_castable_technique()
        grant_technique(self.caster, technique)
        cast = request_technique_cast(
            scene=self.scene,
            initiator_persona=self.caster,
            target_persona=self.target,
            technique=technique,
        )
        encounter = cast.encounter

        participant = CombatParticipant.objects.get(
            encounter=encounter,
            character_sheet=self.caster.character_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        round_action = CombatRoundAction.objects.filter(
            participant=participant,
            focused_action=technique,
        ).first()
        self.assertIsNotNone(
            round_action,
            "A CombatRoundAction with focused_action=technique must exist for the caster.",
        )

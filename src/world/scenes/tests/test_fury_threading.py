"""Tests for fury lever threading through serializer + scene/cast services (#567 Task 6).

Covers:
1. Serializer rejects declaring a fury tier above the provocation cap.
2. A resolved fury cast records Interaction.fury_committed = realized tier.
3. A below-floor control-retention outcome applies Berserk to the caster.
4. Serializer rejects declaring fury when the caster already has Berserk.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase
from evennia import create_object

from actions.constants import ResolutionPhase
from actions.factories import ActionTemplateFactory
from actions.types import PendingActionResolution, StepResult
from world.checks.test_helpers import force_check_outcome
from world.conditions.factories import ConditionInstanceFactory
from world.magic.factories import (
    BerserkConditionTemplateFactory,
    CharacterAnimaFactory,
    FuryConfigFactory,
    FuryTierFactory,
    TechniqueFactory,
)
from world.magic.types.techniques import AnimaCostResult, TechniqueUseResult
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipTierFactory,
    RelationshipTrackFactory,
    RelationshipTrackProgressFactory,
)
from world.scenes.action_constants import ActionRequestStatus, ConsentDecision
from world.scenes.action_services import respond_to_action_request
from world.scenes.factories import PersonaFactory, SceneActionRequestFactory, SceneFactory
from world.traits.factories import CheckOutcomeFactory, CheckSystemSetupFactory
from world.vitals.models import CharacterVitals

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_pending_resolution(success_level: int = 1) -> PendingActionResolution:
    check_result = MagicMock()
    check_result.success_level = success_level
    check_result.outcome_name = "Success" if success_level > 0 else "Failure"
    main_result = StepResult(
        step_label="main",
        check_result=check_result,
        consequence_id=None,
    )
    return PendingActionResolution(
        template_id=1,
        character_id=1,
        target_difficulty=45,
        resolution_context_data={"character_id": 1, "challenge_instance_id": None},
        current_phase=ResolutionPhase.COMPLETE,
        main_result=main_result,
    )


def _make_technique_use_result(resolution: PendingActionResolution) -> TechniqueUseResult:
    """Minimal TechniqueUseResult whose resolution_result is set."""
    anima_cost = AnimaCostResult(
        base_cost=2, effective_cost=2, control_delta=0, current_anima=10, deficit=0
    )
    return TechniqueUseResult(
        anima_cost=anima_cost,
        resolution_result=resolution,
        resonance_involvements=(),
    )


_ROOM_COUNTER = [0]


def _next_room_key() -> str:
    _ROOM_COUNTER[0] += 1
    return f"FuryTestRoom{_ROOM_COUNTER[0]}"


def _setup_fury_fixture(*, tier_depth: int = 2, bond_tier_number: int = 2):
    """Two personas, fury tier, config, and a bond giving cap >= tier_depth.

    Returns (scene, initiator_persona, anchor_persona, fury_tier, fury_config).

    provocation_cap = bond_tier_number // provocation_cap_per_tier (default per=1).
    We need bond_tier_number >= tier_depth to allow the commitment.
    """
    CheckSystemSetupFactory.create()
    room = create_object("typeclasses.rooms.Room", key=_next_room_key(), nohome=True)
    scene = SceneFactory(location=room)
    initiator = PersonaFactory()
    anchor = PersonaFactory()

    CharacterAnimaFactory(character=initiator.character_sheet.character, current=20, maximum=30)
    for persona in (initiator, anchor):
        CharacterVitals.objects.get_or_create(
            character_sheet=persona.character_sheet,
            defaults={"health": 50, "max_health": 50, "base_max_health": 50},
        )

    cfg = FuryConfigFactory()
    tier = FuryTierFactory(
        name=f"Tier_{tier_depth}_{bond_tier_number}",
        depth=tier_depth,
        control_penalty=4,
        intensity_bonus=5,
        base_check_difficulty=10,
        lucid_grade_floor=2,
        berserk_severity=3,
    )

    track = RelationshipTrackFactory(name=f"Bond_{tier_depth}_{bond_tier_number}")
    rel_tier = RelationshipTierFactory(
        track=track,
        tier_number=bond_tier_number,
        point_threshold=bond_tier_number * 10,
    )
    rel = CharacterRelationshipFactory(
        source=initiator.character_sheet,
        target=anchor.character_sheet,
    )
    RelationshipTrackProgressFactory(
        relationship=rel,
        track=track,
        capacity=rel_tier.point_threshold + 10,
        developed_points=rel_tier.point_threshold,
    )

    return scene, initiator, anchor, tier, cfg


# ---------------------------------------------------------------------------
# Test 1: Serializer rejects fury tier above the provocation cap
# ---------------------------------------------------------------------------


class SerializerFuryCapRejectionTests(TestCase):
    """Serializer rejects fury_commitment whose depth exceeds the provocation cap."""

    def test_fury_above_cap_rejected(self) -> None:
        from rest_framework.exceptions import ValidationError

        from world.scenes.action_serializers import (
            SceneActionRequestCreateSerializer,
        )

        # No relationship → provocation_cap = 0 → any tier is rejected
        initiator = PersonaFactory()
        anchor = PersonaFactory()
        tier = FuryTierFactory(name="HighTierNoBond", depth=3)

        ser = SceneActionRequestCreateSerializer(
            data={
                "scene": SceneFactory().pk,
                "initiator_persona": initiator.pk,
                "target_persona": anchor.pk,
                "action_key": "intimidate",
                "fury_commitment_id": tier.pk,
                "fury_anchor_id": anchor.character_sheet.pk,
            }
        )
        with self.assertRaises(ValidationError):
            ser.is_valid(raise_exception=True)

    def test_fury_within_cap_accepted(self) -> None:
        from world.scenes.action_serializers import (
            SceneActionRequestCreateSerializer,
        )

        _scene, initiator, anchor, tier, _cfg = _setup_fury_fixture(
            tier_depth=2, bond_tier_number=2
        )

        ser = SceneActionRequestCreateSerializer(
            data={
                "scene": _scene.pk,
                "initiator_persona": initiator.pk,
                "target_persona": anchor.pk,
                "action_key": "intimidate",
                "fury_commitment_id": tier.pk,
                "fury_anchor_id": anchor.character_sheet.pk,
            }
        )
        self.assertTrue(ser.is_valid(), msg=ser.errors)

    def test_fury_anchor_required_when_commitment_declared(self) -> None:
        from rest_framework.exceptions import ValidationError

        from world.scenes.action_serializers import (
            SceneActionRequestCreateSerializer,
        )

        initiator = PersonaFactory()
        anchor = PersonaFactory()
        tier = FuryTierFactory(name="NeedsAnchorTier", depth=1)

        ser = SceneActionRequestCreateSerializer(
            data={
                "scene": SceneFactory().pk,
                "initiator_persona": initiator.pk,
                "target_persona": anchor.pk,
                "action_key": "intimidate",
                "fury_commitment_id": tier.pk,
                # fury_anchor_id omitted
            }
        )
        with self.assertRaises(ValidationError):
            ser.is_valid(raise_exception=True)


# ---------------------------------------------------------------------------
# Test 4: Serializer rejects fury when caster already has Berserk
# ---------------------------------------------------------------------------


class SerializerBerserkBlockTests(TestCase):
    """Serializer rejects fury commitment when initiator already has Berserk.

    Uses ConditionInstanceFactory directly to bypass the PG-only apply_condition
    DISTINCT ON path — the serializer only needs has_condition, which works on SQLite.
    """

    def test_berserk_caster_fury_rejected(self) -> None:
        from rest_framework.exceptions import ValidationError

        from world.scenes.action_serializers import (
            SceneActionRequestCreateSerializer,
        )

        berserk_template = BerserkConditionTemplateFactory()
        _scene, initiator, anchor, tier, _cfg = _setup_fury_fixture(
            tier_depth=2, bond_tier_number=2
        )

        # Plant a Berserk ConditionInstance directly (avoids DISTINCT ON in apply_condition).
        ConditionInstanceFactory(
            target=initiator.character_sheet.character,
            condition=berserk_template,
            is_suppressed=False,
        )

        ser = SceneActionRequestCreateSerializer(
            data={
                "scene": _scene.pk,
                "initiator_persona": initiator.pk,
                "target_persona": anchor.pk,
                "action_key": "intimidate",
                "fury_commitment_id": tier.pk,
                "fury_anchor_id": anchor.character_sheet.pk,
            }
        )
        with self.assertRaises(ValidationError):
            ser.is_valid(raise_exception=True)


# ---------------------------------------------------------------------------
# Test 2: Resolved fury action records Interaction.fury_committed
# ---------------------------------------------------------------------------


class FuryCommittedAuditTests(TestCase):
    """Resolving a fury-committed action records fury_committed on the Interaction."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene, cls.initiator, cls.anchor, cls.tier, cls.cfg = _setup_fury_fixture()
        cls.action_template = ActionTemplateFactory()
        cls.technique = TechniqueFactory(
            action_template=cls.action_template,
            damage_profile=False,
        )

    def setUp(self) -> None:
        self.award_kudos_patcher = patch("world.scenes.action_services.award_kudos")
        self.award_kudos_patcher.start()

    def tearDown(self) -> None:
        self.award_kudos_patcher.stop()

    @patch("world.magic.services.use_technique")
    @patch("world.scenes.action_services.start_action_resolution")
    def test_fury_committed_recorded_on_interaction(
        self, mock_resolve: MagicMock, mock_use_technique: MagicMock
    ) -> None:
        pending = _make_pending_resolution(success_level=3)
        mock_resolve.return_value = pending
        mock_use_technique.return_value = _make_technique_use_result(pending)

        # Force the control-retention check to succeed (success_level=3 > lucid_grade_floor=2)
        lucid_outcome = CheckOutcomeFactory(name="FuryLucid_Audit", success_level=3)

        request = SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.anchor,
            action_key="intimidate",
            technique=self.technique,
            fury_commitment=self.tier,
            fury_anchor=self.anchor.character_sheet,
        )
        request.action_template = self.action_template
        request.save(update_fields=["action_template"])

        with force_check_outcome(lucid_outcome):
            respond_to_action_request(
                action_request=request,
                decision=ConsentDecision.ACCEPT,
            )

        request.refresh_from_db()
        self.assertEqual(request.status, ActionRequestStatus.RESOLVED)
        self.assertIsNotNone(request.result_interaction)
        self.assertIsNotNone(request.result_interaction.fury_committed)
        self.assertEqual(request.result_interaction.fury_committed, self.tier)


# ---------------------------------------------------------------------------
# Test 3: Below-floor check outcome triggers Berserk via apply_condition
# ---------------------------------------------------------------------------


class BerserkAppliedOnLostControlTests(TestCase):
    """A control-retention check with success_level < lucid_grade_floor applies Berserk.

    Mocks apply_condition to avoid the PG-only DISTINCT ON inside
    _build_bulk_context; asserts it was called with the expected severity.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene, cls.initiator, cls.anchor, cls.tier, cls.cfg = _setup_fury_fixture()
        cls.action_template = ActionTemplateFactory()
        cls.technique = TechniqueFactory(
            action_template=cls.action_template,
            damage_profile=False,
        )
        BerserkConditionTemplateFactory()

    def setUp(self) -> None:
        self.award_kudos_patcher = patch("world.scenes.action_services.award_kudos")
        self.award_kudos_patcher.start()

    def tearDown(self) -> None:
        self.award_kudos_patcher.stop()

    @patch("world.scenes.action_services.start_action_resolution")
    @patch("world.magic.services.use_technique")
    @patch("world.conditions.services.apply_condition")
    def test_berserk_called_on_failed_control_retention(
        self,
        mock_apply: MagicMock,
        mock_use_technique: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        # success_level=-1 < lucid_grade_floor=2 → berserk_severity=3 → apply_condition called
        pending = _make_pending_resolution(success_level=-1)
        mock_resolve.return_value = pending
        mock_use_technique.return_value = _make_technique_use_result(pending)
        failure_outcome = CheckOutcomeFactory(name="FuryFail_Berserk", success_level=-1)

        request = SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.anchor,
            action_key="intimidate",
            technique=self.technique,
            fury_commitment=self.tier,
            fury_anchor=self.anchor.character_sheet,
        )
        request.action_template = self.action_template
        request.save(update_fields=["action_template"])

        with force_check_outcome(failure_outcome):
            respond_to_action_request(
                action_request=request,
                decision=ConsentDecision.ACCEPT,
            )

        # apply_condition must have been called with the Berserk template
        self.assertTrue(mock_apply.called, "apply_condition was not called")
        call_kwargs = mock_apply.call_args
        self.assertEqual(call_kwargs.kwargs.get("severity"), self.tier.berserk_severity)
        from world.conditions.models import ConditionTemplate

        applied_template = (
            call_kwargs.args[1] if call_kwargs.args else call_kwargs.kwargs.get("condition")
        )
        self.assertEqual(applied_template, ConditionTemplate.get_by_name("Berserk"))

"""Tests for fury lever threading through serializer + scene/cast services (#567 Task 6).

Covers:
1. Serializer rejects declaring a fury tier above the provocation cap.
2. A resolved fury cast records Interaction.fury_committed = realized tier.
3. Choosing a Berserk tier applies Berserk even on a critical success (#4738).
4. Serializer accepts fury from a caster already Berserk, and refuses it from a
   caster with no engagement (#4738 rulings 1 and 3).
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
from world.fatigue.constants import EffortLevel
from world.magic.factories import (
    BerserkConditionTemplateFactory,
    CharacterAnimaFactory,
    FuryConfigFactory,
    FuryTierFactory,
    KindledStrengthTierFactory,
    ResonanceFactory,
    TechniqueFactory,
    kindle_resonance,
)
from world.magic.services.fury import NO_ENGAGEMENT_MESSAGE
from world.magic.types.techniques import AnimaCostResult, TechniqueUseResult
from world.mechanics.engagement import CharacterEngagement
from world.mechanics.factories import CharacterEngagementFactory
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
    check_result.outcome = None
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


def _cast_that_goes_off(result: TechniqueUseResult):
    """A stand-in for use_technique that drives its FuryCast as a cast that goes off does."""

    def cast(**kwargs):
        fury = kwargs.get("fury")
        if fury is not None and fury.surrender():
            fury.settle()
        return result

    return cast


_ROOM_COUNTER = [0]


def _next_room_key() -> str:
    _ROOM_COUNTER[0] += 1
    return f"FuryTestRoom{_ROOM_COUNTER[0]}"


def _setup_fury_fixture(*, tier_depth: int = 2):
    """Two personas, fury tier, config, and a strength row giving cap >= tier_depth.

    Returns (scene, initiator_persona, target_persona, fury_tier, fury_config, resonance).
    """
    CheckSystemSetupFactory.create()
    room = create_object("typeclasses.rooms.Room", key=_next_room_key(), nohome=True)
    scene = SceneFactory(room=room)
    initiator = PersonaFactory()
    anchor = PersonaFactory()

    CharacterAnimaFactory(character=initiator.character_sheet, current=20, maximum=30)
    for persona in (initiator, anchor):
        CharacterVitals.objects.get_or_create(
            character_sheet=persona.character_sheet,
            defaults={"health": 50, "max_health": 50, "base_max_health": 50},
        )

    cfg = FuryConfigFactory()
    tier = FuryTierFactory(
        name=f"Tier_{tier_depth}",
        depth=tier_depth,
        control_surrendered=4,
        base_check_difficulty_level=1,
        berserk_severity=3,
    )
    # Fury needs something at stake (#4738): the initiator is engaged.
    CharacterEngagementFactory(character=initiator.character_sheet)

    # The resonance she gives in to is kindled at a strength that reaches the tier.
    resonance = ResonanceFactory()
    kindle_resonance(
        initiator.character_sheet,
        resonance,
        KindledStrengthTierFactory(rank=3, give_in_max_depth=tier_depth),
    )

    return scene, initiator, anchor, tier, cfg, resonance


# ---------------------------------------------------------------------------
# Test 1: Serializer rejects fury tier above the provocation cap
# ---------------------------------------------------------------------------


class SerializerFuryCapRejectionTests(TestCase):
    """Serializer rejects fury_commitment whose depth exceeds the strength cap."""

    def test_fury_above_cap_rejected(self) -> None:
        from rest_framework.exceptions import ValidationError

        from world.scenes.action_serializers import (
            SceneActionRequestCreateSerializer,
        )

        # The resonance is not kindled → any tier is refused.
        # technique_id provided so validation reaches the cap check.
        initiator = PersonaFactory()
        CharacterEngagementFactory(character=initiator.character_sheet)
        anchor = PersonaFactory()
        resonance = ResonanceFactory()
        tier = FuryTierFactory(name="HighTierNoStrength", depth=3)
        technique = TechniqueFactory(damage_profile=False)

        ser = SceneActionRequestCreateSerializer(
            data={
                "scene": SceneFactory().pk,
                "initiator_persona": initiator.pk,
                "target_persona": anchor.pk,
                "action_key": "intimidate",
                "technique_id": technique.pk,
                "fury_commitment_id": tier.pk,
                "fury_resonance_id": resonance.pk,
            }
        )
        with self.assertRaises(ValidationError) as ctx:
            ser.is_valid(raise_exception=True)
        self.assertIn("not kindled", str(ctx.exception.detail["fury_commitment_id"]))

    def test_fury_within_cap_accepted(self) -> None:
        from world.scenes.action_serializers import (
            SceneActionRequestCreateSerializer,
        )

        _scene, initiator, anchor, tier, _cfg, resonance = _setup_fury_fixture(tier_depth=2)
        technique = TechniqueFactory(damage_profile=False)

        ser = SceneActionRequestCreateSerializer(
            data={
                "scene": _scene.pk,
                "initiator_persona": initiator.pk,
                "target_persona": anchor.pk,
                "action_key": "intimidate",
                "technique_id": technique.pk,
                "fury_commitment_id": tier.pk,
                "fury_resonance_id": resonance.pk,
            }
        )
        self.assertTrue(ser.is_valid(), msg=ser.errors)

    def test_fury_on_plain_action_rejected(self) -> None:
        """fury_commitment_id on a plain action (no technique_id) is rejected."""
        from rest_framework.exceptions import ValidationError

        from world.scenes.action_serializers import (
            SceneActionRequestCreateSerializer,
        )

        _scene, initiator, anchor, tier, _cfg, resonance = _setup_fury_fixture(tier_depth=2)

        ser = SceneActionRequestCreateSerializer(
            data={
                "scene": _scene.pk,
                "initiator_persona": initiator.pk,
                "target_persona": anchor.pk,
                "action_key": "intimidate",
                # No technique_id — plain action
                "fury_commitment_id": tier.pk,
                "fury_resonance_id": resonance.pk,
            }
        )
        with self.assertRaises(ValidationError) as ctx:
            ser.is_valid(raise_exception=True)
        self.assertIn("fury_commitment_id", ctx.exception.detail)

    def test_fury_resonance_required_when_commitment_declared(self) -> None:
        from rest_framework.exceptions import ValidationError

        from world.scenes.action_serializers import (
            SceneActionRequestCreateSerializer,
        )

        initiator = PersonaFactory()
        anchor = PersonaFactory()
        tier = FuryTierFactory(name="NeedsResonanceTier", depth=1)
        technique = TechniqueFactory(damage_profile=False)

        ser = SceneActionRequestCreateSerializer(
            data={
                "scene": SceneFactory().pk,
                "initiator_persona": initiator.pk,
                "target_persona": anchor.pk,
                "action_key": "intimidate",
                "technique_id": technique.pk,
                "fury_commitment_id": tier.pk,
                # fury_resonance_id omitted
            }
        )
        with self.assertRaises(ValidationError):
            ser.is_valid(raise_exception=True)


# ---------------------------------------------------------------------------
# Test 4: Berserk does not block Fury; no engagement does (#4738)
# ---------------------------------------------------------------------------


class SerializerBerserkAndEngagementTests(TestCase):
    """Fury may be declared again while Berserk; never with nothing at stake.

    Uses ConditionInstanceFactory directly to bypass the PG-only apply_condition
    DISTINCT ON path.
    """

    def _serializer(self, scene, initiator, anchor, tier, resonance):
        from world.scenes.action_serializers import (
            SceneActionRequestCreateSerializer,
        )

        return SceneActionRequestCreateSerializer(
            data={
                "scene": scene.pk,
                "initiator_persona": initiator.pk,
                "target_persona": anchor.pk,
                "action_key": "intimidate",
                "technique_id": TechniqueFactory(damage_profile=False).pk,
                "fury_commitment_id": tier.pk,
                "fury_resonance_id": resonance.pk,
            }
        )

    def test_berserk_caster_may_declare_fury_again(self) -> None:
        berserk_template = BerserkConditionTemplateFactory()
        scene, initiator, anchor, tier, _cfg, resonance = _setup_fury_fixture(tier_depth=2)
        ConditionInstanceFactory(
            target=initiator.character_sheet.character,
            condition=berserk_template,
            is_suppressed=False,
        )

        ser = self._serializer(scene, initiator, anchor, tier, resonance)
        self.assertTrue(ser.is_valid(), msg=ser.errors)

    def test_fury_with_no_engagement_is_refused(self) -> None:
        scene, initiator, anchor, tier, _cfg, resonance = _setup_fury_fixture(tier_depth=2)
        CharacterEngagement.objects.filter(character=initiator.character_sheet).delete()

        ser = self._serializer(scene, initiator, anchor, tier, resonance)
        self.assertFalse(ser.is_valid())
        self.assertEqual(ser.errors["fury_commitment_id"], [NO_ENGAGEMENT_MESSAGE])


# ---------------------------------------------------------------------------
# Test 2: Resolved fury action records Interaction.fury_committed
# ---------------------------------------------------------------------------


class FuryCommittedAuditTests(TestCase):
    """Resolving a fury-committed action records fury_committed on the Interaction."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene, cls.initiator, cls.anchor, cls.tier, cls.cfg, cls.resonance = (
            _setup_fury_fixture()
        )
        cls.action_template = ActionTemplateFactory()
        cls.technique = TechniqueFactory(
            action_template=cls.action_template,
            damage_profile=False,
        )

    def setUp(self) -> None:
        self.accrue_patcher = patch("world.scenes.action_services.accrue")
        self.accrue_patcher.start()

    def tearDown(self) -> None:
        self.accrue_patcher.stop()

    @patch("world.magic.services.use_technique")
    @patch("world.scenes.action_services.start_action_resolution")
    def test_fury_committed_recorded_on_interaction(
        self, mock_resolve: MagicMock, mock_use_technique: MagicMock
    ) -> None:
        pending = _make_pending_resolution(success_level=3)
        mock_resolve.return_value = pending
        mock_use_technique.side_effect = _cast_that_goes_off(_make_technique_use_result(pending))

        # Force the control roll to a success.
        lucid_outcome = CheckOutcomeFactory(name="FuryLucid_Audit", success_level=3)

        request = SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.anchor,
            action_key="intimidate",
            technique=self.technique,
            fury_commitment=self.tier,
            fury_resonance=self.resonance,
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
# Test 3: A Berserk tier applies Berserk whatever the roll (#4738)
# ---------------------------------------------------------------------------


class BerserkTierIsChosenTests(TestCase):
    """Choosing a tier with berserk_severity applies Berserk even on a critical success.

    Mocks apply_condition to avoid the PG-only DISTINCT ON inside
    _build_bulk_context; asserts it was called with the expected severity.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene, cls.initiator, cls.anchor, cls.tier, cls.cfg, cls.resonance = (
            _setup_fury_fixture()
        )
        cls.action_template = ActionTemplateFactory()
        cls.technique = TechniqueFactory(
            action_template=cls.action_template,
            damage_profile=False,
        )
        BerserkConditionTemplateFactory()

    def setUp(self) -> None:
        self.accrue_patcher = patch("world.scenes.action_services.accrue")
        self.accrue_patcher.start()

    def tearDown(self) -> None:
        self.accrue_patcher.stop()

    @patch("world.scenes.action_services.start_action_resolution")
    @patch("world.magic.services.use_technique")
    @patch("world.conditions.services.apply_condition")
    def test_berserk_applied_on_a_critical_success(
        self,
        mock_apply: MagicMock,
        mock_use_technique: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        pending = _make_pending_resolution(success_level=3)
        mock_resolve.return_value = pending
        mock_use_technique.side_effect = _cast_that_goes_off(_make_technique_use_result(pending))
        crit_outcome = CheckOutcomeFactory(name="FuryCrit_Berserk", success_level=3)

        request = SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.anchor,
            action_key="intimidate",
            technique=self.technique,
            fury_commitment=self.tier,
            fury_resonance=self.resonance,
        )
        request.action_template = self.action_template
        request.save(update_fields=["action_template"])

        with force_check_outcome(crit_outcome):
            respond_to_action_request(
                action_request=request,
                decision=ConsentDecision.ACCEPT,
            )

        # apply_condition must have been called with the Berserk template
        self.assertTrue(mock_apply.called, "apply_condition was not called")
        call_kwargs = mock_apply.call_args
        self.assertEqual(call_kwargs.kwargs.get("severity"), self.tier.berserk_severity)
        from world.magic.services.fury import get_berserk_template

        applied_template = (
            call_kwargs.args[1] if call_kwargs.args else call_kwargs.kwargs.get("condition")
        )
        self.assertEqual(applied_template, get_berserk_template())


# ---------------------------------------------------------------------------
# #1293: effort modifier threads into the technique-enhanced check roll
# ---------------------------------------------------------------------------


class EffortThreadsIntoTechniqueCheckTests(TestCase):
    """A technique-enhanced action threads effort_level into its check roll.

    #3066: effort now reaches ``start_action_resolution`` (and, underneath,
    ``perform_check``) via its own ``effort_level`` kwarg rather than being
    pre-folded into ``extra_modifiers`` — folding it in AND passing
    ``effort_level`` would double-count ``EFFORT_CHECK_MODIFIER``, since
    ``perform_check`` applies it internally whenever ``effort_level`` is set.
    The ``use_technique`` mock invokes the passed ``resolve_fn`` so the inner
    lambda's call is captured.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene, cls.initiator, cls.anchor, cls.tier, cls.cfg, cls.resonance = (
            _setup_fury_fixture()
        )
        cls.action_template = ActionTemplateFactory()
        cls.technique = TechniqueFactory(
            action_template=cls.action_template,
            damage_profile=False,
        )

    def setUp(self) -> None:
        self.accrue_patcher = patch("world.scenes.action_services.accrue")
        self.accrue_patcher.start()

    def tearDown(self) -> None:
        self.accrue_patcher.stop()

    def _resolve_kwargs_for_effort(self, effort_level: str) -> dict:
        pending = _make_pending_resolution(success_level=1)

        def fake_use_technique(*, resolve_fn, **_kwargs):
            resolve_fn(power=1, ledger=None)
            return _make_technique_use_result(pending)

        request = SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.anchor,
            action_key="intimidate",
            technique=self.technique,
            effort_level=effort_level,
        )
        request.action_template = self.action_template
        request.save(update_fields=["action_template"])

        with (
            patch("world.scenes.action_services.start_action_resolution") as mock_resolve,
            patch("world.magic.services.use_technique", side_effect=fake_use_technique),
        ):
            mock_resolve.return_value = pending
            respond_to_action_request(action_request=request, decision=ConsentDecision.ACCEPT)

        self.assertTrue(mock_resolve.called, "start_action_resolution was not invoked")
        return mock_resolve.call_args.kwargs

    def test_high_effort_threads_effort_level_not_extra_modifiers(self) -> None:
        kwargs = self._resolve_kwargs_for_effort(EffortLevel.HIGH)
        self.assertEqual(kwargs["effort_level"], EffortLevel.HIGH)
        # extra_modifiers no longer carries EFFORT_CHECK_MODIFIER (#3066) — a bare
        # fixture with no fatigue/condition modifiers nets 0 here.
        self.assertEqual(kwargs["extra_modifiers"], 0)

    def test_very_low_effort_threads_effort_level_not_extra_modifiers(self) -> None:
        kwargs = self._resolve_kwargs_for_effort(EffortLevel.VERY_LOW)
        self.assertEqual(kwargs["effort_level"], EffortLevel.VERY_LOW)
        self.assertEqual(kwargs["extra_modifiers"], 0)

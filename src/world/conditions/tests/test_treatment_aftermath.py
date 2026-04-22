"""Tests for perform_treatment service (Scope 6 §5.2, §9.1).

Tests the aftermath/primary treatment path.  PENDING_ALTERATION path
is intentionally not tested here — it belongs to Phase 7 once
reduce_pending_alteration_tier lands.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.conditions.constants import TreatmentTargetKind
from world.conditions.exceptions import (
    HelperEngagedForTreatment,
    NoSupportingBondThread,
    TreatmentAlreadyAttempted,
    TreatmentAnimaInsufficient,
    TreatmentParentMismatch,
    TreatmentResonanceInsufficient,
    TreatmentScenePrerequisiteFailed,
    TreatmentTargetMismatch,
)
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionTemplateFactory,
    TreatmentTemplateFactory,
)
from world.conditions.services import perform_treatment
from world.magic.constants import PendingAlterationStatus, TargetKind
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterResonanceFactory,
    PendingAlterationFactory,
    ResonanceFactory,
    ThreadFactory,
)
from world.mechanics.factories import CharacterEngagementFactory
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipTrackProgressFactory,
)
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.traits.factories import CheckOutcomeFactory


def _make_check_result(success_level: int):
    """Build a mock CheckResult with a real CheckOutcome row."""
    outcome = CheckOutcomeFactory(
        name=f"Outcome_sl_{success_level}_{id(object())}",
        success_level=success_level,
    )
    result = MagicMock()
    result.outcome = outcome
    result.success_level = success_level
    return result


def _make_treatment(  # noqa: PLR0913
    target_kind=TreatmentTargetKind.AFTERMATH,
    requires_bond=False,
    scene_required=True,
    once_per_scene_per_helper=True,
    resonance_cost=0,
    anima_cost=0,
    backlash_severity_on_failure=0,
    backlash_target_condition=None,
    reduction_on_crit=5,
    reduction_on_success=3,
    reduction_on_partial=1,
    reduction_on_failure=0,
    target_condition=None,
):
    """Build a TreatmentTemplate with sensible defaults for tests."""
    parent = target_condition or ConditionTemplateFactory()
    return TreatmentTemplateFactory(
        target_kind=target_kind,
        target_condition=parent,
        requires_bond=requires_bond,
        scene_required=scene_required,
        once_per_scene_per_helper=once_per_scene_per_helper,
        resonance_cost=resonance_cost,
        anima_cost=anima_cost,
        backlash_severity_on_failure=backlash_severity_on_failure,
        backlash_target_condition=backlash_target_condition,
        reduction_on_crit=reduction_on_crit,
        reduction_on_success=reduction_on_success,
        reduction_on_partial=reduction_on_partial,
        reduction_on_failure=reduction_on_failure,
        check_type=CheckTypeFactory(),
    )


def _setup_scene_with_participants(*character_sheets):
    """Create an active scene with SceneParticipation rows for each account.

    SceneParticipation links accounts, not characters directly.
    We create a participation row per sheet using a stub account mapping.
    """
    scene = SceneFactory(is_active=True)
    for _sheet in character_sheets:
        # A character's account is accessed through the roster, which may not
        # exist in unit tests.  We create a participation row using a fresh
        # AccountDB directly to satisfy the scene gate.
        from evennia_extensions.factories import AccountFactory

        account = AccountFactory()
        # Store the account on the character object so the gate helper can find it
        # by conventional roster lookup — but since we bypass the roster here,
        # we need to store it at the ObjectDB level via item_data.
        # However, the scene gate helper (_scene_participant) checks
        # scene.participations.filter(account__characters=character) which
        # requires account→character FK setup that is roster-driven.
        # We use a simpler approach: patch is handled inside tests.
        SceneParticipationFactory(scene=scene, account=account)
    return scene


# =============================================================================
# Gate 1 — Type mismatch
# =============================================================================


class TreatmentTypeMismatchTests(TestCase):
    """Gate 1: TreatmentTargetKind vs instance type must match."""

    def setUp(self):
        self.helper_sheet = CharacterSheetFactory()
        self.target_sheet = CharacterSheetFactory()
        self.scene = SceneFactory(is_active=True)

    def test_pending_alteration_treatment_passed_condition_instance_raises(self):
        """PENDING_ALTERATION treatment + ConditionInstance target → TreatmentTargetMismatch."""
        treatment = _make_treatment(target_kind=TreatmentTargetKind.PENDING_ALTERATION)
        target_effect = ConditionInstanceFactory()
        with self.assertRaises(TreatmentTargetMismatch):
            perform_treatment(
                helper_sheet=self.helper_sheet,
                target_sheet=self.target_sheet,
                scene=self.scene,
                treatment=treatment,
                target_effect=target_effect,
            )

    def test_aftermath_treatment_passed_pending_alteration_raises(self):
        """AFTERMATH treatment + PendingAlteration target → TreatmentTargetMismatch."""
        treatment = _make_treatment(target_kind=TreatmentTargetKind.AFTERMATH)
        target_effect = PendingAlterationFactory(
            status=PendingAlterationStatus.OPEN,
        )
        with self.assertRaises(TreatmentTargetMismatch):
            perform_treatment(
                helper_sheet=self.helper_sheet,
                target_sheet=self.target_sheet,
                scene=self.scene,
                treatment=treatment,
                target_effect=target_effect,
            )

    def test_primary_treatment_passed_pending_alteration_raises(self):
        """PRIMARY treatment + PendingAlteration target → TreatmentTargetMismatch."""
        treatment = _make_treatment(target_kind=TreatmentTargetKind.PRIMARY)
        target_effect = PendingAlterationFactory(
            status=PendingAlterationStatus.OPEN,
        )
        with self.assertRaises(TreatmentTargetMismatch):
            perform_treatment(
                helper_sheet=self.helper_sheet,
                target_sheet=self.target_sheet,
                scene=self.scene,
                treatment=treatment,
                target_effect=target_effect,
            )


# =============================================================================
# Gate 2 — Parent/primary mismatch
# =============================================================================


class TreatmentParentMismatchTests(TestCase):
    """Gate 2: condition ancestry must match treatment.target_condition."""

    def setUp(self):
        self.helper_sheet = CharacterSheetFactory()
        self.target_sheet = CharacterSheetFactory()
        self.scene = SceneFactory(is_active=True)

    def test_aftermath_unrelated_parent_raises(self):
        """AFTERMATH treatment: parent_condition must equal treatment.target_condition."""
        soulfray = ConditionTemplateFactory(name="Soulfray_PM")
        unrelated = ConditionTemplateFactory(name="Unrelated_PM")
        # aftermath condition whose parent is 'unrelated', not soulfray
        aftermath_cond = ConditionTemplateFactory(
            name="SoulAche_PM",
            parent_condition=unrelated,
        )
        treatment = _make_treatment(
            target_kind=TreatmentTargetKind.AFTERMATH,
            target_condition=soulfray,
        )
        target_effect = ConditionInstanceFactory(condition=aftermath_cond)
        with self.assertRaises(TreatmentParentMismatch):
            perform_treatment(
                helper_sheet=self.helper_sheet,
                target_sheet=self.target_sheet,
                scene=self.scene,
                treatment=treatment,
                target_effect=target_effect,
            )

    def test_primary_wrong_condition_raises(self):
        """PRIMARY treatment: target_effect.condition must == treatment.target_condition."""
        soulfray = ConditionTemplateFactory(name="Soulfray_PM2")
        other = ConditionTemplateFactory(name="Other_PM")
        treatment = _make_treatment(
            target_kind=TreatmentTargetKind.PRIMARY,
            target_condition=soulfray,
        )
        target_effect = ConditionInstanceFactory(condition=other)
        with self.assertRaises(TreatmentParentMismatch):
            perform_treatment(
                helper_sheet=self.helper_sheet,
                target_sheet=self.target_sheet,
                scene=self.scene,
                treatment=treatment,
                target_effect=target_effect,
            )


# =============================================================================
# Gate 3 — Bond thread
# =============================================================================


class TreatmentBondGateTests(TestCase):
    """Gate 3: bond thread must be set and anchored to target when requires_bond=True."""

    def setUp(self):
        self.helper_sheet = CharacterSheetFactory()
        self.target_sheet = CharacterSheetFactory()
        self.scene = SceneFactory(is_active=True)
        self.soulfray = ConditionTemplateFactory(name="Soulfray_BG")
        self.aftermath_cond = ConditionTemplateFactory(
            name="SoulAche_BG",
            parent_condition=self.soulfray,
        )
        self.treatment = _make_treatment(
            target_kind=TreatmentTargetKind.AFTERMATH,
            target_condition=self.soulfray,
            requires_bond=True,
            scene_required=False,
        )
        self.target_effect = ConditionInstanceFactory(condition=self.aftermath_cond)

    def test_no_bond_thread_raises(self):
        """bond_thread=None when requires_bond=True → NoSupportingBondThread."""
        with self.assertRaises(NoSupportingBondThread):
            perform_treatment(
                helper_sheet=self.helper_sheet,
                target_sheet=self.target_sheet,
                scene=self.scene,
                treatment=self.treatment,
                target_effect=self.target_effect,
                bond_thread=None,
            )

    def test_bond_thread_owned_by_wrong_character_raises(self):
        """Thread owned by a third party → NoSupportingBondThread."""
        other_sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        # Build a relationship that looks like helper→target
        relationship = CharacterRelationshipFactory(
            source=self.helper_sheet, target=self.target_sheet
        )
        progress = RelationshipTrackProgressFactory(relationship=relationship)
        thread = ThreadFactory(
            owner=other_sheet,  # wrong owner
            resonance=resonance,
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            target_trait=None,
            target_relationship_track=progress,
        )
        with self.assertRaises(NoSupportingBondThread):
            perform_treatment(
                helper_sheet=self.helper_sheet,
                target_sheet=self.target_sheet,
                scene=self.scene,
                treatment=self.treatment,
                target_effect=self.target_effect,
                bond_thread=thread,
            )

    def test_bond_thread_not_anchoring_target_raises(self):
        """Thread owned by helper but anchor points to a third party → NoSupportingBondThread."""
        stranger = CharacterSheetFactory()
        resonance = ResonanceFactory()
        # relationship helper→stranger, not helper→target
        relationship = CharacterRelationshipFactory(source=self.helper_sheet, target=stranger)
        progress = RelationshipTrackProgressFactory(relationship=relationship)
        thread = ThreadFactory(
            owner=self.helper_sheet,
            resonance=resonance,
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            target_trait=None,
            target_relationship_track=progress,
        )
        with self.assertRaises(NoSupportingBondThread):
            perform_treatment(
                helper_sheet=self.helper_sheet,
                target_sheet=self.target_sheet,
                scene=self.scene,
                treatment=self.treatment,
                target_effect=self.target_effect,
                bond_thread=thread,
            )


# =============================================================================
# Gate 4 — Scene gate
# =============================================================================


class TreatmentSceneGateTests(TestCase):
    """Gate 4: scene must be active and both characters must be participants."""

    def setUp(self):
        self.helper_sheet = CharacterSheetFactory()
        self.target_sheet = CharacterSheetFactory()
        self.soulfray = ConditionTemplateFactory(name="Soulfray_SG")
        self.aftermath_cond = ConditionTemplateFactory(
            name="SoulAche_SG",
            parent_condition=self.soulfray,
        )
        self.treatment = _make_treatment(
            target_kind=TreatmentTargetKind.AFTERMATH,
            target_condition=self.soulfray,
            scene_required=True,
        )
        self.target_effect = ConditionInstanceFactory(condition=self.aftermath_cond)

    def test_inactive_scene_raises(self):
        """Scene with is_active=False → TreatmentScenePrerequisiteFailed."""
        inactive_scene = SceneFactory(is_active=False)
        with self.assertRaises(TreatmentScenePrerequisiteFailed):
            perform_treatment(
                helper_sheet=self.helper_sheet,
                target_sheet=self.target_sheet,
                scene=inactive_scene,
                treatment=self.treatment,
                target_effect=self.target_effect,
            )

    def test_helper_not_participant_raises(self):
        """Helper not in scene → TreatmentScenePrerequisiteFailed."""
        scene = SceneFactory(is_active=True)
        # Only add target account, not helper
        from evennia_extensions.factories import AccountFactory

        target_account = AccountFactory()
        SceneParticipationFactory(scene=scene, account=target_account)
        # _scene_participant checks helper account — no participation row → False
        with patch(
            "world.conditions.services._scene_participant",
            side_effect=lambda _s, c: c == self.target_sheet.character,
        ):
            with self.assertRaises(TreatmentScenePrerequisiteFailed):
                perform_treatment(
                    helper_sheet=self.helper_sheet,
                    target_sheet=self.target_sheet,
                    scene=scene,
                    treatment=self.treatment,
                    target_effect=self.target_effect,
                )


# =============================================================================
# Gate 5 — Engagement gate
# =============================================================================


class TreatmentEngagementGateTests(TestCase):
    """Gate 5: neither helper nor target may be engaged."""

    def setUp(self):
        self.helper_sheet = CharacterSheetFactory()
        self.target_sheet = CharacterSheetFactory()
        self.scene = SceneFactory(is_active=True)
        self.soulfray = ConditionTemplateFactory(name="Soulfray_EG")
        self.aftermath_cond = ConditionTemplateFactory(
            name="SoulAche_EG",
            parent_condition=self.soulfray,
        )
        self.treatment = _make_treatment(
            target_kind=TreatmentTargetKind.AFTERMATH,
            target_condition=self.soulfray,
            scene_required=False,
        )
        self.target_effect = ConditionInstanceFactory(condition=self.aftermath_cond)

    def test_helper_engaged_raises(self):
        """Helper in CharacterEngagement → HelperEngagedForTreatment."""
        CharacterEngagementFactory(character=self.helper_sheet.character)
        with self.assertRaises(HelperEngagedForTreatment):
            perform_treatment(
                helper_sheet=self.helper_sheet,
                target_sheet=self.target_sheet,
                scene=self.scene,
                treatment=self.treatment,
                target_effect=self.target_effect,
            )

    def test_target_engaged_raises(self):
        """Target in CharacterEngagement → HelperEngagedForTreatment."""
        CharacterEngagementFactory(character=self.target_sheet.character)
        with self.assertRaises(HelperEngagedForTreatment):
            perform_treatment(
                helper_sheet=self.helper_sheet,
                target_sheet=self.target_sheet,
                scene=self.scene,
                treatment=self.treatment,
                target_effect=self.target_effect,
            )


# =============================================================================
# Gate 6 — Duplicate gate
# =============================================================================


class TreatmentDuplicateGateTests(TestCase):
    """Gate 6: same (helper, target, scene, treatment) combo must not repeat."""

    @patch("world.checks.services.perform_check")
    def test_already_treated_this_scene_raises(self, mock_perform_check):
        """Second call with same combo → TreatmentAlreadyAttempted."""
        mock_perform_check.return_value = _make_check_result(success_level=1)

        helper_sheet = CharacterSheetFactory()
        target_sheet = CharacterSheetFactory()
        scene = SceneFactory(is_active=True)
        soulfray = ConditionTemplateFactory(name="Soulfray_DG")
        aftermath_cond = ConditionTemplateFactory(
            name="SoulAche_DG",
            parent_condition=soulfray,
        )
        treatment = _make_treatment(
            target_kind=TreatmentTargetKind.AFTERMATH,
            target_condition=soulfray,
            scene_required=False,
            once_per_scene_per_helper=True,
            reduction_on_success=1,
        )

        # Build distinct condition instances — second call needs a separate one
        # (first call decays/resolves the first instance's severity)
        effect1 = ConditionInstanceFactory(condition=aftermath_cond, severity=10)
        effect2 = ConditionInstanceFactory(condition=aftermath_cond, severity=10)

        # First call succeeds
        perform_treatment(
            helper_sheet=helper_sheet,
            target_sheet=target_sheet,
            scene=scene,
            treatment=treatment,
            target_effect=effect1,
        )

        # Second call on same (helper, target, scene, treatment) should raise
        with self.assertRaises(TreatmentAlreadyAttempted):
            perform_treatment(
                helper_sheet=helper_sheet,
                target_sheet=target_sheet,
                scene=scene,
                treatment=treatment,
                target_effect=effect2,
            )


# =============================================================================
# Gate 7 — Resonance gate
# =============================================================================


class TreatmentResonanceGateTests(TestCase):
    """Gate 7: helper must have sufficient resonance balance."""

    def setUp(self):
        self.helper_sheet = CharacterSheetFactory()
        self.target_sheet = CharacterSheetFactory()
        self.scene = SceneFactory(is_active=True)
        self.soulfray = ConditionTemplateFactory(name="Soulfray_RG")
        self.aftermath_cond = ConditionTemplateFactory(
            name="SoulAche_RG",
            parent_condition=self.soulfray,
        )
        self.resonance = ResonanceFactory()
        # Build a relationship: helper → target
        relationship = CharacterRelationshipFactory(
            source=self.helper_sheet, target=self.target_sheet
        )
        progress = RelationshipTrackProgressFactory(relationship=relationship)
        self.thread = ThreadFactory(
            owner=self.helper_sheet,
            resonance=self.resonance,
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            target_trait=None,
            target_relationship_track=progress,
        )

    def _make_resonance_treatment(self, cost: int):
        return TreatmentTemplateFactory(
            target_kind=TreatmentTargetKind.AFTERMATH,
            target_condition=self.soulfray,
            check_type=CheckTypeFactory(),
            requires_bond=True,
            scene_required=False,
            once_per_scene_per_helper=False,
            resonance_cost=cost,
            anima_cost=0,
            reduction_on_crit=5,
            reduction_on_success=3,
            reduction_on_partial=1,
            reduction_on_failure=0,
        )

    def test_insufficient_resonance_raises(self):
        """CharacterResonance.balance < resonance_cost → TreatmentResonanceInsufficient."""
        treatment = self._make_resonance_treatment(cost=10)
        CharacterResonanceFactory(
            character_sheet=self.helper_sheet,
            resonance=self.resonance,
            balance=5,  # not enough
            lifetime_earned=5,
        )
        target_effect = ConditionInstanceFactory(condition=self.aftermath_cond, severity=10)
        with self.assertRaises(TreatmentResonanceInsufficient):
            perform_treatment(
                helper_sheet=self.helper_sheet,
                target_sheet=self.target_sheet,
                scene=self.scene,
                treatment=treatment,
                target_effect=target_effect,
                bond_thread=self.thread,
            )

    @patch("world.checks.services.perform_check")
    def test_resonance_debited_from_matching_row(self, mock_perform_check):
        """Successful call debits resonance from the helper's CharacterResonance row."""
        mock_perform_check.return_value = _make_check_result(success_level=1)

        treatment = self._make_resonance_treatment(cost=3)
        res_row = CharacterResonanceFactory(
            character_sheet=self.helper_sheet,
            resonance=self.resonance,
            balance=10,
            lifetime_earned=10,
        )
        target_effect = ConditionInstanceFactory(condition=self.aftermath_cond, severity=10)
        perform_treatment(
            helper_sheet=self.helper_sheet,
            target_sheet=self.target_sheet,
            scene=self.scene,
            treatment=treatment,
            target_effect=target_effect,
            bond_thread=self.thread,
        )
        res_row.refresh_from_db()
        self.assertEqual(res_row.balance, 7)  # 10 - 3


# =============================================================================
# Gate 8 — Anima gate
# =============================================================================


class TreatmentAnimaGateTests(TestCase):
    """Gate 8: helper must have sufficient anima."""

    def setUp(self):
        self.helper_sheet = CharacterSheetFactory()
        self.target_sheet = CharacterSheetFactory()
        self.scene = SceneFactory(is_active=True)
        self.soulfray = ConditionTemplateFactory(name="Soulfray_AG")
        self.aftermath_cond = ConditionTemplateFactory(
            name="SoulAche_AG",
            parent_condition=self.soulfray,
        )
        self.treatment = TreatmentTemplateFactory(
            target_kind=TreatmentTargetKind.AFTERMATH,
            target_condition=self.soulfray,
            check_type=CheckTypeFactory(),
            requires_bond=False,
            scene_required=False,
            once_per_scene_per_helper=False,
            anima_cost=5,
            reduction_on_crit=5,
            reduction_on_success=3,
            reduction_on_partial=1,
            reduction_on_failure=0,
        )

    def test_insufficient_anima_raises(self):
        """CharacterAnima.current < anima_cost → TreatmentAnimaInsufficient."""
        # Create anima row with only 2 current (cost is 5)
        CharacterAnimaFactory(character=self.helper_sheet.character, current=2, maximum=10)
        target_effect = ConditionInstanceFactory(condition=self.aftermath_cond, severity=10)
        with self.assertRaises(TreatmentAnimaInsufficient):
            perform_treatment(
                helper_sheet=self.helper_sheet,
                target_sheet=self.target_sheet,
                scene=self.scene,
                treatment=self.treatment,
                target_effect=target_effect,
            )


# =============================================================================
# Execute path — success/partial/failure outcomes
# =============================================================================


class TreatmentSuccessPathTests(TestCase):
    """Happy-path tests for aftermath severity reduction."""

    def _setup(self, **extra_treatment_kwargs):
        helper_sheet = CharacterSheetFactory()
        target_sheet = CharacterSheetFactory()
        scene = SceneFactory(is_active=True)
        soulfray = ConditionTemplateFactory(name=f"Soulfray_{id(object())}")
        aftermath_cond = ConditionTemplateFactory(
            name=f"SoulAche_{id(object())}",
            parent_condition=soulfray,
        )
        treatment = TreatmentTemplateFactory(
            target_kind=TreatmentTargetKind.AFTERMATH,
            target_condition=soulfray,
            check_type=CheckTypeFactory(),
            requires_bond=False,
            scene_required=False,
            once_per_scene_per_helper=False,
            reduction_on_crit=5,
            reduction_on_success=3,
            reduction_on_partial=1,
            reduction_on_failure=0,
            backlash_severity_on_failure=0,
            **extra_treatment_kwargs,
        )
        target_effect = ConditionInstanceFactory(condition=aftermath_cond, severity=10)
        return helper_sheet, target_sheet, scene, treatment, target_effect

    @patch("world.checks.services.perform_check")
    def test_success_reduces_aftermath_by_reduction_on_success(self, mock_check):
        mock_check.return_value = _make_check_result(success_level=1)
        helper_sheet, target_sheet, scene, treatment, target_effect = self._setup()

        result = perform_treatment(
            helper_sheet=helper_sheet,
            target_sheet=target_sheet,
            scene=scene,
            treatment=treatment,
            target_effect=target_effect,
        )

        self.assertEqual(result.severity_reduced, 3)
        self.assertTrue(result.effect_applied)
        target_effect.refresh_from_db()
        self.assertEqual(target_effect.severity, 7)

    @patch("world.checks.services.perform_check")
    def test_partial_reduces_aftermath_by_reduction_on_partial(self, mock_check):
        mock_check.return_value = _make_check_result(success_level=0)
        helper_sheet, target_sheet, scene, treatment, target_effect = self._setup()

        result = perform_treatment(
            helper_sheet=helper_sheet,
            target_sheet=target_sheet,
            scene=scene,
            treatment=treatment,
            target_effect=target_effect,
        )

        self.assertEqual(result.severity_reduced, 1)
        self.assertTrue(result.effect_applied)

    @patch("world.checks.services.perform_check")
    def test_crit_reduces_aftermath_by_reduction_on_crit_and_may_resolve(self, mock_check):
        mock_check.return_value = _make_check_result(success_level=2)
        helper_sheet, target_sheet, scene, treatment, target_effect = self._setup()
        # Set severity == reduction_on_crit so crit resolves it
        target_effect.severity = 5
        target_effect.save()

        result = perform_treatment(
            helper_sheet=helper_sheet,
            target_sheet=target_sheet,
            scene=scene,
            treatment=treatment,
            target_effect=target_effect,
        )

        self.assertEqual(result.severity_reduced, 5)
        self.assertTrue(result.target_resolved)
        target_effect.refresh_from_db()
        self.assertEqual(target_effect.severity, 0)
        self.assertIsNotNone(target_effect.resolved_at)

    @patch("world.checks.services.perform_check")
    def test_failure_no_reduction_helper_gains_backlash_soulfray(self, mock_check):
        mock_check.return_value = _make_check_result(success_level=-1)
        soulfray = ConditionTemplateFactory(name=f"Soulfray_backlash_{id(object())}")
        aftermath_cond = ConditionTemplateFactory(
            name=f"SoulAche_backlash_{id(object())}",
            parent_condition=soulfray,
        )
        helper_sheet, target_sheet, scene = (
            CharacterSheetFactory(),
            CharacterSheetFactory(),
            SceneFactory(is_active=True),
        )
        treatment = TreatmentTemplateFactory(
            target_kind=TreatmentTargetKind.AFTERMATH,
            target_condition=soulfray,
            check_type=CheckTypeFactory(),
            requires_bond=False,
            scene_required=False,
            once_per_scene_per_helper=False,
            reduction_on_crit=5,
            reduction_on_success=3,
            reduction_on_partial=1,
            reduction_on_failure=0,
            backlash_severity_on_failure=2,
            backlash_target_condition=soulfray,
        )
        target_effect = ConditionInstanceFactory(condition=aftermath_cond, severity=10)

        result = perform_treatment(
            helper_sheet=helper_sheet,
            target_sheet=target_sheet,
            scene=scene,
            treatment=treatment,
            target_effect=target_effect,
        )

        self.assertEqual(result.severity_reduced, 0)
        self.assertFalse(result.effect_applied)
        self.assertEqual(result.helper_backlash_applied, 2)
        # Helper should now have a soulfray condition instance
        from world.conditions.models import ConditionInstance

        self.assertTrue(
            ConditionInstance.objects.filter(
                target=helper_sheet.character,
                condition=soulfray,
            ).exists()
        )


# =============================================================================
# Persist — TreatmentAttempt written with correct fields
# =============================================================================


class TreatmentPersistenceTests(TestCase):
    """The attempt row persists with accurate audit fields."""

    @patch("world.checks.services.perform_check")
    def test_treatment_attempt_persisted_with_accurate_fields(self, mock_check):
        outcome_row = CheckOutcomeFactory(name="SuccessForPersist", success_level=1)
        mock_result = MagicMock()
        mock_result.outcome = outcome_row
        mock_result.success_level = 1
        mock_check.return_value = mock_result

        helper_sheet = CharacterSheetFactory()
        target_sheet = CharacterSheetFactory()
        scene = SceneFactory(is_active=True)
        soulfray = ConditionTemplateFactory(name="Soulfray_persist")
        aftermath_cond = ConditionTemplateFactory(
            name="SoulAche_persist",
            parent_condition=soulfray,
        )
        treatment = TreatmentTemplateFactory(
            target_kind=TreatmentTargetKind.AFTERMATH,
            target_condition=soulfray,
            check_type=CheckTypeFactory(),
            requires_bond=False,
            scene_required=False,
            once_per_scene_per_helper=False,
            reduction_on_crit=5,
            reduction_on_success=3,
            reduction_on_partial=1,
            reduction_on_failure=0,
        )
        target_effect = ConditionInstanceFactory(condition=aftermath_cond, severity=10)

        result = perform_treatment(
            helper_sheet=helper_sheet,
            target_sheet=target_sheet,
            scene=scene,
            treatment=treatment,
            target_effect=target_effect,
        )

        from world.conditions.models import TreatmentAttempt

        attempt = TreatmentAttempt.objects.get(pk=result.attempt.pk)
        self.assertEqual(attempt.helper_id, helper_sheet.character.pk)
        self.assertEqual(attempt.target_id, target_sheet.character.pk)
        self.assertEqual(attempt.scene, scene)
        self.assertEqual(attempt.treatment, treatment)
        self.assertEqual(attempt.outcome, outcome_row)
        self.assertEqual(attempt.severity_reduced, 3)
        self.assertEqual(attempt.tiers_reduced, 0)
        self.assertEqual(attempt.helper_backlash_applied, 0)
        self.assertEqual(attempt.resonance_spent, 0)
        self.assertEqual(attempt.anima_spent, 0)
        self.assertEqual(attempt.target_condition_instance, target_effect)
        self.assertIsNone(attempt.target_pending_alteration)
        self.assertIsNotNone(attempt.created_at)

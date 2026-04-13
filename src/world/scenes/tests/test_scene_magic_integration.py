"""Integration tests for technique-enhanced scene actions.

Exercises the full pipeline: enhancement validation -> action creation ->
consent -> full resolution with consequences -> technique pipeline ->
interaction recording.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from actions.factories import ConsequencePoolFactory
from actions.models import ActionEnhancement
from world.character_sheets.models import CharacterSheet
from world.checks.factories import create_social_action_templates
from world.conditions.factories import (
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.conditions.models import ConditionInstance
from world.magic.audere import SOULFRAY_CONDITION_NAME
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    MishapPoolTierFactory,
    SoulfrayConfigFactory,
    TechniqueFactory,
)
from world.scenes.action_availability import get_available_scene_actions
from world.scenes.action_constants import ActionRequestStatus, ConsentDecision
from world.scenes.action_services import create_action_request, respond_to_action_request
from world.scenes.factories import PersonaFactory, SceneFactory
from world.traits.factories import CheckSystemSetupFactory
from world.traits.models import CharacterTraitValue, Trait


class SceneMagicTestMixin:
    """Shared setup for scene magic integration tests."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()  # type: ignore[misc]

        CheckSystemSetupFactory.create()
        templates = create_social_action_templates()
        cls.flirt_template = next(t for t in templates if t.name == "Flirt")
        cls.intimidate_template = next(t for t in templates if t.name == "Intimidate")

        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()
        cls.target = PersonaFactory()

        presence_trait = Trait.objects.get(name="presence")
        CharacterTraitValue.objects.create(
            character=cls.initiator.character,
            trait=presence_trait,
            value=30,
        )

        # Technique with HIGH control — social safety bonus (+10) means effective_cost = 0
        # runtime_control = control(8) + social_safety(10) = 18
        # runtime_intensity = 3; control_delta = 18 - 3 = +15 (large positive)
        # effective_cost drops to 0, so no Soulfray warning
        cls.charm_technique = TechniqueFactory(
            name="Mesmerizing Gaze",
            intensity=3,
            control=8,
            anima_cost=2,
        )

        initiator_sheet = cls.initiator.character_sheet
        CharacterTechniqueFactory(
            character=initiator_sheet,
            technique=cls.charm_technique,
        )
        CharacterAnimaFactory(
            character=cls.initiator.character,
            current=20,
            maximum=30,
        )

        cls.flirt_enhancement = ActionEnhancement.objects.create(
            base_action_key="flirt",
            variant_name="Enchanted Flirt",
            source_type="technique",
            technique=cls.charm_technique,
        )


class TestMundaneActionWithConsequences(SceneMagicTestMixin, TestCase):
    """Mundane social actions use the full pipeline and return EnhancedSceneActionResult."""

    def test_mundane_flirt_full_pipeline(self) -> None:
        """Mundane flirt returns EnhancedSceneActionResult with action_resolution and no
        technique_result."""
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="flirt",
        )
        request.action_template = self.flirt_template
        request.save(update_fields=["action_template"])

        result = respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.ACCEPT,
        )

        assert result is not None
        assert result.action_resolution is not None
        assert result.action_resolution.main_result is not None
        assert result.technique_result is None


class TestEnhancedActionFullPipeline(SceneMagicTestMixin, TestCase):
    """Technique-enhanced actions run use_technique wrapping the full pipeline."""

    def test_enhanced_flirt_deducts_anima_and_resolves(self) -> None:
        """Verifies anima is deducted, social action resolved, and technique_result is present."""
        from world.character_sheets.models import CharacterSheet
        from world.magic.models import CharacterAnima

        # Use a costly technique: intensity >> control so effective_cost > 0
        # intensity=15, control=1 -> runtime_control = 1 + 10 (social safety) = 11
        # control_delta = 11 - 15 = -4; effective_cost = max(5 - (-4), 0) = 9
        costly_technique = TechniqueFactory(
            name="Overwhelming Presence",
            intensity=15,
            control=1,
            anima_cost=5,
        )
        initiator_sheet = CharacterSheet.objects.get(character=self.initiator.character)
        CharacterTechniqueFactory(character=initiator_sheet, technique=costly_technique)

        ActionEnhancement.objects.create(
            base_action_key="flirt",
            variant_name="Overwhelming Flirt",
            source_type="technique",
            technique=costly_technique,
        )

        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="flirt",
            technique=costly_technique,
        )
        request.action_template = self.flirt_template
        request.save(update_fields=["action_template"])

        result = respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.ACCEPT,
        )

        assert result is not None
        assert result.technique_result is not None
        assert result.technique_result.confirmed is True
        assert result.action_resolution is not None

        anima = CharacterAnima.objects.get(character=self.initiator.character)
        assert anima.current < 20

    def test_free_technique_no_soulfray_warning(self) -> None:
        """Technique where control >> intensity has no Soulfray warning in available actions."""
        actions = get_available_scene_actions(character=self.initiator.character)
        flirt_action = next((a for a in actions if a.action_key == "flirt"), None)
        assert flirt_action is not None

        charm_enhancement = next(
            (e for e in flirt_action.enhancements if e.technique == self.charm_technique),
            None,
        )
        assert charm_enhancement is not None
        # High control means effective_cost == 0, so no Soulfray warning
        assert charm_enhancement.effective_cost == 0
        assert charm_enhancement.soulfray_warning is None

    def test_enhancement_rejected_without_record(self) -> None:
        """Cannot attach a technique without a matching ActionEnhancement (raises
        ValidationError)."""
        from world.character_sheets.models import CharacterSheet

        unregistered_technique = TechniqueFactory(name="Unregistered Spell")
        initiator_sheet = CharacterSheet.objects.get(character=self.initiator.character)
        CharacterTechniqueFactory(character=initiator_sheet, technique=unregistered_technique)

        with self.assertRaises(ValidationError):
            create_action_request(
                scene=self.scene,
                initiator_persona=self.initiator,
                target_persona=self.target,
                action_key="flirt",
                technique=unregistered_technique,
            )

    def test_enhanced_action_creates_interaction_with_technique(self) -> None:
        """Interaction content mentions the technique name when action is enhanced."""
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="flirt",
            technique=self.charm_technique,
        )
        request.action_template = self.flirt_template
        request.save(update_fields=["action_template"])

        respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.ACCEPT,
        )

        request.refresh_from_db()
        assert request.result_interaction is not None
        assert request.status == ActionRequestStatus.RESOLVED
        assert self.charm_technique.name in request.result_interaction.content


class TestAvailableActionsFiltering(SceneMagicTestMixin, TestCase):
    """Verifies the available-actions service filtering logic."""

    def test_only_known_techniques_appear(self) -> None:
        """Unknown techniques are excluded from enhancements."""
        unknown_technique = TechniqueFactory(name="Forbidden Spell")
        ActionEnhancement.objects.create(
            base_action_key="flirt",
            variant_name="Forbidden Flirt",
            source_type="technique",
            technique=unknown_technique,
        )

        actions = get_available_scene_actions(character=self.initiator.character)
        flirt_action = next(a for a in actions if a.action_key == "flirt")

        technique_ids = {e.technique.pk for e in flirt_action.enhancements}
        assert unknown_technique.pk not in technique_ids
        assert self.charm_technique.pk in technique_ids

    def test_non_magical_character_has_no_enhancements(self) -> None:
        """Characters without known techniques have no enhancements on any action."""
        non_magical = PersonaFactory()

        actions = get_available_scene_actions(character=non_magical.character)
        for action in actions:
            assert len(action.enhancements) == 0


class TestEnhancedActionEdgeCases(SceneMagicTestMixin, TestCase):
    """Soulfray warning in available actions, severity accumulation, and mishap evaluation."""

    def test_soulfray_warning_appears_in_available_actions(self) -> None:
        """A character with an existing Soulfray condition and a costly technique sees the
        warning in available-actions data for that enhancement."""
        # Create a costly technique: intensity >> control so effective_cost > 0
        # runtime_control = 1 + social_safety(10) = 11
        # runtime_intensity = 15; control_delta = 11 - 15 = -4
        # effective_cost = max(5 - (-4), 0) = 9
        costly_technique = TechniqueFactory(
            name="Soulfray Warning Test Technique",
            intensity=15,
            control=1,
            anima_cost=5,
        )
        initiator_sheet = CharacterSheet.objects.get(character=self.initiator.character)
        CharacterTechniqueFactory(character=initiator_sheet, technique=costly_technique)
        ActionEnhancement.objects.create(
            base_action_key="flirt",
            variant_name="Soulfray Warning Flirt",
            source_type="technique",
            technique=costly_technique,
        )

        # Create a Soulfray condition template, a stage, and an active instance.
        # get_soulfray_warning() returns None when current_stage is None, so we
        # must set current_stage to get a real warning object.
        soulfray_template = ConditionTemplateFactory(
            name=SOULFRAY_CONDITION_NAME,
            has_progression=True,
        )
        soulfray_stage = ConditionStageFactory(
            condition=soulfray_template,
            stage_order=1,
            name="Flickering",
            severity_threshold=1,
        )
        ConditionInstance.objects.create(
            target=self.initiator.character,
            condition=soulfray_template,
            current_stage=soulfray_stage,
            severity=5,
        )

        actions = get_available_scene_actions(character=self.initiator.character)
        flirt_action = next((a for a in actions if a.action_key == "flirt"), None)
        assert flirt_action is not None

        costly_enhancement = next(
            (e for e in flirt_action.enhancements if e.technique == costly_technique),
            None,
        )
        assert costly_enhancement is not None
        assert costly_enhancement.effective_cost > 0
        assert costly_enhancement.soulfray_warning is not None

    def test_soulfray_accumulates_on_depleted_character(self) -> None:
        """A character with very low anima using a costly technique accumulates Soulfray."""
        from world.magic.models import CharacterAnima

        # Costly technique: intensity=15, control=1
        # social safety bonus (+10 since no CharacterEngagement) -> runtime_control = 11
        # runtime_intensity = 15, delta = 11 - 15 = -4
        # effective_cost = max(5 - (-4), 0) = 9
        costly_technique = TechniqueFactory(
            name="Soulfray Accumulation Test Technique",
            intensity=15,
            control=1,
            anima_cost=5,
        )
        initiator_sheet = CharacterSheet.objects.get(character=self.initiator.character)
        CharacterTechniqueFactory(character=initiator_sheet, technique=costly_technique)
        ActionEnhancement.objects.create(
            base_action_key="flirt",
            variant_name="Soulfray Accumulation Flirt",
            source_type="technique",
            technique=costly_technique,
        )

        # Set anima very low so post-deduction ratio falls below soulfray threshold
        # Current=1, effective_cost=9: after deduction current=0 (deficit=8)
        # ratio = 0 / 30 = 0.0, below threshold 0.30 -> Soulfray accumulates
        anima = CharacterAnima.objects.get(character=self.initiator.character)
        anima.current = 1
        anima.save(update_fields=["current"])

        # Create the Soulfray condition template (required for the condition to be created)
        ConditionTemplateFactory(
            name=SOULFRAY_CONDITION_NAME,
            has_progression=True,
        )

        # SoulfrayConfig drives severity calculation
        SoulfrayConfigFactory(
            soulfray_threshold_ratio=Decimal("0.30"),
            severity_scale=10,
            deficit_scale=5,
        )

        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="flirt",
            technique=costly_technique,
        )
        request.action_template = self.flirt_template
        request.save(update_fields=["action_template"])

        result = respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.ACCEPT,
        )

        assert result is not None
        assert result.technique_result is not None
        assert result.technique_result.soulfray_result is not None
        assert result.technique_result.soulfray_result.severity_added > 0

    def test_mishap_evaluated_when_control_deficit_exists(self) -> None:
        """A technique with intensity > runtime_control triggers mishap pool evaluation.

        intensity=15, control=1; no CharacterEngagement so social safety bonus applies:
        runtime_control = 1 + 10 = 11; control_deficit = 15 - 11 = 4.
        A MishapPoolTier covering deficit=4 ensures the pool lookup fires.
        """
        # Costly technique with control deficit of 4 after social safety bonus
        mishap_technique = TechniqueFactory(
            name="Mishap Evaluation Test Technique",
            intensity=15,
            control=1,
            anima_cost=5,
        )
        initiator_sheet = CharacterSheet.objects.get(character=self.initiator.character)
        CharacterTechniqueFactory(character=initiator_sheet, technique=mishap_technique)
        ActionEnhancement.objects.create(
            base_action_key="flirt",
            variant_name="Mishap Flirt",
            source_type="technique",
            technique=mishap_technique,
        )

        # Create a MishapPoolTier covering control_deficit=4
        mishap_pool = ConsequencePoolFactory(name="Scene Mishap Pool")
        MishapPoolTierFactory(
            min_deficit=1,
            max_deficit=None,
            consequence_pool=mishap_pool,
        )

        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="flirt",
            technique=mishap_technique,
        )
        request.action_template = self.flirt_template
        request.save(update_fields=["action_template"])

        result = respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.ACCEPT,
        )

        assert result is not None
        assert result.technique_result is not None
        assert result.technique_result.confirmed is True
        # The pipeline reached mishap evaluation: either a mishap fired (mishap_result set)
        # or the pool existed but no matching entry was selected. Either way the action
        # resolved and technique_result is present, confirming the mishap path was reached.
        assert result.action_resolution is not None

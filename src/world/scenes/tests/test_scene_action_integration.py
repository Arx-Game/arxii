"""Integration tests for the full scene action flow.

Exercises the complete pipeline: create request → consent → check resolution →
interaction creation, using real factories (no mocks) for the check system.
"""

from django.test import TestCase

from actions.models import ActionEnhancement
from world.checks.factories import create_social_action_templates
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    TechniqueFactory,
)
from world.scenes.action_constants import (
    ActionRequestStatus,
    ConsentDecision,
    DifficultyChoice,
)
from world.scenes.action_services import create_action_request, respond_to_action_request
from world.scenes.factories import PersonaFactory, SceneFactory
from world.scenes.place_models import InteractionReceiver
from world.traits.factories import CheckSystemSetupFactory
from world.traits.models import CharacterTraitValue, Trait


class TestSceneActionIntegration(TestCase):
    """Full pipeline: request → consent → real check → interaction."""

    @classmethod
    def setUpTestData(cls) -> None:
        # Check system: outcomes, charts, ranks
        CheckSystemSetupFactory.create()

        # Social action templates + check types + trait weights (creates stat traits too)
        templates = create_social_action_templates()
        cls.intimidate_template = next(t for t in templates if t.name == "Intimidate")
        cls.persuade_template = next(t for t in templates if t.name == "Persuade")
        cls.perform_template = next(t for t in templates if t.name == "Perform")

        # Scene + personas with characters
        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()
        cls.target = PersonaFactory()

        # Give the initiator character some presence so checks aren't all zero
        presence_trait = Trait.objects.get(name="presence")
        CharacterTraitValue.objects.create(
            character=cls.initiator.character,
            trait=presence_trait,
            value=30,
        )

    def test_deny_flow(self) -> None:
        """Deny produces no result and no interaction."""
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="intimidate",
        )
        request.action_template = self.intimidate_template
        request.save(update_fields=["action_template"])

        result = respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.DENY,
        )

        assert result is None
        request.refresh_from_db()
        assert request.status == ActionRequestStatus.DENIED
        assert request.result_interaction is None

    def test_accept_resolves_with_real_check(self) -> None:
        """Accept runs perform_check against real traits and produces an interaction."""
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="intimidate",
        )
        request.action_template = self.intimidate_template
        request.save(update_fields=["action_template"])

        result = respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.ACCEPT,
        )

        assert result is not None
        assert result.action_key == "intimidate"
        # full pipeline ran — action_resolution is populated
        assert result.action_resolution is not None
        assert result.action_resolution.main_result is not None
        assert result.technique_result is None  # no technique

        # Interaction was created
        request.refresh_from_db()
        assert request.status == ActionRequestStatus.RESOLVED
        assert request.result_interaction is not None

        # Target is a receiver of the interaction
        receivers = InteractionReceiver.objects.filter(interaction=request.result_interaction)
        assert receivers.filter(persona=self.target).exists()

    def test_hard_difficulty_affects_check(self) -> None:
        """Higher difficulty choice maps to higher target difficulty."""
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="persuade",
            difficulty_choice=DifficultyChoice.HARD,
        )
        request.action_template = self.persuade_template
        request.save(update_fields=["action_template"])

        result = respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.ACCEPT,
        )

        assert result is not None
        request.refresh_from_db()
        assert request.resolved_difficulty == 60  # HARD = 60

    def test_request_without_template_raises(self) -> None:
        """Requests with no action_template raise ValueError."""
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="intimidate",
        )
        # action_template is None by default

        with self.assertRaises(ValueError):
            respond_to_action_request(
                action_request=request,
                decision=ConsentDecision.ACCEPT,
            )


class TestTechniqueEnhancementValidation(TestCase):
    """Validate technique attachment to action requests."""

    @classmethod
    def setUpTestData(cls) -> None:
        CheckSystemSetupFactory.create()
        templates = create_social_action_templates()
        cls.flirt_template = next(t for t in templates if t.name == "Flirt")

        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()
        cls.target = PersonaFactory()

        from world.magic.factories import CharacterTechniqueFactory, TechniqueFactory

        # PersonaFactory ensures a CharacterSheet exists for its character.
        cls.initiator_sheet = cls.initiator.character_sheet
        cls.technique = TechniqueFactory(name="Mesmerizing Gaze")
        CharacterTechniqueFactory(
            character=cls.initiator_sheet,
            technique=cls.technique,
        )

    def test_create_request_with_valid_technique(self) -> None:
        """Technique is stored when ActionEnhancement exists and character knows it."""
        from actions.models import ActionEnhancement

        ActionEnhancement.objects.create(
            base_action_key="flirt",
            variant_name="Enchanted Flirt",
            source_type="technique",
            technique=self.technique,
        )
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="flirt",
            technique=self.technique,
        )
        assert request.technique == self.technique

    def test_create_request_rejects_technique_without_enhancement(self) -> None:
        """Technique rejected when no ActionEnhancement record exists."""
        from django.core.exceptions import ValidationError

        from world.magic.factories import CharacterTechniqueFactory, TechniqueFactory

        rogue_technique = TechniqueFactory(name="Teleportation")
        CharacterTechniqueFactory(character=self.initiator_sheet, technique=rogue_technique)
        with self.assertRaises(ValidationError):
            create_action_request(
                scene=self.scene,
                initiator_persona=self.initiator,
                target_persona=self.target,
                action_key="flirt",
                technique=rogue_technique,
            )

    def test_create_request_rejects_unknown_technique(self) -> None:
        """Technique rejected when character doesn't know it."""
        from django.core.exceptions import ValidationError

        from actions.models import ActionEnhancement
        from world.magic.factories import TechniqueFactory

        unknown_technique = TechniqueFactory(name="Unknown Spell")
        ActionEnhancement.objects.create(
            base_action_key="flirt",
            variant_name="Unknown Flirt",
            source_type="technique",
            technique=unknown_technique,
        )
        with self.assertRaises(ValidationError):
            create_action_request(
                scene=self.scene,
                initiator_persona=self.initiator,
                target_persona=self.target,
                action_key="flirt",
                technique=unknown_technique,
            )


class TestMundaneActionConsequences(TestCase):
    """Mundane social actions now apply consequences via full pipeline."""

    @classmethod
    def setUpTestData(cls) -> None:
        CheckSystemSetupFactory.create()
        templates = create_social_action_templates()
        cls.flirt_template = next(t for t in templates if t.name == "Flirt")

        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()
        cls.target = PersonaFactory()

        presence_trait = Trait.objects.get(name="presence")
        CharacterTraitValue.objects.create(
            character=cls.initiator.character,
            trait=presence_trait,
            value=30,
        )

    def test_mundane_flirt_uses_full_pipeline(self) -> None:
        """Full pipeline returns EnhancedSceneActionResult."""
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
        assert result.technique_result is None  # no technique


class TestEnhancedActionResolution(TestCase):
    """Technique-enhanced social actions run use_technique wrapping full pipeline."""

    @classmethod
    def setUpTestData(cls) -> None:
        CheckSystemSetupFactory.create()
        templates = create_social_action_templates()
        cls.flirt_template = next(t for t in templates if t.name == "Flirt")

        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()
        cls.target = PersonaFactory()

        from actions.models import ActionEnhancement
        from world.magic.factories import (
            CharacterAnimaFactory,
            CharacterTechniqueFactory,
            TechniqueFactory,
        )

        # intensity=15 overrides the social safety bonus (10) so effective_cost > 0:
        # runtime_control = control(1) + social_safety(10) = 11
        # runtime_intensity = 15; control_delta = 11 - 15 = -4
        # effective_cost = max(anima_cost(5) - (-4), 0) = 9
        cls.technique = TechniqueFactory(
            name="Mesmerizing Gaze",
            intensity=15,
            control=1,
            anima_cost=5,
        )

        initiator_sheet = cls.initiator.character_sheet
        CharacterTechniqueFactory(
            character=initiator_sheet,
            technique=cls.technique,
        )
        CharacterAnimaFactory(
            character=cls.initiator.character,
            current=20,
            maximum=30,
        )

        ActionEnhancement.objects.create(
            base_action_key="flirt",
            variant_name="Enchanted Flirt",
            source_type="technique",
            technique=cls.technique,
        )

        presence_trait = Trait.objects.get(name="presence")
        CharacterTraitValue.objects.create(
            character=cls.initiator.character,
            trait=presence_trait,
            value=30,
        )

    def test_enhanced_action_deducts_anima(self) -> None:
        """Technique-enhanced action deducts anima cost."""
        from world.magic.models import CharacterAnima

        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="flirt",
            technique=self.technique,
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
        assert result.technique_result.anima_cost is not None

        anima = CharacterAnima.objects.get(character=self.initiator.character)
        assert anima.current < 20

    def test_enhanced_action_includes_action_resolution(self) -> None:
        """Enhanced action also resolves the social action."""
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="flirt",
            technique=self.technique,
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
        assert result.action_key == "flirt"

    def test_enhanced_action_creates_interaction_with_technique(self) -> None:
        """Enhanced action records interaction mentioning technique."""
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="flirt",
            technique=self.technique,
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
        assert self.technique.name in request.result_interaction.content


class TestAvailableActionsService(TestCase):
    """Unit tests for get_available_scene_actions service function."""

    @classmethod
    def setUpTestData(cls) -> None:
        CheckSystemSetupFactory.create()
        templates = create_social_action_templates()
        cls.flirt_template = next(t for t in templates if t.name == "Flirt")

        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()

        cls.initiator_sheet = cls.initiator.character_sheet
        cls.technique = TechniqueFactory(
            name="Mesmerizing Gaze",
            intensity=5,
            control=8,
            anima_cost=3,
        )
        CharacterTechniqueFactory(
            character=cls.initiator_sheet,
            technique=cls.technique,
        )
        CharacterAnimaFactory(
            character=cls.initiator.character,
            current=20,
            maximum=30,
        )
        ActionEnhancement.objects.create(
            base_action_key="flirt",
            variant_name="Enchanted Flirt",
            source_type="technique",
            technique=cls.technique,
        )

    def test_returns_enhancements_for_known_techniques(self) -> None:
        """Characters with known techniques see enhancement options for matching actions."""
        from world.scenes.action_availability import get_available_scene_actions

        actions = get_available_scene_actions(character=self.initiator.character)
        flirt_action = next((a for a in actions if a.action_key == "flirt"), None)
        assert flirt_action is not None
        assert len(flirt_action.enhancements) == 1
        assert flirt_action.enhancements[0].technique == self.technique

    def test_excludes_unknown_techniques(self) -> None:
        """Techniques the character does not know are excluded from enhancements."""
        from world.scenes.action_availability import get_available_scene_actions

        unknown = TechniqueFactory(name="Unknown Spell")
        ActionEnhancement.objects.create(
            base_action_key="flirt",
            variant_name="Unknown Flirt",
            source_type="technique",
            technique=unknown,
        )
        actions = get_available_scene_actions(character=self.initiator.character)
        flirt_action = next(a for a in actions if a.action_key == "flirt")
        # Only the known technique's enhancement is present
        assert len(flirt_action.enhancements) == 1
        assert flirt_action.enhancements[0].technique == self.technique

    def test_non_magical_character_has_no_enhancements(self) -> None:
        """Characters with no known techniques have no enhancements on any action."""
        from world.scenes.action_availability import get_available_scene_actions

        non_magical = PersonaFactory()
        actions = get_available_scene_actions(character=non_magical.character)
        for action in actions:
            assert len(action.enhancements) == 0

    def test_returns_all_social_action_templates(self) -> None:
        """All social ActionTemplates are returned, even without enhancements."""
        from actions.models import ActionTemplate
        from world.scenes.action_availability import get_available_scene_actions

        social_count = ActionTemplate.objects.filter(category="social").count()
        actions = get_available_scene_actions(character=self.initiator.character)
        assert len(actions) == social_count

    def test_effective_cost_calculated(self) -> None:
        """Effective anima cost is pre-calculated for each enhancement."""
        from world.scenes.action_availability import get_available_scene_actions

        actions = get_available_scene_actions(character=self.initiator.character)
        flirt_action = next(a for a in actions if a.action_key == "flirt")
        enhancement = flirt_action.enhancements[0]
        # Cost is an integer (non-negative)
        assert isinstance(enhancement.effective_cost, int)
        assert enhancement.effective_cost >= 0

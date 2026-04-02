"""Integration tests for the full scene action flow.

Exercises the complete pipeline: create request → consent → check resolution →
interaction creation, using real factories (no mocks) for the check system.
"""

from django.test import TestCase

from world.checks.factories import create_social_action_templates
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

        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import CharacterTechniqueFactory, TechniqueFactory

        cls.initiator_sheet = CharacterSheetFactory(character=cls.initiator.character)
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

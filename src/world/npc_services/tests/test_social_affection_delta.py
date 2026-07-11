"""Test that social-action graded outcomes move NPC disposition (#1591).

Drives the persuade action through ``action.run()`` and asserts that the
durable ``NPCStanding.affection`` value moves by the success tier. The check
outcome is forced via the test-rig seam so the tests are deterministic without
mocking the action lifecycle itself.
"""

from __future__ import annotations

from django.test import TestCase

from actions.constants import Pipeline
from actions.definitions.social import PersuadeAction
from actions.factories import ActionTemplateFactory
from actions.models.action_templates import ActionTemplate
from actions.types import ActionResult
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckCategoryFactory, CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.npc_services.models import NPCStanding
from world.scenes.constants import PersonaType
from world.scenes.factories import PersonaFactory
from world.traits.factories import CheckOutcomeFactory


class SocialAffectionDeltaTest(TestCase):
    """Social action outcomes apply a tiered disposition delta to persona-bearing NPCs."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.pc_sheet = CharacterSheetFactory()
        cls.pc_character = cls.pc_sheet.character
        cls.npc_persona = PersonaFactory(persona_type=PersonaType.ESTABLISHED)

        check_cat = CheckCategoryFactory(name="Social")
        cls.check_type = CheckTypeFactory(name="Persuasion", category=check_cat)

        # Ensure the "Persuade" ActionTemplate exists with a deterministic SINGLE
        # pipeline. Using the factory with django_get_or_create would silently drop
        # non-lookup kwargs if the row already existed, so we upsert explicitly.
        template = ActionTemplate.objects.filter(name="Persuade").first()
        if template is None:
            template = ActionTemplateFactory(
                name="Persuade",
                check_type=cls.check_type,
                pipeline=Pipeline.SINGLE,
                consequence_pool=None,
                category="social",
            )
        else:
            template.check_type = cls.check_type
            template.consequence_pool = None
            template.pipeline = Pipeline.SINGLE
            template.save(update_fields=["check_type", "consequence_pool", "pipeline"])
        cls.template = template

    def test_persuade_success_moves_durable_affection(self) -> None:
        """A successful social check raises NPCStanding.affection by the tier delta."""
        success = CheckOutcomeFactory(name="Social Success", success_level=5)
        self.assertFalse(
            NPCStanding.objects.filter(
                persona=self.pc_sheet.primary_persona,
                npc_persona=self.npc_persona,
            ).exists()
        )

        with force_check_outcome(success):
            result = PersuadeAction().run(
                self.pc_character,
                target_persona_id=self.npc_persona.pk,
            )

        resolution = result.data["resolution"]
        self.assertIsNotNone(resolution.main_result)
        self.assertGreater(resolution.main_result.check_result.success_level, 0)
        standing = NPCStanding.objects.get(
            persona=self.pc_sheet.primary_persona,
            npc_persona=self.npc_persona,
        )
        self.assertEqual(standing.affection, 5)

    def test_failure_does_not_move_disposition(self) -> None:
        """A failed social check leaves affection unchanged and creates no row."""
        failure = CheckOutcomeFactory(name="Social Failure", success_level=-1)

        with force_check_outcome(failure):
            result = PersuadeAction().run(
                self.pc_character,
                target_persona_id=self.npc_persona.pk,
            )

        resolution = result.data["resolution"]
        self.assertIsNotNone(resolution.main_result)
        self.assertLessEqual(resolution.main_result.check_result.success_level, 0)
        self.assertFalse(
            NPCStanding.objects.filter(
                persona=self.pc_sheet.primary_persona,
                npc_persona=self.npc_persona,
            ).exists()
        )

    def test_persona_less_target_is_noop(self) -> None:
        """A target with no persona is a no-op: no ephemeral store update in Task 6."""
        success = CheckOutcomeFactory(name="Social Success Personaless", success_level=3)

        with force_check_outcome(success):
            result = PersuadeAction().run(self.pc_character)

        resolution = result.data["resolution"]
        self.assertIsNotNone(resolution.main_result)
        self.assertGreater(resolution.main_result.check_result.success_level, 0)
        self.assertFalse(NPCStanding.objects.exists())

    def test_success_level_fallback_for_unexpected_result_shape(self) -> None:
        """The helper returns 0 (no movement) when the result lacks a check_result."""
        from world.npc_services.social_disposition import (
            _delta_for_tier,
            _success_level,
        )

        bare = ActionResult(success=True)
        self.assertEqual(_success_level(bare), 0)
        self.assertEqual(_delta_for_tier(_success_level(bare)), 0)

    def test_pc_target_is_noop(self) -> None:
        """A successful social action aimed at a PC must not write an NPCStanding row."""
        from world.scenes.action_services import _persona_is_npc

        pc_target_character = CharacterFactory()
        pc_target_character.db_account = AccountFactory()
        pc_target_character.save()
        pc_target_sheet = CharacterSheetFactory(character=pc_target_character)
        pc_target_persona = PersonaFactory(
            character_sheet=pc_target_sheet, persona_type=PersonaType.ESTABLISHED
        )

        self.assertFalse(_persona_is_npc(pc_target_persona))

        success = CheckOutcomeFactory(name="Social Success PC Target", success_level=5)

        with force_check_outcome(success):
            result = PersuadeAction().run(
                self.pc_character,
                target_persona_id=pc_target_persona.pk,
            )

        resolution = result.data["resolution"]
        self.assertIsNotNone(resolution.main_result)
        self.assertGreater(resolution.main_result.check_result.success_level, 0)
        self.assertFalse(
            NPCStanding.objects.filter(
                persona=self.pc_sheet.primary_persona,
                npc_persona=pc_target_persona,
            ).exists()
        )

    def test_success_returns_qualitative_message(self) -> None:
        """A successful check returns a ready-to-display warm message, not None."""
        from world.npc_services.social_disposition import apply_social_disposition_delta

        success = CheckOutcomeFactory(name="Social Success", success_level=5)
        with force_check_outcome(success):
            result = PersuadeAction().run(
                self.pc_character,
                target_persona_id=self.npc_persona.pk,
            )
        resolution = result.data["resolution"]
        message = apply_social_disposition_delta(self.pc_character, self.npc_persona.pk, resolution)
        self.assertIsNotNone(message)
        self.assertIn("warms considerably", message)

    def test_no_movement_returns_none(self) -> None:
        """A failed check (no delta) returns None, not an empty message."""
        from world.npc_services.social_disposition import apply_social_disposition_delta

        failure = CheckOutcomeFactory(name="Social Failure", success_level=0)
        with force_check_outcome(failure):
            result = PersuadeAction().run(
                self.pc_character,
                target_persona_id=self.npc_persona.pk,
            )
        resolution = result.data["resolution"]
        message = apply_social_disposition_delta(self.pc_character, self.npc_persona.pk, resolution)
        self.assertIsNone(message)

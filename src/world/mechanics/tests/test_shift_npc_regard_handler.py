"""Tests for the _shift_npc_regard effect handler (#2039)."""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import EffectTarget, EffectType
from world.checks.factories import ConsequenceEffectFactory
from world.checks.types import ResolutionContext
from world.mechanics.effect_handlers import apply_effect
from world.npc_services.constants import NpcRegardEventReason
from world.npc_services.models import NpcRegard
from world.scenes.factories import SceneFactory


class ShiftNpcRegardHandlerTests(TestCase):
    """Dispatches through ``apply_effect`` (the real dispatcher), never the handler directly."""

    def _make_context(self, *, scene, actor_primary_persona=True, recipient_primary_persona=True):
        actor_character = CharacterFactory(db_key="npc_regard_actor")
        CharacterSheetFactory(character=actor_character, primary_persona=actor_primary_persona)

        recipient_character = CharacterFactory(db_key="npc_regard_recipient")
        CharacterSheetFactory(
            character=recipient_character, primary_persona=recipient_primary_persona
        )

        return ResolutionContext(character=actor_character, target=recipient_character, scene=scene)

    def _effect(self, amount):
        return ConsequenceEffectFactory(
            effect_type=EffectType.SHIFT_NPC_REGARD,
            target=EffectTarget.TARGET,
            npc_regard_amount=amount,
        )

    def test_negative_amount_records_regard_event(self) -> None:
        scene = SceneFactory()
        context = self._make_context(scene=scene)
        applied = apply_effect(self._effect(-10), context)

        self.assertTrue(applied.applied)
        regard = NpcRegard.objects.get(
            holder_persona=context.target.sheet_data.primary_persona,
            target_persona=context.character.sheet_data.primary_persona,
        )
        self.assertEqual(regard.value, -10)
        event = regard.events.get()
        self.assertEqual(event.reason, NpcRegardEventReason.SOCIAL_ACTION_RESOLVED)
        self.assertEqual(event.source_scene_id, scene.pk)

    def test_positive_amount_records_regard_event(self) -> None:
        scene = SceneFactory()
        context = self._make_context(scene=scene)
        applied = apply_effect(self._effect(15), context)

        self.assertTrue(applied.applied)
        regard = NpcRegard.objects.get(
            holder_persona=context.target.sheet_data.primary_persona,
            target_persona=context.character.sheet_data.primary_persona,
        )
        self.assertEqual(regard.value, 15)
        event = regard.events.get()
        self.assertEqual(event.reason, NpcRegardEventReason.SOCIAL_ACTION_RESOLVED)
        self.assertEqual(event.source_scene_id, scene.pk)

    def test_no_scene_skips(self) -> None:
        context = self._make_context(scene=None)
        applied = apply_effect(self._effect(-10), context)

        self.assertFalse(applied.applied)
        self.assertEqual(applied.skip_reason, "no_scene")
        self.assertEqual(NpcRegard.objects.count(), 0)

    def test_zero_amount_skips(self) -> None:
        scene = SceneFactory()
        context = self._make_context(scene=scene)
        applied = apply_effect(self._effect(None), context)

        self.assertFalse(applied.applied)
        self.assertEqual(applied.skip_reason, "zero_amount")
        self.assertEqual(NpcRegard.objects.count(), 0)

    def test_missing_sheet_skips(self) -> None:
        scene = SceneFactory()
        actor_character = CharacterFactory(db_key="npc_regard_actor_no_sheet")
        recipient_character = CharacterFactory(db_key="npc_regard_recipient_no_sheet")
        context = ResolutionContext(
            character=actor_character, target=recipient_character, scene=scene
        )
        applied = apply_effect(self._effect(-10), context)

        self.assertFalse(applied.applied)
        self.assertEqual(applied.skip_reason, "missing_sheet")
        self.assertEqual(NpcRegard.objects.count(), 0)

    def test_self_target_skips(self) -> None:
        scene = SceneFactory()
        actor_character = CharacterFactory(db_key="npc_regard_self")
        CharacterSheetFactory(character=actor_character)
        context = ResolutionContext(character=actor_character, target=actor_character, scene=scene)
        applied = apply_effect(self._effect(-10), context)

        self.assertFalse(applied.applied)
        self.assertEqual(applied.skip_reason, "self_target")
        self.assertEqual(NpcRegard.objects.count(), 0)

    def test_missing_persona_skips(self) -> None:
        scene = SceneFactory()
        context = self._make_context(scene=scene, recipient_primary_persona=False)
        applied = apply_effect(self._effect(-10), context)

        self.assertFalse(applied.applied)
        self.assertEqual(applied.skip_reason, "missing_persona")
        self.assertEqual(NpcRegard.objects.count(), 0)

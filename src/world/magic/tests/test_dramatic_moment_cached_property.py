"""Tests for Interaction.cached_dramatic_moment_tags/suggestions (#3816 Task 6).

Write-site mutation at the three gain.py services (create_dramatic_moment_tag,
maybe_suggest_dramatic_moments, resolve_dramatic_moment_suggestion) must keep the
warmed cache on the Interaction in sync, so a serializer reading a warmed
Interaction after one of these calls doesn't issue an extra query -- or worse,
report stale data.
"""

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import SuggestionStatus
from world.magic.factories import (
    CharacterResonanceFactory,
    DramaticMomentTypeFactory,
    ResonanceFactory,
)
from world.magic.services.gain import (
    create_dramatic_moment_tag,
    maybe_suggest_dramatic_moments,
    resolve_dramatic_moment_suggestion,
)
from world.scenes.factories import InteractionFactory, SceneFactory


class DramaticMomentTagCachedPropertyTest(TestCase):
    def setUp(self):
        self.sheet = CharacterSheetFactory()
        self.resonance = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=self.resonance,
            balance=0,
            lifetime_earned=0,
        )
        self.moment_type = DramaticMomentTypeFactory(
            resonance=self.resonance,
            resonance_amount=15,
        )
        self.tagger = AccountFactory()
        self.scene = SceneFactory()
        self.interaction = InteractionFactory(scene=self.scene)

    def test_create_tag_updates_interaction_cache(self):
        _ = self.interaction.cached_dramatic_moment_tags  # warm to []
        create_dramatic_moment_tag(
            character_sheet=self.sheet,
            moment_type=self.moment_type,
            tagged_by=self.tagger,
            scene=self.scene,
            interaction=self.interaction,
        )
        self.assertEqual(len(self.interaction.cached_dramatic_moment_tags), 1)

    def test_create_tag_without_interaction_does_not_crash(self):
        # interaction=None is the nullable-interaction shape -- no cache to update.
        tag = create_dramatic_moment_tag(
            character_sheet=self.sheet,
            moment_type=self.moment_type,
            tagged_by=self.tagger,
            scene=self.scene,
            interaction=None,
        )
        self.assertIsNone(tag.interaction_id)


class DramaticMomentSuggestionCachedPropertyTest(TestCase):
    def setUp(self):
        self.sheet = CharacterSheetFactory()
        self.resonance = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=self.resonance,
            balance=0,
            lifetime_earned=0,
        )
        self.moment_type = DramaticMomentTypeFactory(
            resonance=self.resonance,
            suggest_on_technique_entrance=True,
            suggestion_min_success_level=3,
            per_scene_cap=1,
        )
        self.scene = SceneFactory()
        self.interaction = InteractionFactory(scene=self.scene)
        self.resolver = AccountFactory()

    def test_suggest_updates_interaction_cache(self):
        _ = self.interaction.cached_dramatic_moment_suggestions  # warm to []
        created = maybe_suggest_dramatic_moments(
            character_sheet=self.sheet,
            scene=self.scene,
            success_level=3,
            interaction=self.interaction,
        )
        self.assertEqual(len(created), 1)
        self.assertEqual(len(self.interaction.cached_dramatic_moment_suggestions), 1)
        self.assertEqual(self.interaction.cached_dramatic_moment_suggestions[0].pk, created[0].pk)

    def test_resolve_suggestion_updates_pending_cache(self):
        # A confirmed/dismissed suggestion must drop out of the PENDING-filtered cache.
        [suggestion] = maybe_suggest_dramatic_moments(
            character_sheet=self.sheet,
            scene=self.scene,
            success_level=3,
            interaction=self.interaction,
        )
        _ = self.interaction.cached_dramatic_moment_suggestions  # warm, contains it
        self.assertEqual(len(self.interaction.cached_dramatic_moment_suggestions), 1)

        resolved = resolve_dramatic_moment_suggestion(
            suggestion, confirm=False, resolver=self.resolver
        )

        self.assertEqual(resolved.status, SuggestionStatus.DISMISSED)
        self.assertEqual(self.interaction.cached_dramatic_moment_suggestions, [])

"""Tests for Interaction.cached_dramatic_moment_tags (#3816 Task 6).

Write-site mutation at create_dramatic_moment_tag must keep the warmed cache on
the Interaction in sync, so a serializer reading a warmed Interaction after a
tag-create call doesn't issue an extra query -- or worse, report stale data.

The sibling ``cached_dramatic_moment_suggestions`` coverage (the per-pose
suggestion embed) was retired with the embed itself (#4101 Task 9) -- see
``world.gm.tests.test_prompt_api`` for the replacement GMPromptViewSet queue
coverage.
"""

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import (
    CharacterResonanceFactory,
    DramaticMomentTypeFactory,
    ResonanceFactory,
)
from world.magic.services.gain import create_dramatic_moment_tag
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
        # assertNumQueries(0) is the actual proof the write-site mutation ran: with
        # it deleted, DramaticMomentTag's RelatedCacheClearingMixin still pops the
        # warmed cache and PrunedCachedProperty still falls back to a fresh query,
        # producing the identical `len(...) == 1` result -- only a zero-query read
        # distinguishes "mutation works" from "mutation doesn't exist."
        with self.assertNumQueries(0):
            cached = self.interaction.cached_dramatic_moment_tags
        self.assertEqual(len(cached), 1)

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

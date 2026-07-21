"""Tests for world.magic.services.glimpse (#2427)."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.magic.constants import GlimpseState, GlimpseTagAxis
from world.magic.factories import CharacterAuraFactory, GlimpseTagFactory
from world.magic.models import CharacterGlimpseTag
from world.magic.services.glimpse import (
    link_distinction_to_glimpse,
    refresh_glimpse_state,
    set_glimpse_prose,
    set_glimpse_tags,
    unlink_distinction_from_glimpse,
)


class SetGlimpseTagsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.aura = CharacterAuraFactory()
        cls.tone_a = GlimpseTagFactory(axis=GlimpseTagAxis.TONE, slug="tone-a")
        cls.tone_b = GlimpseTagFactory(axis=GlimpseTagAxis.TONE, slug="tone-b")
        cls.consequence_a = GlimpseTagFactory(axis=GlimpseTagAxis.CONSEQUENCE, slug="consequence-a")
        cls.consequence_b = GlimpseTagFactory(axis=GlimpseTagAxis.CONSEQUENCE, slug="consequence-b")

    def test_sets_tags_and_state_becomes_tags_only(self):
        set_glimpse_tags(self.aura, [self.tone_a], axis=GlimpseTagAxis.TONE)
        assert self.aura.glimpse_state == GlimpseState.TAGS_ONLY
        assert list(
            CharacterGlimpseTag.objects.filter(aura=self.aura).values_list("tag__slug", flat=True)
        ) == ["tone-a"]

    def test_replaces_tags_for_axis_only(self):
        set_glimpse_tags(self.aura, [self.consequence_a], axis=GlimpseTagAxis.CONSEQUENCE)
        set_glimpse_tags(self.aura, [self.tone_a], axis=GlimpseTagAxis.TONE)
        set_glimpse_tags(self.aura, [self.tone_b], axis=GlimpseTagAxis.TONE)
        slugs = set(
            CharacterGlimpseTag.objects.filter(aura=self.aura).values_list("tag__slug", flat=True)
        )
        assert slugs == {"consequence-a", "tone-b"}

    def test_tone_rejects_multiple_tags(self):
        with self.assertRaises(ValidationError):
            set_glimpse_tags(self.aura, [self.tone_a, self.tone_b], axis=GlimpseTagAxis.TONE)

    def test_consequence_accepts_multiple_tags(self):
        set_glimpse_tags(
            self.aura,
            [self.consequence_a, self.consequence_b],
            axis=GlimpseTagAxis.CONSEQUENCE,
        )
        assert CharacterGlimpseTag.objects.filter(aura=self.aura).count() == 2

    def test_rejects_tag_from_wrong_axis(self):
        with self.assertRaises(ValidationError):
            set_glimpse_tags(self.aura, [self.consequence_a], axis=GlimpseTagAxis.TONE)

    def test_clearing_all_tags_returns_to_not_started(self):
        set_glimpse_tags(self.aura, [self.tone_a], axis=GlimpseTagAxis.TONE)
        set_glimpse_tags(self.aura, [], axis=GlimpseTagAxis.TONE)
        assert self.aura.glimpse_state == GlimpseState.NOT_STARTED


class GlimpseStateTransitionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tone = GlimpseTagFactory(axis=GlimpseTagAxis.TONE, slug="tone-x")

    def setUp(self):
        self.aura = CharacterAuraFactory()

    def test_prose_alone_completes(self):
        set_glimpse_prose(self.aura, "I saw the threads.")
        assert self.aura.glimpse_state == GlimpseState.COMPLETE
        assert self.aura.glimpse_story == "I saw the threads."

    def test_tags_then_prose_completes(self):
        set_glimpse_tags(self.aura, [self.tone], axis=GlimpseTagAxis.TONE)
        assert self.aura.glimpse_state == GlimpseState.TAGS_ONLY
        set_glimpse_prose(self.aura, "It was horrifying.")
        assert self.aura.glimpse_state == GlimpseState.COMPLETE

    def test_erasing_prose_with_tags_returns_to_tags_only(self):
        set_glimpse_tags(self.aura, [self.tone], axis=GlimpseTagAxis.TONE)
        set_glimpse_prose(self.aura, "Draft text.")
        set_glimpse_prose(self.aura, "")
        assert self.aura.glimpse_state == GlimpseState.TAGS_ONLY

    def test_refresh_recomputes_from_truth(self):
        self.aura.glimpse_story = "Written out of band."
        self.aura.save()
        assert refresh_glimpse_state(self.aura) == GlimpseState.COMPLETE


class GlimpseDistinctionLinkTests(TestCase):
    def test_link_and_unlink(self):
        from world.character_sheets.factories import CharacterSheetFactory
        from world.distinctions.factories import CharacterDistinctionFactory

        aura = CharacterAuraFactory()
        sheet = CharacterSheetFactory(character=aura.character)
        cd = CharacterDistinctionFactory(character=sheet)
        link_distinction_to_glimpse(cd, aura)
        assert cd.from_glimpse_id == aura.pk
        unlink_distinction_from_glimpse(cd)
        assert cd.from_glimpse_id is None

    def test_link_rejects_other_characters_aura(self):
        from world.distinctions.factories import CharacterDistinctionFactory

        aura = CharacterAuraFactory()
        cd = CharacterDistinctionFactory()  # different character
        with self.assertRaises(ValidationError):
            link_distinction_to_glimpse(cd, aura)

"""Model tests for the glimpse tag catalog (#2427)."""

from django.db import IntegrityError
from django.test import TestCase

from world.distinctions.factories import DistinctionFactory
from world.magic.constants import GlimpseState, GlimpseTagAxis
from world.magic.factories import (
    CharacterAuraFactory,
    CharacterGlimpseTagFactory,
    GlimpseTagDistinctionSuggestionFactory,
    GlimpseTagFactory,
)
from world.magic.models import CharacterGlimpseTag, GlimpseTag


class GlimpseTagModelTests(TestCase):
    def test_natural_key_is_slug(self):
        tag = GlimpseTagFactory(slug="traumatic-awakening")
        assert tag.natural_key() == ("traumatic-awakening",)
        fetched = GlimpseTag.objects.get_by_natural_key("traumatic-awakening")
        assert fetched.pk == tag.pk

    def test_ordering_by_axis_then_sort_order(self):
        GlimpseTagFactory(axis=GlimpseTagAxis.WITNESS, sort_order=1, slug="w1")
        GlimpseTagFactory(axis=GlimpseTagAxis.TONE, sort_order=2, slug="t2")
        GlimpseTagFactory(axis=GlimpseTagAxis.TONE, sort_order=1, slug="t1")
        slugs = list(GlimpseTag.objects.values_list("slug", flat=True))
        assert slugs.index("t1") < slugs.index("t2") < slugs.index("w1")


class CharacterGlimpseTagModelTests(TestCase):
    def test_unique_per_aura_and_tag(self):
        row = CharacterGlimpseTagFactory()
        with self.assertRaises(IntegrityError):
            CharacterGlimpseTag.objects.create(aura=row.aura, tag=row.tag)

    def test_aura_defaults_to_not_started(self):
        aura = CharacterAuraFactory()
        assert aura.glimpse_state == GlimpseState.NOT_STARTED


class GlimpseSuggestionModelTests(TestCase):
    def test_natural_key_round_trip(self):
        suggestion = GlimpseTagDistinctionSuggestionFactory(
            tag__slug="killed-someone", distinction=DistinctionFactory(slug="haunted")
        )
        # NaturalKeyMixin flattens FK natural keys into the tuple (each FK's
        # own 1-tuple natural key contributes its bare value, not a nested
        # tuple) — observed behavior of core.natural_keys.NaturalKeyMixin.
        assert suggestion.natural_key() == ("killed-someone", "haunted")
        fetched = suggestion.__class__.objects.get_by_natural_key("killed-someone", "haunted")
        assert fetched.pk == suggestion.pk


class CharacterDistinctionFromGlimpseTests(TestCase):
    def test_set_null_on_aura_delete(self):
        from world.character_sheets.factories import CharacterSheetFactory
        from world.distinctions.factories import CharacterDistinctionFactory

        aura = CharacterAuraFactory()
        sheet = CharacterSheetFactory(character=aura.character)
        cd = CharacterDistinctionFactory(character=sheet, from_glimpse=aura)
        cd_pk = cd.pk
        aura.delete()
        from world.distinctions.models import CharacterDistinction

        # Collector-driven on_delete=SET_NULL bypasses per-instance .save(), so
        # the idmapper identity map still holds the pre-delete cached instance
        # even after a fresh .get(pk=...) — flush before re-reading (see the
        # sharedmemory-model skill's "Known stale-cache traps").
        CharacterDistinction.flush_instance_cache()
        refreshed = CharacterDistinction.objects.get(pk=cd_pk)
        assert refreshed.from_glimpse is None

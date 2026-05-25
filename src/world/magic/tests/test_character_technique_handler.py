"""Tests for CharacterTechniqueHandler (Phase 2 — combat-resolution-loop)."""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import (
    CharacterTechniqueFactory,
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
)
from world.magic.handlers import CharacterTechniqueHandler
from world.mechanics.models import Property


class CharacterTechniqueHandlerCachingTests(TestCase):
    """The handler should cache the technique inventory across reads."""

    def setUp(self) -> None:
        super().setUp()
        self.sheet = CharacterSheetFactory()
        self.technique_a = TechniqueFactory(clash_capable=True)
        self.technique_b = TechniqueFactory(clash_capable=False)
        CharacterTechniqueFactory(character=self.sheet, technique=self.technique_a)
        CharacterTechniqueFactory(character=self.sheet, technique=self.technique_b)

    def test_state_prefetches_once(self) -> None:
        handler = CharacterTechniqueHandler(self.sheet.character)

        # Populate the cache.
        _ = handler._state

        # Subsequent subset reads do not query.
        with self.assertNumQueries(0):
            handler.all()
            handler.clash_capable()

    def test_all_returns_every_technique(self) -> None:
        handler = CharacterTechniqueHandler(self.sheet.character)
        all_techs = handler.all()
        self.assertEqual(
            {t.pk for t in all_techs},
            {self.technique_a.pk, self.technique_b.pk},
        )

    def test_clash_capable_filters_correctly(self) -> None:
        handler = CharacterTechniqueHandler(self.sheet.character)
        clash_capable = handler.clash_capable()
        self.assertEqual({t.pk for t in clash_capable}, {self.technique_a.pk})

    def test_invalidate_drops_cache(self) -> None:
        handler = CharacterTechniqueHandler(self.sheet.character)
        _ = handler._state  # populate
        handler.invalidate()
        self.assertNotIn("_state", handler.__dict__)


class CharacterTechniqueHandlerEffectPropertyTests(TestCase):
    """Effect properties resolve via the Gift → Resonance → Property chain."""

    def setUp(self) -> None:
        super().setUp()
        # Build the property chain: 2 properties, 1 resonance carrying both.
        self.prop_fire = Property.objects.create(
            name="fire-test",
            category_id=self._category_pk(),
        )
        self.prop_lightning = Property.objects.create(
            name="lightning-test",
            category_id=self._category_pk(),
        )
        self.prop_charm = Property.objects.create(
            name="charm-test",
            category_id=self._category_pk(),
        )

        self.resonance = ResonanceFactory()
        self.resonance.properties.add(self.prop_fire, self.prop_lightning)

        # Gift with the resonance attached, Technique linked to the Gift.
        self.gift = GiftFactory()
        self.gift.resonances.add(self.resonance)

        self.sheet = CharacterSheetFactory()
        self.technique = TechniqueFactory(gift=self.gift, clash_capable=True)
        CharacterTechniqueFactory(character=self.sheet, technique=self.technique)

    def _category_pk(self) -> int:
        from world.mechanics.models import PropertyCategory

        cat, _ = PropertyCategory.objects.get_or_create(
            name="test-elements",
            defaults={"description": "Test elemental properties"},
        )
        return cat.pk

    def test_effect_property_ids_for_walks_gift_resonance_chain(self) -> None:
        handler = CharacterTechniqueHandler(self.sheet.character)
        ids = handler.effect_property_ids_for(self.technique)
        self.assertEqual(ids, frozenset({self.prop_fire.pk, self.prop_lightning.pk}))

    def test_effect_property_ids_for_unknown_technique_returns_empty(self) -> None:
        other_technique = TechniqueFactory()  # not granted to self.sheet
        handler = CharacterTechniqueHandler(self.sheet.character)
        self.assertEqual(handler.effect_property_ids_for(other_technique), frozenset())

    def test_helper_eligible_for_matches_property_overlap(self) -> None:
        handler = CharacterTechniqueHandler(self.sheet.character)

        # Clash needs a fire property — technique carries it, so it's eligible.
        eligible = handler.helper_eligible_for(frozenset({self.prop_fire.pk}))
        self.assertEqual([t.pk for t in eligible], [self.technique.pk])

        # Clash needs a charm property — technique doesn't carry it.
        self.assertEqual(handler.helper_eligible_for(frozenset({self.prop_charm.pk})), [])

    def test_helper_eligible_for_empty_set_returns_empty(self) -> None:
        handler = CharacterTechniqueHandler(self.sheet.character)
        self.assertEqual(handler.helper_eligible_for(frozenset()), [])

    def test_helper_eligible_for_excludes_non_clash_capable(self) -> None:
        non_clash_tech = TechniqueFactory(gift=self.gift, clash_capable=False)
        CharacterTechniqueFactory(character=self.sheet, technique=non_clash_tech)

        handler = CharacterTechniqueHandler(self.sheet.character)
        eligible = handler.helper_eligible_for(frozenset({self.prop_fire.pk}))
        # Only the clash-capable technique should be eligible.
        self.assertEqual([t.pk for t in eligible], [self.technique.pk])

"""A chosen price makes the cast stronger and shows in its narration (#4099)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.interaction_services import render_action_outcome_narration
from world.combat.types import ActionOutcome
from world.magic.factories import CharacterTechniqueFactory, PriceFactory, TechniqueFactory
from world.magic.narration import render_cast_outcome_narration
from world.magic.services.power_terms import (
    PowerTermContext,
    get_power_term_providers,
    price_power_term,
)
from world.magic.services.technique_personalization import resolve_price_snippet
from world.scenes.cast_services import request_technique_cast
from world.scenes.tests.cast_test_helpers import (
    CastScenarioMixin,
    grant_technique,
    make_benign_castable_technique,
)


class PricePowerTermTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.technique = TechniqueFactory()
        cls.price = PriceFactory(power_bonus=6)

    def _ctx(self) -> PowerTermContext:
        self.sheet.character.techniques.invalidate()
        return PowerTermContext(sheet=self.sheet, technique=self.technique, applicable_threads=[])

    def test_registered(self) -> None:
        self.assertIn(price_power_term, get_power_term_providers())

    def test_unpriced_hold_adds_nothing(self) -> None:
        CharacterTechniqueFactory(character=self.sheet, technique=self.technique)
        self.assertEqual(price_power_term(self._ctx()), 0)

    def test_price_adds_its_power_bonus(self) -> None:
        hold = CharacterTechniqueFactory(character=self.sheet, technique=self.technique)
        hold.price = self.price
        hold.save(update_fields=["price"])
        self.assertEqual(price_power_term(self._ctx()), 6)

    def test_no_technique_adds_nothing(self) -> None:
        ctx = PowerTermContext(sheet=self.sheet, technique=None, applicable_threads=[])
        self.assertEqual(price_power_term(ctx), 0)

    def test_price_flipped_to_design_kind_adds_nothing(self) -> None:
        """A row staff later flip from PRICE to DESIGN grants nothing (#4099 final fix) -
        the hold's FK is stale; the row's current kind is checked fresh at read time."""
        from world.magic.constants import RestrictionKind

        hold = CharacterTechniqueFactory(character=self.sheet, technique=self.technique)
        hold.price = self.price
        hold.save(update_fields=["price"])
        self.price.kind = RestrictionKind.DESIGN
        self.price.creation_point_cost = None
        self.price.save(update_fields=["kind", "creation_point_cost"])
        self.assertEqual(price_power_term(self._ctx()), 0)


class PriceOwnershipScopingTests(TestCase):
    """A price belongs to the hold that bought it - never bleeds to another caster's
    cast of the same technique (#4099 fix round 1)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.technique = TechniqueFactory()
        cls.price = PriceFactory(
            power_bonus=6, cast_narration="frost blooms white across their hand"
        )
        cls.sheet_a = CharacterSheetFactory()
        cls.sheet_b = CharacterSheetFactory()
        hold_a = CharacterTechniqueFactory(character=cls.sheet_a, technique=cls.technique)
        hold_a.price = cls.price
        hold_a.save(update_fields=["price"])
        CharacterTechniqueFactory(character=cls.sheet_b, technique=cls.technique)

    def test_non_owner_power_term_is_zero(self) -> None:
        self.sheet_b.character.techniques.invalidate()
        ctx = PowerTermContext(sheet=self.sheet_b, technique=self.technique, applicable_threads=[])
        self.assertEqual(price_power_term(ctx), 0)

    def test_owner_still_gets_the_power_bonus(self) -> None:
        """Sanity check alongside the non-owner test: A's own cast is unaffected by B."""
        self.sheet_a.character.techniques.invalidate()
        ctx = PowerTermContext(sheet=self.sheet_a, technique=self.technique, applicable_threads=[])
        self.assertEqual(price_power_term(ctx), 6)

    def test_non_owner_narration_carries_no_price_clause(self) -> None:
        self.sheet_b.character.techniques.invalidate()
        snippet = resolve_price_snippet(self.sheet_b.character, self.technique)
        self.assertIsNone(snippet)
        line = render_cast_outcome_narration(
            actor_label="B",
            technique_name=self.technique.name,
            target_label=None,
            outcome_label="Success",
            success_level=1,
            price_snippet=snippet,
        )
        self.assertNotIn("frost blooms white", line)


class PriceHandlerCachingTests(TestCase):
    """price_power_term reads the hold through the cached handler - one query no
    matter how many times a single cast context asks for it (#4099 fix round 1)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.technique = TechniqueFactory()
        cls.price = PriceFactory(power_bonus=6)
        hold = CharacterTechniqueFactory(character=cls.sheet, technique=cls.technique)
        hold.price = cls.price
        hold.save(update_fields=["price"])

    def test_hold_is_read_once_and_cached_across_calls(self) -> None:
        self.sheet.character.techniques.invalidate()
        ctx = PowerTermContext(sheet=self.sheet, technique=self.technique, applicable_threads=[])

        with self.assertNumQueries(1):
            self.assertEqual(price_power_term(ctx), 6)
        with self.assertNumQueries(0):
            self.assertEqual(price_power_term(ctx), 6)


class PriceNarrationRenderTests(TestCase):
    def test_price_clause_follows_the_signature_clause(self) -> None:
        line = render_cast_outcome_narration(
            actor_label="Kira",
            technique_name="Winterbite",
            target_label=None,
            outcome_label="Success",
            success_level=1,
            signature_snippet="a chill rides her voice",
            price_snippet="frost blooms white across her hand",
        )
        self.assertIn("Kira casts Winterbite", line)
        self.assertLess(line.index("a chill rides"), line.index("frost blooms white"))


class PriceCombatNarrationRenderTests(TestCase):
    def test_price_clause_appears_in_combat_narration(self) -> None:
        outcome = ActionOutcome(entity_type="pc", entity_label="Kira")
        text = render_action_outcome_narration(
            actor_label="Kira",
            technique_name="Frost Bolt",
            target_label="the Pyromancer",
            outcome=outcome,
            price_snippet="frost blooms white across her hand",
        )
        self.assertIn("frost blooms white across her hand", text)


class PriceCastNarrationTests(CastScenarioMixin):
    """A cast's narration includes the chosen price (spec test seam)."""

    def test_cast_pose_uses_the_players_name_and_price(self) -> None:
        technique = make_benign_castable_technique()
        grant_technique(self.caster, technique)
        hold = self.caster.character_sheet.character_techniques.get(technique=technique)
        hold.custom_name = "Winterbite"
        hold.price = PriceFactory(cast_narration="frost blooms white across their hand")
        hold.save(update_fields=["custom_name", "price"])
        self.caster.character_sheet.character.techniques.invalidate()

        cast = request_technique_cast(
            scene=self.scene, initiator_persona=self.caster, technique=technique
        )
        self.assertIsNotNone(cast.outcome_interaction)
        content = cast.outcome_interaction.content
        self.assertIn("Winterbite", content)
        self.assertIn("frost blooms white across their hand", content)
        self.assertNotIn(technique.name, content)

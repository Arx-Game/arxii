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

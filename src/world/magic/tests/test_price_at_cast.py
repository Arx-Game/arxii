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
from world.magic.services.technique_personalization import (
    paid_price_snippet,
    price_paid_for_cast,
)
from world.magic.types.personalization import PricePayment
from world.scenes.cast_services import request_technique_cast
from world.scenes.tests.cast_test_helpers import (
    CastScenarioMixin,
    grant_technique,
    make_benign_castable_technique,
)


class PricePowerTermTests(TestCase):
    """The power term adds the bonus of the price the cast PAID (its context's one
    decision), never re-reading the hold (#4099)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.technique = TechniqueFactory()
        cls.price = PriceFactory(power_bonus=6)

    def _ctx(self, payment: PricePayment | None) -> PowerTermContext:
        return PowerTermContext(
            sheet=self.sheet,
            technique=self.technique,
            applicable_threads=[],
            price_payment=payment,
        )

    def test_registered(self) -> None:
        self.assertIn(price_power_term, get_power_term_providers())

    def test_unpaid_cast_adds_nothing(self) -> None:
        self.assertEqual(price_power_term(self._ctx(None)), 0)

    def test_paid_price_adds_its_power_bonus(self) -> None:
        self.assertEqual(price_power_term(self._ctx(PricePayment(price=self.price))), 6)

    def test_reads_the_decision_without_a_query(self) -> None:
        ctx = self._ctx(PricePayment(price=self.price))
        with self.assertNumQueries(0):
            self.assertEqual(price_power_term(ctx), 6)


class PriceDecisionTests(TestCase):
    """``price_paid_for_cast`` reads the hold: its price, scoped to its owner, and
    honoured only while the row is still a PRICE (#4099 fix rounds)."""

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

    def setUp(self) -> None:
        self.sheet_a.character.techniques.invalidate()
        self.sheet_b.character.techniques.invalidate()

    def test_owner_pays_their_price(self) -> None:
        payment = price_paid_for_cast(self.sheet_a.character, self.technique)
        self.assertEqual(payment.price, self.price)

    def test_non_owner_pays_nothing_and_narrates_no_clause(self) -> None:
        payment = price_paid_for_cast(self.sheet_b.character, self.technique)
        self.assertIsNone(payment)
        line = render_cast_outcome_narration(
            actor_label="B",
            technique_name=self.technique.name,
            target_label=None,
            outcome_label="Success",
            success_level=1,
            price_snippet=paid_price_snippet(None),
        )
        self.assertNotIn("frost blooms white", line)

    def test_price_flipped_to_design_kind_is_not_paid(self) -> None:
        """A row staff later flip from PRICE to DESIGN grants nothing (#4099 final fix) -
        the hold's FK is stale; the row's current kind is checked fresh at read time."""
        from world.magic.constants import RestrictionKind

        self.price.kind = RestrictionKind.DESIGN
        self.price.creation_point_cost = None
        self.price.save(update_fields=["kind", "creation_point_cost"])
        self.assertIsNone(price_paid_for_cast(self.sheet_a.character, self.technique))


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

    def _priced_with_component(self, *, carried: int):
        """A cast technique whose price consumes 2 needles; the caster carries ``carried``."""
        from world.items.factories import ItemTemplateFactory
        from world.magic.models import PriceComponentRequirement
        from world.magic.tests.price_cost_helpers import carry

        technique = make_benign_castable_technique()
        grant_technique(self.caster, technique)
        needle = ItemTemplateFactory()
        price = PriceFactory(cast_narration="blood beads on the needle")
        PriceComponentRequirement.objects.create(
            restriction=price, item_template=needle, quantity=2
        )
        hold = self.caster.character_sheet.character_techniques.get(technique=technique)
        hold.price = price
        hold.save(update_fields=["price"])
        character = self.caster.character_sheet.character
        character.techniques.invalidate()
        stack = carry(character, needle, quantity=carried)
        cast = request_technique_cast(
            scene=self.scene, initiator_persona=self.caster, technique=technique
        )
        return cast, stack

    def test_scene_cast_with_the_component_spends_it_and_narrates(self) -> None:
        cast, stack = self._priced_with_component(carried=2)
        self.assertIn("blood beads on the needle", cast.outcome_interaction.content)
        from world.items.models import ItemInstance

        self.assertFalse(ItemInstance.objects.filter(pk=stack.pk).exists())

    def test_scene_cast_without_the_component_still_casts_without_the_price(self) -> None:
        cast, stack = self._priced_with_component(carried=1)
        self.assertIsNotNone(cast.outcome_interaction)
        self.assertNotIn("blood beads on the needle", cast.outcome_interaction.content)
        stack.refresh_from_db()
        self.assertEqual(stack.quantity, 1)

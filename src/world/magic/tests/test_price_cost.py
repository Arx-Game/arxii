"""A price costs something real: a consumed component and an inflicted condition (#4099).

The owner's rulings (ADR-4099): a price may consume a carried item on every cast that
pays it and may inflict a condition on the caster. A cast whose caster lacks the
component still happens, just without the price - no power, no clause, no condition,
nothing spent. ``price_paid_for_cast`` is the one place that decides; everything else
follows it.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.models import ItemInstance
from world.magic.constants import RestrictionKind
from world.magic.factories import (
    CharacterTechniqueFactory,
    PriceFactory,
    RestrictionFactory,
    TechniqueFactory,
)
from world.magic.models import PriceComponentRequirement
from world.magic.services import use_technique
from world.magic.services.technique_personalization import (
    paid_price_snippet,
    price_paid_for_cast,
)
from world.magic.tests.price_cost_helpers import carry, make_caster


def capture_power():
    """A resolve_fn recording the power it was handed."""
    captured: dict[str, int] = {}

    def resolve_fn(*, power: int, ledger: object = None, extra_modifiers: int = 0):
        captured["power"] = power
        return SimpleNamespace(check_result=None)

    return captured, resolve_fn


class PriceCostFixture(TestCase):
    """A technique held with a price that consumes 2 bone needles and inflicts Weary."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.technique = TechniqueFactory(intensity=5, control=10, anima_cost=2)
        cls.needle = ItemTemplateFactory(name="Bone needle")
        cls.weary = ConditionTemplateFactory(name="Weary from the price")
        cls.price = PriceFactory(
            power_bonus=7, cast_narration="blood beads on the needle", inflicted_condition=cls.weary
        )
        PriceComponentRequirement.objects.create(
            restriction=cls.price, item_template=cls.needle, quantity=2
        )

    def setUp(self) -> None:
        self.character, self.sheet = make_caster()
        CharacterTechniqueFactory(character=self.sheet, technique=self.technique, price=self.price)
        self.character.techniques.invalidate()

    def weary_on_caster(self) -> bool:
        return ConditionInstance.objects.filter(
            target=self.character, condition=self.weary
        ).exists()


class PricePaidForCastTests(PriceCostFixture):
    def test_carrying_the_component_pays_with_its_allocation(self) -> None:
        stack = carry(self.character, self.needle, quantity=3)
        payment = price_paid_for_cast(self.character, self.technique)
        self.assertIsNotNone(payment)
        self.assertEqual(payment.price, self.price)
        self.assertEqual(payment.allocations, ((stack, 2),))

    def test_without_the_component_the_price_is_not_paid(self) -> None:
        self.assertIsNone(price_paid_for_cast(self.character, self.technique))

    def test_too_few_components_is_not_paid(self) -> None:
        carry(self.character, self.needle, quantity=1)
        self.assertIsNone(price_paid_for_cast(self.character, self.technique))

    def test_an_item_owned_but_not_carried_does_not_pay(self) -> None:
        ItemInstanceFactory(template=self.needle, quantity=5, holder_character_sheet=self.sheet)
        self.character.carried_items.invalidate()
        self.assertIsNone(price_paid_for_cast(self.character, self.technique))

    def test_a_condition_only_price_always_pays(self) -> None:
        technique = TechniqueFactory()
        price = PriceFactory(inflicted_condition=self.weary)
        CharacterTechniqueFactory(character=self.sheet, technique=technique, price=price)
        self.character.techniques.invalidate()
        payment = price_paid_for_cast(self.character, technique)
        self.assertIsNotNone(payment)
        self.assertEqual(payment.allocations, ())

    def test_an_unpriced_hold_pays_nothing(self) -> None:
        technique = TechniqueFactory()
        CharacterTechniqueFactory(character=self.sheet, technique=technique)
        self.character.techniques.invalidate()
        self.assertIsNone(price_paid_for_cast(self.character, technique))

    def test_snippet_is_only_for_a_paid_price(self) -> None:
        self.assertEqual(paid_price_snippet(self.price), "blood beads on the needle")
        self.assertIsNone(paid_price_snippet(None))
        self.assertEqual(paid_price_snippet(PriceFactory(name="Ash", cast_narration="")), "Ash")


class UseTechniquePaysThePriceTests(PriceCostFixture):
    def test_paid_cast_consumes_gains_power_narrates_and_inflicts(self) -> None:
        unpaid, unpaid_resolve = capture_power()
        use_technique(character=self.character, technique=self.technique, resolve_fn=unpaid_resolve)

        stack = carry(self.character, self.needle, quantity=3)
        paid, paid_resolve = capture_power()
        result = use_technique(
            character=self.character, technique=self.technique, resolve_fn=paid_resolve
        )

        self.assertTrue(result.confirmed)
        self.assertEqual(result.price_paid, self.price)
        self.assertEqual(paid["power"] - unpaid["power"], 7)
        stack.refresh_from_db()
        self.assertEqual(stack.quantity, 1)
        self.assertTrue(self.weary_on_caster())
        self.assertEqual(paid_price_snippet(result.price_paid), "blood beads on the needle")

    def test_last_components_are_used_up_leaving_no_ghost(self) -> None:
        from evennia.objects.models import ObjectDB

        stack = carry(self.character, self.needle, quantity=2)
        game_object_pk = stack.game_object_id
        use_technique(character=self.character, technique=self.technique, resolve_fn=MagicMock())
        self.assertFalse(ItemInstance.objects.filter(pk=stack.pk).exists())
        # The item's game object goes with it, never left in inventory as a ghost.
        self.assertFalse(ObjectDB.objects.filter(pk=game_object_pk).exists())
        self.assertIsNone(price_paid_for_cast(self.character, self.technique))

    def test_cast_without_the_component_still_happens_without_the_price(self) -> None:
        stack = carry(self.character, self.needle, quantity=1)
        resolve_fn = MagicMock(return_value=SimpleNamespace(check_result=None))
        result = use_technique(
            character=self.character, technique=self.technique, resolve_fn=resolve_fn
        )

        self.assertTrue(result.confirmed)
        resolve_fn.assert_called_once()
        self.assertIsNone(result.price_paid)
        self.assertIsNone(paid_price_snippet(result.price_paid))
        stack.refresh_from_db()
        self.assertEqual(stack.quantity, 1)
        self.assertFalse(self.weary_on_caster())

    def test_unpaid_cast_gets_no_price_power(self) -> None:
        captured, resolve_fn = capture_power()
        use_technique(character=self.character, technique=self.technique, resolve_fn=resolve_fn)
        bare_character, bare_sheet = make_caster()
        CharacterTechniqueFactory(character=bare_sheet, technique=self.technique)
        bare_character.techniques.invalidate()
        bare, bare_resolve = capture_power()
        use_technique(character=bare_character, technique=self.technique, resolve_fn=bare_resolve)
        self.assertEqual(captured["power"], bare["power"])

    def test_condition_only_price_inflicts_on_every_cast(self) -> None:
        technique = TechniqueFactory(intensity=5, control=10, anima_cost=1)
        price = PriceFactory(inflicted_condition=self.weary)
        CharacterTechniqueFactory(character=self.sheet, technique=technique, price=price)
        self.character.techniques.invalidate()
        result = use_technique(
            character=self.character, technique=technique, resolve_fn=MagicMock()
        )
        self.assertEqual(result.price_paid, price)
        self.assertTrue(self.weary_on_caster())


class RefusedCastSpendsNothingTests(PriceCostFixture):
    def test_unconfirmed_soulfray_refusal_consumes_nothing(self) -> None:
        stack = carry(self.character, self.needle, quantity=2)
        resolve_fn = MagicMock()
        with patch(
            "world.magic.services.techniques.get_soulfray_warning",
            return_value=SimpleNamespace(stage_name="Fraying"),
        ):
            result = use_technique(
                character=self.character,
                technique=self.technique,
                resolve_fn=resolve_fn,
                confirm_soulfray_risk=False,
            )
        self.assertFalse(result.confirmed)
        resolve_fn.assert_not_called()
        stack.refresh_from_db()
        self.assertEqual(stack.quantity, 2)
        self.assertFalse(self.weary_on_caster())

    def test_cancelled_precast_consumes_nothing(self) -> None:
        stack = carry(self.character, self.needle, quantity=2)
        resolve_fn = MagicMock()
        with patch("world.magic.services.techniques._prepare_technique_cast", return_value=None):
            result = use_technique(
                character=self.character, technique=self.technique, resolve_fn=resolve_fn
            )
        self.assertFalse(result.confirmed)
        resolve_fn.assert_not_called()
        stack.refresh_from_db()
        self.assertEqual(stack.quantity, 2)
        self.assertFalse(self.weary_on_caster())

    def test_a_cast_that_fails_while_resolving_consumes_nothing(self) -> None:
        stack = carry(self.character, self.needle, quantity=2)

        def exploding_resolve(**_kwargs):
            raise RuntimeError

        with self.assertRaises(RuntimeError):
            use_technique(
                character=self.character, technique=self.technique, resolve_fn=exploding_resolve
            )
        stack.refresh_from_db()
        self.assertEqual(stack.quantity, 2)
        self.assertFalse(self.weary_on_caster())


class PriceCostValidationTests(TestCase):
    """A component or condition is only allowed on a PRICE restriction."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.condition = ConditionTemplateFactory()
        cls.template = ItemTemplateFactory()

    def test_design_restriction_cannot_inflict_a_condition(self) -> None:
        design = RestrictionFactory(kind=RestrictionKind.DESIGN)
        design.inflicted_condition = self.condition
        with self.assertRaises(ValidationError) as ctx:
            design.full_clean()
        self.assertIn("inflicted_condition", ctx.exception.message_dict)

    def test_db_refuses_a_condition_on_a_design_restriction(self) -> None:
        design = RestrictionFactory(kind=RestrictionKind.DESIGN)
        design.inflicted_condition = self.condition
        with self.assertRaises(IntegrityError), transaction.atomic():
            design.save(update_fields=["inflicted_condition"])

    def test_design_restriction_cannot_consume_a_component(self) -> None:
        design = RestrictionFactory(kind=RestrictionKind.DESIGN)
        row = PriceComponentRequirement(restriction=design, item_template=self.template)
        with self.assertRaises(ValidationError) as ctx:
            row.full_clean()
        self.assertIn("restriction", ctx.exception.message_dict)

    def test_price_cannot_become_design_while_it_consumes_a_component(self) -> None:
        price = PriceFactory()
        PriceComponentRequirement.objects.create(restriction=price, item_template=self.template)
        price.kind = RestrictionKind.DESIGN
        price.creation_point_cost = None
        with self.assertRaises(ValidationError) as ctx:
            price.full_clean()
        self.assertIn("kind", ctx.exception.message_dict)

    def test_price_may_carry_both(self) -> None:
        price = PriceFactory(inflicted_condition=self.condition)
        row = PriceComponentRequirement(restriction=price, item_template=self.template)
        row.full_clean()
        price.full_clean()


class RestrictionAdminPriceCostTests(TestCase):
    """Staff author a price's cost on the Restriction admin; a DESIGN row refuses it."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia.accounts.models import AccountDB

        cls.staff = AccountDB.objects.create_superuser(
            "pricecostadmin", "pricecostadmin@example.com", "pw-123456"
        )
        cls.condition = ConditionTemplateFactory()
        cls.template = ItemTemplateFactory()

    def _request(self):
        from django.test import RequestFactory

        request = RequestFactory().post("/")
        request.user = self.staff
        return request

    def _model_admin(self):
        from django.contrib import admin

        from world.magic.models import Restriction

        return admin.site._registry[Restriction]

    def _inline_formset(self, restriction):
        from world.magic.admin import PriceComponentRequirementInline

        model_admin = self._model_admin()
        inline = next(
            i
            for i in model_admin.get_inline_instances(self._request(), restriction)
            if isinstance(i, PriceComponentRequirementInline)
        )
        formset_class = inline.get_formset(self._request(), restriction)
        prefix = formset_class.get_default_prefix()
        data = {
            f"{prefix}-TOTAL_FORMS": "1",
            f"{prefix}-INITIAL_FORMS": "0",
            f"{prefix}-MIN_NUM_FORMS": "0",
            f"{prefix}-MAX_NUM_FORMS": "1000",
            f"{prefix}-0-item_template": str(self.template.pk),
            f"{prefix}-0-quantity": "1",
        }
        return formset_class(data=data, instance=restriction, prefix=prefix)

    def _change_form(self, restriction, **overrides):
        from django.forms.models import model_to_dict

        form_class = self._model_admin().get_form(self._request(), restriction)
        data = {
            key: value
            for key, value in model_to_dict(restriction).items()
            if value is not None and key in form_class.base_fields
        }
        data["allowed_effect_types"] = []
        data.update(overrides)
        return form_class(data=data, instance=restriction)

    def test_admin_refuses_a_component_on_a_design_restriction(self) -> None:
        formset = self._inline_formset(RestrictionFactory(kind=RestrictionKind.DESIGN))
        self.assertFalse(formset.is_valid())
        self.assertIn("PRICE", str(formset.errors))

    def test_admin_accepts_a_component_on_a_price(self) -> None:
        formset = self._inline_formset(PriceFactory())
        self.assertTrue(formset.is_valid(), formset.errors)

    def test_admin_refuses_a_condition_on_a_design_restriction(self) -> None:
        design = RestrictionFactory(kind=RestrictionKind.DESIGN)
        form = self._change_form(design, inflicted_condition=self.condition.pk)
        self.assertFalse(form.is_valid())
        self.assertIn("inflicted_condition", form.errors)

    def test_admin_accepts_a_condition_on_a_price(self) -> None:
        price = PriceFactory()
        form = self._change_form(price, inflicted_condition=self.condition.pk)
        self.assertTrue(form.is_valid(), form.errors)

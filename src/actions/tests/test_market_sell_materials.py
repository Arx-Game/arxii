"""Tests for SellMaterialsAction (#2540 slice 2): the personal-sell action."""

from __future__ import annotations

from django.test import TestCase

from actions.definitions.market import SellMaterialsAction
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.currency.services import get_or_create_purse
from world.items.factories import MaterialBucketFactory, MaterialCategoryFactory
from world.items.gems.buckets import material_value
from world.items.market.services import MATERIAL_SALE_RATE_PCT


class SellMaterialsActionTests(TestCase):
    def _actor_with_bucket(self, value: int):
        room = ObjectDBFactory(db_key="Room", db_typeclass_path="typeclasses.rooms.Room")
        actor = CharacterFactory(db_key="SellerAlice", location=room)
        sheet = CharacterSheetFactory(character=actor)
        category = MaterialCategoryFactory(name="Cordwood")
        MaterialBucketFactory(character_sheet=sheet, material_category=category, value=value)
        return actor, sheet, category

    def test_sells_bucket_value_at_the_rate(self) -> None:
        actor, sheet, category = self._actor_with_bucket(1000)

        result = SellMaterialsAction().run(actor, material_category_id=category.pk, amount=1000)

        assert result.success is True
        coins = 1000 * MATERIAL_SALE_RATE_PCT // 100
        assert result.data["coins"] == coins
        assert material_value(sheet, category) == 0
        assert get_or_create_purse(sheet).balance == coins

    def test_partial_sale_leaves_the_remainder(self) -> None:
        actor, sheet, category = self._actor_with_bucket(1000)

        result = SellMaterialsAction().run(actor, material_category_id=category.pk, amount=300)

        assert result.success is True
        assert material_value(sheet, category) == 700

    def test_zero_amount_fails_cleanly(self) -> None:
        actor, _sheet, category = self._actor_with_bucket(1000)
        result = SellMaterialsAction().run(actor, material_category_id=category.pk, amount=0)
        assert result.success is False
        assert result.message == "Sell how much?"

    def test_garbage_amount_fails_cleanly(self) -> None:
        actor, _sheet, category = self._actor_with_bucket(1000)
        result = SellMaterialsAction().run(actor, material_category_id=category.pk, amount="lots")
        assert result.success is False
        assert result.message == "Sell how much?"

    def test_missing_amount_fails_cleanly(self) -> None:
        actor, _sheet, category = self._actor_with_bucket(1000)
        result = SellMaterialsAction().run(actor, material_category_id=category.pk)
        assert result.success is False
        assert result.message == "Sell how much?"

    def test_missing_category_fails_cleanly(self) -> None:
        actor, _sheet, _category = self._actor_with_bucket(1000)
        result = SellMaterialsAction().run(actor, amount=100)
        assert result.success is False
        assert result.message == "Sell what?"

    def test_insufficient_bucket_surfaces_the_placeholder_message(self) -> None:
        actor, sheet, category = self._actor_with_bucket(20)
        result = SellMaterialsAction().run(actor, material_category_id=category.pk, amount=50)
        assert result.success is False
        assert "don't have enough" in result.message
        assert material_value(sheet, category) == 20  # nothing moved

    def test_no_character_sheet_fails_cleanly(self) -> None:
        room = ObjectDBFactory(db_key="Room", db_typeclass_path="typeclasses.rooms.Room")
        actor = CharacterFactory(db_key="NoSheetAlice", location=room)
        result = SellMaterialsAction().run(actor, material_category_id=1, amount=10)
        assert result.success is False
        assert result.message == "You have no active character."

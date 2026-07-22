"""Tests for the SheetUpdateRequest model (#2628)."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.factories import (
    CharacterDistinctionFactory,
    DistinctionFactory,
    SheetUpdateRequestFactory,
)
from world.distinctions.types import (
    DistinctionOrigin,
    SheetUpdateRequestStatus,
    SheetUpdateRequestType,
)


class SheetUpdateRequestModelTests(TestCase):
    def test_add_request_requires_target_distinction(self):
        sheet = CharacterSheetFactory()
        req = SheetUpdateRequestFactory.build(
            character_sheet=sheet,
            request_type=SheetUpdateRequestType.DISTINCTION_ADD,
            target_distinction=None,
            justification="Test",
            xp_cost=10,
            origin=DistinctionOrigin.UNLOCK_PURCHASE,
        )
        with self.assertRaises(ValidationError):
            req.clean()

    def test_remove_request_requires_target_character_distinction(self):
        sheet = CharacterSheetFactory()
        req = SheetUpdateRequestFactory.build(
            character_sheet=sheet,
            request_type=SheetUpdateRequestType.DISTINCTION_REMOVE,
            target_distinction=None,
            target_character_distinction=None,
            justification="Test",
            xp_cost=0,
            origin=DistinctionOrigin.UNLOCK_PURCHASE,
        )
        with self.assertRaises(ValidationError):
            req.clean()

    def test_add_must_not_set_target_character_distinction(self):
        sheet = CharacterSheetFactory()
        cd = CharacterDistinctionFactory(character=sheet)
        req = SheetUpdateRequestFactory.build(
            character_sheet=sheet,
            request_type=SheetUpdateRequestType.DISTINCTION_ADD,
            target_distinction=cd.distinction,
            target_character_distinction=cd,
            justification="Test",
            xp_cost=10,
            origin=DistinctionOrigin.UNLOCK_PURCHASE,
        )
        with self.assertRaises(ValidationError):
            req.clean()

    def test_default_status_is_pending(self):
        req = SheetUpdateRequestFactory()
        assert req.status == SheetUpdateRequestStatus.PENDING

    def test_str_includes_type_and_cost(self):
        sheet = CharacterSheetFactory()
        dist = DistinctionFactory(cost_per_rank=5, max_rank=1)
        req = SheetUpdateRequestFactory(
            character_sheet=sheet,
            request_type=SheetUpdateRequestType.DISTINCTION_ADD,
            target_distinction=dist,
            xp_cost=5,
        )
        assert "Add" in str(req)
        assert "5" in str(req)

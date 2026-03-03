"""Tests for magic stage validation with cantrip selection."""

from django.test import TestCase

from world.character_creation.factories import CharacterDraftFactory
from world.character_creation.validators import compute_magic_errors
from world.magic.factories import CantripFactory, FacetFactory


class MagicStageValidationTest(TestCase):
    """Test compute_magic_errors with cantrip-based validation."""

    @classmethod
    def setUpTestData(cls):
        cls.innate_cantrip = CantripFactory(
            name="Danger Sense",
            requires_facet=False,
        )
        cls.manifested_cantrip = CantripFactory(
            name="Elemental Strike",
            requires_facet=True,
            facet_prompt="Choose your element",
        )
        fire = FacetFactory(name="Fire")
        ice = FacetFactory(name="Ice")
        cls.manifested_cantrip.allowed_facets.add(fire, ice)
        cls.fire = fire
        cls.unrelated_facet = FacetFactory(name="Wolf")

    def test_no_cantrip_selected_returns_error(self):
        draft = CharacterDraftFactory()
        errors = compute_magic_errors(draft)
        assert "Select a cantrip" in errors

    def test_innate_cantrip_selected_passes(self):
        draft = CharacterDraftFactory(
            draft_data={"selected_cantrip_id": self.innate_cantrip.id},
        )
        errors = compute_magic_errors(draft)
        assert errors == []

    def test_manifested_cantrip_without_facet_fails(self):
        draft = CharacterDraftFactory(
            draft_data={"selected_cantrip_id": self.manifested_cantrip.id},
        )
        errors = compute_magic_errors(draft)
        assert any(
            "element" in e.lower() or "facet" in e.lower() or "type" in e.lower() for e in errors
        )

    def test_manifested_cantrip_with_valid_facet_passes(self):
        draft = CharacterDraftFactory(
            draft_data={
                "selected_cantrip_id": self.manifested_cantrip.id,
                "selected_facet_id": self.fire.id,
            },
        )
        errors = compute_magic_errors(draft)
        assert errors == []

    def test_manifested_cantrip_with_invalid_facet_fails(self):
        draft = CharacterDraftFactory(
            draft_data={
                "selected_cantrip_id": self.manifested_cantrip.id,
                "selected_facet_id": self.unrelated_facet.id,
            },
        )
        errors = compute_magic_errors(draft)
        assert len(errors) > 0

    def test_inactive_cantrip_fails(self):
        inactive = CantripFactory(is_active=False)
        draft = CharacterDraftFactory(
            draft_data={"selected_cantrip_id": inactive.id},
        )
        errors = compute_magic_errors(draft)
        assert len(errors) > 0

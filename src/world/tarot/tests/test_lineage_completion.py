"""
Tests for tarot card integration with lineage completion.

Verifies that the none family path (no family at all, #3617's amnesiac
Upbringing) requires a tarot card selection to complete the lineage stage.
"""

from django.test import TestCase
from evennia.accounts.models import AccountDB

from world.character_creation.factories import OriginTemplateFactory, make_unknown_upbringing
from world.character_creation.models import Beginnings, CharacterDraft, StartingArea
from world.character_creation.validators import get_lineage_errors
from world.character_sheets.models import Gender
from world.realms.models import Realm
from world.roster.factories import FamilyKindFactory
from world.roster.models import Family
from world.species.models import Species
from world.tarot.constants import ArcanaType
from world.tarot.models import TarotCard


class LineageCompletionTests(TestCase):
    """Test get_lineage_errors() with tarot card requirements on the none path."""

    @classmethod
    def setUpTestData(cls):
        """Set up shared test data."""
        cls.account = AccountDB.objects.create(username="lineage_test_user")
        cls.realm = Realm.objects.create(
            name="Lineage Test Realm",
            description="Test realm for lineage tests",
        )
        cls.area = StartingArea.objects.create(
            name="Lineage Test Area",
            description="Test area",
            realm=cls.realm,
            access_level=StartingArea.AccessLevel.ALL,
        )
        cls.species = Species.objects.create(
            name="Lineage Test Species",
            description="Test species",
        )
        cls.gender, _ = Gender.objects.get_or_create(
            key="lineage_test_gender",
            defaults={"display_name": "Lineage Test Gender"},
        )

        # Beginnings whose Upbringing offers the claim-a-staff-family path.
        cls.claim_beginnings = Beginnings.objects.create(
            name="Lineage Claim Beginnings",
            description="Beginnings offering the claim family path",
            starting_area=cls.area,
            trust_required=0,
            is_active=True,
        )
        cls.claim_beginnings.allowed_species.add(cls.species)
        cls.claim_upbringing = OriginTemplateFactory(
            beginning=cls.claim_beginnings,
            allows_name_family=False,
            named_family_kind=None,
            allows_claim_family=True,
        )

        # Beginnings whose Upbringing is the amnesiac "Unknown" (none path, #3617).
        cls.unknown_beginnings = Beginnings.objects.create(
            name="Lineage Unknown Beginnings",
            description="Unknown origins beginnings",
            starting_area=cls.area,
            trust_required=0,
            is_active=True,
        )
        cls.unknown_beginnings.allowed_species.add(cls.species)
        cls.unknown_upbringing = make_unknown_upbringing(cls.unknown_beginnings)

        cls.tarot_card = TarotCard.objects.create(
            name="The Fool",
            arcana_type=ArcanaType.MAJOR,
            rank=0,
            latin_name="Stultus",
        )

    def test_family_selected_completes_lineage(self):
        """Lineage is complete when a claimed family is selected (unchanged behavior)."""
        kind = FamilyKindFactory()
        family = Family.objects.create(
            name="Lineage Test Family", kind=kind, origin_realm=self.realm
        )

        draft = CharacterDraft.objects.create(
            account=self.account,
            selected_area=self.area,
            selected_beginnings=self.claim_beginnings,
            selected_origin_template=self.claim_upbringing,
            selected_species=self.species,
            selected_gender=self.gender,
            family=family,
            draft_data={},
        )
        assert get_lineage_errors(draft) == []

    def test_none_path_without_tarot_card_incomplete(self):
        """None path (no family) without a tarot card -> lineage INCOMPLETE."""
        draft = CharacterDraft.objects.create(
            account=self.account,
            selected_area=self.area,
            selected_beginnings=self.unknown_beginnings,
            selected_origin_template=self.unknown_upbringing,
            selected_species=self.species,
            selected_gender=self.gender,
            draft_data={},
        )
        assert get_lineage_errors(draft) == ["Select a tarot card for your surname"]

    def test_none_path_with_tarot_card_complete(self):
        """None path (no family) with a tarot card -> lineage complete."""
        draft = CharacterDraft.objects.create(
            account=self.account,
            selected_area=self.area,
            selected_beginnings=self.unknown_beginnings,
            selected_origin_template=self.unknown_upbringing,
            selected_species=self.species,
            selected_gender=self.gender,
            draft_data={
                "tarot_card_name": self.tarot_card.name,
                "tarot_reversed": False,
            },
        )
        assert get_lineage_errors(draft) == []

    def test_none_path_with_reversed_tarot_card_complete(self):
        """A reversed tarot card also satisfies the requirement."""
        draft = CharacterDraft.objects.create(
            account=self.account,
            selected_area=self.area,
            selected_beginnings=self.unknown_beginnings,
            selected_origin_template=self.unknown_upbringing,
            selected_species=self.species,
            selected_gender=self.gender,
            draft_data={
                "tarot_card_name": self.tarot_card.name,
                "tarot_reversed": True,
            },
        )
        assert get_lineage_errors(draft) == []

    def test_no_upbringing_selected_incomplete(self):
        """No Upbringing selected -> lineage incomplete."""
        draft = CharacterDraft.objects.create(
            account=self.account,
            selected_area=self.area,
            draft_data={},
        )
        assert get_lineage_errors(draft) == ["Choose your upbringing"]

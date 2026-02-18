"""
Tests for tarot card integration with lineage completion.

Verifies that familyless characters (orphans and unknown-origins) require
a tarot card selection to complete the lineage stage.
"""

from django.test import TestCase
from evennia.accounts.models import AccountDB

from world.character_creation.models import Beginnings, CharacterDraft, StartingArea
from world.character_sheets.models import Gender
from world.realms.models import Realm
from world.species.models import Species
from world.tarot.constants import ArcanaType
from world.tarot.models import TarotCard


class LineageCompletionTests(TestCase):
    """Test _is_lineage_complete() with tarot card requirements."""

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

        # Beginnings where family IS known (normal upbringing)
        cls.family_known_beginnings = Beginnings.objects.create(
            name="Lineage Normal Beginnings",
            description="Normal beginnings with family known",
            starting_area=cls.area,
            trust_required=0,
            is_active=True,
            family_known=True,
        )
        cls.family_known_beginnings.allowed_species.add(cls.species)

        # Beginnings where family is NOT known (e.g. Misbegotten/Sleeper)
        cls.family_unknown_beginnings = Beginnings.objects.create(
            name="Lineage Unknown Beginnings",
            description="Unknown origins beginnings",
            starting_area=cls.area,
            trust_required=0,
            is_active=True,
            family_known=False,
        )
        cls.family_unknown_beginnings.allowed_species.add(cls.species)

        cls.tarot_card = TarotCard.objects.create(
            name="The Fool",
            arcana_type=ArcanaType.MAJOR,
            rank=0,
            latin_name="Stultus",
        )

    def test_family_selected_completes_lineage(self):
        """Lineage is complete when a family is selected (unchanged behavior)."""
        from world.roster.models import Family

        family = Family.objects.create(name="Lineage Test Family", origin_realm=self.realm)

        draft = CharacterDraft.objects.create(
            account=self.account,
            selected_area=self.area,
            selected_beginnings=self.family_known_beginnings,
            selected_species=self.species,
            selected_gender=self.gender,
            family=family,
            draft_data={},
        )
        assert draft._is_lineage_complete() is True

    def test_orphan_without_tarot_card_incomplete(self):
        """Orphan without tarot card -> lineage INCOMPLETE."""
        draft = CharacterDraft.objects.create(
            account=self.account,
            selected_area=self.area,
            selected_beginnings=self.family_known_beginnings,
            selected_species=self.species,
            selected_gender=self.gender,
            draft_data={"lineage_is_orphan": True},
        )
        assert draft._is_lineage_complete() is False

    def test_orphan_with_tarot_card_complete(self):
        """Orphan with tarot card -> lineage complete."""
        draft = CharacterDraft.objects.create(
            account=self.account,
            selected_area=self.area,
            selected_beginnings=self.family_known_beginnings,
            selected_species=self.species,
            selected_gender=self.gender,
            draft_data={
                "lineage_is_orphan": True,
                "tarot_card_name": self.tarot_card.name,
                "tarot_reversed": False,
            },
        )
        assert draft._is_lineage_complete() is True

    def test_unknown_origins_without_tarot_card_incomplete(self):
        """Unknown origins (family_known=False) without tarot card -> lineage INCOMPLETE."""
        draft = CharacterDraft.objects.create(
            account=self.account,
            selected_area=self.area,
            selected_beginnings=self.family_unknown_beginnings,
            selected_species=self.species,
            selected_gender=self.gender,
            draft_data={},
        )
        assert draft._is_lineage_complete() is False

    def test_unknown_origins_with_tarot_card_complete(self):
        """Unknown origins (family_known=False) with tarot card -> lineage complete."""
        draft = CharacterDraft.objects.create(
            account=self.account,
            selected_area=self.area,
            selected_beginnings=self.family_unknown_beginnings,
            selected_species=self.species,
            selected_gender=self.gender,
            draft_data={
                "tarot_card_name": self.tarot_card.name,
                "tarot_reversed": True,
            },
        )
        assert draft._is_lineage_complete() is True

    def test_no_beginnings_no_family_incomplete(self):
        """No beginnings and no family -> lineage incomplete."""
        draft = CharacterDraft.objects.create(
            account=self.account,
            selected_area=self.area,
            draft_data={},
        )
        assert draft._is_lineage_complete() is False

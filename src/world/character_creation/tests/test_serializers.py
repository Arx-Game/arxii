"""
Tests for character creation serializers.
"""

from unittest.mock import Mock

from django.test import TestCase
from evennia.accounts.models import AccountDB

from evennia_extensions.factories import AccountFactory
from world.character_creation.factories import CharacterDraftFactory
from world.character_creation.models import CharacterDraft, StartingArea
from world.character_creation.serializers import CharacterDraftSerializer
from world.forms.factories import BuildFactory, HeightBandFactory
from world.realms.models import Realm


class CharacterDraftSerializerHeightValidationTest(TestCase):
    """Test height_inches validation in CharacterDraftSerializer."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        cls.height_band = HeightBandFactory(
            name="test_avg", min_inches=68, max_inches=71, is_cg_selectable=True
        )
        cls.build = BuildFactory(name="test_ath", is_cg_selectable=True)

    def test_height_inches_within_band_valid(self):
        """Test height_inches within band range is valid."""
        draft = CharacterDraftFactory(account=self.account, height_band=self.height_band)
        request = Mock()
        request.user = self.account
        serializer = CharacterDraftSerializer(
            draft,
            data={"height_inches": 70},
            partial=True,
            context={"request": request},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_height_inches_at_band_minimum_valid(self):
        """Test height_inches at band minimum is valid."""
        draft = CharacterDraftFactory(account=self.account, height_band=self.height_band)
        request = Mock()
        request.user = self.account
        serializer = CharacterDraftSerializer(
            draft,
            data={"height_inches": 68},  # Exactly at min_inches
            partial=True,
            context={"request": request},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_height_inches_at_band_maximum_valid(self):
        """Test height_inches at band maximum is valid."""
        draft = CharacterDraftFactory(account=self.account, height_band=self.height_band)
        request = Mock()
        request.user = self.account
        serializer = CharacterDraftSerializer(
            draft,
            data={"height_inches": 71},  # Exactly at max_inches
            partial=True,
            context={"request": request},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_height_inches_above_band_invalid(self):
        """Test height_inches above band maximum is invalid."""
        draft = CharacterDraftFactory(account=self.account, height_band=self.height_band)
        request = Mock()
        request.user = self.account
        serializer = CharacterDraftSerializer(
            draft,
            data={"height_inches": 80},  # Outside band range 68-71
            partial=True,
            context={"request": request},
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("height_inches", serializer.errors)

    def test_height_inches_below_band_invalid(self):
        """Test height_inches below band minimum is invalid."""
        draft = CharacterDraftFactory(account=self.account, height_band=self.height_band)
        request = Mock()
        request.user = self.account
        serializer = CharacterDraftSerializer(
            draft,
            data={"height_inches": 60},  # Below band range 68-71
            partial=True,
            context={"request": request},
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("height_inches", serializer.errors)

    def test_height_inches_without_band_valid(self):
        """Test height_inches without height_band set is valid (no validation)."""
        draft = CharacterDraftFactory(account=self.account, height_band=None)
        request = Mock()
        request.user = self.account
        serializer = CharacterDraftSerializer(
            draft,
            data={"height_inches": 80},  # Any value
            partial=True,
            context={"request": request},
        )
        # Without a height_band, no validation is performed on height_inches
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_height_inches_with_band_in_same_request_valid(self):
        """Test height_inches valid when height_band is set in the same request."""
        draft = CharacterDraftFactory(account=self.account, height_band=None)
        request = Mock()
        request.user = self.account
        serializer = CharacterDraftSerializer(
            draft,
            data={"height_band_id": self.height_band.id, "height_inches": 70},
            partial=True,
            context={"request": request},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)


class CharacterDraftSerializerValidationTests(TestCase):
    """Test stat validation in CharacterDraftSerializer."""

    def setUp(self):
        """Set up test data."""
        self.account = AccountDB.objects.create(username="testuser")

        # Create starting area with realm
        self.realm = Realm.objects.create(
            name="Test Realm",
            description="Test realm",
        )
        self.area = StartingArea.objects.create(
            name="Test Area",
            description="Test area",
            realm=self.realm,
            access_level=StartingArea.AccessLevel.ALL,
        )

        self.draft = CharacterDraft.objects.create(
            account=self.account,
            selected_area=self.area,
        )

    def test_validate_draft_data_invalid_stat_name(self):
        """Test validation fails with invalid stat name."""
        data = {
            "draft_data": {
                "stats": {
                    "invalid_stat": 20,
                }
            }
        }

        serializer = CharacterDraftSerializer(instance=self.draft, data=data, partial=True)
        assert not serializer.is_valid()
        assert "draft_data" in serializer.errors

    def test_validate_draft_data_non_integer_value(self):
        """Test validation fails with non-integer stat value."""
        data = {
            "draft_data": {
                "stats": {
                    "strength": 20.5,
                }
            }
        }

        serializer = CharacterDraftSerializer(instance=self.draft, data=data, partial=True)
        assert not serializer.is_valid()
        assert "draft_data" in serializer.errors

    def test_validate_draft_data_not_multiple_of_10(self):
        """Test validation fails when stat not multiple of 10."""
        data = {
            "draft_data": {
                "stats": {
                    "strength": 25,
                }
            }
        }

        serializer = CharacterDraftSerializer(instance=self.draft, data=data, partial=True)
        assert not serializer.is_valid()
        assert "draft_data" in serializer.errors

    def test_validate_draft_data_out_of_range(self):
        """Test validation fails with out of range values."""
        # Below minimum
        data = {
            "draft_data": {
                "stats": {
                    "strength": 5,
                }
            }
        }

        serializer = CharacterDraftSerializer(instance=self.draft, data=data, partial=True)
        assert not serializer.is_valid()
        assert "draft_data" in serializer.errors

        # Above maximum
        data = {
            "draft_data": {
                "stats": {
                    "strength": 60,
                }
            }
        }

        serializer = CharacterDraftSerializer(instance=self.draft, data=data, partial=True)
        assert not serializer.is_valid()
        assert "draft_data" in serializer.errors

    def test_validate_draft_data_valid_stats(self):
        """Test validation passes with valid stats."""
        data = {
            "draft_data": {
                "stats": {
                    "strength": 30,
                    "agility": 20,
                }
            }
        }

        serializer = CharacterDraftSerializer(instance=self.draft, data=data, partial=True)
        assert serializer.is_valid(), serializer.errors

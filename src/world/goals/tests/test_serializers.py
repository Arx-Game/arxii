"""Tests for goals serializers."""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.goals.factories import (
    CharacterGoalFactory,
    GoalDomainFactory,
    GoalJournalFactory,
    GoalRevisionFactory,
)
from world.goals.serializers import (
    MAX_GOAL_POINTS,
    CharacterGoalSerializer,
    CharacterGoalUpdateSerializer,
    GoalDomainSerializer,
    GoalJournalCreateSerializer,
    GoalJournalSerializer,
    GoalRevisionSerializer,
)


class GoalDomainSerializerTests(TestCase):
    """Tests for GoalDomainSerializer (ModifierType with category='goal')."""

    def test_serializes_all_fields(self):
        """Serializer includes all expected fields."""
        domain = GoalDomainFactory(
            name="TestSerializerDomain",
            description="Social status and rank",
            display_order=1,
        )
        serializer = GoalDomainSerializer(domain)
        data = serializer.data

        assert data["id"] == domain.id
        assert data["name"] == "TestSerializerDomain"
        assert data["description"] == "Social status and rank"
        assert data["display_order"] == 1
        assert data["is_optional"] is False

    def test_is_optional_for_drives_domain(self):
        """Serializer correctly identifies optional domains."""
        # "Drives" is in OPTIONAL_GOAL_DOMAINS
        domain = GoalDomainFactory(name="Drives")
        serializer = GoalDomainSerializer(domain)
        data = serializer.data

        assert data["is_optional"] is True


class CharacterGoalSerializerTests(TestCase):
    """Tests for CharacterGoalSerializer."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.character = CharacterFactory()
        cls.domain = GoalDomainFactory(name="Wealth")

    def test_serializes_goal_with_domain_info(self):
        """Serializer includes domain name."""
        goal = CharacterGoalFactory(
            character=self.character,
            domain=self.domain,
            points=15,
            notes="Get rich",
        )
        serializer = CharacterGoalSerializer(goal)
        data = serializer.data

        assert data["domain_name"] == "Wealth"
        assert data["points"] == 15
        assert data["notes"] == "Get rich"


class CharacterGoalUpdateSerializerTests(TestCase):
    """Tests for CharacterGoalUpdateSerializer."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.standing = GoalDomainFactory(name="Standing")
        cls.wealth = GoalDomainFactory(name="Wealth")
        cls.knowledge = GoalDomainFactory(name="Knowledge")

    def test_valid_goals_within_limit(self):
        """Validates goals that don't exceed point limit."""
        data = {
            "goals": [
                {"domain": self.standing.id, "points": 15},
                {"domain": self.wealth.id, "points": 10},
                {"domain": self.knowledge.id, "points": 5},
            ]
        }
        serializer = CharacterGoalUpdateSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
        assert serializer.validated_data["goals"][0]["points"] == 15

    def test_rejects_goals_exceeding_limit(self):
        """Rejects goals that exceed MAX_GOAL_POINTS."""
        data = {
            "goals": [
                {"domain": self.standing.id, "points": 20},
                {"domain": self.wealth.id, "points": 15},
            ]
        }
        serializer = CharacterGoalUpdateSerializer(data=data)
        assert not serializer.is_valid()
        assert "goals" in serializer.errors
        assert f"exceeds maximum of {MAX_GOAL_POINTS}" in str(serializer.errors["goals"])

    def test_rejects_invalid_domain_id(self):
        """Rejects goals with invalid domain IDs."""
        data = {
            "goals": [
                {"domain": 99999, "points": 10},
            ]
        }
        serializer = CharacterGoalUpdateSerializer(data=data)
        assert not serializer.is_valid()
        # DRF's PrimaryKeyRelatedField gives a standard error for invalid PKs
        assert "goals" in serializer.errors

    def test_rejects_missing_domain(self):
        """Rejects goals without domain."""
        data = {
            "goals": [
                {"points": 10},
            ]
        }
        serializer = CharacterGoalUpdateSerializer(data=data)
        assert not serializer.is_valid()
        assert "goals" in serializer.errors

    def test_rejects_negative_points(self):
        """Rejects goals with negative points."""
        data = {
            "goals": [
                {"domain": self.standing.id, "points": -5},
            ]
        }
        serializer = CharacterGoalUpdateSerializer(data=data)
        assert not serializer.is_valid()
        assert "goals" in serializer.errors

    def test_allows_zero_points(self):
        """Allows goals with zero points."""
        data = {
            "goals": [
                {"domain": self.standing.id, "points": 0},
            ]
        }
        serializer = CharacterGoalUpdateSerializer(data=data)
        assert serializer.is_valid()

    def test_allows_notes_field(self):
        """Allows optional notes field."""
        data = {
            "goals": [
                {"domain": self.standing.id, "points": 10, "notes": "Become Count"},
            ]
        }
        serializer = CharacterGoalUpdateSerializer(data=data)
        assert serializer.is_valid()
        assert serializer.validated_data["goals"][0]["notes"] == "Become Count"

    def test_exact_max_points_allowed(self):
        """Allows goals that exactly equal MAX_GOAL_POINTS."""
        data = {
            "goals": [
                {"domain": self.standing.id, "points": MAX_GOAL_POINTS},
            ]
        }
        serializer = CharacterGoalUpdateSerializer(data=data)
        assert serializer.is_valid()

    def test_rejects_duplicate_domains(self):
        """Rejects goals with duplicate domain IDs."""
        data = {
            "goals": [
                {"domain": self.standing.id, "points": 10},
                {"domain": self.standing.id, "points": 5},
            ]
        }
        serializer = CharacterGoalUpdateSerializer(data=data)
        assert not serializer.is_valid()
        assert "Duplicate domains" in str(serializer.errors["goals"])


class GoalJournalSerializerTests(TestCase):
    """Tests for GoalJournalSerializer."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.character = CharacterFactory()
        cls.domain = GoalDomainFactory(name="Bonds")

    def test_serializes_journal_with_domain_info(self):
        """Serializer includes domain name."""
        journal = GoalJournalFactory(
            character=self.character,
            domain=self.domain,
            title="Family Ties",
            xp_awarded=1,
        )
        serializer = GoalJournalSerializer(journal)
        data = serializer.data

        assert data["domain_name"] == "Bonds"
        assert data["title"] == "Family Ties"
        assert data["xp_awarded"] == 1

    def test_serializes_journal_without_domain(self):
        """Serializer handles journals without a domain."""
        journal = GoalJournalFactory(
            character=self.character,
            domain=None,
            title="General Musings",
        )
        serializer = GoalJournalSerializer(journal)
        data = serializer.data

        assert data["domain"] is None
        assert data["domain_name"] is None


class GoalJournalCreateSerializerTests(TestCase):
    """Tests for GoalJournalCreateSerializer."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.character = CharacterFactory()
        cls.domain = GoalDomainFactory(name="Mastery")

    def test_creates_journal_with_valid_data(self):
        """Creates journal with valid data."""
        data = {
            "domain": self.domain.id,
            "title": "Skill Progress",
            "content": "Today I practiced...",
            "is_public": False,
        }
        serializer = GoalJournalCreateSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

        journal = serializer.save(character=self.character)
        assert journal.domain == self.domain
        assert journal.title == "Skill Progress"
        assert journal.xp_awarded == 1  # Default XP

    def test_creates_journal_without_domain(self):
        """Creates journal without specifying domain."""
        data = {
            "title": "General Thoughts",
            "content": "Some content here...",
            "is_public": True,
        }
        serializer = GoalJournalCreateSerializer(data=data)
        assert serializer.is_valid()

        journal = serializer.save(character=self.character)
        assert journal.domain is None
        assert journal.is_public is True

    def test_rejects_invalid_domain_id(self):
        """Rejects journal with invalid domain ID."""
        data = {
            "domain": 99999,
            "title": "Test",
            "content": "Content",
        }
        serializer = GoalJournalCreateSerializer(data=data)
        assert not serializer.is_valid()
        assert "domain" in serializer.errors

    def test_awards_xp_on_creation(self):
        """Journal creation awards XP."""
        data = {
            "title": "My Journal",
            "content": "Some reflections",
        }
        serializer = GoalJournalCreateSerializer(data=data)
        serializer.is_valid()
        journal = serializer.save(character=self.character)

        assert journal.xp_awarded == 1


class GoalRevisionSerializerTests(TestCase):
    """Tests for GoalRevisionSerializer."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.character = CharacterFactory()

    def test_serializes_revision_with_can_revise(self):
        """Serializer includes computed can_revise field."""
        revision = GoalRevisionFactory(character=self.character)
        serializer = GoalRevisionSerializer(revision)
        data = serializer.data

        assert "last_revised_at" in data
        assert "can_revise" in data
        # Newly created revision should not be revisable
        assert data["can_revise"] is False

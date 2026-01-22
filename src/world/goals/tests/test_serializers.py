"""Tests for goals serializers."""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.goals.factories import (
    CharacterGoalFactory,
    GoalDomainFactory,
    GoalJournalFactory,
    GoalRevisionFactory,
)
from world.goals.models import GoalDomain
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
    """Tests for GoalDomainSerializer."""

    def test_serializes_all_fields(self):
        """Serializer includes all expected fields."""
        domain = GoalDomain.objects.create(
            name="TestSerializerDomain",
            slug="test-serializer-domain",
            description="Social status and rank",
            display_order=1,
            is_optional=False,
        )
        serializer = GoalDomainSerializer(domain)
        data = serializer.data

        assert data["id"] == domain.id
        assert data["name"] == "TestSerializerDomain"
        assert data["slug"] == "test-serializer-domain"
        assert data["description"] == "Social status and rank"
        assert data["display_order"] == 1
        assert data["is_optional"] is False


class CharacterGoalSerializerTests(TestCase):
    """Tests for CharacterGoalSerializer."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.character = CharacterFactory()
        cls.domain = GoalDomainFactory(name="Wealth", slug="wealth")

    def test_serializes_goal_with_domain_info(self):
        """Serializer includes domain name and slug."""
        goal = CharacterGoalFactory(
            character=self.character,
            domain=self.domain,
            points=15,
            notes="Get rich",
        )
        serializer = CharacterGoalSerializer(goal)
        data = serializer.data

        assert data["domain_name"] == "Wealth"
        assert data["domain_slug"] == "wealth"
        assert data["points"] == 15
        assert data["notes"] == "Get rich"


class CharacterGoalUpdateSerializerTests(TestCase):
    """Tests for CharacterGoalUpdateSerializer."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.standing = GoalDomainFactory(slug="standing")
        cls.wealth = GoalDomainFactory(slug="wealth")
        cls.knowledge = GoalDomainFactory(slug="knowledge")

    def test_valid_goals_within_limit(self):
        """Validates goals that don't exceed point limit."""
        data = {
            "goals": [
                {"domain_slug": "standing", "points": 15},
                {"domain_slug": "wealth", "points": 10},
                {"domain_slug": "knowledge", "points": 5},
            ]
        }
        serializer = CharacterGoalUpdateSerializer(data=data)
        assert serializer.is_valid()
        assert serializer.validated_data["goals"][0]["points"] == 15

    def test_rejects_goals_exceeding_limit(self):
        """Rejects goals that exceed MAX_GOAL_POINTS."""
        data = {
            "goals": [
                {"domain_slug": "standing", "points": 20},
                {"domain_slug": "wealth", "points": 15},
            ]
        }
        serializer = CharacterGoalUpdateSerializer(data=data)
        assert not serializer.is_valid()
        assert "goals" in serializer.errors
        assert f"exceeds maximum of {MAX_GOAL_POINTS}" in str(serializer.errors["goals"])

    def test_rejects_invalid_domain_slug(self):
        """Rejects goals with invalid domain slugs."""
        data = {
            "goals": [
                {"domain_slug": "nonexistent", "points": 10},
            ]
        }
        serializer = CharacterGoalUpdateSerializer(data=data)
        assert not serializer.is_valid()
        assert "Invalid domain slug" in str(serializer.errors["goals"])

    def test_rejects_missing_domain_slug(self):
        """Rejects goals without domain_slug."""
        data = {
            "goals": [
                {"points": 10},
            ]
        }
        serializer = CharacterGoalUpdateSerializer(data=data)
        assert not serializer.is_valid()
        assert "must have a domain_slug" in str(serializer.errors["goals"])

    def test_rejects_negative_points(self):
        """Rejects goals with negative points."""
        data = {
            "goals": [
                {"domain_slug": "standing", "points": -5},
            ]
        }
        serializer = CharacterGoalUpdateSerializer(data=data)
        assert not serializer.is_valid()
        assert "cannot be negative" in str(serializer.errors["goals"])

    def test_allows_zero_points(self):
        """Allows goals with zero points."""
        data = {
            "goals": [
                {"domain_slug": "standing", "points": 0},
            ]
        }
        serializer = CharacterGoalUpdateSerializer(data=data)
        assert serializer.is_valid()

    def test_allows_notes_field(self):
        """Allows optional notes field."""
        data = {
            "goals": [
                {"domain_slug": "standing", "points": 10, "notes": "Become Count"},
            ]
        }
        serializer = CharacterGoalUpdateSerializer(data=data)
        assert serializer.is_valid()
        assert serializer.validated_data["goals"][0]["notes"] == "Become Count"

    def test_exact_max_points_allowed(self):
        """Allows goals that exactly equal MAX_GOAL_POINTS."""
        data = {
            "goals": [
                {"domain_slug": "standing", "points": MAX_GOAL_POINTS},
            ]
        }
        serializer = CharacterGoalUpdateSerializer(data=data)
        assert serializer.is_valid()


class GoalJournalSerializerTests(TestCase):
    """Tests for GoalJournalSerializer."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.character = CharacterFactory()
        cls.domain = GoalDomainFactory(name="Bonds", slug="bonds")

    def test_serializes_journal_with_domain_info(self):
        """Serializer includes domain name and slug."""
        journal = GoalJournalFactory(
            character=self.character,
            domain=self.domain,
            title="Family Ties",
            xp_awarded=1,
        )
        serializer = GoalJournalSerializer(journal)
        data = serializer.data

        assert data["domain_name"] == "Bonds"
        assert data["domain_slug"] == "bonds"
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
        assert data["domain_slug"] is None


class GoalJournalCreateSerializerTests(TestCase):
    """Tests for GoalJournalCreateSerializer."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.character = CharacterFactory()
        cls.domain = GoalDomainFactory(slug="mastery")

    def test_creates_journal_with_valid_data(self):
        """Creates journal with valid data."""
        data = {
            "domain_slug": "mastery",
            "title": "Skill Progress",
            "content": "Today I practiced...",
            "is_public": False,
        }
        serializer = GoalJournalCreateSerializer(data=data)
        assert serializer.is_valid()

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

    def test_rejects_invalid_domain_slug(self):
        """Rejects journal with invalid domain slug."""
        data = {
            "domain_slug": "nonexistent",
            "title": "Test",
            "content": "Content",
        }
        serializer = GoalJournalCreateSerializer(data=data)
        assert not serializer.is_valid()
        assert "domain_slug" in serializer.errors

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

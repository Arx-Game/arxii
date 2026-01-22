"""Tests for goals models."""

from datetime import timedelta

from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import CharacterFactory
from world.goals.factories import (
    CharacterGoalFactory,
    GoalDomainFactory,
    GoalJournalFactory,
    GoalRevisionFactory,
)
from world.goals.models import CharacterGoal, GoalDomain, GoalJournal, GoalRevision


class GoalDomainModelTests(TestCase):
    """Tests for GoalDomain model."""

    def test_str_representation(self):
        """GoalDomain string representation shows name."""
        domain = GoalDomainFactory(name="TestDomain")
        assert str(domain) == "TestDomain"

    def test_slug_unique(self):
        """GoalDomain slugs must be unique."""
        # Create directly to avoid factory's get_or_create
        GoalDomain.objects.create(name="Test", slug="unique-slug-test")
        with self.assertRaises(IntegrityError):
            GoalDomain.objects.create(name="Test2", slug="unique-slug-test")

    def test_ordering_by_display_order(self):
        """GoalDomains are ordered by display_order."""
        # Use high display_order values to avoid collision with seeded data
        domain3 = GoalDomainFactory(display_order=103, slug="test-order-3")
        domain1 = GoalDomainFactory(display_order=101, slug="test-order-1")
        domain2 = GoalDomainFactory(display_order=102, slug="test-order-2")

        # Filter to only our test domains
        domains = list(GoalDomain.objects.filter(slug__startswith="test-order-"))
        assert domains[0] == domain1
        assert domains[1] == domain2
        assert domains[2] == domain3


class CharacterGoalModelTests(TestCase):
    """Tests for CharacterGoal model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.character = CharacterFactory()
        cls.domain = GoalDomainFactory(name="Wealth")

    def test_str_representation(self):
        """CharacterGoal string shows character, domain, and points."""
        goal = CharacterGoalFactory(
            character=self.character,
            domain=self.domain,
            points=15,
        )
        assert "Wealth" in str(goal)
        assert "15" in str(goal)

    def test_unique_character_domain(self):
        """Character can only have one goal per domain."""
        CharacterGoalFactory(character=self.character, domain=self.domain)
        with self.assertRaises(IntegrityError):
            CharacterGoalFactory(character=self.character, domain=self.domain)

    def test_default_points_zero(self):
        """CharacterGoal defaults to zero points."""
        goal = CharacterGoal.objects.create(
            character=self.character,
            domain=self.domain,
        )
        assert goal.points == 0

    def test_notes_can_be_blank(self):
        """CharacterGoal notes are optional."""
        goal = CharacterGoalFactory(
            character=self.character,
            domain=self.domain,
            notes="",
        )
        assert goal.notes == ""


class GoalJournalModelTests(TestCase):
    """Tests for GoalJournal model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.character = CharacterFactory()
        cls.domain = GoalDomainFactory()

    def test_str_representation(self):
        """GoalJournal string shows character and title."""
        journal = GoalJournalFactory(
            character=self.character,
            title="My Journey",
        )
        assert "My Journey" in str(journal)

    def test_domain_optional(self):
        """GoalJournal domain is optional."""
        journal = GoalJournalFactory(
            character=self.character,
            domain=None,
        )
        assert journal.domain is None

    def test_xp_awarded_default_zero(self):
        """GoalJournal xp_awarded defaults to zero."""
        journal = GoalJournal.objects.create(
            character=self.character,
            title="Test",
            content="Test content",
        )
        assert journal.xp_awarded == 0

    def test_is_public_default_false(self):
        """GoalJournal is_public defaults to False."""
        journal = GoalJournal.objects.create(
            character=self.character,
            title="Test",
            content="Test content",
        )
        assert journal.is_public is False


class GoalRevisionModelTests(TestCase):
    """Tests for GoalRevision model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.character = CharacterFactory()

    def test_str_representation(self):
        """GoalRevision string shows character and last revised date."""
        revision = GoalRevisionFactory(character=self.character)
        assert "Last revised" in str(revision)

    def test_can_revise_returns_true_after_week(self):
        """can_revise returns True when more than a week has passed."""
        revision = GoalRevisionFactory(character=self.character)
        revision.last_revised_at = timezone.now() - timedelta(weeks=1, seconds=1)
        revision.save()

        assert revision.can_revise() is True

    def test_can_revise_returns_false_within_week(self):
        """can_revise returns False when less than a week has passed."""
        revision = GoalRevisionFactory(character=self.character)
        revision.last_revised_at = timezone.now() - timedelta(days=6)
        revision.save()

        assert revision.can_revise() is False

    def test_can_revise_exactly_one_week(self):
        """can_revise returns True at exactly one week."""
        revision = GoalRevisionFactory(character=self.character)
        revision.last_revised_at = timezone.now() - timedelta(weeks=1)
        revision.save()

        assert revision.can_revise() is True

    def test_mark_revised_updates_timestamp(self):
        """mark_revised updates last_revised_at to now."""
        revision = GoalRevisionFactory(character=self.character)
        old_time = revision.last_revised_at
        revision.last_revised_at = timezone.now() - timedelta(weeks=2)
        revision.save()

        before_mark = timezone.now()
        revision.mark_revised()
        after_mark = timezone.now()

        assert revision.last_revised_at >= before_mark
        assert revision.last_revised_at <= after_mark
        assert revision.last_revised_at != old_time

    def test_one_revision_per_character(self):
        """Each character can only have one GoalRevision."""
        GoalRevisionFactory(character=self.character)
        with self.assertRaises(IntegrityError):
            GoalRevisionFactory(character=self.character)

    def test_default_last_revised_at_now(self):
        """GoalRevision defaults last_revised_at to now."""
        before = timezone.now()
        revision = GoalRevision.objects.create(character=self.character)
        after = timezone.now()

        assert revision.last_revised_at >= before
        assert revision.last_revised_at <= after

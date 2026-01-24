"""Tests for consent models."""

from django.db import IntegrityError
from django.test import TestCase

from world.consent.factories import ConsentGroupFactory, ConsentGroupMemberFactory
from world.consent.models import ConsentGroup, ConsentGroupMember
from world.roster.factories import RosterTenureFactory


class ConsentGroupModelTests(TestCase):
    """Tests for ConsentGroup model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.owner = RosterTenureFactory()

    def test_str_representation(self):
        """ConsentGroup string shows owner and name."""
        group = ConsentGroupFactory(owner=self.owner, name="My Friends")
        assert "My Friends" in str(group)

    def test_unique_name_per_owner(self):
        """Owner cannot have two groups with the same name."""
        ConsentGroupFactory(owner=self.owner, name="Unique Group")
        with self.assertRaises(IntegrityError):
            ConsentGroup.objects.create(owner=self.owner, name="Unique Group")

    def test_different_owners_same_name(self):
        """Different owners can have groups with the same name."""
        other_owner = RosterTenureFactory()
        ConsentGroupFactory(owner=self.owner, name="Same Name")
        group2 = ConsentGroupFactory(owner=other_owner, name="Same Name")
        assert group2.name == "Same Name"


class ConsentGroupMemberModelTests(TestCase):
    """Tests for ConsentGroupMember model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.owner = RosterTenureFactory()
        cls.member = RosterTenureFactory()

    def test_str_representation(self):
        """ConsentGroupMember string shows tenure and group."""
        group = ConsentGroupFactory(owner=self.owner, name="Test Group")
        membership = ConsentGroupMemberFactory(group=group, tenure=self.member)
        assert "Test Group" in str(membership)

    def test_unique_member_per_group(self):
        """Same tenure cannot be in the same group twice."""
        group = ConsentGroupFactory(owner=self.owner)
        ConsentGroupMemberFactory(group=group, tenure=self.member)
        with self.assertRaises(IntegrityError):
            ConsentGroupMember.objects.create(group=group, tenure=self.member)

    def test_member_in_multiple_groups(self):
        """Same tenure can be in multiple different groups."""
        group1 = ConsentGroupFactory(owner=self.owner, name="Group 1")
        group2 = ConsentGroupFactory(owner=self.owner, name="Group 2")
        ConsentGroupMemberFactory(group=group1, tenure=self.member)
        membership2 = ConsentGroupMemberFactory(group=group2, tenure=self.member)
        assert membership2.tenure == self.member

"""Tests for permissions models."""

from django.db import IntegrityError
from django.test import TestCase

from world.permissions.factories import PermissionGroupFactory, PermissionGroupMemberFactory
from world.permissions.models import PermissionGroup, PermissionGroupMember
from world.roster.factories import RosterTenureFactory


class PermissionGroupModelTests(TestCase):
    """Tests for PermissionGroup model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.owner = RosterTenureFactory()

    def test_str_representation(self):
        """PermissionGroup string shows owner and name."""
        group = PermissionGroupFactory(owner=self.owner, name="My Friends")
        assert "My Friends" in str(group)

    def test_unique_name_per_owner(self):
        """Owner cannot have two groups with the same name."""
        PermissionGroupFactory(owner=self.owner, name="Unique Group")
        with self.assertRaises(IntegrityError):
            PermissionGroup.objects.create(owner=self.owner, name="Unique Group")

    def test_different_owners_same_name(self):
        """Different owners can have groups with the same name."""
        other_owner = RosterTenureFactory()
        PermissionGroupFactory(owner=self.owner, name="Same Name")
        group2 = PermissionGroupFactory(owner=other_owner, name="Same Name")
        assert group2.name == "Same Name"


class PermissionGroupMemberModelTests(TestCase):
    """Tests for PermissionGroupMember model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.owner = RosterTenureFactory()
        cls.member = RosterTenureFactory()

    def test_str_representation(self):
        """PermissionGroupMember string shows tenure and group."""
        group = PermissionGroupFactory(owner=self.owner, name="Test Group")
        membership = PermissionGroupMemberFactory(group=group, tenure=self.member)
        assert "Test Group" in str(membership)

    def test_unique_member_per_group(self):
        """Same tenure cannot be in the same group twice."""
        group = PermissionGroupFactory(owner=self.owner)
        PermissionGroupMemberFactory(group=group, tenure=self.member)
        with self.assertRaises(IntegrityError):
            PermissionGroupMember.objects.create(group=group, tenure=self.member)

    def test_member_in_multiple_groups(self):
        """Same tenure can be in multiple different groups."""
        group1 = PermissionGroupFactory(owner=self.owner, name="Group 1")
        group2 = PermissionGroupFactory(owner=self.owner, name="Group 2")
        PermissionGroupMemberFactory(group=group1, tenure=self.member)
        membership2 = PermissionGroupMemberFactory(group=group2, tenure=self.member)
        assert membership2.tenure == self.member

"""Tests for VisibilityMixin behavior via CodexTeachingOffer."""

from django.test import TestCase

from world.codex.factories import CodexTeachingOfferFactory
from world.consent.factories import ConsentGroupFactory, ConsentGroupMemberFactory
from world.consent.models import VisibilityMixin
from world.roster.factories import RosterTenureFactory


class CodexTeachingOfferVisibilityTests(TestCase):
    """Tests for visibility behavior on CodexTeachingOffer."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.owner = RosterTenureFactory()
        cls.viewer = RosterTenureFactory()
        cls.other = RosterTenureFactory()

    def test_public_visibility_allows_viewer(self):
        """PUBLIC mode allows any viewer."""
        offer = CodexTeachingOfferFactory(
            teacher=self.owner,
            visibility_mode=VisibilityMixin.VisibilityMode.PUBLIC,
        )

        assert offer.is_visible_to(self.viewer) is True
        assert offer.is_visible_to(self.other) is True

    def test_private_visibility_blocks_viewer(self):
        """PRIVATE mode blocks all viewers."""
        offer = CodexTeachingOfferFactory(
            teacher=self.owner,
            visibility_mode=VisibilityMixin.VisibilityMode.PRIVATE,
        )

        assert offer.is_visible_to(self.viewer) is False
        assert offer.is_visible_to(self.other) is False

    def test_characters_visibility_allows_listed(self):
        """CHARACTERS mode allows only listed tenures."""
        offer = CodexTeachingOfferFactory(
            teacher=self.owner,
            visibility_mode=VisibilityMixin.VisibilityMode.CHARACTERS,
        )
        offer.visible_to_tenures.add(self.viewer)

        assert offer.is_visible_to(self.viewer) is True
        assert offer.is_visible_to(self.other) is False

    def test_groups_visibility_allows_members(self):
        """GROUPS mode allows members of specified groups."""
        group = ConsentGroupFactory(owner=self.owner, name="Friends")
        ConsentGroupMemberFactory(group=group, tenure=self.viewer)

        offer = CodexTeachingOfferFactory(
            teacher=self.owner,
            visibility_mode=VisibilityMixin.VisibilityMode.GROUPS,
        )
        offer.visible_to_groups.add(group)

        assert offer.is_visible_to(self.viewer) is True
        assert offer.is_visible_to(self.other) is False

    def test_excluded_characters_blocked_from_public(self):
        """Excluded tenures are blocked even from public content."""
        offer = CodexTeachingOfferFactory(
            teacher=self.owner,
            visibility_mode=VisibilityMixin.VisibilityMode.PUBLIC,
        )
        offer.excluded_tenures.add(self.viewer)

        assert offer.is_visible_to(self.viewer) is False
        assert offer.is_visible_to(self.other) is True

    def test_excluded_characters_blocked_from_characters_list(self):
        """Excluded tenures are blocked even if on visible list."""
        offer = CodexTeachingOfferFactory(
            teacher=self.owner,
            visibility_mode=VisibilityMixin.VisibilityMode.CHARACTERS,
        )
        offer.visible_to_tenures.add(self.viewer)
        offer.excluded_tenures.add(self.viewer)

        assert offer.is_visible_to(self.viewer) is False

    def test_excluded_characters_blocked_from_groups(self):
        """Excluded tenures are blocked even if in visible group."""
        group = ConsentGroupFactory(owner=self.owner, name="Friends")
        ConsentGroupMemberFactory(group=group, tenure=self.viewer)

        offer = CodexTeachingOfferFactory(
            teacher=self.owner,
            visibility_mode=VisibilityMixin.VisibilityMode.GROUPS,
        )
        offer.visible_to_groups.add(group)
        offer.excluded_tenures.add(self.viewer)

        assert offer.is_visible_to(self.viewer) is False

    def test_multiple_groups_any_membership_works(self):
        """Member of any visible group can see content."""
        group1 = ConsentGroupFactory(owner=self.owner, name="Group 1")
        group2 = ConsentGroupFactory(owner=self.owner, name="Group 2")
        ConsentGroupMemberFactory(group=group2, tenure=self.viewer)

        offer = CodexTeachingOfferFactory(
            teacher=self.owner,
            visibility_mode=VisibilityMixin.VisibilityMode.GROUPS,
        )
        offer.visible_to_groups.add(group1, group2)

        assert offer.is_visible_to(self.viewer) is True

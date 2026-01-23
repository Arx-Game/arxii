"""
Tests for societies system models.

Tests focus on custom methods and behaviors, not standard Django functionality.
"""

from django.core.exceptions import ValidationError
from django.test import TestCase
import pytest

from world.character_creation.factories import RealmFactory
from world.character_sheets.factories import GuiseFactory
from world.societies.factories import (
    LegendEntryFactory,
    LegendSpreadFactory,
    OrganizationFactory,
    OrganizationMembershipFactory,
    OrganizationReputationFactory,
    OrganizationTypeFactory,
    SocietyFactory,
    SocietyReputationFactory,
)
from world.societies.types import ReputationTier


class SocietyModelTests(TestCase):
    """Test Society model functionality."""

    @classmethod
    def setUpTestData(cls):
        """Set up shared test data."""
        cls.realm = RealmFactory(name="Society Test Realm")
        cls.society = SocietyFactory(
            name="Test Society",
            realm=cls.realm,
            mercy=3,
            method=-2,
            status=0,
            change=5,
            allegiance=-5,
            power=1,
        )

    def test_society_str_representation(self):
        """Test string representation includes name and realm."""
        expected = "Test Society (Society Test Realm)"
        assert str(self.society) == expected

    def test_society_realm_relationship(self):
        """Test society is linked to correct realm."""
        assert self.society.realm == self.realm
        assert self.society in self.realm.societies.all()

    def test_society_principle_values(self):
        """Test principle values are stored correctly."""
        assert self.society.mercy == 3
        assert self.society.method == -2
        assert self.society.status == 0
        assert self.society.change == 5
        assert self.society.allegiance == -5
        assert self.society.power == 1

    def test_society_creation_via_factory(self):
        """Test factory creates valid society instance."""
        society = SocietyFactory()
        assert society.pk is not None
        assert society.realm is not None


class OrganizationTypeModelTests(TestCase):
    """Test OrganizationType model functionality."""

    @classmethod
    def setUpTestData(cls):
        """Set up shared test data."""
        cls.org_type = OrganizationTypeFactory(
            name="test_guild",
            rank_1_title="Guildmaster",
            rank_2_title="Master",
            rank_3_title="Journeyman",
            rank_4_title="Apprentice",
            rank_5_title="Initiate",
        )

    def test_org_type_str_representation(self):
        """Test string representation returns name."""
        assert str(self.org_type) == "test_guild"

    def test_org_type_rank_titles(self):
        """Test rank titles are stored correctly."""
        assert self.org_type.rank_1_title == "Guildmaster"
        assert self.org_type.rank_2_title == "Master"
        assert self.org_type.rank_3_title == "Journeyman"
        assert self.org_type.rank_4_title == "Apprentice"
        assert self.org_type.rank_5_title == "Initiate"


class OrganizationModelTests(TestCase):
    """Test Organization model functionality."""

    @classmethod
    def setUpTestData(cls):
        """Set up shared test data."""
        cls.realm = RealmFactory(name="Org Test Realm")
        cls.society = SocietyFactory(
            name="Org Test Society",
            realm=cls.realm,
            mercy=2,
            method=3,
            status=-1,
            change=0,
            allegiance=4,
            power=-3,
        )
        cls.org_type = OrganizationTypeFactory(
            name="test_org_type",
            rank_1_title="Leader",
            rank_2_title="Officer",
            rank_3_title="Member",
            rank_4_title="Associate",
            rank_5_title="Contact",
        )
        cls.organization = OrganizationFactory(
            name="Test Organization",
            society=cls.society,
            org_type=cls.org_type,
        )

    def test_organization_str_representation(self):
        """Test string representation includes name and society."""
        expected = "Test Organization (Org Test Society)"
        assert str(self.organization) == expected

    def test_organization_creation_via_factory(self):
        """Test factory creates valid organization instance."""
        org = OrganizationFactory()
        assert org.pk is not None
        assert org.society is not None
        assert org.org_type is not None


class OrganizationPrincipleInheritanceTests(TestCase):
    """Test Organization.get_effective_principle() inheritance behavior."""

    @classmethod
    def setUpTestData(cls):
        """Set up shared test data."""
        cls.society = SocietyFactory(
            mercy=2,
            method=3,
            status=-1,
            change=0,
            allegiance=4,
            power=-3,
        )
        cls.org_type = OrganizationTypeFactory()
        # Organization with no overrides - inherits from society
        cls.org_no_override = OrganizationFactory(
            society=cls.society,
            org_type=cls.org_type,
        )
        # Organization with some overrides
        cls.org_with_override = OrganizationFactory(
            society=cls.society,
            org_type=cls.org_type,
            mercy_override=5,
            method_override=-5,
            # status, change, allegiance, power use society values
        )

    def test_inherits_from_society_when_no_override(self):
        """Test organization inherits society's principle when override is null."""
        assert self.org_no_override.get_effective_principle("mercy") == 2
        assert self.org_no_override.get_effective_principle("method") == 3
        assert self.org_no_override.get_effective_principle("status") == -1
        assert self.org_no_override.get_effective_principle("change") == 0
        assert self.org_no_override.get_effective_principle("allegiance") == 4
        assert self.org_no_override.get_effective_principle("power") == -3

    def test_returns_override_when_set(self):
        """Test organization returns its override when set."""
        assert self.org_with_override.get_effective_principle("mercy") == 5
        assert self.org_with_override.get_effective_principle("method") == -5

    def test_inherits_unset_principles_with_partial_override(self):
        """Test organization inherits society values for unset overrides."""
        # These should inherit from society
        assert self.org_with_override.get_effective_principle("status") == -1
        assert self.org_with_override.get_effective_principle("change") == 0
        assert self.org_with_override.get_effective_principle("allegiance") == 4
        assert self.org_with_override.get_effective_principle("power") == -3


class OrganizationRankTitleTests(TestCase):
    """Test Organization.get_rank_title() inheritance behavior."""

    @classmethod
    def setUpTestData(cls):
        """Set up shared test data."""
        cls.org_type = OrganizationTypeFactory(
            rank_1_title="Chief",
            rank_2_title="Lieutenant",
            rank_3_title="Soldier",
            rank_4_title="Recruit",
            rank_5_title="Prospect",
        )
        cls.org_no_override = OrganizationFactory(org_type=cls.org_type)
        cls.org_with_override = OrganizationFactory(
            org_type=cls.org_type,
            rank_1_title_override="Grand Master",
            rank_3_title_override="Knight",
        )

    def test_inherits_from_org_type_when_no_override(self):
        """Test organization inherits org_type titles when override is blank."""
        assert self.org_no_override.get_rank_title(1) == "Chief"
        assert self.org_no_override.get_rank_title(2) == "Lieutenant"
        assert self.org_no_override.get_rank_title(3) == "Soldier"
        assert self.org_no_override.get_rank_title(4) == "Recruit"
        assert self.org_no_override.get_rank_title(5) == "Prospect"

    def test_returns_override_when_set(self):
        """Test organization returns its override title when set."""
        assert self.org_with_override.get_rank_title(1) == "Grand Master"
        assert self.org_with_override.get_rank_title(3) == "Knight"

    def test_inherits_unset_titles_with_partial_override(self):
        """Test organization inherits org_type titles for unset overrides."""
        assert self.org_with_override.get_rank_title(2) == "Lieutenant"
        assert self.org_with_override.get_rank_title(4) == "Recruit"
        assert self.org_with_override.get_rank_title(5) == "Prospect"

    def test_invalid_rank_raises_value_error(self):
        """Test that invalid rank numbers raise ValueError."""
        with pytest.raises(ValueError, match="Rank must be 1-5"):
            self.org_no_override.get_rank_title(0)

        with pytest.raises(ValueError, match="Rank must be 1-5"):
            self.org_no_override.get_rank_title(6)


class OrganizationMembershipValidationTests(TestCase):
    """Test OrganizationMembership validation for guise requirements."""

    @classmethod
    def setUpTestData(cls):
        """Set up shared test data."""
        cls.organization = OrganizationFactory()

    def test_default_guise_can_join(self):
        """Test that default guise (is_default=True) can join organizations."""
        guise = GuiseFactory(is_default=True, is_persistent=False)
        membership = OrganizationMembershipFactory(
            organization=self.organization,
            guise=guise,
            rank=3,
        )
        assert membership.pk is not None
        assert membership.guise == guise

    def test_persistent_guise_can_join(self):
        """Test that persistent guise (is_persistent=True) can join organizations."""
        guise = GuiseFactory(is_default=False, is_persistent=True)
        membership = OrganizationMembershipFactory(
            organization=self.organization,
            guise=guise,
            rank=4,
        )
        assert membership.pk is not None
        assert membership.guise == guise

    def test_temporary_guise_cannot_join(self):
        """Test that temporary guise (both False) cannot join organizations."""
        guise = GuiseFactory(is_default=False, is_persistent=False)

        with pytest.raises(ValidationError) as exc_info:
            OrganizationMembershipFactory(
                organization=self.organization,
                guise=guise,
            )

        assert "guise" in exc_info.value.message_dict
        assert "primary identities or persistent aliases" in str(exc_info.value)

    def test_membership_str_representation(self):
        """Test membership string representation."""
        guise = GuiseFactory(name="Test Member")
        org = OrganizationFactory(name="Test Org")
        membership = OrganizationMembershipFactory(
            organization=org,
            guise=guise,
            rank=2,
        )
        expected = "Test Member - Test Org (Rank 2)"
        assert str(membership) == expected

    def test_membership_get_title(self):
        """Test getting the title from organization for this rank."""
        org_type = OrganizationTypeFactory(rank_2_title="Captain")
        org = OrganizationFactory(org_type=org_type)
        membership = OrganizationMembershipFactory(organization=org, rank=2)

        assert membership.get_title() == "Captain"


class SocietyReputationValidationTests(TestCase):
    """Test SocietyReputation validation for guise requirements."""

    @classmethod
    def setUpTestData(cls):
        """Set up shared test data."""
        cls.society = SocietyFactory()

    def test_default_guise_can_have_reputation(self):
        """Test that default guise can have society reputation."""
        guise = GuiseFactory(is_default=True, is_persistent=False)
        reputation = SocietyReputationFactory(
            guise=guise,
            society=self.society,
            value=100,
        )
        assert reputation.pk is not None

    def test_persistent_guise_can_have_reputation(self):
        """Test that persistent guise can have society reputation."""
        guise = GuiseFactory(is_default=False, is_persistent=True)
        reputation = SocietyReputationFactory(
            guise=guise,
            society=self.society,
            value=-200,
        )
        assert reputation.pk is not None

    def test_temporary_guise_cannot_have_reputation(self):
        """Test that temporary guise cannot have society reputation."""
        guise = GuiseFactory(is_default=False, is_persistent=False)

        with pytest.raises(ValidationError) as exc_info:
            SocietyReputationFactory(
                guise=guise,
                society=self.society,
            )

        assert "guise" in exc_info.value.message_dict


class OrganizationReputationValidationTests(TestCase):
    """Test OrganizationReputation validation for guise requirements."""

    @classmethod
    def setUpTestData(cls):
        """Set up shared test data."""
        cls.organization = OrganizationFactory()

    def test_default_guise_can_have_reputation(self):
        """Test that default guise can have organization reputation."""
        guise = GuiseFactory(is_default=True, is_persistent=False)
        reputation = OrganizationReputationFactory(
            guise=guise,
            organization=self.organization,
            value=500,
        )
        assert reputation.pk is not None

    def test_persistent_guise_can_have_reputation(self):
        """Test that persistent guise can have organization reputation."""
        guise = GuiseFactory(is_default=False, is_persistent=True)
        reputation = OrganizationReputationFactory(
            guise=guise,
            organization=self.organization,
            value=-750,
        )
        assert reputation.pk is not None

    def test_temporary_guise_cannot_have_reputation(self):
        """Test that temporary guise cannot have organization reputation."""
        guise = GuiseFactory(is_default=False, is_persistent=False)

        with pytest.raises(ValidationError) as exc_info:
            OrganizationReputationFactory(
                guise=guise,
                organization=self.organization,
            )

        assert "guise" in exc_info.value.message_dict


class ReputationTierCalculationTests(TestCase):
    """Test ReputationTier.from_value() tier calculation."""

    def test_reviled_tier_boundaries(self):
        """Test REVILED tier at boundaries (-1000 to -750)."""
        assert ReputationTier.from_value(-1000) == ReputationTier.REVILED
        assert ReputationTier.from_value(-750) == ReputationTier.REVILED

    def test_despised_tier_boundaries(self):
        """Test DESPISED tier at boundaries (-749 to -500)."""
        assert ReputationTier.from_value(-749) == ReputationTier.DESPISED
        assert ReputationTier.from_value(-500) == ReputationTier.DESPISED

    def test_disliked_tier_boundaries(self):
        """Test DISLIKED tier at boundaries (-499 to -250)."""
        assert ReputationTier.from_value(-499) == ReputationTier.DISLIKED
        assert ReputationTier.from_value(-250) == ReputationTier.DISLIKED

    def test_disfavored_tier_boundaries(self):
        """Test DISFAVORED tier at boundaries (-249 to -100)."""
        assert ReputationTier.from_value(-249) == ReputationTier.DISFAVORED
        assert ReputationTier.from_value(-100) == ReputationTier.DISFAVORED

    def test_unknown_tier_boundaries(self):
        """Test UNKNOWN tier at boundaries (-99 to +99)."""
        assert ReputationTier.from_value(-99) == ReputationTier.UNKNOWN
        assert ReputationTier.from_value(0) == ReputationTier.UNKNOWN
        assert ReputationTier.from_value(99) == ReputationTier.UNKNOWN

    def test_favored_tier_boundaries(self):
        """Test FAVORED tier at boundaries (+100 to +249)."""
        assert ReputationTier.from_value(100) == ReputationTier.FAVORED
        assert ReputationTier.from_value(249) == ReputationTier.FAVORED

    def test_liked_tier_boundaries(self):
        """Test LIKED tier at boundaries (+250 to +499)."""
        assert ReputationTier.from_value(250) == ReputationTier.LIKED
        assert ReputationTier.from_value(499) == ReputationTier.LIKED

    def test_honored_tier_boundaries(self):
        """Test HONORED tier at boundaries (+500 to +749)."""
        assert ReputationTier.from_value(500) == ReputationTier.HONORED
        assert ReputationTier.from_value(749) == ReputationTier.HONORED

    def test_revered_tier_boundaries(self):
        """Test REVERED tier at boundaries (+750 to +1000)."""
        assert ReputationTier.from_value(750) == ReputationTier.REVERED
        assert ReputationTier.from_value(1000) == ReputationTier.REVERED

    def test_tier_display_name(self):
        """Test tier display_name property returns capitalized value."""
        assert ReputationTier.REVILED.display_name == "Reviled"
        assert ReputationTier.UNKNOWN.display_name == "Unknown"
        assert ReputationTier.REVERED.display_name == "Revered"


class ReputationModelTierTests(TestCase):
    """Test reputation models' get_tier() method."""

    def test_society_reputation_get_tier(self):
        """Test SocietyReputation.get_tier() returns correct tier."""
        reputation = SocietyReputationFactory(value=600)
        assert reputation.get_tier() == ReputationTier.HONORED

    def test_organization_reputation_get_tier(self):
        """Test OrganizationReputation.get_tier() returns correct tier."""
        reputation = OrganizationReputationFactory(value=-300)
        assert reputation.get_tier() == ReputationTier.DISLIKED


class LegendEntryModelTests(TestCase):
    """Test LegendEntry model functionality."""

    @classmethod
    def setUpTestData(cls):
        """Set up shared test data."""
        cls.guise = GuiseFactory(name="Hero")
        cls.legend_entry = LegendEntryFactory(
            guise=cls.guise,
            title="Slew the Dragon",
            base_value=50,
        )

    def test_legend_entry_str_representation(self):
        """Test string representation includes guise and title."""
        expected = "Hero: Slew the Dragon"
        assert str(self.legend_entry) == expected

    def test_legend_entry_creation_via_factory(self):
        """Test factory creates valid legend entry."""
        entry = LegendEntryFactory()
        assert entry.pk is not None
        assert entry.guise is not None
        assert entry.title


class LegendTotalCalculationTests(TestCase):
    """Test LegendEntry.get_total_value() calculation."""

    def test_entry_with_no_spreads_returns_base_value(self):
        """Test entry with no spreads returns only base_value."""
        entry = LegendEntryFactory(base_value=100)
        assert entry.get_total_value() == 100

    def test_entry_with_single_spread(self):
        """Test entry with one spread adds value_added to base_value."""
        entry = LegendEntryFactory(base_value=100)
        LegendSpreadFactory(legend_entry=entry, value_added=25)

        assert entry.get_total_value() == 125

    def test_entry_with_multiple_spreads(self):
        """Test entry with multiple spreads sums all value_added."""
        entry = LegendEntryFactory(base_value=100)
        LegendSpreadFactory(legend_entry=entry, value_added=25)
        LegendSpreadFactory(legend_entry=entry, value_added=15)
        LegendSpreadFactory(legend_entry=entry, value_added=10)

        assert entry.get_total_value() == 150  # 100 + 25 + 15 + 10

    def test_entry_with_zero_base_and_spreads(self):
        """Test entry with zero base_value still calculates spreads."""
        entry = LegendEntryFactory(base_value=0)
        LegendSpreadFactory(legend_entry=entry, value_added=50)

        assert entry.get_total_value() == 50


class LegendSpreadModelTests(TestCase):
    """Test LegendSpread model functionality."""

    @classmethod
    def setUpTestData(cls):
        """Set up shared test data."""
        cls.hero_guise = GuiseFactory(name="Hero")
        cls.bard_guise = GuiseFactory(name="The Bard")
        cls.legend_entry = LegendEntryFactory(
            guise=cls.hero_guise,
            title="Defeated the Lich",
        )
        cls.spread = LegendSpreadFactory(
            legend_entry=cls.legend_entry,
            spreader_guise=cls.bard_guise,
            value_added=20,
        )

    def test_legend_spread_str_representation(self):
        """Test string representation includes spreader and entry title."""
        expected = "The Bard spread: Defeated the Lich"
        assert str(self.spread) == expected

    def test_legend_spread_creation_via_factory(self):
        """Test factory creates valid legend spread."""
        spread = LegendSpreadFactory()
        assert spread.pk is not None
        assert spread.legend_entry is not None
        assert spread.spreader_guise is not None

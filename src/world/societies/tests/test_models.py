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
    LegendDeedStoryFactory,
    LegendEntryFactory,
    LegendEventFactory,
    LegendSourceTypeFactory,
    LegendSpreadFactory,
    OrganizationFactory,
    OrganizationMembershipFactory,
    OrganizationReputationFactory,
    OrganizationTypeFactory,
    SocietyFactory,
    SocietyReputationFactory,
)
from world.societies.models import (
    CharacterLegendSummary,
    GuiseLegendSummary,
    SpreadingConfig,
    refresh_legend_views,
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


class LegendSourceTypeModelTests(TestCase):
    """Test LegendSourceType model functionality."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Set up shared test data."""
        cls.source_type = LegendSourceTypeFactory(
            name="Combat",
            description="Legend from combat encounters",
            display_order=1,
        )

    def test_source_type_str_representation(self) -> None:
        """Test string representation returns name."""
        assert str(self.source_type) == "Combat"

    def test_source_type_creation_via_factory(self) -> None:
        """Test factory creates valid source type."""
        source_type = LegendSourceTypeFactory()
        assert source_type.pk is not None
        assert source_type.name

    def test_source_type_is_active_default(self) -> None:
        """Test is_active defaults to True."""
        source_type = LegendSourceTypeFactory()
        assert source_type.is_active is True

    def test_source_type_ordering(self) -> None:
        """Test source types are ordered by display_order then name."""
        from world.societies.models import LegendSourceType

        st_a = LegendSourceTypeFactory(name="Zebra", display_order=0)
        st_b = LegendSourceTypeFactory(name="Alpha", display_order=2)
        types = list(LegendSourceType.objects.filter(pk__in=[st_a.pk, st_b.pk]))
        assert types[0] == st_a
        assert types[1] == st_b


class SpreadingConfigModelTests(TestCase):
    """Test SpreadingConfig model functionality."""

    def test_get_active_config_creates_singleton(self) -> None:
        """Test get_active_config creates config if none exists."""
        config = SpreadingConfig.get_active_config()
        assert config.pk == 1
        assert config.default_spread_multiplier == 9

    def test_get_active_config_returns_existing(self) -> None:
        """Test get_active_config returns existing config."""
        config1 = SpreadingConfig.get_active_config()
        config1.default_spread_multiplier = 12
        config1.save()
        config2 = SpreadingConfig.get_active_config()
        assert config2.default_spread_multiplier == 12

    def test_str_representation(self) -> None:
        """Test string representation."""
        config = SpreadingConfig.get_active_config()
        assert "cap_multiplier=9" in str(config)
        assert "audience_factor=1" in str(config)


class LegendEventModelTests(TestCase):
    """Test LegendEvent model functionality."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Set up shared test data."""
        cls.source_type = LegendSourceTypeFactory(name="Story Completion")
        cls.event = LegendEventFactory(
            title="The Fall of Darkholme",
            source_type=cls.source_type,
            base_value=50,
        )

    def test_event_str_representation(self) -> None:
        """Test string representation returns title."""
        assert str(self.event) == "The Fall of Darkholme"

    def test_event_creation_via_factory(self) -> None:
        """Test factory creates valid event."""
        event = LegendEventFactory()
        assert event.pk is not None
        assert event.source_type is not None
        assert event.base_value > 0

    def test_event_source_type_relationship(self) -> None:
        """Test event links to source type correctly."""
        assert self.event.source_type == self.source_type
        assert self.event in self.source_type.events.all()


class LegendEntryExtendedTests(TestCase):
    """Test new LegendEntry fields and properties."""

    def test_max_spread_calculation(self) -> None:
        """Test max_spread returns base_value * spread_multiplier."""
        entry = LegendEntryFactory(base_value=10, spread_multiplier=9)
        assert entry.max_spread == 90

    def test_max_spread_custom_multiplier(self) -> None:
        """Test max_spread with custom multiplier."""
        entry = LegendEntryFactory(base_value=20, spread_multiplier=5)
        assert entry.max_spread == 100

    def test_spread_value_no_spreads(self) -> None:
        """Test spread_value returns 0 with no spreads."""
        entry = LegendEntryFactory(base_value=50)
        assert entry.spread_value == 0

    def test_spread_value_with_spreads(self) -> None:
        """Test spread_value sums all spreads."""
        entry = LegendEntryFactory(base_value=50)
        LegendSpreadFactory(legend_entry=entry, value_added=10)
        LegendSpreadFactory(legend_entry=entry, value_added=20)
        assert entry.spread_value == 30

    def test_remaining_spread_capacity(self) -> None:
        """Test remaining_spread_capacity calculation."""
        entry = LegendEntryFactory(base_value=10, spread_multiplier=9)
        LegendSpreadFactory(legend_entry=entry, value_added=30)
        # max_spread = 90, spread_value = 30, remaining = 60
        assert entry.remaining_spread_capacity == 60

    def test_remaining_spread_capacity_capped_at_zero(self) -> None:
        """Test remaining_spread_capacity never goes negative."""
        entry = LegendEntryFactory(base_value=10, spread_multiplier=1)
        LegendSpreadFactory(legend_entry=entry, value_added=20)
        # max_spread = 10, spread_value = 20, remaining = max(0, -10) = 0
        assert entry.remaining_spread_capacity == 0

    def test_inactive_entry_returns_zero(self) -> None:
        """Test get_total_value returns 0 for inactive entries."""
        entry = LegendEntryFactory(base_value=100, is_active=False)
        LegendSpreadFactory(legend_entry=entry, value_added=50)
        assert entry.get_total_value() == 0

    def test_active_entry_returns_total(self) -> None:
        """Test get_total_value returns base + spreads for active entries."""
        entry = LegendEntryFactory(base_value=100, is_active=True)
        LegendSpreadFactory(legend_entry=entry, value_added=25)
        assert entry.get_total_value() == 125

    def test_entry_with_source_type(self) -> None:
        """Test entry can be linked to a source type."""
        source_type = LegendSourceTypeFactory()
        entry = LegendEntryFactory(source_type=source_type)
        assert entry.source_type == source_type
        assert entry in source_type.deeds.all()

    def test_entry_with_event(self) -> None:
        """Test entry can be linked to an event."""
        event = LegendEventFactory()
        entry = LegendEntryFactory(event=event)
        assert entry.event == event
        assert entry in event.deeds.all()

    def test_entry_defaults_for_new_fields(self) -> None:
        """Test new fields have correct defaults."""
        entry = LegendEntryFactory()
        assert entry.is_active is True
        assert entry.spread_multiplier == 9
        assert entry.source_type is None
        assert entry.event is None
        assert entry.scene is None
        assert entry.story is None


class LegendSpreadExtendedTests(TestCase):
    """Test new LegendSpread fields."""

    def test_spread_audience_factor_default(self) -> None:
        """Test audience_factor defaults to 1.0."""
        from decimal import Decimal

        spread = LegendSpreadFactory()
        assert spread.audience_factor == Decimal("1.0")

    def test_spread_skill_nullable(self) -> None:
        """Test skill is nullable."""
        spread = LegendSpreadFactory()
        assert spread.skill is None

    def test_spread_scene_nullable(self) -> None:
        """Test scene is nullable."""
        spread = LegendSpreadFactory()
        assert spread.scene is None


class LegendDeedStoryModelTests(TestCase):
    """Test LegendDeedStory model functionality."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Set up shared test data."""
        cls.guise = GuiseFactory(name="The Bard")
        cls.entry = LegendEntryFactory(title="Slew the Dragon")
        cls.story = LegendDeedStoryFactory(
            deed=cls.entry,
            author=cls.guise,
            text="It was a dark and stormy night...",
        )

    def test_deed_story_str_representation(self) -> None:
        """Test string representation."""
        assert str(self.story) == "The Bard's account of: Slew the Dragon"

    def test_deed_story_creation_via_factory(self) -> None:
        """Test factory creates valid deed story."""
        story = LegendDeedStoryFactory()
        assert story.pk is not None
        assert story.deed is not None
        assert story.author is not None
        assert story.text

    def test_unique_deed_story_per_author(self) -> None:
        """Test only one story per deed per author."""
        from django.db import IntegrityError

        with pytest.raises(IntegrityError):
            LegendDeedStoryFactory(
                deed=self.entry,
                author=self.guise,
                text="A different telling...",
            )

    def test_different_authors_can_write_for_same_deed(self) -> None:
        """Test multiple authors can write stories for the same deed."""
        other_guise = GuiseFactory(name="The Knight")
        story2 = LegendDeedStoryFactory(
            deed=self.entry,
            author=other_guise,
            text="From my perspective...",
        )
        assert story2.pk is not None
        assert self.entry.deed_stories.count() == 2

    def test_same_author_can_write_for_different_deeds(self) -> None:
        """Test same author can write stories for different deeds."""
        other_entry = LegendEntryFactory(title="Saved the Village")
        story2 = LegendDeedStoryFactory(
            deed=other_entry,
            author=self.guise,
            text="Another tale...",
        )
        assert story2.pk is not None


class CharacterLegendSummaryTests(TestCase):
    """Test CharacterLegendSummary materialized view."""

    def _refresh(self) -> None:
        refresh_legend_views()

    def test_character_with_no_deeds(self) -> None:
        """Character with no deeds has personal_legend = 0 or no row."""
        guise = GuiseFactory()
        self._refresh()
        row = CharacterLegendSummary.objects.filter(character_id=guise.character_id).first()
        if row is not None:
            assert row.personal_legend == 0

    def test_character_with_single_deed(self) -> None:
        """Character with a single deed gets personal_legend = base_value."""
        guise = GuiseFactory()
        LegendEntryFactory(guise=guise, base_value=42, is_active=True)
        self._refresh()
        row = CharacterLegendSummary.objects.get(character_id=guise.character_id)
        assert row.personal_legend == 42

    def test_deed_with_spreads(self) -> None:
        """Deed with spreads includes spread totals in personal_legend."""
        guise = GuiseFactory()
        entry = LegendEntryFactory(guise=guise, base_value=100, is_active=True)
        LegendSpreadFactory(legend_entry=entry, value_added=25)
        LegendSpreadFactory(legend_entry=entry, value_added=15)
        self._refresh()
        row = CharacterLegendSummary.objects.get(character_id=guise.character_id)
        assert row.personal_legend == 140  # 100 + 25 + 15

    def test_inactive_deed_excluded(self) -> None:
        """Inactive deed is excluded from total."""
        guise = GuiseFactory()
        LegendEntryFactory(guise=guise, base_value=100, is_active=False)
        LegendEntryFactory(guise=guise, base_value=50, is_active=True)
        self._refresh()
        row = CharacterLegendSummary.objects.get(character_id=guise.character_id)
        assert row.personal_legend == 50

    def test_multiple_guises_summed(self) -> None:
        """Multiple guises for same character are summed together."""
        from evennia_extensions.factories import CharacterFactory

        character = CharacterFactory()
        guise1 = GuiseFactory(character=character, name="Identity A")
        guise2 = GuiseFactory(character=character, name="Identity B", is_default=False)
        LegendEntryFactory(guise=guise1, base_value=30, is_active=True)
        LegendEntryFactory(guise=guise2, base_value=20, is_active=True)
        self._refresh()
        row = CharacterLegendSummary.objects.get(character_id=character.pk)
        assert row.personal_legend == 50  # 30 + 20


class GuiseLegendSummaryTests(TestCase):
    """Test GuiseLegendSummary materialized view."""

    def _refresh(self) -> None:
        refresh_legend_views()

    def test_guise_with_deeds_and_spreads(self) -> None:
        """Guise with deeds and spreads returns correct total."""
        guise = GuiseFactory()
        entry1 = LegendEntryFactory(guise=guise, base_value=50, is_active=True)
        LegendSpreadFactory(legend_entry=entry1, value_added=10)
        entry2 = LegendEntryFactory(guise=guise, base_value=30, is_active=True)
        LegendSpreadFactory(legend_entry=entry2, value_added=5)
        self._refresh()
        row = GuiseLegendSummary.objects.get(guise_id=guise.pk)
        assert row.guise_legend == 95  # (50+10) + (30+5)

    def test_guise_with_no_deeds(self) -> None:
        """Guise with no deeds has guise_legend = 0."""
        guise = GuiseFactory()
        self._refresh()
        row = GuiseLegendSummary.objects.get(guise_id=guise.pk)
        assert row.guise_legend == 0

    def test_inactive_deed_excluded_from_guise(self) -> None:
        """Inactive deed excluded from guise legend total."""
        guise = GuiseFactory()
        LegendEntryFactory(guise=guise, base_value=100, is_active=False)
        LegendEntryFactory(guise=guise, base_value=25, is_active=True)
        self._refresh()
        row = GuiseLegendSummary.objects.get(guise_id=guise.pk)
        assert row.guise_legend == 25

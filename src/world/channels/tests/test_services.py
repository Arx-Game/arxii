"""Unit tests for player channel services (#3299).

Only what the Task 5 journeys cannot reach directly: the prune cap, the ORG identity
cascade edge cases, covert provisioning, the default identity and post-time revalidation.
"""

from unittest import mock

from django.test import TestCase
from django.utils import timezone

from world.channels.constants import PUBLIC_CHANNEL_NAME, ChannelKind
from world.channels.factories import (
    ChannelFactory,
    ChannelMessageFactory,
    ChannelSubscriptionFactory,
)
from world.channels.models import Channel, ChannelMessage
from world.channels.services import (
    accessible_channels_for,
    can_access_channel,
    default_tenure_for,
    eligible_tenures,
    ensure_public_channel,
    post_to_channel,
    provision_missing_org_channels,
    provision_org_channel,
    prune_channel_history,
)
from world.channels.types import ChannelError
from world.covenants.factories import CovenantFactory
from world.roster.factories import PlayerDataFactory, RosterTenureFactory
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory
from world.societies.houses.models import FealtyEdge


def _member(tenure, organization):
    return OrganizationMembershipFactory(
        organization=organization,
        persona=tenure.roster_entry.character_sheet.primary_persona,
    )


class PruneChannelHistoryTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.busy = ChannelFactory()
        cls.quiet = ChannelFactory()
        cls.busy_ids = [ChannelMessageFactory(channel=cls.busy).pk for _ in range(5)]
        cls.quiet_ids = [ChannelMessageFactory(channel=cls.quiet).pk for _ in range(2)]

    def test_keeps_newest_cap_per_channel(self) -> None:
        deleted = prune_channel_history(cap=3)

        self.assertEqual(deleted, 2)
        busy_left = set(
            ChannelMessage.objects.filter(channel=self.busy).values_list("pk", flat=True)
        )
        self.assertEqual(busy_left, set(self.busy_ids[-3:]))
        quiet_left = set(
            ChannelMessage.objects.filter(channel=self.quiet).values_list("pk", flat=True)
        )
        self.assertEqual(quiet_left, set(self.quiet_ids))


class OrgIdentityTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.house = OrganizationFactory()
        cls.vassal = OrganizationFactory()
        cls.covert_vassal = OrganizationFactory(is_covert=True)
        FealtyEdge.objects.create(vassal=cls.vassal, liege=cls.house)
        FealtyEdge.objects.create(vassal=cls.covert_vassal, liege=cls.house)
        # A non-covert house sworn under the covert vassal: the whole covert branch is cut.
        cls.under_covert = OrganizationFactory()
        FealtyEdge.objects.create(vassal=cls.under_covert, liege=cls.covert_vassal)
        cls.channel = provision_org_channel(cls.house)

        player = PlayerDataFactory()
        cls.account = player.account
        cls.member = RosterTenureFactory(player_data=player, player_number=1)
        cls.alt = RosterTenureFactory(player_data=player, player_number=1)
        cls.vassal_member = RosterTenureFactory(player_data=player, player_number=1)
        cls.covert_member = RosterTenureFactory(player_data=player, player_number=1)
        cls.under_covert_member = RosterTenureFactory(player_data=player, player_number=1)
        cls.ended = RosterTenureFactory(
            player_data=player, player_number=1, end_date=timezone.now()
        )
        _member(cls.member, cls.house)
        _member(cls.vassal_member, cls.vassal)
        _member(cls.covert_member, cls.covert_vassal)
        _member(cls.under_covert_member, cls.under_covert)
        _member(cls.ended, cls.house)

    def test_only_member_and_vassal_member_tenures_are_eligible(self) -> None:
        eligible = set(eligible_tenures(self.account, self.channel))

        self.assertEqual(eligible, {self.member, self.vassal_member})

    def test_member_only_under_a_covert_vassal_never_reaches_the_liege(self) -> None:
        tenure = RosterTenureFactory(player_number=1)
        _member(tenure, self.under_covert)
        account = tenure.player_data.account

        self.assertEqual(eligible_tenures(account, self.channel), [])
        self.assertFalse(can_access_channel(account, self.channel))
        self.assertNotIn(self.channel, accessible_channels_for(account))

    def test_default_tenure_is_none_when_puppet_is_ineligible(self) -> None:
        alt_character = self.alt.roster_entry.character_sheet.character
        with mock.patch.object(
            self.account, "get_puppeted_characters", return_value=[alt_character]
        ):
            self.assertIsNone(default_tenure_for(self.account, self.channel))

    def test_default_tenure_is_the_puppet_when_eligible(self) -> None:
        character = self.member.roster_entry.character_sheet.character
        with mock.patch.object(self.account, "get_puppeted_characters", return_value=[character]):
            self.assertEqual(default_tenure_for(self.account, self.channel), self.member)


class ProvisionTests(TestCase):
    def test_covert_org_gets_no_channel(self) -> None:
        self.assertIsNone(provision_org_channel(OrganizationFactory(is_covert=True)))

    def test_covenant_org_gets_no_channel_and_backfill_skips_it(self) -> None:
        # Covenant membership is CharacterCovenantRole, so its org channel would be
        # unreachable (ruling, #3299); the seed backfill gives the plain org its channel.
        covenant_org = CovenantFactory().organization
        plain = OrganizationFactory()

        self.assertIsNone(provision_org_channel(covenant_org))
        provision_missing_org_channels()

        self.assertFalse(Channel.objects.filter(organization=covenant_org).exists())
        self.assertTrue(Channel.objects.filter(organization=plain).exists())

    def test_name_clash_takes_org_suffix(self) -> None:
        org = OrganizationFactory()
        ChannelFactory(name=org.name)

        channel = provision_org_channel(org)

        self.assertEqual(channel.name, f"{org.name} (org)")
        self.assertEqual(channel.kind, ChannelKind.ORG)
        self.assertEqual(channel.display_name, org.name)

    def test_org_named_public_never_becomes_the_public_channel(self) -> None:
        org_channel = provision_org_channel(OrganizationFactory(name=PUBLIC_CHANNEL_NAME))

        public = ensure_public_channel()

        self.assertNotEqual(public, org_channel)
        self.assertEqual(public.kind, ChannelKind.PUBLIC)
        self.assertEqual(org_channel.display_name, PUBLIC_CHANNEL_NAME)


class LiveAccessTests(TestCase):
    """Access and identity are re-derived at use time; the subscription proves nothing."""

    def setUp(self) -> None:
        self.org = OrganizationFactory()
        self.channel = provision_org_channel(self.org)
        player = PlayerDataFactory()
        self.account = player.account
        self.tenure = RosterTenureFactory(player_data=player, player_number=1)
        self.membership = _member(self.tenure, self.org)
        ChannelSubscriptionFactory(
            account=self.account, channel=self.channel, display_tenure=self.tenure
        )

    def test_org_turned_covert_loses_access_and_listing(self) -> None:
        self.assertTrue(can_access_channel(self.account, self.channel))
        self.org.is_covert = True
        self.org.save(update_fields=["is_covert"])

        self.assertFalse(can_access_channel(self.account, self.channel))
        self.assertNotIn(self.channel, accessible_channels_for(self.account))

    def test_post_refused_after_leaving_through_a_second_tenure(self) -> None:
        # Still has access through another member tenure, but the chosen one left.
        other = RosterTenureFactory(player_data=self.tenure.player_data, player_number=1)
        _member(other, self.org)
        self.membership.left_at = timezone.now()
        self.membership.save(update_fields=["left_at"])

        with self.assertRaisesMessage(ChannelError, ChannelError.INELIGIBLE_IDENTITY):
            post_to_channel(account=self.account, channel=self.channel, body="hello")

    def test_post_refused_after_tenure_ended(self) -> None:
        other = RosterTenureFactory(player_data=self.tenure.player_data, player_number=1)
        _member(other, self.org)
        self.tenure.end_date = timezone.now()
        self.tenure.save(update_fields=["end_date"])

        with self.assertRaisesMessage(ChannelError, ChannelError.INELIGIBLE_IDENTITY):
            post_to_channel(account=self.account, channel=self.channel, body="hello")

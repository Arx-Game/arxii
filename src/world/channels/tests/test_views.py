"""API contract tests for player channels (#3299).

Only the contract points the Task 5 journeys do not naturally reach: the identity picker
lists only the requester's own eligible tenures as {id, label}; PATCHing an ineligible
or foreign tenure is a 400; the message list requires ``?channel=``; a blocked author's
row comes back hidden with no speaker or body.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from world.channels.factories import ChannelMessageFactory, ChannelSubscriptionFactory
from world.channels.services import ensure_public_channel, provision_org_channel
from world.roster.factories import PlayerDataFactory, RosterTenureFactory
from world.scenes.block_services import create_block
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory


class ChannelApiContractTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.house = OrganizationFactory()
        cls.org_channel = provision_org_channel(cls.house)
        cls.public = ensure_public_channel()

        cls.player = PlayerDataFactory()
        cls.account = cls.player.account
        cls.member = RosterTenureFactory(player_data=cls.player, player_number=1)
        cls.alt = RosterTenureFactory(player_data=cls.player, player_number=1)
        OrganizationMembershipFactory(
            organization=cls.house,
            persona=cls.member.roster_entry.character_sheet.primary_persona,
        )
        cls.subscription = ChannelSubscriptionFactory(
            account=cls.account, channel=cls.org_channel, display_tenure=cls.member
        )

        other = PlayerDataFactory()
        cls.foreign = RosterTenureFactory(player_data=other, player_number=2)

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(self.account)

    def test_identities_lists_only_own_eligible_tenures(self) -> None:
        response = self.client.get(f"/api/channels/channels/{self.org_channel.pk}/identities/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), [{"id": self.member.pk, "label": self.member.speaker_name}]
        )

    def test_patch_with_ineligible_alt_or_foreign_tenure_is_refused(self) -> None:
        url = f"/api/channels/subscriptions/{self.subscription.pk}/"

        alt = self.client.patch(url, {"display_tenure": self.alt.pk}, format="json")
        foreign = self.client.patch(url, {"display_tenure": self.foreign.pk}, format="json")

        self.assertEqual(alt.status_code, 400)
        self.assertIn("display_tenure", alt.json())
        self.assertEqual(foreign.status_code, 400)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.display_tenure, self.member)

    def test_message_list_requires_channel(self) -> None:
        response = self.client.get("/api/channels/messages/")

        self.assertEqual(response.status_code, 400)
        self.assertIn("channel", response.json())

    def test_blocked_author_row_is_hidden(self) -> None:
        message = ChannelMessageFactory(channel=self.public, author_tenure=self.foreign)
        create_block(
            blocker_account=self.account,
            blocker_persona=self.member.roster_entry.character_sheet.primary_persona,
            blocked_persona=self.foreign.roster_entry.character_sheet.primary_persona,
            reason="test",
            account_level=True,
        )

        response = self.client.get(f"/api/channels/messages/?channel={self.public.pk}")

        self.assertEqual(response.status_code, 200)
        row = response.json()["results"][0]
        self.assertEqual(row["id"], message.pk)
        self.assertEqual((row["is_hidden"], row["speaker"], row["body"]), (True, "", ""))
        self.assertNotIn("author_tenure", row)

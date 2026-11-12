"""API contract tests for player channels (#3299).

Only the contract points the Task 5 journeys do not naturally reach: the identity picker
lists only the requester's own eligible tenures as {id, label}; PATCHing an ineligible
or foreign tenure is a 400; the message list requires ``?channel=``; a blocked author's
row comes back hidden with no speaker or body; staff read every org channel while a
non-member is told nothing exists; moderation is staff-only; and a client cannot act as
another account by slipping ``account`` into dispatch kwargs.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from actions.constants import ActionBackend
from actions.definitions.channels import LeaveChannelAction
from actions.player_interface import dispatch_player_action
from actions.types import ActionRef
from evennia_extensions.factories import AccountFactory
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
        cls.outsider = other.account
        cls.foreign_subscription = ChannelSubscriptionFactory(
            account=cls.outsider, channel=cls.public
        )
        cls.org_message = ChannelMessageFactory(channel=cls.org_channel, author_tenure=cls.member)
        cls.staff = AccountFactory(is_staff=True)

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

    def test_staff_read_org_channel_a_non_member_cannot_see_it(self) -> None:
        org_messages = f"/api/channels/messages/?channel={self.org_channel.pk}"
        self.client.force_authenticate(self.staff)
        staff_list = self.client.get("/api/channels/channels/").json()
        staff_history = self.client.get(org_messages).json()["results"]

        self.client.force_authenticate(self.outsider)
        outsider_list = self.client.get("/api/channels/channels/").json()
        outsider_history = self.client.get(org_messages).json()["results"]
        join_org = self.client.post(
            "/api/channels/subscriptions/", {"channel": self.org_channel.pk}, format="json"
        )
        join_missing = self.client.post(
            "/api/channels/subscriptions/", {"channel": 999999}, format="json"
        )

        self.assertIn(self.org_channel.pk, [row["id"] for row in staff_list])
        self.assertEqual([row["id"] for row in staff_history], [self.org_message.pk])
        self.assertNotIn(self.org_channel.pk, [row["id"] for row in outsider_list])
        self.assertEqual(outsider_history, [])
        self.assertEqual(join_org.status_code, 400)
        self.assertEqual(
            join_org.json()["channel"][0].replace(str(self.org_channel.pk), "N"),
            join_missing.json()["channel"][0].replace("999999", "N"),
        )

    def test_moderation_is_staff_only_and_others_rows_are_not_found(self) -> None:
        message_url = f"/api/channels/messages/{self.org_message.pk}/"

        delete = self.client.delete(message_url)
        ban = self.client.post(f"{message_url}ban/", {}, format="json")
        patch = self.client.patch(
            f"/api/channels/subscriptions/{self.foreign_subscription.pk}/",
            {"muted": True},
            format="json",
        )

        self.assertEqual((delete.status_code, ban.status_code), (403, 403))
        self.assertEqual(patch.status_code, 404)

    def test_forged_account_in_dispatch_kwargs_changes_nothing(self) -> None:
        attacker = self.member.roster_entry.character_sheet.character
        forged = {"account": self.outsider.pk, "channel_id": self.public.pk}

        for key, extra in (("leave_channel", {}), ("set_channel_mute", {"muted": True})):
            ref = ActionRef(backend=ActionBackend.REGISTRY, registry_key=key)
            result = dispatch_player_action(attacker, ref, {**forged, **extra})
            self.assertFalse(result.detail.success)
        direct = LeaveChannelAction().run(
            actor=None, account=self.outsider.pk, channel_id=self.public.pk
        )

        self.assertFalse(direct.success)
        self.foreign_subscription.refresh_from_db()
        self.assertFalse(self.foreign_subscription.muted)

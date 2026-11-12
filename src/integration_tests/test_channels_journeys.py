"""Player channels (#3299): talking out of character on named channels.

A player joins the game-wide Public channel or her organization's channel from telnet
(``channel ...`` through the real handler) or the web (``/api/channels/``), speaks as a
character she chooses, and hears the others live: a browser tab gets one
``channel_message`` frame and never a plain text line (that would land in the IC feed),
a MUD client gets the text line. Nobody is ever shown an account name.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from evennia.comms.models import ChannelDB

from actions.definitions.channels import PostToChannelAction
from evennia_extensions.factories import AccountFactory, CharacterFactory
from integration_tests.harness import JourneyCase
from world.channels.models import Channel, ChannelMessage, ChannelSubscription
from world.channels.services import ensure_public_channel, provision_org_channel
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.roster.models import RosterTenure
from world.scenes.block_services import create_block
from world.scenes.constants import PersonaType
from world.scenes.mute_services import set_mute
from world.scenes.services import create_persona
from world.societies.factories import OrganizationFactory
from world.societies.houses.services import swear_fealty
from world.societies.membership_services import join_organization, leave_organization

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB
    from rest_framework.response import Response

    from world.societies.models import Organization, OrganizationMembership

CHANNELS = "/api/channels/channels/"
SUBSCRIPTIONS = "/api/channels/subscriptions/"
MESSAGES = "/api/channels/messages/"


class ChannelJourneyCase(JourneyCase):
    """Shared world: a room, the Public channel, and helpers that act as a player would."""

    def setUp(self) -> None:
        super().setUp()
        self.room = self.make_room("The Lantern")
        self.public = ensure_public_channel()

    def player(self, name: str) -> ObjectDB:
        """A played character whose player is its first: she speaks as plain ``name``."""
        character = self.make_player(name, room=self.room)
        tenure = self.tenure_of(character)
        tenure.player_number = 1
        tenure.save(update_fields=["player_number"])
        return character

    def alt_of(self, main: ObjectDB, name: str) -> ObjectDB:
        """A second character the same account plays (its first player too)."""
        character = CharacterFactory(db_key=name, location=self.room)
        CharacterSheetFactory(character=character)
        entry = RosterEntryFactory(character_sheet__character=character)
        RosterTenureFactory(
            roster_entry=entry,
            player_data=self.account_of(main).player_data,
            end_date=None,
            player_number=1,
        )
        return character

    @staticmethod
    def tenure_of(character: ObjectDB) -> RosterTenure:
        return RosterTenure.objects.get(
            roster_entry__character_sheet__character=character, end_date__isnull=True
        )

    @staticmethod
    def join(character: ObjectDB, organization: Organization) -> OrganizationMembership:
        return join_organization(organization, character.sheet_data.primary_persona)

    def subscribe_web(self, account: AccountDB, channel: Channel, **prefs: Any) -> Response:
        response = self.api(account).post(
            SUBSCRIPTIONS, {"channel": channel.pk, **prefs}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response

    def post_web(self, account: AccountDB, channel: Channel, body: str) -> Response:
        return self.api(account).post(
            MESSAGES, {"channel": channel.pk, "body": body}, format="json"
        )

    def history(self, account: AccountDB, channel: Channel) -> list[dict[str, Any]]:
        response = self.api(account).get(MESSAGES, {"channel": channel.pk})
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["results"]

    def listed_names(self, account: AccountDB) -> list[str]:
        response = self.api(account).get(CHANNELS)
        self.assertEqual(response.status_code, 200, response.content)
        return [row["name"] for row in response.json()]

    def frames(self, session: MagicMock) -> list[dict[str, Any]]:
        """The ``channel_message`` payloads a browser session was pushed."""
        return [payload for _args, payload in self.session_frames(session, "channel_message")]


class TalkingOnPublic(ChannelJourneyCase):
    def setUp(self) -> None:
        super().setUp()
        self.ysmay = self.player("Ysmay")
        self.hobb = self.player("Hobb")
        self.ysmay_account = self.account_of(self.ysmay)
        self.hobb_account = self.account_of(self.hobb)

    def test_a_telnet_greeting_reaches_a_browser_as_one_frame(self) -> None:
        ysmay_client = self.connect_session(self.ysmay_account, "telnet")
        hobb_tab = self.connect_session(self.hobb_account, "websocket")
        # Hobb plays in hidden mode, which the settings page promises keeps channels.
        hobb_player = self.hobb_account.player_data
        hobb_player.private_mode = True
        hobb_player.save(update_fields=["private_mode"])
        # Hobb has no puppet: he joins and speaks from the web as his selected character.
        joined = self.subscribe_web(self.hobb_account, self.public)
        self.assertEqual(joined.json()["display_label"], "Hobb")

        told = self.telnet(self.ysmay, "channel join public")
        self.assertIn("You join Public. You speak as Ysmay.", told)
        picker = self.telnet(self.ysmay, "channel as public")
        self.assertIn("1. Ysmay", picker)
        self.assertIn(
            "In Public you now speak as Ysmay.", self.telnet(self.ysmay, "channel as public=1")
        )
        self.telnet(self.ysmay, "channel public=Hello all")

        frames = self.frames(hobb_tab)
        self.assertEqual(len(frames), 1)
        self.assertEqual(
            set(frames[0]),
            {
                "message_id",
                "channel_id",
                "channel_name",
                "speaker",
                "body",
                "created_at",
                "is_own",
                "notification_level",
                # Evennia's send path adds the message options to every frame's kwargs.
                "options",
            },
        )
        self.assertEqual(frames[0]["channel_id"], self.public.pk)
        self.assertEqual(frames[0]["speaker"], "Ysmay")
        self.assertEqual(frames[0]["body"], "Hello all")
        self.assertEqual(frames[0]["channel_name"], "Public")
        self.assertFalse(frames[0]["is_own"])
        self.assertEqual(self.session_frames(hobb_tab, "text"), [])
        # Her own MUD client hears the echo as a line, never a frame.
        self.assertEqual(
            self.session_frames(ysmay_client, "text"),
            [(["[Public] Ysmay: Hello all"], {"type": "channel", "options": {}})],
        )
        self.assertEqual(self.session_frames(ysmay_client, "channel_message"), [])

        rows = self.history(self.hobb_account, self.public)
        self.assertEqual([(r["speaker"], r["body"]) for r in rows], [("Ysmay", "Hello all")])
        self.assertNotIn("author_tenure", rows[0])

        # Hobb answers from the web with no puppet; her client hears him by character name.
        reply = self.post_web(self.hobb_account, self.public, "Evening, Ysmay.")
        self.assertEqual(reply.status_code, 201, reply.content)
        self.assertEqual(reply.json()["speaker"], "Hobb")
        self.assertIn(
            "[Public] Hobb: Evening, Ysmay.",
            [args[0] for args, _options in self.session_frames(ysmay_client, "text")],
        )

        # No surface names either account.
        bodies = [
            joined.content,
            reply.content,
            self.api(self.hobb_account).get(MESSAGES, {"channel": self.public.pk}).content,
            self.api(self.hobb_account).get(CHANNELS).content,
            self.api(self.hobb_account).get(SUBSCRIPTIONS).content,
            self.api(self.hobb_account).get(f"{CHANNELS}{self.public.pk}/identities/").content,
        ]
        for username in (self.ysmay_account.username, self.hobb_account.username):
            for body in bodies:
                self.assertNotIn(username.encode(), body)
            self.assertNotTold(self.ysmay, username)
            for frame in frames:
                self.assertNotIn(username, str(frame))

    def test_a_web_dispatch_cannot_act_as_another_account(self) -> None:
        # Ysmay is joined and has a speaking identity, so her real account object, slipped
        # into Hobb's dispatch kwargs, would act for her if dispatch let it through.
        ysmay_tab = self.connect_session(self.ysmay_account, "websocket")
        self.subscribe_web(self.ysmay_account, self.public)
        forged = {"account": self.ysmay_account, "channel_id": self.public.pk}

        for key, extra in (
            ("post_to_channel", {"body": "forged"}),
            ("set_channel_mute", {"muted": True}),
            ("leave_channel", {}),
        ):
            result = self.web(self.hobb, key, **forged, **extra)
            self.assertFalse(result.detail.success, key)
            self.assertEqual(result.detail.message, "You must be logged in to use channels.")

        self.assertFalse(ChannelMessage.objects.filter(body="forged").exists())
        self.assertEqual(self.frames(ysmay_tab), [])
        subscription = ChannelSubscription.objects.get(
            account=self.ysmay_account, channel=self.public
        )
        self.assertFalse(subscription.muted)

    def test_a_channel_id_that_is_not_a_number_answers_as_missing(self) -> None:
        # Not through web(): dispatch drops ``account``, so every channel action refuses
        # there before it reads a channel. The action runs with the signed-in account, as
        # the REST view and the telnet command run it. "\u00b2" (superscript two) passes
        # str.isdigit() but int() refuses it.
        result = PostToChannelAction().run(
            actor=None, account=self.hobb_account, channel_id="\u00b2", body="hi"
        )
        self.assertFalse(result.success)
        self.assertEqual(result.message, "No such channel.")

    def test_the_stock_evennia_channel_command_is_gone(self) -> None:
        listing = self.telnet(self.ysmay, "channel")
        self.assertIn("Public (Public) - not joined", listing)
        # The @ prefix is stripped by the handler and reaches the same command.
        self.assertIn("Public (Public) - not joined", self.telnet(self.ysmay, "@channel"))
        # Evennia's "pub" nick and its Public ChannelDB row are retired.
        self.assertFalse(ChannelDB.objects.filter(db_key__iexact="public").exists())
        told = self.telnet(self.ysmay, "pub hello")
        self.assertIn("Command 'pub hello' is not available.", told)
        self.assertFalse(ChannelMessage.objects.filter(body="hello").exists())
        self.assertNotIn("[Public]", told)


class TalkingInYourOrganization(ChannelJourneyCase):
    def setUp(self) -> None:
        super().setUp()
        self.order = OrganizationFactory(name="Lantern Wardens")
        self.channel = provision_org_channel(self.order)
        self.ysmay = self.player("Ysmay")
        self.bryn = self.alt_of(self.ysmay, "Bryn")
        self.corin = self.player("Corin")
        self.hobb = self.player("Hobb")
        self.ysmay_account = self.account_of(self.ysmay)
        self.ysmay_membership = self.join(self.ysmay, self.order)
        self.join(self.corin, self.order)

    def test_a_member_speaks_as_her_member_and_never_as_her_alt(self) -> None:
        self.assertIn("Lantern Wardens", self.listed_names(self.ysmay_account))
        sub = self.subscribe_web(self.ysmay_account, self.channel).json()
        self.assertEqual(sub["display_label"], "Ysmay")
        identities = self.api(self.ysmay_account).get(f"{CHANNELS}{self.channel.pk}/identities/")
        self.assertEqual(
            identities.json(), [{"id": self.tenure_of(self.ysmay).pk, "label": "Ysmay"}]
        )

        refused = self.api(self.ysmay_account).patch(
            f"{SUBSCRIPTIONS}{sub['id']}/",
            {"display_tenure": self.tenure_of(self.bryn).pk},
            format="json",
        )
        self.assertEqual(refused.status_code, 400)
        self.assertEqual(
            refused.json()["display_tenure"], ["That character can't speak in this channel."]
        )
        # Another account's tenure is refused as an unknown id, confirming nothing about it.
        foreign = self.api(self.ysmay_account).patch(
            f"{SUBSCRIPTIONS}{sub['id']}/",
            {"display_tenure": self.tenure_of(self.hobb).pk},
            format="json",
        )
        self.assertEqual(foreign.status_code, 400)
        self.assertIn("display_tenure", foreign.json())
        self.assertNotIn("Hobb", foreign.content.decode())
        self.assertEqual(
            self.api(self.ysmay_account)
            .get(f"{SUBSCRIPTIONS}{sub['id']}/")
            .json()["display_label"],
            "Ysmay",
        )

        posted = self.post_web(self.ysmay_account, self.channel, "Muster at dusk.")
        self.assertEqual(posted.status_code, 201, posted.content)
        self.assertEqual(posted.json()["speaker"], "Ysmay")

    def test_a_non_member_is_told_nothing_exists(self) -> None:
        hobb_account = self.account_of(self.hobb)

        self.assertNotIn("Lantern Wardens", self.listed_names(hobb_account))
        joined = self.api(hobb_account).post(
            SUBSCRIPTIONS, {"channel": self.channel.pk}, format="json"
        )
        self.assertEqual(joined.status_code, 400)
        posted = self.post_web(hobb_account, self.channel, "Let me in.")
        self.assertEqual(posted.status_code, 400)
        self.assertEqual(posted.json()["detail"], "No such channel.")
        self.assertIn("No such channel.", self.telnet(self.hobb, "channel join Lantern Wardens"))
        self.assertEqual(self.history(hobb_account, self.channel), [])

    def test_a_membership_held_by_a_hidden_face_does_not_open_the_channel(self) -> None:
        # Hobb's alter ego, a face whose link to him stays hidden, is the Wardens' member;
        # Hobb himself is not. Speaking there as Hobb would tell the room who the face is.
        hobb_account = self.account_of(self.hobb)
        face = create_persona(
            self.hobb.sheet_data, name="The Grey Lamp", persona_type=PersonaType.ESTABLISHED
        )
        join_organization(self.order, face)

        self.assertNotIn("Lantern Wardens", self.listed_names(hobb_account))
        self.assertIn("No such channel.", self.telnet(self.hobb, "channel join Lantern Wardens"))
        joined = self.api(hobb_account).post(
            SUBSCRIPTIONS, {"channel": self.channel.pk}, format="json"
        )
        self.assertEqual(joined.status_code, 400)
        posted = self.post_web(hobb_account, self.channel, "Evening, Wardens.")
        self.assertEqual(posted.status_code, 400)
        self.assertEqual(posted.json()["detail"], "No such channel.")
        self.assertFalse(ChannelMessage.objects.filter(channel=self.channel).exists())

    def test_leaving_the_organization_loses_the_channel_at_once(self) -> None:
        ysmay_tab = self.connect_session(self.ysmay_account, "websocket")
        self.subscribe_web(self.ysmay_account, self.channel)
        corin_account = self.account_of(self.corin)
        self.subscribe_web(corin_account, self.channel)
        self.assertEqual(self.post_web(corin_account, self.channel, "Muster.").status_code, 201)
        self.assertEqual([f["body"] for f in self.frames(ysmay_tab)], ["Muster."])

        leave_organization(self.ysmay_membership)

        self.assertNotIn("Lantern Wardens", self.listed_names(self.ysmay_account))
        subs = self.api(self.ysmay_account).get(SUBSCRIPTIONS).json()
        self.assertNotIn(self.channel.pk, [row["channel"] for row in subs])
        refused = self.post_web(self.ysmay_account, self.channel, "Still here?")
        self.assertEqual(refused.status_code, 400)
        self.assertEqual(refused.json()["detail"], "You don't have access to that channel.")
        self.assertEqual(self.post_web(corin_account, self.channel, "She's gone.").status_code, 201)
        self.assertEqual([f["body"] for f in self.frames(ysmay_tab)], ["Muster."])
        # Her row survives, so she can still leave it.
        self.assertIn(
            "You leave Lantern Wardens.", self.telnet(self.ysmay, "channel leave Lantern Wardens")
        )
        self.assertFalse(
            ChannelSubscription.objects.filter(
                account=self.ysmay_account, channel=self.channel
            ).exists()
        )


class CovertAndVassalHouses(ChannelJourneyCase):
    def test_a_covert_organization_never_has_a_channel(self) -> None:
        cabal = OrganizationFactory(name="The Quiet Hand", is_covert=True)
        self.assertIsNone(provision_org_channel(cabal))
        self.assertFalse(Channel.objects.filter(organization=cabal).exists())

        ysmay = self.player("Ysmay")
        self.join(ysmay, cabal)
        account = self.account_of(ysmay)
        self.assertEqual(self.listed_names(account), ["Public"])
        self.assertNotIn("Quiet Hand", self.telnet(ysmay, "channel"))
        self.assertIn("No such channel.", self.telnet(ysmay, "channel join The Quiet Hand"))

    def test_a_vassal_member_speaks_in_her_lieges_channel_and_a_covert_vassal_does_not(
        self,
    ) -> None:
        liege = OrganizationFactory(name="House Corve")
        vassal = OrganizationFactory(name="House Elm")
        covert = OrganizationFactory(name="House Ash", is_covert=True)
        swear_fealty(vassal=vassal, liege=liege)
        swear_fealty(vassal=covert, liege=liege)
        channel = provision_org_channel(liege)

        hobb = self.player("Hobb")
        self.join(hobb, liege)
        hobb_tab = self.connect_session(self.account_of(hobb), "websocket")
        self.subscribe_web(self.account_of(hobb), channel)

        ysmay = self.player("Ysmay")
        self.join(ysmay, vassal)
        self.assertIn("House Corve (Organization) - not joined", self.telnet(ysmay, "channel"))
        self.assertIn(
            "You join House Corve. You speak as Ysmay.",
            self.telnet(ysmay, "channel join House Corve"),
        )
        self.telnet(ysmay, "channel House Corve=Elm stands with Corve.")
        self.assertEqual(
            [(f["speaker"], f["body"]) for f in self.frames(hobb_tab)],
            [("Ysmay", "Elm stands with Corve.")],
        )

        corin = self.player("Corin")
        self.join(corin, covert)
        corin_account = self.account_of(corin)
        self.assertNotIn("House Corve", self.listed_names(corin_account))
        self.assertIn("No such channel.", self.telnet(corin, "channel join House Corve"))
        refused = self.api(corin_account).post(
            SUBSCRIPTIONS, {"channel": channel.pk}, format="json"
        )
        self.assertEqual(refused.status_code, 400)


class BlocksMutesAndControls(ChannelJourneyCase):
    def setUp(self) -> None:
        super().setUp()
        self.ysmay = self.player("Ysmay")
        self.hobb = self.player("Hobb")
        self.ysmay_account = self.account_of(self.ysmay)
        self.hobb_account = self.account_of(self.hobb)
        self.hobb_tab = self.connect_session(self.hobb_account, "websocket")
        self.subscribe_web(self.ysmay_account, self.public)
        self.hobb_sub = self.subscribe_web(self.hobb_account, self.public).json()

    def test_a_blocked_author_shows_as_a_hidden_row_and_is_never_pushed(self) -> None:
        create_block(
            blocker_account=self.hobb_account,
            blocker_persona=self.hobb.sheet_data.primary_persona,
            blocked_persona=self.ysmay.sheet_data.primary_persona,
            reason="Not tonight.",
            account_level=True,
        )
        self.assertEqual(self.post_web(self.ysmay_account, self.public, "Hi Hobb").status_code, 201)

        self.assertEqual(self.frames(self.hobb_tab), [])
        rows = self.history(self.hobb_account, self.public)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["is_hidden"])
        self.assertEqual((rows[0]["speaker"], rows[0]["body"]), ("", ""))

    def test_a_block_on_one_character_hides_that_character_behind_the_divider(self) -> None:
        # The ordinary persona-scoped block: Hobb blocks Ysmay's face, not her player.
        create_block(
            blocker_account=self.hobb_account,
            blocker_persona=self.hobb.sheet_data.primary_persona,
            blocked_persona=self.ysmay.sheet_data.primary_persona,
            reason="Not tonight.",
            account_level=False,
        )
        self.assertEqual(self.post_web(self.ysmay_account, self.public, "Hi Hobb").status_code, 201)

        self.assertEqual(self.frames(self.hobb_tab), [])
        rows = self.history(self.hobb_account, self.public)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["is_hidden"])
        self.assertEqual((rows[0]["speaker"], rows[0]["body"]), ("", ""))
        listed = self.api(self.hobb_account).get(SUBSCRIPTIONS).json()
        self.assertEqual(listed[0]["unread_count"], 0)
        # Mutual: Ysmay does not hear Hobb either.
        ysmay_tab = self.connect_session(self.ysmay_account, "websocket")
        self.assertEqual(self.post_web(self.hobb_account, self.public, "Evening.").status_code, 201)
        self.assertEqual(self.frames(ysmay_tab), [])

    def test_an_account_muted_author_is_dropped(self) -> None:
        set_mute(
            owner=self.hobb_account.player_data,
            muted_persona=self.ysmay.sheet_data.primary_persona,
            account_level=True,
        )
        self.assertEqual(self.post_web(self.ysmay_account, self.public, "Hi Hobb").status_code, 201)

        self.assertEqual(self.frames(self.hobb_tab), [])
        self.assertEqual(self.history(self.hobb_account, self.public), [])

    def test_channel_controls_persist_and_a_muted_channel_is_quiet_but_readable(self) -> None:
        url = f"{SUBSCRIPTIONS}{self.hobb_sub['id']}/"
        changed = self.api(self.hobb_account).patch(
            url,
            {"muted": True, "collapsed": True, "notification_level": "badge", "sort_order": 3},
            format="json",
        )
        self.assertEqual(changed.status_code, 200, changed.content)

        row = self.api(self.hobb_account).get(url).json()
        self.assertEqual(
            (row["muted"], row["collapsed"], row["notification_level"], row["sort_order"]),
            (True, True, "badge", 3),
        )
        self.assertIn(
            "Public (Public) - muted, speaking as Hobb", self.telnet(self.hobb, "channel")
        )

        self.post_web(self.ysmay_account, self.public, "Anyone awake?")
        self.assertEqual(self.frames(self.hobb_tab), [])
        self.assertEqual(
            [r["body"] for r in self.history(self.hobb_account, self.public)], ["Anyone awake?"]
        )
        listed = self.api(self.hobb_account).get(SUBSCRIPTIONS).json()
        self.assertEqual(listed[0]["unread_count"], 0)

        self.assertIn("You unmute Public.", self.telnet(self.hobb, "channel unmute public"))
        self.post_web(self.ysmay_account, self.public, "Now?")
        self.assertEqual([f["body"] for f in self.frames(self.hobb_tab)], ["Now?"])


class StaffModeration(ChannelJourneyCase):
    def setUp(self) -> None:
        super().setUp()
        self.ysmay = self.player("Ysmay")
        self.hobb = self.player("Hobb")
        self.ysmay_account = self.account_of(self.ysmay)
        self.hobb_account = self.account_of(self.hobb)
        self.staff = AccountFactory(is_staff=True)
        self.subscribe_web(self.ysmay_account, self.public)
        self.subscribe_web(self.hobb_account, self.public)
        posted = self.post_web(self.ysmay_account, self.public, "Something cruel.")
        self.message_id = posted.json()["id"]

    def test_a_deleted_message_is_gone_for_every_reader(self) -> None:
        self.assertEqual(len(self.history(self.hobb_account, self.public)), 1)
        hobb_tab = self.connect_session(self.hobb_account, "websocket")
        hobb_client = self.connect_session(self.hobb_account, "telnet")
        deleted = self.api(self.staff).delete(f"{MESSAGES}{self.message_id}/")
        self.assertEqual(deleted.status_code, 204)
        # An open browser tab drops the row at once; a MUD client is told nothing.
        removed = self.session_frames(hobb_tab, "channel_message_removed")
        self.assertEqual(len(removed), 1)
        self.assertEqual(removed[0][1]["message_id"], self.message_id)
        self.assertEqual(removed[0][1]["channel_id"], self.public.pk)
        self.assertEqual(self.session_frames(hobb_client, "channel_message_removed"), [])
        self.assertEqual(self.session_frames(hobb_client, "text"), [])
        self.assertEqual(self.history(self.hobb_account, self.public), [])
        self.assertEqual(self.history(self.ysmay_account, self.public), [])

    def test_staff_read_an_org_channel_a_non_member_cannot_find(self) -> None:
        order = OrganizationFactory(name="Lantern Wardens")
        channel = provision_org_channel(order)
        self.join(self.ysmay, order)
        self.subscribe_web(self.ysmay_account, channel)
        self.post_web(self.ysmay_account, channel, "Muster at dusk.")

        self.assertIn("Lantern Wardens", self.listed_names(self.staff))
        self.assertEqual(
            [row["body"] for row in self.history(self.staff, channel)], ["Muster at dusk."]
        )

        self.assertNotIn("Lantern Wardens", self.listed_names(self.hobb_account))
        self.assertEqual(self.history(self.hobb_account, channel), [])
        # Joining a real org channel he can't reach reads exactly like joining a missing one.
        real = self.api(self.hobb_account).post(
            SUBSCRIPTIONS, {"channel": channel.pk}, format="json"
        )
        missing = self.api(self.hobb_account).post(
            SUBSCRIPTIONS, {"channel": 999999}, format="json"
        )
        self.assertEqual((real.status_code, missing.status_code), (400, 400))
        self.assertEqual(
            real.json()["channel"][0].replace(str(channel.pk), "N"),
            missing.json()["channel"][0].replace("999999", "N"),
        )

    def test_a_banned_author_cannot_rejoin_or_post(self) -> None:
        banned = self.api(self.staff).post(
            f"{MESSAGES}{self.message_id}/ban/", {"reason": "Cruelty."}, format="json"
        )
        self.assertEqual(banned.status_code, 200, banned.content)
        self.assertEqual(
            banned.json()["detail"], "The player speaking as Ysmay is banned from Public."
        )
        self.assertNotIn(self.ysmay_account.username.encode(), banned.content)

        self.assertIn(
            "You are banned from that channel.", self.telnet(self.ysmay, "channel join public")
        )
        refused = self.post_web(self.ysmay_account, self.public, "Let me back.")
        self.assertEqual(refused.status_code, 400)
        self.assertEqual(refused.json()["detail"], "You are banned from that channel.")
        self.assertNotIn("Public", self.listed_names(self.ysmay_account))

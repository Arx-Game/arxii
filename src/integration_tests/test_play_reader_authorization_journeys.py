"""Journeys for the narrative-play reader's privacy rules (#3751, gates A11 to A13).

The play reader reaches one pose through several doors: the interaction list and detail,
play search, play context, the conversation and thread summaries (which carry the
participants a conversation names and the unread counts), and the top bar's attention
badges. Each journey states one rule a viewer is promised and checks every door against
it, driving the game the way a player does: lines typed through the command handler,
everything read back over REST.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any

from django.utils import timezone

from evennia_extensions.factories import AccountFactory
from evennia_extensions.models import PlayerData
from integration_tests.harness import JourneyCase
from world.game_clock.week_services import get_current_game_week
from world.progression.constants import NominationTargetType
from world.roster.factories import RosterTenureFactory
from world.scenes.block_services import create_block
from world.scenes.factories import SceneGMParticipationFactory
from world.scenes.interaction_services import record_interaction
from world.scenes.models import Interaction, Scene
from world.scenes.mute_services import set_mute
from world.scenes.services import record_persona_discovery
from world.scenes.thread_services import InteractionThreadError, ReplyTarget
from world.species.factories import LanguageFactory
from world.traits.factories import CharacterTraitValueFactory
from world.traits.models import Trait, TraitCategory, TraitType

CARAVAN = "The caravan leaves at dawn through the salt gate."


@dataclass
class Seen:
    """What one viewer is shown about one pose, door by door."""

    listed: dict[int, dict[str, Any]] = field(default_factory=dict)
    detail_status: int = 0
    detail_content: str | None = None
    searched: list[int] = field(default_factory=list)
    context_status: int = 0
    context: dict[int, dict[str, Any]] = field(default_factory=dict)
    bodies: str = ""

    @property
    def hidden_everywhere(self) -> bool:
        return (
            not self.listed
            and self.detail_status in (403, 404)
            and not self.searched
            and self.context_status == 404
        )


class PlayReaderJourney(JourneyCase):
    """Ysmay, Hobb, Wat and Bram share the Lantern while Ysmay's scene runs."""

    def setUp(self) -> None:
        super().setUp()
        self.lantern = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)
        self.wat = self.make_player("Wat", room=self.lantern)
        self.telnet(self.ysmay, "scene start")
        self.scene = Scene.objects.active_for_room(self.lantern).get()
        self.telnet(self.hobb, "pose nods to the room.")

    # -- reading ---------------------------------------------------------------

    def get(self, viewer_account, url: str, params: dict[str, Any] | None = None):
        return self.api(viewer_account).get(url, params or {})

    def pose_of(self, character, content: str) -> Interaction:
        return Interaction.objects.filter(persona__character_sheet=character.pk).get(
            content=content
        )

    def seen_by(self, account, pose: Interaction, *, term: str, bound: dict[str, str]) -> Seen:
        """Read ``pose`` through list, detail, search and context as ``account``."""
        seen = Seen()
        bodies: list[Any] = []
        listing = self.get(account, "/api/interactions/", {"scene": self.scene.pk})
        self.assertEqual(listing.status_code, 200, listing.content)
        bodies.append(listing.data)
        seen.listed = {row["id"]: row for row in listing.data["results"] if row["id"] == pose.pk}
        detail = self.get(account, f"/api/interactions/{pose.pk}/")
        seen.detail_status = detail.status_code
        bodies.append(detail.data)
        if detail.status_code == 200:
            seen.detail_content = detail.data["content"]
        search = self.get(account, "/api/play/search/", {"q": term, **bound})
        self.assertEqual(search.status_code, 200, search.content)
        bodies.append(search.data)
        seen.searched = [int(row["pose"]["id"]) for row in search.data["results"]]
        context = self.get(
            account,
            "/api/play/context/",
            {"id": pose.pk, "timestamp": pose.timestamp.isoformat()},
        )
        seen.context_status = context.status_code
        bodies.append(context.data)
        if context.status_code == 200:
            seen.context = {row["id"]: row for row in context.data["results"]}
        seen.bodies = json.dumps(bodies, default=str)
        return seen

    def conversations(self, account) -> list[dict[str, Any]]:
        """The navigator's summaries: the participants each names and its unread counts."""
        response = self.get(account, "/api/play/conversations/")
        self.assertEqual(response.status_code, 200, response.content)
        return response.data["results"]

    def threads(self, account) -> list[dict[str, Any]]:
        response = self.get(
            account, "/api/play/threads/", {"conversation": f"scene:{self.scene.pk}"}
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response.data["results"]

    def badges(self, account) -> list[dict[str, Any]]:
        """The top bar's attention badges for every character ``account`` plays."""
        response = self.get(account, "/api/roster/entries/mine/")
        self.assertEqual(response.status_code, 200, response.content)
        return list(response.data)

    def badge_of(self, character) -> dict[str, Any]:
        """The top bar's attention badge for ``character``, as its player reads it."""
        rows = self.badges(self.account_of(character))
        return next(row for row in rows if row["name"] == character.key)

    def reply(self, character, parent: Interaction, content: str) -> Interaction:
        """``character`` answers ``parent`` through the writer a typed pose goes through."""
        reply = record_interaction(
            character=character,
            content=content,
            mode=parent.mode,
            scene=self.scene,
            reply_to=ReplyTarget(interaction_id=parent.pk, timestamp=parent.timestamp),
        )
        self.assertIsNotNone(reply)
        return reply

    @property
    def scene_bound(self) -> dict[str, str]:
        return {"conversation": f"scene:{self.scene.pk}"}


class ABlockedFaceIsHiddenEverywhere(PlayReaderJourney):
    """Hobb blocks Ysmay's face: neither sees the other, through any door."""

    def block(self) -> None:
        create_block(
            blocker_account=self.account_of(self.hobb),
            blocker_persona=self.hobb.sheet_data.primary_persona,
            blocked_persona=self.ysmay.sheet_data.primary_persona,
            reason="Journey block.",
        )

    def test_the_blocked_face_is_absent_from_every_door_both_ways(self) -> None:
        self.block()
        self.telnet(self.ysmay, f"pose {CARAVAN}")
        self.telnet(self.hobb, "pose pulls the door shut behind him.")
        from_ysmay = self.pose_of(self.ysmay, CARAVAN)
        from_hobb = self.pose_of(self.hobb, "pulls the door shut behind him.")

        for viewer, pose, term in (
            (self.hobb, from_ysmay, "caravan"),
            (self.ysmay, from_hobb, "pulls the door"),
        ):
            with self.subTest(viewer=viewer.key):
                seen = self.seen_by(
                    self.account_of(viewer), pose, term=term, bound=self.scene_bound
                )
                self.assertTrue(seen.hidden_everywhere, seen)

        # The people left in the scene still read the whole of it.
        wat = self.seen_by(
            self.account_of(self.wat), from_ysmay, term="caravan", bound=self.scene_bound
        )
        self.assertEqual(wat.detail_status, 200)
        self.assertEqual(wat.searched, [from_ysmay.pk])

    def test_a_reply_does_not_name_the_blocked_pose_it_answers(self) -> None:
        self.block()
        self.telnet(self.ysmay, f"pose {CARAVAN}")
        parent = self.pose_of(self.ysmay, CARAVAN)
        reply = self.reply(self.wat, parent, "tips his hat.")

        seen = self.seen_by(self.account_of(self.hobb), reply, term="tips", bound=self.scene_bound)

        self.assertEqual(seen.detail_status, 200)
        self.assertIsNone(seen.listed[reply.pk]["reply_to"])
        self.assertIsNone(seen.context[reply.pk]["reply_to"])

    def test_a_blocked_pose_can_be_neither_answered_nor_nominated(self) -> None:
        # Both checks used to run through visible_to alone: a refusal that differs from
        # success tells Hobb the pose exists, and a nomination names its writer.
        get_current_game_week()
        self.telnet(self.ysmay, f"pose {CARAVAN}")
        pose = self.pose_of(self.ysmay, CARAVAN)
        self.block()

        with self.assertRaises(InteractionThreadError):
            self.reply(self.hobb, pose, "answers a pose he cannot see.")
        nominated = self.api(self.account_of(self.hobb)).post(
            "/api/progression/nominations/",
            {"target_type": NominationTargetType.INTERACTION, "target_id": pose.pk},
            format="json",
        )
        self.assertEqual(nominated.status_code, 400, nominated.content)
        self.assertNotIn("Ysmay", nominated.content.decode())

    def test_unread_counts_and_badges_ignore_the_blocked_face(self) -> None:
        # Ysmay's whisper and pose are written first: a block refuses new whispers, but
        # whatever she sent before it must stop counting the moment it lands.
        self.telnet(self.ysmay, f"pose {CARAVAN}")
        self.telnet(self.ysmay, "whisper Hobb=Meet me by the well.")
        self.telnet(self.wat, "pose coughs.")
        hobb = self.account_of(self.hobb)
        before = self.conversations(hobb)
        self.assertEqual(sum(row["unread"] for row in before), 3, before)
        self.assertEqual(self.badge_of(self.hobb)["unread_direct"], 1)
        self.assertTrue(self.badge_of(self.hobb)["has_ambient_unread"])

        self.block()

        after = self.conversations(hobb)
        # Only Wat's cough is waiting; Ysmay's pose and whisper are hidden by the block.
        self.assertEqual(sum(row["unread"] for row in after), 1, after)
        self.assertEqual(sum(row["directUnread"] for row in after), 0, after)
        self.assertNotIn("whisper", {row["ref"]["kind"] for row in after})
        self.assertEqual(self.badge_of(self.hobb)["unread_direct"], 0)

    def test_a_scene_only_the_blocked_face_moved_leaves_no_ambient_badge(self) -> None:
        self.telnet(self.ysmay, f"pose {CARAVAN}")
        self.assertTrue(self.badge_of(self.hobb)["has_ambient_unread"])
        self.block()
        self.assertFalse(self.badge_of(self.hobb)["has_ambient_unread"])


class AMutedFaceKeepsItsActionsButNotItsText(PlayReaderJourney):
    """Hobb mutes Ysmay's face: her poses stay in the feed with the text blanked."""

    def test_the_text_is_blank_on_every_door_until_hobb_opens_the_pose(self) -> None:
        set_mute(
            owner=PlayerData.objects.get(account=self.account_of(self.hobb)),
            muted_persona=self.ysmay.sheet_data.primary_persona,
        )
        self.telnet(self.ysmay, f"pose {CARAVAN}")
        pose = self.pose_of(self.ysmay, CARAVAN)
        self.reply(self.wat, pose, "asks about the gate.")

        seen = self.seen_by(
            self.account_of(self.hobb), pose, term="caravan", bound=self.scene_bound
        )

        self.assertEqual(seen.listed[pose.pk]["content"], "")
        self.assertTrue(seen.listed[pose.pk]["is_muted"])
        self.assertEqual(seen.context[pose.pk]["content"], "")
        self.assertEqual(seen.searched, [])
        for thread in self.threads(self.account_of(self.hobb)):
            self.assertNotIn("caravan", thread["opening"])
        self.assertNotIn("salt gate", seen.bodies.replace(str(seen.detail_content), ""))
        # Opening the pose is the one deliberate way back to the text.
        self.assertEqual(seen.detail_status, 200)
        self.assertEqual(seen.detail_content, CARAVAN)
        # Muting hides words, not events: the pose still counts as waiting.
        self.assertEqual(
            sum(row["unread"] for row in self.conversations(self.account_of(self.hobb))), 2
        )


class AVeryPrivateWhisperReachesOnlyItsParties(PlayReaderJourney):
    """Ysmay whispers Hobb and Hobb marks it very private: nobody else may read it, not
    the scene's GM and not staff."""

    def setUp(self) -> None:
        super().setUp()
        self.telnet(self.ysmay, "whisper Hobb=The vault key is under the hearthstone.")
        self.whisper = self.pose_of(self.ysmay, "The vault key is under the hearthstone.")
        marked = self.api(self.account_of(self.hobb)).post(
            f"/api/interactions/{self.whisper.pk}/mark-private/"
        )
        self.assertEqual(marked.status_code, 200, marked.content)
        self.gm = AccountFactory()
        SceneGMParticipationFactory(scene=self.scene, account=self.gm)
        self.staff = AccountFactory(is_staff=True)

    def test_only_the_two_parties_read_it_through_any_door(self) -> None:
        bound = {"kind": "whisper"}
        for name, account, reads in (
            ("Ysmay", self.account_of(self.ysmay), True),
            ("Hobb", self.account_of(self.hobb), True),
            ("Wat", self.account_of(self.wat), False),
            ("the scene's GM", self.gm, False),
            ("staff", self.staff, False),
        ):
            with self.subTest(viewer=name):
                seen = self.seen_by(account, self.whisper, term="hearthstone", bound=bound)
                if reads:
                    self.assertEqual(seen.detail_status, 200)
                    self.assertEqual(seen.searched, [self.whisper.pk])
                    self.assertEqual(seen.context_status, 200)
                else:
                    self.assertTrue(seen.hidden_everywhere, seen)
                    self.assertNotIn("hearthstone", seen.bodies)
                kinds = {row["ref"]["kind"] for row in self.conversations(account)}
                self.assertEqual("whisper" in kinds, reads, kinds)

    def test_nobody_else_is_counted_as_waiting_on_it(self) -> None:
        self.assertEqual(self.badge_of(self.wat)["unread_direct"], 0)
        self.assertEqual(
            sum(row["unread"] for row in self.conversations(self.account_of(self.wat))), 1
        )


class AnUnknownTongueReadsAsNoise(PlayReaderJourney):
    """Ysmay speaks Khatic. Hobb has none of it, so no door gives him her words."""

    def setUp(self) -> None:
        super().setUp()
        trait = Trait.objects.create(
            name="JourneyKhatic", trait_type=TraitType.LANGUAGE, category=TraitCategory.GENERAL
        )
        LanguageFactory(name="JourneyKhatic", trait=trait)
        CharacterTraitValueFactory(character=self.ysmay.sheet_data, trait=trait, value=100)

    def test_search_and_every_read_give_the_viewer_only_what_he_can_understand(self) -> None:
        self.telnet(self.ysmay, f"say (JourneyKhatic) {CARAVAN}")
        pose = self.pose_of(self.ysmay, CARAVAN)
        self.reply(self.wat, pose, "frowns.")

        for name, account, understands in (
            ("Ysmay", self.account_of(self.ysmay), True),
            ("Hobb", self.account_of(self.hobb), False),
        ):
            with self.subTest(viewer=name):
                seen = self.seen_by(account, pose, term="caravan", bound=self.scene_bound)
                for content in (
                    seen.listed[pose.pk]["content"],
                    seen.detail_content,
                    seen.context[pose.pk]["content"],
                ):
                    self.assertEqual(content == CARAVAN, understands, content)
                self.assertEqual(seen.searched == [pose.pk], understands)
                if not understands:
                    self.assertNotIn("caravan", seen.bodies)
                    for thread in self.threads(account):
                        self.assertNotIn("caravan", thread["opening"])


class AMaskedFaceStaysAStranger(PlayReaderJourney):
    """Ysmay poses in a Stag Mask: a viewer who has not uncovered it meets a stranger on
    every door, and one who has meets the name under it."""

    def setUp(self) -> None:
        super().setUp()
        self.telnet(self.ysmay, "persona mask Stag Mask")
        self.telnet(self.ysmay, f"pose {CARAVAN}")
        self.pose = self.pose_of(self.ysmay, CARAVAN)

    def test_the_real_name_reaches_only_those_who_uncovered_it(self) -> None:
        wat = self.account_of(self.wat)
        stranger = self.seen_by(wat, self.pose, term="caravan", bound=self.scene_bound)
        self.assertEqual(stranger.searched, [self.pose.pk])
        self.assertNotIn("Ysmay", stranger.bodies)
        self.assertIsNone(stranger.listed[self.pose.pk]["endorsee_sheet_id"])
        summaries = json.dumps([self.conversations(wat), self.threads(wat)], default=str)
        self.assertNotIn("Ysmay", summaries)

        # Hobb uncovers the mask; now (and only now) the name under it reaches him.
        record_persona_discovery(
            self.pose.persona,
            self.ysmay.sheet_data.primary_persona,
            self.hobb.sheet_data,
        )
        uncovered = self.seen_by(
            self.account_of(self.hobb), self.pose, term="caravan", bound=self.scene_bound
        )
        self.assertIn("Stag Mask (Ysmay)", uncovered.bodies)


class ANewPlayerDoesNotInheritOldWhispers(PlayReaderJourney):
    """Hobb's character passes to a new player. Whispers pin to the account that held
    them: the old account keeps them, the new one finds no trace on any door."""

    def setUp(self) -> None:
        super().setUp()
        self.telnet(self.ysmay, "whisper Hobb=Meet me by the well.")
        self.whisper = self.pose_of(self.ysmay, "Meet me by the well.")
        self.old_account = self.account_of(self.hobb)
        entry = self.hobb.sheet_data.roster_entry
        tenure = entry.current_tenure
        tenure.end_date = timezone.now()
        tenure.save()
        self.new_account = AccountFactory()
        new_player = PlayerData.objects.get_or_create(account=self.new_account)[0]
        RosterTenureFactory(roster_entry=entry, player_data=new_player, end_date=None)

    def test_the_new_player_finds_no_trace_and_the_old_one_keeps_the_whisper(self) -> None:
        bound = {"kind": "whisper"}
        heir = self.seen_by(self.new_account, self.whisper, term="well", bound=bound)
        self.assertTrue(heir.hidden_everywhere, heir)
        self.assertNotIn("Meet me", heir.bodies)
        self.assertNotIn(
            "whisper", {row["ref"]["kind"] for row in self.conversations(self.new_account)}
        )
        self.assertEqual(sum(row["unread"] for row in self.conversations(self.new_account)), 0)

        former = self.seen_by(self.old_account, self.whisper, term="well", bound=bound)
        self.assertEqual(former.searched, [self.whisper.pk])
        self.assertEqual(former.context_status, 200)

    def test_the_new_players_badge_does_not_count_old_whispers(self) -> None:
        rows = self.badges(self.new_account)
        self.assertEqual([row["unread_direct"] for row in rows], [0])

"""Journeys for the scenes tranche (#3657, tranche 3, step 1): running a scene,
speaking in the room, rolling at the table and reacting to a pose. Each types
what a player types or sends what the web client sends, and asserts what the
player, the room and the scene's feed were told."""

from __future__ import annotations

from unittest.mock import patch

from integration_tests.harness import JourneyCase
from world.checks.constants import CheckCallTargetStatus
from world.checks.factories import CheckTypeFactory
from world.checks.models import CheckCall, CheckCallTarget
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory
from world.scenes.constants import InteractionMode
from world.scenes.factories import PlaceFactory
from world.scenes.models import Interaction, Scene, SceneParticipation
from world.traits.factories import CheckSystemSetupFactory

# A roll of 95 lands in the top band of every chart CheckSystemSetupFactory builds.
ROLL_WELL = patch("world.checks.services.random.randint", return_value=95)


def active_scene(room) -> Scene | None:
    return Scene.objects.active_for_room(room).first()


def feed_of(scene: Scene) -> list[tuple[str, str]]:
    """What the scene's feed holds, oldest first, as (mode, content)."""
    rows = Interaction.objects.filter(scene=scene).order_by("pk")
    return list(rows.values_list("mode", "content"))


def is_owner(scene: Scene, character) -> bool:
    return SceneParticipation.objects.filter(
        scene=scene, account=character.db_account, is_owner=True
    ).exists()


class RunningAScene(JourneyCase):
    """Ysmay opens a scene in the Lantern; Hobb is there from the start and Bram wanders in."""

    def setUp(self) -> None:
        super().setUp()
        self.lantern = self.make_room("The Lantern")
        self.street = self.make_room("Lantern Street")
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)
        self.bram = self.make_player("Bram", room=self.street)
        self.watch(self.hobb, self.bram)

    def bram_walks_in(self) -> None:
        self.bram.location = self.lantern
        self.bram.save()

    def test_an_evening_from_scene_start_to_scene_finish(self) -> None:
        told = self.telnet(self.ysmay, "scene start The Lantern Hour")
        self.assertIn("A scene begins.", told)
        scene = active_scene(self.lantern)
        self.assertIsNotNone(scene)
        self.assertEqual(scene.name, "The Lantern Hour")
        self.assertTrue(is_owner(scene, self.ysmay))
        self.assertTrue(is_owner(scene, self.hobb))

        self.assertIn("Scene: The Lantern Hour. No active round.", self.telnet(self.hobb, "scene"))
        self.assertIn("A scene is already active here.", self.telnet(self.hobb, "scene start"))

        self.bram_walks_in()
        told = self.telnet(self.bram, "scene start")
        self.assertIn("A scene is already active here.", told)
        self.assertFalse(is_owner(scene, self.bram))
        self.assertTrue(
            SceneParticipation.objects.filter(scene=scene, account=self.bram.db_account).exists()
        )
        told = self.telnet(self.bram, "scene finish")
        self.assertIn("Only the scene's GM or an owner can finish the scene.", told)
        self.assertIsNotNone(active_scene(self.lantern))

        told = self.telnet(self.hobb, "scene finish")
        self.assertIn("The scene comes to a close.", told)
        self.assertIsNone(active_scene(self.lantern))
        self.assertIn("No active scene here.", self.telnet(self.ysmay, "scene status"))

    def test_nothing_to_finish_and_an_unknown_subcommand_show_the_way(self) -> None:
        self.assertIn("There is no active scene here.", self.telnet(self.ysmay, "scene finish"))
        self.assertIn("Usage: scene <subcommand>", self.telnet(self.ysmay, "scene dance"))

    def test_the_owner_names_a_present_approved_gm(self) -> None:
        self.telnet(self.ysmay, "scene start")
        scene = active_scene(self.lantern)
        GMProfileFactory(account=self.hobb.db_account)

        self.assertIn("Usage: scene gm <name>.", self.telnet(self.ysmay, "scene gm"))
        self.assertIn("No character named 'Bram' here.", self.telnet(self.ysmay, "scene gm Bram"))

        told = self.telnet(self.ysmay, "scene gm Hobb")
        self.assertIn("Hobb is now a GM of this scene.", told)
        self.assertTrue(scene.is_gm(self.hobb.db_account))

        self.bram_walks_in()
        told = self.telnet(self.ysmay, "scene gm Bram")
        self.assertIn("That account is not an approved GM.", told)
        told = self.telnet(self.bram, "scene gm Hobb")
        self.assertIn("Only the scene's GM or an owner can grant GM status.", told)

    def test_the_web_starts_and_finishes_the_same_scene(self) -> None:
        result = self.web(self.ysmay, "start_scene", name="The Lantern Hour")
        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(result.detail.message, "A scene begins.")
        self.assertEqual(active_scene(self.lantern).name, "The Lantern Hour")

        result = self.web(self.hobb, "finish_scene")
        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(result.detail.message, "The scene comes to a close.")
        self.assertIsNone(active_scene(self.lantern))


class SpeakingInTheRoom(JourneyCase):
    """Ysmay, Hobb and Bram share the Lantern; a scene is running so the feed keeps the lines."""

    def setUp(self) -> None:
        super().setUp()
        self.lantern = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)
        self.bram = self.make_player("Bram", room=self.lantern)
        self.watch(self.hobb, self.bram)
        self.telnet(self.ysmay, "scene start")
        self.scene = active_scene(self.lantern)

    def test_a_pose_opens_with_her_name(self) -> None:
        told = self.telnet(self.ysmay, "pose waves to the room.")
        self.assertIn("Ysmay waves to the room.", told)
        self.assertTold(self.hobb, "Ysmay waves to the room.")
        self.assertTold(self.bram, "Ysmay waves to the room.")

        self.telnet(self.ysmay, "pose 's smile fades.")
        self.assertTold(self.hobb, "Ysmay's smile fades.")

        self.telnet(self.ysmay, "emote bows.")
        self.assertTold(self.hobb, "Ysmay bows.")

        self.assertIn("Pose what?", self.telnet(self.ysmay, "pose"))
        self.assertEqual(
            feed_of(self.scene),
            [
                (InteractionMode.POSE, "waves to the room."),
                (InteractionMode.POSE, "'s smile fades."),
                (InteractionMode.POSE, "bows."),
            ],
        )

    def test_an_emit_carries_no_name(self) -> None:
        told = self.telnet(self.ysmay, "emit The wind picks up outside.")
        self.assertIn("The wind picks up outside.", told)
        self.assertTold(self.hobb, "The wind picks up outside.")
        self.assertNotTold(self.hobb, "Ysmay")
        self.assertIn("Emit what?", self.telnet(self.ysmay, "emit"))
        self.assertEqual(
            feed_of(self.scene), [(InteractionMode.EMIT, "The wind picks up outside.")]
        )

    def test_a_whisper_reaches_only_its_target(self) -> None:
        told = self.telnet(self.ysmay, "whisper Hobb=Meet me by the well.")
        self.assertIn('You whisper to Hobb, "Meet me by the well."', told)
        self.assertTold(self.hobb, 'Ysmay whispers, "Meet me by the well."')
        self.assertNotTold(self.bram, "Meet me by the well.")

        self.assertIn("Could not find 'Nobody'.", self.telnet(self.ysmay, "whisper Nobody=hello"))
        self.assertIn("Usage: whisper <target>=<text>", self.telnet(self.ysmay, "whisper Hobb"))
        self.assertEqual(feed_of(self.scene), [(InteractionMode.WHISPER, "Meet me by the well.")])

    def test_a_mutter_gives_the_room_only_a_fragment(self) -> None:
        muttered = "The vault key is under the third hearthstone on the left."
        told = self.telnet(self.ysmay, f"mutter Hobb={muttered}")
        self.assertIn(f'You mutter to Hobb, "{muttered}"', told)
        self.assertTold(self.hobb, f'Ysmay mutters, "{muttered}"')
        self.assertTold(self.bram, "Ysmay mutters,")
        self.assertNotTold(self.bram, muttered)
        self.assertIn(
            "Usage: mutter <name>[,<name>...]=<text>", self.telnet(self.ysmay, "mutter Hobb")
        )

    def test_tabletalk_speaks_at_a_place(self) -> None:
        PlaceFactory(name="The Hearth", room=self.lantern.room_profile)
        self.assertIn("The Hearth", self.telnet(self.ysmay, "places"))
        self.assertIn(
            "You are not at a place. Join one first.", self.telnet(self.ysmay, "tt nods.")
        )
        self.assertIn(
            "No such place here: 'Nowhere'.", self.telnet(self.ysmay, "places join Nowhere")
        )

        self.assertIn("You join The Hearth.", self.telnet(self.ysmay, "places join The Hearth"))
        self.telnet(self.ysmay, "tt nods to the empty chair.")
        self.assertTold(self.hobb, "At The Hearth, Ysmay nods to the empty chair.")
        self.assertIn("Tabletalk what?", self.telnet(self.ysmay, "tt"))

        self.assertIn("You leave The Hearth.", self.telnet(self.ysmay, "places leave"))
        self.assertIn("You aren't at a place.", self.telnet(self.ysmay, "places leave"))

    def test_the_web_poses_the_same_line(self) -> None:
        result = self.web(self.ysmay, "pose", text="waves.")
        self.assertTrue(result.detail.success, result.detail.message)
        self.assertTold(self.hobb, "Ysmay waves.")
        self.assertEqual(feed_of(self.scene), [(InteractionMode.POSE, "waves.")])


class RollingAtTheTable(JourneyCase):
    """Ysmay rolls a catalog check in front of Hobb; Ravenna, a Junior GM, calls for one."""

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        self.climbing = CheckTypeFactory(name="Climbing", description="Scale a wall or a cliff.")
        self.lantern = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)
        self.ravenna = self.make_player("Ravenna", room=self.lantern)
        self.watch(self.ysmay, self.hobb)
        self.telnet(self.ravenna, "scene start")
        self.scene = active_scene(self.lantern)

    def test_she_finds_a_check_and_rolls_it_for_the_room(self) -> None:
        told = self.telnet(self.ysmay, "check find climb")
        self.assertIn(f"[{self.climbing.pk}] Climbing", told)
        self.assertIn("Check catalog:", self.telnet(self.ysmay, "check"))

        with ROLL_WELL:
            told = self.telnet(self.ysmay, "check Climbing at hard")
        self.assertIn("Ysmay attempts Climbing (Hard) and succeeds (Success).", told)
        mode, narration = feed_of(self.scene)[-1]
        self.assertEqual(mode, InteractionMode.OUTCOME)
        self.assertIn("Ysmay attempts Climbing (Hard) and", narration)

        self.assertIn(
            "No such check -- try `check find <term>`.", self.telnet(self.ysmay, "check Flying")
        )
        self.assertIn(
            "Pick a difficulty band:", self.telnet(self.ysmay, "check Climbing at impossible")
        )

    def test_the_gm_calls_for_a_check_and_the_targets_answer(self) -> None:
        self.assertIn("GM trust required.", self.telnet(self.ysmay, "callcheck Climbing=Hobb"))
        GMProfileFactory(account=self.ravenna.db_account, level=GMLevel.JUNIOR)
        self.assertIn(
            "Usage: callcheck <name>=<target1>,<target2>,... [at <band>]",
            self.telnet(self.ravenna, "callcheck Climbing"),
        )

        told = self.telnet(self.ravenna, "callcheck Climbing=Ysmay,Hobb at easy")
        self.assertIn("Ravenna calls for a check: Climbing (Easy) from Ysmay, Hobb.", told)
        call = CheckCall.objects.get(scene=self.scene)
        prompt = f"check answer {call.pk} to roll, check decline {call.pk} to refuse."
        self.assertTold(self.ysmay, "Ravenna calls for a check: Climbing (Easy) from Ysmay, Hobb.")
        self.assertTold(self.ysmay, prompt)
        self.assertTold(self.hobb, prompt)

        with ROLL_WELL:
            told = self.telnet(self.ysmay, f"check answer {call.pk}")
        self.assertIn("Ysmay attempts Climbing (Easy) and", told)
        self.assertEqual(
            CheckCallTarget.objects.get(call=call, target_sheet=self.ysmay.sheet_data).status,
            CheckCallTargetStatus.ANSWERED,
        )
        self.assertIn(
            "No pending check call found for you.",
            self.telnet(self.ysmay, f"check answer {call.pk}"),
        )

        self.assertIn("You decline to roll.", self.telnet(self.hobb, f"check decline {call.pk}"))
        self.assertEqual(
            CheckCallTarget.objects.get(call=call, target_sheet=self.hobb.sheet_data).status,
            CheckCallTargetStatus.DECLINED,
        )
        self.assertIn(
            "No pending check call found for you.",
            self.telnet(self.ravenna, f"check answer {call.pk}"),
        )

    def test_a_bystander_on_telnet_hears_the_call_once_it_commits(self) -> None:
        # A harness character has no session, and the bystander echo goes only to
        # non-web sessions; stand one in so the on-commit echo has somewhere to land.
        GMProfileFactory(account=self.ravenna.db_account, level=GMLevel.JUNIOR)
        on_telnet = patch(
            "world.scenes.interaction_services.non_web_sessions", return_value=[object()]
        )
        with on_telnet, self.captureOnCommitCallbacks(execute=True):
            self.telnet(self.ravenna, "callcheck Climbing=Ysmay at easy")
        call = CheckCall.objects.get(scene=self.scene)
        self.assertTold(self.hobb, "Ravenna calls for a check: Climbing (Easy) from Ysmay.")
        self.assertNotTold(self.hobb, f"check answer {call.pk}")
        self.assertEqual(self.said(self.ysmay).count("Ravenna calls for a check"), 1)

    def test_she_proposes_a_check_the_catalog_lacks(self) -> None:
        told = self.telnet(
            self.ysmay, "check propose Haggling=Talk a merchant down from their price"
        )
        self.assertIn("Proposal for 'Haggling' sent to staff.", told)
        self.assertIn("Usage: check", self.telnet(self.ysmay, "check propose Haggling"))

    def test_the_web_rolls_the_same_check(self) -> None:
        with ROLL_WELL:
            result = self.web(
                self.ysmay, "scene_self_check", check_type_ref="Climbing", difficulty="hard"
            )
        self.assertTrue(result.detail.success, result.detail.message)
        self.assertIn("Ysmay attempts Climbing (Hard) and", result.detail.message)


class ReactingToAPose(JourneyCase):
    """Hobb poses; Ysmay favorites it, reacts to it and gives it kudos."""

    def setUp(self) -> None:
        super().setUp()
        self.lantern = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)
        self.telnet(self.ysmay, "scene start")
        self.telnet(self.hobb, "pose bows low.")

    def test_a_favorite_and_an_emoji_toggle(self) -> None:
        self.assertIn("Favorited.", self.telnet(self.ysmay, "react favorite Hobb #1"))
        self.assertIn("Favorite removed.", self.telnet(self.ysmay, "react favorite Hobb #1"))
        self.assertIn("Reacted :clap:.", self.telnet(self.ysmay, "react emoji Hobb #1 :clap:"))
        self.assertIn(
            "Removed your :clap: reaction.", self.telnet(self.ysmay, "react emoji Hobb #1 :clap:")
        )

    def test_kudos_open_a_moment_once_per_reactor_and_never_for_the_poser(self) -> None:
        # A pose opens its entrance window on its own; kudos open theirs on the first reaction.
        told = self.telnet(self.ysmay, "react")
        self.assertIn("#entrance bows low.", told)
        self.assertNotIn("#kudos", told)
        self.assertIn("Reaction recorded.", self.telnet(self.ysmay, "react kudos Hobb #1"))
        self.assertIn(
            "You have already reacted to this.", self.telnet(self.ysmay, "react kudos Hobb #1")
        )
        self.assertIn(
            "You cannot react to your own moment.", self.telnet(self.hobb, "react kudos Hobb #1")
        )
        told = self.telnet(self.ysmay, "react")
        self.assertIn("Open reactable events in this scene:", told)
        self.assertIn("#kudos bows low.", told)

    def test_a_wrong_pose_number_or_kind_is_named_back(self) -> None:
        self.assertIn(
            "No visible pose #4 from Hobb. Available: #1",
            self.telnet(self.ysmay, "react favorite Hobb #4"),
        )
        self.assertIn(
            "No visible poses from Ysmay in this scene. Use 'poses Ysmay'.",
            self.telnet(self.hobb, "react favorite Ysmay #1"),
        )
        self.assertIn(
            "Unknown reaction 'applause'.", self.telnet(self.ysmay, "react applause Hobb #1")
        )
        self.assertIn(
            "No character named 'Nobody' here.", self.telnet(self.ysmay, "react favorite Nobody #1")
        )

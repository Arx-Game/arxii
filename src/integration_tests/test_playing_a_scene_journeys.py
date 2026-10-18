"""Journeys for the scenes tranche (#3657, tranche 3, step 1): running a scene,
speaking in the room, rolling at the table and reacting to a pose. Each types
what a player types or sends what the web client sends, and asserts what the
player, the room and the scene's feed were told."""

from __future__ import annotations

from unittest.mock import patch

from evennia_extensions.factories import CharacterFactory
from integration_tests.harness import JourneyCase
from world.battles.staging import stage_battle
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import CheckCallTargetStatus
from world.checks.factories import CheckTypeFactory
from world.checks.models import CheckCall, CheckCallTarget, CheckType
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory
from world.magic.factories import CharacterResonanceFactory, ResonanceFactory
from world.player_submissions.models import CheckProposal
from world.scenes.constants import (
    InteractionMode,
    ReactionWindowKind,
    RoundStatus,
    SceneRoundMode,
    SceneRoundParticipantStatus,
)
from world.scenes.factories import PlaceFactory
from world.scenes.models import (
    Interaction,
    Scene,
    SceneActionDeclaration,
    SceneParticipation,
    SceneRound,
    SceneRoundParticipant,
    WindowReaction,
    get_scene_round_defaults_config,
)
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

    def test_a_staged_battle_does_not_block_a_scene_and_staff_may_run_any(self) -> None:
        # A staged battle has a backing scene of its own; the room's RP scene is a new one.
        battle = stage_battle(name="Siege of the Hall", location=self.lantern)
        told = self.telnet(self.ysmay, "scene start The Lantern Hour")
        self.assertIn("A scene begins.", told)
        scene = Scene.objects.get(location_id=self.lantern.pk, is_active=True, battle__isnull=True)
        self.assertNotEqual(scene.pk, battle.scene_id)

        marrow = self.make_player("Marrow", room=self.lantern)
        staff = self.account_of(marrow)
        staff.is_staff = True
        staff.save(update_fields=["is_staff"])
        GMProfileFactory(account=self.hobb.db_account)
        self.assertIn("Hobb is now a GM of this scene.", self.telnet(marrow, "scene gm Hobb"))
        self.assertEqual(self.web(self.ysmay, "start_round").detail.message, "A round begins.")
        self.assertIn("Round mode set to open.", self.telnet(marrow, "scene round open"))
        self.assertIn("The scene comes to a close.", self.telnet(marrow, "scene finish"))
        self.assertIsNone(active_scene(self.lantern))

    def test_nowhere_is_not_a_room_and_the_street_has_no_scene(self) -> None:
        self.ysmay.location = None
        for line in ("scene start", "scene finish", "scene gm Hobb", "scene round open"):
            self.assertIn("You are not in a room.", self.telnet(self.ysmay, line), line)
        self.ysmay.location = self.street
        self.assertIn("There is no active scene here.", self.telnet(self.ysmay, "scene gm Bram"))

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
        self.assertIn("Join which place?", self.telnet(self.ysmay, "places join"))

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

        # The band is a named choice, never a number, and the invention-shaped kwargs
        # a client might send (a stat, a skill, a pool) change nothing.
        result = self.web(self.ysmay, "scene_self_check", check_type_ref="Climbing", difficulty=60)
        self.assertFalse(result.detail.success)
        self.assertIn("difficulty band", result.detail.message)
        with ROLL_WELL:
            result = self.web(
                self.ysmay,
                "scene_self_check",
                check_type_ref="Climbing",
                difficulty="trivial",
                stat="strength",
                skill="athletics",
                consequence_pool_id=999,
            )
        self.assertTrue(result.detail.success, result.detail.message)
        self.assertIn("Ysmay attempts Climbing (Trivial) and", result.detail.message)

    def test_a_signature_working_is_hers_alone(self) -> None:
        # A check synthesized for one character resolves for her and for nobody else,
        # and a GM's call never reaches it.
        CheckTypeFactory(name="Ysmay's Signature Working", owner_sheet=self.ysmay.sheet_data)
        CheckTypeFactory(name="Hobb's Signature Working", owner_sheet=self.hobb.sheet_data)
        with ROLL_WELL:
            told = self.telnet(self.ysmay, "check Ysmay's Signature Working at normal")
        self.assertIn("Ysmay attempts Ysmay's Signature Working (Normal) and", told)
        self.assertIn(
            "No such check -- try `check find <term>`.",
            self.telnet(self.ysmay, "check Hobb's Signature Working at normal"),
        )
        GMProfileFactory(account=self.ravenna.db_account, level=GMLevel.JUNIOR)
        self.assertIn(
            "No such check -- try `check find <term>`.",
            self.telnet(self.ravenna, "callcheck Ysmay's Signature Working=Ysmay at normal"),
        )
        self.assertFalse(CheckCall.objects.exists())

    def test_a_call_needs_a_scene_and_is_answered_or_declined_once(self) -> None:
        GMProfileFactory(account=self.ravenna.db_account, level=GMLevel.JUNIOR)
        street = self.make_room("Lantern Street")
        self.ravenna.location = street
        self.hobb.location = street
        self.assertIn(
            "You must be running an active scene to call for a check.",
            self.telnet(self.ravenna, "callcheck Climbing=Hobb at normal"),
        )
        self.assertFalse(CheckCall.objects.exists())
        self.ravenna.location = self.lantern
        self.hobb.location = self.lantern

        # The web names its targets by id; the call lands the same.
        result = self.web(
            self.ravenna,
            "call_for_check",
            check_type_ref="Climbing",
            difficulty="hard",
            targets=[self.hobb.pk],
        )
        self.assertTrue(result.detail.success, result.detail.message)
        call = CheckCall.objects.get(scene=self.scene)
        self.assertEqual(CheckCallTarget.objects.filter(call=call).count(), 1)
        self.assertIn("You decline to roll.", self.telnet(self.hobb, f"check decline {call.pk}"))
        self.assertIn(
            "No pending check call found for you.",
            self.telnet(self.hobb, f"check decline {call.pk}"),
        )
        self.assertIn(
            "No pending check call found for you.",
            self.telnet(self.hobb, f"check answer {call.pk}"),
        )
        self.assertEqual(
            CheckCallTarget.objects.get(call=call).status, CheckCallTargetStatus.DECLINED
        )

    def test_a_proposal_needs_its_parts_and_mints_nothing(self) -> None:
        result = self.web(
            self.ysmay, "propose_check_type", proposed_name="", intent="", situation_text=""
        )
        self.assertFalse(result.detail.success)
        self.assertIn(
            "A proposal needs a name, its intent, and the situation it serves.",
            result.detail.message,
        )
        told = self.telnet(
            self.ysmay, "check propose Haggling=Talk a merchant down from their price"
        )
        self.assertIn("Proposal for 'Haggling' sent to staff.", told)
        proposal = CheckProposal.objects.get(proposed_name="Haggling")
        self.assertEqual(proposal.submitted_by_account, self.ysmay.db_account)
        self.assertFalse(CheckType.objects.filter(name="Haggling").exists())


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

    def test_a_character_off_the_roster_has_nothing_to_react_with(self) -> None:
        # A staff puppet or a stray body: a sheet but no roster entry and no account.
        stray = CharacterFactory(db_key="Stray", location=self.lantern)
        CharacterSheetFactory(character=stray)
        self.assertIn(
            "You have no roster entry to favorite with.",
            self.telnet(stray, "react favorite Hobb #1"),
        )
        self.assertIn(
            "You have no account to react with.", self.telnet(stray, "react emoji Hobb #1 :clap:")
        )

    def test_an_entrance_is_answered_with_one_of_the_posers_resonances(self) -> None:
        # The pose opened its entrance window on its own; the answer names one of
        # Hobb's resonances, so he has to hold one first.
        CharacterResonanceFactory(
            character_sheet=self.hobb.sheet_data, resonance=ResonanceFactory(name="Ember")
        )
        self.assertIn("Reaction recorded.", self.telnet(self.ysmay, "react entrance Hobb #1 Ember"))
        self.assertEqual(
            WindowReaction.objects.filter(window__kind=ReactionWindowKind.ENTRANCE).count(), 1
        )
        self.assertIn(
            "You have already reacted to this.",
            self.telnet(self.ysmay, "react entrance Hobb #1 Ember"),
        )


class PacingTheRoom(JourneyCase):
    """Ysmay runs a round in her scene: sets its pace, guards an ally, resolves it."""

    def setUp(self) -> None:
        super().setUp()
        self.lantern = self.make_room("The Lantern")
        self.street = self.make_room("Lantern Street")
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)
        self.bram = self.make_player("Bram", room=self.street)
        self.watch(self.hobb, self.bram)

    def current_round(self) -> SceneRound:
        return SceneRound.objects.filter(room=self.lantern.room_profile).order_by("-pk").first()

    def test_the_round_s_doors_open_close_and_a_pass_waits_for_the_round(self) -> None:
        # These verbs have no telnet face; the web client dispatches them.
        for key in ("join_round", "pass_round", "end_round", "force_resolve_round"):
            result = self.web(self.hobb, key)
            self.assertFalse(result.detail.success, key)
            self.assertEqual(result.detail.message, "There is no active round here.", key)
        self.assertEqual(self.web(self.hobb, "leave_round").detail.message, "You leave the round.")

        # Ordering a round's pace needs a scene; a plain round does not, and takes the
        # staff defaults.
        result = self.web(self.ysmay, "start_round", mode="strict")
        self.assertFalse(result.detail.success)
        self.assertIn(
            "Only a scene GM/owner can choose the round mode at start (start a scene first).",
            result.detail.message,
        )
        self.assertEqual(self.web(self.ysmay, "start_round").detail.message, "A round begins.")
        cfg = get_scene_round_defaults_config()
        rnd = self.current_round()
        self.assertIsNone(rnd.scene_id)
        self.assertEqual(
            (rnd.mode, rnd.advance_quorum_pct, rnd.max_actions_per_round),
            (cfg.default_mode, cfg.advance_quorum_pct, cfg.max_actions_per_round),
        )
        self.assertIn(
            "Mode ordering needs an active scene here; start one first.",
            self.telnet(self.ysmay, "scene round open"),
        )

        result = self.web(self.hobb, "pass_round")
        self.assertFalse(result.detail.success)
        self.assertEqual(result.detail.message, "You are not in this round.")
        self.assertEqual(self.web(self.hobb, "join_round").detail.message, "You join the round.")
        self.assertEqual(self.web(self.hobb, "pass_round").detail.message, "You pass.")
        passed = SceneActionDeclaration.objects.get(scene_round=rnd, round_number=1, is_pass=True)
        self.assertFalse(passed.is_immediate)
        self.assertEqual(self.web(self.hobb, "leave_round").detail.message, "You leave the round.")
        # The seat is marked by a queryset update, which the identity map does not see;
        # read the column.
        status = SceneRoundParticipant.objects.filter(
            scene_round=rnd, character_sheet=self.hobb.sheet_data
        ).values_list("status", flat=True)
        self.assertEqual(list(status), [SceneRoundParticipantStatus.LEFT])
        self.assertEqual(self.web(self.ysmay, "end_round").detail.message, "The round ends.")
        rnd.refresh_from_db()
        self.assertEqual(rnd.status, RoundStatus.COMPLETED)

    def test_the_owner_opens_the_round_at_her_own_pace(self) -> None:
        self.telnet(self.ysmay, "scene start The Lantern Hour")
        self.bram.location = self.lantern
        result = self.web(self.bram, "start_round", mode="open")
        self.assertFalse(result.detail.success)
        self.assertIsNone(self.current_round())
        result = self.web(self.ysmay, "start_round", mode="strict", advance_quorum_pct=80)
        self.assertEqual(result.detail.message, "A round begins.")
        rnd = self.current_round()
        self.assertEqual((rnd.mode, rnd.advance_quorum_pct), (SceneRoundMode.STRICT, 80))
        self.assertEqual(rnd.scene_id, active_scene(self.lantern).pk)
        # A knob on its own, without a mode, is a settings update.
        result = self.web(self.ysmay, "set_round_mode", advance_quorum_pct=75)
        self.assertEqual(result.detail.message, "Round settings updated.")
        rnd.refresh_from_db()
        self.assertEqual(rnd.advance_quorum_pct, 75)
        # With nothing declared yet, forcing a resolve has nothing to gather.
        self.assertEqual(
            self.web(self.ysmay, "force_resolve_round").detail.message,
            "You force the round to resolve.",
        )
        self.assertIn("The scene comes to a close.", self.telnet(self.ysmay, "scene finish"))

    def test_the_owner_sets_the_pace_and_a_declaration_holds_it(self) -> None:
        self.telnet(self.ysmay, "scene start The Lantern Hour")
        self.assertIn(
            "There is no active round here.", self.telnet(self.ysmay, "scene round strict")
        )
        self.assertEqual(self.web(self.ysmay, "start_round").detail.message, "A round begins.")
        self.assertIn(
            "Scene: The Lantern Hour. Round 1 (pose_order).", self.telnet(self.hobb, "scene")
        )
        self.assertEqual(self.web(self.hobb, "join_round").detail.message, "You join the round.")

        self.assertIn(
            "Quorum and cap must be numbers.",
            self.telnet(self.ysmay, "scene round strict quorum=abc"),
        )
        self.assertIn(
            "Quorum and cap must be numbers.", self.telnet(self.ysmay, "scene round strict cap=xyz")
        )
        self.assertIn(
            "Round mode set to strict.",
            self.telnet(self.ysmay, "scene round strict quorum=70 cap=2 lock=on"),
        )
        rnd = self.current_round()
        self.assertEqual(rnd.mode, SceneRoundMode.STRICT)
        self.assertEqual(rnd.advance_quorum_pct, 70)
        self.assertEqual(rnd.max_actions_per_round, 2)
        self.assertTrue(rnd.per_target_repeat_lock)
        self.telnet(self.ysmay, "scene round strict lock=off")
        rnd.refresh_from_db()
        self.assertFalse(rnd.per_target_repeat_lock)
        self.assertIn("Scene: The Lantern Hour. Round 1 (strict).", self.telnet(self.hobb, "scene"))

        self.bram.location = self.lantern
        self.bram.save()
        self.assertIn(
            "Only the scene's GM or an owner can set the round mode.",
            self.telnet(self.bram, "scene round open"),
        )

        # Guarding and sheltering an ally are declarations into the strict round.
        self.assertIn("Usage: scene interpose <ally>.", self.telnet(self.ysmay, "scene interpose"))
        self.assertIn("Usage: scene succor <ally>.", self.telnet(self.ysmay, "scene succor"))
        self.assertIn(
            "No active ally named 'Bram' here.", self.telnet(self.ysmay, "scene interpose Bram")
        )
        self.assertIn(
            "You ready yourself to guard your ally.",
            self.telnet(self.ysmay, "scene interpose Hobb"),
        )
        self.assertIn(
            "You move to shelter your ally.", self.telnet(self.ysmay, "scene succor Hobb")
        )

        # A third participant keeps the round short of its quorum here, so a lone
        # declaration holds rather than resolving the round on its own.
        self.assertEqual(self.web(self.bram, "join_round").detail.message, "You join the round.")
        # A declaration on the table holds the mode until the round resolves.
        self.assertEqual(self.web(self.hobb, "pass_round").detail.message, "You pass.")
        self.assertIn(
            "Resolve the current declarations first (force-resolve), then change the mode.",
            self.telnet(self.ysmay, "scene round pose_order"),
        )
        self.assertEqual(rnd.mode, SceneRoundMode.STRICT)
        self.assertEqual(
            self.web(self.ysmay, "force_resolve_round").detail.message,
            "You force the round to resolve.",
        )
        self.assertIn(
            "Round mode set to pose_order.", self.telnet(self.ysmay, "scene round pose_order")
        )
        self.assertEqual(self.current_round().mode, SceneRoundMode.POSE_ORDER)
        self.assertIn("The scene comes to a close.", self.telnet(self.ysmay, "scene finish"))

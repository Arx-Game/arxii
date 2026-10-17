"""Journeys for the scenes tranche (#3657, tranche 3, step 2): wearing another face,
keeping someone out, turning down the noise, taking the floor, and a GM narrating
in private. Each types what a player types or sends what the web client sends, and
asserts what the player, the room and the feed were told."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone
from evennia.utils.ansi import strip_ansi

from evennia_extensions.factories import CharacterFactory
from evennia_extensions.models import PlayerAllowList
from integration_tests.harness import JourneyCase
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMProfileFactory
from world.roster.factories import RosterEntryFactory
from world.scenes.models import BlockContactFlag, Persona, Scene
from world.scenes.tasks import block_finalize_task


def active_scene(room) -> Scene | None:
    return Scene.objects.active_for_room(room).first()


def persona_named(character, name: str) -> Persona:
    return Persona.objects.get(character_sheet=character.sheet_data, name=name)


class WearingAnotherFace(JourneyCase):
    """Ysmay keeps a second identity and a mask; the room sees whichever face she wears."""

    def setUp(self) -> None:
        super().setUp()
        self.lantern = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)
        self.watch(self.hobb)

    def test_she_makes_a_second_identity_and_the_room_meets_it(self) -> None:
        told = strip_ansi(self.telnet(self.ysmay, "persona"))
        self.assertIn("Ysmay (Primary", told)
        self.assertIn("◄ active", told)

        told = self.telnet(self.ysmay, "persona create The Grey Lady")
        self.assertIn(
            "Created established identity 'The Grey Lady'. Switch with: persona The Grey Lady",
            told,
        )
        self.telnet(self.ysmay, "persona The Grey Lady")
        told = strip_ansi(self.telnet(self.ysmay, "persona list"))
        self.assertIn("The Grey Lady (Established", told)
        self.assertRegex(told, r"The Grey Lady \(Established[^\n]*◄ active")
        self.telnet(self.ysmay, "pose adjusts her veil.")
        self.assertTold(self.hobb, "The Grey Lady adjusts her veil.")

        self.telnet(self.ysmay, "wear-face Ysmay")
        self.telnet(self.ysmay, "pose smiles.")
        self.assertTold(self.hobb, "Ysmay smiles.")

        told = self.telnet(self.ysmay, "persona Nobody")
        self.assertIn("No persona named 'Nobody'. Available: Ysmay, The Grey Lady.", told)
        self.assertIn("Usage: persona create <name>", self.telnet(self.ysmay, "persona create"))

        # A face is matched by name in any case; two faces apart only by case are refused.
        self.telnet(self.ysmay, "persona the grey lady")
        self.telnet(self.ysmay, "pose nods.")
        self.assertTold(self.hobb, "The Grey Lady nods.")
        self.telnet(self.ysmay, "persona create Echo")
        self.telnet(self.ysmay, "persona create echo")
        self.assertIn(
            "Multiple personas match 'echo': Echo, echo. Be more specific.",
            self.telnet(self.ysmay, "persona echo"),
        )

    def test_a_mask_is_worn_the_moment_it_is_made(self) -> None:
        told = self.telnet(self.ysmay, "persona mask Crow Mask")
        self.assertIn("You don a mask: 'Crow Mask'. You are now presenting as it.", told)
        told = self.telnet(self.ysmay, "pose keeps to the shadows.")
        self.assertIn("Crow Mask keeps to the shadows.", told)
        # The room meets a stranger in the mask, never her name.
        self.assertTold(self.hobb, "a person wearing a Crow Mask keeps to the shadows.")
        self.assertNotTold(self.hobb, "Ysmay")

    @override_settings(MAX_ESTABLISHED_PERSONAS_PER_SHEET=2)
    def test_established_identities_are_capped(self) -> None:
        self.telnet(self.ysmay, "persona create The Grey Lady")
        self.telnet(self.ysmay, "persona create Mother Hen")
        told = self.telnet(self.ysmay, "persona create One Too Many")
        self.assertIn("You already hold the most established identities allowed (2).", told)
        self.assertFalse(
            Persona.objects.filter(
                character_sheet=self.ysmay.sheet_data, name="One Too Many"
            ).exists()
        )

    def test_a_cover_identity_carries_its_own_bio(self) -> None:
        self.telnet(self.ysmay, "persona create The Grey Lady")
        told = self.telnet(self.ysmay, "persona profile The Grey Lady")
        self.assertIn("'The Grey Lady' has no guise bio yet.", told)

        told = self.telnet(
            self.ysmay,
            "persona profile The Grey Lady concept=A widow of means quote=Grief is a long road",
        )
        self.assertIn("Updated the guise bio for 'The Grey Lady': concept, quote.", told)
        told = strip_ansi(self.telnet(self.ysmay, "persona profile The Grey Lady"))
        self.assertIn("Guise bio for The Grey Lady:", told)
        self.assertIn("Concept: A widow of means", told)
        self.assertIn("Quote: Grief is a long road", told)
        self.assertIn("Fear: (unset)", told)

        told = self.telnet(self.ysmay, "persona profile Ysmay concept=Not a cover")
        self.assertIn(
            "You can't give your true face a cover bio — edit your real sheet instead.", told
        )

    def test_the_web_switches_the_same_face(self) -> None:
        self.telnet(self.ysmay, "persona create The Grey Lady")
        grey = persona_named(self.ysmay, "The Grey Lady")
        result = self.web(self.ysmay, "set_active_persona", persona_id=grey.pk)
        self.assertTrue(result.detail.success, result.detail.message)
        self.telnet(self.ysmay, "pose adjusts her veil.")
        self.assertTold(self.hobb, "The Grey Lady adjusts her veil.")

        hobbs = persona_named(self.hobb, "Hobb")
        result = self.web(self.ysmay, "set_active_persona", persona_id=hobbs.pk)
        self.assertFalse(result.detail.success)


class KeepingSomeoneOut(JourneyCase):
    """Ysmay blocks Hobb: his pages stop reaching her and his poses leave her feed."""

    def setUp(self) -> None:
        super().setUp()
        self.lantern = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)
        self.bram = self.make_player("Bram", room=self.lantern)
        self.watch(self.ysmay, self.hobb, self.bram)

    def feed_personas_for(self, viewer, scene) -> list[str]:
        response = self.api(self.account_of(viewer)).get(f"/api/interactions/?scene={scene.pk}")
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        rows = data["results"] if isinstance(data, dict) else data
        return sorted(row["persona"]["name"] for row in rows)

    def test_a_block_stops_his_pages_and_hides_his_poses(self) -> None:
        self.assertIn(
            "Usage: +block <character>=<reason>  (a reason is required).",
            self.telnet(self.ysmay, "+block Hobb"),
        )
        self.assertIn(
            "You cannot block your own character.", self.telnet(self.ysmay, "+block Ysmay=Myself.")
        )

        told = self.telnet(self.ysmay, "+block Hobb=He will not take no for an answer.")
        self.assertIn(
            "You have blocked Hobb (account). It can only be lifted after a cron cycle.", told
        )
        told = strip_ansi(self.telnet(self.ysmay, "+blocklist"))
        self.assertIn("Blocked:\n  Hobb (all my characters)", told)

        told = self.telnet(self.hobb, "page Ysmay=Are you there?")
        self.assertIn("You page Ysmay: Are you there?", told)
        self.assertNotTold(self.ysmay, "Hobb pages: Are you there?")
        # His side reads as an ordinary send; the attempt is flagged for staff alone.
        self.assertTrue(
            BlockContactFlag.objects.filter(
                blocked_account=self.hobb.db_account, blocker_account=self.ysmay.db_account
            ).exists()
        )
        self.telnet(self.bram, "page Ysmay=Evening.")
        self.assertTold(self.ysmay, "Bram pages: Evening.")

        self.telnet(self.bram, "scene start")
        scene = active_scene(self.lantern)
        self.telnet(self.hobb, "pose looms.")
        self.telnet(self.bram, "pose nods.")
        self.assertEqual(self.feed_personas_for(self.bram, scene), ["Bram", "Hobb"])
        self.assertEqual(self.feed_personas_for(self.ysmay, scene), ["Bram"])

        told = self.telnet(self.ysmay, "+unblock Hobb")
        self.assertIn("Unblocking Hobb — it clears after the next cron cycle.", told)
        self.assertIn(
            "Hobb (all my characters) - lifting", strip_ansi(self.telnet(self.ysmay, "+blocklist"))
        )
        self.assertIn("You have not blocked Bram.", self.telnet(self.ysmay, "+unblock Bram"))

        # The grace holds until the cron's own task runs an hour on; then his page lands.
        self.telnet(self.hobb, "page Ysmay=Still there?")
        self.assertNotTold(self.ysmay, "Hobb pages: Still there?")
        an_hour_on = timezone.now() + timedelta(hours=1, minutes=1)
        with patch("world.scenes.tasks.timezone.now", return_value=an_hour_on):
            block_finalize_task()
        self.telnet(self.hobb, "page Ysmay=Now?")
        self.assertTold(self.ysmay, "Hobb pages: Now?")
        self.assertIn("Blocked:\n  (none)", strip_ansi(self.telnet(self.ysmay, "+blocklist")))

    def test_a_page_needs_a_played_character_and_respects_quiet_mode(self) -> None:
        self.assertIn("Usage: page <character>=<message>", self.telnet(self.hobb, "page Ysmay"))
        unplayed = CharacterFactory(db_key="Marrow", location=self.lantern)
        CharacterSheetFactory(character=unplayed)
        RosterEntryFactory(character_sheet=unplayed.sheet_data)
        self.assertIn(
            "Character 'Marrow' has no active player.",
            self.telnet(self.hobb, "page Marrow=Anyone home?"),
        )
        stranger = CharacterFactory(db_key="Wren", location=self.lantern)
        CharacterSheetFactory(character=stranger)
        self.assertIn(
            "Character 'Wren' is not on the roster.", self.telnet(self.hobb, "page Wren=Anyone?")
        )

        # Hidden, she reads as offline to everyone but her allow-list, and can page
        # only them; the allow-list itself is a staff-set row.
        self.assertIn(
            "You are now hidden, appearing offline.", strip_ansi(self.telnet(self.ysmay, "hide"))
        )
        self.assertIn(
            "Character 'Ysmay' is not online.", self.telnet(self.hobb, "page Ysmay=Are you there?")
        )
        self.assertNotTold(self.ysmay, "Hobb pages: Are you there?")
        PlayerAllowList.objects.create(
            owner=self.ysmay.db_account.player_data, allowed_player=self.bram.db_account.player_data
        )
        self.telnet(self.bram, "page Ysmay=Evening.")
        self.assertTold(self.ysmay, "Bram pages: Evening.")
        self.assertIn(
            "You're hidden (appearing offline), so you can only page people on your allowlist.",
            self.telnet(self.ysmay, "page Hobb=Not now."),
        )
        self.assertNotTold(self.hobb, "Ysmay pages: Not now.")
        self.telnet(self.ysmay, "page Bram=Good evening.")
        self.assertTold(self.bram, "Ysmay pages: Good evening.")
        self.assertIn(
            "You are no longer hidden; you appear online again.", self.telnet(self.ysmay, "unhide")
        )
        self.telnet(self.hobb, "page Ysmay=There you are.")
        self.assertTold(self.ysmay, "Hobb pages: There you are.")

    def test_a_block_on_one_face_can_be_widened_later(self) -> None:
        told = self.telnet(self.ysmay, "+block/persona Hobb=Just this one.")
        self.assertIn("You have blocked Hobb (this character only).", told)
        self.assertIn("Use +shareblock Hobb to extend it account-wide.", told)
        self.assertNotIn("(all my characters)", strip_ansi(self.telnet(self.ysmay, "+blocklist")))
        self.assertIn(
            "All of your characters now block Hobb.", self.telnet(self.ysmay, "+shareblock Hobb")
        )
        self.assertIn("Hobb (all my characters)", strip_ansi(self.telnet(self.ysmay, "+blocklist")))
        self.assertIn("You have not blocked Bram.", self.telnet(self.ysmay, "+shareblock Bram"))


class TurningDownTheNoise(JourneyCase):
    """Ysmay mutes Hobb: his OOC lines skip her, his poses lose their text in her feed."""

    def setUp(self) -> None:
        super().setUp()
        self.lantern = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)
        self.bram = self.make_player("Bram", room=self.lantern)
        self.watch(self.ysmay, self.bram)

    def feed_for(self, viewer, scene) -> list[tuple[str, bool]]:
        response = self.api(self.account_of(viewer)).get(f"/api/interactions/?scene={scene.pk}")
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        rows = data["results"] if isinstance(data, dict) else data
        return sorted((row["persona"]["name"], row["is_muted"]) for row in rows)

    def test_a_mute_quiets_him_for_her_alone(self) -> None:
        self.assertIn("Usage: +mute <character>[=ic|ooc|both]", self.telnet(self.ysmay, "+mute"))
        self.assertIn("Muted Hobb (IC/OOC, account).", self.telnet(self.ysmay, "+mute Hobb"))
        self.assertIn(
            "Muted:\n  Hobb (all my characters)", strip_ansi(self.telnet(self.ysmay, "+blocklist"))
        )

        self.telnet(self.hobb, "ooc Anyone about?")
        self.assertTold(self.bram, "<OOC> Hobb says: Anyone about?")
        self.assertNotTold(self.ysmay, "Anyone about?")

        self.telnet(self.bram, "scene start")
        scene = active_scene(self.lantern)
        self.telnet(self.hobb, "pose looms.")
        self.telnet(self.bram, "pose nods.")
        self.assertEqual(self.feed_for(self.ysmay, scene), [("Bram", False), ("Hobb", True)])
        self.assertEqual(self.feed_for(self.bram, scene), [("Bram", False), ("Hobb", False)])

        self.assertIn("Unmuted Hobb.", self.telnet(self.ysmay, "+unmute Hobb"))
        self.telnet(self.hobb, "ooc Still here.")
        self.assertTold(self.ysmay, "<OOC> Hobb says: Still here.")

    def test_a_mute_can_be_narrowed_to_one_channel_or_one_face(self) -> None:
        self.assertIn("Muted Hobb (OOC, account).", self.telnet(self.ysmay, "+mute Hobb=ooc"))
        self.assertIn(
            "Muted Hobb (IC, this character only).",
            self.telnet(self.ysmay, "+mute/persona Hobb=ic"),
        )
        self.assertIn("Could not find 'Nobody'.", self.telnet(self.ysmay, "+mute Nobody"))


class TakingTheFloor(JourneyCase):
    """Ysmay opens a speaker queue in the Lantern; Hobb and Bram line up for their turns."""

    def setUp(self) -> None:
        super().setUp()
        self.lantern = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)
        self.bram = self.make_player("Bram", room=self.lantern)

    def test_the_floor_passes_in_order(self) -> None:
        self.assertIn(
            "There is no active speaker queue here. Use 'line open' to start one.",
            self.telnet(self.hobb, "line"),
        )
        self.assertIn("There is no active speaker queue here.", self.telnet(self.hobb, "line join"))
        self.assertIn("A speaker queue is now open.", self.telnet(self.ysmay, "line open"))
        self.assertIn("A speaker queue is already open here.", self.telnet(self.hobb, "line open"))
        self.assertIn(
            "The speaker queue is open but empty. Use 'line join' to get in line.",
            self.telnet(self.ysmay, "line status"),
        )

        self.assertIn("You are now in line at position 1.", self.telnet(self.hobb, "line join"))
        self.assertIn("You are already in line.", self.telnet(self.hobb, "line join"))
        self.assertIn("You are now in line at position 2.", self.telnet(self.bram, "line join"))
        told = self.telnet(self.ysmay, "line")
        self.assertIn("Speaker queue:\n > Hobb\n  2. Bram", told)

        told = self.telnet(self.bram, "line next")
        self.assertIn(
            "It is not your turn, and only the current speaker, the person who opened the "
            "queue, or a GM may advance it.",
            told,
        )
        self.assertIn("The queue advances. Bram is now up.", self.telnet(self.hobb, "line next"))
        self.assertIn("You are not in line.", self.telnet(self.hobb, "line leave"))

        self.assertIn("You are now in line at position 2.", self.telnet(self.hobb, "line join"))
        self.assertIn("Bram is skipped. Hobb is now up.", self.telnet(self.ysmay, "line skip Bram"))
        self.assertIn("Skip whom?", self.telnet(self.ysmay, "line skip"))
        self.assertIn("No one named 'Nobody' here.", self.telnet(self.ysmay, "line skip Nobody"))
        self.assertIn("You leave the speaker queue.", self.telnet(self.hobb, "line leave"))
        self.assertIn("The queue is now empty.", self.telnet(self.ysmay, "line next"))

        self.assertIn(
            "Only the person who opened the queue or a GM may close it.",
            self.telnet(self.hobb, "line close"),
        )
        self.assertIn("The speaker queue is now closed.", self.telnet(self.ysmay, "line close"))
        self.assertIn("Usage: line <subcommand>", self.telnet(self.ysmay, "line dance"))

    def test_the_web_opens_and_joins_the_same_queue(self) -> None:
        result = self.web(self.ysmay, "open_speaker_queue")
        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(result.detail.message, "A speaker queue is now open.")
        result = self.web(self.hobb, "join_speaker_queue")
        self.assertEqual(result.detail.message, "You are now in line at position 1.")
        self.assertIn("Speaker queue:\n > Hobb", self.telnet(self.bram, "line"))


class NarratingInPrivate(JourneyCase):
    """Ravenna, an approved GM, narrates to two players without the third hearing."""

    def setUp(self) -> None:
        super().setUp()
        self.lantern = self.make_room("The Lantern")
        self.ravenna = self.make_player("Ravenna", room=self.lantern)
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)
        self.bram = self.make_player("Bram", room=self.lantern)
        self.watch(self.ysmay, self.hobb, self.bram)
        self.telnet(self.ravenna, "scene start")
        self.scene = active_scene(self.lantern)

    def feed_for(self, viewer) -> list[str]:
        response = self.api(self.account_of(viewer)).get(
            f"/api/interactions/?scene={self.scene.pk}"
        )
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        rows = data["results"] if isinstance(data, dict) else data
        return [row["content"] for row in rows]

    def test_only_the_named_players_hear_the_narration(self) -> None:
        self.assertIn(
            "GM trust required.", self.telnet(self.ysmay, "pemit Hobb=The shadows lengthen.")
        )
        GMProfileFactory(account=self.ravenna.db_account)

        self.assertIn(
            "Usage: pemit <name>[,<name>...]=<text>", self.telnet(self.ravenna, "pemit Hobb")
        )
        self.assertIn("Could not find 'Nobody'.", self.telnet(self.ravenna, "pemit Nobody=Boo."))

        told = self.telnet(
            self.ravenna, "pemit Ysmay,Hobb=A cold draft finds the back of your neck."
        )
        self.assertIn("You narrate to Ysmay, Hobb: A cold draft finds the back of your neck.", told)
        self.assertTold(self.ysmay, "A cold draft finds the back of your neck.")
        self.assertTold(self.hobb, "A cold draft finds the back of your neck.")
        self.assertNotTold(self.bram, "A cold draft")

        self.assertIn("A cold draft finds the back of your neck.", self.feed_for(self.hobb))
        self.assertNotIn("A cold draft finds the back of your neck.", self.feed_for(self.bram))

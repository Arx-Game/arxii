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

from actions.constants import ActionTargetType
from actions.factories import ActionTemplateFactory
from evennia_extensions.factories import CharacterFactory
from evennia_extensions.models import PlayerAllowList
from integration_tests.harness import JourneyCase
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.consent.factories import SocialConsentCategoryFactory
from world.consent.models import SocialConsentBlacklist
from world.gm.factories import GMProfileFactory
from world.roster.factories import RosterEntryFactory
from world.scenes.action_constants import ActionRequestStatus
from world.scenes.action_models import SceneActionRequest
from world.scenes.models import BlockContactFlag, Friendship, Mute, Persona, Scene
from world.scenes.tasks import block_finalize_task
from world.traits.factories import CheckSystemSetupFactory


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
        mute = Mute.objects.get(owner__account=self.ysmay.db_account)
        self.assertEqual((mute.mute_ic, mute.mute_ooc, mute.account_level), (True, True, True))
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
        self.assertFalse(Mute.objects.filter(owner__account=self.ysmay.db_account).exists())
        self.telnet(self.hobb, "ooc Still here.")
        self.assertTold(self.ysmay, "<OOC> Hobb says: Still here.")

    def test_a_mute_can_be_narrowed_to_one_channel_or_one_face(self) -> None:
        self.assertIn("Muted Hobb (OOC, account).", self.telnet(self.ysmay, "+mute Hobb=ooc"))
        mute = Mute.objects.get(owner__account=self.ysmay.db_account)
        self.assertEqual((mute.mute_ic, mute.mute_ooc, mute.account_level), (False, True, True))
        # A face-only mute is a fresh row; an account-wide one is never narrowed back.
        self.telnet(self.ysmay, "+unmute Hobb")
        self.assertIn(
            "Muted Hobb (IC, this character only).",
            self.telnet(self.ysmay, "+mute/persona Hobb=ic"),
        )
        mute = Mute.objects.get(owner__account=self.ysmay.db_account)
        self.assertEqual((mute.mute_ic, mute.mute_ooc, mute.account_level), (True, False, False))
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


# A roll of 95 lands in the top band of every chart CheckSystemSetupFactory builds.
ROLL_WELL = patch("world.checks.services.random.randint", return_value=95)


class KeepingAFriendsList(JourneyCase):
    """Ysmay keeps an out-of-character friends list, one character at a time or all at once."""

    def setUp(self) -> None:
        super().setUp()
        self.lantern = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)

    def friends_of(self, character) -> int:
        return Friendship.objects.filter(
            friender_tenure__roster_entry__character_sheet__character=character
        ).count()

    def test_a_friend_is_added_listed_and_removed(self) -> None:
        self.assertIn(
            "Usage: friend <character>  (or friend/all <character>).",
            self.telnet(self.ysmay, "friend"),
        )
        self.assertIn(
            "This character has no friends listed.", strip_ansi(self.telnet(self.ysmay, "friends"))
        )
        self.assertIn(
            "You added Hobb as a friend (from this character).",
            self.telnet(self.ysmay, "friend Hobb"),
        )
        self.assertEqual(self.friends_of(self.ysmay), 1)
        self.assertIn(
            "Your friends (this character): Hobb", strip_ansi(self.telnet(self.ysmay, "friends"))
        )
        # The keyed spellings (`+friends`, `+unfriend`) are the same lines.
        self.assertIn(
            "Your friends (this character): Hobb", strip_ansi(self.telnet(self.ysmay, "+friends"))
        )
        self.assertIn(
            "You removed Hobb as a friend (from this character).",
            self.telnet(self.ysmay, "+unfriend Hobb"),
        )
        self.assertEqual(self.friends_of(self.ysmay), 0)
        self.assertIn("Usage: unfriend <character>.", self.telnet(self.ysmay, "unfriend"))
        self.assertIn("Could not find 'Nobody'.", self.telnet(self.ysmay, "friend Nobody"))
        self.assertIn(
            "All your characters now count Hobb as a friend.",
            self.telnet(self.ysmay, "friend/all Hobb"),
        )
        self.assertEqual(self.friends_of(self.ysmay), 1)

    def test_someone_she_has_blocked_cannot_be_her_friend(self) -> None:
        self.telnet(self.ysmay, "+block Hobb=He will not take no for an answer.")
        refusal = "That character is not available to add as a friend right now."
        told = self.telnet(self.ysmay, "friend Hobb")
        self.assertIn(refusal, told)
        self.assertNotIn("block", told.lower())
        self.assertIn(refusal, self.telnet(self.ysmay, "friend/all Hobb"))
        self.assertEqual(Friendship.objects.count(), 0)


class PressingSomeoneInAScene(JourneyCase):
    """Ysmay moves to intimidate Hobb in a scene; the game waits on his answer."""

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        self.lantern = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)
        self.bram = self.make_player("Bram", room=self.lantern)
        self.menace = SocialConsentCategoryFactory(key="menace", name="Menace")
        ActionTemplateFactory(
            name="Intimidate",
            category="social",
            target_type=ActionTargetType.SINGLE,
            check_type=CheckTypeFactory(name="Intimidation"),
            consent_category=self.menace,
        )
        self.telnet(self.ysmay, "scene start")
        self.watch(self.hobb)

    def pending_for(self, character) -> list[SceneActionRequest]:
        return list(
            SceneActionRequest.objects.filter(
                target_persona=character.sheet_data.primary_persona,
                status=ActionRequestStatus.PENDING,
            ).order_by("pk")
        )

    def test_a_threat_waits_on_its_target(self) -> None:
        self.assertIn("Whom do you want to intimidate?", self.telnet(self.ysmay, "intimidate"))
        self.assertIn("Could not find 'Nobody'.", self.telnet(self.ysmay, "intimidate Nobody"))
        self.assertIn("You have no pending action to respond to.", self.telnet(self.hobb, "deny"))

        told = self.telnet(self.ysmay, "intimidate Hobb")
        (request,) = self.pending_for(self.hobb)
        self.assertIn(
            f"You move to intimidate Hobb. Awaiting their response (request #{request.pk}).", told
        )
        self.assertEqual(request.initiator_persona, self.ysmay.sheet_data.primary_persona)
        self.assertEqual(request.action_key, "intimidate")
        self.assertIn("You deny the action against you.", self.telnet(self.hobb, "deny"))
        self.assertEqual(
            SceneActionRequest.objects.get(pk=request.pk).status, ActionRequestStatus.DENIED
        )

        self.telnet(self.ysmay, "intimidate Hobb")
        (request,) = self.pending_for(self.hobb)
        with ROLL_WELL:
            told = self.telnet(self.hobb, "accept")
        self.assertIn("You accept the action against you.", told)
        self.assertNotEqual(
            SceneActionRequest.objects.get(pk=request.pk).status, ActionRequestStatus.PENDING
        )
        self.assertEqual(self.pending_for(self.hobb), [])

    def test_an_answer_names_its_request_and_may_bar_the_asker(self) -> None:
        self.telnet(self.ysmay, "intimidate Hobb")
        self.telnet(self.bram, "intimidate Hobb")
        first, second = self.pending_for(self.hobb)
        with ROLL_WELL:
            self.assertIn(
                "You accept the action against you.",
                self.telnet(self.hobb, f"accept/hard {first.pk}"),
            )
        self.assertEqual(
            SceneActionRequest.objects.get(pk=second.pk).status, ActionRequestStatus.PENDING
        )
        # A deny with a blacklist bars the asker only once Hobb's rule for the category
        # reads all-but-blacklist; under the default ("everyone") the entry is written and
        # bars nobody, though the reply says otherwise (recorded on #3657).
        self.assertIn(
            "Menace set to all-but-blacklist.",
            self.telnet(self.hobb, "consent category menace=blacklist"),
        )
        told = self.telnet(self.hobb, "deny/blacklist")
        self.assertIn("You deny the action against you.", told)
        self.assertIn("They can no longer target you with actions of this kind.", told)
        self.assertEqual(
            SceneActionRequest.objects.get(pk=second.pk).status, ActionRequestStatus.DENIED
        )
        # The entry is on Hobb's list, keyed by the two players' tenures. It keeps Bram off
        # the web's target picker for this category; the typed verb opens a request all the
        # same, since create_action_request consults no consent rule (recorded on #3657).
        self.assertTrue(
            SocialConsentBlacklist.objects.filter(
                owner_tenure=self.hobb.sheet_data.roster_entry.current_tenure,
                blocked_tenure=self.bram.sheet_data.roster_entry.current_tenure,
                category=self.menace,
            ).exists()
        )

    def test_a_threat_needs_a_scene(self) -> None:
        yard = self.make_room("The Yard")
        tam = self.make_player("Tam", room=yard)
        self.make_player("Pim", room=yard)
        self.assertIn("You are not in an active scene.", self.telnet(tam, "intimidate Pim"))
        self.assertEqual(SceneActionRequest.objects.count(), 0)

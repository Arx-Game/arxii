"""Prayers and visions (#3779): the plain log, its three qualifying conditions, the GM's answer."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from evennia.accounts.models import AccountDB

from actions.definitions.worship import PrayAction, SendVisionAction
from evennia_extensions.factories import ObjectDBFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.clues.constants import ClueTargetKind
from world.clues.factories import ClueFactory
from world.clues.models import CharacterClue
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.narrative.constants import NarrativeCategory
from world.narrative.models import NarrativeMessageDelivery
from world.roster.factories import grant_test_tenure
from world.stories.factories import EpisodeFactory, StoryParticipationFactory
from world.vitals.factories import CharacterVitalsFactory
from world.worship.constants import (
    PRAYER_SITE_DEVOTION_AMOUNT,
    VISION_RESONANCE_POOL_COST,
    DireStraitsKind,
    MiracleTrigger,
)
from world.worship.exceptions import (
    PrayerEmpty,
    VisionClueNotCodex,
    VisionEpisodeNotShared,
    VisionPoolInsufficient,
    VisionPrayerMismatch,
)
from world.worship.factories import (
    PrayerFactory,
    ShrineDetailsFactory,
    WorshippedBeingFactory,
)
from world.worship.models import DevotionStanding, Miracle, Prayer, Vision
from world.worship.prayer_services import dire_straits_for, pray, send_vision


def _soulfray_on():
    return patch("world.worship.prayer_services.get_soulfray_warning", return_value=object())


class PrayerTestBase(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.being = WorshippedBeingFactory(resonance_pool=500)
        cls.other_being = WorshippedBeingFactory()
        cls.room = ObjectDBFactory(db_key="Chapel", db_typeclass_path="typeclasses.rooms.Room")
        cls.profile = RoomProfileFactory(objectdb=cls.room)
        cls.sheet.character.db_location = cls.room
        cls.sheet.character.save(update_fields=["db_location"])
        CharacterVitalsFactory(character_sheet=cls.sheet, health=100, max_health=100)


class PlainPrayerTests(PrayerTestBase):
    def test_a_prayer_is_logged_and_does_nothing_else(self) -> None:
        outcome = pray(self.sheet, self.being, "  Hear me.  ")

        prayer = Prayer.objects.get()
        self.assertEqual(prayer.text, "Hear me.")
        self.assertEqual(prayer.room_profile, self.profile)
        self.assertEqual(prayer.devotion_granted, 0)
        self.assertEqual(prayer.dire_straits, "")
        self.assertFalse(outcome.at_holy_site)
        self.assertIsNone(outcome.intervention)
        self.assertFalse(DevotionStanding.objects.filter(character_sheet=self.sheet).exists())

    def test_empty_words_are_refused(self) -> None:
        with self.assertRaises(PrayerEmpty):
            pray(self.sheet, self.being, "   ")
        self.assertFalse(Prayer.objects.exists())


class HolySitePrayerTests(PrayerTestBase):
    def test_the_first_prayer_of_the_week_at_the_beings_shrine_is_devotion(self) -> None:
        ShrineDetailsFactory(feature_instance__room_profile=self.profile, being=self.being)

        first = pray(self.sheet, self.being, "Keep this house.")
        second = pray(self.sheet, self.being, "Keep it still.")

        self.assertTrue(first.at_holy_site)
        self.assertEqual(first.devotion_granted, PRAYER_SITE_DEVOTION_AMOUNT)
        self.assertEqual(second.devotion_granted, 0)
        standing = DevotionStanding.objects.get(character_sheet=self.sheet, being=self.being)
        self.assertEqual(standing.favor, PRAYER_SITE_DEVOTION_AMOUNT)
        self.assertEqual(Prayer.objects.filter(devotion_granted__gt=0).count(), 1)

    def test_another_beings_shrine_pays_nothing(self) -> None:
        ShrineDetailsFactory(feature_instance__room_profile=self.profile, being=self.other_being)

        outcome = pray(self.sheet, self.being, "Hear me.")

        self.assertFalse(outcome.at_holy_site)
        self.assertEqual(outcome.devotion_granted, 0)


class DireStraitsTests(PrayerTestBase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.miracle = Miracle.objects.create(
            name="Last Breath",
            being=cls.being,
            resonance_pool_cost=100,
            intervention_trigger=MiracleTrigger.NEAR_DEATH,
            favor_threshold=50,
            narrative_text="[PLACEHOLDER] A hand closes the wound.",
        )
        DevotionStanding.objects.create(character_sheet=cls.sheet, being=cls.being, favor=75)
        ConditionTemplateFactory(name="Divine Intervention Cooldown")

    def _wound(self) -> None:
        vitals = self.sheet.vitals
        vitals.health = 10
        vitals.save(update_fields=["health"])

    def test_hale_and_unfrayed_is_not_dire(self) -> None:
        straits = dire_straits_for(self.sheet)
        self.assertFalse(straits.any)
        self.assertEqual(straits.kind, "")

    def test_near_death_prayer_is_answered_by_a_near_death_miracle(self) -> None:
        self._wound()

        with patch("world.worship.services._broadcast_miracle_narrative"):
            outcome = pray(self.sheet, self.being, "Not yet.")

        self.assertEqual(outcome.dire_straits.kind, DireStraitsKind.NEAR_DEATH)
        self.assertIsNotNone(outcome.intervention)
        self.assertEqual(outcome.intervention.trigger_event, "prayer_near_death")
        self.assertEqual(outcome.prayer.intervention, outcome.intervention)
        self.assertEqual(outcome.prayer.dire_straits, DireStraitsKind.NEAR_DEATH)
        self.assertTrue(
            ConditionInstance.objects.filter(
                target=self.sheet.character, condition__name="Divine Intervention Cooldown"
            ).exists()
        )

    def test_soulfray_counts_as_dire_straits(self) -> None:
        with _soulfray_on(), patch("world.worship.services._broadcast_miracle_narrative"):
            outcome = pray(self.sheet, self.being, "Hold me together.")

        self.assertEqual(outcome.dire_straits.kind, DireStraitsKind.SOULFRAY)
        self.assertIsNotNone(outcome.intervention)
        self.assertEqual(outcome.intervention.trigger_event, "prayer_soulfray")

    def test_an_incapacitation_miracle_does_not_answer_a_prayer(self) -> None:
        self.miracle.intervention_trigger = MiracleTrigger.INCAPACITATED
        self.miracle.save(update_fields=["intervention_trigger"])
        self._wound()

        outcome = pray(self.sheet, self.being, "Not yet.")

        self.assertEqual(outcome.dire_straits.kind, DireStraitsKind.NEAR_DEATH)
        self.assertIsNone(outcome.intervention)
        self.assertEqual(Prayer.objects.count(), 1)

    def test_a_prayer_to_another_god_is_not_answered_by_this_one(self) -> None:
        self._wound()
        with patch("world.worship.services._broadcast_miracle_narrative"):
            outcome = pray(self.sheet, self.other_being, "Anyone.")
        self.assertIsNone(outcome.intervention)

    def test_the_cooldown_holds_between_answers(self) -> None:
        self._wound()
        with patch("world.worship.services._broadcast_miracle_narrative"):
            first = pray(self.sheet, self.being, "Not yet.")
            second = pray(self.sheet, self.being, "Again.")
        self.assertIsNotNone(first.intervention)
        self.assertIsNone(second.intervention)


class SendVisionTests(PrayerTestBase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.tenure = grant_test_tenure(cls.sheet)
        cls.gm = AccountDB.objects.create(username="gm-3779", is_staff=True)

    def test_a_vision_is_delivered_as_a_visions_message_and_spends_the_pool(self) -> None:
        vision = send_vision(
            recipient=self.sheet, being=self.being, body=" A door opens. ", sent_by=self.gm
        )

        self.assertEqual(vision.body, "A door opens.")
        self.assertEqual(vision.message.category, NarrativeCategory.VISIONS)
        self.assertEqual(vision.message.body, "A door opens.")
        self.assertEqual(vision.message.sender_account, self.gm)
        self.assertTrue(
            NarrativeMessageDelivery.objects.filter(
                message=vision.message, recipient_character_sheet=self.sheet
            ).exists()
        )
        self.assertEqual(vision.resonance_spent, VISION_RESONANCE_POOL_COST)
        self.assertEqual(self.being.resonance_pool, 500 - VISION_RESONANCE_POOL_COST)

    def test_a_revealed_source_is_named_in_the_delivered_prose(self) -> None:
        vision = send_vision(
            recipient=self.sheet, being=self.being, body="A door opens.", reveal_source=True
        )
        self.assertIn(self.being.name, vision.message.body)
        self.assertEqual(vision.body, "A door opens.")

    def test_an_empty_pool_cannot_send(self) -> None:
        self.being.resonance_pool = 0
        self.being.save(update_fields=["resonance_pool"])
        with self.assertRaises(VisionPoolInsufficient):
            send_vision(recipient=self.sheet, being=self.being, body="A door opens.")
        self.assertFalse(Vision.objects.exists())

    def test_a_codex_clue_is_handed_over_with_the_vision(self) -> None:
        clue = ClueFactory()

        vision = send_vision(
            recipient=self.sheet, being=self.being, body="A name, half heard.", clue=clue
        )

        self.assertEqual(vision.clue, clue)
        self.assertTrue(
            CharacterClue.objects.filter(roster_entry=self.sheet.roster_entry, clue=clue).exists()
        )

    def test_only_a_codex_clue_rides_a_vision(self) -> None:
        clue = ClueFactory()
        clue.target_kind = ClueTargetKind.MISSION
        with self.assertRaises(VisionClueNotCodex):
            send_vision(recipient=self.sheet, being=self.being, body="No.", clue=clue)

    def test_an_episode_needs_the_recipient_in_its_story(self) -> None:
        episode = EpisodeFactory()
        with self.assertRaises(VisionEpisodeNotShared):
            send_vision(recipient=self.sheet, being=self.being, body="No.", episode=episode)

        StoryParticipationFactory(story=episode.chapter.story, character=self.sheet)
        vision = send_vision(
            recipient=self.sheet, being=self.being, body="A beat.", episode=episode
        )
        self.assertEqual(vision.episode, episode)
        self.assertEqual(vision.message.related_story, episode.chapter.story)

    def test_a_vision_answers_only_the_recipients_own_prayer(self) -> None:
        theirs = PrayerFactory(being=self.being)
        with self.assertRaises(VisionPrayerMismatch):
            send_vision(recipient=self.sheet, being=self.being, body="No.", prayer=theirs)

        mine = PrayerFactory(character_sheet=self.sheet, being=self.being)
        vision = send_vision(recipient=self.sheet, being=self.being, body="Yes.", prayer=mine)
        self.assertEqual(vision.prayer, mine)


class PrayerActionTests(PrayerTestBase):
    def test_pray_by_being_name(self) -> None:
        result = PrayAction().run(
            actor=self.sheet.character, being_name=self.being.name.lower(), text="Hear me."
        )
        self.assertTrue(result.success, result.message)
        self.assertEqual(Prayer.objects.get().being, self.being)

    def test_vision_send_is_staff_only(self) -> None:
        player = AccountDB.objects.create(username="player-3779", is_staff=False)
        gm = AccountDB.objects.create(username="gm2-3779", is_staff=True)

        refused = SendVisionAction().run(
            actor=None,
            account=player,
            recipient=self.sheet,
            being=self.being,
            body="No.",
        )
        sent = SendVisionAction().run(
            actor=None,
            account=gm,
            recipient_name=self.sheet.character.key,
            being_name=self.being.name,
            body="A door opens.",
            reveal_source=True,
        )

        self.assertFalse(refused.success)
        self.assertTrue(sent.success, sent.message)
        vision = Vision.objects.get()
        self.assertEqual(vision.sent_by, gm)
        self.assertTrue(vision.reveal_source)


class PrayerAndVisionAPITests(PrayerTestBase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.tenure = grant_test_tenure(cls.sheet)
        cls.owner = cls.tenure.player_data.account
        cls.stranger = AccountDB.objects.create(username="stranger-3779", is_staff=False)
        cls.gm = AccountDB.objects.create(username="gm-api-3779", is_staff=True)
        cls.prayer = PrayerFactory(character_sheet=cls.sheet, being=cls.being)
        cls.vision = send_vision(
            recipient=cls.sheet, being=cls.being, body="A door opens.", prayer=cls.prayer
        )

    def _client(self, account):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=account)
        return client

    def test_the_owner_reads_their_own_prayers_and_visions(self) -> None:
        client = self._client(self.owner)

        prayers = client.get("/api/worship/prayers/").json()["results"]
        visions = client.get("/api/worship/visions/").json()["results"]

        self.assertEqual([row["id"] for row in prayers], [self.prayer.pk])
        self.assertTrue(prayers[0]["answered"])
        self.assertEqual([row["id"] for row in visions], [self.vision.pk])
        # The source stays concealed unless revealed.
        self.assertIsNone(visions[0]["being_name"])

    def test_a_stranger_sees_none_of_them(self) -> None:
        client = self._client(self.stranger)
        self.assertEqual(client.get("/api/worship/prayers/").json()["results"], [])
        self.assertEqual(client.get("/api/worship/visions/").json()["results"], [])

    def test_staff_read_the_source_and_send_a_vision(self) -> None:
        client = self._client(self.gm)

        listed = client.get(f"/api/worship/visions/?recipient={self.sheet.pk}").json()["results"]
        response = client.post(
            "/api/worship/visions/",
            {
                "recipient": self.sheet.pk,
                "being": self.being.pk,
                "body": "A second door.",
                "reveal_source": True,
                "prayer": self.prayer.pk,
            },
            format="json",
        )

        self.assertEqual(listed[0]["being_name"], self.being.name)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["being_name"], self.being.name)
        self.assertEqual(Vision.objects.filter(recipient=self.sheet).count(), 2)

    def test_a_player_cannot_send_a_vision(self) -> None:
        client = self._client(self.owner)
        response = client.post(
            "/api/worship/visions/",
            {"recipient": self.sheet.pk, "being": self.being.pk, "body": "No."},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

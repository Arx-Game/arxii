"""Prayers and visions (#3779): the plain log, its three qualifying conditions, the GM's answer."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from evennia.accounts.models import AccountDB

from actions.definitions.worship import PrayAction, SendVisionAction
from evennia_extensions.factories import ObjectDBFactory, RoomProfileFactory
from world.action_points.models import ActionPointPool
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.clues.constants import ClueResolution, ClueTargetKind
from world.clues.factories import ClueFactory
from world.clues.models import CharacterClue
from world.codex.constants import CodexKnowledgeStatus
from world.codex.factories import CodexEntryFactory
from world.codex.models import CharacterCodexKnowledge
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.narrative.constants import NarrativeCategory
from world.narrative.models import NarrativeMessageDelivery
from world.roster.factories import grant_test_tenure
from world.stories.factories import EpisodeFactory, StoryParticipationFactory
from world.traits.constants import CANONICAL_OUTCOME_LEVELS
from world.traits.factories import CheckOutcomeFactory
from world.vitals.factories import CharacterVitalsFactory
from world.worship.constants import (
    VISION_RESONANCE_POOL_COST,
    DireStraitsKind,
    FavorAwardKind,
    InterventionStatus,
    MiracleTrigger,
)
from world.worship.exceptions import (
    PrayerApLimit,
    PrayerEmpty,
    VisionClueNotFact,
    VisionEpisodeNotShared,
    VisionPoolInsufficient,
    VisionPrayerMismatch,
)
from world.worship.factories import (
    DevotionConfigFactory,
    FavorOutcomeAwardFactory,
    PrayerFactory,
    ShrineDetailsFactory,
    WorshippedBeingFactory,
    make_chosen,
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
    def _pool(self):
        return ActionPointPool.get_or_create_for_character(self.sheet.character)

    def test_ap_spent_at_the_beings_shrine_earns_favor(self) -> None:
        ShrineDetailsFactory(feature_instance__room_profile=self.profile, being=self.being)
        before = self._pool().current

        outcome = pray(self.sheet, self.being, "Keep this house.", ap=15)

        self.assertTrue(outcome.at_holy_site)
        self.assertEqual(outcome.ap_spent, 15)
        self.assertEqual(outcome.devotion_granted, 3)
        self.assertEqual(Prayer.objects.get().ap_spent, 15)
        standing = DevotionStanding.objects.get(character_sheet=self.sheet, being=self.being)
        self.assertEqual(standing.favor, 3)
        self.assertEqual(self._pool().current, before - 15)

    def test_a_chosen_earns_double_for_the_same_ap(self) -> None:
        ShrineDetailsFactory(feature_instance__room_profile=self.profile, being=self.being)
        make_chosen(self.sheet, self.being)

        outcome = pray(self.sheet, self.being, "Keep this house.", ap=15)

        self.assertEqual(outcome.devotion_granted, 6)

    def test_the_weekly_limit_refuses_before_any_ap_is_spent(self) -> None:
        ShrineDetailsFactory(feature_instance__room_profile=self.profile, being=self.being)
        pray(self.sheet, self.being, "Morning.", ap=30)
        before = self._pool().current

        with self.assertRaises(PrayerApLimit):
            pray(self.sheet, self.being, "Evening.", ap=5)

        self.assertEqual(self._pool().current, before)
        self.assertEqual(Prayer.objects.count(), 1)

    def test_favor_that_pays_owed_favor_first_says_so(self) -> None:
        ShrineDetailsFactory(feature_instance__room_profile=self.profile, being=self.being)
        DevotionStanding.objects.create(
            character_sheet=self.sheet, being=self.being, favor=0, owed_favor=2
        )

        outcome = pray(self.sheet, self.being, "Keep this house.", ap=15)

        # 3 base favor: 2 pay the debt first, the remaining 1 is earned.
        self.assertEqual((outcome.owed_paid, outcome.devotion_granted), (2, 1))
        standing = DevotionStanding.objects.get(character_sheet=self.sheet, being=self.being)
        standing.owed_favor = 1
        standing.save(update_fields=["owed_favor"])
        result = PrayAction().run(
            actor=self.sheet.character, being=self.being.pk, text="Again.", ap=5
        )
        self.assertIn("paid what you owe", result.message)

    def test_another_beings_shrine_or_no_shrine_spends_and_earns_nothing(self) -> None:
        ShrineDetailsFactory(feature_instance__room_profile=self.profile, being=self.other_being)
        before = self._pool().current

        outcome = pray(self.sheet, self.being, "Hear me.", ap=10)

        self.assertFalse(outcome.at_holy_site)
        self.assertEqual((outcome.ap_spent, outcome.devotion_granted), (0, 0))
        self.assertEqual(self._pool().current, before)


class DireStraitsTests(PrayerTestBase):
    """A prayer in dire straits is one graded roll (#4349); the result is forced each way."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.check_type = CheckTypeFactory(name="Invocation")
        cls.config = DevotionConfigFactory(invocation_check_type=cls.check_type)
        outcomes = {
            name: CheckOutcomeFactory(name=name, success_level=level)
            for name, level in CANONICAL_OUTCOME_LEVELS.items()
        }
        cls.success = outcomes["Success"]
        cls.failure = outcomes["Failure"]
        cls.partial = outcomes["Partial Success"]
        for kind, amount in (
            (FavorAwardKind.INTERVENTION_SPEND, 20),
            (FavorAwardKind.INTERVENTION_DEBT, 10),
            (FavorAwardKind.INTERVENTION_WAIT_HOURS, 72),
        ):
            FavorOutcomeAwardFactory(
                config=cls.config, kind=kind, outcome_tier=cls.success, amount=amount
            )
        cls.miracle = Miracle.objects.create(
            name="Last Breath",
            being=cls.being,
            resonance_pool_cost=100,
            intervention_trigger=MiracleTrigger.NEAR_DEATH,
            favor_threshold=0,
            narrative_text="[PLACEHOLDER] A hand closes the wound.",
        )
        cls.standing = DevotionStanding.objects.create(
            character_sheet=cls.sheet, being=cls.being, favor=75
        )
        cls.cooldown = ConditionTemplateFactory(name="Divine Intervention Cooldown")

    def _wound(self) -> None:
        vitals = self.sheet.vitals
        vitals.health = 10
        vitals.save(update_fields=["health"])

    def _pray(self, outcome, being=None):
        with (
            force_check_outcome(outcome),
            patch("world.worship.services._broadcast_miracle_narrative"),
        ):
            return pray(self.sheet, being or self.being, "Not yet.")

    def _standing(self) -> DevotionStanding:
        return DevotionStanding.objects.get(character_sheet=self.sheet, being=self.being)

    def test_hale_and_unfrayed_is_not_dire(self) -> None:
        straits = dire_straits_for(self.sheet)
        self.assertFalse(straits.any)
        self.assertEqual(straits.kind, "")

    def test_a_rescue_fires_the_miracle_and_costs_the_one_praying(self) -> None:
        self._wound()

        outcome = self._pray(self.success)

        result = outcome.intervention
        self.assertEqual(outcome.dire_straits.kind, DireStraitsKind.NEAR_DEATH)
        self.assertEqual(result.performance.trigger_event, "prayer_near_death")
        self.assertEqual(result.performance.outcome_tier, self.success)
        self.assertEqual(outcome.prayer.intervention, result.performance)
        # The owed 10 is softened by the high favor band (50 percent), read before the spend.
        self.assertEqual((result.cost.favor_spent, result.cost.favor_owed), (20, 5))
        standing = self._standing()
        self.assertEqual((standing.favor, standing.owed_favor), (55, 5))
        self.assertTrue(
            ConditionInstance.objects.filter(
                target=self.sheet.character, condition__name="Divine Intervention Cooldown"
            ).exists()
        )
        self.assertIn(
            "answered you (Success); favor spent 20; favor owed 5; "
            "it will not answer again for 36 hours.",
            outcome.lines[0],
        )

    def test_soulfray_counts_as_dire_straits(self) -> None:
        with _soulfray_on():
            outcome = self._pray(self.success)

        self.assertEqual(outcome.dire_straits.kind, DireStraitsKind.SOULFRAY)
        self.assertEqual(outcome.intervention.performance.trigger_event, "prayer_soulfray")

    def test_a_failure_is_unanswered_and_still_sets_a_wait(self) -> None:
        self._wound()

        outcome = self._pray(self.failure)

        self.assertIsNone(outcome.intervention.performance)
        self.assertFalse(outcome.answered)
        self.assertEqual(self._standing().favor, 75)
        self.assertTrue(
            ConditionInstance.objects.filter(
                target=self.sheet.character, condition__name="Divine Intervention Cooldown"
            ).exists()
        )

    def test_an_incapacitation_miracle_does_not_answer_a_prayer(self) -> None:
        self.miracle.intervention_trigger = MiracleTrigger.INCAPACITATED
        self.miracle.save(update_fields=["intervention_trigger"])
        self._wound()

        outcome = self._pray(self.success)

        self.assertIsNone(outcome.intervention.performance)
        self.assertEqual(Prayer.objects.count(), 1)

    def test_below_the_prayer_gate_nothing_is_rolled(self) -> None:
        self._wound()

        outcome = self._pray(self.success, being=self.other_being)

        self.assertEqual(outcome.intervention.status, InterventionStatus.BELOW_GATE)
        self.assertFalse(outcome.intervention.rolled)

    def test_the_wait_holds_between_calls(self) -> None:
        self._wound()
        first = self._pray(self.success)
        second = self._pray(self.success)

        self.assertTrue(first.answered)
        self.assertEqual(second.intervention.status, InterventionStatus.WAITING)

    def test_owed_favor_means_the_being_ignores_the_call(self) -> None:
        self.standing.owed_favor = 4
        self.standing.save(update_fields=["owed_favor"])
        self._wound()

        outcome = self._pray(self.success)

        self.assertEqual(outcome.intervention.status, InterventionStatus.OWED)
        self.assertEqual(self._standing().favor, 75)


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

    def test_an_automatic_codex_clue_grants_its_entry_with_the_vision(self) -> None:
        entry = CodexEntryFactory(learn_threshold=5)
        clue = ClueFactory(target_codex_entry=entry, resolution_mode=ClueResolution.AUTOMATIC)

        send_vision(recipient=self.sheet, being=self.being, body="A name, half heard.", clue=clue)

        knowledge = CharacterCodexKnowledge.objects.get(
            roster_entry=self.sheet.roster_entry, entry=entry
        )
        self.assertEqual(knowledge.status, CodexKnowledgeStatus.KNOWN)

    def test_a_research_codex_clue_is_only_held_by_the_vision(self) -> None:
        entry = CodexEntryFactory(learn_threshold=5)
        clue = ClueFactory(target_codex_entry=entry, resolution_mode=ClueResolution.RESEARCH)

        send_vision(recipient=self.sheet, being=self.being, body="A name, half heard.", clue=clue)

        self.assertTrue(
            CharacterClue.objects.filter(roster_entry=self.sheet.roster_entry, clue=clue).exists()
        )
        self.assertFalse(
            CharacterCodexKnowledge.objects.filter(
                roster_entry=self.sheet.roster_entry, entry=entry
            ).exists()
        )

    def test_only_a_codex_or_secret_clue_rides_a_vision(self) -> None:
        clue = ClueFactory()
        clue.target_kind = ClueTargetKind.MISSION
        with self.assertRaises(VisionClueNotFact):
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

"""The Backgrounds beat library at character creation (#4124).

A beat is a prompt over priced distinction offers, pooled per life stage for every
Beginning that does not exclude it; its answers open when the beat is taken; a
one-of beat refuses a second answer; a Sleeper-style Beginning keeps one beat.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.character_creation.constants import (
    BeatMode,
    BeatSelection,
    LifeStage,
    OfferArrival,
    OfferChapter,
)
from world.character_creation.factories import (
    BeginningsFactory,
    CharacterDraftFactory,
    DistinctionOfferFactory,
    LifeBeatExclusionFactory,
    LifeBeatFactory,
)
from world.character_creation.offers import (
    beat_pool,
    beats_for,
    offers_for,
    one_of_beat_conflicts,
    reconcile_offer_picks,
    visible_offers,
)
from world.distinctions.factories import DistinctionFactory


def _answer(beat, name, cost):
    return DistinctionOfferFactory(
        chapter=OfferChapter.BACKGROUNDS,
        beat=beat,
        appearance_section=None,
        prompt="",
        distinction=DistinctionFactory(name=name, cost_per_rank=cost, max_rank=1),
    )


class BeatPoolTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.beginning = BeginningsFactory(name="Nobility")
        cls.other = BeginningsFactory(name="Underworld")
        cls.household = LifeBeatFactory(name="The household", sort_order=1)
        cls.work = LifeBeatFactory(
            name="The work", life_stage=LifeStage.ADULTHOOD, selection=BeatSelection.ANY
        )
        cls.court = LifeBeatFactory(name="The court", sort_order=2)
        LifeBeatExclusionFactory(beat=cls.court, beginning=cls.other)
        LifeBeatFactory(name="Retired", is_active=False)

    def test_pool_is_the_library_minus_this_beginnings_exclusions_in_life_order(self):
        draft = CharacterDraftFactory(selected_beginnings=self.other)
        self.assertEqual([b.name for b in beat_pool(draft)], ["The household", "The work"])
        noble = CharacterDraftFactory(selected_beginnings=self.beginning)
        self.assertEqual(
            [b.name for b in beat_pool(noble)], ["The household", "The court", "The work"]
        )

    def test_no_beginning_no_pool(self):
        self.assertEqual(beat_pool(CharacterDraftFactory()), [])

    def test_beats_for_reads_the_drafts_state(self):
        draft = CharacterDraftFactory(
            selected_beginnings=self.beginning,
            draft_data={
                "beats": {
                    str(self.household.pk): {"taken": True, "line": "A line."},
                    str(self.court.pk): {"taken": True, "unknown": True},
                }
            },
        )
        by_name = {e.name: e for e in beats_for(draft)}
        self.assertTrue(by_name["The household"].taken)
        self.assertEqual(by_name["The household"].line, "A line.")
        self.assertFalse(by_name["The household"].unknown)
        self.assertTrue(by_name["The court"].unknown)
        self.assertFalse(by_name["The work"].taken)
        self.assertEqual(by_name["The work"].selection, BeatSelection.ANY)

    def test_one_kept_beginning_takes_its_pool_by_itself(self):
        sleeper = BeginningsFactory(name="Sleeper", beat_mode=BeatMode.ONE_KEPT)
        for beat in (self.household, self.court):
            LifeBeatExclusionFactory(beat=beat, beginning=sleeper)
        draft = CharacterDraftFactory(selected_beginnings=sleeper)
        entries = beats_for(draft)
        self.assertEqual([e.name for e in entries], ["The work"])
        self.assertTrue(entries[0].taken)


class BeatAnswerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.beginning = BeginningsFactory(name="Nobility")
        cls.household = LifeBeatFactory(name="The household")
        cls.spoiled = _answer(cls.household, "Spoiled", -10)
        cls.patient = _answer(cls.household, "Patient", 10)
        cls.work = LifeBeatFactory(
            name="The work", life_stage=LifeStage.ADULTHOOD, selection=BeatSelection.ANY
        )
        cls.efficient = _answer(cls.work, "Efficient", 10)
        cls.secretive = _answer(cls.work, "Secretive", 25)

    def test_an_answer_opens_only_once_its_beat_is_taken(self):
        draft = CharacterDraftFactory(selected_beginnings=self.beginning)
        self.assertEqual(offers_for(draft, OfferChapter.BACKGROUNDS), [])
        draft.draft_data = {"beats": {str(self.household.pk): {"taken": True}}}
        draft.save()
        names = [o.name for o in offers_for(draft, OfferChapter.BACKGROUNDS)]
        self.assertEqual(names, ["Spoiled", "Patient"])
        self.assertTrue(
            all(
                o.opener_key == f"beat:{self.household.pk}" and o.arrives_as == OfferArrival.CHOICE
                for o in offers_for(draft, OfferChapter.BACKGROUNDS)
            )
        )

    def test_an_unknown_beat_opens_nothing(self):
        draft = CharacterDraftFactory(
            selected_beginnings=self.beginning,
            draft_data={"beats": {str(self.household.pk): {"taken": True, "unknown": True}}},
        )
        self.assertEqual(offers_for(draft, OfferChapter.BACKGROUNDS), [])

    def test_answers_group_by_beat_in_pool_order(self):
        draft = CharacterDraftFactory(
            selected_beginnings=self.beginning,
            draft_data={
                "beats": {
                    str(self.work.pk): {"taken": True},
                    str(self.household.pk): {"taken": True},
                }
            },
        )
        keys = [o.opener_key for o in offers_for(draft, OfferChapter.BACKGROUNDS)]
        self.assertEqual(
            keys,
            [f"beat:{self.household.pk}"] * 2 + [f"beat:{self.work.pk}"] * 2,
        )

    def test_removing_a_beat_drops_its_picks(self):
        draft = CharacterDraftFactory(
            selected_beginnings=self.beginning,
            draft_data={
                "beats": {str(self.household.pk): {"taken": True}},
                "distinctions": [
                    {
                        "distinction_id": self.patient.distinction_id,
                        "distinction_name": "Patient",
                        "rank": 1,
                        "cost": 10,
                        "offer_ids": [self.patient.pk],
                        "sources": ["The household"],
                        "arrivals": [OfferArrival.CHOICE],
                    }
                ],
            },
        )
        self.assertIn(self.patient.pk, visible_offers(draft))
        draft.draft_data["beats"] = {}
        draft.save()
        dropped = reconcile_offer_picks(draft)
        self.assertEqual(dropped, ["Patient"])
        self.assertEqual(draft.draft_data["distinctions"], [])

    def test_one_of_conflicts_name_the_beat(self):
        self.assertEqual(one_of_beat_conflicts([self.spoiled, self.patient]), ["The household"])
        self.assertEqual(one_of_beat_conflicts([self.efficient, self.secretive]), [])
        self.assertEqual(one_of_beat_conflicts([self.spoiled, self.efficient]), [])


class BeatsEndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        cls.beginning = BeginningsFactory(name="Nobility")
        cls.household = LifeBeatFactory(name="The household")
        cls.patient = _answer(cls.household, "Patient", 10)
        cls.spoiled = _answer(cls.household, "Spoiled", -10)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)
        self.draft = CharacterDraftFactory(account=self.account, selected_beginnings=self.beginning)

    def test_the_pool_endpoint_lists_the_beats_with_their_answers(self):
        resp = self.client.get(f"/api/character-creation/drafts/{self.draft.id}/beats/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.json(),
            [
                {
                    "beat_id": self.household.pk,
                    "name": "The household",
                    "prompt": self.household.prompt,
                    "life_stage": "childhood",
                    "selection": "one_of",
                    "taken": False,
                    "unknown": False,
                    "line": "",
                    "answer_offer_ids": [self.patient.pk, self.spoiled.pk],
                }
            ],
        )

    def test_taking_a_beat_is_a_draft_patch_and_the_sync_refuses_two_answers_on_one_of(self):
        resp = self.client.patch(
            f"/api/character-creation/drafts/{self.draft.id}/",
            {"draft_data": {"beats": {str(self.household.pk): {"taken": True, "line": "x"}}}},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        both = {
            "distinctions": [
                {"id": self.patient.distinction_id, "rank": 1, "offer_id": self.patient.pk},
                {"id": self.spoiled.distinction_id, "rank": 1, "offer_id": self.spoiled.pk},
            ]
        }
        resp = self.client.put(
            f"/api/distinctions/drafts/{self.draft.id}/distinctions/sync/", both, format="json"
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("The household", resp.json()["detail"])
        one = {"distinctions": both["distinctions"][:1]}
        resp = self.client.put(
            f"/api/distinctions/drafts/{self.draft.id}/distinctions/sync/", one, format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual([d["distinction_name"] for d in resp.json()["distinctions"]], ["Patient"])

    def test_a_malformed_beats_map_is_refused(self):
        resp = self.client.patch(
            f"/api/character-creation/drafts/{self.draft.id}/",
            {"draft_data": {"beats": {"x": {"taken": True}}}},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

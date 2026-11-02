"""Journeys: the suggested life a beginning loads (#4865, slice 7 of #4813).

Maud's beginning carries a suggested life in its starred first-look pins: two on the
one-of childhood beat, one on the any youth beat, two careers on the age-scaled adulthood
beat. The life opens and loads: the first childhood card by the grid's order, the youth
card, and the one career her one point at nineteen buys; the beats read taken, the picks
are priced, and the draft is stamped for that beginning. Loading again changes nothing,
Start blank empties the life and keeps her Actor's Sheet pick, and at twenty-four both
careers load. The expected shapes come from the rulings of 2026-10-19 (the suggested life, the
star, Start blank) and the parent's item 13.
"""

from __future__ import annotations

from evennia_extensions.factories import AccountFactory
from integration_tests.harness import JourneyCase
from world.character_creation.constants import (
    BeatSelection,
    LifeStage,
    OfferArrival,
    OfferChapter,
    Parentage,
)
from world.character_creation.factories import (
    BeginningsFactory,
    DistinctionOfferFactory,
    LifeBeatFactory,
    OriginTemplateFactory,
)
from world.character_creation.models import OfferFirstLook
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin
from world.distinctions.factories import DistinctionFactory


def _answer(beat, name: str, cost: int, sort_order: int = 0):
    return DistinctionOfferFactory(
        chapter=OfferChapter.BACKGROUNDS,
        beat=beat,
        appearance_section=None,
        prompt="",
        sort_order=sort_order,
        distinction=DistinctionFactory(name=name, cost_per_rank=cost, max_rank=1),
    )


class TheSuggestedLife(FinalizationTestMixin, JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        self._flush_common_caches()
        self.account = AccountFactory()
        self._setup_finalization_base(self, prefix="Lives", height_min=700, height_max=800)
        OriginTemplateFactory(
            beginning=self.beginnings,
            allows_no_family=True,
            allows_name_family=False,
            parentage=Parentage.KNOWN,
        )
        self.household = LifeBeatFactory(name="How you were raised")
        self.spoiled = _answer(self.household, "Spoiled", -10, sort_order=1)
        self.hard = _answer(self.household, "Hard scrabble", -10, sort_order=2)
        self.youth = LifeBeatFactory(
            name="Influences", life_stage=LifeStage.YOUTH, selection=BeatSelection.ANY
        )
        self.tutored = _answer(self.youth, "Extensively Tutored", 10)
        self.drama = _answer(self.youth, "Explosive Drama", -10)
        self.careers = LifeBeatFactory(
            name="Past Careers",
            life_stage=LifeStage.ADULTHOOD,
            selection=BeatSelection.ANY,
            picks_scale_with_age=True,
        )
        self.socialite = _answer(self.careers, "Socialite", 0, sort_order=1)
        self.sailor = _answer(self.careers, "Sailor", 0, sort_order=2)
        self.jailbird = DistinctionFactory(name="Jailbird", cost_per_rank=-5, max_rank=1)
        self.jailbird_offer = DistinctionOfferFactory(
            distinction=self.jailbird,
            chapter=OfferChapter.ACTORS_SHEET,
            arrives_as=OfferArrival.CHOICE,
            prompt="never_do",
        )
        # The suggested life: both childhood cards starred (the first by order stands),
        # one youth card starred and one merely pinned, the career starred.
        for offer, starred in (
            (self.spoiled, True),
            (self.hard, True),
            (self.tutored, True),
            (self.drama, False),
            (self.socialite, True),
            (self.sailor, True),
        ):
            OfferFirstLook.objects.create(
                offer=offer, beginning=self.beginnings, preselected=starred
            )
        self.client = self.api(self.account)

    def _url(self, draft, tail: str = "") -> str:
        return f"/api/character-creation/drafts/{draft.pk}/{tail}"

    def _picks(self, payload: dict) -> dict[str, int]:
        return {e["distinction_name"]: e["cost"] for e in payload["draft_data"]["distinctions"]}

    def _taken(self, draft) -> dict[str, bool]:
        response = self.client.get(self._url(draft, "beats/"))
        self.assertEqual(response.status_code, 200, response.content)
        return {b["name"]: b["taken"] for b in response.json()}

    def test_the_life_loads_once_per_beginning_and_start_blank_empties_it(self) -> None:
        draft = self._create_base_draft(first_name="Maud")
        draft.age = 19
        draft.save(update_fields=["age"])
        # An Actor's Sheet pick the life never touches.
        response = self.client.put(
            f"/api/distinctions/drafts/{draft.pk}/distinctions/sync/",
            {
                "distinctions": [
                    {"id": self.jailbird.pk, "rank": 1, "offer_id": self.jailbird_offer.pk}
                ]
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)

        response = self.client.post(self._url(draft, "load-default-life/"))
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(
            self._picks(payload),
            {"Jailbird": -5, "Spoiled": -10, "Extensively Tutored": 10, "Socialite": 0},
        )
        self.assertEqual(payload["draft_data"]["life_loaded_for"], self.beginnings.pk)
        taken = self._taken(draft)
        self.assertTrue(taken["How you were raised"])
        self.assertTrue(taken["Influences"])
        self.assertTrue(taken["Past Careers"])

        # The player drops Spoiled; loading again does not bring it back.
        response = self.client.put(
            f"/api/distinctions/drafts/{draft.pk}/distinctions/sync/",
            {
                "distinctions": [
                    {"id": self.jailbird.pk, "rank": 1, "offer_id": self.jailbird_offer.pk},
                    {"id": self.tutored.distinction_id, "rank": 1, "offer_id": self.tutored.pk},
                ]
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        response = self.client.post(self._url(draft, "load-default-life/"))
        self.assertEqual(set(self._picks(response.json())), {"Jailbird", "Extensively Tutored"})

        # Start blank: the life goes, the Actor's Sheet pick stays, the stamp stays.
        response = self.client.post(self._url(draft, "clear-life/"))
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(self._picks(payload), {"Jailbird": -5})
        self.assertEqual(payload["draft_data"]["beats"], {})
        self.assertEqual(payload["draft_data"]["life_loaded_for"], self.beginnings.pk)
        self.assertFalse(any(self._taken(draft).values()))
        response = self.client.post(self._url(draft, "load-default-life/"))
        self.assertEqual(self._picks(response.json()), {"Jailbird": -5})

    def test_an_age_scaled_beat_loads_as_many_careers_as_the_age_allows(self) -> None:
        """Two careers starred; one point at nineteen takes the first, two at twenty-four
        take both (#4829's rule: one point at or under nineteen, one more every five years)."""
        draft = self._create_base_draft(first_name="Maud")
        draft.age = 24
        draft.save(update_fields=["age"])
        response = self.client.post(self._url(draft, "load-default-life/"))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            set(self._picks(response.json())),
            {"Spoiled", "Extensively Tutored", "Socialite", "Sailor"},
        )

    def test_a_card_held_elsewhere_and_an_excluded_partner_stay_out(self) -> None:
        """Review on #4866: a starred card the draft already holds from another chapter is
        not entered twice, and a starred card excluded by a held or taken one is left out."""
        # Jailbird is also a youth card, starred; and a youth card excluded by Spoiled.
        jailbird_beat = DistinctionOfferFactory(
            chapter=OfferChapter.BACKGROUNDS,
            beat=self.youth,
            appearance_section=None,
            prompt="",
            distinction=self.jailbird,
        )
        pampered = _answer(self.youth, "Pampered", -10, sort_order=9)
        pampered.distinction.mutually_exclusive_with.add(self.spoiled.distinction)
        for offer in (jailbird_beat, pampered):
            OfferFirstLook.objects.create(offer=offer, beginning=self.beginnings, preselected=True)
        draft = self._create_base_draft(first_name="Maud")
        draft.age = 19
        draft.save(update_fields=["age"])
        response = self.client.put(
            f"/api/distinctions/drafts/{draft.pk}/distinctions/sync/",
            {
                "distinctions": [
                    {"id": self.jailbird.pk, "rank": 1, "offer_id": self.jailbird_offer.pk}
                ]
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        response = self.client.post(self._url(draft, "load-default-life/"))
        self.assertEqual(response.status_code, 200, response.content)
        entries = response.json()["draft_data"]["distinctions"]
        names = sorted(e["distinction_name"] for e in entries)
        self.assertEqual(names, ["Extensively Tutored", "Jailbird", "Socialite", "Spoiled"])
        (jailbird_entry,) = [e for e in entries if e["distinction_name"] == "Jailbird"]
        self.assertEqual(jailbird_entry["offer_ids"], [self.jailbird_offer.pk])

    def test_a_changed_beginning_loads_its_own_life(self) -> None:
        other = BeginningsFactory(name="Another Beginning", starting_area=self.area, is_active=True)
        other.allowed_species.add(self.species)
        OfferFirstLook.objects.create(offer=self.hard, beginning=other, preselected=True)
        draft = self._create_base_draft(first_name="Maud")
        draft.age = 19
        draft.save(update_fields=["age"])
        response = self.client.post(self._url(draft, "load-default-life/"))
        self.assertIn("Spoiled", self._picks(response.json()))
        response = self.client.patch(
            self._url(draft), {"selected_beginnings_id": other.pk}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        response = self.client.post(self._url(draft, "load-default-life/"))
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(self._picks(payload), {"Hard scrabble": -10})
        self.assertEqual(payload["draft_data"]["life_loaded_for"], other.pk)

    def test_a_draft_with_no_beginning_loads_nothing(self) -> None:
        draft = self._create_base_draft(first_name="Maud")
        draft.selected_beginnings = None
        draft.save(update_fields=["selected_beginnings"])
        response = self.client.post(self._url(draft, "load-default-life/"))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["draft_data"].get("distinctions", []), [])
        self.assertNotIn("life_loaded_for", response.json()["draft_data"])

"""Journeys for a life in grids (#4395): a beginning strikes stages out of the life and
brings its own family route, an age-scaled beat allows one more pick per decade, and a life
picked straight from the grids, with a twin and a dead spouse seated beside the parents,
reaches the sheet and the kinship graph."""

from __future__ import annotations

from evennia_extensions.factories import AccountFactory
from integration_tests.harness import JourneyCase
from world.character_creation.constants import (
    BeatSelection,
    LifeStage,
    OfferChapter,
    Parentage,
)
from world.character_creation.factories import (
    BeginningsFactory,
    DistinctionOfferFactory,
    LifeBeatFactory,
    OriginTemplateFactory,
)
from world.character_creation.services import finalize_character
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin
from world.distinctions.factories import DistinctionFactory
from world.roster.factories import UnionKindFactory
from world.roster.models import Kinsperson, ParentageEdge, Union

STRANGERS_GAP = "The family paths for this beginning are not set up yet"


def _answer(beat, name: str, cost: int):
    return DistinctionOfferFactory(
        chapter=OfferChapter.BACKGROUNDS,
        beat=beat,
        appearance_section=None,
        prompt="",
        distinction=DistinctionFactory(name=name, cost_per_rank=cost, max_rank=1),
    )


class ALifeInGrids(FinalizationTestMixin, JourneyCase):
    """Five beats, one per stage, from the shared library; a Sleeper strikes three."""

    def setUp(self) -> None:
        super().setUp()
        self._flush_common_caches()
        self.account = AccountFactory()
        self._setup_finalization_base(self, prefix="Grids", height_min=700, height_max=800)
        UnionKindFactory(name="Marriage", confers_wedlock=True)
        # The route the base beginning carries: known parents, no family (the tarot name).
        self.route = OriginTemplateFactory(
            beginning=self.beginnings,
            allows_no_family=True,
            allows_name_family=False,
            parentage=Parentage.KNOWN,
        )
        self.household = LifeBeatFactory(name="How you were raised")
        self.spoiled = _answer(self.household, "Spoiled", 2)
        self.hard = _answer(self.household, "Hard scrabble", 2)
        self.youth = LifeBeatFactory(name="What they made of you", life_stage=LifeStage.YOUTH)
        self.apprenticed = _answer(self.youth, "Apprenticed", 2)
        self.known_for = LifeBeatFactory(
            name="What you were known for",
            life_stage=LifeStage.ADULTHOOD,
            selection=BeatSelection.ANY,
            picks_scale_with_age=True,
        )
        self.spied = _answer(self.known_for, "Spied for a house", 3)
        self.killed = _answer(self.known_for, "Killed for coin", 3)
        self.glimpse = LifeBeatFactory(name="The Glimpse", life_stage=LifeStage.AT_THE_GLIMPSE)
        self.carry = LifeBeatFactory(
            name="What you carry",
            life_stage=LifeStage.SINCE_THE_GLIMPSE,
            selection=BeatSelection.ANY,
        )
        self.client = self.api(self.account)

    def _draft_url(self, draft) -> str:
        return f"/api/character-creation/drafts/{draft.pk}/"

    def _beats(self, draft) -> list[dict]:
        response = self.client.get(f"{self._draft_url(draft)}beats/")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def _sync(self, draft, offers) -> object:
        return self.client.put(
            f"/api/distinctions/drafts/{draft.pk}/distinctions/sync/",
            {
                "distinctions": [
                    {"id": o.distinction_id, "rank": 1, "offer_id": o.pk} for o in offers
                ]
            },
            format="json",
        )

    def test_a_sleeper_meets_two_rows_and_its_beginning_brings_no_route(self) -> None:
        sleeper = BeginningsFactory(
            name="Sleeper",
            starting_area=self.area,
            frame="You woke with nothing behind you.",
            station="Nobody's",
            strikes_childhood=True,
            strikes_youth=True,
            strikes_adulthood=True,
        )
        draft = self._create_base_draft()
        response = self.client.patch(
            self._draft_url(draft), {"selected_beginnings_id": sleeper.pk}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertIsNone(body["selected_origin_template"])
        self.assertEqual(body["selected_beginnings"]["frame"], "You woke with nothing behind you.")
        self.assertTrue(body["selected_beginnings"]["strikes_childhood"])
        self.assertEqual([b["name"] for b in self._beats(draft)], ["The Glimpse", "What you carry"])
        errors = body["stage_errors"]
        self.assertIn(STRANGERS_GAP, errors[str(draft.Stage.LINEAGE)])

    def test_the_years_lived_set_the_known_for_allowance(self) -> None:
        draft = self._create_base_draft()
        draft.age = 19
        draft.save(update_fields=["age"])
        allowances = {b["name"]: b["allowance"] for b in self._beats(draft)}
        self.assertEqual(allowances["What you were known for"], 1)
        self.assertEqual(allowances["How you were raised"], 1)
        self.assertIsNone(allowances["What you carry"])

        response = self._sync(draft, [self.spied, self.killed])
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("1 career point on What you were known for", response.json()["detail"])

        response = self.client.patch(self._draft_url(draft), {"age": 50}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            {b["name"]: b["allowance"] for b in self._beats(draft)}["What you were known for"], 7
        )
        response = self._sync(draft, [self.spied, self.killed])
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(len(response.json()["distinctions"]), 2)

    def test_a_life_from_the_grids_with_a_twin_and_a_dead_spouse_reaches_the_sheet(
        self,
    ) -> None:
        draft = self._create_base_draft(line_parent_name="Mother", other_parent_name="Father")
        draft.selected_origin_template = self.route
        draft.save(update_fields=["selected_origin_template"])

        # The grids: a pick under a beat takes it; no "add" first.
        response = self._sync(draft, [self.spoiled, self.apprenticed, self.spied])
        self.assertEqual(response.status_code, 200, response.content)
        taken = {b["name"]: b["taken"] for b in self._beats(draft)}
        self.assertTrue(taken["How you were raised"])
        self.assertTrue(taken["What they made of you"])
        self.assertFalse(taken["The Glimpse"])
        # A swap on a one-of beat, and a line of the player's own under it.
        response = self._sync(draft, [self.hard, self.apprenticed, self.spied])
        self.assertEqual(response.status_code, 200, response.content)
        response = self.client.patch(
            self._draft_url(draft),
            {
                "draft_data": {
                    "beats": {str(self.household.pk): {"line": "Soft hands, hard lessons."}},
                    "kin_rows": [
                        {"kind": "twin", "name": "Wen", "gender_id": None, "fate": ""},
                        {"kind": "spouse", "name": "Ser Aldo", "gender_id": None, "fate": "dead"},
                    ],
                }
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)

        character = finalize_character(draft, add_to_roster=True)
        sheet = character.sheet_data

        staff = self.api(AccountFactory(is_staff=True))
        response = staff.get(f"/api/character-sheets/{sheet.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        beats = {row["name"]: row for row in response.data["beats"]}
        self.assertEqual(beats["How you were raised"]["answers"], ["Hard scrabble"])
        self.assertEqual(beats["How you were raised"]["line"], "Soft hands, hard lessons.")
        self.assertEqual(beats["What they made of you"]["answers"], ["Apprenticed"])
        self.assertEqual(beats["What you were known for"]["answers"], ["Spied for a house"])
        self.assertNotIn("The Glimpse", beats)

        node = Kinsperson.objects.get(sheet=sheet)
        twin = Kinsperson.objects.get(name="Wen")
        self.assertEqual(
            {e.parent.name for e in ParentageEdge.objects.filter(child=twin)}, {"Mother", "Father"}
        )
        spouse = Kinsperson.objects.get(name="Ser Aldo")
        self.assertTrue(spouse.is_deceased)
        union = Union.objects.get(members=node)
        self.assertIn(spouse, union.members.all())
        self.assertIsNotNone(union.ended_at)

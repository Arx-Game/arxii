"""Journeys: career points come with age and buy careers and ranks (#4829).

Slice 3 of #4813.

Maelis is fifty, which is seven career points: one at nineteen and one more every five
years. She syncs Sailor at rank four and Soldier at rank three, seven points; a fourth
rank on Soldier is refused by name. She cannot then be thirty-three, and the refusal
names forty-nine, the youngest age with seven points; forty-nine is accepted. Finalized,
she holds Sailor at four and Soldier at three. A nineteen-year-old holds one point.
The expected numbers come from the parent spec's slice 3 section and the card pass
ruling of 2026-10-29: one point at nineteen, one more every five years, capped at
fifty-nine, a point per career or rank.
"""

from __future__ import annotations

from integration_tests.harness import JourneyCase
from world.character_creation.constants import BeatSelection, LifeStage, OfferChapter
from world.character_creation.factories import DistinctionOfferFactory, LifeBeatFactory
from world.character_creation.services import finalize_character
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin
from world.distinctions.factories import DistinctionFactory
from world.distinctions.models import CharacterDistinction


class CareerPointsComeWithAge(FinalizationTestMixin, JourneyCase):
    """Maelis, fifty, and the Past Careers row."""

    def setUp(self) -> None:
        super().setUp()
        self._flush_common_caches()
        self.harbor = self.make_room("The Harbor")
        self.player = self.make_player("Maelis", room=self.harbor)
        self.account = self.account_of(self.player)
        # The finalization base: a realm, an area, a species, a beginning, a path, a
        # tradition, the rows a draft needs to finalize for real.
        self._setup_finalization_base(self, prefix="Careers", height_min=700, height_max=800)
        self.careers = LifeBeatFactory(
            name="Past Careers",
            life_stage=LifeStage.ADULTHOOD,
            selection=BeatSelection.ANY,
            picks_scale_with_age=True,
        )
        self.sailor = self._career("Sailor")
        self.soldier = self._career("Soldier")
        self.draft = self._create_base_draft(first_name="Maelis")
        self.draft.age = 50
        self.draft.save(update_fields=["age"])
        self.client = self.api(self.account)

    def _career(self, name: str):
        return DistinctionOfferFactory(
            chapter=OfferChapter.BACKGROUNDS,
            beat=self.careers,
            appearance_section=None,
            prompt="",
            distinction=DistinctionFactory(
                name=name, slug=name.lower(), cost_per_rank=0, max_rank=4
            ),
        )

    def sync(self, *picks: tuple[object, int]):
        return self.client.put(
            f"/api/distinctions/drafts/{self.draft.id}/distinctions/sync/",
            {
                "distinctions": [
                    {"id": offer.distinction_id, "rank": rank, "offer_id": offer.pk}
                    for offer, rank in picks
                ]
            },
            format="json",
        )

    def test_seven_points_at_fifty_buy_two_careers_and_their_ranks(self) -> None:
        beats = self.client.get(f"/api/character-creation/drafts/{self.draft.id}/beats/").json()
        (row,) = [b for b in beats if b["name"] == "Past Careers"]
        self.assertEqual((row["allowance"], row["allowance_is_points"]), (7, True))

        ok = self.sync((self.sailor, 4), (self.soldier, 3))
        self.assertEqual(ok.status_code, 200, ok.content)

        too_many = self.sync((self.sailor, 4), (self.soldier, 4))
        self.assertEqual(too_many.status_code, 400, too_many.content)
        self.assertIn("7 career points on Past Careers", too_many.json()["detail"])

        draft_url = f"/api/character-creation/drafts/{self.draft.id}/"
        younger = self.client.patch(draft_url, {"age": 33}, format="json")
        self.assertEqual(younger.status_code, 400, younger.content)
        self.assertIn("the youngest age with 7 is 49", str(younger.json()))
        fits = self.client.patch(draft_url, {"age": 49}, format="json")
        self.assertEqual(fits.status_code, 200, fits.content)

        self.draft.refresh_from_db()
        character = finalize_character(self.draft, add_to_roster=True)
        held = {
            row.distinction.name: row.rank
            for row in CharacterDistinction.objects.filter(character=character.sheet_data)
        }
        self.assertEqual((held["Sailor"], held["Soldier"]), (4, 3))

    def test_nineteen_holds_one_point(self) -> None:
        self.draft.age = 19
        self.draft.save(update_fields=["age"])
        beats = self.client.get(f"/api/character-creation/drafts/{self.draft.id}/beats/").json()
        (row,) = [b for b in beats if b["name"] == "Past Careers"]
        self.assertEqual(row["allowance"], 1)

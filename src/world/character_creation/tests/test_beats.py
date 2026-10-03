"""The Backgrounds beat library at character creation (#4124).

A beat is a prompt over priced distinction offers, pooled per life stage for every
Beginning that does not exclude it; its answers open when the beat is taken; a
one-of beat refuses a second answer; a Sleeper-style Beginning keeps one beat.
"""

from django.test import TestCase
from evennia.accounts.models import AccountDB
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
from world.character_creation.models import CharacterOriginSlot
from world.character_creation.offers import (
    beat_pool,
    beats_for,
    offers_for,
    one_of_beat_conflicts,
    reconcile_offer_picks,
    visible_offers,
)
from world.character_creation.services import finalize_character
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin
from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.factories import DistinctionFactory
from world.distinctions.models import CharacterDistinction
from world.progression.services.maturation import available_points, next_milestone_year
from world.roster.factories import RosterEntryFactory
from world.secrets.factories import SecretFactory
from world.secrets.services import grant_secret_knowledge


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
        self.assertTrue(entries[0].kept)


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
                    "kept": False,
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


class FinalizeBeatsTest(FinalizationTestMixin, TestCase):
    """A finalized draft carries its beats onto the sheet (#4124)."""

    def setUp(self) -> None:
        self._flush_common_caches()
        self.account = AccountDB.objects.create(username="beats_finalize")
        self._setup_finalization_base(self, prefix="Beats", height_min=700, height_max=800)
        self.household = LifeBeatFactory(name="The household")
        self.patient = _answer(self.household, "Patient", 10)
        self.work = LifeBeatFactory(
            name="The work", life_stage=LifeStage.ADULTHOOD, selection=BeatSelection.ANY
        )
        self.youth = LifeBeatFactory(name="The first rule", life_stage=LifeStage.YOUTH)

    def test_taken_beats_become_rows_and_draft_the_background(self) -> None:
        draft = self._create_base_draft()
        draft.draft_data["beats"] = {
            str(self.household.pk): {"taken": True, "line": "A line about the house."},
            str(self.youth.pk): {"taken": True, "unknown": True},
        }
        draft.draft_data["distinctions"] = [
            {
                "distinction_id": self.patient.distinction_id,
                "distinction_name": "Patient",
                "rank": 1,
                "cost": 10,
                "offer_ids": [self.patient.pk],
                "sources": ["The household"],
                "arrivals": [OfferArrival.CHOICE],
            }
        ]
        draft.save()

        character = finalize_character(draft, add_to_roster=True)
        sheet = character.sheet_data

        rows = {row.beat_id: row for row in CharacterOriginSlot.objects.filter(sheet=sheet)}
        self.assertEqual(set(rows), {self.household.pk, self.youth.pk})
        self.assertEqual(rows[self.household.pk].value, "A line about the house.")
        self.assertFalse(rows[self.household.pk].unknown)
        self.assertTrue(rows[self.youth.pk].unknown)
        self.assertIsNone(rows[self.household.pk].slot_id)
        held = CharacterDistinction.objects.get(
            character=sheet, distinction=self.patient.distinction
        )
        self.assertEqual(held.source_description, "The household")
        background = sheet.true_profile.background
        self.assertIn("Childhood: The household", background)
        self.assertIn("A line about the house.", background)
        self.assertNotIn("The first rule", background)
        # Age is experience through beats, not banked points (#4124).
        self.assertEqual(sheet.maturation_floor, 25)
        self.assertEqual(available_points(sheet), 0)

    def test_an_untaken_pool_writes_nothing(self) -> None:
        draft = self._create_base_draft()
        draft.save()
        character = finalize_character(draft, add_to_roster=True)
        self.assertFalse(CharacterOriginSlot.objects.filter(sheet=character.sheet_data).exists())


class MaturationFloorTest(TestCase):
    """Milestones at or below the creation age never bank (#4124)."""

    def test_a_character_made_at_forty_five_starts_at_zero_and_earns_at_forty_seven(self):
        sheet = CharacterSheetFactory(matured_years=45, maturation_floor=45)
        self.assertEqual(available_points(sheet), 0)
        self.assertEqual(next_milestone_year(sheet.matured_years), 47)
        sheet.matured_years = 47
        sheet.save(update_fields=["matured_years"])
        self.assertEqual(available_points(sheet), 1)

    def test_a_character_made_before_the_rule_keeps_its_bank(self):
        sheet = CharacterSheetFactory(matured_years=45, maturation_floor=0)
        self.assertGreater(available_points(sheet), 0)


class SpeciesPriceTest(TestCase):
    """An eternal-youth species prices its long life into the purse (#4124)."""

    def test_the_species_own_cost_rides_the_species_line(self):
        from world.species.factories import SpeciesFactory

        species = SpeciesFactory(name="Elf", eternal_youth=True, cg_point_cost=12)
        draft = CharacterDraftFactory(selected_species=species)
        lines = [e for e in draft.calculate_cg_points_breakdown() if e["category"] == "species"]
        self.assertEqual(lines, [{"category": "species", "item": "Elf", "cost": 12}])


class SecretResolvesBeatTest(TestCase):
    """A secret naming an unknown beat fills it in when the subject learns it (#4124)."""

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.entry = RosterEntryFactory(character_sheet=cls.sheet)
        cls.beat = LifeBeatFactory(name="The work", life_stage=LifeStage.ADULTHOOD)
        cls.row = CharacterOriginSlot.objects.create(
            sheet=cls.sheet, beat=cls.beat, unknown=True, value=""
        )
        cls.secret = SecretFactory(subject_sheet=cls.sheet, resolves_beat=cls.row)

    def test_the_subject_learning_it_resolves_the_beat(self):
        grant_secret_knowledge(roster_entry=self.entry, secret=self.secret)
        self.row.refresh_from_db()
        self.assertFalse(self.row.unknown)

    def test_someone_else_learning_it_does_not(self):
        other = RosterEntryFactory()
        grant_secret_knowledge(roster_entry=other, secret=self.secret)
        self.row.refresh_from_db()
        self.assertTrue(self.row.unknown)


class LifeBeatAdminTest(TestCase):
    """The beat library admin (#4124): answers save as Backgrounds choices on the beat."""

    @classmethod
    def setUpTestData(cls):
        from evennia_extensions.factories import AccountFactory as _AccountFactory

        cls.staff = _AccountFactory(is_staff=True, is_superuser=True)
        cls.distinction = DistinctionFactory(name="Patient", cost_per_rank=10, max_rank=1)
        cls.beginning = BeginningsFactory(name="Sleeper")

    def test_adding_a_beat_with_an_answer_and_an_exclusion(self):
        from django.urls import reverse

        self.client.force_login(self.staff)
        offers_prefix = "distinction_offers"
        exclusions_prefix = "exclusions"
        data = {
            "name": "The household",
            "life_stage": LifeStage.CHILDHOOD,
            "prompt": "Placeholder prompt.",
            "selection": BeatSelection.ONE_OF,
            "sort_order": 1,
            "is_active": "on",
            f"{offers_prefix}-TOTAL_FORMS": "1",
            f"{offers_prefix}-INITIAL_FORMS": "0",
            f"{offers_prefix}-MIN_NUM_FORMS": "0",
            f"{offers_prefix}-MAX_NUM_FORMS": "1000",
            f"{offers_prefix}-0-distinction": self.distinction.pk,
            f"{offers_prefix}-0-name": "",
            f"{offers_prefix}-0-player_line": "Placeholder gloss.",
            f"{offers_prefix}-0-sort_order": "0",
            f"{offers_prefix}-0-is_active": "on",
            f"{exclusions_prefix}-TOTAL_FORMS": "1",
            f"{exclusions_prefix}-INITIAL_FORMS": "0",
            f"{exclusions_prefix}-MIN_NUM_FORMS": "0",
            f"{exclusions_prefix}-MAX_NUM_FORMS": "1000",
            f"{exclusions_prefix}-0-beginning": self.beginning.pk,
            f"{exclusions_prefix}-0-reason": "Starts blank.",
        }
        response = self.client.post(reverse("admin:arxii_lifebeat_add"), data, follow=True)
        self.assertEqual(response.status_code, 200)
        from world.character_creation.models import LifeBeat

        beat = LifeBeat.objects.get(name="The household")
        (offer,) = beat.distinction_offers.all()
        self.assertEqual(offer.chapter, OfferChapter.BACKGROUNDS)
        self.assertEqual(offer.arrives_as, OfferArrival.CHOICE)
        self.assertEqual(offer.name, "Patient")
        self.assertEqual([e.beginning_id for e in beat.exclusions.all()], [self.beginning.pk])

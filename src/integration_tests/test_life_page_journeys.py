"""Journeys for the life page's backend (#4872, slice 9 of #4813): the offers carry a
beat answer's group, its effects with magnitudes and the terms' definitions read from the
rows that own them; a paragraph per stage, a stage marked unknown, a secret answer with a
cover story and a figure's name on a person card reach the sheet; a cover with no secret
and a secret on an unpicked answer write nothing; the first name is asked on the Origin
stage."""

from __future__ import annotations

from evennia_extensions.factories import AccountFactory
from integration_tests.harness import JourneyCase
from world.character_creation.constants import BeatSelection, LifeStage, OfferChapter
from world.character_creation.factories import (
    DistinctionOfferFactory,
    LifeBeatFactory,
)
from world.character_creation.services import finalize_character
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin
from world.classes.factories import AspectFactory
from world.distinctions.factories import DistinctionEffectFactory, DistinctionFactory
from world.distinctions.models import CharacterDistinction
from world.mechanics.factories import ModifierTargetFactory
from world.mechanics.models import CharacterModifier
from world.traits.factories import SkillTraitFactory


def _answer(beat, name: str, cost: int, *, group: str = "", **distinction_kwargs):
    return DistinctionOfferFactory(
        chapter=OfferChapter.BACKGROUNDS,
        beat=beat,
        appearance_section=None,
        prompt="",
        group=group,
        distinction=DistinctionFactory(
            name=name, cost_per_rank=cost, max_rank=1, **distinction_kwargs
        ),
    )


class TheLifePage(FinalizationTestMixin, JourneyCase):
    """Three beats: a one-of childhood row with two answers, an any-that-apply youth row
    holding a person card, and one adulthood row left to mark unknown."""

    def setUp(self) -> None:
        super().setUp()
        self._flush_common_caches()
        self.account = AccountFactory()
        self._setup_finalization_base(self, prefix="LifePage", height_min=700, height_max=800)
        self.household = LifeBeatFactory(name="Early Upbringing")
        self.spoiled = _answer(self.household, "Spoiled", 2, group="Treatment")
        self.hard = _answer(self.household, "Hard scrabble", -2, group="Treatment")
        self.youth = LifeBeatFactory(
            name="Influences", life_stage=LifeStage.YOUTH, selection=BeatSelection.ANY
        )
        self.rival = _answer(self.youth, "Rival", 1, asks_figure_name=True)
        self.known_for = LifeBeatFactory(
            name="What you were known for",
            life_stage=LifeStage.ADULTHOOD,
            selection=BeatSelection.ANY,
        )
        self.spied = _answer(self.known_for, "Spied for a house", 3)
        # The terms on Spoiled's card: a skill-bound lever reads the Trait's own words,
        # an aspect-bound one the Aspect's, a plain lever the target's.
        sailing = SkillTraitFactory(name="Sailing", description="Handling a ship at sea.")
        self.sailing_target = ModifierTargetFactory(
            name="sailing", target_trait=sailing, description="TODO"
        )
        martial = AspectFactory(name="Martial", description="The fighting arts.")
        self.martial_target = ModifierTargetFactory(
            name="martial", target_aspect=martial, description="TODO"
        )
        self.allure_target = ModifierTargetFactory(
            name="allure", description="How much people want to be near you."
        )
        DistinctionEffectFactory(
            distinction=self.spoiled.distinction, target=self.sailing_target, value_per_rank=10
        )
        DistinctionEffectFactory(
            distinction=self.spoiled.distinction, target=self.martial_target, value_per_rank=-5
        )
        DistinctionEffectFactory(
            distinction=self.hard.distinction, target=self.allure_target, value_per_rank=2
        )
        self.client = self.api(self.account)

    def _draft_url(self, draft) -> str:
        return f"/api/character-creation/drafts/{draft.pk}/"

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

    def _patch(self, draft, draft_data: dict) -> object:
        return self.client.patch(self._draft_url(draft), {"draft_data": draft_data}, format="json")

    def test_the_offers_carry_groups_magnitudes_and_the_terms_definitions(self) -> None:
        draft = self._create_base_draft()
        response = self.client.get(f"{self._draft_url(draft)}offers/?chapter=backgrounds")
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        offers = {o["name"]: o for o in body["offers"]}
        self.assertEqual(offers["Spoiled"]["group"], "Treatment")
        self.assertEqual(offers["Rival"]["group"], "")
        self.assertTrue(offers["Rival"]["asks_figure_name"])
        self.assertFalse(offers["Spoiled"]["asks_figure_name"])
        self.assertEqual(
            offers["Spoiled"]["effects"],
            [
                {"target": "sailing", "label": "sailing", "value": 10, "immune": False},
                {"target": "martial", "label": "martial", "value": -5, "immune": False},
            ],
        )
        # The sign-and-name line the list layouts print is unchanged.
        self.assertEqual(offers["Spoiled"]["effect_line"], "+Sailing; -Martial")
        terms = {t["name"]: t for t in body["terms"]}
        self.assertEqual(set(terms), {"sailing", "martial", "allure"})
        self.assertEqual(terms["sailing"]["definition"], "Handling a ship at sea.")
        self.assertEqual(terms["martial"]["definition"], "The fighting arts.")
        self.assertEqual(terms["allure"]["definition"], "How much people want to be near you.")

    def test_a_paragraph_an_unknown_stage_a_secret_with_a_cover_and_a_figure_reach_the_sheet(
        self,
    ) -> None:
        draft = self._create_base_draft()
        response = self._sync(draft, [self.hard, self.rival])
        self.assertEqual(response.status_code, 200, response.content)
        response = self._patch(
            draft,
            {
                "beats": {
                    str(self.household.pk): {
                        "secret_offer_ids": [self.hard.pk],
                        "cover_offer_id": self.spoiled.pk,
                    },
                    str(self.youth.pk): {"figures": {str(self.rival.pk): "Ser Gaston"}},
                    str(self.known_for.pk): {"unknown": True},
                },
                "stage_descriptions": {"childhood": "Soft hands, hard lessons."},
            },
        )
        self.assertEqual(response.status_code, 200, response.content)

        character = finalize_character(draft, add_to_roster=True)
        sheet = character.sheet_data

        background = sheet.true_profile.background
        self.assertIn("Childhood\nSoft hands, hard lessons.", background)
        self.assertIn("Childhood: Early Upbringing", background)
        self.assertIn("Before the Glimpse: unknown", background)
        self.assertNotIn("What you were known for", background)

        hard = CharacterDistinction.objects.get(character=sheet, distinction=self.hard.distinction)
        self.assertIsNotNone(hard.secret)
        self.assertFalse(hard.is_cover)
        cover = CharacterDistinction.objects.get(
            character=sheet, distinction=self.spoiled.distinction
        )
        self.assertTrue(cover.is_cover)
        self.assertIsNone(cover.secret)
        self.assertEqual(cover.source_description, "cover on Early Upbringing")
        # The cover grants nothing: no modifier reaches the sheet from Spoiled's effects.
        self.assertFalse(
            CharacterModifier.objects.filter(
                character=sheet, target__in=[self.sailing_target, self.martial_target]
            ).exists()
        )
        self.assertTrue(
            CharacterModifier.objects.filter(character=sheet, target=self.allure_target).exists()
        )
        rival = CharacterDistinction.objects.get(
            character=sheet, distinction=self.rival.distinction
        )
        self.assertEqual(rival.notes, "Ser Gaston")

        # A stranger reads the cover where the secret is absent; staff see it flagged.
        stranger = self.api(AccountFactory())
        response = stranger.get(f"/api/character-sheets/{sheet.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        public = {d["name"]: d for d in response.data["distinctions"]}
        self.assertIn("Spoiled", public)
        self.assertNotIn("Hard scrabble", public)
        staff = self.api(AccountFactory(is_staff=True))
        response = staff.get(f"/api/character-sheets/{sheet.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        held = {d["name"]: d for d in response.data["distinctions"]}
        self.assertTrue(held["Spoiled"]["is_cover"])
        self.assertTrue(held["Hard scrabble"]["is_secret"])
        self.assertFalse(held["Hard scrabble"]["is_cover"])

    def test_a_cover_with_no_secret_and_a_secret_on_an_unpicked_answer_write_nothing(
        self,
    ) -> None:
        draft = self._create_base_draft()
        response = self._sync(draft, [self.hard])
        self.assertEqual(response.status_code, 200, response.content)
        response = self._patch(
            draft,
            {
                "beats": {
                    # A cover with nothing to hide, and a secret mark on the answer the
                    # draft did not pick.
                    str(self.household.pk): {
                        "secret_offer_ids": [self.spoiled.pk],
                        "cover_offer_id": self.spoiled.pk,
                    },
                }
            },
        )
        self.assertEqual(response.status_code, 200, response.content)

        character = finalize_character(draft, add_to_roster=True)
        sheet = character.sheet_data
        hard = CharacterDistinction.objects.get(character=sheet, distinction=self.hard.distinction)
        self.assertIsNone(hard.secret)
        self.assertFalse(
            CharacterDistinction.objects.filter(character=sheet, is_cover=True).exists()
        )
        self.assertFalse(
            CharacterDistinction.objects.filter(
                character=sheet, distinction=self.spoiled.distinction
            ).exists()
        )

    def test_the_marks_and_the_paragraphs_are_checked_for_shape(self) -> None:
        draft = self._create_base_draft()
        for bad in (
            {"beats": {str(self.household.pk): {"secret_offer_ids": "all"}}},
            {"beats": {str(self.household.pk): {"cover_offer_id": "Spoiled"}}},
            {"beats": {str(self.household.pk): {"figures": {"Rival": "Ser Gaston"}}}},
            {"beats": {str(self.household.pk): {"figures": {"1": "x" * 61}}}},
            {"stage_descriptions": {"midlife": "No such stage."}},
            {"stage_descriptions": {"childhood": "x" * 1001}},
        ):
            response = self._patch(draft, bad)
            self.assertEqual(response.status_code, 400, (bad, response.content))

    def test_the_first_name_is_asked_on_the_origin_stage(self) -> None:
        draft = self._create_base_draft(first_name="")
        response = self.client.get(self._draft_url(draft))
        self.assertEqual(response.status_code, 200, response.content)
        errors = response.json()["stage_errors"]
        self.assertIn("Enter a first name", errors[str(draft.Stage.ORIGIN)])
        self.assertEqual(errors[str(draft.Stage.IDENTITY)], [])
        response = self._patch(draft, {"first_name": "Marisol"})
        self.assertEqual(response.status_code, 200, response.content)
        errors = response.json()["stage_errors"]
        self.assertNotIn("Enter a first name", errors[str(draft.Stage.ORIGIN)])

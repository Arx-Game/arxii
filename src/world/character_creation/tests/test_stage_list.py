"""What the stage list is told about each stage (#5199).

The owner's rulings of 2026-11-18: a stage's to-do shows only once the player has opened
that stage, a stage lists only what is asked on it, and a stage that asks nothing reads
"optional". These tests read a draft the way the page does and move it between stages
through the same PATCH the page sends.
"""

from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.character_creation.constants import (
    OPTIONAL_STAGES,
    REQUIRED_STATS,
    STAT_DEFAULT_VALUE,
    FamilyPath,
    Stage,
)
from world.character_creation.factories import CharacterDraftFactory, OriginTemplateFactory
from world.character_creation.models import DraftStageVisit
from world.character_creation.validators import (
    get_all_stage_errors,
    get_attributes_errors,
    get_heritage_errors,
    get_lineage_errors,
    get_origin_errors,
)
from world.roster.factories import FamilyFactory
from world.tarot.factories import TarotCardFactory


class VisitedStagesTests(TestCase):
    def setUp(self) -> None:
        self.account = AccountFactory()
        self.draft = CharacterDraftFactory(account=self.account)
        self.client = APIClient()
        self.client.force_authenticate(self.account)
        self.url = f"/api/character-creation/drafts/{self.draft.pk}/"

    def _move(self, stage: Stage) -> list[int]:
        response = self.client.patch(self.url, {"current_stage": int(stage)}, format="json")
        assert response.status_code == 200, response.content
        return response.json()["visited_stages"]

    def test_a_new_draft_has_been_opened_on_origin_alone(self):
        body = self.client.get(self.url).json()
        assert body["visited_stages"] == [int(Stage.ORIGIN)]
        # Standing on a stage is not a row; the first move writes the stage it left.
        assert not DraftStageVisit.objects.filter(draft=self.draft).exists()

    def test_moving_records_the_stage_left_and_the_stage_opened(self):
        assert self._move(Stage.ATTRIBUTES) == [int(Stage.ORIGIN), int(Stage.ATTRIBUTES)]
        # A reload reads the same list from the server.
        assert self.client.get(self.url).json()["visited_stages"] == [1, 7]

    def test_a_stage_jumped_over_is_not_visited(self):
        self._move(Stage.ATTRIBUTES)
        visited = self._move(Stage.HERITAGE)
        assert visited == [int(Stage.ORIGIN), int(Stage.HERITAGE), int(Stage.ATTRIBUTES)]
        assert int(Stage.LINEAGE) not in visited
        assert int(Stage.PATH) not in visited

    def test_opening_a_stage_twice_keeps_one_row(self):
        self._move(Stage.PATH)
        self._move(Stage.ORIGIN)
        self._move(Stage.PATH)
        stages = list(
            DraftStageVisit.objects.filter(draft=self.draft).values_list("stage", flat=True)
        )
        assert stages == [int(Stage.ORIGIN), int(Stage.PATH)]

    def test_a_save_that_does_not_move_the_draft_writes_no_visit(self):
        response = self.client.patch(self.url, {"draft_data": {"concept": "x"}}, format="json")
        assert response.status_code == 200, response.content
        assert not DraftStageVisit.objects.filter(draft=self.draft).exists()

    def test_the_client_cannot_write_the_list(self):
        response = self.client.patch(
            self.url, {"visited_stages": [int(stage) for stage in Stage]}, format="json"
        )
        assert response.status_code == 200, response.content
        assert response.json()["visited_stages"] == [int(Stage.ORIGIN)]

    def test_the_visits_go_with_the_draft(self):
        self._move(Stage.PATH)
        self.draft.delete()
        assert not DraftStageVisit.objects.exists()


class OptionalStagesTests(TestCase):
    def setUp(self) -> None:
        self.account = AccountFactory()
        self.draft = CharacterDraftFactory(account=self.account)

    def test_the_response_names_identity_and_final_touches(self):
        client = APIClient()
        client.force_authenticate(self.account)
        body = client.get(f"/api/character-creation/drafts/{self.draft.pk}/").json()
        assert body["optional_stages"] == [int(Stage.IDENTITY), int(Stage.FINAL_TOUCHES)]

    def test_an_optional_stage_asks_nothing_of_a_draft_with_nothing_chosen(self):
        """The list is true only while these validators want nothing: a requirement
        added to one of them has to take the stage out of ``OPTIONAL_STAGES``."""
        errors = get_all_stage_errors(self.draft)
        for stage in OPTIONAL_STAGES:
            assert errors[stage] == [], stage.label

    def test_every_other_stage_asks_something_of_that_draft(self):
        errors = get_all_stage_errors(self.draft)
        for stage in Stage:
            if stage in OPTIONAL_STAGES or stage in (Stage.REVIEW, Stage.ORIGIN):
                continue
            assert errors[stage], stage.label


class StageAsksOnlyItsOwnTests(TestCase):
    def test_heritage_does_not_list_what_lineage_asks(self):
        template = OriginTemplateFactory(allows_no_family=True)
        draft = CharacterDraftFactory(
            selected_area=template.beginning.starting_area,
            selected_beginnings=template.beginning,
            selected_origin_template=template,
        )
        lineage = get_lineage_errors(draft)
        heritage = get_heritage_errors(draft)
        # Lineage has something left to ask, and none of it is repeated on Heritage.
        assert lineage
        assert not set(lineage) & set(heritage)
        assert heritage == ["Select a species", "Select a gender"]

    def test_lineage_with_no_beginning_points_at_heritage(self):
        draft = CharacterDraftFactory()
        assert get_lineage_errors(draft) == ["Choose a beginning on Heritage first"]

    def test_lineage_keeps_the_staff_gap_line_for_a_beginning_with_no_route(self):
        template = OriginTemplateFactory()
        draft = CharacterDraftFactory(
            selected_area=template.beginning.starting_area,
            selected_beginnings=template.beginning,
        )
        assert draft.selected_origin_template is None
        assert get_lineage_errors(draft) == [
            "The family paths for this beginning are not set up yet"
        ]

    def test_missing_statistics_are_asked_for_in_plain_words(self):
        draft = CharacterDraftFactory()
        errors = get_attributes_errors(draft)
        assert "Set your statistics" in errors
        assert not any("strength" in error for error in errors)


class StageListWordingTests(TestCase):
    """The stage list prints a stage's first error as written, so each is a plain line (#5331)."""

    def test_origin_asks_for_a_starting_realm_as_the_page_does(self):
        draft = CharacterDraftFactory(selected_area=None)
        assert get_origin_errors(draft)[0] == "Select a starting realm"

    def test_points_left_to_place_agree_with_their_number(self):
        draft = CharacterDraftFactory()
        draft.draft_data = {"stats": dict.fromkeys(REQUIRED_STATS, STAT_DEFAULT_VALUE)}
        draft.save()
        assert get_attributes_errors(draft) == ["110 points remaining to allocate"]

    def test_points_over_the_budget_agree_with_their_number(self):
        draft = CharacterDraftFactory()
        draft.draft_data = {"stats": dict.fromkeys(REQUIRED_STATS, 30)}
        draft.save()
        assert get_attributes_errors(draft) == ["10 points over budget"]

    def test_one_point_is_a_point(self):
        # The page places statistics in tens, so one point left over takes a spread the
        # page cannot send: eleven at 30 and one at 19 is 349 of 350.
        stats = dict.fromkeys(REQUIRED_STATS, 30)
        stats[next(iter(stats))] = 19
        draft = CharacterDraftFactory()
        draft.draft_data = {"stats": stats}
        draft.save()
        assert "1 point remaining to allocate" in get_attributes_errors(draft)


class SurnameTests(TestCase):
    """The surname the side panel shows on every stage, by family path."""

    def _draft(self, **route):
        paths = {
            "allows_claim_family": False,
            "allows_name_family": False,
            "allows_no_family": False,
        } | route
        template = OriginTemplateFactory(**paths)
        return CharacterDraftFactory(
            selected_area=template.beginning.starting_area,
            selected_beginnings=template.beginning,
            selected_origin_template=template,
        )

    def test_no_route_has_no_surname(self):
        assert CharacterDraftFactory().surname() == ""

    def test_a_claimed_family_gives_its_name(self):
        draft = self._draft(allows_claim_family=True)
        assert draft.resolve_family_path() == FamilyPath.CLAIMED
        assert draft.surname() == ""
        draft.family = FamilyFactory(name="Thrax")
        assert draft.surname() == "Thrax"

    def test_a_new_family_gives_the_name_typed_for_it(self):
        draft = self._draft(allows_name_family=True)
        assert draft.resolve_family_path() == FamilyPath.NAMED
        draft.draft_data = {"new_family_name": "  Valardin "}
        assert draft.surname() == "Valardin"

    def test_no_family_gives_the_drawn_cards_surname(self):
        card = TarotCardFactory(name="The Fool", latin_name="Stultus")
        draft = self._draft(allows_no_family=True)
        assert draft.resolve_family_path() == FamilyPath.NONE
        # Nothing drawn yet.
        assert draft.surname() == ""
        draft.draft_data = {"tarot_card_name": card.name}
        assert draft.surname() == card.get_surname(False) == "Stultus"
        draft.draft_data = {"tarot_card_name": card.name, "tarot_reversed": True}
        assert draft.surname() == card.get_surname(True)
        assert draft.surname() != "Stultus"

    def test_a_card_that_no_longer_exists_gives_no_surname(self):
        draft = self._draft(allows_no_family=True)
        draft.draft_data = {"tarot_card_name": "A card nobody authored"}
        assert draft.surname() == ""

    def test_the_draft_response_carries_it(self):
        card = TarotCardFactory(name="The Tower", latin_name="Turris")
        draft = self._draft(allows_no_family=True)
        draft.draft_data = {"tarot_card_name": card.name}
        draft.save()
        client = APIClient()
        client.force_authenticate(draft.account)
        body = client.get(f"/api/character-creation/drafts/{draft.pk}/").json()
        assert body["surname"] == "Turris"


class ClearedStatisticsTests(TestCase):
    """A draft whose statistics were cleared still reads (#5199).

    The draft serializer merges ``draft_data`` key by key, so ``{"stats": null}`` leaves
    the key in place holding ``None``. The Attributes validator took that for a dict, and
    every read of the draft answered 500 from then on.
    """

    def setUp(self) -> None:
        self.account = AccountFactory()
        self.draft = CharacterDraftFactory(account=self.account)
        self.client = APIClient()
        self.client.force_authenticate(self.account)
        self.url = f"/api/character-creation/drafts/{self.draft.pk}/"

    def test_a_draft_with_its_statistics_set_to_null_reads_and_asks_for_them(self):
        saved = self.client.patch(self.url, {"draft_data": {"stats": None}}, format="json")
        assert saved.status_code == 200, saved.content
        body = self.client.get(self.url).json()
        assert "Set your statistics" in body["stage_errors"][str(int(Stage.ATTRIBUTES))]
        # The budget less the default spread, as for a draft that never saved any.
        fresh = CharacterDraftFactory()
        assert body["stats_points_remaining"] == fresh.calculate_points_remaining()

    def test_the_final_statistics_of_such_a_draft_are_the_defaults(self):
        self.draft.draft_data = {"stats": None}
        assert set(self.draft.calculate_final_stats().values()) == {20}

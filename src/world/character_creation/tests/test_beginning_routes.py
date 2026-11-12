"""A beginning is a frame and a strike-list (#4395): its route is assigned with it, and its
general prompts never render."""

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.character_creation.constants import (
    FamilyPath,
    Parentage,
    QuestionKind,
)
from world.character_creation.factories import (
    BeginningsFactory,
    CharacterDraftFactory,
    OriginTemplateFactory,
    OriginTemplateSlotFactory,
)
from world.character_creation.questionnaire import visible_slot_ids
from world.character_creation.validators import get_lineage_errors


class RouteFollowsTheBeginningTests(TestCase):
    """The Upbringing pick retired: the beginning's one route comes with it."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        cls.noble = BeginningsFactory(name="Nobility", frame="Born to a house.", station="Noble")
        cls.noble_route = OriginTemplateFactory(
            beginning=cls.noble, allows_claim_family=True, allows_no_family=True
        )
        cls.sleeper = BeginningsFactory(
            name="Sleeper",
            strikes_childhood=True,
            strikes_youth=True,
            strikes_adulthood=True,
            struck_stages_text="Your new life begins now without any memory of who you were.",
        )
        cls.sleeper_route = OriginTemplateFactory(
            beginning=cls.sleeper, allows_no_family=True, parentage=Parentage.UNKNOWN
        )
        cls.bare = BeginningsFactory(name="Peerage")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)
        self.draft = CharacterDraftFactory(
            account=self.account, selected_area=self.noble.starting_area
        )
        self.url = f"/api/character-creation/drafts/{self.draft.pk}/"

    def test_picking_a_beginning_brings_its_route_and_a_change_drops_the_old_family(self):
        res = self.client.patch(self.url, {"selected_beginnings_id": self.noble.pk}, format="json")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["selected_origin_template"]["id"], self.noble_route.pk)
        res = self.client.patch(self.url, {"family_path": FamilyPath.NONE}, format="json")
        self.assertEqual(res.status_code, 200, res.content)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.family_path, FamilyPath.NONE)

        for beginning in (self.sleeper, self.bare):
            beginning.starting_area = self.noble.starting_area
            beginning.save(update_fields=["starting_area"])
        res = self.client.patch(
            self.url, {"selected_beginnings_id": self.sleeper.pk}, format="json"
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.selected_origin_template_id, self.sleeper_route.pk)
        self.assertEqual(self.draft.family_path, "")

        res = self.client.patch(self.url, {"selected_beginnings_id": self.bare.pk}, format="json")
        self.assertEqual(res.status_code, 200, res.content)
        self.draft.refresh_from_db()
        self.assertIsNone(self.draft.selected_origin_template_id)
        self.assertEqual(
            get_lineage_errors(self.draft),
            ["The family paths for this beginning are not set up yet"],
        )

    def test_the_beginnings_payload_carries_frame_station_and_strikes(self):
        res = self.client.get(
            f"/api/character-creation/beginnings/?starting_area={self.noble.starting_area.pk}"
        )
        self.assertEqual(res.status_code, 200, res.content)
        rows = res.json()
        rows = rows["results"] if isinstance(rows, dict) else rows
        by_name = {row["name"]: row for row in rows}
        self.assertEqual(by_name["Nobility"]["frame"], "Born to a house.")
        self.assertEqual(by_name["Nobility"]["station"], "Noble")
        self.assertFalse(by_name["Nobility"]["strikes_childhood"])
        self.assertEqual(by_name["Nobility"]["struck_stages_text"], "")

    def test_a_beginning_that_strikes_every_stage_carries_its_text(self):
        """The life page shows this in place of the stage rows (#4830)."""
        res = self.client.get(
            f"/api/character-creation/beginnings/?starting_area={self.sleeper.starting_area.pk}"
        )
        self.assertEqual(res.status_code, 200, res.content)
        rows = res.json()
        rows = rows["results"] if isinstance(rows, dict) else rows
        sleeper = {row["name"]: row for row in rows}["Sleeper"]
        self.assertTrue(sleeper["strikes_adulthood"])
        self.assertEqual(
            sleeper["struck_stages_text"],
            "Your new life begins now without any memory of who you were.",
        )


class GeneralPromptsRetiredTests(TestCase):
    """A question on every path never renders; a path-scoped one still does."""

    @classmethod
    def setUpTestData(cls):
        cls.route = OriginTemplateFactory(allows_no_family=True, allows_name_family=False)
        cls.general = OriginTemplateSlotFactory(
            template=cls.route,
            name="A memory",
            kind=QuestionKind.TEXT,
            applies_to=FamilyPath.ANY,
            is_required=True,
        )
        cls.scoped = OriginTemplateSlotFactory(
            template=cls.route,
            name="The ritual",
            kind=QuestionKind.TEXT,
            applies_to=FamilyPath.NONE,
            is_required=True,
        )

    def test_only_the_path_scoped_prompt_shows_and_is_required(self):
        draft = CharacterDraftFactory(
            selected_beginnings=self.route.beginning, selected_origin_template=self.route
        )
        self.assertEqual(visible_slot_ids(draft), {self.scoped.pk})
        errors = get_lineage_errors(draft)
        self.assertTrue(any("The ritual" in e for e in errors), errors)
        self.assertFalse(any("A memory" in e for e in errors), errors)

    def test_the_route_payload_leaves_the_general_prompt_out(self):
        account = AccountFactory()
        draft = CharacterDraftFactory(
            account=account,
            selected_beginnings=self.route.beginning,
            selected_origin_template=self.route,
        )
        client = APIClient()
        client.force_authenticate(user=account)
        res = client.get(f"/api/character-creation/drafts/{draft.pk}/")
        self.assertEqual(res.status_code, 200, res.content)
        names = [s["name"] for s in res.json()["selected_origin_template"]["slots"]]
        self.assertEqual(names, ["The ritual"])

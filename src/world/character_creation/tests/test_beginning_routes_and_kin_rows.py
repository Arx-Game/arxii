"""A beginning is a frame and a strike-list (#4395): its route is assigned with it, its
general prompts never render, and the people seated beside the parents are kin rows the
finalize writes into the kinship graph."""

from django.test import TestCase
from evennia.accounts.models import AccountDB
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.character_creation.constants import (
    ChildFate,
    FamilyPath,
    KinRowKind,
    Parentage,
    QuestionKind,
    SpouseFate,
)
from world.character_creation.factories import (
    BeginningsFactory,
    CharacterDraftFactory,
    OriginTemplateFactory,
    OriginTemplateSlotFactory,
)
from world.character_creation.questionnaire import visible_slot_ids
from world.character_creation.services import finalize_character
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin
from world.character_creation.validators import get_lineage_errors
from world.roster.factories import UnionKindFactory
from world.roster.models import Kinsperson, ParentageEdge, Union


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
            name="Sleeper", strikes_childhood=True, strikes_youth=True, strikes_adulthood=True
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


class KinRowsValidationTests(TestCase):
    def setUp(self):
        self.account = AccountFactory()
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)
        self.draft = CharacterDraftFactory(account=self.account)
        self.url = f"/api/character-creation/drafts/{self.draft.pk}/"

    def _patch(self, rows):
        return self.client.patch(self.url, {"draft_data": {"kin_rows": rows}}, format="json")

    def test_a_twin_a_spouse_and_children_are_accepted(self):
        rows = [
            {"kind": "twin", "name": "Wen", "gender_id": None, "fate": ""},
            {"kind": "spouse", "name": "Ser Aldo", "gender_id": None, "fate": "dead"},
            {"kind": "child", "name": "Pip", "gender_id": None, "fate": "fostered_away"},
        ]
        res = self._patch(rows)
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["draft_data"]["kin_rows"], rows)

    def test_a_wrong_kind_fate_or_second_twin_is_refused(self):
        for rows in (
            [{"kind": "cousin", "name": "x", "fate": ""}],
            [{"kind": "spouse", "name": "x", "fate": "lost"}],
            [{"kind": "child", "name": "x", "fate": "fled"}],
            [{"kind": "twin", "name": "x", "fate": "dead"}],
            [{"kind": "twin", "name": "a", "fate": ""}, {"kind": "twin", "name": "b", "fate": ""}],
            [{"kind": "child", "name": "x", "fate": "raised"}] * 9,
        ):
            res = self._patch(rows)
            self.assertEqual(res.status_code, 400, (rows, res.content))

    def test_malformed_kin_row_does_not_replace_saved_people(self):
        rows = [{"kind": "child", "name": "Pip", "fate": "raised"}]
        self.assertEqual(self._patch(rows).status_code, 200)
        for invalid in (
            "Pip",
            {"kind": "child", "name": 17},
            {"kind": "child", "name": "Pip", "gender_id": "unknown"},
        ):
            with self.subTest(row=invalid):
                res = self._patch([invalid])
                self.assertEqual(res.status_code, 400, res.content)
                self.draft.refresh_from_db()
                self.assertEqual(self.draft.draft_data["kin_rows"], rows)


class KinRowsFinalizeTests(FinalizationTestMixin, TestCase):
    """The seated people reach the kinship graph at finalize (#4395)."""

    def setUp(self) -> None:
        self._flush_common_caches()
        self.account = AccountDB.objects.create(username="kin_rows_finalize")
        self._setup_finalization_base(self, prefix="Kin", height_min=700, height_max=800)
        UnionKindFactory(name="Marriage", confers_wedlock=True)
        # Known parents on this route, so the twin has edges to share.
        self.known_route = OriginTemplateFactory(
            beginning=self.beginnings,
            allows_no_family=True,
            allows_name_family=False,
            parentage=Parentage.KNOWN,
        )

    def test_twin_spouse_and_children_are_seated(self) -> None:
        draft = self._create_base_draft(
            line_parent_name="Mother",
            other_parent_name="Father",
            kin_rows=[
                {"kind": KinRowKind.TWIN, "name": "Wen", "gender_id": None, "fate": ""},
                {
                    "kind": KinRowKind.SPOUSE,
                    "name": "Ser Aldo",
                    "gender_id": None,
                    "fate": SpouseFate.DEAD,
                },
                {
                    "kind": KinRowKind.CHILD,
                    "name": "Pip",
                    "gender_id": None,
                    "fate": ChildFate.LOST,
                },
                {
                    "kind": KinRowKind.CHILD,
                    "name": "Tam",
                    "gender_id": None,
                    "fate": ChildFate.RAISED,
                },
            ],
        )
        draft.selected_origin_template = self.known_route
        draft.save(update_fields=["selected_origin_template"])

        character = finalize_character(draft, add_to_roster=True)
        node = Kinsperson.objects.get(sheet=character.sheet_data)
        parents = {e.parent.name for e in ParentageEdge.objects.filter(child=node)}
        self.assertEqual(parents, {"Mother", "Father"})

        twin = Kinsperson.objects.get(name="Wen")
        self.assertEqual({e.parent.name for e in ParentageEdge.objects.filter(child=twin)}, parents)
        self.assertEqual(twin.age, 25)

        spouse = Kinsperson.objects.get(name="Ser Aldo")
        self.assertTrue(spouse.is_deceased)
        union = Union.objects.get(members=node)
        self.assertIn(spouse, union.members.all())
        self.assertIsNotNone(union.ended_at)

        pip = Kinsperson.objects.get(name="Pip")
        tam = Kinsperson.objects.get(name="Tam")
        self.assertTrue(pip.is_deceased)
        self.assertFalse(tam.is_deceased)
        self.assertEqual(
            {e.child.name for e in ParentageEdge.objects.filter(parent=node)}, {"Pip", "Tam"}
        )

    def test_a_fled_spouse_is_missing_and_a_divorce_ends_the_union(self) -> None:
        draft = self._create_base_draft(
            kin_rows=[
                {"kind": KinRowKind.SPOUSE, "name": "Rue", "gender_id": None, "fate": "fled"},
            ]
        )
        character = finalize_character(draft, add_to_roster=True)
        node = Kinsperson.objects.get(sheet=character.sheet_data)
        rue = Kinsperson.objects.get(name="Rue")
        self.assertTrue(rue.is_missing)
        self.assertIsNone(Union.objects.get(members=node).ended_at)

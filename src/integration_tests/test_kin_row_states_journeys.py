"""Journeys: the kin-row states (#4870, slice 8 of #4813).

Maud names a dead line parent and a missing other parent, seats a dead twin, a separated
spouse and a promised betrothed, and finalizes: the dead nodes are deceased, the missing
one missing, the marriage stands with its separation dated, the betrothal is a union of
the betrothal kind. A broken betrothal is an ended union. A fate outside a role's list is
refused on the draft. With no betrothal kind authored the betrothed is skipped and the
rest seated. The expected shapes come from the plan's kin-row ruling (a fate on each
named parent; a betrothed row under a Betrothal union kind; a separated spouse; a dead
twin) and the kinship graph's own states.
"""

from __future__ import annotations

from evennia_extensions.factories import AccountFactory
from integration_tests.harness import JourneyCase
from world.character_creation.constants import Parentage
from world.character_creation.factories import OriginTemplateFactory
from world.character_creation.services import finalize_character
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin
from world.roster.factories import UnionKindFactory
from world.roster.models import Kinsperson, ParentageEdge, Union


class TheKinRowStates(FinalizationTestMixin, JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        self._flush_common_caches()
        self.account = AccountFactory()
        self._setup_finalization_base(self, prefix="Kin", height_min=700, height_max=800)
        UnionKindFactory(name="Marriage", confers_wedlock=True)
        self.betrothal = UnionKindFactory(
            name="Betrothal", confers_wedlock=False, is_betrothal=True
        )
        OriginTemplateFactory(
            beginning=self.beginnings,
            allows_no_family=True,
            allows_name_family=False,
            parentage=Parentage.KNOWN,
        )
        self.client = self.api(self.account)

    def _url(self, draft) -> str:
        return f"/api/character-creation/drafts/{draft.pk}/"

    def _patch(self, draft, draft_data: dict) -> object:
        return self.client.patch(self._url(draft), {"draft_data": draft_data}, format="json")

    def _finalize(self, draft):
        draft.refresh_from_db()
        character = finalize_character(draft, add_to_roster=True)
        return Kinsperson.objects.get(sheet=character.sheet_data)

    def test_the_states_reach_the_graph(self) -> None:
        draft = self._create_base_draft(first_name="Maud")
        response = self._patch(
            draft,
            {
                "line_parent_name": "Mother",
                "line_parent_fate": "dead",
                "other_parent_name": "Father",
                "other_parent_fate": "missing",
                "kin_rows": [
                    {"kind": "twin", "name": "Wen", "gender_id": None, "fate": "dead"},
                    {"kind": "spouse", "name": "Aldo", "gender_id": None, "fate": "separated"},
                    {"kind": "betrothed", "name": "Rue", "gender_id": None, "fate": "promised"},
                ],
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        node = self._finalize(draft)
        parents = {e.parent.name: e.parent for e in ParentageEdge.objects.filter(child=node)}
        self.assertEqual(set(parents), {"Mother", "Father"})
        self.assertTrue(parents["Mother"].is_deceased)
        self.assertFalse(parents["Mother"].is_missing)
        self.assertTrue(parents["Father"].is_missing)
        self.assertFalse(parents["Father"].is_deceased)
        self.assertTrue(Kinsperson.objects.get(name="Wen").is_deceased)
        marriage = Union.objects.get(members=node, kind__confers_wedlock=True)
        self.assertIsNone(marriage.ended_at)
        self.assertIsNotNone(marriage.separated_at)
        self.assertFalse(Kinsperson.objects.get(name="Aldo").is_deceased)
        betrothal = Union.objects.get(members=node, kind=self.betrothal)
        self.assertIsNone(betrothal.ended_at)
        self.assertIn(Kinsperson.objects.get(name="Rue"), betrothal.members.all())

    def test_a_broken_betrothal_is_an_ended_union_and_a_missing_one_is_missing(self) -> None:
        draft = self._create_base_draft(first_name="Maud")
        response = self._patch(
            draft,
            {
                "kin_rows": [
                    {"kind": "betrothed", "name": "Rue", "gender_id": None, "fate": "broken"},
                    {"kind": "betrothed", "name": "Sol", "gender_id": None, "fate": "missing"},
                ]
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        node = self._finalize(draft)
        # Two filters, two joins: one member is the PC, another is the named betrothed.
        rue = Union.objects.filter(members=node).get(members__name="Rue")
        self.assertIsNotNone(rue.ended_at)
        sol = Union.objects.filter(members=node).get(members__name="Sol")
        self.assertIsNone(sol.ended_at)
        self.assertTrue(Kinsperson.objects.get(name="Sol").is_missing)

    def test_a_fate_outside_the_roles_list_is_refused(self) -> None:
        draft = self._create_base_draft(first_name="Maud")
        for bad in (
            {"kin_rows": [{"kind": "twin", "name": "Wen", "gender_id": None, "fate": "missing"}]},
            {
                "kin_rows": [
                    {"kind": "betrothed", "name": "Rue", "gender_id": None, "fate": "alive"}
                ]
            },
            {"kin_rows": [{"kind": "spouse", "name": "Aldo", "gender_id": None, "fate": "broken"}]},
            {"line_parent_fate": "fled"},
        ):
            response = self._patch(draft, bad)
            self.assertEqual(response.status_code, 400, (bad, response.content))
        response = self._patch(
            draft,
            {
                "kin_rows": [{"kind": "spouse", "name": "Aldo", "gender_id": None, "fate": "fled"}],
                "other_parent_fate": "",
            },
        )
        self.assertEqual(response.status_code, 200, response.content)

    def test_without_a_betrothal_kind_the_betrothed_is_skipped_and_the_rest_seated(self) -> None:
        self.betrothal.delete()
        draft = self._create_base_draft(first_name="Maud")
        response = self._patch(
            draft,
            {
                "kin_rows": [
                    {"kind": "betrothed", "name": "Rue", "gender_id": None, "fate": "promised"},
                    {"kind": "child", "name": "Pip", "gender_id": None, "fate": "raised"},
                ]
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        with self.assertLogs("world.character_creation.services", level="ERROR"):
            node = self._finalize(draft)
        self.assertFalse(Union.objects.filter(members=node).exists())
        self.assertFalse(Kinsperson.objects.filter(name="Rue").exists())
        self.assertEqual({e.child.name for e in ParentageEdge.objects.filter(parent=node)}, {"Pip"})

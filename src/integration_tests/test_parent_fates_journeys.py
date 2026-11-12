"""Journeys: the named parents' fates (#4870, slice 8 of #4813; kin rows left creation, #5102).

Maud names a dead line parent and a missing other parent and finalizes: the dead parent's
node is deceased, the missing one missing. A parent fate outside alive, dead and missing is
refused on the draft and a blank one saves. A spouse, a child, a twin or a betrothed is no
longer built in creation (ADR-5102-A): a draft that still carries the old ``kin_rows`` key
finalizes with the parents alone.
"""

from __future__ import annotations

from evennia_extensions.factories import AccountFactory
from integration_tests.harness import JourneyCase
from world.character_creation.constants import Parentage
from world.character_creation.factories import OriginTemplateFactory
from world.character_creation.services import finalize_character
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin
from world.roster.models import Kinsperson, ParentageEdge, Union


class TheParentFates(FinalizationTestMixin, JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        self._flush_common_caches()
        self.account = AccountFactory()
        self._setup_finalization_base(self, prefix="Kin", height_min=700, height_max=800)
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

    def test_a_dead_parent_and_a_missing_one_reach_the_graph(self) -> None:
        draft = self._create_base_draft(first_name="Maud")
        response = self._patch(
            draft,
            {
                "line_parent_name": "Mother",
                "line_parent_fate": "dead",
                "other_parent_name": "Father",
                "other_parent_fate": "missing",
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

    def test_a_parent_fate_outside_the_list_is_refused_and_a_blank_one_saves(self) -> None:
        draft = self._create_base_draft(first_name="Maud")
        response = self._patch(draft, {"line_parent_fate": "fled"})
        self.assertEqual(response.status_code, 400, response.content)
        response = self._patch(draft, {"other_parent_fate": ""})
        self.assertEqual(response.status_code, 200, response.content)

    def test_old_kin_rows_on_a_draft_build_no_one(self) -> None:
        draft = self._create_base_draft(first_name="Maud")
        response = self._patch(
            draft,
            {
                "line_parent_name": "Mother",
                "kin_rows": [
                    {"kind": "spouse", "name": "Aldo", "gender_id": None, "fate": "alive"},
                    {"kind": "child", "name": "Pip", "gender_id": None, "fate": "raised"},
                ],
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        node = self._finalize(draft)
        self.assertFalse(Union.objects.filter(members=node).exists())
        self.assertFalse(ParentageEdge.objects.filter(parent=node).exists())
        self.assertFalse(Kinsperson.objects.filter(name__in=["Aldo", "Pip"]).exists())

"""Character-scoped kin tree tests (#3003): family-bound vs familyless payloads.

``kin_tree_for_sheet`` is the single entry point a character sheet uses to show
"someone's family" — including characters (Misbegotten, tarot-named) who have
no ``Family`` at all. It must emit the same node/edge/union dict shapes as
``family_tree_for`` (one payload definition, ADR-0097's visibility ladder
preserved) whether or not the subject belongs to a house.
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.constants import DefinitionTier
from world.roster.factories import FamilyFactory, RosterEntryFactory
from world.roster.services import kinship
from world.roster.services.kinship import OMNISCIENT, family_tree_for, kin_tree_for_sheet


class KinTreeForSheetTests(TestCase):
    """``kin_tree_for_sheet`` covers both family-bound and familyless subjects."""

    @classmethod
    def setUpTestData(cls) -> None:
        # A family-bound PC: kin_tree_for_sheet must delegate to family_tree_for.
        cls.family = FamilyFactory()
        cls.pc_sheet = CharacterSheetFactory(character=CharacterFactory(db_key="Scion"))
        cls.pc_entry = RosterEntryFactory(character_sheet=cls.pc_sheet)
        kinship.create_person(tier=DefinitionTier.PC, sheet=cls.pc_sheet, family=cls.family)

        # A familyless PC (Misbegotten/tarot-named) with a visible mother: the
        # ego-centric branch must still surface their kin.
        cls.orphan_sheet = CharacterSheetFactory(character=CharacterFactory(db_key="Orphan"))
        cls.orphan_entry = RosterEntryFactory(character_sheet=cls.orphan_sheet)
        cls.orphan_node = kinship.create_person(tier=DefinitionTier.PC, sheet=cls.orphan_sheet)
        cls.orphan_mother = kinship.create_person(name="Orphan's Mother")
        kinship.record_parentage(child=cls.orphan_node, parent=cls.orphan_mother)

        # A sheet with no Kinsperson node at all.
        cls.unbound_sheet = CharacterSheetFactory(character=CharacterFactory(db_key="Unbound"))

        # A familyless PC with a hidden true parentage fact (the Misbegotten case).
        cls.misbegotten_sheet = CharacterSheetFactory(
            character=CharacterFactory(db_key="Misbegotten")
        )
        cls.misbegotten_entry = RosterEntryFactory(character_sheet=cls.misbegotten_sheet)
        cls.misbegotten_node = kinship.create_person(
            tier=DefinitionTier.PC, sheet=cls.misbegotten_sheet
        )
        cls.official_father = kinship.create_person(name="Official Father")
        cls.secret_father = kinship.create_person(name="Secret Father")
        kinship.record_parentage(
            child=cls.misbegotten_node, parent=cls.official_father, is_true=False
        )
        cls.hidden_edge = kinship.record_parentage(
            child=cls.misbegotten_node,
            parent=cls.secret_father,
            is_public_record=False,
            secret_content="The Misbegotten's true father is another PLACEHOLDER.",
        )

        stranger_sheet = CharacterSheetFactory(character=CharacterFactory(db_key="Stranger"))
        cls.stranger_entry = RosterEntryFactory(character_sheet=stranger_sheet)

    def test_family_bound_matches_family_tree(self) -> None:
        payload = kin_tree_for_sheet(self.pc_sheet, self.pc_entry)
        reference = family_tree_for(self.family, self.pc_entry)
        assert {n["id"] for n in payload.nodes} == {n["id"] for n in reference.nodes}

    def test_familyless_returns_ego_centric_payload(self) -> None:
        payload = kin_tree_for_sheet(self.orphan_sheet, self.orphan_entry)
        assert payload.family is None
        node_ids = {n["id"] for n in payload.nodes}
        assert self.orphan_node.pk in node_ids
        assert self.orphan_mother.pk in node_ids

    def test_no_kinsperson_returns_empty(self) -> None:
        payload = kin_tree_for_sheet(self.unbound_sheet, None)
        assert payload.nodes == []
        assert payload.family is None

    def test_hidden_edge_absent_for_unknowing_viewer(self) -> None:
        payload = kin_tree_for_sheet(self.misbegotten_sheet, self.stranger_entry)
        assert not any(e["parent_id"] == self.secret_father.pk for e in payload.parentage)

    def test_hidden_edge_flagged_for_staff(self) -> None:
        payload = kin_tree_for_sheet(self.misbegotten_sheet, OMNISCIENT)
        edge = next(e for e in payload.parentage if e["parent_id"] == self.secret_father.pk)
        assert edge["via_secret"] is True

    def test_subject_gets_no_implicit_pass(self) -> None:
        # ADR-0097: the secret's own subject does not see it without learning it.
        payload = kin_tree_for_sheet(self.misbegotten_sheet, self.misbegotten_entry)
        assert not any(e["parent_id"] == self.secret_father.pk for e in payload.parentage)

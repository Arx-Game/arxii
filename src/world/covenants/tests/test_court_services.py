"""Tests for create_covenant() COURT arm (Task 2)."""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import CovenantType
from world.covenants.exceptions import CourtLeaderNotAllowedError, CourtLeaderRequiredError
from world.covenants.factories import CovenantRoleFactory
from world.covenants.services import create_covenant
from world.covenants.types import CovenantFounder


class CreateCourtCovenantTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.master = CharacterSheetFactory()
        cls.servant = CharacterSheetFactory()
        cls.master_role = CovenantRoleFactory(covenant_type=CovenantType.COURT)
        cls.servant_role = CovenantRoleFactory(covenant_type=CovenantType.COURT)

    def _founders(self):
        return [
            CovenantFounder(character_sheet=self.master, role=self.master_role, is_leader=True),
            CovenantFounder(character_sheet=self.servant, role=self.servant_role),
        ]

    def test_court_covenant_created_with_leader(self):
        cov = create_covenant(
            name="Court of the Pale Moon",
            covenant_type=CovenantType.COURT,
            sworn_objective="Govern the night.",
            founders=self._founders(),
            leader=self.master,
        )
        self.assertEqual(cov.covenant_type, CovenantType.COURT)
        cov.refresh_from_db()
        self.assertEqual(cov.leader_id, self.master.pk)

    def test_court_without_leader_raises(self):
        with self.assertRaises(CourtLeaderRequiredError):
            create_covenant(
                name="Leaderless Court",
                covenant_type=CovenantType.COURT,
                sworn_objective="Govern the night.",
                founders=self._founders(),
            )

    def test_non_court_with_leader_raises(self):
        durance_role_a = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        durance_role_b = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        with self.assertRaises(CourtLeaderNotAllowedError):
            create_covenant(
                name="Durance with Leader",
                covenant_type=CovenantType.DURANCE,
                sworn_objective="Bind the soul.",
                founders=[
                    CovenantFounder(
                        character_sheet=self.master, role=durance_role_a, is_leader=True
                    ),
                    CovenantFounder(character_sheet=self.servant, role=durance_role_b),
                ],
                leader=self.master,
            )

    def test_worshipped_being_cannot_be_court_master(self):
        """A WorshippedBeing's avatar cannot lead a Court covenant (#2550)."""
        from world.worship.factories import WorshipTraditionFactory
        from world.worship.models import WorshippedBeing

        tradition = WorshipTraditionFactory()
        WorshippedBeing.objects.create(
            name="The Dread Patron",
            tradition=tradition,
            avatar_sheet=self.master,
        )
        with self.assertRaises(CourtLeaderNotAllowedError):
            create_covenant(
                name="Court of the Dread Patron",
                covenant_type=CovenantType.COURT,
                sworn_objective="Serve the patron.",
                founders=self._founders(),
                leader=self.master,
            )

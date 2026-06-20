"""Tests for MentorBond model (#1165)."""

from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import MentorBondAdjusted
from world.covenants.factories import CovenantFactory, MentorBondFactory
from world.covenants.models import MentorBond


class MentorBondModelTests(TestCase):
    def setUp(self):
        self.covenant = CovenantFactory()
        self.mentor_sheet = CharacterSheetFactory()
        self.sidekick_sheet = CharacterSheetFactory()

    def test_create_bond(self):
        bond = MentorBondFactory(
            covenant=self.covenant,
            mentor_sheet=self.mentor_sheet,
            sidekick_sheet=self.sidekick_sheet,
            adjusted_party=MentorBondAdjusted.SIDEKICK,
        )
        self.assertIsNotNone(bond.pk)
        self.assertIsNone(bond.dissolved_at)

    def test_active_queryset_includes_active_bond(self):
        bond = MentorBondFactory(
            covenant=self.covenant,
            mentor_sheet=self.mentor_sheet,
            sidekick_sheet=self.sidekick_sheet,
        )
        self.assertIn(bond, MentorBond.objects.active())

    def test_unique_active_sidekick_bond_constraint(self):
        MentorBondFactory(
            covenant=self.covenant,
            mentor_sheet=self.mentor_sheet,
            sidekick_sheet=self.sidekick_sheet,
        )
        with self.assertRaises(IntegrityError):
            MentorBond.objects.create(
                covenant=self.covenant,
                mentor_sheet=self.mentor_sheet,
                sidekick_sheet=self.sidekick_sheet,
                adjusted_party=MentorBondAdjusted.SIDEKICK,
            )

    def test_dissolved_bond_excluded_from_active(self):
        bond = MentorBondFactory(
            covenant=self.covenant,
            mentor_sheet=self.mentor_sheet,
            sidekick_sheet=self.sidekick_sheet,
        )
        bond.dissolved_at = timezone.now()
        bond.save()
        self.assertNotIn(bond, MentorBond.objects.active())

    def test_dissolved_bond_allows_new_active_bond(self):
        """After dissolving, another active bond for the same (covenant, sidekick) is allowed."""
        bond = MentorBondFactory(
            covenant=self.covenant,
            mentor_sheet=self.mentor_sheet,
            sidekick_sheet=self.sidekick_sheet,
        )
        bond.dissolved_at = timezone.now()
        bond.save()
        new_bond = MentorBondFactory(
            covenant=self.covenant,
            mentor_sheet=self.mentor_sheet,
            sidekick_sheet=self.sidekick_sheet,
        )
        self.assertIn(new_bond, MentorBond.objects.active())

    def test_related_names(self):
        bond = MentorBondFactory(
            covenant=self.covenant,
            mentor_sheet=self.mentor_sheet,
            sidekick_sheet=self.sidekick_sheet,
        )
        self.assertIn(bond, self.mentor_sheet.mentor_bonds_as_mentor.all())
        self.assertIn(bond, self.sidekick_sheet.mentor_bonds_as_sidekick.all())

    def test_ordering_newest_first(self):
        bond1 = MentorBondFactory(
            covenant=self.covenant,
            mentor_sheet=self.mentor_sheet,
            sidekick_sheet=self.sidekick_sheet,
        )
        # Dissolve first bond so we can create another active bond for the same sidekick
        bond1.dissolved_at = timezone.now()
        bond1.save()
        bond2 = MentorBondFactory(
            covenant=self.covenant,
            mentor_sheet=self.mentor_sheet,
            sidekick_sheet=self.sidekick_sheet,
        )
        bonds = list(MentorBond.objects.filter(covenant=self.covenant))
        self.assertEqual(bonds[0], bond2)
        self.assertEqual(bonds[1], bond1)

"""RosterType is the single vocabulary for roster identity (#2728)."""

from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase

from world.roster.models import Roster
from world.roster.models.choices import RosterType
from world.roster.seeds import ensure_rosters


class RosterTypeVocabularyTests(SimpleTestCase):
    def test_covers_every_shelf_a_character_can_sit_on(self):
        """Pending and NPC were real shelves living outside the enum."""
        self.assertEqual(
            set(RosterType.values),
            {"Active", "Inactive", "Available", "Restricted", "Frozen", "Pending", "NPC"},
        )

    def test_pending_and_npc_are_addressable(self):
        self.assertEqual(RosterType.PENDING, "Pending")
        self.assertEqual(RosterType.NPC, "NPC")


class RosterTypeKeyTests(TestCase):
    def test_roster_type_is_unique(self):
        """One row per shelf — this is what stopped the duplicate seeds."""
        Roster.objects.create(name="Active Characters", roster_type=RosterType.ACTIVE)
        with self.assertRaises(IntegrityError):
            Roster.objects.create(name="Active", roster_type=RosterType.ACTIVE)

    def test_a_roster_outside_the_vocabulary_is_rejected_by_the_database(self):
        """The CheckConstraint is the backstop for code paths that bypass
        full_clean() — ``choices`` alone is validation-time only, so a bare
        ``objects.create()`` would otherwise mint an unreachable shelf."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            Roster.objects.create(name="Retired", roster_type="Retired")

    def test_a_roster_created_without_a_roster_type_is_rejected(self):
        """The original defect: ``roster_type`` omitted falls back to Django's
        empty-string default, which is not a shelf. Nothing may sit off-vocabulary."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            Roster.objects.create(name="Nameless Shelf")

    def test_ensure_rosters_reuses_a_staff_renamed_row_instead_of_duplicating_it(self):
        """A staff-edited ``name`` must not cause ensure_rosters() to mint a second
        shelf for that roster_type — get_or_create's ``defaults`` must never clobber
        an already-existing row's hand-edited display label."""
        seeded = ensure_rosters()
        active = seeded[RosterType.ACTIVE]
        active.name = "Currently Played Characters"
        active.save(update_fields=["name"])

        reseeded = ensure_rosters()

        self.assertEqual(Roster.objects.count(), 7)
        reused = reseeded[RosterType.ACTIVE]
        self.assertEqual(reused.pk, active.pk)
        self.assertEqual(reused.name, "Currently Played Characters")

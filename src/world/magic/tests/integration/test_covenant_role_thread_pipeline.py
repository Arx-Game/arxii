"""End-to-end integration tests for Spec D — covenant role thread pipeline.

Pipeline: build sheet + CharacterClassLevel (sets current_level) + CovenantRole →
assign_covenant_role to satisfy has_ever_held gate → call weave_thread →
assert Thread created with COVENANT_ROLE kind → call compute_anchor_cap and
assert cap == current_level × 10.

Math reference (happy path with current_level=5):
  compute_anchor_cap(thread) == thread.owner.current_level * 10 == 5 * 10 == 50
"""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassLevelFactory
from world.covenants.exceptions import CovenantRoleNeverHeldError
from world.covenants.factories import CovenantRoleFactory
from world.covenants.services import assign_covenant_role, end_covenant_role
from world.magic.constants import TargetKind
from world.magic.factories import ResonanceFactory
from world.magic.models import Thread
from world.magic.services import weave_thread
from world.magic.services.threads import compute_anchor_cap


class CovenantRoleThreadHappyPathTests(TestCase):
    """Happy path: assign role → weave thread → anchor cap == current_level × 10."""

    @classmethod
    def setUpTestData(cls) -> None:
        # 1. CharacterSheet with active RosterTenure (provided by factory).
        cls.sheet = CharacterSheetFactory()

        # 2. Set current_level=5 via a CharacterClassLevel row.
        CharacterClassLevelFactory(character=cls.sheet.character, level=5)
        cls.sheet.invalidate_class_level_cache()

        # 3. CovenantRole.
        cls.role = CovenantRoleFactory()

        # 4. Resonance.
        cls.resonance = ResonanceFactory()

    def test_assign_then_weave_then_anchor_cap_matches_current_level_x_10(self) -> None:
        """assign_covenant_role → weave_thread → compute_anchor_cap == 50 (level 5 × 10).

        Math:
          current_level = 5
          compute_anchor_cap(thread) = 5 * 10 = 50
        """
        assign_covenant_role(character_sheet=self.sheet, covenant_role=self.role)

        thread = weave_thread(
            self.sheet,
            TargetKind.COVENANT_ROLE,
            self.role,
            self.resonance,
            name="Vow",
        )

        self.assertEqual(thread.target_kind, TargetKind.COVENANT_ROLE)
        self.assertEqual(thread.target_covenant_role, self.role)
        self.assertEqual(thread.owner, self.sheet)
        self.assertEqual(thread.resonance, self.resonance)

        cap = compute_anchor_cap(thread)
        self.assertEqual(self.sheet.current_level, 5)
        self.assertEqual(cap, 50)


class CovenantRoleThreadNeverHeldTests(TestCase):
    """Failure path: weave without assignment → CovenantRoleNeverHeldError."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.role = CovenantRoleFactory()
        cls.resonance = ResonanceFactory()

    def test_weave_without_assignment_raises_never_held_error(self) -> None:
        """No CharacterCovenantRole row → CovenantRoleNeverHeldError; no Thread created."""
        pre_count = Thread.objects.filter(owner=self.sheet).count()

        with self.assertRaises(CovenantRoleNeverHeldError):
            weave_thread(self.sheet, TargetKind.COVENANT_ROLE, self.role, self.resonance)

        self.assertEqual(Thread.objects.filter(owner=self.sheet).count(), pre_count)


class CovenantRoleThreadHistoricalRoleTests(TestCase):
    """Coverage: ended role still satisfies has_ever_held → weave succeeds."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.role = CovenantRoleFactory()
        cls.resonance = ResonanceFactory()

    def test_role_ended_in_history_still_allows_weave(self) -> None:
        """assign then end → weave still succeeds because has_ever_held checks all rows."""
        assignment = assign_covenant_role(character_sheet=self.sheet, covenant_role=self.role)
        end_covenant_role(assignment=assignment)

        # Handler cache reflects the ended state — invalidate to be safe.
        self.sheet.character.covenant_roles.invalidate()

        thread = weave_thread(
            self.sheet,
            TargetKind.COVENANT_ROLE,
            self.role,
            self.resonance,
            name="Ended Vow",
        )

        self.assertIsNotNone(thread.pk)
        self.assertEqual(thread.target_covenant_role, self.role)
        self.assertEqual(Thread.objects.filter(owner=self.sheet).count(), 1)

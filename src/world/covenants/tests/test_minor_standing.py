"""Minor (guest) membership standing (#2992).

Mirrors ``test_secondary_vows.py``'s setup style (built in ``setUp``, not
``setUpTestData`` — factories here create Evennia ``ObjectDB`` instances,
which aren't deepcopyable).
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import CovenantType, MembershipStanding
from world.covenants.exceptions import (
    MinorStandingRequiresSecondaryEngageError,
    SecondaryVowRequiresEngagedPrimaryError,
    SecondaryVowSameAnchorError,
)
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
)
from world.covenants.services import set_engaged_membership


class MinorStandingEngageTests(TestCase):
    """Engage-time behavior of MINOR-standing memberships (#2992)."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.primary_role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)

    def _minor_membership(self, role=None, covenant=None):
        role = role or CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        covenant = covenant or CovenantFactory(covenant_type=CovenantType.DURANCE)
        return CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=covenant,
            covenant_role=role,
            standing=MembershipStanding.MINOR,
        )

    def test_minor_row_cannot_engage_primary_lane(self) -> None:
        minor_membership = self._minor_membership()

        with self.assertRaises(MinorStandingRequiresSecondaryEngageError):
            set_engaged_membership(membership=minor_membership, as_secondary=False)

    def test_minor_row_engages_secondary_without_engaged_primary(self) -> None:
        minor_membership = self._minor_membership()

        set_engaged_membership(membership=minor_membership, as_secondary=True)

        minor_membership.refresh_from_db()
        self.assertTrue(minor_membership.engaged)
        self.assertTrue(minor_membership.is_secondary)

    def test_core_row_secondary_engage_still_requires_engaged_primary(self) -> None:
        core_membership = CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=CovenantFactory(covenant_type=CovenantType.DURANCE),
            covenant_role=self.primary_role,
        )

        with self.assertRaises(SecondaryVowRequiresEngagedPrimaryError):
            set_engaged_membership(membership=core_membership, as_secondary=True)

    def test_minor_standing_forbidden_on_battle_covenant(self) -> None:
        battle_role = CovenantRoleFactory(covenant_type=CovenantType.BATTLE)
        battle_membership = CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=CovenantFactory(covenant_type=CovenantType.BATTLE),
            covenant_role=battle_role,
            standing=MembershipStanding.MINOR,
        )

        with self.assertRaises(ValidationError):
            battle_membership.full_clean()

    def test_minor_secondary_respects_same_anchor_and_thread_cap_when_primary_engaged(
        self,
    ) -> None:
        primary_membership = CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=CovenantFactory(covenant_type=CovenantType.DURANCE),
            covenant_role=self.primary_role,
        )
        set_engaged_membership(membership=primary_membership)

        minor_membership = self._minor_membership(role=self.primary_role)

        with self.assertRaises(SecondaryVowSameAnchorError):
            set_engaged_membership(membership=minor_membership, as_secondary=True)

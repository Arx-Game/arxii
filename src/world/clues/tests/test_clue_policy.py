"""clue_target_kind_allowed (#3566): the clue authoring policy as one callable."""

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.clues.constants import ClueTargetKind
from world.clues.services import clue_target_kind_allowed
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory


class ClueTargetKindAllowedTests(TestCase):
    def test_staff_may_target_anything(self) -> None:
        staff = AccountFactory(is_staff=True)
        self.assertTrue(clue_target_kind_allowed(staff, ClueTargetKind.SECRET))

    def test_senior_gm_may_target_codex_but_not_secret(self) -> None:
        account = AccountFactory()
        GMProfileFactory(account=account, level=GMLevel.SENIOR)
        self.assertTrue(clue_target_kind_allowed(account, ClueTargetKind.CODEX))
        self.assertFalse(clue_target_kind_allowed(account, ClueTargetKind.SECRET))

    def test_below_senior_may_target_nothing(self) -> None:
        account = AccountFactory()
        GMProfileFactory(account=account, level=GMLevel.EXPERIENCED)
        self.assertFalse(clue_target_kind_allowed(account, ClueTargetKind.CODEX))

    def test_no_profile_may_target_nothing(self) -> None:
        self.assertFalse(clue_target_kind_allowed(AccountFactory(), ClueTargetKind.CODEX))

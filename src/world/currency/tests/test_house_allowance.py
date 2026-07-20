"""Non-discretionary house allowance (#2540): a share of surplus auto-splits among members.

Only *active piloted* members share — a member whose account logged in within
``ACTIVE_WEEK_LOGIN_DAYS``. Pure NPCs (no ``db_account``) and stale members are excluded.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import AccountFactory
from world.currency.services import (
    distribute_allowance,
    get_or_create_purse,
    get_or_create_treasury,
)
from world.scenes.factories import PersonaFactory
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory


def _pilot(persona, *, days_ago: int) -> None:
    """Attach an account to the persona's character with a login ``days_ago`` days back."""
    account = AccountFactory()
    account.last_login = timezone.now() - timedelta(days=days_ago)
    account.save(update_fields=["last_login"])
    character = persona.character_sheet.character
    character.db_account = account
    character.save(update_fields=["db_account"])


class DistributeAllowanceTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.org = OrganizationFactory()
        cls.active = PersonaFactory()
        cls.stale = PersonaFactory()
        cls.npc = PersonaFactory()  # no account → never piloted
        for persona in (cls.active, cls.stale, cls.npc):
            OrganizationMembershipFactory(persona=persona, organization=cls.org, rank=2)
        _pilot(cls.active, days_ago=1)
        _pilot(cls.stale, days_ago=60)

    def setUp(self) -> None:
        self.treasury = get_or_create_treasury(self.org)
        self.treasury.balance = 1000
        self.treasury.save(update_fields=["balance"])

    def _purse(self, persona) -> int:
        purse = get_or_create_purse(persona.character_sheet)
        purse.refresh_from_db()
        return purse.balance

    def test_only_active_piloted_members_receive(self) -> None:
        result = distribute_allowance(organization=self.org, surplus=1000)  # 50% → pool 500
        self.assertEqual(result.member_count, 1)  # only `active`
        self.assertEqual(result.per_member, 500)
        self.assertEqual(result.total_distributed, 500)
        self.assertEqual(self._purse(self.active), 500)
        self.assertEqual(self._purse(self.stale), 0)  # login too old
        self.assertEqual(self._purse(self.npc), 0)  # no account
        self.treasury.refresh_from_db()
        self.assertEqual(self.treasury.balance, 500)  # paid from the vault

    def test_multiple_active_members_split_equally(self) -> None:
        _pilot(self.stale, days_ago=1)  # now active too
        result = distribute_allowance(organization=self.org, surplus=1000)  # pool 500 / 2
        self.assertEqual(result.member_count, 2)
        self.assertEqual(result.per_member, 250)
        self.assertEqual(self._purse(self.active), 250)
        self.assertEqual(self._purse(self.stale), 250)

    def test_member_with_multiple_personas_is_paid_once(self) -> None:
        second_face = PersonaFactory(character_sheet=self.active.character_sheet)
        OrganizationMembershipFactory(persona=second_face, organization=self.org, rank=3)
        result = distribute_allowance(organization=self.org, surplus=1000)
        self.assertEqual(result.member_count, 1)  # both memberships share one sheet
        self.assertEqual(self._purse(self.active), 500)  # not doubled

    def test_no_surplus_is_a_noop(self) -> None:
        result = distribute_allowance(organization=self.org, surplus=0)
        self.assertEqual(result.total_distributed, 0)
        self.treasury.refresh_from_db()
        self.assertEqual(self.treasury.balance, 1000)

    def test_pool_capped_at_treasury_balance(self) -> None:
        self.treasury.balance = 80  # less than the 500 the surplus would allocate
        self.treasury.save(update_fields=["balance"])
        result = distribute_allowance(organization=self.org, surplus=1000)
        self.assertEqual(result.total_distributed, 80)  # never overdraws
        self.treasury.refresh_from_db()
        self.assertEqual(self.treasury.balance, 0)

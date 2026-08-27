"""Materials allowance leg (#2540 slice 2): "the crafting draw".

The materials analogue of ``distribute_allowance`` (``test_house_allowance.py``): a share
of what a collection just landed **per category** auto-splits among the org's active
piloted members — same population, same ``_active_allowance_sheets`` scan, non-discretionary.
Only *active piloted* members share; pure NPCs (no ``db_account``) and stale members are
excluded, exactly as the coin leg.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import AccountFactory
from world.currency.services import distribute_material_allowance
from world.items.factories import MaterialCategoryFactory
from world.items.gems.buckets import material_value
from world.items.materials_models import OrgMaterialStock
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


class DistributeMaterialAllowanceTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.org = OrganizationFactory()
        cls.category = MaterialCategoryFactory(name="Semiprecious")
        cls.other_category = MaterialCategoryFactory(name="Timber")
        cls.active = PersonaFactory()
        cls.stale = PersonaFactory()
        cls.npc = PersonaFactory()  # no account → never piloted
        for persona in (cls.active, cls.stale, cls.npc):
            OrganizationMembershipFactory(persona=persona, organization=cls.org, rank=2)
        _pilot(cls.active, days_ago=1)
        _pilot(cls.stale, days_ago=60)

    def setUp(self) -> None:
        self.stock = OrgMaterialStock.objects.create(
            organization=self.org, material_category=self.category, value=1000
        )

    def _stock_value(self) -> int:
        self.stock.refresh_from_db()
        return self.stock.value

    def test_credits_active_member_bucket_and_debits_stock_by_total(self) -> None:
        result = distribute_material_allowance(
            organization=self.org, landed_by_category=[(self.category, 1000)]
        )
        # 50% of 1000 landed → pool 500; one active member → per_member 500.
        self.assertEqual(result.member_count, 1)
        self.assertEqual(result.total_by_category, [(self.category, 500)])
        self.assertEqual(material_value(self.active.character_sheet, self.category), 500)
        self.assertEqual(self._stock_value(), 500)  # 1000 - 500 debited

    def test_only_active_piloted_members_receive(self) -> None:
        distribute_material_allowance(
            organization=self.org, landed_by_category=[(self.category, 1000)]
        )
        self.assertEqual(material_value(self.stale.character_sheet, self.category), 0)
        self.assertEqual(material_value(self.npc.character_sheet, self.category), 0)

    def test_multiple_active_members_split_and_floor_remainder_stays_in_stock(self) -> None:
        _pilot(self.stale, days_ago=1)  # now active too
        self.stock.value = 10_000
        self.stock.save(update_fields=["value"])
        # 50% of 302 landed = 151 pool; 151 // 2 members = 75 per_member; credited 150.
        result = distribute_material_allowance(
            organization=self.org, landed_by_category=[(self.category, 302)]
        )
        self.assertEqual(result.member_count, 2)
        self.assertEqual(result.total_by_category, [(self.category, 150)])
        self.assertEqual(material_value(self.active.character_sheet, self.category), 75)
        self.assertEqual(material_value(self.stale.character_sheet, self.category), 75)
        self.assertEqual(self._stock_value(), 10_000 - 150)  # floor remainder (1) stays

    def test_member_with_multiple_personas_is_paid_once(self) -> None:
        second_face = PersonaFactory(character_sheet=self.active.character_sheet)
        OrganizationMembershipFactory(persona=second_face, organization=self.org, rank=3)
        result = distribute_material_allowance(
            organization=self.org, landed_by_category=[(self.category, 1000)]
        )
        self.assertEqual(result.member_count, 1)  # both memberships share one sheet
        self.assertEqual(material_value(self.active.character_sheet, self.category), 500)

    def test_zero_active_members_keeps_all_value_in_stock(self) -> None:
        # No pilots on setUpTestData's class-level personas here — use a fresh org/member
        # so nobody is active.
        org = OrganizationFactory()
        member = PersonaFactory()
        OrganizationMembershipFactory(persona=member, organization=org, rank=2)
        OrgMaterialStock.objects.create(
            organization=org, material_category=self.category, value=1000
        )
        result = distribute_material_allowance(
            organization=org, landed_by_category=[(self.category, 1000)]
        )
        self.assertEqual(result.member_count, 0)
        self.assertEqual(result.total_by_category, [])
        stock = OrgMaterialStock.objects.get(organization=org, material_category=self.category)
        self.assertEqual(stock.value, 1000)  # untouched

    def test_category_with_zero_landed_is_skipped(self) -> None:
        result = distribute_material_allowance(
            organization=self.org, landed_by_category=[(self.category, 0)]
        )
        self.assertEqual(result.member_count, 1)  # active scan still runs
        self.assertEqual(result.total_by_category, [])
        self.assertEqual(self._stock_value(), 1000)  # untouched

    def test_empty_landed_by_category_is_a_noop(self) -> None:
        result = distribute_material_allowance(organization=self.org, landed_by_category=[])
        self.assertEqual(result.member_count, 0)
        self.assertEqual(result.total_by_category, [])

    def test_missing_stock_row_is_skipped_not_created_negative(self) -> None:
        # other_category never got an OrgMaterialStock row (collection landed 0 for it once,
        # so nothing ever created it) — guard get-or-skip rather than raising or going negative.
        result = distribute_material_allowance(
            organization=self.org,
            landed_by_category=[(self.other_category, 1000), (self.category, 1000)],
        )
        self.assertEqual(
            result.total_by_category, [(self.category, 500)]
        )  # other_category silently skipped
        self.assertFalse(
            OrgMaterialStock.objects.filter(
                organization=self.org, material_category=self.other_category
            ).exists()
        )

    def test_credit_capped_at_stock_value_never_goes_negative(self) -> None:
        self.stock.value = 10  # far less than what 1000 landed would compute
        self.stock.save(update_fields=["value"])
        result = distribute_material_allowance(
            organization=self.org, landed_by_category=[(self.category, 1000)]
        )
        self.assertEqual(result.total_by_category, [(self.category, 10)])
        self.assertEqual(material_value(self.active.character_sheet, self.category), 10)
        self.assertEqual(self._stock_value(), 0)  # never negative

    def test_multiple_categories_each_credited_independently(self) -> None:
        OrgMaterialStock.objects.create(
            organization=self.org, material_category=self.other_category, value=2000
        )
        result = distribute_material_allowance(
            organization=self.org,
            landed_by_category=[(self.category, 1000), (self.other_category, 400)],
        )
        self.assertEqual(
            set(result.total_by_category), {(self.category, 500), (self.other_category, 200)}
        )
        self.assertEqual(material_value(self.active.character_sheet, self.category), 500)
        self.assertEqual(material_value(self.active.character_sheet, self.other_category), 200)

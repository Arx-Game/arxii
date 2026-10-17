"""The income lever (#4394) at the two personal payouts: allowance and asset collection."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import AccountFactory
from world.assets.factories import NPCAssetFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.currency.services import (
    collect_asset_income,
    distribute_allowance,
    get_or_create_purse,
    get_or_create_treasury,
)
from world.mechanics.constants import INCOME_CATEGORY_NAME, INCOME_TARGET_NAME
from world.mechanics.test_helpers import grant_lever
from world.scenes.factories import PersonaFactory
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory
from world.traits.factories import CheckOutcomeFactory


def _balance(sheet) -> int:
    purse = get_or_create_purse(sheet)
    purse.refresh_from_db()
    return purse.balance


class AllowanceIncomeLeverTests(TestCase):
    def setUp(self) -> None:
        self.org = OrganizationFactory()
        self.persona = PersonaFactory()
        OrganizationMembershipFactory(persona=self.persona, organization=self.org, rank=2)
        account = AccountFactory()
        account.last_login = timezone.now() - timedelta(days=1)
        account.save(update_fields=["last_login"])
        character = self.persona.character_sheet.character
        character.db_account = account
        character.save(update_fields=["db_account"])
        treasury = get_or_create_treasury(self.org)
        treasury.balance = 1000
        treasury.save(update_fields=["balance"])

    def test_without_a_lever_the_share_lands_whole(self) -> None:
        result = distribute_allowance(organization=self.org, surplus=1000)  # pool 500, 1 member
        assert result.per_member == 500
        assert result.total_distributed == 500
        assert _balance(self.persona.character_sheet) == 500

    def test_a_gambler_collects_less_of_the_same_share(self) -> None:
        grant_lever(self.persona.character_sheet, INCOME_CATEGORY_NAME, INCOME_TARGET_NAME, -20)
        result = distribute_allowance(organization=self.org, surplus=1000)
        assert result.per_member == 500  # the house's even split is unchanged
        assert result.total_distributed == 400
        assert _balance(self.persona.character_sheet) == 400


class AssetIncomeLeverTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        CheckTypeFactory(name="Tax Collection")

    def setUp(self) -> None:
        self.asset = NPCAssetFactory()
        self.asset.weekly_income = 1000
        self.asset.uncollected_pool = 1000
        self.asset.save(update_fields=["weekly_income", "uncollected_pool"])

    def _collect(self):
        outcome = CheckOutcomeFactory(name="asset_collect_lever", success_level=1)
        with force_check_outcome(outcome):
            return collect_asset_income(asset=self.asset, character_sheet=self.sheet)

    def test_without_a_lever_the_clean_band_lands_whole(self) -> None:
        assert self._collect().landed == 1000
        assert _balance(self.sheet) == 1000

    def test_a_new_nobility_row_collects_more(self) -> None:
        grant_lever(self.sheet, INCOME_CATEGORY_NAME, INCOME_TARGET_NAME, 25)
        assert self._collect().landed == 1250
        assert _balance(self.sheet) == 1250


class AllowancePoolCeilingTests(TestCase):
    """A positive lever takes from what the split left, never past the pool."""

    def setUp(self) -> None:
        self.org = OrganizationFactory()
        self.sheets = []
        for _ in range(2):
            persona = PersonaFactory()
            OrganizationMembershipFactory(persona=persona, organization=self.org, rank=2)
            account = AccountFactory()
            account.last_login = timezone.now() - timedelta(days=1)
            account.save(update_fields=["last_login"])
            character = persona.character_sheet.character
            character.db_account = account
            character.save(update_fields=["db_account"])
            self.sheets.append(persona.character_sheet)
        treasury = get_or_create_treasury(self.org)
        treasury.balance = 500  # the pool is capped here: surplus 1000 -> 500
        treasury.save(update_fields=["balance"])

    def test_payouts_never_exceed_the_pool(self) -> None:
        grant_lever(self.sheets[1], INCOME_CATEGORY_NAME, INCOME_TARGET_NAME, 50)
        result = distribute_allowance(organization=self.org, surplus=1000)
        assert result.per_member == 250
        assert result.total_distributed == 500
        assert sum(_balance(sheet) for sheet in self.sheets) == 500
        treasury = get_or_create_treasury(self.org)
        treasury.refresh_from_db()
        assert treasury.balance == 0

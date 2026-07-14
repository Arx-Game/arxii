"""E2E tests for ASSET_TASK_COLLECT offer (#2294).

Tests the full dispatch_offer_effect → run_asset_collect_task pipeline:
PC interacts with their asset, selects the collect offer, check is rolled,
and money lands in the PC's purse (or is lost on catastrophe).
"""

from __future__ import annotations

from evennia.utils.test_resources import EvenniaTestCase

from world.assets.constants import AssetStatus
from world.assets.factories import NPCAssetFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.currency.services import get_or_create_purse
from world.npc_services.constants import OfferKind
from world.npc_services.effects import dispatch_offer_effect, reset_offer_effect_handlers
from world.npc_services.factories import NPCRoleFactory
from world.npc_services.models import NPCServiceOffer
from world.traits.factories import CheckOutcomeFactory


class AssetTaskCollectHandlerTests(EvenniaTestCase):
    """Tests for the ASSET_TASK_COLLECT offer effect handler (#2294)."""

    def setUp(self) -> None:
        super().setUp()
        from world.assets.apps import AssetsConfig  # noqa: F401

        self.sheet = CharacterSheetFactory()
        self.promoter = self.sheet.primary_persona
        self.character = self.sheet.character

        self.asset = NPCAssetFactory(promoter_persona=self.promoter)
        self.asset.weekly_income = 1000
        self.asset.uncollected_pool = 1000
        self.asset.save(update_fields=["weekly_income", "uncollected_pool"])

        CheckTypeFactory(name="Tax Collection")

        self.role = NPCRoleFactory()
        self.offer = NPCServiceOffer.objects.create(
            role=self.role,
            kind=OfferKind.ASSET_TASK_COLLECT,
            label="Collect Income",
            is_final=True,
        )

    def tearDown(self) -> None:
        reset_offer_effect_handlers()
        super().tearDown()

    def _purse_balance(self) -> int:
        purse = get_or_create_purse(self.sheet)
        purse.refresh_from_db()
        return purse.balance

    def test_successful_collection_lands_money_in_purse(self) -> None:
        outcome = CheckOutcomeFactory(name="collect_ok", success_level=1)
        with force_check_outcome(outcome):
            result = dispatch_offer_effect(self.offer, self.promoter)

        self.assertIn("banked", result.message)
        self.assertEqual(self._purse_balance(), 1000)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.uncollected_pool, 0)

    def test_catastrophe_loses_everything(self) -> None:
        outcome = CheckOutcomeFactory(name="collect_cat", success_level=-2)
        with force_check_outcome(outcome):
            result = dispatch_offer_effect(self.offer, self.promoter)

        self.assertIn("gone", result.message)
        self.assertEqual(self._purse_balance(), 0)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.uncollected_pool, 0)

    def test_no_active_asset_returns_failure(self) -> None:
        self.asset.status = AssetStatus.COMPROMISED
        self.asset.save(update_fields=["status"])

        result = dispatch_offer_effect(self.offer, self.promoter)

        self.assertEqual(result.message, "This asset is not available for tasking.")

    def test_empty_pool_returns_nothing_to_collect(self) -> None:
        self.asset.uncollected_pool = 0
        self.asset.save(update_fields=["uncollected_pool"])

        result = dispatch_offer_effect(self.offer, self.promoter)

        self.assertIn("nothing", result.message.lower())

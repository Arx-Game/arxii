"""Cachet staking + weekly settlement ladder (#2907)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.items.constants import ShowcaseMode, WearFamily
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.models import (
    FashionShowing,
    ShowcaseState,
    Silhouette,
    SilhouetteVogueMomentum,
)
from world.items.services.fashion_showcase import (
    get_or_create_wallet,
    record_showcase_showing,
    settle_fashion_showings,
)


class ShowcaseStakeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.boot = Silhouette.objects.create(name="Boot", wear_family=WearFamily.FOOTWEAR)
        cls.item = ItemInstanceFactory(
            template=ItemTemplateFactory(silhouette=cls.boot),
            holder_character_sheet=cls.sheet,
        )
        ShowcaseState.objects.create(
            character_sheet=cls.sheet,
            is_active=True,
            mode=ShowcaseMode.PIECE,
            item=cls.item,
        )

    def test_stake_deducts_and_records_statement(self):
        from world.items.models import CachetWallet

        wallet = get_or_create_wallet(self.sheet)
        wallet.balance = 3
        wallet.save(update_fields=["balance"])
        showing = record_showcase_showing(self.sheet, scene=None, roll_success=True)
        assert showing is not None
        assert showing.stake == 1
        assert showing.statement_item == self.item
        assert showing.statement_silhouette == self.boot
        # DB truth, not the idmapper-cached instance (test-pollution guard).
        stored = CachetWallet.objects.values_list("balance", flat=True).get(
            character_sheet=self.sheet
        )
        assert stored == 2

    def test_no_toggle_records_nothing(self):
        other = CharacterSheetFactory()
        assert record_showcase_showing(other, scene=None, roll_success=True) is None

    def test_empty_wallet_records_nothing(self):
        wallet = get_or_create_wallet(self.sheet)
        wallet.balance = 0
        wallet.save()
        assert record_showcase_showing(self.sheet, scene=None, roll_success=True) is None


class SettlementLadderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.boot = Silhouette.objects.create(name="Boot", wear_family=WearFamily.FOOTWEAR)
        cls.item = ItemInstanceFactory(
            template=ItemTemplateFactory(silhouette=cls.boot),
            holder_character_sheet=cls.sheet,
        )

    def _showing(self, *, roll_success: bool, engagement: int) -> FashionShowing:
        return FashionShowing.objects.create(
            character_sheet=self.sheet,
            mode=ShowcaseMode.PIECE,
            statement_item=self.item,
            statement_silhouette=self.boot,
            stake=1,
            roll_success=roll_success,
            engagement_count=engagement,
        )

    def test_good_roll_no_engagement_breaks_even(self):
        from world.items.models import ItemInstance

        showing = self._showing(roll_success=True, engagement=0)
        settle_fashion_showings()
        showing.refresh_from_db()
        assert showing.settled
        assert showing.payout == 1  # refund only — economically inert farming
        # no engagement = nothing moves (DB truth, cache-pollution guard)
        assert ItemInstance.objects.values_list("acclaim", flat=True).get(pk=self.item.pk) == 0

    def test_engaged_showing_pays_second_point_and_loads_acclaim(self):
        from world.items.models import ItemInstance

        showing = self._showing(roll_success=True, engagement=1)
        settle_fashion_showings()
        showing.refresh_from_db()
        assert showing.payout == 2
        # DB truth, not the idmapper-cached instance (test-pollution guard).
        assert ItemInstance.objects.values_list("acclaim", flat=True).get(pk=self.item.pk) == 1
        assert (
            SilhouetteVogueMomentum.objects.values_list("points", flat=True).get(
                silhouette=self.boot
            )
            >= 1
        )

    def test_overwhelming_pays_third_point_capped(self):
        showing = self._showing(roll_success=True, engagement=5)
        settle_fashion_showings()
        showing.refresh_from_db()
        assert showing.payout == 3  # the cap — three is a triumph

    def test_failed_roll_loses_stake(self):
        from world.items.models import CachetWallet

        showing = self._showing(roll_success=False, engagement=0)
        wallet = get_or_create_wallet(self.sheet)
        wallet.balance = 2
        wallet.save(update_fields=["balance"])
        settle_fashion_showings()
        showing.refresh_from_db()
        assert showing.payout == 0
        stored = CachetWallet.objects.values_list("balance", flat=True).get(
            character_sheet=self.sheet
        )
        assert stored == 2  # the stake was already spent; no refund


class ShowcaseActionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from actions.definitions.fashion import ShowcaseAction

        cls.action_cls = ShowcaseAction
        cls.character = CharacterSheetFactory().character
        cls.sheet = cls.character.sheet_data
        cls.item = ItemInstanceFactory(holder_character_sheet=cls.sheet)

    def test_piece_toggle_on_and_off(self):
        result = self.action_cls().run(actor=self.character, mode="piece", item_id=self.item.pk)
        assert result.success, result.message
        state = ShowcaseState.objects.get(character_sheet=self.sheet)
        assert state.is_active
        assert state.item == self.item

        result = self.action_cls().run(actor=self.character, mode="off")
        assert result.success
        state.refresh_from_db()
        assert not state.is_active

    def test_unowned_item_rejected(self):
        stranger_item = ItemInstanceFactory()
        result = self.action_cls().run(actor=self.character, mode="piece", item_id=stranger_item.pk)
        assert not result.success

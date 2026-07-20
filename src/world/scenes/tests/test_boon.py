"""Boon fulfillment (#2540): a granted MONEY ask moves coppers target -> asker."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.currency.services import get_or_create_purse
from world.scenes.action_constants import BoonKind
from world.scenes.boon_models import Boon
from world.scenes.boon_services import fulfill_boon
from world.scenes.factories import SceneActionRequestFactory


class FulfillBoonTests(TestCase):
    def setUp(self) -> None:
        self.request = SceneActionRequestFactory()
        self.asker_sheet = self.request.initiator_persona.character_sheet
        self.target_sheet = self.request.target_persona.character_sheet

    def _fund_target(self, amount: int) -> None:
        purse = get_or_create_purse(self.target_sheet)
        purse.balance = amount
        purse.save(update_fields=["balance"])

    def _balance(self, sheet) -> int:
        purse = get_or_create_purse(sheet)
        purse.refresh_from_db()
        return purse.balance

    def test_money_boon_moves_coppers_target_to_asker(self) -> None:
        self._fund_target(500)
        boon = Boon.objects.create(action_request=self.request, kind=BoonKind.MONEY, amount=200)
        moved = fulfill_boon(boon)
        self.assertTrue(moved)
        self.assertEqual(self._balance(self.target_sheet), 300)
        self.assertEqual(self._balance(self.asker_sheet), 200)
        boon.refresh_from_db()
        self.assertIsNotNone(boon.fulfilled_at)

    def test_fulfillment_is_idempotent(self) -> None:
        self._fund_target(500)
        boon = Boon.objects.create(action_request=self.request, kind=BoonKind.MONEY, amount=200)
        fulfill_boon(boon)
        self.assertFalse(fulfill_boon(boon))  # second call is a no-op
        self.assertEqual(self._balance(self.asker_sheet), 200)  # not doubled

    def test_deed_boon_is_rp_only_and_moves_nothing(self) -> None:
        boon = Boon.objects.create(
            action_request=self.request, kind=BoonKind.DEED, deed_text="Guard the gate"
        )
        self.assertFalse(fulfill_boon(boon))
        boon.refresh_from_db()
        self.assertIsNotNone(boon.fulfilled_at)  # still marked resolved

    def test_targetless_request_is_rejected(self) -> None:
        request = SceneActionRequestFactory(target_persona=None)
        boon = Boon.objects.create(action_request=request, kind=BoonKind.MONEY, amount=100)
        with self.assertRaises(ValidationError):
            fulfill_boon(boon)
        boon.refresh_from_db()
        self.assertIsNone(boon.fulfilled_at)  # never claimed as fulfilled

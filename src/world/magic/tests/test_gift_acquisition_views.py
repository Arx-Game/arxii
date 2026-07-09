"""Tests for the gift/technique acquisition web endpoints (#2116).

POST /api/magic/gift-unlocks/purchase/
POST /api/magic/technique-offers/accept/

Both dispatch through the same Actions the telnet `learn` command uses
(actions/definitions/gift_acquisition.py) — thin API-shape coverage; the
acquisition-logic itself is covered by
world.magic.tests.integration.test_gift_acquisition_action_e2e.
"""

from __future__ import annotations

from unittest.mock import patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from evennia_extensions.models import PlayerData
from world.action_points.models import ActionPointPool
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import GiftKind
from world.magic.factories import (
    GiftFactory,
    GiftUnlockFactory,
    ResonanceFactory,
    TechniqueFactory,
    TechniqueTeachingOfferFactory,
)
from world.magic.models import CharacterGiftUnlock, CharacterTechnique
from world.progression.models import ExperiencePointsData
from world.roster.factories import RosterEntryFactory, RosterTenureFactory


def _link_account_to_sheet(account, character, sheet):
    """Tie an AccountDB to a CharacterSheet via an active RosterTenure."""
    character.account = account
    account.characters.add(character)
    player_data, _ = PlayerData.objects.get_or_create(account=account)
    return RosterTenureFactory(
        roster_entry=RosterEntryFactory(character_sheet=sheet),
        player_data=player_data,
    )


def _give_xp(account, amount: int) -> ExperiencePointsData:
    xp, _ = ExperiencePointsData.objects.get_or_create(
        account=account,
        defaults={"total_earned": amount, "total_spent": 0},
    )
    if xp.current_available != amount:
        xp.total_earned = xp.total_spent + amount
        xp.save(update_fields=["total_earned"])
    return xp


class PurchaseGiftUnlockViewTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory(username="gift_unlock_purchaser")
        cls.character = CharacterFactory(db_key="GiftUnlockBuyer")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.tenure = _link_account_to_sheet(cls.account, cls.character, cls.sheet)
        cls.gift = GiftFactory(kind=GiftKind.MINOR, name="Sight_view_e2e")
        cls.unlock = GiftUnlockFactory(gift=cls.gift, xp_cost=25)

    def _url(self):
        return reverse("magic:gift-unlock-purchase")

    def test_unauthenticated_returns_401(self):
        response = self.client.post(self._url(), {"gift_unlock_id": self.unlock.pk}, format="json")
        self.assertIn(
            response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]
        )

    @patch("world.magic.services.gift_acquisition.enforce_advancement_gate")
    def test_happy_path_purchases_unlock(self, mock_gate):
        mock_gate.return_value = None
        _give_xp(self.account, 100)
        self.client.force_authenticate(user=self.account)

        response = self.client.post(self._url(), {"gift_unlock_id": self.unlock.pk}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(
            CharacterGiftUnlock.objects.filter(character=self.sheet, unlock=self.unlock).exists()
        )

    def test_insufficient_xp_returns_400(self):
        _give_xp(self.account, 0)
        self.client.force_authenticate(user=self.account)

        response = self.client.post(self._url(), {"gift_unlock_id": self.unlock.pk}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class AcceptTechniqueOfferViewTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory(username="technique_offer_acceptor")
        cls.character = CharacterFactory(db_key="TechniqueAcceptor")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.tenure = _link_account_to_sheet(cls.account, cls.character, cls.sheet)

        cls.gift = GiftFactory(kind=GiftKind.MINOR, name="Sight_technique_view_e2e")
        cls.gift.resonances.add(ResonanceFactory(name="Sight_view_resonance"))
        cls.technique = TechniqueFactory(gift=cls.gift, name="Soulsight_view_e2e")

        cls.teacher_tenure = RosterTenureFactory()
        cls.offer = TechniqueTeachingOfferFactory(
            teacher=cls.teacher_tenure,
            technique=cls.technique,
            learn_ap_cost=5,
            banked_ap=1,
        )

    def _url(self):
        return reverse("magic:technique-offer-accept")

    def test_unauthenticated_returns_401(self):
        response = self.client.post(self._url(), {"offer_id": self.offer.pk}, format="json")
        self.assertIn(
            response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]
        )

    @patch("world.magic.services.gift_acquisition.enforce_advancement_gate")
    def test_happy_path_requires_purchase_first(self, mock_gate):
        """Without a GiftUnlock purchase, acceptance of a first technique fails (400)."""
        mock_gate.return_value = None
        _give_xp(self.account, 500)
        learner_ap = ActionPointPool.get_or_create_for_character(self.character)
        learner_ap.current = 200
        learner_ap.save()
        teacher_ap = ActionPointPool.get_or_create_for_character(self.teacher_tenure.character)
        teacher_ap.current = 200
        teacher_ap.save()
        self.client.force_authenticate(user=self.account)

        response = self.client.post(self._url(), {"offer_id": self.offer.pk}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(
            CharacterTechnique.objects.filter(
                character=self.sheet, technique=self.technique
            ).exists()
        )

    @patch("world.magic.services.gift_acquisition.enforce_advancement_gate")
    def test_happy_path_after_purchase_mints_technique(self, mock_gate):
        mock_gate.return_value = None
        _give_xp(self.account, 500)
        learner_ap = ActionPointPool.get_or_create_for_character(self.character)
        learner_ap.current = 200
        learner_ap.save()
        teacher_ap = ActionPointPool.get_or_create_for_character(self.teacher_tenure.character)
        teacher_ap.current = 200
        teacher_ap.save()
        gift_unlock = GiftUnlockFactory(gift=self.gift, xp_cost=10)
        CharacterGiftUnlock.objects.create(character=self.sheet, unlock=gift_unlock, xp_spent=10)

        self.client.force_authenticate(user=self.account)
        response = self.client.post(self._url(), {"offer_id": self.offer.pk}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(
            CharacterTechnique.objects.filter(
                character=self.sheet, technique=self.technique
            ).exists()
        )

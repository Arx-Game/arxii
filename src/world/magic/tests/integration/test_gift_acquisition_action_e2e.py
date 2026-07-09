"""E2E journey test for the gift/technique/thread-weaving acquisition Actions (#2116).

Proves the three new REGISTRY Actions (`purchase_gift_unlock`, `accept_technique_offer`,
`accept_thread_weaving_offer`) wire the already-tested `world.magic.services
.gift_acquisition` / `world.magic.services.threads` services to a real action.run()
seam — the surface #2116 wires up (previously zero non-test callers existed).
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from actions.definitions.gift_acquisition import (
    AcceptTechniqueOfferAction,
    AcceptThreadWeavingOfferAction,
    PurchaseGiftUnlockAction,
)
from world.action_points.models import ActionPointPool
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import GiftKind, TargetKind
from world.magic.factories import (
    GiftFactory,
    GiftUnlockFactory,
    ResonanceFactory,
    TechniqueFactory,
    TechniqueTeachingOfferFactory,
    ThreadWeavingTeachingOfferFactory,
    ThreadWeavingUnlockFactory,
)
from world.magic.models import (
    CharacterGift,
    CharacterGiftUnlock,
    CharacterTechnique,
    CharacterThreadWeavingUnlock,
    Thread,
)


class GiftAcquisitionActionE2ETest(TestCase):
    """purchase_gift_unlock -> accept_technique_offer, both via action.run()."""

    def setUp(self):
        from evennia_extensions.factories import AccountFactory
        from world.progression.models.rewards import ExperiencePointsData
        from world.roster.factories import RosterTenureFactory

        self.gift = GiftFactory(kind=GiftKind.MINOR, name="Sight_action_e2e")
        self.gift.resonances.add(ResonanceFactory(name="Sight_resonance_action_e2e"))
        self.technique = TechniqueFactory(gift=self.gift, name="Soulsight_action_e2e")

        self.sheet = CharacterSheetFactory()
        self.account = AccountFactory()
        self.sheet.character.account = self.account
        self.sheet.character.save()

        self.teacher_tenure = RosterTenureFactory()
        self.gift_unlock = GiftUnlockFactory(gift=self.gift, xp_cost=10)
        self.offer = TechniqueTeachingOfferFactory(
            teacher=self.teacher_tenure,
            technique=self.technique,
            learn_ap_cost=5,
            banked_ap=1,
        )

        self.xp_tracker, _ = ExperiencePointsData.objects.get_or_create(
            account=self.account,
            defaults={"total_earned": 100, "total_spent": 0},
        )
        learner_ap = ActionPointPool.get_or_create_for_character(self.sheet.character)
        learner_ap.current = 200
        learner_ap.save()
        teacher_ap = ActionPointPool.get_or_create_for_character(self.teacher_tenure.character)
        teacher_ap.current = 200
        teacher_ap.save()

    @patch("world.magic.services.gift_acquisition.enforce_advancement_gate")
    def test_purchase_then_accept_mints_character_technique(self, mock_gate):
        mock_gate.return_value = None

        purchase_result = PurchaseGiftUnlockAction().run(
            actor=self.sheet.character,
            gift_unlock_id=self.gift_unlock.pk,
        )
        self.assertTrue(purchase_result.success, purchase_result.message)
        self.assertTrue(
            CharacterGiftUnlock.objects.filter(
                character=self.sheet, unlock=self.gift_unlock
            ).exists()
        )

        accept_result = AcceptTechniqueOfferAction().run(
            actor=self.sheet.character,
            offer_id=self.offer.pk,
        )
        self.assertTrue(accept_result.success, accept_result.message)

        self.assertTrue(
            CharacterTechnique.objects.filter(
                character=self.sheet, technique=self.technique
            ).exists()
        )
        self.assertTrue(CharacterGift.objects.filter(character=self.sheet, gift=self.gift).exists())
        self.assertTrue(
            Thread.objects.filter(
                owner=self.sheet, target_kind=TargetKind.GIFT, target_gift=self.gift
            ).exists()
        )

    @patch("world.magic.services.gift_acquisition.enforce_advancement_gate")
    def test_accept_without_purchase_fails_loud(self, mock_gate):
        """Accepting a first-technique offer with no GiftUnlock purchase fails cleanly."""
        mock_gate.return_value = None

        result = AcceptTechniqueOfferAction().run(
            actor=self.sheet.character, offer_id=self.offer.pk
        )
        self.assertFalse(result.success)
        self.assertFalse(
            CharacterTechnique.objects.filter(
                character=self.sheet, technique=self.technique
            ).exists()
        )


class ThreadWeavingOfferAcceptanceActionParityTest(TestCase):
    """accept_thread_weaving_offer mirrors the web-serializer acceptance path (#2116).

    Same assertions as world.magic.tests.test_teaching_offer_accept_view's happy path,
    but driven through the Action directly (telnet parity) rather than the DRF view.
    """

    def setUp(self):
        from evennia_extensions.factories import AccountFactory
        from world.progression.models.rewards import ExperiencePointsData
        from world.roster.factories import RosterTenureFactory

        self.sheet = CharacterSheetFactory()
        self.account = AccountFactory()
        self.sheet.character.account = self.account
        self.sheet.character.save()

        self.teacher_tenure = RosterTenureFactory()
        self.unlock = ThreadWeavingUnlockFactory(xp_cost=100)
        self.offer = ThreadWeavingTeachingOfferFactory(
            teacher=self.teacher_tenure,
            unlock=self.unlock,
            banked_ap=5,
        )

        self.xp_tracker, _ = ExperiencePointsData.objects.get_or_create(
            account=self.account,
            defaults={"total_earned": 500, "total_spent": 0},
        )
        teacher_ap = ActionPointPool.get_or_create_for_character(self.teacher_tenure.character)
        teacher_ap.banked = 5
        teacher_ap.save()

    def test_accept_deducts_xp_and_creates_receipt(self):
        result = AcceptThreadWeavingOfferAction().run(
            actor=self.sheet.character,
            offer_id=self.offer.pk,
        )
        self.assertTrue(result.success, result.message)

        char_unlock = CharacterThreadWeavingUnlock.objects.filter(
            character=self.sheet, unlock=self.unlock
        ).first()
        self.assertIsNotNone(char_unlock)
        self.assertEqual(char_unlock.xp_spent, 100)
        self.assertEqual(char_unlock.teacher, self.teacher_tenure)

        self.xp_tracker.refresh_from_db()
        self.assertEqual(self.xp_tracker.total_spent, 100)

"""E2E journey test for post-CG gift acquisition (#1587).

Full flow: teacher creates offer → learner buys GiftUnlock (XP) →
learner accepts offer (first technique: gift implicitly acquired +
latent thread + technique minted) → learner accepts second offer
(cheaper AP) → learner hits cap.
"""

from unittest.mock import patch

from django.test import TestCase

from world.action_points.models import ActionPointPool
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import GiftKind, TargetKind
from world.magic.exceptions import TechniqueCapExceeded
from world.magic.factories import GiftFactory, ResonanceFactory, TechniqueFactory
from world.magic.models import (
    CharacterGift,
    CharacterTechnique,
    GiftUnlock,
    TechniqueTeachingOffer,
    Thread,
)
from world.magic.services.gift_acquisition import (
    accept_technique_offer,
    spend_xp_on_gift_unlock,
)


class GiftAcquisitionE2ETest(TestCase):
    """Drives the full post-CG gift-acquisition journey end-to-end."""

    def setUp(self):
        from evennia_extensions.factories import AccountFactory
        from world.progression.models.rewards import ExperiencePointsData
        from world.roster.factories import RosterTenureFactory

        self.gift = GiftFactory(kind=GiftKind.MINOR, name="Sight")
        self.resonance = ResonanceFactory()
        self.gift.resonances.add(self.resonance)

        self.technique1 = TechniqueFactory(gift=self.gift, name="Soulsight")
        self.technique2 = TechniqueFactory(gift=self.gift, name="Magesight")
        self.technique3 = TechniqueFactory(gift=self.gift, name="Arcane Vision")
        self.technique4 = TechniqueFactory(gift=self.gift, name="Overcap")

        self.sheet = CharacterSheetFactory()
        self.account = AccountFactory()
        self.sheet.character.account = self.account
        self.sheet.character.save()
        self.teacher_tenure = RosterTenureFactory()
        self.unlock = GiftUnlock.objects.create(gift=self.gift, xp_cost=10)

        self.xp_tracker, _ = ExperiencePointsData.objects.get_or_create(
            account=self.account,
            defaults={"total_earned": 100, "total_spent": 0},
        )
        self.learner_ap = ActionPointPool.get_or_create_for_character(self.sheet.character)
        self.learner_ap.current = 200
        self.learner_ap.save()
        self.teacher_ap = ActionPointPool.get_or_create_for_character(self.teacher_tenure.character)
        self.teacher_ap.current = 200
        self.teacher_ap.save()

    @patch("world.magic.services.gift_acquisition.enforce_advancement_gate")
    def test_full_journey(self, mock_gate):
        mock_gate.return_value = None

        # 1. Learner buys the GiftUnlock (XP gate)
        receipt = spend_xp_on_gift_unlock(self.sheet, self.unlock)
        self.assertEqual(receipt.xp_spent, 10)
        self.xp_tracker.refresh_from_db()
        self.assertEqual(self.xp_tracker.total_spent, 10)

        # 2. Teacher creates an offer for the first technique
        offer1 = TechniqueTeachingOffer.objects.create(
            teacher=self.teacher_tenure,
            technique=self.technique1,
            pitch="I will teach you Soulsight",
            learn_ap_cost=5,
            banked_ap=1,
        )

        # 3. Learner accepts — first technique, gift implicitly acquired
        ct1 = accept_technique_offer(self.sheet, offer1)
        self.assertEqual(ct1.technique, self.technique1)

        # Gift was acquired
        self.assertTrue(CharacterGift.objects.filter(character=self.sheet, gift=self.gift).exists())
        # Latent GIFT thread was provisioned
        thread = Thread.objects.get(
            owner=self.sheet,
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
        )
        self.assertEqual(thread.level, 0)

        # AP cost was 5 * 3 (first_technique_ap_multiplier) = 15
        self.learner_ap.refresh_from_db()
        self.assertEqual(self.learner_ap.current, 200 - 15)

        # 4. Teacher creates offer for second technique
        offer2 = TechniqueTeachingOffer.objects.create(
            teacher=self.teacher_tenure,
            technique=self.technique2,
            pitch="I will teach you Magesight",
            learn_ap_cost=5,
            banked_ap=1,
        )

        # 5. Learner accepts — second technique, gift already owned, base AP
        self.learner_ap.current = 200
        self.learner_ap.save()
        ct2 = accept_technique_offer(self.sheet, offer2)
        self.assertEqual(ct2.technique, self.technique2)
        self.learner_ap.refresh_from_db()
        self.assertEqual(self.learner_ap.current, 200 - 5)  # 5 AP, no multiplier

        # 6. Learn a third technique (cap = 3 at depth 1 for level-0 thread)
        offer3 = TechniqueTeachingOffer.objects.create(
            teacher=self.teacher_tenure,
            technique=self.technique3,
            pitch="Third technique",
            learn_ap_cost=5,
            banked_ap=1,
        )
        self.learner_ap.current = 200
        self.learner_ap.save()
        ct3 = accept_technique_offer(self.sheet, offer3)
        self.assertEqual(ct3.technique, self.technique3)

        # 7. Fourth technique should hit the cap
        offer4 = TechniqueTeachingOffer.objects.create(
            teacher=self.teacher_tenure,
            technique=self.technique4,
            pitch="Over cap",
            learn_ap_cost=5,
            banked_ap=1,
        )
        self.learner_ap.current = 200
        self.learner_ap.save()
        with self.assertRaises(TechniqueCapExceeded):
            accept_technique_offer(self.sheet, offer4)

        # 8. Verify total techniques learned
        self.assertEqual(
            CharacterTechnique.objects.filter(
                character=self.sheet, technique__gift=self.gift
            ).count(),
            3,
        )

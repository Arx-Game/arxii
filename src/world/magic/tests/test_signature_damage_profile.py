from decimal import Decimal

from django.test import TestCase

from world.magic.models.signature import SignatureMotifBonus, SignatureMotifBonusDamageProfile


class SignatureDamageProfileBudgetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.bonus = SignatureMotifBonus.objects.create(name="Spider's Bite")
        cls.profile = SignatureMotifBonusDamageProfile.objects.create(
            signature_bonus=cls.bonus,
            base_damage=4,
            damage_intensity_multiplier=Decimal("0.5"),
            damage_per_extra_sl=1,
            minimum_success_level=1,
        )

    def test_signature_profile_has_compute_damage_budget(self):
        # Inherited from AbstractDamageProfile after Task 1.
        budget = self.profile.compute_damage_budget(effective_power=10, success_level=2)
        assert budget > 0

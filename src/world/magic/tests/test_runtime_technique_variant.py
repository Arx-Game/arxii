"""Runtime technique stats: gift-technique variant deltas applied at cast time.

When a character's GIFT thread has reached a TechniqueVariant's unlock_thread_level,
get_runtime_technique_stats must return intensity and control values that include the
variant's intensity_delta and control_delta on top of the base and any identity/process
terms.  This is Task 2 of the gift-specialization engine (#1581).
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import TargetKind
from world.magic.factories import (
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
    TechniqueVariantFactory,
)
from world.magic.services import get_runtime_technique_stats
from world.magic.specialization.services import provision_latent_gift_thread


class RuntimeTechniqueVariantTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.gift = GiftFactory()
        cls.resonance = ResonanceFactory()
        cls.gift.resonances.add(cls.resonance)
        cls.technique = TechniqueFactory(gift=cls.gift, intensity=10, control=10)
        cls.variant = TechniqueVariantFactory(
            parent_technique=cls.technique,
            resonance=cls.resonance,
            unlock_thread_level=3,
            intensity_delta=5,
            control_delta=2,
        )
        provision_latent_gift_thread(cls.sheet, cls.gift, resonance=cls.resonance)
        thread = next(
            t for t in cls.sheet.character.threads.all() if t.target_kind == TargetKind.GIFT
        )
        thread.level = 3
        thread.save()
        cls.sheet.character.threads.invalidate()

    def test_runtime_stats_apply_variant_deltas(self):
        stats = get_runtime_technique_stats(self.technique, self.sheet.character)
        # base 10 + variant 5 (plus any identity/process terms which are >= 0)
        self.assertGreaterEqual(stats.intensity, 15)
        self.assertGreaterEqual(stats.control, 12)

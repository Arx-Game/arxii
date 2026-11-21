"""The cast sites read the character's GIFT-thread resonance, not the authored M2M."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import GiftFactory, ResonanceFactory
from world.magic.specialization.services import provision_latent_gift_thread


class GiftResonancesReadSeamTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.gift = GiftFactory()
        # The gift SUPPORTS two resonances...
        cls.supported_a = ResonanceFactory()
        cls.supported_b = ResonanceFactory()
        cls.gift.resonances.add(cls.supported_a, cls.supported_b)
        # ...but the character's thread is woven at supported_a only.
        provision_latent_gift_thread(cls.sheet, cls.gift, resonances=[cls.supported_a])

    def test_gift_resonances_for_returns_only_thread_resonance(self) -> None:
        from world.magic.specialization.services import gift_resonances_for

        result = gift_resonances_for(self.sheet.character, self.gift)
        self.assertEqual([r.pk for r in result], [self.supported_a.pk])

    def test_a_cast_with_no_resonance_draws_on_the_thread_resonance(self) -> None:
        """``cast_working_resonances`` (the one reader of power-tied resonances, #5231) falls
        back to the thread's resonances when no cast resonance is given, never the M2M."""
        from world.magic.factories import TechniqueFactory
        from world.magic.specialization.services import cast_working_resonances

        technique = TechniqueFactory(gift=self.gift)
        result = cast_working_resonances(self.sheet.character, technique, None)
        self.assertEqual([r.pk for r in result], [self.supported_a.pk])

"""weave_thread for a GIFT target commits a resonance onto the latent thread."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import TargetKind
from world.magic.factories import GiftFactory, ResonanceFactory
from world.magic.models import Thread
from world.magic.services.threads import weave_thread
from world.magic.specialization.services import provision_latent_gift_thread


class WeaveGiftThreadTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.gift = GiftFactory()
        cls.res_a = ResonanceFactory()
        cls.res_b = ResonanceFactory()
        cls.gift.resonances.add(cls.res_a, cls.res_b)
        # Latent thread at res_a (as provisioned at CG).
        provision_latent_gift_thread(cls.sheet, cls.gift, resonance=cls.res_a)

    def test_weave_commits_resonance_onto_latent_thread(self) -> None:
        thread = weave_thread(
            self.sheet,
            target_kind=TargetKind.GIFT,
            target=self.gift,
            resonance=self.res_b,
        )
        # The latent thread is reused (not a new row), resonance updated to res_b.
        self.assertEqual(thread.resonance, self.res_b)
        self.assertEqual(
            Thread.objects.filter(
                owner=self.sheet,
                target_kind=TargetKind.GIFT,
                target_gift=self.gift,
            ).count(),
            1,
        )

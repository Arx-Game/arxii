"""Tests for multi-resonance GIFT threads and cast-time variant selection (#1619).

One thread per gift now holds several resonances on its ThreadResonance rows
(#5123); the cases that built a second thread per resonance are retired, and
the gift-resonance rewrite adds the several-rows cases back.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import TargetKind
from world.magic.factories import (
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
)
from world.magic.models import Thread
from world.magic.specialization.models import TechniqueVariant
from world.magic.specialization.services import (
    gift_resonances_for,
    provision_additional_gift_thread,
    provision_latent_gift_thread,
)


class MultiResonanceTests(TestCase):
    """Multiple GIFT threads per gift at different resonances."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.gift = GiftFactory()
        cls.celestial = ResonanceFactory(name="Celestial")
        cls.abyssal = ResonanceFactory(name="Abyssal")
        cls.gift.resonances.add(cls.celestial, cls.abyssal)

        cls.technique = TechniqueFactory(gift=cls.gift)

        cls.celestial_variant = TechniqueVariant.objects.create(
            parent_technique=cls.technique,
            resonance=cls.celestial,
            unlock_thread_level=30,
            name_override="Celestial Form",
            intensity_delta=5,
        )
        cls.abyssal_variant = TechniqueVariant.objects.create(
            parent_technique=cls.technique,
            resonance=cls.abyssal,
            unlock_thread_level=30,
            name_override="Abyssal Form",
            intensity_delta=10,
        )

    def _level_thread(self, resonance) -> Thread:
        """Provision and level a GIFT thread at the given resonance."""
        provision_latent_gift_thread(self.sheet, self.gift, resonance=resonance)
        thread = Thread.objects.get(
            owner=self.sheet,
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
            resonance=resonance,
        )
        thread.level = 30  # the variants' unlock level
        thread.save(update_fields=["level"])
        self.sheet.character.threads.invalidate()
        return thread

    def test_provision_additional_rejects_unsupported_resonance(self) -> None:
        """provision_additional_gift_thread rejects a resonance not in the gift's supported set."""
        from world.magic.exceptions import UnsupportedGiftResonanceError

        self._level_thread(self.celestial)
        primal = ResonanceFactory(name="Primal")

        with self.assertRaises(UnsupportedGiftResonanceError):
            provision_additional_gift_thread(self.sheet, self.gift, resonance=primal)

    def test_provision_latent_idempotent_on_same_resonance(self) -> None:
        """provision_latent_gift_thread is idempotent on (owner, gift, resonance)."""
        t1 = provision_latent_gift_thread(self.sheet, self.gift, resonance=self.celestial)
        t2 = provision_latent_gift_thread(self.sheet, self.gift, resonance=self.celestial)
        self.assertEqual(t1.pk, t2.pk)

    def test_gift_resonances_for_single_when_one_thread(self) -> None:
        """gift_resonances_for returns a single-element list when only one thread exists."""
        self._level_thread(self.celestial)

        resonances = gift_resonances_for(self.sheet.character, self.gift)
        self.assertEqual([r.pk for r in resonances], [self.celestial.pk])

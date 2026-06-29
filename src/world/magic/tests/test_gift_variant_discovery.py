"""GIFT-thread variant discovery beat fires on imbue past unlock_thread_level."""

from django.test import TestCase

from world.achievements.factories import AchievementFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.codex.factories import CodexEntryFactory
from world.magic.constants import TargetKind
from world.magic.factories import (
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
    ThreadFactory,
)
from world.magic.services.resonance import spend_resonance_for_imbuing
from world.magic.specialization.models import TechniqueVariant


class GiftVariantDiscoveryTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.gift = GiftFactory()
        cls.resonance = ResonanceFactory()
        cls.gift.resonances.add(cls.resonance)
        # Latent level-0 GIFT thread (as provisioned at CG).
        cls.thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            target_kind=TargetKind.GIFT,
            target_gift=cls.gift,
            target_trait=None,
            level=0,
        )
        cls.technique = TechniqueFactory(gift=cls.gift)
        cls.achievement = AchievementFactory()
        cls.codex_entry = CodexEntryFactory()
        cls.variant = TechniqueVariant.objects.create(
            parent_technique=cls.technique,
            resonance=cls.resonance,
            unlock_thread_level=3,
            name_override="Celestial Form",
            discovery_achievement=cls.achievement,
            codex_entry=cls.codex_entry,
        )

    def test_imbue_past_unlock_fires_discovery(self) -> None:
        from world.achievements.models import CharacterAchievement
        from world.magic.factories import CharacterResonanceFactory

        CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=self.resonance,
            balance=10000,
        )
        spend_resonance_for_imbuing(
            character_sheet=self.sheet,
            thread=self.thread,
            amount=500,  # enough to cross level 3
        )
        self.thread.refresh_from_db()
        self.assertGreaterEqual(self.thread.level, 3)
        # Discovery beat fired:
        self.assertTrue(
            CharacterAchievement.objects.filter(
                character_sheet=self.sheet,
                achievement=self.achievement,
            ).exists()
        )

    def test_imbue_below_unlock_does_not_fire(self) -> None:
        from world.achievements.models import CharacterAchievement
        from world.magic.factories import CharacterResonanceFactory

        CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=self.resonance,
            balance=10000,
        )
        spend_resonance_for_imbuing(
            character_sheet=self.sheet,
            thread=self.thread,
            amount=1,  # stays below level 3
        )
        self.assertFalse(
            CharacterAchievement.objects.filter(
                character_sheet=self.sheet,
                achievement=self.achievement,
            ).exists()
        )

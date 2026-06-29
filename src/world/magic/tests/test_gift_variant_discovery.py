"""GIFT-thread variant discovery beat tested by calling the ceremony directly."""

from django.test import TestCase

from world.achievements.factories import AchievementFactory
from world.achievements.models import CharacterAchievement
from world.character_sheets.factories import CharacterSheetFactory
from world.codex.factories import CodexEntryFactory
from world.covenants.discovery import fire_variant_discoveries
from world.magic.constants import TargetKind
from world.magic.factories import (
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
    ThreadFactory,
)
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

    def test_crossing_unlock_fires_discovery(self) -> None:
        fire_variant_discoveries(thread=self.thread, starting_level=0, new_level=3)

        self.assertTrue(
            CharacterAchievement.objects.filter(
                character_sheet=self.sheet,
                achievement=self.achievement,
            ).exists()
        )
        # Codex unlock is keyed on RosterEntry; skip gracefully when absent.
        if hasattr(self.sheet, "roster_entry") and self.sheet.roster_entry is not None:
            from world.codex.constants import CodexKnowledgeStatus
            from world.codex.models import CharacterCodexKnowledge

            self.assertTrue(
                CharacterCodexKnowledge.objects.filter(
                    roster_entry=self.sheet.roster_entry,
                    entry=self.codex_entry,
                    status=CodexKnowledgeStatus.KNOWN,
                ).exists()
            )

    def test_below_unlock_does_not_fire(self) -> None:
        fire_variant_discoveries(thread=self.thread, starting_level=0, new_level=2)

        self.assertFalse(
            CharacterAchievement.objects.filter(
                character_sheet=self.sheet,
                achievement=self.achievement,
            ).exists()
        )

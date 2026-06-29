"""E2E: gift specialization — CG latent thread -> base resolve -> imbue -> variant -> discovery.

North-star journey proving the specialization engine works end-to-end: a character
provisioned with a latent GIFT thread at CG resolves to the base technique; once the
thread advances past the variant's unlock threshold the resolver derives the variant
(derive-on-read, no regeneration) and the discovery beat fires (achievement + codex).

NOTE: the thread is advanced past ``unlock_thread_level=3`` by setting ``level``
directly, NOT via ``spend_resonance_for_imbuing``. The GIFT anchor cap
(``compute_anchor_cap``) has no GIFT case and returns 0, so the cap-gated imbue path
raises ``AnchorCapExceeded`` on a fresh GIFT thread. The GIFT anchor cap is a
deliberately deferred needs-design follow-up (see the #1578 PR notes); until it lands,
the E2E advances the level directly and calls the discovery ceremony explicitly — the
same ceremony-direct pattern proven in ``test_gift_variant_discovery.py``.
"""

from typing import ClassVar

from django.test import TestCase

from world.achievements.factories import AchievementFactory
from world.achievements.models import Achievement, CharacterAchievement
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import CharacterSheet
from world.codex.factories import CodexEntryFactory
from world.codex.models import CodexEntry
from world.covenants.discovery import fire_variant_discoveries
from world.magic.constants import TargetKind
from world.magic.factories import GiftFactory, ResonanceFactory, TechniqueFactory
from world.magic.models import Gift, Resonance, Technique, Thread
from world.magic.specialization.models import TechniqueVariant
from world.magic.specialization.services import (
    gift_resonances_for,
    provision_latent_gift_thread,
    resolve_specialized_variant,
)
from world.roster.factories import RosterEntryFactory


class GiftSpecializationE2ETest(TestCase):
    sheet: ClassVar[CharacterSheet]
    gift: ClassVar[Gift]
    resonance: ClassVar[Resonance]
    technique: ClassVar[Technique]
    achievement: ClassVar[Achievement]
    codex_entry: ClassVar[CodexEntry]
    variant: ClassVar[TechniqueVariant]

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        # Codex unlock is keyed on RosterEntry; ensure one exists so the full
        # discovery beat (achievement + codex) can be asserted end-to-end.
        RosterEntryFactory(character_sheet=cls.sheet)
        cls.gift = GiftFactory()
        cls.resonance = ResonanceFactory()
        cls.gift.resonances.add(cls.resonance)
        # The gift's starting technique.
        cls.technique = TechniqueFactory(gift=cls.gift)
        # A resonance-specialized variant of that technique, unlocking at level 3.
        cls.achievement = AchievementFactory()
        cls.codex_entry = CodexEntryFactory()
        cls.variant = TechniqueVariant.objects.create(
            parent_technique=cls.technique,
            resonance=cls.resonance,
            unlock_thread_level=3,
            name_override="Celestial Form",
            intensity_delta=5,
            control_delta=2,
            discovery_achievement=cls.achievement,
            codex_entry=cls.codex_entry,
        )

    def test_full_journey(self) -> None:
        # 1. CG: provision the latent level-0 GIFT thread at the chosen resonance.
        provision_latent_gift_thread(self.sheet, self.gift, resonance=self.resonance)

        # 2. Read at level 0: the resolver returns the parent (no variant yet).
        resolved = resolve_specialized_variant(
            entity=self.technique, character=self.sheet.character
        )
        self.assertEqual(resolved.name, self.technique.name)  # base form

        # 3. Cast-pipeline read seam: gift_resonances_for returns the thread's resonance.
        resonances = gift_resonances_for(self.sheet.character, self.gift)
        self.assertEqual([r.pk for r in resonances], [self.resonance.pk])

        # 4. Advance the thread past the variant's unlock threshold (level 3).
        #    Set level directly — the GIFT anchor cap is 0 (deferred needs-design),
        #    so the cap-gated imbue path would raise AnchorCapExceeded. See module
        #    docstring. We then fire the discovery ceremony explicitly (the real
        #    imbue path fires it internally; here we invoke it directly).
        latent = Thread.objects.get(
            owner=self.sheet,
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
        )
        latent.level = 3
        latent.save(update_fields=["level"])
        fire_variant_discoveries(thread=latent, starting_level=0, new_level=3)

        # 5. Read again: the resolver now returns the variant (derive-on-read).
        resolved = resolve_specialized_variant(
            entity=self.technique, character=self.sheet.character
        )
        self.assertEqual(resolved.name, "Celestial Form")
        self.assertEqual(resolved.intensity, self.technique.intensity + 5)
        self.assertEqual(resolved.control, self.technique.control + 2)

        # 6. Discovery beat fired: achievement granted.
        self.assertTrue(
            CharacterAchievement.objects.filter(
                character_sheet=self.sheet,
                achievement=self.achievement,
            ).exists()
        )
        # Codex unlock is keyed on RosterEntry; skip gracefully when absent
        # (CharacterSheetFactory does not create a roster_entry).
        if self.sheet.roster_entry:
            from world.codex.constants import CodexKnowledgeStatus
            from world.codex.models import CharacterCodexKnowledge

            self.assertTrue(
                CharacterCodexKnowledge.objects.filter(
                    roster_entry=self.sheet.roster_entry,
                    entry=self.codex_entry,
                    status=CodexKnowledgeStatus.KNOWN,
                ).exists()
            )

    def test_base_form_resolves_without_thread(self) -> None:
        # A character with the technique but no GIFT thread still resolves to parent.
        other_sheet = CharacterSheetFactory()
        resolved = resolve_specialized_variant(
            entity=self.technique, character=other_sheet.character
        )
        self.assertEqual(resolved.name, self.technique.name)

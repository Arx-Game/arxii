"""E2E: gift specialization — CG latent thread -> base resolve -> imbue -> variant -> discovery.

North-star journey proving the specialization engine works end-to-end: a character
provisioned with a latent GIFT thread at CG resolves to the base technique; once the
thread advances past the variant's unlock threshold the resolver derives the variant
(derive-on-read, no regeneration) and the discovery beat fires (achievement + codex).

The GIFT anchor cap (``compute_anchor_cap``) is now handled: for a fresh character with
no path history ``_current_path_stage`` returns 1, giving an effective cap of 10 (1
stage × ANCHOR_CAP_GIFT_PER_STAGE=10), so ``spend_resonance_for_imbuing`` can advance
a GIFT thread to level 3 without hitting the cap. The journey therefore exercises two
paths:

- ``test_full_journey`` / ``test_base_form_resolves_without_thread``: direct
  level-setting + explicit ``fire_variant_discoveries`` ceremony (ceremony-direct pattern).
- ``test_imbuing_to_unlock_fires_discovery``: real ``spend_resonance_for_imbuing`` path
  (internally calls ``fire_variant_discoveries``).
- ``test_variant_takes_effect_at_cast``: runtime-stat read via ``get_runtime_technique_stats``
  proves variant deltas reach the cast power seam.
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
from world.magic.models import CharacterResonance, Gift, Resonance, Technique, Thread
from world.magic.services.resonance import spend_resonance_for_imbuing
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
        #    Set level directly + invoke fire_variant_discoveries explicitly —
        #    this is the ceremony-direct pattern (as opposed to the real imbue
        #    path in test_imbuing_to_unlock_fires_discovery, which calls
        #    spend_resonance_for_imbuing and fires the ceremony internally).
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

    def test_variant_takes_effect_at_cast(self) -> None:
        """Variant intensity/control deltas are visible through the cast-power seam.

        Uses the delta between a level-0 (base-form) read and a level-3 (variant)
        read to isolate the variant contribution from social-safety, identity
        modifier, and IntensityTier noise — the difference must equal the authored
        ``intensity_delta=5`` and ``control_delta=2`` on the variant.
        """
        from world.magic.services.techniques import get_runtime_technique_stats

        provision_latent_gift_thread(self.sheet, self.gift, resonance=self.resonance)
        thread = next(
            t for t in self.sheet.character.threads.all() if t.target_kind == TargetKind.GIFT
        )

        # Read base-form stats (thread at level 0 — below the variant's unlock_thread_level=3).
        base_stats = get_runtime_technique_stats(self.technique, self.sheet.character)

        # Advance to level 3 to unlock the variant; invalidate the cached handler.
        thread.level = 3
        thread.save(update_fields=["level"])
        self.sheet.character.threads.invalidate()

        # Read again — the resolver should now return the variant form.
        variant_stats = get_runtime_technique_stats(self.technique, self.sheet.character)

        # The delta must match the variant's authored deltas exactly, regardless of any
        # constant modifier streams (social-safety, identity modifiers, IntensityTier).
        self.assertEqual(
            variant_stats.intensity - base_stats.intensity,
            self.variant.intensity_delta,
            "intensity delta should equal variant.intensity_delta",
        )
        self.assertEqual(
            variant_stats.control - base_stats.control,
            self.variant.control_delta,
            "control delta should equal variant.control_delta",
        )

    def test_imbuing_to_unlock_fires_discovery(self) -> None:
        """Real imbue path: spending resonance to level 3 fires the discovery ceremony.

        ``spend_resonance_for_imbuing(character_sheet, thread, amount)`` advances the
        thread greedily by spending ``amount`` developed-points.  Sub-10 levels each
        cost 1 dp, so ``amount=3`` carries the thread from 0 → 3 (crossing
        ``unlock_thread_level=3``).  The function internally calls
        ``fire_variant_discoveries``, so the achievement should be granted without any
        explicit ceremony call in this test.

        The GIFT anchor cap for a fresh character with no path history is
        ``_current_path_stage() × ANCHOR_CAP_GIFT_PER_STAGE = 1 × 10 = 10``, so the
        cap does not block advancement to level 3.
        """
        provision_latent_gift_thread(self.sheet, self.gift, resonance=self.resonance)
        thread = next(
            t for t in self.sheet.character.threads.all() if t.target_kind == TargetKind.GIFT
        )

        # Ensure the CharacterResonance row exists and has sufficient balance.
        # ``provision_latent_gift_thread`` does not create this row; the imbue
        # service requires it to debit the resonance currency bucket.
        cr, _ = CharacterResonance.objects.get_or_create(
            character_sheet=self.sheet,
            resonance=self.resonance,
        )
        cr.balance = 9999
        cr.save(update_fields=["balance"])

        # Spend 3 dp: levels 0→1, 1→2, 2→3 each cost 1 dp (sub-10 formula).
        spend_resonance_for_imbuing(self.sheet, thread, 3)

        # The discovery ceremony fires internally; achievement must now exist.
        self.assertTrue(
            CharacterAchievement.objects.filter(
                character_sheet=self.sheet,
                achievement=self.achievement,
            ).exists(),
            "discovery achievement should be granted after imbuing across level 3",
        )

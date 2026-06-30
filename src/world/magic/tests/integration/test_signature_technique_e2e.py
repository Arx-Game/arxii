"""E2E: signature technique-threads (ADR-0056, #1582).

North-star journey proving the signature axis works end-to-end:

1. A character with a gift + GIFT thread (resonance A) and a technique under
   that gift. Weaving a signature (TECHNIQUE) thread on that technique with the
   *same* resonance A: ``cast_resonances_for`` returns [A] and the resolver
   matches the variant on resonance A using cumulative level
   (gift baseline + signature depth).

2. **Discordant signature**: the signature thread carries resonance B (different
   from the gift's resonance A). ``cast_resonances_for`` returns [B] for this
   technique — the signature overrides the gift's resonance for one technique.
   A *different* technique under the same gift (no signature) still returns [A].

3. **One active signature per technique**: a second active TECHNIQUE thread on
   the same technique is rejected by the DB constraint. Retiring the old thread
   and weaving a new one succeeds.

4. **Cumulative variant matching**: a signature thread whose level, combined
   with the gift thread's level, crosses the variant's ``unlock_thread_level``
   resolves the variant — even when neither thread alone would cross it.
"""

from typing import ClassVar

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.achievements.factories import AchievementFactory
from world.achievements.models import Achievement, CharacterAchievement
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import CharacterSheet
from world.codex.factories import CodexEntryFactory
from world.codex.models import CodexEntry
from world.magic.constants import TargetKind
from world.magic.factories import (
    AffinityFactory,
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
)
from world.magic.models import Gift, Resonance, Technique, Thread
from world.magic.specialization.models import TechniqueVariant
from world.magic.specialization.services import (
    cast_resonances_for,
    gift_resonances_for,
    provision_latent_gift_thread,
    resolve_specialized_variant,
    signature_thread_for_technique,
)
from world.roster.factories import RosterEntryFactory


class SignatureTechniqueE2ETest(TestCase):
    """Proves the signature thread's resonance override + variant resolution."""

    sheet: ClassVar[CharacterSheet]
    gift: ClassVar[Gift]
    resonance_a: ClassVar[Resonance]
    resonance_b: ClassVar[Resonance]
    technique: ClassVar[Technique]
    other_technique: ClassVar[Technique]
    achievement: ClassVar[Achievement]
    codex_entry: ClassVar[CodexEntry]

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        RosterEntryFactory(character_sheet=cls.sheet)

        # Two resonances on *different* affinities — the core of the discordant
        # signature test.
        affinity_celestial = AffinityFactory(name="Celestial")
        affinity_primal = AffinityFactory(name="Primal")
        cls.resonance_a = ResonanceFactory(name="Fire", affinity=affinity_celestial)
        cls.resonance_b = ResonanceFactory(name="Shadow", affinity=affinity_primal)

        cls.gift = GiftFactory()
        # The gift supports both resonances.
        cls.gift.resonances.add(cls.resonance_a, cls.resonance_b)

        # Two techniques under the gift.
        cls.technique = TechniqueFactory(gift=cls.gift, name="Flame Bolt")
        cls.other_technique = TechniqueFactory(gift=cls.gift, name="Fire Shield")

        # A variant unlocking at level 3 on resonance_a.
        cls.achievement = AchievementFactory()
        cls.codex_entry = CodexEntryFactory()
        cls.variant_a = TechniqueVariant.objects.create(
            parent_technique=cls.technique,
            resonance=cls.resonance_a,
            unlock_thread_level=3,
            name_override="Celestial Flame Bolt",
            intensity_delta=5,
            control_delta=2,
            discovery_achievement=cls.achievement,
            codex_entry=cls.codex_entry,
        )
        # A variant unlocking at level 3 on resonance_b (the discordant path).
        cls.achievement_b = AchievementFactory()
        cls.codex_entry_b = CodexEntryFactory()
        cls.variant_b = TechniqueVariant.objects.create(
            parent_technique=cls.technique,
            resonance=cls.resonance_b,
            unlock_thread_level=3,
            name_override="Shadow Flame Bolt",
            intensity_delta=3,
            control_delta=4,
            discovery_achievement=cls.achievement_b,
            codex_entry=cls.codex_entry_b,
        )

    def setUp(self) -> None:
        """Provision the latent GIFT thread at resonance_a before each test."""
        super().setUp()
        provision_latent_gift_thread(self.sheet, self.gift, resonance=self.resonance_a)

    def test_no_signature_falls_back_to_gift_resonance(self) -> None:
        """Without a signature thread, cast_resonances_for returns the gift's."""
        resonances = cast_resonances_for(self.sheet.character, self.technique)
        self.assertEqual([r.pk for r in resonances], [self.resonance_a.pk])

    def test_signature_same_resonance_as_gift(self) -> None:
        """A signature thread at the same resonance as the gift returns that resonance."""
        Thread.objects.create(
            owner=self.sheet,
            resonance=self.resonance_a,
            target_kind=TargetKind.TECHNIQUE,
            target_technique=self.technique,
            level=0,
        )
        self.sheet.character.threads.invalidate()

        resonances = cast_resonances_for(self.sheet.character, self.technique)
        self.assertEqual([r.pk for r in resonances], [self.resonance_a.pk])

    def test_discordant_signature_overrides_gift_resonance(self) -> None:
        """A signature thread at resonance_b overrides the gift's resonance_a."""
        Thread.objects.create(
            owner=self.sheet,
            resonance=self.resonance_b,
            target_kind=TargetKind.TECHNIQUE,
            target_technique=self.technique,
            level=0,
        )
        self.sheet.character.threads.invalidate()

        # The signature overrides the gift's resonance for THIS technique.
        resonances = cast_resonances_for(self.sheet.character, self.technique)
        self.assertEqual([r.pk for r in resonances], [self.resonance_b.pk])

    def test_discordant_signature_does_not_affect_other_techniques(self) -> None:
        """A signature on one technique doesn't change another technique's resonance."""
        Thread.objects.create(
            owner=self.sheet,
            resonance=self.resonance_b,
            target_kind=TargetKind.TECHNIQUE,
            target_technique=self.technique,
            level=0,
        )
        self.sheet.character.threads.invalidate()

        # The signature technique gets the signature's resonance.
        sig_resonances = cast_resonances_for(self.sheet.character, self.technique)
        self.assertEqual([r.pk for r in sig_resonances], [self.resonance_b.pk])

        # The other technique (no signature) still gets the gift's resonance.
        other_resonances = cast_resonances_for(self.sheet.character, self.other_technique)
        self.assertEqual([r.pk for r in other_resonances], [self.resonance_a.pk])

    def test_signature_thread_lookup(self) -> None:
        """signature_thread_for_technique returns the active thread."""
        sig = Thread.objects.create(
            owner=self.sheet,
            resonance=self.resonance_b,
            target_kind=TargetKind.TECHNIQUE,
            target_technique=self.technique,
            level=5,
        )
        self.sheet.character.threads.invalidate()

        found = signature_thread_for_technique(self.sheet.character, self.technique)
        self.assertIsNotNone(found)
        self.assertEqual(found.pk, sig.pk)

        # No signature on the other technique.
        self.assertIsNone(
            signature_thread_for_technique(self.sheet.character, self.other_technique)
        )

    def test_one_active_signature_per_technique(self) -> None:
        """The DB constraint prevents two active TECHNIQUE threads on the same technique."""
        Thread.objects.create(
            owner=self.sheet,
            resonance=self.resonance_a,
            target_kind=TargetKind.TECHNIQUE,
            target_technique=self.technique,
            level=0,
        )

        # A second active thread on the same technique (different resonance)
        # must be rejected by the uniq_thread_technique_active constraint.
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Thread.objects.create(
                    owner=self.sheet,
                    resonance=self.resonance_b,
                    target_kind=TargetKind.TECHNIQUE,
                    target_technique=self.technique,
                    level=0,
                )

    def test_retire_then_reweave_signature(self) -> None:
        """Retiring a signature allows weaving a new one on the same technique."""
        old = Thread.objects.create(
            owner=self.sheet,
            resonance=self.resonance_a,
            target_kind=TargetKind.TECHNIQUE,
            target_technique=self.technique,
            level=0,
        )
        self.sheet.character.threads.invalidate()

        # Retire the old signature.
        from django.utils import timezone

        old.retired_at = timezone.now()
        old.save(update_fields=["retired_at"])
        self.sheet.character.threads.invalidate()

        # Weaving a new one at a different resonance succeeds.
        new = Thread.objects.create(
            owner=self.sheet,
            resonance=self.resonance_b,
            target_kind=TargetKind.TECHNIQUE,
            target_technique=self.technique,
            level=0,
        )
        self.sheet.character.threads.invalidate()
        self.assertEqual(new.resonance_id, self.resonance_b.pk)

    def test_cumulative_variant_matching(self) -> None:
        """Signature depth adds to gift baseline for variant unlocking.

        Gift thread at level 1 + signature thread at level 2 = effective level 3,
        which crosses the variant's unlock_thread_level=3. Neither thread alone
        would cross it.
        """
        # Set the gift thread to level 1 (below the variant's unlock at 3).
        gift_thread = Thread.objects.get(
            owner=self.sheet,
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
        )
        gift_thread.level = 1
        gift_thread.save(update_fields=["level"])

        # Signature at level 2 (also below 3 on its own).
        Thread.objects.create(
            owner=self.sheet,
            resonance=self.resonance_a,
            target_kind=TargetKind.TECHNIQUE,
            target_technique=self.technique,
            level=2,
        )
        self.sheet.character.threads.invalidate()

        # Cumulative level (1 + 2 = 3) crosses the threshold.
        resolved = resolve_specialized_variant(
            entity=self.technique, character=self.sheet.character
        )
        self.assertEqual(resolved.name, "Celestial Flame Bolt")
        self.assertEqual(resolved.intensity, self.technique.intensity + 5)
        self.assertEqual(resolved.control, self.technique.control + 2)

    def test_discordant_signature_resolves_variant_on_signature_resonance(self) -> None:
        """A discordant signature matches the variant on the signature's resonance."""
        # Set the gift thread to level 3 (would unlock variant_a on resonance_a).
        gift_thread = Thread.objects.get(
            owner=self.sheet,
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
        )
        gift_thread.level = 3
        gift_thread.save(update_fields=["level"])

        # Discordant signature at resonance_b, level 0 (latent). Effective level
        # for variant matching = gift(3) + sig(0) = 3, which crosses variant_b's
        # unlock_thread_level=3 on resonance_b.
        Thread.objects.create(
            owner=self.sheet,
            resonance=self.resonance_b,
            target_kind=TargetKind.TECHNIQUE,
            target_technique=self.technique,
            level=0,
        )
        self.sheet.character.threads.invalidate()

        resolved = resolve_specialized_variant(
            entity=self.technique, character=self.sheet.character
        )
        # Should resolve to the variant on resonance_b, NOT resonance_a.
        self.assertEqual(resolved.name, "Shadow Flame Bolt")
        self.assertEqual(resolved.intensity, self.technique.intensity + 3)
        self.assertEqual(resolved.control, self.technique.control + 4)

    def test_no_variant_matched_on_signature_resonance(self) -> None:
        """When the signature's resonance has no matching variant, returns parent."""
        # Use a resonance that has no variant.
        resonance_c = ResonanceFactory(name="Void")
        self.gift.resonances.add(resonance_c)

        Thread.objects.create(
            owner=self.sheet,
            resonance=resonance_c,
            target_kind=TargetKind.TECHNIQUE,
            target_technique=self.technique,
            level=10,
        )
        self.sheet.character.threads.invalidate()

        resolved = resolve_specialized_variant(
            entity=self.technique, character=self.sheet.character
        )
        # No variant on resonance_c → parent technique unchanged (wrapped, no variant).
        self.assertEqual(resolved.name, self.technique.name)
        self.assertEqual(resolved.intensity, self.technique.intensity)

    def test_gift_resonances_for_unchanged_by_signature(self) -> None:
        """gift_resonances_for still returns the gift's resonance (gift-scoped).

        The signature override only happens through cast_resonances_for, which
        is the per-technique seam. gift_resonances_for is gift-scoped and must
        NOT be affected by a signature thread on one technique.
        """
        Thread.objects.create(
            owner=self.sheet,
            resonance=self.resonance_b,
            target_kind=TargetKind.TECHNIQUE,
            target_technique=self.technique,
            level=0,
        )
        self.sheet.character.threads.invalidate()

        # gift_resonances_for still returns the gift thread's resonance (A),
        # NOT the signature's (B).
        gift_resonances = gift_resonances_for(self.sheet.character, self.gift)
        self.assertEqual([r.pk for r in gift_resonances], [self.resonance_a.pk])

        # cast_resonances_for returns the signature's resonance (B).
        cast_resonances = cast_resonances_for(self.sheet.character, self.technique)
        self.assertEqual([r.pk for r in cast_resonances], [self.resonance_b.pk])

    def test_weave_thread_rejects_technique_not_owned(self) -> None:
        """weave_thread raises TechniqueNotOwned for a technique the character doesn't know."""
        from world.magic.exceptions import TechniqueNotOwned
        from world.magic.models import ThreadWeavingUnlock
        from world.magic.services.threads import weave_thread

        # Create a technique the character does NOT know.
        unknown_technique = TechniqueFactory(gift=self.gift, name="Unknown Spell")

        # Grant the gift-level weaving unlock so the ownership check is the gate.
        unlock = ThreadWeavingUnlock.objects.create(
            target_kind=TargetKind.TECHNIQUE,
            unlock_gift=self.gift,
            xp_cost=1,
        )
        from world.magic.models import CharacterThreadWeavingUnlock

        CharacterThreadWeavingUnlock.objects.create(
            character=self.sheet,
            unlock=unlock,
            xp_spent=1,
        )

        with self.assertRaises(TechniqueNotOwned):
            weave_thread(
                self.sheet,
                TargetKind.TECHNIQUE,
                unknown_technique,
                self.resonance_a,
            )

    def test_signature_variant_discovery_fires(self) -> None:
        """fire_variant_discoveries handles TargetKind.TECHNIQUE (#1582).

        When a signature thread's level crosses a variant's unlock threshold,
        the discovery beat should fire (achievement + codex), just like GIFT
        threads. The signature variant is matched on the signature's resonance.
        """
        from world.covenants.discovery import fire_variant_discoveries

        Thread.objects.create(
            owner=self.sheet,
            resonance=self.resonance_b,
            target_kind=TargetKind.TECHNIQUE,
            target_technique=self.technique,
            level=0,
        )
        self.sheet.character.threads.invalidate()

        # Advance from 0 to 3, crossing variant_b's unlock_thread_level=3.
        sig = Thread.objects.get(
            owner=self.sheet,
            target_kind=TargetKind.TECHNIQUE,
            target_technique=self.technique,
        )
        sig.level = 3
        sig.save(update_fields=["level"])

        fire_variant_discoveries(thread=sig, starting_level=0, new_level=3)

        # The discovery beat should have granted the achievement for variant_b.
        self.assertTrue(
            CharacterAchievement.objects.filter(
                character_sheet=self.sheet,
                achievement=self.achievement_b,
            ).exists()
        )

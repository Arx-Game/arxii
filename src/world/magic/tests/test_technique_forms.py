"""The per-caster form list (#2901).

#2898 proved every surface shows *what a technique does*. This proves the two
per-character surfaces also show *which forms of it this caster can work* —
base, each unlocked variant, and one step ahead.

The regression this file exists to prevent is the silent one: a variant with its
own payload summarising as the base form under the variant's name, because
``_ResolvedTechnique`` exposed ``damage_profiles`` while the summariser reads
``cached_damage_profiles`` and ``__getattr__`` forwarded that to the parent.
"""

from typing import ClassVar

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import CharacterSheet
from world.conditions.factories import ConditionTemplateFactory, DamageTypeFactory
from world.magic.constants import TargetKind
from world.magic.factories import (
    BinaryEffectTypeFactory,
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
)
from world.magic.models import Gift, Resonance, Technique, Thread
from world.magic.services.technique_effects import invalidate_variant_payload_caches
from world.magic.services.technique_forms import available_technique_forms
from world.magic.specialization.models import (
    TechniqueVariant,
    TechniqueVariantDamageProfile,
)
from world.magic.specialization.services import (
    _ResolvedTechnique,
    provision_latent_gift_thread,
)


class ResolvedTechniquePayloadAliasTest(TestCase):
    """``summarize_technique_effects`` must read the *variant's* payload."""

    technique: ClassVar[Technique]
    variant: ClassVar[TechniqueVariant]

    @classmethod
    def setUpTestData(cls) -> None:
        gift = GiftFactory()
        cls.technique = TechniqueFactory(
            gift=gift, effect_type=BinaryEffectTypeFactory(), damage_profile=False
        )
        cls.variant = TechniqueVariant.objects.create(
            parent_technique=cls.technique,
            resonance=ResonanceFactory(),
            unlock_thread_level=3,
            name_override="Ashfall Form",
        )
        TechniqueVariantDamageProfile.objects.create(
            variant=cls.variant,
            damage_type=DamageTypeFactory(name="cinder"),
            base_damage=11,
            minimum_success_level=1,
        )

    def test_variant_summary_reads_variant_damage_not_parent(self) -> None:
        """The variant's own damage rows reach the summary.

        Before the ``cached_*`` aliases this returned the parent's damage
        silently, so a variant that swapped its payload was displayed as the
        base form under the variant's name and nothing failed.
        """
        summary = self.variant.cached_effect_summary
        self.assertEqual(
            [row["damage_type"] for row in summary["damage"]],
            ["cinder"],
        )
        self.assertNotEqual(summary["damage"], self.technique.cached_effect_summary["damage"])
        self.assertIn("cinder damage", summary["summary"])

    def test_resolved_technique_aliases_agree_with_bare_accessors(self) -> None:
        """``cached_x`` and ``x`` must never disagree on a resolved form."""
        resolved = _ResolvedTechnique(self.technique, variant=self.variant)
        self.assertEqual(resolved.cached_damage_profiles, resolved.damage_profiles)
        self.assertEqual(resolved.cached_capability_grants, resolved.capability_grants)
        self.assertEqual(resolved.cached_condition_applications, resolved.condition_applications)

    def test_removed_conditions_always_come_from_the_parent(self) -> None:
        """No ``TechniqueVariantRemovedCondition`` model exists, so dispel is parent-only."""
        resolved = _ResolvedTechnique(self.technique, variant=self.variant)
        self.assertEqual(
            resolved.cached_removed_conditions,
            self.technique.cached_removed_conditions,
        )


class AvailableTechniqueFormsTest(TestCase):
    """What the sheet and the cast list read."""

    sheet: ClassVar[CharacterSheet]
    gift: ClassVar[Gift]
    resonance: ClassVar[Resonance]
    other_resonance: ClassVar[Resonance]
    technique: ClassVar[Technique]
    variant: ClassVar[TechniqueVariant]

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.gift = GiftFactory()
        cls.resonance = ResonanceFactory(name="Cinder")
        cls.other_resonance = ResonanceFactory(name="Tide")
        cls.gift.resonances.add(cls.resonance, cls.other_resonance)
        cls.technique = TechniqueFactory(
            gift=cls.gift, effect_type=BinaryEffectTypeFactory(), damage_profile=False
        )
        cls.variant = TechniqueVariant.objects.create(
            parent_technique=cls.technique,
            resonance=cls.resonance,
            unlock_thread_level=3,
            name_override="Ashfall Lash",
            intensity_delta=2,
            control_delta=-1,
        )

    def _thread_at(self, level: int, resonance: Resonance | None = None) -> Thread:
        provision_latent_gift_thread(self.sheet, self.gift, resonance=resonance or self.resonance)
        thread = Thread.objects.get(
            owner=self.sheet,
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
            resonance=resonance or self.resonance,
        )
        thread.level = level
        thread.save(update_fields=["level"])
        self.sheet.character.threads.invalidate()
        return thread

    def test_no_thread_yields_base_form_only(self) -> None:
        forms = available_technique_forms(self.sheet.character, self.technique)
        self.assertEqual(len(forms), 1)
        self.assertIsNone(forms[0]["variant_id"])
        self.assertTrue(forms[0]["is_default"])
        self.assertFalse(forms[0]["is_locked"])

    def test_below_unlock_shows_base_default_and_the_next_form_locked(self) -> None:
        """The deepening reads as a goal, one step ahead."""
        self._thread_at(1)
        forms = available_technique_forms(self.sheet.character, self.technique)

        base, locked = forms
        self.assertIsNone(base["variant_id"])
        self.assertTrue(base["is_default"])

        self.assertEqual(locked["variant_id"], self.variant.pk)
        self.assertTrue(locked["is_locked"])
        self.assertFalse(locked["is_default"])
        self.assertEqual(locked["unlock_thread_level"], 3)
        self.assertEqual(locked["thread_level"], 1)
        self.assertEqual(locked["resonance_name"], "Cinder")

    def test_at_unlock_the_variant_becomes_default_and_base_stays_available(self) -> None:
        """A variant does not replace the technique; it adds a form."""
        self._thread_at(3)
        forms = available_technique_forms(self.sheet.character, self.technique)

        self.assertEqual(len(forms), 2)
        base, unlocked = forms
        self.assertIsNone(base["variant_id"])
        self.assertFalse(base["is_default"])
        self.assertFalse(base["is_locked"])

        self.assertEqual(unlocked["variant_id"], self.variant.pk)
        self.assertTrue(unlocked["is_default"])
        self.assertFalse(unlocked["is_locked"])
        self.assertEqual(unlocked["name"], "Ashfall Lash")
        self.assertEqual(unlocked["intensity"], self.technique.intensity + 2)
        self.assertEqual(unlocked["control"], self.technique.control - 1)

    def test_exactly_one_form_is_default(self) -> None:
        self._thread_at(3)
        forms = available_technique_forms(self.sheet.character, self.technique)
        self.assertEqual(sum(1 for f in forms if f["is_default"]), 1)

    def test_higher_tier_shadows_the_lower_rather_than_listing_both(self) -> None:
        """``matching_variant`` picks the highest qualifying tier per resonance."""
        deeper = TechniqueVariant.objects.create(
            parent_technique=self.technique,
            resonance=self.resonance,
            unlock_thread_level=6,
            name_override="Cinderfall Rite",
        )
        self.technique.__dict__.pop("cached_variants", None)
        self._thread_at(6)

        forms = available_technique_forms(self.sheet.character, self.technique)
        variant_ids = [f["variant_id"] for f in forms if f["variant_id"] is not None]
        self.assertEqual(variant_ids, [deeper.pk])

    def test_multi_resonance_caster_gets_one_form_per_thread(self) -> None:
        """#1619: a second thread at another resonance adds its own form."""
        tide_variant = TechniqueVariant.objects.create(
            parent_technique=self.technique,
            resonance=self.other_resonance,
            unlock_thread_level=3,
            name_override="Tidewrack Lash",
        )
        self.technique.__dict__.pop("cached_variants", None)
        self._thread_at(3)
        self._thread_at(3, resonance=self.other_resonance)

        forms = available_technique_forms(self.sheet.character, self.technique)
        names = {f["name"] for f in forms}
        self.assertIn("Ashfall Lash", names)
        self.assertIn("Tidewrack Lash", names)
        self.assertIn(tide_variant.pk, {f["variant_id"] for f in forms})
        self.assertEqual(sum(1 for f in forms if f["is_default"]), 1)

    def test_each_form_carries_its_own_effect_summary(self) -> None:
        """The block #2898 built, per form rather than per technique."""
        self._thread_at(3)
        forms = available_technique_forms(self.sheet.character, self.technique)
        for form in forms:
            self.assertIn("summary", form["effect_summary"])
            self.assertIn("applies", form["effect_summary"])

    def test_variant_payload_reaches_the_form_summary(self) -> None:
        """End-to-end guard on the alias fix, through the display service."""
        condition = ConditionTemplateFactory(name="Scorched")
        self.variant.condition_applications.create(condition=condition, target_kind="enemy")
        invalidate_variant_payload_caches(self.variant)
        self._thread_at(3)

        forms = available_technique_forms(self.sheet.character, self.technique)
        unlocked = next(f for f in forms if f["variant_id"] == self.variant.pk)
        self.assertIn("Scorched", [row["name"] for row in unlocked["effect_summary"]["applies"]])

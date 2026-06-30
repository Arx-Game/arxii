"""Variant cast must never cost more anima than the base form — strict bonus (#1581, Task 7).

A TechniqueVariant with a pure intensity bump (intensity_delta > 0, control_delta = 0)
raises the variant's runtime intensity.  Because the anima cost formula is:

    effective_cost = max(base_cost - (control - intensity), 0)

a higher intensity with the same control normally raises the effective cost.  The
strict-bonus rule says the variant MUST clamp to the base-form cost — more power,
never more anima.

Test seam: ``use_technique`` (the real cast orchestrator) — mirrors the setup in
``test_use_technique_control_penalty.py``.  Two casters are built: one whose GIFT
thread is at level 0 (base form) and one whose GIFT thread is at level 3 (variant
resolved).  The variant caster's anima deduction must be ≤ the base caster's.
"""

from types import SimpleNamespace

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import TargetKind
from world.magic.factories import (
    CharacterAnimaFactory,
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
    TechniqueVariantFactory,
)
from world.magic.services import use_technique
from world.magic.services.techniques import get_runtime_technique_stats
from world.magic.specialization.services import provision_latent_gift_thread
from world.mechanics.factories import CharacterEngagementFactory


def _noop_resolve(
    *, power: int, ledger: object = None, extra_modifiers: int = 0
) -> SimpleNamespace:
    return SimpleNamespace(check_result=None)


class VariantStrictBonusCostTests(TestCase):
    """A gift-technique variant with a pure intensity bump must not raise anima cost.

    Setup:
    - Technique: intensity=10, control=10, anima_cost=5
    - Variant: intensity_delta=5, control_delta=0 (pure intensity bump)
    - Base-form effective_cost = max(5 − (10 − 10), 0) = 5
    - Variant effective_cost = max(5 − (10 − 15), 0) = 10  (before clamp)
    - After #1581 fix: variant cost must be clamped to 5 (= base form cost).
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.gift = GiftFactory()
        cls.resonance = ResonanceFactory()
        cls.gift.resonances.add(cls.resonance)
        # Tune so the math is predictable with no identity/process modifiers:
        # base_cost = max(5 − (10 − 10), 0) = 5
        cls.technique = TechniqueFactory(gift=cls.gift, intensity=10, control=10, anima_cost=5)
        # intensity_delta=5 → variant effective_cost = max(5 − (10 − 15), 0) = 10 (pre-fix)
        cls.variant = TechniqueVariantFactory(
            parent_technique=cls.technique,
            resonance=cls.resonance,
            unlock_thread_level=3,
            intensity_delta=5,
            control_delta=0,
        )

    def _make_caster(self, *, with_variant: bool) -> tuple:
        """Return (character, anima) with or without the GIFT thread at level 3."""
        sheet = CharacterSheetFactory()
        anima = CharacterAnimaFactory(character=sheet.character, current=50, maximum=50)
        CharacterEngagementFactory(character=sheet.character)
        if with_variant:
            provision_latent_gift_thread(sheet, self.gift, resonance=self.resonance)
            thread = next(
                t for t in sheet.character.threads.all() if t.target_kind == TargetKind.GIFT
            )
            thread.level = 3
            thread.save()
            sheet.character.threads.invalidate()
        return sheet.character, anima

    def test_variant_cast_never_costs_more_anima_than_base(self) -> None:
        """Variant cast (intensity +5) must deduct ≤ anima than base form cast."""
        # Base cast — no GIFT thread → base technique, no variant resolved
        base_char, base_anima = self._make_caster(with_variant=False)
        use_technique(
            character=base_char,
            technique=self.technique,
            resolve_fn=_noop_resolve,
        )
        base_anima.refresh_from_db()
        base_deducted = 50 - base_anima.current

        # Variant cast — GIFT thread at level 3 → intensity_delta=5 applied
        variant_char, variant_anima = self._make_caster(with_variant=True)
        use_technique(
            character=variant_char,
            technique=self.technique,
            resolve_fn=_noop_resolve,
        )
        variant_anima.refresh_from_db()
        variant_deducted = 50 - variant_anima.current

        self.assertLessEqual(
            variant_deducted,
            base_deducted,
            msg=(
                f"variant cast deducted {variant_deducted} anima but base form only costs "
                f"{base_deducted}: a variant must never cost more anima than the base "
                f"form (#1581 strict bonus)"
            ),
        )

    def test_variant_runtime_intensity_remains_higher_than_base(self) -> None:
        """After clamping cost, variant power (intensity) must still be higher than base."""
        base_char, _ = self._make_caster(with_variant=False)
        base_stats = get_runtime_technique_stats(self.technique, base_char)

        variant_char, _ = self._make_caster(with_variant=True)
        variant_stats = get_runtime_technique_stats(self.technique, variant_char)

        self.assertGreater(
            variant_stats.intensity,
            base_stats.intensity,
            msg=(
                f"variant runtime intensity ({variant_stats.intensity}) should be "
                f"greater than base ({base_stats.intensity}) — power must still apply"
            ),
        )

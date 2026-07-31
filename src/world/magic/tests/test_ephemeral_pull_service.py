"""Tests for the apply_ephemeral_pull_capability_grants service (#2840)."""

from django.test import TestCase, override_settings

from world.conditions.factories import CapabilityTypeFactory
from world.magic.constants import EffectKind
from world.magic.factories import (
    CharacterResonanceFactory,
    ResonanceFactory,
    ThreadFactory,
    ThreadPullEffectFactory,
)
from world.magic.models import EphemeralPullCapabilityGrant
from world.magic.services.ephemeral_pull import apply_ephemeral_pull_capability_grants
from world.magic.services.resonance import resolve_pull_effects


class ApplyEphemeralPullCapabilityGrantsTest(TestCase):
    """Tests for the apply_ephemeral_pull_capability_grants service."""

    def _setup(self, level=10):
        from world.character_sheets.factories import CharacterSheetFactory

        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=sheet,
            resonance=resonance,
            balance=10,
            lifetime_earned=10,
        )
        cap = CapabilityTypeFactory()
        thread = ThreadFactory(owner=sheet, resonance=resonance, level=level)
        ThreadPullEffectFactory(
            target_kind=thread.target_kind,
            resonance=resonance,
            tier=0,
            min_thread_level=0,
            effect_kind=EffectKind.CAPABILITY_GRANT,
            flat_bonus_amount=None,
            capability_grant=cap,
            capability_grant_value=1,
        )
        return sheet, thread, cap, resonance

    @override_settings(SEED_SAMPLE_CONTENT=True)
    def test_applies_condition_and_sidecar(self):
        """A CAPABILITY_GRANT effect creates a condition + sidecar row."""
        sheet, thread, cap, _resonance = self._setup()
        resolved = resolve_pull_effects([thread], tier=1, in_combat=False, character_sheet=sheet)
        cap_effects = [r for r in resolved if r.kind == EffectKind.CAPABILITY_GRANT]
        self.assertTrue(len(cap_effects) > 0)

        instance = apply_ephemeral_pull_capability_grants(sheet, resolved)
        self.assertIsNotNone(instance)

        grants = EphemeralPullCapabilityGrant.objects.filter(character_sheet=sheet)
        self.assertEqual(grants.count(), 1)
        self.assertEqual(grants[0].capability, cap)
        self.assertEqual(grants[0].character_sheet, sheet)
        self.assertGreater(grants[0].grant_value, 0)

    @override_settings(SEED_SAMPLE_CONTENT=True)
    def test_no_capability_grant_effects_returns_none(self):
        """When resolved has no CAPABILITY_GRANT effects, no condition is applied."""
        from world.character_sheets.factories import CharacterSheetFactory

        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=sheet,
            resonance=resonance,
            balance=10,
            lifetime_earned=10,
        )
        thread = ThreadFactory(owner=sheet, resonance=resonance, level=10)
        ThreadPullEffectFactory(
            target_kind=thread.target_kind,
            resonance=resonance,
            tier=1,
            flat_bonus_amount=3,
        )
        resolved = resolve_pull_effects([thread], tier=1, in_combat=False, character_sheet=sheet)

        instance = apply_ephemeral_pull_capability_grants(sheet, resolved)
        self.assertIsNone(instance)
        self.assertEqual(
            EphemeralPullCapabilityGrant.objects.filter(character_sheet=sheet).count(), 0
        )

    @override_settings(SEED_SAMPLE_CONTENT=True)
    def test_upsert_with_max_on_second_pull(self):
        """A second pull for the same capability updates to MAX, not sum."""
        sheet, thread, cap, _resonance = self._setup()
        resolved = resolve_pull_effects([thread], tier=1, in_combat=False, character_sheet=sheet)
        instance = apply_ephemeral_pull_capability_grants(sheet, resolved)
        self.assertIsNotNone(instance)

        first_value = EphemeralPullCapabilityGrant.objects.get(
            condition_instance=instance, capability=cap
        ).grant_value

        # Second pull with same effects — should upsert to MAX
        resolved2 = resolve_pull_effects([thread], tier=1, in_combat=False, character_sheet=sheet)
        instance2 = apply_ephemeral_pull_capability_grants(sheet, resolved2)
        self.assertEqual(instance2.pk, instance.pk)

        grants = EphemeralPullCapabilityGrant.objects.filter(
            condition_instance=instance, capability=cap
        )
        self.assertEqual(grants.count(), 1)
        self.assertEqual(grants[0].grant_value, first_value)

    @override_settings(SEED_SAMPLE_CONTENT=True)
    def test_sidecar_removed_when_condition_removed(self):
        """Removing the Thread Surge condition CASCADE-deletes sidecar rows."""
        sheet, thread, _cap, _resonance = self._setup()
        resolved = resolve_pull_effects([thread], tier=1, in_combat=False, character_sheet=sheet)
        instance = apply_ephemeral_pull_capability_grants(sheet, resolved)
        self.assertIsNotNone(instance)

        self.assertEqual(
            EphemeralPullCapabilityGrant.objects.filter(character_sheet=sheet).count(), 1
        )
        instance.delete()
        self.assertEqual(
            EphemeralPullCapabilityGrant.objects.filter(character_sheet=sheet).count(), 0
        )

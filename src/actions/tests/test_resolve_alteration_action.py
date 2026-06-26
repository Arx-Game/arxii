"""Tests for ResolveAlterationAction."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from actions.definitions.alterations import ResolveAlterationAction
from world.conditions.factories import ConditionTemplateFactory, DamageTypeFactory
from world.magic.constants import (
    MIN_ALTERATION_DESCRIPTION_LENGTH,
    AlterationTier,
    PendingAlterationStatus,
)
from world.magic.factories import (
    AffinityFactory,
    MagicalAlterationTemplateFactory,
    PendingAlterationFactory,
    ResonanceFactory,
)
from world.magic.services import staff_clear_alteration
from world.magic.types import AlterationResolutionError


class ResolveAlterationActionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = PendingAlterationFactory().character
        cls.character = cls.sheet.character
        cls.affinity = AffinityFactory()
        cls.resonance = ResonanceFactory(affinity=cls.affinity)

    def _open_pending(self, tier: int = AlterationTier.MARKED):
        return PendingAlterationFactory(
            character=self.sheet,
            tier=tier,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            status=PendingAlterationStatus.OPEN,
        )

    def _library_template(self, pending):
        return MagicalAlterationTemplateFactory(
            condition_template=ConditionTemplateFactory(
                name="Library Scar",
                player_description="Player sees this.",
                observer_description="Observer sees this.",
            ),
            tier=pending.tier,
            origin_affinity=pending.origin_affinity,
            origin_resonance=pending.origin_resonance,
            is_library_entry=True,
        )

    def test_library_path_success(self):
        pending = self._open_pending()
        library_template = self._library_template(pending)

        result = ResolveAlterationAction().run(
            actor=self.character,
            pending_id=pending.pk,
            library_template_id=library_template.pk,
        )

        self.assertTrue(result.success, result.message)
        self.assertIn("Library Scar", result.message or "")
        self.assertEqual(result.data["status"], "RESOLVED")
        self.assertIsNotNone(result.data["event_id"])

        pending.refresh_from_db()
        self.assertEqual(pending.status, PendingAlterationStatus.RESOLVED)
        self.assertEqual(pending.resolved_alteration, library_template)

    def test_scratch_path_success(self):
        pending = self._open_pending()
        damage_type = DamageTypeFactory()
        desc = "A" * MIN_ALTERATION_DESCRIPTION_LENGTH

        result = ResolveAlterationAction().run(
            actor=self.character,
            pending_id=pending.pk,
            name="Custom Scar",
            player_description=desc,
            observer_description=desc,
            weakness_damage_type=damage_type,
            weakness_magnitude=1,
            resonance_bonus_magnitude=1,
            social_reactivity_magnitude=0,
            is_visible_at_rest=False,
        )

        self.assertTrue(result.success, result.message)
        self.assertIn("Custom Scar", result.message or "")
        self.assertEqual(result.data["status"], "RESOLVED")
        self.assertIsNotNone(result.data["event_id"])

        pending.refresh_from_db()
        self.assertEqual(pending.status, PendingAlterationStatus.RESOLVED)
        self.assertIsNotNone(pending.resolved_alteration)
        self.assertEqual(
            pending.resolved_alteration.condition_template.name,
            "Custom Scar",
        )

    def test_rejects_non_owner(self):
        other_pending = PendingAlterationFactory(
            tier=AlterationTier.MARKED,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            status=PendingAlterationStatus.OPEN,
        )
        library_template = self._library_template(other_pending)

        result = ResolveAlterationAction().run(
            actor=self.character,
            pending_id=other_pending.pk,
            library_template_id=library_template.pk,
        )

        self.assertFalse(result.success)
        self.assertIn("no open pending alteration", result.message or "")

    def test_rejects_non_open_pending(self):
        pending = self._open_pending()
        staff_clear_alteration(pending=pending, staff_account=None)

        result = ResolveAlterationAction().run(
            actor=self.character,
            pending_id=pending.pk,
            library_template_id=self._library_template(pending).pk,
        )

        self.assertFalse(result.success)
        self.assertIn("no open pending alteration", result.message or "")

    def test_library_validation_failure_mismatch_tier(self):
        pending = self._open_pending(tier=AlterationTier.MARKED)
        wrong_tier_template = MagicalAlterationTemplateFactory(
            condition_template=ConditionTemplateFactory(
                name="Wrong Tier",
                player_description="Player sees this.",
                observer_description="Observer sees this.",
            ),
            tier=AlterationTier.TOUCHED,
            origin_affinity=pending.origin_affinity,
            origin_resonance=pending.origin_resonance,
            is_library_entry=True,
        )

        result = ResolveAlterationAction().run(
            actor=self.character,
            pending_id=pending.pk,
            library_template_id=wrong_tier_template.pk,
        )

        self.assertFalse(result.success)
        self.assertIn("does not match pending tier", result.message or "")

    def test_scratch_validation_failure_missing_description(self):
        pending = self._open_pending()

        result = ResolveAlterationAction().run(
            actor=self.character,
            pending_id=pending.pk,
            name="Short",
            player_description="too short",
            observer_description="too short",
        )

        self.assertFalse(result.success)
        self.assertIn("player_description must be at least", result.message or "")
        self.assertIn("observer_description must be at least", result.message or "")

    def test_rejects_non_int_library_template_id(self):
        pending = self._open_pending()

        result = ResolveAlterationAction().run(
            actor=self.character,
            pending_id=pending.pk,
            library_template_id="not-an-int",
        )

        self.assertFalse(result.success)
        self.assertIn("library entry is required", result.message or "")

    def test_handles_alteration_resolution_error(self):
        pending = self._open_pending()
        library_template = self._library_template(pending)

        with patch("world.magic.services.resolve_pending_alteration") as mock_resolve:
            mock_resolve.side_effect = AlterationResolutionError("Already resolved.")
            result = ResolveAlterationAction().run(
                actor=self.character,
                pending_id=pending.pk,
                library_template_id=library_template.pk,
            )

        self.assertFalse(result.success)
        self.assertIn("could not be applied", result.message or "")
        mock_resolve.assert_called_once()

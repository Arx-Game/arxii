"""Tests for the captured_alive outcome in the abandonment_enemy pool (Task 6, #1479).

Covers:
- abandonment_enemy pool contains a captured_alive entry with weight_override=2.
- pvp and environmental pools do NOT contain a captured_alive entry.
- The ConsequenceEffect for captured_alive has effect_type=CAPTURE and
  capture_offscreen_loss_allowed=False (the safe default — #931 gates further loss).
- Applying the effect on a character with a CharacterSheet creates a HELD
  Captivity row for that sheet.

SQLite-compatible: capture_character uses no DISTINCT ON or PostgreSQL-specific
features. ObjectDB fixtures in setUp to avoid the DbHolder trap (MEMORY.md).
"""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.captivity.constants import CaptivityStatus
from world.captivity.models import Captivity
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.types import LifecycleState
from world.checks.constants import EffectType
from world.checks.types import ResolutionContext
from world.mechanics.effect_handlers import apply_effect
from world.vitals.factories import create_abandonment_pools


class CapturedAlivePoolEntryTests(TestCase):
    """abandonment_enemy contains captured_alive; pvp/environmental do not."""

    def setUp(self) -> None:
        self.pools = create_abandonment_pools()

    def test_enemy_pool_contains_captured_alive(self) -> None:
        """abandonment_enemy must have a captured_alive ConsequencePoolEntry."""
        enemy_pool = self.pools["abandonment_enemy"]
        labels = list(
            enemy_pool.entries.select_related("consequence").values_list(
                "consequence__label", flat=True
            )
        )
        self.assertIn("captured_alive", labels)

    def test_captured_alive_weight_override_is_2(self) -> None:
        """The captured_alive entry in abandonment_enemy uses weight_override=2."""
        enemy_pool = self.pools["abandonment_enemy"]
        entry = enemy_pool.entries.select_related("consequence").get(
            consequence__label="captured_alive"
        )
        self.assertEqual(entry.weight_override, 2)

    def test_captured_alive_is_not_character_loss(self) -> None:
        """captured_alive is a survival outcome — character_loss must be False."""
        enemy_pool = self.pools["abandonment_enemy"]
        entry = enemy_pool.entries.select_related("consequence").get(
            consequence__label="captured_alive"
        )
        self.assertFalse(entry.consequence.character_loss)

    def test_pvp_pool_does_not_contain_captured_alive(self) -> None:
        """abandonment_pvp has no captured_alive entry — no NPC captor."""
        pvp_pool = self.pools["abandonment_pvp"]
        labels = list(
            pvp_pool.entries.select_related("consequence").values_list(
                "consequence__label", flat=True
            )
        )
        self.assertNotIn("captured_alive", labels)

    def test_environmental_pool_does_not_contain_captured_alive(self) -> None:
        """abandonment_environmental has no captured_alive entry — no NPC captor."""
        env_pool = self.pools["abandonment_environmental"]
        labels = list(
            env_pool.entries.select_related("consequence").values_list(
                "consequence__label", flat=True
            )
        )
        self.assertNotIn("captured_alive", labels)

    def test_idempotent_does_not_duplicate_captured_alive(self) -> None:
        """Calling create_abandonment_pools twice does not duplicate the entry."""
        create_abandonment_pools()
        enemy_pool = self.pools["abandonment_enemy"]
        count = enemy_pool.entries.filter(consequence__label="captured_alive").count()
        self.assertEqual(count, 1)


class CapturedAliveEffectTests(TestCase):
    """The ConsequenceEffect for captured_alive is a CAPTURE effect."""

    def setUp(self) -> None:
        self.pools = create_abandonment_pools()

    def _get_captured_alive_consequence(self):
        enemy_pool = self.pools["abandonment_enemy"]
        return (
            enemy_pool.entries.select_related("consequence")
            .get(consequence__label="captured_alive")
            .consequence
        )

    def test_effect_type_is_capture(self) -> None:
        """captured_alive consequence has a CAPTURE ConsequenceEffect."""
        consequence = self._get_captured_alive_consequence()
        effects = list(consequence.effects.all())
        self.assertEqual(len(effects), 1)
        self.assertEqual(effects[0].effect_type, EffectType.CAPTURE)

    def test_offscreen_loss_allowed_is_false(self) -> None:
        """The CAPTURE effect is authored with offscreen_loss_allowed=False (safe default)."""
        consequence = self._get_captured_alive_consequence()
        effect = consequence.effects.first()
        self.assertFalse(effect.capture_offscreen_loss_allowed)

    def test_captor_organization_is_none(self) -> None:
        """No specific captor organization is authored on the pool-level effect."""
        consequence = self._get_captured_alive_consequence()
        effect = consequence.effects.first()
        self.assertIsNone(effect.capture_captor_organization)


class CaptureEffectIntegrationTests(TestCase):
    """Applying the captured_alive CAPTURE effect creates a HELD Captivity row."""

    def setUp(self) -> None:
        self.pools = create_abandonment_pools()
        # ObjectDB-backed objects in setUp to avoid the DbHolder trap.
        character = CharacterFactory(db_key="peril_capture_victim")
        self.sheet = CharacterSheetFactory(character=character)
        self.character = character

    def _get_capture_effect(self):
        enemy_pool = self.pools["abandonment_enemy"]
        consequence = (
            enemy_pool.entries.select_related("consequence")
            .get(consequence__label="captured_alive")
            .consequence
        )
        return consequence.effects.get(effect_type=EffectType.CAPTURE)

    def test_applying_capture_effect_creates_held_captivity(self) -> None:
        """apply_effect(CAPTURE, context) creates a HELD Captivity for the victim's sheet."""
        effect = self._get_capture_effect()
        context = ResolutionContext(character=self.character)

        result = apply_effect(effect, context)

        self.assertTrue(result.applied, msg=f"Effect was skipped: {result.skip_reason}")
        captivity = Captivity.objects.get(captive=self.sheet)
        self.assertEqual(captivity.status, CaptivityStatus.HELD)

    def test_captivity_offscreen_loss_flag_matches_effect(self) -> None:
        """The Captivity row inherits offscreen_loss_allowed=False from the effect."""
        effect = self._get_capture_effect()
        context = ResolutionContext(character=self.character)

        apply_effect(effect, context)

        captivity = Captivity.objects.get(captive=self.sheet)
        self.assertFalse(captivity.offscreen_loss_allowed)

    def test_captivity_flips_sheet_lifecycle_to_captured(self) -> None:
        """The sheet's lifecycle_state becomes CAPTURED after capture."""
        effect = self._get_capture_effect()
        context = ResolutionContext(character=self.character)

        apply_effect(effect, context)

        self.sheet.refresh_from_db()
        self.assertEqual(self.sheet.lifecycle_state, LifecycleState.CAPTURED)

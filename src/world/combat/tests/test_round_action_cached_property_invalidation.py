"""related_cache_fields is the PRIMARY invalidation for cached_round_actions —
no direct write-site mutation exists (16 scattered write sites), so this test
proves the fallback mechanism itself, not an optimization on top of it."""

from evennia.utils.test_resources import EvenniaTest

from world.combat.factories import CombatRoundActionFactory
from world.scenes.factories import InteractionFactory


class RoundActionCacheInvalidationTests(EvenniaTest):
    def test_new_round_action_is_visible_on_next_read(self):
        action_interaction = InteractionFactory()
        self.assertEqual(action_interaction.cached_round_actions, [])  # warm, empty
        CombatRoundActionFactory(interaction=action_interaction)
        self.assertEqual(len(action_interaction.cached_round_actions), 1)

    def test_interaction_stamped_after_creation_is_visible_on_next_read(self):
        """Mirrors the real production write pattern (services.py:8326-8328,
        8394-8396): a CombatRoundAction is created unresolved (interaction=None)
        and the FK is stamped onto it LATER via an update_fields save, not at
        creation. That later stamping save is the moment a stale
        cached_round_actions would surface undetected."""
        action_interaction = InteractionFactory()
        self.assertEqual(action_interaction.cached_round_actions, [])  # warm, empty
        action = CombatRoundActionFactory(interaction=None)
        action.interaction = action_interaction
        action.interaction_timestamp = action_interaction.timestamp
        action.save(update_fields=["interaction", "interaction_timestamp"])
        self.assertEqual(len(action_interaction.cached_round_actions), 1)

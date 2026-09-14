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

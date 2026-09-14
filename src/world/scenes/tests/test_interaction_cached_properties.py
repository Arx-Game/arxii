"""Direct-mutation + related_cache_fields regressions for Interaction's 5 satellite caches.

See #3816: the 5 original ``cached_*`` properties on ``Interaction`` used a plain
``@property``/``@x.setter`` pair backed by a mangled ``_cached_x`` attribute. That defeats
Django's own ``Prefetch(to_attr=)`` freshness check (a cold instance never has
``_cached_x`` set, but the property never raises ``AttributeError`` either, so Django's
``hasattr`` probe reports "already populated" and skips the batched query entirely) and
also means any write bypassing a fresh fetch leaves a stale, requery-needed cache.
``PrunedCachedProperty`` (Task 1) fixes the descriptor; this task converts the 5
properties to use it and adds direct write-site mutation so a mutation is reflected in an
already-warmed cache without an extra query.
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.roster.factories import RosterEntryFactory
from world.scenes.factories import (
    InteractionFactory,
    InteractionFavoriteFactory,
    InteractionReactionFactory,
)
from world.scenes.reaction_toggle_services import (
    toggle_interaction_favorite,
    toggle_interaction_reaction,
)


class InteractionCachedPropertyDirectMutationTests(TestCase):
    """The write-site mutation itself: a warmed cache reflects a toggle with no requery."""

    def setUp(self) -> None:
        self.interaction = InteractionFactory()
        self.roster_entry = RosterEntryFactory()
        self.account = AccountFactory()

    def test_favorite_toggle_on_updates_cache_without_requery(self) -> None:
        # Warm the cache first (simulating a page load that hit the Prefetch pipeline).
        self.assertEqual(self.interaction.cached_favorites, [])
        toggle_interaction_favorite(interaction=self.interaction, roster_entry=self.roster_entry)
        # Reading the already-warmed cache again must not issue a fresh query — the
        # toggle mutated the cached list in place instead of leaving it stale.
        with self.assertNumQueries(0):
            self.assertEqual(len(self.interaction.cached_favorites), 1)

    def test_favorite_toggle_off_updates_cache_without_requery(self) -> None:
        toggle_interaction_favorite(interaction=self.interaction, roster_entry=self.roster_entry)
        self.assertEqual(len(self.interaction.cached_favorites), 1)
        toggle_interaction_favorite(interaction=self.interaction, roster_entry=self.roster_entry)
        with self.assertNumQueries(0):
            self.assertEqual(self.interaction.cached_favorites, [])

    def test_reaction_toggle_updates_cache_without_requery(self) -> None:
        self.assertEqual(self.interaction.cached_reactions, [])
        toggle_interaction_reaction(
            interaction=self.interaction, account=self.account, emoji="\U0001f389"
        )
        with self.assertNumQueries(0):
            self.assertEqual(len(self.interaction.cached_reactions), 1)
        toggle_interaction_reaction(
            interaction=self.interaction, account=self.account, emoji="\U0001f389"
        )
        with self.assertNumQueries(0):
            self.assertEqual(self.interaction.cached_reactions, [])


class InteractionCachedPropertyRelatedCacheFieldsTests(TestCase):
    """The safety net: a write that bypasses the service layer still gets cleared.

    ``related_cache_fields``/``RelatedCacheClearingMixin`` fire on ``Model.save()`` —
    a factory-built row (going through ``save()``, unlike the toggle services' raw
    ``.filter().delete()``) clears ``Interaction.cached_favorites``/``cached_reactions``
    so the next read re-queries instead of returning the stale warmed-empty list.
    """

    def setUp(self) -> None:
        self.interaction = InteractionFactory()
        self.roster_entry = RosterEntryFactory()
        self.account = AccountFactory()

    def test_favorite_written_directly_clears_the_warmed_cache(self) -> None:
        self.assertEqual(self.interaction.cached_favorites, [])  # warm the cache
        InteractionFavoriteFactory(interaction=self.interaction, roster_entry=self.roster_entry)
        self.assertEqual(len(self.interaction.cached_favorites), 1)

    def test_reaction_written_directly_clears_the_warmed_cache(self) -> None:
        self.assertEqual(self.interaction.cached_reactions, [])  # warm the cache
        InteractionReactionFactory(interaction=self.interaction, account=self.account)
        self.assertEqual(len(self.interaction.cached_reactions), 1)

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
from world.scenes.constants import InteractionMode
from world.scenes.factories import (
    InteractionFactory,
    InteractionFavoriteFactory,
    InteractionReactionFactory,
    PersonaFactory,
)
from world.scenes.interaction_services import create_interaction, write_target_personas
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

    def test_favorite_toggle_off_leaves_another_roster_entrys_favorite_alone(self) -> None:
        """Exercises the filter predicate: removing one's own favorite must not
        also drop a different roster entry's favorite already in the warmed cache.
        """
        other_entry = RosterEntryFactory()
        toggle_interaction_favorite(interaction=self.interaction, roster_entry=other_entry)
        toggle_interaction_favorite(interaction=self.interaction, roster_entry=self.roster_entry)
        self.assertEqual(len(self.interaction.cached_favorites), 2)

        toggle_interaction_favorite(interaction=self.interaction, roster_entry=self.roster_entry)
        with self.assertNumQueries(0):
            remaining = self.interaction.cached_favorites
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0].roster_entry_id, other_entry.pk)

    def test_reaction_toggle_off_leaves_another_accounts_reaction_alone(self) -> None:
        """Exercises the filter predicate: removing one's own reaction must not
        also drop a different account's reaction already in the warmed cache.
        """
        other_account = AccountFactory()
        toggle_interaction_reaction(
            interaction=self.interaction, account=other_account, emoji="\U0001f389"
        )
        toggle_interaction_reaction(
            interaction=self.interaction, account=self.account, emoji="\U0001f389"
        )
        self.assertEqual(len(self.interaction.cached_reactions), 2)

        toggle_interaction_reaction(
            interaction=self.interaction, account=self.account, emoji="\U0001f389"
        )
        with self.assertNumQueries(0):
            remaining = self.interaction.cached_reactions
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0].account_id, other_account.pk)


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


class BulkCreateWriteSiteCacheTests(TestCase):
    """The 5 bulk_create write sites must not double-count on a cold cache.

    ``bulk_create`` never calls ``Model.save()``, so ``RelatedCacheClearingMixin``
    never fires for these -- but reading the cached list AFTER the bulk_create on
    a cache that has never been read before (the common case: these all populate
    an interaction that was just created moments ago) would find nothing in
    ``instance.__dict__``, re-query the DB (which already includes the rows just
    inserted), and then append them again. Each fix captures the existing list
    BEFORE the write instead.
    """

    def test_write_target_personas_on_a_cold_cache_is_not_doubled(self) -> None:
        interaction = InteractionFactory()
        persona = PersonaFactory()
        # cached_target_personas has never been read on this instance -- cold.
        write_target_personas(interaction, [persona])
        self.assertEqual(
            [p.pk for p in interaction.cached_target_personas],
            [persona.pk],
        )

    def test_write_target_personas_called_twice_accumulates_without_doubling(self) -> None:
        interaction = InteractionFactory()
        first, second = PersonaFactory(), PersonaFactory()
        write_target_personas(interaction, [first])
        write_target_personas(interaction, [second])
        self.assertEqual(
            sorted(p.pk for p in interaction.cached_target_personas),
            sorted([first.pk, second.pk]),
        )

    def test_create_interaction_receivers_are_not_doubled(self) -> None:
        writer_entry = RosterEntryFactory()
        receiver_entry = RosterEntryFactory()
        interaction = create_interaction(
            persona=writer_entry.character_sheet.primary_persona,
            content="a pose",
            mode=InteractionMode.POSE,
            receivers=[receiver_entry.character_sheet.primary_persona],
        )
        self.assertEqual(
            [r.persona_id for r in interaction.cached_receivers],
            [receiver_entry.character_sheet.primary_persona.pk],
        )

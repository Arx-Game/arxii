"""Direct-mutation regression for CharacterSheet.cached_resonances (#3816 Task 3).

``CharacterSheet.cached_resonances`` is fed by the play-reader feed's
``Prefetch("persona__character_sheet__resonances", to_attr="cached_resonances")``
(``world/scenes/interaction_views.py``) but had no model-level cached property backing
it at all -- a page load's warmed cache was never kept in sync with a same-request
resonance grant. Converting it to ``PrunedCachedProperty`` (Task 1) fixes the
Prefetch freshness check; this task also adds direct write-site mutation at the 4
``CharacterResonance.objects.get_or_create()`` call sites so a warmed cache reflects
a grant without a requery.

**The double-count trap (mirrors Task 2's fix, #3816):** ``get_or_create()``'s own
``Model.save()`` (via ``RelatedCacheClearingMixin`` + ``related_cache_fields`` on
``CharacterResonance``) clears ``character_sheet.cached_resonances`` out from under
callers as a side effect of creating the row -- even on a cache that was never read
before this call. Reading ``character_sheet.cached_resonances`` again *after* the
write re-queries the DB (which now already includes the row just created) and then
appending it again duplicates it. Each of the 4 write sites captures the existing
list BEFORE the get_or_create/save instead.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.factories import CharacterDistinctionFactory, DistinctionFactory
from world.magic.constants import GainSource
from world.magic.factories import (
    AffinityFactory,
    CharacterResonanceFactory,
    DistinctionResonanceGrantFactory,
    ResonanceFactory,
)
from world.magic.models import CharacterResonance, ResonanceConversion
from world.magic.services.conversion import convert_resonance
from world.magic.services.distinction_resonance import reconcile_distinction_resonance_grants
from world.magic.services.resonance import grant_resonance


class CharacterResonancesCachedPropertyTests(TestCase):
    """Basic ``cached_resonances`` read behavior."""

    def test_empty_sheet_has_no_cached_resonances(self) -> None:
        sheet = CharacterSheetFactory()
        self.assertEqual(sheet.cached_resonances, [])

    def test_reads_existing_rows(self) -> None:
        sheet = CharacterSheetFactory()
        cr = CharacterResonanceFactory(character_sheet=sheet)
        self.assertEqual([r.pk for r in sheet.cached_resonances], [cr.pk])


class GrantResonanceWarmedCacheTests(TestCase):
    """Direct write-site mutation: a warmed cache reflects grant_resonance with no requery."""

    def test_grant_resonance_updates_warmed_cache_without_requery(self) -> None:
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        # Warm the cache first (simulating a page load that hit the Prefetch pipeline).
        self.assertEqual(sheet.cached_resonances, [])
        grant_resonance(sheet, resonance, 10, source=GainSource.STAFF_GRANT)
        with self.assertNumQueries(0):
            cached = sheet.cached_resonances
        self.assertEqual(len(cached), 1)
        self.assertEqual(cached[0].balance, 10)

    def test_grant_resonance_on_existing_row_leaves_warmed_cache_length_unchanged(self) -> None:
        """No new row is created, so the cache must never grow past 1 entry.

        Unlike the create path, updating an existing row's balance still calls
        ``cr.save()``, which self-heals the cache via ``RelatedCacheClearingMixin``
        (one requery on the next read) rather than being mutated in place -- that
        extra query is an accepted trade-off (ADR-0296), not the doubling bug this
        module guards against.
        """
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=sheet, resonance=resonance, balance=5, lifetime_earned=5
        )
        self.assertEqual(len(sheet.cached_resonances), 1)  # warm
        grant_resonance(sheet, resonance, 3, source=GainSource.STAFF_GRANT)
        cached = sheet.cached_resonances
        self.assertEqual(len(cached), 1)
        self.assertEqual(cached[0].balance, 8)


class CharacterResonanceColdCacheTests(TestCase):
    """The 4 get_or_create write sites must not double-count on a cold cache.

    ``CharacterResonance.objects.get_or_create()``'s own ``Model.save()`` clears
    ``character_sheet.cached_resonances`` (via ``RelatedCacheClearingMixin``) as a
    side effect of creating the row -- but a cache that has never been read before
    this call has nothing to clear either way, so reading it for the first time
    right AFTER the write would still re-query the DB (which already includes the
    row just created) and then append it again, doubling it. Each fix captures the
    existing list BEFORE the write instead.
    """

    def test_grant_resonance_on_a_cold_cache_is_not_doubled(self) -> None:
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        # cached_resonances has never been read on this instance -- cold.
        grant_resonance(sheet, resonance, 10, source=GainSource.STAFF_GRANT)
        cr = CharacterResonance.objects.get(character_sheet=sheet, resonance=resonance)
        self.assertEqual([r.pk for r in sheet.cached_resonances], [cr.pk])

    def test_handler_get_or_create_on_a_cold_cache_is_not_doubled(self) -> None:
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        # cached_resonances has never been read on this instance -- cold.
        cr = sheet.character.resonances.get_or_create(resonance)
        self.assertEqual([r.pk for r in sheet.cached_resonances], [cr.pk])

    def test_reconcile_distinction_resonance_grants_on_a_cold_cache_is_not_doubled(self) -> None:
        sheet = CharacterSheetFactory()
        distinction = DistinctionFactory()
        resonance = ResonanceFactory()
        DistinctionResonanceGrantFactory(
            distinction=distinction, resonance=resonance, flat_amount_per_rank=10
        )
        character_distinction = CharacterDistinctionFactory(
            character=sheet, distinction=distinction, rank=1
        )
        # cached_resonances has never been read on this instance -- cold.
        reconcile_distinction_resonance_grants(character_distinction)
        cr = CharacterResonance.objects.get(character_sheet=sheet, resonance=resonance)
        self.assertEqual([r.pk for r in sheet.cached_resonances], [cr.pk])

    def test_convert_resonance_full_on_a_cold_cache_is_not_doubled(self) -> None:
        celestial = AffinityFactory(name="Celestial")
        primal = AffinityFactory(name="Primal")
        source_resonance = ResonanceFactory(name="Bene", affinity=celestial)
        target_resonance = ResonanceFactory(name="Praedari", affinity=primal)
        ResonanceConversion.objects.get_or_create(
            source_resonance=source_resonance,
            target_affinity="primal",
            defaults={"target_resonance": target_resonance},
        )
        sheet = CharacterSheetFactory()
        source_cr = CharacterResonanceFactory(
            character_sheet=sheet, resonance=source_resonance, balance=10, lifetime_earned=10
        )
        # cached_resonances has never been read on this instance -- cold.
        convert_resonance(
            sheet,
            source_affinity="celestial",
            target_affinity="primal",
            multiplier=Decimal("1.0"),
        )
        target_cr = CharacterResonance.objects.get(
            character_sheet=sheet, resonance=target_resonance
        )
        self.assertEqual(
            sorted(r.pk for r in sheet.cached_resonances),
            sorted([source_cr.pk, target_cr.pk]),
        )

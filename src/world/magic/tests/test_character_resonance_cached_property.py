"""Direct-mutation regression for CharacterSheet.cached_resonances (#3816 Task 3).

``CharacterSheet.cached_resonances`` is fed by the play-reader feed's
``Prefetch("persona__character_sheet__resonances", to_attr="cached_resonances")``
(``world/scenes/interaction_views.py``) but had no model-level cached property backing
it at all -- a page load's warmed cache was never kept in sync with a same-request
resonance grant. Converting it to ``PrunedCachedProperty`` (Task 1) fixes the
Prefetch freshness check; this task also adds direct write-site mutation at four
call sites on the grant path so a warmed cache reflects a grant without a requery:
``CharacterResonanceHandler.get_or_create`` (``handlers.py``), ``grant_resonance``
(``services/resonance.py``), ``reconcile_distinction_resonance_grants``
(``services/distinction_resonance.py``), and ``_convert_full``
(``services/conversion.py``). Every OTHER ``CharacterResonance.objects.get_or_create()``
call site in the app (e.g. ``services/corruption.py``, ``services/soul_tether.py``) is
left untouched and relies on the mixin's fallback invalidation instead (still correct,
just one extra query on the next read) -- these four are the ones worth optimizing
because they sit on the hot grant path.

**The peek-not-read rule.** Reading ``character_sheet.cached_resonances`` to capture
it forces a query whenever the cache is cold -- which, for a resonance grant, is most
of the time (unlike Task 2's interaction relations, a grant isn't usually preceded by
something else that already warmed the sheet's resonance cache in the same request).
So every site below **peeks** at ``character_sheet.__dict__.get("cached_resonances")``
(no query, ``None`` when cold) instead of reading the property, and only performs the
direct-mutation append when something was actually cached -- a cold cache re-queries
correctly on next real access regardless, so there is nothing to lose by skipping the
mutation when cold.

**The double-count trap this still guards against (mirrors Task 2's fix, #3816):**
``get_or_create()``'s own ``Model.save()`` (via ``RelatedCacheClearingMixin`` +
``related_cache_fields`` on ``CharacterResonance``) clears
``character_sheet.cached_resonances`` out from under callers as a side effect of
creating the row. Reading ``character_sheet.cached_resonances`` again *after* the
write (rather than peeking a value captured before it) would re-query the DB (which
now already includes the row just created) and then appending it again would
duplicate it. ``_convert_full`` peeks at the very top of the function, before its own
``cr.save()`` -- the peeked list holds the same idmapper instance as ``cr``, so
zeroing ``cr``'s balance in place is already reflected in the peeked list with no
re-read needed, making that site genuinely free rather than merely no-worse.
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
        extra query is an accepted trade-off (ADR-0298), not the doubling bug this
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
    """The 4 optimized write sites must not double-count on a cold cache, and must
    not force a query to check.

    Peeking ``character_sheet.__dict__.get("cached_resonances")`` (rather than
    reading the property) means a genuinely cold cache is left alone entirely --
    no query, no premature population -- and correctness still holds because the
    next real read of ``cached_resonances`` queries the DB fresh, which by then
    already includes the row the write just created.
    """

    def test_grant_resonance_on_a_cold_cache_does_not_query_or_populate_it(self) -> None:
        """The fix this class exists for: peeking must not force a query.

        Reading (rather than peeking) ``character_sheet.cached_resonances`` before
        the write would force a query on every cold-cache grant -- the common
        case -- defeating the point of a query-reduction fix.
        """
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        self.assertNotIn("cached_resonances", sheet.__dict__)
        grant_resonance(sheet, resonance, 10, source=GainSource.STAFF_GRANT)
        self.assertNotIn("cached_resonances", sheet.__dict__)

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

"""Two facet binds at once on one resonance must stop at the cap of five (#5021).

The cap is a count in ``MotifResonanceLink.clean`` followed by an insert, so two binds
that both count four before either commits would both insert. ``bind_motif_facet`` locks
the character's Motif row first; these tests run two real binds on two real Postgres
connections and hold them at the point between the count and the insert, so the second
bind can only see the first one's row if the lock made it wait.
"""

from __future__ import annotations

import contextlib
import threading
from unittest.mock import patch

from django.db import connection
from django.test import TransactionTestCase, tag

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.exceptions import FacetBindingCapExceeded
from world.magic.factories import (
    CharacterResonanceFactory,
    FacetFactory,
    MotifFactory,
    MotifResonanceAssociationFactory,
    MotifResonanceFactory,
    ResonanceFactory,
)
from world.magic.models import Motif, MotifResonanceAssociation
from world.magic.models.motifs import MotifResonanceLink
from world.magic.services.motif_facet import bind_motif_facet

# How long a bind waits at the count for the other bind to reach it too. With the lock
# in place the other bind is blocked on the Motif row, so this wait runs out once.
_RENDEZVOUS_SECONDS = 2


@tag("postgres")
class ConcurrentFacetBindTests(TransactionTestCase):
    """Four facets are already tied to Moonsilver; two more binds arrive together."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.moonsilver = ResonanceFactory(name="Moonsilver")
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.moonsilver)
        motif = MotifFactory(character=self.sheet)
        self.motif_resonance = MotifResonanceFactory(motif=motif, resonance=self.moonsilver)
        for name in ("Wolf", "Silk", "Scythe", "Red"):
            MotifResonanceAssociationFactory(
                motif_resonance=self.motif_resonance, facet=FacetFactory(name=name)
            )
        self.late_facets = [FacetFactory(name="Moon"), FacetFactory(name="Ash")]

    def _race(self) -> tuple[list[object], list[BaseException]]:
        """Run both binds on their own threads; return (successes, refusals)."""
        rendezvous = threading.Barrier(2)
        original_clean = MotifResonanceLink.clean

        def clean_then_wait(link: MotifResonanceLink) -> None:
            original_clean(link)
            # Both binds have counted and passed; hold here so neither inserts and
            # commits before the other has counted. A broken barrier (the other bind
            # is waiting on the lock, or already refused) lets this one go on.
            with contextlib.suppress(threading.BrokenBarrierError):
                rendezvous.wait(timeout=_RENDEZVOUS_SECONDS)

        successes: list[object] = []
        refusals: list[BaseException] = []
        unexpected: list[BaseException] = []

        def bind(facet) -> None:
            try:
                successes.append(bind_motif_facet(self.sheet, facet, self.moonsilver))
            except FacetBindingCapExceeded as exc:
                refusals.append(exc)
            except BaseException as exc:  # noqa: BLE001 - re-raised on the test thread
                unexpected.append(exc)
            finally:
                connection.close()

        with patch.object(MotifResonanceLink, "clean", clean_then_wait):
            threads = [threading.Thread(target=bind, args=(f,)) for f in self.late_facets]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=30)
        if unexpected:
            raise unexpected[0]
        return successes, refusals

    def _tied(self) -> int:
        return MotifResonanceAssociation.objects.filter(
            motif_resonance=self.motif_resonance
        ).count()

    def test_two_binds_at_once_stop_at_five(self) -> None:
        successes, refusals = self._race()

        self.assertEqual(self._tied(), 5)
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(refusals), 1)

    def test_the_race_is_real_without_the_motif_lock(self) -> None:
        """Control: with the Motif lock taken out, the same race writes a sixth facet.

        Proves the rendezvous really interleaves the two binds, so the test above
        passes because of the lock and not because one bind happened to finish first.
        """
        with patch.object(Motif.objects, "select_for_update", Motif.objects.get_queryset):
            successes, refusals = self._race()

        self.assertEqual(self._tied(), 6)
        self.assertEqual(len(successes), 2)
        self.assertEqual(refusals, [])

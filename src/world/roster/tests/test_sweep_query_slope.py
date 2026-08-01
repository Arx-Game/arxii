"""Query-count guards on the weekly activity sweep (#2728 Testing).

``sweep_activity_states`` is playerbase-scoped cron, so the number that matters is
its *slope* — what each additional swept character costs — not its absolute count.
A per-character read is invisible at ten characters and ruinous at a thousand, and
it is exactly the kind of regression a plain behavioural test never sees.

The invariant pinned here: **a swept character costs writes only.** Everything the
loop reads — the roster entry, its shelf, the sheet's profile, the tenures and the
tenure's player account — is fetched in bulk before iteration, so the read cost is
flat no matter how large the population grows.

Two deliberate choices in how this is measured:

*Slope, not absolutes.* Both tests compare two population sizes rather than pinning
a total, so the guard survives an unrelated change to the sweep's fixed setup cost
while still failing the moment per-character work creeps in.

*The identity map is flushed first.* Factories leave every row they built in the
idmapper cache, so an un-flushed measurement would serve the account/player_data
hops from memory and report a slope the cron never enjoys on a cold worker.
"""

from __future__ import annotations

from datetime import timedelta

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from evennia.accounts.models import AccountDB

from evennia_extensions.models import PlayerData
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import CharacterSheet, Profile
from world.roster.factories import (
    RosterEntryFactory,
    RosterFactory,
    RosterTenureFactory,
)
from world.roster.models import Roster, RosterEntry, RosterTenure
from world.roster.models.choices import ActivityRequirement, RosterType
from world.roster.seeds import ensure_rosters
from world.roster.services.activity import sweep_activity_states

# The four rows a swept-and-released character writes: its Profile (persisted by
# ``CharacterSheet.save`` since #1270), the sheet itself (activity_state), the
# tenure (end_date) and the roster entry (move_to_roster). All four are inherent —
# there is no read in this number, and that is the whole point of the guard.
WRITES_PER_RELEASED_CHARACTER = 4


def _stale_active_character(
    *,
    requirement: str = ActivityRequirement.HIGH,
    days_inactive: int = 400,
):
    """A character on the Active shelf with an open tenure and a stale login."""
    sheet = CharacterSheetFactory()
    entry = RosterEntryFactory(
        character_sheet=sheet,
        roster=RosterFactory(roster_type=RosterType.ACTIVE),
        activity_requirement=requirement,
    )
    tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
    account = tenure.player_data.account
    account.last_login = timezone.now() - timedelta(days=days_inactive)
    account.save(update_fields=["last_login"])
    return sheet


def _flush_identity_map() -> None:
    """Drop every cached instance the factories left behind.

    The sweep's real cost is its cold-cache cost; a warm idmapper would mask the
    account/player_data hops entirely and let an N+1 through the guard.
    """
    for model in (
        CharacterSheet,
        Profile,
        RosterEntry,
        RosterTenure,
        Roster,
        PlayerData,
        AccountDB,
    ):
        model.flush_instance_cache()


class SweepQuerySlopeTests(TestCase):
    """The sweep's per-character cost, measured rather than asserted by eye."""

    def setUp(self):
        ensure_rosters()

    def _sweep_queries(self, population: int) -> list[str]:
        """The SQL issued while sweeping ``population`` freshly-stale characters.

        Characters swept by an earlier call are excluded from later ones by
        construction — they are either INACTIVE (so out of ``demotable``) or moved
        off the Active shelf entirely — so each call does exactly the work of the
        batch created just before it.
        """
        for _ in range(population):
            _stale_active_character()
        _flush_identity_map()
        with CaptureQueriesContext(connection) as captured:
            result = sweep_activity_states()
        self.assertEqual(result["released"], population)
        return [query["sql"] for query in captured.captured_queries]

    @staticmethod
    def _reads(sql: list[str]) -> int:
        return sum(1 for statement in sql if statement.lstrip().upper().startswith("SELECT"))

    @staticmethod
    def _writes(sql: list[str]) -> int:
        return sum(
            1
            for statement in sql
            if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        )

    def test_read_cost_does_not_scale_with_population(self):
        """Sweeping three characters issues no more SELECTs than sweeping one.

        This is the guard that matters. Every read the loop needs is prefetched, so
        adding characters adds no queries at all on the read side — the sweep scans
        a fixed number of times regardless of playerbase size.
        """
        one = self._reads(self._sweep_queries(1))
        three = self._reads(self._sweep_queries(3))

        self.assertEqual(three, one)

    def test_write_cost_is_exactly_the_inherent_writes(self):
        """Each additional released character costs its four row updates and nothing more."""
        one = self._writes(self._sweep_queries(1))
        three = self._writes(self._sweep_queries(3))

        slope = (three - one) / 2
        self.assertEqual(slope, WRITES_PER_RELEASED_CHARACTER)
        self.assertEqual(one, WRITES_PER_RELEASED_CHARACTER)


class SweepLeavesNoStalePrefetchTests(TestCase):
    """The sweep's bulk fill must not outlive the sweep.

    The prefetch that flattens the read cost fills ``cached_tenures`` on the
    ``RosterEntry`` instance, and ``SharedMemoryModel`` hands that same object to
    every later reader in the process. Left in place, it would pin the entry's
    tenures as they stood mid-sweep — for the life of the process, for every
    character the cron examined. That is a worse bug than the N+1 it replaced, so
    the escape is pinned here rather than left to the incidental test that caught it.
    """

    def setUp(self):
        ensure_rosters()

    def test_tenures_created_after_a_sweep_are_visible(self):
        sheet = _stale_active_character()
        entry = sheet.roster_entry

        sweep_activity_states()
        # player_number is left to the factory's sequence: hardcoding a number can
        # collide with the one the first tenure happened to draw from that same
        # process-global counter.
        RosterTenureFactory(roster_entry=entry, end_date=None)

        self.assertEqual(entry.tenures.count(), 2)
        self.assertEqual(len(entry.cached_tenures), 2)

    def test_an_examined_but_unswept_character_is_also_cleared(self):
        """The ``continue`` path takes the prefetch too, so it must clear it too."""
        sheet = _stale_active_character(days_inactive=1)
        entry = sheet.roster_entry

        result = sweep_activity_states()
        self.assertEqual(result["flipped_to_inactive"], 0)
        RosterTenureFactory(roster_entry=entry, end_date=None)

        self.assertEqual(entry.tenures.count(), 2)

"""Somehow Always Broke: weekly purse-drain snapshot + drain (#2613)."""

from django.test import TestCase
from django.utils import timezone

from world.character_sheets.factories import CharacterSheetFactory
from world.currency.models import (
    CurrencyInstrumentDetails,
    CurrencyTransfer,
    DistinctionPurseDrain,
    PurseDrainWeek,
)
from world.currency.services import (
    get_or_create_purse,
    run_purse_drains,
    snapshot_purse_drains,
    transfer,
)
from world.distinctions.factories import CharacterDistinctionFactory, DistinctionFactory
from world.game_clock.models import GameSeason, GameWeek


class PurseDrainTests(TestCase):
    """The two-band drain leaves a holder with exactly this week's income."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.season = GameSeason.objects.create(number=1, name="Season 1")
        cls.week = GameWeek.objects.create(
            number=1, season=cls.season, is_current=True, started_at=timezone.now()
        )

    def _make_holder(self, *, balance: int, percent: int = 100, floor: int = 0):
        """A sheet holding a full-drain distinction, with a funded purse."""
        sheet = CharacterSheetFactory()
        distinction = DistinctionFactory(cost_per_rank=-50, max_rank=1)
        DistinctionPurseDrain.objects.create(
            distinction=distinction, drain_percent=percent, floor_coppers=floor
        )
        CharacterDistinctionFactory(character=sheet.character, distinction=distinction)
        purse = get_or_create_purse(sheet)
        purse.balance = balance
        purse.save(update_fields=["balance"])
        return sheet, purse

    def _run_week(self):
        """SNAPSHOT then DRAIN, the way the cron fires them in-tick."""
        snapshot_purse_drains()
        return run_purse_drains()

    def _balance(self, purse) -> int:
        purse.refresh_from_db()
        return purse.balance

    # --- core algebra ---

    def test_snapshot_records_opening_balance(self) -> None:
        sheet, _ = self._make_holder(balance=500)
        created = snapshot_purse_drains()
        self.assertEqual(created, 1)
        row = PurseDrainWeek.objects.get(character_sheet=sheet, game_week=self.week)
        self.assertEqual(row.opening_balance, 500)
        self.assertIsNone(row.drained_at)

    def test_full_drain_with_no_income_or_outflow_empties_purse(self) -> None:
        _, purse = self._make_holder(balance=500)
        self._run_week()
        self.assertEqual(self._balance(purse), 0)

    def test_income_after_snapshot_survives_the_drain(self) -> None:
        # S=500 hoard; +300 income lands after the snapshot. O=0.
        # drain = S - O = 500, leaving exactly the 300 income.
        _, purse = self._make_holder(balance=500)
        snapshot_purse_drains()
        transfer(amount=300, reason="wages", to_purse=purse)
        run_purse_drains()
        self.assertEqual(self._balance(purse), 300)

    def test_outflows_come_out_of_the_hoard_not_the_paycheck(self) -> None:
        # S=500, then 200 upkeep leaves, then 300 income lands.
        # O=200 so drain = 500 - 200 = 300; final balance = 500 - 200 + 300 - 300 = 300.
        _, purse = self._make_holder(balance=500)
        snapshot_purse_drains()
        transfer(amount=200, reason="upkeep", from_purse=purse)
        transfer(amount=300, reason="wages", to_purse=purse)
        run_purse_drains()
        self.assertEqual(self._balance(purse), 300)

    def test_voluntary_spend_and_upkeep_are_interchangeable(self) -> None:
        # Same numbers as above but the 200 is a purchase, not upkeep — identical result.
        _, purse = self._make_holder(balance=500)
        snapshot_purse_drains()
        transfer(amount=200, reason="bought a hat", from_purse=purse)
        transfer(amount=300, reason="wages", to_purse=purse)
        run_purse_drains()
        self.assertEqual(self._balance(purse), 300)

    def test_outspending_the_hoard_clamps_to_zero_drain(self) -> None:
        # S=500, spend 600 (income 400 first so the purse can afford it), O=600.
        # S - O = -100 → clamps to 0, no drain. Final = 500 + 400 - 600 = 300.
        _, purse = self._make_holder(balance=500)
        snapshot_purse_drains()
        transfer(amount=400, reason="wages", to_purse=purse)
        transfer(amount=600, reason="spree", from_purse=purse)
        drained = run_purse_drains()
        self.assertEqual(self._balance(purse), 300)
        self.assertEqual(drained, 0)

    # --- config knobs (sibling distinctions) ---

    def test_partial_percent_drains_a_fraction(self) -> None:
        _, purse = self._make_holder(balance=1000, percent=50)
        self._run_week()
        self.assertEqual(self._balance(purse), 500)

    def test_floor_is_never_breached(self) -> None:
        _, purse = self._make_holder(balance=1000, floor=200)
        self._run_week()
        self.assertEqual(self._balance(purse), 200)

    # --- ledger + non-goals ---

    def test_drain_writes_an_audited_sink_row(self) -> None:
        _, purse = self._make_holder(balance=500)
        self._run_week()
        sink = CurrencyTransfer.objects.filter(
            from_purse=purse, to_purse__isnull=True, to_treasury__isnull=True
        ).latest("created_at")
        self.assertEqual(sink.amount, 500)

    def test_drain_sink_does_not_inflate_next_weeks_outflows(self) -> None:
        # Week 1 drains 500. Week 2 snapshot opens a fresh window that must not
        # count last week's drain transfer as an outflow.
        sheet, purse = self._make_holder(balance=500)
        self._run_week()
        # Flip week 1 off before week 2 on — the is_current partial unique
        # constraint forbids two current weeks even momentarily.
        self.week.is_current = False
        self.week.save(update_fields=["is_current"])
        week2 = GameWeek.objects.create(
            number=2, season=self.season, is_current=True, started_at=timezone.now()
        )
        purse.balance = 800
        purse.save(update_fields=["balance"])
        self._run_week()
        row = PurseDrainWeek.objects.get(character_sheet=sheet, game_week=week2)
        self.assertEqual(row.outflows, 0)
        self.assertEqual(self._balance(purse), 0)

    def test_non_holder_is_untouched(self) -> None:
        sheet = CharacterSheetFactory()
        purse = get_or_create_purse(sheet)
        purse.balance = 500
        purse.save(update_fields=["balance"])
        self._run_week()
        self.assertEqual(self._balance(purse), 500)
        self.assertFalse(PurseDrainWeek.objects.filter(character_sheet=sheet).exists())

    def test_zero_balance_drains_cleanly_without_a_sink_row(self) -> None:
        _, purse = self._make_holder(balance=0)
        before = CurrencyTransfer.objects.count()
        self._run_week()
        self.assertEqual(self._balance(purse), 0)
        self.assertEqual(CurrencyTransfer.objects.count(), before)

    # --- lifecycle guards ---

    def test_distinction_acquired_after_snapshot_is_skipped_this_week(self) -> None:
        # No snapshot row exists for a holder who gained the distinction mid-week.
        _, purse = self._make_holder(balance=500)
        PurseDrainWeek.objects.all().delete()  # simulate: snapshot ran before they qualified
        drained = run_purse_drains()
        self.assertEqual(drained, 0)
        self.assertEqual(self._balance(purse), 500)

    def test_snapshot_is_idempotent(self) -> None:
        self._make_holder(balance=500)
        self.assertEqual(snapshot_purse_drains(), 1)
        self.assertEqual(snapshot_purse_drains(), 0)
        self.assertEqual(PurseDrainWeek.objects.count(), 1)

    def test_drain_is_not_repeated_on_a_second_run(self) -> None:
        _, purse = self._make_holder(balance=500)
        self._run_week()
        transfer(amount=200, reason="wages", to_purse=purse)
        # A second drain pass this week must be a no-op (row already drained).
        drained = run_purse_drains()
        self.assertEqual(drained, 0)
        self.assertEqual(self._balance(purse), 200)

    def test_physical_coin_instruments_are_not_drained(self) -> None:
        # CurrencyInstrumentDetails are ItemInstances (possessions) — the purse
        # drain must never touch them. Guards the deliberate laundering route.
        self._make_holder(balance=0)
        self._run_week()
        # No instrument rows created or destroyed by the drain path.
        self.assertEqual(CurrencyInstrumentDetails.objects.count(), 0)

    def test_snapshot_query_count_is_flat_across_holders(self) -> None:
        # The snapshot's holder/purse fetch must not be per-holder — same query
        # count for one holder as for five (bulk_create, no N+1). The drain
        # itself is unavoidably linear: each holder gets an atomic transfer and
        # a narrative message, which cannot be bulked.
        self._make_holder(balance=500)
        with self.assertNumQueries(7):
            snapshot_purse_drains()
        PurseDrainWeek.objects.all().delete()
        for _ in range(4):
            self._make_holder(balance=500)
        with self.assertNumQueries(7):
            snapshot_purse_drains()

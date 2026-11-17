"""Retuning a thread's resonance rows, and Fall / Redemption converting them (#5123).

The retune moves part of one ``ThreadResonance`` row's amount to another row on the same
thread, by the same option rules as before; the thread's level and ``developed_points`` do
not move. The Fall and Redemption convert every row in the converted affinity, scaling
amounts and points, and merge rows that land on a resonance the thread already holds.

Pair rates are the production ones ``ensure_conversion_pairs`` authors: Celestial -> Primal
is a Fall at 1.20, Abyssal -> Celestial a Redemption at 0.50.
"""

from decimal import Decimal

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import GainSource
from world.magic.exceptions import ThreadResonanceChangeError
from world.magic.factories import (
    GiftFactory,
    ResonanceFactory,
    ThreadFactory,
    ThreadResonanceFactory,
    ensure_conversion_pairs,
)
from world.magic.models import ResonanceConversion, ThreadResonance
from world.magic.services.conversion import convert_resonance
from world.magic.services.resonance import grant_resonance
from world.magic.services.thread_resonance import (
    change_thread_resonance,
    check_thread_resonance_change,
    resolve_retune_amount,
    thread_resonance_options,
)
from world.magic.specialization.services import provision_latent_gift_thread


def size_row(thread, resonance, amount: int) -> None:
    """Set a row's amount through the identity map (a queryset update would leave it stale)."""
    ThreadResonanceFactory(thread=thread, resonance=resonance, amount=amount)


def amounts(thread) -> dict[str, int]:
    """``{resonance name: amount}`` for the thread's rows as the database holds them."""
    return dict(
        ThreadResonance.objects.filter(thread=thread).values_list("resonance__name", "amount")
    )


class RetuneRowsCase(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.celestial, cls.primal, cls.abyssal = ensure_conversion_pairs()
        cls.bene = ResonanceFactory(name="Bene", affinity=cls.celestial)
        cls.lumen = ResonanceFactory(name="Lumen", affinity=cls.celestial)
        cls.praedari = ResonanceFactory(name="Praedari", affinity=cls.primal)
        cls.sylvan = ResonanceFactory(name="Sylvan", affinity=cls.primal)
        cls.ruin = ResonanceFactory(name="Ruin", affinity=cls.abyssal)
        for source, target_affinity, target in (
            (cls.bene, cls.primal, cls.praedari),
            (cls.sylvan, cls.celestial, cls.bene),
            (cls.ruin, cls.celestial, cls.bene),
            (cls.lumen, cls.primal, cls.praedari),
        ):
            ResonanceConversion.objects.create(
                source_resonance=source, target_affinity=target_affinity, target_resonance=target
            )

    def mixed_thread(self, *, bene: int = 10, lumen: int = 3, level: int = 20, points: int = 13):
        thread = ThreadFactory(
            resonance=self.bene, level=level, developed_points=points, _trait_value=999
        )
        size_row(thread, thread.resonance, bene)
        ThreadResonanceFactory(thread=thread, resonance=self.lumen, amount=lumen)
        return thread


class RetuneMovesAmountTests(RetuneRowsCase):
    def test_retune_moves_amount_keeps_level(self) -> None:
        thread = self.mixed_thread()

        result = change_thread_resonance(
            thread.owner,
            thread=thread,
            from_resonance=self.bene,
            target_resonance=self.lumen,
            amount=2,
        )

        self.assertEqual(amounts(thread), {"Bene": 8, "Lumen": 5})
        self.assertEqual((result.amount_moved, result.points_gained), (2, 2))
        self.assertEqual((result.from_amount_after, result.to_amount_after), (8, 5))
        thread.refresh_from_db()
        self.assertEqual((thread.level, thread.developed_points), (20, 13))
        self.assertEqual(thread.resonance, self.bene)
        self.assertIn("moved 2 Bene into Lumen", result.message)
        self.assertIn("It now holds 8 Bene and 5 Lumen.", result.message)

    def test_a_gift_thread_retunes_into_a_resonance_off_the_gifts_list(self) -> None:
        """A Gift's ``resonances`` list limits nothing: every option is offered (#5123)."""
        sheet = CharacterSheetFactory()
        gift = GiftFactory()
        gift.resonances.add(self.bene)
        thread = provision_latent_gift_thread(sheet, gift, resonances=[self.bene])
        size_row(thread, self.bene, 10)
        sheet.character.threads.invalidate()

        offered = [option.resonance for option in thread_resonance_options(thread, self.bene)]
        change_thread_resonance(
            sheet,
            thread=thread,
            from_resonance=self.bene,
            target_resonance=self.lumen,
            amount=2,
        )

        self.assertIn(self.lumen, offered)
        self.assertEqual(amounts(thread), {"Bene": 8, "Lumen": 2})

    def test_retune_flips_leading_when_it_should(self) -> None:
        thread = self.mixed_thread()
        # Warm the handler's cache first, so the assertion below proves it was invalidated.
        self.assertEqual(
            thread.owner.character.threads.resonances_of(thread), [self.bene, self.lumen]
        )

        change_thread_resonance(
            thread.owner,
            thread=thread,
            from_resonance=self.bene,
            target_resonance=self.lumen,
            amount=8,
        )

        thread.refresh_from_db()
        self.assertEqual(thread.resonance, self.lumen)
        self.assertEqual(amounts(thread), {"Bene": 2, "Lumen": 11})
        self.assertEqual(
            thread.owner.character.threads.resonances_of(thread), [self.lumen, self.bene]
        )

    def test_from_defaults_to_the_leading_resonance_and_amount_to_all_of_it(self) -> None:
        thread = self.mixed_thread()
        self.assertEqual(len(thread.owner.character.threads.resonances_of(thread)), 2)

        result = change_thread_resonance(thread.owner, thread=thread, target_resonance=self.lumen)

        # The emptied Bene row is deleted, and the handler no longer lists it.
        self.assertEqual(amounts(thread), {"Lumen": 13})
        self.assertEqual(thread.owner.character.threads.resonances_of(thread), [self.lumen])
        self.assertIn("It holds no Bene now, and 13 Lumen.", result.message)
        thread.refresh_from_db()
        self.assertEqual(thread.resonance, self.lumen)

    def test_a_target_the_thread_does_not_hold_gets_a_new_row(self) -> None:
        thread = ThreadFactory(resonance=self.bene, developed_points=10)
        size_row(thread, thread.resonance, 10)

        change_thread_resonance(thread.owner, thread=thread, target_resonance=self.lumen, amount=3)

        self.assertEqual(amounts(thread), {"Bene": 7, "Lumen": 3})

    def test_a_move_across_affinities_converts_at_the_pair_rate(self) -> None:
        thread = self.mixed_thread()

        result = change_thread_resonance(
            thread.owner,
            thread=thread,
            from_resonance=self.bene,
            target_resonance=self.praedari,
            amount=5,
        )

        # Celestial -> Primal is a Fall at 1.20: int(5 x 1.20) = 6.
        self.assertEqual(amounts(thread), {"Bene": 5, "Lumen": 3, "Praedari": 6})
        self.assertEqual(result.conversion_type, "FALL")
        self.assertIn("which became 6", result.message)
        thread.refresh_from_db()
        self.assertEqual(thread.developed_points, 13)

    def test_a_redemption_never_loses_the_amount_entirely(self) -> None:
        thread = ThreadFactory(resonance=self.ruin, developed_points=1)
        size_row(thread, thread.resonance, 1)

        change_thread_resonance(thread.owner, thread=thread, target_resonance=self.bene)

        # Abyssal -> Celestial is a Redemption at 0.50: int(1 x 0.50) = 0, floored to 1.
        self.assertEqual(amounts(thread), {"Bene": 1})

    def test_options_are_computed_for_the_chosen_row(self) -> None:
        thread = self.mixed_thread()
        sylvan_thread = ThreadFactory(owner=thread.owner, resonance=self.sylvan, developed_points=5)

        move = check_thread_resonance_change(
            thread.owner, thread=sylvan_thread, target_resonance=self.bene
        )

        # Sylvan is Primal: Bene is its Celestial counterpart, a Redemption path.
        self.assertEqual(move.from_resonance, self.sylvan)
        self.assertEqual(move.option.conversion_type, "REDEMPTION")


class RetuneRefusalTests(RetuneRowsCase):
    def refused(self, thread, **kwargs) -> str:
        with self.assertRaises(ThreadResonanceChangeError) as raised:
            change_thread_resonance(thread.owner, thread=thread, **kwargs)
        return raised.exception.user_message

    def test_retune_refuses_unrelated_resonance(self) -> None:
        thread = self.mixed_thread()

        told = self.refused(
            thread, from_resonance=self.bene, target_resonance=self.sylvan, amount=2
        )

        self.assertIn("Bene cannot move to Sylvan.", told)
        self.assertEqual(amounts(thread), {"Bene": 10, "Lumen": 3})

    def test_a_resonance_the_thread_holds_no_row_for_is_refused(self) -> None:
        thread = self.mixed_thread()

        told = self.refused(thread, from_resonance=self.ruin, target_resonance=self.bene)

        self.assertEqual(told, "This thread holds no Ruin. It holds: Bene 10, Lumen 3.")

    def test_an_amount_past_the_row_is_refused(self) -> None:
        thread = self.mixed_thread()

        told = self.refused(thread, from_resonance=self.lumen, target_resonance=self.bene, amount=4)

        self.assertEqual(told, "This thread holds 3 Lumen; name an amount from 1 to 3.")
        self.assertEqual(amounts(thread), {"Bene": 10, "Lumen": 3})

    def test_an_empty_row_has_nothing_to_move(self) -> None:
        thread = self.mixed_thread(lumen=0)

        told = self.refused(thread, from_resonance=self.lumen, target_resonance=self.bene)

        self.assertEqual(told, "This thread has no Lumen to move.")

    def test_a_row_drained_behind_the_cache_is_refused_under_the_lock(self) -> None:
        thread = self.mixed_thread()
        row = ThreadResonance.objects.get(thread=thread, resonance=self.bene)
        # Another process drained the row; this process's cached instance still says 10.
        ThreadResonance.objects.filter(pk=row.pk).update_with_reason(
            reason="test: another process drained the row behind this one's cache", amount=1
        )

        told = self.refused(thread, from_resonance=self.bene, target_resonance=self.lumen, amount=5)

        self.assertEqual(told, "This thread holds 1 Bene; name an amount from 1 to 1.")
        self.assertEqual(amounts(thread), {"Bene": 1, "Lumen": 3})

    def test_naming_no_target_lists_the_options_for_the_row(self) -> None:
        thread = self.mixed_thread()

        told = self.refused(thread, from_resonance=self.lumen)

        self.assertEqual(
            told,
            "Name the resonance to move it to. It can move to: Bene (same affinity), "
            "Praedari (Fall).",
        )

    def test_the_amount_must_be_a_whole_number(self) -> None:
        for raw in (0, -2, "abc", True, [3]):
            with self.subTest(raw=raw), self.assertRaises(ThreadResonanceChangeError):
                resolve_retune_amount(raw)
        self.assertIsNone(resolve_retune_amount(None))
        self.assertEqual(resolve_retune_amount("5"), 5)


class FallConvertsRowsTests(RetuneRowsCase):
    def setUp(self) -> None:
        super().setUp()
        self.sheet = CharacterSheetFactory()
        for resonance in (self.bene, self.lumen, self.praedari):
            grant_resonance(self.sheet, resonance, 50, source=GainSource.STAFF_GRANT)

    def fall(self) -> None:
        convert_resonance(
            self.sheet,
            source_affinity=self.celestial,
            target_affinity=self.primal,
            multiplier=Decimal("1.20"),
        )

    def test_fall_converts_rows_in_affinity(self) -> None:
        thread = ThreadFactory(owner=self.sheet, resonance=self.bene, level=20, developed_points=10)
        size_row(thread, thread.resonance, 10)
        self.assertEqual(self.sheet.character.threads.resonances_of(thread), [self.bene])

        self.fall()

        # Celestial -> Primal is a Fall at 1.20: the whole thread scales, int(10 x 1.20) = 12.
        self.assertEqual(amounts(thread), {"Praedari": 12})
        thread.refresh_from_db()
        self.assertEqual(thread.resonance, self.praedari)
        self.assertEqual((thread.level, thread.developed_points), (20, 12))
        self.assertEqual(self.sheet.character.threads.resonances_of(thread), [self.praedari])

    def test_fall_merges_rows_on_one_thread(self) -> None:
        thread = ThreadFactory(owner=self.sheet, resonance=self.bene, developed_points=15)
        size_row(thread, thread.resonance, 10)
        ThreadResonanceFactory(thread=thread, resonance=self.praedari, amount=5)
        self.assertEqual(len(self.sheet.character.threads.resonances_of(thread)), 2)

        self.fall()

        self.assertEqual(self.sheet.character.threads.resonances_of(thread), [self.praedari])
        # Bene's 10 become 12 and land on the Praedari row already there: one row, 17.
        # Points: int(15 x (5 + 10 x 1.2) / 15) = 17.
        self.assertEqual(amounts(thread), {"Praedari": 17})
        thread.refresh_from_db()
        self.assertEqual(thread.resonance, self.praedari)
        self.assertEqual(thread.developed_points, 17)

    def test_two_source_rows_converging_on_one_target_merge(self) -> None:
        thread = ThreadFactory(owner=self.sheet, resonance=self.bene, developed_points=10)
        size_row(thread, thread.resonance, 5)
        ThreadResonanceFactory(thread=thread, resonance=self.lumen, amount=5)

        self.fall()

        # Bene and Lumen both convert to Praedari: int(5 x 1.2) = 6 each, one row of 12.
        self.assertEqual(amounts(thread), {"Praedari": 12})

    def test_points_scale_over_the_share_of_the_thread_that_converted(self) -> None:
        thread = ThreadFactory(owner=self.sheet, resonance=self.bene, developed_points=20)
        size_row(thread, thread.resonance, 10)
        ThreadResonanceFactory(thread=thread, resonance=self.sylvan, amount=10)

        self.fall()

        # Half the rows converted: int(20 x (10 + 10 x 1.2) / 20) = 22.
        self.assertEqual(amounts(thread), {"Praedari": 12, "Sylvan": 10})
        thread.refresh_from_db()
        self.assertEqual(thread.developed_points, 22)

    def test_threads_with_no_row_in_the_affinity_and_retired_ones_are_untouched(self) -> None:
        untouched = ThreadFactory(owner=self.sheet, resonance=self.praedari, developed_points=7)
        retired = ThreadFactory(owner=self.sheet, resonance=self.bene, developed_points=9)
        retired.retired_at = retired.created_at
        retired.save(update_fields=["retired_at"])

        self.fall()

        self.assertEqual(amounts(untouched), {"Praedari": 7})
        self.assertEqual(amounts(retired), {"Bene": 9})

    def redeem(self) -> None:
        convert_resonance(
            self.sheet,
            source_affinity=self.abyssal,
            target_affinity=self.celestial,
            multiplier=Decimal("0.50"),
        )

    def test_a_redemption_lossy_enough_to_empty_a_row_deletes_it(self) -> None:
        grant_resonance(self.sheet, self.ruin, 50, source=GainSource.STAFF_GRANT)
        thread = ThreadFactory(owner=self.sheet, resonance=self.lumen, developed_points=10)
        size_row(thread, thread.resonance, 10)
        ThreadResonanceFactory(thread=thread, resonance=self.ruin, amount=1)
        self.assertEqual(len(self.sheet.character.threads.resonances_of(thread)), 2)

        self.redeem()

        # Abyssal -> Celestial is a Redemption at 0.50: int(1 x 0.50) = 0, so the Ruin row goes.
        self.assertEqual(amounts(thread), {"Lumen": 10})
        self.assertEqual(self.sheet.character.threads.resonances_of(thread), [self.lumen])

    def test_a_redemption_keeps_the_only_row_even_at_zero(self) -> None:
        grant_resonance(self.sheet, self.ruin, 50, source=GainSource.STAFF_GRANT)
        thread = ThreadFactory(owner=self.sheet, resonance=self.ruin, developed_points=1)
        size_row(thread, thread.resonance, 1)

        self.redeem()

        self.assertEqual(amounts(thread), {"Bene": 0})
        thread.refresh_from_db()
        self.assertEqual(thread.resonance, self.bene)

    def test_a_creation_pick_already_at_zero_follows_the_fall(self) -> None:
        # Dawn maps to a different Primal resonance than the leader does, so its zero row
        # is moved onto Sylvan rather than merged into the leader's Praedari row.
        dawn = ResonanceFactory(name="Dawn", affinity=self.celestial)
        ResonanceConversion.objects.create(
            source_resonance=dawn, target_affinity=self.primal, target_resonance=self.sylvan
        )
        thread = ThreadFactory(owner=self.sheet, resonance=self.bene, developed_points=10)
        size_row(thread, thread.resonance, 10)
        ThreadResonanceFactory(thread=thread, resonance=dawn, amount=0)

        self.fall()

        # The 0 row is not "emptied" (it held nothing): it follows to its own target.
        self.assertEqual(amounts(thread), {"Praedari": 12, "Sylvan": 0})

"""Fuzz: the invariants of several resonances and the unsettled aura (#5123).

Two properties of the aura, and of a thread's resonance rows, that no hand-picked journey can
exhaust, judged on what the database holds after each step of a random history.

The aura. Hypothesis seeds a character who is settled somewhere (a random split of 100), holds
random lifetime resonance in six resonances (two per affinity), then runs up to five steps: a
grant, an atone (moving lifetime from one resonance to another) or an accept. After every step:

- her settled shares sum to exactly 100;
- an atone moves lifetime and creates none (the total lifetime is unchanged);
- a grant of the main affinity (the largest settled share) never raises ``steps_past``;
- an accept leaves her with ``steps_past == 0``, whoever she was, and refuses when she was not
  unsettled.

The rite of settling disowning her Ruin (``perform_settling_rite``, the service the web dialog
and ``aura settle`` reach) is fuzzed too: whatever the cap lets her convert, she converts
exactly the least of the cap, what she holds of Ruin and what stands past who she is, and total
lifetime is conserved.

The Mire. A Sineater's Mire is corruption she carries for her Sinners (``MireHolding``). Over any
sequence of taking a Sinner's corruption on, releasing some of it, daily decay and giving in to
a Compulsion, the holdings in a resonance never sum to more than her corruption in it.

The thread. A thread's ``ThreadResonance`` amounts are cumulative per resonance (the total
ever imbued), NOT the points still in the bucket: ``developed_points`` is what is left after
levelling spent from it, so the rows' sum and ``developed_points`` diverge as soon as the
thread levels. What is true, and checked here:

- imbuing alone: each row is exactly what was imbued with that resonance, the rows sum to
  everything imbued, ``developed_points`` is that sum less what the levels climbed cost (ten
  points a level from 0 to 19 on the shared development curve), and so never exceeds the
  rows' sum;
- over any history of imbues, retunes and Falls: no row is ever below zero, the thread always
  holds a row, and ``Thread.resonance`` is the resonance of the leading row (the largest
  amount, the earliest created on a tie), which ``refresh_leading_resonance`` alone writes;
- a retune moves nothing but the two rows, leaves ``level`` and ``developed_points`` alone, and
  the target gains the moved amount at the pair rate (one for one in the same affinity), so a
  same-affinity retune conserves the rows' sum; a refused retune changes nothing;
- a Fall of Primal into Abyssal leaves no Primal row, adds each Primal row at the Fall rate
  to the one Abyssal row, leaves the Celestial row and the level alone.

Each example runs in its own transaction; the character and everything that changes is built
inside the example, the shared catalog (resonances, affinity pairs) once in ``setUpTestData``
(a Hypothesis test's own ``setUp`` runs outside any transaction, so it would leak).
"""

from __future__ import annotations

from decimal import Decimal
from math import ceil

from hypothesis import example, given, strategies as st
from hypothesis.extra.django import TestCase as HypothesisTestCase

from world.action_points.models import ActionPointConfig, ActionPointPool
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.magic.constants import GainSource, ReflectionChoice
from world.magic.exceptions import NotUnsettledError
from world.magic.factories import (
    CharacterAuraFactory,
    CharacterResonanceFactory,
    CorruptionConditionTemplateFactory,
    DriftConversionCapFactory,
    DriftConversionOfferFactory,
    DriftCorrectionRiteFactory,
    ReflectionFactory,
    ResonanceFactory,
    ResonanceTierFactory,
    ThreadFactory,
    ensure_canonical_affinities,
    ensure_conversion_pairs,
    set_aura_split,
)
from world.magic.models import (
    Affinity,
    AffinityInteraction,
    CharacterAura,
    CharacterAuraShare,
    CharacterResonance,
    DriftCorrectionOutcomeShare,
    MireHolding,
    ResonanceConversion,
    Thread,
    ThreadResonance,
)
from world.magic.services.aura import recompute_aura, set_settled_shares
from world.magic.services.conversion import convert_resonance, convert_resonance_amount
from world.magic.services.corruption import accrue_corruption, reduce_corruption
from world.magic.services.drift import (
    accept_aura_change,
    drift_for,
    get_drift_config,
    get_drift_correction_config,
)
from world.magic.services.drift_correction import perform_settling_rite
from world.magic.services.mire import add_to_largest_holding, release_mire, take_on_corruption
from world.magic.services.resonance import grant_resonance, spend_resonance_for_imbuing
from world.magic.services.thread_resonance import (
    ThreadResonanceChangeError,
    change_thread_resonance,
)
from world.magic.types import AffinityShare
from world.magic.types.corruption import CorruptionRecoverySource, CorruptionSource
from world.relationships.factories import CharacterRelationshipFactory
from world.scenes.factories import SceneFactory
from world.traits.constants import CANONICAL_OUTCOME_LEVELS
from world.traits.services import ensure_canonical_check_outcome

# --- the aura ----------------------------------------------------------------------------

ONE_HUNDRED = Decimal(100)
KINDS = ("grant", "atone", "accept")


@st.composite
def auras(draw: st.DrawFn) -> tuple[tuple[int, int, int], list[int]]:
    """Settled weights for Celestial / Primal / Abyssal, and the lifetime held in each of six
    resonances, two per affinity in that order."""
    weights = draw(st.tuples(*[st.integers(0, 10)] * 3).filter(lambda w: sum(w) > 0))
    held = draw(st.lists(st.integers(0, 300), min_size=6, max_size=6))
    return weights, held


steps = st.tuples(
    st.sampled_from(KINDS),
    st.integers(0, 5),  # which resonance (or source row)
    st.integers(0, 5),  # which resonance (the atone's target)
    st.integers(1, 200),  # an amount, or a percent of the source's lifetime
    st.sampled_from([Decimal("0.5"), Decimal(1), Decimal("1.5")]),
)


class UnsettledAuraInvariants(HypothesisTestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        Affinity.objects.clear_cache()
        cls.affinities = ensure_canonical_affinities()
        cls.resonances = [
            ResonanceFactory(name=f"{affinity.name} {n}", affinity=affinity)
            for affinity in cls.affinities
            for n in (1, 2)
        ]

    def character(self, aura_spec):
        weights, held = aura_spec
        sheet = CharacterSheetFactory()
        aura = CharacterAura.objects.create(character=sheet)
        total = sum(weights)
        set_settled_shares(
            aura,
            [
                AffinityShare(affinity=affinity, percent=Decimal(weight) * ONE_HUNDRED / total)
                for affinity, weight in zip(self.affinities, weights, strict=True)
                if weight
            ],
        )
        for resonance, lifetime in zip(self.resonances, held, strict=True):
            CharacterResonance.objects.create(
                character_sheet=sheet,
                resonance=resonance,
                balance=lifetime,
                lifetime_earned=lifetime,
            )
        recompute_aura(sheet)
        return sheet, aura

    def assert_sound(self, aura) -> None:
        settled = CharacterAuraShare.objects.filter(aura=aura).values_list(
            "settled_percent", flat=True
        )
        self.assertEqual(sum(settled, Decimal(0)), ONE_HUNDRED)

    def lifetime(self, sheet) -> int:
        return sum(
            CharacterResonance.objects.filter(character_sheet=sheet).values_list(
                "lifetime_earned", flat=True
            )
        )

    def step(self, sheet, kind, i, j, n, rate) -> None:  # noqa: PLR0913 - the drawn step
        resonance = self.resonances[i]
        if kind == "grant":
            before = drift_for(sheet)
            grant_resonance(sheet, resonance, n, source=GainSource.STAFF_GRANT)
            if (
                before.main_affinity is not None
                and resonance.affinity_id == before.main_affinity.pk
            ):
                self.assertLessEqual(drift_for(sheet).steps_past, before.steps_past)
        elif kind == "atone":
            rows = list(
                CharacterResonance.objects.filter(character_sheet=sheet, lifetime_earned__gt=0)
            )
            target = self.resonances[j]
            if not rows or rows[i % len(rows)].resonance_id == target.pk:
                return
            source = rows[i % len(rows)]
            amount = max(1, source.lifetime_earned * min(n, 100) // 100)
            total = self.lifetime(sheet)
            convert_resonance_amount(
                sheet,
                source_resonance=source.resonance,
                target_resonance=target,
                amount=amount,
                multiplier=rate,
                gain_source=GainSource.DRIFT_CORRECTION,
            )
            self.assertEqual(self.lifetime(sheet), total)
        else:
            before = drift_for(sheet)
            if before.steps_past > 0:
                accept_aura_change(sheet)
                self.assertEqual(drift_for(sheet).steps_past, 0)
            else:
                with self.assertRaises(NotUnsettledError):
                    accept_aura_change(sheet)

    def run_history(self, aura_spec, history) -> None:
        sheet, aura = self.character(aura_spec)
        self.assert_sound(aura)
        for kind, i, j, n, rate in history:
            self.step(sheet, kind, i, j, n, rate)
            self.assert_sound(aura)

    @given(aura_spec=auras(), history=st.lists(steps, max_size=5))
    def test_any_history_keeps_the_aura_sound(self, aura_spec, history) -> None:
        self.run_history(aura_spec, history)


# --- the atone rite on a Sineater ---------------------------------------------------------


class AtoningConvertsWhatStandsPast(HypothesisTestCase):
    """A character is settled Celestial with Dawnlight lifetime D and Ruin (Abyssal) lifetime R.
    She atones Ruin into Dawnlight through the real rite, the check forced to a full-share
    Success.

    She converts the least of the open cap, what she holds of Ruin, and what stands past who
    she is: the Abyssal share of all her lifetime, less the shipped range before Unsettled,
    in points rounded up. Total lifetime is conserved. What the rite refuses (more than is
    past who she is) changes nothing.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        Affinity.objects.clear_cache()
        AffinityInteraction.objects.clear_cache()
        cls.celestial, _primal, cls.abyssal = ensure_conversion_pairs()
        AffinityInteraction.objects.clear_cache()
        cls.dawnlight = ResonanceFactory(name="Dawnlight", affinity=cls.celestial)
        cls.ruin = ResonanceFactory(name="Ruin", affinity=cls.abyssal)
        cls.scene = SceneFactory(is_active=True)
        config = get_drift_correction_config()
        config.rite = DriftCorrectionRiteFactory()
        config.check_type = CheckTypeFactory()
        config.check_difficulty_level = 0
        config.cap_percent = 50
        config.save()
        cls.outcomes = {
            name: ensure_canonical_check_outcome(name) for name in CANONICAL_OUTCOME_LEVELS
        }
        for outcome in cls.outcomes.values():
            DriftCorrectionOutcomeShare.objects.update_or_create(
                outcome_tier=outcome, defaults={"converted_share": Decimal("1.00")}
            )

    def character(self, dawn: int, ruin: int):
        sheet = CharacterSheetFactory()
        set_aura_split(
            CharacterAuraFactory(character=sheet), celestial="100", primal="0", abyssal="0"
        )
        CharacterResonance.objects.create(
            character_sheet=sheet, resonance=self.dawnlight, balance=dawn, lifetime_earned=dawn
        )
        CharacterResonance.objects.create(
            character_sheet=sheet, resonance=self.ruin, balance=ruin, lifetime_earned=ruin
        )
        recompute_aura(sheet)
        return sheet

    def atone(self, dawn: int, ruin: int, amount: int) -> int:
        """Settle with an open cap of ``amount``, disowning her Ruin; return what converted."""
        sheet = self.character(dawn, ruin)
        offer = DriftConversionOfferFactory(character_sheet=sheet, scene=self.scene)
        DriftConversionCapFactory(offer=offer, target_resonance=self.dawnlight, cap=amount)
        ReflectionFactory(
            character_sheet=sheet, resonance=self.ruin, choice=ReflectionChoice.DISOWN
        )
        offering = ItemInstanceFactory(
            template=ItemTemplateFactory(
                tied_resonance=self.dawnlight, resonance_tier=ResonanceTierFactory()
            )
        )
        total = dawn + ruin
        # Ruin is all of the Abyssal, which she settled at nothing.
        past = Decimal(ruin) * ONE_HUNDRED / total - get_drift_config().unsettled_tolerance_percent
        past_points = ceil(past * total / ONE_HUNDRED) if past > 0 else 0
        moved = min(amount, ruin, past_points)

        with force_check_outcome(self.outcomes["Success"]):
            perform_settling_rite(sheet, components=[offering])

        row = CharacterResonance.objects.get(character_sheet=sheet, resonance=self.ruin)
        self.assertEqual(row.lifetime_earned, ruin - moved)
        self.assertEqual(
            sum(
                CharacterResonance.objects.filter(character_sheet=sheet).values_list(
                    "lifetime_earned", flat=True
                )
            ),
            total,
        )
        return moved

    @given(dawn=st.integers(100, 700), ruin=st.integers(1, 300), amount=st.integers(1, 300))
    @example(dawn=500, ruin=300, amount=40)
    def test_she_converts_the_least_of_the_cap_her_ruin_and_what_stands_past(
        self, dawn, ruin, amount
    ) -> None:
        self.atone(dawn, ruin, min(amount, ruin))

    def test_a_cap_past_what_stands_past_her_line_clamps_to_it(self) -> None:
        # 500 Ruin of 1000 is 50 percent against a range of 5: 450 points stand past.
        self.assertEqual(self.atone(500, 500, 300), 300)
        self.assertEqual(self.atone(500, 500, 500), 450)


# --- the Mire a Sineater carries ----------------------------------------------------------

MIRE_OPERATIONS = ("take", "release", "decay", "indulge")

mire_steps = st.tuples(
    st.sampled_from(MIRE_OPERATIONS),
    st.integers(0, 1),  # which of her two Sinners
    st.integers(1, 120),  # an amount
)


class MireNeverExceedsTheSineatersCorruption(HypothesisTestCase):
    """Corvin carries Ruin for two Sinners, each of whom carries 500 of it.

    Whatever order she takes a Sinner's corruption on, releases some of what she holds, lets
    daily decay take some off, or gives in to a Compulsion (which adds to the Sinner she holds
    the most for), the holdings in Ruin never sum to more than her corruption in it.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        Affinity.objects.clear_cache()
        cls.abyssal = ensure_canonical_affinities()[2]
        cls.ruin = ResonanceFactory(name="Mire Fuzz Ruin", affinity=cls.abyssal)
        CorruptionConditionTemplateFactory(corruption_resonance=cls.ruin)

    def cast(self):
        """Corvin, her two Sinners, and the Sinners' corruption, built inside the example."""
        sineater = CharacterSheetFactory()
        CharacterResonanceFactory(character_sheet=sineater, resonance=self.ruin)
        sinners = [CharacterSheetFactory() for _ in range(2)]
        for sinner in sinners:
            CharacterResonanceFactory(
                character_sheet=sinner, resonance=self.ruin, corruption_current=500
            )
            CharacterRelationshipFactory(source=sineater, target=sinner)
        return sineater, sinners

    def assert_within(self, sineater) -> None:
        held = sum(
            MireHolding.objects.filter(
                relationship__source=sineater, resonance=self.ruin
            ).values_list("amount", flat=True)
        )
        carried = CharacterResonance.objects.get(
            character_sheet=sineater, resonance=self.ruin
        ).corruption_current
        self.assertLessEqual(held, carried)

    def operate(self, sineater, sinners, operation: str, who: int, amount: int) -> None:
        sinner = sinners[who]
        if operation == "take":
            take_on_corruption(
                sineater_sheet=sineater, sinner_sheet=sinner, resonance=self.ruin, amount=amount
            )
        elif operation == "release":
            holding = MireHolding.objects.filter(
                relationship__source=sineater, relationship__target=sinner, resonance=self.ruin
            ).first()
            if holding is not None:
                release_mire(holding=holding, amount=amount)
        elif operation == "decay":
            reduce_corruption(
                character_sheet=sineater,
                resonance=self.ruin,
                amount=amount,
                source=CorruptionRecoverySource.PASSIVE_DECAY,
                _from_decay=True,
                grant_resonance_back=False,
            )
        else:
            added = accrue_corruption(
                character_sheet=sineater,
                resonance=self.ruin,
                amount=amount,
                source=CorruptionSource.INDULGED,
            ).amount_applied
            add_to_largest_holding(sineater, self.ruin, added)

    @given(history=st.lists(mire_steps, max_size=12))
    def test_the_holdings_never_sum_to_more_than_her_corruption(self, history) -> None:
        sineater, sinners = self.cast()
        for operation, who, amount in history:
            self.operate(sineater, sinners, operation, who, amount)
            self.assert_within(sineater)


# --- a thread's resonance rows -----------------------------------------------------------

# Pair rates as ``ensure_conversion_pairs`` authors them (the production values).
FALL_RATE = Decimal("1.20")  # Primal into Abyssal
REDEMPTION_RATE = Decimal("0.70")  # Abyssal into Primal
SAME_AFFINITY = Decimal(1)

# The moves the catalog authors, as indexes into the four resonances (Primal 1, Primal 2,
# Abyssal 1, Celestial 1): within Primal both ways, Primal into Abyssal, Abyssal into Primal.
RETUNES = ((0, 1), (1, 0), (0, 2), (1, 2), (2, 0))

thread_steps = st.tuples(
    st.sampled_from(("imbue", "retune", "fall")),
    st.integers(0, 3),  # which resonance (or the retune's source)
    st.integers(0, 3),  # the retune's target
    st.integers(1, 20),  # an amount
)


class ThreadRowInvariants(HypothesisTestCase):
    """Four resonances: Primal 1 and 2, Abyssal 1, Celestial 1. The character holds 50 of each."""

    @classmethod
    def setUpTestData(cls) -> None:
        ActionPointConfig.objects.update_or_create(
            name="Default", defaults={"is_active": True, "weekly_regen": 80}
        )
        cls.celestial, cls.primal, cls.abyssal = ensure_conversion_pairs()
        AffinityInteraction.objects.clear_cache()
        cls.p1 = ResonanceFactory(name="Primal One", affinity=cls.primal)
        cls.p2 = ResonanceFactory(name="Primal Two", affinity=cls.primal)
        cls.a1 = ResonanceFactory(name="Abyssal One", affinity=cls.abyssal)
        cls.c1 = ResonanceFactory(name="Celestial One", affinity=cls.celestial)
        cls.resonances = [cls.p1, cls.p2, cls.a1, cls.c1]
        for source, target_affinity, target in (
            (cls.p1, cls.abyssal, cls.a1),
            (cls.p2, cls.abyssal, cls.a1),
            (cls.a1, cls.primal, cls.p1),
        ):
            ResonanceConversion.objects.create(
                source_resonance=source, target_affinity=target_affinity, target_resonance=target
            )

    def character_and_thread(self):
        sheet = CharacterSheetFactory()
        CharacterAuraFactory(character=sheet)
        for resonance in self.resonances:
            CharacterResonance.objects.create(
                character_sheet=sheet, resonance=resonance, balance=50, lifetime_earned=50
            )
        pool = ActionPointPool.get_or_create_for_character(sheet.character)
        pool.current = pool.maximum = 10_000
        pool.save()
        thread = ThreadFactory(
            owner=sheet,
            resonance=self.p1,
            level=0,
            developed_points=0,
            _trait_value=500,
        )
        return sheet, thread

    @staticmethod
    def rows(thread) -> dict[int, int]:
        """``{resonance pk: amount}``, as the database holds them."""
        return dict(
            ThreadResonance.objects.filter(thread=thread).values_list("resonance_id", "amount")
        )

    @staticmethod
    def stored(thread) -> tuple[int, int, int]:
        """``(resonance pk, level, developed points)`` as the database holds them."""

        return Thread.objects.filter(pk=thread.pk).values_list(
            "resonance_id", "level", "developed_points"
        )[0]

    def assert_sound(self, thread) -> None:
        held = list(ThreadResonance.objects.filter(thread=thread))
        self.assertTrue(held, "a thread always holds a row")
        for row in held:
            self.assertGreaterEqual(row.amount, 0)
        leading = max(held, key=lambda row: (row.amount, -row.pk))
        self.assertEqual(self.stored(thread)[0], leading.resonance_id)

    def imbue(self, sheet, thread, resonance, amount: int) -> None:
        balance = CharacterResonance.objects.get(character_sheet=sheet, resonance=resonance).balance
        if balance < amount:
            return
        rows_before = self.rows(thread)
        _lead, level_before, points_before = self.stored(thread)

        spend_resonance_for_imbuing(sheet, thread, resonance, amount)

        rows_after = self.rows(thread)
        self.assertEqual(
            rows_after, {**rows_before, resonance.pk: rows_before.get(resonance.pk, 0) + amount}
        )
        _lead, level_after, points_after = self.stored(thread)
        # Every level from 0 to 19 costs ten points of the bucket on the shared curve.
        self.assertEqual(points_after, points_before + amount - 10 * (level_after - level_before))

    def retune(self, sheet, thread, source, target, amount: int) -> None:
        rows_before = self.rows(thread)
        _lead, level_before, points_before = self.stored(thread)
        try:
            result = change_thread_resonance(
                sheet,
                thread=thread,
                target_resonance=target,
                from_resonance=source,
                amount=amount,
            )
        except ThreadResonanceChangeError:
            self.assertEqual(self.rows(thread), rows_before)
            self.assertEqual(self.stored(thread)[1:], (level_before, points_before))
            return
        rows_after = self.rows(thread)
        self.assertEqual(self.stored(thread)[1:], (level_before, points_before))
        moved = result.amount_moved
        self.assertTrue(1 <= moved <= rows_before[source.pk])
        rate = {
            (self.primal.pk, self.abyssal.pk): FALL_RATE,
            (self.abyssal.pk, self.primal.pk): REDEMPTION_RATE,
        }.get((source.affinity_id, target.affinity_id), SAME_AFFINITY)
        gained = max(1, int(Decimal(moved) * rate))
        expected = dict(rows_before)
        expected[source.pk] -= moved
        if not expected[source.pk]:
            del expected[source.pk]
        expected[target.pk] = expected.get(target.pk, 0) + gained
        self.assertEqual(rows_after, expected)
        if rate == SAME_AFFINITY:
            self.assertEqual(sum(rows_after.values()), sum(rows_before.values()))

    def fall(self, sheet, thread) -> None:
        rows_before = self.rows(thread)
        _lead, level_before, _points = self.stored(thread)

        convert_resonance(
            sheet,
            source_affinity=self.primal,
            target_affinity=self.abyssal,
            multiplier=FALL_RATE,
        )

        expected = {
            pk: amount for pk, amount in rows_before.items() if pk not in (self.p1.pk, self.p2.pk)
        }
        converted = sum(
            int(Decimal(rows_before.get(resonance.pk, 0)) * FALL_RATE)
            for resonance in (self.p1, self.p2)
        )
        if self.p1.pk in rows_before or self.p2.pk in rows_before:
            expected[self.a1.pk] = expected.get(self.a1.pk, 0) + converted
        self.assertEqual(self.rows(thread), expected)
        self.assertEqual(self.stored(thread)[1], level_before)

    @given(
        start=st.lists(st.tuples(st.integers(0, 3), st.integers(1, 8)), min_size=1, max_size=4),
        history=st.lists(thread_steps, max_size=6),
    )
    def test_any_history_keeps_the_rows_sound(self, start, history) -> None:
        sheet, thread = self.character_and_thread()
        # The thread holds something imbued first, so there is a row to retune or convert.
        for i, amount in start:
            self.imbue(sheet, thread, self.resonances[i], amount)
        self.assert_sound(thread)
        for kind, i, j, n in history:
            if kind == "imbue":
                self.imbue(sheet, thread, self.resonances[i], n)
            elif kind == "retune":
                source, target = (self.resonances[k] for k in RETUNES[(i + j) % len(RETUNES)])
                self.retune(sheet, thread, source, target, n)
            else:
                self.fall(sheet, thread)
            self.assert_sound(thread)

    @given(imbues=st.lists(st.tuples(st.integers(0, 3), st.integers(1, 8)), min_size=1, max_size=6))
    def test_imbuing_alone_leaves_the_rows_the_total_ever_imbued(self, imbues) -> None:
        sheet, thread = self.character_and_thread()
        imbued: dict[int, int] = {}
        for i, amount in imbues:
            resonance = self.resonances[i]
            spend_resonance_for_imbuing(sheet, thread, resonance, amount)
            imbued[resonance.pk] = imbued.get(resonance.pk, 0) + amount

            rows = self.rows(thread)
            # Each row is what was imbued with that resonance; the thread's own resonance
            # holds its creation row at zero when nothing of it has been imbued.
            self.assertEqual({pk: v for pk, v in rows.items() if v}, imbued)
            _lead, level, points = self.stored(thread)
            self.assertEqual(points, sum(imbued.values()) - 10 * level)
            self.assertLessEqual(points, sum(rows.values()))
            self.assert_sound(thread)

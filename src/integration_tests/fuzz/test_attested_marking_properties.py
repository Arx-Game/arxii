"""Fuzz: the rules of marking an act, and what a mark costs, as properties (#5327).

A character gains resonance outside an authored choice only when her player marks an act her
character took (a ``RecordedAct``) with a resonance, in a pose or a journal entry. Each class
below holds one rule of that design, quoted in the maintainer's words from the issue. Every
example builds its characters, acts, suggestions and writings fresh with factories and uses our
own functions (``pending_mark_from`` and ``record_pending_mark``, which call
``grant_resonance``, the weekly table and the fatigue charge); the shared catalog lives once in
``setUpTestData`` (a Hypothesis test's own ``setUp`` runs outside any transaction, so it would
leak rows between examples).

How outcomes are pinned: the bonus check is a real ``perform_check``.
``force_every_check_outcome`` (``world.checks.test_helpers``) names the result of every roll,
and its ``calls`` list counts the rolls and shows the stat and skill each added, so no property
patches one of our own functions. A property that does not care about the bonus check turns it
off, so a grant's amount is exactly what the mark computed.

``_World`` is the shared builder: the three affinities each linked to a skill, one resonance on
each, a bonus check type that weighs one stat, an act check type that weighs another, an award
row on every canonical result tier, three strength tiers and a four-step weekly table. Every
example sets what it needs first, because those config rows are idmapper singletons that an
earlier example may have changed.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from django.utils import timezone
from hypothesis import given, settings, strategies as st
from hypothesis.extra.django import TestCase as HypothesisTestCase

from actions.constants import ActionCategory
from actions.definitions.journals import CreateJournalEntryAction
from commands.acts import act_lines
from commands.exceptions import CommandError
from commands.reach import reach_kwargs_and_rest
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import CharacterSheet
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.checks.test_helpers import force_every_check_outcome, make_player_character
from world.checks.types import ExtraTraitTerm
from world.fatigue.services import get_fatigue_capacity, get_or_create_fatigue_pool
from world.fatigue.tests import setup_stat
from world.journals.factories import JournalEntryFactory
from world.journals.models import JournalEntry, WeeklyJournalXP
from world.magic.constants import GainSource
from world.magic.exceptions import MarkError
from world.magic.factories import (
    CharacterAuraFactory,
    KindledDeedAwardFactory,
    KindledStrengthTierFactory,
    RecordedActFactory,
    RecordedActSuggestionFactory,
    ResonanceCheckAwardFactory,
    ResonanceFactory,
    ResonanceGrantFactory,
    WeeklyMarkReturnFactory,
    ensure_conversion_pairs,
)
from world.magic.models import (
    Affinity,
    CharacterResonance,
    RecordedAct,
    RecordedActSuggestion,
    Resonance,
    ResonanceCheckAward,
    ResonanceGrant,
    WeeklyMarkReturn,
)
from world.magic.services.gain import get_resonance_gain_config
from world.magic.services.marking import (
    pending_mark_from,
    pointable_acts_page,
    record_pending_mark,
    weekly_percent_paid,
)
from world.magic.types.marking import MarkResult, PendingMark
from world.scenes.factories import InteractionFactory
from world.skills.factories import MagicSkillFactory
from world.traits.constants import CANONICAL_OUTCOME_LEVELS
from world.traits.factories import StatTraitFactory
from world.traits.models import CheckOutcome, TraitCategory
from world.traits.services import ensure_canonical_check_outcome

# One resonance on each affinity. The key is what a strategy draws.
KEYS = ("mercy", "fury", "cruelty")
AFFINITY_OF = {"mercy": "celestial", "fury": "primal", "cruelty": "abyssal"}
# The canonical result tiers, worst roll first.
TIERS = tuple(sorted(CANONICAL_OUTCOME_LEVELS, key=lambda name: CANONICAL_OUTCOME_LEVELS[name]))
# What a character must already have gained from marks this game week for a weekly step to
# apply, one threshold per authored step.
THRESHOLDS = (0, 10, 20, 30)
RANKS = (1, 2, 3)


class _World:
    """The shared builder for the properties below (a mixin for the test classes)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.celestial, cls.primal, cls.abyssal = ensure_conversion_pairs()
        cls.affinities: dict[str, Affinity] = {
            "celestial": cls.celestial,
            "primal": cls.primal,
            "abyssal": cls.abyssal,
        }
        cls.skills = {}
        for affinity_name, skill_name in (
            ("celestial", "Heroism"),
            ("primal", "Reflection"),
            ("abyssal", "Villainy"),
        ):
            skill = MagicSkillFactory(name=skill_name)
            affinity = cls.affinities[affinity_name]
            affinity.skill = skill
            affinity.save()
            cls.skills[affinity_name] = skill
        Affinity.objects.clear_cache()
        cls.resonances: dict[str, Resonance] = {
            key: ResonanceFactory(name=key.title(), affinity=cls.affinities[AFFINITY_OF[key]])
            for key in KEYS
        }
        cls.outcomes: dict[str, CheckOutcome] = {
            name: ensure_canonical_check_outcome(name) for name in CANONICAL_OUTCOME_LEVELS
        }
        # The bonus check weighs one stat and the act's own check another, so a roll says
        # which of them it borrowed.
        cls.bonus_stat = StatTraitFactory(name="poise")
        cls.bonus_check = CheckTypeFactory(name="Resonance bonus")
        CheckTypeTraitFactory(check_type=cls.bonus_check, trait=cls.bonus_stat, weight=Decimal(1))
        cls.act_stat = StatTraitFactory(name="presence")
        cls.act_check = CheckTypeFactory(name="Intimidate")
        CheckTypeTraitFactory(check_type=cls.act_check, trait=cls.act_stat, weight=Decimal(1))
        for name in CANONICAL_OUTCOME_LEVELS:
            ResonanceCheckAwardFactory(
                outcome_tier=cls.outcomes[name], gain_bonus_percent=0, spend_worth_percent=100
            )
        cls.strengths = {
            rank: KindledStrengthTierFactory(rank=rank, earn_percent=100) for rank in RANKS
        }
        cls.weekly_rows = [
            WeeklyMarkReturnFactory(gained_at_least=threshold, percent_paid=100)
            for threshold in THRESHOLDS
        ]
        # The fatigue capacity of a character comes from these two stats.
        StatTraitFactory(name="composure", category=TraitCategory.SOCIAL)
        StatTraitFactory(name="willpower", category=TraitCategory.META)

    # -- configuration, set at the top of every example ---------------------------------

    def configure(
        self,
        *,
        bonus_percent: int | None = None,
        awards: Mapping[str, int] | int = 10,
        shares: Mapping[int, int] | None = None,
        weekly: tuple[int, ...] = (100, 100, 100, 100),
        gain_fatigue: int = 0,
    ) -> None:
        """Set every config row a mark reads.

        ``bonus_percent`` turns the bonus check on and makes every canonical result worth that
        percent, or turns it off when None. ``awards`` is the kindled deed award for every
        canonical tier, or a mapping by tier name. ``shares`` is the earn percent of each
        strength rank (all 100 when None), ``weekly`` the percent each weekly step pays and
        ``gain_fatigue`` what a gain costs its payer on every affinity.
        """
        cfg = get_resonance_gain_config()
        cfg.bonus_check_type = self.bonus_check if bonus_percent is not None else None
        cfg.save()
        for name in CANONICAL_OUTCOME_LEVELS:
            row = ResonanceCheckAward.objects.get(outcome_tier=self.outcomes[name])
            row.gain_bonus_percent = bonus_percent or 0
            row.save()
            KindledDeedAwardFactory(
                outcome_tier=self.outcomes[name],
                amount=awards[name] if isinstance(awards, Mapping) else awards,
            )
        for rank in RANKS:
            KindledStrengthTierFactory(
                rank=rank, earn_percent=100 if shares is None else shares[rank]
            )
        for step, percent in zip(self.weekly_rows, weekly, strict=True):
            row = WeeklyMarkReturn.objects.get(pk=step.pk)
            row.percent_paid = percent
            row.save()
        for affinity in self.affinities.values():
            affinity.gain_fatigue = gain_fatigue
            affinity.save()

    # -- characters, acts and marks -----------------------------------------------------

    def character(self) -> CharacterSheet:
        """A player character with a Primal aura."""
        sheet = make_player_character(CharacterSheetFactory())
        CharacterAuraFactory(character=sheet, celestial=0, primal=100, abyssal=0)
        return sheet

    def act(  # noqa: PLR0913 - the act's sheet, tier, suggestion, check and target
        self,
        sheet: CharacterSheet,
        tier: str,
        *,
        label: str = "Intimidated Hale",
        suggest: tuple[str, int] | None = None,
        check: bool = False,
        target: CharacterSheet | None = None,
    ) -> RecordedAct:
        """An unmarked act ``sheet`` took, its roll landing on ``tier``.

        ``suggest`` is a ``(resonance key, strength rank)`` a situation suggested for it.
        """
        act = RecordedActFactory(
            character_sheet=sheet,
            outcome=self.outcomes[tier],
            label=label,
            check_type=self.act_check if check else None,
            target_sheet=target,
            fatigue_category=ActionCategory.SOCIAL,
        )
        if suggest is not None:
            key, rank = suggest
            RecordedActSuggestionFactory(
                act=act, resonance=self.resonances[key], strength=self.strengths[rank]
            )
        return act

    def mark(
        self, sheet: CharacterSheet, act: RecordedAct, key: str, *, pose: bool = False
    ) -> MarkResult:
        """Mark ``act`` with ``key``'s resonance in a pose or a journal entry, as the pose and
        journal paths do: check first, then record once the writing is saved."""
        pending = pending_mark_from(
            sheet,
            {"reach_act_id": act.pk, "reach_resonance_id": self.resonances[key].pk},
        )
        assert pending is not None
        if pose:
            return record_pending_mark(
                sheet, pending, interaction=InteractionFactory(persona=sheet.primary_persona)
            )
        return record_pending_mark(sheet, pending, journal_entry=JournalEntryFactory(author=sheet))

    def is_unmarked(self, act: RecordedAct) -> bool:
        """Whether the database still shows ``act`` unmarked."""
        return RecordedAct.objects.filter(pk=act.pk, marked_grant__isnull=True).exists()


class MarkWorthFollowsTheActsAward(_World, HypothesisTestCase):
    """What a mark pays is read from the act's own roll and the strength a situation reached."""

    @settings(max_examples=30, deadline=None)
    @given(
        amounts=st.lists(st.integers(1, 80), min_size=len(TIERS), max_size=len(TIERS)).map(sorted),
        shares=st.fixed_dictionaries({rank: st.integers(0, 150) for rank in RANKS}),
        key=st.sampled_from(KEYS),
        suggested=st.sampled_from((None, *RANKS)),
        pose=st.booleans(),
    )
    def test_a_mark_pays_the_award_times_the_strength_share_and_a_worse_roll_never_more(
        self,
        amounts: list[int],
        shares: dict[int, int],
        key: str,
        suggested: int | None,
        pose: bool,
    ) -> None:
        """Maintainer: "1. agreed." (a mark is worth the act's own award times the share of the
        strength a situation reached) and "I'd always want rolls involved".

        Given any award table that never pays less for a better result, any earn percent on
        each of the three strengths, and an act whose situation suggested the resonance at any
        strength or at none, marking it pays exactly the tier's award times the suggested
        strength's share (the lowest strength's when none was suggested), rounded down and at
        least 1, in a pose or a journal entry alike, for a Celestial, Primal or Abyssal
        resonance. Across the five result tiers a worse roll never pays more.
        """
        self.configure(awards=dict(zip(TIERS, amounts, strict=True)), shares=shares)
        paid = []
        for tier, award in zip(TIERS, amounts, strict=True):
            sheet = self.character()
            act = self.act(sheet, tier, suggest=None if suggested is None else (key, suggested))
            grant = self.mark(sheet, act, key, pose=pose).grant

            share = shares[suggested or 1]
            self.assertEqual(grant.amount, max(1, award * share // 100))
            self.assertEqual(grant.source, GainSource.MARKED_ACT)
            # What situations suggested is dropped once the act is marked.
            self.assertFalse(RecordedActSuggestion.objects.filter(act=act).exists())
            paid.append(grant.amount)
        self.assertEqual(paid, sorted(paid))


class MarkBonusCheck(_World, HypothesisTestCase):
    """A mark rolls the bonus resonance check once, with the act's stat and the affinity's skill."""

    @settings(max_examples=30, deadline=None)
    @given(
        key=st.sampled_from(KEYS),
        percent=st.integers(0, 300),
        amount=st.integers(1, 60),
        pose=st.booleans(),
    )
    def test_a_mark_rolls_one_bonus_check_with_the_acts_stat_and_the_affinitys_skill(
        self, key: str, percent: int, amount: int, pose: bool
    ) -> None:
        """Maintainer: "heroism/villainy/reflection does matter for increasing it".

        Given a mark of any resonance (Celestial, Primal or Abyssal) on an act that rolled a
        check, with any bonus percent the result is worth, the bonus check rolls exactly once,
        borrows the stat that act's own check weighed most, adds the skill of the marked
        resonance's own affinity and no other, and grows the grant by that percent of what
        the mark computed.
        """
        self.configure(bonus_percent=percent, awards=amount)
        sheet = self.character()
        act = self.act(sheet, "Success", check=True)

        with force_every_check_outcome(self.outcomes["Success"]) as capture:
            grant = self.mark(sheet, act, key, pose=pose).grant

        (call,) = [c for c in capture.calls if c.check_type == self.bonus_check]
        self.assertEqual(call.stat_override, self.act_stat.name)
        self.assertEqual(
            call.extra_traits,
            (ExtraTraitTerm(trait=self.skills[AFFINITY_OF[key]], weight=Decimal(1)),),
        )
        self.assertEqual(grant.bonus_percent, percent)
        self.assertEqual(grant.amount, amount + amount * percent // 100)


class AnActPaysOnce(_World, HypothesisTestCase):
    """An act that has been marked cannot be marked again, by anyone, in any writing."""

    @settings(max_examples=30, deadline=None)
    @given(
        first_key=st.sampled_from(KEYS),
        second_key=st.sampled_from(KEYS),
        first_pose=st.booleans(),
        second_pose=st.booleans(),
    )
    def test_a_second_mark_of_the_same_act_pays_nothing(
        self, first_key: str, second_key: str, first_pose: bool, second_pose: bool
    ) -> None:
        """Maintainer: "they point to an act".

        Given an act marked once, in a pose or a journal entry, then marked again with any
        resonance in either kind of writing, or by a mark that was checked before the first
        landed, the second is refused and writes no grant and changes no balance. A character
        who did not take the act cannot point at it at all.
        """
        self.configure()
        sheet = self.character()
        act = self.act(sheet, "Success")
        self.mark(sheet, act, first_key, pose=first_pose)
        grants = ResonanceGrant.objects.filter(
            character_sheet=sheet, nullified_at__isnull=True
        ).count()
        balances = sorted(
            CharacterResonance.objects.filter(character_sheet=sheet).values_list("pk", "balance")
        )

        with self.assertRaises(MarkError):
            self.mark(sheet, act, second_key, pose=second_pose)
        stale = PendingMark(act_id=act.pk, resonance_id=self.resonances[second_key].pk)
        with self.assertRaises(MarkError):
            record_pending_mark(sheet, stale, journal_entry=JournalEntryFactory(author=sheet))
        with self.assertRaises(MarkError):
            pending_mark_from(
                self.character(),
                {"reach_act_id": act.pk, "reach_resonance_id": self.resonances[second_key].pk},
            )

        self.assertEqual(
            ResonanceGrant.objects.filter(character_sheet=sheet, nullified_at__isnull=True).count(),
            grants,
        )
        self.assertEqual(
            sorted(
                CharacterResonance.objects.filter(character_sheet=sheet).values_list(
                    "pk", "balance"
                )
            ),
            balances,
        )


class OneMarkPerWriting(_World, HypothesisTestCase):
    """A pose or a journal entry carries one mark, however many acts the player has."""

    @settings(max_examples=20, deadline=None)
    @given(
        first_key=st.sampled_from(KEYS),
        second_key=st.sampled_from(KEYS),
        pose=st.booleans(),
    )
    def test_a_second_mark_in_the_same_pose_or_entry_is_refused_and_consumes_nothing(
        self, first_key: str, second_key: str, pose: bool
    ) -> None:
        """Maintainer: "they point to an act" (one writing, one act).

        Given two unmarked acts and one pose or journal entry that has already carried a mark,
        a second mark carried by that same writing is refused cleanly before anything is paid:
        no grant is written, the second act stays unmarked and pointable, and the same acts
        can then be marked in writings of their own.
        """
        self.configure()
        sheet = self.character()
        first_act, second_act = self.act(sheet, "Success"), self.act(sheet, "Success")
        interaction = InteractionFactory(persona=sheet.primary_persona)
        entry = JournalEntryFactory(author=sheet)
        writing = {"interaction": interaction} if pose else {"journal_entry": entry}

        def mark_in(act: RecordedAct, key: str, **where: object) -> MarkResult:
            pending = pending_mark_from(
                sheet, {"reach_act_id": act.pk, "reach_resonance_id": self.resonances[key].pk}
            )
            return record_pending_mark(sheet, pending, **where)

        mark_in(first_act, first_key, **writing)
        grants = ResonanceGrant.objects.filter(character_sheet=sheet).count()
        with self.assertRaises(MarkError):
            mark_in(second_act, second_key, **writing)
        self.assertEqual(ResonanceGrant.objects.filter(character_sheet=sheet).count(), grants)
        self.assertTrue(self.is_unmarked(second_act))

        other = {"journal_entry": entry} if pose else {"interaction": interaction}
        self.assertTrue(mark_in(second_act, second_key, **other).paid)


class JournalAndPoseAreOneSystem(_World, HypothesisTestCase):
    """A journal entry and a pose pointed at one act pay the same."""

    @settings(max_examples=30, deadline=None)
    @given(
        tier=st.sampled_from(TIERS),
        amount=st.integers(1, 80),
        key=st.sampled_from(KEYS),
        suggested=st.sampled_from((None, *RANKS)),
        shares=st.fixed_dictionaries({rank: st.integers(0, 150) for rank in RANKS}),
    )
    def test_a_journal_mark_and_a_pose_mark_of_the_same_kind_of_act_pay_the_same(
        self, tier: str, amount: int, key: str, suggested: int | None, shares: dict[int, int]
    ) -> None:
        """Maintainer: "Doesn't that prevent us from unifying the systems?"

        Given two characters who took the same kind of act (the same result, the same
        suggestion, the same label) and mark it with the same resonance, one in a journal
        entry and one in a pose, the two grants are the same source, the same amount and the
        same label, both resonance balances are equal, and each act records only the writing
        that carried its mark.
        """
        self.configure(awards=amount, shares=shares)
        suggest = None if suggested is None else (key, suggested)
        by_journal, by_pose = self.character(), self.character()
        journal_act = self.act(by_journal, tier, suggest=suggest)
        pose_act = self.act(by_pose, tier, suggest=suggest)

        journal_grant = self.mark(by_journal, journal_act, key, pose=False).grant
        pose_grant = self.mark(by_pose, pose_act, key, pose=True).grant

        self.assertEqual(journal_grant.source, pose_grant.source)
        self.assertEqual(journal_grant.amount, pose_grant.amount)
        self.assertEqual(journal_grant.deed_label, pose_grant.deed_label)
        balance = {
            sheet.pk: CharacterResonance.objects.get(
                character_sheet=sheet, resonance=self.resonances[key]
            ).balance
            for sheet in (by_journal, by_pose)
        }
        self.assertEqual(balance[by_journal.pk], balance[by_pose.pk])
        journal_act.refresh_from_db()
        pose_act.refresh_from_db()
        self.assertIsNotNone(journal_act.marked_journal_entry_id)
        self.assertIsNone(journal_act.marked_interaction_id)
        self.assertIsNotNone(pose_act.marked_interaction_id)
        self.assertIsNone(pose_act.marked_journal_entry_id)


class FatigueFallsOnTheRightPayer(_World, HypothesisTestCase):
    """A gain tires one character, never past what they can bear, and shrinks to fit."""

    def run_scenario(  # noqa: PLR0913 - one mark's character, cost and how worn each side is
        self,
        *,
        key: str,
        stats: tuple[int, int] | None,
        gainer_worn: int,
        target_worn: int,
        target_is_character: bool,
        pose: bool,
    ) -> dict:
        """Mark one act and read back the payer, her room before, what was paid and every pool.

        ``stats`` is (composure, willpower) in tens, or None when no stats are set up. The room
        is the spec's word: capacity minus what is already taken minus one, never below 0.
        """
        gainer, target = self.character(), self.character()
        pools = {}
        for sheet, worn in ((gainer, gainer_worn), (target, target_worn)):
            if stats is not None:
                setup_stat(sheet.character, "composure", stats[0] * 10, TraitCategory.SOCIAL)
                setup_stat(sheet.character, "willpower", stats[1] * 10, TraitCategory.META)
            capacity = get_fatigue_capacity(sheet, ActionCategory.SOCIAL)
            pool = get_or_create_fatigue_pool(sheet)
            pool.set_current(ActionCategory.SOCIAL, worn % (capacity + 3) if capacity else 0)
            pool.save()
            pools[sheet.pk] = (pool, capacity)
        before = {pk: pool.get_current(ActionCategory.SOCIAL) for pk, (pool, _) in pools.items()}
        act = self.act(gainer, "Success", target=target if target_is_character else None)
        # Primal and Celestial tire the gainer; Abyssal tires the target, and no one when the
        # target is a game-run opponent with no sheet.
        payer = (target if target_is_character else None) if key == "cruelty" else gainer
        capacity = pools[payer.pk][1] if payer is not None else 0
        room = max(0, capacity - before[payer.pk] - 1) if capacity > 0 else None
        try:
            result = self.mark(gainer, act, key, pose=pose)
            paid, line = result.grant.amount, result.line
        except MarkError as exc:
            paid, line = None, exc.user_message
        return {
            "payer": payer,
            "gainer": gainer,
            "room": room,
            "paid": paid,
            "line": line,
            "act": act,
            "before": before,
            "after": {
                pk: pool.get_current(ActionCategory.SOCIAL) for pk, (pool, _) in pools.items()
            },
            "capacity": {pk: cap for pk, (_pool, cap) in pools.items()},
        }

    @settings(max_examples=40, deadline=None)
    @given(
        key=st.sampled_from(KEYS),
        base=st.integers(1, 60),
        cost=st.integers(1, 12),
        stats_set_up=st.booleans(),
        composure=st.integers(1, 4),
        willpower=st.integers(1, 3),
        gainer_worn=st.integers(0, 60),
        target_worn=st.integers(0, 60),
        target_is_character=st.booleans(),
        pose=st.booleans(),
    )
    def test_the_payer_follows_the_affinity_and_no_gain_reaches_full_capacity(  # noqa: PLR0913
        self,
        key: str,
        base: int,
        cost: int,
        stats_set_up: bool,
        composure: int,
        willpower: int,
        gainer_worn: int,
        target_worn: int,
        target_is_character: bool,
        pose: bool,
    ) -> None:
        """Maintainer: "for primal, the person getting it, for abyssal their victim, for
        celestial the caster".

        Given a gainer and a target with any stats (or none set up), any fatigue already taken
        and a gain that costs any amount: only the payer's pool changes, and a payer with stats
        set up ends below capacity, so no gain ever takes anyone to 100 percent. What is paid is
        never more than the act's base, and it is the whole base when there is no payer (a
        game-run opponent, or stats not set up) or when the payer's room covers the cost. A
        payer with no room pays nothing, the mark is refused and the act is not used.
        """
        self.configure(awards=base, gain_fatigue=cost)
        stats = (composure, willpower) if stats_set_up else None

        out = self.run_scenario(
            key=key,
            stats=stats,
            gainer_worn=gainer_worn,
            target_worn=target_worn,
            target_is_character=target_is_character,
            pose=pose,
        )

        payer = out["payer"]
        for pk, after in out["after"].items():
            if payer is None or pk != payer.pk:
                self.assertEqual(after, out["before"][pk])
        if payer is not None and out["capacity"][payer.pk] > 0:
            self.assertLess(out["after"][payer.pk], out["capacity"][payer.pk])
        if out["paid"] is not None:
            self.assertLessEqual(out["paid"], base)
            if out["room"] is None or out["room"] >= cost:
                self.assertEqual(out["paid"], base)
            self.assertEqual("had little left to give" in out["line"], out["paid"] < base)
            self_paid = payer is not None and payer.pk == out["gainer"].pk
            self.assertEqual(
                "and you are wearier" in out["line"],
                self_paid and out["after"][payer.pk] > out["before"][payer.pk],
            )
        if out["room"] == 0:
            self.assertIsNone(out["paid"])
            self.assertTrue(self.is_unmarked(out["act"]))
            self.assertIn("does not grow. The act stays on your list.", out["line"])
        if out["paid"] is None:
            self.assertTrue(self.is_unmarked(out["act"]))

    @settings(max_examples=30, deadline=None)
    @given(
        key=st.sampled_from(KEYS),
        base=st.integers(1, 60),
        cost=st.integers(1, 12),
        worn_a=st.integers(0, 60),
        worn_b=st.integers(0, 60),
    )
    def test_a_payer_with_less_room_never_pays_more(
        self, key: str, base: int, cost: int, worn_a: int, worn_b: int
    ) -> None:
        """The amount paid never rises as the payer's room falls.

        Two identical marks against payers who differ only in how worn they already are: the one
        with the room of the other or more is paid at least as much.
        """
        self.configure(awards=base, gain_fatigue=cost)

        outcomes = [
            self.run_scenario(
                key=key,
                stats=(2, 2),
                gainer_worn=worn,
                target_worn=worn,
                target_is_character=True,
                pose=False,
            )
            for worn in (worn_a, worn_b)
        ]

        first, second = outcomes
        if first["room"] >= second["room"]:
            self.assertGreaterEqual(first["paid"] or 0, second["paid"] or 0)
        else:
            self.assertGreaterEqual(second["paid"] or 0, first["paid"] or 0)


class WeeklyTableCutsRepeatMarks(_World, HypothesisTestCase):
    """Each further mark in a game week pays no more than the last, and an undone mark stops
    counting."""

    @settings(max_examples=25, deadline=None)
    @given(
        percents=st.lists(st.integers(0, 100), min_size=4, max_size=4).map(
            lambda values: tuple(sorted(values, reverse=True))
        ),
        amount=st.integers(5, 40),
        count=st.integers(1, 8),
        key=st.sampled_from(KEYS),
    )
    def test_marks_of_equal_worth_pay_no_more_than_the_last_and_an_undone_one_stops_counting(
        self, percents: tuple[int, ...], amount: int, count: int, key: str
    ) -> None:
        """Maintainer: "diminishing returns".

        Given a weekly table whose steps never pay more as she has gained more, and a run of
        marks of acts of equal worth in one game week, each mark pays the percent of its
        amount that the step she had reached allows, so no mark pays more than the one before;
        a step that pays 0 percent refuses the mark and the act stays unmarked, while any step
        above 0 pays at least 1. Grants
        from other sources (an endorsement, a staff grant) never count toward the table. A
        mark that is then undone (``nullified_at`` set on its grant) stops counting: she
        stands where she did before it, and the next mark pays what that step allows.
        """
        self.configure(awards=amount, weekly=percents)
        sheet = self.character()
        ResonanceGrantFactory(
            character_sheet=sheet,
            resonance=self.resonances[key],
            amount=500,
            source=GainSource.STAFF_GRANT,
        )
        self.assertEqual(weekly_percent_paid(sheet).gained, 0)

        def allowed(gained: int) -> int:
            step = max(t for t in THRESHOLDS if t <= gained)
            percent = percents[THRESHOLDS.index(step)]
            # A step above 0 percent pays at least 1; only a 0 percent step pays nothing.
            return max(1, amount * percent // 100) if percent > 0 else 0

        paid: list[int] = []
        for _ in range(count):
            act = self.act(sheet, "Success")
            expected = allowed(sum(paid))
            if expected == 0:
                with self.assertRaises(MarkError):
                    self.mark(sheet, act, key)
                self.assertTrue(self.is_unmarked(act))
                continue
            grant = self.mark(sheet, act, key).grant
            self.assertEqual(grant.amount, expected)
            paid.append(grant.amount)
        self.assertEqual(paid, sorted(paid, reverse=True))
        self.assertEqual(weekly_percent_paid(sheet).gained, sum(paid))

        if paid:
            last = ResonanceGrant.objects.filter(
                character_sheet=sheet, source=GainSource.MARKED_ACT
            ).latest("pk")
            last.nullified_at = timezone.now()
            last.save(update_fields=["nullified_at"])
            self.assertEqual(weekly_percent_paid(sheet).gained, sum(paid[:-1]))
            act = self.act(sheet, "Success")
            if allowed(sum(paid[:-1])) == 0:
                with self.assertRaises(MarkError):
                    self.mark(sheet, act, key)
            else:
                self.assertEqual(self.mark(sheet, act, key).grant.amount, allowed(sum(paid[:-1])))


class AJournalEntrySurvivesARefusedMark(_World, HypothesisTestCase):
    """A journal entry whose mark is refused late stays written, and says why."""

    @settings(max_examples=12, deadline=None)
    @given(percent=st.sampled_from((0, 100)), key=st.sampled_from(KEYS))
    def test_a_refused_mark_keeps_the_entry_the_counters_and_the_act(
        self, percent: int, key: str
    ) -> None:
        """Maintainer: "they point to an act and if it doesn't make sense, well, we could
        nullify it and chide them." A refused mark must not cost her the entry she wrote.

        Given a week whose table pays her marks at ``percent``, a journal entry that points at
        an act: at 100 percent the entry is written and the mark pays; at 0 percent the week
        refuses the mark, and the entry is still written and still counted (the weekly post
        counter holds the same number in the cache and in the database), the act stays
        unmarked and pointable, and the writer reads the refusal beside the entry, in the
        entry's message and in ``mark_line``, with ``mark_recorded`` false.
        """
        self.configure(weekly=(percent, percent, percent, percent))
        sheet = self.character()
        act = self.act(sheet, "Success")

        result = CreateJournalEntryAction().execute(
            actor=sheet.character,
            title="The night at the Lantern",
            body="I said what I meant.",
            is_public=False,
            reach_act_id=act.pk,
            reach_resonance_id=self.resonances[key].pk,
        )

        self.assertTrue(result.success, result.message)
        self.assertEqual(JournalEntry.objects.filter(author=sheet).count(), 1)
        self.assertEqual(result.data["mark_recorded"], percent > 0)
        self.assertEqual(self.is_unmarked(act), percent == 0)
        self.assertEqual(
            ResonanceGrant.objects.filter(
                character_sheet=sheet, source=GainSource.MARKED_ACT
            ).count(),
            1 if percent > 0 else 0,
        )
        if percent == 0:
            self.assertIn("stays on your list", result.data["mark_line"])
            self.assertIn(result.data["mark_line"], result.message)
        tracker = WeeklyJournalXP.objects.get(character_sheet=sheet)
        stored = WeeklyJournalXP.objects.filter(character_sheet=sheet).values_list(
            "posts_this_week", flat=True
        )
        self.assertEqual(list(stored), [1])
        self.assertEqual(tracker.posts_this_week, 1)


class ActNumbersNeverShift(_World, HypothesisTestCase):
    """The number a telnet player types is the act's own id, so a new act cannot redirect it."""

    @settings(max_examples=15, deadline=None)
    @given(
        count=st.integers(1, 26),
        newer=st.integers(0, 3),
        pick=st.integers(0, 19),
        key=st.sampled_from(KEYS),
    )
    def test_the_listed_id_marks_the_listed_act_whatever_lands_after_listing(
        self, count: int, newer: int, pick: int, key: str
    ) -> None:
        """Maintainer: "they point to an act".

        Given any number of acts, the list shows the newest twenty, each behind its own id,
        and says how many older acts it leaves out. Whatever the player types after the colon
        marks the act that carried that id when the list was read, however many newer acts land
        between listing and posing; an id that is not one of her unmarked acts is refused.
        """
        self.configure()
        sheet = self.character()
        acts = [self.act(sheet, "Success", label=f"Did thing {n}") for n in range(count)]
        listed, older = pointable_acts_page(sheet, 20)
        text = "\n".join(act_lines(listed, older))

        newest = acts[::-1][:20]
        self.assertEqual([act.pk for act in listed], [act.pk for act in newest])
        for act in newest:
            self.assertIn(f"  {act.pk}. {act.label} (", text)
        self.assertEqual(older, max(count - 20, 0))
        self.assertEqual("older" in text, count > 20)

        chosen = listed[pick % len(listed)]
        for _ in range(newer):
            self.act(sheet, "Success")
        kwargs, rest = reach_kwargs_and_rest(
            f"{self.resonances[key].name}:{chosen.pk}=waves", sheet
        )
        self.assertEqual(kwargs["reach_act_id"], chosen.pk)
        self.assertEqual(rest, "waves")
        stranger = self.act(self.character(), "Success")
        with self.assertRaises(CommandError):
            reach_kwargs_and_rest(f"{self.resonances[key].name}:{stranger.pk}=waves", sheet)

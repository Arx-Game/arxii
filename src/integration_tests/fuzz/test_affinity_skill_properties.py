"""Fuzz: the rules of Villainy, Heroism and Reflection, as properties (#5308).

Staff link one Magic skill to each affinity. Every earned resonance gain then rolls one bonus
check per affinity it pays (the act's stat plus that affinity's skill), a good result grows the
gain, and every pull rolls a worth check with the same skill. Each class below holds one rule of
that design, quoted in the maintainer's words from the issue. Every example builds its
characters fresh with factories and uses our own functions (``grant_resonance``,
``award_kindled_deeds``, ``apply_ritual_bond``, ``spend_resonance_for_pull``);
the shared catalog lives once in ``setUpTestData`` (a Hypothesis test's own ``setUp`` runs
outside any transaction, so it would leak rows between examples).

How outcomes are pinned: the bonus check is a real ``perform_check``. ``force_check_outcome``
(``world.checks.test_helpers``) names the result of the first rolls, and its ``calls`` list
counts every roll and shows the skill each one added, so no property patches one of our own
functions. A property that does not care which result lands rewrites the award table to the
same percent on every tier, or forces every roll to one result.

``_World`` is the shared builder: the three affinities each linked to a skill, two resonances
each, a bonus check type that weighs one stat, an award row on every canonical result tier and
one result tier with no row. Every example sets the configuration it needs first (the bonus
check on or off, the awards, the floors), because the config rows are idmapper singletons that
an earlier example may have changed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal

from hypothesis import given, settings, strategies as st
from hypothesis.extra.django import TestCase as HypothesisTestCase

from evennia_extensions.factories import ObjectDBFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import CharacterSheet
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.checks.services import perform_check
from world.checks.test_helpers import (
    CheckCapture,
    force_check_outcome,
    force_every_check_outcome,
    make_player_character,
)
from world.checks.types import ExtraTraitTerm
from world.covenants.perks.constants import Situation
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import (
    CraftedItemRecipeFactory,
    CraftingRecipeFactory,
    CraftingRecipeModifierFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
    QualityTierFactory,
    TemplateSlotFactory,
)
from world.items.services.equip import equip_item
from world.magic.constants import (
    GainSource,
    KindlingActKind,
    RitualExecutionKind,
)
from world.magic.factories import (
    AnimaRitualPerformanceFactory,
    AnimaRitualResonanceAwardFactory,
    CharacterAnimaFactory,
    CharacterAuraFactory,
    CharacterResonanceFactory,
    KindledDeedAwardFactory,
    KindledStrengthTierFactory,
    KindlingSituationFactory,
    ResonanceCheckAwardFactory,
    ResonanceFactory,
    RitualCheckConfigFactory,
    RitualFactory,
    ThreadFactory,
    ThreadPullCostFactory,
    ThreadPullEffectFactory,
    ensure_conversion_pairs,
)
from world.magic.models import (
    Affinity,
    CharacterResonance,
    Resonance,
    ResonanceCheckAward,
    ResonanceGrant,
    TrickleAccrual,
)
from world.magic.services import preview_resonance_pull, spend_resonance_for_pull
from world.magic.services.gain import (
    get_resonance_gain_config,
    residence_trickle_tick,
    set_residence,
    tag_room_resonance,
    waiting_trickles,
)
from world.magic.services.kindling import award_kindled_deeds
from world.magic.services.resonance import grant_resonance, seed_creation_resonance
from world.magic.services.ritual_bond import apply_ritual_bond
from world.magic.types import PullActionContext
from world.magic.types.kindling import KindlingAct
from world.magic.types.resonance_checks import NO_GAIN_BONUS
from world.mechanics.services import ensure_skill_target
from world.missions.factories import (
    MissionInstanceFactory,
    MissionOptionFactory,
    MissionThemeFactory,
)
from world.skills.factories import MagicSkillFactory
from world.traits.constants import CANONICAL_OUTCOME_LEVELS, TraitType
from world.traits.factories import CheckOutcomeFactory, StatTraitFactory
from world.traits.models import CheckOutcome, PointConversionRange, Trait
from world.traits.services import ensure_canonical_check_outcome

# The six resonances, two per affinity. The key is what a strategy draws.
RESONANCE_KEYS = ("heroic 1", "heroic 2", "primal 1", "primal 2", "villain 1", "villain 2")
AFFINITY_OF = {
    "heroic 1": "celestial",
    "heroic 2": "celestial",
    "primal 1": "primal",
    "primal 2": "primal",
    "villain 1": "abyssal",
    "villain 2": "abyssal",
}
# The result tiers a bonus check can land on: every canonical one, plus one the staff table
# has no row for.
UNROWED = "Unlisted result"
ALL_TIERS = (*sorted(CANONICAL_OUTCOME_LEVELS), UNROWED)

# An award table where each tier is worth a different percent, so a grant's percent says which
# result its roll landed on.
RANKED_GAINS = {name: 10 * rank for rank, name in enumerate(ALL_TIERS, start=1)}

# Rolled sources whose grant names no typed row, so a property can grant them with a bare call.
BARE_ROLLED_SOURCES = (
    GainSource.MISSION_REPORT,
    GainSource.STAKE_REWARD,
    GainSource.COMBO_DISCOVERY,
    GainSource.COMPROMISE,
    GainSource.SINEATING,
    GainSource.MIRE_PURIFIED,
    GainSource.SUCCUMB_BONUS,
    GainSource.SINEATER_FALL,
)
# Caller-rolled sources whose grant names no typed row (a kindled deed names its situation).
BARE_CALLER_ROLLED_SOURCES = (GainSource.ANIMA_RITUAL, GainSource.TRICKLE_HARVEST)
# The moves nobody earned, which the maintainer named: each takes no bonus check.
UNEARNED_SOURCES = (
    GainSource.STAFF_GRANT,
    GainSource.FALL_CONVERSION,
    GainSource.DRIFT_CORRECTION,
    GainSource.CORRUPTION_CLEANSING,
)


@st.composite
def aura_splits(draw: st.DrawFn) -> tuple[int, int, int]:
    """Celestial / Primal / Abyssal percents of an aura that sum to 100."""
    celestial = draw(st.integers(0, 100))
    primal = draw(st.integers(0, 100 - celestial))
    return celestial, primal, 100 - celestial - primal


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
        cls.skills: dict[str, Trait] = {}
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
            for key in RESONANCE_KEYS
        }
        cls.outcomes: dict[str, CheckOutcome] = {
            name: ensure_canonical_check_outcome(name) for name in CANONICAL_OUTCOME_LEVELS
        }
        cls.outcomes[UNROWED] = CheckOutcomeFactory(name=UNROWED, success_level=0)
        cls.bonus_stat = StatTraitFactory(name="willpower")
        cls.bonus_check = CheckTypeFactory(name="Resonance bonus")
        CheckTypeTraitFactory(check_type=cls.bonus_check, trait=cls.bonus_stat, weight=Decimal(1))
        # One award row per canonical tier. An example rewrites them in place (never deletes
        # and recreates: the idmapper would hand back the old row), and UNROWED has none.
        for name in CANONICAL_OUTCOME_LEVELS:
            ResonanceCheckAwardFactory(
                outcome_tier=cls.outcomes[name], gain_bonus_percent=0, spend_worth_percent=100
            )

    # -- configuration, set at the top of every example ---------------------------------

    def configure(
        self,
        *,
        bonus: bool = True,
        gain: Mapping[str, int] | int = 0,
        worth: Mapping[str, int] | int = 100,
        floor: int = 0,
    ) -> None:
        """Turn the bonus check on or off and write every canonical tier's award row.

        ``gain`` and ``worth`` are a percent for every tier, or a mapping by tier name.
        ``floor`` is the least worth every affinity gives a pull.
        """
        cfg = get_resonance_gain_config()
        cfg.bonus_check_type = self.bonus_check if bonus else None
        cfg.save()
        for name in CANONICAL_OUTCOME_LEVELS:
            row = ResonanceCheckAward.objects.get(outcome_tier=self.outcomes[name])
            row.gain_bonus_percent = gain[name] if isinstance(gain, Mapping) else gain
            row.spend_worth_percent = worth[name] if isinstance(worth, Mapping) else worth
            row.save()
        for affinity in self.affinities.values():
            affinity.spend_worth_floor_percent = floor
            affinity.save()

    def bonus_calls(self, capture: CheckCapture) -> list:
        """The rolls of ``capture`` that were a bonus resonance check."""
        return [call for call in capture.calls if call.check_type == self.bonus_check]

    # -- characters -------------------------------------------------------------------

    def character(
        self,
        *,
        split: tuple[int, int, int] = (0, 100, 0),
        holds: Sequence[str] = (),
        anima: int = 0,
    ) -> CharacterSheet:
        """A player character with an aura split and the resonances in ``holds``."""
        sheet = make_player_character(CharacterSheetFactory())
        celestial, primal, abyssal = split
        CharacterAuraFactory(
            character=sheet,
            celestial=Decimal(celestial),
            primal=Decimal(primal),
            abyssal=Decimal(abyssal),
        )
        for key in holds:
            CharacterResonanceFactory(character_sheet=sheet, resonance=self.resonances[key])
        if anima:
            CharacterAnimaFactory(character=sheet, current=anima, maximum=anima)
        return sheet

    def balance(self, sheet: CharacterSheet, key: str) -> int:
        row = CharacterResonance.objects.filter(
            character_sheet=sheet, resonance=self.resonances[key]
        ).first()
        return row.balance if row is not None else 0

    # -- a kindled deed ---------------------------------------------------------------

    def kindle(self, keys: Sequence[str]) -> KindlingAct:
        """Author a choice that pays each of ``keys`` and return the act that takes it.

        The act takes a mission option whose themes each carry a "mission theme" situation on
        one of ``keys``: an authored choice, the only kind that pays at once (#5327). The one
        strength tier reaches at once and earns the whole award.
        """
        KindledStrengthTierFactory(rank=1, min_severity=1, earn_percent=100)
        option = MissionOptionFactory()
        for key in keys:
            theme = MissionThemeFactory()
            option.themes.add(theme)
            KindlingSituationFactory(
                resonance=self.resonances[key],
                situation=Situation.MISSION_THEME,
                mission_theme=theme,
                strength=1,
            )
        return KindlingAct(
            kind=KindlingActKind.MISSION_OPTION,
            mission_option=option,
            label="Threatened a prisoner",
        )

    def deed_award(self, amount: int) -> None:
        """What a deed earns at every canonical result: ``amount``."""
        for name in CANONICAL_OUTCOME_LEVELS:
            KindledDeedAwardFactory(outcome_tier=self.outcomes[name], amount=amount)

    def do_deed(
        self, sheet: CharacterSheet, act: KindlingAct, tier: str = "Success"
    ) -> list[ResonanceGrant]:
        """The sheet takes ``act`` (from ``kindle``) in a mission, its roll landing on ``tier``."""
        return award_kindled_deeds(
            sheet, act=act, outcome=self.outcomes[tier], mission=MissionInstanceFactory()
        )


def _gain(sheet: CharacterSheet, key: str, world: _World, **kwargs: object) -> ResonanceGrant:
    """Grant ``key``'s resonance once through ``grant_resonance`` and return the ledger row."""
    ledger: list[ResonanceGrant] = []
    grant_resonance(
        sheet,
        world.resonances[key],
        ledger_out=ledger,
        **kwargs,  # ty: ignore[invalid-argument-type]
    )
    return ledger[-1]


class NeverLessThanTheAct(_World, HypothesisTestCase):
    """A poor roll never takes anything away."""

    @settings(max_examples=40, deadline=None)
    @given(
        tier=st.sampled_from(ALL_TIERS),
        percents=st.fixed_dictionaries({name: st.integers(0, 300) for name in ALL_TIERS}),
        key=st.sampled_from(RESONANCE_KEYS),
        source=st.sampled_from(BARE_ROLLED_SOURCES),
        amount=st.integers(1, 60),
    )
    def test_a_gain_is_never_smaller_than_it_would_be_with_no_bonus_check(
        self, tier: str, percents: dict[str, int], key: str, source: str, amount: int
    ) -> None:
        """Maintainer's inferred rule, agreed 2026-11-23: "A poor bonus check never gives less
        than the act earned. It only adds, so an untrained character cannot escape a consequence
        by rolling badly."

        Given any award table, any result tier (one with no award row too), any rolled source
        and any amount, the gain the bonus check grew is at least the gain with no bonus
        (``NO_GAIN_BONUS``, the same call with the check's result set to nothing), and it is
        exactly that plus the tier's percent of it, or the plain gain where the tier has no row.
        """
        self.configure(gain=percents)
        sheet = self.character()

        plain = _gain(sheet, key, self, amount=amount, source=source, gain_bonus=NO_GAIN_BONUS)
        with force_check_outcome(self.outcomes[tier]) as capture:
            grown = _gain(sheet, key, self, amount=amount, source=source)

        self.assertGreaterEqual(grown.amount, plain.amount)
        added = percents[tier] if tier != UNROWED else 0
        self.assertEqual(grown.amount, plain.amount + plain.amount * added // 100)
        self.assertEqual(grown.bonus_percent, added)
        self.assertEqual(len(self.bonus_calls(capture)), 1)


class SkillFollowsTheSituation(_World, HypothesisTestCase):
    """The affinity comes from what was earned, never from the aura of who earned it."""

    @settings(max_examples=40, deadline=None)
    @given(
        key=st.sampled_from(RESONANCE_KEYS),
        splits=st.lists(aura_splits(), min_size=2, max_size=3),
        source=st.sampled_from(BARE_ROLLED_SOURCES),
    )
    def test_the_skill_rolled_is_the_earned_resonances_affinitys_whatever_the_aura(
        self, key: str, splits: list[tuple[int, int, int]], source: str
    ) -> None:
        """Maintainer: "the fact her resonance is celestial isn't what makes her add Heroism.
        It should be derived from the situation: trying to inspire and give people hope is
        Celestial and gives Celestial resonance; it's an action that would do so, regardless of
        who's doing it."

        Given any resonance and several characters with any aura splits (Celestial-main,
        Abyssal-main, anything), each earning it, every one's bonus check adds the skill of the
        resonance's own affinity, and only that skill: a Cruelty-type gain rolls Villainy for a
        hero and a villain alike.
        """
        self.configure()
        expected = self.skills[AFFINITY_OF[key]]
        for split in splits:
            sheet = self.character(split=split)
            with force_every_check_outcome(self.outcomes["Success"]) as capture:
                _gain(sheet, key, self, amount=5, source=source)

            (call,) = self.bonus_calls(capture)
            self.assertEqual(
                call.extra_traits, (ExtraTraitTerm(trait=expected, weight=Decimal(1)),)
            )


class OneCheckPerAffinity(_World, HypothesisTestCase):
    """An act that pays several resonances rolls once for each affinity it pays."""

    @settings(max_examples=40, deadline=None)
    @given(keys=st.sets(st.sampled_from(RESONANCE_KEYS), min_size=1), amount=st.integers(1, 40))
    def test_one_act_paying_n_resonances_across_k_affinities_rolls_k_checks(
        self, keys: set[str], amount: int
    ) -> None:
        """Maintainer: "Always a check per affinity when doing resonance gain."

        Given an act that pays N resonances across K affinities (a chosen deed, which pays every
        resonance an authored choice names), it rolls the bonus check exactly K times. Every
        grant of one affinity shares the one roll's result and percent, and two affinities
        never share a result (each roll is given a different one here).
        """
        sheet = self.character(holds=sorted(keys))
        self.configure(gain=RANKED_GAINS)
        act = self.kindle(sorted(keys))
        self.deed_award(amount)
        distinct = [self.outcomes[name] for name in ("Failure", "Success", "Critical Success")]

        with force_check_outcome(*distinct) as capture:
            grants = self.do_deed(sheet, act)

        affinities = {AFFINITY_OF[key] for key in keys}
        self.assertEqual(len(grants), len(keys))
        self.assertEqual(len(self.bonus_calls(capture)), len(affinities))
        by_affinity: dict[int, set[tuple[int | None, int]]] = {}
        for grant in grants:
            self.assertEqual(grant.bonus_percent, RANKED_GAINS[grant.bonus_outcome.name])
            by_affinity.setdefault(grant.resonance.affinity_id, set()).add(
                (grant.bonus_outcome_id, grant.bonus_percent)
            )
        self.assertTrue(all(len(results) == 1 for results in by_affinity.values()), by_affinity)
        outcomes = [next(iter(results))[0] for results in by_affinity.values()]
        self.assertEqual(len(set(outcomes)), len(affinities))


class MovesNobodyEarnedPayWhatTheyDid(_World, HypothesisTestCase):
    """Staff grants, creation, drift correction, Fall conversions and cleansing pay as before."""

    @settings(max_examples=40, deadline=None)
    @given(
        source=st.sampled_from(UNEARNED_SOURCES),
        key=st.sampled_from(RESONANCE_KEYS),
        amount=st.integers(1, 60),
        gain=st.integers(1, 300),
    )
    def test_an_unearned_move_pays_its_plain_amount_and_rolls_nothing(
        self, source: str, key: str, amount: int, gain: int
    ) -> None:
        """Maintainer: "Skip those, it's for resonance that's earned."

        Given any amount and a bonus check that would add up to 300 percent, a staff grant, a
        Fall conversion, a drift correction and a cleansing each write exactly the amount they
        were asked for (the affinities earn at the default rate), record no bonus, roll
        nothing, and refuse a bonus result passed to them.
        """
        self.configure(gain=gain)
        sheet = self.character()

        with force_every_check_outcome(self.outcomes["Critical Success"]) as capture:
            grant = _gain(sheet, key, self, amount=amount, source=source)
            with self.assertRaises(ValueError):
                _gain(sheet, key, self, amount=amount, source=source, gain_bonus=NO_GAIN_BONUS)

        self.assertEqual(grant.amount, amount)
        self.assertEqual((grant.bonus_outcome, grant.bonus_percent), (None, 0))
        self.assertEqual(self.bonus_calls(capture), [])

    @settings(max_examples=20, deadline=None)
    @given(
        key=st.sampled_from(RESONANCE_KEYS), lifetime=st.integers(1, 60), gain=st.integers(1, 300)
    )
    def test_a_creation_pick_seeds_exactly_its_lifetime_with_no_roll(
        self, key: str, lifetime: int, gain: int
    ) -> None:
        """Maintainer: "Skip those, it's for resonance that's earned." Character creation
        seeds a pick's lifetime and nothing more, whatever the bonus check is worth."""
        self.configure(gain=gain)
        sheet = self.character()

        with force_every_check_outcome(self.outcomes["Critical Success"]) as capture:
            grant = seed_creation_resonance(sheet, self.resonances[key], lifetime)

        self.assertEqual(grant.amount, lifetime)
        self.assertEqual((grant.bonus_outcome, grant.bonus_percent), (None, 0))
        self.assertEqual(self.bonus_calls(capture), [])


def _tier_name(outcome: CheckOutcome) -> str:
    return outcome.name


class TricklesWaitForTheRitual(_World, HypothesisTestCase):
    """A day's trickle piles up and only an anima ritual turns it into resonance."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        for name in CANONICAL_OUTCOME_LEVELS:
            AnimaRitualResonanceAwardFactory(outcome_tier=cls.outcomes[name], amount=10)

    def performer_with_a_residence(self, keys: Sequence[str]) -> tuple[CharacterSheet, int]:
        """A player character who holds ``keys`` and lives in a room tagged with each, and the
        day's trickle per resonance."""
        sheet = self.character(split=(30, 40, 30), holds=["primal 1", "villain 1", *keys])
        room = RoomProfileFactory()
        for key in keys:
            tag_room_resonance(room, self.resonances[key])
        set_residence(sheet, room)
        return sheet, get_resonance_gain_config().residence_daily_trickle_per_resonance

    @settings(max_examples=25, deadline=None)
    @given(
        keys=st.sets(st.sampled_from(RESONANCE_KEYS), min_size=1),
        days=st.integers(1, 5),
        tier=st.sampled_from(sorted(CANONICAL_OUTCOME_LEVELS)),
    )
    def test_ticks_change_no_balance_and_a_ritual_harvests_them_once_a_check_per_affinity(
        self, keys: set[str], days: int, tier: str
    ) -> None:
        """Maintainer: "what if we make those trickles build up, and the act of harvesting is
        the anima ritual? So they have this resonance they can claim, and they do so via that."
        And: "for anima rituals it gets trickles and those are added in to the roll there for
        resonance gains. So they're distinct."

        Given any resonances a room's residence trickles, any days of ticks and a ritual that
        succeeds or fails: the ticks change no balance, and what
        waits is exactly the days' trickle; the ritual then writes one ``TRICKLE_HARVEST`` grant
        per trickle resonance, each the pile grown by its affinity's check; it rolls one check
        per affinity across every grant it wrote (a roll's result shared by that affinity's
        grants); nothing is left waiting; and a second ritual harvests nothing.
        """
        self.configure(gain=RANKED_GAINS)
        sheet, daily = self.performer_with_a_residence(sorted(keys))
        before = {
            row.resonance_id: row.balance
            for row in CharacterResonance.objects.filter(character_sheet=sheet)
        }

        for _ in range(days):
            residence_trickle_tick()

        after = {
            row.resonance_id: row.balance
            for row in CharacterResonance.objects.filter(character_sheet=sheet)
        }
        self.assertEqual(after, before)
        piled = {self.resonances[key].pk: daily * days for key in keys}
        self.assertEqual(waiting_trickles(sheet), piled)
        self.assertFalse(ResonanceGrant.objects.filter(source=GainSource.TRICKLE_HARVEST).exists())

        ritual = RitualFactory(
            execution_kind=RitualExecutionKind.SCENE_ACTION, service_function_path="", flow=None
        )
        RitualCheckConfigFactory(ritual=ritual, stat=self.bonus_stat)
        partner = CharacterSheetFactory()
        distinct = [self.outcomes[name] for name in ("Failure", "Success", "Critical Success")]
        with force_check_outcome(*distinct) as capture:
            apply_ritual_bond(
                sheet,
                partner,
                ritual,
                self.outcomes[tier],
                AnimaRitualPerformanceFactory(ritual=ritual, target_character=partner),
                primal=self.resonances["primal 1"],
                outward=self.resonances["villain 1"],
            )

        written = ResonanceGrant.objects.filter(character_sheet=sheet).select_related("resonance")
        harvested = [g for g in written if g.source == GainSource.TRICKLE_HARVEST]
        self.assertEqual({g.resonance_id for g in harvested}, set(piled))
        self.assertEqual(len(harvested), len(piled))
        for grant in harvested:
            plain = piled[grant.resonance_id]
            self.assertEqual(grant.amount, plain + plain * grant.bonus_percent // 100)
        affinities = {g.resonance.affinity_id for g in written}
        self.assertEqual(len(self.bonus_calls(capture)), len(affinities))
        results = {}
        for grant in written:
            if grant.bonus_outcome is not None:
                self.assertEqual(grant.bonus_percent, RANKED_GAINS[grant.bonus_outcome.name])
            results.setdefault(grant.resonance.affinity_id, set()).add(
                (grant.bonus_outcome_id, grant.bonus_percent)
            )
        self.assertTrue(all(len(each) == 1 for each in results.values()), results)
        self.assertEqual(waiting_trickles(sheet), {})
        self.assertFalse(TrickleAccrual.objects.filter(harvested_at__isnull=True).exists())

        with force_every_check_outcome(self.outcomes["Success"]):
            apply_ritual_bond(
                sheet,
                partner,
                ritual,
                self.outcomes["Success"],
                AnimaRitualPerformanceFactory(ritual=ritual, target_character=partner),
                primal=self.resonances["primal 1"],
                outward=self.resonances["villain 1"],
            )
        self.assertEqual(
            ResonanceGrant.objects.filter(source=GainSource.TRICKLE_HARVEST).count(), len(piled)
        )


class AnAccentCountsWithoutTheSkill(_World, HypothesisTestCase):
    """An outfit's +Villainy, +Heroism or +Reflection counts for a character who has none."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        # One check point per rating point, as the skills docs state.
        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.SKILL,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )
        # The skills' modifier targets are written once here: the target lookup caches by
        # trait, so one made inside an example (and rolled back with it) would be cached dead.
        cls.skill_targets = {name: ensure_skill_target(skill) for name, skill in cls.skills.items()}

    def bonus_check_points(self, sheet: CharacterSheet, key: str) -> int:
        """The skill points of the one bonus check an earned gain of ``key`` rolls: the gain is
        made through ``grant_resonance`` and the roll it made is read back from the capture."""
        with force_every_check_outcome(self.outcomes["Success"]) as capture:
            _gain(sheet, key, self, amount=3, source=GainSource.MISSION_REPORT)
            (call,) = self.bonus_calls(capture)
            return perform_check(
                sheet.character, call.check_type, extra_traits=call.extra_traits
            ).trait_points

    @settings(max_examples=20, deadline=None)
    @given(key=st.sampled_from(RESONANCE_KEYS), accent=st.integers(1, 40))
    def test_a_plus_skill_accent_raises_the_bonus_checks_points_for_a_character_with_no_skill(
        self, key: str, accent: int
    ) -> None:
        """Maintainer: "let them use outfits with +affinity-skill even if they lack the skill
        itself."

        Given a character with no rating in the earned resonance's affinity skill, and any
        accent from 1 to 40 on that skill worked into a worn piece: her bonus check's points
        rise by exactly the accent.
        """
        self.configure()
        sheet = self.character()
        without = self.bonus_check_points(sheet, key)

        recipe = CraftingRecipeFactory()
        CraftingRecipeModifierFactory(
            recipe=recipe, target=self.skill_targets[AFFINITY_OF[key]], base_value=accent
        )
        template = ItemTemplateFactory(name=f"Gown of {sheet.pk}")
        TemplateSlotFactory(
            template=template, body_region=BodyRegion.TORSO, equipment_layer=EquipmentLayer.BASE
        )
        template.__dict__.pop("cached_slots", None)
        item = ItemInstanceFactory(
            template=template,
            game_object=ObjectDBFactory(db_key=f"Gown of {sheet.pk}", location=sheet.character),
            holder_character_sheet=sheet,
            quality_tier=QualityTierFactory(name="Sound"),
        )
        CraftedItemRecipeFactory(item_instance=item, recipe=recipe, quality_tier=item.quality_tier)
        equip_item(
            character_sheet=sheet,
            item_instance=item,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )

        self.assertEqual(self.bonus_check_points(sheet, key), without + accent)


class _PullWorld(_World):
    """A character with anima and resonance enough to pull, and a fresh resonance with a pull
    effect worth ``flat`` on its own thread."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        ThreadPullCostFactory(tier=1, resonance_cost=2, anima_per_thread=1)

    def puller(self, affinity: str, flat: int) -> tuple[CharacterSheet, object, PullActionContext]:
        sheet = self.character(anima=20)
        resonance = ResonanceFactory(affinity=self.affinities[affinity])
        CharacterResonanceFactory(
            character_sheet=sheet, resonance=resonance, balance=20, lifetime_earned=20
        )
        thread = ThreadFactory(owner=sheet, resonance=resonance)
        ThreadPullEffectFactory(
            target_kind=thread.target_kind, resonance=resonance, tier=1, flat_bonus_amount=flat
        )
        return sheet, thread, PullActionContext(involved_traits=(thread.target_trait_id,))


class PullsScaleByWorth(_PullWorld, HypothesisTestCase):
    """A pull's effects are worth what the payer's check made them."""

    @settings(max_examples=40, deadline=None)
    @given(
        affinity=st.sampled_from(("celestial", "primal", "abyssal")),
        tier=st.sampled_from(ALL_TIERS),
        worths=st.fixed_dictionaries({name: st.integers(0, 400) for name in ALL_TIERS}),
        floor=st.integers(0, 300),
        flat=st.integers(1, 80),
    )
    def test_a_pulls_effects_scale_by_the_payers_worth_and_never_fall_below_the_floor(
        self, affinity: str, tier: str, worths: dict[str, int], floor: int, flat: int
    ) -> None:
        """Maintainer: "probably how much each is worth? That way we could have success
        outcomes tied to a percentage modifier or something like that? Flat bonuses would
        probably be the wrong shape." And: "the baseline itself should be tempting ... adding in
        a base bonus/floor."

        Given any award table of worth percents, any result tier (one with no row too), any
        floor on the paying affinity and any effect size: every effect the pull buys is the
        unscaled effect times the worth percent, rounded down, and the worth is the tier's
        percent (100 where it has no row) but never under the affinity's floor. A preview of the
        same pull rolls nothing and shows the unscaled effect.
        """
        self.configure(worth=worths, floor=floor)
        sheet, thread, context = self.puller(affinity, flat)

        with force_every_check_outcome(self.outcomes[tier]) as preview_capture:
            preview = preview_resonance_pull(sheet, 1, [thread])
        with force_check_outcome(self.outcomes[tier]) as capture:
            pulled = spend_resonance_for_pull(sheet, 1, [thread], context)

        expected_worth = max(worths[tier] if tier != UNROWED else 100, floor)
        self.assertEqual(preview_capture.calls, [])
        self.assertEqual(len(self.bonus_calls(capture)), 1)
        self.assertEqual(pulled.worth_by_affinity, {self.affinities[affinity].pk: expected_worth})
        self.assertGreaterEqual(expected_worth, floor)
        self.assertTrue(preview.resolved_effects)
        self.assertEqual(len(pulled.resolved_effects), len(preview.resolved_effects))
        for scaled, unscaled in zip(pulled.resolved_effects, preview.resolved_effects, strict=True):
            self.assertEqual(scaled.scaled_value, unscaled.scaled_value * expected_worth // 100)


class NothingConfiguredChangesNothing(_PullWorld, HypothesisTestCase):
    """With no bonus check type set, every gain and spend is what it was before the skills."""

    @settings(max_examples=30, deadline=None)
    @given(
        key=st.sampled_from(RESONANCE_KEYS),
        source=st.sampled_from(BARE_ROLLED_SOURCES + BARE_CALLER_ROLLED_SOURCES),
        amount=st.integers(1, 60),
        gain=st.integers(1, 300),
    )
    def test_a_gain_with_no_check_type_pays_its_plain_amount_and_rolls_nothing(
        self, key: str, source: str, amount: int, gain: int
    ) -> None:
        """The spec's rule, not a maintainer quote: "With no check type configured, every gain
        and spend equals today's." Blank turns the bonus check off.

        Given any rolled or caller-rolled source and a table that would add up to 300 percent,
        a gain through ``grant_resonance`` writes exactly the amount asked for (the affinities
        earn at the default rate), records no bonus and rolls nothing; a caller-rolled source
        needs no result passed while the check is off.
        """
        self.configure(bonus=False, gain=gain)
        sheet = self.character()

        with force_every_check_outcome(self.outcomes["Critical Success"]) as capture:
            grant = _gain(sheet, key, self, amount=amount, source=source)

        self.assertEqual(grant.amount, amount)
        self.assertEqual((grant.bonus_outcome, grant.bonus_percent), (None, 0))
        self.assertEqual(capture.calls, [])

    @settings(max_examples=30, deadline=None)
    @given(
        affinity=st.sampled_from(("celestial", "primal", "abyssal")),
        worth=st.integers(0, 400),
        floor=st.integers(0, 300),
        flat=st.integers(1, 80),
    )
    def test_a_pull_with_no_check_type_is_worth_100_percent_whatever_the_floor(
        self, affinity: str, worth: int, floor: int, flat: int
    ) -> None:
        """The spec's rule, not a maintainer quote: "With no check type configured, every gain
        and spend equals today's." A pull is then worth 100 percent, whatever worth table and
        floors exist.

        Given any worth percents and floor, the pull's effects equal the preview's unscaled
        effects, its worth is 100 percent, and no check was rolled.
        """
        self.configure(bonus=False, worth=worth, floor=floor)
        sheet, thread, context = self.puller(affinity, flat)

        preview = preview_resonance_pull(sheet, 1, [thread])
        with force_every_check_outcome(self.outcomes["Critical Success"]) as capture:
            pulled = spend_resonance_for_pull(sheet, 1, [thread], context)

        self.assertEqual(capture.calls, [])
        self.assertEqual(set(pulled.worth_by_affinity.values()), {100})
        self.assertEqual(
            [e.scaled_value for e in pulled.resolved_effects],
            [e.scaled_value for e in preview.resolved_effects],
        )

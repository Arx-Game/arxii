"""Fuzz: only an authored choice pays at once; every other situation only suggests (#5327).

The maintainer ruled on 2026-11-27 that gaining a resonance needs intent, and the game cannot
read intent from a situation. So an authored choice (a mission option whose theme names its
resonance) pays at once and says so, while a situation (a feeling she bears, a state she caused,
an affinity-wide row) only suggests a resonance beside an act she can later mark, and still
makes her magic stronger. Each class below holds one rule of that design, quoted in the
maintainer's words from the issue.

Every example builds its characters fresh with factories and calls our own function
(``award_kindled_deeds``), reading the ledger, the recorded acts and the mission option
preview back. The shared catalog (three affinities each linked to a skill, six resonances, the
canonical result tiers) is the ``_World`` builder of ``test_affinity_skill_properties``; it
lives once in ``setUpTestData``, because a Hypothesis test's own ``setUp`` runs outside any
transaction and would leak rows between examples.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import timedelta

from django.utils import timezone
from hypothesis import assume, given, settings, strategies as st
from hypothesis.extra.django import TestCase as HypothesisTestCase

from actions.constants import ActionCategory
from integration_tests.fuzz.test_affinity_skill_properties import (
    AFFINITY_OF,
    RESONANCE_KEYS,
    UNROWED,
    _gain,
    _World,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import CharacterSheet
from world.checks.factories import CheckTypeFactory
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.covenants.perks.constants import Situation
from world.magic.constants import GainSource, KindlingActKind
from world.magic.factories import (
    KindledStrengthTierFactory,
    KindlingSituationFactory,
    RecordedActFactory,
)
from world.magic.models import RecordedAct, RecordedActSuggestion, ResonanceGrant
from world.magic.services.kindling import (
    award_kindled_deeds,
    get_kindling_config,
    kindled_resonances,
)
from world.magic.types.kindling import KindlingAct
from world.mechanics.factories import PropertyFactory
from world.missions.constants import OptionKind
from world.missions.factories import (
    MissionInstanceFactory,
    MissionOptionFactory,
    MissionThemeFactory,
)
from world.missions.services.play import _kindled_feeds
from world.missions.types import PresentedOption

# The strongest rank a staff-authored strength tier reaches in these examples.
TOP_RANK = 3


def _reason(key: str) -> str:
    """The reason text staff wrote on every situation row of ``key``."""
    return f"{key} reason"


class _EarningWorld(_World):
    """``_World`` plus the staging of one act in a mission, with chosen and situation rows."""

    def stage(  # noqa: PLR0913 - the three kinds of row, their strengths and the earn share
        self,
        sheet: CharacterSheet,
        *,
        chosen: Sequence[str] = (),
        caused: Sequence[str] = (),
        felt: Sequence[str] = (),
        ranks: Mapping[str, int] | None = None,
        earn_percent: int = 100,
    ) -> tuple[KindlingAct, PresentedOption]:
        """Set one mission scene and return the act ``sheet`` makes in it, and its option.

        The act takes a mission option aimed at one other character. The option carries a theme
        for each resonance in ``chosen``, each with a "mission theme" situation: an authored
        choice. Each resonance in ``caused`` gets a "target in a state she caused" situation,
        and the other character bears a condition ``sheet`` laid that carries its feeling.
        Each resonance in ``felt`` gets an "own feeling" situation, and ``sheet`` herself bears
        a condition carrying its feeling. ``ranks`` names the strength each key's row kindles
        at (1 when absent); every rank up to the highest has a tier earning ``earn_percent``.
        """
        ranks = ranks or {}
        for rank in range(1, max([1, *ranks.values()]) + 1):
            KindledStrengthTierFactory(rank=rank, min_severity=1, earn_percent=earn_percent)
        other = CharacterSheetFactory()
        option = MissionOptionFactory(
            option_kind=OptionKind.CHECK, authored_check_type=CheckTypeFactory()
        )
        done_to_them = ConditionTemplateFactory(name=f"What {sheet.pk} did")
        felt_by_her = ConditionTemplateFactory(name=f"What {sheet.pk} feels")
        for key in sorted({*chosen, *caused, *felt}):
            resonance = self.resonances[key]
            resonance.feeling = PropertyFactory()
            resonance.save()
            row = {
                "resonance": resonance,
                "strength": ranks.get(key, 1),
                "reason_text": _reason(key),
            }
            if key in chosen:
                theme = MissionThemeFactory()
                option.themes.add(theme)
                KindlingSituationFactory(
                    situation=Situation.MISSION_THEME, mission_theme=theme, **row
                )
            if key in caused:
                done_to_them.properties.add(resonance.feeling)
                KindlingSituationFactory(situation=Situation.TARGET_IN_STATE_THEY_CAUSED, **row)
            if key in felt:
                felt_by_her.properties.add(resonance.feeling)
                KindlingSituationFactory(situation=Situation.OWN_FEELING, **row)
        ConditionInstanceFactory(
            target=other.character,
            condition=done_to_them,
            severity=1,
            source_character=sheet.character,
        )
        ConditionInstanceFactory(target=sheet.character, condition=felt_by_her, severity=1)
        act = KindlingAct(
            kind=KindlingActKind.MISSION_OPTION,
            target=other,
            mission_option=option,
            label="Threatened a prisoner",
        )
        presented = PresentedOption(
            option=option,
            kind=OptionKind.CHECK,
            check_type=None,
            base_risk=0,
            ic_framing=act.label,
            owner=sheet.character,
        )
        return act, presented

    def take(
        self, sheet: CharacterSheet, act: KindlingAct, tier: str = "Success"
    ) -> list[ResonanceGrant]:
        """``sheet`` takes ``act`` in one mission with its roll on ``tier``."""
        return award_kindled_deeds(
            sheet, act=act, outcome=self.outcomes[tier], mission=MissionInstanceFactory()
        )


class NoSituationPaysByItself(_EarningWorld, HypothesisTestCase):
    """A situation never pays: Primal, Celestial or Abyssal, in her aura or not."""

    @settings(max_examples=50, deadline=None)
    @given(
        chosen=st.sets(st.sampled_from(RESONANCE_KEYS)),
        caused=st.sets(st.sampled_from(RESONANCE_KEYS)),
        felt=st.sets(st.sampled_from(RESONANCE_KEYS)),
        held=st.sets(st.sampled_from(RESONANCE_KEYS)),
        amount=st.integers(1, 40),
    )
    def test_no_grant_is_written_for_a_situation_unless_a_chosen_row_names_it(
        self, chosen: set[str], caused: set[str], felt: set[str], held: set[str], amount: int
    ) -> None:
        """Maintainer: "Primal working based on the pose makes sense to me. Getting it based on
        'is surrounded' doesn't really make sense to me." And, on 2026-11-27: "there needs to be
        a measure of *intent* to gaining that resonance."

        Given any resonances named by the mission option she takes (chosen), any whose feeling
        she caused in the character she acts on (caused), any whose feeling she only bears
        herself (felt), and any she already holds, the only resonances that earn are the ones an
        authored choice names (a Primal one only if she holds it). A state she caused, a feeling
        she bears and a situation on any resonance of any affinity write no grant, held or not,
        and move no balance.
        """
        assume(chosen or caused or felt)
        sheet = self.character(holds=sorted(held))
        self.configure()
        act, _ = self.stage(sheet, chosen=sorted(chosen), caused=sorted(caused), felt=sorted(felt))
        self.deed_award(amount)
        paid = {key for key in chosen if AFFINITY_OF[key] != "primal" or key in held}

        grants = self.take(sheet, act)

        self.assertEqual({grant.resonance for grant in grants}, {self.resonances[k] for k in paid})
        self.assertEqual(ResonanceGrant.objects.filter(character_sheet=sheet).count(), len(grants))
        for key in (chosen | caused | felt) - paid:
            self.assertEqual(self.balance(sheet, key), 0)
            self.assertFalse(
                ResonanceGrant.objects.filter(
                    character_sheet=sheet, resonance=self.resonances[key]
                ).exists()
            )

    @settings(max_examples=20, deadline=None)
    @given(key=st.sampled_from(RESONANCE_KEYS), holds=st.booleans(), amount=st.integers(1, 40))
    def test_a_situation_for_a_whole_affinity_pays_no_one_and_suggests_only_what_she_holds(
        self, key: str, holds: bool, amount: int
    ) -> None:
        """Maintainer: "we might have situations *suggest* possible resonances to players so
        they don't forget as a convenience."

        An affinity-wide situation names no one resonance. Whether she holds the resonance or
        not it pays nothing, and it suggests a resonance only to a character who holds it.
        """
        sheet = self.character(holds=[key] if holds else [])
        self.configure()
        feeling = PropertyFactory()
        resonance = self.resonances[key]
        resonance.feeling = feeling
        resonance.save()
        KindledStrengthTierFactory(rank=1, min_severity=1, earn_percent=100)
        KindlingSituationFactory(
            resonance=None,
            for_affinity=resonance.affinity,
            situation=Situation.OWN_FEELING,
            condition_property=feeling,
            strength=None,
        )
        template = ConditionTemplateFactory(name=f"Feeling of {sheet.pk}")
        template.properties.add(feeling)
        ConditionInstanceFactory(target=sheet.character, condition=template, severity=1)
        self.deed_award(amount)

        grants = award_kindled_deeds(
            sheet,
            act=KindlingAct(kind=KindlingActKind.SOCIAL, label="Threatened a prisoner"),
            outcome=self.outcomes["Success"],
            mission=MissionInstanceFactory(),
        )

        self.assertEqual(grants, [])
        self.assertFalse(ResonanceGrant.objects.filter(character_sheet=sheet).exists())
        suggested = set(
            RecordedActSuggestion.objects.filter(act__character_sheet=sheet).values_list(
                "resonance_id", flat=True
            )
        )
        self.assertEqual(suggested, {resonance.pk} if holds else set())


class AnActLeavesARecordOfWhatSituationsSuggest(_EarningWorld, HypothesisTestCase):
    """An act that earned an award row is written down, with each situation's suggestion."""

    @settings(max_examples=50, deadline=None)
    @given(
        ranked=st.dictionaries(
            st.sampled_from(RESONANCE_KEYS), st.integers(1, TOP_RANK), min_size=1
        ),
        held=st.sets(st.sampled_from(RESONANCE_KEYS)),
        amount=st.integers(1, 40),
    )
    def test_one_recorded_act_lists_what_situations_reached_strongest_first(
        self, ranked: dict[str, int], held: set[str], amount: int
    ) -> None:
        """Maintainer: "we might have situations *suggest* possible resonances to players so
        they don't forget as a convenience ... Things we can author and point to." And: "I
        wouldn't necessarily disagree with being stronger on a circumstance as a -shorthand- to
        the sort of things that work with the resonance: that in specific situations, your
        resonance becomes stronger, even if it's not the same thing as deliberately trying to
        obtain it."

        Given any feelings she bears, each authored at its own strength, an act that earned an
        award row leaves exactly one recorded act: its label, its result tier, who it was aimed
        at and the fatigue pool a mission option charges, with one suggestion for each resonance
        a situation reached (a Primal one only when she holds it), at that strength, with the
        row's reason, strongest first. The suggestions pay nothing, and they do not change her
        kindled strength: the strength she reads before and after is the same, and a resonance
        she holds is kindled at the strength its row sets.
        """
        sheet = self.character(holds=sorted(held))
        self.configure()
        act, _ = self.stage(sheet, felt=sorted(ranked), ranks=ranked)
        self.deed_award(amount)
        before = {row.resonance.pk: row.tier for row in kindled_resonances(sheet)}
        expected = {
            key: rank for key, rank in ranked.items() if AFFINITY_OF[key] != "primal" or key in held
        }

        grants = self.take(sheet, act)

        self.assertEqual(grants, [])
        (recorded,) = RecordedAct.objects.filter(character_sheet=sheet)
        self.assertEqual(recorded.label, act.label)
        self.assertEqual(recorded.outcome, self.outcomes["Success"])
        self.assertEqual(recorded.target_sheet, act.target)
        self.assertEqual(recorded.fatigue_category, ActionCategory.SOCIAL)
        self.assertIsNone(recorded.marked_grant)
        suggestions = list(
            recorded.suggestions.select_related("resonance", "strength").order_by("pk")
        )
        self.assertEqual(
            {row.resonance_id: row.strength.rank for row in suggestions},
            {self.resonances[key].pk: rank for key, rank in expected.items()},
        )
        listed = [row.strength.rank for row in suggestions]
        self.assertEqual(listed, sorted(listed, reverse=True))
        for key in expected:
            row = next(r for r in suggestions if r.resonance_id == self.resonances[key].pk)
            self.assertEqual(row.reason, _reason(key))
        self.assertFalse(ResonanceGrant.objects.filter(character_sheet=sheet).exists())
        after = {row.resonance.pk: row.tier for row in kindled_resonances(sheet)}
        self.assertEqual(after, before)
        for key in held & set(ranked):
            tier = after[self.resonances[key].pk]
            self.assertIsNotNone(tier)
            self.assertEqual(tier.rank, ranked[key])

    @settings(max_examples=20, deadline=None)
    @given(amount=st.integers(1, 40))
    def test_an_act_with_no_award_row_for_its_result_leaves_no_record(self, amount: int) -> None:
        """Maintainer: "we might have situations *suggest* possible resonances to players ...
        Things we can author and point to."

        A roll whose result tier staff authored no award for (a failure, say) earns nothing and
        so leaves nothing to point at, whatever situations held.
        """
        sheet = self.character()
        self.configure()
        act, _ = self.stage(sheet, felt=["heroic 1"])
        self.deed_award(amount)

        grants = self.take(sheet, act, tier=UNROWED)

        self.assertEqual(grants, [])
        self.assertFalse(RecordedAct.objects.filter(character_sheet=sheet).exists())

    @settings(max_examples=30, deadline=None)
    @given(days=st.integers(1, 365), age=st.integers(0, 800), marked=st.booleans())
    def test_an_unmarked_act_past_the_window_is_pruned_and_a_marked_one_stays(
        self, days: int, age: int, marked: bool
    ) -> None:
        """Maintainer: "they point to an act and if it doesn't make sense, well, we could
        nullify it and chide them." (Staff set how long an act stays pointable; the settled
        default is 90 days.)

        Given any window and any age of an earlier act, writing the next act removes her
        unmarked acts older than the window and keeps every act that is younger, and every
        marked act whatever its age, because its grant keeps it.
        """
        assume(age != days)
        sheet = self.character()
        self.configure()
        self.deed_award(5)
        config = get_kindling_config()
        config.recorded_act_days = days
        config.save()
        earlier = RecordedActFactory(character_sheet=sheet, outcome=self.outcomes["Success"])
        if marked:
            earlier.marked_grant = _gain(
                sheet, "primal 1", self, amount=1, source=GainSource.STAFF_GRANT
            )
        # ``auto_now_add`` stamps only the first save, so saving again backdates the act.
        earlier.created_at = timezone.now() - timedelta(days=age)
        earlier.save()

        award_kindled_deeds(
            sheet,
            act=KindlingAct(kind=KindlingActKind.SOCIAL, label="Spoke to the guard"),
            outcome=self.outcomes["Success"],
        )

        self.assertEqual(RecordedAct.objects.filter(pk=earlier.pk).exists(), marked or age < days)
        self.assertTrue(
            RecordedAct.objects.filter(character_sheet=sheet, label="Spoke to the guard").exists()
        )


class AChosenDeedPaysInFullAtOnce(_EarningWorld, HypothesisTestCase):
    """An authored choice names its resonance, says so before she picks, and pays when she does."""

    @settings(max_examples=50, deadline=None)
    @given(
        chosen=st.sets(st.sampled_from(RESONANCE_KEYS), min_size=1),
        caused=st.sets(st.sampled_from(RESONANCE_KEYS)),
        felt=st.sets(st.sampled_from(RESONANCE_KEYS)),
        held=st.sets(st.sampled_from(RESONANCE_KEYS)),
        amount=st.integers(1, 60),
        earn_percent=st.integers(1, 100),
    )
    def test_a_chosen_deed_pays_its_whole_amount_at_once_and_the_preview_names_it(  # noqa: PLR0913 - one drawn value per rule input
        self,
        chosen: set[str],
        caused: set[str],
        felt: set[str],
        held: set[str],
        amount: int,
        earn_percent: int,
    ) -> None:
        """Maintainer: "authored content could pay immediately for celestial/abyssal,
        especially in missions where we say 'X will give Y resonance'. Like we're defining it
        ahead of time, there's no ambiguity." And, of an otherwise celestial hero: "I *do* think
        characters should earn resonance they don't have."

        Given any resonances a mission option's themes name, with the award for her roll and the
        strength's earn share, whether she holds them or not: every one of them that is
        Celestial or Abyssal, or a Primal one she holds, is paid at once and in full (the
        award times the share, rounded down, one grant each, on the balance with nothing set
        aside), and a Primal one she lacks is not. The option's preview, read before she picks,
        names exactly the resonances the roll then pays, each with its reason and never an
        amount, and a situation that only suggests is not in it. A chosen deed that paid leaves
        no recorded act.
        """
        assume(amount * earn_percent // 100 > 0)
        sheet = self.character(holds=sorted(held))
        self.configure(bonus=False)
        act, presented = self.stage(
            sheet,
            chosen=sorted(chosen),
            caused=sorted(caused),
            felt=sorted(felt),
            earn_percent=earn_percent,
        )
        self.deed_award(amount)
        mission = MissionInstanceFactory()
        paid = {key for key in chosen if AFFINITY_OF[key] != "primal" or key in held}

        (previewed,) = _kindled_feeds(mission, [presented], sheet.character)
        grants = award_kindled_deeds(
            sheet, act=act, outcome=self.outcomes["Success"], mission=mission
        )

        self.assertEqual(
            {feed.resonance_name for feed in previewed}, {self.resonances[k].name for k in paid}
        )
        for feed in previewed:
            key = next(k for k in paid if self.resonances[k].name == feed.resonance_name)
            self.assertEqual(feed.reason, _reason(key))
        self.assertEqual({grant.resonance for grant in grants}, {self.resonances[k] for k in paid})
        for grant in grants:
            self.assertEqual(grant.amount, amount * earn_percent // 100)
            self.assertEqual(grant.source, GainSource.KINDLED_DEED)
        for key in paid:
            self.assertEqual(self.balance(sheet, key), amount * earn_percent // 100)
        for key in chosen - paid:
            self.assertEqual(self.balance(sheet, key), 0)
        if grants:
            self.assertFalse(RecordedAct.objects.filter(character_sheet=sheet).exists())

"""Journeys for Resonance Conflict from carried drift (#4732).

Ysmay's true aura leads Celestial. She carries 100 Celestial resonance and some Abyssal.
With the authored defaults (threshold 50% of the dominant balance, floor 20, a step per 20
points past it, focus difficulty 10 + 2 per step, one step for an off-aura pull) her
Abyssal balance is drift: at 50 it sits on the threshold and nothing happens; past it,
each cast she makes calls for a focus roll first. A failed roll lays "Resonance Conflict"
on her, and its authored -10 on her cast check reaches the very cast that failed.
Worn, her Abyssal alternate self turns the measure around: her Celestial balance becomes
the drift.

Spies on the check engine read the focus roll's difficulty and the cast's modifier
breakdown, which no player-facing line carries; everything else is read off what she is
told and the condition she holds. The focus outcome is forced with
``force_check_outcome``, which the focus roll consumes because it is the cast's first
roll. Names are invented.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Self
from unittest.mock import patch

from django.urls import reverse
from rest_framework import status

from actions.factories import ActionTemplateFactory
from actions.models import ActionEnhancement
from integration_tests.harness import JourneyCase
from integration_tests.test_acting_aura_journeys import _AShifter
from world.checks import services as check_services
from world.checks.factories import (
    CheckTypeFactory,
    CheckTypeTraitFactory,
    create_social_action_templates,
)
from world.checks.test_helpers import force_check_outcome
from world.combat import services as combat_services
from world.combat.constants import ActionCategory, ClashStatus, PaceMode, ParticipantStatus
from world.combat.factories import (
    ClashConfigFactory,
    ClashFactory,
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    StrainConfigFactory,
)
from world.combat.models import ClashContribution
from world.combat.services import resolve_round
from world.conditions.constants import DurationType
from world.conditions.factories import (
    ConditionCategoryFactory,
    ConditionCheckModifierFactory,
    ConditionTemplateFactory,
)
from world.conditions.models import ConditionInstance
from world.magic.constants import EffectKind, TargetKind
from world.magic.factories import (
    AffinityInteractionFactory,
    BinaryEffectTypeFactory,
    CharacterAnimaFactory,
    CharacterAuraFactory,
    CharacterResonanceFactory,
    CharacterTechniqueFactory,
    CharacterThreadWeavingUnlockFactory,
    EffectTypeFactory,
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
    ThreadPullCostFactory,
    ThreadPullEffectFactory,
    ThreadWeavingUnlockFactory,
    ensure_canonical_affinities,
)
from world.magic.models import Affinity, AffinityInteraction
from world.magic.services.drift import get_drift_config
from world.magic.services.threads import weave_thread
from world.magic.tests._cache_isolation import ResonanceCacheIsolationMixin
from world.magic.types.pull import CastPullDeclaration
from world.scenes.constants import RoundStatus
from world.scenes.factories import SceneFactory
from world.scenes.tests.cast_test_helpers import grant_technique
from world.traits.factories import (
    CheckOutcomeFactory,
    CheckSystemSetupFactory,
    StatTraitFactory,
)
from world.traits.models import CheckOutcome
from world.vitals.models import CharacterVitals

CONFLICT = "Resonance Conflict"
PENALTY = -10


class _Recorder:
    """Spies on the check engine: every focus roll, and every cast breakdown."""

    def __init__(self, *, focus_type, cast_type) -> None:
        self.focus_type = focus_type
        self.cast_type = cast_type
        self.focus_difficulties: list[int] = []
        self.cast_breakdowns: list = []

    def perform(self, character, check_type, target_difficulty=0, *args, **kwargs):
        if check_type == self.focus_type:
            self.focus_difficulties.append(target_difficulty)
        return self._real_perform(character, check_type, target_difficulty, *args, **kwargs)

    def collect(self, sheet, check_type, *args, **kwargs):
        breakdown = self._real_collect(sheet, check_type, *args, **kwargs)
        if check_type == self.cast_type:
            self.cast_breakdowns.append(breakdown)
        return breakdown

    def __enter__(self) -> Self:
        self._real_perform = check_services.perform_check_with_modifiers
        self._real_collect = check_services.collect_check_modifiers
        self._patches = [
            patch.object(check_services, "perform_check_with_modifiers", side_effect=self.perform),
            patch.object(check_services, "collect_check_modifiers", side_effect=self.collect),
            # The combat resolver reaches the aggregator through world.combat.services.
            patch.object(combat_services, "collect_check_modifiers", side_effect=self.collect),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc) -> None:
        for p in self._patches:
            p.stop()


def _labels(breakdown) -> dict[str, int]:
    """A modifier breakdown's contributions, by the label a player sees."""
    return {c.source_label: c.value for c in breakdown.contributions}


def _author_conflict(cast_check_type):
    """The config, focus check and conflict condition staff author for the contest."""
    focus_type = CheckTypeFactory(name="Keeping Focus")
    CheckTypeTraitFactory(check_type=focus_type, trait=StatTraitFactory(), weight=1)
    condition = ConditionTemplateFactory(
        name=CONFLICT,
        category=ConditionCategoryFactory(self_shakeable=True),
        default_duration_type=DurationType.SCENE,
    )
    ConditionCheckModifierFactory(
        condition=condition, check_type=cast_check_type, modifier_value=PENALTY
    )
    cfg = get_drift_config()
    cfg.focus_check_type = focus_type
    cfg.conflict_condition = condition
    cfg.save()
    return focus_type, condition


class _Drifting(_AShifter):
    """Ysmay, Celestial-led, with her Abyssal alternate self, in a scene, casting on the web."""

    abyssal_balance = 60

    def setUp(self) -> None:
        super().setUp()
        AffinityInteraction.objects.clear_cache()
        self.outcomes = CheckSystemSetupFactory.create()
        self.ysmay, self.sheet, self.alt = self.make_shifter(
            "Ysmay", room=self.room, mask_affinity=self.abyssal
        )
        SceneFactory(room=self.room)
        CharacterAnimaFactory(character=self.sheet, current=30, maximum=30)
        CharacterVitals.objects.create(
            character_sheet=self.sheet, health=50, max_health=50, base_max_health=50
        )

        self.cast_type = CheckTypeFactory()
        self.cast_stat = StatTraitFactory()
        CheckTypeTraitFactory(check_type=self.cast_type, trait=self.cast_stat, weight=1)
        gift = GiftFactory()
        gift.resonances.add(ResonanceFactory(affinity=self.celestial))
        self.technique = TechniqueFactory(
            name="Lantern Ward",
            gift=gift,
            anima_cost=1,
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_template=ActionTemplateFactory(check_type=self.cast_type),
        )
        grant_technique(self.sheet.primary_persona, self.technique)

        self.celestial_resonance = ResonanceFactory(affinity=self.celestial)
        self.abyssal_resonance = ResonanceFactory(affinity=self.abyssal)
        CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=self.celestial_resonance,
            balance=100,
            lifetime_earned=100,
        )
        self.abyssal_row = CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=self.abyssal_resonance,
            balance=self.abyssal_balance,
            lifetime_earned=self.abyssal_balance,
        )
        self.focus_type, self.condition = _author_conflict(self.cast_type)

    def cast(self, *, focus: str | None = None, **cast_kwargs) -> _Recorder:
        """Cast through the web seam, forcing the focus roll to ``focus`` when given."""
        self.ysmay.resonances.invalidate()
        with _Recorder(focus_type=self.focus_type, cast_type=self.cast_type) as rec:
            if focus is None:
                outcome = self.web(
                    self.ysmay, "cast_technique", technique_id=self.technique.pk, **cast_kwargs
                )
            else:
                with force_check_outcome(CheckOutcome.objects.get(name=focus)):
                    outcome = self.web(
                        self.ysmay,
                        "cast_technique",
                        technique_id=self.technique.pk,
                        **cast_kwargs,
                    )
        self.assertTrue(outcome.detail.success, outcome.detail.message)
        self.assertEqual(len(rec.cast_breakdowns), 1)
        return rec

    def conflict(self) -> ConditionInstance | None:
        return ConditionInstance.objects.filter(target=self.ysmay, condition=self.condition).first()


class DriftOnTheThresholdCallsForNothing(_Drifting):
    abyssal_balance = 50

    def test_no_focus_roll_and_no_conflict(self) -> None:
        rec = self.cast()
        self.assertEqual(rec.focus_difficulties, [])
        self.assertIsNone(self.conflict())

    def test_a_softer_authored_pair_weighs_less(self) -> None:
        """Abyssal against Celestial at half weight: 100 Abyssal carries 50 drift."""
        self.abyssal_row.balance = 100
        self.abyssal_row.save(update_fields=["balance"])
        AffinityInteractionFactory(
            source_affinity=self.abyssal,
            environment_affinity=self.celestial,
            conflict_weight=Decimal("0.50"),
        )
        AffinityInteraction.objects.clear_cache()
        self.assertEqual(self.cast().focus_difficulties, [])


class AnUnsetConflictConditionRollsNothing(_Drifting):
    """Staff have not named the conflict condition yet: the Required content dashboard
    lists it, and a drifting cast resolves with no focus roll."""

    def test_the_cast_resolves_without_a_focus_roll(self) -> None:
        cfg = get_drift_config()
        cfg.conflict_condition = None
        cfg.save()
        rec = self.cast()
        self.assertEqual(rec.focus_difficulties, [])
        self.assertIsNone(self.conflict())


class DriftPastTheThreshold(_Drifting):
    """60 Abyssal against a threshold of 50: one step, focus difficulty 12."""

    def test_a_failed_focus_roll_penalises_the_same_cast(self) -> None:
        self.watch(self.ysmay)
        rec = self.cast(focus="Failure")

        self.assertEqual(rec.focus_difficulties, [12])
        self.assertTold(self.ysmay, f"You lose your focus as you work Lantern Ward: {CONFLICT}.")
        instance = self.conflict()
        self.assertIsNotNone(instance)
        self.assertEqual(instance.severity, 3)  # one step + (1 - (-1))
        self.assertEqual(_labels(rec.cast_breakdowns[0]).get(CONFLICT), PENALTY)

    def test_a_kept_focus_applies_nothing(self) -> None:
        rec = self.cast(focus="Success")

        self.assertEqual(rec.focus_difficulties, [12])
        self.assertIsNone(self.conflict())
        self.assertNotIn(CONFLICT, _labels(rec.cast_breakdowns[0]))

    def test_a_worse_roll_costs_more(self) -> None:
        self.cast(focus="Partial Success")
        self.assertEqual(self.conflict().severity, 2)  # one step + (1 - 0)

    def test_failing_again_advances_the_conflict_by_one(self) -> None:
        self.cast(focus="Failure")
        self.cast(focus="Failure")
        self.assertEqual(self.conflict().severity, 4)

    def test_succeeding_while_conflicted_changes_nothing(self) -> None:
        self.cast(focus="Failure")
        self.cast(focus="Success")
        self.assertEqual(self.conflict().severity, 3)


class AnOffAuraPullAddsAStep(_Drifting):
    """Pulling an Abyssal thread while Celestial-led adds a step: difficulty 14."""

    def test_the_focus_roll_is_harder(self) -> None:
        ThreadPullCostFactory(tier=1, resonance_cost=1, anima_per_thread=0)
        ThreadPullEffectFactory(
            target_kind=TargetKind.TRAIT,
            resonance=self.abyssal_resonance,
            tier=1,
            flat_bonus_amount=1,
            effect_kind=EffectKind.FLAT_BONUS,
        )
        CharacterThreadWeavingUnlockFactory(
            character=self.sheet,
            unlock=ThreadWeavingUnlockFactory(
                target_kind=TargetKind.TRAIT, unlock_trait=self.cast_stat
            ),
        )
        thread = weave_thread(
            self.sheet, TargetKind.TRAIT, self.cast_stat, self.abyssal_resonance, name="Ash"
        )
        unpulled = self.cast(focus="Success")
        pulled = self.cast(
            focus="Success",
            cast_pull=CastPullDeclaration(
                resonance=self.abyssal_resonance, tier=1, threads=(thread,)
            ),
        )
        self.assertEqual(unpulled.focus_difficulties, [12])
        self.assertEqual(pulled.focus_difficulties, [14])


class TheAlternateSelfTurnsTheMeasureAround(_Drifting):
    """10 Abyssal, 100 Celestial. As herself, 10 is no drift. In the Abyssal self the
    threshold is the floor of 20 and her 100 Celestial is drift: 1 + 79 // 20 = 4 steps,
    difficulty 18."""

    abyssal_balance = 10

    def test_her_celestial_balance_becomes_drift_in_the_abyssal_self(self) -> None:
        self.assertEqual(self.cast().focus_difficulties, [])
        self.shift(self.ysmay)
        self.assertEqual(self.cast(focus="Success").focus_difficulties, [18])


class NoAuraNoContest(ResonanceCacheIsolationMixin, JourneyCase):
    """A caster with no aura row and drift on her books rolls nothing and errs nothing."""

    def test_a_cast_without_an_aura(self) -> None:
        Affinity.objects.clear_cache()
        _celestial, _primal, abyssal = ensure_canonical_affinities()
        CheckSystemSetupFactory.create()
        room = self.make_room("The Cellar")
        SceneFactory(room=room)
        hobb = self.make_player("Hobb", room=room)
        sheet = hobb.sheet_data
        CharacterAnimaFactory(character=sheet, current=30, maximum=30)
        CharacterVitals.objects.create(
            character_sheet=sheet, health=50, max_health=50, base_max_health=50
        )
        cast_type = CheckTypeFactory()
        technique = TechniqueFactory(
            gift=GiftFactory(),
            anima_cost=1,
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_template=ActionTemplateFactory(check_type=cast_type),
        )
        grant_technique(sheet.primary_persona, technique)
        CharacterResonanceFactory(
            character_sheet=sheet, resonance=ResonanceFactory(affinity=abyssal), balance=500
        )
        _focus_type, condition = _author_conflict(cast_type)
        self.watch(hobb)
        # A failure is forced for the first roll: had a focus roll been made, it would
        # have taken it and laid the conflict on her.
        with force_check_outcome(CheckOutcome.objects.get(name="Failure")):
            outcome = self.web(hobb, "cast_technique", technique_id=technique.pk)
        self.assertTrue(outcome.detail.success, outcome.detail.message)
        self.assertFalse(
            ConditionInstance.objects.filter(target=hobb, condition=condition).exists()
        )
        self.assertNotTold(hobb, "You lose your focus")


class _DriftingInCombat(_AShifter):
    """Ysmay, 60 Abyssal against 100 Celestial, in a combat round against Gristle."""

    def setUp(self) -> None:
        super().setUp()
        AffinityInteraction.objects.clear_cache()
        CheckSystemSetupFactory.create()
        self.ysmay, self.sheet, _alt = self.make_shifter(
            "Ysmay", room=self.room, mask_affinity=self.abyssal
        )
        self.cast_type = CheckTypeFactory()
        self.cast_stat = StatTraitFactory()
        CheckTypeTraitFactory(check_type=self.cast_type, trait=self.cast_stat, weight=1)
        self.technique = TechniqueFactory(
            name="Ember Lash",
            gift=GiftFactory(),
            anima_cost=1,
            effect_type=EffectTypeFactory(base_power=10),
            action_category=ActionCategory.PHYSICAL,
            action_template=ActionTemplateFactory(check_type=self.cast_type),
            clash_capable=True,
        )
        CharacterTechniqueFactory(character=self.sheet, technique=self.technique)
        CharacterAnimaFactory(character=self.sheet, current=20, maximum=30)
        CharacterVitals.objects.create(
            character_sheet=self.sheet, health=50, max_health=50, base_max_health=50
        )
        CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=ResonanceFactory(affinity=self.celestial),
            balance=100,
        )
        self.abyssal_resonance = ResonanceFactory(name="Ashfall", affinity=self.abyssal)
        CharacterResonanceFactory(
            character_sheet=self.sheet, resonance=self.abyssal_resonance, balance=60
        )
        self.focus_type, self.condition = _author_conflict(self.cast_type)
        # A manual pace: the declaration never resolves the round by itself, and the
        # resolve below is the one a GM's resolve call makes.
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING,
            round_number=1,
            room=self.room,
            pace_mode=PaceMode.MANUAL,
        )
        CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.sheet, status=ParticipantStatus.ACTIVE
        )
        self.opponent = CombatOpponentFactory(encounter=self.encounter, name="Gristle")


class ACombatCastRollsFocusOnce(_DriftingInCombat):
    """Ysmay declares a technique in a combat round from telnet; the round's resolution
    rolls her focus once, before her offense roll."""

    def test_the_round_rolls_focus_once_and_the_conflict_reaches_the_offense_roll(self) -> None:
        failure = CheckOutcome.objects.get(name="Failure")
        self.watch(self.ysmay)
        with (
            _Recorder(focus_type=self.focus_type, cast_type=self.cast_type) as rec,
            force_check_outcome(failure),
        ):
            told = self.telnet(self.ysmay, "cast Ember Lash at Gristle")
            self.encounter.refresh_from_db()
            self.assertEqual(self.encounter.round_number, 1, told)
            self.assertEqual(rec.focus_difficulties, [], "declaring rolls nothing")
            resolve_round(self.encounter)
        self.assertEqual(rec.focus_difficulties, [12], told)
        self.assertTold(self.ysmay, f"You lose your focus as you work Ember Lash: {CONFLICT}.")
        self.assertTrue(
            ConditionInstance.objects.filter(target=self.ysmay, condition=self.condition).exists()
        )
        self.assertEqual(len(rec.cast_breakdowns), 1)
        self.assertEqual(_labels(rec.cast_breakdowns[0]).get(CONFLICT), PENALTY)


class ACombatRoundPullAddsAStep(_DriftingInCombat):
    """Ysmay pulls an Abyssal thread with her combat cast. The pull is committed when she
    declares, and the round's resolution counts it toward her focus roll: one step for
    her drift (59 Abyssal after the pull's cost) and one for the off-aura pull,
    difficulty 14."""

    def test_the_committed_pull_makes_the_focus_roll_harder(self) -> None:
        ThreadPullCostFactory(tier=1, resonance_cost=1, anima_per_thread=0)
        ThreadPullEffectFactory(
            target_kind=TargetKind.TRAIT,
            resonance=self.abyssal_resonance,
            tier=1,
            flat_bonus_amount=1,
            effect_kind=EffectKind.FLAT_BONUS,
        )
        CharacterThreadWeavingUnlockFactory(
            character=self.sheet,
            unlock=ThreadWeavingUnlockFactory(
                target_kind=TargetKind.TRAIT, unlock_trait=self.cast_stat
            ),
        )
        weave_thread(
            self.sheet, TargetKind.TRAIT, self.cast_stat, self.abyssal_resonance, name="Ash"
        )
        success = CheckOutcome.objects.get(name="Success")
        with (
            _Recorder(focus_type=self.focus_type, cast_type=self.cast_type) as rec,
            force_check_outcome(success),
        ):
            told = self.telnet(self.ysmay, "cast Ember Lash at Gristle pull=Ash resonance=Ashfall")
            self.ysmay.resonances.invalidate()
            resolve_round(self.encounter)
        self.assertEqual(rec.focus_difficulties, [14], told)


class AClashContributionRollsFocus(_DriftingInCombat):
    """Ysmay commits Ember Lash to a clash against Gristle from telnet. When the round
    resolves, her contribution rolls her focus first; the conflict a failed roll lays
    on her is on that same contribution's roll."""

    def setUp(self) -> None:
        super().setUp()
        ClashConfigFactory()
        StrainConfigFactory()
        # The clash settles its round on an outcome tier the check charts do not carry.
        CheckOutcomeFactory(name="Clash Lost", success_level=-2)
        self.clash = ClashFactory(
            encounter=self.encounter,
            npc_opponent=self.opponent,
            status=ClashStatus.ACTIVE,
            started_round=1,
        )

    def test_the_conflict_reaches_the_contribution_roll(self) -> None:
        failure = CheckOutcome.objects.get(name="Failure")
        self.watch(self.ysmay)
        with (
            _Recorder(focus_type=self.focus_type, cast_type=self.cast_type) as rec,
            force_check_outcome(failure),
        ):
            told = self.telnet(self.ysmay, "clash Gristle with Ember Lash")
            self.assertEqual(rec.focus_difficulties, [], "committing rolls nothing")
            resolve_round(self.encounter)
        self.assertEqual(rec.focus_difficulties, [12], told)
        self.assertTold(self.ysmay, f"You lose your focus as you work Ember Lash: {CONFLICT}.")
        self.assertTrue(
            ClashContribution.objects.filter(
                clash_round__clash=self.clash, character=self.sheet
            ).exists()
        )
        self.assertEqual(len(rec.cast_breakdowns), 1)
        self.assertEqual(_labels(rec.cast_breakdowns[0]).get(CONFLICT), PENALTY)


class AnEnchantedFlirtRollsFocusToo(ResonanceCacheIsolationMixin, JourneyCase):
    """A technique-enhanced social action is a cast: Ysmay, 60 Abyssal against 100
    Celestial, flirts with Hobb through a technique and rolls her focus at 12 when Hobb
    accepts."""

    def setUp(self) -> None:
        super().setUp()
        Affinity.objects.clear_cache()
        AffinityInteraction.objects.clear_cache()
        celestial, _primal, abyssal = ensure_canonical_affinities()
        CheckSystemSetupFactory.create()
        self.seed_social_engagement()
        self.parlor = self.make_room("The Parlor")
        self.scene = SceneFactory(room=self.parlor)
        flirt = next(t for t in create_social_action_templates() if t.name == "Flirt")
        self.ysmay = self.make_player("Ysmay", room=self.parlor)
        self.hobb = self.make_player("Hobb", room=self.parlor)
        sheet = self.ysmay.sheet_data
        CharacterAuraFactory(
            character=sheet,
            celestial=Decimal("80.00"),
            primal=Decimal("0.00"),
            abyssal=Decimal("20.00"),
        )
        self.technique = TechniqueFactory(
            name="Mesmerizing Gaze", intensity=3, control=8, anima_cost=2, gift=GiftFactory()
        )
        CharacterTechniqueFactory(character=sheet, technique=self.technique)
        CharacterAnimaFactory(character=sheet, current=30, maximum=30)
        ActionEnhancement.objects.create(
            base_action_key="flirt",
            variant_name="Enchanted Flirt",
            source_type="technique",
            technique=self.technique,
        )
        CharacterResonanceFactory(
            character_sheet=sheet, resonance=ResonanceFactory(affinity=celestial), balance=100
        )
        CharacterResonanceFactory(
            character_sheet=sheet, resonance=ResonanceFactory(affinity=abyssal), balance=60
        )
        self.focus_type, self.condition = _author_conflict(flirt.check_type)
        self.flirt_type = flirt.check_type

    def test_the_flirt_rolls_focus_once(self) -> None:
        created = self.api(self.account_of(self.ysmay)).post(
            reverse("sceneactionrequest-list"),
            {
                "scene": self.scene.pk,
                "initiator_persona": self.ysmay.sheet_data.primary_persona.pk,
                "target_persona": self.hobb.sheet_data.primary_persona.pk,
                "action_key": "flirt",
                "technique_id": self.technique.pk,
            },
            format="json",
            headers={"X-Character-ID": str(self.ysmay.pk)},
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        failure = CheckOutcome.objects.get(name="Failure")
        self.watch(self.ysmay)
        with (
            _Recorder(focus_type=self.focus_type, cast_type=self.flirt_type) as rec,
            force_check_outcome(failure),
        ):
            accepted = self.api(self.account_of(self.hobb)).post(
                reverse("sceneactionrequest-respond", args=[created.data["id"]]),
                {"decision": "accept"},
                format="json",
                headers={"X-Character-ID": str(self.hobb.pk)},
            )
        self.assertEqual(accepted.status_code, status.HTTP_200_OK, accepted.data)
        self.assertEqual(rec.focus_difficulties, [12])
        self.assertTold(
            self.ysmay, f"You lose your focus as you work Mesmerizing Gaze: {CONFLICT}."
        )
        self.assertTrue(
            ConditionInstance.objects.filter(target=self.ysmay, condition=self.condition).exists()
        )

"""Tests for the situation evaluator registry (#2536, Task 2; parameterized
#2623 Task 3).

Per evaluator: a fixture-built TRUE case, a FALSE case, and a missing-context
False case (spec convention: a missing required field always reads False).
Every call site passes ``NO_PARAMS`` unless the evaluator's own params matter
to the case under test (the affinity matrix, origin-side, and per-row
threshold classes below).

Built in ``setUp`` rather than ``setUpTestData`` throughout — factories here
create Evennia ``ObjectDB`` instances (``DbHolder``, not deepcopyable), which
would break ``setUpTestData``'s deepcopy (same rationale as
``world/combat/tests/test_technique_can_reach.py`` and
``world/combat/tests/test_position_cover.py``).
"""

from __future__ import annotations

from decimal import Decimal

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from evennia import create_object

from world.areas.positioning.services import connect_positions, create_position, place_in_position
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import CombatManeuver, ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    CombatRoundActionFactory,
    EngagementLockFactory,
    PendingOpponentAttackFactory,
)
from world.combat.models import CombatEncounter
from world.combat.round_context import CombatRoundContext
from world.conditions.factories import ConditionInstanceFactory
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
)
from world.covenants.perks import evaluators
from world.covenants.perks.constants import Situation, SituationOriginSide
from world.covenants.perks.context import NO_PARAMS, SituationContext, SituationParams
from world.covenants.perks.evaluators import SITUATION_EVALUATORS
from world.magic.constants import TechniqueFunction
from world.magic.factories import (
    CharacterAuraFactory,
    TechniqueFactory,
    TechniqueFunctionTagFactory,
)
from world.magic.types.aura import AffinityType
from world.npc_services.factories import NPCStandingFactory
from world.scenes.factories import PersonaFactory, SceneFactory
from world.vitals.models import CharacterVitals


class SituationEvaluatorRegistryTests(TestCase):
    """The registry carries exactly every live ``Situation`` value (9 from slice 1,
    ``CHAMPION_DUEL`` from slice 3 Task 3, ``COMBAT_OPENED_FROM_PARLEY`` and
    ``AMBUSH_UNDERWAY`` from slice 3 Task 4, ``ALLY_INTERCEPTED_FOR_ME`` from
    slice 3 Task 5, ``ATTACKER_AFFINITY`` from slice 3 Task 6 (#2536), plus
    ``ON_CHOSEN_GROUND`` (#2646))."""

    def test_registry_covers_every_surviving_situation(self) -> None:
        self.assertEqual(set(SITUATION_EVALUATORS), set(Situation.values))

    def test_registry_values_are_callable(self) -> None:
        for func in SITUATION_EVALUATORS.values():
            self.assertTrue(callable(func))


class AtRangeInMeleeEvaluatorTests(TestCase):
    """AT_RANGE / IN_MELEE read the subject's positional adjacency to engaged enemies."""

    def setUp(self) -> None:
        self.room = create_object("typeclasses.rooms.Room", key="MeleeRoom", nohome=True)
        self.pos_a = create_position(self.room, "pos_a")
        self.pos_b = create_position(self.room, "pos_b")
        connect_positions(self.pos_a, self.pos_b, is_passable=True)

        self.scene = SceneFactory(location=self.room)
        self.holder_sheet = CharacterSheetFactory()
        self.holder_sheet.character.location = self.room
        self.holder_sheet.character.save()
        place_in_position(self.holder_sheet.character, self.pos_a)

        self.encounter = CombatEncounter.objects.create(scene=self.scene, room=self.room)
        self.participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.holder_sheet
        )
        self.resolution = CombatRoundContext(self.participant)

    def _engage_opponent_at(self, position):
        opponent = CombatOpponentFactory(encounter=self.encounter)
        place_in_position(opponent.objectdb, position)
        EngagementLockFactory(
            encounter=self.encounter, participant=self.participant, opponent=opponent
        )
        return opponent

    def _ctx(self, resolution) -> SituationContext:
        return SituationContext(
            holder=self.holder_sheet, subject=self.holder_sheet, target=None, resolution=resolution
        )

    def test_in_melee_true_when_engaged_enemy_shares_position(self) -> None:
        self._engage_opponent_at(self.pos_a)
        ctx = self._ctx(self.resolution)
        self.assertTrue(evaluators.in_melee(ctx, NO_PARAMS))
        self.assertFalse(evaluators.at_range(ctx, NO_PARAMS))

    def test_at_range_true_when_engaged_enemy_elsewhere(self) -> None:
        self._engage_opponent_at(self.pos_b)
        ctx = self._ctx(self.resolution)
        self.assertFalse(evaluators.in_melee(ctx, NO_PARAMS))
        self.assertTrue(evaluators.at_range(ctx, NO_PARAMS))

    def test_missing_context_returns_false(self) -> None:
        ctx = self._ctx(None)
        self.assertFalse(evaluators.in_melee(ctx, NO_PARAMS))
        self.assertFalse(evaluators.at_range(ctx, NO_PARAMS))


class SurroundedEvaluatorTests(TestCase):
    """SURROUNDED fires at >= SURROUNDED_LOCK_THRESHOLD active EngagementLock rows."""

    def setUp(self) -> None:
        self.holder_sheet = CharacterSheetFactory()
        self.participant = CombatParticipantFactory(character_sheet=self.holder_sheet)
        self.resolution = CombatRoundContext(self.participant)

    def _ctx(self, resolution) -> SituationContext:
        return SituationContext(
            holder=self.holder_sheet, subject=self.holder_sheet, target=None, resolution=resolution
        )

    def test_true_at_threshold(self) -> None:
        EngagementLockFactory(participant=self.participant, encounter=self.participant.encounter)
        EngagementLockFactory(participant=self.participant, encounter=self.participant.encounter)
        self.assertTrue(evaluators.surrounded(self._ctx(self.resolution), NO_PARAMS))

    def test_false_below_threshold(self) -> None:
        EngagementLockFactory(participant=self.participant, encounter=self.participant.encounter)
        self.assertFalse(evaluators.surrounded(self._ctx(self.resolution), NO_PARAMS))

    def test_missing_context_returns_false(self) -> None:
        self.assertFalse(evaluators.surrounded(self._ctx(None), NO_PARAMS))

    def test_surrounded_row_threshold(self) -> None:
        """An authored count_threshold overrides SURROUNDED_LOCK_THRESHOLD per row."""
        EngagementLockFactory(participant=self.participant, encounter=self.participant.encounter)
        EngagementLockFactory(participant=self.participant, encounter=self.participant.encounter)
        self.assertFalse(
            evaluators.surrounded(self._ctx(self.resolution), SituationParams(count_threshold=3))
        )
        self.assertTrue(evaluators.surrounded(self._ctx(self.resolution), NO_PARAMS))


class TargetDistractedEvaluatorTests(TestCase):
    """TARGET_DISTRACTED reads an active condition sourced from a DISTRACTION/CHARM technique."""

    def setUp(self) -> None:
        self.holder_sheet = CharacterSheetFactory()
        self.target_sheet = CharacterSheetFactory()
        self.technique = TechniqueFactory()
        TechniqueFunctionTagFactory(
            technique=self.technique, function=TechniqueFunction.DISTRACTION
        )

    def _ctx(self, target) -> SituationContext:
        return SituationContext(
            holder=self.holder_sheet, subject=self.holder_sheet, target=target, resolution=None
        )

    def test_true_when_distraction_condition_active(self) -> None:
        ConditionInstanceFactory(
            target=self.target_sheet.character, source_technique=self.technique
        )
        self.assertTrue(evaluators.target_distracted(self._ctx(self.target_sheet), NO_PARAMS))

    def test_false_when_no_matching_condition(self) -> None:
        self.assertFalse(evaluators.target_distracted(self._ctx(self.target_sheet), NO_PARAMS))

    def test_missing_context_returns_false(self) -> None:
        self.assertFalse(evaluators.target_distracted(self._ctx(None), NO_PARAMS))


class TargetSwayedByAllyEvaluatorTests(TestCase):
    """TARGET_SWAYED_BY_ALLY: the condition's applier is holder or a covenant-mate."""

    def setUp(self) -> None:
        self.holder_sheet = CharacterSheetFactory()
        self.target_sheet = CharacterSheetFactory()
        self.stranger_sheet = CharacterSheetFactory()
        self.technique = TechniqueFactory()
        TechniqueFunctionTagFactory(technique=self.technique, function=TechniqueFunction.CHARM)

    def _ctx(self, target) -> SituationContext:
        return SituationContext(
            holder=self.holder_sheet, subject=self.holder_sheet, target=target, resolution=None
        )

    def test_true_when_applied_by_holder(self) -> None:
        ConditionInstanceFactory(
            target=self.target_sheet.character,
            source_technique=self.technique,
            source_character=self.holder_sheet.character,
        )
        self.assertTrue(evaluators.target_swayed_by_ally(self._ctx(self.target_sheet), NO_PARAMS))

    def test_true_when_applied_by_covenant_mate(self) -> None:
        mate_sheet = CharacterSheetFactory()
        covenant = CovenantFactory()
        role = CovenantRoleFactory(covenant_type=covenant.covenant_type)
        CharacterCovenantRoleFactory(
            character_sheet=self.holder_sheet, covenant=covenant, covenant_role=role
        )
        CharacterCovenantRoleFactory(
            character_sheet=mate_sheet, covenant=covenant, covenant_role=role
        )
        ConditionInstanceFactory(
            target=self.target_sheet.character,
            source_technique=self.technique,
            source_character=mate_sheet.character,
        )
        self.assertTrue(evaluators.target_swayed_by_ally(self._ctx(self.target_sheet), NO_PARAMS))

    def test_false_when_applied_by_stranger(self) -> None:
        ConditionInstanceFactory(
            target=self.target_sheet.character,
            source_technique=self.technique,
            source_character=self.stranger_sheet.character,
        )
        self.assertFalse(evaluators.target_swayed_by_ally(self._ctx(self.target_sheet), NO_PARAMS))

    def test_missing_context_returns_false(self) -> None:
        self.assertFalse(evaluators.target_swayed_by_ally(self._ctx(None), NO_PARAMS))


class TargetFocusedElsewhereEvaluatorTests(TestCase):
    """TARGET_FOCUSED_ELSEWHERE reads the target's declared CombatRoundAction target(s)."""

    def setUp(self) -> None:
        self.subject_sheet = CharacterSheetFactory()
        self.target_sheet = CharacterSheetFactory()
        self.encounter = CombatEncounterFactory(round_number=1)
        self.subject_participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.subject_sheet
        )
        self.target_participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.target_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        self.resolution = CombatRoundContext(self.subject_participant)

    def _ctx(self, resolution) -> SituationContext:
        return SituationContext(
            holder=self.subject_sheet,
            subject=self.subject_sheet,
            target=self.target_sheet,
            resolution=resolution,
        )

    def test_true_when_target_declared_action_targets_an_opponent(self) -> None:
        opponent = CombatOpponentFactory(encounter=self.encounter)
        CombatRoundActionFactory(
            participant=self.target_participant, round_number=1, focused_opponent_target=opponent
        )
        self.assertTrue(evaluators.target_focused_elsewhere(self._ctx(self.resolution), NO_PARAMS))

    def test_false_when_target_declared_action_targets_subject(self) -> None:
        CombatRoundActionFactory(
            participant=self.target_participant,
            round_number=1,
            focused_ally_target=self.subject_participant,
        )
        self.assertFalse(evaluators.target_focused_elsewhere(self._ctx(self.resolution), NO_PARAMS))

    def test_missing_context_returns_false(self) -> None:
        self.assertFalse(evaluators.target_focused_elsewhere(self._ctx(None), NO_PARAMS))


class AllyLowHealthEvaluatorTests(TestCase):
    """ALLY_LOW_HEALTH: a covenant-mate's health falls below the fraction.

    "Ally" is scoped to a covenant-mate holding a non-departed role in a
    covenant the holder is also actively engaged in (#2536 reversal, Tehom
    2026-07-20: the MATE's own ``engaged`` flag is irrelevant — a KO'd or
    disengaged covenant-mate still in the encounter keeps counting, so
    losing allies mid-fight never weakens the survivors).
    """

    def setUp(self) -> None:
        self.covenant = CovenantFactory()
        self.role = CovenantRoleFactory(covenant_type=self.covenant.covenant_type)
        self.holder_sheet = CharacterSheetFactory()
        self.mate_sheet = CharacterSheetFactory()
        CharacterCovenantRoleFactory(
            character_sheet=self.holder_sheet, covenant=self.covenant, covenant_role=self.role
        )
        self.encounter = CombatEncounterFactory()
        self.holder_participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.holder_sheet
        )
        CombatParticipantFactory(encounter=self.encounter, character_sheet=self.mate_sheet)
        self.resolution = CombatRoundContext(self.holder_participant)

    def _ctx(self, resolution) -> SituationContext:
        return SituationContext(
            holder=self.holder_sheet, subject=self.holder_sheet, target=None, resolution=resolution
        )

    def _mate_membership(self, *, engaged: bool) -> None:
        CharacterCovenantRoleFactory(
            character_sheet=self.mate_sheet,
            covenant=self.covenant,
            covenant_role=self.role,
            engaged=engaged,
        )

    def test_true_when_engaged_mate_below_fraction(self) -> None:
        self._mate_membership(engaged=True)
        CharacterVitals.objects.create(character_sheet=self.mate_sheet, health=10, max_health=100)
        self.assertTrue(evaluators.ally_low_health(self._ctx(self.resolution), NO_PARAMS))

    def test_false_when_mate_healthy(self) -> None:
        self._mate_membership(engaged=True)
        CharacterVitals.objects.create(character_sheet=self.mate_sheet, health=90, max_health=100)
        self.assertFalse(evaluators.ally_low_health(self._ctx(self.resolution), NO_PARAMS))

    def test_true_when_mate_unengaged(self) -> None:
        """Reversal (Tehom 2026-07-20): an unengaged low-health covenant-mate still
        counts — Last Bulwark fires hardest exactly when mates are down."""
        self._mate_membership(engaged=False)
        CharacterVitals.objects.create(character_sheet=self.mate_sheet, health=10, max_health=100)
        self.assertTrue(evaluators.ally_low_health(self._ctx(self.resolution), NO_PARAMS))

    def test_missing_context_returns_false(self) -> None:
        self._mate_membership(engaged=True)
        CharacterVitals.objects.create(character_sheet=self.mate_sheet, health=10, max_health=100)
        self.assertFalse(evaluators.ally_low_health(self._ctx(None), NO_PARAMS))

    def test_ally_low_health_row_threshold(self) -> None:
        """An authored threshold_percent overrides ALLY_LOW_HEALTH_FRACTION per row."""
        self._mate_membership(engaged=True)
        CharacterVitals.objects.create(character_sheet=self.mate_sheet, health=40, max_health=100)
        self.assertFalse(
            evaluators.ally_low_health(
                self._ctx(self.resolution), SituationParams(threshold_percent=25)
            )
        )
        self.assertTrue(
            evaluators.ally_low_health(
                self._ctx(self.resolution), SituationParams(threshold_percent=50)
            )
        )


class AllyLowHealthQueryBudgetTests(TestCase):
    """ALLY_LOW_HEALTH resolves membership with a FIXED query count (Task 2 review Important #1).

    Regression test for the N+1 previously caused by calling
    ``shares_covenant_with`` once per candidate mate inside the evaluator's
    loop — the query count must not scale with the number of mates.
    """

    def setUp(self) -> None:
        self.covenant = CovenantFactory()
        self.role = CovenantRoleFactory(covenant_type=self.covenant.covenant_type)
        self.holder_sheet = CharacterSheetFactory()
        CharacterCovenantRoleFactory(
            character_sheet=self.holder_sheet, covenant=self.covenant, covenant_role=self.role
        )
        self.encounter = CombatEncounterFactory()
        self.holder_participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.holder_sheet
        )
        self.resolution = CombatRoundContext(self.holder_participant)

    def _ctx(self) -> SituationContext:
        return SituationContext(
            holder=self.holder_sheet,
            subject=self.holder_sheet,
            target=None,
            resolution=self.resolution,
        )

    def _add_engaged_mates(self, count: int) -> None:
        for _ in range(count):
            mate_sheet = CharacterSheetFactory()
            CharacterCovenantRoleFactory(
                character_sheet=mate_sheet,
                covenant=self.covenant,
                covenant_role=self.role,
                engaged=True,
            )
            CombatParticipantFactory(encounter=self.encounter, character_sheet=mate_sheet)
            CharacterVitals.objects.create(character_sheet=mate_sheet, health=90, max_health=100)

    def _count_queries(self) -> int:
        with CaptureQueriesContext(connection) as ctx:
            evaluators.ally_low_health(self._ctx(), NO_PARAMS)
        return len(ctx)

    def test_query_count_fixed_regardless_of_mate_count(self) -> None:
        # Warm the holder's covenant-roles handler cache first, so both
        # measurements below start from the same (warm) state and compare
        # only the queries that genuinely run per evaluation.
        evaluators.ally_low_health(self._ctx(), NO_PARAMS)

        self._add_engaged_mates(2)
        count_with_two = self._count_queries()

        self._add_engaged_mates(3)  # 5 total mates now
        count_with_five = self._count_queries()

        self.assertEqual(count_with_two, count_with_five)


class DuringNegotiationEvaluatorTests(TestCase):
    """DURING_NEGOTIATION: an active room-scoped Scene while NOT resolving in combat."""

    def setUp(self) -> None:
        self.room = create_object("typeclasses.rooms.Room", key="NegotiationRoom", nohome=True)
        self.subject_sheet = CharacterSheetFactory()
        self.subject_sheet.character.location = self.room
        self.subject_sheet.character.save()

    def _ctx(self, resolution, subject=True) -> SituationContext:
        return SituationContext(
            holder=self.subject_sheet,
            subject=self.subject_sheet if subject else None,
            target=None,
            resolution=resolution,
        )

    def test_true_when_active_scene_and_not_in_combat(self) -> None:
        SceneFactory(location=self.room)
        self.assertTrue(evaluators.during_negotiation(self._ctx(None), NO_PARAMS))

    def test_false_when_no_active_scene(self) -> None:
        self.assertFalse(evaluators.during_negotiation(self._ctx(None), NO_PARAMS))

    def test_false_when_resolving_in_combat(self) -> None:
        SceneFactory(location=self.room)
        participant = CombatParticipantFactory(character_sheet=self.subject_sheet)
        resolution = CombatRoundContext(participant)
        self.assertFalse(evaluators.during_negotiation(self._ctx(resolution), NO_PARAMS))

    def test_missing_context_returns_false(self) -> None:
        self.assertFalse(evaluators.during_negotiation(self._ctx(None, subject=False), NO_PARAMS))


class TargetFavorablyDisposedEvaluatorTests(TestCase):
    """TARGET_FAVORABLY_DISPOSED reads NPCStanding.affection between holder and target."""

    def setUp(self) -> None:
        self.holder_sheet = CharacterSheetFactory()
        self.target_sheet = CharacterSheetFactory()

    def _ctx(self, target) -> SituationContext:
        return SituationContext(
            holder=self.holder_sheet, subject=self.holder_sheet, target=target, resolution=None
        )

    def test_true_when_affection_favorable(self) -> None:
        NPCStandingFactory(
            persona=self.holder_sheet.primary_persona,
            npc_persona=self.target_sheet.primary_persona,
            affection=5,
        )
        ctx = self._ctx(self.target_sheet)
        self.assertTrue(evaluators.target_favorably_disposed(ctx, NO_PARAMS))

    def test_false_when_no_standing_row(self) -> None:
        ctx = self._ctx(self.target_sheet)
        self.assertFalse(evaluators.target_favorably_disposed(ctx, NO_PARAMS))

    def test_missing_context_returns_false(self) -> None:
        self.assertFalse(evaluators.target_favorably_disposed(self._ctx(None), NO_PARAMS))

    def test_favorably_disposed_row_threshold(self) -> None:
        """An authored count_threshold overrides FAVORABLY_DISPOSED_MIN_AFFECTION
        per row."""
        NPCStandingFactory(
            persona=self.holder_sheet.primary_persona,
            npc_persona=self.target_sheet.primary_persona,
            affection=1,
        )
        ctx = self._ctx(self.target_sheet)
        self.assertFalse(
            evaluators.target_favorably_disposed(ctx, SituationParams(count_threshold=2))
        )
        self.assertTrue(evaluators.target_favorably_disposed(ctx, NO_PARAMS))


class ChampionDuelEvaluatorTests(TestCase):
    """CHAMPION_DUEL reads the subject's resolution participant's encounter flag
    (#2536 slice 3 Battle wiring)."""

    def setUp(self) -> None:
        self.room = create_object("typeclasses.rooms.Room", key="ChampionDuelRoom", nohome=True)
        self.scene = SceneFactory(location=self.room)
        self.sheet = CharacterSheetFactory()

    def _ctx(self, resolution) -> SituationContext:
        return SituationContext(
            holder=self.sheet, subject=self.sheet, target=None, resolution=resolution
        )

    def test_true_in_champion_duel_encounter(self) -> None:
        encounter = CombatEncounterFactory(scene=self.scene, room=self.room, is_champion_duel=True)
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=self.sheet)
        resolution = CombatRoundContext(participant)
        self.assertTrue(evaluators.champion_duel(self._ctx(resolution), NO_PARAMS))

    def test_false_in_ordinary_encounter(self) -> None:
        encounter = CombatEncounterFactory(scene=self.scene, room=self.room)
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=self.sheet)
        resolution = CombatRoundContext(participant)
        self.assertFalse(evaluators.champion_duel(self._ctx(resolution), NO_PARAMS))

    def test_false_outside_combat(self) -> None:
        self.assertFalse(evaluators.champion_duel(self._ctx(None), NO_PARAMS))


class OnChosenGroundEvaluatorTests(TestCase):
    """ON_CHOSEN_GROUND reads the subject's resolution participant's encounter
    flag (#2646) — mirrors ChampionDuelEvaluatorTests exactly."""

    def setUp(self) -> None:
        self.room = create_object("typeclasses.rooms.Room", key="ChosenGroundRoom", nohome=True)
        self.scene = SceneFactory(location=self.room)
        self.sheet = CharacterSheetFactory()

    def _ctx(self, resolution) -> SituationContext:
        return SituationContext(
            holder=self.sheet, subject=self.sheet, target=None, resolution=resolution
        )

    def test_true_when_encounter_on_chosen_ground(self) -> None:
        encounter = CombatEncounterFactory(scene=self.scene, room=self.room, on_chosen_ground=True)
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=self.sheet)
        resolution = CombatRoundContext(participant)
        self.assertTrue(evaluators.on_chosen_ground(self._ctx(resolution), NO_PARAMS))

    def test_false_in_ordinary_encounter(self) -> None:
        encounter = CombatEncounterFactory(scene=self.scene, room=self.room)
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=self.sheet)
        resolution = CombatRoundContext(participant)
        self.assertFalse(evaluators.on_chosen_ground(self._ctx(resolution), NO_PARAMS))

    def test_false_outside_combat(self) -> None:
        self.assertFalse(evaluators.on_chosen_ground(self._ctx(None), NO_PARAMS))


class CombatOpenedFromParleyEvaluatorTests(TestCase):
    """COMBAT_OPENED_FROM_PARLEY reads the subject's resolution participant's
    encounter flag (#2536 slice 3, Task 4)."""

    def setUp(self) -> None:
        self.room = create_object("typeclasses.rooms.Room", key="ParleyOriginRoom", nohome=True)
        self.scene = SceneFactory(location=self.room)
        self.sheet = CharacterSheetFactory()

    def _ctx(self, resolution) -> SituationContext:
        return SituationContext(
            holder=self.sheet, subject=self.sheet, target=None, resolution=resolution
        )

    def test_true_when_encounter_opened_from_parley(self) -> None:
        encounter = CombatEncounterFactory(
            scene=self.scene, room=self.room, opened_from_parley=True
        )
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=self.sheet)
        resolution = CombatRoundContext(participant)
        self.assertTrue(evaluators.combat_opened_from_parley(self._ctx(resolution), NO_PARAMS))

    def test_false_in_ordinary_encounter(self) -> None:
        encounter = CombatEncounterFactory(scene=self.scene, room=self.room)
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=self.sheet)
        resolution = CombatRoundContext(participant)
        self.assertFalse(evaluators.combat_opened_from_parley(self._ctx(resolution), NO_PARAMS))

    def test_false_outside_combat(self) -> None:
        self.assertFalse(evaluators.combat_opened_from_parley(self._ctx(None), NO_PARAMS))


class AmbushUnderwayEvaluatorTests(TestCase):
    """AMBUSH_UNDERWAY holds only during round 1 of a surprise-opened encounter
    (#2536 slice 3, Task 4): ``opened_from_parley=True`` OR a round-1
    ``from_entrance=True`` ``CombatRoundAction`` — False from round 2 on."""

    def setUp(self) -> None:
        self.room = create_object("typeclasses.rooms.Room", key="AmbushRoom", nohome=True)
        self.scene = SceneFactory(location=self.room)
        self.sheet = CharacterSheetFactory()

    def _ctx(self, resolution) -> SituationContext:
        return SituationContext(
            holder=self.sheet, subject=self.sheet, target=None, resolution=resolution
        )

    def test_true_round_one_from_entrance_action(self) -> None:
        encounter = CombatEncounterFactory(scene=self.scene, room=self.room, round_number=1)
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=self.sheet)
        CombatRoundActionFactory(participant=participant, round_number=1, from_entrance=True)
        resolution = CombatRoundContext(participant)
        self.assertTrue(evaluators.ambush_underway(self._ctx(resolution), NO_PARAMS))

    def test_true_round_one_opened_from_parley(self) -> None:
        encounter = CombatEncounterFactory(
            scene=self.scene, room=self.room, round_number=1, opened_from_parley=True
        )
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=self.sheet)
        resolution = CombatRoundContext(participant)
        self.assertTrue(evaluators.ambush_underway(self._ctx(resolution), NO_PARAMS))

    def test_false_round_two_even_with_from_entrance_action(self) -> None:
        encounter = CombatEncounterFactory(scene=self.scene, room=self.room, round_number=2)
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=self.sheet)
        CombatRoundActionFactory(participant=participant, round_number=1, from_entrance=True)
        resolution = CombatRoundContext(participant)
        self.assertFalse(evaluators.ambush_underway(self._ctx(resolution), NO_PARAMS))

    def test_false_round_one_without_surprise_origin(self) -> None:
        encounter = CombatEncounterFactory(scene=self.scene, room=self.room, round_number=1)
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=self.sheet)
        CombatRoundActionFactory(participant=participant, round_number=1, from_entrance=False)
        resolution = CombatRoundContext(participant)
        self.assertFalse(evaluators.ambush_underway(self._ctx(resolution), NO_PARAMS))

    def test_false_outside_combat(self) -> None:
        self.assertFalse(evaluators.ambush_underway(self._ctx(None), NO_PARAMS))

    def _round_one_surprise_encounter(self, *, initiated_by_pc_side: bool | None):
        encounter = CombatEncounterFactory(
            scene=self.scene,
            room=self.room,
            round_number=1,
            initiated_by_pc_side=initiated_by_pc_side,
        )
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=self.sheet)
        CombatRoundActionFactory(participant=participant, round_number=1, from_entrance=True)
        return CombatRoundContext(participant)

    def test_ambush_ours_requires_pc_side_true(self) -> None:
        resolution = self._round_one_surprise_encounter(initiated_by_pc_side=True)
        params = SituationParams(origin_side=SituationOriginSide.OURS)
        self.assertTrue(evaluators.ambush_underway(self._ctx(resolution), params))

    def test_ambush_theirs_false_when_pc_side_true(self) -> None:
        resolution = self._round_one_surprise_encounter(initiated_by_pc_side=True)
        params = SituationParams(origin_side=SituationOriginSide.THEIRS)
        self.assertFalse(evaluators.ambush_underway(self._ctx(resolution), params))

    def test_ambush_directed_false_when_initiator_null(self) -> None:
        """A non-blank origin_side never holds when the initiator is unprovable
        (NULL initiated_by_pc_side) — regression for #2623 spec §3."""
        resolution = self._round_one_surprise_encounter(initiated_by_pc_side=None)
        params = SituationParams(origin_side=SituationOriginSide.OURS)
        self.assertFalse(evaluators.ambush_underway(self._ctx(resolution), params))

    def test_ambush_blank_side_blind_unchanged(self) -> None:
        """NO_PARAMS (blank origin_side) is side-blind — today's behavior,
        unaffected by a NULL initiated_by_pc_side."""
        resolution = self._round_one_surprise_encounter(initiated_by_pc_side=None)
        self.assertTrue(evaluators.ambush_underway(self._ctx(resolution), NO_PARAMS))


class AllyInterceptedForMeEvaluatorTests(TestCase):
    """ALLY_INTERCEPTED_FOR_ME: a covenant-mate's armed INTERPOSE this round,
    guarding the subject specifically or guard-anyone (#2536 slice 3, Task 5).

    Declared cover counts — the guarded moment is the situation, it does not
    wait for damage to land (ratified judgment call, see the ``Situation``
    enum docstring).
    """

    def setUp(self) -> None:
        self.covenant = CovenantFactory()
        self.role = CovenantRoleFactory(covenant_type=self.covenant.covenant_type)
        self.holder_sheet = CharacterSheetFactory()
        self.mate_sheet = CharacterSheetFactory()
        self.other_ally_sheet = CharacterSheetFactory()
        CharacterCovenantRoleFactory(
            character_sheet=self.holder_sheet, covenant=self.covenant, covenant_role=self.role
        )
        CharacterCovenantRoleFactory(
            character_sheet=self.mate_sheet, covenant=self.covenant, covenant_role=self.role
        )
        self.encounter = CombatEncounterFactory(round_number=1)
        self.holder_participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.holder_sheet
        )
        self.mate_participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.mate_sheet
        )
        self.other_ally_participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.other_ally_sheet
        )
        self.resolution = CombatRoundContext(self.holder_participant)

    def _ctx(self, resolution: object | None) -> SituationContext:
        return SituationContext(
            holder=self.holder_sheet, subject=self.holder_sheet, target=None, resolution=resolution
        )

    def _declare_interpose(self, *, participant, is_ready: bool, focused_ally_target) -> None:
        CombatRoundActionFactory(
            participant=participant,
            round_number=self.encounter.round_number,
            maneuver=CombatManeuver.INTERPOSE,
            is_ready=is_ready,
            focused_ally_target=focused_ally_target,
        )

    def test_true_when_mate_guards_subject(self) -> None:
        self._declare_interpose(
            participant=self.mate_participant,
            is_ready=True,
            focused_ally_target=self.holder_participant,
        )
        self.assertTrue(evaluators.ally_intercepted_for_me(self._ctx(self.resolution), NO_PARAMS))

    def test_false_when_guarding_a_different_ally(self) -> None:
        self._declare_interpose(
            participant=self.mate_participant,
            is_ready=True,
            focused_ally_target=self.other_ally_participant,
        )
        self.assertFalse(evaluators.ally_intercepted_for_me(self._ctx(self.resolution), NO_PARAMS))

    def test_true_when_guard_anyone(self) -> None:
        self._declare_interpose(
            participant=self.mate_participant, is_ready=True, focused_ally_target=None
        )
        self.assertTrue(evaluators.ally_intercepted_for_me(self._ctx(self.resolution), NO_PARAMS))

    def test_false_when_interposer_not_covenant_mate(self) -> None:
        stranger_sheet = CharacterSheetFactory()
        stranger_participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=stranger_sheet
        )
        self._declare_interpose(
            participant=stranger_participant,
            is_ready=True,
            focused_ally_target=self.holder_participant,
        )
        self.assertFalse(evaluators.ally_intercepted_for_me(self._ctx(self.resolution), NO_PARAMS))

    def test_false_when_declaration_unready(self) -> None:
        self._declare_interpose(
            participant=self.mate_participant,
            is_ready=False,
            focused_ally_target=self.holder_participant,
        )
        self.assertFalse(evaluators.ally_intercepted_for_me(self._ctx(self.resolution), NO_PARAMS))

    def test_false_outside_combat(self) -> None:
        self._declare_interpose(
            participant=self.mate_participant,
            is_ready=True,
            focused_ally_target=self.holder_participant,
        )
        self.assertFalse(evaluators.ally_intercepted_for_me(self._ctx(None), NO_PARAMS))


class AllyInterceptedForMeSubjectExclusionTests(TestCase):
    """Regression for Task 5 review Critical #1: the evaluator must exclude the
    SUBJECT's own declaration, not the HOLDER's. A character can never be their
    own intercepting ally — a subject's own guard-anyone INTERPOSE must not
    self-satisfy a covenant-mate's ``COVENANT_ALLIES`` perk when holder != subject
    (#2536 slice 3, Task 5 review). Bob is the perk-owning holder; Alice is the
    acting subject; both are covenant-mates in the same encounter.
    """

    def setUp(self) -> None:
        self.covenant = CovenantFactory()
        self.role = CovenantRoleFactory(covenant_type=self.covenant.covenant_type)
        self.holder_sheet = CharacterSheetFactory()  # Bob
        self.subject_sheet = CharacterSheetFactory()  # Alice
        CharacterCovenantRoleFactory(
            character_sheet=self.holder_sheet, covenant=self.covenant, covenant_role=self.role
        )
        CharacterCovenantRoleFactory(
            character_sheet=self.subject_sheet, covenant=self.covenant, covenant_role=self.role
        )
        self.encounter = CombatEncounterFactory(round_number=1)
        self.holder_participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.holder_sheet
        )
        self.subject_participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.subject_sheet
        )
        # SituationContext.resolution is always the SUBJECT's resolution.
        self.resolution = CombatRoundContext(self.subject_participant)

    def _ctx(self) -> SituationContext:
        return SituationContext(
            holder=self.holder_sheet,
            subject=self.subject_sheet,
            target=None,
            resolution=self.resolution,
        )

    def _declare_interpose(self, *, participant, focused_ally_target) -> None:
        CombatRoundActionFactory(
            participant=participant,
            round_number=self.encounter.round_number,
            maneuver=CombatManeuver.INTERPOSE,
            is_ready=True,
            focused_ally_target=focused_ally_target,
        )

    def test_false_when_only_the_subject_guards_herself(self) -> None:
        """Alice's own armed guard-anyone INTERPOSE must not self-satisfy the
        situation on Bob's perk — no other mate is guarding her."""
        self._declare_interpose(participant=self.subject_participant, focused_ally_target=None)
        self.assertFalse(evaluators.ally_intercepted_for_me(self._ctx(), NO_PARAMS))

    def test_true_when_holder_guards_the_subject(self) -> None:
        """A companion positive case: Bob (the holder) declares guard-anyone —
        a genuine covenant-mate other than the subject — must satisfy it."""
        self._declare_interpose(participant=self.holder_participant, focused_ally_target=None)
        self.assertTrue(evaluators.ally_intercepted_for_me(self._ctx(), NO_PARAMS))


class AllyInterceptedForMeQueryBudgetTests(TestCase):
    """ALLY_INTERCEPTED_FOR_ME resolves with a FIXED query count (Task 5 review
    Minor #3 fold-in), mirroring ``AllyLowHealthQueryBudgetTests``: one
    declarations query + one batched ``CharacterCovenantRole`` membership query,
    regardless of interposer count.
    """

    def setUp(self) -> None:
        self.covenant = CovenantFactory()
        self.role = CovenantRoleFactory(covenant_type=self.covenant.covenant_type)
        self.holder_sheet = CharacterSheetFactory()
        CharacterCovenantRoleFactory(
            character_sheet=self.holder_sheet, covenant=self.covenant, covenant_role=self.role
        )
        self.encounter = CombatEncounterFactory(round_number=1)
        self.holder_participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.holder_sheet
        )
        self.resolution = CombatRoundContext(self.holder_participant)

    def _ctx(self) -> SituationContext:
        return SituationContext(
            holder=self.holder_sheet,
            subject=self.holder_sheet,
            target=None,
            resolution=self.resolution,
        )

    def _add_guarding_mates(self, count: int) -> None:
        for _ in range(count):
            mate_sheet = CharacterSheetFactory()
            CharacterCovenantRoleFactory(
                character_sheet=mate_sheet, covenant=self.covenant, covenant_role=self.role
            )
            mate_participant = CombatParticipantFactory(
                encounter=self.encounter, character_sheet=mate_sheet
            )
            CombatRoundActionFactory(
                participant=mate_participant,
                round_number=self.encounter.round_number,
                maneuver=CombatManeuver.INTERPOSE,
                is_ready=True,
                focused_ally_target=None,
            )

    def _count_queries(self) -> int:
        with CaptureQueriesContext(connection) as ctx:
            evaluators.ally_intercepted_for_me(self._ctx(), NO_PARAMS)
        return len(ctx)

    def test_query_count_fixed_regardless_of_interposer_count(self) -> None:
        # Warm the holder's covenant-roles handler cache first, so both
        # measurements below start from the same (warm) state and compare
        # only the queries that genuinely run per evaluation.
        evaluators.ally_intercepted_for_me(self._ctx(), NO_PARAMS)

        self._add_guarding_mates(1)
        count_with_one = self._count_queries()

        self._add_guarding_mates(2)  # 3 total guarding mates now
        count_with_three = self._count_queries()

        self.assertEqual(count_with_one, count_with_three)
        self.assertEqual(count_with_one, 2)


class AttackerAffinityEvaluatorTests(TestCase):
    """ATTACKER_AFFINITY (#2536 slice 3, Task 6; parameterized #2623 spec §2):
    resolution order — (1) a ``CombatOpponent`` with a non-empty authored
    ``affinity`` compares directly against ``params.affinity`` (threshold
    ignored), (2) a reachable ``ObjectDB``'s ``CharacterAura`` is the
    fallback — with ``params.threshold_percent`` set, that axis's percentage
    must be >= the threshold; unset, the aura's ``dominant_affinity`` must
    equal the axis, (3) otherwise False. ``affinity`` is a REQUIRED param
    (``SITUATION_PARAM_SPECS``) — ``NO_PARAMS`` (blank ``affinity``) never
    holds, regardless of attacker data. Never raises on missing relations;
    False when ``ctx.attacker`` is ``None``.
    """

    def setUp(self) -> None:
        self.holder_sheet = CharacterSheetFactory()
        self.subject_sheet = CharacterSheetFactory()

    def _ctx(self, attacker: object | None) -> SituationContext:
        return SituationContext(
            holder=self.holder_sheet,
            subject=self.subject_sheet,
            target=None,
            resolution=None,
            attacker=attacker,
        )

    def test_authored_affinity_axis_match(self) -> None:
        opponent = CombatOpponentFactory(affinity=AffinityType.PRIMAL)
        params = SituationParams(affinity=AffinityType.PRIMAL)
        self.assertTrue(evaluators.attacker_affinity(self._ctx(opponent), params))

    def test_authored_affinity_axis_mismatch(self) -> None:
        opponent = CombatOpponentFactory(affinity=AffinityType.ABYSSAL)
        params = SituationParams(affinity=AffinityType.PRIMAL)
        self.assertFalse(evaluators.attacker_affinity(self._ctx(opponent), params))

    def test_aura_dominant_match_without_threshold(self) -> None:
        """No authored affinity — falls back to the persona's ObjectDB
        CharacterAura's dominant axis; no threshold_percent authored."""
        persona = PersonaFactory()
        CharacterAuraFactory(
            character=persona.character_sheet.character,
            celestial=Decimal("80.00"),
            primal=Decimal("10.00"),
            abyssal=Decimal("10.00"),
        )
        opponent = CombatOpponentFactory(persona=persona)
        params = SituationParams(affinity=AffinityType.CELESTIAL)
        self.assertTrue(evaluators.attacker_affinity(self._ctx(opponent), params))

    def test_aura_axis_threshold_met(self) -> None:
        persona = PersonaFactory()
        CharacterAuraFactory(
            character=persona.character_sheet.character,
            celestial=Decimal("30.00"),
            primal=Decimal("40.00"),
            abyssal=Decimal("30.00"),
        )
        opponent = CombatOpponentFactory(persona=persona)
        params = SituationParams(affinity=AffinityType.PRIMAL, threshold_percent=30)
        self.assertTrue(evaluators.attacker_affinity(self._ctx(opponent), params))

    def test_aura_axis_threshold_not_met(self) -> None:
        persona = PersonaFactory()
        CharacterAuraFactory(
            character=persona.character_sheet.character,
            celestial=Decimal("40.00"),
            primal=Decimal("20.00"),
            abyssal=Decimal("40.00"),
        )
        opponent = CombatOpponentFactory(persona=persona)
        params = SituationParams(affinity=AffinityType.PRIMAL, threshold_percent=30)
        self.assertFalse(evaluators.attacker_affinity(self._ctx(opponent), params))

    def test_no_affinity_param_false(self) -> None:
        """affinity is a REQUIRED param — NO_PARAMS never holds, even against
        an attacker unambiguously typed to an axis."""
        opponent = CombatOpponentFactory(affinity=AffinityType.ABYSSAL)
        self.assertFalse(evaluators.attacker_affinity(self._ctx(opponent), NO_PARAMS))

    def test_false_with_no_affinity_and_no_aura_data(self) -> None:
        """A generic ephemeral opponent: no authored affinity, no CharacterAura row."""
        opponent = CombatOpponentFactory()
        params = SituationParams(affinity=AffinityType.ABYSSAL)
        self.assertFalse(evaluators.attacker_affinity(self._ctx(opponent), params))

    def test_false_when_no_attacker(self) -> None:
        params = SituationParams(affinity=AffinityType.ABYSSAL)
        self.assertFalse(evaluators.attacker_affinity(self._ctx(None), params))


class EnemyWindupEvaluatorTests(TestCase):
    """ENEMY_WINDUP_UNDERWAY / ENEMY_WINDUP_CALLED_OUT (#2637): true only while
    a not-yet-matured PendingOpponentAttack exists in the subject's encounter."""

    def setUp(self) -> None:
        self.encounter = CombatEncounterFactory(round_number=2)
        self.opponent = CombatOpponentFactory(encounter=self.encounter)
        self.subject_sheet = CharacterSheetFactory()
        self.participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.subject_sheet
        )
        self.resolution = CombatRoundContext(self.participant)

    def _ctx(self) -> SituationContext:
        return SituationContext(
            holder=self.subject_sheet,
            subject=self.subject_sheet,
            target=None,
            resolution=self.resolution,
        )

    def test_underway_true_while_pending(self) -> None:
        PendingOpponentAttackFactory(
            encounter=self.encounter,
            opponent=self.opponent,
            declared_round=1,
            resolves_round=2,
        )
        self.assertTrue(evaluators.enemy_windup_underway(self._ctx(), NO_PARAMS))

    def test_underway_false_with_no_pending_row(self) -> None:
        self.assertFalse(evaluators.enemy_windup_underway(self._ctx(), NO_PARAMS))

    def test_underway_true_for_a_future_round_too(self) -> None:
        PendingOpponentAttackFactory(
            encounter=self.encounter,
            opponent=self.opponent,
            declared_round=1,
            resolves_round=5,
        )
        self.assertTrue(evaluators.enemy_windup_underway(self._ctx(), NO_PARAMS))

    def test_called_out_false_when_not_called_out(self) -> None:
        PendingOpponentAttackFactory(
            encounter=self.encounter,
            opponent=self.opponent,
            declared_round=1,
            resolves_round=2,
            called_out=False,
        )
        self.assertTrue(evaluators.enemy_windup_underway(self._ctx(), NO_PARAMS))
        self.assertFalse(evaluators.enemy_windup_called_out(self._ctx(), NO_PARAMS))

    def test_called_out_true_when_called_out(self) -> None:
        PendingOpponentAttackFactory(
            encounter=self.encounter,
            opponent=self.opponent,
            declared_round=1,
            resolves_round=2,
            called_out=True,
        )
        self.assertTrue(evaluators.enemy_windup_called_out(self._ctx(), NO_PARAMS))

    def test_missing_resolution_returns_false_outside_combat(self) -> None:
        ctx = SituationContext(
            holder=self.subject_sheet, subject=self.subject_sheet, target=None, resolution=None
        )
        self.assertFalse(evaluators.enemy_windup_underway(ctx, NO_PARAMS))
        self.assertFalse(evaluators.enemy_windup_called_out(ctx, NO_PARAMS))

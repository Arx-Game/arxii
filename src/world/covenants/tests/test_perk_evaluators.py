"""Tests for the situation evaluator registry (#2536, Task 2).

Per evaluator: a fixture-built TRUE case, a FALSE case, and a missing-context
False case (spec convention: a missing required field always reads False).

Built in ``setUp`` rather than ``setUpTestData`` throughout — factories here
create Evennia ``ObjectDB`` instances (``DbHolder``, not deepcopyable), which
would break ``setUpTestData``'s deepcopy (same rationale as
``world/combat/tests/test_technique_can_reach.py`` and
``world/combat/tests/test_position_cover.py``).
"""

from __future__ import annotations

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from evennia import create_object

from world.areas.positioning.services import connect_positions, create_position, place_in_position
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    CombatRoundActionFactory,
    EngagementLockFactory,
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
from world.covenants.perks.constants import Situation
from world.covenants.perks.context import SituationContext
from world.covenants.perks.evaluators import SITUATION_EVALUATORS
from world.magic.constants import TechniqueFunction
from world.magic.factories import TechniqueFactory, TechniqueFunctionTagFactory
from world.npc_services.factories import NPCStandingFactory
from world.scenes.factories import SceneFactory
from world.vitals.models import CharacterVitals


class SituationEvaluatorRegistryTests(TestCase):
    """The registry carries exactly the 9 surviving Situation values."""

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
        self.assertTrue(evaluators.in_melee(ctx))
        self.assertFalse(evaluators.at_range(ctx))

    def test_at_range_true_when_engaged_enemy_elsewhere(self) -> None:
        self._engage_opponent_at(self.pos_b)
        ctx = self._ctx(self.resolution)
        self.assertFalse(evaluators.in_melee(ctx))
        self.assertTrue(evaluators.at_range(ctx))

    def test_missing_context_returns_false(self) -> None:
        ctx = self._ctx(None)
        self.assertFalse(evaluators.in_melee(ctx))
        self.assertFalse(evaluators.at_range(ctx))


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
        self.assertTrue(evaluators.surrounded(self._ctx(self.resolution)))

    def test_false_below_threshold(self) -> None:
        EngagementLockFactory(participant=self.participant, encounter=self.participant.encounter)
        self.assertFalse(evaluators.surrounded(self._ctx(self.resolution)))

    def test_missing_context_returns_false(self) -> None:
        self.assertFalse(evaluators.surrounded(self._ctx(None)))


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
        self.assertTrue(evaluators.target_distracted(self._ctx(self.target_sheet)))

    def test_false_when_no_matching_condition(self) -> None:
        self.assertFalse(evaluators.target_distracted(self._ctx(self.target_sheet)))

    def test_missing_context_returns_false(self) -> None:
        self.assertFalse(evaluators.target_distracted(self._ctx(None)))


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
        self.assertTrue(evaluators.target_swayed_by_ally(self._ctx(self.target_sheet)))

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
        self.assertTrue(evaluators.target_swayed_by_ally(self._ctx(self.target_sheet)))

    def test_false_when_applied_by_stranger(self) -> None:
        ConditionInstanceFactory(
            target=self.target_sheet.character,
            source_technique=self.technique,
            source_character=self.stranger_sheet.character,
        )
        self.assertFalse(evaluators.target_swayed_by_ally(self._ctx(self.target_sheet)))

    def test_missing_context_returns_false(self) -> None:
        self.assertFalse(evaluators.target_swayed_by_ally(self._ctx(None)))


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
        self.assertTrue(evaluators.target_focused_elsewhere(self._ctx(self.resolution)))

    def test_false_when_target_declared_action_targets_subject(self) -> None:
        CombatRoundActionFactory(
            participant=self.target_participant,
            round_number=1,
            focused_ally_target=self.subject_participant,
        )
        self.assertFalse(evaluators.target_focused_elsewhere(self._ctx(self.resolution)))

    def test_missing_context_returns_false(self) -> None:
        self.assertFalse(evaluators.target_focused_elsewhere(self._ctx(None)))


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
        self.assertTrue(evaluators.ally_low_health(self._ctx(self.resolution)))

    def test_false_when_mate_healthy(self) -> None:
        self._mate_membership(engaged=True)
        CharacterVitals.objects.create(character_sheet=self.mate_sheet, health=90, max_health=100)
        self.assertFalse(evaluators.ally_low_health(self._ctx(self.resolution)))

    def test_true_when_mate_unengaged(self) -> None:
        """Reversal (Tehom 2026-07-20): an unengaged low-health covenant-mate still
        counts — Last Bulwark fires hardest exactly when mates are down."""
        self._mate_membership(engaged=False)
        CharacterVitals.objects.create(character_sheet=self.mate_sheet, health=10, max_health=100)
        self.assertTrue(evaluators.ally_low_health(self._ctx(self.resolution)))

    def test_missing_context_returns_false(self) -> None:
        self._mate_membership(engaged=True)
        CharacterVitals.objects.create(character_sheet=self.mate_sheet, health=10, max_health=100)
        self.assertFalse(evaluators.ally_low_health(self._ctx(None)))


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
            evaluators.ally_low_health(self._ctx())
        return len(ctx)

    def test_query_count_fixed_regardless_of_mate_count(self) -> None:
        # Warm the holder's covenant-roles handler cache first, so both
        # measurements below start from the same (warm) state and compare
        # only the queries that genuinely run per evaluation.
        evaluators.ally_low_health(self._ctx())

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
        self.assertTrue(evaluators.during_negotiation(self._ctx(None)))

    def test_false_when_no_active_scene(self) -> None:
        self.assertFalse(evaluators.during_negotiation(self._ctx(None)))

    def test_false_when_resolving_in_combat(self) -> None:
        SceneFactory(location=self.room)
        participant = CombatParticipantFactory(character_sheet=self.subject_sheet)
        resolution = CombatRoundContext(participant)
        self.assertFalse(evaluators.during_negotiation(self._ctx(resolution)))

    def test_missing_context_returns_false(self) -> None:
        self.assertFalse(evaluators.during_negotiation(self._ctx(None, subject=False)))


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
        self.assertTrue(evaluators.target_favorably_disposed(self._ctx(self.target_sheet)))

    def test_false_when_no_standing_row(self) -> None:
        self.assertFalse(evaluators.target_favorably_disposed(self._ctx(self.target_sheet)))

    def test_missing_context_returns_false(self) -> None:
        self.assertFalse(evaluators.target_favorably_disposed(self._ctx(None)))

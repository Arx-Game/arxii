"""Reactive catch ends the plummet (#1228, Task 7).

A bystander with a qualifying catch capability resolves the "Catch the Faller"
challenge against a plummeting faller. The graded outcome maps onto the plummet:

- clean catch (SUCCESS / DESTROY resolution): the faller stops plummeting (no
  impact) and is placed safely at the catcher's non-CHASM position;
- partial: the descent is softened (accumulated ``severity`` decremented) but the
  plummet continues;
- failure: no-op, the plummet continues.

The catch is dispatched through ``dispatch_catch``, a thin wrapper that locates the
faller's catch challenge + the catcher's capability-matched approach via
``get_available_actions`` (so a catcher WITHOUT a catch capability is offered no
approach — eligibility is pure data-gating), resolves it via ``resolve_challenge``
(the immediate-challenge path used in DANGER rounds), then translates the graded
outcome through ``resolve_catch``.

Tagged ``postgres``: ``apply_condition`` (plummet + capability setup) hits a
PG-only ``DISTINCT ON`` that errors on the SQLite fast tier — pre-existing; run on
CI's PG shard.

Built in setUp (not setUpTestData): factories create Evennia ObjectDB instances
(DbHolder — not deepcopyable), which would break setUpTestData's deepcopy.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase, tag

from world.areas.positioning.constants import (
    PLUMMETING_CONDITION_NAME,
    TELEKINESIS_CAPABILITY_NAME,
    PositionKind,
)
from world.areas.positioning.models import Position
from world.areas.positioning.plummet import (
    begin_plummet,
    dispatch_catch,
    resolve_catch,
)
from world.areas.positioning.plummet_content import ensure_fall_content
from world.areas.positioning.services import force_move_to_position, position_of
from world.checks.types import CheckResult
from world.conditions.models import CapabilityType
from world.conditions.services import apply_condition, get_active_conditions
from world.mechanics.constants import ResolutionType
from world.mechanics.models import ChallengeInstance
from world.mechanics.services import get_available_actions
from world.traits.factories import CheckOutcomeFactory


@tag("postgres")  # apply_condition (plummet + capability setup) uses DISTINCT ON (PG-only)
class CatchActionTests(TestCase):
    def setUp(self) -> None:
        from evennia import create_object

        from world.character_sheets.factories import CharacterSheetFactory
        from world.conditions.factories import (
            ConditionCapabilityEffectFactory,
            ConditionTemplateFactory,
        )

        ensure_fall_content()

        self.room = create_object("typeclasses.rooms.Room", key="CatchRoom", nohome=True)

        # Faller's vertical stack: top (CHASM) -> ground (anchor None).
        self.ground = Position.objects.create(
            room=self.room, name="the ground", kind=PositionKind.PRIMARY
        )
        self.top_chasm = Position.objects.create(
            room=self.room, name="the top of the chasm", kind=PositionKind.CHASM
        )
        self.top_chasm.elevation_anchor = self.ground
        self.top_chasm.save(update_fields=["elevation_anchor"])

        # A safe ledge the catcher occupies (non-CHASM).
        self.ledge = Position.objects.create(
            room=self.room, name="the safe ledge", kind=PositionKind.ELEVATED
        )

        faller_sheet = CharacterSheetFactory()
        self.faller = faller_sheet.character
        self.faller.db_location = self.room
        self.faller.save(update_fields=["db_location"])

        catcher_sheet = CharacterSheetFactory()
        self.catcher = catcher_sheet.character
        self.catcher.db_location = self.room
        self.catcher.save(update_fields=["db_location"])
        force_move_to_position(self.catcher, self.ledge)

        # Grant the catcher the telekinesis catch capability via an active condition.
        self.telekinesis = CapabilityType.objects.get(name=TELEKINESIS_CAPABILITY_NAME)
        grant_template = ConditionTemplateFactory(name="Telekinetic")
        ConditionCapabilityEffectFactory(
            condition=grant_template, capability=self.telekinesis, value=10
        )
        apply_condition(self.catcher, grant_template)

        self._ConditionCapabilityEffectFactory = ConditionCapabilityEffectFactory
        self._ConditionTemplateFactory = ConditionTemplateFactory

    # --- helpers -----------------------------------------------------------

    def _start_plummet(self) -> None:
        force_move_to_position(self.faller, self.top_chasm)
        begin_plummet(self.faller, self.top_chasm)

    def _is_plummeting(self) -> bool:
        return (
            get_active_conditions(self.faller)
            .filter(condition__name=PLUMMETING_CONDITION_NAME)
            .exists()
        )

    def _plummeting_severity(self) -> int:
        from world.areas.positioning.plummet import _plummeting_instance

        instance = _plummeting_instance(self.faller)
        return instance.severity if instance is not None else -1

    def _result_for(self, success_level: int, resolution_type: str):
        """A ChallengeResolutionResult stub carrying a graded CheckResult."""
        from world.checks.models import Consequence
        from world.mechanics.types import ChallengeResolutionResult

        outcome = CheckOutcomeFactory(
            name=f"Outcome_{success_level}_{resolution_type}", success_level=success_level
        )
        check_result = CheckResult(
            check_type=None,
            outcome=outcome,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )
        return ChallengeResolutionResult(
            challenge_instance_id=0,
            challenge_name="Catch the Faller",
            approach_name="Telekinesis",
            check_result=check_result,
            consequence=Consequence(outcome_tier=outcome, label="x", weight=1),
            applied_effects=[],
            resolution_type=resolution_type,
            challenge_deactivated=resolution_type == ResolutionType.DESTROY,
            display_consequences=[],
        )

    # --- resolve_catch grading (unit) --------------------------------------

    def test_resolve_catch_success_ends_plummet_and_places_faller_safely(self) -> None:
        self._start_plummet()
        result = self._result_for(success_level=1, resolution_type=ResolutionType.DESTROY)

        resolve_catch(self.faller, self.catcher, result)

        self.assertFalse(self._is_plummeting(), "clean catch should end the plummet")
        self.assertNotEqual(
            position_of(self.faller).kind,
            PositionKind.CHASM,
            "caught faller must rest at a safe non-CHASM position",
        )
        self.assertEqual(position_of(self.faller), self.ledge)
        self.assertFalse(
            ChallengeInstance.objects.filter(target_object=self.faller, is_active=True).exists(),
            "clean catch should clear the bound catch challenge",
        )

    def test_resolve_catch_partial_softens_but_continues(self) -> None:
        self._start_plummet()
        # Pre-accumulate some depth so the decrement is observable.
        from world.areas.positioning.plummet import _plummeting_instance

        instance = _plummeting_instance(self.faller)
        instance.severity = 3
        instance.save(update_fields=["severity"])

        result = self._result_for(success_level=0, resolution_type=ResolutionType.PERSONAL)
        resolve_catch(self.faller, self.catcher, result)

        self.assertTrue(self._is_plummeting(), "partial catch should NOT end the plummet")
        self.assertEqual(self._plummeting_severity(), 2, "partial should soften the descent")

    def test_resolve_catch_partial_never_negative(self) -> None:
        self._start_plummet()  # severity starts at 0
        result = self._result_for(success_level=0, resolution_type=ResolutionType.PERSONAL)
        resolve_catch(self.faller, self.catcher, result)
        self.assertGreaterEqual(self._plummeting_severity(), 0)

    def test_resolve_catch_failure_is_noop(self) -> None:
        self._start_plummet()
        result = self._result_for(success_level=-1, resolution_type=ResolutionType.PERSONAL)
        resolve_catch(self.faller, self.catcher, result)
        self.assertTrue(self._is_plummeting(), "failed catch should let the plummet continue")
        self.assertEqual(position_of(self.faller), self.top_chasm)

    # --- dispatch_catch routes through resolve_challenge -------------------

    @patch("world.mechanics.challenge_resolution.perform_check")
    def test_dispatch_catch_success_ends_plummet(self, mock_check) -> None:
        success = CheckOutcomeFactory(name="DispatchSuccess", success_level=2)
        mock_check.return_value = CheckResult(
            check_type=None,
            outcome=success,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )
        self._start_plummet()

        dispatch_catch(self.catcher, self.faller, approach=TELEKINESIS_CAPABILITY_NAME)

        self.assertTrue(mock_check.called, "dispatch_catch must route through resolve_challenge")
        self.assertFalse(self._is_plummeting())
        self.assertNotEqual(position_of(self.faller).kind, PositionKind.CHASM)
        self.assertFalse(
            ChallengeInstance.objects.filter(target_object=self.faller, is_active=True).exists()
        )

    @patch("world.mechanics.challenge_resolution.perform_check")
    def test_dispatch_catch_failure_lets_plummet_continue(self, mock_check) -> None:
        failure = CheckOutcomeFactory(name="DispatchFailure", success_level=-2)
        mock_check.return_value = CheckResult(
            check_type=None,
            outcome=failure,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )
        self._start_plummet()

        dispatch_catch(self.catcher, self.faller, approach=TELEKINESIS_CAPABILITY_NAME)

        self.assertTrue(self._is_plummeting(), "failed catch leaves the faller plummeting")

    def test_catcher_without_capability_is_offered_no_catch_approach(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory

        self._start_plummet()

        bystander = CharacterSheetFactory().character
        bystander.db_location = self.room
        bystander.save(update_fields=["db_location"])
        force_move_to_position(bystander, self.ledge)

        # Data-gated: no catch capability → the catch approach is never surfaced.
        actions = get_available_actions(bystander, self.room)
        catch_actions = [a for a in actions if a.challenge_name == "Catch the Faller"]
        self.assertEqual(catch_actions, [], "a capability-less bystander gets no catch approach")

        # And the capable catcher IS offered it.
        catcher_actions = get_available_actions(self.catcher, self.room)
        catcher_catch = [a for a in catcher_actions if a.challenge_name == "Catch the Faller"]
        self.assertTrue(catcher_catch, "the telekinetic catcher is offered the catch approach")

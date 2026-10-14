"""Invoking favor on scene checks (#4333 slice 1).

Self-checks roll the invocation at once; a scene action declares it and rolls it
when the target accepts. ``world.checks.services.perform_check`` is replaced with
a recorder so the tests see both rolls in order (the invocation's difficulty, then
the check's extra modifiers) and pin each outcome; everything else is the real
service path, including the room lines written as OUTCOME interactions.
"""

from __future__ import annotations

from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from actions.definitions.scene_checks import SceneSelfCheckAction
from actions.factories import ActionTemplateFactory
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.types import CheckResult
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.action_constants import ActionRequestStatus, ConsentDecision, DifficultyChoice
from world.scenes.action_services import create_action_request, respond_to_action_request
from world.scenes.constants import InteractionMode
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.scenes.favor_invocation import declared_invocation_contribution
from world.scenes.models import Interaction
from world.scenes.services import active_persona_for_sheet
from world.traits.factories import CheckOutcomeFactory
from world.worship.constants import FavorAwardKind
from world.worship.factories import (
    DevotionConfigFactory,
    DevotionStandingFactory,
    FavorOutcomeAwardFactory,
    WorshipDeclarationFactory,
    WorshippedBeingFactory,
)
from world.worship.favor_services import ensure_being_modifier_targets
from world.worship.models import FavorInvocation, PatronageValence
from world.worship.types import InvocationChoice

_PERFORM_CHECK = "world.checks.services.perform_check"


class _RollRecorder:
    """Stands in for ``perform_check``: records each roll, returns pinned outcomes."""

    def __init__(self, outcomes) -> None:
        self.outcomes = list(outcomes)
        self.rolls: list[tuple[str, int, int]] = []

    def __call__(self, _character, check_type, target_difficulty=0, extra_modifiers=0, **_kw):
        self.rolls.append((check_type.name, target_difficulty, extra_modifiers))
        return CheckResult(
            check_type=check_type,
            outcome=self.outcomes.pop(0),
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=extra_modifiers,
        )


def _pc_in_room(room, *, db_key: str):
    character = CharacterFactory(db_key=db_key, location=room)
    CharacterSheetFactory(character=character)
    entry = RosterEntryFactory(character_sheet__character=character)
    tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
    return character, tenure.player_data.account


class SceneInvocationBase(TestCase):
    def setUp(self) -> None:
        self.success = CheckOutcomeFactory(name="Success", success_level=1)
        self.partial = CheckOutcomeFactory(name="Partial Success", success_level=0)
        self.failure = CheckOutcomeFactory(name="Failure", success_level=-1)
        self.invocation_type = CheckTypeFactory(name="Invocation")
        config = DevotionConfigFactory(invocation_check_type=self.invocation_type)
        for outcome, amount in ((self.success, 10), (self.partial, 5), (self.failure, 0)):
            FavorOutcomeAwardFactory(
                config=config, kind=FavorAwardKind.INVOCATION, outcome_tier=outcome, amount=amount
            )
        self.being = WorshippedBeingFactory(name="Fenwright Dead")
        ensure_being_modifier_targets(self.being)

        self.room = ObjectDBFactory(db_key="Hall", db_typeclass_path="typeclasses.rooms.Room")
        self.scene = SceneFactory(location=self.room, is_active=True)
        self.actor, account = _pc_in_room(self.room, db_key="Tobiah")
        SceneParticipationFactory(scene=self.scene, account=account)
        self.onlooker, onlooker_account = _pc_in_room(self.room, db_key="Hobb")
        SceneParticipationFactory(scene=self.scene, account=onlooker_account)
        self.sheet = self.actor.sheet_data
        self.persona = active_persona_for_sheet(self.sheet)

    def _outcome_lines(self) -> list[str]:
        return list(
            Interaction.objects.filter(mode=InteractionMode.OUTCOME)
            .order_by("pk")
            .values_list("content", flat=True)
        )

    def _make_secret_faith(self) -> None:
        WorshipDeclarationFactory(
            character_sheet=self.sheet,
            public_being=WorshippedBeingFactory(name="A Public God"),
            secret_being=self.being,
        )


class SelfCheckInvocationTests(SceneInvocationBase):
    def setUp(self) -> None:
        super().setUp()
        DevotionStandingFactory(character_sheet=self.sheet, being=self.being, favor=12)
        self.perception = CheckTypeFactory(name="Perception")

    def _self_check(self, recorder, **kwargs):
        with patch(_PERFORM_CHECK, side_effect=recorder):
            return SceneSelfCheckAction().run(
                actor=self.actor,
                check_type_ref=self.perception.name,
                difficulty=DifficultyChoice.HARD,
                **kwargs,
            )

    def test_self_check_invocation_journey(self) -> None:
        # Tobiah: favor 12, not Chosen: Daunting (75). Partial Success: +5.
        recorder = _RollRecorder([self.partial, self.success])
        result = self._self_check(
            recorder, invoke_being_id=self.being.pk, invoke_line="[player line]"
        )

        self.assertTrue(result.success, result.message)
        self.assertEqual(recorder.rolls, [("Invocation", 75, 0), ("Perception", 60, 5)])
        name = self.persona.name
        lines = self._outcome_lines()
        self.assertEqual(lines[0], f"{name} calls on Fenwright Dead: [player line]")
        self.assertEqual(lines[1], f"{name}'s invocation: Partial Success.")
        self.assertIn("Perception", lines[2])
        # The bonus is in the roller's own result only, never in a room line.
        self.assertIn("Fenwright Dead's favor (invocation: Partial Success): +5", result.message)
        self.assertFalse(any("+5" in line for line in lines))
        row = FavorInvocation.objects.get(character_sheet=self.sheet)
        self.assertEqual((row.scene, row.bonus), (self.scene, 5))

    def test_secret_faith_room_line_omits_player_line(self) -> None:
        self._make_secret_faith()
        recorder = _RollRecorder([self.failure, self.success])
        result = self._self_check(
            recorder, invoke_being_id=self.being.pk, invoke_line="[player line]"
        )

        name = self.persona.name
        lines = self._outcome_lines()
        self.assertEqual(
            lines[:2], [f"{name} calls on something.", f"{name}'s invocation: Failure."]
        )
        self.assertFalse(any("[player line]" in line or "Fenwright" in line for line in lines))
        # Failure adds nothing, and the roller still sees their own line.
        self.assertEqual(recorder.rolls[1][2], 0)
        self.assertIn(f"{name} calls on Fenwright Dead: [player line]", result.message)

    def test_refusal_rolls_nothing(self) -> None:
        stranger = WorshippedBeingFactory(name="River Spirit")
        recorder = _RollRecorder([])
        result = self._self_check(recorder, invoke_being_id=stranger.pk)
        self.assertFalse(result.success)
        self.assertEqual(result.message, "You have no favor with River Spirit to call on.")
        self.assertEqual(recorder.rolls, [])
        self.assertEqual(self._outcome_lines(), [])


class SceneActionInvocationTests(SceneInvocationBase):
    def setUp(self) -> None:
        super().setUp()
        DevotionStandingFactory(
            character_sheet=self.sheet,
            being=self.being,
            favor=44,
            valence=PatronageValence.DEVOTIONAL,
            established_at=timezone.now(),
        )
        self.persuasion = CheckTypeFactory(name="Persuasion")
        ActionTemplateFactory(name="Persuade", check_type=self.persuasion)
        self.target_sheet = self.onlooker.sheet_data
        self.target_persona = active_persona_for_sheet(self.target_sheet)

    def _declare(self, **kwargs):
        return create_action_request(
            scene=self.scene,
            initiator_persona=self.persona,
            target_persona=self.target_persona,
            action_key="persuade",
            invoke=InvocationChoice(being_id=self.being.pk, player_line="[player line]"),
            **kwargs,
        )

    def test_scene_action_invocation_rolls_at_accept(self) -> None:
        request = self._declare()
        self.assertEqual((request.invoke_being, request.invoke_line), (self.being, "[player line]"))
        # Declaring rolls nothing and uses no invocation.
        self.assertFalse(FavorInvocation.objects.exists())

        contributions = []
        from world.checks.services import collect_check_modifiers as real_collect

        def _collect(*args, **kwargs):
            contributions.extend(kwargs.get("extra_contributions") or [])
            return real_collect(*args, **kwargs)

        recorder = _RollRecorder([self.success, self.success])
        with (
            patch(_PERFORM_CHECK, side_effect=recorder),
            patch("world.checks.services.collect_check_modifiers", side_effect=_collect),
        ):
            respond_to_action_request(action_request=request, decision=ConsentDecision.ACCEPT)

        request.refresh_from_db()
        self.assertEqual(request.status, ActionRequestStatus.RESOLVED)
        # Chosen, favor 44: 75 - 30 - 15 = 30, Easy; Success gives +10 on the action.
        self.assertEqual(recorder.rolls[0], ("Invocation", 30, 0))
        favor = [c for c in contributions if c.source_kind == "favor"]
        self.assertEqual(len(favor), 1)
        self.assertEqual(
            (favor[0].source_label, favor[0].value),
            ("Fenwright Dead's favor (invocation: Success)", 10),
        )
        name = self.persona.name
        lines = self._outcome_lines()
        self.assertEqual(
            lines[:2],
            [f"{name} calls on Fenwright Dead: [player line]", f"{name}'s invocation: Success."],
        )
        self.assertEqual(FavorInvocation.objects.get().scene_action_request, request)

    def test_declared_invocation_rolls_once_per_request(self) -> None:
        request = self._declare()
        recorder = _RollRecorder([self.success])
        with patch(_PERFORM_CHECK, side_effect=recorder):
            first = declared_invocation_contribution(request)
            second = declared_invocation_contribution(request)
        self.assertEqual(first, second)
        self.assertEqual(len(recorder.rolls), 1)
        self.assertEqual(FavorInvocation.objects.count(), 1)

    def test_denied_action_uses_no_invocation(self) -> None:
        request = self._declare()
        respond_to_action_request(action_request=request, decision=ConsentDecision.DENY)
        self.assertFalse(FavorInvocation.objects.exists())

    def test_refused_at_declaration(self) -> None:
        stranger = WorshippedBeingFactory(name="River Spirit")
        with self.assertRaises(ValidationError) as refused:
            create_action_request(
                scene=self.scene,
                initiator_persona=self.persona,
                target_persona=self.target_persona,
                action_key="persuade",
                invoke=InvocationChoice(being_id=stranger.pk),
            )
        self.assertEqual(
            refused.exception.messages, ["You have no favor with River Spirit to call on."]
        )

    def test_onlooker_payloads(self) -> None:
        """Onlookers get the call line, the outcome line and the action's own line:
        never the bonus, the difficulty or the favor."""
        self._make_secret_faith()
        request = self._declare()
        recorder = _RollRecorder([self.failure, self.success])
        with patch(_PERFORM_CHECK, side_effect=recorder):
            respond_to_action_request(action_request=request, decision=ConsentDecision.ACCEPT)

        name = self.persona.name
        lines = self._outcome_lines()
        self.assertEqual(
            lines[:2], [f"{name} calls on something.", f"{name}'s invocation: Failure."]
        )
        everything = " ".join(
            Interaction.objects.filter(scene=self.scene).values_list("content", flat=True)
        )
        for leak in ("[player line]", "Fenwright", "favor", "Easy", "30", "+"):
            self.assertNotIn(leak, everything, leak)

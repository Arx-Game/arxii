"""Tests for opt-in start/join/leave/end round registry actions (#520)."""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.constants import RoundStatus, SceneRoundParticipantStatus
from world.scenes.models import (
    SceneActionDeclaration,
    SceneRound,
    SceneRoundParticipant,
)


def _make_actor(name: str) -> tuple:
    """Return (room, actor, sheet) with located Character and CharacterSheet."""
    room = ObjectDBFactory(
        db_key=f"{name}Room",
        db_typeclass_path="typeclasses.rooms.Room",
    )
    actor = CharacterFactory(db_key=name, location=room)
    sheet = CharacterSheetFactory(character=actor)
    return room, actor, sheet


class StartRoundActionTests(TestCase):
    """start_round creates a DECLARING SceneRound and enrolls the actor."""

    def setUp(self) -> None:
        self.room, self.actor, self.sheet = _make_actor("RoundStarter")

    def test_start_round_creates_declaring_round_with_actor_enrolled(self) -> None:
        from actions.registry import get_action

        result = get_action("start_round").run(self.actor)

        self.assertTrue(result.success)
        rnd = SceneRound.objects.get(room=self.room)
        self.assertEqual(rnd.status, RoundStatus.DECLARING)
        self.assertTrue(
            SceneRoundParticipant.objects.filter(
                scene_round=rnd,
                character_sheet=self.sheet,
            ).exists()
        )

    def test_start_round_reuses_existing_between_rounds(self) -> None:
        """If a BETWEEN_ROUNDS round already exists, start_round advances it to DECLARING."""
        from actions.registry import get_action
        from world.scenes.constants import SceneRoundStartReason

        existing = SceneRound.objects.create(
            room=self.room,
            status=RoundStatus.BETWEEN_ROUNDS,
            round_number=1,
            start_reason=SceneRoundStartReason.OPT_IN,
        )

        result = get_action("start_round").run(self.actor)

        self.assertTrue(result.success)
        existing.refresh_from_db()
        self.assertEqual(existing.status, RoundStatus.DECLARING)
        self.assertEqual(SceneRound.objects.filter(room=self.room).count(), 1)

    def test_start_round_no_location_returns_failure(self) -> None:
        """Actor with no location gets a graceful failure."""
        from actions.registry import get_action

        self.actor.location = None
        result = get_action("start_round").run(self.actor)

        self.assertFalse(result.success)


class JoinRoundActionTests(TestCase):
    """join_round enrolls the actor in an existing active round."""

    def setUp(self) -> None:
        self.room, self.actor, self.sheet = _make_actor("RoundJoiner")
        from world.scenes.constants import SceneRoundStartReason

        self.round = SceneRound.objects.create(
            room=self.room,
            status=RoundStatus.DECLARING,
            round_number=1,
            start_reason=SceneRoundStartReason.OPT_IN,
        )

    def test_join_round_enrolls_actor(self) -> None:
        from actions.registry import get_action

        result = get_action("join_round").run(self.actor)

        self.assertTrue(result.success)
        self.assertTrue(
            SceneRoundParticipant.objects.filter(
                scene_round=self.round,
                character_sheet=self.sheet,
            ).exists()
        )

    def test_join_round_no_active_round_returns_failure(self) -> None:
        """No active round in the room → graceful failure."""
        from actions.registry import get_action

        self.round.status = RoundStatus.COMPLETED
        self.round.save()

        result = get_action("join_round").run(self.actor)

        self.assertFalse(result.success)


class LeaveRoundActionTests(TestCase):
    """leave_round marks the actor's participant row as LEFT."""

    def setUp(self) -> None:
        self.room, self.actor, self.sheet = _make_actor("RoundLeaver")
        from world.scenes.constants import SceneRoundStartReason

        self.round = SceneRound.objects.create(
            room=self.room,
            status=RoundStatus.DECLARING,
            round_number=1,
            start_reason=SceneRoundStartReason.OPT_IN,
        )
        self.participant = SceneRoundParticipant.objects.create(
            scene_round=self.round,
            character_sheet=self.sheet,
        )

    def test_leave_round_sets_participant_left(self) -> None:
        from actions.registry import get_action

        result = get_action("leave_round").run(self.actor)

        self.assertTrue(result.success)
        # flush_from_cache + refresh: queryset update() bypasses idmapper
        self.participant.flush_from_cache()
        fresh = SceneRoundParticipant.objects.get(pk=self.participant.pk)
        self.assertEqual(fresh.status, SceneRoundParticipantStatus.LEFT)

    def test_leave_round_no_participation_returns_success(self) -> None:
        """No participant row is a no-op (graceful)."""
        from actions.registry import get_action

        self.participant.delete()
        result = get_action("leave_round").run(self.actor)

        self.assertTrue(result.success)


class EndRoundActionTests(TestCase):
    """end_round marks the active round COMPLETED."""

    def setUp(self) -> None:
        self.room, self.actor, self.sheet = _make_actor("RoundEnder")
        from world.scenes.constants import SceneRoundStartReason

        self.round = SceneRound.objects.create(
            room=self.room,
            status=RoundStatus.DECLARING,
            round_number=1,
            start_reason=SceneRoundStartReason.OPT_IN,
        )

    def test_end_round_completes_the_round(self) -> None:
        from actions.registry import get_action

        result = get_action("end_round").run(self.actor)

        self.assertTrue(result.success)
        self.round.refresh_from_db()
        self.assertEqual(self.round.status, RoundStatus.COMPLETED)

    def test_end_round_no_active_round_returns_failure(self) -> None:
        """No active round in the room → graceful failure."""
        from actions.registry import get_action

        self.round.status = RoundStatus.COMPLETED
        self.round.save()

        result = get_action("end_round").run(self.actor)

        self.assertFalse(result.success)


class PassRoundActionTests(TestCase):
    """pass_round records an is_pass declaration for the actor's participant."""

    def setUp(self) -> None:
        self.room, self.actor, self.sheet = _make_actor("RoundPasser")
        from world.scenes.constants import SceneRoundStartReason

        self.round = SceneRound.objects.create(
            room=self.room,
            status=RoundStatus.DECLARING,
            round_number=1,
            start_reason=SceneRoundStartReason.OPT_IN,
        )
        self.participant = SceneRoundParticipant.objects.create(
            scene_round=self.round,
            character_sheet=self.sheet,
            status=SceneRoundParticipantStatus.ACTIVE,
        )

    def test_pass_round_writes_pass_declaration(self) -> None:
        from actions.definitions.rounds import PassRoundAction

        result = PassRoundAction().execute(actor=self.actor)

        self.assertTrue(result.success)
        decl = SceneActionDeclaration.objects.get(
            scene_round=self.round,
            round_number=1,
            participant=self.participant,
        )
        self.assertTrue(decl.is_pass)
        self.assertIsNone(decl.challenge_instance)
        self.assertIsNone(decl.challenge_approach)

    def test_pass_round_no_active_round_returns_failure(self) -> None:
        from actions.definitions.rounds import PassRoundAction

        self.round.status = RoundStatus.COMPLETED
        self.round.save()

        result = PassRoundAction().execute(actor=self.actor)

        self.assertFalse(result.success)

    def test_pass_round_action_registered_and_costs_turn(self) -> None:
        from actions.registry import get_action

        action = get_action("pass_round")
        self.assertIsNotNone(action)
        self.assertTrue(action.costs_turn)

    def test_pass_round_danger_round_returns_failure_no_row(self) -> None:
        """A danger round is the acute tier; passing is a social-round concept only."""
        from actions.definitions.rounds import PassRoundAction
        from world.scenes.constants import SceneRoundStartReason

        self.round.start_reason = SceneRoundStartReason.DANGER
        self.round.save(update_fields=["start_reason"])

        result = PassRoundAction().execute(actor=self.actor)

        self.assertFalse(result.success)
        self.assertFalse(SceneActionDeclaration.objects.filter(scene_round=self.round).exists())


class ForceResolveRoundActionTests(TestCase):
    """force_resolve_round resolves a DECLARING round even when partially declared."""

    def setUp(self) -> None:
        self.room, self.actor, self.sheet = _make_actor("RoundForcer")
        from world.scenes.constants import SceneRoundStartReason

        self.other_sheet = CharacterSheetFactory(
            character=CharacterFactory(db_key="RoundForcerOther", location=self.room)
        )
        self.round = SceneRound.objects.create(
            room=self.room,
            status=RoundStatus.DECLARING,
            round_number=1,
            start_reason=SceneRoundStartReason.OPT_IN,
        )
        self.participant = SceneRoundParticipant.objects.create(
            scene_round=self.round,
            character_sheet=self.sheet,
            status=SceneRoundParticipantStatus.ACTIVE,
        )
        self.other_participant = SceneRoundParticipant.objects.create(
            scene_round=self.round,
            character_sheet=self.other_sheet,
            status=SceneRoundParticipantStatus.ACTIVE,
        )
        # Only one of the two participants has declared (a pass).
        SceneActionDeclaration.objects.create(
            scene_round=self.round,
            round_number=1,
            participant=self.participant,
            is_pass=True,
        )

    def test_force_resolve_advances_partially_declared_round(self) -> None:
        from actions.definitions.rounds import ForceResolveRoundAction

        result = ForceResolveRoundAction().execute(actor=self.actor)

        self.assertTrue(result.success)
        self.round.refresh_from_db()
        self.assertEqual(self.round.round_number, 2)
        self.assertEqual(self.round.status, RoundStatus.DECLARING)
        self.assertEqual(
            SceneActionDeclaration.objects.filter(scene_round=self.round, round_number=1).count(),
            0,
        )

    def test_force_resolve_not_declaring_returns_failure(self) -> None:
        from actions.definitions.rounds import ForceResolveRoundAction

        self.round.status = RoundStatus.BETWEEN_ROUNDS
        self.round.save()

        result = ForceResolveRoundAction().execute(actor=self.actor)

        self.assertFalse(result.success)

    def test_force_resolve_action_registered(self) -> None:
        from actions.registry import get_action

        self.assertIsNotNone(get_action("force_resolve_round"))

    def test_force_resolve_danger_round_returns_failure_unchanged(self) -> None:
        """force_resolve must not resolve a DANGER round (it bypasses the acute auto-end)."""
        from actions.definitions.rounds import ForceResolveRoundAction
        from world.scenes.constants import SceneRoundStartReason

        self.round.start_reason = SceneRoundStartReason.DANGER
        self.round.save(update_fields=["start_reason"])

        result = ForceResolveRoundAction().execute(actor=self.actor)

        self.assertFalse(result.success)
        self.round.refresh_from_db()
        self.assertEqual(self.round.round_number, 1)
        self.assertEqual(self.round.status, RoundStatus.DECLARING)

"""Round-shape regressions the journeys cannot stage (#520, #1466).

Every player path of the round verbs (start, join, leave, end, pass, force-resolve,
interpose, succor, the mode and its knobs) is typed or dispatched in
``integration_tests/test_playing_a_scene_journeys.py`` (``PacingTheRoom``). What stays
here are row shapes no player path produces on demand: a pass on top of leftover
immediate declarations (the ``MultipleObjectsReturned`` regression) and a DANGER round,
which only an acute peril opens.
"""

from __future__ import annotations

from django.test import TestCase

from actions.definitions.rounds import ForceResolveRoundAction, PassRoundAction
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.constants import (
    RoundStatus,
    SceneRoundMode,
    SceneRoundParticipantStatus,
    SceneRoundStartReason,
)
from world.scenes.models import SceneActionDeclaration, SceneRound, SceneRoundParticipant


class RoundRegressionTests(TestCase):
    def setUp(self) -> None:
        self.room = ObjectDBFactory(
            db_key="RoundRegressionRoom", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.actor = CharacterFactory(db_key="RoundPasser", location=self.room)
        self.sheet = CharacterSheetFactory(character=self.actor)
        self.round = SceneRound.objects.create(
            room=RoomProfileFactory(objectdb=self.room),
            status=RoundStatus.DECLARING,
            round_number=1,
            start_reason=SceneRoundStartReason.OPT_IN,
        )
        self.participant = SceneRoundParticipant.objects.create(
            scene_round=self.round,
            character_sheet=self.sheet,
            status=SceneRoundParticipantStatus.ACTIVE,
        )

    def _make_danger_round(self) -> None:
        self.round.start_reason = SceneRoundStartReason.DANGER
        self.round.mode = SceneRoundMode.STRICT
        self.round.save(update_fields=["start_reason", "mode"])

    def test_pass_round_with_existing_immediate_declarations_does_not_raise(self) -> None:
        """With the one-declaration-per-round constraint gone, a participant may hold
        several immediate rows for one round; the pass upsert must look only at the
        deferred row, or it raises ``MultipleObjectsReturned``."""
        for _ in range(2):
            SceneActionDeclaration.objects.create(
                scene_round=self.round,
                round_number=1,
                participant=self.participant,
                is_immediate=True,
                is_pass=False,
            )

        result = PassRoundAction().execute(actor=self.actor)

        self.assertTrue(result.success)
        deferred = SceneActionDeclaration.objects.filter(
            scene_round=self.round,
            round_number=1,
            participant=self.participant,
            is_immediate=False,
        )
        self.assertEqual(deferred.count(), 1)
        self.assertTrue(deferred.get().is_pass)

    def test_pass_round_danger_round_records_pass(self) -> None:
        """#1466: a danger round is an ordinary STRICT round. A present bystander passing
        is exactly how the presence-gated resolution (which ticks the peril) is driven,
        so passing records a deferred pass row, not a failure."""
        self._make_danger_round()

        result = PassRoundAction().execute(actor=self.actor)

        self.assertTrue(result.success)
        row = SceneActionDeclaration.objects.get(
            scene_round=self.round, participant=self.participant, is_immediate=False
        )
        self.assertTrue(row.is_pass)

    def test_force_resolve_danger_round_resolves_and_auto_ends(self) -> None:
        """#1466: force_resolve resolves a danger round like any other; with no peril
        remaining on any ACTIVE participant, ``resolve_scene_round`` completes it."""
        self._make_danger_round()
        SceneActionDeclaration.objects.create(
            scene_round=self.round, round_number=1, participant=self.participant, is_pass=True
        )

        result = ForceResolveRoundAction().execute(actor=self.actor)

        self.assertTrue(result.success)
        self.round.refresh_from_db()
        self.assertEqual(self.round.status, RoundStatus.COMPLETED)

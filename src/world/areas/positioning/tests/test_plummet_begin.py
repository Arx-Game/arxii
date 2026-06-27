"""End-to-end FELL → plummet integration (#1228, Task 5).

Proves the seam: placing a character into a CHASM position emits ``EventName.FELL``
(``maybe_emit_fall``), which the room-owned ``fall_to_plummet`` trigger dispatches
to ``begin_plummet_handler`` -> ``begin_plummet``. The plummet then starts an
AFK-safe DANGER scene round (faller enrolled), applies the seeded Plummeting
condition, and instantiates the catch challenge bound to the faller.

Tagged ``postgres``: ``apply_condition`` (called by ``begin_plummet`` for the
progressive Plummeting condition) hits a PG-only ``DISTINCT ON`` that errors on
the SQLite fast tier — a known pre-existing limitation, run on CI's PG shard.

Built in setUp (not setUpTestData): factories create Evennia ObjectDB instances
(DbHolder — not deepcopyable), which would break setUpTestData's deepcopy.
"""

from __future__ import annotations

from django.test import TestCase, tag

from world.areas.positioning.constants import (
    CATCH_THE_FALLER_NAME,
    PLUMMETING_CONDITION_NAME,
    PositionKind,
)
from world.areas.positioning.factories import wire_fall_triggers
from world.areas.positioning.models import Position
from world.areas.positioning.plummet import install_fall_triggers
from world.areas.positioning.plummet_content import ensure_fall_content
from world.areas.positioning.services import force_move_to_position, maybe_emit_fall
from world.conditions.services import get_active_conditions
from world.mechanics.models import ChallengeInstance
from world.scenes.constants import SceneRoundStartReason
from world.scenes.models import SceneRound


@tag("postgres")  # begin_plummet -> apply_condition uses DISTINCT ON (PG-only)
class FellBeginsPlummetTests(TestCase):
    def setUp(self) -> None:
        from evennia import create_object

        from world.character_sheets.factories import CharacterSheetFactory

        ensure_fall_content()
        wire_fall_triggers()

        self.room = create_object("typeclasses.rooms.Room", key="PlummetRoom", nohome=True)
        sheet = CharacterSheetFactory()
        self.faller = sheet.character
        self.faller.db_location = self.room
        self.faller.save(update_fields=["db_location"])

        # A present bystander (a potential catcher): with someone able to attempt a
        # catch, begin_plummet rides an AFK-safe danger round (multi-round descent +
        # catch window) instead of resolving the fall immediately. The unattended
        # (no-catcher) fall is covered by test_plummet_immediate.py.
        bystander_sheet = CharacterSheetFactory()
        self.bystander = bystander_sheet.character
        self.bystander.db_location = self.room
        self.bystander.save(update_fields=["db_location"])

        install_fall_triggers(self.room)

        self.chasm = Position.objects.create(
            room=self.room, name="the pit", kind=PositionKind.CHASM
        )
        force_move_to_position(self.faller, self.chasm)

    def _danger_round(self) -> SceneRound | None:
        return SceneRound.objects.filter(
            room=self.room, start_reason=SceneRoundStartReason.DANGER
        ).first()

    def test_fell_emission_begins_plummet(self) -> None:
        emitted = maybe_emit_fall(self.faller, self.chasm)
        self.assertTrue(emitted)

        rnd = self._danger_round()
        self.assertIsNotNone(rnd)
        self.assertTrue(
            rnd.participants.filter(character_sheet__character=self.faller).exists(),
            "faller should be enrolled as a DANGER round participant",
        )

        self.assertTrue(
            get_active_conditions(self.faller, include_suppressed=False)
            .filter(condition__name=PLUMMETING_CONDITION_NAME)
            .exists(),
            "faller should carry the Plummeting condition",
        )

        self.assertTrue(
            ChallengeInstance.objects.filter(
                template__name=CATCH_THE_FALLER_NAME,
                target_object=self.faller,
                is_active=True,
            ).exists(),
            "a Catch the Faller challenge should be bound to the faller",
        )

    def test_second_fall_is_idempotent(self) -> None:
        maybe_emit_fall(self.faller, self.chasm)
        maybe_emit_fall(self.faller, self.chasm)

        self.assertEqual(
            SceneRound.objects.filter(
                room=self.room, start_reason=SceneRoundStartReason.DANGER
            ).count(),
            1,
            "re-entry must not create a second DANGER round",
        )
        self.assertEqual(
            get_active_conditions(self.faller)
            .filter(condition__name=PLUMMETING_CONDITION_NAME)
            .count(),
            1,
            "re-entry must not stack the Plummeting condition",
        )
        self.assertEqual(
            ChallengeInstance.objects.filter(
                template__name=CATCH_THE_FALLER_NAME,
                target_object=self.faller,
                is_active=True,
            ).count(),
            1,
            "re-entry must not create a second catch challenge",
        )

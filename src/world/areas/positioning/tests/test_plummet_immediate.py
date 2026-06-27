"""Unattended plummet resolves immediately — never frozen mid-air (#1479).

Falling is environmental and self-completing: gravity does not pause for an idle
round. When NO one is present who could catch the faller, ``begin_plummet``
resolves the descent all the way to the floor + impact in a single call rather
than starting a danger round that nothing would ever drive (ADR-0004:
action-driven tempo — there is no wall clock to advance the fall).

The companion ``test_plummet_descent.py`` covers the attended case (a bystander
present → the fall rides the round, descending one level per resolution, with the
catch window open).

Tagged ``postgres``: ``apply_condition`` (plummet setup) hits a PG-only
``DISTINCT ON`` that errors on the SQLite fast tier — run on CI's PG shard.

Built in setUp (not setUpTestData): factories create Evennia ObjectDB instances
(DbHolder — not deepcopyable), which would break setUpTestData's deepcopy.
"""

from __future__ import annotations

from django.test import TestCase, tag

from world.areas.positioning.constants import (
    PLUMMETING_CONDITION_NAME,
    PositionKind,
)
from world.areas.positioning.models import Position
from world.areas.positioning.plummet import begin_plummet, resolve_unattended_plummets
from world.areas.positioning.plummet_content import ensure_fall_content
from world.areas.positioning.services import force_move_to_position, position_of
from world.conditions.services import get_active_conditions
from world.mechanics.models import ChallengeInstance
from world.scenes.constants import SceneRoundStartReason
from world.scenes.models import SceneRound


@tag("postgres")  # apply_condition (plummet setup) uses DISTINCT ON (PG-only)
class UnattendedPlummetTests(TestCase):
    def setUp(self) -> None:
        from evennia import create_object

        from world.character_sheets.factories import CharacterSheetFactory
        from world.vitals.factories import CharacterVitalsFactory

        ensure_fall_content()

        self.room = create_object("typeclasses.rooms.Room", key="LonelyChasm", nohome=True)
        sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=sheet)
        self.faller = sheet.character
        self.faller.db_location = self.room
        self.faller.save(update_fields=["db_location"])

        # A deep vertical stack: top -> mid -> ground (anchor None). Deeper than one
        # level so "frozen mid-air" would be observable if the fall did not resolve.
        self.ground = Position.objects.create(
            room=self.room, name="the ground", kind=PositionKind.PRIMARY
        )
        self.mid_chasm = Position.objects.create(
            room=self.room, name="the mid ledge", kind=PositionKind.CHASM
        )
        self.mid_chasm.elevation_anchor = self.ground
        self.mid_chasm.save(update_fields=["elevation_anchor"])
        self.top_chasm = Position.objects.create(
            room=self.room, name="the top of the chasm", kind=PositionKind.CHASM
        )
        self.top_chasm.elevation_anchor = self.mid_chasm
        self.top_chasm.save(update_fields=["elevation_anchor"])

    def _vitals(self):
        return self.faller.sheet_data.vitals

    def test_alone_faller_impacts_at_floor_immediately(self) -> None:
        # No one else present → the fall is unattended → begin_plummet resolves it
        # all the way to the floor + impact in one call. NOT frozen mid-descent.
        force_move_to_position(self.faller, self.top_chasm)
        health_before = self._vitals().health

        begin_plummet(self.faller, self.top_chasm)

        self.assertEqual(
            position_of(self.faller),
            self.ground,
            "an unattended fall must reach the floor immediately, not freeze mid-air",
        )
        self.assertLess(
            self._vitals().health,
            health_before,
            "impact must apply fall-damage consequences",
        )
        self.assertFalse(
            get_active_conditions(self.faller)
            .filter(condition__name=PLUMMETING_CONDITION_NAME)
            .exists(),
            "impact removes the Plummeting condition",
        )

    def test_alone_faller_starts_no_lingering_plummet_round(self) -> None:
        # The fall resolves synchronously, so there is no danger round left ticking a
        # frozen faller. (A bleed-out caused BY the impact would start its own danger
        # round under the normal bleed-out rules — that is a separate, correct flow.)
        force_move_to_position(self.faller, self.top_chasm)
        begin_plummet(self.faller, self.top_chasm)

        plummet_round = SceneRound.objects.filter(
            room=self.room, start_reason=SceneRoundStartReason.DANGER
        ).first()
        if plummet_round is not None:
            self.assertFalse(
                get_active_conditions(self.faller)
                .filter(condition__name=PLUMMETING_CONDITION_NAME)
                .exists(),
                "any danger round present must not be holding a still-plummeting faller",
            )
        self.assertFalse(
            ChallengeInstance.objects.filter(target_object=self.faller, is_active=True).exists(),
            "no active catch challenge should linger after an unattended fall",
        )

    def test_departure_of_last_catcher_resolves_the_fall(self) -> None:
        # With a catcher present, begin_plummet rides the round (faller stays mid-air).
        # When that catcher leaves — removing the last person who could catch — the
        # fall completes to impact immediately rather than freezing.
        from world.character_sheets.factories import CharacterSheetFactory

        catcher = CharacterSheetFactory().character
        catcher.db_location = self.room
        catcher.save(update_fields=["db_location"])

        force_move_to_position(self.faller, self.top_chasm)
        begin_plummet(self.faller, self.top_chasm)

        # Attended → still mid-air, still plummeting.
        self.assertNotEqual(position_of(self.faller), self.ground)
        self.assertTrue(
            get_active_conditions(self.faller)
            .filter(condition__name=PLUMMETING_CONDITION_NAME)
            .exists()
        )

        # The catcher departs; at_object_leave fires while the mover is still in
        # contents, so resolve_unattended_plummets excludes them as a remaining catcher.
        catcher.db_location = None
        catcher.save(update_fields=["db_location"])
        resolve_unattended_plummets(self.room, departing=catcher)

        self.assertEqual(
            position_of(self.faller),
            self.ground,
            "losing the last catcher must complete the fall, not freeze it",
        )
        self.assertFalse(
            get_active_conditions(self.faller)
            .filter(condition__name=PLUMMETING_CONDITION_NAME)
            .exists(),
        )

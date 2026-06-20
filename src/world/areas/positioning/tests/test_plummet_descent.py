"""Action-driven plummet descent + impact in the round tick (#1228, Task 6).

Proves the descent seam: a faller carrying the Plummeting condition walks one
``elevation_anchor`` level down per END-of-round tick, and impacts (fall-damage
consequences through the standard survivability pipeline) the round they land on
solid ground (``elevation_anchor is None``). Impact removes the Plummeting
condition and clears the bound catch challenge.

AFK-safety is structural: ``tick_round_for_targets([], "end")`` is a no-op, so a
faller with no round participants never descends.

Tagged ``postgres``: ``apply_condition`` (used to set up the plummeting faller)
hits a PG-only ``DISTINCT ON`` that errors on the SQLite fast tier — a known
pre-existing limitation; run on CI's PG shard.

Built in setUp (not setUpTestData): factories create Evennia ObjectDB instances
(DbHolder — not deepcopyable), which would break setUpTestData's deepcopy.
"""

from __future__ import annotations

from django.test import TestCase, tag

from world.areas.positioning.constants import (
    FALL_DAMAGE_TYPE_NAME,
    PLUMMETING_CONDITION_NAME,
    PositionKind,
)
from world.areas.positioning.models import Position
from world.areas.positioning.plummet import begin_plummet
from world.areas.positioning.plummet_content import ensure_fall_content
from world.areas.positioning.services import force_move_to_position, position_of
from world.conditions.services import get_active_conditions
from world.mechanics.models import ChallengeInstance
from world.scenes.constants import SceneRoundStartReason
from world.scenes.models import SceneRound
from world.scenes.round_services import _danger_persists
from world.vitals.services import tick_round_for_targets


@tag("postgres")  # apply_condition (plummet setup) uses DISTINCT ON (PG-only)
class PlummetDescentTests(TestCase):
    def setUp(self) -> None:
        from evennia import create_object

        from world.character_sheets.factories import CharacterSheetFactory

        ensure_fall_content()

        self.room = create_object("typeclasses.rooms.Room", key="DescentRoom", nohome=True)
        sheet = CharacterSheetFactory()
        self.faller = sheet.character
        self.faller.db_location = self.room
        self.faller.save(update_fields=["db_location"])

        # A three-level vertical stack: top -> mid -> ground (anchor None).
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

    def _start_plummet_at(self, position: Position) -> None:
        force_move_to_position(self.faller, position)
        begin_plummet(self.faller, position)

    def _vitals(self):
        return self.faller.sheet_data.vitals

    def test_descends_one_level_per_round(self) -> None:
        self._start_plummet_at(self.top_chasm)
        tick_round_for_targets([self.faller], timing="end")
        self.assertEqual(position_of(self.faller), self.mid_chasm)

    def test_impact_at_bottom_applies_fall_damage_consequences(self) -> None:
        self._start_plummet_at(self.mid_chasm)
        health_before = self._vitals().health

        tick_round_for_targets([self.faller], timing="end")

        # Landed on the ground (anchor None) -> impact fired.
        self.assertEqual(position_of(self.faller), self.ground)
        self.assertLess(
            self._vitals().health,
            health_before,
            "fall impact should apply damage consequences",
        )
        self.assertFalse(
            get_active_conditions(self.faller)
            .filter(condition__name=PLUMMETING_CONDITION_NAME)
            .exists(),
            "impact should remove the Plummeting condition",
        )
        self.assertFalse(
            ChallengeInstance.objects.filter(target_object=self.faller, is_active=True).exists(),
            "impact should clear the bound catch challenge",
        )

    def test_afk_safe_no_tick_without_participants(self) -> None:
        self._start_plummet_at(self.top_chasm)
        tick_round_for_targets([], timing="end")
        self.assertEqual(
            position_of(self.faller),
            self.top_chasm,
            "no participants -> no tick -> no descent",
        )

    def test_danger_round_persists_while_plummeting(self) -> None:
        self._start_plummet_at(self.top_chasm)
        rnd = SceneRound.objects.filter(
            room=self.room, start_reason=SceneRoundStartReason.DANGER
        ).first()
        self.assertIsNotNone(rnd)
        self.assertTrue(_danger_persists(rnd))

    def test_fall_damage_type_seeded(self) -> None:
        from world.conditions.models import DamageType

        self.assertTrue(DamageType.objects.filter(name=FALL_DAMAGE_TYPE_NAME).exists())

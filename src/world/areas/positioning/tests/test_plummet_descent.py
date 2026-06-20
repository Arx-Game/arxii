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
        from world.vitals.factories import CharacterVitalsFactory

        ensure_fall_content()

        self.room = create_object("typeclasses.rooms.Room", key="DescentRoom", nohome=True)
        sheet = CharacterSheetFactory()
        # The impact path reads/writes the faller's CharacterVitals; CharacterSheetFactory
        # does not create one, so seed it explicitly (OneToOne to the sheet).
        CharacterVitalsFactory(character_sheet=sheet)
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

    def test_deep_fall_reaches_impact_not_stranded_midair(self) -> None:
        """I1 regression: a chasm deeper than the old 3-round duration must reach
        the floor and impact, never strand the faller mid-air.

        Builds a ≥4-level chasm chain ABOVE the existing top_chasm, applies the
        plummet, and ticks end-of-round repeatedly. With a PERMANENT (non-expiring)
        Plummeting condition the descent loop owns its lifetime, so the faller
        descends through every level to the floor and impacts — rather than the
        condition expiring on the 3rd tick mid-air (orphaning the catch challenge).
        """
        # Stack three more CHASM levels on top of the existing 3-level stack so the
        # fall is 5 levels deep (deeper than the old default_duration_value of 3).
        deeper_top = self.top_chasm
        for name in ("ledge two up", "ledge three up", "ledge four up"):
            higher = Position.objects.create(room=self.room, name=name, kind=PositionKind.CHASM)
            higher.elevation_anchor = deeper_top
            higher.save(update_fields=["elevation_anchor"])
            deeper_top = higher

        self._start_plummet_at(deeper_top)
        health_before = self._vitals().health

        # Tick generously more rounds than there are levels; descent + impact must
        # land well within them, and ticking past impact is a harmless no-op.
        for _ in range(12):
            tick_round_for_targets([self.faller], timing="end")
            if position_of(self.faller) == self.ground:
                break

        # Reached the floor — NOT stranded in a chasm mid-air.
        self.assertEqual(
            position_of(self.faller),
            self.ground,
            "deep fall must descend all the way to the floor, not expire mid-air",
        )
        # Impact fired (damage applied through the survivability pipeline).
        self.assertLess(
            self._vitals().health,
            health_before,
            "deep fall must reach impact and apply fall-damage consequences",
        )
        # Plummeting condition removed by impact.
        self.assertFalse(
            get_active_conditions(self.faller)
            .filter(condition__name=PLUMMETING_CONDITION_NAME)
            .exists(),
            "impact should remove the Plummeting condition",
        )
        # Catch challenge deactivated — not orphaned is_active=True.
        self.assertFalse(
            ChallengeInstance.objects.filter(target_object=self.faller, is_active=True).exists(),
            "impact should deactivate the bound catch challenge",
        )

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

"""Direct unit tests for defile_place_for_cast (#847).

The function is otherwise only exercised indirectly through use_technique
orchestrator tests. These assert its own branches: the defilement gate, the
opposed-resonance degrade, abyssal-taint spread, and the caster->world
corruption accrual (asserted at the call boundary — accrue_corruption has its
own preconditions/tests).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase, tag

from evennia_extensions.factories import RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.locations.services import effective_value, upsert_room_resonance_modifier
from world.magic.constants import ResonanceDirection
from world.magic.factories import (
    AffinityFactory,
    AffinityInteractionFactory,
    CharacterAuraFactory,
    ResonanceFactory,
    TechniqueFactory,
)
from world.magic.services.defilement import defile_place_for_cast
from world.magic.services.resonance_environment import ResonanceEnvironmentEffect
from world.magic.types.corruption import CorruptionSource
from world.magic.types.techniques import ResonanceInvolvement

_SEED_SOURCE = "test_seed"


def _effect(*, environment_affinity, source_affinity, defiles: bool, direction: str):
    """Build a ResonanceEnvironmentEffect to feed directly (skips evaluation)."""
    interaction = AffinityInteractionFactory(caster_dominance_defiles=defiles)
    return ResonanceEnvironmentEffect(
        valence="",
        kind="",
        direction=direction,
        magnitude=1,
        source_affinity=source_affinity,
        environment_affinity=environment_affinity,
        interaction=interaction,
        backfire_difficulty=0,
    )


@tag("postgres")  # magic is a parity-only app (materialized views / cascade reads)
class DefilePlaceForCastTest(TestCase):
    def setUp(self) -> None:
        self.caster_sheet = CharacterSheetFactory()
        CharacterAuraFactory(character=self.caster_sheet.character)  # → magically active
        self.room_profile = RoomProfileFactory()
        self.technique = TechniqueFactory()
        self.place_affinity = AffinityFactory(name="Primal")
        self.abyssal_affinity = AffinityFactory(name="Abyssal")

    def _defiling_effect(self):
        return _effect(
            environment_affinity=self.place_affinity,
            source_affinity=self.abyssal_affinity,
            defiles=True,
            direction=ResonanceDirection.CASTER_DOMINANT,
        )

    def _abyssal_result(self):
        resonance = ResonanceFactory(affinity=self.abyssal_affinity)
        result = MagicMock()
        result.resonance_involvements = (
            ResonanceInvolvement(
                resonance=resonance, stat_bonus_contribution=1, thread_pull_resonance_spent=0
            ),
        )
        return result, resonance

    @patch("world.magic.services.defilement.accrue_corruption")
    def test_no_aura_is_noop(self, mock_accrue) -> None:
        """A Quiescent caster (no aura) defiles nothing."""
        npc_sheet = CharacterSheetFactory()  # no CharacterAuraFactory → no aura
        result, _ = self._abyssal_result()

        defile_place_for_cast(
            caster_sheet=npc_sheet,
            room_profile=self.room_profile,
            technique=self.technique,
            technique_result=result,
            effect=self._defiling_effect(),
        )

        mock_accrue.assert_not_called()

    @patch("world.magic.services.defilement.accrue_corruption")
    def test_gate_not_met_is_noop(self, mock_accrue) -> None:
        """An effect that isn't a caster_dominance_defiles interaction is inert."""
        result, abyssal_resonance = self._abyssal_result()
        non_defiling = _effect(
            environment_affinity=self.place_affinity,
            source_affinity=self.abyssal_affinity,
            defiles=False,  # gate fails
            direction=ResonanceDirection.CASTER_DOMINANT,
        )

        defile_place_for_cast(
            caster_sheet=self.caster_sheet,
            room_profile=self.room_profile,
            technique=self.technique,
            technique_result=result,
            effect=non_defiling,
        )

        mock_accrue.assert_not_called()
        self.assertEqual(
            effective_value(self.room_profile.objectdb, resonance=abyssal_resonance), 0
        )

    def test_degrades_opposed_place_resonance(self) -> None:
        """The place's dominant opposed resonance is degraded by defile_degrade_per_cast."""
        opposed = ResonanceFactory(affinity=self.place_affinity)
        upsert_room_resonance_modifier(self.room_profile, opposed, source=_SEED_SOURCE, delta=50)
        room = self.room_profile.objectdb
        before = effective_value(room, resonance=opposed)
        # No abyssal involvements → isolates the degrade step (no spread/corruption).
        empty_result = MagicMock()
        empty_result.resonance_involvements = ()

        defile_place_for_cast(
            caster_sheet=self.caster_sheet,
            room_profile=self.room_profile,
            technique=self.technique,
            technique_result=empty_result,
            effect=self._defiling_effect(),
        )

        # Default defile_degrade_per_cast is 6; a DEFILE_SOURCE row carries the -6.
        self.assertEqual(effective_value(room, resonance=opposed), before - 6)

    @patch("world.magic.services.defilement.accrue_corruption")
    def test_spreads_abyssal_taint_and_accrues_corruption(self, mock_accrue) -> None:
        """Abyssal resonances spread onto the room and accrue caster corruption."""
        result, abyssal_resonance = self._abyssal_result()
        room = self.room_profile.objectdb

        defile_place_for_cast(
            caster_sheet=self.caster_sheet,
            room_profile=self.room_profile,
            technique=self.technique,
            technique_result=result,
            effect=self._defiling_effect(),
        )

        # Spread: default defile_spread_per_cast is 6 (room started at 0).
        self.assertEqual(effective_value(room, resonance=abyssal_resonance), 6)
        # Corruption accrued to the caster via the DEFILEMENT source (amount = 2 default).
        mock_accrue.assert_called_once_with(
            character_sheet=self.caster_sheet,
            resonance=abyssal_resonance,
            amount=2,
            source=CorruptionSource.DEFILEMENT,
        )

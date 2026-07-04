"""Tests for Court signed-regard pull modulation (#1831 Task 3).

``court_regard_modulation`` scales a COVENANT_ROLE thread's pull effect by the
covenant leader's signed ``NpcRegard`` for the live target, sign-directed by
the effect's ``RegardPolarity``. Full branch table below.
"""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import CovenantType
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
)
from world.magic.constants import COURT_REGARD_PULL_K, RegardPolarity, TargetKind
from world.magic.factories import ThreadFactory, ThreadPullEffectFactory
from world.magic.services.pull_modulation_court import court_regard_modulation
from world.npc_services.factories import NpcRegardFactory
from world.npc_services.models import REGARD_MAX
from world.scenes.services import active_persona_for_sheet


class CourtRegardModulationTests(TestCase):
    """Full branch table for court_regard_modulation."""

    BASE_SCALED = 10

    def _setup_leader_and_role(self) -> tuple:
        """A Court covenant with a leader + role."""
        leader_sheet = CharacterSheetFactory()
        covenant = CovenantFactory(covenant_type=CovenantType.COURT, leader=leader_sheet)
        role = CovenantRoleFactory(covenant_type=CovenantType.COURT)
        return leader_sheet, covenant, role

    def _servant_thread(self, *, covenant, role, engaged=True) -> object:
        """A servant with an engaged Court membership + a COVENANT_ROLE thread anchored on role."""
        servant = CharacterSheetFactory()
        CharacterCovenantRoleFactory(
            character_sheet=servant,
            covenant=covenant,
            covenant_role=role,
            engaged=engaged,
        )
        return ThreadFactory(
            owner=servant,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=role,
            target_trait=None,
        )

    def _effect(self, polarity) -> object:
        return ThreadPullEffectFactory(
            target_kind=TargetKind.COVENANT_ROLE,
            regard_polarity=polarity,
        )

    def _regard(self, *, leader_sheet, target_sheet, value: int) -> None:
        NpcRegardFactory(
            holder_persona=active_persona_for_sheet(leader_sheet),
            target_persona=active_persona_for_sheet(target_sheet),
            value=value,
        )

    def _expected_empowered(self, regard: int) -> int:
        bonus = round(self.BASE_SCALED * (abs(regard) / REGARD_MAX) * COURT_REGARD_PULL_K)
        return self.BASE_SCALED + bonus

    # -- OFFENSIVE ----------------------------------------------------------

    def test_offensive_empowered_by_negative_regard(self) -> None:
        leader_sheet, covenant, role = self._setup_leader_and_role()
        thread = self._servant_thread(covenant=covenant, role=role)
        target_sheet = CharacterSheetFactory()
        self._regard(leader_sheet=leader_sheet, target_sheet=target_sheet, value=-500)
        effect = self._effect(RegardPolarity.OFFENSIVE)
        target = target_sheet.character

        result = court_regard_modulation(thread, target, effect, self.BASE_SCALED)

        self.assertEqual(result, self._expected_empowered(-500))
        self.assertGreater(result, self.BASE_SCALED)

    def test_offensive_noop_on_positive_regard(self) -> None:
        leader_sheet, covenant, role = self._setup_leader_and_role()
        thread = self._servant_thread(covenant=covenant, role=role)
        target_sheet = CharacterSheetFactory()
        self._regard(leader_sheet=leader_sheet, target_sheet=target_sheet, value=500)
        effect = self._effect(RegardPolarity.OFFENSIVE)
        target = target_sheet.character

        result = court_regard_modulation(thread, target, effect, self.BASE_SCALED)

        self.assertEqual(result, self.BASE_SCALED)

    # -- PROTECTIVE -----------------------------------------------------------

    def test_protective_empowered_by_positive_regard(self) -> None:
        leader_sheet, covenant, role = self._setup_leader_and_role()
        thread = self._servant_thread(covenant=covenant, role=role)
        target_sheet = CharacterSheetFactory()
        self._regard(leader_sheet=leader_sheet, target_sheet=target_sheet, value=500)
        effect = self._effect(RegardPolarity.PROTECTIVE)
        target = target_sheet.character

        result = court_regard_modulation(thread, target, effect, self.BASE_SCALED)

        self.assertEqual(result, self._expected_empowered(500))
        self.assertGreater(result, self.BASE_SCALED)

    def test_protective_noop_on_negative_regard(self) -> None:
        leader_sheet, covenant, role = self._setup_leader_and_role()
        thread = self._servant_thread(covenant=covenant, role=role)
        target_sheet = CharacterSheetFactory()
        self._regard(leader_sheet=leader_sheet, target_sheet=target_sheet, value=-500)
        effect = self._effect(RegardPolarity.PROTECTIVE)
        target = target_sheet.character

        result = court_regard_modulation(thread, target, effect, self.BASE_SCALED)

        self.assertEqual(result, self.BASE_SCALED)

    # -- NEUTRAL --------------------------------------------------------------

    def test_neutral_empowered_by_positive_regard(self) -> None:
        leader_sheet, covenant, role = self._setup_leader_and_role()
        thread = self._servant_thread(covenant=covenant, role=role)
        target_sheet = CharacterSheetFactory()
        self._regard(leader_sheet=leader_sheet, target_sheet=target_sheet, value=200)
        effect = self._effect(RegardPolarity.NEUTRAL)
        target = target_sheet.character

        result = court_regard_modulation(thread, target, effect, self.BASE_SCALED)

        self.assertEqual(result, self._expected_empowered(200))
        self.assertGreater(result, self.BASE_SCALED)

    def test_neutral_empowered_by_negative_regard(self) -> None:
        leader_sheet, covenant, role = self._setup_leader_and_role()
        thread = self._servant_thread(covenant=covenant, role=role)
        target_sheet = CharacterSheetFactory()
        self._regard(leader_sheet=leader_sheet, target_sheet=target_sheet, value=-200)
        effect = self._effect(RegardPolarity.NEUTRAL)
        target = target_sheet.character

        result = court_regard_modulation(thread, target, effect, self.BASE_SCALED)

        self.assertEqual(result, self._expected_empowered(-200))
        self.assertGreater(result, self.BASE_SCALED)

    # -- Regard == 0 / no leader ------------------------------------------------

    def test_regard_zero_is_noop(self) -> None:
        _leader_sheet, covenant, role = self._setup_leader_and_role()
        thread = self._servant_thread(covenant=covenant, role=role)
        target_sheet = CharacterSheetFactory()
        effect = self._effect(RegardPolarity.NEUTRAL)
        target = target_sheet.character

        result = court_regard_modulation(thread, target, effect, self.BASE_SCALED)

        self.assertEqual(result, self.BASE_SCALED)

    def test_no_leader_is_noop(self) -> None:
        servant = CharacterSheetFactory()
        covenant = CovenantFactory(covenant_type=CovenantType.COURT, leader=None)
        role = CovenantRoleFactory(covenant_type=CovenantType.COURT)
        CharacterCovenantRoleFactory(
            character_sheet=servant, covenant=covenant, covenant_role=role, engaged=True
        )
        thread = ThreadFactory(
            owner=servant,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=role,
            target_trait=None,
        )
        target_sheet = CharacterSheetFactory()
        effect = self._effect(RegardPolarity.NEUTRAL)
        target = target_sheet.character

        result = court_regard_modulation(thread, target, effect, self.BASE_SCALED)

        self.assertEqual(result, self.BASE_SCALED)

    def test_no_engaged_membership_is_noop(self) -> None:
        """Membership exists but is not engaged on this covenant_role -> no leader resolution."""
        leader_sheet, covenant, role = self._setup_leader_and_role()
        thread = self._servant_thread(covenant=covenant, role=role, engaged=False)
        target_sheet = CharacterSheetFactory()
        self._regard(leader_sheet=leader_sheet, target_sheet=target_sheet, value=500)
        effect = self._effect(RegardPolarity.NEUTRAL)
        target = target_sheet.character

        result = court_regard_modulation(thread, target, effect, self.BASE_SCALED)

        self.assertEqual(result, self.BASE_SCALED)

    def test_target_with_no_sheet_is_noop(self) -> None:
        from evennia_extensions.factories import ObjectDBFactory

        _leader_sheet, covenant, role = self._setup_leader_and_role()
        thread = self._servant_thread(covenant=covenant, role=role)
        effect = self._effect(RegardPolarity.NEUTRAL)
        target = ObjectDBFactory()

        result = court_regard_modulation(thread, target, effect, self.BASE_SCALED)

        self.assertEqual(result, self.BASE_SCALED)

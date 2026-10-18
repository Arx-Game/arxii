"""The ``gm dramatic`` subverb of ``CmdGMDashboard`` (#3387, Senior GM+).

Every player path of ``gm check``, ``gm award`` and ``gm condition`` (and
``gm condition remove``) is typed through the command handler in
``integration_tests/test_refereeing_the_table_journeys.py`` (#3657 tranche 7).
What stays here is the dramatic-beat subverb, which belongs to the combat group
of the ledger and keeps its hand-built fixture until that group's journeys take
it; a new ``gm`` subverb gets its lines in the journeys, not here.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from commands.gm_ops import CmdGMDashboard
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import ParticipantStatus, SurgeTriggerKind
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.models import DramaticSurgeRecord
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory
from world.mechanics.constants import EngagementType
from world.mechanics.services import begin_engagement
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import SceneFactory, SceneParticipationFactory


def _room(*, db_key: str = "GMOpsRoom") -> object:
    return ObjectDBFactory(db_key=db_key, db_typeclass_path="typeclasses.rooms.Room")


def _pc_in_room(room: object, *, db_key: str) -> tuple[object, object]:
    char = CharacterFactory(db_key=db_key, location=room)
    CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet__character=char)
    tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
    return char, tenure.player_data.account


def _run_cmd(caller: object, args: str) -> list[str]:
    cmd = CmdGMDashboard()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"gm {args}".strip()
    cmd.func()
    return [str(c.args[0]) for c in caller.msg.call_args_list if c.args]


class CmdGMDramaticTests(TestCase):
    """``gm dramatic <character> reason=<text>`` (#3387, Senior GM+)."""

    def setUp(self) -> None:
        self.room = _room()
        self.scene = SceneFactory(room=self.room)

        self.gm_actor, self.gm_account = _pc_in_room(self.room, db_key="GMOpsGM")
        GMProfileFactory(account=self.gm_account, level=GMLevel.SENIOR)
        SceneParticipationFactory(scene=self.scene, account=self.gm_account, is_gm=True)
        self.gm_actor.msg = MagicMock()

        self.player_actor, self.player_account = _pc_in_room(self.room, db_key="GMOpsPlayer")
        SceneParticipationFactory(scene=self.scene, account=self.player_account, is_gm=False)
        self.player_actor.msg = MagicMock()

        self.target, self.target_account = _pc_in_room(self.room, db_key="GMOpsTarget")

        self.encounter = CombatEncounterFactory(room=self.room, scene=self.scene)
        self.participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.target.character_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        begin_engagement(self.target, EngagementType.COMBAT, source=self.encounter)

        self.junior_gm_actor, self.junior_gm_account = _pc_in_room(
            self.room, db_key="GMOpsJuniorGM"
        )
        GMProfileFactory(account=self.junior_gm_account, level=GMLevel.JUNIOR)
        SceneParticipationFactory(scene=self.scene, account=self.junior_gm_account, is_gm=True)
        self.junior_gm_actor.msg = MagicMock()

    def test_senior_gm_triggers_a_dramatic_beat(self) -> None:
        messages = _run_cmd(self.gm_actor, f"dramatic {self.target.key} reason=a costly misstep")
        self.assertTrue(messages)
        self.assertFalse(any("Usage" in m for m in messages))
        self.assertTrue(
            DramaticSurgeRecord.objects.filter(
                encounter=self.encounter, trigger_kind=SurgeTriggerKind.GM_MANUAL
            ).exists()
        )

    def test_missing_reason_shows_usage(self) -> None:
        messages = _run_cmd(self.gm_actor, f"dramatic {self.target.key}")
        self.assertTrue(any("Usage: gm dramatic" in m for m in messages))
        self.assertFalse(
            DramaticSurgeRecord.objects.filter(
                encounter=self.encounter, trigger_kind=SurgeTriggerKind.GM_MANUAL
            ).exists()
        )

    def test_below_senior_gm_is_refused(self) -> None:
        messages = _run_cmd(
            self.junior_gm_actor, f"dramatic {self.target.key} reason=not senior enough"
        )
        self.assertTrue(len(messages) > 0)
        self.assertFalse(
            DramaticSurgeRecord.objects.filter(
                encounter=self.encounter, trigger_kind=SurgeTriggerKind.GM_MANUAL
            ).exists()
        )

    def test_non_gm_is_refused(self) -> None:
        messages = _run_cmd(self.player_actor, f"dramatic {self.target.key} reason=self-serving")
        self.assertTrue(len(messages) > 0)
        self.assertFalse(
            DramaticSurgeRecord.objects.filter(
                encounter=self.encounter, trigger_kind=SurgeTriggerKind.GM_MANUAL
            ).exists()
        )

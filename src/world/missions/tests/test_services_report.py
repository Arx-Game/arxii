"""Tests for mission after-action reporting (#1753) — Slice 1 (Accurate payout + gates)."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from evennia.objects.models import ObjectDB

from evennia_extensions.factories import RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.missions.constants import DeedRewardKind, DeedRewardSink, MissionStatus
from world.missions.factories import (
    MissionDeedRecordFactory,
    MissionDeedRewardLineFactory,
    MissionInstanceFactory,
    MissionParticipantFactory,
    MissionTemplateFactory,
)
from world.missions.services.report import (
    MissionReportError,
    report_mission,
    report_to_role_for,
)
from world.npc_services.factories import FunctionaryFactory, NPCRoleFactory

_DELIVER = "world.missions.services.rewards.deliver_mission_money"


def _build_reportable():
    """Return (role, room, reporter, instance) — a RESOLVED run reportable to a `role` clerk."""
    role = NPCRoleFactory(name="Builders Guild Clerk")
    room = RoomProfileFactory()
    reporter = CharacterSheetFactory().character
    ObjectDB.objects.filter(pk=reporter.pk).update(db_location=room.objectdb)
    reporter.db_location = room.objectdb
    instance = MissionInstanceFactory(
        template=MissionTemplateFactory(report_to_role=role),
        status=MissionStatus.RESOLVED,
    )
    MissionParticipantFactory(instance=instance, character=reporter, is_contract_holder=True)
    deed = MissionDeedRecordFactory(instance=instance, actor=reporter)
    MissionDeedRewardLineFactory(
        deed=deed,
        recipient=reporter,
        kind=DeedRewardKind.IMMEDIATE,
        sink=DeedRewardSink.MONEY,
        amount=100,
    )
    return role, room, reporter, instance


class ReportToRoleForTests(TestCase):
    def test_prefers_template_report_to_role(self) -> None:
        role = NPCRoleFactory(name="Guildmaster")
        instance = MissionInstanceFactory(template=MissionTemplateFactory(report_to_role=role))
        self.assertEqual(report_to_role_for(instance), role)

    def test_none_when_no_report_target(self) -> None:
        instance = MissionInstanceFactory()  # no report_to_role, no source_offer
        self.assertIsNone(report_to_role_for(instance))


class ReportMissionTests(TestCase):
    def setUp(self) -> None:
        self.role = NPCRoleFactory(name="Builders Guild Clerk")
        self.room = RoomProfileFactory()
        self.reporter = CharacterSheetFactory().character
        ObjectDB.objects.filter(pk=self.reporter.pk).update(db_location=self.room.objectdb)
        self.reporter.db_location = self.room.objectdb
        self.instance = MissionInstanceFactory(
            template=MissionTemplateFactory(report_to_role=self.role),
            status=MissionStatus.RESOLVED,
        )
        MissionParticipantFactory(
            instance=self.instance, character=self.reporter, is_contract_holder=True
        )
        deed = MissionDeedRecordFactory(instance=self.instance, actor=self.reporter)
        MissionDeedRewardLineFactory(
            deed=deed,
            recipient=self.reporter,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.MONEY,
            amount=100,
        )

    def _place_clerk(self) -> None:
        FunctionaryFactory(role=self.role, room=self.room)

    @patch(_DELIVER)
    def test_accurate_report_pays_and_completes(self, mock_deliver) -> None:
        self._place_clerk()
        result = report_mission(instance=self.instance, style="accurate", reporter=self.reporter)
        mock_deliver.assert_called_once()
        self.assertEqual(mock_deliver.call_args.kwargs["amount"], 100)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.status, MissionStatus.COMPLETE)
        self.assertEqual(self.instance.report_style, "accurate")
        self.assertIsNotNone(self.instance.reported_at)
        self.assertEqual(result.functionary.role, self.role)

    @patch(_DELIVER)
    def test_no_co_located_functionary_refuses(self, mock_deliver) -> None:
        # No clerk placed in the room.
        with self.assertRaises(MissionReportError):
            report_mission(instance=self.instance, style="accurate", reporter=self.reporter)
        mock_deliver.assert_not_called()
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.status, MissionStatus.RESOLVED)

    def test_not_resolved_refuses(self) -> None:
        self._place_clerk()
        self.instance.status = MissionStatus.ACTIVE
        self.instance.save(update_fields=["status"])
        with self.assertRaises(MissionReportError):
            report_mission(instance=self.instance, style="accurate", reporter=self.reporter)

    def test_unknown_style_refuses(self) -> None:
        self._place_clerk()
        with self.assertRaises(MissionReportError):
            report_mission(instance=self.instance, style="bragging", reporter=self.reporter)

    @patch(_DELIVER)
    def test_mostly_accurate_is_offerable(self, mock_deliver) -> None:
        # #1765 lit this style up; the dodge/consequence matrix lives in
        # test_report_heat.py — here we just pin that it completes the run.
        self._place_clerk()
        result = report_mission(
            instance=self.instance, style="mostly_accurate", reporter=self.reporter
        )
        mock_deliver.assert_called_once()
        self.assertIsNotNone(result.dodge_success)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.status, MissionStatus.COMPLETE)

    @patch(_DELIVER)
    def test_humble_grants_bene_resonance(self, mock_deliver) -> None:  # noqa: ARG002
        from world.magic.factories import ResonanceFactory
        from world.magic.models import CharacterResonance

        bene = ResonanceFactory(name="Bene")
        self._place_clerk()
        report_mission(instance=self.instance, style="humble", reporter=self.reporter)
        cr = CharacterResonance.objects.get(
            character_sheet=self.reporter.sheet_data, resonance=bene
        )
        self.assertEqual(cr.balance, 1)

    def _seed_persuasion(self, *, has_skill: bool = True) -> None:
        from world.checks.factories import CheckTypeFactory
        from world.skills.factories import CharacterSkillValueFactory, SkillFactory
        from world.traits.factories import SkillTraitFactory

        CheckTypeFactory(name="Persuasion")
        if has_skill:
            skill = SkillFactory(trait=SkillTraitFactory(name="Persuasion"))
            CharacterSkillValueFactory(character=self.reporter.sheet_data, skill=skill, value=30)

    def test_embellished_requires_persuasion(self) -> None:
        self._seed_persuasion(has_skill=False)
        self._place_clerk()
        with self.assertRaises(MissionReportError):
            report_mission(instance=self.instance, style="embellished", reporter=self.reporter)

    @patch("world.currency.services.deliver_mission_money")
    @patch("world.missions.services.rewards.deliver_mission_money")
    @patch("world.checks.services.perform_check")
    def test_embellished_success_doubles_money_and_grants_insidia(
        self,
        mock_check,
        mock_base,  # noqa: ARG002
        mock_bonus,
    ) -> None:
        from unittest.mock import MagicMock

        from world.magic.factories import ResonanceFactory
        from world.magic.models import CharacterResonance

        insidia = ResonanceFactory(name="Insidia")
        self._seed_persuasion()
        mock_check.return_value = MagicMock(outcome=MagicMock(success_level=1))
        self._place_clerk()
        result = report_mission(instance=self.instance, style="embellished", reporter=self.reporter)
        self.assertTrue(result.embellish_success)
        mock_bonus.assert_called_once()
        self.assertEqual(mock_bonus.call_args.kwargs["amount"], 100)  # doubled the base 100
        cr = CharacterResonance.objects.get(
            character_sheet=self.reporter.sheet_data, resonance=insidia
        )
        self.assertEqual(cr.balance, 1)

    @patch("world.currency.services.deliver_mission_money")
    @patch("world.missions.services.rewards.deliver_mission_money")
    @patch("world.checks.services.perform_check")
    def test_embellished_failure_no_bonus_but_completes(
        self,
        mock_check,
        mock_base,  # noqa: ARG002
        mock_bonus,
    ) -> None:
        from unittest.mock import MagicMock

        self._seed_persuasion()
        mock_check.return_value = MagicMock(outcome=MagicMock(success_level=-1))
        self._place_clerk()
        result = report_mission(instance=self.instance, style="embellished", reporter=self.reporter)
        self.assertFalse(result.embellish_success)
        mock_bonus.assert_not_called()
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.status, MissionStatus.COMPLETE)


class CmdMissionReportSurfaceTests(TestCase):
    """The telnet `mission report <id> <style>` verb (#1753)."""

    def test_report_completes_via_command(self) -> None:
        from unittest.mock import MagicMock

        from commands.missions import CmdMission

        role, room, reporter, instance = _build_reportable()
        FunctionaryFactory(role=role, room=room)
        cmd = CmdMission()
        cmd.caller = reporter
        cmd.args = f"report {instance.pk} accurate"
        cmd.raw_string = f"mission report {instance.pk} accurate"
        reporter.msg = MagicMock()
        with patch(_DELIVER):
            cmd.func()
        instance.refresh_from_db()
        self.assertEqual(instance.status, MissionStatus.COMPLETE)
        reporter.msg.assert_called()


class MissionReportApiTests(TestCase):
    """The web `POST /api/missions/journal/<id>/report/` endpoint (#1753)."""

    def test_report_endpoint_completes(self) -> None:
        from types import SimpleNamespace

        from rest_framework.test import APIClient

        from world.roster.factories import PlayerDataFactory

        role, room, reporter, instance = _build_reportable()
        FunctionaryFactory(role=role, room=room)
        player_data = PlayerDataFactory()
        client = APIClient()
        user = SimpleNamespace(
            is_authenticated=True, is_staff=False, player_data=player_data, puppet=reporter
        )
        client.force_authenticate(user=user)
        with patch(_DELIVER):
            response = client.post(
                f"/api/missions/journal/{instance.pk}/report/", {"style": "accurate"}, format="json"
            )
        assert response.status_code == 200, response.data
        instance.refresh_from_db()
        self.assertEqual(instance.status, MissionStatus.COMPLETE)

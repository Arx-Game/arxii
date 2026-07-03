"""Report-time criminal consequences (#1765): CRIME_WATCH heat, dodge, association.

The live crime-watch path: a RESOLVED run whose terminal deed carries a
``PROPAGATION/CRIME_WATCH`` line (``ref`` = CrimeKind slug) reported inside the
enforcing society's dominion. ``perform_check`` is mocked at its source module
(the report helpers lazy-import it), matching the embellish-test pattern.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase
from evennia.objects.models import ObjectDB

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.justice.constants import DEFAULT_HEAT_WEIGHT
from world.justice.factories import AreaLawFactory, CrimeKindFactory
from world.justice.models import PersonaHeat
from world.missions.constants import DeedRewardKind, DeedRewardSink, MissionStatus
from world.missions.factories import (
    MissionDeedRecordFactory,
    MissionDeedRewardLineFactory,
    MissionInstanceFactory,
    MissionParticipantFactory,
    MissionTemplateFactory,
)
from world.missions.services.report import report_mission
from world.npc_services.factories import FunctionaryFactory, NPCRoleFactory
from world.scenes.factories import PersonaFactory
from world.societies.factories import SocietyFactory
from world.societies.models import SocietyReputation

_DELIVER = "world.missions.services.rewards.deliver_mission_money"
_CHECK = "world.checks.services.perform_check"


class ReportHeatTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.crown = SocietyFactory()
        cls.kingdom = AreaFactory(level=AreaLevel.KINGDOM, dominant_society=cls.crown)
        cls.city = AreaFactory(level=AreaLevel.CITY, parent=cls.kingdom)
        cls.theft = CrimeKindFactory(slug="theft", name="Theft")
        cls.law = AreaLawFactory(
            area=cls.kingdom, crime_kind=cls.theft, heat_weight=DEFAULT_HEAT_WEIGHT
        )

    def setUp(self) -> None:
        self.role = NPCRoleFactory(name="Fence")
        self.room = RoomProfileFactory(area=self.city)
        self.sheet = CharacterSheetFactory()
        self.reporter = self.sheet.character
        ObjectDB.objects.filter(pk=self.reporter.pk).update(db_location=self.room.objectdb)
        self.reporter.db_location = self.room.objectdb
        self.instance = MissionInstanceFactory(
            template=MissionTemplateFactory(report_to_role=self.role),
            status=MissionStatus.RESOLVED,
        )
        self.participant = MissionParticipantFactory(
            instance=self.instance, character=self.reporter, is_contract_holder=True
        )
        deed = MissionDeedRecordFactory(instance=self.instance, actor=self.reporter)
        MissionDeedRewardLineFactory(
            deed=deed,
            recipient=self.reporter,
            kind=DeedRewardKind.PROPAGATION,
            sink=DeedRewardSink.CRIME_WATCH,
            ref="theft",
        )
        FunctionaryFactory(role=self.role, room=self.room)

    @property
    def primary(self):
        return self.sheet.primary_persona

    def _seed_persuasion_check(self) -> None:
        # The dodge/association helpers look the CheckTypes up before calling
        # perform_check (which the tests mock) — without them they fail closed.
        # Ratified names (2026-07-03): dodge → Con, association → Deceive.
        from world.checks.factories import CheckTypeFactory

        CheckTypeFactory(name="Con")
        CheckTypeFactory(name="Deceive")

    @patch(_DELIVER)
    def test_accurate_report_mints_heat_and_reputation_sting(self, mock_deliver) -> None:  # noqa: ARG002
        report_mission(instance=self.instance, style="accurate", reporter=self.reporter)
        row = PersonaHeat.objects.get(persona=self.primary)
        self.assertEqual(row.value, DEFAULT_HEAT_WEIGHT)
        self.assertEqual(row.area, self.city)
        self.assertEqual(row.society, self.crown)
        rep = SocietyReputation.objects.get(persona=self.primary, society=self.crown)
        self.assertEqual(rep.value, -DEFAULT_HEAT_WEIGHT)

    @patch(_CHECK)
    @patch(_DELIVER)
    def test_mostly_accurate_success_dodges_consequences(self, mock_deliver, mock_check) -> None:  # noqa: ARG002
        self._seed_persuasion_check()
        mock_check.return_value = MagicMock(outcome=MagicMock(success_level=1))
        result = report_mission(
            instance=self.instance, style="mostly_accurate", reporter=self.reporter
        )
        self.assertTrue(result.dodge_success)
        self.assertEqual(PersonaHeat.objects.count(), 0)
        self.assertFalse(SocietyReputation.objects.filter(persona=self.primary).exists())

    @patch(_CHECK)
    @patch(_DELIVER)
    def test_mostly_accurate_failure_applies_consequences(self, mock_deliver, mock_check) -> None:  # noqa: ARG002
        mock_check.return_value = MagicMock(outcome=MagicMock(success_level=-1))
        result = report_mission(
            instance=self.instance, style="mostly_accurate", reporter=self.reporter
        )
        self.assertFalse(result.dodge_success)
        row = PersonaHeat.objects.get(persona=self.primary)
        self.assertEqual(row.value, DEFAULT_HEAT_WEIGHT)

    @patch(_DELIVER)
    def test_unseeded_check_fails_closed(self, mock_deliver) -> None:  # noqa: ARG002
        # No Persuasion CheckType exists in this fixture: the dodge simply
        # fails and the consequences land — never a crash, never a free pass.
        result = report_mission(
            instance=self.instance, style="mostly_accurate", reporter=self.reporter
        )
        self.assertFalse(result.dodge_success)
        self.assertEqual(PersonaHeat.objects.count(), 1)

    @patch(_CHECK)
    @patch(_DELIVER)
    def test_masked_deed_heat_lands_on_the_mask(self, mock_deliver, mock_check) -> None:  # noqa: ARG002
        """The run was accepted under a mask: the mask soaks the heat, and a
        successful association check keeps the reporting face clean."""
        self._seed_persuasion_check()
        mask = PersonaFactory(character_sheet=self.sheet)
        self.instance.accepted_as_persona = mask
        self.instance.save(update_fields=["accepted_as_persona"])
        mock_check.return_value = MagicMock(outcome=MagicMock(success_level=1))
        report_mission(instance=self.instance, style="accurate", reporter=self.reporter)
        self.assertEqual(PersonaHeat.objects.get(persona=mask).value, DEFAULT_HEAT_WEIGHT)
        self.assertFalse(PersonaHeat.objects.filter(persona=self.primary).exists())

    @patch(_CHECK)
    @patch(_DELIVER)
    def test_failed_association_copies_mask_heat_to_reporter(
        self,
        mock_deliver,  # noqa: ARG002
        mock_check,
    ) -> None:
        self._seed_persuasion_check()
        mask = PersonaFactory(character_sheet=self.sheet)
        self.instance.accepted_as_persona = mask
        self.instance.save(update_fields=["accepted_as_persona"])
        mock_check.return_value = MagicMock(outcome=MagicMock(success_level=-1))
        report_mission(instance=self.instance, style="accurate", reporter=self.reporter)
        mask_row = PersonaHeat.objects.get(persona=mask)
        face_row = PersonaHeat.objects.get(persona=self.primary)
        self.assertEqual(mask_row.value, DEFAULT_HEAT_WEIGHT)
        self.assertEqual(face_row.value, DEFAULT_HEAT_WEIGHT)  # copied, mask keeps its own

    @patch(_DELIVER)
    def test_unknown_crime_slug_drops_consequence_loudly(self, mock_deliver) -> None:  # noqa: ARG002
        deed = self.instance.deeds.first()
        deed.reward_lines.all().delete()
        MissionDeedRewardLineFactory(
            deed=deed,
            recipient=self.reporter,
            kind=DeedRewardKind.PROPAGATION,
            sink=DeedRewardSink.CRIME_WATCH,
            ref="not-a-crime-kind",
        )
        report_mission(instance=self.instance, style="accurate", reporter=self.reporter)
        self.assertEqual(PersonaHeat.objects.count(), 0)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.status, MissionStatus.COMPLETE)

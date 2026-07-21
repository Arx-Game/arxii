"""Table sheet-update request actions (#2607)."""

from django.test import TestCase

from actions.definitions.table_requests import (
    TableRequestCompleteAction,
    TableRequestSignoffAction,
    TableRequestSubmitAction,
)
from actions.registry import ACTIONS_BY_KEY
from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.factories import DistinctionFactory
from world.distinctions.models import CharacterDistinction
from world.gm.constants import TableRequestStatus
from world.gm.factories import GMTableFactory, GMTableMembershipFactory
from world.gm.models import TableUpdateRequest
from world.progression.models.rewards import ExperiencePointsData
from world.scenes.factories import PersonaFactory


class TableRequestActionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.table = GMTableFactory()
        # Member: funded sheet + persona pinned to the table.
        cls.member_sheet = CharacterSheetFactory()
        member_account = AccountFactory()
        cls.member_sheet.character.account = member_account
        cls.member_sheet.character.save()
        ExperiencePointsData.objects.get_or_create(
            account=member_account, defaults={"total_earned": 100, "total_spent": 0}
        )
        cls.member = cls.member_sheet.character
        cls.membership = GMTableMembershipFactory(
            table=cls.table, persona=PersonaFactory(character_sheet=cls.member_sheet)
        )
        # GM actor: a character whose account owns the table.
        cls.gm_sheet = CharacterSheetFactory()
        cls.gm_sheet.character.account = cls.table.gm.account
        cls.gm_sheet.character.save()
        cls.gm = cls.gm_sheet.character
        cls.distinction = DistinctionFactory(slug="silver-tongue", cost_per_rank=4)

    def test_all_four_registered(self) -> None:
        for key in (
            "table_request_submit",
            "table_request_withdraw",
            "table_request_complete",
            "table_request_signoff",
        ):
            assert key in ACTIONS_BY_KEY

    def test_submit_signoff_complete_happy_path(self) -> None:
        result = TableRequestSubmitAction().run(
            self.member,
            table_id=self.table.pk,
            distinction_slug="silver-tongue",
            removing="0",
        )
        assert result.success is True
        req = TableUpdateRequest.objects.get(membership=self.membership)

        signoff = TableRequestSignoffAction().run(self.gm, request_id=req.pk, approve="1")
        assert signoff.success is True
        req.refresh_from_db()
        assert req.status == TableRequestStatus.APPROVED

        completed = TableRequestCompleteAction().run(self.member, request_id=req.pk)
        assert completed.success is True
        assert CharacterDistinction.objects.filter(
            character=self.member_sheet, distinction=self.distinction
        ).exists()

    def test_signoff_by_non_gm_fails(self) -> None:
        req = TableRequestSubmitAction().run(
            self.member, table_id=self.table.pk, distinction_slug="silver-tongue", removing="0"
        )
        assert req.success
        request = TableUpdateRequest.objects.get(membership=self.membership)
        # The member is not the GM of the table.
        result = TableRequestSignoffAction().run(self.member, request_id=request.pk, approve="1")
        assert result.success is False
        assert "not the GM" in result.message

    def test_complete_by_non_owner_fails(self) -> None:
        TableRequestSubmitAction().run(
            self.member, table_id=self.table.pk, distinction_slug="silver-tongue", removing="0"
        )
        request = TableUpdateRequest.objects.get(membership=self.membership)
        TableRequestSignoffAction().run(self.gm, request_id=request.pk, approve="1")
        # A different character tries to complete it.
        other = CharacterSheetFactory().character
        result = TableRequestCompleteAction().run(other, request_id=request.pk)
        assert result.success is False
        assert "not your request" in result.message

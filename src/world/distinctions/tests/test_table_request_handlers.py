"""Distinction table-request completion handlers (#2607)."""

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.factories import DistinctionChangeRequestFactory, DistinctionFactory
from world.distinctions.models import CharacterDistinction
from world.distinctions.services import grant_distinction
from world.distinctions.table_request_handlers import (
    XPInsufficient,
    complete_distinction_add,
    complete_distinction_remove,
)
from world.distinctions.types import DistinctionOrigin
from world.gm.constants import TableRequestKind
from world.gm.factories import GMTableMembershipFactory, TableUpdateRequestFactory
from world.progression.models.rewards import ExperiencePointsData
from world.scenes.factories import PersonaFactory


class _HandlerSetup:
    """Build a membership whose character has a funded account."""

    def _funded(self, *, earned: int):
        sheet = CharacterSheetFactory()
        account = AccountFactory()
        sheet.character.account = account
        sheet.character.save()
        ExperiencePointsData.objects.get_or_create(
            account=account, defaults={"total_earned": earned, "total_spent": 0}
        )
        membership = GMTableMembershipFactory(persona=PersonaFactory(character_sheet=sheet))
        return sheet, account, membership

    def _request(self, membership, distinction, *, kind, rank=1):
        req = TableUpdateRequestFactory(membership=membership, kind=kind)
        DistinctionChangeRequestFactory(request=req, distinction=distinction, rank=rank)
        return req


class CompleteAddTests(TestCase, _HandlerSetup):
    def test_add_charges_xp_and_grants(self) -> None:
        sheet, account, membership = self._funded(earned=100)
        distinction = DistinctionFactory(cost_per_rank=4)  # positive -> costs 3*4*1 = 12
        req = self._request(membership, distinction, kind=TableRequestKind.DISTINCTION_ADD)

        complete_distinction_add(req)

        assert CharacterDistinction.objects.filter(character=sheet, distinction=distinction).exists()
        tracker = ExperiencePointsData.objects.get(account=account)
        assert tracker.total_spent == 12

    def test_add_negative_is_free(self) -> None:
        sheet, account, membership = self._funded(earned=0)
        distinction = DistinctionFactory(cost_per_rank=-2)  # gaining a drawback -> free
        req = self._request(membership, distinction, kind=TableRequestKind.DISTINCTION_ADD)

        complete_distinction_add(req)

        assert CharacterDistinction.objects.filter(character=sheet, distinction=distinction).exists()
        assert ExperiencePointsData.objects.get(account=account).total_spent == 0

    def test_add_refused_when_unaffordable(self) -> None:
        sheet, _account, membership = self._funded(earned=5)
        distinction = DistinctionFactory(cost_per_rank=4)  # needs 12, has 5
        req = self._request(membership, distinction, kind=TableRequestKind.DISTINCTION_ADD)

        with self.assertRaises(XPInsufficient):
            complete_distinction_add(req)
        assert not CharacterDistinction.objects.filter(
            character=sheet, distinction=distinction
        ).exists()


class CompleteRemoveTests(TestCase, _HandlerSetup):
    def test_remove_negative_charges_and_revokes(self) -> None:
        sheet, account, membership = self._funded(earned=200)
        distinction = DistinctionFactory(cost_per_rank=-50)  # removing drawback -> 3*50 = 150
        grant_distinction(sheet, distinction, origin=DistinctionOrigin.GM_AWARD)
        req = self._request(membership, distinction, kind=TableRequestKind.DISTINCTION_REMOVE)

        complete_distinction_remove(req)

        assert not CharacterDistinction.objects.filter(
            character=sheet, distinction=distinction
        ).exists()
        assert ExperiencePointsData.objects.get(account=account).total_spent == 150

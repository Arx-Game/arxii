"""Table-request state-machine transitions (#2607)."""

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.factories import DistinctionFactory
from world.distinctions.models import CharacterDistinction
from world.distinctions.table_request_handlers import submit_distinction_request
from world.gm.constants import TableRequestStatus
from world.gm.factories import GMTableMembershipFactory
from world.gm.table_request_services import (
    TableRequestStateError,
    complete_request,
    signoff_request,
    withdraw_request,
)
from world.progression.models.rewards import ExperiencePointsData
from world.scenes.factories import PersonaFactory


class TableRequestServiceTests(TestCase):
    def _membership(self, *, earned: int = 0):
        sheet = CharacterSheetFactory()
        account = AccountFactory()
        sheet.character.account = account
        sheet.character.save()
        ExperiencePointsData.objects.get_or_create(
            account=account, defaults={"total_earned": earned, "total_spent": 0}
        )
        membership = GMTableMembershipFactory(persona=PersonaFactory(character_sheet=sheet))
        return membership, sheet

    def test_unsupported_submit_refused(self) -> None:
        membership, _ = self._membership()
        distinction = DistinctionFactory(post_cg_immutable=True)
        with self.assertRaises(TableRequestStateError):
            submit_distinction_request(
                membership=membership, distinction=distinction, removing=False, reasoning="x"
            )

    def test_remove_without_holding_refused(self) -> None:
        membership, _ = self._membership()
        distinction = DistinctionFactory(cost_per_rank=-2)
        with self.assertRaises(TableRequestStateError):
            submit_distinction_request(
                membership=membership, distinction=distinction, removing=True, reasoning="x"
            )

    def test_full_add_flow(self) -> None:
        membership, sheet = self._membership(earned=100)
        distinction = DistinctionFactory(cost_per_rank=4)  # costs 12
        req = submit_distinction_request(
            membership=membership, distinction=distinction, removing=False, reasoning="mentor"
        )
        assert req.status == TableRequestStatus.PENDING
        assert req.distinction_change_details.xp_cost == 12

        req = signoff_request(req, approve=True)
        assert req.status == TableRequestStatus.APPROVED

        req = complete_request(req)
        assert req.status == TableRequestStatus.COMPLETED
        assert CharacterDistinction.objects.filter(
            character=sheet, distinction=distinction
        ).exists()

    def test_reject_is_terminal(self) -> None:
        membership, _ = self._membership()
        distinction = DistinctionFactory(cost_per_rank=-2)
        req = submit_distinction_request(
            membership=membership, distinction=distinction, removing=False, reasoning="x"
        )
        req = signoff_request(req, approve=False, gm_notes="not this season")
        assert req.status == TableRequestStatus.REJECTED
        with self.assertRaises(TableRequestStateError):
            complete_request(req)

    def test_withdraw_only_while_pending(self) -> None:
        membership, _ = self._membership()
        distinction = DistinctionFactory(cost_per_rank=-2)
        req = submit_distinction_request(
            membership=membership, distinction=distinction, removing=False, reasoning="x"
        )
        req = withdraw_request(req)
        assert req.status == TableRequestStatus.WITHDRAWN
        with self.assertRaises(TableRequestStateError):
            withdraw_request(req)

    def test_complete_refused_when_unaffordable_stays_approved(self) -> None:
        membership, sheet = self._membership(earned=3)
        distinction = DistinctionFactory(cost_per_rank=4)  # needs 12, has 3
        req = submit_distinction_request(
            membership=membership, distinction=distinction, removing=False, reasoning="x"
        )
        req = signoff_request(req, approve=True)
        from world.distinctions.table_request_handlers import XPInsufficient

        with self.assertRaises(XPInsufficient):
            complete_request(req)
        req.refresh_from_db()
        assert req.status == TableRequestStatus.APPROVED
        assert not CharacterDistinction.objects.filter(
            character=sheet, distinction=distinction
        ).exists()

"""TableUpdateRequest + DistinctionChangeDetails models (#2607)."""

from django.test import TestCase

from world.distinctions.factories import DistinctionChangeRequestFactory
from world.gm.constants import TableRequestKind, TableRequestStatus
from world.gm.factories import TableUpdateRequestFactory


class TableUpdateRequestModelTests(TestCase):
    def test_defaults_pending(self) -> None:
        req = TableUpdateRequestFactory()
        assert req.status == TableRequestStatus.PENDING
        assert req.membership_id is not None

    def test_distinction_details_link(self) -> None:
        details = DistinctionChangeRequestFactory()
        assert details.request.kind == TableRequestKind.DISTINCTION_ADD
        assert details.request.distinction_change_details == details

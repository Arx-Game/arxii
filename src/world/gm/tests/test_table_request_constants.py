"""Enums for the table sheet-update request framework (#2607)."""

from django.test import SimpleTestCase

from world.gm.constants import TableRequestKind, TableRequestStatus
from world.progression.types import ProgressionReason


class TableRequestEnumTests(SimpleTestCase):
    def test_kinds(self) -> None:
        assert TableRequestKind.DISTINCTION_ADD.value == "distinction_add"
        assert TableRequestKind.DISTINCTION_REMOVE.value == "distinction_remove"

    def test_statuses(self) -> None:
        assert {s.value for s in TableRequestStatus} == {
            "pending",
            "approved",
            "rejected",
            "completed",
            "withdrawn",
        }

    def test_progression_reason(self) -> None:
        assert ProgressionReason.TABLE_REQUEST.value == "table_request"
        assert len(ProgressionReason.TABLE_REQUEST.value) <= 20

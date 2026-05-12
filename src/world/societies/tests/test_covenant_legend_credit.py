"""Tests for CovenantLegendCredit model."""

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.covenants.factories import CovenantFactory
from world.societies.factories import CovenantLegendCreditFactory, LegendEntryFactory


class CovenantLegendCreditModelTests(TestCase):
    def test_unique_entry_covenant(self) -> None:
        entry = LegendEntryFactory()
        covenant = CovenantFactory()
        CovenantLegendCreditFactory(entry=entry, covenant=covenant)
        from world.societies.models import CovenantLegendCredit

        with self.assertRaises(IntegrityError), transaction.atomic():
            CovenantLegendCredit.objects.create(entry=entry, covenant=covenant)

    def test_cascade_on_entry_delete(self) -> None:
        entry = LegendEntryFactory()
        covenant = CovenantFactory()
        credit = CovenantLegendCreditFactory(entry=entry, covenant=covenant)
        entry.delete()
        from world.societies.models import CovenantLegendCredit

        self.assertFalse(CovenantLegendCredit.objects.filter(pk=credit.pk).exists())

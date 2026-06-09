from __future__ import annotations

from django.test import TestCase

from world.magic.constants import LedgerOp, PowerStage
from world.scenes.constants import InteractionMode
from world.scenes.factories import InteractionFactory
from world.scenes.models import InteractionPowerLedgerEntry


class InteractionPowerLedgerEntryModelTests(TestCase):
    def test_entries_round_trip_in_order(self) -> None:
        interaction = InteractionFactory(mode=InteractionMode.ACTION)
        InteractionPowerLedgerEntry.objects.create(
            interaction=interaction,
            ordering=1,
            stage=PowerStage.ENVIRONMENT,
            source_label="resonance environment",
            op=LedgerOp.ADD,
            amount=7,
            running_total=12,
        )
        InteractionPowerLedgerEntry.objects.create(
            interaction=interaction,
            ordering=0,
            stage=PowerStage.BASE,
            source_label="channeled intensity",
            op=LedgerOp.SET,
            amount=5,
            running_total=5,
        )
        rows = list(interaction.power_ledger_entries.all())
        assert [r.ordering for r in rows] == [0, 1]
        assert rows[0].stage == PowerStage.BASE
        assert rows[1].running_total == 12

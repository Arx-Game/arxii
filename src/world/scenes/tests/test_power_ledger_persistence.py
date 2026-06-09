from __future__ import annotations

from django.test import TestCase

from world.magic.constants import LedgerOp, PowerStage
from world.magic.types.power_ledger import PowerLedgerBuilder
from world.scenes.constants import InteractionMode
from world.scenes.factories import InteractionFactory
from world.scenes.models import InteractionPowerLedgerEntry
from world.scenes.power_ledger_services import load_persisted_ledger, persist_power_ledger


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


class PersistAndLoadLedgerTests(TestCase):
    def _ledger(self):
        return (
            PowerLedgerBuilder(base=5)
            .add(PowerStage.ENVIRONMENT, "resonance environment", 7)
            .build()
        )

    def test_persist_then_load_round_trips(self) -> None:
        interaction = InteractionFactory(mode=InteractionMode.ACTION)
        persist_power_ledger(interaction=interaction, ledger=self._ledger())
        loaded = load_persisted_ledger(interaction.pk)
        assert loaded is not None
        assert loaded.total == 12
        assert [e.stage for e in loaded.entries] == [PowerStage.BASE, PowerStage.ENVIRONMENT]
        assert loaded.entries[1].amount == 7

    def test_persist_empty_is_noop(self) -> None:
        interaction = InteractionFactory(mode=InteractionMode.ACTION)
        persist_power_ledger(interaction=interaction, ledger=None)
        assert load_persisted_ledger(interaction.pk) is None

"""Tests for the transient power-derivation ledger types and builder."""

from django.test import SimpleTestCase

from world.magic.constants import LedgerOp, PowerStage
from world.magic.types.power_ledger import PowerLedgerBuilder


class PowerLedgerBuilderTests(SimpleTestCase):
    def test_add_multiply_set_clamp(self):
        b = PowerLedgerBuilder(base=100, base_label="channeled")
        b.add(PowerStage.FLAT_MODIFIER, "fire buff", 20)  # 120
        b.multiply(PowerStage.MULTIPLIER, "Audere", 50)  # round(120 * 1.5) = 180
        b.add(PowerStage.ENVIRONMENT, "resonant node", 10)  # 190
        b.set_value(PowerStage.PENETRATION, "ward", 0)  # bounced -> 0
        ledger = b.clamp_floor().build()
        self.assertEqual(ledger.total, 0)
        self.assertEqual(ledger.entries[0].stage, PowerStage.BASE)
        self.assertEqual(ledger.entries[0].running_total, 100)
        self.assertEqual(ledger.entries[2].running_total, 180)
        self.assertEqual(ledger.entries[-1].op, LedgerOp.SET)

    def test_no_floor_needed(self):
        b = PowerLedgerBuilder(base=50, base_label="channeled")
        b.add(PowerStage.FLAT_MODIFIER, "buff", 5)
        self.assertEqual(b.clamp_floor().build().total, 55)

    def test_skips_zero_amounts(self):
        b = PowerLedgerBuilder(base=100, base_label="channeled")
        b.add(PowerStage.FLAT_MODIFIER, "noop", 0)
        b.multiply(PowerStage.MULTIPLIER, "noop", 0)
        ledger = b.build()
        self.assertEqual(len(ledger.entries), 1)  # only BASE
        self.assertEqual(ledger.total, 100)

    def test_from_ledger_continues_accumulation(self):
        base_ledger = (
            PowerLedgerBuilder(base=100, base_label="channeled")
            .add(PowerStage.FLAT_MODIFIER, "buff", 20)
            .build()
        )
        extended = (
            PowerLedgerBuilder.from_ledger(base_ledger)
            .add(PowerStage.COMBAT_PULL, "pull", 30)
            .build()
        )
        self.assertEqual(extended.total, 150)
        self.assertEqual(len(extended.entries), 3)
        self.assertEqual(extended.entries[-1].running_total, 150)

"""Transient power-derivation ledger. NEVER persisted — recomputed each cast."""

from __future__ import annotations

from dataclasses import dataclass

from world.magic.constants import LedgerOp, PowerStage


@dataclass(frozen=True)
class PowerLedgerEntry:
    stage: PowerStage
    source_label: str
    op: LedgerOp
    amount: int  # signed delta (add) | whole percent (multiply) | target value (set)
    running_total: int


@dataclass(frozen=True)
class PowerLedger:
    entries: tuple[PowerLedgerEntry, ...]
    total: int  # == entries[-1].running_total when non-empty, floored at 0


class PowerLedgerBuilder:
    """Accumulates ledger entries, tracking the running total. Mutable; build() freezes."""

    def __init__(self, *, base: int, base_label: str = "channeled intensity") -> None:
        self._total = base
        self._entries: list[PowerLedgerEntry] = [
            PowerLedgerEntry(PowerStage.BASE, base_label, LedgerOp.SET, base, base)
        ]

    @classmethod
    def from_ledger(cls, ledger: PowerLedger) -> PowerLedgerBuilder:
        b = cls.__new__(cls)
        b._total = ledger.total  # noqa: SLF001
        b._entries = list(ledger.entries)  # noqa: SLF001
        return b

    def add(self, stage: str, source_label: str, amount: int) -> PowerLedgerBuilder:
        if amount == 0:
            return self
        self._total += amount
        self._entries.append(
            PowerLedgerEntry(stage, source_label, LedgerOp.ADD, amount, self._total)
        )
        return self

    def multiply(self, stage: str, source_label: str, percent: int) -> PowerLedgerBuilder:
        if percent == 0:
            return self
        self._total = round(self._total * (100 + percent) / 100)
        self._entries.append(
            PowerLedgerEntry(stage, source_label, LedgerOp.MULTIPLY, percent, self._total)
        )
        return self

    def set_value(self, stage: str, source_label: str, value: int) -> PowerLedgerBuilder:
        self._total = value
        self._entries.append(
            PowerLedgerEntry(stage, source_label, LedgerOp.SET, value, self._total)
        )
        return self

    def _apply_floor(self) -> None:
        if self._total < 0:
            self._total = 0
            self._entries.append(PowerLedgerEntry(PowerStage.CLAMP, "floor", LedgerOp.SET, 0, 0))

    def clamp_floor(self) -> PowerLedgerBuilder:
        self._apply_floor()
        return self

    def build(self) -> PowerLedger:
        self._apply_floor()
        return PowerLedger(entries=tuple(self._entries), total=self._total)

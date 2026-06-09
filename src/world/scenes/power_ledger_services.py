"""Persist + reload the per-cast power ledger off an ACTION Interaction."""

from __future__ import annotations

from world.magic.types.power_ledger import PowerLedger, PowerLedgerEntry
from world.scenes.models import Interaction, InteractionPowerLedgerEntry


def persist_power_ledger(*, interaction: Interaction, ledger: PowerLedger | None) -> None:
    """Copy a transient PowerLedger's entries onto the interaction. No-op when empty."""
    if ledger is None or not ledger.entries:
        return
    InteractionPowerLedgerEntry.objects.bulk_create(
        [
            InteractionPowerLedgerEntry(
                interaction=interaction,
                ordering=i,
                stage=entry.stage,
                source_label=entry.source_label,
                op=entry.op,
                amount=entry.amount,
                running_total=entry.running_total,
            )
            for i, entry in enumerate(ledger.entries)
        ]
    )


def load_persisted_ledger(interaction_id: int) -> PowerLedger | None:
    """Rebuild a PowerLedger dataclass from persisted rows, or None when none exist."""
    rows = list(
        InteractionPowerLedgerEntry.objects.filter(interaction_id=interaction_id).order_by(
            "ordering"
        )
    )
    if not rows:
        return None
    entries = tuple(
        PowerLedgerEntry(
            stage=row.stage,
            source_label=row.source_label,
            op=row.op,
            amount=row.amount,
            running_total=row.running_total,
        )
        for row in rows
    )
    return PowerLedger(entries=entries, total=entries[-1].running_total)

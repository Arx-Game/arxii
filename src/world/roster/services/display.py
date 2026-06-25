"""Per-character display-settings services (#1463).

Writes to ``TenureDisplaySettings`` — the per-tenure UI/visibility preferences. Account/roster
management uses plain Django patterns, not flows (see roster/CLAUDE.md). Quiet/hidden mode
(``appear_offline``) is read through ``world.scenes.presence.character_appears_offline``; this
module owns the write side.
"""

from __future__ import annotations

from world.roster.models import RosterTenure, TenureDisplaySettings


def set_appear_offline(*, tenure: RosterTenure, value: bool) -> bool:
    """Set quiet/hidden mode (``appear_offline``) for a tenure; return the stored value.

    Get-or-creates the tenure's settings row, so a character that has never touched its
    display settings can still go quiet. Persistent — survives logout (#1463).
    """
    settings, _ = TenureDisplaySettings.objects.get_or_create(tenure=tenure)
    if settings.appear_offline != value:
        settings.appear_offline = value
        settings.save(update_fields=["appear_offline", "updated_date"])
    return value

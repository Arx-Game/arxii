"""Sanctum state queries — public dormancy helper (#671).

UI / API callers that don't already have the threads-list pre-loaded should
call ``sanctum_is_dormant`` instead of touching the cron's private helper.
The cron path uses its already-loaded ``threads`` list to avoid extra
queries; this helper fetches threads itself for one-off lookups.
"""

from __future__ import annotations

from world.magic.constants import TargetKind
from world.magic.models import SanctumDetails, SanctumOwnerMode, Thread


def sanctum_is_dormant(sanctum: SanctumDetails) -> bool:
    """Return True when the Sanctum is Dormant (no resonance generation).

    PERSONAL: dormant when ``founder_character_sheet`` is set AND that founder
    is dormant. Null founder (pre-Sanctification rows, historical seed data,
    test fixtures) is treated as "no gate" — production Sanctums always
    carry a founder.
    COVENANT: dormant when ALL current Sanctum-threaded weavers are dormant,
    OR when there are no current threaders at all (no one to generate for).

    Single query for the COVENANT path (load active threads with owners).
    PERSONAL path is one CharacterSheet read via the FK chain.
    """
    if sanctum.owner_mode == SanctumOwnerMode.PERSONAL:
        founder = sanctum.founder_character_sheet
        return founder is not None and founder.is_dormant

    threads = list(
        Thread.objects.select_related("owner").filter(
            target_sanctum_details=sanctum,
            target_kind=TargetKind.SANCTUM,
            retired_at__isnull=True,
        )
    )
    if not threads:
        return True
    return all(t.owner.is_dormant for t in threads)

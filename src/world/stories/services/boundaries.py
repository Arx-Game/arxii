"""Player-boundary screening seam for stakes contracts (#1770 pillar 10).

The seam runs at authoring time (``StakeSerializer``) and at every
activation/commit call site (combat encounter creation, mission issue, the
``declare_stakes`` GM action), so it exists from day one even though the
screening itself is an allow-all stub. The real implementation — a
per-player boundary registry (tracked on the boundaries sibling issue of
#1770, #1771) — will follow the shape of the consent app
(``world.consent.services``, ADR-0024): explicit per-player preference rows
consulted by free service functions, no signals.

Call sites gate on ``StakeBoundaryReport.cleared`` (allowed AND no pending
sign-off), so #1771 can start returning ``requires_signoff`` without
revisiting any call site.

Privacy invariant (ADR-0033): a blocked report's ``blocked_reason_private``
is for staff/audit logging only. It is NEVER shown to the GM or other
players — a boundary is private; callers surface only a generic
"stakes could not be presented" failure.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.stories.types import StakeBoundaryReport

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from world.character_sheets.models import CharacterSheet
    from world.stories.models import Stake


def check_stake_boundaries(
    stakes: Iterable[Stake],
    character_sheets: Sequence[CharacterSheet],
) -> StakeBoundaryReport:
    """Screen a contract's stakes against the participants' boundaries.

    Accepts the whole contract's stakes in one call so call sites screen a
    beat's contract with a single invocation. ``character_sheets`` is the
    party the contract would activate for; at authoring time (StakeSerializer)
    the players are not yet known and callers pass an empty sequence.

    Allow-all stub: always returns ``allowed=True`` with no sign-off
    requirements. The boundary registry (#1771) replaces the body; the
    signature and the ``StakeBoundaryReport`` contract stay.
    """
    # Consume the arguments so the seam's contract is exercised (and the
    # stub stays honest about what the real implementation will inspect).
    _ = list(stakes), list(character_sheets)
    return StakeBoundaryReport(allowed=True)

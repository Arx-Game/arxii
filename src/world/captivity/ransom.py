"""Ransom amount defaults (#931, #1500).

The captor's default demand is ~1 year of the captive's income, but until
professions/income ledgers exist that figure isn't computable, so it falls to a
flat floor (a GM may always override at demand time). The ransom *loop* itself is
the crowdfundable RANSOM Project — see ``world.captivity.ransom_project``; the old
org-treasury Contract path was retired in #1500 in favour of that single route.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet

# 1000g floor (1g = 100c), used until incomes are computable. GM may override.
_RANSOM_FLOOR_COPPERS = 100_000


def default_ransom_amount(captive: CharacterSheet) -> int:  # noqa: ARG001
    """The captor's default demand: ~1 year of the captive's income.

    PLACEHOLDER seam (#931): until the income ledger (professions/businesses)
    exists there is nothing to read, so every captive defaults to the flat
    floor. When it lands, compute ~1 year of the captive's income here (with
    the family-org income as a secondary fallback) and keep the floor as the
    final fallback. A GM may always override the amount at demand time.
    """
    # TODO(#931): read the income ledger here once professions/businesses ship.
    return _RANSOM_FLOOR_COPPERS

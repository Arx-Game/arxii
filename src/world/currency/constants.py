"""Currency constants (#925 — economy umbrella #923).

One integer base unit: the **copper**. All storage, math, and APIs deal in
coppers; display always shows the canonical mixed form ("3g 4s 7c") — the
system translates, players never do arithmetic.

The named coins above gold are *physical instruments* (items), not account
units — see ``world.currency.models.CurrencyInstrumentDetails``.
"""

from decimal import Decimal

from django.db import models

COPPERS_PER_SILVER = 10
COPPERS_PER_GOLD = 100


class Denomination(models.TextChoices):
    """The minted instrument coins (each ×10 the last, in gold)."""

    GOLD_KNIGHT = "gold_knight", "Gold Knight"
    BARONESS = "baroness", "Baroness"
    COUNTESS = "countess", "Countess"
    DUCHESS = "duchess", "Duchess"
    QUEEN = "queen", "Queen"
    EMPRESS = "empress", "Empress"


# Face value of each instrument, in coppers.
DENOMINATION_VALUES: dict[str, int] = {
    Denomination.GOLD_KNIGHT.value: 10 * COPPERS_PER_GOLD,
    Denomination.BARONESS.value: 100 * COPPERS_PER_GOLD,
    Denomination.COUNTESS.value: 1_000 * COPPERS_PER_GOLD,
    Denomination.DUCHESS.value: 10_000 * COPPERS_PER_GOLD,
    Denomination.QUEEN.value: 100_000 * COPPERS_PER_GOLD,
    Denomination.EMPRESS.value: 1_000_000 * COPPERS_PER_GOLD,
}

# Bank fee charged on top of face value when minting an instrument
# (a deliberate sink, #923). Redemption is fee-free.
MINT_FEE_PCT = Decimal("0.01")


def format_coppers(amount: int) -> str:
    """Canonical mixed display: ``1234`` → ``"12g 3s 4c"``.

    Zero components are omitted except the all-zero case (``"0c"``).
    Negative amounts (ledger deltas) keep a single leading sign.
    """
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    gold, rem = divmod(amount, COPPERS_PER_GOLD)
    silver, copper = divmod(rem, COPPERS_PER_SILVER)
    parts = []
    if gold:
        parts.append(f"{gold}g")
    if silver:
        parts.append(f"{silver}s")
    if copper:
        parts.append(f"{copper}c")
    if not parts:
        return "0c"  # noqa: STRING_LITERAL - display literal, not an identifier
    return sign + " ".join(parts)


class IncomeStreamKind(models.TextChoices):
    """Flavors of org income — one machinery, two fictions (#926)."""

    DOMAIN_TAX = "domain_tax", "Domain Tax"
    CRIME_KICKUP = "crime_kickup", "Crime Kick-up"


# Graft never reaches zero — some leak always survives (#923 doctrine).
GRAFT_FLOOR_PCT = 1
GRAFT_DEFAULT_PCT = 10
GRAFT_MAX_PCT = 75


class ContractFormality(models.TextChoices):
    """Enforcement tiers (#928): notarized contracts settle; handshakes are RP."""

    HANDSHAKE = "handshake", "Handshake"
    NOTARIZED = "notarized", "Notarized"


class ContractStatus(models.TextChoices):
    """Lifecycle of a contract (#928)."""

    PROPOSED = "proposed", "Proposed"
    ACTIVE = "active", "Active"
    COMPLETED = "completed", "Completed"
    DEFAULTED = "defaulted", "Defaulted"
    CANCELLED = "cancelled", "Cancelled"


# Notarization fee (the formality sink), in coppers. Content-tunable later.
NOTARY_FEE_COPPERS = 1_000

# A notarized obligation defaults after this many consecutive missed cycles.
CONTRACT_DEFAULT_AFTER_MISSES = 2

"""Currency constants (#925 — economy umbrella #923).

One integer base unit: the **copper**. All storage, math, and APIs deal in
coppers; display always shows the canonical mixed form ("3g 4s 7c") — the
system translates, players never do arithmetic.

The named coins above gold are *physical instruments* (items), not account
units — see ``world.currency.models.CurrencyInstrumentDetails``.
"""

from decimal import Decimal
import re

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
    LOOSE = "loose", "Loose Coins"


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


_COIN_TOKEN = re.compile(r"^(\d+)\s*(g|s|c)$", re.IGNORECASE)

_UNIT_COPPERS = {"g": COPPERS_PER_GOLD, "s": COPPERS_PER_SILVER, "c": 1}


def parse_coppers(text: str) -> int | None:
    """Parse "1g 2s 3c"-style amounts to coppers; None when it isn't money.

    Tokens may appear in any order, case-insensitively, but each unit
    (g/s/c) may only appear once. Rejects item-ish text (no unit match),
    negative amounts (the regex has no sign), and an all-zero total.
    """
    tokens = text.strip().split()
    if not tokens:
        return None
    total = 0
    seen: set[str] = set()
    for token in tokens:
        match = _COIN_TOKEN.match(token)
        if match is None:
            return None
        unit = match.group(2).lower()
        if unit in seen:
            return None
        seen.add(unit)
        total += int(match.group(1)) * _UNIT_COPPERS[unit]
    return total if total > 0 else None


class IncomeStreamKind(models.TextChoices):
    """Flavors of org income — one machinery, two fictions (#926)."""

    DOMAIN_TAX = "domain_tax", "Domain Tax"
    CRIME_KICKUP = "crime_kickup", "Crime Kick-up"


# Graft never reaches zero — some leak always survives (#923 doctrine).
GRAFT_FLOOR_PCT = 1
GRAFT_DEFAULT_PCT = 10
GRAFT_MAX_PCT = 75


# ---------------------------------------------------------------------------
# #930 — active income collection. All magnitudes PLACEHOLDER (tuning pass);
# band weights are data here, never documented player-facing.
# ---------------------------------------------------------------------------

TAX_COLLECTION_CHECK_NAME = "Tax Collection"
DOMAIN_INVESTMENT_CHECK_NAME = "Domain Investment"

# Collection outcome bands: minimum success_level → percent of the gathered
# pool that arrives (before graft). Descending; first floor <= level wins.
# Below the last floor is catastrophe: nothing lands, the pool is gone (the
# collector-incident encounter seam — combat domain follow-up).
COLLECTION_BAND_PCTS: tuple[tuple[int, int], ...] = (
    (2, 110),  # critical — goodwill bonus over the gathered aggregate
    (1, 100),  # clean collection
    (0, 85),  # skimmed — some of the money stolen en route
    (-1, 35),  # waylaid — most of the money stolen
)

# Domain-improvement effects (PLACEHOLDER): a success raises every active
# stream's gross by this percent AND cracks down on graft by this step;
# a partial success only manages the graft crackdown.
IMPROVEMENT_GROSS_PCT = 5
IMPROVEMENT_GRAFT_STEP = 1


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


# Profession chore checks (#929): success_level → wage multiplier (×100 to
# stay integer; 150 = 1.5×). Up to ~2× the automated rate per the spec.
CHORE_MULTIPLIER_FAIL = 100
CHORE_MULTIPLIER_SUCCESS = 150
CHORE_MULTIPLIER_CRIT = 200

# Businesses (#929): invested coppers per level step, and the per-level
# weekly base yield. Variance can push a week negative by design.
BUSINESS_INVESTMENT_PER_LEVEL = 50_000
BUSINESS_BASE_WEEKLY_PER_LEVEL = 200


# Weekly business fortune range (#932): the percentage swing run_business_week
# receives at rollover. Skewed positive but genuinely negative-capable —
# a bad week loses real money by design. Calibration starting points.
BUSINESS_FORTUNE_MIN = -40
BUSINESS_FORTUNE_MAX = 60

# Wages pay only for actively-played weeks (#929/#932): a login within this
# many days of the rollover counts as active.
ACTIVE_WEEK_LOGIN_DAYS = 8

# House allowance (#2540): the non-discretionary share of a collection's surplus that
# auto-splits among active piloted members. PLACEHOLDER — magnitude is Apostate's tuning call.
ALLOWANCE_SURPLUS_PCT = 50

# Distribution dispatch (#2540, ruled 2026-07-20): debt principal services FIRST as a
# flat share of the collection's gross — a mandatory allowance to the creditor — before
# the member allowance draws from the post-debt remainder. Complements (does not
# replace) the weekly at-source ARREARS withholding (#927): arrears = interest, this =
# principal. PLACEHOLDER — magnitude is Apostate's tuning call.
DEBT_PRINCIPAL_GROSS_PCT = 13

"""Estate constants (#1985).

``INTESTATE_KIN_ORDER`` documents the fixed next-of-kin walk (spec Decision 6b,
PLACEHOLDER order): wedlock spouse -> eldest child -> elder living parent ->
eldest sibling. The walk lives in ``services.resolve_intestate_heir``; this
constant exists so the order is greppable and staff-documented in one place.
"""

from django.db import models


class BequestKind(models.TextChoices):
    """What a single bequest line moves at settlement."""

    SPECIFIC_ITEM = "specific_item", "Specific Item"
    COIN_AMOUNT = "coin_amount", "Coin Amount"
    ALL_COIN = "all_coin", "All Remaining Coin"
    BUILDING = "building", "Building"
    BUSINESS = "business", "Business"
    RESIDUARY = "residuary", "Residuary (everything else)"


class SettlementStatus(models.TextChoices):
    """Lifecycle of an estate settlement window."""

    PENDING = "pending", "Pending"
    SETTLED = "settled", "Settled"
    PARKED = "parked", "Parked (staff attention)"


class SettlementDoor(models.TextChoices):
    """Which door executed the settlement (spec Decision 2)."""

    FUNERAL = "funeral", "Funeral"
    READING = "reading", "Will Reading"
    AUTO = "auto", "Deadline Sweeper"


INTESTATE_KIN_ORDER = ("wedlock_spouse", "eldest_child", "elder_parent", "eldest_sibling")

"""
Service functions for kudos operations.

These functions handle atomic transactions for kudos awards and claims,
ensuring that balance updates and audit trail creation happen together.
"""

from django.db import transaction
from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB

from world.progression.models import (
    KudosClaimCategory,
    KudosPointsData,
    KudosSourceCategory,
    KudosTransaction,
)
from world.progression.types import AwardResult, ClaimResult, KudosXPResult, ProgressionReason


class InsufficientKudosError(Exception):
    """Raised when an account doesn't have enough kudos for a claim."""


@transaction.atomic
def award_kudos(  # noqa: PLR0913
    account: AccountDB,
    amount: int,
    source_category: KudosSourceCategory,
    description: str,
    awarded_by: AccountDB | None = None,
    character: ObjectDB | None = None,
) -> AwardResult:
    """
    Award kudos to an account with full audit trail.

    This function atomically:
    1. Gets or creates the account's KudosPointsData
    2. Increments total_earned
    3. Creates a KudosTransaction record

    Args:
        account: The account receiving kudos.
        amount: Positive integer of kudos to award.
        source_category: The category explaining why kudos was awarded.
        description: Human-readable description for the transaction feed.
        awarded_by: Optional account that awarded this kudos (for player votes).
        character: Optional character involved (for death bonuses, etc.).

    Returns:
        AwardResult with the updated points data and created transaction.

    Raises:
        ValueError: If amount is not positive.
    """
    if amount <= 0:
        msg = "Award amount must be positive"
        raise ValueError(msg)

    points_data, _ = KudosPointsData.objects.get_or_create(account=account)
    points_data.total_earned += amount
    points_data.save()

    kudos_transaction = KudosTransaction.objects.create(
        account=account,
        amount=amount,
        source_category=source_category,
        description=description,
        awarded_by=awarded_by,
        character=character,
    )

    return AwardResult(points_data=points_data, transaction=kudos_transaction)


@transaction.atomic
def claim_kudos(
    account: AccountDB,
    amount: int,
    claim_category: KudosClaimCategory,
    description: str,
) -> ClaimResult:
    """
    Claim kudos from an account for conversion to rewards.

    This function atomically:
    1. Gets the account's KudosPointsData
    2. Validates sufficient balance
    3. Increments total_claimed
    4. Creates a KudosTransaction record (with negative amount)
    5. Calculates the reward amount

    Args:
        account: The account claiming kudos.
        amount: Positive integer of kudos to claim.
        claim_category: The category defining what the kudos converts to.
        description: Human-readable description for the transaction feed.

    Returns:
        ClaimResult with updated points data, transaction, and calculated reward.

    Raises:
        ValueError: If amount is not positive.
        InsufficientKudosError: If account doesn't have enough kudos.
    """
    if amount <= 0:
        msg = "Claim amount must be positive"
        raise ValueError(msg)

    points_data, _ = KudosPointsData.objects.get_or_create(account=account)

    if not points_data.can_claim(amount):
        msg = f"Insufficient kudos: have {points_data.current_available}, need {amount}"
        raise InsufficientKudosError(msg)

    points_data.total_claimed += amount
    points_data.save()

    kudos_transaction = KudosTransaction.objects.create(
        account=account,
        amount=-amount,  # Negative for claims
        claim_category=claim_category,
        description=description,
    )

    reward_amount = claim_category.calculate_reward(amount)

    return ClaimResult(
        points_data=points_data,
        transaction=kudos_transaction,
        reward_amount=reward_amount,
    )


@transaction.atomic
def claim_kudos_for_xp(
    account: AccountDB,
    amount: int,
    claim_category: KudosClaimCategory,
    description: str = "",
) -> KudosXPResult:
    """
    Claim kudos and convert the reward to account-level XP.

    Orchestrates claim_kudos → award_xp in a single atomic transaction.

    Args:
        account: The account claiming kudos.
        amount: Positive integer of kudos to claim.
        claim_category: The claim category defining the conversion rate.
        description: Optional description (auto-generated if empty).

    Returns:
        KudosXPResult with the claim result, XP transaction, and XP awarded.

    Raises:
        ValueError: If amount is not positive or reward calculates to zero.
        InsufficientKudosError: If account doesn't have enough kudos.
    """
    from world.progression.services.awards import award_xp

    claim_result = claim_kudos(
        account=account,
        amount=amount,
        claim_category=claim_category,
        description=description or f"Claimed {amount} kudos for XP",
    )

    if claim_result.reward_amount <= 0:
        msg = f"Kudos amount {amount} is not enough for any XP with this conversion rate"
        raise ValueError(msg)

    xp_transaction = award_xp(
        account=account,
        amount=claim_result.reward_amount,
        reason=ProgressionReason.KUDOS_CLAIM,
        description=f"Converted {amount} kudos to {claim_result.reward_amount} XP",
    )

    return KudosXPResult(
        claim_result=claim_result,
        xp_transaction=xp_transaction,
        xp_awarded=claim_result.reward_amount,
    )

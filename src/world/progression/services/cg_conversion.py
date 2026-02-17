"""Service functions for CG-to-XP conversion."""

from world.progression.models import CharacterXP, CharacterXPTransaction
from world.progression.types import ProgressionReason


def award_cg_conversion_xp(character, *, remaining_cg_points: int, conversion_rate: int) -> None:
    """
    Award locked XP to a character for unspent CG points.

    Args:
        character: The character object to award XP to.
        remaining_cg_points: Number of unspent CG points.
        conversion_rate: XP per CG point (e.g., 2 means 2 XP per 1 CG point).
    """
    if remaining_cg_points <= 0:
        return

    xp_amount = remaining_cg_points * conversion_rate

    xp, _created = CharacterXP.objects.get_or_create(
        character=character,
        transferable=False,
        defaults={"total_earned": 0},
    )
    xp.award_xp(xp_amount)

    CharacterXPTransaction.objects.create(
        character=character,
        amount=xp_amount,
        reason=ProgressionReason.CG_CONVERSION,
        description=f"{remaining_cg_points} unspent CG points converted at {conversion_rate}:1",
        transferable=False,
    )

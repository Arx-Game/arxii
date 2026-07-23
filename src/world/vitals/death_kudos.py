"""Death-kudos: the capped graceful-death earning channel (#2287).

A new earning channel on the existing account-scoped kudos economy
(ADR-0115's "graciousness" axis — reuse, not a new currency). Witnesses of a
character's death honor how the player handled it:

- The death scene's GM and staff each grant ``max(20, 50%)`` of the
  character's lifetime XP spend; other scene participants ``max(1, 5%)``.
- Scaled grants are aggregate-capped at 100% of lifetime spend; past the cap
  givers land a deliberate trickle floor (1 per player, 20 per staff).
- Window: opens at death, closes when retire fires.
- Offscreen deaths (no death scene) are staff-only.

Kudos is account-scoped, so the honor carries to the player's next character
with no extra machinery. Lives in vitals (the death domain) and consumes
progression's primitives — FK/import direction per ADR-0010.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db.models import Sum

from world.vitals.services import is_dead, is_retired

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB

    from world.progression.models import KudosSourceCategory

DEATH_KUDOS_CATEGORY_NAME = "death"

# Tier shape: (floor, spend divisor) — scaled grant is max(floor, spend // divisor).
_STAFF_TIER = (20, 2)  # max(20, 50% of lifetime spend)
_PLAYER_TIER = (1, 20)  # max(1, 5% of lifetime spend)


class DeathKudosError(Exception):
    """Typed refusal with a player-safe message (never str(exc) of internals)."""

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


@dataclass
class DeathKudosResult:
    """Outcome of a death-kudos grant."""

    amount: int
    capped: bool
    message: str


def _lifetime_xp_spent(dead_character: ObjectDB) -> int:  # noqa: OBJECTDB_PARAM
    from world.progression.models import CharacterXP  # noqa: PLC0415

    total = CharacterXP.objects.filter(character_id=dead_character.pk).aggregate(
        total=Sum("total_spent")
    )["total"]
    return total or 0


def _giver_tier(
    giver_account: AccountDB,
    dead_character: ObjectDB,  # noqa: OBJECTDB_PARAM
) -> tuple[int, int]:
    """Return the giver's (floor, divisor) tier or raise DeathKudosError.

    Staff and the death scene's GM get the staff tier; other participants of
    the death scene the player tier. No death scene → staff only.
    """
    from world.scenes.models import SceneParticipation  # noqa: PLC0415

    if giver_account.is_staff:
        return _STAFF_TIER
    vitals = dead_character.sheet_data.vitals
    scene = vitals.died_in_scene
    if scene is None:
        msg = "That death happened offscreen; only staff may honor it."
        raise DeathKudosError(msg)
    participation = SceneParticipation.objects.filter(scene=scene, account=giver_account).first()
    if participation is None:
        msg = "Only those who shared the death scene may honor it."
        raise DeathKudosError(msg)
    if participation.is_gm:
        return _STAFF_TIER
    return _PLAYER_TIER


def _death_category() -> KudosSourceCategory:
    from world.progression.models import KudosSourceCategory  # noqa: PLC0415

    category = KudosSourceCategory.objects.filter(name=DEATH_KUDOS_CATEGORY_NAME).first()
    if category is None:
        msg = "Death kudos is not configured yet."
        raise DeathKudosError(msg)
    return category


def award_death_kudos(
    giver_account: AccountDB,
    dead_character: ObjectDB,  # noqa: OBJECTDB_PARAM
) -> DeathKudosResult:
    """Grant death-kudos to the dead character's player account.

    Raises DeathKudosError for: not dead, window closed (retired), no bound
    account, ineligible giver, double-give, or missing category seed.
    """
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    from world.progression.models import KudosTransaction  # noqa: PLC0415
    from world.progression.services.kudos import award_kudos  # noqa: PLC0415

    try:
        sheet = dead_character.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        sheet = None
    if sheet is None or not is_dead(sheet):
        msg = "Death kudos honors a death; that character is not dead."
        raise DeathKudosError(msg)
    if is_retired(sheet):
        msg = "That character has been laid to rest; the window has closed."
        raise DeathKudosError(msg)
    recipient_account = dead_character.db_account
    if recipient_account is None:
        msg = "That character has no player to receive the honor."
        raise DeathKudosError(msg)
    if recipient_account.pk == giver_account.pk:
        msg = "You cannot honor your own character's death."
        raise DeathKudosError(msg)

    category = _death_category()
    floor, divisor = _giver_tier(giver_account, dead_character)

    already_gave = KudosTransaction.objects.filter(
        awarded_by=giver_account,
        character=dead_character,
        source_category=category,
    ).exists()
    if already_gave:
        msg = "You have already honored this death."
        raise DeathKudosError(msg)

    lifetime_spent = _lifetime_xp_spent(dead_character)
    scaled = max(floor, lifetime_spent // divisor)
    prior_total = (
        KudosTransaction.objects.filter(
            character=dead_character, source_category=category
        ).aggregate(total=Sum("amount"))["total"]
        or 0
    )
    remaining = max(0, lifetime_spent - prior_total)
    amount = max(floor, min(scaled, remaining))
    capped = scaled > remaining

    award_kudos(
        recipient_account,
        amount,
        category,
        f"Honoring the death of {dead_character.key}",
        awarded_by=giver_account,
        character=dead_character,
    )
    return DeathKudosResult(
        amount=amount,
        capped=capped,
        message=f"You honor {dead_character.key}'s death with {amount} kudos.",
    )

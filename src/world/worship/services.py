"""Worship service functions (#2355).

The single write paths for worship: ceremonies (#2289) and future worship acts
call ``grant_worship`` (being pool + ledger) and ``bump_devotion`` (PC↔god
standing + the God's Favorite achievement check). Explicit calls, no signals.
"""

from typing import TYPE_CHECKING

from django.db.models import Max

from world.worship.constants import (
    GODS_FAVORITE_CHOSEN,
    GODS_FAVORITE_PRINCE,
    GODS_FAVORITE_PRINCESS,
)
from world.worship.models import DevotionStanding, WorshipGrant, WorshippedBeing

if TYPE_CHECKING:
    from world.achievements.models import Achievement
    from world.character_sheets.models import CharacterSheet


def grant_worship(
    being: WorshippedBeing,
    amount: int,
    *,
    granted_by: "CharacterSheet | None" = None,
    reason: str = "",
) -> WorshipGrant:
    """Add worship to a being's pool and record the audit ledger row."""
    if amount <= 0:
        msg = "Worship grants must be a positive amount."
        raise ValueError(msg)
    being.resonance_pool += amount
    being.lifetime_worship += amount
    being.save(update_fields=["resonance_pool", "lifetime_worship"])
    return WorshipGrant.objects.create(
        being=being, amount=amount, granted_by=granted_by, reason=reason
    )


def gods_favorite_achievement_for(character_sheet: "CharacterSheet") -> "Achievement | None":
    """Resolve the gender-matched God's Favorite achievement row (Decision 6).

    ``female`` → Princess, ``male`` → Prince, anything else (nonbinary keys,
    unspecified, or no gender row) → Chosen. Returns None when the achievement
    rows aren't seeded (bare test DB) — callers skip gracefully.
    """
    from world.achievements.models import Achievement  # noqa: PLC0415

    gender_key = character_sheet.gender.key if character_sheet.gender_id else ""
    name = {
        "female": GODS_FAVORITE_PRINCESS,
        "male": GODS_FAVORITE_PRINCE,
    }.get(gender_key, GODS_FAVORITE_CHOSEN)
    return Achievement.objects.filter(name=name, is_active=True).first()


def bump_devotion(
    character_sheet: "CharacterSheet", being: WorshippedBeing, amount: int
) -> DevotionStanding:
    """Upsert the (sheet, being) standing and run the God's Favorite check.

    Becoming — or tying — the top ``favor`` holder for the being grants the
    gender-matched achievement (leapfroggers earn it too; earlier holders keep
    theirs; ``grant_achievement`` is idempotent per sheet).
    """
    standing, _ = DevotionStanding.objects.get_or_create(
        character_sheet=character_sheet, being=being
    )
    standing.favor += amount
    standing.lifetime_favor += max(amount, 0)
    standing.save(update_fields=["favor", "lifetime_favor"])

    top_other = (
        (
            DevotionStanding.objects.filter(being=being)
            .exclude(pk=standing.pk)
            .aggregate(top=Max("favor"))["top"]
        )
        or 0
    )
    if standing.favor >= top_other:
        achievement = gods_favorite_achievement_for(character_sheet)
        if achievement is not None:
            from world.achievements.services import grant_achievement  # noqa: PLC0415

            grant_achievement(achievement, [character_sheet])
    return standing

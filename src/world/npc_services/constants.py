"""Constants for the NPC services framework."""

from django.db import models


class OfferKind(models.TextChoices):
    """Discriminator for the per-kind details model + effect handler."""

    PERMIT = "permit", "Permit"
    MISSION = "mission", "Mission"
    # Future kinds: loans/training/favors/marriage/attunement.


class DrawMode(models.TextChoices):
    """How offers on a role are surfaced to the player."""

    MENU = "menu", "Menu"  # Deterministic — every eligible offer is shown.
    POOL = "pool", "Pool"  # NPC draws a subset per visit (mission-style; #686).


# #726 — how many POOL offers an NPC surfaces, by the PC's durable standing
# (``NPCStanding.affection``). Ordered ascending by affection floor;
# ``offer_policy.mission_pool_count`` walks the bands and keeps the count of the
# highest band whose floor the standing meets. A stranger (no standing row /
# class-1 functionary) or a neutral/disliked PC lands on the first band — one
# trial job; a trusted contact reaches the ceiling. These are mechanical tuning
# values, not player-visible flavor — adjust freely.
MISSION_POOL_COUNT_FLOOR = 1
MISSION_POOL_COUNT_BANDS: tuple[tuple[int, int], ...] = (
    (0, 1),  # neutral / stranger — one trial job
    (10, 2),  # acquaintance
    (25, 3),  # trusted
    (50, 4),  # confidant
    (100, 5),  # inner circle — full slate
)

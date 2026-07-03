"""Constants for the NPC services framework."""

from django.db import models


class OfferKind(models.TextChoices):
    """Discriminator for the per-kind details model + effect handler."""

    PERMIT = "permit", "Permit"
    MISSION = "mission", "Mission"
    LOAN = "loan", "Loan"
    # #930 — the domain-running loop: dispatch a collection / invest in the domain.
    COLLECTION = "collection", "Collection"
    IMPROVEMENT = "improvement", "Improvement"
    # Future kinds: training/favors/marriage/attunement.


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

# #1020 — org-reputation lift to the POOL count for NPCs that front an org
# (``NPCRole.faction_affiliation``). Keyed on the persona's ReputationTier
# *rank* — the declaration order of ``societies.types.ReputationTier``
# (reviled=0 … unknown=4 … revered=8). Walked like MISSION_POOL_COUNT_BANDS
# (highest met floor wins). The final POOL count is
# ``max(npc-standing count, org count)``, so org favor lifts the floor without
# capping a personally-cultivated contact. Tuning values — adjust freely.
MISSION_POOL_ORG_COUNT_BANDS: tuple[tuple[int, int], ...] = (
    (0, 1),  # reviled..unknown — org connection alone gives no slate lift
    (5, 2),  # favored
    (6, 3),  # liked
    (7, 4),  # honored
    (8, 5),  # revered
)

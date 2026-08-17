"""Market regard-gating constants (#2995): standing-based service pricing/access.

A persona-bearing NPC seller (a crafter running their own `CraftingServiceOffer`,
or the notable NPC named as a stall's `shopkeeper_persona`) reads `NpcRegard`
(#1717) at purchase time: these are functionary SERVICES the NPC extends, not a
static shop window, so their opinion of the buyer can refuse service outright or
shift the price. PLACEHOLDER tuning — the band walk mirrors
`world.npc_services.offer_policy`'s `_band_count` (ascending ``(floor, value)``
tuples, highest-met-floor wins).
"""

from __future__ import annotations

from world.npc_services.models import REGARD_MIN

REGARD_REFUSAL_FLOOR = -500
"""At or below this NpcRegard value, the seller refuses service outright —
regardless of any authored ``min_regard`` on the listing/offer. PLACEHOLDER."""

REGARD_PRICE_BANDS: tuple[tuple[int, int], ...] = (
    (REGARD_MIN, 150),
    (-200, 115),
    (0, 100),
    (200, 90),
    (500, 75),
)
"""Ascending ``(regard_floor, price_multiplier_percent)``; the buyer's price is
``base_price * percent // 100`` at the highest floor their regard meets (mirrors
``offer_policy._band_count``). PLACEHOLDER — tune on sight."""

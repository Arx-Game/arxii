"""Market demo seed (#2066) — a walkable capital square. PLACEHOLDER content.

Idempotent get-or-create keyed on names. Seeds one market square on a
PLACEHOLDER capital area with an NPC stall carrying material, reagent, and
plain-necessity stock — the coin-sink floor — plus an empty PC stall ready
for ware listings, so the buy/list/finish loop is walkable on a dev DB.
"""

from __future__ import annotations

MARKET_SQUARE_NAME = "City Center Market PLACEHOLDER"
NPC_STALL_NAME = "Provisioners' Row PLACEHOLDER"
PC_STALL_NAME = "Open Crafters' Stall PLACEHOLDER"

_NPC_STOCK = (
    ("Bolt of Plain Cloth PLACEHOLDER", 50),
    ("Iron Ingot PLACEHOLDER", 120),
    ("Dram of Luminous Salts PLACEHOLDER", 400),
    ("Plain Traveling Clothes PLACEHOLDER", 200),
)


def seed_market_demo() -> None:
    """Seed the PLACEHOLDER capital market square (idempotent)."""
    from world.areas.models import Area  # noqa: PLC0415
    from world.items.market.models import (  # noqa: PLC0415
        MarketSquare,
        MarketStall,
        StockListing,
    )
    from world.items.models import ItemTemplate  # noqa: PLC0415

    area = Area.objects.filter(market_squares__name=MARKET_SQUARE_NAME).first()
    if area is None:
        area, _ = Area.objects.get_or_create(
            name="Capital Market District PLACEHOLDER",
            defaults={"level": 20},
        )
    square, created = MarketSquare.objects.get_or_create(
        name=MARKET_SQUARE_NAME, defaults={"area": area}
    )
    if not created:
        return

    npc_stall, _ = MarketStall.objects.get_or_create(square=square, name=NPC_STALL_NAME)
    MarketStall.objects.get_or_create(square=square, name=PC_STALL_NAME)

    for template_name, price in _NPC_STOCK:
        template, _ = ItemTemplate.objects.get_or_create(
            name=template_name,
            defaults={
                "description": "PLACEHOLDER — market stock awaiting authored prose.",
            },
        )
        StockListing.objects.get_or_create(
            stall=npc_stall, template=template, defaults={"price": price}
        )

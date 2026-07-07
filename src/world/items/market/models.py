"""Market models (#2066): capital squares, stalls, listings, service offers.

The two-tier commerce geography (design tenet): **market squares** carry the
transactional trade — NPC stock (materials, reagents, plain necessities;
pure coin sinks) and PC stalls of **unfinished wares** (real crafted
instances sold generic; the buyer's purchase grants a one-time finishing
pass: name, prose, open style/facet slots). **Crafter shops** carry crafting
itself — standing ``CraftingServiceOffer``s execute only at the crafter's
shop (crafting is station-anchored), keeping shops worth visiting and RP
distributed instead of crowded into one square.

The description is the buyer's: nothing here generates prose, ever. Dual
provenance renders "Crafted by X, Designed by Y" (designer fields live on
``ItemInstance`` beside the crafter pair).
"""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

_PERSONA_FK = "scenes.Persona"
_TEMPLATE_FK = "items.ItemTemplate"
_INSTANCE_FK = "items.ItemInstance"


class MarketSquare(SharedMemoryModel):
    """A capital's market hub — one per realm capital (#2066).

    Anchored to the capital's Area; stalls live here. Every capital gets
    one (City Center, Luxen, the Umbral capital...), not just Arx.
    """

    name = models.CharField(max_length=120, unique=True)
    area = models.ForeignKey(
        "areas.Area",
        on_delete=models.PROTECT,
        related_name="market_squares",
        help_text="The capital-city Area this square trades in.",
    )
    realm = models.ForeignKey(
        "realms.Realm",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="market_squares",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class MarketStall(SharedMemoryModel):
    """A stall in a market square (#2066). Cheap and abstract by design.

    ``owner_persona`` null = an NPC stall (materials/reagents/necessities;
    authored ``StockListing`` rows, pure sinks). Owned shopfronts — the
    prestige retail tier with upkeep and cuts — are buildings, not stalls.
    """

    square = models.ForeignKey(
        MarketSquare,
        on_delete=models.CASCADE,
        related_name="stalls",
    )
    name = models.CharField(max_length=120)
    owner_persona = models.ForeignKey(
        _PERSONA_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="market_stalls",
        help_text="Null = NPC stall (authored stock, infinite supply).",
    )
    host_org = models.ForeignKey(
        "societies.Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hosted_stalls",
        help_text="Org taking the listing cut, when the stall is org-hosted (#1884 stream).",
    )
    cut_percent = models.PositiveSmallIntegerField(
        default=0,
        help_text="Host's percentage cut of each sale (0 for plain stalls). PLACEHOLDER.",
    )

    class Meta:
        ordering = ["square", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["square", "name"], name="items_market_stall_unique_name_per_square"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.square.name})"


class StockListing(SharedMemoryModel):
    """NPC stall stock: a template at an authored price, infinite supply (#2066).

    Materials, magical reagents, and plain-quality necessities — the floor
    that keeps nobody blocked on a crafter being online. Purchases mint an
    instance and sink the coin (deflationary tenet).
    """

    stall = models.ForeignKey(
        MarketStall,
        on_delete=models.CASCADE,
        related_name="stock_listings",
    )
    template = models.ForeignKey(
        _TEMPLATE_FK,
        on_delete=models.PROTECT,
        related_name="stock_listings",
    )
    price = models.PositiveIntegerField(help_text="Coppers. PLACEHOLDER pricing.")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["stall", "template__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["stall", "template"], name="items_market_stock_unique_per_stall"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.template} @ {self.price}c ({self.stall.name})"


class WareListing(SharedMemoryModel):
    """A PC's unfinished ware for sale: a real crafted instance (#2066).

    Stock is finite because each unit is an actual ``ItemInstance`` the
    crafter produced. Sold generic; the buyer's purchase transfers the item
    plus a ``FinishingPass`` (name, prose, whichever style/facet slots the
    crafter left open).
    """

    stall = models.ForeignKey(
        MarketStall,
        on_delete=models.CASCADE,
        related_name="ware_listings",
    )
    item_instance = models.OneToOneField(
        _INSTANCE_FK,
        on_delete=models.CASCADE,
        related_name="ware_listing",
    )
    seller_persona = models.ForeignKey(
        _PERSONA_FK,
        on_delete=models.PROTECT,
        related_name="ware_listings",
        help_text="The persona listing (and credited as crafter via the instance).",
    )
    price = models.PositiveIntegerField(help_text="Coppers.")
    open_style_slot = models.BooleanField(
        default=True,
        help_text="Whether the finishing pass may attach a style.",
    )
    open_facet_slot = models.BooleanField(
        default=False,
        help_text="Whether the finishing pass may attach a facet.",
    )
    listed_at = models.DateTimeField(auto_now_add=True)
    sold_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-listed_at"]
        indexes = [models.Index(fields=["stall", "sold_at"])]

    def __str__(self) -> str:
        return f"{self.item_instance} @ {self.price}c"


class FinishingPass(SharedMemoryModel):
    """The buyer's one-time right to finish a purchased ware (#2066).

    The description is the buyer's (design tenet — no generated prose,
    ever): consuming the pass sets the instance's custom name/description
    and stamps the **designer** credit. Open slots let the finishing also
    attach a style/facet through the normal crafting seam.
    """

    listing = models.OneToOneField(
        WareListing,
        on_delete=models.CASCADE,
        related_name="finishing_pass",
    )
    buyer_persona = models.ForeignKey(
        _PERSONA_FK,
        on_delete=models.PROTECT,
        related_name="finishing_passes",
    )
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["pk"]
        verbose_name_plural = "Finishing passes"

    def __str__(self) -> str:
        state = "consumed" if self.consumed_at else "open"
        return f"FinishingPass<{self.listing_id}> ({state})"


class CraftingServiceOffer(SharedMemoryModel):
    """A crafter's standing offer: their skill, your item, at their shop (#2066).

    Arx 1's real loop made consensual and priced. Executes only in the
    offering crafter's shop room (crafting is station-anchored), whether or
    not the crafter is online; the buyer supplies the item + materials and
    runs the attempt; the crafter's traits roll the check and their purse
    takes the fee.
    """

    crafter_persona = models.ForeignKey(
        _PERSONA_FK,
        on_delete=models.CASCADE,
        related_name="crafting_service_offers",
    )
    recipe_kind = models.CharField(
        max_length=40,
        help_text="CraftingRecipeKind this offer covers (attachment crafting).",
    )
    shop_room = models.ForeignKey(
        "evennia_extensions.RoomProfile",
        on_delete=models.CASCADE,
        related_name="crafting_service_offers",
        help_text="The crafter's shop — service runs require presence here.",
    )
    fee = models.PositiveIntegerField(help_text="Coppers per attempt. PLACEHOLDER.")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["crafter_persona", "recipe_kind"]
        constraints = [
            models.UniqueConstraint(
                fields=["crafter_persona", "recipe_kind", "shop_room"],
                name="items_market_service_offer_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.crafter_persona} offers {self.recipe_kind} ({self.fee}c)"


class MarketSale(SharedMemoryModel):
    """Provenance ledger row for every market transaction (#2066)."""

    class SaleKind(models.TextChoices):
        STOCK = "stock", "NPC Stock"
        WARE = "ware", "Ware"
        SERVICE = "service", "Crafting Service"

    kind = models.CharField(max_length=10, choices=SaleKind.choices)
    buyer_persona = models.ForeignKey(
        _PERSONA_FK,
        on_delete=models.PROTECT,
        related_name="market_purchases",
    )
    seller_persona = models.ForeignKey(
        _PERSONA_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="market_sales",
        help_text="Null for NPC stock sales (pure sink).",
    )
    item_instance = models.ForeignKey(
        _INSTANCE_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="market_sales",
    )
    price = models.PositiveIntegerField()
    host_cut = models.PositiveIntegerField(default=0)
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_at"]

    def __str__(self) -> str:
        return f"Sale<{self.kind}>(#{self.pk}, {self.price}c)"

"""Typed exceptions for the items app.

Per CLAUDE.md `ViewSet & API Design`: typed exceptions with `user_message`
property + `SAFE_MESSAGES` allowlist for safe API surfacing. View and
inputfunc layers read `exc.user_message` — never `str(exc)`.

Two families share `ItemError` as the base so `except ItemError:` catches
both:

* Data-layer errors raised by `world.items.services.*` for invalid slot,
  facet capacity, etc.
* Inventory action errors raised by `flows.service_functions.inventory.*`
  for permission denial, possession mismatches, container constraints, etc.
"""

from typing import ClassVar


class ItemError(Exception):
    """Base for items typed exceptions."""

    user_message: str = "An items error occurred."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({"An items error occurred."})


# ---------------------------------------------------------------------------
# Configuration errors (misconfigured game systems)
# ---------------------------------------------------------------------------


class CraftingNotConfigured(Exception):
    """Raised when crafting is attempted before a CheckType is configured."""

    user_message = "Crafting is not available yet."


# ---------------------------------------------------------------------------
# Data-layer errors (slot validity, facet capacity, etc.)
# ---------------------------------------------------------------------------


class SlotConflict(ItemError):
    """Another item already occupies the requested (body_region, equipment_layer) slot."""

    user_message = "Something is already worn there."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({"Something is already worn there."})


class SlotIncompatible(ItemError):
    """The item's template does not declare the requested (body_region, equipment_layer)."""

    user_message = "That item cannot be worn there."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({"That item cannot be worn there."})


class ItemPlacedNotEquippable(ItemError):
    """Item is currently placed in a room as decor and can't be equipped.

    #676 enforces the placed-XOR-equipped invariant at the service layer:
    a decorative item must be removed from its room before it can be worn.
    """

    user_message = "That item is on display. Remove it from the room first."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {"That item is on display. Remove it from the room first."},
    )


class FacetCapacityExceeded(ItemError):
    """The item already carries the maximum number of facets its template allows."""

    user_message = "This item has no remaining facet slots."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {"This item has no remaining facet slots."},
    )


class FacetAlreadyAttached(ItemError):
    """That facet is already attached to this item."""

    user_message = "That facet is already attached to this item."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {"That facet is already attached to this item."},
    )


class StyleCapacityExceeded(ItemError):
    """The item already carries the maximum number of styles its template allows (#546)."""

    user_message = "This item has no remaining style slots."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {"This item has no remaining style slots."},
    )


class StyleAlreadyAttached(ItemError):
    """That style is already attached to this item (#546)."""

    user_message = "That style is already attached to this item."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {"That style is already attached to this item."},
    )


class FashionPresentationError(ItemError):
    """A fashion presentation or peer judging could not be completed (#514).

    Raised for a missing host society, self/alt judging, and duplicate judging.
    The specific ``user_message`` is supplied per raise site via the
    constructor; every such message is enumerated in ``SAFE_MESSAGES`` so the
    API layer may surface it.
    """

    user_message = "That fashion action could not be completed."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "That fashion action could not be completed.",
            "This event has no host society to judge fashion.",
            "You cannot judge your own presentation.",
            "You cannot judge a presentation by your own character.",
            "You have already judged this presentation.",
        },
    )

    def __init__(self, message: str | None = None) -> None:
        if message is not None:
            self.user_message = message
        super().__init__(message or self.user_message)


class ItemNotUsable(ItemError):
    """The item has no on-use pool, or is not a consumable."""

    user_message = "That item can't be used."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({"That item can't be used."})


class NoChargesRemaining(ItemError):
    """The item has no charges left to spend."""

    user_message = "That item has no uses left."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({"That item has no uses left."})


class CraftingStationRequired(ItemError):
    """Raised when a recipe requiring a station has none active in the room (#1234)."""

    user_message = "This crafting requires an installed workspace here."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {"This crafting requires an installed workspace here."},
    )


class CraftingStationBroken(ItemError):
    """Raised when the room's station is too worn (durability 0) to use (#1234)."""

    user_message = "The station here is too worn to use — it needs repair first."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {"The station here is too worn to use — it needs repair first."},
    )


class RecipeNotKnown(ItemError):
    """Raised when a character acts on a gated recipe they have not learned (#2242)."""

    user_message = "You don't know that recipe."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {"You don't know that recipe.", "You can't teach a recipe you don't know."},
    )

    def __init__(self, message: str | None = None) -> None:
        if message:
            self.user_message = message
        super().__init__(self.user_message)


class CategoryRequirementsNotQuotable(ItemError):
    """Raised by build_crafting_quote for a recipe with material-category requirements.

    Crafting *execution* (stage_and_assert_affordable) already supports category
    requirements. The read-only quote preview cannot yet represent a material class
    (no single template) in its per-row API shape; that lands with the quote-surface
    work. No seeded recipe uses category requirements today, so this is a forward
    guard, not a live path.
    """

    user_message = "A materials preview isn't available for this recipe yet."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {"A materials preview isn't available for this recipe yet."},
    )


class AdornmentCapacityExceeded(ItemError):
    """Raised when a host item is already at its template's adornment_capacity (Build 0b)."""

    user_message = "There is no room to set another gem in this piece."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {"There is no room to set another gem in this piece."},
    )


class NotAGem(ItemError):
    """Raised when an item that is not a gem is offered for adornment (Build 0b)."""

    user_message = "That is not a gem."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({"That is not a gem."})


class GemAlreadyAdorned(ItemError):
    """Raised when a gem already set in a piece is offered for adornment again (Build 0b)."""

    user_message = "That gem is already set in a piece."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({"That gem is already set in a piece."})


class InsufficientCommonGems(ItemError):
    """Raised when a common-gem value bucket lacks the value a bulk requirement needs (Build 0b)."""

    user_message = "You don't have enough common gems of that kind."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {"You don't have enough common gems of that kind."},
    )


# ---------------------------------------------------------------------------
# Inventory action errors (pick_up, drop, give, equip, etc.)
# ---------------------------------------------------------------------------


class InventoryError(ItemError):
    """Base for inventory-action failures (pick_up, drop, give, equip, etc.)."""

    user_message: str = "That action could not be completed."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({"That action could not be completed."})


class PermissionDenied(InventoryError):
    user_message = "You cannot do that with that item."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({"You cannot do that with that item."})


class NotInPossession(InventoryError):
    user_message = "You are not carrying that."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({"You are not carrying that."})


class NotEquipped(InventoryError):
    user_message = "You are not wearing that."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({"You are not wearing that."})


class ContainerFull(InventoryError):
    user_message = "That container is already full."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({"That container is already full."})


class ContainerClosed(InventoryError):
    user_message = "That container is closed."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({"That container is closed."})


class ItemTooLarge(InventoryError):
    user_message = "That item is too large to fit in there."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {"That item is too large to fit in there."},
    )


class NotAContainer(InventoryError):
    user_message = "That isn't a container."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({"That isn't a container."})


class NoDropLocation(InventoryError):
    user_message = "You have nowhere to drop that."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {"You have nowhere to drop that."},
    )


class RecipientNotAdjacent(InventoryError):
    user_message = "They are not here to receive it."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({"They are not here to receive it."})


class RecipientConsentDenied(InventoryError):
    """The recipient's consent settings refuse this transfer (#1985).

    Deliberately category-generic: the message must never reveal WHY the
    transfer was refused (naming the stolen-goods category would leak the
    item's hot provenance to both parties).
    """

    user_message = "Their consent settings do not permit this transfer."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {"Their consent settings do not permit this transfer."}
    )


class NotReachable(InventoryError):
    user_message = "You can't reach that."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({"You can't reach that."})


class NotInContainer(InventoryError):
    user_message = "That isn't in a container."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({"That isn't in a container."})


class OutfitIncomplete(InventoryError):
    user_message = "Some pieces of that outfit are missing."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {"Some pieces of that outfit are missing."},
    )


class OwnedByAnother(InventoryError):
    """Raised when a plain take targets a room item owned by someone else (#1909).

    Steal is the deliberate bypass (with consequences); plain pick_up never
    reassigns another character's item.
    """

    user_message = "That belongs to someone else."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({"That belongs to someone else."})


class ContainerAccessDenied(InventoryError):
    """Raised when a container's access policy bars a taker from its contents (#1909)."""

    user_message = "You aren't permitted to take things from there."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {"You aren't permitted to take things from there."},
    )


class TheftNotPermitted(InventoryError):
    """Raised when ``steal`` is refused: no ownership gate to bypass, or consent denies it.

    Covers both "this item doesn't require steal" (steal is not a synonym for
    take) and "the owner's consent settings exclude this actor" (#1909).
    """

    user_message = "You can't bring yourself to take that."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({"You can't bring yourself to take that."})


class VaultAccessDenied(InventoryError):
    """Raised when take is refused: item in a vault room, taker lacks access (#2179).

    The vault access list gates ``take`` for unheld room items. ``steal``
    bypasses this gate with the existing consent-gated theft machinery.
    """

    user_message = "You cannot take that from here."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({"You cannot take that from here."})


class VaultFull(InventoryError):
    """Raised when dropping an item into a vault room that is at capacity (#2179)."""

    user_message = "The vault is full."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({"The vault is full."})


# ---------------------------------------------------------------------------
# Material consumption errors (services/materials.py)
# ---------------------------------------------------------------------------


class CraftingCostUnaffordable(ItemError):
    """Raised when a crafter cannot afford the AP, Anima, or material cost of a recipe.

    Raised by ``stage_and_assert_affordable`` when any resource is short.
    The ``user_message`` is surfaced directly to the player via the API layer.
    """

    user_message = "You cannot afford the cost of this crafting attempt."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {"You cannot afford the cost of this crafting attempt."},
    )

    def __init__(self, message: str | None = None) -> None:
        if message is not None:
            self.user_message = message
        super().__init__(message or self.user_message)


class InsufficientMaterials(ItemError):
    """Raised when a material-consumption check finds an unsatisfied requirement.

    Carries structured data so callers can compose context-appropriate messages.

    Attributes:
        requirement: The duck-typed requirement object that failed
            (e.g. RitualComponentRequirement, CraftingMaterialRequirement).
        provided_qty: Total quantity of matching instances found (may be 0).
    """

    user_message = "You do not have the required materials."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {"You do not have the required materials."},
    )

    def __init__(self, *, requirement: object, provided_qty: int) -> None:
        self.requirement = requirement
        self.provided_qty = provided_qty
        super().__init__(self.user_message)

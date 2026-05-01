# Outfits Phase A — Design

**Date:** 2026-04-30
**Status:** Design accepted, implementation not started
**Roadmap link:** [Items & Equipment](../roadmap/items-equipment.md) — outfits as savable named looks

## Goal

Let a character save their currently-worn loadout as a named **Outfit**, then
swap to it later with one action. Outfits are the primary unit of wardrobe
manipulation — RP players don't min-max single pieces, they swap looks for a
mood, scene, or occasion.

This Phase A delivers the foundation: a real `Outfit` data model, the apply
service + action, the wardrobe-storage constraint, and a polished frontend
wardrobe page. Fashion styles, legendary status, mantles, fame bonuses, and
the modeling minigame are deliberately out of scope and tracked as future
phases.

## Scope

**In scope (Phase A):**

- `Outfit` model — saved named look stored in a wardrobe (a special item)
- `OutfitSlot` through-model — which item goes in which body region/layer
- `ItemTemplate.is_wardrobe` flag — marks a template as a wardrobe
- `apply_outfit(character, outfit)` service — atomic equip of all pieces
- `ApplyOutfitAction` — action-layer wrapper for the apply, telnet + web
- `undress(character)` service — unequip every worn item; items stay in
  inventory (the default unequip behavior — only EquippedItem rows are
  removed)
- `UndressAction` — action-layer wrapper for undress, telnet + web
- `save_outfit`, `delete_outfit`, edit-slot ops — REST CRUD with permission
  checks
- REST endpoints: `OutfitViewSet` with full CRUD on player-owned outfits
- Frontend: wardrobe page in `frontend/src/inventory/` — outfit cards, paper
  doll of currently-worn, item list, item detail panel, save/edit/delete
  flows
- New exception: `OutfitIncomplete`
- Documentation comment in magic's `outfit_daily_trickle` clarifying the
  naming overload

**Deliberately out of scope (future phases):**

- Phase B — Fashion: `FashionStyle` model, item-style compatibility, current
  fashion rotation, fame/resonance bonuses for outfit-style alignment
- Phase C — Modeling minigame: present outfit, peer judging, leaderboards
- Phase D — Legendary outfits + Mantle integration: outfit legend accrual,
  outfit-bound mantles, famous outfits as referenceable artifacts
- Servant retrieval (parked in
  [`docs/roadmap/rooms-and-estates.md`](../roadmap/rooms-and-estates.md)) —
  letting a character apply an outfit when the wardrobe is in another room
  of an estate they own

The frontend's outfit card design includes **placeholder regions** for
fashion style, legendary badge, mantle indicator, and aggregate bonus values
so Phase B–D land their content into existing slots instead of forcing a
redesign.

## Architecture

### The architectural rule for outfit operations

The codebase established last PR that "all mutations flow through the action
layer; REST is read-only" — but that rule was articulated in the context of
inventory ops where two divergent paths (REST equip vs. action equip) had
genuinely different semantics. The actual rule, refined:

> The **action layer** handles **IC actions with game-state consequences**.
> **REST** handles **configuration CRUD**. The distinction is whether the
> operation has IC effects or is just player bookkeeping.

For outfits:

| Operation | Has IC effect? | Path |
|---|---|---|
| Apply outfit (`wear Court Attire`) | Yes — character physically changes clothes; `move_to` fires; room sees emits; hooks run | Action layer |
| Save outfit (snapshot current loadout) | No — labeling a configuration | REST POST |
| Edit outfit (add/remove a slot) | No — changing the configuration | REST PATCH |
| Delete outfit (remove the label) | No — pure bookkeeping; items untouched | REST DELETE |

Permission checks still apply at the REST layer (request user is currently
playing the character; wardrobe is reachable; etc.). They live in a custom
`OutfitWritePermission` class plus serializer validation, the same pattern
the rest of the app already uses for Stories, Journals, and other player-
configured CRUD.

The principle in one line:

> Action layer = "what your character does." REST = "what you the player
> configure about your character."

### Models

Location: `world/items/models.py`

```python
class ItemTemplate(SharedMemoryModel):
    # ... existing fields ...
    is_wardrobe = models.BooleanField(
        default=False,
        help_text="Whether instances of this template can store Outfit definitions.",
    )


class Outfit(SharedMemoryModel):
    """A named saved look — a defined arrangement of items in body slots.

    Owned by a CharacterSheet (the source-of-truth above personas). Stored in
    a wardrobe (an ItemInstance whose template is_wardrobe=True). Applying an
    outfit equips its pieces atomically, replacing whatever was worn.

    Deleting an outfit removes the definition only — the items themselves
    are not affected.
    """

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="outfits",
    )
    wardrobe = models.ForeignKey(
        ItemInstance,
        on_delete=models.CASCADE,  # destroy the wardrobe → its outfit defs go
        related_name="stored_outfits",
        help_text="The wardrobe ItemInstance this outfit is stored in.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["character_sheet", "name"],
                name="items_outfit_unique_name_per_character",
            ),
        ]
        ordering = ["name"]


class OutfitSlot(SharedMemoryModel):
    """One item assignment within an outfit definition.

    The unique constraint on (outfit, body_region, equipment_layer) mirrors
    EquippedItem's per-slot uniqueness. Multi-region items (full plate)
    create multiple OutfitSlot rows, same as EquippedItem.
    """

    outfit = models.ForeignKey(
        Outfit,
        on_delete=models.CASCADE,
        related_name="slots",
    )
    item_instance = models.ForeignKey(
        ItemInstance,
        on_delete=models.CASCADE,  # if the item is destroyed, the slot vanishes
        related_name="outfit_slots",
    )
    body_region = models.CharField(max_length=20, choices=BodyRegion.choices)
    equipment_layer = models.CharField(max_length=20, choices=EquipmentLayer.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["outfit", "body_region", "equipment_layer"],
                name="items_outfit_slot_unique_per_outfit",
            ),
        ]
```

Migration: `0004_outfit_and_more.py` (or whatever the next number is) — adds
the `is_wardrobe` field, `Outfit`, `OutfitSlot`.

### Service functions

Location: `flows/service_functions/outfits.py` (new module)

```python
@transaction.atomic
def apply_outfit(character: CharacterState, outfit_state: OutfitState) -> None:
    """Equip all of ``outfit_state``'s pieces atomically.

    Validation:
        - The outfit's character_sheet matches ``character``.
        - The outfit's wardrobe is reachable by the actor.
        - Every slot's item_instance is reachable by the actor.

    Behavior:
        - Unequips whatever conflicts with the outfit's slots (per the
          existing equip auto-swap policy).
        - Calls equip() per slot, atomically.
    """


@transaction.atomic
def undress(character: CharacterState) -> None:
    """Unequip every item currently worn by the character.

    Items stay in inventory (the default unequip behavior — only
    EquippedItem rows are removed; ObjectDB.location is unchanged because
    equipped items already lived on the character). Idempotent: undressing
    a fully-naked character is a no-op, not an error.
    """


@transaction.atomic
def save_outfit(
    character_sheet: CharacterSheet,
    wardrobe: ItemInstance,
    name: str,
    description: str = "",
) -> Outfit:
    """Snapshot the character's currently-equipped items into a new Outfit.

    Validation:
        - wardrobe.template.is_wardrobe is True.
        - The actor's character must be in reach of the wardrobe.
        - Name is unique for this character_sheet.

    Returns the new Outfit with its OutfitSlot rows populated.
    """


@transaction.atomic
def delete_outfit(outfit: Outfit) -> None:
    """Delete the outfit definition. Items are not touched."""


@transaction.atomic
def add_outfit_slot(
    outfit: Outfit,
    item_instance: ItemInstance,
    body_region: str,
    equipment_layer: str,
) -> OutfitSlot:
    """Add or replace a slot in an outfit. Validates the template declares
    that (region, layer) for the item."""


@transaction.atomic
def remove_outfit_slot(
    outfit: Outfit,
    body_region: str,
    equipment_layer: str,
) -> None:
    """Remove a slot from an outfit. The item is not touched."""
```

Note: `apply_outfit` and `undress` are exposed via the action layer (they're
IC actions — your character physically changes clothes). The save/edit/delete
service functions are called from REST serializers' `create`/`update`/`destroy`
since they're player bookkeeping with no IC effect.

### Object state

Location: `flows/object_states/outfit_state.py` (new)

`OutfitState(BaseState)` mirroring `ItemState` — wraps an Outfit instance,
exposes `is_reachable_by(character_obj)` (delegates to `wardrobe.is_reachable_by`),
permission method `can_apply(actor)` defaulting to True, routed through
`_run_package_hook` for behavior package overrides.

### Action

Location: `actions/definitions/outfits.py` (new)

```python
@dataclass
class ApplyOutfitAction(Action):
    """Wear an outfit (a saved arrangement of items)."""

    key: str = "apply_outfit"
    name: str = "Wear Outfit"
    icon: str = "wardrobe"
    category: str = "items"
    target_type: TargetType = TargetType.SINGLE

    intent_event: str | None = "before_apply_outfit"
    result_event: str | None = "apply_outfit"

    def execute(self, actor, context, **kwargs) -> ActionResult:
        # target = ObjectDB? no — outfit is a model, not a typeclass.
        # Frontend sends outfit_id; inputfunc resolves... wait, current
        # _id resolver only handles ObjectDB. Need to extend OR pass
        # outfit_id raw and resolve in the action.
        ...
```

**Design note on resolver:** The current `execute_action` inputfunc resolves
any `*_id` kwarg to an `ObjectDB`. Outfits aren't ObjectDBs. Options:

1. Extend the resolver to dispatch on a name registry: `outfit_id` → Outfit,
   `target_id` → ObjectDB, etc. Centralized but couples the resolver to
   model names.
2. Have `ApplyOutfitAction.execute` accept `outfit_id` raw (an int) and
   resolve internally via `Outfit.objects.get(pk=...)`.
3. Have the frontend send `target_id` (the wardrobe's ObjectDB) plus
   `outfit_name` and look up by `(wardrobe, name)`. Awkward.

**Recommendation: Option 2.** Per-action resolution keeps the inputfunc
naive, and each action knows its own argument shape. We'll document this
pattern as the standard for non-ObjectDB targets.

Also a parallel `UndressAction` (key `undress`, target_type `SELF`, no
target argument). Register both in `actions/registry.py`.

### Telnet commands

Both telnet commands ship in Phase A so the feature is complete on every
transport:

- **`undress`** — trivial parser (no args), dispatches to `UndressAction`.
- **`wear outfit <name>`** — extend the existing `CmdWear` to fork on the
  `outfit ` prefix. Pattern mirrors `CmdGet`'s `from <container>` extension:
  `resolve_action_args` detects the `outfit ` prefix, looks up the outfit
  by `(character_sheet, name)` (the unique constraint guarantees no
  ambiguity), reassigns `self.action = ApplyOutfitAction()`, and returns
  `{"outfit_id": outfit.pk}`. Wardrobe-reach validation happens in the
  service function.

If the outfit isn't found by name, raise `CommandError` with a clear
"You have no outfit named '<name>'." message. Don't leak whether other
characters have outfits by that name.

### REST endpoints

Location: `world/items/views.py` (extend existing)

```python
class OutfitWritePermission(IsAuthenticated):
    """Allow create/update/delete only when the request.user is currently
    playing the character whose character_sheet owns the outfit."""

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if request.method in SAFE_METHODS or request.user.is_staff:
            return True
        # POST: validated via serializer (character_sheet must be one the
        #       user is currently playing).
        # PATCH/DELETE: object-level check below.
        if request.method == "POST":
            return True
        return True  # delegated to has_object_permission

    def has_object_permission(self, request, view, obj: Outfit):
        if request.user.is_staff:
            return True
        return _account_currently_plays(request.user, obj.character_sheet)


class OutfitViewSet(ModelViewSet):
    """Full CRUD for outfit definitions on player-owned characters."""

    permission_classes = [OutfitWritePermission]
    queryset = Outfit.objects.select_related(
        "character_sheet",
        "wardrobe",
        "wardrobe__template",
    ).prefetch_related(
        Prefetch("slots", queryset=OutfitSlot.objects.select_related(
            "item_instance",
            "item_instance__template",
        ), to_attr="cached_slots"),
    )
    filter_backends = [DjangoFilterBackend]
    filterset_class = OutfitFilter  # filter by character_sheet, wardrobe
    pagination_class = ItemTemplatePagination

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return OutfitWriteSerializer
        return OutfitReadSerializer
```

`OutfitWriteSerializer.create` calls `save_outfit` (or builds the Outfit +
slots manually with the same validation). `update` and `destroy` delegate
to the corresponding service functions. Failures raise
`serializers.ValidationError({"non_field_errors": [exc.user_message]})`.

Slot edit endpoints: nested or flat?

- **Flat** — `OutfitSlotViewSet` with FK filter. Simple but more URLs.
- **Nested** — `POST /api/items/outfits/<id>/slots/`, etc. More REST-y.

Recommend **flat** for consistency with how the rest of the app exposes
through-models (e.g., `EquippedItemViewSet` is flat).

### Frontend

Location: `frontend/src/inventory/` (new feature folder)

Following the existing `frontend/src/codex/` layout:

```
frontend/src/inventory/
├── api.ts                   # OpenAPI-typed query client wrappers
├── components/
│   ├── PaperDoll.tsx        # body silhouette with slot indicators
│   ├── OutfitCard.tsx       # the named outfit card with placeholder regions
│   ├── OutfitGrid.tsx       # list of all outfits for the current character
│   ├── ItemCard.tsx         # single item row in the inventory list
│   ├── ItemDetailPanel.tsx  # large detail drawer when an item is selected
│   ├── SaveOutfitDialog.tsx # name/description form for save-current-as-outfit
│   ├── EditOutfitDialog.tsx # add/remove pieces, rename
│   └── DeleteOutfitDialog.tsx
├── hooks/
│   └── useOutfits.ts        # react-query hooks: list, create, update, delete
├── pages/
│   └── WardrobePage.tsx     # the page everything assembles into
├── types.ts
└── index.ts
```

#### Layout sketch

```
┌─────────────────────────────────────────────────────────────────┐
│  Wardrobe                                                        │
│  ──────────                                                      │
│                                                                  │
│  My Outfits                                       [+ Save Look]  │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐              │
│  │ Court   │  │ Riding  │  │ Mourning│  │ Casual  │              │
│  │ Attire  │  │ Leathers│  │  Black  │  │  Day    │              │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘              │
│                                                                  │
│  Currently Worn ────────────────────────────────────             │
│                                                                  │
│  ┌──────────┐    ┌──────────────────────────────┐                │
│  │          │    │ Items:                       │                │
│  │  paper   │    │ • Silk underdress  (Common)  │                │
│  │  doll    │    │ • Velvet gown      (Fine)    │                │
│  │          │    │ • Pearl necklace   (Master)  │                │
│  │          │    │ ...                          │                │
│  └──────────┘    └──────────────────────────────┘                │
│                                                                  │
│  All Items ─────────────────────────────────────────             │
│  [filterable grid of item cards, quality borders, facet chips]   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

When an outfit card or item card is **clicked**, a side drawer
(`framer-motion`) slides in from the right with the full detail panel:

- Item: large image, full markdown description, quality tier color accent,
  facet chips, weight/size/value, action buttons (Wear, Drop, Give, Put in)
- Outfit: list of constituent items (clickable to drill down), placeholder
  regions for fashion / legendary / mantle / bonuses (visible but empty in
  Phase A), "Wear" button, "Edit" / "Delete" menu

#### Outfit card visual

Concrete spec for `OutfitCard.tsx`:

```
┌──────────────────────────────────────┐
│  Court Attire                  ⋯     │   name (editable inline), kebab menu
│  ──────────────────────────────      │
│  ┌──┐ ┌──┐ ┌──┐ ┌──┐ ┌──┐            │   thumbnails of items, max 5 visible
│  │  │ │  │ │  │ │  │ │  │ +3         │   "+N" badge if more
│  └──┘ └──┘ └──┘ └──┘ └──┘            │
│                                       │
│  ⋯ fashion style                      │   placeholder, gray text in Phase A
│  ⋯ legendary  ⋯ mantle                │   placeholder badges, hidden if
│                                       │     all empty in Phase A
│  Bonuses                              │
│  ⋯                                    │   placeholder
│                                       │
│         [   Wear   ]    [ Edit ]      │
└──────────────────────────────────────┘
```

Phase A renders with the placeholder regions visible-but-empty so Phases
B–D drop content into existing slots. Each placeholder gets a CSS class
that future PRs can hook into.

#### Visual polish

- Quality tier `color_hex` becomes the item card border color (Tailwind
  arbitrary value: `style={{ borderColor: tier.color_hex }}`). Uniform
  border thickness, color carries the meaning.
- **Markdown descriptions** rendered with `react-markdown` + `remark-gfm`,
  with editorial typography (serif body, generous line-height, drop cap on
  the first paragraph if description is long).
- **Framer Motion** for the detail drawer slide-in (300ms ease-out).
- **Dark mode aware** via `next-themes` — borders, backgrounds, text all
  use Tailwind's theme tokens.
- **Empty wardrobe state** is intentional, not broken — illustration of an
  empty hanger and a "Save your first look" CTA pointing at the button.
- **Loading states** use shadcn skeleton components, not spinners.

#### Interaction patterns

- **Click an outfit card** → opens the outfit detail drawer (read-only
  view of the outfit's items + bonuses). "Wear" button at the bottom
  fires the apply action; "Edit" opens the edit dialog.
- **Click an item card** (in worn list or all-items list) → opens the
  item detail drawer.
- **"+ Save Look"** opens a dialog: name input, optional description,
  wardrobe selector (defaulting to the nearest reachable wardrobe).
  Submit → POST to `/api/items/outfits/`. Success → toast via `sonner`.
- **Edit outfit** → dialog with the current slots listed; remove buttons
  per slot, "+ Add item" picker that drops the item into a chosen
  region/layer. Each change is a separate REST call (REST PATCH on the
  Outfit isn't ideal here — slot edits go to a flat
  `/api/items/outfit-slots/` endpoint).
- **Delete outfit** → confirmation dialog, then REST DELETE.
- **Drag-to-equip** for individual items (out of scope for Phase A; tracked
  as a follow-up). The outfit-first model means dragging is secondary.
- **"Undress" button** lives in the "Currently Worn" panel header — a
  small subdued button that fires `UndressAction` via WS execute_action.
  Confirmation modal only if the character is wearing 3+ items (avoid the
  "I changed one accessory" case from needing a confirm).
- **WS action_result** subscription updates the UI after `apply_outfit` /
  `UndressAction` completes — paper doll re-renders, items move from
  "available" to "worn" in the lists.

### Edge cases

- **Outfit references items the character no longer owns.** The
  `OutfitSlot.item_instance` FK is `CASCADE` — if the item is destroyed,
  the slot vanishes. The outfit becomes "incomplete" (fewer slots than
  the character intended). UI shows the outfit card with a warning chip
  ("Missing 2 pieces"); apply still works on the remaining slots.
  Editor lets the user replace missing pieces.
- **Wardrobe is destroyed.** `Outfit.wardrobe` is `CASCADE` — outfit
  definitions go with the wardrobe. Items are not affected.
- **Wardrobe moves rooms.** Outfit definitions stay with the wardrobe;
  the apply action's reach check follows the wardrobe's current location.
- **Saving an outfit when nothing is worn.** Valid — creates an empty
  outfit. UI lets the user add slots after the fact.
- **Saving an outfit with items in containers.** A worn item never has
  `contained_in` set (equipping clears it); so this case shouldn't arise
  in practice. If it does (data integrity issue), the snapshot ignores
  the item.
- **Apply outfit when current loadout includes items not in the outfit.**
  The current equip auto-swap policy already handles same-slot
  replacement. Items in body slots NOT touched by the outfit (e.g., a
  necklace at neck/accessory when the outfit only specifies torso/base)
  are left equipped. **Design call: we don't strip them.** If players
  want a "clean apply" that removes everything else, that's a future
  toggle.

### Migration plan

Single migration, `world/items/migrations/0004_<auto-name>.py`. Adds:

- `ItemTemplate.is_wardrobe` (BooleanField, default False — backfill safe)
- `Outfit` table
- `OutfitSlot` table
- Constraints

No data migration needed.

## Risks and mitigations

- **Naming overload with magic's `outfit_daily_trickle`.** Mitigation:
  add a clarifying comment in that service. Future PR can rename if it
  becomes confusing.
- **Outfit-incomplete UX.** Mitigation: explicit visual treatment of
  incomplete outfits; editor flow for replacing missing pieces.
- **Frontend loading from cold start.** Wardrobe page needs: outfits +
  worn items + carried items + wardrobes-in-reach. Could be 4 round trips.
  Mitigation: a single `/api/items/inventory/` endpoint that returns all
  of it for the active character (or the existing endpoints prefetched
  via `select_related`/`prefetch_related` and called in parallel).
- **No carried-items endpoint exists yet.** Mitigation: add a thin
  `ItemInstanceViewSet` (read-only) with a `?character=` filter that
  returns items where `game_object.location == character`. Lands in this
  PR alongside the outfit work — small addition.
- **Action-layer resolver doesn't handle Outfit pks.** Mitigation:
  `ApplyOutfitAction.execute` resolves `outfit_id` internally (Option 2
  above). Document the pattern for future non-ObjectDB-target actions.

## Out-of-scope follow-ups

- Phase B (Fashion), Phase C (Modeling), Phase D (Legendary + Mantle) —
  separate brainstorm sessions, separate PRs.
- Drag-to-equip individual items in the wardrobe view.
- Servant retrieval (rooms-and-estates roadmap).
- Outfit sharing / cross-character viewing — not planned.
- Outfit auto-apply on scene entry — not planned.

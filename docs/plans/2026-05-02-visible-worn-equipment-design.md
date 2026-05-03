# Visible Worn Equipment — Design

**Date:** 2026-05-02
**Status:** Design accepted, implementation not started
**Roadmap link:** [Items & Equipment](../roadmap/items-equipment.md) — visible equipment in look output

## Goal

When a character looks at another character, they see the visible portion of
that character's worn equipment — names only, with deeper layers concealed by
covering items. From that view, drilling into a specific piece reveals its
description and details. Same data on every transport: telnet uses
`look <person>'s <item>` (or preposition forms); the React frontend uses a
side-panel focus stack.

## Scope

**In scope:**

- Per-(body_region, equipment_layer) visibility computation using existing
  `TemplateSlot.covers_lower_layers` flag
- `visible_worn_items_for(character_obj)` service in `world.items.services`
- `CharacterState.get_display_worn(looker)` display-component method +
  `appearance_template` extension to render worn items into the look output
- Telnet `CmdLook` parser extended to handle:
  - `look <person>'s <item>` (possessive)
  - `look <item> on <person>` (worn preposition)
  - `look <item> in <container>` (contained preposition)
- API: extend the character/persona read serializer with a
  `visible_worn_items` field (slim — id, display_name, body_region,
  equipment_layer; full details fetched from existing item endpoints when
  needed)
- Frontend: evolve the right sidebar's `RoomPanel` into a focus stack
  - Default focus: room (current behavior)
  - Click a character → push character-focus view
  - Click a worn item → push item-focus view
  - Back button → pop
  - Tab label dynamic: room name → character name → item name
  - Item-focus content reuses the existing `ItemDetailPanel` rendering

**Out of scope (parked):**

- **Narrative status in character descriptions** ("she looks tired and
  bloody") — tracked in `docs/roadmap/combat.md`. The appearance template
  gets a `{status}` slot now so that follow-up plugs in cleanly without
  retrofitting.
- Examining items inside containers a third party owns
- Double-click semantics — single-click drills in everywhere

## Architecture

### Visibility rules

For each body region a character has equipped items at:

1. Sort the `EquippedItem` rows for that region by `equipment_layer`
   (skin → under → base → over → outer → accessory).
2. Walk top-down. Find the highest layer whose `TemplateSlot.covers_lower_layers`
   is True for that region. Call that the "covering layer."
3. Items at or above the covering layer are visible. Items strictly below
   are concealed.
4. If no slot covers, every layer at the region is visible.

Layer hiding is purely per-(region, layer). A cloak that declares slots only
at SHOULDERS/OVER + BACK/OVER hides only those regions' lower layers — it
does not affect what's visible on the torso, because it has no torso slot.

**Two observer-based bypasses to layer hiding:**

1. **Looking at yourself** — your own concealed items are visible to you
   (it'd be silly for the look output to hide your own underwear from
   yourself).
2. **Staff** — staff bypass layer hiding entirely. Staff routinely need to
   investigate equipment in-game and shouldn't have to drop into Django
   admin to see what's actually on a character. The same bypass applies to
   the API permission gates.

Both bypasses skip the hiding pass and return everything equipped.

### Service function

Location: `world/items/services/appearance.py` (new module — sibling of
`equip.py` and `facets.py`).

```python
@dataclass(frozen=True)
class VisibleWornItem:
    """One visible piece of a character's worn equipment."""

    item_instance: ItemInstance
    body_region: str  # BodyRegion choice value
    equipment_layer: str  # EquipmentLayer choice value


def visible_worn_items_for(
    character: ObjectDB,
    observer: ObjectDB | AccountDB | None = None,
) -> list[VisibleWornItem]:
    """Return the character's worn items that are visible to ``observer``.

    Walks EquippedItem rows for ``character``, applies per-(region, layer)
    hiding via TemplateSlot.covers_lower_layers, returns an ordered list
    (top-down by region: head → face → neck → … → feet, then accessories).

    Layer hiding is bypassed when:
        - ``observer`` is the same character (looking at yourself), OR
        - ``observer`` is staff (or the AccountDB of a staff user).

    ``observer=None`` (the default) applies hiding. Pass the observer
    explicitly when the caller has the context.
    """
```

The service uses the existing `CharacterEquipmentHandler` (already cached
on the character) to avoid a fresh DB roundtrip when the look path runs
inside a scene.

### CharacterState extension

Add to `flows/object_states/character_state.py`:

```python
def get_display_worn(self, looker: BaseState | None = None, **kwargs) -> str:
    """Return the visible worn equipment as look-output text.

    Empty string when nothing visible is worn — the appearance template
    omits the section entirely in that case.
    """
    visible = visible_worn_items_for(self.obj)
    if not visible:
        return ""
    names = iter_to_str(
        (item.item_instance.display_name for item in visible),
        endsep=", and",
    )
    return f"|wWearing:|n {names}."


def get_display_status(self, looker=None, **kwargs) -> str:
    """Placeholder for narrative status (parked in combat roadmap)."""
    return ""
```

Extend `CharacterState.template`:

```python
@property
def template(self) -> str:
    return "Character: {name}\n{description}\n{status}\n{worn}"
```

`return_appearance` already calls `get_display_*` for each template slot.
Adding two new slots needs `return_appearance` to pass `worn=` and `status=`
to the format call. Override `return_appearance` on `CharacterState` (or
generalize the base to dispatch via attribute lookup — TBD by implementer
based on what's least invasive).

### Telnet command — possessive + preposition parsing

Extend `CmdLook.resolve_action_args` in
`commands/evennia_overrides/perception.py` to detect three forms:

```python
POSSESSIVE_RE = re.compile(r"^(.+?)'s\s+(.+)$")
ON_RE = re.compile(r"^(.+?)\s+on\s+(.+)$", flags=re.IGNORECASE)
IN_RE = re.compile(r"^(.+?)\s+in\s+(.+)$", flags=re.IGNORECASE)
```

Order of detection: possessive first, then `on`, then `in`. If any matches,
dispatch to a new `LookAtItemAction` with `{owner: ObjectDB, item: ObjectDB}`
or `{container: ObjectDB, item: ObjectDB}` kwargs. Otherwise fall through to
the existing single-target `LookAction`.

Item-resolution rules:
- Possessive / `on` form: search the named character's *visible* worn items
  by name. If not visible (concealed under another layer), fail with "You
  can't see anything by that name on them."
- `in` form: search the named container's contents (visible only — closed
  containers reject the search at this phase).

The `look <foo> on <bar>` form competes with positional words. Prefer the
*possessive* parse if both could match (`look hat on bob`'s "hat" is the
target item, "bob" is the owner — the possessive doesn't apply here, so the
`on` regex catches it).

### `LookAtItemAction`

New action in `actions/definitions/perception.py`:

```python
@dataclass
class LookAtItemAction(Action):
    key: str = "look_at_item"
    name: str = "Examine Item"
    target_type: TargetType = TargetType.SINGLE

    def execute(self, actor, context, **kwargs):
        item = kwargs.get("item")
        owner = kwargs.get("owner")  # if from possessive/on form
        container = kwargs.get("container")  # if from "in" form

        # Visibility gate: if owner provided, item must be in owner's
        # visible_worn_items. If container provided, container must be
        # open and item must be in its contents.
        ...
        # Render item appearance and msg the actor.
```

Registered in `actions.registry`.

### REST API

Two pieces:

1. Extend the **persona/character read serializer** with a
   `visible_worn_items` field. Returns a slim list of items the looker
   would see if they were in the same room. Slim = `{id, display_name,
   body_region, equipment_layer}`. Full item detail fetched via the
   existing `/api/items/inventory/<id>/` (we should verify the inventory
   endpoint allows fetching ANY visible item — see permission notes
   below).

2. **Permission adjustment on `ItemInstanceViewSet`.** Currently scoped to
   items where `game_object.location == characters the user plays`. For the
   look-at flow we need to allow retrieval of items currently equipped on
   characters in the looker's room (visibility-scoped). Adding a separate
   read-only endpoint `/api/items/visible-worn/?character=N` that returns
   the slim VisibleWornItem rows is cleaner than relaxing the existing
   queryset filter — it keeps the inventory endpoint genuinely private to
   the requester's own carriers.

   Staff bypass: the new endpoint passes `request.user` as the observer to
   `visible_worn_items_for`, which short-circuits the hiding pass for staff
   users. Staff can also fetch items they don't otherwise own via the
   existing `is_staff: True` short-circuit on the inventory detail view.

### Frontend — focus stack

Right sidebar's "Room" tab evolves into a generic focus stack:

```typescript
type FocusEntry =
  | { kind: 'room'; roomData: RoomData; sceneData: SceneSummary | null }
  | { kind: 'character'; character: VisiblePersona }
  | { kind: 'item'; item: ItemInstance };

const [focusStack, setFocusStack] = useState<FocusEntry[]>([{ kind: 'room', ... }]);
const currentFocus = focusStack[focusStack.length - 1];

const pushFocus = (entry: FocusEntry) => setFocusStack(s => [...s, entry]);
const popFocus = () => setFocusStack(s => s.length > 1 ? s.slice(0, -1) : s);
```

The tab label reads from `currentFocus`:

- `kind === 'room'`: the room name (or "Room" for the icon-only label).
- `kind === 'character'`: the character's display name.
- `kind === 'item'`: the item's display name.

Components:

- `FocusPanel` — top-level component for the right sidebar. Renders a
  back-button when stack depth > 1, then dispatches by `currentFocus.kind`
  to the appropriate sub-view.
- `RoomFocusView` — what `RoomPanel` is today. Click a character in
  `CharactersList` calls `pushFocus({ kind: 'character', character })`.
- `CharacterFocusView` (new) — name header, description (markdown),
  `<Status />` placeholder slot (empty until combat follow-up), worn
  items list. Each worn item's row is clickable → `pushFocus({ kind:
  'item', item })`.
- `ItemFocusView` (new, slim) — adapts the existing `ItemDetailPanel`
  rendering for the narrower sidebar context. Image, description, quality,
  facets. No "Wear / Drop / Give" actions when looking at someone else's
  item — those only appear when the item is in the looker's possession.

### Data flow for the click-to-drill UX

1. Player clicks a character in `RoomFocusView`'s `CharactersList`.
2. `pushFocus({ kind: 'character', character })` updates the focus stack.
3. `FocusPanel` renders `CharacterFocusView`.
4. `CharacterFocusView` calls `useCharacterAppearance(character.id)` — a
   new react-query hook that hits the persona/character endpoint and
   returns description + visible_worn_items.
5. Each worn item is clickable; click pushes
   `{ kind: 'item', item: <slim item> }` onto the stack.
6. `ItemFocusView` lazy-fetches full item detail via existing item endpoint
   keyed by id.
7. Back button pops; tab name updates accordingly.

### Edge cases

- **Looker can't see the room** (different room, scene-permission gate):
  the look command already fails at the action layer; nothing new needed.
- **Looker examines themselves** (`look me`): visible worn items include
  everything they're wearing — handled by the `observer` parameter on
  `visible_worn_items_for`.
- **Staff looking at any character**: staff bypass layer hiding (no Django
  admin trip required to investigate gear) — also handled by the
  `observer` parameter.
- **Item destroyed mid-look**: existing `ItemInstance.objects.get` patterns
  raise `DoesNotExist`; surface as "That item is no longer there."
- **Possessive `look bob's hat`** when Bob isn't in the room: the search
  for Bob fails first; standard "Could not find 'Bob'" applies.
- **Multiple visible items with the same display_name** (twins wearing
  identical pendants): standard Evennia search disambiguation. The look
  command's caller.search handles it.

### Tests

- Service: visibility computation across permutations (single layer, two
  layers no covering, two layers with covering, multiple body regions).
- Service: observer == character (self-look) skips hiding.
- Service: observer is staff skips hiding.
- Service: observer is non-staff non-self → hiding applies.
- CharacterState: `get_display_worn` returns formatted string with
  `iter_to_str` for visible items, empty string for naked character.
- CharacterState: `return_appearance` includes `{worn}` slot when populated,
  omits when empty.
- CmdLook: parser detects each of the three forms, dispatches to
  `LookAtItemAction` with correct kwargs, falls through to plain
  `LookAction` when nothing matches.
- LookAtItemAction: visibility gate (concealed item raises with clear
  message), happy path renders item appearance, container-open check.
- API: `visible_worn_items` field returns the slim list with correct
  visibility filtering.
- Frontend: focus stack push/pop, dynamic tab label, click-through from
  room to character to item, back button.

## Migration plan

No new models. No migrations.

## Risks and mitigations

- **`return_appearance` extension might break sibling states.** The base
  `BaseState.return_appearance` calls `get_display_*` for fixed slots
  (name, desc, exits, characters, things). Adding `worn` and `status` is
  character-specific — best to override `return_appearance` on
  `CharacterState` rather than adding new slots to the base template.
  Or generalize the base to dispatch by attribute lookup. Implementer
  picks based on least-invasive approach.

- **Visibility rule subtlety: items at the same region, same layer.**
  Unique constraint already prevents this, so no ambiguity.

- **API permission for visible-worn lookups.** The `ItemInstanceViewSet` is
  scoped to the request user's own characters. Adding a new
  `/api/items/visible-worn/?character=N` endpoint that returns slim rows
  for any character in the requester's room is the right separation. The
  full item detail is fetchable from a separate endpoint; that endpoint
  needs to allow lookups for items visibly worn by characters in the same
  room as the looker. A simple approach: add a `VisibleItemDetailViewSet`
  that filters by "currently equipped on a character in your room." Avoid
  loosening `ItemInstanceViewSet` itself.

- **Server-pushed updates.** When another player equips/unequips, the
  current focus might go stale. The existing WS `action_result` bus
  invalidates `equipped` queries; the focus panel's `CharacterFocusView`
  hooks into the same invalidation path. If the focused character moves
  rooms, the looker should auto-pop back to the room focus.

## Out-of-scope follow-ups

- Narrative status in character descriptions (combat roadmap)
- Examining items in containers belonging to others
- Privacy gates (some items might be hidden from non-owners even when
  worn — e.g., a magical disguise)
- Right-click context menu on worn items (e.g., "Compliment outfit")
- Character profile page integration (separate dedicated page beyond the
  scene-side focus panel)

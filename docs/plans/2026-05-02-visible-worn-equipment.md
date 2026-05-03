# Visible Worn Equipment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** When a character looks at another character, see their visible worn equipment (names only, with deeper layers concealed by covering items). Drill into a specific piece to read its full description. Same data on every transport — telnet `look <person>'s <item>` / preposition forms, and a focus-stack side panel in the React frontend.

**Architecture:** Visibility computed per-(body_region, equipment_layer) using existing `TemplateSlot.covers_lower_layers`. Service in `world.items.services` is the single source of truth; `CharacterState.get_display_worn` calls it for telnet output; REST endpoints expose slim + detail views; frontend right-sidebar `RoomPanel` evolves into a focus stack with dynamic tab label. Bundled with this slice: cross-cutting **staff-bypass infrastructure** — `PlayerOnlyPermission` / `PlayerOrStaffPermission` DRF base classes plus `is_staff_observer(observer)` service helper. Picking the base class is the per-resource opt-in for staff bypass; default is no surprise bypass.

**Tech Stack:** Django 5, DRF, Evennia, FactoryBoy, React 18, shadcn/ui, react-query, Tailwind, Framer Motion.

**Design source:** `docs/plans/2026-05-02-visible-worn-equipment-design.md`

---

## Pre-flight

```bash
git -C /c/Users/apost/PycharmProjects/arxii status
git -C /c/Users/apost/PycharmProjects/arxii branch --show-current
```

Expected: `visible-worn-equipment` branch, clean tree (only the design + plan + roadmap docs ahead of main).

Each task ends with a commit. TDD: failing test → run → minimal code → run → commit.

To run backend tests: `echo "yes" | uv run --directory /c/Users/apost/PycharmProjects/arxii arx test world.items --keepdb -v 2`

---

## Task 1: Staff-bypass infrastructure (helper + base permission classes)

**Files:**
- Create: `src/core_management/permissions.py` (new module — exports `is_staff_observer`, `PlayerOnlyPermission`, `PlayerOrStaffPermission`)
- Create: `src/core_management/tests/test_permissions.py`

The module placement: `core_management` already exists for cross-cutting infrastructure (Evennia migration shims, etc.). It's the right home for shared permission primitives. If a different shared location feels more natural after reading existing structure, use that and document why.

### Step 1: Write failing test

```python
# src/core_management/tests/test_permissions.py
"""Tests for the shared permission primitives."""

from unittest.mock import MagicMock, PropertyMock

from django.test import TestCase
from rest_framework.test import APIRequestFactory

from core_management.permissions import (
    PlayerOnlyPermission,
    PlayerOrStaffPermission,
    is_staff_observer,
)


class IsStaffObserverTests(TestCase):
    def test_none_returns_false(self) -> None:
        self.assertFalse(is_staff_observer(None))

    def test_user_with_is_staff_true(self) -> None:
        observer = MagicMock(is_staff=True, is_authenticated=True)
        self.assertTrue(is_staff_observer(observer))

    def test_user_with_is_staff_false(self) -> None:
        observer = MagicMock(is_staff=False, is_authenticated=True)
        self.assertFalse(is_staff_observer(observer))

    def test_object_db_with_staff_account(self) -> None:
        # ObjectDB (character) — walks .account.is_staff
        account = MagicMock(is_staff=True, is_authenticated=True)
        observer = MagicMock(spec=["account"])
        observer.account = account
        # Bypass the spec=["account"] limitation: we want is_staff lookup
        # to fall through. Use real attribute setting:
        observer = type("FakeObj", (), {"account": account})()
        self.assertTrue(is_staff_observer(observer))

    def test_object_db_with_non_staff_account(self) -> None:
        account = MagicMock(is_staff=False, is_authenticated=True)
        observer = type("FakeObj", (), {"account": account})()
        self.assertFalse(is_staff_observer(observer))

    def test_object_db_with_no_account(self) -> None:
        observer = type("FakeObj", (), {"account": None})()
        self.assertFalse(is_staff_observer(observer))

    def test_object_with_no_is_staff_or_account_attr(self) -> None:
        observer = type("FakeObj", (), {})()
        self.assertFalse(is_staff_observer(observer))


class PlayerOnlyPermissionTests(TestCase):
    """Staff get NO bypass on writes; SAFE_METHODS pass for any authenticated user."""

    def setUp(self) -> None:
        self.factory = APIRequestFactory()
        self.permission = PlayerOnlyPermission()

    def _request(self, method: str, *, is_authenticated: bool, is_staff: bool):
        req = getattr(self.factory, method.lower())("/")
        req.user = MagicMock(is_authenticated=is_authenticated, is_staff=is_staff)
        return req

    def test_unauthenticated_get_denied(self) -> None:
        req = self._request("get", is_authenticated=False, is_staff=False)
        self.assertFalse(self.permission.has_permission(req, MagicMock()))

    def test_authenticated_get_allowed(self) -> None:
        req = self._request("get", is_authenticated=True, is_staff=False)
        self.assertTrue(self.permission.has_permission(req, MagicMock()))

    def test_staff_post_NOT_bypassed(self) -> None:
        # PlayerOnly → staff get NO bypass on writes.
        # Subclass that returns False for player check:
        class Denying(PlayerOnlyPermission):
            def has_permission_for_player(self, request, view): return False
        permission = Denying()
        req = self._request("post", is_authenticated=True, is_staff=True)
        self.assertFalse(permission.has_permission(req, MagicMock()))


class PlayerOrStaffPermissionTests(TestCase):
    """Staff get bypass on every method including writes."""

    def setUp(self) -> None:
        self.factory = APIRequestFactory()

    def _request(self, method: str, *, is_authenticated: bool, is_staff: bool):
        req = getattr(self.factory, method.lower())("/")
        req.user = MagicMock(is_authenticated=is_authenticated, is_staff=is_staff)
        return req

    def test_staff_post_bypassed(self) -> None:
        class Denying(PlayerOrStaffPermission):
            def has_permission_for_player(self, request, view): return False
        permission = Denying()
        req = self._request("post", is_authenticated=True, is_staff=True)
        self.assertTrue(permission.has_permission(req, MagicMock()))

    def test_player_check_runs_for_non_staff_post(self) -> None:
        called = []
        class Permission(PlayerOrStaffPermission):
            def has_permission_for_player(self, request, view):
                called.append(True)
                return True
        permission = Permission()
        req = self._request("post", is_authenticated=True, is_staff=False)
        self.assertTrue(permission.has_permission(req, MagicMock()))
        self.assertEqual(called, [True])

    def test_staff_object_permission_bypassed(self) -> None:
        class Denying(PlayerOrStaffPermission):
            def has_object_permission_for_player(self, request, view, obj): return False
        permission = Denying()
        req = self._request("delete", is_authenticated=True, is_staff=True)
        self.assertTrue(permission.has_object_permission(req, MagicMock(), MagicMock()))
```

### Step 2: Run, verify failure

```bash
echo "yes" | uv run --directory /c/Users/apost/PycharmProjects/arxii arx test core_management.tests.test_permissions --keepdb -v 2
```

Expected: ImportError on `core_management.permissions`.

### Step 3: Implement

Create `src/core_management/permissions.py`:

```python
"""Shared permission primitives.

The principle: staff bypass is explicitly opt-in per resource, never
automatic. Two base classes encode the policy at class definition time —
``PlayerOnlyPermission`` (staff get NO bypass) and
``PlayerOrStaffPermission`` (staff bypass everything). Subclasses override
``has_permission_for_player`` and ``has_object_permission_for_player``;
the base handles the auth/SAFE_METHODS plumbing.

For service-layer staff-aware logic, ``is_staff_observer(observer)`` is a
yes/no question. The caller decides what to do with the answer — no
automatic policy.
"""

from __future__ import annotations

from rest_framework.permissions import SAFE_METHODS, IsAuthenticated


def is_staff_observer(observer: object) -> bool:
    """Whether ``observer`` represents a staff user.

    Accepts any of: ObjectDB (character), AccountDB, Django User-like.
    For ObjectDB (character), walks ``character.account.is_staff``.
    Returns False if ``observer`` is None, has no ``is_staff`` attr and no
    associated account, or the associated account isn't staff.

    The helper is policy-free — it only answers the yes/no question.
    Callers that need a staff bypass call this and decide their own behavior.
    """
    if observer is None:
        return False
    is_staff = getattr(observer, "is_staff", None)
    if is_staff is not None:
        return bool(is_staff)
    account = getattr(observer, "account", None)
    if account is None:
        return False
    return bool(getattr(account, "is_staff", False))


class PlayerOnlyPermission(IsAuthenticated):
    """Player-side check only. Staff get NO special bypass.

    Use for sensitive resources where staff shouldn't peek (very private
    scenes, sealed journals, secret pose targets).
    """

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if request.method in SAFE_METHODS:
            return True
        return self.has_permission_for_player(request, view)

    def has_object_permission(self, request, view, obj):
        return self.has_object_permission_for_player(request, view, obj)

    def has_permission_for_player(self, request, view):
        return True

    def has_object_permission_for_player(self, request, view, obj):
        return True


class PlayerOrStaffPermission(PlayerOnlyPermission):
    """Like ``PlayerOnlyPermission``, but staff bypass.

    Use when staff legitimately need cross-player access (look at gear,
    manage events, edit any character's roster — the common case).
    """

    def has_permission(self, request, view):
        if request.user.is_authenticated and request.user.is_staff:
            return True
        return super().has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        return super().has_object_permission(request, view, obj)
```

### Step 4: Run, verify pass

```bash
echo "yes" | uv run --directory /c/Users/apost/PycharmProjects/arxii arx test core_management.tests.test_permissions --keepdb -v 2
```

Expected: all tests pass.

### Step 5: Commit

```bash
git -C /c/Users/apost/PycharmProjects/arxii add src/core_management/permissions.py src/core_management/tests/test_permissions.py
git -C /c/Users/apost/PycharmProjects/arxii commit -m "feat(core): is_staff_observer helper and PlayerOnly/PlayerOrStaff permission bases"
```

---

## Task 2: Audit + refactor existing permission classes with inline staff bypass

The goal: find every permission class that inlines `request.user.is_staff` short-circuits, refactor to inherit `PlayerOrStaffPermission`. The behavior is preserved; the inline check is dropped because the base handles it.

### Step 1: Audit

```bash
grep -rn "is_staff" /c/Users/apost/PycharmProjects/arxii/src/world /c/Users/apost/PycharmProjects/arxii/src/web 2>&1 | grep -v "test_" | grep -v "/migrations/" | head -50
```

For each hit, classify:
- **Refactor candidate:** permission class with `if request.user.is_staff: return True` short-circuit. Typical pattern: outfit, equipped-item, item-facet ViewSet permissions.
- **Skip:** non-permission code (e.g., admin bypass logic in a serializer, model validation, etc.). Document if dubious.

Likely candidates based on prior PRs:
- `src/world/items/views.py`: `OutfitWritePermission`, `OutfitSlotWritePermission`, possibly any others
- `src/world/items/views.py`: anything else with a permission class
- `src/world/scenes/`, `src/world/journals/`, etc.: possibly more

For each refactor candidate, write a brief audit note (in your task report, not in code):

```
<Permission class>: <file>:<line> — staff bypass intentional? (yes/no/dubious)
```

### Step 2: For each YES bypass — refactor

Mechanical refactor:
- Change base from `IsAuthenticated` → `PlayerOrStaffPermission`
- Rename `has_permission` → `has_permission_for_player`
- Drop the inline `super().has_permission(request, view)` check (the base handles it)
- Drop the inline `if request.method in SAFE_METHODS: return True` (the base handles it)
- Drop the inline `if request.user.is_staff: return True` (the base handles it)
- Rename `has_object_permission` → `has_object_permission_for_player`; drop inline staff bypass
- Update the import block

Existing tests that exercise these permissions should keep passing — the behavior is identical (staff still bypass; non-staff still go through the player check). Run the full test suite for each touched app before moving on.

### Step 3: For each DUBIOUS bypass — flag, don't change

If you find any inline staff bypass that looks like it might not be intentional, leave it alone in this task. List it in your report under "Flagged for review." We'll handle each in a focused follow-up.

### Step 4: Run regression after refactor

```bash
echo "yes" | uv run --directory /c/Users/apost/PycharmProjects/arxii arx test world.items --keepdb -v 2
echo "yes" | uv run --directory /c/Users/apost/PycharmProjects/arxii arx test world --keepdb -v 2
```

Expected: all tests pass without modification. If any test fails, the refactor changed behavior — back out and report.

### Step 5: Commit

```bash
git -C /c/Users/apost/PycharmProjects/arxii commit -am "refactor(items): adopt PlayerOrStaffPermission base in existing permission classes"
```

(One commit per app touched is fine if the refactor is large; keep them mechanical and reviewable.)

---

## Task 3: Visible-worn-items service

**Files:**
- Create: `src/world/items/services/appearance.py`
- Modify: `src/world/items/services/__init__.py` — re-export `visible_worn_items_for`
- Create: `src/world/items/tests/test_appearance_service.py`

### Step 1: Write failing test

```python
# src/world/items/tests/test_appearance_service.py
"""Tests for the visible-worn-items service."""

from django.test import TestCase

from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    ObjectDBFactory,
)
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import (
    ItemInstanceFactory,
    ItemTemplateFactory,
    TemplateSlotFactory,
)
from world.items.models import EquippedItem
from world.items.services.appearance import visible_worn_items_for


class VisibleWornItemsServiceTests(TestCase):
    def setUp(self) -> None:
        self.character = CharacterFactory(db_key="VisTestChar")

    def _equip(self, item, region, layer):
        return EquippedItem.objects.create(
            character=self.character,
            item_instance=item,
            body_region=region,
            equipment_layer=layer,
        )

    def _make_item(self, name, region, layer, *, covers=False):
        template = ItemTemplateFactory(name=name)
        TemplateSlotFactory(
            template=template,
            body_region=region,
            equipment_layer=layer,
            covers_lower_layers=covers,
        )
        item_obj = ObjectDBFactory(
            db_key=f"{name}_obj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        return ItemInstanceFactory(template=template, game_object=item_obj)

    def test_single_layer_returns_one_visible(self) -> None:
        shirt = self._make_item("Shirt", BodyRegion.TORSO, EquipmentLayer.BASE)
        self._equip(shirt, BodyRegion.TORSO, EquipmentLayer.BASE)
        result = visible_worn_items_for(self.character)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].item_instance, shirt)

    def test_two_layers_no_covering_both_visible(self) -> None:
        shirt = self._make_item("Shirt", BodyRegion.TORSO, EquipmentLayer.BASE)
        coat = self._make_item("Coat", BodyRegion.TORSO, EquipmentLayer.OVER, covers=False)
        self._equip(shirt, BodyRegion.TORSO, EquipmentLayer.BASE)
        self._equip(coat, BodyRegion.TORSO, EquipmentLayer.OVER)
        result = visible_worn_items_for(self.character)
        self.assertEqual(len(result), 2)

    def test_two_layers_with_covering_only_top_visible(self) -> None:
        shirt = self._make_item("Shirt", BodyRegion.TORSO, EquipmentLayer.BASE)
        coat = self._make_item("Coat", BodyRegion.TORSO, EquipmentLayer.OVER, covers=True)
        self._equip(shirt, BodyRegion.TORSO, EquipmentLayer.BASE)
        self._equip(coat, BodyRegion.TORSO, EquipmentLayer.OVER)
        result = visible_worn_items_for(self.character)
        names = [v.item_instance.display_name for v in result]
        self.assertIn("Coat", names)
        self.assertNotIn("Shirt", names)

    def test_different_regions_unaffected_by_each_other(self) -> None:
        # Cloak covers shoulders/back at OVER; doesn't touch torso.
        cloak = self._make_item("Cloak", BodyRegion.SHOULDERS, EquipmentLayer.OVER, covers=True)
        torso_shirt = self._make_item("Shirt", BodyRegion.TORSO, EquipmentLayer.BASE)
        self._equip(cloak, BodyRegion.SHOULDERS, EquipmentLayer.OVER)
        self._equip(torso_shirt, BodyRegion.TORSO, EquipmentLayer.BASE)
        result = visible_worn_items_for(self.character)
        names = [v.item_instance.display_name for v in result]
        self.assertIn("Cloak", names)
        self.assertIn("Shirt", names)

    def test_self_observer_skips_hiding(self) -> None:
        shirt = self._make_item("Shirt", BodyRegion.TORSO, EquipmentLayer.BASE)
        coat = self._make_item("Coat", BodyRegion.TORSO, EquipmentLayer.OVER, covers=True)
        self._equip(shirt, BodyRegion.TORSO, EquipmentLayer.BASE)
        self._equip(coat, BodyRegion.TORSO, EquipmentLayer.OVER)
        # Looking at yourself — should see everything.
        result = visible_worn_items_for(self.character, observer=self.character)
        self.assertEqual(len(result), 2)

    def test_staff_observer_skips_hiding(self) -> None:
        staff_account = AccountFactory(is_staff=True)
        staff_character = CharacterFactory(db_key="StaffChar")
        staff_character.db_account = staff_account
        staff_character.save()

        shirt = self._make_item("Shirt", BodyRegion.TORSO, EquipmentLayer.BASE)
        coat = self._make_item("Coat", BodyRegion.TORSO, EquipmentLayer.OVER, covers=True)
        self._equip(shirt, BodyRegion.TORSO, EquipmentLayer.BASE)
        self._equip(coat, BodyRegion.TORSO, EquipmentLayer.OVER)
        result = visible_worn_items_for(self.character, observer=staff_character)
        self.assertEqual(len(result), 2)

    def test_non_staff_observer_in_other_room_sees_only_visible(self) -> None:
        observer = CharacterFactory(db_key="OtherChar")
        shirt = self._make_item("Shirt", BodyRegion.TORSO, EquipmentLayer.BASE)
        coat = self._make_item("Coat", BodyRegion.TORSO, EquipmentLayer.OVER, covers=True)
        self._equip(shirt, BodyRegion.TORSO, EquipmentLayer.BASE)
        self._equip(coat, BodyRegion.TORSO, EquipmentLayer.OVER)
        result = visible_worn_items_for(self.character, observer=observer)
        names = [v.item_instance.display_name for v in result]
        self.assertEqual(names, ["Coat"])

    def test_naked_character_returns_empty(self) -> None:
        result = visible_worn_items_for(self.character)
        self.assertEqual(result, [])
```

### Step 2: Run, verify failure

```bash
echo "yes" | uv run --directory /c/Users/apost/PycharmProjects/arxii arx test world.items.tests.test_appearance_service --keepdb -v 2
```

Expected: ImportError.

### Step 3: Implement

Create `src/world/items/services/appearance.py`:

```python
"""Visibility computation for worn equipment."""

from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Prefetch

from core_management.permissions import is_staff_observer
from world.items.constants import EquipmentLayer
from world.items.models import EquippedItem, TemplateSlot


# Order from lowest (closest to skin) to highest (farthest away).
_LAYER_ORDER = (
    EquipmentLayer.SKIN,
    EquipmentLayer.UNDER,
    EquipmentLayer.BASE,
    EquipmentLayer.OVER,
    EquipmentLayer.OUTER,
    EquipmentLayer.ACCESSORY,
)
_LAYER_RANK = {layer.value: idx for idx, layer in enumerate(_LAYER_ORDER)}


@dataclass(frozen=True)
class VisibleWornItem:
    """One visible piece of a character's worn equipment."""

    item_instance: object  # ItemInstance — avoiding the import cycle here
    body_region: str
    equipment_layer: str


def visible_worn_items_for(character, observer=None) -> list[VisibleWornItem]:
    """Return the character's worn items visible to ``observer``.

    Walks ``EquippedItem`` rows for ``character`` and applies per-(region,
    layer) hiding via ``TemplateSlot.covers_lower_layers``.

    Layer hiding is bypassed when:
        - ``observer is character`` (looking at yourself), OR
        - ``observer`` is a staff user (via ``is_staff_observer``).

    ``observer=None`` applies hiding (default-restrictive).
    """
    bypass_hiding = observer is character or is_staff_observer(observer)

    rows = list(
        EquippedItem.objects.filter(character=character)
        .select_related(
            "item_instance",
            "item_instance__template",
        )
        .prefetch_related(
            Prefetch(
                "item_instance__template__slots",
                queryset=TemplateSlot.objects.all(),
                to_attr="cached_slots",
            ),
        )
    )

    if bypass_hiding:
        return [
            VisibleWornItem(
                item_instance=row.item_instance,
                body_region=row.body_region,
                equipment_layer=row.equipment_layer,
            )
            for row in rows
        ]

    # Group by region; per region, find the highest layer with a covering slot.
    region_to_rows: dict[str, list[EquippedItem]] = {}
    for row in rows:
        region_to_rows.setdefault(row.body_region, []).append(row)

    visible: list[VisibleWornItem] = []
    for region, region_rows in region_to_rows.items():
        # Sort by layer rank (low → high).
        region_rows.sort(key=lambda r: _LAYER_RANK.get(r.equipment_layer, 99))

        # Find highest covering layer index.
        cover_idx = -1
        for idx, row in enumerate(region_rows):
            slot = _find_slot(row, region)
            if slot is not None and slot.covers_lower_layers:
                cover_idx = max(cover_idx, idx)

        # Items at index >= cover_idx are visible (cover_idx == -1 means all visible).
        for idx, row in enumerate(region_rows):
            if idx >= cover_idx:
                visible.append(
                    VisibleWornItem(
                        item_instance=row.item_instance,
                        body_region=row.body_region,
                        equipment_layer=row.equipment_layer,
                    )
                )

    return visible


def _find_slot(row: EquippedItem, region: str) -> TemplateSlot | None:
    """Return the TemplateSlot for ``row``'s template at ``region``."""
    template = row.item_instance.template
    slots = getattr(template, "cached_slots", None) or list(template.slots.all())
    for slot in slots:
        if slot.body_region == region and slot.equipment_layer == row.equipment_layer:
            return slot
    return None
```

Update `src/world/items/services/__init__.py`:

```python
from world.items.services.appearance import VisibleWornItem, visible_worn_items_for
# ... add to __all__
```

### Step 4: Run, verify pass

```bash
echo "yes" | uv run --directory /c/Users/apost/PycharmProjects/arxii arx test world.items.tests.test_appearance_service --keepdb -v 2
```

Expected: 8 tests pass.

### Step 5: Commit

```bash
git -C /c/Users/apost/PycharmProjects/arxii commit -am "feat(items): visible_worn_items_for service with self/staff bypass"
```

---

## Task 4: CharacterState appearance extension

**Files:**
- Modify: `src/flows/object_states/character_state.py`
- Modify: `src/flows/tests/test_character_state.py` (or wherever existing CharacterState tests live; create if needed)

### Step 1: Failing tests

Add tests for:
- `get_display_worn(looker)` returns formatted "Wearing: ..." string for visible items
- `get_display_worn` returns empty string for naked character
- `get_display_status(looker)` returns empty string (placeholder)
- `return_appearance` includes the worn line when items present
- `return_appearance` omits the worn line when no items

### Step 2-5: Implement, run, commit

Add to `CharacterState`:

```python
from evennia.utils.utils import iter_to_str
from world.items.services.appearance import visible_worn_items_for


def get_display_worn(self, looker=None, **kwargs) -> str:
    """Return the visible worn equipment as look-output text."""
    observer = looker.obj if looker is not None and hasattr(looker, "obj") else None
    visible = visible_worn_items_for(self.obj, observer=observer)
    if not visible:
        return ""
    names = iter_to_str(
        (v.item_instance.display_name for v in visible),
        endsep=", and",
    )
    return f"|wWearing:|n {names}."


def get_display_status(self, looker=None, **kwargs) -> str:
    """Placeholder for narrative status (parked in combat roadmap)."""
    return ""
```

Update `appearance_template`:

```python
@property
def appearance_template(self) -> str:
    return (
        "{name}\n"
        "{desc}"
        "{status_section}"
        "{worn_section}"
    )
```

(Use empty-string-prefix sections so they collapse cleanly when empty. The implementer picks the cleanest format string approach — could be straight `{worn}` with the rendering method returning a leading `\n` when non-empty, or section-style as above.)

Override `return_appearance` to pass the new slots:

```python
def return_appearance(self, mode: str = "look", **kwargs) -> str:
    looker = kwargs.get("looker")
    name = self.get_display_name(looker, **kwargs)
    desc = self.get_display_desc(mode=mode, **kwargs)
    worn = self.get_display_worn(looker, **kwargs)
    status = self.get_display_status(looker, **kwargs)
    appearance = self.appearance_template.format(
        name=name,
        desc=desc,
        status_section=f"\n{status}" if status else "",
        worn_section=f"\n{worn}" if worn else "",
    )
    return self.format_appearance(appearance, **kwargs)
```

Commit message: `feat(flows): CharacterState renders visible worn equipment in look output`

---

## Task 5: Telnet `look <person>'s <item>` parser + LookAtItemAction

**Files:**
- Modify: `src/commands/evennia_overrides/perception.py`
- Modify: `src/actions/definitions/perception.py` — add `LookAtItemAction`
- Modify: `src/actions/registry.py` — register
- Modify: `src/actions/tests/test_base.py` — add `look_at_item` to expected keys
- Create: `src/actions/tests/test_look_at_item_action.py`
- Modify: `src/commands/tests/test_dispatchers.py` — add CmdLook parser tests

### Step 1: Tests

Action tests (`test_look_at_item_action.py`):

1. `test_visible_item_returns_appearance` — owner has the item visibly worn → action returns success with the item description.
2. `test_concealed_item_returns_failure` — owner has the item but it's concealed under a covering layer → returns ActionResult(success=False, "You don't see anything by that name on them.")
3. `test_self_can_see_concealed` — actor IS the owner; concealed item is visible to self.
4. `test_staff_can_see_concealed` — actor is staff (set via account.is_staff); concealed item visible.
5. `test_in_container_form_open_returns_appearance` — `container` kwarg; container is open; item is in contents.
6. `test_in_container_form_closed_returns_failure` — container is closed → "That container is closed."

Parser tests (`test_dispatchers.py`):

1. `test_possessive_form_dispatches_look_at_item_action` — `cmd.args = "bob's hat"` → cmd.action becomes `LookAtItemAction`, kwargs include `owner=bob, item=hat`.
2. `test_on_form_dispatches_look_at_item_action` — `cmd.args = "hat on bob"` → same dispatch.
3. `test_in_form_dispatches_look_at_item_action` — `cmd.args = "coin in pouch"` → dispatch with `container=pouch, item=coin`.
4. `test_plain_form_unchanged` — `cmd.args = "bob"` → still dispatches to `LookAction` with `target=bob`.
5. `test_possessive_unknown_owner_raises_command_error`.

### Step 2-5: Implement, run, commit

Parser extension in `CmdLook.resolve_action_args`:

```python
import re
from actions.definitions.perception import LookAtItemAction
# ...

POSSESSIVE_RE = re.compile(r"^(.+?)'s\s+(.+)$", flags=re.IGNORECASE)
ON_RE = re.compile(r"^(.+?)\s+on\s+(.+)$", flags=re.IGNORECASE)
IN_RE = re.compile(r"^(.+?)\s+in\s+(.+)$", flags=re.IGNORECASE)


def resolve_action_args(self):
    args = (self.args or "").strip()
    if not args:
        target = self.caller.location
        return {"target": target}

    # Try the three "drilled" forms in priority order.
    if match := POSSESSIVE_RE.match(args):
        owner_name, item_name = match.group(1).strip(), match.group(2).strip()
        return self._dispatch_look_at_worn(owner_name, item_name)
    if match := ON_RE.match(args):
        item_name, owner_name = match.group(1).strip(), match.group(2).strip()
        return self._dispatch_look_at_worn(owner_name, item_name)
    if match := IN_RE.match(args):
        item_name, container_name = match.group(1).strip(), match.group(2).strip()
        return self._dispatch_look_at_contained(item_name, container_name)

    target = self.caller.search(args)
    if not target:
        raise CommandError(f"Could not find '{args}'.")
    return {"target": target}


def _dispatch_look_at_worn(self, owner_name, item_name):
    owner = self.caller.search(owner_name)
    if not owner:
        raise CommandError(f"Could not find '{owner_name}'.")
    self.action = LookAtItemAction()
    return {"owner_id": owner.pk, "item_name": item_name}


def _dispatch_look_at_contained(self, item_name, container_name):
    container = self.caller.search(container_name)
    if not container:
        raise CommandError(f"Could not find '{container_name}'.")
    self.action = LookAtItemAction()
    return {"container_id": container.pk, "item_name": item_name}
```

(The `owner_id` / `container_id` kwargs feed through the inputfunc resolver; with the staff-bypass groundwork in place from the prior PR, these resolve to ObjectDB. The `item_name` stays a string; `LookAtItemAction.execute` handles the string-name lookup against the owner's visible worn items / container contents.)

Implement `LookAtItemAction` in `actions/definitions/perception.py` per the design doc. Register in registry. Update test_base expected keys.

Commit message: `feat(commands): CmdLook parses possessive/on/in forms and dispatches LookAtItemAction`

---

## Task 6: REST endpoints — visible-worn list + visible-item-detail

**Files:**
- Modify: `src/world/items/views.py` — add `VisibleWornItemViewSet`, `VisibleItemDetailViewSet`
- Modify: `src/world/items/serializers.py` — add `VisibleWornItemSerializer` (slim)
- Modify: `src/world/items/filters.py` — add `VisibleWornItemFilter`
- Modify: `src/world/items/urls.py` — register
- Create: `src/world/items/tests/test_visible_worn_views.py`

### Endpoint shape

`GET /api/items/visible-worn/?character=N` — returns slim list `[{id, item_instance: {id, display_name}, body_region, equipment_layer}, ...]` for the character. Visibility scoped to:
- The requester is in the same room as the character, OR
- The requester is staff (bypass), OR
- The requester IS the character (self-look).

`GET /api/items/visible-item-detail/<id>/` — full item detail (mirroring the existing `ItemInstanceReadSerializer`) for items currently visibly worn by characters in the requester's room (or staff, or self).

Both use `PlayerOrStaffPermission` from Task 1. The queryset filtering does the same-room scoping.

### Tests (10+ scenarios)

- Unauthenticated → 401/403
- Same-room observer → returns visible items only (concealed not in list)
- Different-room observer → empty list (or 403; pick one — empty list is friendlier and matches "they're not in your room so the answer is nothing")
- Self-look → returns everything including concealed
- Staff observer → returns everything from anywhere
- Detail endpoint: visible item → full data
- Detail endpoint: concealed item → 404 (would-leak-information attack)
- Detail endpoint: staff → can fetch concealed
- Detail endpoint: item from another room → 404

### Step 5: Commit

`feat(items): visible-worn and visible-item-detail REST endpoints with same-room scoping`

---

## Task 7: Frontend — focus stack state

**Files:**
- Modify: `frontend/src/game/components/RoomPanel.tsx` — rename to `FocusPanel.tsx` OR keep filename and add focus stack state inside. Pick whichever causes less churn.
- Modify: `frontend/src/game/components/SidebarTabPanel.tsx` — accept dynamic tab label for the room/focus tab
- Create: `frontend/src/inventory/hooks/useFocusStack.ts` — hook + provider for the focus stack state
- Create: `frontend/src/inventory/components/__tests__/useFocusStack.test.tsx`

### State model

```typescript
type FocusEntry =
  | { kind: 'room'; roomData: RoomData; sceneData: SceneSummary | null }
  | { kind: 'character'; character: { id: number; name: string } }
  | { kind: 'item'; item: { id: number; name: string } };

function useFocusStack(initialRoom: FocusEntry) {
  const [stack, setStack] = useState<FocusEntry[]>([initialRoom]);
  const current = stack[stack.length - 1];
  const push = (entry: FocusEntry) => setStack(s => [...s, entry]);
  const pop = () => setStack(s => s.length > 1 ? s.slice(0, -1) : s);
  const reset = (entry: FocusEntry) => setStack([entry]);
  return { current, push, pop, reset, depth: stack.length };
}
```

The hook lives in `inventory/hooks/` because the focus-stack abstraction conceptually belongs to inventory/wardrobe-style "drill into things" navigation. Could move to `game/hooks/` if more general use cases emerge.

Tests: push, pop bounds, reset, depth tracking.

Commit: `feat(frontend): focus stack hook for the right-sidebar drill navigation`

---

## Task 8: Frontend — CharacterFocusView + ItemFocusView components

**Files:**
- Create: `frontend/src/inventory/components/CharacterFocusView.tsx`
- Create: `frontend/src/inventory/components/ItemFocusView.tsx`
- Create: `frontend/src/inventory/hooks/useVisibleWornItems.ts` — react-query hook for the new endpoint
- Create: `frontend/src/inventory/hooks/useVisibleItemDetail.ts`
- Create test files for each component

### `CharacterFocusView`

Props: `character: { id; name }`, `onItemClick: (item) => void`.

Renders:
- Header: character name + thumbnail (if available)
- Description (markdown, via the existing `react-markdown` setup from Phase A)
- Status placeholder slot (`<div data-placeholder="status" />`, hidden until combat follow-up lands)
- Visible worn items list — each row clickable

Data via `useVisibleWornItems(character.id)`.

### `ItemFocusView`

Props: `item: { id; name }`, optional `onActionClick?` for "wear/drop/etc." (only shown if the viewer can act on the item).

Reuses the existing `ItemDetailPanel` content — large image, markdown description, quality tier color accent, facets, weight/size/value. Slim variant since the sidebar is narrower than the Sheet drawer; use a single column layout instead of two-column.

Data via `useVisibleItemDetail(item.id)`.

Tests: each renders without crashing, click handlers fire, loading and empty states present.

Commit: `feat(frontend): CharacterFocusView + ItemFocusView for the focus stack`

---

## Task 9: Frontend — `RoomPanel` → `FocusPanel` evolution

**Files:**
- Modify: `frontend/src/game/components/RoomPanel.tsx` (or create `FocusPanel.tsx` and re-export `RoomPanel`)
- Modify: `frontend/src/game/components/SidebarTabPanel.tsx` — accept dynamic label
- Modify: `frontend/src/game/GamePage.tsx` — wire the focus stack into the right sidebar

### Behavior

When `currentFocus.kind === 'room'`: render the existing `RoomPanel` body (header, description, characters list, exits, objects).

When `currentFocus.kind === 'character'`: render `<CharacterFocusView character={currentFocus.character} onItemClick={item => push({kind: 'item', item})} />`.

When `currentFocus.kind === 'item'`: render `<ItemFocusView item={currentFocus.item} />`.

Above all: a back button (only shown when `depth > 1`) that calls `pop()`.

Click handlers:
- `CharactersList` (in `RoomPanel`): clicking a character calls `push({kind: 'character', ...})`.
- `CharactersList` worn items list (inside the new `CharacterFocusView`): clicking a worn item calls `push({kind: 'item', ...})`.

### Dynamic tab label

`SidebarTabPanel` accepts a `roomTabLabel` prop. `GamePage` computes:

```typescript
const roomTabLabel = (() => {
  switch (focusStack.current.kind) {
    case 'room': return focusStack.current.roomData?.name ?? 'Room';
    case 'character': return focusStack.current.character.name;
    case 'item': return focusStack.current.item.name;
  }
})();
```

Or simpler: keep "Room" as the icon-only label (the icon already conveys "room"), and let the label show the focus name only when not in room mode. Implementer's call based on what looks better.

Tests: tab label updates with focus, back button shows/hides at right depth, click on character pushes correctly.

Commit: `feat(frontend): right-sidebar room panel evolves into a focus stack with dynamic tab`

---

## Task 10: Wire click handlers + WardrobePage compatibility

**Files:**
- Modify: `frontend/src/game/components/room-panel/CharactersList.tsx` — accept onCharacterClick prop, wire to focus push
- Modify: `frontend/src/game/components/room-panel/ObjectsList.tsx` — same for objects (push items into focus stack on click)
- Possibly: existing components that render character names (event participant lists, story participant lists, etc.) — keep them with their current click behavior; we don't want to globally hijack character clicks. Only the room panel's CharactersList integrates with the focus stack.

Tests: scene view click on character → focus stack push, click on item → focus stack push, click on existing wardrobe page item still uses ItemDetailPanel (NOT the focus panel — different surface).

Commit: `feat(frontend): wire room panel character/item clicks into the focus stack`

---

## Task 11: Final regression + roadmap update

### Step 1: Targeted regression

```bash
echo "yes" | uv run --directory /c/Users/apost/PycharmProjects/arxii arx test world.items actions commands flows core_management web --keepdb
```

### Step 2: Broader sanity

```bash
echo "yes" | uv run --directory /c/Users/apost/PycharmProjects/arxii arx test world --keepdb
```

### Step 3: Frontend

```bash
cd /c/Users/apost/PycharmProjects/arxii/frontend && pnpm typecheck && pnpm lint && pnpm test && pnpm build
```

### Step 4: Roadmap

Update `docs/roadmap/items-equipment.md` — add a "Visible Worn Equipment (DONE)" section listing what shipped:
- Visibility computation service
- CharacterState appearance extension
- Telnet possessive / on / in parsing + LookAtItemAction
- Visible-worn / visible-item-detail REST endpoints
- Frontend focus stack with dynamic tab label
- Cross-cutting: PlayerOnly/PlayerOrStaff permission bases + is_staff_observer helper

Note still pending:
- Narrative status display (combat roadmap follow-up)
- Examining items in containers belonging to others
- Right-click context menu on worn items

### Step 5: Commit + push

```bash
git -C /c/Users/apost/PycharmProjects/arxii commit -am "docs(items): mark visible worn equipment complete in roadmap"
git -C /c/Users/apost/PycharmProjects/arxii push -u origin visible-worn-equipment
```

---

## Risks and mitigations

- **Audit / refactor of existing permission classes** (Task 2) is the highest-risk piece. The refactor must preserve behavior exactly. If a refactored class has different behavior in any scenario that an existing test exercises, the test will fail and the implementer must back out and report. Don't bypass this.
- **`return_appearance` override on `CharacterState`** could conflict with existing tests that exercise the room/character view. Run `arx test flows world` after the change.
- **REST endpoint scoping is a privacy gate.** `VisibleWornItemViewSet` and `VisibleItemDetailViewSet` must NOT leak items to characters in different rooms. Tests should specifically exercise this scenario; if any test passes when it should fail (e.g., different-room observer can fetch), back out.
- **Frontend focus stack and existing tests:** the existing wardrobe page from Phase A uses `ItemDetailPanel` as a `Sheet` drawer (not in the sidebar). Don't accidentally change that — Phase A wardrobe-page tests must continue to pass.

## Out-of-scope follow-ups

- Narrative status display (combat roadmap)
- Examining items in containers belonging to others
- Right-click context menu on worn items ("compliment outfit", "ask about")
- Privacy gates beyond layer hiding (e.g., magical-disguise items, hidden daggers)

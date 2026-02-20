# Areas System

Spatial hierarchy for organizing rooms into buildings, neighborhoods, wards, cities, regions, kingdoms, continents, worlds, and planes.

**Source:** `src/world/areas/`

---

## Enums (constants.py)

```python
from world.areas.constants import AreaLevel
# BUILDING(10), NEIGHBORHOOD(20), WARD(30), CITY(40), REGION(50),
# KINGDOM(60), CONTINENT(70), WORLD(80), PLANE(90)
```

---

## Models

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `Area` (SharedMemoryModel) | A spatial hierarchy node at a specific level | `name`, `level` (AreaLevel), `parent` (self-FK), `realm` (FK to `realms.Realm`), `description` |
| `AreaClosure` | Read-only materialized view for transitive closure | `ancestor` (FK), `descendant` (FK), `depth` |

---

## Key Methods

### Area Model

```python
from world.areas.models import Area

# Validation on save: child level must be < parent level, no circular chains
area = Area(name="Market District", level=AreaLevel.NEIGHBORHOOD, parent=city_area)
area.save()  # Runs full_clean() and refreshes AreaClosure materialized view

area.delete()  # Also refreshes AreaClosure
```

### Service Functions

```python
from world.areas.services import (
    get_ancestry,            # Full ancestor chain from root down to area
    get_ancestor_at_level,   # Find ancestor at specific AreaLevel
    get_effective_realm,     # Walk up hierarchy to find nearest realm
    get_descendant_areas,    # All areas in the subtree below
    get_rooms_in_area,       # All RoomProfiles in area and descendants
    reparent_area,           # Move area under a new parent (auto-refreshes closure)
    get_room_profile,        # Get or create RoomProfile for a room ObjectDB
)
```

### Ancestry Queries (via AreaClosure materialized view)

```python
from world.areas.services import get_ancestry, get_ancestor_at_level, get_effective_realm
from world.areas.constants import AreaLevel

# Get full ancestry (single indexed query via materialized view)
ancestry = get_ancestry(market_area)
# Returns: [Plane, World, Continent, Kingdom, Region, City, Ward, Market District]

# Find the city this area belongs to
city = get_ancestor_at_level(market_area, AreaLevel.CITY)

# Walk up to find the nearest realm assignment
realm = get_effective_realm(market_area)
```

### Room Queries

```python
from world.areas.services import get_rooms_in_area

# Get all rooms in an area and everything beneath it
rooms = get_rooms_in_area(city_area)
# Returns list of RoomProfile instances with objectdb and area select_related
```

---

## AreaClosure Materialized View

The `AreaClosure` model is backed by a Postgres materialized view that stores every ancestor-descendant pair with depth. This enables efficient ancestry and descendant queries without recursive CTEs at query time.

- **Refreshed automatically** when any `Area` is saved or deleted via `refresh_area_closure()`
- **Not Django-managed** (`managed = False`), created via migration with raw SQL
- Enables single-query ancestry lookups instead of walking parent chains

```python
from world.areas.models import AreaClosure, refresh_area_closure

# Direct query: find all ancestors of an area
AreaClosure.objects.filter(descendant=area).order_by("-depth")

# Direct query: find all descendants
AreaClosure.objects.filter(ancestor=area, depth__gt=0)

# Manual refresh (normally automatic)
refresh_area_closure()
```

---

## Admin

- `AreaAdmin` - List with name, level, parent, realm; filterable by level and realm; autocomplete for parent and realm

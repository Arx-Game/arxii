# Realms System

Canonical game world realms for geographical and political organization.

**Source:** `src/world/realms/`

---

## Enums (constants.py)

```python
from world.realms.constants import RealmTheme
# Values: DEFAULT, ARX, UMBROS, LUXEN, INFERNA, ARIWN, AYTHIRMOK
```

---

## Models

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `Realm` | A game world realm (e.g., Arx, Luxen, Umbros) | `name` (unique), `description`, `crest_asset`, `theme` (RealmTheme) |

---

## Key Methods

```python
from world.realms.models import Realm

realm = Realm.objects.get(name="Arx")
realm.slug   # Property: slugify(name) -> "arx"
realm.theme  # RealmTheme value for frontend visual theming
```

---

## Integration Points

- **Societies**: `Society.realm` - societies belong to a realm
- **Character Sheets**: `CharacterSheet.origin_realm` - character's homeland
- **Character Creation**: `StartingArea.realm` - starting areas reference a realm
- **Areas**: `Area.realm` - spatial hierarchy nodes can belong to a realm

---

## Admin

- `RealmAdmin` - Simple list with name and theme; searchable by name

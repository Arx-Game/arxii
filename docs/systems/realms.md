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
| `Realm` | A game world realm (e.g., Arx, Luxen, Umbros) | `name` (unique), `formal_name` (the long name under the page title, #3725), `description`, `crest_asset`, `theme` (RealmTheme) |
| `RealmTestamentSection` | One movement of the realm's testament, the pitch its page opens on (#3725); credited content (ADR-0201) | `realm` FK (`testament_sections`), `sort_order` (unique per realm), `body`, `motto` (the line the movement ends on) |

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

- `RealmAdmin` - name, formal name and theme; searchable; a `RealmTestamentSectionInline` (sort order, body, motto) for the testament. The testament is entered here and lives only here (ADR-0238).

---

## Public API (#3725, ADR-0285; amends ADR-0227)

`/api/realms/` (`world.realms.views.RealmViewSet`, `AllowAny`, unpaginated, `?theme=`
filter). Read-only; nothing on the realm page writes.

| Endpoint | Purpose |
|---|---|
| `GET /api/realms/` | The Realms hub: every `Realm` row as `{id, name, slug, formal_name, theme, first_motto}` (the motto of the lowest-ordered section, blank when none). Ungated, so a starting area's access level never hides its realm |
| `GET /api/realms/<slug>/` | The realm page: the list fields plus `threshold_line` (`TESTAMENT_THRESHOLD_LINE`), `sections` (movements in order), `societies` (`{id, name, description, enforcer_name}` of `Society.realm`, nothing of principles or reputation), `starting_area` (`{id, name, crest_image}`, the viewer-accessible area first by name, or null) |
| `GET /api/realms/<slug>/organizations/` | The realm's houses and organizations through `OrganizationShopWindowSerializer` (`id, name, description, words, colors, sigil_description, org_type_name, society_name`); covenants excluded; a covert kind (#2820) appears only to a viewer whose active persona holds a live membership in that row |
| `GET /api/realms/<slug>/notables/` | The realm's two boards, `{renown: [RankingRow], legend: [RankingRow]}` through `RankingRowSerializer` (name and band label, never a number); `get_realm_renown_top_n` / `get_realm_legend_top_n` in `societies.ranking_services` over `realm_notable_personas` (the PRIMARY persona of every sheet whose true profile is from the realm and whose roster entry is on the public Active roster). Read-time, nothing stored; #676's "per-realm rankings" addition |

The slug is derived (`Realm.slug`, slugified name), resolved over the rows by
`world.realms.services.realm_by_slug`; there is no stored slug column. The same lookup
backs the roster read's `?realm=<slug>` filter (`RosterEntryFilterSet.realm`, on the
sheet's true profile `origin_realm`) and `StartingAreaSerializer.realm_slug` /
`realm_name`, which the front page's realm row and the Origin index entry use for their
link to the realm page.

The landing page still reads its realm pitch content off the starting-area read
(ADR-0227); that read stays. ADR-0227's rejection of a realms API is amended by
ADR-0285: the realm now carries content of its own (the testament) that no other row
holds, which is the capability gain ADR-0227 said was missing.

## Frontend (`frontend/src/realms/`)

- `/realms` (`RealmsHubPage`): six cards, each in its realm's palette (`data-realm` on
  the card, as the landing page's realm rows do), each only name, formal name and first
  motto, each a link. Reached from World › Realms, one plain link.
- `/realms/:slug` (`RealmPage`): the realm's palette for the visit (`setForcedRealm`,
  restored on leaving), the testament in movements with their motto lines, a sticky
  rail above it (Testament, Societies, Houses and organizations, Names spoken here,
  Characters), the hub sections with an empty line each, and a hand-off to
  `/roster?realm=<slug>` (the roster page reads the slug and offers a realm select).
- Copy on the page is interface chrome (plain labels); the only prose is the testament.

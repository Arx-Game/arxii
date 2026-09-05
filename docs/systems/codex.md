# Codex System

Lore storage and character knowledge tracking with teaching mechanics and clue-based research.

**Source:** `src/world/codex/`
**API Base:** `/api/codex/`

---

## Enums (constants.py)

```python
from world.codex.constants import CodexKnowledgeStatus
# UNCOVERED - Character is aware of / learning this entry
# KNOWN     - Character has fully learned this entry
```

---

## Models

### Lore Structure (SharedMemoryModel - cached, rarely change)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `CodexCategory` | Top-level lore category (e.g., "Arx Lore", "Umbral Lore") | `name`, `description`, `display_order` |
| `CodexSubject` | Nestable subject within a category | `category`, `parent` (self-FK, nullable), `name`, `description`, `display_order` |
| `CodexEntry` | Individual lore entry that can be learned/taught | `subject`, `name`, `summary`, `lore_content`, `mechanics_content`, `prerequisites` (M2M self), `share_cost`, `learn_cost`, `learn_difficulty`, `learn_threshold`, `is_public`, `modifier_target` (OneToOne to `mechanics.ModifierTarget`), `subject_item_template`/`subject_item_instance` (nullable FKs → `items.ItemTemplate`/`ItemInstance`, #2540 exact-pointer ruling — optional "this entry is about an item" pointer, instance narrows template) |

### Character Knowledge (models.Model - per-character instances)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `CharacterCodexKnowledge` | Tracks what a character knows or is learning | `roster_entry`, `entry`, `status` (CodexKnowledgeStatus), `learning_progress`, `learned_from` (RosterTenure), `learned_at` |
| `CodexClue` | A clue that hints at a codex entry and grants research progress | `entry`, `name`, `description`, `research_value` |
| `CharacterClueKnowledge` | Tracks which clues a character has found | `roster_entry`, `clue`, `found_at` |

### Teaching (models.Model)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `CodexTeachingOffer` | Teaching offer from one tenure to others (uses `VisibilityMixin`) | `teacher` (RosterTenure), `entry`, `pitch`, `gold_cost`, `banked_ap`, visibility fields from mixin |

### CG Grant Tables (models.Model - link CG choices to codex entries)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `BeginningsCodexGrant` | Codex entries granted by a Beginnings choice | `beginnings`, `entry`, `is_perspective` |
| `PathCodexGrant` | Codex entries granted by a Path choice | `path`, `entry` |
| `DistinctionCodexGrant` | Codex entries granted by a Distinction | `distinction`, `entry` |
| `TraditionCodexGrant` | Codex entries granted by a Tradition | `tradition`, `entry`, `is_perspective` |

Species are the exception: there is no `SpeciesCodexGrant` table. `Species.codex_entry`
is a plain nullable FK on the species row (one entry per species, not many), and
`_finalize_species_codex` walks `Species.parent` so a subspecies character receives
its own entry *and* every ancestor's — see `docs/systems/species.md`.

---

## Filing an entry under a second subject (ADR-0270)

`CodexEntry.subject` stays the entry's one canonical home: its detail page lives
there, and it is the subject `resolve_codex_links` prefers when a wikilink could
match more than one entry. `CodexEntryFiling(entry, subject, sort_order)` is a
separate cross-listing: it puts the entry in a second subject's listing without
moving it or duplicating its `lore_content`/`mechanics_content`. An entry may have
any number of filings, one per additional subject (unique on `(entry, subject)`);
`sort_order` controls display position within that subject's listing, mirroring
`CodexEntry.display_order` for the entry's own subject.

`world.codex.services.file_entry_under(entry, subject, *, sort_order=0)` and
`unfile_entry(entry, subject)` are the only sanctioned mutation path:

- `file_entry_under` raises `ValidationError` when `subject` is the entry's own
  `entry.subject`, since that would duplicate the entry's canonical listing rather than add a
  second one. It is idempotent: filing the same `(entry, subject)` pair twice
  returns the existing row rather than raising `IntegrityError`.
- `unfile_entry` removes a filing if one exists and is a no-op otherwise.

Both directions are navigable: `entry.filings` (all of an entry's cross-listings)
and `subject.filed_entries` (all filings pointing at a subject). Deleting either
the entry or the subject CASCADEs and removes the filing row.

`CodexEntryFiling` carries `NaturalKeyMixin` on `(entry, subject)` and joins
`CONTENT_MODELS` (`core_management/content_export.py`) right after
`codex.codexentry`, so filings round-trip through the content export/import
pipeline the same as the entries they point at.

---

## Perspective entries (#3277, #3281; ADR-0222, ADR-0224)

A `BeginningsCodexGrant` or `TraditionCodexGrant` row with `is_perspective=True`
marks the entry as the granting culture's or tradition's own take on its
subject - a canon-accurate record of a biased in-world voice, not canon-neutral
knowledge the holder happens to teach. Each table caps its own holders at one
per entry with a partial unique constraint on `entry`
(`condition=Q(is_perspective=True)`): `one_perspective_holder_per_entry` on
`BeginningsCodexGrant`, `one_tradition_perspective_holder_per_entry` on
`TraditionCodexGrant`. That per-table constraint cannot see across tables, so
an entry has at most one perspective holder overall, not one per table: both
models' `clean()` additionally queries the other table and rejects a second
holder there.

The holder surfaces as `perspective_of` on the entry list and detail payloads: a
`Coalesce` of two `Subquery` annotations in `CodexEntryViewSet.get_queryset`
resolves the perspective holder's `beginnings__name` first, falling back to
`tradition__name`, and `EntryKnowledgeMixin.get_perspective_of` (shared by
both entry serializers) reads the annotation. The frontend renders it as an "As told
by {perspective_of}" attribution line in both `EntryDetail.tsx` and `CodexModal.tsx`.

Granting is viewer-only: creating the flagged grant row does not itself teach anyone
anything, so the viewed culture's own characters discover other cultures' takes on
them the same way they discover any other codex entry, in play. Species perspectives
are deferred - there is no `SpeciesCodexGrant` table for the flag to live on (see
above), so a species-level perspective would need that table to exist first.

**CG shop-window endpoints (ADR-0224).** Mid-chargen players have no roster entry, so
`CharacterCodexKnowledge` rows don't exist yet and non-public entries (which most
perspective entries are) stay invisible through `/api/codex/`. Two ungated detail
actions serve perspective content straight from the grant tables while a player is
still choosing, with no codex-knowledge gating: `GET
/api/character-creation/beginnings/{id}/perspectives/` and `GET
/api/character-creation/traditions/{id}/perspectives/` (`world/character_creation`,
not `world/codex`). Both return the same holder-agnostic
`PerspectiveEntrySerializer` shape - `{entry_id, name, summary, lore_content,
subject_name}` - built directly from the `is_perspective=True` grants for that
holder. Codex proper is unchanged by this: the viewed culture still discovers a
stereotype about itself through play, same as always. Corollary authoring rule: a
perspective entry is shop-window content by definition, so it must never carry
secret or spoiler material.

---

## Granting an entry: one path only (#2880)

**`world.codex.services.grant_codex_entry(roster_entry, entry, *, learned_from=None)` is
the only sanctioned way to land a character on KNOWN.** It returns
`(knowledge, newly_known)` and is idempotent.

Landing on KNOWN is not just a column value — it stamps `learned_at` and fires
`world.stories.services.reactivity.on_codex_entry_unlocked`, so `CODEX_ENTRY_UNLOCKED`
beats re-evaluate. That hook lives on `CharacterCodexKnowledge.add_progress`, which #939
chose deliberately: *"a separate service wrapper used to carry the hook and every caller
bypassed it; reactivity now lives on the only path."*

The bypass came back anyway. `add_progress` returns early unless the row is UNCOVERED,
and seven callers were creating rows with `status=KNOWN` directly — all six
character-creation grants (beginnings, path, distinction, tradition, species, gift
resonance) and the crossing ceremony. Those characters got the column value and neither
the timestamp nor the hook. `grant_codex_entry` therefore does **not** set the status
itself: it opens the row UNCOVERED and pushes progress past the threshold, keeping the
transition on the one path that carries the reactivity.

Two callers deliberately create UNCOVERED rows and must keep doing so, because they mean
"you can start researching this," not "you know this":

- the `GRANT_CODEX` consequence effect (`world.mechanics.effect_handlers`) — a scene hands
  you a lead, not the answer;
- `CodexTeachingOffer.accept` — the learner has paid AP and now has to make progress.

**Wired to achievements (#2899).** `CodexEntry` inherits
`world.achievements.models.DiscoverableContent` (a nullable `discovery_achievement` FK),
so a codex entry can carry a discovery achievement the same way Technique and
CovenantRole do. `grant_codex_entry` is the seam that carries it: on `newly_known` it
calls `announce_access_change` (gated on a live, non-staff `RosterTenure` and excluded
for CG-catalog content — see `world/achievements/CLAUDE.md` for the full mechanism) and
increments the `codex.entries_learned` `StatDefinition`.

---

## Key Methods

### CodexSubject

```python
# Get full breadcrumb path from category to this subject
subject.breadcrumb_path  # Returns ["Category Name", "Parent", "Child"]
```

### CodexEntry

```python
# Validation: at least one of lore_content or mechanics_content must be provided
entry.clean()  # Raises ValidationError if both are empty
```

### CharacterCodexKnowledge

```python
# Add learning progress and check for completion
completed = knowledge.add_progress(amount=5)
# Returns True if learning_progress >= entry.learn_threshold (auto-sets KNOWN status)

# Check if fully learned
knowledge.is_complete()  # True if status == KNOWN
```

### CodexTeachingOffer

```python
# Check if a learner can accept this offer
can_accept, reason = offer.can_accept(learner_tenure)
# Checks: not self-teaching, no existing knowledge, prerequisites met, AP affordable

# Accept the offer (atomic transaction)
knowledge = offer.accept(learner_tenure)
# Learner pays AP, teacher's banked AP consumed, creates UNCOVERED knowledge entry
# Raises ValueError if learner cannot accept

# Cancel offer and recover banked AP
restored_ap = offer.cancel()
# Unbanks AP to teacher's pool, deletes the offer
```

---

## API Endpoints

### Categories
- `GET /api/codex/categories/` - List visible categories
- `GET /api/codex/categories/{id}/` - Get category detail (404 when hidden)
- `GET /api/codex/categories/tree/` - Visible categories with visible top-level subjects
  (lazy-loaded tree)

### Subjects
- `GET /api/codex/subjects/` - List visible subjects (filterable)
- `GET /api/codex/subjects/{id}/` - Get subject detail (404 when hidden)
- `GET /api/codex/subjects/{id}/children/` - Lazy-load visible children for tree expansion

**Query Parameters (subjects):**
- `category` - Filter by category ID
- `parent` - Filter by parent subject ID
- `character` - Scope knowledge to one of the account's roster entries (see Visibility Rules)

### Entries
- `GET /api/codex/entries/` - List visible entries (public + entries the reader's
  characters know)
- `GET /api/codex/entries/{id}/` - Get entry detail (content gated by knowledge status)

**Query Parameters (entries):**
- `subject` - Filter by subject ID
- `category` - Filter by category ID (via subject)
- `search` - Search name, summary, lore/mechanics content (min 2 chars)
- `character` - Scope knowledge to one of the account's roster entries

**Visibility Rules (ADR-0221):**
- Anonymous users see only `is_public=True` entries
- Authenticated users see public entries plus the **union** of entries any of their
  playable characters has `CharacterCodexKnowledge` for (`CodexVisibilityMixin` in
  `views.py`); the account's knowledge map is `Account.cached_codex_knowledge` (#3597),
  cleared on every knowledge write, so the mixin holds no per-request state;
  `?character=<roster_entry_id>` narrows the scope to one character, and a
  foreign/unknown id yields public-only (never another player's knowledge)
- Entry serializers expose `known_by` (per-character name/status/progress) alongside
  best-of-union `knowledge_status` and max `research_progress`
- **Containers are hidden when their subtree holds no visible entry**: categories and
  subjects have no visibility of their own, so tree/list/retrieve/children all filter
  out any category/subject without at least one visible entry among its descendants.
  A subject description must not become the public face of a topic with no readable
  entries, and an all-secret branch must not leak its name
- Detail view gates `lore_content` and `mechanics_content` behind KNOWN status or `is_public`

---

## Admin

All models registered with filters, search, and inline editing:

- `CodexCategoryAdmin` - With inline subjects, shows subject count
- `CodexSubjectAdmin` - With inline entries, filterable by category
- `CodexEntryAdmin` - Full editing with fieldsets for content, costs, learning, prerequisites, and modifier type link; `filter_horizontal` for prerequisites; inline `CodexEntryFilingInline` for the entry's secondary subject listings
- `CharacterCodexKnowledgeAdmin` - Read-only debugging with status/progress fields
- `CodexClueAdmin` - Clue management with autocomplete to entries
- `CharacterClueKnowledgeAdmin` - Read-only debugging for found clues
- `CodexTeachingOfferAdmin` - Teaching offer management with visibility controls

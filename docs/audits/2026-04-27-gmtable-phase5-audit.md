# GMTable / GMTableMembership Audit for Phase 5

**Date:** 2026-04-27
**Branch:** `stories-phase-5`
**Purpose:** Inform Wave 1 backend API design for GMTable + Membership endpoints.

---

## GMTable model (current)

**File:** `src/world/gm/models.py` line 114

Fields:

| Field | Type | Notes |
|---|---|---|
| `id` | auto PK | standard |
| `gm` | FK → `gm.GMProfile` | `on_delete=PROTECT`, `related_name="tables"` |
| `name` | CharField(200) | required |
| `description` | TextField | blank=True, default="" |
| `status` | CharField(20) | `GMTableStatus` choices: `active` / `archived`; default `active`; db_index |
| `created_at` | DateTimeField | auto_now_add, db_index |
| `archived_at` | DateTimeField | null, blank — set by `archive_table()` service |

**No `is_active` boolean field.** Active/archived state is carried by `status = GMTableStatus.ACTIVE` / `GMTableStatus.ARCHIVED`.

**No `title` field.** Only `name`.

**No custom manager** — uses the default SharedMemoryModel manager.

**Related objects pointing at GMTable:**

- `GMTableMembership.table` (FK, `related_name="memberships"`)
- `Story.primary_table` (FK, null, `related_name="primary_stories"`)
- `BeatCompletion.gm_table` (FK, null, `related_name="beat_completions"`)
- `EpisodeResolution.gm_table` (FK, null, `related_name="episode_resolutions"`)
- `GroupStoryProgress.gm_table` (FK, `related_name="story_progress"`)

**Factory:** `GMTableFactory` in `src/world/gm/factories.py` — creates via `GMProfileFactory`, sequences `name`.

---

## GMTableMembership model (current)

**File:** `src/world/gm/models.py` line 141

Fields:

| Field | Type | Notes |
|---|---|---|
| `id` | auto PK | standard |
| `table` | FK → `gm.GMTable` | `on_delete=CASCADE`, `related_name="memberships"` |
| `persona` | FK → `scenes.Persona` | `on_delete=PROTECT`, `related_name="gm_table_memberships"` |
| `joined_at` | DateTimeField | auto_now_add |
| `left_at` | DateTimeField | null, blank, db_index — soft-leave mechanism |

**No `is_active` boolean field.** Active membership is represented by `left_at__isnull=True`.

**No `role` field** (no Lead GM / member / guest distinction at the membership level).

**No `gm_profile` field** — membership is anchored to a `Persona` (player's IC face), NOT an account or GMProfile.

**Unique constraint:** `unique_active_gm_table_membership` — partial unique on `(table, persona)` where `left_at IS NULL`. Historical (left) rows can coexist with a new active membership for the same persona.

**Validation:** `clean()` rejects TEMPORARY personas; `save()` calls `full_clean()` to enforce this on direct ORM creates.

**Factory:** `GMTableMembershipFactory` — defaults `persona` to an ESTABLISHED `PersonaFactory`.

---

## Other GM models relevant to Phase 5

**GMProfile** — one per account; carries `level` (GMLevel: STARTING/JUNIOR/GM/EXPERIENCED/SENIOR). The `gm` FK on `GMTable` points here. This is the "who owns the table" anchor. No changes needed for Phase 5.

**GMRosterInvite** — invite system for specific roster characters; not involved in Phase 5 table management or story-offer flow.

**GMApplication / GMApplicationStatus** — GM vetting pipeline; not involved in Phase 5.

---

## Existing API surface

`src/web/urls.py` mounts `world.gm.urls` at `/api/gm/`.

The GM app already has **full CRUD ViewSets** for both models:

| URL pattern | ViewSet | Actions |
|---|---|---|
| `GET/POST /api/gm/tables/` | `GMTableViewSet` | list, create |
| `GET/PUT/PATCH/DELETE /api/gm/tables/:id/` | `GMTableViewSet` | retrieve, update, partial_update, destroy |
| `POST /api/gm/tables/:id/archive/` | `GMTableViewSet` | `@action` — staff only |
| `POST /api/gm/tables/:id/transfer_ownership/` | `GMTableViewSet` | `@action` — staff only |
| `GET/POST /api/gm/table-memberships/` | `GMTableMembershipViewSet` | list, create (join_table service) |
| `GET /api/gm/table-memberships/:id/` | `GMTableMembershipViewSet` | retrieve |
| `DELETE /api/gm/table-memberships/:id/` | `GMTableMembershipViewSet` | destroy = soft-leave |

**Scoping logic already implemented:**
- Staff sees all tables / memberships.
- Non-staff GM sees only tables where `gm__account == request.user`.
- `GMTableMembershipViewSet` for non-staff sees only memberships for tables they own (`table__gm__account == user`).

**Filters already implemented** (`src/world/gm/filters.py`):
- `GMTableFilter`: status, gm (numeric FK)
- `GMTableMembershipFilter`: table (numeric FK), active (boolean method filter on `left_at__isnull`)

**Services already implemented** (`src/world/gm/services.py`):

| Service | Description |
|---|---|
| `create_table(gm, name, description)` | Creates GMTable |
| `archive_table(table)` | Sets status=ARCHIVED, archived_at=now |
| `transfer_ownership(table, new_gm)` | Reassigns gm FK — staff only |
| `join_table(table, persona)` | Idempotent add, rejects TEMPORARY personas |
| `leave_table(membership)` | Soft-leave: sets left_at |
| `soft_leave_memberships_for_retired_persona(persona)` | Integration hook — **no production caller wired yet** |
| `surrender_character_story(gm, story)` | Clears `Story.primary_table` — no API endpoint yet |

**The `surrender_character_story` service exists** but its docstring explicitly notes: "There is currently no 'pick up orphan story' service. Staff or another GM must manually set `primary_table` again."

No API endpoint exposes `Story.primary_table` mutation beyond Django admin. This is the primary gap Wave 2 must fill.

---

## Phase 4 data path (GMQueueView)

`GET /api/stories/gm-queue/` is served by `GMQueueView` in `src/world/stories/views.py` (line 1271).

**Query path:**
```
Story.objects.filter(primary_table__gm=gm_profile, status="active")
```
Then calls `_build_gm_queue_for_story()` per story to populate:
- `episodes_ready_to_run` — episodes with eligible transitions
- `pending_agm_claims` — AGM beat claims awaiting approval
- `assigned_session_requests` — SessionRequests assigned to this GM

**The GMQueueView accesses table-scoped data entirely by walking `Story.primary_table.gm`.** It never touches `GMTable` directly — it uses the story → table → gm path. Wave 1's new `GMTableViewSet` is independent of this view; the view doesn't need to change.

**Reusable helper for Wave 1:** `gm_application_queue(gm)` in `services.py` (line 108) also uses the `story__primary_table__gm=gm` chain. Both queries rely on `Story.primary_table` being the source of truth for table ownership.

---

## Story.primary_table (current)

**Model:** `src/world/stories/models.py`, `Story` line 128.

```python
primary_table = models.ForeignKey(
    "gm.GMTable",
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="primary_stories",
)
```

**Already nullable.** `on_delete=SET_NULL` means if the table is deleted, stories are orphaned automatically. The "seeking GM" state (Phase 5 terminology) is simply `primary_table=None`. No migration needed.

**No mutation API exists** beyond Django admin and the `surrender_character_story` service (which only clears the field, not assigns it). Wave 2 must add assignment + clearing endpoints.

---

## StoryParticipation (current)

**Model:** `src/world/stories/models.py` line 241.

Key fields:

| Field | Type | Notes |
|---|---|---|
| `story` | FK → Story | CASCADE |
| `character` | FK → **`objects.ObjectDB`** | CASCADE — confirmed ObjectDB, NOT CharacterSheet or Persona |
| `participation_level` | CharField | `ParticipationLevel` choices: OPTIONAL / (others) |
| `trusted_by_owner` | BooleanField | default False |
| `joined_at` | DateTimeField | auto_now_add |
| `is_active` | BooleanField | default True |

**ObjectDB anchor confirmed.** The `gm_application_queue` and related queries use `character__story_participations__is_active=True` and traverse `character__story_participations__story__primary_table`.

**No guest vs. full-member distinction** at the StoryParticipation level. `participation_level` exists but only covers OPTIONAL (and possibly other values from `ParticipationLevel` choices, not membership-role semantics).

**No direct link between StoryParticipation and GMTableMembership.** A character can be a story participant without being a table member ("guest story-participant" scenario from Phase 5 design). This distinction is implicit: table member = has active `GMTableMembership`; story guest = in `StoryParticipation` but no `GMTableMembership`.

**Factory:** `GMTableMembershipFactory` uses `PersonaFactory`. `StoryParticipation` factory is in `src/world/stories/factories.py` (not read in this audit but referenced in Phase 4 plan).

---

## Decision points for Wave 1

**Decision A: Role field on GMTableMembership.**

No `role` field exists. The current model has no way to distinguish Lead GM / member / guest at the membership level. The table's GM is identified by `GMTable.gm` (the GMProfile FK), not by a membership row.

Recommendation: **Do not add a role field to `GMTableMembership`.** The "Lead GM" is `table.gm`; "member" is anyone with an active `GMTableMembership`; "guest" is a story participant (`StoryParticipation`) whose persona has no active `GMTableMembership` at that table. This three-tier hierarchy is derivable from existing data without a new field, and matches Phase 5's design intent. Wave 1 serializers should compute and return a `viewer_role` field (e.g., `lead_gm / member / guest / none`) in the table detail response.

**Decision B: `Story.primary_table` nullability.**

Already nullable with `on_delete=SET_NULL`. **No migration needed.** "Seeking GM" state is `primary_table=None`. Wave 2 can build the mutation endpoint on the existing schema immediately.

**Decision C: `StoryParticipation.character` is ObjectDB, not Persona.**

Phase 5's permission layer for "player at table sees only stories they participate in" will need to join `ObjectDB` → `CharacterSheet` → `Persona` to match against `GMTableMembership.persona`. The `gm_application_queue` already does this chain: `character__story_participations__story__primary_table__gm`. Wave 1 should document this join path in the viewset's docstring.

**Decision D: `soft_leave_memberships_for_retired_persona` has no caller.**

The service in `services.py` is a documented stub. Phase 5 Wave 2 (auto-detach on leave) is the table-leave side; this service covers the persona-retirement side. Wave 2 can wire this service into the persona retirement flow if that system exists, or leave the TODO comment in place.

---

## Recommended Wave 1 model adjustments

**No model changes needed.** Wave 1 can build the API on existing models:

- `GMTable` and `GMTableMembership` are fully migrated and factory-backed.
- `GMTableViewSet` and `GMTableMembershipViewSet` already exist with full CRUD, filters, serializers, and correct permission scoping.
- `Story.primary_table` is already nullable — Wave 2 mutation endpoints need zero schema changes.

**The primary work for Wave 1 is:**

1. Verify the existing `GMTableViewSet` covers Phase 5's permission requirements (player-scoped view — currently GMs only see their own tables; players cannot list tables at all). Phase 5 requires players to see tables they are members of. The current viewset's `get_queryset()` returns nothing for non-GM, non-staff users. A player permission tier needs to be added.

2. Extend `GMTableSerializer` to include `member_count`, `story_count`, and a computed `viewer_role` field (derived from `request.user` vs. `table.gm.account` and membership lookup).

3. Add a "my tables" scoping mode for player-facing access: a player should be able to list tables where their personas have active memberships. This requires an additional queryset branch in `get_queryset()`.

4. Add tests for the player access path (`GMTableMembershipViewSet` currently only exposes memberships to the GM who owns the table; players cannot see their own memberships via this endpoint).

**Wave 1 scope note:** These are API extension tasks, not model-creation tasks. All the schema is in place.

---

## Surprises / notes for Wave 1

- The `GMTableMembershipViewSet.perform_create` wraps `join_table()` correctly but notes in a comment that HTTP 201 is returned even on idempotent re-join (existing active membership). This is acceptable but should be documented in the Phase 5 API spec.
- `archive_table()` includes a TODO: orphaned PENDING applications when a table is archived. This is a known gap, not a blocker for Wave 1.
- `surrender_character_story()` comment notes no "pick up orphan story" service exists — Wave 3 (GM re-offer flow) will close this gap.
- `GMTableViewSet.transfer_ownership` reads `new_gm` from `request.data` directly (not via serializer). This is a minor CLAUDE.md violation (`request.data` instead of a serializer), but it's existing code and is staff-only. Wave 1 should not change it unless the tests flag it.

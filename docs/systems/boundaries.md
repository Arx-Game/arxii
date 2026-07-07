# Player Content Boundaries

A private registry that lets a player declare **hard lines** (auto-blocked content
themes, never surfaced to anyone) and **treasured subjects** (specific entities that
require an explicit pre-scene sign-off before they can be staked) — backing the
stakes-contract engine's `check_stake_boundaries` seam (#1770 PR4 stub → #1771). Also
provides a consent-style sharing layer (advisories, not hard lines) and a scene
"lines & veils" aggregate, plus a privacy-safe GM availability read.

**Source:** `src/world/boundaries/` (models, services, DRF surfaces); enforcement +
sign-off + GM availability live in `src/world/stories/` (they touch stories-owned
models — see [Dependency direction](#dependency-direction-boundaries-never-imports-stories)).
**API prefix:** `/api/boundaries/` (+ `/api/treasured-signoffs/`,
`/api/beats/{id}/stake-availability/` on the stories router).
**[BUILT & WIRED]** — every surface below is verified against the committed code.

**Not to be confused with custody (#2001, [custody.md](custody.md)):** a
`TreasuredSubject` is *player*-declared OOC emotional safety (may not even know who an
NPC really is); a `StoryProtectedSubject` is *GM/story*-declared narrative-structure
protection. Same typed-subject-FK shape and `_subject_identity` matching helper,
deliberately separate systems (ADR-0098).

---

## Two matching mechanisms

Boundaries screens a stakes contract with **two independently-evaluated checks**:

1. **Hard lines — coarse, `ContentTheme` intersection.** A player hard-lines a
   staff-authored `ContentTheme` (e.g. "Sexual violence"). A `StakeTemplate` is
   tagged with the `ContentTheme`s its staking would involve
   (`StakeTemplate.content_themes`, M2M). If any participant has hard-lined a theme
   any staked template carries, the **whole contract is blocked** — not just that
   stake. This is a category match, not an identity match: it doesn't matter *which*
   NPC/location/item is at risk, only that the *kind of content* intersects.
2. **Treasured subjects — fine, specific-entity identity match.** A player flags a
   specific entity (their PC's NPC ally, a location, an heirloom item, a faction
   standing, …) as `TreasuredSubject`. If a `Stake`'s wagered subject is
   *identity-equal* to one of a participant's `TreasuredSubject` rows (same
   `subject_kind` and whichever typed FK that kind populates — see
   `_subject_identity` below), that stake **requires an explicit sign-off**
   (`TreasuredSignoff`) before it can activate. Unlike a hard line, this is not a
   block: an active sign-off clears it, and only the flagged stake needs one — its
   siblings on the same contract are unaffected.

Both checks run inside the single `check_stake_boundaries` call (batched, no
per-loop queries); see [Enforcement seam](#enforcement-seam-check_stake_boundaries).

---

## Models (`src/world/boundaries/models.py`)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `ContentTheme` | Staff-authored, coarse content category (NaturalKey on `key`) — mirrors `SocialConsentCategory` | `key` (slug, unique), `name`, `description`, `display_order`, `is_active` |
| `PlayerBoundary` | An OOC player content boundary, owned by `PlayerData` (persists across every character the person plays) | `owner` (PlayerData FK), `kind` (`BoundaryKind`), `theme` (ContentTheme FK, nullable, `PROTECT`), `detail` (staff/audit-only free text for HARD_LINE), `created_at`, + `VisibilityMixin` fields |
| `TreasuredSubject` | A specific entity a player flags as devastating-if-lost, owned by the `RosterTenure` (the character-instance whose attachment it is) | `owner` (RosterTenure FK), `subject_kind` (`TreasuredSubjectKind`), typed subject FKs (below), `subject_label`, `detail`, `created_at`, + `VisibilityMixin` fields |

**`PlayerBoundary.clean()` invariant:** a `HARD_LINE` boundary must name a `theme`
(`ValidationError` if null) and must stay `PRIVATE` visibility (`ValidationError` if
not) — hard lines can never be shared. A DB-level partial unique constraint
(`uniq_hard_line_per_owner_theme`, `Meta.constraints`) additionally prevents the same
owner hard-lining the same theme twice. `PlayerBoundarySerializer.validate()`
duplicates this same invariant at the API layer (the model's `clean()` isn't called
automatically on `ModelViewSet` saves, and m2m fields aren't settable pre-save).

**`TreasuredSubject`'s typed subject FKs** mirror `Stake`'s typed pointers
(`world/stories/models.py`) field-for-field, confirmed against code (the plan's own
draft guessed wrong on three of four — see Task 1's report):

| Field | Target | For kind |
|-------|--------|----------|
| `subject_sheet` | `character_sheets.CharacterSheet` (`SET_NULL`) | NPC_FATE / PERSONAL_JEOPARDY |
| `subject_item` | `items.ItemInstance` (`SET_NULL`) | ITEM |
| `subject_society` | `societies.Society` (`SET_NULL`) | FACTION (society-level) |
| `subject_organization` | `societies.Organization` (`SET_NULL`) | FACTION (organization-level) |
| `subject_label` | plain `CharField` | CUSTOM / CAMPAIGN_TRACK / freeform LOCATION, or flavor text alongside a typed FK |

`SET_NULL` (not `CASCADE`) so a consumed/deleted subject doesn't silently erase the
player's flag — the `TreasuredSubject` row survives with a null typed FK.

### Enums (`src/world/boundaries/constants.py`)

```python
class BoundaryKind(TextChoices):
    HARD_LINE = "hard_line"   # auto-blocked, always private
    ADVISORY = "advisory"     # communicated, shareable

class TreasuredSubjectKind(TextChoices):
    PERSONAL_JEOPARDY = "personal_jeopardy"
    NPC_FATE = "npc_fate"
    LOCATION = "location"
    FACTION = "faction"
    ITEM = "item"
    CAMPAIGN_TRACK = "campaign_track"
    CUSTOM = "custom"
```

`TreasuredSubjectKind` copies `world.stories.constants.StakeSubjectKind`'s member
values **verbatim** (same raw strings) — matching compares string values directly,
with zero import of `world.stories` (see Dependency direction below).

### Stories-side additions (`src/world/stories/models.py`)

- **`StakeTemplate.content_themes`** — `ManyToManyField("boundaries.ContentTheme",
  blank=True, related_name="stake_templates")`. Staff tag a template with the content
  themes its staking would involve; this is what a hard line is matched against.
- **`TreasuredSignoff`** — a player's explicit pre-scene consent to stake one of
  their treasured subjects on a `Beat`. Soft-withdrawal only (story-significant data
  is never hard-deleted): `beat` (FK, CASCADE), `player_data` (FK, CASCADE),
  `treasured_subject` (FK → `boundaries.TreasuredSubject`, CASCADE), `granted_at`
  (auto), `withdrawn_at` (nullable — `None` means active), and an `active` property
  (`withdrawn_at is None`).

---

## Dependency direction: `boundaries` never imports `stories`

Per ADR-0010 (FK direction specific→general), `stories` depends on `boundaries`
(the `StakeTemplate.content_themes` M2M, `TreasuredSignoff.treasured_subject` FK),
never the reverse. This has one real consequence worth calling out explicitly: **not
every "boundaries" function lives in the `world.boundaries` package.**
`grant_treasured_signoff`, `withdraw_treasured_signoff`, and `stake_availability` all
need `Beat`/`TreasuredSignoff` (stories-owned) and reuse `check_stake_boundaries`
(stories-owned) — so they live in `world/stories/services/boundaries.py` alongside
`check_stake_boundaries` itself, not in `world/boundaries/services.py`. The only
function that lives in `world.boundaries.services` is `scene_lines_and_veils`, which
touches only boundaries-owned models plus `Scene` and `VisibilityMixin`. The same
split applies to the DRF surfaces (see below) and was made identically at every task
(3, 5, 6) — confirmed via `grep` that `world/boundaries/services.py` and
`world/boundaries/views.py` have zero `world.stories` imports.

---

## Enforcement seam (`check_stake_boundaries`)

`world/stories/services/boundaries.py`:

```python
def check_stake_boundaries(
    stakes: Iterable[Stake],
    character_sheets: Sequence[CharacterSheet],
) -> StakeBoundaryReport: ...
```

Unchanged signature/contract from the #1770 PR4 stub (every existing call site —
`StakeSerializer` at authoring time, PvP/lethal duel entry, hostile-cast seed/feed,
mission acceptance, the freeform `declare_stakes` GM action, battle round 1 — needed
no changes). Early-returns `allowed=True` when either input is empty (authoring time,
before players are known). Otherwise, batched (no query inside a loop over `stakes`
or `sheets`):

1. **Hard-line check** (`_hard_line_blocked_pair_count`) — one query for
   participants' `HARD_LINE` `PlayerBoundary` rows, one for every staked template's
   `ContentTheme`s, then an in-memory count of blocked `(player, stake)` pairs. Any
   hit blocks the **whole** report: `allowed=False`,
   `blocked_reason_private=f"hard-line theme match on {n} (player,stake) pair(s)"`
   — an **integer count only**, never a theme id/name/key, player id, or sheet id.
2. **Treasured-subject check** (`_treasured_requires_signoff`) — one query for
   participants' `TreasuredSubject` rows, one for active `TreasuredSignoff` rows on
   the beat, then an in-memory identity match. Sheets whose treasured subject is
   staked without an active sign-off populate `requires_signoff` (a tuple of sheet
   ids) — `allowed` stays `True`; `StakeBoundaryReport.cleared` (allowed AND no
   pending sign-off) is the one predicate every call site gates on, so #1771 could
   start returning `requires_signoff` without any call-site change.

**Subject identity** (`_subject_identity`, module-level in
`world/stories/services/boundaries.py` — the single definition, reused by both the
enforcement check and the Task-4 withdrawal override below): two subjects are "the
same thing" when `subject_kind` matches and whichever typed FK that kind populates
matches. Kinds with no typed pointer set (CUSTOM / CAMPAIGN_TRACK / freeform
LOCATION) fall back to comparing `subject_label` instead, so untyped subjects don't
all collide on `(kind, None, None, None, None)`.

---

## Resolution override: withdrawn sign-off routes its stake to WITHDRAWAL

`resolve_stakes_for_completion` (`world/stories/services/stake_resolution.py`)
computes `withdrawn_stake_ids = _withdrawn_consent_stake_ids(beat, stakes)` once
before its per-stake loop (batched: one query for the beat's withdrawn
`TreasuredSignoff` rows, one for the `TreasuredSubject` rows they point at — reuses
`_subject_identity`, not a redefinition). In the per-stake loop, branch order is:

1. `if withdrawal:` — the existing whole-encounter FLED/ABANDONED path, **unchanged**.
2. `elif stake.pk in withdrawn_stake_ids:` — **new** (#1771): a player who withdrew
   their treasured-subject sign-off mid-story never has that stake grade WIN/LOSS at
   a later ordinary completion, even though sibling stakes on the same beat grade
   normally. Routes to `StakeResolutionColumn.WITHDRAWAL`; pends for a GM's
   constrained pick if no authored WITHDRAWAL branch exists (same semantics as the
   whole-encounter path).
3. `else:` — ordinary WIN/LOSS machine grading, **unchanged**.

If a player has both an active sign-off and an unrelated withdrawn sign-off for the
*same identity* on the same beat, the withdrawn one wins (a revoked consent is a hard
stop) — a deliberate design default, not exercised by a test (flagged in the SDD
ledger in case product wants active-wins precedence instead).

---

## Sign-off lifecycle

`world/stories/services/boundaries.py`:

```python
def grant_treasured_signoff(beat, player_data, treasured_subject) -> TreasuredSignoff
def withdraw_treasured_signoff(signoff) -> None
```

`grant_treasured_signoff` is idempotent: it reactivates the most recent existing
`(beat, player_data, treasured_subject)` row (clearing `withdrawn_at`) instead of
creating a duplicate; calling it when an active sign-off already exists is a no-op.
`withdraw_treasured_signoff` sets `withdrawn_at` (never deletes — story-significant
data); a no-op if already withdrawn.

**API** (`world/stories/views.py`, mounted via `world/stories/urls.py`):
`TreasuredSignoffViewSet` (`/api/treasured-signoffs/`, `ModelViewSet` restricted to
`get`/`post`/`head`/`options` — no `destroy`, soft-withdrawal only) — `get_queryset`
scopes to the requester's own sign-offs; `create()` calls `grant_treasured_signoff`;
`POST /api/treasured-signoffs/{id}/withdraw/` calls `withdraw_treasured_signoff`.
Permission `IsSignoffOwner` (self-authored, no staff bypass).
`TreasuredSignoffSerializer.validate_treasured_subject` rejects a subject not owned
by the requester's own tenure.

---

## Sharing / visibility

Both `PlayerBoundary` and `TreasuredSubject` subclass `world.consent.VisibilityMixin`
(`PUBLIC` / `PRIVATE` / `CHARACTERS` / `GROUPS`, `is_visible_to(viewer_tenure)`) — the
same abstract mixin `SocialConsentCategory`'s siblings use. **A `HARD_LINE` boundary
is forced `PRIVATE`** by `clean()`/serializer validation, so sharing only ever
applies to `ADVISORY` boundaries and to `TreasuredSubject` rows.

---

## Scene "lines & veils" aggregate

`world.boundaries.services.scene_lines_and_veils(scene, viewer_tenure) ->
SceneLinesAndVeils` (`world/boundaries/services.py`) — an **anonymized union** of a
scene's participants' shared content:

- Resolves participant sheets via `scene.persona_handler.active_participant_personas()`
  (the same resolver `Scene.finish_scene()` uses — not re-derived by hand).
- Collects each participant's `ADVISORY` `PlayerBoundary` rows and `TreasuredSubject`
  rows that are (a) not `PRIVATE` visibility (excluded at the DB level, regardless of
  viewer) and (b) visible to `viewer_tenure` per `VisibilityMixin.is_visible_to`.
- Returns `SceneLinesAndVeils(advisories: tuple[SharedAdvisoryBoundary, ...],
  treasured_subjects: tuple[SharedTreasuredSubject, ...])` — frozen dataclasses
  (`world/boundaries/types.py`) with **no owner-identifying field**:
  `SharedAdvisoryBoundary(theme_name, detail)`,
  `SharedTreasuredSubject(subject_kind, subject_label, detail)`.

**Hard lines cannot reach this output even in principle** — the query is hardcoded
`kind=BoundaryKind.ADVISORY`; a `HARD_LINE` row is structurally unreachable, not
filtered out after the fact.

**API:** `GET /api/boundaries/scenes/{scene_id}/lines-and-veils/?tenure={id}`
(`SceneLinesAndVeilsView`, an `APIView` — the aggregate is a single-object read, not
CRUD, so pagination/filters don't apply). `tenure` is validated to belong to the
requester before the aggregate is built.

---

## GM stake availability (counts only)

`world.stories.services.boundaries.stake_availability(beat, character_sheets) ->
StakeAvailability` (`world/stories/types.py`: `available`, `blocked`,
`needs_signoff`, all `int`, default 0) — calls `check_stake_boundaries` once per
candidate `Stake` on the beat and tallies. **No reason, no player id, no theme id,
no stake id** — a GM sees "3 available, 1 blocked, 2 need sign-off," never which
stake or why.

**API:** `GET /api/beats/{beat_id}/stake-availability/?sheets={id}&sheets={id}`
(`BeatStakeAvailabilityView`, `world/stories/views.py`) — permission
`IsBeatStoryOwnerOrStaffForAvailability` (staff or the beat's story owner, on every
method — this is a GM planning tool, never player-readable; it deliberately does
**not** reuse `IsBeatStoryOwnerOrStaff`'s GET branch, which delegates to the far more
permissive player-read rule).

---

## Privacy invariant (ADR-0033, extended by ADR-0086)

A hard line's `theme`/`detail` — and `blocked_reason_private` — must **never** reach
any player- or GM-facing surface. This holds structurally, not just by convention:

- `blocked_reason_private` is a fixed-template string embedding only an integer
  count; there is no code path that threads a theme id/name/key, player id, or sheet
  id into it. `StakeBoundaryReport` has exactly 3 fields
  (`allowed`/`requires_signoff`/`blocked_reason_private`) — a test pins the exact
  field set. It appears in **no** serializer's `Meta.fields` in either app.
- `PlayerBoundaryViewSet`/`TreasuredSubjectViewSet` are **owner-scoped querysets**
  (`get_queryset` filters to the requester's own rows) — a non-owner's request 404s;
  another player's hard-line row is never returned with fields stripped, because it
  is never returned. `IsOwnPlayerData` has **no staff carve-out** — a hard line is
  private even from staff.
- `SceneLinesAndVeilsSerializer`/`SharedAdvisoryBoundarySerializer`/
  `SharedTreasuredSubjectSerializer` have no `owner`/`player_data` field to leak, and
  the underlying service only ever queries `ADVISORY` rows (see above).
- `StakeAvailabilitySerializer` has exactly three integer fields — no reason, no
  identifiers.

---

## DRF surfaces

**`world/boundaries/` (mounted at `/api/boundaries/`, `web/urls.py`):**

| Endpoint | ViewSet/View | Notes |
|----------|---------------|-------|
| `/api/boundaries/content-themes/` | `ContentThemeViewSet` (`ReadOnlyModelViewSet`) | The shared staff-authored catalog; every authenticated player reads it to pick hard lines / tag advisories from. |
| `/api/boundaries/player-boundaries/` | `PlayerBoundaryViewSet` (`ModelViewSet`) | Owner self-authoring; `perform_create` force-sets `owner`; `IsOwnPlayerData` (no staff carve-out). |
| `/api/boundaries/treasured-subjects/` | `TreasuredSubjectViewSet` (`ModelViewSet`) | `owner` (a `RosterTenure`) is client-writable; serializer `validate()` rejects a tenure not belonging to the requester. |
| `/api/boundaries/scenes/{id}/lines-and-veils/` | `SceneLinesAndVeilsView` (`APIView`) | See [Scene aggregate](#scene-lines--veils-aggregate) above. |

**`world/stories/` (mounted via `world/stories/urls.py`, per the Dependency
direction split above):**

| Endpoint | ViewSet/View | Notes |
|----------|---------------|-------|
| `/api/treasured-signoffs/` | `TreasuredSignoffViewSet` (`ModelViewSet`, no `destroy`) | See [Sign-off lifecycle](#sign-off-lifecycle) above. |
| `/api/beats/{id}/stake-availability/` | `BeatStakeAvailabilityView` (`APIView`) | See [GM availability](#gm-stake-availability-counts-only) above. |
| `/api/stories/my-pending-signoffs/?beats=<id>&beats=<id>` | `PlayerPendingTreasuredSignoffsView` (`APIView`) | Player-safe batched read — see [Player-safe pending-signoff discovery](#frontend-frontendsrcboundaries) below. |

---

## Frontend (`frontend/src/boundaries/`)

Mirrors the `frontend/src/consent/` module layout (`types.ts`/`api.ts`/`queries.ts`/
`components/`/`pages/`):

- **`pages/BoundariesPage.tsx`** (`/profile/boundaries`, a "Boundaries" tab on
  `ProfilePage`) — three sections: account-wide "My content boundaries"
  (`PlayerBoundaryList`/`PlayerBoundaryFormDialog`), per-tenure "Treasured subjects"
  (`TreasuredSubjectList`/`TreasuredSubjectFormDialog`), and per-tenure "Pre-scene
  sign-offs" (a Beat # input driving `TreasuredSignoffPrompt`).
- **`components/SceneLinesAndVeilsCard.tsx`** — mounted on `SceneDetailPage`; renders
  the read-only aggregate for a chosen viewer tenure.
- **`components/TreasuredSignoffPrompt.tsx`** — renders nothing when the tenure has
  no treasured subjects; otherwise offers "Sign off" / "Signed off" + "Withdraw" per
  subject. Accepts an optional `pendingSubjectIds` prop (#1853): when supplied, the
  panel narrows to only those subject ids instead of showing every treasured
  subject the tenure owns. `BoundariesPage` still passes nothing (its manual Beat #
  field keeps the original "browse and preemptively sign off anything" behavior);
  `BeatRow` (`frontend/src/stories/components/BeatRow.tsx`) passes the ids a
  player-safe backend query flags as actually staked-without-signoff on that beat,
  so the prompt auto-surfaces only where it's actually relevant.
- **Player-safe pending-signoff discovery (#1853):**
  `world.stories.services.boundaries.player_pending_treasured_signoffs(player_data,
  beats) -> list[PendingTreasuredSignoffs]` is the query seam — for a batch of
  beats, which of the *requesting player's own* treasured subjects are staked
  without an active sign-off. Exposed to web via
  `GET /api/stories/my-pending-signoffs/?beats=<id>&beats=<id>`
  (`PlayerPendingTreasuredSignoffsView`) and to telnet via `story beats
  <episode-id>` (flags them inline) and `story signoff <beat-id> <subject>
  [withdraw]` (grants/withdraws) — see `src/commands/CLAUDE.md`'s `story.py` entry.
  Both surfaces call the identical query function; this is the single shared seam,
  not two parallel implementations.
- Both form dialogs wire the `visible_to_tenures` ("Specific characters") sharing
  picker via the existing `TenureMultiSearch` component; the "Consent groups"
  visibility mode has no picker UI anywhere in the frontend yet (no prior art to
  mirror), so it's selectable but not yet configurable from these forms.
- `TreasuredSubjectFormDialog` identifies every subject kind via `subject_label`
  (freeform text) — it does not yet build character/item/faction search pickers for
  the typed FKs (`subject_sheet`/`subject_item`/`subject_society`/
  `subject_organization`); documented in-component.

---

## Seed data (`src/world/boundaries/factories.py`)

A **small starter** `ContentTheme` catalog — deliberately not a Shang-scale content-
warning taxonomy; staff extend it via Django admin as real needs surface:

```python
from world.boundaries.factories import make_default_content_themes

themes = make_default_content_themes()
# {"child-endangerment": ..., "suicide-self-harm": ..., "sexual-violence": ..., "torture": ...}
```

Mirrors `world.consent.factories.make_default_categories()`'s pattern exactly: plain
`ContentTheme.objects.get_or_create(key=..., defaults={...})` per theme (not the
`ContentThemeFactory` sequence factory — sidesteps the FactoryBoy
`django_get_or_create` gotcha where a pre-existing row silently drops non-lookup
kwargs), idempotent, safe to call multiple times. **Not yet wired into a
`world/seeds/clusters.py` cluster / `arx seed dev`** (unlike consent's
`"consent"` cluster) — that wiring was out of this task's scope; today the starter
set is reached by calling `make_default_content_themes()` directly (tests, a shell,
or a future seed cluster).

---

## Admin (`src/world/boundaries/admin.py`)

- `ContentThemeAdmin` — list/search; `display_order`/`is_active` editable inline.
- `PlayerBoundaryAdmin` — `raw_id_fields` for `owner`/`theme`; filter by
  `kind`/`visibility_mode`/`theme`.
- `TreasuredSubjectAdmin` — `raw_id_fields` for all five FKs (owner + four typed
  subject pointers); filter by `subject_kind`.

---

## Test coverage

- `world/boundaries/tests/test_models.py` — `clean()` invariants (hard-line requires
  theme, hard-line forced private, advisory allows sharing), `TreasuredSubject.__str__`,
  the default-content-themes seed helper (creates the expected keys, idempotent).
- `world/boundaries/tests/test_services.py` — `scene_lines_and_veils` anonymization +
  hard-line exclusion + visibility gating.
- `world/boundaries/tests/test_api.py` — owner-scoping/404-not-filtered privacy tests,
  scene-aggregate privacy, availability counts-only privacy, standard CRUD.
- `world/stories/tests/test_boundary_enforcement.py` — hard-line block, treasured
  requires-signoff (with/without active sign-off), privacy of `blocked_reason_private`.
- `world/stories/tests/test_treasured_signoff.py` — `TreasuredSignoff.active`,
  `StakeTemplate.content_themes`.
- `world/stories/tests/test_services_stake_resolution.py` — the withdrawal override
  (a withdrawn treasured stake grades `WITHDRAWAL`, siblings grade normally).

---

## Integration points

- **Stories / Stakes Contract Engine** (`docs/systems/stakes.md`) — the primary
  consumer; `check_stake_boundaries` is the enforcement seam, `stake_availability`
  is the GM planning read. See that doc's
  [Boundary seam](stakes.md#boundary-seam-worldstoriesservicesboundaries) section
  for the stakes-side call-site wiring map.
- **Consent** (`world.consent.VisibilityMixin`) — both `PlayerBoundary` and
  `TreasuredSubject` reuse it verbatim for sharing.
- **Roster** (`RosterTenure`) — `TreasuredSubject.owner`; consent-style visibility is
  tenure-scoped, same as the consent app.
- **Character sheets / Items / Societies** — the typed `TreasuredSubject` subject
  pointers.
- **Scenes** (`Scene.persona_handler`) — participant resolution for
  `scene_lines_and_veils`.

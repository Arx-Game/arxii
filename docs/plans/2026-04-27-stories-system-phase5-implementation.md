# Stories System Phase 5 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make GMs and staff capable of running the game from the web UI — table management, story-GM mobility, era lifecycle, GM/staff messaging, and a story-sectioned table bulletin board. Plus a public "Browse Stories" directory so global metaplot is discoverable, and the polish items deferred from Phase 4.

**Architecture:** Backend additions to `world.gm` (table API + memberships), `world.stories` (primary_table mutation, withdraw/re-offer flow, era advancement service, browse-stories endpoint), `world.narrative` (sender endpoints + global gemit broadcast), and a new `world.stories.bulletin` submodule for the table bulletin board. Frontend feature folders gain Tables / TableBulletin / EraAdmin pages plus polish across existing dialogs. Permissions follow the canonical three-layer pattern enforced in `src/world/stories/CLAUDE.md`.

**Tech Stack:** Django 4.x, DRF, PostgreSQL, SharedMemoryModel, FactoryBoy, Evennia test runner; React 18, TypeScript, Vite, React Query, Radix UI, Tailwind CSS, Playwright.

**Design References:**
- `docs/plans/2026-04-20-stories-system-design.md` (overall design)
- Phase 1-4 plans for context: `docs/plans/2026-04-{20,22,23,25}-stories-system-phase{1,2,3,4}-implementation.md`

---

## Phase Scope

### In Phase 5

**Group A — Table management:**
- `GMTableViewSet` + `GMTableMembershipViewSet` (full CRUD with permission classes, filters, serializers)
- `Story.primary_table` assignment endpoints (add story to table, remove)
- Permission layer:
  - GM at table sees ALL stories + ALL members
  - Player at table sees ONLY stories they participate in (cannot enumerate other stories or see other table members on stories they're not in)
  - Guest story-membership without table-membership (Lead GM adds an outsider as a story participant)
- Player leaves table → personal stories at that table auto-detach non-destructively (story enters "seeking GM" state)
- Frontend: `/tables` list, `/tables/:id` detail with role-aware view, join/leave/manage UIs, "Add story to table" / "Remove story from table" actions, member roster, story roster
- "Story participants" view (Phase 4 audit gap): players see other personas in the same story

**Group B — Story withdrawal + GM re-offer:**
- Service: `withdraw_story_from_gm(story)` — clears `primary_table`, story enters seeking state
- Service: `offer_story_to_gm(story, gm_profile)` — creates `StoryGMOffer` notification
- Service: `accept_story_offer(offer)` / `decline_story_offer(offer)` — GM responses
- Frontend: "Change my GM" CTA on player's story detail, "Pending GM offers" inbox for GMs
- Notification: NarrativeMessage with category SYSTEM informs the GM of incoming offer

**Group C — GM ad-hoc messaging:**
- **C1:** Story-scoped OOC notice — Lead GM/staff composes via dialog → sends NarrativeMessage to all story participants. Backend sender endpoint already mostly designed (Phase 4 deferred).
- **C2:** Real-time gemit broadcast — staff composes; backend pushes via Evennia `character.msg(text, type="gemit")` to every online account; frontend renders inline in green (Arx tradition: `|G[GEMIT]|n`). Persistent record in a `Gemit` model for retroactive viewing.
- **C3 (simplified):** No new bulletin model. Add a public "Browse Stories" directory page (`/stories/browse`) that lists all stories with visibility-aware access. Anyone can find GLOBAL stories and read their visibility-filtered logs. Per-user notification mute becomes `UserStoryMute` model + preferences UI (decides whether the user gets real-time inline pushes from a story; doesn't gate read access).

**Group D — Era lifecycle:**
- Service: `advance_era(next_era)` — closes current ACTIVE era (sets `concluded_at`), activates next (sets `activated_at`)
- Service: `archive_era(era)` — marks era CONCLUDED, no further effect on stories
- Stories continue across eras (per Phase 1 design call) — no auto-mutation of in-flight stories
- Frontend: staff `/stories/eras` page with list, advance/archive actions, era detail showing tagged stories

**Group E — Table bulletin board:**
- New models: `TableBulletinPost(table, story|null, author_persona, body, allow_replies, created_at)` + `TableBulletinReply(post, author_persona, body, created_at)`
- Permission layer:
  - **Top-level posts:** authored by GM/staff only. Story-scoped (story FK set) visible to story members; table-wide (story FK null) visible to all table members.
  - **Replies:** any qualifying viewer can reply if the parent post has `allow_replies=True`
- Frontend: bulletin section on the Table detail page, organized by story-section + a "Table-wide" section. New post composer (GM-only). Threaded view collapses long reply chains.

**Group F — Phase 4 polish deferrals:**
- `BeatSerializer.can_mark` field for client-side button gating (kills Phase 4 Wave 6 optimistic-rendering hack)
- `BeatCreateBody` / `BeatUpdateBody` types replacing `Partial<Beat>` (cleaner contracts)
- DAG drag-to-add-transitions edit mode (React Flow `onConnect` handler + transition-create-on-drop)
- TransitionFormDialog two-phase save with rollback (or backend `save-with-children` action)
- Mobile-responsive layout polish across stories pages

### Deferred beyond Phase 5

- **Covenant / organization chat channels** — broader feature beyond stories scope; will land alongside organizations system
- **MISSION_COMPLETE predicate UI** — blocked on missions system
- **DAG advanced editing** beyond drag-to-add (multi-select, copy/paste, layout templates)
- **Cross-table GM availability marketplace** — searchable directory of GMs accepting story offers; Phase 6+ thing
- **Notification settings UI beyond story mute** — Phase 6+

---

## Conventions for this plan

Same as Phases 1-4:
- Backend: SharedMemoryModel, absolute imports, no JSON fields, TextChoices in `constants.py`, no signals, typed apps require full annotations
- Backend canonical pattern (per `src/world/stories/CLAUDE.md`): permission classes for "who can call", input serializers for "what's valid", services receive validated data only — no validation in views, no inline permission checks
- Frontend: functional components, TypeScript interfaces, React Query for server state, Radix UI primitives, `apiFetch` from `@/evennia_replacements/api`, `React.lazy()` at the route level for code splitting
- `git -C <abs-path>`, never `gh` CLI, never `cd &&` compounds
- Pre-commit hooks must pass cleanly; never `--no-verify`
- TransactionTestCase for unique-constraint tests
- `try/except RelatedObjectDoesNotExist` over `getattr(obj, "reverse_accessor", None)`
- `match/case` over chained `if x == ...` on the same value

---

## Execution structure — Waves

This is a large phase. Wave breakdown:

- **Wave 0** — Investigation: existing GMTable / GMTableMembership models, scopes, integration with Phase 4 author UI
- **Wave 1** — Backend: GMTable + GMTableMembership ViewSets with permission gating
- **Wave 2** — Backend: Story.primary_table mutation services + endpoints; auto-detach on leave
- **Wave 3** — Backend: Story withdrawal + GM offer flow (`StoryGMOffer` model + lifecycle services)
- **Wave 4** — Frontend: Tables list + detail pages with role-aware permissions
- **Wave 5** — Frontend: Withdraw + re-offer UI on player story detail; GM offer inbox
- **Wave 6** — Backend + frontend: Era lifecycle services + staff Era admin page
- **Wave 7** — Backend: Narrative sender endpoints (story OOC + gemit) + Gemit model
- **Wave 8** — Frontend: GM/staff messaging composers (story OOC + gemit broadcast)
- **Wave 9** — Frontend: Browse Stories public directory + UserStoryMute preferences
- **Wave 10** — Backend: TableBulletinPost + TableBulletinReply models + services + ViewSets
- **Wave 11** — Frontend: Table bulletin board UI on Table detail page
- **Wave 12** — Phase 4 polish deferrals: `can_mark`, write-body types, DAG drag-edit
- **Wave 13** — TransitionFormDialog rollback + mobile-responsive layout polish
- **Wave 14** — End-to-end integration tests + docs

---

## Wave 0 — Investigation

### Task 0.1: Audit GMTable / GMTableMembership current state

**Deliverable:** a brief written audit (5-15 minutes of investigation) confirming:

- Current shape of `GMTable` model in `src/world/gm/models.py` (line 114) — fields, FKs, related_name
- Current shape of `GMTableMembership` model — what does `is_active`, `gm_profile`, `persona`, etc. look like
- Whether any `GMTableViewSet` already exists
- Whether `Story.primary_table` mutation has any existing API surface beyond Django admin
- How the Phase 4 GMQueuePage already accesses table-scoped data (it consumes `/api/stories/gm-queue/` which derives from primary_table — verify)
- Whether `Story.character_sheet` is the correct ownership for "personal story at a table" (it is; CHARACTER scope)

**Output:** comment in the implementation plan or a short markdown file in `docs/audits/` if substantial. Decision points:
- Whether `GMTableMembership` needs a new role/permission field or current roles cover Lead GM / member / guest
- Whether `Story.primary_table` should remain nullable (yes — needed for "seeking GM" state)

Commit: `chore(gm): audit GMTable + GMTableMembership state for Phase 5`

If the audit reveals significant model gaps (missing roles, can't represent guest membership without table membership), surface them as a **Wave 0a** task before Wave 1 starts.

---

## Wave 1 — Backend: Table management API

### Task 1.1: GMTableSerializer + filter + permissions + ViewSet

**Files:**
- Create or modify: `src/world/gm/serializers.py`
- Create or modify: `src/world/gm/permissions.py`
- Create or modify: `src/world/gm/filters.py`
- Modify: `src/world/gm/views.py`
- Modify: `src/world/gm/urls.py`
- Create: `src/world/gm/tests/test_views_gmtable.py`

**`GMTableSerializer`:**
- Fields: id, name, description, gm (FK), created_at, updated_at, is_active
- Read-only context fields: `gm_name`, `member_count`, `story_count`
- Validators: `gm` must be a GMProfile owned by the requesting user (for create) OR staff
- Read shape includes the convenience fields above; write shape is name + description (gm derived from request)

**`GMTableFilter`:**
- Filter by `is_active`, `gm`, `member` (membership lookup)

**Permission classes:**
- `IsGMTableOwnerOrStaff` — write access: only the GM that owns the table or staff
- `IsGMTableMemberOrStaffForReads` — read: staff, the GM, OR any member of the table
- For non-members querying the list, results are restricted to public tables / their own memberships

**`GMTableViewSet`:**
- Standard ModelViewSet
- `get_queryset` filters to: tables where requester is GM OR member, plus all if staff
- Custom action: `GET /api/gm-tables/{id}/members/` returns memberships with persona display info
- Custom action: `GET /api/gm-tables/{id}/stories/` returns visible stories (full list for GM/staff, filtered to participated stories for players)

**Tests:**
- GM creates a table → 201, table belongs to them
- Non-GM creates a table → 403
- Member lists tables → sees only tables they belong to
- Staff lists tables → sees all
- GM updates their table → 200
- Member updates GM's table → 403
- Members action returns the right roster

Commit: `feat(gm-api): GMTableViewSet with role-aware permissions`

---

### Task 1.2: GMTableMembership lifecycle endpoints

**Files:**
- Modify: `src/world/gm/serializers.py` — add `GMTableMembershipSerializer`
- Modify: `src/world/gm/views.py` — add `GMTableMembershipViewSet`
- Modify: `src/world/gm/permissions.py` — add `IsMembershipOwnerOrTableGMOrStaff`
- Modify: `src/world/gm/urls.py`
- Create: `src/world/gm/tests/test_views_gmtable_membership.py`

**Behaviors:**
- Create membership: GM (table owner) invites a persona; OR a player applies to join (separate flow — defer if scope creeps)
  - For Phase 5: GM-driven invitation only. Player-driven join can be a Phase 6 feature.
- List memberships: scoped per-table (queryset filtered by `table_id` query param)
- Update membership: GM toggles `is_active`, changes role
- Delete (or deactivate) membership: GM removes a member, OR member removes themselves (self-leave)
  - On self-leave: trigger Story.primary_table=None for that member's CHARACTER-scope stories at this table (Wave 2 service)

**Tests:**
- GM invites a persona → 201
- Member self-leave → 200, membership inactive, personal stories detached
- Non-GM tries to add another → 403
- Member removes themselves → 200; GM removes a member → 200; non-GM removes someone → 403

Commit: `feat(gm-api): GMTableMembershipViewSet with self-leave triggering story detach`

---

### Task 1.3: Story permissions respect story membership at the table

**Files:**
- Modify: `src/world/stories/permissions.py`
- Modify: `src/world/stories/views.py` (StoryViewSet.get_queryset and various other ViewSet querysets)
- Modify: `src/world/stories/tests/`

The story queryset for non-GMs must filter to:
- Stories the user has participation in (via StoryParticipation)
- For CHARACTER scope: stories where `character_sheet` is owned by the user
- For GROUP scope: stories at GMTables the user is a member of AND the user is in the StoryParticipation
- For GLOBAL scope: any GLOBAL story (publicly browsable, but content visibility still per `classify_story_log_viewer_role`)

GMs see all stories at tables they own. Staff sees all.

This is a tightening of existing permissions — Phase 4 likely already handles most of this. Verify and tighten:
- `StoryViewSet.get_queryset` — match the rules above
- Beat / Episode / Transition / etc. all derived through Story — verify the chain holds

Tests cover each scope's permission matrix.

Commit: `refactor(stories-api): tighten Story queryset to respect table+story membership`

---

## Wave 2 — Backend: primary_table assignment + auto-detach

### Task 2.1: Add story to table service + endpoint

**Files:**
- Modify: `src/world/stories/services/tables.py` (new module)
- Modify: `src/world/stories/views.py` — add `assign_to_table` and `detach_from_table` actions on StoryViewSet
- Modify: `src/world/stories/serializers.py` — add input serializers
- Modify: tests

**Service:**
```python
def assign_story_to_table(*, story: Story, table: GMTable) -> Story:
    """Assign a story to a GM's table.

    Permission gating happens in the serializer/view; this service trusts
    its inputs. Sets primary_table; clears any prior table assignment.
    """
    story.primary_table = table
    story.save(update_fields=["primary_table", "updated_at"])
    return story


def detach_story_from_table(*, story: Story) -> Story:
    """Clear the primary_table; story enters 'seeking GM' state."""
    story.primary_table = None
    story.save(update_fields=["primary_table", "updated_at"])
    return story
```

**Action endpoints:**
- `POST /api/stories/{id}/assign-to-table/` — body: `{ table_id: number }` — Lead-GM-or-staff
- `POST /api/stories/{id}/detach-from-table/` — Lead GM (current owner) or the personal-story owner (CHARACTER scope) or staff

**Tests:** standard happy paths + permission rejections.

Commit: `feat(stories-api): assign-to-table and detach-from-table actions`

---

### Task 2.2: Auto-detach on member self-leave

**Files:**
- Modify: `src/world/gm/services.py` (new module if not present, or extend `world.gm`)
- Modify: tests

**Service:**
```python
def leave_table(*, persona: Persona, table: GMTable) -> None:
    """Member leaves a table.

    Side effects:
    - GMTableMembership becomes inactive
    - Any CHARACTER-scope Story owned by this persona's character_sheet
      whose primary_table=table is detached (primary_table=None)
    - Story log + history is preserved (non-destructive)
    """
    membership = GMTableMembership.objects.get(table=table, persona=persona, is_active=True)
    membership.is_active = False
    membership.save(update_fields=["is_active", "updated_at"])

    # Auto-detach CHARACTER-scope stories owned by this persona's character_sheet
    sheet = persona.character_sheet
    Story.objects.filter(
        scope=StoryScope.CHARACTER,
        character_sheet=sheet,
        primary_table=table,
    ).update(primary_table=None, updated_at=timezone.now())
```

Wire this from `GMTableMembershipViewSet.destroy` (or its self-leave action).

**Tests:**
- Member leaves; their personal CHARACTER story detaches
- Member leaves; their participation in GROUP stories at the table is also marked inactive (verify if this is desired — probably yes; defer if it creates complications)
- Member leaves with no personal stories → membership deactivates cleanly
- Non-member tries to leave → 404 / clean error

Commit: `feat(gm-api): self-leave detaches personal stories non-destructively`

---

## Wave 3 — Backend: Story withdrawal + GM offer flow

### Task 3.1: StoryGMOffer model

**Files:**
- Modify: `src/world/stories/models.py` — add `StoryGMOffer` + status choices
- Modify: `src/world/stories/constants.py` — add `StoryGMOfferStatus`
- Modify: `src/world/stories/factories.py`
- Modify: `src/world/stories/admin.py`
- Create: `src/world/stories/tests/test_story_gm_offer.py`
- Migration

```python
class StoryGMOfferStatus(models.TextChoices):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    WITHDRAWN = "withdrawn"


class StoryGMOffer(SharedMemoryModel):
    """A player's offer to assign their personal story to a specific GM.

    Lifecycle: PENDING -> ACCEPTED (GM takes the story; primary_table set)
                       -> DECLINED (GM rejects; story stays seeking)
                       -> WITHDRAWN (player rescinds; story stays seeking)
    """
    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name="gm_offers")
    offered_to = models.ForeignKey("gm.GMProfile", on_delete=models.CASCADE, related_name="story_offers_received")
    offered_by_account = models.ForeignKey("accounts.AccountDB", on_delete=models.CASCADE, related_name="story_offers_made")
    status = models.CharField(max_length=20, choices=StoryGMOfferStatus.choices, default=StoryGMOfferStatus.PENDING)
    message = models.TextField(blank=True)  # optional note from offerer
    response_note = models.TextField(blank=True)  # optional note from GM
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["story", "offered_to"],
                condition=models.Q(status=StoryGMOfferStatus.PENDING),
                name="unique_pending_offer_per_story_per_gm",
            )
        ]
        indexes = [
            models.Index(fields=["offered_to", "status"]),
        ]
```

Tests cover unique constraint (TransactionTestCase), factory, admin registration.

Commit: `feat(stories): add StoryGMOffer model for player-driven GM reassignment`

---

### Task 3.2: Offer lifecycle services

**Files:**
- Modify: `src/world/stories/services/tables.py`
- Modify: `src/world/stories/exceptions.py` — add `StoryGMOfferError` subclasses

```python
def offer_story_to_gm(
    *,
    story: Story,
    offered_to: GMProfile,
    offered_by_account: AccountDB,
    message: str = "",
) -> StoryGMOffer:
    """Player offers a personal story to a specific GM."""
    if story.scope != StoryScope.CHARACTER:
        raise StoryGMOfferError("Only CHARACTER-scope stories support GM re-offers.")
    if story.primary_table_id is not None:
        raise StoryGMOfferError("Withdraw from current GM before offering to another.")
    return StoryGMOffer.objects.create(
        story=story,
        offered_to=offered_to,
        offered_by_account=offered_by_account,
        message=message,
    )


def accept_story_offer(*, offer: StoryGMOffer, response_note: str = "") -> StoryGMOffer:
    """GM accepts; story is assigned to GM's primary table."""
    if offer.status != StoryGMOfferStatus.PENDING:
        raise StoryGMOfferError("Offer is no longer pending.")
    table = offer.offered_to.tables.filter(is_active=True).first()
    if table is None:
        raise StoryGMOfferError("GM has no active table to assign the story to.")
    with transaction.atomic():
        offer.status = StoryGMOfferStatus.ACCEPTED
        offer.response_note = response_note
        offer.responded_at = timezone.now()
        offer.save(update_fields=["status", "response_note", "responded_at"])
        offer.story.primary_table = table
        offer.story.save(update_fields=["primary_table", "updated_at"])
        # Send a NarrativeMessage to the offerer that the offer was accepted
        ...
    return offer


def decline_story_offer(*, offer: StoryGMOffer, response_note: str = "") -> StoryGMOffer:
    ...

def withdraw_story_offer(*, offer: StoryGMOffer) -> StoryGMOffer:
    """Player rescinds a pending offer."""
    ...
```

NarrativeMessage notifications:
- On offer creation: NarrativeMessage to the GM (`category=SYSTEM`, `related_story=story`)
- On accept: NarrativeMessage to the offerer
- On decline: NarrativeMessage to the offerer with response_note

Tests cover each lifecycle transition + permission/state errors.

Commit: `feat(stories): GM offer lifecycle services with narrative notifications`

---

### Task 3.3: Offer ViewSet + action endpoints

**Files:**
- Modify: `src/world/stories/serializers.py`
- Modify: `src/world/stories/views.py`
- Modify: `src/world/stories/urls.py`
- Modify: `src/world/stories/permissions.py`
- Tests

**Endpoints:**
- `GET /api/story-gm-offers/?status=pending&offered_to=<id>` — list offers (GM sees received; player sees made)
- `POST /api/stories/{id}/offer-to-gm/` — body: `{ gm_profile_id, message }` — player offers
- `POST /api/story-gm-offers/{id}/accept/` — body: `{ response_note? }` — GM accepts
- `POST /api/story-gm-offers/{id}/decline/` — body: `{ response_note? }` — GM declines
- `POST /api/story-gm-offers/{id}/withdraw/` — player rescinds

Tests for each endpoint with permission and state matrices.

Commit: `feat(stories-api): StoryGMOffer endpoints (offer / accept / decline / withdraw)`

---

## Wave 4 — Frontend: Tables list + detail pages

### Task 4.1: Tables API + types + hooks

**Files:**
- Create: `frontend/src/tables/api.ts`
- Create: `frontend/src/tables/queries.ts`
- Create: `frontend/src/tables/types.ts`
- Create: `frontend/src/tables/components/.gitkeep`
- Create: `frontend/src/tables/pages/.gitkeep`
- Create: `frontend/src/tables/CLAUDE.md`

(Or place under `frontend/src/gm/` if a `gm` folder already exists for GMProfile management. Investigate first; prefer reusing the existing structure if `gm` exists, else create `tables`.)

Bootstrap pattern matches Phase 4 narrative/stories. Functions cover Wave 1's API surface.

Commit: `feat(tables-fe): bootstrap tables feature folder with API/queries/types`

---

### Task 4.2: TablesListPage (player + GM views unified)

**Files:**
- Create: `frontend/src/tables/pages/TablesListPage.tsx`
- Create: `frontend/src/tables/components/TableCard.tsx`
- Tests

Layout:
- For GM: list of tables they own + tables they're a member of (clearly labeled)
- For player: list of tables they're a member of
- For staff: optional "All tables" filter
- Each card shows table name, GM name, member count, story count, "View" / "Manage" CTA based on role
- "+ Create Table" button (GMs only)

Commit: `feat(tables-fe): TablesListPage with role-aware view`

---

### Task 4.3: TableDetailPage with role-aware sections

**Files:**
- Create: `frontend/src/tables/pages/TableDetailPage.tsx`
- Create: `frontend/src/tables/components/TableMemberRoster.tsx`
- Create: `frontend/src/tables/components/TableStoryRoster.tsx`
- Tests

Layout (role-aware):
- Header: table name, GM name, description
- Tabs: Stories / Members / Bulletin (Wave 11 placeholder for now — empty state if Wave 11 not yet landed)
- **Stories tab:**
  - GM sees all stories at the table (with admin actions)
  - Player sees only stories they participate in
- **Members tab:**
  - GM sees all members + ability to invite/remove
  - Player sees only members they share a story with (cross-reference StoryParticipation)
- "Other participants on this story" surface — when viewing a story they're in, shows list of other personas

Commit: `feat(tables-fe): TableDetailPage with role-aware visibility`

---

### Task 4.4: Create / edit / delete table dialogs + invite/leave UIs

**Files:**
- Create: `frontend/src/tables/components/TableFormDialog.tsx` (create + edit modes)
- Create: `frontend/src/tables/components/InviteToTableDialog.tsx`
- Create: `frontend/src/tables/components/RemoveFromTableDialog.tsx` (confirm)
- Create: `frontend/src/tables/components/LeaveTableDialog.tsx` (player-side, confirm with auto-detach explanation)
- Tests

`LeaveTableDialog` notes: "If you have any personal stories overseen at this table, they will be detached and enter a 'seeking GM' state. Story history is preserved; you can offer the story to a new GM after leaving."

Commit: `feat(tables-fe): table CRUD + invite + leave dialogs`

---

## Wave 5 — Frontend: Withdraw + offer UI on player story detail; GM offer inbox

### Task 5.1: "Change my GM" CTA on player story detail

**Files:**
- Modify: `frontend/src/stories/pages/StoryDetailPage.tsx` — surface "Change my GM" action for CHARACTER-scope stories where the requester is the owner
- Create: `frontend/src/stories/components/OfferStoryToGMDialog.tsx`
- Modify: `frontend/src/stories/queries.ts` — add `useOfferStoryToGM`, `useWithdrawStoryFromGM`
- Tests

Dialog flow:
1. Confirm: "Withdraw '{story_title}' from {current_gm_name}? Story will enter 'seeking GM' state."
2. After withdrawal: prompt to either browse GMs or close
3. Browse: pick a GM (autocomplete from `/api/gm-profiles/?accepting_offers=true` if such filter exists; else just a search), add optional message, submit offer
4. Toast on success: "Offer sent to {gm_name}"

Commit: `feat(stories-fe): withdraw + offer-to-GM flow on player story detail`

---

### Task 5.2: GM offer inbox

**Files:**
- Create: `frontend/src/stories/pages/MyStoryOffersPage.tsx` (route `/stories/my-offers`)
- Create: `frontend/src/stories/components/OfferRow.tsx`
- Create: `frontend/src/stories/components/AcceptOfferDialog.tsx` + `DeclineOfferDialog.tsx`
- Tests

Tabs:
- **Pending** (incoming) — accept/decline actions; shows story summary, offerer name, message
- **Decided** (history) — accepted/declined offers, read-only

Commit: `feat(stories-fe): GM story-offer inbox with accept/decline actions`

---

## Wave 6 — Era lifecycle

### Task 6.1: Era lifecycle services

**Files:**
- Modify: `src/world/stories/services/era.py` (new module if not present)
- Modify: `src/world/stories/exceptions.py`
- Modify: tests

```python
def advance_era(*, next_era: Era) -> Era:
    """Close current ACTIVE era, activate next.

    Stories continue across eras (per Phase 1 design); no auto-mutation.
    Sends a system NarrativeMessage to all currently-online accounts as
    a real-time gemit announcement (Wave 7 implements gemit; for Phase 5
    Wave 6 this is the hook point — leave a TODO).
    """
    if next_era.status != EraStatus.UPCOMING:
        raise EraAdvanceError("Next era must be UPCOMING.")
    with transaction.atomic():
        Era.objects.filter(status=EraStatus.ACTIVE).update(
            status=EraStatus.CONCLUDED, concluded_at=timezone.now()
        )
        next_era.status = EraStatus.ACTIVE
        next_era.activated_at = timezone.now()
        next_era.save(update_fields=["status", "activated_at"])
    return next_era


def archive_era(*, era: Era) -> Era:
    """Mark an era CONCLUDED without advancing to a new one."""
    ...
```

Commit: `feat(stories): era advance / archive lifecycle services`

---

### Task 6.2: Era ViewSet + admin action endpoints

**Files:**
- Modify: `src/world/stories/serializers.py` — add `EraSerializer`
- Modify: `src/world/stories/views.py` — add `EraViewSet` (CRUD for staff) + actions
- Tests

Endpoints:
- Standard CRUD on `/api/eras/` (staff-only writes; reads for everyone — eras are public metaplot info)
- `POST /api/eras/{id}/advance/` — staff advances; the targeted era becomes the new ACTIVE
- `POST /api/eras/{id}/archive/` — staff archives

Commit: `feat(stories-api): EraViewSet with advance/archive actions`

---

### Task 6.3: Frontend Era admin page

**Files:**
- Create: `frontend/src/stories/pages/EraAdminPage.tsx` (route `/stories/eras`, staff-only)
- Create: `frontend/src/stories/components/EraTimeline.tsx` — visual list of past + current + upcoming eras
- Create: `frontend/src/stories/components/AdvanceEraDialog.tsx`
- Tests

Commit: `feat(stories-fe): EraAdminPage with timeline + advance dialog`

---

## Wave 7 — Backend: Narrative sender endpoints + Gemit model

### Task 7.1: Story-scoped OOC sender endpoint

**Files:**
- Modify: `src/world/narrative/services.py` — add `send_story_ooc_message`
- Modify: `src/world/narrative/views.py` — add action endpoint
- Modify: `src/world/narrative/serializers.py`
- Tests

```python
def send_story_ooc_message(
    *,
    story: Story,
    sender_account: AccountDB,
    body: str,
    ooc_note: str = "",
) -> NarrativeMessage:
    """Lead GM/staff sends an OOC notice to all story participants."""
    recipients = list(_resolve_story_participants(story))
    return send_narrative_message(
        recipients=recipients,
        body=body,
        category=NarrativeCategory.STORY,
        sender_account=sender_account,
        ooc_note=ooc_note,
        related_story=story,
    )
```

Endpoint: `POST /api/stories/{id}/send-ooc/` — body: `{ body, ooc_note? }` — Lead GM or staff.

Commit: `feat(narrative-api): story-scoped OOC sender endpoint`

---

### Task 7.2: Gemit model + broadcast service

**Files:**
- Modify: `src/world/narrative/models.py` — add `Gemit` model
- Modify: `src/world/narrative/services.py` — add `broadcast_gemit`
- Modify: tests
- Migration

```python
class Gemit(SharedMemoryModel):
    """A staff-sent real-time broadcast to all online players.

    Persistent record so any account can browse retroactively. Does NOT
    fan out into NarrativeMessageDelivery rows — gemit is server-wide,
    not per-recipient.
    """
    body = models.TextField()
    sender_account = models.ForeignKey("accounts.AccountDB", null=True, on_delete=models.SET_NULL, related_name="gemits_sent")
    related_era = models.ForeignKey(Era, null=True, blank=True, on_delete=models.SET_NULL, related_name="gemits")
    related_story = models.ForeignKey("stories.Story", null=True, blank=True, on_delete=models.SET_NULL, related_name="gemits")
    sent_at = models.DateTimeField(auto_now_add=True)


def broadcast_gemit(*, body: str, sender_account: AccountDB, related_era=None, related_story=None) -> Gemit:
    """Create a Gemit and push to all online sessions in green."""
    gemit = Gemit.objects.create(body=body, sender_account=sender_account, related_era=related_era, related_story=related_story)
    # Push to all online sessions
    for session in evennia.SESSION_HANDLER.get_sessions(connected=True):
        session.msg(text=f"|G[GEMIT]|n {body}", type="gemit")
    return gemit
```

Endpoint: `POST /api/narrative/gemit/` — staff-only — body: `{ body, related_era?, related_story? }`.

Commit: `feat(narrative-api): Gemit model + real-time broadcast service`

---

### Task 7.3: UserStoryMute model + preferences endpoints

**Files:**
- Modify: `src/world/narrative/models.py` — add `UserStoryMute`
- Modify: `src/world/narrative/views.py` — add `UserStoryMuteViewSet`
- Modify: `src/world/narrative/services.py` — modify the per-story narrative push to skip muted users
- Modify: tests

```python
class UserStoryMute(SharedMemoryModel):
    """A user's preference to suppress real-time narrative pushes for a specific story.

    Does not gate read access — muted users can still browse the story log.
    Only suppresses real-time inline pushes via character.msg().
    """
    account = models.ForeignKey("accounts.AccountDB", on_delete=models.CASCADE, related_name="story_mutes")
    story = models.ForeignKey("stories.Story", on_delete=models.CASCADE, related_name="muted_by")
    muted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["account", "story"], name="unique_user_story_mute"),
        ]
```

Update `send_narrative_message` to filter out muted recipients before pushing real-time (still creates the delivery row so login catch-up surfaces it; only suppresses the live push).

Endpoints: `POST /api/user-story-mutes/` (mute), `DELETE /api/user-story-mutes/{id}/` (unmute), `GET /api/user-story-mutes/` (list mine).

Commit: `feat(narrative-api): UserStoryMute model + push suppression`

---

## Wave 8 — Frontend: GM/staff messaging composers

### Task 8.1: Story OOC composer dialog

**Files:**
- Create: `frontend/src/stories/components/SendStoryOOCDialog.tsx`
- Modify: `frontend/src/stories/pages/StoryDetailPage.tsx` to surface a "Send OOC notice" CTA for Lead GMs/staff
- Tests

Form: body, optional ooc_note. Submit calls the Wave 7.1 endpoint. Toast on success.

Commit: `feat(stories-fe): story OOC notice composer dialog`

---

### Task 8.2: Staff gemit composer dialog

**Files:**
- Create: `frontend/src/stories/components/SendGemitDialog.tsx` (or under `narrative/`)
- Modify: somewhere staff-accessible — `StaffWorkloadPage` or new gemit composer page (route `/staff/gemit`)
- Tests

Form: body, optional related_era selector, optional related_story selector. Submit broadcasts.

Commit: `feat(narrative-fe): staff gemit composer dialog`

---

### Task 8.3: Gemit inline rendering in main game text

**Files:**
- Modify: `frontend/src/game/components/ChatWindow.tsx` (and parseGameMessage)
- Tests

Recognize `type="gemit"` events; render in green styling distinct from narrative (which is light red). Use `text-green-300 bg-green-950/20 border-l-2 border-green-500` or similar.

Commit: `feat(narrative-fe): gemit inline rendering in main game feed`

---

## Wave 9 — Frontend: Browse Stories directory + UserStoryMute UI

### Task 9.1: Browse Stories directory page

**Files:**
- Create: `frontend/src/stories/pages/BrowseStoriesPage.tsx` (route `/stories/browse`, public to authenticated)
- Modify: `frontend/src/stories/queries.ts` — `useBrowseStories` (calls `/api/stories/?scope=global` and similar filters)
- Tests

Layout:
- Filter chips: All / Personal / Group / Global
- For Personal and Group: only stories the user has access to
- For Global: all GLOBAL stories (publicly discoverable)
- Click → `/stories/:id` detail page (already permission-gated)

Commit: `feat(stories-fe): public Browse Stories directory`

---

### Task 9.2: UserStoryMute toggle + list

**Files:**
- Create: `frontend/src/narrative/api.ts` additions for mute endpoints
- Create: `frontend/src/narrative/queries.ts` additions
- Create: `frontend/src/narrative/components/MuteStoryToggle.tsx` (used on StoryDetailPage)
- Modify: `frontend/src/narrative/components/MessagesSection.tsx` — surface a "Manage muted stories" link
- Create: `frontend/src/narrative/pages/MuteSettingsPage.tsx` (lists muted stories, unmute action)
- Tests

Commit: `feat(narrative-fe): UserStoryMute toggle on story detail + settings page`

---

## Wave 10 — Backend: TableBulletinPost + TableBulletinReply

### Task 10.1: Models + migration

**Files:**
- Modify: `src/world/stories/models.py` (or new `src/world/stories/bulletin.py` submodule for cleanliness — pick whichever fits the file-size convention)
- Modify: `src/world/stories/factories.py`
- Modify: `src/world/stories/admin.py`
- Tests + migration

```python
class TableBulletinPost(SharedMemoryModel):
    table = models.ForeignKey("gm.GMTable", on_delete=models.CASCADE, related_name="bulletin_posts")
    story = models.ForeignKey(Story, null=True, blank=True, on_delete=models.CASCADE, related_name="bulletin_posts")
    author_persona = models.ForeignKey("scenes.Persona", on_delete=models.SET_NULL, null=True, related_name="table_bulletin_posts")
    title = models.CharField(max_length=200)
    body = models.TextField()
    allow_replies = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["table", "story", "-created_at"])]


class TableBulletinReply(SharedMemoryModel):
    post = models.ForeignKey(TableBulletinPost, on_delete=models.CASCADE, related_name="replies")
    author_persona = models.ForeignKey("scenes.Persona", on_delete=models.SET_NULL, null=True)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
```

Tests + migration.

Commit: `feat(stories): TableBulletinPost + TableBulletinReply models`

---

### Task 10.2: Bulletin services + ViewSets + permissions

**Files:**
- Modify: `src/world/stories/services/bulletin.py` (new module)
- Modify: `src/world/stories/views.py`
- Modify: `src/world/stories/serializers.py`
- Modify: `src/world/stories/permissions.py` — `CanReadBulletinPost`, `CanReplyToBulletinPost`, `CanAuthorBulletinPost` (GM/staff only for top-level)
- Modify: `src/world/stories/filters.py`
- Tests

Endpoints:
- `GET /api/table-bulletin-posts/?table=<id>&story=<id>` — list (permissions filter to visible)
- `POST /api/table-bulletin-posts/` — GM/staff create top-level post
- `PATCH /api/table-bulletin-posts/{id}/` — author edits own post
- `DELETE /api/table-bulletin-posts/{id}/` — author deletes
- `GET /api/table-bulletin-posts/{id}/replies/` — list replies (or use a sub-router under TableBulletinReplyViewSet)
- `POST /api/table-bulletin-replies/` — body: `{ post: <id>, body }` — any qualifying viewer if `allow_replies=True`

Permission rules:
- Top-level read: if `story` is null → all active table members see; else → story participants only
- Top-level write: GM (table owner) or staff
- Reply read: same as parent post
- Reply write: any qualifying reader if parent's `allow_replies=True`

Tests cover the permission matrix thoroughly.

Commit: `feat(stories-api): TableBulletin endpoints with story-scoped permissions`

---

## Wave 11 — Frontend: Table bulletin board UI

### Task 11.1: Bulletin section on TableDetailPage

**Files:**
- Create: `frontend/src/tables/components/TableBulletin.tsx`
- Create: `frontend/src/tables/components/BulletinPostCard.tsx`
- Create: `frontend/src/tables/components/BulletinReplyRow.tsx`
- Modify: `frontend/src/tables/pages/TableDetailPage.tsx` — mount the bulletin tab
- Tests

Layout:
- Section selector at top: "Table-Wide" / per-story sections (only stories the viewer is in show)
- Selected section: list of posts ordered newest first
- Each post: title, author persona, sent_at, body, "Reply" button if `allow_replies && qualifying`
- Replies expanded inline below post; collapse if more than 3, "Show all replies" toggle
- "+ New Post" button (GM/staff only)

Commit: `feat(tables-fe): TableBulletin section with story-scoped sections`

---

### Task 11.2: Post composer + reply composer

**Files:**
- Create: `frontend/src/tables/components/CreateBulletinPostDialog.tsx`
- Create: `frontend/src/tables/components/ReplyToPostDialog.tsx` (or inline reply form)
- Tests

Post composer fields: title, body, optional story selector (table-wide if null), allow_replies toggle.
Reply composer: body only.

Commit: `feat(tables-fe): bulletin post + reply composers`

---

## Wave 12 — Phase 4 polish: can_mark, write-body types, DAG drag-edit

### Task 12.1: BeatSerializer.can_mark field

**Files:**
- Modify: `src/world/stories/serializers.py` — add `can_mark` SerializerMethodField on BeatSerializer
- Modify: `src/world/stories/permissions.py` — extract the can-mark logic if scattered
- Modify: `frontend/src/stories/components/BeatRow.tsx` — render Mark button only if `beat.can_mark`
- Tests

```python
def get_can_mark(self, obj: Beat) -> bool:
    user = self.context["request"].user
    return CanMarkBeat().has_object_permission(self.context["request"], None, obj)
```

Frontend: hide the Mark button when `beat.can_mark === false`.

Commit: `feat(stories-api): BeatSerializer.can_mark for client-side button gating`

---

### Task 12.2: BeatCreateBody / BeatUpdateBody types

**Files:**
- Modify: `frontend/src/stories/types.ts`
- Modify: `frontend/src/stories/api.ts` — change createBeat/updateBeat signatures
- Tests

Replace `Partial<Beat>` with explicit write-body types that omit read-only fields (`id`, `episode_title`, etc.).

Commit: `refactor(stories-fe): BeatCreateBody/UpdateBody types replace Partial<Beat>`

---

### Task 12.3: DAG drag-to-add-transitions edit mode

**Files:**
- Modify: `frontend/src/stories/components/EpisodeDAG.tsx`
- Modify: `frontend/src/stories/pages/StoryAuthorPage.tsx` — add an "Edit Mode" toggle
- Tests

When edit mode is on:
- Nodes become draggable (positioning persists locally only — no backend layout storage)
- Node connection handles enabled; dragging from one node to another triggers `onConnect` → opens TransitionFormDialog with `source_episode` and `target_episode` pre-filled
- Toggle "Read-only" / "Edit" prominently

Commit: `feat(stories-fe): DAG drag-to-add-transitions edit mode`

---

## Wave 13 — TransitionFormDialog rollback + mobile polish

### Task 13.1: TransitionFormDialog two-phase save with rollback

**Files:**
- Modify: `frontend/src/stories/components/TransitionFormDialog.tsx`
- Tests

If the transition POST succeeds but a TransitionRequiredOutcome POST fails, attempt to revert by deleting the just-created transition. If revert fails, surface a clear error to the user with the partial-state explanation.

Alternative (simpler, recommended): backend `save-with-children` action endpoint that creates the transition + required outcomes atomically. Add it to the backend if it's a clean addition.

Commit: `refactor(stories-fe): TransitionFormDialog atomic save (rollback or backend action)`

---

### Task 13.2: Mobile-responsive layout polish

**Files:**
- Modify: every stories page — apply Tailwind responsive utility classes (`sm:`, `md:`, `lg:`)
- Tests: minimal — visual verification

Pages to audit:
- MyActiveStoriesPage
- StoryDetailPage
- GMQueuePage
- AGMOpportunitiesPage
- MyAGMClaimsPage
- StaffWorkloadPage
- StoryAuthorPage (DAG view especially)
- TablesListPage
- TableDetailPage
- EraAdminPage
- BrowseStoriesPage

Commit: `feat(stories-fe): mobile-responsive layout polish across stories pages`

---

## Wave 14 — Integration tests + docs

### Task 14.1: End-to-end backend integration test

**File:** `src/world/stories/tests/test_integration_phase5.py`

Scenario:
1. Staff creates Era 1 (active)
2. GM creates a table
3. Two players join the table
4. GM creates a CHARACTER-scope story for Player 1 → assigns to table
5. GM creates a GROUP story → adds both players as participants
6. GM authors beats + transitions; runs a session
7. Staff broadcasts a gemit
8. Player 1 mutes the GROUP story
9. GM sends a story OOC notice
10. Player 1 withdraws their personal story from the GM
11. Player 1 offers to a different GM
12. Other GM accepts → story now at the new table
13. Original GM posts a table-wide bulletin announcement
14. Player 2 replies (allow_replies=true)
15. Staff advances Era 1 → Era 2; broadcasts gemit
16. All assertions: NarrativeMessage delivery, Gemit row, mute suppression, withdraw/offer state machine

Run full backend regression (fresh DB) at the end.

Commit: `test(stories): Phase 5 end-to-end integration test`

---

### Task 14.2: Frontend e2e Playwright tests

Add at minimum:
- `frontend/e2e/tables.spec.ts` — TablesListPage, TableDetailPage smoke tests
- `frontend/e2e/era-admin.spec.ts` — EraAdminPage smoke test (staff)
- `frontend/e2e/bulletin.spec.ts` — bulletin section smoke test

Same smoke-test approach as Phase 4 Wave 12.

Commit: `test(stories-fe): Playwright smoke tests for Phase 5 surfaces`

---

### Task 14.3: Docs + roadmap

- Mark Phase 5 complete in `docs/roadmap/stories-gm.md`
- Update `frontend/src/tables/CLAUDE.md` and `frontend/src/narrative/CLAUDE.md` with Phase 5 additions
- Regenerate `docs/systems/MODEL_MAP.md`
- Document any deferred items as Phase 6+

Commit: `docs(stories): Phase 5 complete — update roadmap, systems index, model map`

---

## Execution Notes

- **Order dependencies:** Wave 1 must land before Waves 2-5. Wave 7 must land before Wave 8 (composers). Wave 10 before Wave 11. Wave 14 last.
- **Backend-first:** every wave with both backend and frontend should land backend (with tests) before frontend can consume it. Schema regen required after backend additions.
- **Pre-commit hooks:** ESLint, Prettier, TypeScript Check, Frontend Build, Django migrations check, ty, ruff — fix and re-stage; never `--no-verify`.
- **Production verification:** After Wave 13's polish work, run `pnpm build` + manually verify against the production server (port 4001), not just dev.
- **Permission tightening (Task 1.3):** If the Phase 4 queryset gating already covers the rules, this task becomes a verification task with minor tweaks. If it's looser than this plan describes, tighten — but do it in a way that doesn't break Phase 4 tests.
- **GM/staff role detection in frontend:** Phase 4 found that `AccountData` doesn't expose `gm_profile`. Phase 5 may need to add a thin user-info field for GM-ness if the navigation gating requires it. If so, add it as a small backend addition (one line) early in the phase.
- **Notes field on Era model:** Era already has a `description` field — consider whether to add a `summary` for "what happened during this era" content. Probably defer.

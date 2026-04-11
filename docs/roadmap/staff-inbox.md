# Staff Inbox and Player Submissions

**Status:** in-progress (backend complete, frontend pending)
**Depends on:** None (foundational infrastructure)

## Overview
Two complementary pieces:
1. **`player_submissions`** app — distinct models for each kind of thing a player can submit (feedback, bug report, problematic behavior report). Each model owns its own shape, workflow, and management interface.
2. **`staff_inbox`** — a thin aggregator layer that reads from all submission sources (plus existing ones like RosterApplication) and presents a unified triage view: "what needs staff attention right now?"

Each submission type stays distinct — we do NOT force unrelated concerns into a generic polymorphic model. The inbox is a triage view, not a shared table.

## Why This Exists
- **Central triage for staff** — one place to see "what needs attention," filterable by type and priority
- **Safety-critical harassment reporting** — players must be able to report problematic behavior reliably. Roleplaying games are frequent targets for harassment; this must be a first-class feature
- **Per-type management is separate** — the inbox is for triage. Each type has its own full management UI for historical review (e.g., "show me all character applications ever," "show me every report against this player")

## Key Design Principles

### Submission categories
Three player-facing categories, each a distinct model:
- **`PlayerFeedback`** — general feedback/suggestions (freeform)
- **`BugReport`** — technical bug reports (description + context)
- **`PlayerReport`** — reporting problematic behavior from another player (stub for now; full design later)

Separate from the submissions app:
- **`RosterApplication`** — exists in roster app
- **`GMApplication`** — will live in future `gm` app

The inbox aggregates across all of these without owning any of them.

### Identity anchoring — Persona is the source of truth
Every submission anchors to the submitter's active **Persona** (the IC identity they were wearing). Persona is the IC-facing identity and everything derives from it:
- Persona → Character → RosterEntry → active RosterTenure → PlayerData → Account

This gives us:
- **Historical accuracy** — the tenure at the time of submission is captured, so ownership changes later don't invalidate the record
- **Staff derivation** — from any submission, staff can derive "Account X, Player N of Character Y, wearing Persona Z"
- **Accumulated history queries** — "all reports against Account X" walks persona → character → tenures → account

There is no account-level submission path. All player actions happen through a Persona; the model never has an account-only mode.

### Identity summary helper
Staff context often needs "who did this?" as a one-line summary. A helper method (probably on Persona) produces:

```
Crucible (Player 1, Account Bob)
```

Walking persona → character → current tenure → player_number → account. The account portion is staff-only visibility; the persona/player number portion is safe for broader contexts.

This format becomes the canonical staff identifier for players, reusable across the inbox, account history pages, and anywhere else staff needs to identify a player.

### Location and scene context
Every submission captures where the reporter was when they submitted:
- **`location`** — FK to ObjectDB (room), nullable
- **`created_at`** — auto timestamp

`PlayerReport` also captures:
- **`scene`** — FK to Scene, nullable (the scene where the behavior happened)
- **`interaction`** — FK to Interaction, nullable (specific flagged interaction)

This lets staff jump straight to the relevant context instead of hunting.

### Staff inbox — triage view
The inbox aggregates open items across all sources:
- Queries each submission source (the three models above + RosterApplication initially)
- Returns a unified list with common fields: title, category, priority, created_at, reporter identity summary, detail URL
- Filters: category, age, priority, reporter account
- **Not for historical browsing** — that's what per-type management is for

Implementation is a service function + API endpoint + small dataclass. No models.

### Per-type management interfaces
Each submission model has its own ViewSet with filters appropriate to that type:
- `PlayerFeedbackViewSet` — list/retrieve/mark reviewed
- `BugReportViewSet` — list/retrieve/mark reviewed, filter by status
- `PlayerReportViewSet` — list/retrieve/mark reviewed, filter by reported account, filter by reporter, date range
- (existing) `RosterApplicationViewSet` — already exists

These are the "show me all of X" views for history, analytics, and deep review.

### Account staff history page
A dedicated staff-only view showing everything related to a specific account:
- Reports against them (walk persona chain)
- Reports they submitted
- Feedback/bug reports they submitted
- Character applications history
- Each entry: identity snapshot, brief description, link to full detail

This is the "is this a pattern or noise?" tool. A player with 10 reports in a day is obvious; a 10-year flawless player with one suspect report is obvious in the other direction.

Implementation: query service on Account (or a standalone service) that walks through every submission type. Optimized for staff review workflows.

### Review tier scoping
Each submission type has a review tier determining who can see/resolve it:
- **Staff-only** — `PlayerReport` (safety-sensitive). Never delegated.
- **Staff + senior GMs** — possible future default for bug reports, feedback
- **Staff + GM groups** — future crowdsourced review for RosterApplication, GMApplication (requires GM system to exist)

For the first PR, everything is **staff-only**. Delegation tiers come later.

## What Exists
- **`player_submissions` app** — `PlayerFeedback`, `BugReport`, `PlayerReport` (stub) models with SharedMemoryModel, factories, admin, migrations
- **Per-type ViewSets** — create (any authenticated player) / list / retrieve / update (staff only) endpoints at `/api/player-submissions/{feedback,bug-reports,player-reports}/`
- **FilterSets** — status and date range filters on each ViewSet
- **Direct account FK** — submissions store `reporter_account` (and `reported_account` on `PlayerReport`) so staff can query by account without walking the persona chain. Detail serializers expose `reporter_account_username` / `reporter_persona_name` as structured fields.
- **`staff_inbox` app** — thin aggregator with no models. `get_staff_inbox()` service + `GET /api/staff-inbox/` endpoint
- **Account history** — `get_account_submission_history(account_id)` service + `GET /api/staff-inbox/accounts/{id}/history/` endpoint
- **RosterApplication integration** — shows up in the inbox alongside new types; no migration or wrapping of the existing flow

## What's Needed for MVP

### Phase 1 — Core models and submission ✅
- `player_submissions` app with three models: `PlayerFeedback`, `BugReport`, `PlayerReport` (stub)
- All three carry `reporter_account` + `reporter_persona` FKs and capture `location` + `created_at`. Account is the actionable unit; persona is the IC context.
- `PlayerReport` additionally has: `reported_account`, `reported_persona`, `behavior_description`, `asked_to_stop`, `blocked_or_muted`, `scene`, `interaction`
- Submission APIs (create-only for players). Frontend supplies `reporter_persona`; the serializer validates the requesting account currently plays it.

### Phase 2 — Per-type management ✅
- ViewSets for each model with appropriate filters and permissions
- Status filter and date range filter
- Staff-only review tier enforcement

### Phase 3 — Staff inbox aggregator ✅
- `staff_inbox` app — service functions, API endpoint, InboxItem dataclass
- Reads from three new models + existing RosterApplication
- Filter by categories query param
- No models — purely a view/service layer

### Phase 4 — Account history view ✅
- Staff-only endpoint: all submissions related to a specific account (walking persona chains)
- Reports against, reports submitted, feedback, bug reports, character applications

### Phase 5 — Frontend (separate work)
- Staff dashboard widget showing job counts by category
- Per-type list views
- Account history page UI
- Submission forms for players (feedback, bug report)

## PlayerReport — Full Design Deferred

The stub fields cover the data model, but the **full design of PlayerReport is a separate future design pass** because:
- **Wording is safety-critical** — the form language must not alienate victims or encourage bad reports. This is extremely delicate UX work.
- **Block/mute coupling** — the report flow should integrate with a to-be-designed block/mute system so reporters can take immediate action
- **Flow integrity** — the submission path needs thoughtful UX (where it lives, how accessible, how it confirms receipt)
- **Evidence handling** — attaching scene logs, screenshots, timestamps; possibly redacting

**For the first PR:** PlayerReport model exists, submission API works, but the player-facing form and full flow are deferred. Staff can see them in the inbox. Players need a way to submit (even if minimal) so the infrastructure is in place.

## Cross-System Dependencies

- **Persona app** — identity summary helper lives on Persona; submissions anchor to Persona
- **Roster app** — RosterApplication shows up in the inbox alongside new submissions; no migration
- **Scenes app** — PlayerReport optionally references Scene and Interaction
- **GM app (future)** — GMApplication will be another source the inbox reads from
- **Block/mute system (future)** — PlayerReport submission flow will eventually couple with this

## Notes

Harassment reporting is the safety feature that has to work. Everything else can be iterated on, but:
- The reporting path must be accessible (not buried)
- The model must capture enough context for staff investigation
- Staff must be able to see accumulated history (patterns vs noise)
- Reporter privacy must be preserved (staff sees everything; reported party never sees reporter identity)

The first PR establishes the infrastructure. The full PlayerReport UX comes in a dedicated design pass when we have block/mute and a proper safety flow to build around.

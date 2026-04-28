# Stories - Narrative Campaign UI

Frontend for the `world.stories` backend app. Player dashboards, story
detail and log reader, action UIs (mark beat / contribute / schedule /
acknowledge), Lead GM queue, AGM claim management, staff workload
dashboard, and story author editor. Implemented in Phase 4 (Waves 1-12).

## File Inventory

### `api.ts`

REST API client — one thin `apiFetch` wrapper per endpoint. Grouped by
endpoint family:

**Phase 4 — stories core:**

- **Dashboard reads:** `getMyActiveStories()`, `getGMQueue()`, `getStaffWorkload()`
- **Story / chapter / episode / beat / transition CRUD:** `getStory()`,
  `listChapters()`, `listEpisodes()`, `listBeats()`, `listTransitions()`,
  `createStory()` / `updateStory()` / `deleteStory()` and equivalents for
  Chapter, Episode, Beat, Transition
- **Progress reads:** `getStoryLog()`, `listGroupStoryProgress()`,
  `listGlobalStoryProgress()`
- **Action endpoints:** `resolveEpisode()`, `markBeat()`, `contributeToBeat()`,
  `approveClaim()`, `rejectClaim()`, `cancelClaim()`, `completeClaim()`,
  `requestClaim()`, `createEventFromSessionRequest()`, `cancelSessionRequest()`,
  `resolveSessionRequest()`, `expireOverdueBeats()`
- **AGM / session request reads:** `listAssistantGMClaims()`, `listSessionRequests()`

**Phase 5 — era + story mobility + browse:**

- **Era CRUD + actions:** `listEras()`, `getEra()`, `createEra()`, `updateEra()`, `deleteEra()`, `advanceEra()`, `archiveEra()`
- **Story table assignment:** `assignToTable(storyId, tableId)`, `detachFromTable(storyId)`
- **GM offers:** `listStoryGMOffers()`, `createGMOffer(storyId, body)`, `acceptGMOffer(offerId)`, `declineGMOffer(offerId)`, `withdrawGMOffer(offerId)`
- **Browse:** `listStoriesPublic(params?)` — visibility-filtered list for `BrowseStoriesPage`
- **Atomic transition save:** `saveTransitionWithOutcomes(transitionId?, body)` — `POST /api/stories/transitions/save-with-outcomes/`

### `queries.ts`

React Query hooks with a `storiesKeys` query key factory. Mutations
invalidate appropriate caches (e.g., marking a beat invalidates the episode
beats list and the story log). Hook naming follows the `use<Resource>()` and
`use<Action>Mutation()` conventions.

### `types.ts`

TypeScript aliases for generated types from `@/generated/api`. Frontend-only
utility types (e.g., `MyActiveStoryEntry`, `GMQueueEpisodeEntry`,
`StaffWorkloadResponse`) were authored manually because `spectacular` cannot
introspect `APIView`-based dashboard endpoints.

### `components/`

| File                                | Purpose                                                    |
| ----------------------------------- | ---------------------------------------------------------- |
| `AGMOpportunityCard.tsx`            | Single beat card on the AGM opportunities page             |
| `AggregateProgressBar.tsx`          | Progress bar for `AGGREGATE_THRESHOLD` beats               |
| `ApproveClaimDialog.tsx`            | Lead GM dialog to approve an AGM claim                     |
| `AssignedSessionRequestRow.tsx`     | Session request row on the GM queue                        |
| `BeatFormDialog.tsx`                | Beat CRUD dialog with predicate-type-driven config form    |
| `BeatList.tsx`                      | Beat list for the current episode panel                    |
| `BeatOutcomeBadge.tsx`              | Colored badge for beat outcome values                      |
| `BeatRow.tsx`                       | Single beat row with predicate description                 |
| `ChapterFormDialog.tsx`             | Chapter CRUD dialog                                        |
| `ContributeBeatDialog.tsx`          | Player dialog to contribute to aggregate beats             |
| `CurrentEpisodePanel.tsx`           | Active episode beats panel on the story detail page        |
| `EpisodeDAG.tsx`                    | Episode DAG read-only visualization (React Flow)           |
| `EpisodeFormDialog.tsx`             | Episode CRUD dialog                                        |
| `EpisodeNode.tsx`                   | Single node in the DAG — frontier vs. visited state        |
| `EpisodeReadyCard.tsx`              | Episode card on the GM queue "ready to run" list           |
| `ExpireBeatsButton.tsx`             | Staff action to trigger `expire_overdue_beats`             |
| `FrontierStoriesTable.tsx`          | Stories-at-frontier table on the staff workload page       |
| `MarkBeatDialog.tsx`                | GM dialog to mark a `GM_MARKED` beat                       |
| `MyClaimRow.tsx`                    | Single AGM claim row on the My Claims page                 |
| `PendingClaimRow.tsx`               | AGM claim row on the GM queue                              |
| `PerGMQueueTable.tsx`               | Per-GM queue depth table on the staff workload page        |
| `ProgressionRequirementsEditor.tsx` | Add/remove progression requirements on the author editor   |
| `RejectClaimDialog.tsx`             | Lead GM dialog to reject an AGM claim                      |
| `RequestClaimDialog.tsx`            | AGM dialog to request a new claim                          |
| `ResolveEpisodeDialog.tsx`          | GM dialog to resolve an episode (transition selection)     |
| `ScheduleEventDialog.tsx`           | GM dialog to create an event from a session request        |
| `ScopeBadge.tsx`                    | Colored badge for story scope (character / group / global) |
| `SessionRequestStatusCard.tsx`      | Status card for the session request flow                   |
| `StaleStoriesTable.tsx`             | Stale stories table on the staff workload page             |
| `StatusBadge.tsx`                   | Story status badge                                         |
| `StoryAuthorTree.tsx`               | Left-panel tree for the story author editor                |
| `StoryCard.tsx`                     | Clickable story card on the active-stories list            |
| `StoryFormDialog.tsx`               | Story CRUD dialog                                          |
| `StoryLog.tsx`                      | Visibility-filtered story log timeline                     |
| `TransitionFormDialog.tsx`          | Transition CRUD dialog                                     |
| `WorkloadStatCard.tsx`              | Stat card on the staff workload dashboard                  |

**Phase 5 additions:**

| File                   | Purpose                                                               |
| ---------------------- | --------------------------------------------------------------------- |
| `ChangeMyGMDialog.tsx` | Player dialog: withdraw story from current GM + offer to a new one    |
| `OfferCard.tsx`        | GM offer card for `MyStoryOffersPage` (pending offer display)         |
| `OfferRow.tsx`         | Single offer row in the responded-offers history section              |
| `EraCard.tsx`          | Single era card for `EraAdminPage` (status badge + advance/archive)   |
| `StoryBrowseCard.tsx`  | Compact story card for `BrowseStoriesPage` with scope + status badges |

### `pages/`

**Phase 4:**

| File                       | Route                                            | Auth                             |
| -------------------------- | ------------------------------------------------ | -------------------------------- |
| `MyActiveStoriesPage.tsx`  | `/stories/my-active`                             | ProtectedRoute                   |
| `StoryDetailPage.tsx`      | `/stories/:id`                                   | ProtectedRoute                   |
| `GMQueuePage.tsx`          | `/stories/gm-queue`                              | ProtectedRoute (403 for non-GMs) |
| `AGMOpportunitiesPage.tsx` | `/stories/agm-opportunities`                     | ProtectedRoute                   |
| `MyAGMClaimsPage.tsx`      | `/stories/my-claims`                             | ProtectedRoute                   |
| `StaffWorkloadPage.tsx`    | `/stories/staff-workload`                        | StaffRoute                       |
| `StoryAuthorPage.tsx`      | `/stories/author` and `/stories/author/:storyId` | ProtectedRoute                   |

**Phase 5:**

| File                    | Route                | Auth           |
| ----------------------- | -------------------- | -------------- |
| `EraAdminPage.tsx`      | `/stories/eras`      | StaffRoute     |
| `BrowseStoriesPage.tsx` | `/stories/browse`    | Public (any)   |
| `MyStoryOffersPage.tsx` | `/stories/my-offers` | ProtectedRoute |

`EraAdminPage` — staff admin for era (season) lifecycle: list + advance + archive actions + era
detail showing tagged stories.

`BrowseStoriesPage` — public directory listing all stories the requester can access, grouped by
scope (Personal / Group / Global) with filter chips. Backend restricts visibility per the existing
queryset rules.

`MyStoryOffersPage` — GM offer inbox; pending story offers in a card grid with Accept / Decline
actions, responded offers in a history section. `OfferRow` and `OfferCard` are sub-components.

## Data Flow

- **REST API**: Full CRUD via `/api/stories/`, `/api/beats/`, `/api/transitions/`,
  `/api/group-story-progress/`, `/api/global-story-progress/`,
  `/api/aggregate-beat-contributions/`, `/api/assistant-gm-claims/`,
  `/api/session-requests/`
- **Custom actions**: `resolve-episode`, `mark`, `contribute`,
  `approve` / `reject` / `complete` / `cancel` claim, `create-event`,
  `expire-beats`
- **Dashboards**: `my-active`, `gm-queue`, `staff-workload`

## Integration Points

- **Backend Models**: All `world.stories` models
- **Narrative**: Beat completions and episode resolutions emit narrative
  messages; the story log surfaces them via `GET /api/stories/{pk}/log/`
- **Events**: Session requests bridge to `world.events.Event` via the
  `create-event-from-session-request` action
- **Character Sheets**: `Story.character_sheet` ownership for CHARACTER scope;
  player dashboards filter by the puppeted character
- **GM**: `GMTable` ownership for GROUP scope; `GMProfile` for permissions
- **Navigation**: Unread narrative badge from `frontend/src/narrative/` wires
  into the nav via the Redux auth slice

## Common Gotchas

**`spectacular` cannot introspect APIView-based dashboards.** The `my-active`,
`gm-queue`, and `staff-workload` endpoints are `APIView` subclasses rather
than ViewSets; `drf-spectacular` skips them during schema generation.
Types for their responses (`MyActiveStoriesResponse`, `GMQueueResponse`,
`StaffWorkloadResponse`, and nested entry types) are authored manually in
`types.ts` and must be kept in sync with the backend serializers by hand.

**`GMProfile` is not in the `/api/user/` account payload.** The account
endpoint returns `is_staff`, `is_superuser`, and character sheet data but
not whether the user has a `GMProfile`. The navigation shows GM links for
any authenticated user; non-GMs hit a 403 when the `gm-queue` API call
resolves and `GMQueuePage` renders the `NotGMPage` fallback instead of
blowing the error boundary.

**`ProtectedRoute` redirects unauthenticated users to `/login`.** In the
Playwright e2e smoke tests (which run without a live backend), all
`ProtectedRoute`-wrapped stories pages redirect to the login page. Tests
verify the app renders without crashing and `#root` is non-empty — they
do not assert stories-specific UI because that requires authentication.

**Episode DAG uses React Flow.** The `EpisodeDAG` component imports
`@xyflow/react`. React Flow requires a CSS import (`@xyflow/react/dist/style.css`)
already in `index.css`. Phase 5 Wave 12 added drag-to-add-transitions edit mode
via `onConnect`. Multi-select, copy/paste, and layout templates are deferred to Phase 6+.

**Phase 5: `BeatSerializer.can_mark` field is now wired.** `MarkBeatDialog` reads
`beat.can_mark` to gate the "Mark" button. The button is hidden for unauthorized
users rather than relying on the 403 response. `can_mark` is `true` when the
requesting user is the Lead GM, staff, or has an APPROVED AGM claim on this beat.

**Phase 5: `TransitionFormDialog` uses atomic save.** Creating or editing a
transition with required-outcome rows now fires a single `POST /api/stories/transitions/save-with-outcomes/`
request. The prior two-step create-then-patch approach is removed; rollback
on partial failure is handled server-side.

**Phase 5: Story GM offer flow.** `ChangeMyGMDialog` on `StoryDetailPage` fires
`detach-from-table` then `create-gm-offer` (two requests). If the detach succeeds
but the offer creation fails, the story is left in "seeking GM" state (primary_table=None).
The player can retry from `MyStoryOffersPage`.

**`BrowseStoriesPage` is public (no ProtectedRoute).** It is wrapped directly
in a `<Suspense>` in `App.tsx` without `<ProtectedRoute>`. The backend queryset
restricts results by visibility — private stories are excluded for anonymous or
non-participant viewers.

# Stories System Phase 4 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship the React frontend for the entire stories + narrative backend — player dashboards, story log reader, action UIs (mark beat / contribute / schedule / acknowledge), Lead GM queue, AGM claim management, staff workload dashboard, story author editor, and inline narrative-message rendering. End state: a player can sign in, see their active stories, follow along as beats flip in real time, schedule sessions with their GM, and read their narrative messages — all without touching Django admin.

**Architecture:** New `frontend/src/stories/` and `frontend/src/narrative/` feature folders matching the established per-feature layout (`api.ts`, `queries.ts`, `types.ts`, `components/`, `pages/`, `CLAUDE.md`, optional `__tests__/`). Server state via React Query. API calls via the existing `apiFetch` wrapper from `@/evennia_replacements/api`. Types regenerated from the backend OpenAPI schema. Routes registered in `App.tsx`. Tailwind + Radix UI for styling. Real-time narrative messages delivered via the existing WebSocket session channel and rendered with a `|R[NARRATIVE]|n` color tag → light red display class. Episode DAG visualization via React Flow.

**Tech Stack:** React 18, TypeScript, Vite, React Query, Redux Toolkit (only for global client state — server state uses RQ), Tailwind CSS, Radix UI, React Router, Vitest (unit), Playwright (e2e).

**Design Reference:** `docs/plans/2026-04-20-stories-system-design.md`
**Phase 1 plan:** `docs/plans/2026-04-20-stories-system-phase1-implementation.md`
**Phase 2 plan:** `docs/plans/2026-04-22-stories-system-phase2-implementation.md`
**Phase 3 plan:** `docs/plans/2026-04-23-stories-system-phase3-implementation.md`

---

## Phase Scope

**In Phase 4:**

### `frontend/src/narrative/`
- API client + React Query hooks for `/api/narrative/my-messages/` and `/api/narrative/deliveries/{id}/acknowledge/`
- Inline narrative-message rendering in the main game text feed (light red, distinct visual treatment)
- Messages section on the character sheet — browseable history with category filter, unread-first ordering
- Unread counter badge surfaced in the top-level navigation
- Acknowledge button per message; bulk-acknowledge optional
- WebSocket integration: real-time narrative-message arrival appends to the in-text feed AND increments the unread counter

### `frontend/src/stories/`
- API client + React Query hooks for the full stories API surface (story / chapter / episode / beat / transition / progress / completion / resolution / aggregate / AGM claim / session request / dashboards / actions)
- **Player UI:**
  - "My Active Stories" page — list with status one-liners
  - Story detail page — current episode panel, beat list with progress for aggregates, story log reader, schedule CTA
  - Story log component — visibility-filtered timeline (BeatCompletion + EpisodeResolution + StoryMessage entries)
  - Aggregate-contribute action UI
  - Session-request flow UI (open-to-any-GM, schedule-with-my-GM)
- **Lead GM UI:**
  - GM queue page — episodes ready to run, with filters by scope and table
  - Mark-beat action UI (GM-only on GM_MARKED beats)
  - Resolve-episode action UI (transition selection for GM_CHOICE)
  - Approve/reject AGM claim action UIs
  - Schedule session via Events bridge (create-event-from-session-request)
- **AGM UI:**
  - Browse AGM-eligible beats and request a claim
  - View scoped beat info after claim approved
  - Mark beat outcome on claimed beat
- **Staff UI:**
  - Cross-story workload dashboard
  - Manual expire-overdue-beats trigger
- **Author editor:**
  - Story / Chapter / Episode CRUD via forms (Radix Dialog + form patterns matching existing features)
  - Beat CRUD with predicate-type-driven config form (the form shape changes based on `predicate_type`)
  - Transition CRUD with routing predicate (TransitionRequiredOutcome rows)
  - EpisodeProgressionRequirement add/remove
  - Episode DAG visualization (React Flow): read-only first, edit-mode for transitions optional

### Cross-cutting
- Shared status-line rendering helper (computed from `compute_story_status_line` data on backend OR re-derived on frontend from raw progress + transition info — pick whichever is simpler given the API shape)
- Routing in `App.tsx` — new routes under `/stories/*` and integration into character sheet for `/sheet/:id/messages` (or similar)
- Navigation links in the top-level nav (player vs. GM vs. staff visibility)
- Page-level error boundaries
- Loading skeletons
- E2E Playwright smoke tests covering the major player flow and major GM flow

**Deferred beyond Phase 4:**
- **MISSION_COMPLETE predicate UI** — blocked on missions system; will land alongside missions
- **Covenant leadership UI** — PC leader / group vote / assigned GM UX requires the covenant model first
- **Era lifecycle tooling UI** — staff era-advancement flow, Season-N closing ceremonies
- **Dispute / withdrawal UI** — personal-story GM change, story transfer, GROUP withdrawal
- **GM ad-hoc narrative message composer** — backend sender endpoint not built yet; defer until that's added
- **Mobile-responsive layout polish** — assume desktop-first; mobile tweaks later

---

## Conventions for this plan

From global CLAUDE.md and `frontend/CLAUDE.md`:

- Functional components only with TypeScript interfaces. **No class components.**
- React Query for server state. Redux only for global client state (auth, theme).
- Tailwind utility classes; Radix UI primitives via shadcn-style component imports (look at `frontend/src/components/ui/` for existing primitives).
- `apiFetch` from `@/evennia_replacements/api` for HTTP — handles auth/CSRF.
- Per-feature folder layout (api.ts, queries.ts, types.ts, components/, pages/, CLAUDE.md).
- Code splitting: never use `manualChunks` file path patterns for app code. Use `React.lazy()` at the route level for page-level splitting.
- Production build verification: `pnpm build` succeeds ≠ app works. Verify against the production server (port 4001) for any Vite config or dependency change.
- Pre-commit hooks: ESLint, Prettier, TypeScript check, Frontend Build. Fix and re-stage; never `--no-verify`.
- Loading states with skeletons; error boundaries at the page level.
- Form validation matches backend serializer validation — surface DRF 400 field errors inline.
- Run unit tests via `pnpm test`; e2e via `pnpm test:e2e` after `pnpm build`.

Backend-side conventions still apply for any wave that touches Python (e.g., schema regen):
- Never `gh` CLI; use `git -C <abs-path>`.
- Never `cd &&` compounds.
- Pre-commit on every commit.

---

## Execution structure — Waves

- **Wave 0** — Schema regeneration + frontend feature folder bootstrap
- **Wave 1** — Narrative core: inline messages + character-sheet messages section + unread counter + acknowledge
- **Wave 2** — Stories: API + types + queries layer (no UI yet, just the data foundation)
- **Wave 3** — Stories: Player active-stories list + story detail page (read-only)
- **Wave 4** — Stories: Player action UIs (contribute, session request flow, acknowledge integration)
- **Wave 5** — Stories: Lead GM queue dashboard
- **Wave 6** — Stories: GM action UIs (mark beat, resolve episode, approve/reject AGM claims, schedule via Events)
- **Wave 7** — Stories: AGM claim flow UI (request, view scoped beat, mark)
- **Wave 8** — Stories: Staff workload dashboard
- **Wave 9** — Stories: Author editor (Story / Chapter / Episode / Beat / Transition CRUD)
- **Wave 10** — Stories: Episode DAG visualization (React Flow)
- **Wave 11** — Routing, navigation, polish, error boundaries
- **Wave 12** — E2E Playwright tests for the player and GM happy paths

---

## Wave 0 — Schema regeneration + bootstrap

### Task 0.1: Regenerate API types from backend schema

**Files:**
- Modify: `src/schema.json` (auto-generated)
- Modify: `frontend/src/generated/api.d.ts` (auto-generated)

The backend stories + narrative endpoints landed in Phases 2 and 3. Their OpenAPI schema needs to flow into the frontend types.

**Steps:**

1. Run the API type regeneration command:
   ```
   just gen-api-types
   ```
   (Per global CLAUDE.md. Falls back to whatever the underlying tool is — likely a `drf-spectacular` invocation + an OpenAPI codegen step.)

2. Verify the generated `frontend/src/generated/api.d.ts` includes the new Phase 2/3 endpoints:
   - `/api/stories/` (existing) plus new actions like `/api/stories/{pk}/resolve-episode/`, `/api/stories/{pk}/log/`
   - `/api/stories/my-active/`, `/api/stories/gm-queue/`, `/api/stories/staff-workload/`
   - `/api/beats/{pk}/mark/`, `/api/beats/{pk}/contribute/`
   - `/api/group-story-progress/`, `/api/global-story-progress/`
   - `/api/aggregate-beat-contributions/`, `/api/assistant-gm-claims/`, `/api/session-requests/`
   - `/api/narrative/my-messages/`, `/api/narrative/deliveries/{id}/acknowledge/`

3. Skim the generated types for shape sanity. Spot-check a few — `paths['/api/stories/my-active/']`, the `BeatSerializer` shape with all predicate config fields, etc.

4. Commit:
   ```
   chore(frontend): regenerate API types after Phase 2/3 backend additions

   Brings stories + narrative endpoints into frontend/src/generated/api.d.ts.
   No frontend code yet — Wave 1 starts consuming.

   Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
   ```

If the regeneration command fails or the generated file is unchanged, investigate before proceeding — Phase 4 depends on accurate types.

---

### Task 0.2: Bootstrap `frontend/src/narrative/` and `frontend/src/stories/`

**Files:**
- Create: `frontend/src/narrative/api.ts`
- Create: `frontend/src/narrative/queries.ts`
- Create: `frontend/src/narrative/types.ts`
- Create: `frontend/src/narrative/components/.gitkeep`
- Create: `frontend/src/narrative/pages/.gitkeep`
- Create: `frontend/src/narrative/CLAUDE.md`
- Create: `frontend/src/stories/api.ts`
- Create: `frontend/src/stories/queries.ts`
- Create: `frontend/src/stories/types.ts`
- Create: `frontend/src/stories/components/.gitkeep`
- Create: `frontend/src/stories/pages/.gitkeep`
- Create: `frontend/src/stories/CLAUDE.md`

Each `CLAUDE.md` follows the pattern from `frontend/src/roster/CLAUDE.md` and `frontend/src/codex/CLAUDE.md` — describes the feature, key files, and integration points. Initially placeholder content noting that Phase 4 implementation is in progress.

Each `api.ts` is a thin wrapper around `apiFetch` (no functions yet — just the import + base URL constant). Each `queries.ts` is empty except for the query-keys factory pattern. Each `types.ts` re-exports relevant types from `frontend/src/generated/api.d.ts` with shorter local aliases.

Sample `frontend/src/narrative/api.ts`:
```typescript
/**
 * Narrative API functions
 */

import { apiFetch } from '@/evennia_replacements/api';

const BASE_URL = '/api/narrative';

// Functions added in Wave 1.
```

Sample `frontend/src/stories/api.ts`:
```typescript
/**
 * Stories API functions
 */

import { apiFetch } from '@/evennia_replacements/api';

const BASE_URL = '/api/stories';

// Functions added in Wave 2.
```

Commit:
```
feat(frontend): bootstrap stories and narrative feature folders

Standard per-feature layout: api.ts, queries.ts, types.ts, components/,
pages/, CLAUDE.md. Empty scaffolding for Wave 1+ to fill in.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

Run `pnpm typecheck` and `pnpm lint` to verify nothing broke. Run `pnpm build` to confirm the production bundle compiles with the new (empty) entries.

---

## Wave 1 — Narrative core UI

### Task 1.1: Narrative API + queries

**Files:**
- Modify: `frontend/src/narrative/api.ts`
- Modify: `frontend/src/narrative/queries.ts`
- Modify: `frontend/src/narrative/types.ts`
- Create: `frontend/src/narrative/__tests__/queries.test.tsx` (Vitest unit tests via `@testing-library/react` and React Query's test utilities)

**API functions:**
```typescript
// api.ts
export interface MyMessagesResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: NarrativeMessageDelivery[];
}

export async function getMyMessages(params?: {
  category?: NarrativeCategory;
  acknowledged?: boolean;
  page?: number;
}): Promise<MyMessagesResponse> {
  const search = new URLSearchParams();
  if (params?.category) search.set('category', params.category);
  if (params?.acknowledged !== undefined) search.set('acknowledged', String(params.acknowledged));
  if (params?.page) search.set('page', String(params.page));
  const qs = search.toString();
  const res = await apiFetch(`${BASE_URL}/my-messages/${qs ? `?${qs}` : ''}`);
  if (!res.ok) throw new Error('Failed to load narrative messages');
  return res.json();
}

export async function acknowledgeDelivery(deliveryId: number): Promise<NarrativeMessageDelivery> {
  const res = await apiFetch(`${BASE_URL}/deliveries/${deliveryId}/acknowledge/`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error('Failed to acknowledge message');
  return res.json();
}
```

**Types** — re-export the relevant generated types from `frontend/src/generated/api.d.ts` with local aliases:
```typescript
// types.ts
import type { paths, components } from '@/generated/api';

export type NarrativeMessage = components['schemas']['NarrativeMessage'];
export type NarrativeMessageDelivery = components['schemas']['NarrativeMessageDelivery'];
export type NarrativeCategory = NonNullable<components['schemas']['NarrativeMessage']['category']>;
```

Adjust path / component names based on what the actual generated file exposes — names depend on the codegen tool.

**Query hooks:**
```typescript
// queries.ts
export const narrativeKeys = {
  all: ['narrative'] as const,
  myMessages: (filters?: { category?: NarrativeCategory; acknowledged?: boolean; page?: number }) =>
    [...narrativeKeys.all, 'my-messages', filters] as const,
};

export function useMyMessages(filters?: { ... }) {
  return useQuery({
    queryKey: narrativeKeys.myMessages(filters),
    queryFn: () => getMyMessages(filters),
    throwOnError: true,
  });
}

export function useAcknowledgeDelivery() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: acknowledgeDelivery,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: narrativeKeys.all });
    },
  });
}

export function useUnreadCount() {
  // Filter `acknowledged=false`, return `count` only
  const { data } = useMyMessages({ acknowledged: false });
  return data?.count ?? 0;
}
```

Tests cover hook return shapes, error throwing, mutation cache invalidation. Use React Query's `QueryClientProvider` test wrapper.

Commit:
```
feat(narrative-fe): API client and React Query hooks

useMyMessages, useAcknowledgeDelivery, useUnreadCount hooks. Pagination
and category/acknowledged filtering. Mutation invalidates the messages
cache so the unread counter and inline feed both refresh after ack.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

---

### Task 1.2: Inline narrative-message rendering in main text feed

**Files:**
- Investigate: `frontend/src/game/` and `frontend/src/evennia_replacements/` to find the main text-feed component (likely a `TextFeed.tsx` or similar that renders `character.msg(...)` output)
- Modify: that component to recognize narrative-message events and render them in light red
- Possibly create: `frontend/src/narrative/components/InlineNarrative.tsx` for the message rendering

The backend pushes narrative messages through Evennia's `character.msg(text, type="narrative")` — the WebSocket session sees them with the `|R[NARRATIVE]|n` color tag prefix. The text-feed component needs to:
- Recognize messages with `type="narrative"` (or detect the `|R[NARRATIVE]|n` prefix as fallback)
- Render in a visually distinct way (light red text, optionally an icon, optionally a subtle highlight background)
- Preserve normal scroll/feed behavior — narrative messages flow inline with the rest of the feed

**Implementation notes:**
- The Evennia color code `|R...|n` is light red; the existing text-feed should already have a color-code parser. If it does, the narrative tag flows through naturally — verify it does, or extend the parser.
- If the WebSocket event carries a `type` discriminator, prefer that over string-prefix matching.
- Tests: Vitest snapshot of a feed rendering with one narrative message and two normal messages, verifying CSS classes / styling.

Commit:
```
feat(narrative-fe): inline rendering of narrative messages in main text feed

Narrative messages from the backend (character.msg with type='narrative')
render in distinct light-red styling within the main game feed, alongside
normal messages. Players see narrative drops in real time without leaving
the feed view.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

---

### Task 1.3: Character-sheet messages section

**Files:**
- Investigate: existing character-sheet page (likely `frontend/src/roster/pages/CharacterSheetPage.tsx` per the roster/CLAUDE.md)
- Modify: that page to add a Messages tab/section
- Create: `frontend/src/narrative/components/MessagesSection.tsx` — the actual list component
- Create: `frontend/src/narrative/components/MessageRow.tsx` — single message row, with category badge, sender, body preview, ack button, link to related story if applicable

**Layout:**
- Tab or panel within the character sheet page
- Filter chips at top: All / Unread / Story / Atmosphere / Visions / Happenstance / System
- List of messages, unread first, then by sent_at desc
- Each row shows: category badge (color-coded), sender name (or "system"), body excerpt, sent_at relative time, ack button if unacknowledged
- Click a row to expand the full body inline; clicking "Acknowledge" calls `useAcknowledgeDelivery` and the row visually settles into "read" state
- Click a related-story link if `related_story` is populated → navigates to the story detail page (added in Wave 3; for now just disabled link with tooltip "story view coming soon")

Use Radix UI primitives — the existing components in `frontend/src/components/ui/` (Tabs, Badge, Button, etc.) cover this.

Commit:
```
feat(narrative-fe): messages section on character sheet page

Browseable history of narrative messages delivered to this character.
Category filter, unread-first ordering, inline expand, acknowledge
button. Story-tied messages link to the story detail page (Wave 3).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

---

### Task 1.4: Unread counter in top-level nav

**Files:**
- Investigate: top-level navigation component (likely `frontend/src/components/AppNav.tsx` or `frontend/src/components/Header.tsx`)
- Modify: that nav to show an unread-narrative badge

Use `useUnreadCount()` hook from queries.ts. If count > 0, render a small red badge with the number. Click → navigates to the messages section of the active character's sheet.

**Edge case:** if the user has multiple characters, decide whether the badge counts unread across all of them or only the currently-puppeted one. For Phase 4, scope to the currently-puppeted character — multi-character handling can be a Phase 5+ refinement.

Commit:
```
feat(narrative-fe): unread-narrative counter in top-level nav

Red badge displayed when the puppeted character has unacknowledged
narrative messages. Click navigates to the messages section.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

---

## Wave 2 — Stories API + types + queries layer

### Task 2.1: Stories API client

**Files:**
- Modify: `frontend/src/stories/api.ts`

Add a function per endpoint we'll consume in Waves 3-10. Group into sections by endpoint family:

```typescript
// stories
export async function getMyActiveStories(): Promise<MyActiveStoriesResponse> { ... }
export async function getStory(id: number): Promise<Story> { ... }
export async function getStoryLog(id: number): Promise<StoryLogResponse> { ... }
export async function listStories(filters?: ...): Promise<PaginatedStories> { ... }

// dashboards
export async function getGMQueue(): Promise<GMQueueResponse> { ... }
export async function getStaffWorkload(): Promise<StaffWorkloadResponse> { ... }

// chapters / episodes / beats / transitions
export async function listChapters(storyId: number): Promise<Chapter[]> { ... }
export async function listEpisodes(chapterId: number): Promise<Episode[]> { ... }
export async function listBeats(episodeId: number): Promise<Beat[]> { ... }
export async function listTransitions(sourceEpisodeId: number): Promise<Transition[]> { ... }

// progress (read)
export async function listGroupStoryProgress(filters?: ...): Promise<...> { ... }
export async function listGlobalStoryProgress(filters?: ...): Promise<...> { ... }

// AGM claims
export async function listAssistantGMClaims(filters?: ...): Promise<...> { ... }
export async function getAssistantGMClaim(id: number): Promise<...> { ... }

// session requests
export async function listSessionRequests(filters?: ...): Promise<...> { ... }

// CRUD for author editor (Wave 9)
export async function createStory(data: ...): Promise<Story> { ... }
export async function updateStory(id: number, data: ...): Promise<Story> { ... }
export async function deleteStory(id: number): Promise<void> { ... }
// ...same for Chapter, Episode, Beat, Transition

// actions
export async function resolveEpisode(storyId: number, body: { chosen_transition?: number; gm_notes?: string }): Promise<EpisodeResolution> { ... }
export async function markBeat(beatId: number, body: { outcome: BeatOutcome; gm_notes?: string; progress?: number }): Promise<BeatCompletion> { ... }
export async function contributeToBeat(beatId: number, body: { points: number; source_note?: string; character_sheet: number }): Promise<AggregateBeatContribution> { ... }
export async function approveClaim(claimId: number, body?: { framing_note?: string }): Promise<AssistantGMClaim> { ... }
export async function rejectClaim(claimId: number, body: { rejection_note?: string }): Promise<AssistantGMClaim> { ... }
export async function cancelClaim(claimId: number): Promise<AssistantGMClaim> { ... }
export async function completeClaim(claimId: number): Promise<AssistantGMClaim> { ... }
export async function requestClaim(body: { beat: number; framing_note?: string }): Promise<AssistantGMClaim> { ... }
export async function createEventFromSessionRequest(requestId: number, body: { name: string; scheduled_real_time: string; host_persona: number; location_id: number; description?: string; is_public?: boolean }): Promise<Event> { ... }
export async function cancelSessionRequest(requestId: number): Promise<SessionRequest> { ... }
export async function resolveSessionRequest(requestId: number): Promise<SessionRequest> { ... }
export async function expireOverdueBeats(): Promise<{ expired_count: number }> { ... }
```

Each is a thin `apiFetch` wrapper. Errors throw with descriptive messages.

Commit:
```
feat(stories-fe): full stories API client surface

API functions for every Phase 1-3 backend endpoint: list/detail reads,
dashboards, action endpoints, author CRUD. Wave 3+ consume these.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

---

### Task 2.2: Stories types

**Files:**
- Modify: `frontend/src/stories/types.ts`

Re-export the generated types with local aliases for the most-used shapes. Add any frontend-only utility types (e.g., a `StoryStatusLine` shape that combines progress + episode + status).

```typescript
// types.ts
import type { components } from '@/generated/api';

export type Story = components['schemas']['Story'];
export type Chapter = components['schemas']['Chapter'];
export type Episode = components['schemas']['Episode'];
export type Beat = components['schemas']['Beat'];
export type Transition = components['schemas']['Transition'];
export type StoryProgress = components['schemas']['StoryProgress'];
export type GroupStoryProgress = components['schemas']['GroupStoryProgress'];
export type GlobalStoryProgress = components['schemas']['GlobalStoryProgress'];
export type AnyStoryProgress = StoryProgress | GroupStoryProgress | GlobalStoryProgress;
export type BeatCompletion = components['schemas']['BeatCompletion'];
export type EpisodeResolution = components['schemas']['EpisodeResolution'];
export type AggregateBeatContribution = components['schemas']['AggregateBeatContribution'];
export type AssistantGMClaim = components['schemas']['AssistantGMClaim'];
export type SessionRequest = components['schemas']['SessionRequest'];

export type BeatPredicateType = NonNullable<Beat['predicate_type']>;
export type BeatOutcome = NonNullable<Beat['outcome']>;
export type BeatVisibility = NonNullable<Beat['visibility']>;
export type StoryScope = NonNullable<Story['scope']>;
export type AssistantClaimStatus = NonNullable<AssistantGMClaim['status']>;
export type SessionRequestStatus = NonNullable<SessionRequest['status']>;
```

Commit with the api.ts changes (squash into Task 2.1's commit if possible) or as its own minor commit.

---

### Task 2.3: Stories React Query hooks

**Files:**
- Modify: `frontend/src/stories/queries.ts`

Standard query-keys + hooks. For mutations, invalidate appropriate caches.

```typescript
export const storiesKeys = {
  all: ['stories'] as const,
  myActive: () => [...storiesKeys.all, 'my-active'] as const,
  story: (id: number) => [...storiesKeys.all, 'story', id] as const,
  storyLog: (id: number) => [...storiesKeys.all, 'story', id, 'log'] as const,
  gmQueue: () => [...storiesKeys.all, 'gm-queue'] as const,
  staffWorkload: () => [...storiesKeys.all, 'staff-workload'] as const,
  chapters: (storyId: number) => [...storiesKeys.all, 'story', storyId, 'chapters'] as const,
  episodes: (chapterId: number) => [...storiesKeys.all, 'chapter', chapterId, 'episodes'] as const,
  beats: (episodeId: number) => [...storiesKeys.all, 'episode', episodeId, 'beats'] as const,
  transitions: (sourceEpisodeId: number) => [...storiesKeys.all, 'episode', sourceEpisodeId, 'transitions'] as const,
  // ...etc
};

export function useMyActiveStories() {
  return useQuery({ queryKey: storiesKeys.myActive(), queryFn: getMyActiveStories, throwOnError: true });
}

export function useStory(id: number) {
  return useQuery({ queryKey: storiesKeys.story(id), queryFn: () => getStory(id), enabled: id > 0, throwOnError: true });
}

export function useStoryLog(id: number) {
  return useQuery({ queryKey: storiesKeys.storyLog(id), queryFn: () => getStoryLog(id), enabled: id > 0, throwOnError: true });
}

// ...etc

// Mutations
export function useResolveEpisode() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ storyId, ...body }: { storyId: number; chosen_transition?: number; gm_notes?: string }) =>
      resolveEpisode(storyId, body),
    onSuccess: (_, { storyId }) => {
      qc.invalidateQueries({ queryKey: storiesKeys.story(storyId) });
      qc.invalidateQueries({ queryKey: storiesKeys.storyLog(storyId) });
      qc.invalidateQueries({ queryKey: storiesKeys.myActive() });
      qc.invalidateQueries({ queryKey: storiesKeys.gmQueue() });
    },
  });
}

export function useMarkBeat() { ... }
export function useContributeToBeat() { ... }
export function useApproveClaim() { ... }
// ...etc
```

Commit:
```
feat(stories-fe): React Query hooks layer

useMyActiveStories, useStory, useStoryLog, useGMQueue, useStaffWorkload,
plus mutation hooks for every action endpoint with sensible cache
invalidation.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

---

## Wave 3 — Player active-stories + story detail (read-only)

### Task 3.1: My Active Stories page

**File:** `frontend/src/stories/pages/MyActiveStoriesPage.tsx`

Layout:
- Page title: "My Stories"
- Filter chips: All / Personal / Group / Global (mapped to `Story.scope`)
- List of stories — one card per story:
  - Story title + scope badge
  - Status one-liner (e.g., "Chapter 1, Episode 3 — waiting on you" or "ready to schedule")
  - Last advanced time (relative, e.g., "Last advanced 3 days ago")
  - Click → navigate to `/stories/:id`

Use the `useMyActiveStories` hook. Loading skeleton; error boundary at the page level.

Commit:
```
feat(stories-fe): My Active Stories page (read-only)
```

---

### Task 3.2: Story detail page — current episode panel + beat list

**File:** `frontend/src/stories/pages/StoryDetailPage.tsx`

Layout:
- Header: story title, scope badge, current chapter/episode breadcrumb
- Three sections:
  1. **Current Episode panel** — episode title, summary (if visible to player), list of beats with:
     - Beat title (or hint text for HINTED beats)
     - Beat outcome state (UNSATISFIED / SUCCESS / FAILURE / EXPIRED)
     - For aggregate beats: progress bar (current / required_points)
     - For deadlined beats: time remaining
     - Player resolution text (once SUCCESS, shown inline)
  2. **Story log** (placeholder for Task 3.3)
  3. **Schedule CTA** (placeholder for Wave 4)

Visibility filtering happens server-side via `useStoryLog`; the frontend just renders what the API returns.

For non-CHARACTER scope stories, show participant info: GROUP shows GMTable name + member count; GLOBAL shows total active StoryParticipations.

Commit:
```
feat(stories-fe): Story detail page — current episode + beat list
```

---

### Task 3.3: Story log reader component

**Files:**
- Create: `frontend/src/stories/components/StoryLog.tsx`
- Modify: `frontend/src/stories/pages/StoryDetailPage.tsx` to mount it

The story log is a chronological timeline:
- BeatCompletion entries (rendered with `beat.player_resolution_text`)
- EpisodeResolution entries (rendered with `transition.connection_summary` + `connection_type`)
- (Phase 4-deferred) StoryMessage entries — backend doesn't have a sender endpoint yet, so frontend shows whatever exists in the log_entries response

Layout:
- Vertical timeline with timestamp markers
- Each entry: icon by type (beat / episode / message), category color, sender (for messages), body
- "Load more" button for pagination if applicable

Commit:
```
feat(stories-fe): Story log reader timeline component
```

---

## Wave 4 — Player action UIs

### Task 4.1: Aggregate-contribute action

**Files:**
- Create: `frontend/src/stories/components/ContributeBeatDialog.tsx`
- Modify: `StoryDetailPage.tsx` to surface a "Contribute" button on aggregate beats

When the player has an active CharacterSheet AND the beat is `AGGREGATE_THRESHOLD` AND the beat is in their active episode:
- Show a "Contribute" button on the beat row
- Click → opens a Radix Dialog with:
  - Points input (number, min 1, max remaining-to-threshold)
  - Source note text area
  - Character selector (if the player has multiple characters; auto-select if only one)
  - Submit → `useContributeToBeat` mutation
  - On success: close dialog, refresh beat data, show toast "Contribution recorded"

Surface DRF validation errors inline (e.g., "points must be ≤ remaining").

Commit:
```
feat(stories-fe): aggregate-contribute action dialog
```

---

### Task 4.2: Session-request flow UI

**Files:**
- Create: `frontend/src/stories/components/ScheduleSessionDialog.tsx`
- Modify: `StoryDetailPage.tsx` to show "Schedule Session" CTA when an open SessionRequest exists for the current episode

When the current episode has an OPEN SessionRequest visible to the player:
- Show "Schedule Session" CTA
- Click → dialog with:
  - "Schedule with my GM" / "Open to first-available GM" radio (CHARACTER scope only — GROUP/GLOBAL handled by GM)
  - Notes field (optional)
  - Submit → updates the SessionRequest's `assigned_gm` and `open_to_any_gm` fields (need a backend update endpoint — verify it exists or add it)

If no update endpoint exists for these fields specifically, this becomes "open the SessionRequest in the schedule view" linking to a Lead-GM-only schedule action. For Phase 4, flag and implement the simpler version: player can just open the request to first-available; the actual scheduling form is GM-side.

Commit:
```
feat(stories-fe): player session-request flow UI
```

---

## Wave 5 — Lead GM queue dashboard

### Task 5.1: GM queue page

**File:** `frontend/src/stories/pages/GMQueuePage.tsx`

Layout:
- Page title: "GM Queue"
- Tabs/sections:
  - **Episodes ready to run** — from `useGMQueue`. Each row: story title, scope, episode title, eligible-transitions count, "Resolve" CTA (Wave 6.1)
  - **AGM claims pending approval** — pending claims on stories where I'm Lead GM, with approve/reject buttons (Wave 6.3)
  - **My session requests** — assigned + open requests with status, "Schedule" CTA (Wave 6.4)

Permission-gated: only render for users with a GMProfile. Use a `RequireGM` wrapper component or check `request.user.gm_profile` at the route level.

Commit:
```
feat(stories-fe): Lead GM queue dashboard
```

---

## Wave 6 — GM action UIs

### Task 6.1: Resolve-episode action

**Files:**
- Create: `frontend/src/stories/components/ResolveEpisodeDialog.tsx`
- Modify: `GMQueuePage.tsx` and `StoryDetailPage.tsx` to mount the dialog

Dialog:
- Show eligible transitions as radio options (each shows target episode + connection_summary)
- If only one AUTO transition: "Resolve" button auto-fires
- If GM_CHOICE: GM must select one
- GM notes textarea
- Submit → `useResolveEpisode` mutation
- On success: close dialog, refresh story data, toast "Episode resolved"

Surface validation errors (e.g., race-condition `NoEligibleTransitionError` from Phase 2).

Commit:
```
feat(stories-fe): Resolve-episode action dialog (GM-only)
```

---

### Task 6.2: Mark-beat action (GM-only)

**Files:**
- Create: `frontend/src/stories/components/MarkBeatDialog.tsx`
- Modify: `GMQueuePage.tsx` and `StoryDetailPage.tsx` to surface "Mark beat" on GM_MARKED beats

Dialog:
- Outcome selector (SUCCESS / FAILURE)
- GM notes textarea
- Progress selector (CHARACTER scope auto-pick; GROUP needs the right group_progress; GLOBAL singleton)
- Submit → `useMarkBeat` mutation

Permission-gated: only Lead GM on the beat's story OR an AGM with an APPROVED claim on this beat.

Commit:
```
feat(stories-fe): Mark-beat action dialog (Lead GM + claimed AGM)
```

---

### Task 6.3: AGM claim approve/reject UIs

**Files:**
- Create: `frontend/src/stories/components/ApproveClaimDialog.tsx`
- Create: `frontend/src/stories/components/RejectClaimDialog.tsx`
- Modify: `GMQueuePage.tsx` to surface them on each pending-claim row

Approve dialog:
- Optional framing-note textarea (Lead GM authors framing for the AGM session)
- Submit → `useApproveClaim` mutation

Reject dialog:
- Optional rejection-note textarea
- Submit → `useRejectClaim` mutation

Commit:
```
feat(stories-fe): AGM claim approve/reject action dialogs
```

---

### Task 6.4: Schedule session (create event from session request)

**Files:**
- Create: `frontend/src/stories/components/ScheduleEventDialog.tsx`
- Modify: `GMQueuePage.tsx` to surface scheduling on open session requests

Dialog:
- Event name input
- Scheduled real time (datetime picker)
- Host persona selector (defaults to GM's primary persona)
- Location selector (RoomProfile picker — investigate existing component reuse from `frontend/src/events/`)
- Description textarea (optional)
- Public? checkbox
- Submit → `useCreateEventFromSessionRequest` mutation

On success: link to the created Event in the events feature (open in new tab).

Commit:
```
feat(stories-fe): GM schedule-event dialog from session request
```

---

## Wave 7 — AGM claim flow UI

### Task 7.1: Browse AGM-eligible beats + request claim

**Files:**
- Create: `frontend/src/stories/pages/AGMOpportunitiesPage.tsx`
- Create: `frontend/src/stories/components/RequestClaimDialog.tsx`

Page layout:
- Filter to beats where `agm_eligible=true` AND no current REQUESTED/APPROVED claim from this AGM
- Each row shows: beat description (limited info), parent episode/story title, GM/staff context
- "Request claim" button → dialog with optional framing note (or read-only display of what the Lead GM has set)
- Submit → `useRequestClaim` mutation

Permission-gated: any user with a GMProfile (not just Lead GMs).

Commit:
```
feat(stories-fe): AGM browse opportunities + request claim
```

---

### Task 7.2: My claims view

**File:** `frontend/src/stories/pages/MyAGMClaimsPage.tsx`

Lists the user's own AGM claims grouped by status (REQUESTED / APPROVED / etc.). For APPROVED claims, surface the beat + framing note + "Mark beat" CTA (uses Task 6.2's dialog). For REJECTED, show the rejection note. For COMPLETED, show as history.

Commit:
```
feat(stories-fe): My AGM claims page
```

---

## Wave 8 — Staff workload dashboard

### Task 8.1: Staff workload page

**File:** `frontend/src/stories/pages/StaffWorkloadPage.tsx`

Layout:
- Page title: "Staff Workload"
- Sections:
  - **All active stories** — sortable table (story, scope, GM, last_advanced_at, episode count)
  - **Stale stories** — stories not advanced in N days (server provides; show staleness indicator)
  - **Pending AGM claims** — across all stories
  - **Open session requests** — across all stories
  - **Manual actions** — "Expire overdue beats" button (calls `useExpireOverdueBeats` mutation)

Permission-gated: staff only.

Commit:
```
feat(stories-fe): Staff workload dashboard
```

---

## Wave 9 — Story author editor

### Task 9.1: Story / Chapter / Episode CRUD forms

**Files:**
- Create: `frontend/src/stories/pages/StoryAuthorPage.tsx`
- Create: `frontend/src/stories/components/StoryFormDialog.tsx`
- Create: `frontend/src/stories/components/ChapterFormDialog.tsx`
- Create: `frontend/src/stories/components/EpisodeFormDialog.tsx`

Page:
- Sidebar: list of stories the user is Lead GM on (or all stories for staff)
- Click a story → main panel shows tree: chapters → episodes
- Edit/Add buttons at each level
- Form dialogs surface DRF validation errors inline

Commit:
```
feat(stories-fe): author editor — Story/Chapter/Episode CRUD
```

---

### Task 9.2: Beat CRUD with predicate-type-driven config form

**File:** `frontend/src/stories/components/BeatFormDialog.tsx`

The form's shape changes based on `predicate_type`. Use a discriminated-union pattern in the form state.

For each predicate type, render the appropriate config inputs:
- `GM_MARKED`: nothing extra
- `CHARACTER_LEVEL_AT_LEAST`: `required_level` number input
- `ACHIEVEMENT_HELD`: `required_achievement` selector (autocomplete from `/api/achievements/`)
- `CONDITION_HELD`: `required_condition_template` selector
- `CODEX_ENTRY_UNLOCKED`: `required_codex_entry` selector
- `STORY_AT_MILESTONE`: `referenced_story` + `referenced_milestone_type` + (chapter or episode based on milestone type)
- `AGGREGATE_THRESHOLD`: `required_points` number input

Plus shared fields: title, internal description, player hint, player resolution text, visibility, optional deadline, agm_eligible flag.

Submit → `useCreateBeat` / `useUpdateBeat` mutation. DRF validation via `Beat.clean()` surfaces field-level errors.

Commit:
```
feat(stories-fe): Beat form with predicate-type-driven config
```

---

### Task 9.3: Transition CRUD with routing predicate

**Files:**
- Create: `frontend/src/stories/components/TransitionFormDialog.tsx`

Form:
- Source episode (read-only — context-determined)
- Target episode selector (or "frontier — leave null")
- Mode (AUTO / GM_CHOICE)
- Connection type (THEREFORE / BUT)
- Connection summary textarea
- TransitionRequiredOutcome rows: each row pairs a beat (selector) with a required_outcome (enum dropdown). "Add outcome" button to add rows.
- Order (for tie-breaking)

Submit → CRUD mutations.

Commit:
```
feat(stories-fe): Transition form with routing predicate rows
```

---

### Task 9.4: EpisodeProgressionRequirement add/remove

**File:** `frontend/src/stories/components/ProgressionRequirementsEditor.tsx`

Embedded in the Episode form: a list of required (beat, required_outcome) pairs. "Add requirement" / "Remove" buttons.

Commit:
```
feat(stories-fe): Episode progression-requirements editor
```

---

## Wave 10 — Episode DAG visualization

### Task 10.1: Install React Flow

**Files:**
- Modify: `frontend/package.json` — add `reactflow` dep
- Run: `pnpm install`

Test: `pnpm dev` starts cleanly with the new dep.

Commit:
```
build(frontend): add reactflow for episode DAG visualization
```

---

### Task 10.2: Episode DAG view

**File:** `frontend/src/stories/components/EpisodeDAG.tsx`

Read-only visualization of an episode graph:
- Nodes: episodes (color-coded by reached/current/future)
- Edges: transitions (labeled with connection_type and abbreviated routing predicate)
- Layout: dagre-driven (top-to-bottom or left-to-right)
- Click a node → opens that episode in the author editor

Mount on the StoryAuthorPage as a panel toggle alongside the tree view.

Commit:
```
feat(stories-fe): Episode DAG visualization (read-only)
```

---

## Wave 11 — Routing, navigation, polish

### Task 11.1: Register Phase 4 routes in App.tsx

Add routes:
- `/stories/my-active` → `MyActiveStoriesPage`
- `/stories/:id` → `StoryDetailPage`
- `/stories/gm-queue` → `GMQueuePage` (gated on GM role)
- `/stories/agm-opportunities` → `AGMOpportunitiesPage`
- `/stories/my-claims` → `MyAGMClaimsPage`
- `/stories/staff-workload` → `StaffWorkloadPage` (staff only via `StaffRoute`)
- `/stories/author/:storyId?` → `StoryAuthorPage` (GM/staff only)

Use `React.lazy()` at the route level for code splitting (per CLAUDE.md) — never `manualChunks` for app code.

Commit:
```
feat(frontend): register stories Phase 4 routes
```

---

### Task 11.2: Top-level navigation entries

Add navigation links in the appropriate header / sidebar component:
- Player: "My Stories" → `/stories/my-active`
- GM (visible if user has GMProfile): "GM Queue", "AGM Opportunities", "My Claims"
- Staff: "Staff Workload", "Story Author"

Use the existing role-checking pattern.

Commit:
```
feat(frontend): top-level navigation for Phase 4 stories pages
```

---

### Task 11.3: Loading skeletons + error boundaries

Each page needs:
- Loading skeleton component (Tailwind `animate-pulse` placeholders)
- Error boundary at the route level (use the existing ErrorBoundary component)

Verify each page degrades gracefully when:
- API call fails
- User has no relevant data (empty states with friendly copy)
- User lacks permissions (redirect or show explicit "you don't have access" page)

Commit:
```
feat(stories-fe): loading skeletons + error boundaries across all pages
```

---

## Wave 12 — E2E Playwright tests

### Task 12.1: Player happy path

**File:** `frontend/e2e/stories-player.spec.ts`

Test scenario:
1. Log in as a player
2. Navigate to "My Stories"
3. Click into the first active story
4. See the current episode and beat list
5. Click "Acknowledge" on a narrative message in the messages section
6. Verify the unread counter decrements

Setup uses Django fixtures or test factories that pre-seed the data. Run via `pnpm test:e2e` after `pnpm build`.

Commit:
```
test(stories-fe): Playwright e2e — player happy path
```

---

### Task 12.2: GM happy path

**File:** `frontend/e2e/stories-gm.spec.ts`

Test scenario:
1. Log in as a Lead GM
2. Navigate to GM Queue
3. See an episode ready to run
4. Click "Resolve" → select a transition → submit
5. Verify episode advances
6. Approve a pending AGM claim

Commit:
```
test(stories-fe): Playwright e2e — Lead GM happy path
```

---

### Task 12.3: Final regression + docs

- Update `docs/roadmap/stories-gm.md` to mark Phase 4 complete; restructure remaining items as Phase 5+
- Update `frontend/src/stories/CLAUDE.md` and `frontend/src/narrative/CLAUDE.md` with the actual implemented file inventory
- Run full backend regression: `echo "yes" | uv run arx test` (no backend changes expected, but verify nothing in Phase 4's schema regen broke anything)
- Run frontend regression: `pnpm test`, `pnpm test:e2e`, `pnpm typecheck`, `pnpm lint`, `pnpm build`

Commit:
```
docs(stories-fe): Phase 4 complete — update roadmap, feature CLAUDE.md
```

---

## Execution Notes

- **Order dependencies:** Wave 0 must land first (types). Wave 1 depends on 0 only. Wave 2 must land before 3-10. Within Waves 3-10, mostly independent except 4 depends on 3, 6 depends on 5.
- **Visual verification:** Frontend work needs visual verification more than backend did. After each Wave that ships UI, run `pnpm dev`, log in, and click through. Backend phases relied entirely on tests; frontend tests catch logic but not visual correctness.
- **API mismatches:** The Phase 4 plan assumes the schema regen surfaces all needed types. If a needed shape isn't there (e.g., `MyActiveStoriesResponse` shape), either fix the backend serializer (small backend addition) or extend the local types in `types.ts`.
- **Author editor scope:** The author editor (Wave 9) is the most complex piece. If time pressure surfaces, it could be split off to Phase 4b — but the user has explicitly said to build at full depth.
- **Pre-commit hooks:** ESLint, Prettier, TypeScript check, Frontend Build all run on commit. Fix and re-stage; never `--no-verify`.
- **Production verification:** After Wave 11, run `pnpm build` and verify the bundle loads against the production server (port 4001), not just dev (port 3000). Per `frontend/CLAUDE.md`, dev mode resolves ESM differently and won't catch all production bugs.

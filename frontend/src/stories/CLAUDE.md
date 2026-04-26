# Stories - Narrative Campaign UI

Frontend for the `world.stories` backend app. Player dashboards, story
detail and log reader, action UIs (mark beat / contribute / schedule /
acknowledge), Lead GM queue, AGM claim management, staff workload
dashboard, and story author editor.

## Key Directories

### `components/`

Feature-specific components added during Phase 4 Waves 3-10.

### `pages/`

Page-level routes added during Phase 4 Waves 3-10:

- `MyActiveStoriesPage` — player's active stories list
- `StoryDetailPage` — current episode, beat list, story log
- `GMQueuePage` — Lead GM queue dashboard
- `AGMOpportunitiesPage` — AGM browse + request claim
- `MyAGMClaimsPage` — AGM claims status
- `StaffWorkloadPage` — staff cross-story view
- `StoryAuthorPage` — author CRUD editor with episode DAG visualization

## Key Files

### API Integration

- **`api.ts`**: REST API functions for stories operations
- **`queries.ts`**: React Query hooks
- **`types.ts`**: TypeScript definitions, re-exported from generated API types

## Data Flow

- **REST API**: Full CRUD via `/api/stories/`, `/api/beats/`, `/api/transitions/`, `/api/group-story-progress/`, `/api/global-story-progress/`, `/api/aggregate-beat-contributions/`, `/api/assistant-gm-claims/`, `/api/session-requests/`
- **Custom actions**: `resolve-episode`, `mark`, `contribute`, `approve` / `reject` / `complete` / `cancel` claim, `create-event`, `expire-beats`
- **Dashboards**: `my-active`, `gm-queue`, `staff-workload`

## Integration Points

- **Backend Models**: All `world.stories` models
- **Narrative**: Beat completions and episode resolutions emit narrative messages; story log surfaces them
- **Events**: Session requests bridge to `world.events.Event` via the create-event-from-session-request action
- **Character Sheets**: `Story.character_sheet` ownership for CHARACTER scope; player dashboards filter by puppeted character
- **GM**: `GMTable` ownership for GROUP scope; `GMProfile` for permissions

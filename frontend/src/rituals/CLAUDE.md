# Rituals Module

Frontend for the ritual system. Allows players to browse available rituals and
perform them via `POST /api/magic/rituals/perform/`. Implemented in Phase 2 of
the Soul Tether UI (Wave soul-tether-ui).

## File Inventory

### `types.ts`

TypeScript types for the rituals feature.

- `Ritual` — re-export from generated schema (`components['schemas']['Ritual']`)
- `PaginatedRitualList` — re-export from generated schema; `count/next/previous/results`
- `RitualFieldType` — union of known field type strings for `RitualField.type`
- `RitualField` — a single field descriptor in an `input_schema` blob
- `RitualInputSchema` — `{ fields: RitualField[] }` — typed overlay for the
  generated `Ritual.input_schema: unknown`
- `RitualWithSchema` — `Ritual` with `input_schema` typed as `RitualInputSchema | null`
  instead of `unknown`; use this when rendering the perform form
- `PerformRitualRequest` — body for `POST /api/magic/rituals/perform/`
  (`ritual_id`, `character_sheet_id`, `kwargs`, optional `components`)
- `PerformRitualResponse` — response shape from `perform/`

### `api.ts`

REST API client for `/api/magic/rituals/`.

- `getRituals()` — `GET /api/magic/rituals/` → `PaginatedRitualList`
- `getRitual(id)` — `GET /api/magic/rituals/{id}/` → `Ritual`
- `performRitual(body)` — `POST /api/magic/rituals/perform/` → `PerformRitualResponse`

### `queries.ts`

React Query hooks with a `ritualKeys` query key factory.

- **Key factory:** `ritualKeys.all`, `ritualKeys.list()`, `ritualKeys.detail(id)`
- **Reads:** `useRituals()`, `useRitual(id)`
- **Mutations:** `usePerformRitual()` — invalidates `list` and `all` on success

### `__tests__/queries.test.tsx`

Unit tests for the query hooks. Uses vi.fn mocks of `api.*` (no msw).

- `useRituals` — fetches list, enters error state on failure
- `useRitual` — fetches by id, skips fetch for id ≤ 0
- `usePerformRitual` — POSTs correct body, handles optional `components`
- `ritualKeys` — key shape assertions

## Data Flow

- **REST API:** Read-only browse via `GET /api/magic/rituals/` and `/{id}/`
- **Perform:** `POST /api/magic/rituals/perform/` dispatches the ritual
  server-side (SERVICE or FLOW execution kind)
- **input_schema:** Backend-authored blob; frontend renders dynamic form fields
  from `RitualField[]` based on `type` discriminator

## Integration Points

- **Backend:** `world.magic` — `Ritual` model, `RitualViewSet`, `RitualPerformView`
- **Serializer body shape:** `RitualPerformRequestSerializer`
  (`ritual_id`, `character_sheet_id`, `kwargs`, `components`)
- **Consumers:** `RitualForm` (Task 2.4), `RitualPerformDialog` (Task 2.5),
  `RitualsListPage` (Task 2.6)

## Ritual Session UI (Induction and Multi-Participant Rituals)

### `RitualSessionDetailPage` / `RitualSessionResponseDialog`

`RitualSessionDetailPage` fetches the session via `useRitualSessionDetail` and passes
`participantFieldsSchema` (parsed from `session.participant_fields`, the serialized
`input_schema.participant_fields` blob) down to `RitualSessionResponseDialog`.

`RitualSessionResponseDialog` handles the invitee accept / decline flow with an optional
participant-fields form:

- **`participantFieldsSchema`** prop — `RitualInputSchema | null`. When provided, Accept
  renders a `RitualForm` for the fields the participant must fill in before accepting.
- **`applies_to` gating** — fields with `applies_to === "candidate_only"` are hidden from
  the session initiator (`participantId === session.initiator_id`). The `effectiveSchema`
  reflects only the fields the current viewer should fill in.
- **`emits_reference` conversion** — on accept, any field with `emits_reference` is NOT
  sent in `participant_kwargs`; instead it becomes an entry in the `references` array
  (`{ kind: emits_reference, ref_<kind>_id: value }`). Currently wired kinds:
  `COVENANT_ROLE → ref_covenant_role_id`, `COVENANT → ref_covenant_id`.
- **`depends_on` path resolution** — `CovenantRolePickerField` declares
  `depends_on: "session.target_covenant.covenant_type"`. The dialog resolves this by:
  1. Reading the `COVENANT`-kind entry from `session.session_references` (primary path).
  2. Falling back to `session_kwargs.target_covenant` for older sessions.
  3. Fetching `GET /api/covenants/covenants/{id}/` to get `covenant_type`.
  4. Injecting the resolved value into `formValues` under the full
     `"session.target_covenant.covenant_type"` key — so `CovenantRolePickerField`
     reads it via `formValues[field.depends_on]` with no changes to the field component.

### `RitualField` descriptors (extended)

Two optional fields on `RitualField` gate the induction participant flow:

| Field             | Type                     | Meaning                                                                                                                      |
| ----------------- | ------------------------ | ---------------------------------------------------------------------------------------------------------------------------- |
| `emits_reference` | `string` (ReferenceKind) | Field value is sent as a typed `RitualSessionReference` on accept (not in `participant_kwargs`). Example: `"COVENANT_ROLE"`. |
| `applies_to`      | `string`                 | Audience gate for rendering. `"candidate_only"` hides the field from the session initiator.                                  |

These are defined in `RitualField` in `types.ts` and used by `RitualSessionResponseDialog`.
The `participant_fields` schema lives in `input_schema.participant_fields` on the backend
`Ritual` model and is exposed by `RitualSessionDetailSerializer.participant_fields`.

### Test coverage

- `frontend/src/rituals/__tests__/RitualSessionPages.test.tsx` — component tests for
  `RitualSessionResponseDialog` covering: role-picker rendering from `participantFieldsSchema`,
  `emits_reference` → `references` conversion on accept, and `candidate_only` field hiding
  for the initiator.

## Common Gotchas

**`Ritual.input_schema` is `unknown` in the generated types.** Cast the ritual to
`RitualWithSchema` before accessing `input_schema.fields`. Never cast to `any`.

**`PaginatedRitualList.results` is optional in the generated type.**
Always guard with `?? []` when mapping over results.

**`ritual_id` in `PerformRitualRequest` is the Ritual PK.** The backend
`RitualPerformRequestSerializer` accepts `ritual_id` as a PrimaryKeyRelatedField
and resolves it server-side — do not pass the full Ritual object.

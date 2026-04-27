# Tables - GM Table Management UI

Frontend for the GM table system. Allows GMs to manage their tables,
invite players, and view table-scoped stories. Implemented in Phase 5 (Wave 4).

Folder placement decision: placed under `frontend/src/tables/` (not `gm/tables/`)
because no `frontend/src/gm/` directory existed at the time of creation.
If a `gm/` module is created in a future wave, consider consolidating.

## File Inventory

### `api.ts`

REST API client for `/api/gm/tables/` and `/api/gm/table-memberships/`.

- **Table reads:** `getTables()`, `getTable()`
- **Table writes:** `createTable()`, `updateTable()`
- **Table actions:** `archiveTable()`, `transferOwnership()`
- **Membership reads:** `getTableMemberships()`
- **Membership writes:** `inviteToTable()`, `removeMembership()`, `leaveTable()`

### `queries.ts`

React Query hooks with a `tablesKeys` query key factory.

- **Reads:** `useTables()`, `useTable()`, `useTableMembers()`
- **Table mutations:** `useCreateTable()`, `useUpdateTable()`, `useArchiveTable()`,
  `useTransferOwnership()`
- **Membership mutations:** `useInviteToTable()`, `useRemoveMembership()`, `useLeaveTable()`

### `types.ts`

TypeScript types for the tables feature.

- `GMTable` — extends the generated `GMTableBase` with `member_count`, `story_count`,
  `viewer_role` (computed fields returned by `GMTableSerializer`)
- `GMTableMembership` — re-export from generated schema
- `GMTableViewerRole` — `'gm' | 'staff' | 'member' | 'guest' | 'none'`
- Request body shapes: `GMTableCreateBody`, `GMTableUpdateBody`, `GMTableTransferBody`,
  `GMTableMembershipCreateBody`
- Paginated wrappers: `PaginatedTables`, `PaginatedMemberships`

### `components/`

| File                        | Purpose                                     |
| --------------------------- | ------------------------------------------- |
| `TableCard.tsx`             | Clickable table card for the list page      |
| `TableMemberRoster.tsx`     | Member list in the table detail Members tab |
| `TableStoryRoster.tsx`      | Story list in the table detail Stories tab  |
| `TableFormDialog.tsx`       | Create + edit table dialog                  |
| `InviteToTableDialog.tsx`   | GM invites a persona to the table           |
| `RemoveFromTableDialog.tsx` | GM confirms removing a member               |
| `LeaveTableDialog.tsx`      | Player confirms leaving the table           |
| `ArchiveTableDialog.tsx`    | GM archives the whole table                 |

### `pages/`

| File                  | Route (Wave 11 will register) | Auth           |
| --------------------- | ----------------------------- | -------------- |
| `TablesListPage.tsx`  | `/tables`                     | ProtectedRoute |
| `TableDetailPage.tsx` | `/tables/:id`                 | ProtectedRoute |

## Data Flow

- **REST API:** Full CRUD via `/api/gm/tables/`, `/api/gm/table-memberships/`
- **Custom actions:** `archive`, `transfer_ownership`
- **viewer_role:** `'gm' | 'staff' | 'member' | 'guest' | 'none'` — controls
  which UI sections are shown (GM sees all; member sees scoped; guest sees stories only)

## Integration Points

- **Backend:** `world.gm` models (GMTable, GMTableMembership, GMProfile)
- **Stories:** Stories with `primary_table` set appear in the table detail
- **Persona search:** Reuses `searchPersonas` from `@/events/queries`
- **Navigation:** Wave 11 will add `/tables` route to App.tsx routing

## Common Gotchas

**`member_count`, `story_count`, `viewer_role` are not in the generated schema.**
The generated `GMTable` type from `api.d.ts` reflects the old serializer before
Phase 5 added these computed fields. The local `GMTable` interface in `types.ts`
extends `GMTableBase` to add them. After the next `openapi-typescript` schema
regeneration, check if these fields appear in the generated type and remove the
extension.

**`viewer_role === 'none'` can appear even for logged-in users.** Tables are
visible (non-404) to any authenticated user if the backend queryset allows it.
A `viewer_role` of `'none'` means the user has no relationship to this table;
show read-only mode.

**Persona search reuses `searchPersonas` from `@/events/queries`.** The pattern
was established in `ScheduleEventDialog.tsx` — a debounced text search against
`/api/personas/?search=`. Reuse it directly rather than duplicating.

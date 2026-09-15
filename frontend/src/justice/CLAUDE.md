# Justice Module

Frontend for justice-system surfaces: the crime tab's warrant rows (#1765),
the wanted board + trial/pardon/lie-low/bribe flows (#2378, #1826), and the
witness reaction pop-up (#2987).

## File Inventory

### `api.ts`

Fetch functions over `apiFetch`. Warrants/cases: `fetchPersonaHeat`
(`/api/justice/heat/` - self-only, tiers never raw heat), `fetchWantedList`,
`fetchMyCase`, `postEvidence`, `postTrial`, `postPardon`, `postLieLow`,
`postBribe`. Witness windows (#2987): `getPendingWitnessWindows` - GET
`/api/reaction-windows/pending/` (`kind` defaults to `witness` server-side) →
`PaginatedPendingReactionWindowList`; backend is
`ReactionWindowViewSet.pending` (`src/world/scenes/reaction_views.py`).
Type re-exports from the generated schema include `PersonaHeatRow`,
`PendingReactionWindow`, `PaginatedPendingReactionWindowList`.

### `queries.ts`

React Query hooks. Warrants/cases: `usePersonaHeat`, `useWantedList`,
`useMyCase`, `useSubmitEvidenceMutation`, `useInitiateTrialMutation`,
`usePardonMutation`, `useLieLowMutation`, `useBribeMutation` (mutations
invalidate the `['justice']` prefix). Witness windows (#2987):

- `usePendingWitnessWindows(enabled)` - 5 s poll, mounted only inside the
  active scene view; no `throwOnError` (the gate degrades to rendering
  nothing on fetch errors). Mirrors `usePendingEntryFlourishOffers`
  (`@/magic/queries`).
- `useReactToWindow()` - mutation wrapping the shared `reactToWindow`
  transport (`@/scenes/queries`, POST `/api/reaction-windows/{id}/react/`
  with `{persona_id, choice}`); invalidates the pending-witness key on
  success.

### `components/CrimeTab.tsx` / `components/WantedBoard.tsx`

The character sheet's crime tab (self-only warrant rows) and the area wanted
board with the trial/pardon/lie-low/bribe flows. Pre-existing; see their
file headers.

### `components/WitnessReactionOfferGate.tsx` (#2987)

Mounted in `SceneDetailPage` (`frontend/src/scenes/pages/`), beside
`EntryFlourishOfferGate`, only while the scene is active. Takes
`personaId: number | null` (the page's already-resolved acting persona);
never polls without one. Polls pending witness windows, renders a call-out
strip for the first, and auto-opens the dialog once per window id via the
shared `useAutoOpenOncePerOffer` (`@/magic/hooks`) - dismissal leaves the
strip, which re-opens the dialog on click. Mirrors `EntryFlourishOfferGate`.

### `components/WitnessReactionDialog.tsx` (#2987)

Renders the window's choices (report / intervene / ignore for the witness
kind) as plain buttons; one tap posts the choice slug via `useReactToWindow`
and closes on success. A failed post keeps the dialog open with a
`role="alert"` banner. "Not Now" (and Escape) defers - the strip stays until
the player chooses or the window settles server-side.

### `__tests__/WitnessReactionDialog.test.tsx`

7 tests (real hooks, mocked `apiFetch` + `reactToWindow` transports -
`EntryFlourishOfferDialog.test.tsx`'s idiom). Covers: the three choices
render from the payload; choosing posts the slug (window id + `persona_id`)
through `reactToWindow`; the dialog dismisses after a choice; a failing post
keeps it open with the server message; no reactor attribution ever renders;
nothing renders without a pending window or acting persona; once-per-id
auto-open/dismiss bookkeeping; strip re-open.

## Design invariants for the witness surface (binding, #2987)

- **Anonymous end to end.** The pending payload (`PendingReactionWindow`)
  deliberately carries no reactor list, no counts, no attribution - and no
  component here may grow any. The test file pins this.
- **Interface chrome is OOC.** Plain labels and neutral copy; no
  in-character voice in buttons or nav.
- **The game never speaks for the player.** The dialog presents the
  window's choices verbatim from the payload; it never characterizes,
  recommends, or narrates a feeling for the player.

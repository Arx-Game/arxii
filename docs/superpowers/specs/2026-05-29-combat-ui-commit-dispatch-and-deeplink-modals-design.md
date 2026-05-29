# Combat-UI: Commit dispatch + outcome deep-link modals

**Issues:** #555 (wire ActiveState Commit button to dispatch; remove Lend), #551 (deep-link routing for outcome-detail effects)
**Branch:** `feature-555-wire-activestate-commit-lend-buttons-to`
**Descoped:** #558 (focused-category resolution) → refiled as #614 — needs a physical/social/mental technique taxonomy that does not exist yet.
**Date:** 2026-05-29

Two orthogonal frontend wiring tasks against the unified combat UI. #555 reuses the existing dispatch path; #551 adds a generic deep-link modal mechanism + one small backend retrieve endpoint.

## Verify-against-code ledger (per CLAUDE.md Anti-Reinvention Pass)

| Surface | Verdict | Evidence |
|---|---|---|
| `useDispatchPlayerAction(characterId)` + `DispatchActionRequest {ref, kwargs}` | BUILT & WIRED | `frontend/src/combat/queries.ts:209`; live clash dispatch `YourTurn.tsx:310-327` |
| `ActionRef` (`backend:'COMBAT'`, `clash_id`, `clash_action_slot`) | BUILT & WIRED | `frontend/src/combat/types.ts:74`; constructed `YourTurn.tsx:315-319` |
| Radix `Dialog` primitive | BUILT & WIRED | `frontend/src/components/ui/dialog.tsx` (CodexModal, RouletteModal consumers) |
| Redux-driven modal pattern | BUILT & WIRED | `RouletteModal.tsx` reads `state.roulette.current`, dismiss via slice action |
| ActiveState Commit/Lend buttons + optional handler props | BUILT, NOT WIRED | `ActiveState.tsx:29-38,160-184`; `CombatTurnPanel.tsx:166` passes neither |
| `deep_link {modal,id}` on outcome effect rows | BUILT (payload), NOT WIRED (UI) | type `combat/api.ts:95`; `PoseUnitDetailPanel.tsx:69-74` renders label only |
| `deep_link` backend producer + modal-kind set | BUILT & WIRED | `src/world/combat/views_outcome_details.py` emits `combo/opponent/participant/condition/clash` (NO `damage`) |
| `ConditionInstanceSerializer` | BUILT & WIRED (list only) | `src/world/conditions/serializers.py:116`; used by `CharacterConditionsViewSet.list` |
| single-instance `GET /conditions/instances/<pk>/` | ABSENT | no retrieve route for a `ConditionInstance` pk |
| opponent / participant / clash serializers | BUILT & WIRED | `combat/serializers.py` Opponent/Participant/ClashState serializers; rendered in CombatantsList / ActiveState |
| `CLASH_SUPPORT` action backend (Lend target) | ABSENT — stays absent | `ActionBackend` = CHALLENGE/COMBAT/REGISTRY; `YourTurn.tsx:439` TODO confirms |

## #555 — Commit dispatch + remove Lend

**Remove Lend (no CLASH_SUPPORT exists; #559 closed):**
- Delete the `onLendClick` prop + the Lend `<button>` from `ActiveState.tsx`.
- Delete the disabled `lend-to-clash-stub` block in `YourTurn.tsx:433-447`.
- Update `ActiveState.tsx` header docstring (drop the Commit/Lend "Phase 11" TODO).

**Wire Commit to the existing dispatch path:**
- `ActiveState` keeps `onCommitClick?(clashId: number)`. The parent supplies it.
- The dispatch is identical to the clash-contribution dispatch already in `YourTurn.tsx:310-327`:
  ```ts
  dispatchAction({
    ref: { backend: 'COMBAT', clash_id: clashId, clash_action_slot: <focused slot ref> },
    kwargs: { technique_id: <focused technique>, strain_commitment: <strain> },
  })
  ```
- **Where the handler lives:** `ActiveState` is a rail-overview section. The Commit button there is a shortcut that commits the player's *currently-focused* clash action. The handler is owned by the same component that owns the focused clash ref + strain state (the combat turn container, `CombatTurnPanel`/`CombatScenePage`). It calls `useDispatchPlayerAction` and passes `onCommitClick` down to `ActiveState`. **No new dispatch infra** — reuse the hook + ActionRef shape.
- **Optimistic / error handling:** mirror `YourTurn`'s pattern — `try { await mutateAsync(...) } catch { setError(...) }`, disable the button while `isPending`, surface failure inline on the clash card. No optimistic cache mutation (the round refetch is the source of truth, matching YourTurn).
- **Guard:** Commit is disabled when there is no selected focused clash ref (no implicit first-item selection, per CLAUDE.md).

**Tests (vitest):** ActiveState renders Commit (no Lend); clicking Commit calls `onCommitClick(clashId)`; CombatTurnPanel passes a handler that invokes the dispatch mutation with the COMBAT ActionRef; disabled-while-pending + error-surface.

## #551 — Deep-link modal routing (5 kinds)

Backend emits exactly five modal kinds: `combo`, `opponent`, `participant`, `condition`, `clash`. No `damage` (the issue's "damage breakdown" is not produced — out of scope, noted).

**Mechanism — one generic deep-link modal host (Redux, mirrors RouletteModal):**
- New slice `deepLinkModal: { modal: DeepLinkKind; id: number } | null` with `openDeepLink` / `closeDeepLink` actions.
- `PoseUnitDetailPanel` effect rows: when `effect.deep_link != null`, render the row as a button that dispatches `openDeepLink(effect.deep_link)`. Keyboard-accessible (button, not div).
- Top-level `<DeepLinkModalHost>` (mounted in the combat scene shell) reads the slice and renders the modal component for the active `modal` kind in a Radix `Dialog`.

**Per-kind content (reuse existing serializers/data; build only what's ABSENT):**
- `condition` → **new** `ConditionDetailModal` fetching the **new** `GET /api/conditions/instances/<pk>/` retrieve route (DRF `RetrieveAPIView`/detail action reusing `ConditionInstanceSerializer`, account-scoped permission). This is the only kind with no existing UI surface.
- `opponent` → reuse `OpponentSerializer` data already present in the encounter detail (CombatantsList rows); modal shows the opponent card content.
- `participant` → reuse `ParticipantSerializer` data from encounter detail.
- `clash` → reuse `ClashStateSerializer` data from `EncounterDetail.clashes` (already in `ActiveState`); modal shows the clash card content.
- `combo` → reuse `ComboDefinition` data from the outcome-details payload / combo source; modal shows name + description + effects.

For the four reuse kinds, the modal pulls from data already in the React Query cache (encounter detail / outcome details) keyed by id — no new endpoints. Only `condition` needs the retrieve route (its pk isn't otherwise resolvable from cached lists reliably).

**Backend (the one addition):** `GET /api/conditions/instances/<pk>/` → `ConditionInstanceSerializer`, permission-scoped to the requesting account's visibility. No model change, **no migration**.

**Tests:**
- Backend (`arx test conditions`): the new retrieve route returns the serialized instance; permission denies cross-account access.
- Frontend (vitest): clicking an effect with `deep_link` dispatches `openDeepLink`; `DeepLinkModalHost` renders the correct modal per kind; condition modal fetches the instance; close action clears the slice.
- e2e (Playwright, per #551 "done when"): at least one effect kind opens its modal against the built bundle.

## Out of scope / follow-ups
- #614 — physical/social/mental technique taxonomy (blocks focused-category resolution).
- `damage` deep-link modal — backend emits no such kind; revisit if/when a damage-breakdown payload is added.
- CLASH_SUPPORT / lend-to-clash — no backend action; Lend UI removed rather than stubbed.

## Notes
- No migrations in this branch (the only backend change is a read-only route). Safe across the #613 migration collapse.
- Two-tier tests: `conditions` is SQLite-clean; frontend via `pnpm test`/`pnpm test:e2e`.

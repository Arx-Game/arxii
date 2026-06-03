# Combat-state surfacing: fatigue pools + conditions on the combat UI

**Issues:** #552 (fatigue on VitalPools), #553 (conditions on CombatantsList rows)
**Branch:** `feature-552-expose-fatigue-model-on-combatparticipan`
**Milestone:** Next Playable Boss Fight
**Date:** 2026-05-30

Two display-only combat-UI completions surfacing existing backend state. Both add `SerializerMethodField`s to the combat serializers and render in adjacent React sections. **No migrations** (`FatiguePool` and the conditions system already exist). Heavy reuse; the one new component is a condition badge.

## Verify-against-code ledger (capability check applied per #620)

| Surface | Verdict | Evidence |
|---|---|---|
| `FatiguePool` (physical/social/mental_current) + `get_fatigue_capacity`/`get_fatigue_percentage`/`get_fatigue_penalty` | BUILT, NOT WIRED | `src/world/fatigue/models.py:8`; `src/world/fatigue/services.py` |
| `CombatParticipant.available_strain` (returns `CharacterAnima.current`) | BUILT & WIRED | `src/world/combat/models.py:570` — **stays anima; do not change** |
| `ParticipantSerializer` / `OpponentSerializer` | BUILT & WIRED | `src/world/combat/serializers.py:71` — no fatigue, no conditions fields yet |
| `VitalPools` (renders `0/10` placeholders) | BUILT, NOT WIRED | `frontend/src/combat/sections/VitalPools.tsx:177` (TODO(fatigue)) |
| `ConditionInstanceSerializer` (icon, color_hex, name, severity, …) | BUILT & WIRED | `src/world/conditions/serializers.py:116` |
| `get_active_conditions(target, …)` | BUILT & WIRED | `src/world/conditions/services.py:114` |
| `CombatantsList` rows (condition-icon stub) | BUILT, NOT WIRED | `frontend/src/combat/sections/CombatantsList.tsx:90` (TODO(conditions)) |
| `openDeepLink({modal:'condition', id})` + `DeepLinkModalHost` → `ConditionDetailModal` | BUILT & WIRED | `frontend/src/store/deepLinkModalSlice.ts`; `combat/modals/DeepLinkModalHost.tsx:52` (shipped #551) |
| condition-badge component (icon/color_hex) | ABSENT | `EffectKindBadge` is for outcome kinds, not conditions — genuinely new |
| fatigue/conditions displayed anywhere else (capability check) | ABSENT | neither is shown on any other surface → no parallel implementation |

## #552 — fatigue pools on VitalPools (display)

- **Backend:** add fatigue fields to `ParticipantSerializer` via a `SerializerMethodField` (e.g. `fatigue: {physical: {current, capacity}, social: {…}, mental: {…}}`), sourced from the participant's `character_sheet.fatigue` (`FatiguePool`) for `*_current` and `get_fatigue_capacity(sheet, category)` for capacity. Defensive: a participant with no `FatiguePool` row → zeros/null (mirror `available_strain`'s try/except). Prefetch `character_sheet__fatigue` on the encounter queryset to avoid N+1.
- **Frontend:** `VitalPools.tsx` renders real `current / capacity` per pool instead of `0/10`; drop the "(placeholder)" / `opacity-50` / "not yet implemented" affordances. Use a fatigue zone/percentage for bar fill if the serializer exposes it.
- **Strain slider: UNCHANGED.** `available_strain` stays anima (ratified — strain *is* anima). The "hardcoded 10" fallback stays only as a missing-data fallback.
- **Deferred (follow-up, file at PR time):** "pushing"/low-anima should also *incur* fatigue — a future mechanic, out of scope here.

## #553 — conditions on CombatantsList rows

- **Backend:** add `active_conditions` to BOTH `ParticipantSerializer` and `OpponentSerializer` via `SerializerMethodField`, returning `ConditionInstanceSerializer(get_active_conditions(target), many=True).data`. Target = the participant's character ObjectDB / the opponent's target. Respect `is_visible_to_others` (don't leak hidden conditions to other players — filter on it, matching how condition visibility works elsewhere). Prefetch to avoid N+1.
- **Frontend — new `ConditionBadge` component** (`frontend/src/combat/components/ConditionBadge.tsx` or similar): renders one condition's `icon` + `color_hex` (small badge/chip), `title`/tooltip = name (+ severity/stage). Accessible `<button>` that dispatches `openDeepLink({modal:'condition', id})` on click. No new modal — reuse the shipped `ConditionDetailModal` via the deep-link host.
- **Frontend — `CombatantsList.tsx`:** in `ParticipantRow` and `OpponentRow`, replace the `TODO(conditions)` stub with a row of `ConditionBadge`s from `participant.active_conditions` / `opponent.active_conditions` (ordered by `display_priority`). Empty list → render nothing.

## Testing
- Backend (`world.combat` + `world.conditions`): serializer tests asserting `fatigue` pool values (with + without a `FatiguePool` row) and `active_conditions` (participant + opponent; visibility filtering; empty case). No query explosion (assert prefetch). `world.combat` is SQLite-with-caveats → use `just test-parity world.combat` for the serializer additions; conditions is SQLite-clean.
- Frontend (vitest): `VitalPools` renders real values (no "placeholder"); `ConditionBadge` renders icon/color + click dispatches `openDeepLink`; `CombatantsList` rows render badges from `active_conditions` and an empty list renders none.
- No migration (confirm `git diff --name-only main | grep migration` empty).

## Follow-ups (file at PR time)
- Fatigue-cost-on-push: pushing/low-anima incurs fatigue (mechanics — future).
- (Already tracked) #614 per-category strain binding once the technique taxonomy exists.

## Out of scope
- Changing `available_strain` away from anima (ratified: strain = anima).
- #554 portraits, #557 WebSocket poses (separate milestone issues).

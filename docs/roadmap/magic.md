# Magic System — Playable-Loop Status

**Status:** engine essentially complete; blocked on onboarding/content, not mechanics.
**North star:** a player can **cast → see it posed into the scene → it's logged → it
resolves an outcome**, in a live RP scene in the web client.

This is the **status map** — the one place to answer "where are we / what's left." The
full scope-by-scope build record lives in
[`magic-build-history.md`](magic-build-history.md) (archive; consult it before designing
anything new, to avoid reinventing existing surfaces). When this doc and the archive
disagree, this doc and the code win.

## The playable loop, stage by stage

| Stage | Status | Where |
|-------|--------|-------|
| Cast initiation — REST `POST /api/action-requests/cast/`, WebSocket, `ActionPanel` UI | ✅ wired | `world/scenes/cast_services.py:request_technique_cast`; `frontend/src/scenes/actionQueries.ts:castTechnique` |
| Check resolution — anima, soulfray, mishap, corruption, environment | ✅ wired | `world/magic/services/techniques.py:use_technique` |
| Effects / outcome — conditions, combat damage, thread pulls, mage scars | ✅ wired | `world/combat/services.py`; `world/magic/services/` |
| Pose / narration into the scene | ✅ wired | `world/scenes/cast_services.py:create_cast_outcome_pose` → `world/magic/narration.py` |
| Logging — `SceneActionRequest` + `Interaction` + power ledger | ✅ wired | `world/scenes/action_models.py`; `cast_services.py:persist_power_ledger` |
| Resonance / progression feedback | ✅ by design | earned from RP perception (endorsements), **not** from casting — see "By design" below |
| **A real character actually being able to cast** | ❌ **blocked** | **see #1306** |

The backend cast→pose→log→outcome loop is fully wired and resolves end-to-end (verified
by tracing + a throwaway smoke test). The remaining frontier is **assembly, content, and
integration**, not engine mechanics.

## What's left (the real gaps)

Ordered by priority. These are the gaps between "the engine works" and "a player can do
magic." Each is a filed issue — work these, not micro-hardening tickets.

1. **🔴 #1306 — nothing is castable out of the box** (`priority:now`). Standalone cast
   rejects any technique with no `action_template` (`cast_services.py:418`); the CG
   cantrip→technique path (`character_creation/services.py:_finalize_cantrip_gift_and_technique`
   → `magic/services/technique_builder.py:create_technique`) never sets one, and 0 seeded
   techniques have one. The cast button fails for every real character. **This is the
   one blocker that gates playable magic.**
2. **🟠 #1307 — seed produces no playable character or scene** (`priority:next`). The
   "Big Button" (`world/seeds/database.py:seed_dev_database`, #651) seeds rules content
   only — 0 CharacterSheets / Personas / Scenes. Needs a playable-slice path (demo
   character via `create_character_with_sheet` + CG finalize, placed in a scene). Child
   of epic #1220.
3. **🟡 #1308 — the web cast loop is never tested live** (`priority:next`). Frontend cast
   tests mock `castTechnique`; backend tested only at service level. No test drives
   `POST /api/action-requests/cast/` against a seeded + CG'd character. Add one as the
   regression guard. Cross-refs #617.
4. **🟢 #1309 — frictionless scene start** (`priority:later`). Casting needs an active
   scene; a player should be able to start/auto-join one without staff setup (the
   "implicit scene start" intent).

## By design — do not re-file these as gaps

A code read flags these as "missing"; they are intentional. Verify against the design
before treating any as a bug:

- **Casting does not grant resonance.** Resonance is earned from *perception* — pose
  endorsements, scene entry, residence/outfit trickle (the four `grant_resonance`
  surfaces in Spec C, `docs/architecture/resonance-gain.md`). You earn it when others
  endorse your dramatic cast pose, not mechanically from the cast.
- **Non-combat casts deal no damage.** A hostile cast at a PC routes into combat
  (`seed_or_feed_encounter_from_cast`), where damage applies. Non-combat = benign / self
  / room. Consistent with the non-lethal-PvP invariant.
- **Non-combat thread pulls are passive-only** (VITAL_BONUS inactive outside combat) —
  Resonance Spec §7.4.

## Open design question carried by #1306

Is castability (the `action_template`) auto-provisioned per technique, shared per
effect-type/style, or authored staff content? The cast gate keys on a per-technique FK
today (`world/magic/models/techniques.py:362`). Resolve this in #1306's spec.

## Deeper design & history

- Scope-by-scope build record: [`magic-build-history.md`](magic-build-history.md)
- Architecture references: `docs/architecture/` (power-derivation, resonance-threads,
  resonance-gain, reactive-layer-foundation, magical-alteration, non-clash-casting, …)
- System reference: `docs/systems/magic.md`

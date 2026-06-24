# Telnet Backend-Journey Coverage

**Date:** 2026-06-21 — **rewritten 2026-06-23** (post-#1351) around the backend-journey principle.
**Tracking issue:** [#1328](https://github.com/Arx-Game/arxii/issues/1328)
**Loops covered deep:** magic casting, combat, thread weaving, social scenes. Other journeys
(missions, covenant, persona, progression, journals) get the broad pass at the end.

## Why this doc exists (the principle)

Telnet is **not** an interface we're investing in for its own sake — it's **pure backend**, which
makes it the ideal way to write full **end-to-end tests of user journeys**. Every journey is one
question: **"Can a player do X?"** — perform a major ritual, fight through a combat sequence, run a
mission, drive a social scene.

The ordering that keeps this coherent: **get the journey working end-to-end in the backend first
(proven by a telnet test); the frontend can always be made to follow.** Sometimes a frontend piece
will need to be **re-pointed afterward** — e.g. the web's "cast" still uses an older path instead
of the shared one #1351 introduced. That's a follow-the-backend fixup, **not** a reason the journey
"doesn't work."

So the real question this doc answers is **"which important player journeys work end-to-end in the
backend today, and which don't yet?"** — not "do telnet and web match." Where the web is on an
older path, it's a **frontend-follows** note, listed but never counted as a blocker.

### How to read the tables

- **End-to-end in backend?** — can a player drive the whole journey start-to-finish with backend
  commands today? (Yes / Partial / No.)
- **Telnet test** — the integration test that proves it (in `src/integration_tests/pipeline/`).
- **Backend gap** — the missing piece a player can't yet drive (the work that matters).
- **Frontend follows** — where the web reaches the same journey by an older path that should be
  re-pointed later (secondary).

> One shared path underneath: a player command (telnet) and a web action both express *intent to
> use an action*, and the active scene's rules decide whether it happens now, waits its turn, or is
> blocked (`SceneRound` mode OPEN / POSE_ORDER / STRICT, #1351). Combat is one specialization of
> that, not a separate thing. See `docs/architecture/unified-player-action.md`.

---

## The four priority journeys

| Journey ("can a player…") | End-to-end in backend? | Telnet test | Backend gap | Frontend follows |
|---|---|---|---|---|
| **Cast a technique** (in or out of a scene) | **Yes** | `test_noncombat_cast_telnet_e2e.py`, `test_combat_cast_telnet_e2e.py` | — | Web cast uses an older path (`SceneActionRequestViewSet.cast` → `request_technique_cast` directly) instead of the shared scene-adaptive cast. Re-point afterward — already routed here by #1351's own follow-up and tracked in #1444. |
| **Perform a ritual** (incl. multi-person sessions) | **Yes** | `test_ritual_telnet_e2e.py`, `test_ritual_session_telnet_e2e.py` | — | Web and backend already share the ritual path. |
| **Weave → imbue → pull a thread** | **Mostly** | `test_weave_imbue_pull_journey_e2e.py`, `test_weave_telnet_e2e.py` | **Acquiring the unlock**: no backend command to accept the teaching offer that grants thread-weaving, so the journey can't be driven from the very start. | Web imbue uses an older path (`PerformRitualAction`) vs the backend's imbue finisher; same end result. Re-point afterward. |
| **Fight a combat sequence** | **Partial** | `test_combat_cast_telnet_e2e.py`, `test_combat_clash_telnet_e2e.py` | **Declaring a technique (with effort / target / secondary slot) and committing to a clash (with strain) are now drivable** (#1330/#1451). The remaining player moves still have no backend command: flee, take cover, interpose, join/leave, ready, combo up/down (#1453). A player can declare + clash but can't yet drive a full fight. | Web has the rest (encounter viewset); not yet drivable in the backend, so not yet testable end-to-end. |
| **Drive a social scene** | **Yes** | `test_consent_telnet_e2e.py`, `test_social_pipeline.py` | — | Say/pose and the targeted social actions (intimidate, accept/deny) share the same backend path web uses. |

**Reading the combat row:** GM-only steps (start an encounter, resolve a round, add opponents)
are correctly not player-drivable and out of scope — a player never does them. The gap is only the
*player's own* moves beyond "declare a technique."

---

## Beyond the four loops (broad pass)

These journeys mostly have **no backend command yet**, so they can't be driven or tested
end-to-end. Each already has a tracking issue (the "Telnet journey:" children of #1328):

| Journey | Backend command today | Tracking |
|---|---|---|
| Missions (resolve a beat, abandon, group pick/vote) | none | #1349 |
| Covenant membership (engage/leave/kick/rank, banner-call) | none | #1346 |
| Persona / guise switching | none | #1347 |
| Progression rewards (claim kudos, vote, random-scene, path-intent) | none | #1348 |
| Journals & goals authoring | none | #1350 |
| Interaction reactions & favorites | none | #1341 |
| Entry flourish (resolve a pending offer) | none | #1246 |

A player-facing state change with costs/prerequisites should become a real action driven the same
way casts and weaves are, so a backend command and the web both reach it; GM/system-only steps stay
backend services with no player command.

## What to do next

**Real backend work — these unblock testable journeys:**

1. **Combat player moves** — declare-with-options (#1330) and clash-commit (#1451) now ship telnet
   commands. The remaining moves — flee, cover, interpose, join/leave, ready, combo up/down — still
   need backend commands over the existing combat services (#1453), so a full fight is drivable and a
   combat journey test can cover it.
2. **Thread-weaving unlock** — a backend command to accept the teaching offer, so the weave→imbue→pull
   journey is drivable from acquisition.
3. **The broad-pass journeys** above — each child issue adds the backend command(s) + one journey test.

**Frontend-follows fixups — do after the backend journey works, never a blocker:**

4. **Web cast** → move onto the shared scene-adaptive cast path (tracked in #1444 under #1328).
5. **Web imbue** → converge on the same imbue path the backend uses.

**Already done — don't redo:** telnet journey tests already exist for cast, rituals, ritual
sessions, thread weave/imbue/pull, social consent, challenges, endorsements, and progression
(`src/integration_tests/pipeline/`). Most working journeys are already covered; the gaps above are
the remainder.

> **Note for the next pass:** several of the original deep-trace "gaps" were already resolved in
> #1331 / #1337 / #1342 / #1351 before this rewrite. Reconcile the #1328 child map against this doc
> before filing anything new — most of the early findings are closed, and a few (like web-cast
> parity) are already tracked. Don't re-file them.

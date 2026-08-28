# ADR-0245: The offscreen-act gate extends the dead-gate choke point

<!--
Numbering note (final, post-renumber): main took 0243 via #3418; the
Commonplace Book (formerly 0243 on this stack) is 0244 on this branch; this
ADR is 0245.
-->

**Status:** Accepted (2026-08-28, #3412 slice 3)

**Decision.** A character in a degraded lifecycle state (CAPTURED, unconscious,
DEAD, RETIRED, or whereabouts UNKNOWN) cannot be onscreen, but a narrow set of
"2.5 acts" — journal entries, character-goal updates, persona swaps, and
proclamations — represent things the *player* can still do offscreen on the
character's behalf. The offscreen-act gate
(`src/actions/offscreen_gate.py`'s `offscreen_act_state(sheet, action_key)`)
is the single predicate that decides ALLOWED / ROUTED / BLOCKED for a given
character and action key, keyed on `CharacterSheet.lifecycle_state` plus one
cheap unconscious-overlay query (`world.vitals.services.unconscious_instance`).
It runs inside `Action.check_availability()`
(`Action._offscreen_gate_reason`, `src/actions/base.py`), immediately AFTER
the existing #2287 dead gate and BEFORE `get_prerequisites()` — extending the
same pre-Prerequisite choke point every action (web and telnet alike) already
passes through, rather than introducing a second, parallel gating mechanism.
Only action keys in `OFFSCREEN_ACT_KEYS` are ever inspected; every other key
resolves ALLOWED without a lifecycle read at all, so the gate adds zero cost
to the overwhelming majority of action dispatches. `ROUTED` is mechanically a
refusal this slice (no channel-delivery mechanics exist yet) but is kept
distinct from `BLOCKED` so a future channel mechanic can activate without an
API resignature — the frontend already renders it as world-voice prose, not a
flat "no."

**Why extend the dead gate instead of building something new.** #2287 already
solved the identical shape of problem — a lifecycle state that must refuse
most actions while whitelisting a narrow set of exceptions — for DEAD
specifically, at exactly the choke point every action (web REST dispatch,
websocket dispatch, and telnet commands via `command.func()` →
`action.run()`) already converges on. Building a second gate elsewhere (a
prerequisite class, a viewset permission, a serializer validator) would only
ever cover the surface that happened to call it, reproducing the "audit every
IC action for a dead-gate" problem #2287's own doc comment names as the
reason a central whitelist beats a scattered one. Extending the same
choke point keeps that guarantee for the wider CAPTURED/UNKNOWN/RETIRED
ladder for free, and keeps the two gates' refusal semantics composable rather
than accidentally overlapping: the dead gate is checked first and short-
circuits (a dead actor's refusal text for a non-whitelisted key stays
byte-identical to before this slice — no second reason ever appends to the
same failure list), and the offscreen gate is only consulted once the dead
gate has already passed.

**Rejected alternative 1 — a `CharacterCapabilities` facade now.** The
actions system's own "What's Not Built Yet" section
(`src/actions/CLAUDE.md`) already names a unified "can this character do X
right now?" facade as a known future seam. Building it now to host this gate
would mean designing that facade's full shape (which other capability checks
it should absorb, how prerequisites would query it, what it returns) under
this slice's much narrower scope. Rejected as premature generalization: the
offscreen gate is deliberately scoped to exactly the lifecycle-state
question this slice needs, and stands as the facade's first concrete seed
rather than trying to be the facade itself.

**Rejected alternative 2 — a DB config table for act keys / dispositions
now.** `OFFSCREEN_ACT_KEYS` and `OFFSCREEN_LIFECYCLE_DISPOSITIONS` are Python
constants (`src/actions/constants.py`), not database rows, so which actions
count as "2.5 acts" and what each lifecycle state does to them is
code-authored, not staff-authorable. Rejected for this slice on the same
"authorability deferred" grounds as the rest of #3412's phased build: no
migration this slice, and turning this into staff-editable content is real
future scope (recorded as an open roadmap item), not a default to reach for
before any staff workflow has asked for it.

**Rejected alternative 3 — per-viewset checks instead of the action layer.**
Gating each of the four acts' DRF viewsets individually (a permission class
per `JournalEntryViewSet`, `CharacterGoalViewSet`, `PersonaViewSet`,
`ProclamationViewSet`) was rejected because it only covers the web surface —
telnet commands for the same acts would need the identical check duplicated
separately, and the two would inevitably drift (this is the same
web/telnet-fork risk ADR-0001 already ruled against for action dispatch in
general). Gating inside `Action.check_availability()` instead means both
telnet and web get the same refusal for free, and is why proclamations were
routed through a new `issue_proclamation` action (Task 3) rather than gated
directly in `ProclamationViewSet.proclaim` — the view had no `Action` to gate
through until this slice added one.

**The COMA-is-unwritten finding.** `LifecycleState.COMA` is a real enum
member (`world.character_sheets.types`), but nothing anywhere in the
codebase ever sets a `CharacterSheet` to it (#3412 recon, verified by
searching for every `lifecycle_state = ` assignment site) — no action, no
service function, no admin action. `OFFSCREEN_LIFECYCLE_DISPOSITIONS`
therefore deliberately does NOT key on it: an untriggerable state has no
disposition to be wrong about, and adding one now would be speculative
design for a state that has no path into existence. COMA falls through to
the same ALLOWED default as ALIVE. If a future slice adds a COMA setter, its
disposition (most likely ROUTED, alongside unconscious) is real, scoped work
for that slice — not a gap in this one.

**Channel mechanics, phased.** `ROUTED` results name a channel
(`OFFSCREEN_CHANNEL_SMUGGLE`, `OFFSCREEN_CHANNEL_DREAM`) but no actual
message-delivery mechanic exists for either yet — this slice's `ROUTED` is
refusal-with-API-room, not a working feature. Each channel is a distinct
future scope, at a different distance from ready:
- **Séance (DEAD)** is the closest to buildable — `GhostWindowPrerequisite`
  already gates the #2287 dead-gate whitelist's `emit`/`pose` verbs to a
  death-scene/same-IC-day window (funeral + séance containers, #2393), so a
  séance-channel mechanic would extend an already-usable substrate rather
  than invent one.
- **Smuggle (CAPTURED)** has zero substrate today — no captor/captive
  messaging model, no delivery-check design. Building it needs the same
  check-design pass any new mechanic gets (perform_check philosophy: no flat
  probability) before it can be scoped, not a quick bolt-on.
- **Dream (unconscious)** needs a one-way variant of whatever dream-contact
  mechanics exist or get built for magic's dreamside systems (Tehom's
  domain, per `project_domain_ownership_tehom` — combat/soulfray/scars/
  zones/magic) — the unconscious character can be reached, but canonically
  should not be able to reach back the same way a waking character would.
  Needs Tehom coordination before design, not before this ADR.

None of the three block this slice: `ROUTED`'s only observable behavior right
now is world-voice refusal text (backend `OFFSCREEN_REASON_*` strings at
gate-check time, and separate Hall-display copy — see
`frontend/src/home/hall/OffscreenActsPlate.tsx`'s doc comment for why the two
registers are allowed to diverge slightly), never a working delivery.

**Consequences.** Any future "2.5 act" (a new thing a degraded-lifecycle
character can do offscreen) adds its action key to `OFFSCREEN_ACT_KEYS`
rather than inventing a parallel check — the gate is the seam, not a template
to copy. `Action.check_availability()`'s ordering (dead gate, then offscreen
gate, then `get_prerequisites()`) is now a fixed contract other pre-
Prerequisite gates would need to respect if any get added later — see
`actions/CLAUDE.md`'s Prerequisites section, updated in this task to name
both. The unconscious overlay stays a display-only seam client-side (the
Hall's `MyRosterEntry.lifecycle_state` field, also added this task, does NOT
attempt to expose it — an unconscious character's `lifecycle_state` column
is unchanged, so surfacing "unconscious" on the Hall would need a second,
conditions-system-backed field this task deliberately did not add) until a
real display need justifies the extra query.

> Status: accepted · Source: issue #3412 (slice 3), `src/actions/offscreen_gate.py`,
> `src/actions/base.py`'s `check_availability`, ADR-0244 (the Hall's visual
> idiom this gate's refusal prose renders inside).

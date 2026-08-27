# ADR-0241: Selection is not presence, and the server is the mirror source

<!--
Numbering note (#3412 slice 1 task 5): this worktree's docs/adr/ topped out at
0239 (shared-DE-currency) at task-5 time, but origin/main had already moved to
0240 (situations-are-state-driven) via merged PRs #3408/#3409 (which resolved
the earlier 0235/0236 in-flight collision this branch was warned about). 0241
is the next number clear of both this worktree's local tip and main's tip;
re-verify at enqueue in case another PR claimed it in the meantime.
-->

**Status:** Accepted (2026-08-27, #3412 slice 1)

**Decision.** The account's chosen character ("who am I browsing as") is a durable
server-side fact — `PlayerData.selected_entry` (state 2.5 in the ruled four-state
model: logged out / logged in-no-selection / selected / puppeting), mutated only
through `world.roster.services.selection.set_selected_entry` and read/written via
`GET /api/user/`'s `selected_entry`/`selected_entry_id` and
`POST /api/roster/entries/select/`. Setting or clearing it triggers **zero**
lifecycle, session, or puppeting side effects — it is inert data, not an IC action.
The React client's `gameSlice` is a **mirror** of this server fact, hydrated on
every account fetch and never the system of record; a hard reload or a second
device reproduces the same selection because the truth lives in Postgres, not in
`localStorage` or component state.

**Why.** Two forces point the same direction. First, cross-device/reload
continuity: a player who selects a character on one tab or device and reloads (or
opens another) should see the same character, which only a server-durable fact can
guarantee. Second, and more load-bearing for the roadmap: slice 2/3's offscreen-act
system (the 2.5 gate — acts a selected-but-not-puppeting character can take) needs
a server-queryable "who is this account currently browsing as" fact to gate against;
a client-only selection gives the backend nothing to check. Building the durable
substrate now, even though slice 1 ships no offscreen acts, avoids re-deriving this
exact model under time pressure in slice 2.

**Rejected alternative 1 — client-persist-only** (`localStorage`/Redux-persist,
no backend field). Simpler for slice 1's own scope, but loses cross-device
continuity outright and leaves nothing for the 2.5 offscreen-act gate to check
against server-side; slice 2 would need to retrofit the exact durable substrate
this ADR builds, under more schedule pressure and with an existing client-only
contract to migrate off of.

**Rejected alternative 2 — conflating selection with puppeting** (treat "selected"
as an alias for "actively puppeted," collapsing selection into the existing
session/puppet state). Rejected because it collapses the ruled four-state model
(logged out / logged in / selected / puppeting; see #3412) down to three, destroying
exactly the state slice 2's offscreen acts depend on — a character can be selected
(the account is "browsing as" them) without a live puppeting session existing at
all, and that gap is the entire point of state 2.5.

**Consequences.** Any future selection consumer reads `PlayerData.selected_entry`
(or the mirrored `gameSlice` fields client-side) rather than inferring "current
character" from puppet/session state. Any future mutation path for this field must
go through `set_selected_entry`, never a direct model write, so the zero-side-effect
guarantee stays enforceable in one place. The name-keyed `gameSlice` shape (mirroring
by character name rather than `RosterEntry` id) is a known, deliberately deferred
wart — see the #3412 slice-1 roadmap entry's "known seams" note; a 25-surface
entry-id refactor is out of this slice's scope.

> Status: accepted · Source: issue #3412 (slice 1), `docs/roadmap/ROADMAP.md`
</content>

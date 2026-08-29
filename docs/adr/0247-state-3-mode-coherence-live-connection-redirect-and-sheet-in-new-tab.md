# ADR-0247: State-3 mode coherence — live-connection redirect and sheet-in-new-tab

<!--
Numbering note (#3412 slice 4, final task): origin/main was at 0243 (#3418)
when this stack started; this branch already claimed 0244 (the Commonplace
Book, slice 2) and 0245 (the offscreen-act gate, slice 3). 0246 is the next
number clear of both origin/main's tip and this branch's own tip as of
2026-08-28; re-verify at enqueue in case another PR claimed it meanwhile.
-->

**Status:** Accepted (2026-08-28, #3412 slice 4)

**Decision.** Two small routing/UI decisions complete #3412's mode-coherence work.
First, `GatefoldPage` (`frontend/src/home/GatefoldPage.tsx`) redirects an
authenticated account straight to `/game` when its active character has a **live
connection** — `active && sessions[active].isConnected`, the same
selection-is-not-presence distinction ADR-0241 already drew — never on selection
alone; a selected-but-unconnected character still resolves to the Hall, since
there is nothing live to jump back into. Second, `GameTopBar`'s own-sheet link
(`frontend/src/game/components/GameTopBar.tsx`) opens `/characters/:id` in a
**new tab** (`target="_blank" rel="noopener"`) rather than in-client or same-tab,
keyed on the active `RosterEntry.id` CharacterSheetPage already expects.

**Why live-connection, not selection, keys the redirect.** Selection ("who am I
browsing as") and presence ("who is live in the world right now") are a ruled
distinction (ADR-0241) — collapsing them here would silently re-merge exactly the
states ADR-0241 built `PlayerData.selected_entry` to keep apart. A player who
merely *selected* a character (browsing the Hall, reading their own sheet, queued
for an offscreen 2.5 act) is not yet in play; sending them straight to `/game` on
selection alone would strand them in the game client with no live session, forcing
a round trip back out. Keying on the connected session instead means the redirect
only fires for a player who is *already* live — exactly the case where the Hall
would otherwise be a pointless waiting room in front of a game they're already in.

**Rejected alternative — key the redirect on selection instead of connection.**
Rejected because it collapses the ruled selection≠presence distinction (ADR-0241):
a selected-but-not-connected account would be forced into `/game` with nothing to
render there, and the 2.5-state offscreen-act surface (ADR-0246) — reachable
specifically *because* a character can be selected without being connected — would
lose its natural home (the Hall) for players in exactly that state.

**Rejected alternative — no redirect at all.** Rejected because it leaves a player
who is already live in the world clicking through the Hall's advertisement-shaped
menu (built for a state-2 "logged in, picking who to play" audience) every time
they land on `/`, instead of returning them to the game they're already playing —
a dead-end detour for the one audience state-3 exists to serve.

**Why the sheet opens in a new tab.** The own-sheet link's job is to let a live
player check their own sheet without breaking the mode they're in — the game
client's WebSocket session, its composer state, its open conversation tabs. A new
tab preserves all of that untouched; the player alt-tabs back into the exact game
state they left.

**Rejected alternative — an in-client sheet drawer.** Rejected as the heavier
build: `CharacterSheetPage` is already a full SPA route with its own data
fetching, tabs, and edit flows: rendering a second, in-client copy of it (a
drawer/modal variant) duplicates that surface rather than reusing it, for a
marginal UX gain (staying in one browser tab) that a new-tab link already delivers
without breaking the live session.

**Rejected alternative — same-tab navigation.** Rejected because it breaks the
mode outright: navigating the active tab away from `/game` drops the player out of
their live WebSocket session (or at minimum orphans it in the background) just to
glance at their own sheet, which is a worse UX regression than the marginal
one-more-tab cost a new tab imposes.

**Composer consolidation — recorded as already satisfied.** #3412's original scope
named "consolidate the combat and scene composers" as an open item, but recon this
slice (task 1) found it already true: one shared `CommandInput` component has
served every composer since #2156/#2166, and #2197 folded the standalone
`CombatScenePage` into `SceneDetailPage` — carrying `speakingAs` along with it —
so no separate combat composer has existed since. The one real gap (`speakingAs`
not threaded through `SceneDetailPage`'s composer call site) is fixed as part of
this slice, closing the item by verification rather than by new consolidation
work; see Apostate's 2026-08-28 ruling on the #3412 issue thread and the updated
doc comment on `CommandInput.tsx` (`frontend/src/game/CLAUDE.md`).

**The clock-readout fold (review finding, folded in-branch).** `GameTopBar`'s new
`ClockReadout` and the existing `WeatherWidget` both trace to `game_clock`'s
`get_ic_now` and, as first built this slice, both rendered `hh:mm` — a literal
duplicate reading in the same bar. Rather than filing a follow-up, `ClockReadout`
was narrowed on review to show only what `WeatherWidget` lacks: the season, plus
the paused indicator, with the full date/time/phase kept in the title tooltip.
`WeatherWidget` itself is untouched — smallest fix, no relocation of either
widget's data source.

**Consequences.** Any future account-state routing decision on `/` reads the live
`sessions[active].isConnected` shape, never `PlayerData.selected_entry` alone —
selection answers "who," connection answers "are they in play," and only the
second question routes past the Hall. `GameTopBar`'s clock and weather stay two
narrow, non-overlapping glances (season+paused vs. phase+hh:mm+conditions) rather
than one merged widget; a future readout that wants to show both together should
consolidate the two components deliberately rather than let a third glance
duplicate either.

> Status: accepted · Source: issue #3412 (slice 4), `frontend/src/home/GatefoldPage.tsx`,
> `frontend/src/game/components/GameTopBar.tsx`, ADR-0241, ADR-0246

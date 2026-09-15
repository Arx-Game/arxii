# Browsing identity is per tab; the account column is the default

**Status:** Accepted (2026-09, #3479). Amends ADR-0241 (the mirror is seeded, not
rehydrated); reconciled with ADR-0294 (puppeting records the selection).

**Context.** ADR-0241 made "who am I browsing as" a durable server-side fact,
`PlayerData.selected_entry`, and had the client's `gameSlice` mirror it on every
account fetch. That is one fact per account, and a player with two characters in
two browser windows has two identities. Every in-game switch wrote the column and
invalidated the account query, so the other window's mirror was overwritten on
its next refetch and its ambient pages (journal, tidings, wardrobe, NPC
interactions, weather) silently began reading as the wrong character. Dan's
ruling on #3479 was option 1: a client-side per-tab identity, with multi-playing
in telnet and in tabs a requirement, not a tolerated edge.

**Decision.** Each browser tab owns its browsing identity, a `RosterEntry` id in
`sessionStorage` (`frontend/src/store/browsingIdentity.ts`), which the browser
already scopes per tab: a reload keeps it, a new tab starts without one. The
account column is the default a tab seeds from when it has none, or when its
stored entry is no longer one of the account's own; the account refetch never
overwrites a tab that has one (`useAccountQuery`'s hydration effect seeds, it does
not rehydrate, and it keys on the account payload alone).
`gameSlice.browsingEntryId` mirrors the tab's store for ambient pages through
`useBrowsingIdentity()`; `active` and `sessions` stay the live-session fields,
and the Gatefold redirect (ADR-0247) still keys on them. Every
player-scoped read the ambient pages make carries the tab's id explicitly
(`entry_id`, resolved by `selection.character_for_request`, which accepts only
the caller's own entries and falls back to the column when absent), so two tabs
reading as two characters get two answers from one account. The Hall picker is
the one surface whose purpose is to write the default, and it still does.
In-game switches (the top bar's avatars, the puppet-tab bar) are tab-local, with
one reconciliation forced by ADR-0294: login puppets the durable selection the
moment a socket authenticates, and puppeting records the selection anyway, so a
switch that opens a socket writes the column just before the connect, and a
switch between two already-open sessions writes nothing. Telnet never reads any
of this; a telnet session's identity is its puppet, so web identity semantics
can change without a telnet change (stated at the top of `selection.py`).

**Rejected alternative: a server-side per-session identity.** A `Session`-keyed
row would make the server the source of truth for every window, but the web
client's HTTP session is one cookie per browser, not per tab, so the server has
nothing to key on without the client minting a tab id and sending it on every
request, at which point the client already holds the fact. It would also give
the multi-tab case a table the single-tab case never needs.

**Rejected alternative: identity in the URL.** Putting the entry in every
ambient route (`/journal/as/<entry>`) makes identity explicit and shareable, and
that is the problem: a pasted link would carry one player's identity into
another's tab, and every ambient link in the app would need rewriting. The tab
store gives the same per-window isolation with no route change.

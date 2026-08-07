# ADR-0204: Account-first block/mute extends #1278; IC stays flag-only; OOC is write-then-filter

Context: #1278 built `Block`/`Mute` persona-scoped by default (an `account_level` opt-in existed
only on `Block`), and wired enforcement into the profile gate, the scene target picker, and the
IC interaction feed — but four OOC delivery seams (mail, journal reactions, event invites,
kudos/reaction windows), journal feed visibility, and unilateral friend-adds never consulted it,
and the Friends-List design rule ("OOC, account-scoped, never derived from IC relationships",
`docs/roadmap/ooc-social.md`) wants the *default* to be account-first, not persona-narrow.
Decision (#2996): `+block`/the web block control and `+mute`/the web mute control now default to
`account_level=True` (blocking/muting every character the target's player currently plays), with
the narrower persona-only shape staying reachable as an explicit advanced opt-out
(`+block/persona`, `+mute/persona`, `account_level: false`); `Mute` gained the same
`muted_player`/`account_level` shape `Block` already had, snapshotted at creation and never
re-derived (preserves #1278's anti-derivation invariant — the blocked/muted player's *other*
identities are never something coded enforcement lets the blocker/muter observe). **IC channels
(say/pose/whisper) deliberately stay flag-only** — delivery-suppressing an IC message would be an
RP leak (silence itself becomes a tell), so those keep #1278's original behavior unchanged. Of the
**seven** OOC seams this extends (mail, journal reactions, event invites, kudos/reaction windows,
journal feed, pages/tells, friend adds), five follow one uniform mechanism:
**write-then-filter, never skip-the-write** — the actor's own write path is byte-identical to an
unblocked/unmuted send, and suppression is exclusion on the *other* party's read. Pages/tells were
previously flag-only for a block (like IC channels); #2996 upgrades them to delivered-suppressed
since a page is genuinely OOC (no scene, no RP-leak risk), reusing the existing OOC-mute drop
mechanism while keeping the pre-existing staff `BlockContactFlag` signal firing unconditionally.
**Two seams are deliberate reject-before-write exceptions, for two different reasons:** journal
praise/retort responses reject a blocked responder outright with a neutral shared failure message,
since "this entry isn't available to respond to" already has many innocent causes and can't leak a
block by itself — whereas creating-then-hiding a response row would still let the responder infer
a block from render-vs-list discrepancies; friend adds reject a blocked pair outright because
creating the `Friendship` row would itself be the harm being guarded against — a blocked party
unilaterally recorded as your friend, however invisibly, is not a state write-then-filter can
safely produce and then hide. Rejected: leave account-level narrowing at the players' own
knowledge of the advanced option — this is exactly the shape the spec's Decision 6 anti-derivation
review flagged as silently under-serving the common case ("I block/mute a person, not one face of
them"), and it would have left four of seven enforcement seams unenforceable without a parallel,
easy-to-drift `account_level` check duplicated in each caller instead of the two shared query
helpers (`account_block_active`/`blocked_player_ids_for`, `account_muted`/`muted_player_ids_for`).

> Status: accepted · Source: #2996 (extends #1278) · Related: ADR-0009 (no signals — every seam
> is an explicit service-function/query-helper call), ADR-0007 (no JSON fields — `Mute` gained
> two real columns, not a config blob)

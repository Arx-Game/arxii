# XP unlocks, never grants — major acquisitions stack gates, all required

A major acquisition (a Durance class-level advance, a gift/technique unlock) is gated by
**multiple independent preconditions** — authored `Requirement` rows (Legend, Relationships,
Traits, …) **and** a purchased XP unlock (`CharacterUnlock` / `CharacterGiftUnlock`) — and
**all** must pass; XP buys one gate among several, never the capability itself. We rejected
removing the inert purchase surfaces to "fix" the disconnected XP-spend loops found in #2116;
that would make advancement permissive exactly where community/RP-earned XP is meant to be a
real cost. This extends ADR-0053 (unlock-then-acquire is a two-step process) with the sibling
rule that when several gates exist on the same acquisition, none may be dropped to simplify —
they stack.

> Status: accepted · Source: issue #2116 (rev 2 ruling by Tehom, 2026-07-09)

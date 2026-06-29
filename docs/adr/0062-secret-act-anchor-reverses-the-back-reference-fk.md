# The Secret↔act anchor puts the FK on the Secret, reversing the back-reference pattern

A `Secret` can be the hidden truth behind a recorded act (Bob's "legendary duel" was a murder).
The act surfaces through several records — a `societies.LegendEntry` (public telling), a
`missions.MissionDeedRecord` (mechanical act), and/or a `scenes.Scene` (where it happened). The
secrets system's general rule (see `docs/systems/secrets.md`) is the **back-reference pattern**:
the more-specific *originating* system holds an FK *into* `Secret`, so `secrets` stays the uniform
substrate consumers point at (e.g. `distinctions.CharacterDistinction.secret → Secret`). The
act-anchor cross-link (#1573) **deliberately reverses that** — the three FKs live on `Secret`,
pointing *out* at the act records.

Two reasons force the reversal. **Cardinality:** one act can have many secrets behind it (a single
blackmail-worthy scene hides several truths about different people), and conversely one secret = one
act surfaced through several records — so the FK must sit on the secret side (`many secrets → one
act`), not as a single `explaining_secret` on each record. **Dependency direction (ADR-0010):** the
records are reusable primitives, and `scenes` is a foundational app; a back-reference
(`Scene.explaining_secret → Secret`) would make a core RP-recording model import the `secrets`
consumer — backwards. With the FKs on `Secret`, `scenes`/`missions`/`societies` never import
`secrets` (which already imports `scenes`/`societies`).

We also rejected a discriminated "exactly one of the three" link: an act legitimately has *all*
records at once, and forcing one would fragment a single truth into three secrets — confusing to a
knower. The three FKs are therefore independent and optional; "one act = one secret" is the
load-bearing invariant. An act-anchored secret is evidenced ("true because it happened") and so can
never be `PLAYER_FLAVOR`.

> Status: accepted · Source: issue #1573

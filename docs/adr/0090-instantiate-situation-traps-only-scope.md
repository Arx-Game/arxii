# ADR-0090: instantiate_situation scoped to traps only, not challenges

## Status

Superseded by ADR-0091 (#1895) — `instantiate_situation` now mints
ChallengeInstances too, once `SituationChallengeLink.target_object_name`
answered the target_object-sourcing question this ADR left open.

## Context

#1625 needed a way for a `SituationTemplate` to carry authored trap content
that comes alive when the Situation is instantiated at a room — mirroring how
`SituationChallengeLink` already lets templates carry Challenges. Building
`instantiate_situation(template, location)` for real meant deciding whether it
should also mint `ChallengeInstance`s per `SituationChallengeLink`, which is
what the existing pipeline test (`integration_tests/pipeline/
test_situation_pipeline.py`) manually chains together and what the roadmap
(`docs/roadmap/capabilities-and-challenges.md` Phase 5.7) has long assumed a
real `instantiate_situation` would eventually do.

`instantiate_challenge()` (`world/mechanics/challenge_resolution.py`) already
exists and mints a bare `ChallengeInstance`, but requires the caller to supply
an explicit `target_object` (the ObjectDB "embodying" the challenge — e.g. an
actual door object for a "Locked Door" challenge). There is no generic
mechanism for sourcing that object automatically, and Phase 5.7 explicitly
marks the full Situation-runtime trigger/lifecycle design as unresolved.

## Decision

`instantiate_situation` mints the `SituationInstance` and materializes
`SituationTrapLink` rows into `Trap` rows only. It does not call
`instantiate_challenge` or otherwise mint `ChallengeInstance`s. Traps don't
need a `target_object` (they anchor to `RoomProfile` directly), so they were
safe to solve now without guessing at the harder, still-open challenge-target
question.

A future issue will need to decide the `target_object` sourcing strategy
(auto-created placeholder object per template? author-specified existing prop?
something else?) before `instantiate_situation` can also mint challenges.

## Consequences

- `instantiate_situation`'s name is broader than its current behavior — a
  future reader might assume it mints challenges too. This ADR is the pointer
  back to why it doesn't yet.
- The follow-up issue (target_object sourcing) is a precondition for closing
  Phase 5.7, not an optional nice-to-have.

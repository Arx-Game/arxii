# ADR-0147: Bare-object affordances mint challenges lazily from authored templates

## Status

Accepted

## Context

#2503 needed to close the last mile between "a character has a granted
capability" and "the world actually offers something to do with it." Before
this work, `get_available_actions` had exactly one source: authored
`ChallengeInstance` rows. A GM (or a content author) had to explicitly place a
challenge instance in a room before any capability-gated affordance appeared —
so a plain flammable torch dropped in a room, or a dark room a GM narrates
into being, offered nothing to ignite or illuminate unless someone had also
remembered to instantiate a matching challenge there. Everyday objects with
`ObjectProperty` tags (a torch's `flammable`, a room's `dark`) were inert to
the capability pipeline even though the Property data existed and a character
standing there had the relevant `generation` capability.

Three shapes were considered for closing this gap:

1. **Eager reflector** — a signal/trigger that mints a `ChallengeInstance` the
   moment an `ObjectProperty` is added to an object, and destroys it when the
   property is removed.
2. **Direct resolution without templates** — skip `ChallengeInstance`/
   `ChallengeApproach` entirely for bare objects; resolve a bare-object
   "Ignite" action against the object's `Property` with an ad hoc check and
   hardcoded consequence.
3. **Lazy synthesis from an authored per-Application template** — extend
   `get_available_actions` with a second source that matches `ObjectProperty`
   rows against `Application.default_template` (a curated, nullable FK to a
   `ChallengeTemplate`) and synthesizes an `AvailableAction` on the fly, with
   no `ChallengeInstance` row until the player actually acts.

## Decision

Went with (3). `Application.default_template` is a curated, nullable FK — an
author must deliberately wire a world-interaction `ChallengeTemplate` (with
its `ChallengeApproach` rows, check type, and consequence pool) onto an
`Application` before any bare-object affordance for that Application can ever
appear; a null `default_template` is the gate that keeps the vast majority of
`Application` rows (challenge-only, no ambient world presence) exactly as
narrow as before. `get_available_actions`'s bare-object scan
(`_bare_object_actions` in `world/mechanics/services.py`) reads
`ObjectProperty` rows on the room and its contents, matches them against
`Application.target_property` for Applications with a non-null
`default_template`, and produces an `AvailableAction` whose `ActionRef` is
`ActionBackend.WORLD_INTERACTION` (`application_id` + `target_object_id` — both
stable identifiers that exist before any instance does, unlike a
`ChallengeInstance` pk). Dispatch re-validates the pair against a fresh
`get_available_actions` call, then mints the real `ChallengeInstance` via
`instantiate_challenge(resolved_default_template, location, target_object)`
and resolves it through the unchanged `resolve_challenge()` path — zero
reimplementation of resolution, consequence selection, or effect dispatch.
A row-scan against an already-active `ChallengeInstance` for the same
`(target_object, template)` pair is deduplicated, so an authored instance
covering the same affordance always wins over lazy synthesis.

## Rationale

- **Rejected: eager reflector.** Minting a real `ChallengeInstance` the
  instant an `ObjectProperty` lands (and destroying it on removal) means every
  torch, every staged prop, every technique-granted temporary Property change
  churns database rows with a lifecycle someone has to keep synchronized with
  the object's actual lifetime — a torch that burns out, a room re-tagged
  mid-scene, a GM's staged prop that leaves with the scene. It also directly
  conflicts with this codebase's no-Django-signals invariant (ADR-0009):
  reflecting property changes into instance churn is exactly the kind of
  implicit, hard-to-trace side effect that rule exists to prevent. Lazy
  synthesis needs no lifecycle management at all — the `ObjectProperty` row
  already is the source of truth, checked fresh on every `get_available_actions`
  call.
- **Rejected: direct resolution without templates.** Skipping
  `ChallengeTemplate`/`ChallengeApproach` for the bare-object path would mean
  reinventing (or hardcoding) a second, parallel resolution shape — its own
  check type selection, its own consequence pool, its own effect dispatch —
  losing every bit of authored richness (custom approach descriptions,
  tiered consequences, `ApproachConsequence` overrides) the challenge system
  already provides for the exact same Application. It would also mean two
  divergent code paths for "a character resolves an Application against a
  Property," doubling the maintenance surface for zero gameplay benefit.
- **Why lazy synthesis wins:** it reuses 100% of the existing
  `ChallengeTemplate`/`ChallengeApproach`/`resolve_challenge()` machinery —
  the only new surface is the `default_template` FK (the curated gate) and the
  `_bare_object_actions` read-side scan plus the `WORLD_INTERACTION` backend's
  mint-then-resolve dispatch step. A `ChallengeInstance` only ever gets created
  at the moment a player actually commits to acting, never speculatively.

## Consequences

- Content authors control ambient world-interactivity per `Application` by
  setting (or leaving null) `default_template` — this is a deliberate
  authoring surface, not automatic: an `Application` with no
  `default_template` never grants a bare-object affordance no matter what
  `ObjectProperty` rows exist, even if its `target_property` matches.
- `get_available_actions` now has two sources (authored `ChallengeInstance`
  rows, and lazy bare-object synthesis) that a reader must know about — see
  the second-source note added to `docs/architecture/action-template-pipeline.md`
  and `docs/architecture/property-capability-action.md`.
- Because instances are minted lazily and only at dispatch time, a
  `ChallengeInstance` produced by a bare-object affordance can be re-synthesized
  after its resolution DESTROYs it (e.g., igniting the same torch again mints a
  fresh instance) — this is intentional (a torch that already burned can be
  re-lit) but content authors should account for it when choosing
  `resolution_type` on world-interaction templates.

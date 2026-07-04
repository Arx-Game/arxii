# ADR-0086: Content boundaries split enforcement from communication; a hard line stays private forever

## Context

#1770 PR4 shipped `check_stake_boundaries` as a wired-but-allow-all stub — every
stakes-contract call site already gated on its report, waiting for a real per-player
boundary registry (#1771). Two different player-protection needs had to be served by
that registry: (a) a **hard, no-discussion limit** on content themes a player never
wants staked against their character, and (b) a **softer flag** on specific entities
(an NPC ally, an heirloom, a location) whose loss would be devastating, where the
player wants a heads-up and a chance to opt in per-scene rather than a blanket
block. Modeling both as one undifferentiated "boundary severity" invites the exact
failure this feature exists to prevent: a hard limit's private reason accidentally
becoming visible, editable by someone else, or overridable at GM-authorship time.

## Decision

**Enforcement (auto-block, always private) and communication (shareable, opt-in via
sign-off) are two separate code paths, never one severity flag on one shape:**

- `PlayerBoundary` (`kind`: `HARD_LINE` | `ADVISORY`) is matched against a
  `StakeTemplate`'s `content_themes` — a coarse **category** match. `HARD_LINE`
  blocks the whole contract; `ADVISORY` never blocks anything and may be shared.
  Both kinds share one model (owner `PlayerData`, `VisibilityMixin`, `theme`,
  `detail`) rather than two — but the `HARD_LINE`-implies-private invariant is
  enforced redundantly at three layers so the shared shape never leaks it: model
  `clean()` (raises if theme is null or visibility isn't `PRIVATE`), the DRF
  serializer's `validate()` (duplicated, since `clean()` isn't called automatically
  on a `ModelViewSet` save and m2m fields aren't settable pre-save), and
  `IsOwnPlayerData` (no staff read carve-out, unlike most owner-scoped permissions
  in this codebase — a hard line is private even from staff).
- `TreasuredSubject` is a **wholly separate model**, matched against a `Stake`'s
  wagered subject by **specific-entity identity** (typed FK equality, or
  `subject_label` for untyped kinds) rather than theme. A match never blocks —
  it requires an explicit `TreasuredSignoff` before the stake can activate for that
  player, because losing a treasured NPC/item/relationship is often the exact
  narrative beat the player is opting into; a theme-level hard line, by contrast,
  is never wanted regardless of narrative frame. `TreasuredSubject` is owned by
  `RosterTenure` (one persona's attachment), not `PlayerData` (which a
  `PlayerBoundary` deliberately is, since an OOC content limit follows the player
  across every character they play).

This mirrors the split ADR-0024 draws for social consent (gate on
behavior-altering, not benign-vs-hostile) and extends ADR-0033 (privacy is
MVP-gating, never deferrable): a hard line is enforcement infrastructure that must
never become a communication surface, while a treasured subject is communication
infrastructure (a heads-up + opt-in) that never blocks by itself.

## Consequences

- Every read surface over `PlayerBoundary`/`TreasuredSubject` (owner-scoped
  `ModelViewSet`s, the scene "lines & veils" aggregate, the GM `stake_availability`
  counts-only read) is built with the hard-line exclusion as a *query-shape*
  guarantee rather than a post-hoc filter — e.g. `scene_lines_and_veils` only ever
  queries `kind=BoundaryKind.ADVISORY`, so a hard line cannot reach an anonymized
  aggregate even if a row were somehow miswritten.
- A GM never sees *why* a stakes contract was rejected, only that it was — the
  same generic "stakes could not be presented" message for every hard-line block,
  regardless of theme or player. This is a deliberate UX cost (no actionable error
  for the GM) accepted because a more specific message could let a GM infer a
  player's private limit by elimination.
- `stories` depends on `boundaries` (ADR-0010: FK direction specific→general) —
  `StakeTemplate.content_themes`, `TreasuredSignoff.treasured_subject`. Functions
  that need stories-owned models (`grant_treasured_signoff`,
  `withdraw_treasured_signoff`, `stake_availability`) live in
  `world/stories/services/boundaries.py`, not `world/boundaries/services.py`, to
  keep `boundaries` free of a reverse import — even though they read as
  "boundaries" functionality.

## Rejected

- **Two separate models for `HARD_LINE`/`ADVISORY`** (e.g. `HardLineBoundary` +
  `AdvisoryBoundary`) instead of one `PlayerBoundary` with a `kind` field. Rejected:
  the two kinds share the identical shape (owner, `theme`, `detail`,
  `VisibilityMixin`) and the same CRUD surface; splitting the schema would not make
  the privacy guarantee any stronger than enforcing it at `clean()` +
  serializer + permission, and it would duplicate the admin/API surface for no
  behavioral gain.
- **A third `kind` on `PlayerBoundary` for treasured subjects**, instead of a
  separate `TreasuredSubject` model. Rejected: a treasured subject needs typed FKs
  to specific entities (`subject_sheet`/`subject_item`/`subject_society`/
  `subject_organization`) that a theme-matched boundary has no use for, and it is
  owned by `RosterTenure` (a specific character-instance's attachment), not
  `PlayerData` — cramming it into `PlayerBoundary` would force either unused typed
  columns on every hard-line/advisory row, or the wrong owner model for one of the
  two use cases.

> Status: accepted · Source: #1771; extends ADR-0024 (consent gates
> behavior-altering effects), ADR-0033 (privacy is MVP-gating), ADR-0010 (FK
> direction specific→general).

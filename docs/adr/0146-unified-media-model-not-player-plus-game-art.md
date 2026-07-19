# ADR-0146: One unified `Media` model, not separate `PlayerMedia`/`GameArt`

## Status

Accepted

## Context

#2408 needed a way to attach staff-authored art (page backgrounds, codex
illustrations, CG card art) to the game, kept separate from the existing
player-upload pipeline (`PlayerMedia`: Cloudinary-backed, malware-scanned,
FK'd to a player). The obvious first instinct was a second model
(`GameArt`) parallel to `PlayerMedia`.

## Decision

`PlayerMedia` was renamed to `Media` in place and extended to serve both
roles. "Player-owned vs. staff-owned" is derived from whether `player_data`
is set — no separate boolean/type flag. Staff-authored rows additionally
carry a nullable, unique `slug` for natural-key addressing from the
lore-repo content pipeline; player rows never set it.

## Rationale

Both kinds of art need the same shape: Cloudinary fields, and — critically —
an `Artist` credit, since staff plans to commission artists for game art
too, not just accept player uploads. A second model would duplicate that
shape entirely. Two-model and two-app alternatives were considered and
rejected during design:

- **Two separate models** would duplicate the Cloudinary/Artist-credit
  fields and every FK site that currently points at `PlayerMedia`
  (`ObjectDisplayData.thumbnail`, `ItemTemplate.image`, etc.) would need to
  choose which model to point at, or both — doubling the FK surface for no
  behavioral gain.
- **A new dedicated app** (`world/game_art`) was rejected per a standing
  project concern about migration-graph weight from small-app proliferation
  — `evennia_extensions` already owns `PlayerMedia`/now `Media`, so a new
  app would add overhead without adding any capability a same-app extension
  doesn't already provide.

## Consequences

- `Media.player_data` is nullable, which is a real behavior change from the
  original `PlayerMedia.player_data` (previously required) — any code that
  assumed every `Media`/`PlayerMedia` row has a player must now handle
  `None`.
- A `Media` row's role (player upload vs. staff art) is always derived, never
  stored explicitly — consistent with this codebase's general preference for
  derived state over duplicated flags.

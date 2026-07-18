# ADR-0141: Game invites live in world/roster/

**Date:** 2026-07-18
**Status:** Accepted

## Context

The game invites feature (#2483) lets a trusted player invite a friend to play
Arx with a contextual message. The friend arrives via a tokenized registration
URL, the invite annotates their first `DraftApplication`, and the inviter is
notified on submission.

The question was where the `GameInvite` model should live. Three options were
considered:

1. **`world/roster/`** — alongside `RosterApplication` and `RosterTenure`.
2. **A new `world/invites/` app** — separate domain.
3. **Extend `RosterApplication`** — add invite fields directly.

## Decision

Game invites live in `world/roster/` as a new model (`GameInvite`) and submodule
(`models/invites.py`, `services/invite_services.py`, `views/invite_views.py`).

## Rationale

- **Roster owns the player→character lifecycle.** `RosterApplication`,
  `RosterTenure`, and `PlayerData` are all roster models. Invites are the step
  *before* that lifecycle begins — the inviter is a `PlayerData`, and the invite
  annotates the player's first `DraftApplication`.
- **Reuses existing infrastructure.** The `PlayerData` FK, trust checks
  (`PlayerTrust`), and notification patterns (`notify_mail_arrived`) are all
  roster-local or roster-adjacent.
- **ADR-0017 compliance.** New subsystems are submodules, not standalone apps.
  A single model doesn't justify a new app.
- **Distinct from `GMRosterInvite`.** A token-based invite model already exists
  in `world/gm/` (`GMRosterInvite`), but it serves a different domain: a GM
  inviting someone to apply for a *specific roster character*. `GameInvite` is
  a *player* inviting a *friend to play the game* with a contextual message.
  The lifecycle patterns (pending→claimed→expired→revoked) are mirrored, but
  the models are not merged — the FK targets and domains differ fundamentally.

## Consequences

- Invite services use the `game_invite` prefix (`create_game_invite`,
  `claim_game_invite`, `revoke_game_invite`) to avoid naming collision with
  `world/gm/services.py`'s `create_invite`/`claim_invite`/`revoke_invite`.
- Invites annotate `DraftApplication` via a nullable `invited_via` FK rather
  than being a separate review path. The review process is unchanged — the
  invite is social context, not a shortcut.

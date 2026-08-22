# Tavern games (#3292)

A pure social-fun coin sink: characters at a table in a social hub open a
curated coin-stakes dice game, ante in, roll, and the winner takes the pot,
visible to the room. Lives in `world/tavern_games/`. Design goal: a
lighthearted drain on the currency ledger (`world/currency/`) plus low-stakes
rivalry RP with a built-in escape valve (the weekly loss cap). No skill input
at MVP - pure chance.

## Models (`world/tavern_games/models.py`)

- **`TavernGame`** (`NaturalKeyMixin`) - authored content: `name` (natural
  key), `rules_blurb`, `min_ante`/`max_ante`, `resolution_kind`
  (`GameResolutionKind`; one value at MVP, `HIGHEST_ROLL`), `is_active`. One
  seeded row (`ensure_dice_game`, see Seeding below).
- **`TavernGamblingConfig`** - singleton (pk=1, mirrors
  `world.gm.models.GMRewardConfig`): `weekly_loss_cap` (PLACEHOLDER
  magnitude, staff-editable).
- **`GameSession`** - a live table: `place` (FK `scenes.Place`), `game` (FK
  `TavernGame`), `state` (`GameSessionState`: OPEN/RESOLVED/ABANDONED),
  `ante` (fixed for the table, chosen by the opener within the game's
  range), `pot` (escrowed coppers), `opened_by` (FK `scenes.Persona`),
  `opened_at`/`resolved_at`.
- **`GameSeat`** - one persona's seat: `session`, `persona`, `ante_paid`,
  `roll_result` (nullable - null means "hasn't rolled this hand").
  Unique per `(session, persona)`.
- **`GamblingLossLedger`** - one row per `(character_sheet, game_week)`,
  shape mirrors `currency.models.PurseDrainWeek`: `total_lost` accumulates
  every ante paid that week, win or lose (winnings never subtract).

## Services (`world/tavern_games/services.py`)

`open_session` / `join_session` / `roll` / `leave_session` - the only
mutators. Internal `_resolve` (called from `roll` once every seat has
rolled) is not a player-facing verb.

Money moves ONLY through `world.currency.services.transfer`, never a
parallel ledger:

- **Ante** (`_charge_ante`, shared by open/join): `transfer(from_purse=...)`
  with no destination (a sink) debits the purse; `GameSession.pot` is
  incremented in the same call. Before debiting, it locks and bumps the
  caller's `GamblingLossLedger` row for the current IC week
  (`game_clock.week_services.get_current_game_week`) and refuses
  (`LossCapExceededError`) if the ante would exceed
  `TavernGamblingConfig.weekly_loss_cap`.
- **Payout** (`_resolve`): `transfer(to_purse=winner_purse)` with no source
  (a mint) credits the winner the whole pot; `pot` zeroes, `state` becomes
  RESOLVED.
- **Refund** (`leave_session`): refunds the leaving seat's own `ante_paid`
  via `transfer(to_purse=...)`, deletes the seat, and decrements `pot` to
  match. A session with zero seats left becomes ABANDONED.

Resolution (`_maybe_resolve`, called at the end of `roll`): once every seated
persona has a non-null `roll_result`, the highest roll wins. A tie among the
leaders resets every seat's `roll_result` to null and narrates "the table
rolls again" - the whole table re-rolls, not just the tied seats. Requires
`MIN_SEATS_TO_ROLL` (2) seated players before anyone may roll, so a lone
opener can't round-trip their own ante for no reason.

Gates: `_require_present` (the persona must have a `PlacePresence` row for
the session's `place`); `_require_social_hub` (the place's room must be
`RoomProfile.is_social_hub`) - both checked at `open_session`; `join_session`
re-checks presence (a session outlives any one joiner's presence).

Randomness: server-side `random.randint(1, DICE_SIDES)` (6 at MVP), the same
stdlib call the check engine uses (`checks/services.py`) - never client-supplied.

Narration: every state change onlookers care about is public. `open`/`join`/
`roll` narrate as a POSE-mode `Interaction` authored by the acting character
(`world.scenes.interaction_services.record_interaction`); resolve/tie/refund/
breakup narrate as a Narrator-authored OUTCOME `Interaction`
(`create_interaction` + `_broadcast_to_location`, the same "no `SceneRound`
to ride `broadcast_scene_outcome`" pattern `world.covenants.perks.services`
uses).

## Typed errors (`world/tavern_games/exceptions.py`)

`TavernGameError` base (`user_message`, never `str(exc)` in a response):
`NotAtPlaceError`, `NotASocialHubError`, `GameNotActiveError`,
`AnteOutOfRangeError`, `SessionNotOpenError`, `AlreadySeatedError`,
`NotSeatedError`, `AlreadyRolledError`, `NotEnoughSeatsError`,
`LossCapExceededError`.

## Actions (`actions/definitions/tavern_games.py`)

Thin REGISTRY wrappers, `target_type=SELF`, `category=scenes`: `OpenGameAction`
(`tavern_game_open`; kwargs `place`, `game`, `ante`), `JoinGameAction`
(`tavern_game_join`; kwarg `session`), `RollGameAction` (`tavern_game_roll`;
kwarg `session`), `LeaveGameAction` (`tavern_game_leave`; kwarg `session`).
Each resolves the actor's active persona via
`world.scenes.services.active_persona_for_sheet` and translates a
`TavernGameError` into a failure `ActionResult`.

## Telnet (`commands/tavern_games.py`)

`CmdGame` (`game`, help category Social): bare `game` shows the open table
at the caller's current Place; `game open <name>=<ante>` resolves the
`TavernGame` by name and opens a session there; `game join`/`game roll`/
`game leave` act on the single open session at the caller's current place.
No business logic in the command - every subverb dispatches the matching
REGISTRY action.

## Web API (`world/tavern_games/views.py`, `urls.py`)

Mounted at `/api/tavern-games/`. `TavernGameViewSet` (`games/`) - read-only
catalog (`is_active=True`), filters `is_active`/`name`. `GameSessionViewSet`
(`sessions/`) - read-only list/retrieve (filters `place`, `room`, `state`)
plus four custom actions that dispatch the REGISTRY actions exactly like
`world.scenes.place_views.PlaceViewSet.join`/`.leave`: `POST sessions/open/`
(body: `place`, `game`, `ante`), `POST sessions/{id}/join/`, `.../roll/`,
`.../leave/`. The account's active-persona character is resolved via
`world.scenes.interaction_permissions.get_account_personas`, mirroring
`PlaceViewSet` exactly.

## Web frontend

The Place bar (`frontend/src/scenes/components/PlaceBar.tsx` neighborhood)
gains a game widget showing the open session at the room (state, ante, pot,
seats) with Join/Roll/Leave buttons and an Open form, scoped to whichever
Place the viewer's `viewer_is_present` flag says they're at.

## Seeding

One dice game rides the clone-bootstrap seed path (`world.tavern_games.seeds
.ensure_dice_game`, cluster key `tavern_games` in `world.seeds.clusters
.CLUSTER_SEEDERS`) - without it `game open` fails "no such game" on a fresh
clone/dev DB, matching the "seeder vs fixture" line: this row is load-bearing
for the feature to be exercisable at all, not authored content.

## Deferred (verified absent, design-open)

Cheating as a Skulduggery move; card games with hidden state; NPC house
games / house rake; player-vs-player side bets on outcomes; a real timeout
sweep for an idle OPEN session with no further activity (today a session
only closes when the last seat explicitly leaves).

# Trade (#2990)

Player<->player negotiated exchange: each side stages items and/or coin,
either side may restage until both explicitly confirm, and the swap executes
atomically. Barter (goods-for-goods, mixed with coin) falls out of the same
primitive for free — nothing distinguishes it as a separate mode. Lives in
`world/items/trade/` (submodule per ADR-0017, beside `world/items/market/`
— a different shape: two-sided negotiation vs. posted-price buy-now).
Auction is deferred to its own follow-up issue (no bid/lot/time-boxed-escrow
substrate exists; not two-party-confirm shaped).

## Models (`world/items/trade/models.py`)

- **`TradeSession`** — `CharacterSheet`-keyed (#684: the body owns items, not
  the account or a persona) `initiator_sheet`/`counterparty_sheet` pair;
  `status` (`PROPOSED` -> `ACTIVE` -> `COMPLETED`/`CANCELLED`);
  `initiator_confirmed`/`counterparty_confirmed`; plain
  `initiator_coppers`/`counterparty_coppers` columns (one scalar per side).
  No DB-level "one open session per pair" constraint — `propose_trade`
  checks either direction inside its own transaction instead.
- **`TradeItemStake`** — one row per staged item; `session`, `offered_by_sheet`,
  `item_instance`. No DB constraint blocks double-staking across sessions
  (can't express "no other open session" in a `UniqueConstraint`) —
  `stake_item` and `execute_trade` both re-verify possession under
  `select_for_update`.

## Services (`world/items/trade/services.py`)

`propose_trade` (adjacency + self-trade + existing-open-session guards) ->
`accept_trade` (`PROPOSED` -> `ACTIVE`) -> `stake_item`/`unstake_item`/
`set_coin_offer` (any offer-table change resets both confirms; `stake_item`
runs the same `require_hot_goods_consent` gate `give()` uses, promoted out of
`flows.service_functions.inventory` to a plain `CharacterSheet` signature so
both callers can share it) -> `confirm` (sets the caller's flag; calls
`execute_trade` once both are `True`) -> `execute_trade` (the atomic core) or
`cancel_trade` (either party, any time before `COMPLETED`; nothing to roll
back — stakes are declarations, not escrow).

`execute_trade` mirrors `resolve_crossing_offer`'s
(`world.magic.services.crossing`) two-phase `select_for_update` shape: one
`transaction.atomic()` block re-locks the session row and every staked item,
re-verifying `ACTIVE` + both confirms + each item's current holder before
moving anything. A mismatch (item moved/destroyed/vaulted since staking, or
the purse now short) aborts the *whole* trade — session stays `ACTIVE`, both
confirms reset to `False` (in a fresh statement after the transaction rolls
back, so the reset survives even though everything else in the aborted
attempt doesn't), and `TradeItemUnavailable` (or the underlying
`RecipientNotAdjacent`/`ValidationError`) propagates so the caller knows
which stake failed. On success, item relocation mirrors `give()`'s shape
(unequip if worn, `move_to`, reassign `holder_character_sheet`, write an
`OwnershipEvent(TRANSFERRED, notes="trade #<id>")` per item) and coin moves
both directions through `currency.services.transfer` — the single money
mutation point, whose own `select_for_update` + insufficient-funds
`ValidationError` is the final currency guard.

## Surfaces

- Actions (REGISTRY): `propose_trade`, `accept_trade`, `stage_trade_item`,
  `unstage_trade_item`, `set_trade_coin`, `confirm_trade`, `cancel_trade`
  (`actions/definitions/trade.py`) — thin over the services above, each
  owning its own prerequisite checks (adjacency, session/stake membership).
- REST (read-only): `/api/items/trade-sessions/` — IC-scoped to sessions
  where the viewer's active character is either party; every mutation
  dispatches through the actions above.
- Web: `TradePanel` (`frontend/src/trade/components/TradePanel.tsx`) — a
  two-column staging card (your offer / their offer), an item picker sourced
  from the viewer's `carried_items` (`useInventory`), coin input, and
  confirm/cancel controls. `TradeSession.initiator_sheet`/`counterparty_sheet`
  compare directly against the viewer's ObjectDB character id with no extra
  lookup (`CharacterSheet` shares ObjectDB's pk 1:1).
- Telnet: no bespoke grammar shipped yet beyond the actions themselves being
  reachable via the generic dispatch seam — a `trade`/`stage`/`confirm`/
  `cancel` command shim is a small follow-up, not required for the web-first
  experience the actions already serve.

## Deferred

- **Auction** — its closing seller<->winner handshake may reuse
  `TradeSession`, but the bidding machinery (lots, time-boxed escrow, N
  bidders) is its own design pass.
- **NPC-initiated trade** — out of scope; NPC vendor interaction is the
  market's job.
- **Remote/cross-room trade** — co-location required, matching `give()`'s
  `RecipientNotAdjacent` precedent.
- **Auto-cancel on room-leave** — the Adopted default re-checks adjacency at
  confirm/execute time instead of wiring a movement-triggered hook; either
  side can `cancel_trade` explicitly if the other wanders off.

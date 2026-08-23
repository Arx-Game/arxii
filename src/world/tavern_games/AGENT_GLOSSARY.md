# Tavern games glossary

Domain-local vocabulary for `world/tavern_games`. Cross-cutting terms live in
the root `AGENT_GLOSSARY_MAP.md`.

- **Tavern game** - a curated, staff-authored coin-stakes contest (`TavernGame`):
  name, rules blurb, min/max ante, resolution kind. One row at MVP (a dice
  contest). _Avoid_: "gamble"/"gambling" as a noun for the row itself - that
  word names the domain, not a specific game.
- **Session (game session)** - a live table (`GameSession`): one `TavernGame`
  at one scene `Place`, an escrowed `pot`, and a fixed `ante` every seat pays
  to join. Always ends OPEN -> RESOLVED or OPEN -> ABANDONED; never reopens.
- **Seat** - one persona's place at a session (`GameSeat`): their `ante_paid`
  and (once rolled) `roll_result`. _Avoid_: "player" alone when the seated-at-
  this-table sense is meant - a persona can be present at the Place without
  being seated.
- **Ante** - the fixed coppers every seat pays to join a session, set by the
  opener within the game's min/max range. Moves purse -> pot at join (a
  currency sink), never a parallel money path.
- **Pot** - the session's escrowed coppers (an integer field on `GameSession`,
  not a purse or treasury). Credited to the winner at resolve (a currency
  mint), or refunded seat-by-seat on leave/abandon.
- **Resolve** - the internal step that picks a winner once every seated
  persona has rolled: highest roll takes the pot; a tie among the leaders
  resets every seat's roll and the whole table rolls again. Not a player
  action - it fires automatically at the end of `roll`.
- **Loss cap** - the weekly ceiling (`TavernGamblingConfig.weekly_loss_cap`) on
  coppers a character may ante in one IC week, tracked per
  (character_sheet, game_week) in `GamblingLossLedger.total_lost`. Every ante
  counts against it, win or lose; winnings never subtract from it.

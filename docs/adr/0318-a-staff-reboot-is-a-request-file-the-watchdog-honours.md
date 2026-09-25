# ADR-0318: A staff reboot is a request file the watchdog honours; `@shutdown` stays down

- **Status:** Accepted
- **Date:** 2026-09-24
- **Issue:** #4001

## Context

Staff had no way to restart both Evennia daemons without the ops SSH gate or the
deploy button. Evennia gives a Developer three verbs: `@reload` (Server only;
`@restart` is its alias), `@reset` (Server only, cold) and `@shutdown` (both daemons,
and the unit stays down because it is `Restart=on-failure`). The game process runs as
a user with no sudo and no way to talk to systemd. The maintainer also ruled that
whatever brings the game back must be a **separate verb** from `@shutdown`: a staffer
who takes the game down to work on it must never get it back up by surprise.

## Decision

`@reboot` writes `<gamedir>/server/reboot.requested`, announces to everyone, and
shuts both daemons down exactly as `@shutdown` does. The root watchdog that already
runs every minute (`arxii-watchdog.timer`) gains one branch: an **inactive** unit plus
a request file **younger than ten minutes** means `systemctl start`, with the file
deleted first so a start that fails cannot loop, and a stale file discarded so a
forgotten request can never start a game somebody stopped on purpose later. The
watchdog also skips a stop in flight, so it never restarts a unit that is shutting
itself down. The verb is `@reboot`, matching the launcher's own `evennia reboot`,
because `@restart` already means reload. `acceptance.sh` checks the branch, the age
bound, the shared file name, and that the unit never carries `Restart=always`.

## Rejected

- **`Restart=always` on the unit.** One line, and it would have made the stock
  `@shutdown` a restart. That is the exact mistake the maintainer wanted impossible.
- **A sudo grant for the game user** (`systemctl restart arxii`, exact command). It
  is immediate, but it hands the game process a privilege nothing else in it needs,
  and the ops gate's design (#3324) keeps every privilege on a separate account.
- **An out-of-band REST endpoint** that restarts without a game session. It would
  work while logins are broken, but the wedge that broke logins is healed by the
  tick script now (#4001 re-arms it), and the deploy's reload-then-restart fallback
  already covers anything else. Not built until a case needs it.

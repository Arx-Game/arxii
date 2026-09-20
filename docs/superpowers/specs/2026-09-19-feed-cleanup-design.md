# Feed cleanup: tagged compatibility frames, a puppet handshake, and a quiet reconnect (#3933)

**Status:** approved design, 2026-09-19. Parent defect: #3933 (items 2 to 5). The
liveness fix and the diagnostic recorder (#3934) are out of scope.

## Problem

A web session shows the server's login and reconnect lifecycle as story content.
One login renders, as feed notes: `[MudInfo] tehom connected`, `You become Tehom`,
Evennia's stock look of the room (which reads Limbo's Evennia `desc` attribute,
not our room state), our own `look`, `Now controlling Tehom`, and, from the
client's reconnect-time `@ic`, `Already controlling Tehom`. One pose renders twice:
the compatibility text line as a note, then the structured Interaction. A control
frame the client does not know produces a permanent alert with no detail. The
System chip cannot hide the untyped `system` notes it is named for.

Every reconnect replays all of it, so the reconnect problem in #3933 is amplified
by these paths. They are fixed here, independently of the closer.

## Decision: tag, do not filter

The server does not branch on a session's protocol when it delivers text. A
compatibility line goes to every session with metadata in its options, and each
frontend decides: telnet prints the text, the web client discards, transforms, or
records it. This keeps the delivery layer protocol-agnostic and testable at one
seam, and it makes the failure mode visible (a missing tag leaks a duplicate note)
instead of silent (a filter drops a message nobody sees). The endpoint of this
model is telnet rendering structured frames too, at which point the compatibility
echo and its tag disappear; that is separate telnet work. Recorded as an ADR.

## 1. Tagged compatibility frames (backend)

Evennia's tuple form `(text, {options})` becomes the frame's kwargs on the web,
which is where `type` already rides (#3856).

| Producer | Options added | Web client rule |
| --- | --- | --- |
| `message_location(..., interaction_echo=True)` for say, pose, emit, and companion poses (every caller that also records an Interaction) | `{"type": <pose/say/emit>, "interaction_echo": True}` | discard: the Interaction is the render |
| Every other `message_location` caller | unchanged | feed note, as today |
| `You become X.` and Evennia's stock post-puppet look | not sent from our hook (see below) | n/a |
| `Switching from A to B.`, and the puppet result line at login (`Now controlling`, `Already controlling`) | `{"type": "lifecycle", "event": "switch" / "puppet"}` | lifecycle milestone, no note |
| The joining session's `look` output | `{"type": "look", "on_entry": True}` | discard on entry; the room panel shows the prose. One rule flips it back |
| `X has entered the game.` | `{"type": "arrive"}` | Movement chip owns it |

`Character.at_post_puppet` stops calling Evennia's default hook, which renders
`You become` plus the stock look and cannot be tagged. It reproduces the base
hook's side effects that matter (the room broadcast, typed `arrive`) and sends its
own tagged `You become` line with `{"type": "lifecycle", "event": "become"}`. The
`look` command still runs for the joining session so telnet keeps its entry look;
its output is tagged through the session's console-style capture already used for
`console` (#3857), extended to carry a per-line option set.

`message_location` gains `interaction_echo: bool = False` and a `kind` parameter
from `InteractionMode`, so the `type` option is derived, never a free string.

## 2. Puppet handshake (backend + client)

A new websocket inputfunc `puppet(session, *, character: str)` in
`server/conf/inputfuncs.py` calls the existing idempotent
`Account.puppet_character_in_session`. It sends no text. Success is the existing
`puppet_changed` broadcast (`session_id`, `character_id`, `character_name`).
Failure sends the existing `command_error` frame with the refusal reason; the
client toasts it and marks the session `entry-error`.

The client sends `["puppet", [], {"character": name}]` on every socket open
instead of `@ic <name>`. `puppet_changed` whose `character_name` equals the
socket's character is the puppet milestone for that socket. A `puppet_changed`
for another character (another tab's socket) is ignored, as today. Readiness
stays gated on `room_state`. Multisession is unchanged: each tab's socket puppets
its own character through the same idempotent path, and a second tab on the same
character is a no-op puppet that still receives `room_state`.

`@ic` remains a telnet command.

## 3. Control-frame inventory (client)

Every message key the server can send gets an explicit case in
`useGameSocket.ts`:

- ours, missing today: `character_died`, `estate_settlement_opened`, `oob`;
- Evennia's: `webclient_options`, `channel`, `ping`, `heartbeat`, `reconnect`,
  `nickname`, `subscribe`, `unsubscribe`, `repeat`, `monitored`, `send`, `role`,
  `session`, `privmsg`, `request_nicklist`, the `*_variables` family;
- `logged_in` becomes a silent milestone instead of a message-lane line.

The inventory is a test: a list in `message_types.py` on the server and the
client's switch are compared, so a new server key without a client case fails.

An unknown type is recorded in a bounded in-memory diagnostics list (type name,
generation, timestamp; never the payload) and logged to the browser console. No
feed diagnostic, no alert. The persistent alert remains for a frame that fails
to parse.

## 4. System chip (client)

`DEFAULT_FEED_CHIPS` gives the System chip `['look', 'item', 'error', 'system']`.
`normalizeFeedChips` migrates stored preferences: a chip with the default System
id whose kinds are exactly the old default set, while `system` is unowned, gets
`system` appended. Any other stored layout is respected. `error` stays with
System; command errors already toast.

## 5. Tests

Backend (`arx test`): `message_location` tags per caller and leaves other callers
untagged; `at_post_puppet` sends the tagged `become` line and no stock look;
`puppet` inputfunc success, refusal, idempotent repeat, second tab on the same
character, second character in another session; login puppet line tagged;
inventory parity test.

Frontend (Vitest): open sends the `puppet` frame and no `@ic`; `puppet_changed`
naming the socket's character sets the milestone and one for another character
does not; `interaction_echo` and `on_entry` notes are discarded; `lifecycle`
frames add no note; an unknown type adds no diagnostic and lands in the
diagnostics list; chip migration from the old default and from a custom layout.

Playwright: one login shows no lifecycle notes; one pose shows exactly one block.

## 6. Docs

- ADR: websocket sessions receive structured frames and tagged compatibility text;
  frontends decide.
- `src/server/CLAUDE.md`, `frontend/src/hooks/CLAUDE.md`, `frontend/src/game/CLAUDE.md`,
  `src/flows/CLAUDE.md` (message_location signature), `docs/systems/INDEX.md` if
  it lists the inputfuncs.
- Issue #3933 comment on merge naming what remains (liveness, recorder).

## Out of scope

The idle disconnect itself (#3933 item 1, #3934), the `/api/clock/` 503 in
production (a missing clock row, configured in admin), and telnet rendering of
structured frames.

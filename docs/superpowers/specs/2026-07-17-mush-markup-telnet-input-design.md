# MUSH `%r`/`%t` markup for telnet input — design

**Date:** 2026-07-17
**Status:** approved (design)

## Problem

Players arriving from other MU* codebases expect `%r` to mean "newline" and `%t`
to mean "tab" — the near-universal MUSH/MUX convention. The telnet protocol is
line-oriented: each line the client sends is a separate input, so `%r` is the
*only* way a telnet user can embed a newline into a single line of input (e.g. a
multi-line room description or pose typed on one line).

Current Evennia does **not** parse `%r`/`%t` — its ANSI map only has `|/`
(newline) and `|-` (tab). Nothing in the Arx II codebase parses `%r` either
(every `%r` in `src/` is a Python logging repr specifier). So today a telnet
user's `%r` is stored and displayed as the literal two characters.

## Goal

Give telnet users their expected `%r`/`%t` behavior, such that content they
author renders with real line breaks/tabs on **every** surface: telnet output,
live web messages, and REST-read stored fields — with no per-frontend-component
work.

## Key architectural facts (verified against code)

The React frontend has two distinct text paths:

1. **Live game messages** — poses/says/room text over the webclient websocket,
   rendered by `frontend/src/game/components/EvenniaMessage.tsx`. These run
   through Evennia's ANSI→HTML conversion (the component receives HTML with
   `<br>` and `class="color-0xx"` spans).
2. **Stored text over REST** — journals, mission beats, descriptions, bios, etc.,
   rendered as `whitespace-pre-wrap` `<p>{body}</p>`. These **bypass Evennia's
   parser entirely** and render raw DB text.

Consequence: an output-time ANSI-map alias (`COLOR_ANSI_EXTRA_MAP`) would cover
path 1 but leave path 2 showing a literal `%r`. Converting at **input** instead
stores real `\n`/`\t`, so both paths — plus telnet re-render — just work.

Input boundaries (also verified):

- Telnet command text enters through the `text` inputfunc, then the cmdhandler.
  `server/conf/inputfuncs.py` already overrides Evennia's inputfuncs module (it
  defines `execute_action`), so adding a `text()` function there takes precedence
  over Evennia's default. There is no existing `text` override to collide with.
- The web frontend dispatches structured actions through the separate
  `execute_action` inputfunc and sends real newlines from textareas — it never
  uses the `text` path for authoring.
- `session.protocol_key` distinguishes telnet-family sessions (`"telnet"`,
  `"telnet/ssl"`) from `"websocket"` / `"ajax/comet"` (already used in
  `src/commands/account/account_info.py`).

## Design

### 1. Converter — `normalize_mush_markup(text: str) -> str`

A pure, single-pass function (single pass so escape handling is unambiguous).

| Input                          | Output      | Note                                   |
|--------------------------------|-------------|----------------------------------------|
| `%r`, `%R`                     | `\n`        | newline (both cases — MUSH clients vary)|
| `%t`, `%T`                     | `\t`        | tab                                    |
| `%%`                           | `%`         | escape → literal percent               |
| `%` + any other char           | unchanged   | e.g. `%s`, `%d`, `%z` pass through      |
| trailing lone `%`              | unchanged   |                                        |

Algorithm: scan left to right; on `%`, consume the next char and emit per the
table; a `%` with no following char is emitted literally. This makes `%%r`
produce a literal `%r` (escape consumed first, `r` emitted as-is).

Location: a small dedicated module so it is trivially unit-testable and importable
from the inputfunc — e.g. `src/server/conf/mush_markup.py`.

### 2. Telnet input adapter — `text()` inputfunc

Add to `src/server/conf/inputfuncs.py`:

```python
def text(session, *args, **kwargs):
    if args and str(session.protocol_key or "").startswith("telnet"):
        args = (normalize_mush_markup(args[0]), *args[1:])
    evennia_text(session, *args, **kwargs)   # delegate to Evennia's default
```

- Only telnet-family sessions are normalized; websocket/ajax pass through
  untouched, so the `%r` collision can never affect a web user.
- Preprocess-then-delegate: we do not re-implement command handling, only rewrite
  the raw line before Evennia's normal `text` handler runs.

### 3. Deliberately NOT changed

- `execute_action` (web action path) and REST serializers — untouched.
- `COLOR_ANSI_EXTRA_MAP` / the ANSI output map — we do **not** alias at output.
  Output aliasing would leave raw `%r` in storage and re-open the REST-field gap.

## Known trade-off

`%r`/`%t` greedily consume any `%` immediately followed by `r`/`t`, so
`"100%ready"` (no space) becomes `"100⏎eady"`. This is the classic, expected MUSH
behavior; the audience for this feature knows to write `"100% ready"` or `"%%r"`.
Percent-*encoding* (`%20`, `%2F`) is safe because those use hex digits, not `r`/`t`.
The collision is scoped to telnet input only.

## Testing

- Unit tests on `normalize_mush_markup` covering every row of the table, a mixed
  case (`"A man.%rHe wears a hat."` → two lines), and the escape
  (`"100%%ready"` → `"100%ready"`).
- One test asserting the `text` inputfunc normalizes for a telnet-`protocol_key`
  session and leaves an identical websocket-session input unchanged.

## Docs to update in tandem

- `src/commands/CLAUDE.md` (telnet layer) — document the supported markup.
- Connection/help text — tell telnet players `%r`/`%t` are available.

## Out of scope

- Any additional MUSH markup beyond `%r`/`%t` (e.g. `%b`, ansi `%c...`) — not
  requested; add later only if players ask.
- Output-side aliasing for the traditional Evennia webclient (unused; the React
  client is the web target).

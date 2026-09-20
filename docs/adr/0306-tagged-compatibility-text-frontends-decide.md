# ADR-0306: Compatibility text is tagged, and every frontend decides what to render

**Status:** Accepted (2026-09-20, #3933)

## Context

One web login rendered its whole server lifecycle as story content: `You become Tehom`,
Evennia's stock look of the room, our own `look`, `Now controlling Tehom`, and, from the
client's reconnect-time `@ic`, `Already controlling Tehom`. One pose rendered twice, as
the compatibility text line and then as the structured Interaction that the reader
actually shows. Every reconnect replayed all of it.

Each of those lines exists for telnet. The web client has a structured render for the
same fact: an Interaction for a pose, a room panel for the entry look, a session
lifecycle state for a puppet milestone. So the question was where the two clients part
company.

## Decision

**The server tags compatibility text with metadata and sends it to every session; each
frontend decides what to render.** A line that also has a structured render carries its
meaning in the frame's options: `{"type": <mode>, "interaction_echo": True}` for an
Interaction echo, `{"type": "lifecycle", "event": ...}` for a puppet milestone, and
`on_entry: True` for the joining session's look. Evennia's tuple form `(text,
{options})` is the carrier, so the options arrive as the websocket frame's kwargs, which
is where `type` already rode (#3856). Telnet ignores the options and prints the text.
The web client drops the three tagged shapes and keeps everything else.

The vocabulary is one module, `src/core/wire_options.py` (`TextFrameOption`,
`TextFrameType`, `LifecycleEvent`), so no layer spells a tag as a free string.

**The rejected alternative was a server-side per-protocol filter in
`ServerSession.data_out`.** It would have read the session's protocol and dropped the
compatibility line for a websocket session. Three things rule it out. It makes the
delivery layer branch on protocol, which puts protocol sniffing into typeclass hooks and
service functions that have no business knowing one. It is untestable at one seam,
because what a session receives then depends on which protocol the test built. And its
failure mode is silent: a filter that drops the wrong line removes a message nobody
sees, and nobody reports a message that never arrived. Tagging fails the other way. A
missing tag leaks a visible duplicate into the feed, which a player reports on the first
login.

The endpoint of this model is telnet rendering structured frames as well. At that point
the compatibility echo and its tag both disappear, and no filter has to be unwound. That
is separate telnet work.

## Consequences

Adding a producer of compatibility text now carries one obligation: tag the line if it
also records an Interaction or announces a lifecycle milestone. The client rule is three
checks in one place (`dispatchLegacyText`), not a growing list of text patterns.

One case stays imperfect and is recorded rather than papered over. A place-scoped pose
or emit passes `echo_of=None`, so its room line renders as an ordinary note. The reason
is a scope mismatch, not an oversight: `record_interaction` fills a place-scoped row's
receivers from `PlacePresence`, so the Interaction reaches only the personas at that
Place, while `message_location` broadcasts the compatibility line to the whole room. A
tag would leave a room occupant outside the Place with the line dropped and no
Interaction to replace it. Personas at the Place therefore see both the line and the
Interaction. The real fix is place-aware room delivery, which is its own design.

## Alternatives rejected

- **A per-protocol filter in `ServerSession.data_out`** - see above: protocol sniffing
  reaches into typeclass hooks, one seam can no longer be tested protocol-free, and the
  failure mode is an invisible dropped message.
- **Text matching on the client** - deciding from the wording of `You become X.` or
  `Already controlling X.`. It breaks on any rewording, on colour markup, and on
  translation, and it encodes server strings in the client.
- **A separate out-of-band frame beside each text line** - the client cannot attach a
  sibling frame to the line it describes, which is the same reason `type` rides the
  tuple form rather than a keyword of its own (#3856).

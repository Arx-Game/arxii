# The actor is rendered into the line at display time, by one server formatter

**Status:** Accepted (2026-09, #3858)

**Context.** A pose or a say has to read as a whole sentence with its actor in it,
`Apostate is testing`, `Apostate says, "Test"`, on the web and on telnet alike; the
card above a bubble (avatar, name, time) is metadata and never stands in for the
actor. Production showed both halves broken: the web readers drew the raw
`content` under the card, and `PoseAction` broadcast a pose to telnet with no name
at all. The recorded `content` is also what threading (#3787), muting (#2087),
comprehension (#2993) and search read, so whatever renders the sentence must not
change what is stored.

**Decision.** One server-owned formatter, `world/scenes/line_rendering.render_line`,
turns a name, a mode and a content into the line: a pose opens with the name (with
semipose glue for `'s`/`,`, and a pose that already opens with the name is left
alone), say, whisper, mutter and shout quote the text after their verb and name the
language, and emit, action and outcome rows pass through. It runs at display time
only. The WebSocket payload and `InteractionListSerializer` carry the result as
`line`, built from the name that viewer already sees on the card (a mask stays a
mask, #1109; a companion pose reads as the companion, #3294) and the content that
viewer already reads (a comprehension-garbled say is a garbled sentence; a muted
row stays blank). Telnet calls the same formatter: the pose broadcast carries
`{caller}`, which `message_location`'s mapping resolves per looker, and the whisper,
mutter and companion lines come from it too. Say keeps `$You() $conj(say)` on
telnet, Evennia's own second-person echo to the speaker (#2993 M2); for every other
listener it already reads as the formatter's line. The readers show `line` and
everything else keeps reading `content`; the client sets the leading name a shade
heavier only when the line opens with the card's own name, a presentation choice
derived from data the server already sent, never a second formatter.

**Rejected alternative: store the rendered line on the interaction.** A stored
line freezes the name as it was at write time, which sounds right until a viewer's
relationship to a mask changes (#1109 reveals the real name only to viewers who
have discovered it, so one stored string cannot be right for both), a language is
learned later (#2993 deliberately re-renders comprehension on every read), or a
mute hides the text (the stored line would still carry it). It would also give
telnet and the web two places to drift apart and would double every content
column on the partitioned interaction table. Rendering at read time from the
per-viewer name and content the serializer already resolves costs a string
concatenation per row and keeps one truth.

**Rejected alternative: render on the client from `persona.name` and `mode`.** The
grammar would then live in TypeScript and in Python, and the two would drift the
first time either grew a case (the semipose glue, the language clause, the
companion name). The server is the only place that already knows the per-viewer
name and content together.

# ADR-4128: A pose is a prose line; left click plays, right click sorts

**Issue:** #4128 · **Related:** ADR-0299 (the one formatter puts the actor in the line),
#3856 (the feed's blocks, minimise and dismiss), #4030 (the persona menu).

## Context

The feed rendered every pose as a card: a header row (avatar, name, timestamp), a role
label ("Standalone", "Opening pose"), a bubble, a Kudos chip, Show less / Reply links,
and two hover buttons at the top right for minimise and dismiss. Roleplay is paragraphs
of prose most of the time, and the maintainer, reviewing the conversation-rail demo, found
the chrome got in the way of reading it and the hover buttons easy to miss. Whispers and
tabletalk had no sentence form of their own beyond `Name whispers, "…"`.

## Decision

A pose renders as its sentence or paragraphs and nothing else: the avatar floats at the
start as an indent (the first line beside it, later lines wrapping back under it), the time
shows only on hover, there is no header row, role label or bubble. The server's one
formatter gains two lead-ins so web and telnet agree: a whisper typed as an emote reads
*Quietly, Name …*, and anything posed at a place reads *At <place>, …*.

Controls split by button, and never sit on the line. **Left click is play flow**: the
avatar (or name) opens Reply, Kudos, then the persona menu as it was, Mute and Block
included. **Right click is information flow**, how text renders: a quick right-click on the
text folds the line to its one-line stub and unfolds it again; a held right-click, a
long-press, or a right-click on the avatar opens the sorting menu (Minimize or Expand, Hide,
Minimize all from this character, Hide all from this character, Minimize all, Expand all,
Unhide all). "Show hidden" stays at the top right of the feed while anything is hidden.
There is no hide-everything: "players don't really work that way, it would only be a
noob trap". Labels are American English (Minimize).

## Rejected

Keeping hover buttons on a condensed card (obscured, jarring, easy to miss); putting the
sorting controls behind the same menu as the play actions (one menu for two kinds of
intent); a say form of tabletalk (`tt I fold.` → *At the table, Aria says, "I fold."*):
tabletalk is a pose at a place on every path today, so the formatter renders SAY at a place
but nothing produces it until a say-at-place audience path exists.

## Consequences

`FeedBlockFrame` owns the gestures and the `LineMenu`; the persona menu gains
`contextMenu={false}` so the two never share the right button on a pose. The feed's
per-pose Kudos chip and the `poseRoleLabel` are gone. The browser's own context menu must be
suppressed at document level while ours is open: on Windows `contextmenu` fires on mouse
up, after a held press has opened ours under the pointer.

# Narrative play design and implementation specification

Tracking issue: [Arx-Game/arxii #3731](https://github.com/Arx-Game/arxii/issues/3731).

Start with **[arx-play-specification.md](arx-play-specification.md)**. It is the authoritative design handoff and supersedes the preliminary layout guidance in the original brief. It specifies one sidebar, long-form typography, independently scrolling history/context, explicit collapsible reply threads, historical reference, scoped drafts, lifecycle states, data contracts, privacy/retention boundaries, existing-code reuse and 22 acceptance journeys.

The user confirmed that references open in the same wide reader, preserving the live draft with a clear return to live. Right placement, 14px desktop prose and explicit reply semantics are concrete design defaults; presentation can be refined without dropping the mandatory capabilities.

## Revised reader study

- [Interactive source](arx-wide-reader.html) for the Codex conversation.
- [Standalone preview](arx-wide-reader-preview.html): download and open locally; GitHub displays source rather than executing it.
- [Desktop reader](arx-wide-reader-desktop.png), [historical whisper reference](arx-wide-reader-reference.png), [phone reader](arx-wide-reader-mobile.png).
- [Local validation results](wide-reader-validation.json).

The reader study demonstrates smaller prose, a single sidebar, collapsible exchanges, sample history lookup and preserved live writing. The fixture has 500 poses across 20 threads, with a 250-pose thread. Five poses are displayed per sample page so the presentation can be explored without mounting the full fixture. Production page sizes and windowing requirements are in the spec.

Try collapsing an exchange, expanding it, loading earlier replies, selecting History and searching for `Aldren`, then returning to the live draft. Optional Codex design controls change sidebar placement, prose size and spacing. All interactions remain local; sample identities/prose/actions are fictional.

This is a focused design study, not the implementation or proof of production performance. It does not implement backend authorization, production pagination/windowing, exact unread tracking, full conversation datasets, persistence, rich-text editing, reliable delivery, character entry or combat. Conversation selections illustrate scoped drafts; the same fixture remains visible and does not constitute a private-feed implementation. The written specification takes precedence wherever the prototype simplifies behavior.

Validation: 20 combinations of light/dark theme, left/right sidebar and 320/360/736/1024/1440px widths; no horizontal page overflow or runtime errors. Local checks exercised independent scrolling, collapsed arrivals, history search, read-only reference, draft restoration, reply/send and the exported preview's form handler. Production acceptance tests remain work for implementation.

## Initial designs preserved

The original [brief](arx-play-design.md), [interactive study](arx-narrative-play.html), [standalone preview](arx-play-preview.html), and `arx-scene-*`, `arx-exploration-*`, `arx-combat-*`, `arx-conversation-*`, `arx-reading-*` screenshots remain as visual references. Their three-column layout is superseded by the specification. Encounter and exploration content still inform the final experience.

This branch contains documentation/design artifacts only. No production implementation, merge or deployment is included. When implementation begins, create a repository worktree and follow AGENTS.md; do not transplant the prototype DOM code into React.


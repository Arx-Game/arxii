# ADR-0228: Board posts are authored by Persona, not by account or CharacterSheet

**Status:** Accepted (2026-08-22, #3286).

Player-postable bulletin boards (#3286) needed an authorship FK on
`BoardPost`. The candidates were the OOC account, the `CharacterSheet` (the
body), or the `scenes.Persona` (the face). We picked `Persona`.

A board notice is IC correspondence, consistent with the 2026-08-19 IC/OOC
messaging split ruling (PlayerMail stays OOC; IC messages get their own
storage). Pinning it to `CharacterSheet` would mean a masked/temporary face
could not post under its false identity without leaking the real one at the
data layer - the whole point of the shipped persona-masking system
(anonymous-notice gameplay) would be unavailable for free. Pinning it to the
account would be worse: it collapses every alt onto one row and breaks the
"a tenure never outs another tenure's alt" invariant this codebase already
enforces elsewhere (`feedback-never-account-names-tenure-identity`).

`Persona` is the correct authorship unit because it IS the identity a
character is presenting to the world at post time. Reading it back already
has a proven per-viewer resolution path
(`scenes.persona_display.resolve_display_for_viewer`) that renders a masked
poster as the mask, a discovered mask as `"<mask> (<real>)"`, and lets staff
see through every mask - no bespoke display logic was needed for boards,
and no reinvention of the persona-discovery machinery.

The rejected alternative (CharacterSheet FK, revealing the real identity in
admin/API payloads regardless of mask state) was ruled out because it would
have made a "masked notice" feature that only worked in the fiction, not in
the data - any staff or API leak would defeat the mask entirely, whereas
persona-scoped authorship keeps the reveal boundary exactly where the rest
of the persona system already draws it.

# ADR-4329: An object has one description store and one renderer; Evennia's desc is retired

**Status:** Accepted (#4329, 2026-10-13). Extends ADR-0213 (look renders through the action
layer, not typeclass hooks) and ADR-0306 (#3933, the login look).

**Context.** Arx stores a description in `ObjectDisplayData.permanent_description` (a
character's on its sheet, `additional_desc`) and renders it through `LookAction`. Evennia keeps
a second store, the `desc` Attribute, and its own code still used it: the stock `desc` command
wrote it, two dream-room seeds wrote it, and `DefaultCharacter.at_post_move`, reached by
`Character.at_post_move`'s `super()`, sent a stock look that read it. Nothing errored. Staff
`desc` answered "The description was set on Limbo." while `look` never changed, and every room
the world builder made arrived as "This is a room." with no exits while `look` in the same room
showed the authored text. `BaseState.description` also read `item_data.desc`, which no handler
defines, so `look` at any plain object or exit said "You see nothing of note.".

**Decision.** One store and one renderer. Every description write goes to `ObjectDisplayData`
through `evennia_extensions.services.display.set_permanent_description` (a character's through
the versioned `set_physical_description`), and every read is the data handler's
`get_display_description()`, which `BaseState.description` now calls. `desc` is overridden to
write there with Evennia's own permission checks and line editor. The post-move look runs our
`look` command (as the login look has since #3933); `super(DefaultCharacter, self)` passes over
exactly the stock hook. Migration 0221 carries any text still held in the Attribute into an
empty `permanent_description`. The `evennia-desc-attribute` hook rejects the Attribute in
`src/`, and `evennia-stock-path-reviewer` reads for the wider shape.

*Rejected:* keeping the Attribute in step (writing both stores, or having our renderer fall
back to it). That keeps Evennia contribs and the tutorial world working unmodified, but it
leaves two copies that drift the first time any path writes only one, which is the bug this
fixes. *Rejected:* removing `desc`. Staff reach for it from telnet and the console out of habit,
and the ruling (ApostateCD, 2026-10-13) was that it should describe any object.

**Consequences.** Evennia code that reads or writes `db.desc` (contribs, the tutorial world,
`DefaultObject.return_appearance`) shows defaults here, never our descriptions; anything adopted
from Evennia that renders a description has to be routed through `LookAction` first.

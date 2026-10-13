# ADR-4329: An object's description has one store per kind and one renderer; Evennia's desc is retired

**Status:** Accepted (#4329, 2026-10-13). Extends ADR-0213 (look renders through the action
layer, not typeclass hooks) and ADR-0306 (#3933, the login look).

**Context.** Arx keeps a description where its kind owns it: a room, plain object or exit in
`ObjectDisplayData.permanent_description`, a character on its sheet (`additional_desc`), an
item on its `ItemInstance` (`custom_description`, else the template's). It renders them through
`LookAction`. Evennia keeps a second store, the `desc` Attribute, and its own code still used
it: the stock `desc` and `setdesc` commands wrote it, two dream-room seeds wrote it, and
`DefaultCharacter.at_post_move`, reached by `Character.at_post_move`'s `super()`, sent a stock
look that read it. Nothing errored. Staff `desc` answered "The description was set on Limbo."
while `look` never changed, and every room the world builder made arrived as "This is a room."
with Evennia's contents list while `look` in the same room showed the authored text.
`BaseState.description` also read `item_data.desc`, which no handler defines, so `look` at any
plain object, exit or item said "You see nothing of note.".

**Decision.** One store per kind and one renderer, never the Attribute.
`BaseState.description` reads an item from its instance and anything else through the data
handler's `get_display_description()`. `desc` is overridden (Evennia's own permission checks
and line editor) to write each kind's store: a character's through the versioned
`set_physical_description`, an item's `custom_description`, anything else's through
`evennia_extensions.services.display.set_permanent_description`, the shared writer new code
uses (the builder's room creation and the seeds call it; `set_room_display_data` and grid
import still write the same field directly). `setdesc` is removed. The post-move look runs
`LookAction` at the room, as typed `look` does, and never as typed input (inside the line
editor the word would join the buffer); `super(DefaultCharacter, self)` passes over the stock
hook. Migration 0221 carries text still held in the Attribute into an empty
`permanent_description`. The `evennia-desc-attribute` hook rejects the Attribute in `src/`, and
`evennia-stock-path-reviewer` reads for the wider shape.

*Rejected:* keeping the Attribute in step (writing both stores, or having our renderer fall
back to it). That keeps Evennia contribs and the tutorial world working unmodified, but it
leaves two copies that drift the first time any path writes only one, which is the bug this
fixes. *Rejected:* removing `desc`. Staff reach for it from telnet and the console out of habit,
and the ruling (ApostateCD, 2026-10-13) was that it should describe any object.

**Consequences.** Evennia code that reads or writes `db.desc` shows defaults here, never our
descriptions: contribs, the tutorial world, `DefaultObject.return_appearance`, and three
Builder-only stock commands still in the cmdset, `@set <obj>/desc = ...` (writes the
Attribute), `@spawn` (a prototype's `desc` becomes the Attribute) and `@copy` (copies
Attributes, not `ObjectDisplayData` or `RoomProfile`, so a copied room shows "This is a
room."). Anything adopted from Evennia that renders or sets a description has to be routed
through `LookAction` and the stores above first.

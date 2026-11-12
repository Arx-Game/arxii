# Messengers glossary

**Missive** (#3289):
An in-character letter from one persona to another (`Missive`). Written under a face,
delayed in game time by its transmission method, readable once it arrives, and able to carry
coin and items. Addressed to a persona, never to a character or a player. A reply goes out
under the face the original was written to, so answering a letter sent to a mask never
unmasks the writer.
_Avoid_: letter, mail, message, PlayerMail for an IC missive. `PlayerMail` is the OOC,
tenure-routed player-to-player surface in `world.roster` (ADR-0226); "letter" is fine as
play-facing prose but never as a code name.

**Transmission method** (#3289):
A staff-tuned way a missive travels (`TransmissionMethod`): its in-game delay, whether it can
carry items and coin, and who may use it (universal, or a character whose effective value of
a required capability is above zero, the hook for a magical method). Staff author it in the
admin; it is the only missives model with an admin.
_Avoid_: courier type, delivery mode, channel (the offscreen-contact channels are a
different system).

**Messenger** (#3289):
The seeded universal transmission method: a runner from the messenger guild who carries a
letter across the city. It is the default method, open to everyone, and its delay is a
30 IC-minute placeholder staff tune. The in-fiction word is "messenger"; the code name for
the thing it is an instance of is Transmission method.
_Avoid_: courier, postman, mail service.

**Undeliverable** (#3289):
`Missive.undeliverable`, the write-then-suppress block (ADR-3289-A). When the two
correspondents' players are blocked, a send is written like any other and flagged
undeliverable: the recipient never sees it, the sender is never told, and any coin or items
on it stay held. Checked at send, again at arrival (the sweep and read time). Never shown to
either side, never serialized.
_Avoid_: blocked missive, bounced, rejected, returned (nothing is returned; that would
reveal the block).

**Attachment resolution** (#3289):
Where an item or sum of coin riding on a missive stands (`AttachmentResolution`): pending
("Waiting", held in custody), accepted (the recipient took it) or refused (it went back to
the sender's character). Resolved by `accept_missive` / `refuse_missive`; an item is in
transit on at most one pending attachment at a time.
_Avoid_: delivery status (a missive arrives; its attachments are answered), claim.

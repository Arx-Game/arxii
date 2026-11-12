# Channels glossary

**Channel**:
A persistent named out-of-character chat room (`Channel`), one of three kinds:
PUBLIC (the curated game-wide channel), ORG (one per non-covert organization),
STAFF. "Channel" always means this OOC surface. In-character speech (say, pose,
whisper) is never a channel, and Evennia's `ChannelDB` is not used for player
channels (ADR-3299).
_Avoid_: comm, chat room, "IC channel" for say/pose/whisper (call those scene
speech), Evennia channel.

**ORG channel**:
The `Channel` anchored to one `Organization` (`organization` set, `kind=ORG`).
Its label is the organization's current name. Covert and covenant-backed
organizations have none. A house's ORG channel is the house channel.
_Avoid_: house channel as a separate thing, org chat.

**Speaker**:
The identity a player speaks as in a channel: one of their own roster tenures,
chosen per channel and shown as the character name for a first player or
"2nd player of Ariel" otherwise (`RosterTenure.speaker_name`). Never an account
name.
_Avoid_: handle, account name, nick, alias.

**Display tenure**:
The tenure a subscription speaks as (`ChannelSubscription.display_tenure`),
limited to tenures eligible for that channel. Each message freezes the tenure it
was posted under as its author tenure.
_Avoid_: channel identity setting, default persona (a tenure is not a Persona).

**Subscription**:
An account's membership in one channel plus its per-channel preferences
(`ChannelSubscription`: speaker, mute, collapse, notification level, order,
last read).
_Avoid_: channel membership (reserved for `OrganizationMembership`), listener.

**Muted channel**:
A subscription with `muted` set: no live push and no unread badge, still
readable when opened. Distinct from muting a player (`world.scenes` Mute),
which drops that player's channel messages silently.
_Avoid_: silenced, gagged.

**Channel ban**:
A staff ban of one account from one channel (`ChannelBan`); it removes the
subscription and outlives it.
_Avoid_: channel_banned permission (Evennia's, not honoured).

# ADR-0197: Dreamwalk presence is a persisted row keyed on the host sheet, not ephemeral per-process state

#3003 replaces the pre-existing `ndb.dreamwalk_destination` stash with `DreamwalkPresence`, a
`SharedMemoryModel` row FK'd `dreamer -> CharacterSheet` (unique) and `host -> CharacterSheet`.
`ndb` was rejected on two grounds: it is process-local, so a server reload silently strands a
dreamwalker mid-visit with no record of where they went or how to get back; and it is
unqueryable, so no surface — telnet, web room-state, or a future "who's dreaming with me right
now" readout — can ever answer the question without walking every online character's in-memory
state. The anchor is the host's **sheet**, not a room: a raw `target.location` has no guaranteed
`RoomProfile` row (see ADR-0008's idmapper-pk-sharing caveat), and dreamwalking targets a person,
not a place — the walker should keep following a host who wakes and moves rather than being
stranded in a room the host has left. The consequence is that every dreamside-redirect call site
(look perception, the web room-state push, the dream-engagement wake gate, the dreamwalk action's
entry, and the wake action's escape lever) now routes through one service, `dreamspace_for(sheet)`,
so telnet and web can never disagree about whose dreamspace a character currently perceives.

> Status: accepted · Source: #3003 · Related: ADR-0008 (SharedMemoryModel), ADR-0131 (death off-ramp, #2287)

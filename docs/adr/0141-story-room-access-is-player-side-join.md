# Story-room access is a consent-first player-side join, not a GM summon

GM story areas and temp scene rooms (#2450, epic #2436 slice 3) need a way for a GM to bring
players into a room they built or spun up. The chosen shape is a `StoryRoomGrant` — a GM-issued
row naming a room and a character — that gates only the `join_story_room`/`leave_story_room`
verbs (telnet `joinroom`/`leaveroom`, actions `join_story_room`/`leave_story_room`); the
character must dispatch the join themselves, `join_story_room` captures their `return_location`
at that moment (`world.gm.story_services`), and `leave_story_room` (or a GM's
`close_scene_room`) sends them back to it, falling back to `home` only if that origin location
is gone. Once inside, movement between story rooms rides ordinary exits the GM links with
`story_link_rooms` — the grant plays no further role in navigation. Two alternatives were
rejected: a GM-summon verb that force-moves a character into the room the instant it's granted
(no per-scene yes from the player — every other "GM changes where a player's body is" surface in
this codebase, e.g. `EntranceAction`/`ConsentRequestCommand`'s ADR-0024 consent gate, requires
the target's own action or explicit accept); and auto-moving an entire `GMTable`'s membership
together (couples two unrelated lifecycles — table membership is long-lived and roster-wide,
while a scene room's population is per-scene and often a subset of the table — and removes the
player's ability to decline or arrive late).

> Status: accepted · Source: epic #2436, issue #2450 (GM story areas / dungeon & mission maps) ·
> Related: ADR-0024 (consent gates behavior-altering effects), ADR-0139 (staff world-builder
> canvas — the room-graph substrate story rooms share), ADR-0140 (grid content export/import —
> STORY-origin rooms are excluded by construction)

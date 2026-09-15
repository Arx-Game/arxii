# Scene participation is read off the log, and the entrance is the first line

**Status:** Accepted (2026-09, #3867)

**Context.** A live scene has two kinds of people in the room: the ones in it and
the ones who have walked in and are reading before they pose. Nothing showed the
second group, the target picker offered them, `add_present_as_co_owners` made
everyone present a participant before anyone had posed, and the "make an
entrance" star (#904, #2183) was a toggle any pose could carry any number of
times, so the acclaim grant's earliest-`ENTRY` lookup and its per-scene dedupe
were only right by luck. Dan's design (2026-09-14): presence and participation
are two facts; participation begins with the first pose; the threshold is
visible and never OOC; the entrance is that first pose, not a toggle; leaving
without entering is nothing.

**Decision.** Whether a character is in a scene is read off the scene's log:
they have entered once the scene holds a room-heard line of theirs (a pose, a
say or an emit; `world/scenes/participation.py`). Nothing is stored for it.
`record_interaction` marks a writer's first such line `ENTRY` whatever the
client sent, demotes any later "entry" to standard, opens the acclaim window on
it and refreshes every occupant's `room_state`; `submit_pose` refuses a second
client-sent entry. `persona_can_receive`'s room-heard branch requires presence
and entry, so a target at the threshold is refused with its own wording, while a
whisper, directed by construction, still reaches them. `room_state` carries
`in_scene` per present character and `viewer_entered` on the scene block; the
Here panel marks the threshold with an asterisk and the composer shows the
entrance as a state, never a control. `SceneParticipation` keeps answering the
other question (admin co-ownership and read membership) and is not consulted.

**Rejected alternative: an `entered_at` column on `SceneParticipation`.** It
would need a backfill for a scene that formalises around people already posing,
which the issue named as the hard part; the log already answers it, since
`capture_prescene_interactions` attaches a present writer's recent room poses to
the new scene the moment it starts, so those people are in and nobody silent is.
A column would also double the truth: `SceneSerializer.participants` has derived
"who is in the scene" from the log since before this change, and two answers to
one question drift. The cost of deriving is one indexed `exists` per addressed
target and one batched query per room-state payload.

**Rejected alternative: keep the star as a toggle and only cap it at one.** A
control that is legal exactly once and refused every time after is a state
wearing a button's clothes; the server has to decide anyway, so the composer
reads the room's answer and the pose it sends agrees with it.

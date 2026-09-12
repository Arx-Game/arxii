# ADR-0293: Reachability governs who can be addressed; the reply parent is the thread's anchor

**Status:** Accepted (#3787, 2026-09-12). Related: ADR-0170 (concealed casts record no
target rows), ADR-0260 (per-request memo policy, unrelated mechanism but the same
"denormalize deliberately" instinct), #3757 (thread membership), #3760 (client_request_id
kept off the largest table).

**Context.** #3787 lets a player answer a mechanical event (a combat outcome, a failed
check, an NPC's swing) the same way they answer a pose: the row gets an involvement mark,
one control puts the composer on it, and the answer records what it answered. Doing that
required four decisions, each hard to reverse once other code depends on the shape.

**Decision 1: Reachability over audience promotion.** A player can only name or answer
someone in a venue where that persona is actually available right now
(`world/scenes/reachability.py`'s `persona_can_receive`). A reply from a private venue (a
Place, a table) to a public row is **refused**, never silently widened to reach it. The
refusal names the venue that would work and preserves the draft.

*Rejected alternative:* promote the reply to scene scope automatically, with a composer
notice explaining the widening. Rejected because it disrupts the thread the reader is
building (the reply lands somewhere the writer did not choose) and mutates the pose's
audience on the player's behalf without their consent at the moment of writing. A refusal
the player can act on is safer than a promotion they have to notice happened.

**Decision 2: Targeting and grouping are separate concerns.** `target_persona_ids` drives
two things and only two: the per-viewer involvement mark
(`interaction_services._send_involvement_mark`, gated on `target_character_ids`) and
`attention.ts`'s existing `direct` badge tier. It must **not** drive reader grouping.
`getThreadKey` (`frontend/src/scenes/hooks/useThreading.ts`) special-cases `action`/
`outcome` mode rows to key by scene (or `room`) before it ever reaches the `target:`
fallback that ordinary tagged poses still use.

The `direct` tier therefore reads `target_persona_ids` per row, not the thread key
(`game/attention.ts`). Those were the same answer while `target:` was the only key a
named row could land in; once mechanical rows key by scene, a key-based tier would
demote a blow aimed at you to `ambient` and leave user story 8 undelivered. Grouping
goes by scene, direct counts by targeting, and both halves of this decision hold.

*Rejected alternative:* let the existing `target:` fallback apply uniformly, including to
mechanical rows. Rejected because a resolved combat action can name several targets at
once (a cleave, an area effect); keying by target would fragment one fight into one reader
group per victim, destroying the "one exchange" reading a scene log depends on.

**Decision 3: System-authored rows record what happened; player-authored rows address
someone.** Only the latter is governed by reachability. `write_target_personas`
(`world/scenes/interaction_services.py`) is the shared writer, and it does no reachability
check of its own; `create_interaction` runs `persona_can_receive` before calling it for a
player's own tagging, while every system-authored writer calls it directly and skips that
check: `create_action_interaction_core` (`world/scenes/interaction_services.py`),
`create_npc_action_interaction` and `broadcast_action_outcome`
(`world/combat/interaction_services.py`), `create_cast_outcome_pose`
(`world/scenes/cast_services.py`), `narrate_privately`
(`world/scenes/interaction_services.py`), and the two resolved-action-request outcome
writers in `world/scenes/action_services.py`.

"System-authored" is about who composed the text, not which persona is credited:
`create_action_interaction_core` and the action-request outcome writers all credit a
PLAYER's persona while the content itself is machine-rendered from a resolved mechanic.
The test is whether the row records what happened (not governed by reachability) or
carries something a player wrote at somebody (governed). Adding a new caller of
`create_interaction`'s `target_personas` kwarg means asserting the row is the latter.

*The concrete forcing case:* Battle scenes are created with `location=None`
(`world/battles/models.py:165`), and the Narrator persona that authors ACTION/OUTCOME rows
is never physically placed anywhere. Requiring `persona_can_receive` on combat's own
targets would raise `UnreachableError` for every targeted hit in every Battle-scale
encounter, because there is no room for presence to be evaluated against. A resolved
action's target is already governed by the encounter's own targeting rules (must already
be a live participant/opponent); the narrative "is this persona standing somewhere this
pose actually reaches" question does not apply to a system-authored record of a mechanical
outcome.

**Decision 4: The parent edge is the thread's anchor, not a table of edges.**
`InteractionThread` carries `anchor_interaction` + `anchor_timestamp`, both required: the
row every member of that thread answers. The anchor is not itself a member. The `parent`
self-FK names the thread the anchor row belongs to when the anchor is itself a reply,
which is what makes this thread a nested one, and `root` denormalizes the top of that
tree so a reader groups a whole exchange without walking parents. A row's `thread`
therefore means "what I am an answer to", not "which pile I am in"; root poses keep
`thread_id` null. `parent(row) = row.thread.anchor`, and
`exchange(row) = row.thread.root or row.thread` (`world/scenes/models.py`,
`world/scenes/thread_services.py`).

*Rejected alternative:* a per-reply edge table (`InteractionReply`), one row per reply
holding a child reference and a parent reference with their own denormalized timestamps.
It was built, reviewed and merged into this branch, then removed at maintainer review.
Rejected because a flat membership container plus a separate edge table is two mechanisms
for one topology, and nesting expresses that topology with one. The duplication showed up
in the rows themselves: N people answering the same blow wrote N edge rows each repeating
the same fact, where one anchored thread carries it once. A reply to a reply is a nested
thread, the way a mailing list nests, not a new data structure.

Two things fell out of the anchored shape, and they are evidence for the decision rather
than decoration. First, `get_reply_to` needs no join and no per-row handler: the chip's
whole payload is `{id, timestamp}`, and both are columns on the thread row the serializer
already joins in, so `InteractionReplyHandler` and the `list()` priming that existed only
to feed it were both deleted and the list query budgets went down. Second,
`InteractionThread.parent` had existed since #3757 with no writer anywhere in the
codebase, a self-FK nothing ever set. A field designed and half-built is a strong hint
about the shape the model was already reaching for, and the edge table was building the
other half of it somewhere else.

**The partition constraint still governs the anchor.** `arxii_interaction` is monthly
range-partitioned with a composite primary key `(id, timestamp)`, so an ordinary
single-column database FK to its id cannot exist at all. The anchor is therefore
`db_constraint=False` paired with a denormalized `anchor_timestamp`, and
`unique_thread_per_anchor` over that pair is what makes "one thread per answered row"
true in the database rather than only in the service.

**The two channels gate the parent edge differently, and the WS gate is the weaker
one.** REST gates it per viewer on `visible_to(request.user)`
(`InteractionSerializer.get_reply_to`). The live WebSocket push has no single viewer, so
it uses a structural gate evaluated once (`interaction_services._reply_parent_payload`):
the parent goes on the wire only when it is room-heard in the same scene, using the
shared `managers.ROOM_HEARD` classification. State that gate's guarantee exactly: **it
discloses strictly less than the live push it rides on already delivers to that same
audience.** It does NOT match per-recipient REST visibility, and two cases send a parent
`visible_to` would withhold: a room-heard parent in a PRIVATE scene reaching a bystander
standing in the room who never authored or received anything in it (`visible_to`'s
`present_scene_ids` keys on authorship/receipt, not presence), and a parent older than
`visible_to`'s 90-day `time_bound`, which the room-heard predicate does not carry. Both
are accepted: the disclosure is an opaque id and an ISO timestamp with no path to content
(`ParentChip` renders "a pose not currently loaded" on a miss and never fetches), and
both recipients are receiving the reply's own full text over that same broadcast. Do not
restate this as "the WS gate can never over-disclose"; it can, in those two cases, and it
is fine because it still says less than the push already did.

**A correction worth recording:** `InteractionAction` (the POSE-to-ACTION-Interaction
bridge, `world/scenes/models.py`) is not a precedent for the denormalized-timestamp half of
this pattern. It carries `db_constraint=False` on both its FKs but no timestamp column on
either side, so it depends on the partitioned table never actually needing the timestamp
for a join it doesn't do. `InteractionReceiver` (`world/scenes/place_models.py`) is the
true precedent: FK plus denormalized `timestamp`, `db_constraint=False`, for the same
composite-PK reason the thread anchor needs it. An earlier draft of this spec cited
`InteractionAction`, and that citation was wrong. Do not cite it as justification for
adding a timestamp column to a future reference into the partitioned table; cite
`InteractionReceiver`.

*Rejected alternative:* an ordinary FK column `Interaction.reply_to` pointing straight at
the parent's id. Rejected outright, not weighed: the partitioned table's composite key
makes a single-column FK a schema error, not a style preference.

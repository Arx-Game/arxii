# ADR-0293: Reachability governs who can be addressed; the reply parent is the thread's anchor

**Status:** Accepted (#3787, 2026-09-12); decision 1 corrected (#3811, 2026-09-13).
Related: ADR-0170 (concealed casts record no target rows), ADR-0260 (per-request memo
policy, unrelated mechanism but the same "denormalize deliberately" instinct), #3757
(thread membership), #3760 (client_request_id kept off the largest table).

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

**Correction (#3811, 2026-09-13):** the refusal above was directionally too broad. A
Place declutters room chat - it hides table talk from the room so the room doesn't drown
in it - it does not isolate the table's occupants from the room. A player seated there
already sees every room-wide (or combat OUTCOME) row as it happens; answering one is not
an audience widening, since nothing about its audience changes and the writer already
had it. The refusal now applies to only ONE direction: a Place-held draft answering a
Scene-held target in the SAME scene is reachable (the reply keeps whatever venue the
writer actually chose - the thread it joins still anchors on the target's own Scene
holder, per decision 4's "holder kwargs always derive from the target's own signature").
The reverse direction is unaffected and stays refused: a Scene-drafted reply cannot reach
a Place-held target, because table talk was never visible outside the table in the first
place, and answering it from the room would be a genuine, un-consented widening of an
actually-private exchange. `world.scenes.thread_services._reachable_from_place` is the
narrowed check; `frontend/src/scenes/replyReachability.ts`'s pre-emptive mirror was
simplified to match (no ratified pre-emptive refusal remains on the composer side - the
one case it used to catch is now allowed, and the still-refused reverse direction has no
ratified copy to show in advance either, same as every other holder mismatch).

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

**Decision 4: The parent edge is derived from thread membership, not a table of edges.**
`InteractionThread` stores the members of an exchange and its `parent` self-FK. The
anchor is the first member of the thread, derived by `thread_services.thread_anchor_ids`
with `Min("id")`; it is a member, not a separate anchor field or timestamp column. When
an unanswered reply is answered, that reply becomes the
first member of a nested child thread, whose `parent` is the enclosing thread. The top of
the tree is derived by walking `parent` (`thread_services.thread_roots`), not copied to a
separate field. An `Interaction.thread` therefore identifies the thread containing the
answer; an unanswered root pose keeps it null. The reader derives the answered row from
the first member of the row's thread, or from the first member of its parent thread when
the row itself is that first member.

`thread_anchor_ids` and `thread_roots` are the canonical derivations used by the
serializer, live push, and play views. There is no one-thread-per-anchor database
constraint: two answers to the same row join the same thread through the existing
membership assignment, while nested replies use `parent`. The holder-shape check on the
thread still enforces scene, place, and fixed-party-whisper context.

*Rejected alternative:* a per-reply edge table (`InteractionReply`), one row per reply
holding a child reference and a parent reference with their own denormalized timestamps.
It was built, reviewed and merged into this branch, then removed at maintainer review.
Rejected because a flat membership container plus a separate edge table is two mechanisms
for one topology, and nesting expresses that topology with one. The duplication showed up
in the rows themselves: N people answering the same blow wrote N edge rows each repeating
the same fact, where one thread carries the membership once. A reply to a reply is a
nested thread, the way a mailing list nests, not a new data structure.

Two things fell out of this shape, and they are evidence for the decision rather than
decoration. First, `get_reply_to` derives the parent id from the thread-member aggregates
and the enclosing thread, then performs a page-wide `visible_to` lookup. The chip's whole
payload is `{id, timestamp}`, with the timestamp read from the parent interaction; no
`InteractionReplyHandler` or per-row edge lookup is needed. Second,
`InteractionThread.parent` had existed since #3757 with no writer anywhere in the codebase,
a self-FK nothing ever set. A field designed and half-built was a strong hint about the
shape the model was already reaching for, and the edge table was building the other half
of it somewhere else.

**The partition constraint still governs parent lookup.** `InteractionThread` stores no
foreign key or denormalized timestamp to the partitioned `Interaction` table. When a
reader needs the parent chip, the parent interaction is resolved with its `(id, timestamp)`
identity and checked by `visible_to`; `InteractionReceiver` remains the precedent for
cross-partition references that do store a timestamp. `InteractionAction` is not a
precedent for adding one.

**The two channels gate the parent edge differently, and the WS gate is the weaker one.**
REST derives the parent id from thread membership and gates it per viewer on
`visible_to(request.user)` (`InteractionListSerializer.get_reply_to`). The live WebSocket
push has no single viewer, so it uses a structural gate evaluated once
(`interaction_services._reply_parent_payload`): the parent goes on the wire only when it
is room-heard in the same scene, using the shared `managers.ROOM_HEARD` classification.
State that gate's guarantee exactly: **it discloses strictly less than the live push it
rides on already delivers to that same audience.** It does NOT match per-recipient REST
visibility, and two cases send a parent `visible_to` would withhold: a room-heard parent
in a PRIVATE scene reaching a bystander standing in the room who never authored or
received anything in it, and a parent older than `visible_to`'s 90-day `time_bound`, which
the room-heard predicate does not carry. Both are accepted: the disclosure is an opaque id
and an ISO timestamp with no path to content (`ParentChip` renders "a pose not currently
loaded" on a miss and never fetches), and both recipients are receiving the reply's own
full text over that same broadcast. Do not restate this as "the WS gate can never
over-disclose"; it can, in those two cases, and it is fine because it still says less than
the push already did.

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

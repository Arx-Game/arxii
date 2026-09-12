# ADR-0291: Reachability governs who can be addressed; the reply parent is a sparse bridge, not a column

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

**Decision 4: The parent edge is a sparse bridge, not a column.** The new
`InteractionReply` model carries the reply parent as a bridge row, not an FK column on
`Interaction` itself: a child reference and a parent reference, each paired with its own
denormalized timestamp, both `db_constraint=False`, unique on the child
(`world/scenes/models.py`). `arxii_interaction` is monthly range-partitioned with a
composite primary key `(id, timestamp)`, so an ordinary single-column database FK to its
id cannot exist at all; the approved narrative-play spec mandates exactly this
timestamp-aware bridge shape. Keeping the edge in its own sparse table (one row per actual
reply, never one per Interaction) also keeps a web/narrative concern off the app's largest
table, consistent with #3760's ruling to keep `client_request_id` off it too.

**A correction worth recording:** `InteractionAction` (the POSE-to-ACTION-Interaction
bridge, `world/scenes/models.py`) is not a precedent for the denormalized-timestamp half of
this pattern. It carries `db_constraint=False` on both its FKs but no timestamp column on
either side, so it depends on the partitioned table never actually needing the timestamp
for a join it doesn't do. `InteractionReceiver` (`world/scenes/place_models.py`) is the
true precedent: FK plus denormalized `timestamp`, `db_constraint=False`, for the same
composite-PK reason `InteractionReply` needed it. Do not cite `InteractionAction` as
justification for adding a timestamp column to a future bridge; cite `InteractionReceiver`.

*Rejected alternative:* an ordinary FK from `Interaction.reply_to` straight at the parent's
id. Rejected outright, not weighed: the partitioned table's composite key makes a
single-column FK a schema error, not a style preference.

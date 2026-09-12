# Scene Interaction Threads

Narrative interaction threads group explicit replies without changing scene history,
privacy, or delivery rules.

**Source:** `src/world/scenes/`
**API:** `POST /api/interactions/submit-pose/` accepts an optional write-only `reply_to` target.

## Data model

- `InteractionThread` owns a UUID thread identity and immutable scene, place, or
  fixed-whisper-party holder metadata.
- `Interaction.thread` is nullable. Existing interactions remain unthreaded.
- `InteractionThread.parent` is nullable for a future nested-thread operation. The
  current reply path is flat and creates top-level threads only.
- Thread members use existing `(timestamp, id)` chronology. No order column is stored.
- `InteractionReply` (#3787) records the reply PARENT edge, separately from
  `InteractionThread` membership. `Interaction.thread` already answers "which exchange
  does this row belong to"; `InteractionReply` answers the narrower "which specific row
  did this one answer," which is what the reader's parent chip renders. One row per
  reply (unique on the child interaction), modelled on `InteractionReceiver` (see ADR-0292
  for why `InteractionAction` is NOT the precedent here): child and parent FKs are both
  `db_constraint=False` with their own denormalized timestamp, since `arxii_interaction`
  is monthly range-partitioned with a composite `(id, timestamp)` primary key and cannot
  take an ordinary single-column FK. Written inside `assign_interaction_thread`
  (`world.scenes.thread_services`), which already holds the locked reply target; read by
  `InteractionListSerializer.get_reply_to` via a prefetched, context-cached batch lookup,
  gated on the parent's own `visible_to` (a reader who cannot see the parent gets no
  `reply_to`, never a leaked reference).

## Reachability (#3787)

`world.scenes.reachability.persona_can_receive` is the one predicate answering "can this
persona receive content of this shape, right now" - a live spatial-presence question,
distinct from `InteractionQuerySet.visible_to` (a read-access/privacy-tier question over
history). It is read from two call sites, never duplicated:

- **Tagging** (`create_interaction`'s `target_personas` handling): every named target is
  checked before any row is written. A target who fails the check raises
  `reachability.UnreachableError` (`code = "target_unreachable"`), naming the venue that
  would work; `create_interaction` writes nothing when this fires.
- **Replying** (`thread_services.assign_interaction_thread`): a reply whose holder
  (scene/place/whisper-party signature) doesn't match its target's raises
  `InteractionThreadError` (`code = "reply_target_unavailable"`), carrying the same
  `venue_hint` shape when the mismatch is specifically a Place-to-scene reach failure.

Both refusals translate through the same `{code, field, detail, hint}` 400 body
(`interaction_views._refusal_response`) and the same telnet hint-append in
`Action.run()`'s exception handler (`actions/base.py`) - one refusal vocabulary for REST
and telnet alike. Both preserve the writer's draft; neither ever widens the audience to
make the reply land (ADR-0292, decision 1: refuse, never promote).

**Reachability governs only player-authored addressing.** A resolved combat action's
targets are written through `write_target_personas` directly, with no reachability check
- see ADR-0292, decision 3, and the module's own docstring for why (Battle scenes have no
location, so the check cannot even be evaluated there).

## Targeting drives the mark and the badge, never the grouping (#3787)

`target_persona_ids` (backed by `InteractionTargetPersona`, written by the shared
`write_target_personas` helper) feeds exactly two surfaces:

1. **The involvement mark** - "this happened to you," derived per viewer with no stored
   flag. Web renders it as the reader's `InvolvementFlag`/parent-chip treatment; telnet
   gets the equivalent plain-text line (`interaction_services._send_involvement_mark`),
   scoped to the recipient's non-webclient sessions only so a web session never sees the
   raw line duplicate its own chip.
2. **`attention.ts`'s existing `direct` badge tier**, via `useThreading.ts`'s
   `getThreadKey` deriving a `target:` key from `target_persona_ids` for ordinary tagged
   poses.

It must NOT drive reader **grouping** for mechanical rows: `getThreadKey` special-cases
`action`/`outcome` mode to key by `scene:<id>` (or `room`) before it ever reaches the
`target:` fallback, so a multi-target combat round stays one reader group instead of
fragmenting into one group per victim (ADR-0292, decision 2). Combat ACTION/OUTCOME rows
now carry `target_persona_ids` (`world.combat.interaction_services.
create_action_interaction_core` / `create_npc_action_interaction`), populated from the
targets the resolvers already hold; concealed tiers continue to record none, unchanged
(ADR-0170).

## Write contract

`reply_to` has the shape `{"id": integer, "timestamp": RFC3339 timestamp}`. It is
serializer/action input only. The service validates visibility with
`InteractionQuerySet.visible_to()`, exact timestamp, holder compatibility, and pinned
place/whisper audience before assigning the new interaction to a thread and writing its
`InteractionReply` parent edge.

Responses and websocket payloads expose `thread_id` and `reply_to` when membership/parent
data exists. They do not infer relationships from names, targets, proximity, or ordering.
Ephemeral interactions cannot join or create persisted threads.

## Key code

- `world.scenes.thread_services.assign_interaction_thread`
- `world.scenes.interaction_services.create_interaction`
- `world.scenes.interaction_services.write_target_personas`
- `world.scenes.reachability.persona_can_receive` / `UnreachableError`
- `world.scenes.interaction_serializers.ReplyTargetSerializer`
- `world.scenes.interaction_serializers.InteractionListSerializer` (`get_reply_to`)

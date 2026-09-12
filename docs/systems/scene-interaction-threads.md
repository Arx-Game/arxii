# Scene Interaction Threads

Narrative interaction threads group explicit replies without changing scene history,
privacy, or delivery rules. A thread is anchored at the row it answers, and answering a
reply nests a thread inside the one its anchor belongs to (#3787).

**Source:** `src/world/scenes/`
**API:** `POST /api/interactions/submit-pose/` accepts an optional write-only `reply_to` target.

## Data model

- `InteractionThread` is ANCHORED at the row it answers: `anchor_interaction` +
  `anchor_timestamp`, both required, name that row, and the thread's members are the
  replies to it. The anchor is not a member of its own thread. `unique_thread_per_anchor`
  over the pair is what makes two people answering the same blow land in one exchange
  instead of opening parallel ones.
- `Interaction.thread` is nullable and means "what I am an answer to", not "which pile I
  am in" (changed by #3787; #3757's flat membership put the answered row in the thread
  too). Root poses keep `thread_id = null`, and so does a row that is only ever answered.
- `InteractionThread.parent` names the thread the anchor row itself belongs to, when the
  anchor is a reply. Null makes this thread a root. Answering a reply therefore nests a
  thread rather than flattening into the enclosing one. The field has existed since #3757;
  #3787 is the first writer.
- `InteractionThread.root` denormalizes the top of the nesting tree, null on a root thread,
  so a reader groups a whole exchange without walking parents.
- `InteractionThread` also owns a UUID identity and immutable scene, place, or
  fixed-whisper-party holder metadata. `interaction_thread_holder_shape` pins which holder
  columns each kind may set; `interaction_thread_no_self_nesting` refuses a thread that
  nests inside itself.
- Thread members use existing `(timestamp, id)` chronology. No order column is stored.
- `anchor_interaction` is `db_constraint=False` with its own denormalized timestamp because
  `arxii_interaction` is monthly range-partitioned with a composite `(id, timestamp)`
  primary key and cannot take an ordinary single-column FK. `InteractionReceiver`
  (`world/scenes/place_models.py`) is the precedent; see ADR-0293 for why
  `InteractionAction` is not.
- There is no `InteractionReply` bridge and no reply-edge handler. A per-reply edge table
  was built and removed at review, because the thread carries the edge itself (ADR-0293,
  decision 4).

## The two derivations every consumer uses

`parent(row) = row.thread.anchor` and `exchange(row) = row.thread.root or row.thread`.
Nothing walks the tree; both are columns on the one thread row.

- **Parent** is the reader's chip. `InteractionListSerializer.get_reply_to` reads
  `anchor_interaction_id` / `anchor_timestamp` straight off the joined thread row (no join
  to the partitioned interaction table, no per-row handler), gated on the parent's own
  `visible_to` through a context-cached batch lookup: a reader who cannot see the parent
  gets no `reply_to`, never a leaked reference.
- **Exchange** is the grouping key. `get_root_thread_id` serializes it as `root_thread_id`,
  which the reader (`ThreadedNarrativeReader`) groups by so a nested back-and-forth renders
  as ONE card opening on the anchor, and which `useThreading.getThreadKey` prefers over
  `thread_id` so a nested exchange opens one conversation tab. Server-side,
  `play_views._exchange_keys` resolves the same pair of facts for a whole page in two flat
  queries, so `PlayThreadsView` groups by exchange and puts the root thread's anchor back at
  the head of its members when the viewer can see it.

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
make the reply land (ADR-0293, decision 1: refuse, never promote).

**Reachability governs only player-authored addressing.** A resolved combat action's
targets are written through `write_target_personas` directly, with no reachability check
- see ADR-0293, decision 3, and the module's own docstring for why (Battle scenes have no
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
fragmenting into one group per victim (ADR-0293, decision 2). Combat ACTION/OUTCOME rows
now carry `target_persona_ids` (`world.combat.interaction_services.
create_action_interaction_core` / `create_npc_action_interaction`), populated from the
targets the resolvers already hold; concealed tiers continue to record none, unchanged
(ADR-0170).

## Write contract

`reply_to` has the shape `{"id": integer, "timestamp": RFC3339 timestamp}`. It is
serializer/action input only. The service validates visibility with
`InteractionQuerySet.visible_to()`, exact timestamp, holder compatibility, and pinned
place/whisper audience before assigning the new interaction to the thread anchored at
that target, creating that thread only if this is the first answer to the row.

Responses and websocket payloads expose `thread_id`, `root_thread_id` and `reply_to` when
the row is a reply. `root_thread_id` is null when the row's own thread IS the root (a
first-level reply), so a consumer grouping an exchange falls back to `thread_id` there.
They do not infer relationships from names, targets, proximity, or ordering.
Ephemeral interactions cannot join or create persisted threads.

## Key code

- `world.scenes.thread_services.assign_interaction_thread`
- `world.scenes.interaction_services.create_interaction`
- `world.scenes.interaction_services.write_target_personas`
- `world.scenes.reachability.persona_can_receive` / `UnreachableError`
- `world.scenes.interaction_serializers.ReplyTargetSerializer`
- `world.scenes.interaction_serializers.InteractionListSerializer` (`get_reply_to`,
  `get_root_thread_id`)
- `world.scenes.play_views.PlayThreadsView` / `_exchange_keys`
- `frontend/src/game/components/ThreadedNarrativeReader.tsx` (exchange grouping)

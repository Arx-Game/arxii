# Scene Interaction Threads

Narrative interaction threads group explicit replies without changing scene history,
privacy, or delivery rules. A thread is anchored at the row it answers, and answering a
reply nests a thread inside the one its anchor belongs to (#3787).

**Source:** `src/world/scenes/`
**API:** `POST /api/interactions/submit-pose/` accepts an optional write-only `reply_to` target.

## Data model

- `InteractionThread` is ANCHORED at its first member: `thread_services.thread_anchor_ids`
  derives the anchor with `Min("id")` over the thread's interaction members. The anchor
  is a member of its own thread; no anchor interaction or timestamp columns are stored,
  and there is no one-thread-per-anchor database constraint.
- `Interaction.thread` is nullable and identifies the thread containing an answer. An
  unanswered root pose keeps `thread_id = null`. A target that is already in a thread
  may be moved into a nested child thread when answered, preserving the parent edge.
- `InteractionThread.parent` names the enclosing thread when this thread's first member
  was itself a reply. Null makes this thread a root. The top of the nesting tree is
  derived by walking `parent` (`thread_services.thread_roots`); it is not stored on the
  thread.
- `InteractionThread` also owns a UUID identity and immutable scene, place, or
  fixed-whisper-party holder metadata. `interaction_thread_holder_shape` pins which holder
  columns each kind may set.
- Thread members use the derived `Min("id")` anchor and existing `(timestamp, id)`
  chronology. No order, anchor, or root column is stored.
- There is no `InteractionReply` bridge and no reply-edge handler. A per-reply edge table
  was built and removed at review, because the thread's membership plus `parent` carries
  the topology (ADR-0293, decision 4).

## The two derivations every consumer uses

`parent(row)` is the first member of `row.thread` when `row` is not that first member;
when `row` is the anchor, it is the first member of `row.thread.parent`, if any.
`exchange(row)` is the derived root thread, or `row.thread` when that thread is already
root. `thread_anchor_ids` and `thread_roots` calculate these values; no anchor or root
columns are read.

- **Parent** is the reader's chip. `InteractionListSerializer.get_reply_to` derives the
  parent id from the thread-member aggregates and parent thread, then batch-checks that
  interaction with `visible_to`; a reader who cannot see the parent gets no `reply_to`,
  never a leaked reference. The returned `{id, timestamp}` comes from the parent row.
- **Exchange** is the grouping key. `get_root_thread_id` serializes the derived value as
  `root_thread_id`, which the reader (`ThreadedNarrativeReader`) groups by so a nested
  back-and-forth renders as ONE card opening on the anchor, and which
  `useThreading.getThreadKey` prefers over `thread_id` so a nested exchange opens one
  conversation tab. Server-side, `play_views._exchange_keys` resolves the same facts for a
  whole page, so `PlayThreadsView` groups by exchange and puts the root thread's anchor
  back at the head of its members when the viewer can see it.

## Reachability (#3787)

`world.scenes.reachability.persona_can_receive` is the one predicate answering "can this
persona receive content of this shape, right now" - a live spatial-presence question,
distinct from `InteractionQuerySet.visible_to` (a read-access/privacy-tier question over
history). Server-side, it is read from two call sites, never duplicated:

- **Tagging** (`create_interaction`'s `target_personas` handling): every named target is
  checked before any row is written. A target who fails the check raises
  `reachability.UnreachableError` (`code = "target_unreachable"`), naming the venue that
  would work; `create_interaction` writes nothing when this fires. Before the spatial check,
  #3827 also applies `block_services.social_control_excluded_target_ids` to player-authored
  targets. Active Block or IC Mute exclusions use neutral detail and preserve the draft without
  exposing which moderation row matched; system-authored target rows stay on the direct writer.
- **Replying** (`thread_services.assign_interaction_thread`): a reply whose holder
  (scene/place/whisper-party signature) doesn't match its target's raises
  `InteractionThreadError` (`code = "reply_target_unavailable"`) - **except** a
  Place-held draft answering a Scene-held target in the SAME scene, which is
  reachable by design (#3811 / ADR-0293 decision 1 correction): a Place declutters
  room chat, it does not isolate its occupants from it, so a reply from a table
  can always answer the room-wide (or combat OUTCOME) row it already saw. The
  reverse direction - a room-drafted reply reaching table talk it was never able
  to see - stays refused, with no ratified hint copy.

Both refusals translate through the same `{code, field, detail, hint}` 400 body
(`interaction_views._refusal_response`), and the typed errors are also handled by telnet
(`Action.run()` in `actions/base.py`). The `hint` is optional: tagging refusals provide a
venue hint, while reply refusals currently do not. Neither ever widens the audience of an
already-refused reply to make it land (ADR-0293, decision 1); the Place-to-Scene case
above is not a widening, since the writer could already read what they're answering.

`tagReachability.ts` (#3810) mirrors tagging so the composer can give a pre-emptive
refusal before the server's authoritative check. `replyReachability.ts` (#3787) remains
permissive: there is no ratified pre-emptive refusal copy, and the reverse holder mismatch
is caught only by the server's authoritative check. These client and server rules must
stay aligned when a refusal is ratified or `persona_can_receive` changes.

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

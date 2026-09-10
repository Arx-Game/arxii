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

## Write contract

`reply_to` has the shape `{"id": integer, "timestamp": RFC3339 timestamp}`. It is
serializer/action input only. The service validates visibility with
`InteractionQuerySet.visible_to()`, exact timestamp, holder compatibility, and pinned
place/whisper audience before assigning the new interaction to a thread.

Responses and websocket payloads expose `thread_id` when membership exists. They do not
infer relationships from names, targets, proximity, or ordering. Ephemeral interactions
cannot join or create persisted threads.

## Key code

- `world.scenes.thread_services.assign_interaction_thread`
- `world.scenes.interaction_services.create_interaction`
- `world.scenes.interaction_serializers.ReplyTargetSerializer`
- `world.scenes.interaction_serializers.InteractionListSerializer`

# Combat narration shares the pose Interaction model and reply-threading

Combat ACTION and OUTCOME rows (`world/combat/interaction_services.py`'s
`create_action_interaction()`, `create_npc_action_interaction()`, and
`broadcast_action_outcome()`) write into the same `Interaction` model, the same
`visible_to()` gate, and the same #3757 reply-threading mechanism
(`thread_services.py`'s `holder_signature()`) that ordinary poses/says/whispers
use — not a separate combat log or event model. This was not a deliberate
design choice when #3757's threading and combat's narration were each built;
it fell out of both being written generically over "interactions in a scene."
It is now ratified as the intended direction: a player's pose can already
target a combat ACTION/OUTCOME row as a reply parent via the ordinary
mechanism, with no combat-specific branch or exclusion anywhere in the write
path. This extends ADR-0127's "combat is part of the same scene, not a side
trip" from routing down to the data model — narrating combat into a separate
log would silo it from the ordinary conversation feed and require a second,
parallel reply mechanism, which is the rejected alternative. What's still
missing — end-to-end test coverage proving the reply resolves cleanly, the
reply-parent display wiring (`get_reply_to()` always returns `null` today,
a pre-existing #3757 gap), and the reader design for what a reply-to-a-combat-
action should actually look like — is tracked in #3787, not built here.

> Status: accepted · Source: #3761 brainstorming (2026-09-11) · Related:
> ADR-0127, ADR-0274, #3757, #3787

# Traps ride situations, and a GM manages them rather than authoring them

A trap's authored blueprint stays `SituationTrapLink`, hanging off a `SituationTemplate`;
there is no standalone trap catalog row and no `place_trap` verb. #3002 asked for "the
authoring half of the trap loop" on the premise that no GM action places a trap, and that
premise was false: `SetSituationAction` (`set_situation`, JUNIOR-gated, telnet
`setsituation <name|id>`) has placed armed `Trap` rows since #1895, because
`instantiate_situation` mints one per authored `SituationTrapLink`. What was genuinely
missing was everything after placement, so #3002 shipped **management** instead:
`list_room_traps`, `arm_trap` and `gm_disarm_trap` (`src/actions/definitions/traps.py`,
telnet `gm trap list|arm <id>|disarm <id>`), each gated on
`MinimumGMLevelPrerequisite(JUNIOR)` **and** `IsSceneGMPrerequisite()`. Both gates are
required: JUNIOR matches the tier that can already mint armed traps, and the scene gate
exists because listing traps reveals concealed room content and a GM is also a player, so
trust alone would let any JUNIOR GM read the hazards of a dungeon they are merely standing
in. This is ADR-0110's catalog-not-invention rule applied unchanged - arming an authored
trap composes no mechanics and touches no `consequence_pool`.

**A standalone `TrapTemplate` was drafted and rejected.** It would have duplicated
`SituationTrapLink`, which already carries exactly the authorable fields (name, pool, both
check types, both difficulties, `is_hidden`) and is already registered in `CONTENT_MODELS`
so the lore repo can author it. ADR-0110's #2865 addendum rejected "a family of
one-challenge `SituationTemplate`s" because an impromptu challenge beat has no fiction of
its own; a trap is the opposite case. A trap is scenery, and "the sealed passage, which has
a spike pit in it" is the natural authored unit, so the reasoning that justified a
standalone challenge path argues against a standalone trap path.

**Collapsing `Trap` into `ChallengeInstance` was also rejected.** `Trap` is the only model
in the codebase that applies a consequence to a character unbidden, and it has three live
trigger sites: the `at_post_move` movement hook (`src/typeclasses/characters.py:548`), a
magic reposition landing (`src/world/magic/services/effect_handlers.py:453`), and a combat
knockback landing (`src/world/combat/services.py:9981`). A `ChallengeInstance` has no
trigger at all; it waits for a player to pick an approach. Collapsing the two would mean
bolting an entry trigger, a `Position` anchor, per-character resolution memory
(`detected_by`) and the `duration_rounds` tick onto a model that wants none of them, and
rewriting the magic zone-hazard and knockback paths, for no gameplay gain.

**Two consequences worth recording.** First, a GM-placed trap is now scene-scoped:
`instantiate_situation` takes a keyword-only `placed_by_sheet`, `SetSituationAction` passes
the placing GM's sheet, and `finish_scene_full` calls `teardown_conjured_hazards` alongside
the obstacle and rampart teardowns it already ran. An admin-authored trap has a null
`created_by_sheet` and so stays armed permanently, which is what a persistent dungeon
needs. Second, `teardown_conjured_hazards` was changed from a bulk `.filter().update()` to
a per-instance save loop, matching `tick_zone_hazards` directly above it and
`teardown_conjured_obstacles` beside it: a bulk update sends no `post_save`, so
SharedMemoryModel's identity map kept serving a stale `is_armed` and the GM's own trap
listing would have reported a disarmed trap as armed.

**Not closed by this decision:** the player half. `DisarmTrapAction` is registered but
unreachable, because it needs a `trap_id` and no serializer, view, command or frontend
surface exposes a trap to a player; `search_room` finds clues and concealed characters
only. `Trap.is_hidden` is written by `instantiate_situation` and read by nothing, and is
the field waiting on that surface - it is documented as unwired in place rather than
deleted, since it is authored on a `CONTENT_MODELS` row.

> Status: accepted · Source: issue #3002 (spec approved 2026-08-05), ADR-0110, #1895, #2865

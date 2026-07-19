# Investigation & discovery glossary

**Clue**:
A pointer to exactly one discoverable target — a codex entry, a mission, a captive to rescue, or a character secret — selected by `target_kind` and its matching per-kind FK. It is a real fact that always points at something: a clue cannot be saved without a target, so there are no red herrings and no empty clues. Carries a `NaturalKeyMixin` `slug` and is a `CONTENT_MODELS` citizen (#2451) — a `Clue` exports/imports as lore-repo content, natural-keyed by slug.
_Avoid_: hint, lead, red herring.

**RoomClue**:
A placement that hides a `Clue` in a room with an authored `detect_difficulty`, found via a Search check. The active-acquisition counterpart to a `ClueTrigger`, mirroring `room_features.Trap`. Carries a nullable-unique `fixture_key` (#2451) when placed from the staff world-builder canvas — see the areas glossary's "Fixture key" entry.
_Avoid_: hidden clue, room placement.

**ClueTrigger**:
A placement that grants a `Clue` passively on room entry to any eligible character who does not already hold it — no roll, the world reveals it because of who you are or where you are. The item-anchored variant `ItemClueTrigger` fires the same way on acquiring an item of a given kind. Carries a nullable-unique `fixture_key` (#2451) when placed from the staff world-builder canvas — see the areas glossary's "Fixture key" entry.
_Avoid_: passive clue, auto-grant.

**Search**:
The active acquisition path: the `SearchAction` charges AP plus mental fatigue and rolls the seeded Search CheckType (Perception + Investigation) against each hidden `RoomClue`'s `detect_difficulty`, acquiring the ones spotted.
_Avoid_: look, detect, perception roll.

**Research Project**:
A `ProjectKind.RESEARCH` project (on the shared `world/projects` framework, with `ResearchProjectDetails` naming the clue) by which contributors spend AP on Research rolls to win a clue's target collaboratively. The RESEARCH `resolution_mode`; progress is floored at zero so a failed help never detracts, and completion grants the target to every contributor.
_Avoid_: investigation, study.

**Rescue**:
The RESCUE clue target: a `Clue` pointing at a `Captivity`, planted at a capture site, that hands the finder the captive's rescue mission on acquisition. Capture plants discovery and freeing the captive clears the rescue clues.
_Avoid_: free, recover.

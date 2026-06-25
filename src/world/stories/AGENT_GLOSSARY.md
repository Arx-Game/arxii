# Stories glossary

**Story / Chapter / Episode / Beat / Transition**:
The narrative hierarchy: a **Story** is a top-level campaign container with a scope and maturity; a **Chapter** is a major arc within it; an **Episode** is a node in the episode DAG; a **Beat** is a boolean predicate attached to an episode (the gateable unit of progress); and a **Transition** is a first-class directed edge between episodes, fired automatically or by GM choice. Episodes are nodes and Transitions are edges — a Story progresses by satisfying Beats to make Transitions eligible.
_Avoid_: campaign (Story), arc (Chapter), session/scene (Episode), objective/flag (Beat), branch/link (Transition).

**Era**:
A temporal metaplot tag (player-facing "Season N") that stories and events are stamped against, with exactly one ACTIVE era enforced at a time. It is a temporal label, not a parent in the Story/Chapter/Episode hierarchy.
_Avoid_: season, age, epoch.

**Story Maturity**:
The authoring-completeness of a single Story / Chapter / Episode node — `StoryMaturity`: PITCH, OUTLINE, or PLOT. Per-node and orthogonal to runtime progress status, with no cross-node ordering constraint; it is how finished the authoring is, not where play has reached.
_Avoid_: draft state, completeness, stage.

**Progress Status**:
The finer-grained state of a progress pointer (`ProgressStatus`: ACTIVE, WAITING_FOR_GM, RESTING, COMPLETED, FORECLOSED). `is_active` stays True for ACTIVE / WAITING_FOR_GM / RESTING; COMPLETED and FORECLOSED clear it.
_Avoid_: progress state, pointer status.

**FORECLOSED**:
The honest terminal `ProgressStatus` for a progress run still in flight when its story is concluded — distinct from COMPLETED (which means the run genuinely reached an ending). It exists so an unfinished thread is never falsely reported done, nor left orphaned in a live state.
_Avoid_: cancelled, abandoned, completed.

**Resting Conclusion**:
The player-facing `Episode.resting_conclusion` text shown when a progress pointer RESTS at that episode — a deliberately non-final pause-point ending. Required before an episode can be promoted to PLOT maturity.
_Avoid_: ending, pause text.

**Story Note**:
An append-only, never-player-visible OOC authorial note attached to a Story — general notes and future-idea seeds for the next author. Distinct from per-node pitch/`description` text; not promotable and not editable through the API.
_Avoid_: GM note, comment, pitch.

**Story Scope**:
Which kind of subject a Story progresses for — `StoryScope`: UNASSIGNED (the default, not yet placed), CHARACTER (personal), GROUP, or GLOBAL. It selects the progress-pointer type, and an UNASSIGNED story rejects progress creation until it is assigned a scope.
_Avoid_: level, reach, audience.

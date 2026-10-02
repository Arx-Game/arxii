# ADR-4101: GM prompts are one queue, and a narration links to its prompt

**Issue:** #4101 · **Related:** ADR-0010 (FK direction), ADR-0270 (authored outcome
flavor replaces the head sentence, never the ledger), ADR-0293 (receivers and audience;
InteractionReceiver precedent), ADR-0237.

## Context

Big mechanical moments (an Audere surge, a Crossing, a miracle, a death, a resolved
stake) fired with generic authored text and the GM running the scene got no signal and
no chance to say something specific. A GM-facing confirm inbox already existed for one
case, the technique-entrance Dramatic Moment Suggestion (#2183).

## Decision

`DramaticMomentSuggestion` is renamed `GMPrompt`, moved to `world/gm`, and gains a
`kind` (seven values: the original `dramatic_moment` confirm kind, plus
`audere_surge`/`audere_ultimate`/`crossing`/`miracle`/`death`/`stake_outcome`). Every
narratable event calls `route_narratable_event`, which prompts each opted-in GM
(per-GM, per-group filter via `GMPromptFilter`), minus the event's own subject's
currently-playing account; with no recipient it returns `[]` and the caller delivers
the authored defaults itself, unprompted, exactly as before. A GM's narration is an
ordinary EMIT or PEMIT `Interaction` created by `EmitAction`/`PemitAction`'s
`gm_prompt_id` kwarg; a `GMPromptNarration` side row links it back to the prompt.

**A GM's narration never releases the authored defaults by itself.** Both legs of a
prompt (the room line, the private line) go out at most once, independently, and only
when the prompt's event CLOSES: every sibling GM's own copy of that event has reached
DISMISSED, whether by explicit dismiss, by the GM marking a narrated prompt "done," or
by `expire_scene_prompts` at scene end. A GM's first narration moves the prompt to
NARRATED, not DISMISSED, and stays open so the same GM can add more lines (a room line,
then a private line, in either order) before closing it. Release is computed fresh at
close time from the linked `GMPromptNarration` rows, under a `select_for_update` lock
on the event's sibling prompts in pk order (`_lock_siblings`): a dismiss racing a
scene-end sweep, or two tabs narrating the same prompt, serializes on that lock instead
of double-sending. This was not the first draft: an earlier version released on first
narration and sent the vision twice when a GM covered the room line before the private
one.

`GMPrompt.subject_persona` freezes the face the subject was presenting as at the
moment the event routed (`active_persona_for_sheet`, resolved once per event, shared by
every addressed GM's own copy); a later persona switch (removing a mask, wearing a
different one) must never rewrite what an already-routed or already-narrated prompt
says about who it concerns. The player-facing `narrates` field on the interaction feed
names this frozen persona through the page's own per-viewer display map (never a bare
unmasked name), and omits the subject's name entirely (`kind_label` only) when there
is no frozen persona (a scene-less `stake_outcome` prompt, or the persona was later
deleted, `SET_NULL`) rather than falling back to the current face.

Prepared per-character text (`CharacterCrossingText`, `CharacterSurgeText`) resolves
field by field: the character's own prepared text, then the patron variant (Crossing
only), then the tier default. A Crossing consumes its prepared text on use.

## Rejected

Extending `DramaticMomentSuggestion` in place (the name would lie for a Crossing or a
death); a parallel narration-prompt model (two GM inboxes instead of one queue); an
`Interaction.gm_prompt` column (an FK on the partitioned primitive, requiring DDL
edits to the hand-maintained partition SQL; the link stays a side row per ADR-0010);
a prompt row created even when no GM is present (a filtered-out kind, or an event whose
only candidate is the subject's own player, must create no prompt at all); releasing a
default the moment any GM narrates (double-sends the other leg when a GM covers the two
legs in separate sends).

> Status: accepted · Source: issue #4101 · Supersedes in part: #2183's confirm-only inbox

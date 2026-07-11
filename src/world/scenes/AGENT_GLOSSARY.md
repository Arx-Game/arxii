# Scenes glossary

**Scene**:
Root term — the primary roleplay-session entity (participants, personas, recorded interactions, privacy mode). Defined in the wider character/identity domain; not redefined here.

**Persona**:
Root term — the identity a participant wears within a scene (PRIMARY/ESTABLISHED/TEMPORARY), anchored by FK to the source-of-truth CharacterSheet. Not redefined here.

**SceneUnseenObserver**:
An active unseen-observation grant on a `Scene` — records that some mechanism (concealment today, a future scrying/remote-viewing feature later) lets a `CharacterSheet` witness the scene without other participants' characters being aware. Powers an OOC-only, identity-free "someone is watching" notice (ADR-0083) via `register_unseen_observer`/`clear_unseen_observer`/`has_unseen_observers` — never reveals *who*, only *that* someone is watching.
_Avoid_: lurker, hidden watcher, silent observer (this system explicitly guarantees no silent/undisclosed observation)

**Guise Sheet**:
The fabricated bio a non-primary (cover/established) persona presents as its own — its `Persona.profile` (a `character_sheets.Profile`: concept/quote/personality/background), so the *absence* of a bio doesn't out the cover as fake. Distinct from the sheet's `true_profile` (the real face's bio, presented by PRIMARY). Authored via `set_persona_profile`; lineage stays display-only (mechanical reads pin to `true_profile`).
_Avoid_: fake sheet, alt bio, cover profile (the model is `Profile`; the surface is the Guise Sheet).

**Gemit**:
Root term — a staff/GM broadcast pushed to a public-reaction surface. Not redefined here.

**SceneRound**:
A non-combat round/turn structure anchored to a room, carrying a gating mode (OPEN, POSE_ORDER, STRICT) plus per-round knobs (quorum, action cap, repeat-target lock). At most one active round exists per room. Combat is one specialization of this round seam; rounds advance on declared action, never on wall-clock time.
_Avoid_: turn, tick, combat round (for the general case)

**Pose**:
A single IC contribution recorded within a scene — the atomic unit of RP (pose, say, whisper, emit), modelled by `Interaction`. It carries its own privacy tier and target personas for thread derivation.
_Avoid_: message, post, line, Interaction (at player surfaces)

**Effort Level**:
The initiator's declared exertion on a social action (`EffortLevel`: very low / low / medium / high / extreme), forwarded at dispatch. It is a check-roll modifier and charges the initiator social fatigue — orthogonal to a technique's power levers.
_Avoid_: intensity, difficulty (effort is the initiator's input, not the target's)

**Difficulty Choice**:
The defender's authored plausibility band (`DifficultyChoice`: trivial / easy / normal / hard / daunting) selected at consent time — the defender, never the initiator, sets how hard the action is to land. Frontend labels map to bands ("It works" → easy, "Hard but possible" → hard, "No way" → daunting).
_Avoid_: difficulty rating, target number (for the player-facing choice)

**Highlight reel**:
A read-only curated digest of a scene: one fully-sealed featured moment (highest-ranked GM-tagged pose, else most-ranked pose) plus a ranked index of remaining voted-or-reacted poses, capped at ten. Ranked by all-time `progression.WeeklyVote` count first (the popularity axis, persists past weekly XP settlement), `InteractionReaction` count as tie-break, recency last (#2161 — previously reaction-count-only). Filtered through interaction read-visibility so it can never surface a pose the viewer cannot see. Each pose carries a `VoteButton` (see `progression/AGENT_GLOSSARY.md`'s Weekly Vote entry) so applause and reel ranking are driven by the same click.
_Avoid_: feed, recap, summary, spotlight

**Co-owner**:
A character marked `is_owner=True` on their `SceneParticipation` because they were present in the room at scene creation, granting scene-administration rights (finish, change round mode). Latecomers who join mid-scene are non-owner participants and never inherit admin rights by entering.
_Avoid_: host, GM (GMs administer via story-runner status, not co-ownership), moderator

**Sudden Harm (out-of-combat Interpose)**:
The non-combat sibling of combat's Interpose maneuver (#1316) — a bystander readies a
capability-gated block against out-of-combat harm (a trap, a failed-check consequence) by
declaring `interpose_target` during a bootstrapped DANGER round instead of a `CombatRoundAction`.
Below the room's `sudden_harm_interpose_threshold`, or with no bystander present, harm still
applies immediately — this only exists for the significant, witnessed case. Named-ally only (no
"any ally" path), mirroring Succor's #1744 narrowing. See `world/combat/AGENT_GLOSSARY.md`'s
Interpose entry for the shared mechanism.
_Avoid_: reactive block, ambush guard, trap interpose (the model name is `PendingSuddenHarm`)

**ReactionEmoji** (reaction-emoji catalog, #1699):
The staff-editable catalog of emoji the scene footer offers on poses, each carrying a relationship valence (+1 / 0 / −1). Valence-0 entries are cosmetic — the pre-#1699 behavior, exactly. Nonzero-valence entries additionally fire an ambient relationship Bump (see `world/relationships/AGENT_GLOSSARY.md`) at the pose's author. Whether emoji survive playtesting is a data edit here (deactivate the row), never a deploy.
_Avoid_: emoji whitelist, emote catalog, sticker set.

# Scenes glossary

**Scene**:
Root term — the primary roleplay-session entity (participants, personas, recorded interactions, privacy mode). Defined in the wider character/identity domain; not redefined here.

**Persona**:
Root term — the identity a participant wears within a scene (PRIMARY/ESTABLISHED/TEMPORARY), anchored by FK to the source-of-truth CharacterSheet. Not redefined here.

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
A read-only curated digest of a scene: one fully-sealed featured moment (highest-reacted GM-tagged pose, else most-reacted pose) plus a ranked index of remaining reacted poses, capped at ten. Filtered through interaction read-visibility so it can never surface a pose the viewer cannot see.
_Avoid_: feed, recap, summary, spotlight

**Co-owner**:
A character marked `is_owner=True` on their `SceneParticipation` because they were present in the room at scene creation, granting scene-administration rights (finish, change round mode). Latecomers who join mid-scene are non-owner participants and never inherit admin rights by entering.
_Avoid_: host, GM (GMs administer via story-runner status, not co-ownership), moderator

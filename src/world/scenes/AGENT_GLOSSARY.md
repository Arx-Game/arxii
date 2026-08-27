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

**Spoken language** (#2993, ADR-0214):
`Interaction.language` (nullable FK to `species.Language`) records which tongue a say/whisper/mutter pose was spoken in — null means untagged/universal (poses, emits, pre-#2993 rows). It never changes what got written; it changes how each reader sees it — read-time comprehension (garbled per the reader's fluency, `species.language_services.render_speech`) is recomputed live on every serializer read, not snapshotted, so learning the language later un-garbles old logs. `CharacterSheet.current_language` is the separate sticky default a bare `say` speaks in; a `(tongue) text` prefix on `say` overrides it for one line only. See `species` AGENT_GLOSSARY's Language/Fluency/Garble entries for the trait-backed mechanics.
_Avoid_: persisting the garbled text on the Interaction (comprehension is always derived, never stored).

**Perceived Only** (#2710, ADR-0170):
An `InteractionVisibility` tier restricting an interaction to its writer and the personas recorded as `InteractionReceiver` rows — the characters who actually perceived the event — while still admitting staff and the scene's GM, so a scene stays runnable. The GM exception is a scene-log read guarantee only (`InteractionQuerySet.visible_to`'s `gm_visible` branch); a non-staff GM is denied on the REST object-access permission (`CanViewInteraction`) and the reaction-witness gate (`can_view_interaction`), both staff-only. Introduced for concealed casts (magic AGENT_GLOSSARY: "Cast Audience"), but the tier itself is a general scenes primitive, not magic-specific. Distinct from `VERY_PRIVATE`, which admits no exception, staff included — the two are not interchangeable.
_Avoid_: private (ambiguous with `VERY_PRIVATE`), hidden pose.

**Effort Level**:
The initiator's declared exertion on a social action (`EffortLevel`: very low / low / medium / high / extreme), forwarded at dispatch. It is a check-roll modifier and charges the initiator social fatigue — orthogonal to a technique's power levers. Accumulated social fatigue feeds back as a penalty on subsequent social check rolls (#2241): a character who has flirted several times in a scene sees their composure fatigue rise, penalizing later rolls.
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

**Pre-scene capture** (#3069 sub-item 4):
Folding a room's prior unattached (`scene=None`) poses into a scene at the moment it starts (`capture_prescene_interactions`), so lead-in RP that happened before anyone remembered to hit "Start Scene" isn't lost from the persisted log. A present pose's author attaches immediately; an absent author's poses stay unattached pending a `PrecaptureConsentRequest`.
_Avoid_: retroactive attach, backfill (this is a one-time scene-start sweep, not a data migration or periodic job)

**Precapture consent** (#3069 sub-item 4):
The explicit opt-in a non-member author must give before their prior poses join a scene they weren't part of at start — one `PrecaptureConsentRequest` per (scene, account), reusing `SceneActionRequest`'s `ActionRequestStatus` vocabulary. Rides the generic telnet offer registry (`accept precapture` / `decline precapture`) and a dedicated web inbox; never exposes the candidate poses to anyone but the requester.
_Avoid_: retroactive consent, backfill approval

**Precapture truncation**:
The scene starter's (or staff's) "start scene from here" cutoff control — detaches (`scene=None`, never deletes) every pre-scene-captured pose before a chosen one. Distinguishes captured poses from live ones purely by `timestamp < scene.date_started`; no separate flag exists, and a live in-scene pose can never be truncated.
_Avoid_: trim, prune, delete (truncation only detaches; the interaction row survives)

**Perception Axis** (#2997):
One of three genuinely different answers to "who perceives what is real" — see
`docs/systems/scenes.md`'s "Perception & altered reality" section for the full
taxonomy. Room-broadcast membership exclusion (Axis 1 — `_dreamside_occupants` is
this app's only current consumer, registered from `flows/service_functions
/communication.py`) is deliberately kept separate from per-viewer content
shape/tiering on a recorded event (Axis 2 — cast concealment's ADR-0170 snapshot,
language/persona-display's ADR-0214 live recompute) and downstream read-time feed
filtering (Axis 3 — this app's own Mute/`InteractionQuerySet.visible_to`/Block).
Root cross-app entry: root `AGENT_GLOSSARY_MAP.md`'s "Perception" section.
_Avoid_: perception layer, visibility mode.

**Boon** (#2540):
A structured social ask — "ask a target for a thing, backed by a social roll" — riding `SceneActionRequest` 1:1 as its payload (`kind`, `amount`, `item_instance`, `deed_text`, `material_category`). Four ask flavors share one payload and one resolver: `boon`/`boon_con`/`boon_charm`/`boon_menace` (plain, Con, Seduction, Intimidation checks respectively). A granted Boon fulfills via kind-specific mechanics (money transfer, item hand-over, vault withdraw, material bucket credit, or RP-only for a deed) and permanently costs the target's affection for the asker, stacking per granted ask. See Item Pointer, Material Boon, Standing-Gap Shift below.
_Avoid_: favor, request (Boon names the specific structured-ask model; a plain conversational request is not a Boon unless it rides this payload)

**Item Pointer** (#2540 slice 3):
Prior in-fiction knowledge that a specific item (or its template) exists — a discovered `Clue` with `target_kind=ITEM`, a known `CodexEntry`, or known `SecretKnowledge`, tested via `character_has_item_pointer`. A held-item or vault-item Boon ask requires the asker to hold a pointer to the named item; the check is exact (the item itself or its unpinned template), never a browse of anyone's actual holdings — the asker's ask window is bounded by what they know, not what exists.
_Avoid_: inventory visibility, item awareness, knowledge flag (the term names the FK-backed knowledge link specifically, not a generic "has seen it" state)

**Material Boon** (#2540 slice 3):
A `Boon` of `kind=MATERIAL`: an ask for a crafting-equivalence class of bulk material (a `MaterialCategory`) at a relative sum tier (MINOR/FAIR/GREAT, reusing money's vocabulary), rather than a named item or coin. The category list offered is the full public catalog, never filtered by the target's actual stock (a filtered list would leak wealth OOC) — a well-formed ask against an empty bucket is instead honestly refused at submit time (`BoonUnavailable`, a 200 `{boon_refused: true}`, not an error), with no roll, no consent burn, no affection drain. The granted amount is computed fresh at fulfillment (a tier percentage of the target's bucket at that moment), never frozen at ask time like money's amount. See ADR-0235.
_Avoid_: material request, bulk gift (Material Boon specifically names this kind's honest-refusal ask/fulfill shape)

**Standing-Gap Shift** (Audacity Shift, #2540 slice 3):
The additional NPC-only difficulty tier(s) a Boon ask picks up when the asker's standing sits well below the target's (`npc_boon_tier_shift`'s rank-gap term, banded via `RANK_GAP_TIER_BANDS`) — asking a much higher-standing NPC for a boon is harder than asking a peer or someone beneath you; punching down never adds a tier. Applies to dial 2's NPC band only — a piloted (player-controlled) target's own chosen difficulty is never band-shifted by the asker's standing.
_Avoid_: standing penalty, rank check (the shift only ever adds difficulty tiers on NPC-target boon asks; it is not a general standing gate)

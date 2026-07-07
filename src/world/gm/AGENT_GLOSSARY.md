# GM glossary

**GM / Storyteller**:
A player approved to run stories for others, identified by a `GMProfile` and a trust/permission `GMLevel`. The canonical term throughout the codebase is "GM"; a Lead GM is the GM assigned to and authoring a given story.
_Avoid_: Storyteller, Dungeon Master, DM, game master.

**GMProfile**:
A player's GM identity — one per account, carrying their `GMLevel`, approval date, and approver. Created when a `GMApplication` is approved; GM-level permission checks query this model.
_Avoid_: GM account, GM record.

**GMTable**:
A GM's working group: a named set of players (via their personas) engaging with a set of stories, with an ACTIVE/ARCHIVED lifecycle. The unit that owns GROUP-scope story progress and anchors Lead-GM permission checks.
_Avoid_: party, group, campaign.

**GMTableMembership**:
A player's presence at a `GMTable`, pinned to a specific `Persona` (never a temporary mask) rather than to a CharacterSheet. Supports soft-leave via `left_at` so membership history outlives a persona, with one active membership per (table, persona); it is not a privacy mechanism, since the underlying character stays walkable.
_Avoid_: seat, table member, participant.

**Assistant GM (AGM)**:
A GM (`GMProfile`) who has claimed a single `agm_eligible` beat session to run, seeing only that beat's internal description plus the Lead GM's framing — not the rest of the story. The claim lifecycle lives in the stories app as `AssistantGMClaim` (REQUESTED → APPROVED/REJECTED/CANCELLED → COMPLETED); AGM is a per-beat role, not a separate identity from GMProfile.
_Avoid_: co-GM, helper GM, sub-GM.

**GM Level**:
A GM's trust tier (`GMProfile.level`, the `GMLevel` enum: STARTING/JUNIOR/GM/EXPERIENCED/SENIOR), canonical since #2000 (ADR-0097) — the single source of GM trust; supersedes the dead `PlayerTrust.gm_trust_level` field, which was removed. Ordered via `GM_LEVEL_ORDER`/`gm_level_index`; consumed by `stories.BeatSerializer`'s risk gate, `stories.StakeSerializer`'s custom-stakes gate, and `combat.StakesLevelRequirement.minimum_gm_level`.
_Avoid_: GM trust level (on PlayerTrust — that field is gone), trust score.

**Level Cap**:
`GMLevelCap` — one staff-tunable row per `GMLevel`, holding what a GM at that level may author: `max_beat_risk` (the highest `RenownRisk` beat tier), `allow_custom_stakes` (template-null Stakes), `allow_global_scope_authoring`. Seeded via `world.gm.factories.seed_default_gm_level_caps`. A GM with no `GMLevelCap` row (or no `GMProfile`) falls back to the most restrictive read (`RenownRisk.NONE` / `False`).
_Avoid_: trust cap, permission cap.

**Promotion**:
A staff-only, audited change to a GM's `level` via `world.gm.services.promote_gm` (covers both promotion and demotion — the function name is the historical verb). Every call writes a `GMLevelChange` row (`old_level`, `new_level`, `changed_by`, `reason`); nothing else may write `GMProfile.level`. Reachable via `GMProfileViewSet.promote` (`IsAdminUser`) or telnet `gmtrust promote <account>=<level> reason=<why>`.
_Avoid_: demotion (as a separate concept — same service, same audit row), level change (ambiguous with the `GMLevelChange` model name — use "promotion" for the act).

**Evidence Summary**:
`GMEvidenceSummary` (`world.gm.types`) — the read model `gm_evidence_summary(profile)` builds for a staff reviewer deciding on a promotion: stories currently running, beats completed by risk tier, feedback by trust category (`CategoryFeedback`), and the GM's `GMLevelChange` audit trail. Reachable via `GMProfileViewSet.evidence` (`IsAdminUser`) or telnet `gmtrust evidence <account>`.
_Avoid_: track record (informal; use the type name in code/docs), review packet.

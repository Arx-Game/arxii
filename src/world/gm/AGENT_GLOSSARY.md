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

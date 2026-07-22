# Sheet updates are player-proposed, GM-vetoed, never content-prompting — and history is never lost

Arx 1's +request/+actions/+investigations systems collapsed staff under open-ended prompts to
generate story on demand; the fear of recreating that pushed Arx II toward full automation, which
turned out to be more cumbersome than a simple judgment call for story-driven sheet changes
(#2607 → #2624 → #2631). The ruling inverts each property of the failed shape rather than
avoiding requests altogether: a `gm.TableUpdateRequest` is always a **concrete proposed change**
(a full background rewrite, a specific distinction add/remove) with a `Reason:`, answered
yes/no — the GM judges story-fit and never authors content (a request that would need content
generated is a story hook, not a request); it routes to the **table GM** via `GMTableMembership`
(joining a table is a GM taking responsibility for a player's story — **no table, no requests**,
deliberately: a tableless sheet has no story event to reflect); GMs approve story-consistency
but cannot ratify new world facts through prose approval (lore stays with staff, per the GM
leash); cost follows **benefit direction only** (gaining a benefit or shedding a flaw costs XP;
detriments and story-reason losses are free); and every write to a versioned profile field
snapshots into `character_sheets.ProfileTextVersion` (era + IC-date stamped) — Arx 1
permanently lost original backgrounds and descriptions to overwrites, so no write path may
skip `update_profile_text`. Rejected alternatives: a global staff request queue (recreates the
Arx 1 failure), applying distinction changes at GM approval (the player must control when XP is
spent — approval creates a `DistinctionChangeAuthorization` instead), and diff-based version
storage (full text per version is trivially cheap at these volumes and never corrupts).

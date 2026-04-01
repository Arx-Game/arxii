# Scene XP, Voting, and Random Scene Design

**Date:** 2026-03-31
**Status:** Approved design, ready for implementation

## Overview

XP rewards players for creating content other players enjoy. This design covers three
interconnected systems that turn RP activity into progression: a voting system for
recognizing good writing, Random Scene bounties for encouraging new connections, and
First Impression XP for relationship building.

## Design Principles

- XP rewards the IC actions that create content for others
- Voting is private and ephemeral in feel but persistent for analytics
- Scarcity of votes makes them meaningful; generous players must choose
- No system should feel punishing for playing later in the week
- No system should be trivially gameable by multi-accounters (vote history enables detection)

---

## 1. Vote System

### Budget

7 votes per week + 1 bonus vote per scene attended that week. Unvoting returns
the vote to the budget. Votes lock when weekly cron processes them.

### Votable Targets

- **Interaction** — a specific pose, in a scene or organic RP (no scene required)
- **Scene participation** — a participant persona in an ephemeral scene (no recorded interactions)
- **Journal entry** — a journal post

### Toggle Behavior

Voting is a toggle: vote to spend a vote, unvote to reclaim it. Voters can see
their own vote state (filled/unfilled icon). No one else sees anything — not the
author, not other players, not staff (except via analytics queries).

### Data Model

**`WeeklyVoteBudget`** — one row per account per week:
- `account` (FK), `week_start` (date)
- `base_votes` (default 7), `scene_bonus_votes` (int), `votes_spent` (int)
- Remaining = base + bonus - spent

**`WeeklyVote`** — one row per vote cast, persistent with processed flag:
- `voter` (FK account), `week_start` (date)
- `target_type` (TextChoices: interaction / scene_participation / journal)
- `target_id` (integer, not a FK — avoids cascade complexity)
- `author_account` (FK account, denormalized for fast aggregation)
- `processed` (boolean, default false)
- Unique constraint on (voter, target_type, target_id, week_start)

After cron processes votes, `processed` is set to true. Unvoting is blocked
on processed rows. Vote history is retained permanently for staff analytics
(multi-account detection, voting pattern analysis, XP curve tuning).

### Memorable Poses

Integer `vote_count` field on Interaction model. Incremented on vote, decremented
on unvote. Weekly cron reads top 3 interactions per scene by vote_count:
- 1st place: 3 XP to author
- 2nd place: 2 XP to author
- 3rd place: 1 XP to author
- Ties: all tied authors receive the higher tier's XP (e.g., 3-way tie for 1st = 3 XP each)

After processing, vote_count is reset to 0.

Only applies to scenes with recorded interactions (not ephemeral, not organic RP).

### Weekly XP Calculation (Cron)

1. Count `DISTINCT voter` per `author_account` from unprocessed `WeeklyVote` rows
2. Apply diminishing returns curve:
   - ~5 XP for 1 unique voter
   - 1:1 ratio around 10-20 voters
   - Steep dropoff after ~20
   - Cap around ~50 XP even for hundreds of voters
   - Exact curve TBD via tuning with real data
3. Award XP to each author
4. Process Memorable Poses per scene (top 3 by vote_count, award bonus XP)
5. Mark all `WeeklyVote` rows as `processed = true`
6. Reset `WeeklyVoteBudget` rows (base=7, bonus=0, spent=0)
7. Reset all Interaction `vote_count` to 0

---

## 2. Random Scene (Weekly RP Bounties)

### Generation (Weekly Cron)

Each active player receives 5 target characters:
- **Slots 1-3:** Active characters the player has never had a shared interaction/scene
  with. If fewer than 3 strangers exist, fill from general active pool.
- **Slots 4-5:** Active characters the player has an existing relationship with.
  If none are active, fill from general active pool.
- **All slots exclude:** Player's own characters, blocked/muted players.
- **One free reroll** per week on any single slot — replacement drawn from general
  active pool with no restriction.

### Claiming

- Player selects a target and claims
- **Auto-validated:** System checks for shared SceneParticipation or Interactions
  involving both characters' personas during the current week
- Covers recorded scenes, ephemeral scenes, and organic RP
- **Immediate XP award on claim** (not at cron):
  - 5 XP to both the claimer and the target
  - First-time bonus: +10 XP to the claimer if this is their first RS completion
    with this target ever (so claimer gets 15, target gets 5)

### Data Model

**`RandomSceneTarget`** — generated weekly:
- `account` (FK), `target_character` (FK), `week_start` (date)
- `slot_number` (1-5), `claimed` (boolean), `claimed_at` (timestamp)
- `first_time` (boolean, calculated at generation)
- `rerolled` (boolean, to enforce one-reroll limit)

**`RandomSceneCompletion`** — permanent record:
- `account` (FK), `target_character` (FK), `completed_at` (timestamp)
- Used to weight future target generation toward strangers
- Used for first-time bonus eligibility

---

## 3. First Impression

### Trigger

The first `RelationshipUpdate` with `is_first_impression=True` that a character
writes about another character. The model and `create_first_impression()` service
function already exist in the relationships app.

### Awards

- 5 XP to the target character's account
- 3 XP to the author's account
- Immediate on creation
- One-time per character pair (enforced by existing model constraints)

### Implementation

Add `award_xp()` calls inside the existing `create_first_impression()` service
function. No new models needed.

---

## 4. XP Sources Summary

| Source | XP Range | Timing | Status |
|--------|----------|--------|--------|
| Random Scene completions | 5-15 per claim (up to 5/week) | Immediate | New |
| First Impressions | 3 (author) / 5 (target) | Immediate | Wire-up |
| Journals | 5/2/1 decreasing per week | Immediate | Done |
| Votes received | ~5-50 depending on voter count | Weekly cron | New |
| Memorable Poses | 3/2/1 for top 3 (ties get higher tier) | Weekly cron | New |
| Kudos to XP conversion | Variable | On player claim | Done |
| GM compensation | TBD | TBD | Not designed |

---

## 5. Interaction with Existing Systems

### InteractionFavorite (existing)
Remains as a separate personal bookmark system with no gameplay impact. Completely
independent from voting. Favorites are permanent; votes are weekly.

### InteractionReaction (existing)
Bridge model noted as temporary. Can coexist with voting — reactions are visible
social feedback (emoji), votes are invisible progression input. May be deprecated
later if voting subsumes the use case.

### Scene Completion Flow
`finish_scene()` currently does nothing for progression. After this design is
implemented, scene completion should:
1. Increment `scene_bonus_votes` on the `WeeklyVoteBudget` for each participant
2. (Future) Award development points based on scene activity

### Block/Mute System
Referenced by Random Scene target generation (excluded from targets). Models for
block/mute may not exist yet — Random Scene generation should check for them when
available, with a no-op fallback if the models don't exist.

---

## 6. Staff Analytics (from persistent vote data)

Vote history enables:
- Multi-account detection (accounts that exclusively vote for each other)
- Vote distribution analysis (are votes concentrated or spread?)
- XP curve tuning (actual voter counts vs. awarded XP)
- Player engagement metrics (voting activity as a proxy for content consumption)
- Pattern anomaly detection (sudden vote spikes, coordinated voting)

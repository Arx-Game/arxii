# Scene XP, Voting, and Random Scene Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the voting system, random scene bounties, and scene completion → XP pipeline as designed in `docs/plans/2026-03-31-scene-xp-voting-design.md`.

**Architecture:** Three new model groups in the `progression` app: vote tracking (WeeklyVoteBudget, WeeklyVote), random scene (RandomSceneTarget, RandomSceneCompletion), and a `vote_count` field on Interaction. Weekly cron tasks process votes→XP and generate random scene targets. Service functions handle all business logic. Frontend gets vote toggle buttons and a random scene claiming UI.

**Tech Stack:** Django models (SharedMemoryModel), DRF ViewSets, React + React Query, existing cron registry (`world.game_clock.task_registry`)

**Key files to consult:**
- Design doc: `docs/plans/2026-03-31-scene-xp-voting-design.md`
- Existing progression services: `src/world/progression/services/awards.py`
- Cron registry: `src/world/game_clock/task_registry.py`, `src/world/game_clock/tasks.py`
- Scene models: `src/world/scenes/models.py`
- Journal models: `src/world/journals/models.py`
- Interaction model for `vote_count` field addition
- CLAUDE.md for coding standards (SharedMemoryModel, no signals, constants in constants.py, etc.)

---

## Task 1: Vote System Models

**Files:**
- Create: `src/world/progression/models/voting.py`
- Modify: `src/world/progression/models/__init__.py`
- Modify: `src/world/progression/constants.py` (create if needed)
- Modify: `src/world/scenes/models.py` (add `vote_count` to Interaction)
- Test: `src/world/progression/tests/test_vote_models.py`

**Models to create:**

`VoteTargetType` TextChoices in `src/world/progression/constants.py`:
- `INTERACTION = "interaction"`
- `SCENE_PARTICIPATION = "scene_participation"`
- `JOURNAL = "journal"`

`WeeklyVoteBudget` (SharedMemoryModel):
- `account` — FK to AccountDB
- `week_start` — DateField
- `base_votes` — PositiveIntegerField (default=7)
- `scene_bonus_votes` — PositiveIntegerField (default=0)
- `votes_spent` — PositiveIntegerField (default=0)
- Property: `votes_remaining` = base + bonus - spent
- UniqueConstraint on (account, week_start)

`WeeklyVote` (SharedMemoryModel):
- `voter` — FK to AccountDB (related_name="weekly_votes")
- `week_start` — DateField
- `target_type` — CharField (VoteTargetType choices)
- `target_id` — PositiveIntegerField (not a FK)
- `author_account` — FK to AccountDB (related_name="votes_received")
- `processed` — BooleanField (default=False)
- `created_at` — DateTimeField (auto_now_add)
- UniqueConstraint on (voter, target_type, target_id, week_start)

Add `vote_count` field to `Interaction` model:
- `vote_count` — PositiveIntegerField (default=0)

**Tests:** Create budget, create vote, test uniqueness constraint, test votes_remaining property, test processed flag blocks changes.

**Migration:** Generate after models created. Single migration for progression + separate for scenes.

**Commit message:** `feat(progression): add vote system models (WeeklyVoteBudget, WeeklyVote, Interaction.vote_count)`

---

## Task 2: Vote Service Functions

**Files:**
- Create: `src/world/progression/services/voting.py`
- Test: `src/world/progression/tests/test_vote_services.py`

**Service functions:**

`get_current_week_start()` — Returns the Monday of the current week as a date.

`get_or_create_vote_budget(account)` — Returns WeeklyVoteBudget for current week, creating with defaults if needed.

`increment_scene_bonus(account)` — Adds 1 to scene_bonus_votes for current week's budget. Called when a player joins a scene.

`cast_vote(voter_account, target_type, target_id, author_account)`:
- Check budget has votes remaining
- Check not already voted for this target this week
- Check vote is not processed
- Create WeeklyVote row
- Increment budget.votes_spent
- If target_type is INTERACTION, increment Interaction.vote_count
- Raise VoteError on failures
- Return the created WeeklyVote

`remove_vote(voter_account, target_type, target_id)`:
- Find the unprocessed WeeklyVote for this week
- Delete it
- Decrement budget.votes_spent
- If target_type is INTERACTION, decrement Interaction.vote_count
- Raise VoteError if not found or already processed

`get_vote_state(voter_account, target_type, target_id)` — Returns bool (voted or not) for current week.

`get_votes_by_voter(voter_account)` — Returns all unprocessed votes for current week (for showing toggle state in UI).

**Tests:** Budget creation, cast vote success, cast vote over budget, duplicate vote, remove vote restores budget, remove processed vote fails, vote_count increment/decrement on Interaction.

**Commit message:** `feat(progression): add vote service functions (cast, remove, budget tracking)`

---

## Task 3: Weekly Vote XP Cron Task

**Files:**
- Create: `src/world/progression/services/vote_processing.py`
- Modify: `src/world/game_clock/tasks.py` (register new task)
- Test: `src/world/progression/tests/test_vote_processing.py`

**Functions:**

`calculate_vote_xp(unique_voter_count: int) -> int`:
- Diminishing returns curve
- 1 vote → 5 XP
- 10 votes → 10 XP (1:1 zone)
- 20 votes → 20 XP
- 30 votes → 25 XP (dropoff begins)
- 50+ votes → ~35 XP
- 100+ votes → ~45 XP
- Cap at 50 XP
- Formula: Use logarithmic curve, tunable later. Start with `min(50, int(10 * log2(count + 1)))` or similar. Exact curve can be tuned with real data.

`process_memorable_poses(week_start: date)`:
- For each scene that has interactions with vote_count > 0:
  - Find top 3 interactions by vote_count
  - Handle ties: all tied at a tier get that tier's XP (3/2/1)
  - Award XP to interaction authors
  - Reset all Interaction.vote_count to 0 for that scene
- Use `Interaction.objects.filter(scene__isnull=False, vote_count__gt=0)` grouped by scene

`process_weekly_votes(week_start: date)`:
- Count DISTINCT voter per author_account from unprocessed WeeklyVote where week_start matches
- For each author, calculate XP via `calculate_vote_xp(count)` and call `award_xp()`
- Mark all WeeklyVote rows as processed=True
- Call `process_memorable_poses(week_start)`
- Reset all WeeklyVoteBudget rows for this week (base=7, bonus=0, spent=0)
- Reset ALL Interaction.vote_count to 0 (catch any stragglers)

Register in `tasks.py`:
```python
CronDefinition(
    task_key="weekly_vote_xp_processing",
    callable=weekly_vote_processing_task,
    interval=timedelta(days=7),
    description="Process weekly votes into XP awards and memorable poses",
)
```

The wrapper `weekly_vote_processing_task()` calls `process_weekly_votes(get_current_week_start())`.

**Tests:** XP curve at various vote counts, memorable poses top 3 selection, tie handling, processed flag set, budget reset, vote_count reset.

**Commit message:** `feat(progression): add weekly vote XP processing cron task`

---

## Task 4: Vote API Endpoints

**Files:**
- Create: `src/world/progression/views/voting.py`
- Create: `src/world/progression/serializers/voting.py`
- Create: `src/world/progression/filters/voting.py`
- Modify: `src/world/progression/urls.py` (add vote routes)
- Test: `src/world/progression/tests/test_vote_views.py`

**Endpoints:**

`VoteViewSet` (create + destroy + list):
- POST `/api/progression/votes/` — Cast a vote (body: target_type, target_id)
  - Derives author_account from target (interaction→persona→character→roster, journal→author→character→roster)
  - Returns vote data + remaining budget
- DELETE `/api/progression/votes/<id>/` — Remove a vote (unvote)
- GET `/api/progression/votes/` — List current week's votes for the requesting user (for toggle state)
- GET `/api/progression/votes/budget/` — Return current budget (base, bonus, spent, remaining)

**Serializers:**
- `CastVoteSerializer` — target_type, target_id (validates target exists)
- `WeeklyVoteSerializer` — id, target_type, target_id, created_at
- `VoteBudgetSerializer` — base_votes, scene_bonus_votes, votes_spent, votes_remaining

**Permissions:** IsAuthenticated for all actions.

**Tests:** Cast vote via API, unvote via API, budget endpoint, over-budget rejection, duplicate rejection.

**Commit message:** `feat(progression): add vote API endpoints (cast, unvote, budget)`

---

## Task 5: Random Scene Models

**Files:**
- Create: `src/world/progression/models/random_scene.py`
- Modify: `src/world/progression/models/__init__.py`
- Test: `src/world/progression/tests/test_random_scene_models.py`

**Models:**

`RandomSceneTarget` (SharedMemoryModel):
- `account` — FK to AccountDB (related_name="random_scene_targets")
- `target_character` — FK to ObjectDB (related_name="targeted_for_random_scene")
- `week_start` — DateField
- `slot_number` — PositiveSmallIntegerField (1-5)
- `claimed` — BooleanField (default=False)
- `claimed_at` — DateTimeField (nullable)
- `first_time` — BooleanField (calculated at generation)
- `rerolled` — BooleanField (default=False)
- UniqueConstraint on (account, week_start, slot_number)

`RandomSceneCompletion` (SharedMemoryModel):
- `account` — FK to AccountDB (related_name="random_scene_completions")
- `target_character` — FK to ObjectDB
- `completed_at` — DateTimeField (auto_now_add)
- UniqueConstraint on (account, target_character) — one completion record per pair

**Tests:** Model creation, uniqueness constraints, first_time flag.

**Commit message:** `feat(progression): add random scene models (RandomSceneTarget, RandomSceneCompletion)`

---

## Task 6: Random Scene Service Functions

**Files:**
- Create: `src/world/progression/services/random_scene.py`
- Test: `src/world/progression/tests/test_random_scene_services.py`

**Functions:**

`generate_random_scene_targets(account, week_start)`:
- Get the account's characters via RosterEntry.objects.for_account()
- For slots 1-3: find active characters the player has never shared a scene/interaction with
  - Query: exclude characters with a RandomSceneCompletion record for this account
  - Also exclude: own characters, blocked/muted (no-op if models don't exist yet)
  - If fewer than 3 strangers, fill from general active pool
- For slots 4-5: active characters with an existing CharacterRelationship
  - If none active, fill from general active pool
- Calculate `first_time` for each target
- Create 5 RandomSceneTarget rows

`generate_all_random_scene_targets(week_start)`:
- For all active accounts, call generate_random_scene_targets()
- Register as cron task (weekly)

`validate_random_scene_claim(account, target_character, week_start)`:
- Check for shared SceneParticipation in same scene this week, OR
- Check for Interactions where both characters' personas are present this week
- Return bool

`claim_random_scene(account, target_id)`:
- Find the RandomSceneTarget row
- Validate not already claimed
- Call validate_random_scene_claim()
- Award 5 XP to claimer + 5 XP to target's account
- If first_time: award extra 10 XP to claimer
- Create RandomSceneCompletion record
- Mark target as claimed
- Return claim result

`reroll_random_scene_target(account, slot_number)`:
- Check not already rerolled this week (any slot)
- Pick random active character (no restrictions except own chars + blocked)
- Replace the target in that slot
- Mark as rerolled

**Tests:** Target generation with strangers, generation with relationships, claiming with valid scene evidence, claiming with interaction evidence, first-time bonus, reroll mechanics, over-claim rejection.

**Commit message:** `feat(progression): add random scene service functions (generation, claiming, reroll)`

---

## Task 7: Random Scene Cron Task

**Files:**
- Modify: `src/world/game_clock/tasks.py` (register task)
- Test: `src/world/progression/tests/test_random_scene_services.py` (add cron wrapper test)

Register:
```python
CronDefinition(
    task_key="weekly_random_scene_generation",
    callable=weekly_random_scene_generation_task,
    interval=timedelta(days=7),
    description="Generate random scene targets for all active players",
)
```

**Commit message:** `feat(progression): register random scene generation cron task`

---

## Task 8: Random Scene API Endpoints

**Files:**
- Create: `src/world/progression/views/random_scene.py`
- Create: `src/world/progression/serializers/random_scene.py`
- Modify: `src/world/progression/urls.py`
- Test: `src/world/progression/tests/test_random_scene_views.py`

**Endpoints:**
- GET `/api/progression/random-scenes/` — List current week's targets for requesting user
- POST `/api/progression/random-scenes/<id>/claim/` — Claim a target
- POST `/api/progression/random-scenes/<id>/reroll/` — Reroll a target

**Serializers:**
- `RandomSceneTargetSerializer` — id, target_character (with name), slot_number, claimed, first_time, rerolled

**Tests:** List targets, claim success, claim without evidence, reroll, double reroll rejected.

**Commit message:** `feat(progression): add random scene API endpoints`

---

## Task 9: Scene Completion → Vote Budget

**Files:**
- Modify: `src/world/scenes/models.py` (or `src/world/scenes/services.py` if exists)
- Test: `src/world/progression/tests/test_vote_services.py` (add scene bonus test)

**Wire-up:** When a scene finishes, increment `scene_bonus_votes` on each participant's WeeklyVoteBudget. Add this to `Scene.finish_scene()` or create a new `finish_scene_with_rewards()` service function (preferred — avoid putting progression logic in the scene model).

Create `src/world/progression/services/scene_rewards.py`:

`on_scene_finished(scene)`:
- For each SceneParticipation in the scene:
  - Call `increment_scene_bonus(participation.account)`

Modify the scene completion flow (in events services and scene views) to call this after `finish_scene()`.

**Tests:** Scene finish increments vote budget for all participants.

**Commit message:** `feat(progression): increment vote budget on scene completion`

---

## Task 10: Frontend — Vote Toggle Button

**Files:**
- Create: `frontend/src/components/VoteButton.tsx`
- Create: `frontend/src/progression/voteQueries.ts`
- Modify: `frontend/src/scenes/components/InteractionItem.tsx` (or wherever interactions render)
- Modify: `frontend/src/journals/` (add vote button to journal entries)

**VoteButton component:**
- Props: targetType, targetId, initialVoted (from API)
- Shows filled/unfilled icon
- On click: POST to cast vote or DELETE to unvote
- Shows remaining budget somewhere (tooltip or nearby)
- Invalidates vote budget query on mutation

**Vote queries:**
- `fetchVoteBudget()` — GET /api/progression/votes/budget/
- `fetchMyVotes()` — GET /api/progression/votes/
- `castVote(targetType, targetId)` — POST /api/progression/votes/
- `removeVote(voteId)` — DELETE /api/progression/votes/:id/

**Integration:** Add VoteButton to interaction rendering and journal entry rendering.

**Commit message:** `feat(frontend): add vote toggle button for interactions and journals`

---

## Task 11: Frontend — Random Scene Panel

**Files:**
- Create: `frontend/src/progression/components/RandomScenePanel.tsx`
- Create: `frontend/src/progression/randomSceneQueries.ts`
- Modify: `frontend/src/progression/XpKudosPage.tsx` (or sidebar)

**RandomScenePanel component:**
- Shows 5 target cards with character name
- "Claim" button (disabled if not valid)
- "Reroll" button on one slot (disabled after use)
- First-time badge on eligible targets
- Budget display (claimed X/5)

**Queries:**
- `fetchRandomSceneTargets()` — GET /api/progression/random-scenes/
- `claimTarget(id)` — POST /api/progression/random-scenes/:id/claim/
- `rerollTarget(id)` — POST /api/progression/random-scenes/:id/reroll/

**Commit message:** `feat(frontend): add random scene panel with claim and reroll`

---

## Task 12: Update Roadmap and Documentation

**Files:**
- Modify: `docs/roadmap/character-progression.md`
- Modify: `docs/roadmap/ROADMAP.md`

Update character progression roadmap to mark completed items:
- Scene XP via voting: done
- Vote system: done
- Random scene bounties: done
- First impression XP: done
- Scene completion → vote budget: done

Note remaining items: skill development, training, path leveling, GM compensation.

**Commit message:** `docs(roadmap): update character progression with completed voting and random scene systems`

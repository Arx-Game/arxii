# Training System Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a persistent, fire-and-forget training system where characters allocate weekly AP to skill training with optional mentors, producing deterministic development point gains processed at weekly cron.

**Architecture:** TrainingAllocation model stores persistent skill+mentor+AP entries. Weekly cron processes all allocations using a formula combining self-study base, mentor skill ratio, teaching skill, and relationship tier. Integrates with existing progression, skills, action points, and relationship systems.

**Tech Stack:** Django models, existing service function patterns, `award_development_points()` from progression app, `ActionPointPool` from action_points app.

---

## Core Formula

```
base_gain = 5 × AP_spent × path_level
mentor_skill_total = mentor_skill + parent_skill + teaching_skill
student_skill_total = student_skill + parent_skill
mentor_ratio = mentor_skill_total / student_skill_total
effective_AP = AP_spent + teaching_skill
mentor_bonus = effective_AP × mentor_ratio × (relationship_tier + 1)
dev_points = base_gain + mentor_bonus
```

### Key Properties

- **Deterministic:** No check roll. Training is reliable, predictable progress.
- **Overflow carries over:** Dev points accumulate continuously. Crossing a level threshold levels up the skill and remaining points carry into the next level.
- **Cost per level:** `(level - 9) × 100` — so 10→11 = 100, 11→12 = 200, 15→16 = 600, 20→21 = 1,100.
- **X9 boundaries:** At skill 19, 29, 39, 49 the player must buy the next tier with XP. Dev points are wasted while stuck at a boundary, but training still prevents rust.
- **No mentor (null):** Only `base_gain` applies — self-study at `5 × AP × path_level`.
- **Mentor obsolescence:** As the student approaches the mentor's skill level, the ratio approaches 1.0 and mentor bonus shrinks naturally. The mentor eventually has nothing left to teach.

### Example Scenarios

**Sharlyt (path level 5) training Seduction with Victoria, 20 AP:**
- Student: persuasion 30 + seduction 10 = 40
- Mentor: persuasion 50 + seduction 50 + teaching 20 = 120
- Ratio: 120 / 40 = 3.0
- Effective AP: 20 + 20 = 40
- Relationship tier 1: (1 + 1) = 2
- Base: 5 × 20 × 5 = 500
- Mentor bonus: 40 × 3.0 × 2 = 240
- **Total: 740 dev points** — multiple level-ups in one week with a strong mentor

**Self-study, no mentor, 20 AP, path level 5:**
- Base: 5 × 20 × 5 = 500
- Mentor bonus: 0
- **Total: 500 dev points** — still significant at higher path levels

**Novice (path level 1) self-study, 20 AP:**
- Base: 5 × 20 × 1 = 100
- **Total: 100 dev points** — exactly one level (10→11)

---

## Rust System

- Skills **not** receiving dev points from **any** source in a given week accumulate rust.
- Rust per week: `character_level + 5` development points.
- Rust caps at the current level's dev cost (skill 11 → max 100, skill 15 → max 500).
- Dev points pay off rust first, then count toward advancement.
- **Rust prevention:** Any dev point source prevents rust for that skill that week — training, scene checks, missions, jobs, etc.
- Training a specialization prevents rust on both the specialization AND its parent skill.
- At X9 boundaries: dev points are wasted, but training still prevents rust.

### Example

A level 5 character ignoring a skill 15 for 10 weeks:
- 10 rust/week, capped at 500 (skill 15's dev cost = 600, so cap = 600)
- After 10 weeks: 100 rust accumulated
- To advance 15→16: must pay off 100 rust + 600 level cost = 700 dev points

---

## Training Allocation Model

### TrainingAllocation

| Field | Type | Notes |
|-------|------|-------|
| character | FK → ObjectDB | The character training |
| skill | FK → Skill | The skill being trained (nullable if specialization set) |
| specialization | FK → Specialization | The specialization being trained (nullable if skill set) |
| mentor | FK → Guise (nullable) | Null = self-study |
| ap_amount | PositiveIntegerField | AP allocated per week |

### Constraints

- Character can have multiple allocations (one per skill/specialization).
- Total AP across all allocations validated against character's weekly AP regen.
- One allocation per skill per character (unique together).
- Either `skill` or `specialization` is set, not both.
- Persists week to week until player modifies or removes.

### Behavior

- At cron: process each allocation with whatever values exist at that moment.
- Mid-week modifications take effect at next cron — no partial week tracking.
- Players can withdraw AP anytime; that week's training for that skill simply doesn't fire.

---

## Cron Processing

Weekly cron runs these steps in order:

1. **Process training allocations:**
   - For each `TrainingAllocation`, look up current skill values for student and mentor.
   - Calculate `base_gain` and `mentor_bonus` per formula.
   - Apply dev points via `award_development_points()`.
   - If at X9 boundary: points wasted, but mark skill as "active" for rust prevention.
   - Consume AP from character's `ActionPointPool`.

2. **Apply rust:**
   - For every `CharacterSkillValue` that received zero dev points from any source that week:
     - Add `character_level + 5` rust points.
     - Cap rust at the current level's dev cost.

3. **Reset weekly tracking:**
   - Clear the "received development this week" flags.

---

## Integration Points

| System | How It Connects |
|--------|----------------|
| `world.progression.services.awards` | `award_development_points()` applies dev points to skills |
| `world.action_points.models` | `ActionPointPool` — AP consumption at cron |
| `world.skills.models` | `CharacterSkillValue`, `Skill`, `Specialization` — lookups and targets |
| `world.character_sheets.models` | `Guise` — mentor FK |
| `world.relationships` | `get_relationship_tier()` — **TODO: stub returning 0 until tiers are defined** |
| `world.checks` | Scene checks that award dev points (future — see Scenes roadmap) |

---

## Out of Scope (Future Work)

- **Relationship tiers:** Calculation of tier from affection/impression values. Stub with 0 for now.
- **Scene check dev points:** Certain in-scene checks award development and prevent rust. Defined in scenes/RP tools roadmap.
- **Job system:** Weekly AP activity with its own skill gains, money, and narrative.
- **Mission dev points:** Skill gains from on-grid mission activities.
- **Cron scheduling:** The actual cron job infrastructure (daily/weekly regen + training). Training processing logic is built; wiring to cron is separate.
- **Lightweight NPC trainer guises:** Slimmed-down guise creation for dedicated trainer NPCs.
- **Training UI:** Frontend for managing allocations.

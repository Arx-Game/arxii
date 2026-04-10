# GM System

**Status:** not-started
**Depends on:** StaffJobs (prerequisite), Stories, Roster, Scenes

## Overview
The infrastructure for player GMs to run stories, manage tables of PCs, create roster characters, grant rewards, and progress through a trust-based level system. Staff coordinates the overall game with unrestricted tooling; GMs operate within level-appropriate caps.

## Key Design Points

### GM Identity
- **GMCharacter typeclass** — in-game object that can occupy rooms and interact with PCs. No vitals, not attackable, not a combat target, configurable approachability (who can start conversations). Puppetable by the GM's account.
- **StaffCharacter typeclass** — separate typeclass for staff (not a subclass of GM). Similar "can't be attacked" immunity but exists to host custom staff tooling commands (replacing Django admin workflows for most operations). Orthogonal to GM storytelling behavior.
- **NPCs are not the parent class** — regular NPCs have vitals and are attackable. GM/Staff characters are exceptions to that default, not extensions of it.

### GM Levels (five tiers + staff)
1. **Starting GM** — minimum approved, very limited scope and rewards
2. **Junior GM** — small scope, some independence
3. **GM** — normal operational level
4. **Experienced GM** — broader scope, world-impact stories allowed
5. **Senior GM** — near-staff privileges, can mentor others
6. **Staff** — above all levels, unrestricted

Progression is driven by player feedback/upvotes tied to stories run and how players received them — an upvote system tangentially related to kudos. Exact progression curves and reward caps are late design; early implementation just has the level enum and permission hooks.

### GM Applications
- Players apply to become GMs (motivations, experience, availability)
- Applications flow through the **StaffJobs** queue (not a separate review UI)
- Staff approves/denies from the shared jobs hub
- On approval: account gains a GMProfile, GM commands unlocked, abbreviated CG flow creates their GMCharacter

### GM Tables
- A **GMTable** is a container linking one GM to a set of PCs and active stories
- Table membership: PCs are assigned (primary GM responsibility), one GM owns
- PCs can participate in stories run by other GMs (storyline relationship, not table relationship)
- Lifecycle: create, rename, archive
- **Ownership transfer** — staff can reassign a table when a GM quits or idles out
- **Surrender** — a GM can voluntarily give up a story or a table
- **Idle detection** — track GM activity; staff tooling to reassign idle tables

### Roster Character Creation (GM-owned)
- GMs create new roster characters scoped to their table (gated by level)
- Created characters go through the normal roster application flow
- GM approves/denies applications to their table's roster (via their own job queue)
- **Invite codes** — GM sends an out-of-game invite code (email); new player signs up and can claim the character during registration. Crucial for recruitment — brings in players who aren't on the game at all.

### Stories (GM's role only — stories app owns itself)
The stories app is separate and large. From the GM system's perspective, we only care about GM roles and permissions on stories:
- **Primary GM** — responsible for a PC's main storyline
- **Story author** — created and owns a story
- **Story advancer** — permission to create beats/advance a story
- **Story participant** — can run sessions for but does not own

The GM system defines these role relationships; the stories app uses them for permission checks when a GM tries to create beats, schedule sessions, or resolve tasks.

### Rewards and Gating
- GMs can grant XP, items, codex entries, legend
- All capped by GM level (exact caps are late design)
- Every grant is audit-logged (who gave what to whom, when, why, which story)
- Anti-abuse tracking: per-GM/per-week caps, unusual patterns flagged to staff
- Rewards tie into existing XP/codex/kudos systems, not a new reward pipeline

### Trust and Feedback
- **Stub data model early** — just record upvotes and feedback entries
- Player feedback on stories feeds trust
- Trust feeds GM level progression
- **Progression math is late design** — the curves, thresholds, decay rates all come later
- Tangentially related to kudos system

### Staff Character and Staff Tooling
- Staff has commands to edit world state, manage GMs, override any system
- Prefer custom tooling over Django admin for day-to-day operations
- Staff character hosts these commands; Django admin is a fallback

## What Exists
- Nothing. This is a brand new system.
- **Prerequisites in place:** Roster system, Stories app (partial), Scenes, Covenants stub, Combat (for GM combat tools)

## What's Needed for MVP

### Phase 0 (prerequisite) — Staff Jobs System
- Generic job queue for all staff work (not GM-specific)
- Categories: character_application, gm_application, bug_report, harassment_report, player_complaint, player_fyi, story_escalation, trust_appeal, etc.
- Assignment, claim, status, priority, age filtering
- Existing RosterApplication flow migrated to post jobs
- **Harassment reporting is a critical safety feature** — must be ready before GM onboarding

### Phase 1 — GM Identity Foundation
- `GMCharacter` typeclass (no vitals, not attackable, puppetable)
- `StaffCharacter` typeclass (orthogonal, hosts staff tooling)
- `GMProfile` model (level, stats, approval date)
- `GMApplication` model (posts a StaffJob on creation)
- GM level TextChoices (STARTING/JUNIOR/GM/EXPERIENCED/SENIOR)
- Permission framework keyed on level
- Feedback/trust stub data model (no progression math yet)

### Phase 2 — GM Tables
- `GMTable` model (one GM owner, many PCs)
- `GMTableMembership` (PC assignment with role)
- Table lifecycle: create, surrender, archive
- Staff tools to reassign idle/quit tables to a new GM
- Idle detection tracking (no automation yet — just data)

### Phase 3 — Roster & Recruitment
- GM creates roster characters (level-gated scope)
- GM approves/denies apps to their table's roster (via job queue)
- Invite code flow for out-of-game recruitment
- Integration with existing roster application system

### Phase 4 — Reward Tooling
- Level-capped reward granting (XP, items, codex, legend)
- Audit log of all grants
- Anti-abuse caps and reporting
- Hooks into existing reward systems (no new pipeline)

### Phase 5 — Dashboards and UI
- GM dashboard — their table, stories, PCs, pending tasks
- Staff coordination view — cross-table overview leveraging StaffJob queue
- Application review UI (wrapped around StaffJob queue with filters)
- GM story management interface

## Cross-System Dependencies

- **Stories app** — needs GM role relations and permission checks added as it grows
- **Roster app** — RosterApplication migrates to post StaffJobs; GMs get scoped approval permissions
- **Scenes app** — GMCharacter needs to participate in scenes (likely works out of the box)
- **Combat app** — GM combat tools build on Phase 3's GM-gated encounter management
- **Trust system** — current stub needs fleshing out with the upvote mechanics; late design

## Notes

The GM system is safety-critical. Players complaining about harassment need to reach staff quickly and reliably. The StaffJobs system must support harassment reports as a first-class category with appropriate priority handling, even before GM work begins. This is why Phase 0 (StaffJobs) is the prerequisite — we don't want to build GM onboarding without the safety infrastructure already in place.

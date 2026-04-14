# GM System

**Status:** in-progress (Phase 1 backend complete)
**Depends on:** Staff Inbox & Player Submissions (prerequisite), Stories, Roster, Scenes

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
- Applications are their own model in the `gm` app; they show up in the **staff inbox** alongside other submission types for triage
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
- **`world.gm` app** — GMProfile, GMApplication models with factories, admin, ViewSet, filters, serializers
- **`typeclasses.gm_characters`** — GMCharacter and StaffCharacter typeclasses (combat immune, fun rejection messages)
- **Staff inbox integration** — GMApplication appears as a triage category alongside other submission types
- **Prerequisites in place:** Roster system, Stories app (partial), Scenes, Covenants stub, Combat (for GM combat tools)

## What's Needed for MVP

### Phase 0 (prerequisite) — Staff Inbox & Player Submissions
- See `staff-inbox.md` for the full design
- New `player_submissions` app with `PlayerFeedback`, `BugReport`, `PlayerReport` (stub) models
- Staff inbox aggregator that reads from those + existing `RosterApplication`
- Identity summary helper on Persona for staff context
- Account history page (staff-only)
- **PlayerReport is safety-critical** — the model and submission path exist before GM onboarding, even though the full UX design comes later

### Phase 1 — GM Identity Foundation ✅
- ✅ `GMCharacter` typeclass (extends Character, combat/targeting immune, fun rejection messages)
- ✅ `StaffCharacter` typeclass (orthogonal, same immunity, hosts future staff commands)
- ✅ `GMProfile` model (OneToOne account, level, approval tracking)
- ✅ `GMApplication` model (freeform text, staff response, staff inbox integration)
- ✅ GM level TextChoices (STARTING/JUNIOR/GM/EXPERIENCED/SENIOR)
- ✅ GMApplication ViewSet (create for players, list/review/update for staff, filters)
- ✅ Staff inbox integration (GM applications appear as triage category)
- ✅ Trust/feedback — reuses existing `PlayerTrust.gm_trust_level` from stories app
- Permission checks deferred to individual commands (each checks `GMProfile.level` as needed)

### Phase 2 — GM Tables ✅
- ✅ `GMTable` model (gm FK, name, status, lifecycle fields, archived_at)
- ✅ `GMTableMembership` (persona-pinned, soft-leave, unique-active-constraint, temporary-persona rejection)
- ✅ Service functions (create, archive, transfer_ownership, join, leave, retire-persona hook)
- ✅ ViewSets with staff/GM permission split and staff-only actions (archive, transfer_ownership)
- ✅ `last_active_at` stub on GMProfile (not yet auto-stamped)
- Remaining: story attachment (future phase when stories are wired up), frontend pages (Phase 5)

### Phase 3 — Roster & Recruitment ✅
- ✅ `Story.primary_table` FK links stories to tables (orphaned stories are legal, character falls out of default visibility)
- ✅ `CharacterDraft` extended with `is_gm_creation`, `target_table`, `story_title`, `story_description`
- ✅ `finalize_gm_character` service creates character + story + participation atomically; character goes to Available roster with no tenure
- ✅ Shared finalize helpers extracted from `finalize_character` for reuse
- ✅ `RosterEntry.objects.actively_overseen()` queryset filters for characters with active stories at active GM tables
- ✅ `gm_application_queue` service surfaces pending apps to the overseeing GM
- ✅ `approve_application_as_gm` / `deny_application_as_gm` — GM-side approval that verifies table ownership; delegates to existing `RosterApplication` flow so tenure creation + side effects stay intact
- ✅ `surrender_character_story` — GM releases a story, clearing `primary_table`
- ✅ `GMRosterInvite` model (single-use, 30-day default expiry, public or private with email match)
- ✅ Invite services: `create_invite`, `revoke_invite`, `claim_invite` with `select_for_update` for race safety
- ✅ API: `GMRosterInviteViewSet`, `GMApplicationQueueView`, `GMApplicationActionView`, `GMInviteClaimView`
- ✅ Staff continue to see applications via existing staff inbox; GM queue surfaces the same apps to the overseeing GM
- Remaining: frontend (Phase 5), email delivery for private invites (follow-up), level-gated character creation exceptions (kudo points / GM leeway — post-MVP)

### Phase 4 — Reward Tooling
- Level-capped reward granting (XP, items, codex, legend)
- Audit log of all grants
- Anti-abuse caps and reporting
- Hooks into existing reward systems (no new pipeline)

### Phase 5 — Dashboards and UI
- GM dashboard — their table, stories, PCs, pending tasks
- Staff coordination view — cross-table overview leveraging the staff inbox
- Application review UI — dedicated per-type management for GMApplication and RosterApplication
- GM story management interface

## Cross-System Dependencies

- **Stories app** — needs GM role relations and permission checks added as it grows
- **Roster app** — RosterApplication stays as-is but shows up in the staff inbox; GMs eventually get scoped approval permissions via delegation tiers
- **Scenes app** — GMCharacter needs to participate in scenes (likely works out of the box)
- **Combat app** — GM combat tools build on Phase 3's GM-gated encounter management
- **Trust system** — current stub needs fleshing out with the upvote mechanics; late design

## Notes

The GM system is safety-critical. Players need a reliable path to report problematic behavior before we open up new trust relationships (GMs have power over other players, so the stakes go up). The Staff Inbox & Player Submissions infrastructure must exist before GM onboarding — we do not want to grant players GM powers without the reporting system already in place.

Note that the full PlayerReport UX (form wording, flow, block/mute integration) is a separate design pass, deferred until we have the right context to design it delicately. The first PR establishes the data model and basic submission path.

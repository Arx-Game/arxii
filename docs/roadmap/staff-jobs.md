# Staff Jobs

**Status:** not-started
**Depends on:** None (foundational infrastructure)

## Overview
A generic queue for all work that needs staff attention. Any app can post jobs; staff and trusted players (GMs) pick from the queue, filter by category, and resolve them. Replaces ad-hoc review flows scattered across individual apps with a single unified hub.

## Why This Exists
- **Central place for "things waiting for staff"** — one queue, filterable, prioritizable, assignable
- **Safety-critical harassment reporting** — players must be able to report problematic behavior reliably. Roleplaying games are frequent targets for sexual harassment and similar issues; this must be a first-class feature, not an afterthought
- **Replaces scattered review UIs** — RosterApplication has its own approval flow; GM applications would need another; bug reports would need another. Instead: one queue, multiple job types
- **GM scoped access** — GMs see jobs relevant to their table (e.g., roster apps to their characters) through the same queue system

## Key Design Points

### Job Categories
Jobs are categorized for filtering. Initial categories:
- **character_application** — player applied for a roster character
- **gm_application** — player applied to become a GM
- **harassment_report** — player reported problematic behavior (high priority, restricted visibility)
- **player_complaint** — general complaint about another player or situation
- **player_fyi** — informational note to staff (no action required but worth knowing)
- **bug_report** — player-reported bug
- **story_escalation** — GM escalated a story decision to staff
- **trust_appeal** — player appealing a trust/permission decision

New categories added as needed.

### Job Model Fields
- `category` — TextChoices for filtering
- `title` — short summary
- `description` — full details (rich text or plain, TBD)
- `priority` — enum (low/normal/high/urgent)
- `status` — enum (open/claimed/in_progress/resolved/closed/rejected)
- `created_at`, `resolved_at`
- `created_by` — optional (some jobs are system-generated)
- `assignee` — account who claimed/was assigned the job
- `related_object` — FK to the thing the job is about (polymorphic — ContentType or discriminator-based, TBD)
- `resolution_notes` — what staff did to resolve it
- `visibility` — who can see the job (all staff, restricted for harassment reports)

### Visibility and Permissions
- Most jobs visible to all staff and senior GMs
- Harassment reports visible only to staff (not GMs) for privacy
- GMs see jobs related to their own table/characters
- Creator of a job sees their own submission

### Integration Pattern
Other apps post jobs via a service function:
```python
post_staff_job(
    category=JobCategory.CHARACTER_APPLICATION,
    title=f"Application: {character.name}",
    related_object=application,
    created_by=applicant_account,
    priority=JobPriority.NORMAL,
)
```
The resolving staff member's action on the job triggers the appropriate followup in the source app (e.g., approving a character_application job approves the underlying RosterApplication).

## What Exists
- Nothing — this is brand new
- **Existing patterns to migrate:** RosterApplication has its own flow that should be wrapped/replaced by StaffJobs

## What's Needed for MVP

### Core Models
- `StaffJob` model with fields above
- `JobCategory`, `JobStatus`, `JobPriority` TextChoices
- Service functions: `post_staff_job`, `claim_job`, `resolve_job`, `reject_job`

### Permissions
- Permission class gating by staff status and category visibility
- GM access to relevant jobs (scoped by table)
- Harassment report visibility restricted to staff

### API
- `StaffJobViewSet` with list/retrieve/claim/resolve/reject actions
- Filters: category, status, priority, assignee, age, related object type
- Pagination

### UI (Phase 2)
- Staff dashboard widget showing job counts by category
- Job list view with filters
- Job detail view with resolve/reject actions
- Quick-resolve shortcuts for common job types

### Migration of RosterApplication
- RosterApplication creates a StaffJob on submission
- Job resolution updates the application
- Legacy review endpoints either redirect to job endpoints or wrap them

### Harassment Reporting (critical)
- Accessible from anywhere in the UI (not buried)
- Low-friction submission (don't gatekeep victims)
- High priority by default
- Restricted visibility (staff only)
- Audit log of all views and actions
- Response SLA tracking (future)

## Notes

Harassment reporting is the safety feature that has to work. Everything else in the StaffJobs system can be iterated on, but the reporting flow needs to be accessible, reliable, and respectful of victim privacy from day one. This is why StaffJobs is a prerequisite for GM onboarding — we will not let players become GMs until the system for reporting abuse exists.

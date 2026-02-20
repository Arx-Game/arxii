# Character Creation System

Multi-stage character creation flow with draft persistence, CG point budgets, magic templates, and staff review workflow.

**Source:** `src/world/character_creation/`
**API Base:** `/api/character-creation/`

---

## Enums (constants.py)

```python
from world.character_creation.constants import (
    Stage,                    # ORIGIN(1) through REVIEW(11)
    StartingAreaAccessLevel,  # ALL, TRUST_REQUIRED, STAFF_ONLY
    ApplicationStatus,        # SUBMITTED, IN_REVIEW, REVISIONS_REQUESTED, APPROVED, DENIED, WITHDRAWN
    CommentType,              # MESSAGE, STATUS_CHANGE
)
```

## Types (types.py)

```python
from world.character_creation.types import (
    StatAdjustment,      # TypedDict: stat, old_display, new_display, reason
    ResonanceSource,     # Dataclass: distinction_name, value
    ProjectedResonance,  # Dataclass: resonance_id, resonance_name, total, sources
)
```

---

## Models

### Lookup Tables (SharedMemoryModel - cached)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `CGPointBudget` | Global CG point budget config | `name`, `starting_points`, `is_active`, `xp_conversion_rate` |
| `StartingArea` | Selectable origin locations | `name`, `realm` (FK), `description`, `crest_image`, `default_starting_room`, `is_active`, `sort_order`, `access_level`, `minimum_trust` |
| `Beginnings` | Worldbuilding paths per area | `name`, `starting_area` (FK), `description`, `family_known`, `allowed_species` (M2M), `starting_languages` (M2M), `societies` (M2M), `traditions` (M2M via `BeginningTradition`), `cg_point_cost`, `social_rank` |

### Template/Configuration Tables

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `BeginningTradition` | Maps traditions to beginnings with optional required distinction | `beginning`, `tradition`, `required_distinction`, `sort_order` |
| `TraditionTemplate` | Pre-fill data for Magic stage by tradition x path | `tradition`, `path`, `gift_name`, `gift_description`, `resonances` (M2M), `motif_description`, `anima_ritual_*` fields |
| `TraditionTemplateTechnique` | Default techniques within a template | `template`, `name`, `description`, `style`, `effect_type`, `sort_order` |
| `TraditionTemplateFacet` | Suggested facets within a template | `template`, `resonance`, `facet` |

### Draft State (models.Model - per-player)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `CharacterDraft` | In-progress creation state | `account`, `current_stage`, `selected_area`, `selected_beginnings`, `selected_species`, `selected_gender`, `age`, `family`, `family_member`, `selected_path`, `selected_tradition`, `height_band`, `height_inches`, `build`, `draft_data` (JSON) |
| `DraftGift` | Gift being designed in CG | `draft`, `name`, `resonances` (M2M), `description`, `source_distinction`, `max_techniques`, `bonus_resonance_value` |
| `DraftTechnique` | Technique within a draft gift | `gift`, `name`, `style`, `effect_type`, `restrictions` (M2M), `level`, `description` |
| `DraftMotif` | Motif being designed in CG | `draft` (OneToOne), `description` |
| `DraftMotifResonance` | Resonance on a draft motif | `motif`, `resonance`, `is_from_gift` |
| `DraftMotifResonanceAssociation` | Facet on a draft motif resonance | `motif_resonance`, `facet` |
| `DraftAnimaRitual` | Anima ritual being designed | `draft` (OneToOne), `stat`, `skill`, `specialization`, `resonance`, `description` |

### Application/Review

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `DraftApplication` | Review lifecycle for a draft | `draft` (OneToOne), `status`, `submitted_at`, `reviewer`, `reviewed_at`, `submission_notes`, `expires_at` |
| `DraftApplicationComment` | Comment or status change event | `application`, `author`, `text`, `comment_type`, `created_at` |

---

## CG Stages

| # | Stage | Completion Criteria |
|---|-------|-------------------|
| 1 | Origin | `selected_area` is set |
| 2 | Heritage | Beginnings, species, gender selected; family/tarot complete; CG points >= 0; species allowed by beginnings |
| 3 | Lineage | Family selected, OR familyless with tarot card |
| 4 | Distinctions | `traits_complete` flag set; CG points >= 0 |
| 5 | Path & Skills | Path and tradition selected; skills validated against budget |
| 6 | Attributes | All 9 stats present, valid range (10-50), multiples of 10, free points = 0 |
| 7 | Magic | Gifts match expected count; all gifts/motif/anima ritual valid |
| 8 | Appearance | Age, height band, height inches, build all set |
| 9 | Identity | `first_name` in draft_data |
| 10 | Final Touches | Always complete (goals are optional) |
| 11 | Review | Never "complete" -- final submission step |

---

## Key Methods

### CGPointBudget

```python
from world.character_creation.models import CGPointBudget

CGPointBudget.get_active_budget()          # Returns int (default 100)
CGPointBudget.get_active_conversion_rate() # Returns int (default 2 XP per CG point)
```

### CharacterDraft

```python
from world.character_creation.models import CharacterDraft

draft.is_expired                        # True if > 60 days inactive (staff exempt)
draft.get_starting_room()               # Beginnings override -> area default -> None
draft.get_stage_completion()            # Dict[int, bool] for all stages
draft.can_submit()                      # True if all stages (except Review) complete
draft.calculate_cg_points_remaining()   # starting_budget - total_spent
draft.calculate_final_stats()           # Dict[str, int] with bonuses applied
draft.enforce_stat_caps()               # Clamp stats after distinction changes
draft.get_expected_gift_count()         # Base 1 + bonus from distinctions
```

### DraftApplication

```python
from world.character_creation.models import DraftApplication

application.is_locked     # True when submitted or in_review
application.is_terminal   # True when approved, denied, or withdrawn
application.is_editable   # True when revisions_requested
```

---

## Service Functions

```python
from world.character_creation.services import (
    finalize_character,           # Create Character from completed draft (atomic)
    get_accessible_starting_areas,# Filter areas by account access
    can_create_character,         # Check eligibility (trust, limits)
    submit_draft_for_review,      # Create DraftApplication in SUBMITTED
    unsubmit_draft,               # Return to REVISIONS_REQUESTED
    resubmit_draft,               # Re-submit after revisions
    withdraw_draft,               # Withdraw with soft-delete expiry
    claim_application,            # Staff: claim for IN_REVIEW
    approve_application,          # Staff: approve and finalize (atomic)
    request_revisions,            # Staff: send back with feedback
    deny_application,             # Staff: deny with 14-day soft-delete
    add_application_comment,      # Add message to thread
    apply_tradition_template,     # Pre-fill magic data from template
    clear_draft_magic_data,       # Delete all magic draft data
    ensure_draft_motif,           # Sync motif resonances from gifts/distinctions
    get_projected_resonances,     # Calculate resonance totals from distinctions
)
```

---

## API Endpoints

### Lookup Data
- `GET /api/character-creation/starting-areas/` - Starting areas filtered by access level
- `GET /api/character-creation/beginnings/` - Beginnings filtered by `starting_area` and trust
- `GET /api/character-creation/species/` - Species with parent hierarchy
- `GET /api/character-creation/families/` - Playable families, filterable by `area_id`
- `GET /api/character-creation/genders/` - Gender options
- `GET /api/character-creation/pronouns/` - Pronoun sets
- `GET /api/character-creation/cg-budgets/` - Active CG point budget
- `GET /api/character-creation/paths/` - Active Prospect-stage paths
- `GET /api/character-creation/traditions/?beginning_id=X` - Traditions for a beginning
- `GET /api/character-creation/tarot-cards/` - Tarot cards for naming ritual
- `GET /api/character-creation/form-options/{species_id}/` - Form traits for a species
- `GET /api/character-creation/can-create/` - Eligibility check

### Draft Management
- `GET/POST /api/character-creation/drafts/` - List/create drafts
- `GET/PATCH/DELETE /api/character-creation/drafts/{id}/` - Read/update/delete draft
- `GET /api/character-creation/drafts/{id}/cg-points/` - CG points breakdown
- `POST /api/character-creation/drafts/{id}/select-tradition/` - Select/clear tradition
- `GET /api/character-creation/drafts/{id}/projected-resonances/` - Projected resonances

### Magic Draft Models
- `GET/POST/PATCH/DELETE` for `draft-gifts/`, `draft-techniques/`, `draft-motifs/`, `draft-motif-resonances/`, `draft-anima-rituals/`, `draft-facet-assignments/`
- `POST /api/character-creation/draft-motifs/ensure/` - Auto-create/sync motif

### Application Workflow (Player)
- `POST /api/character-creation/drafts/{id}/submit/` - Submit for review
- `POST /api/character-creation/drafts/{id}/unsubmit/` - Un-submit to resume editing
- `POST /api/character-creation/drafts/{id}/resubmit/` - Resubmit after revisions
- `POST /api/character-creation/drafts/{id}/withdraw/` - Withdraw application
- `GET /api/character-creation/drafts/{id}/application/` - Get application with thread
- `POST /api/character-creation/drafts/{id}/application/comments/` - Add comment

### Staff Review
- `GET /api/character-creation/applications/` - List all applications (filterable by status)
- `GET /api/character-creation/applications/{id}/` - Application detail with thread
- `POST /api/character-creation/applications/{id}/claim/` - Claim for review
- `POST /api/character-creation/applications/{id}/approve/` - Approve
- `POST /api/character-creation/applications/{id}/request-revisions/` - Request revisions
- `POST /api/character-creation/applications/{id}/deny/` - Deny
- `POST /api/character-creation/applications/{id}/comments/` - Staff comment
- `GET /api/character-creation/applications/pending-count/` - Pending count

### Staff-Only
- `POST /api/character-creation/drafts/{id}/add-to-roster/` - Bypass review, add to roster

---

## Admin

Registered admin classes: `StartingAreaAdmin`, `BeginningsAdmin` (with `BeginningTraditionInline`), `CharacterDraftAdmin` (stage tracking and JSON draft data), `DraftApplicationAdmin` (review status with `DraftApplicationCommentInline`), `TraditionTemplateAdmin` (with `TraditionTemplateTechniqueInline` and `TraditionTemplateFacetInline`). Draft magic models (DraftGift, DraftTechnique, DraftMotif, etc.) and CGPointBudget are not registered in admin.

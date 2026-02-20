# Codex System

Lore storage and character knowledge tracking with teaching mechanics and clue-based research.

**Source:** `src/world/codex/`
**API Base:** `/api/codex/`

---

## Enums (constants.py)

```python
from world.codex.constants import CodexKnowledgeStatus
# UNCOVERED - Character is aware of / learning this entry
# KNOWN     - Character has fully learned this entry
```

---

## Models

### Lore Structure (SharedMemoryModel - cached, rarely change)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `CodexCategory` | Top-level lore category (e.g., "Arx Lore", "Umbral Lore") | `name`, `description`, `display_order` |
| `CodexSubject` | Nestable subject within a category | `category`, `parent` (self-FK, nullable), `name`, `description`, `display_order` |
| `CodexEntry` | Individual lore entry that can be learned/taught | `subject`, `name`, `summary`, `lore_content`, `mechanics_content`, `prerequisites` (M2M self), `share_cost`, `learn_cost`, `learn_difficulty`, `learn_threshold`, `is_public`, `modifier_type` (OneToOne to `mechanics.ModifierType`) |

### Character Knowledge (models.Model - per-character instances)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `CharacterCodexKnowledge` | Tracks what a character knows or is learning | `roster_entry`, `entry`, `status` (CodexKnowledgeStatus), `learning_progress`, `learned_from` (RosterTenure), `learned_at` |
| `CodexClue` | A clue that hints at a codex entry and grants research progress | `entry`, `name`, `description`, `research_value` |
| `CharacterClueKnowledge` | Tracks which clues a character has found | `roster_entry`, `clue`, `found_at` |

### Teaching (models.Model)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `CodexTeachingOffer` | Teaching offer from one tenure to others (uses `VisibilityMixin`) | `teacher` (RosterTenure), `entry`, `pitch`, `gold_cost`, `banked_ap`, visibility fields from mixin |

### CG Grant Tables (models.Model - link CG choices to codex entries)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `BeginningsCodexGrant` | Codex entries granted by a Beginnings choice | `beginnings`, `entry` |
| `PathCodexGrant` | Codex entries granted by a Path choice | `path`, `entry` |
| `DistinctionCodexGrant` | Codex entries granted by a Distinction | `distinction`, `entry` |
| `TraditionCodexGrant` | Codex entries granted by a Tradition | `tradition`, `entry` |

---

## Key Methods

### CodexSubject

```python
# Get full breadcrumb path from category to this subject
subject.breadcrumb_path  # Returns ["Category Name", "Parent", "Child"]
```

### CodexEntry

```python
# Validation: at least one of lore_content or mechanics_content must be provided
entry.clean()  # Raises ValidationError if both are empty
```

### CharacterCodexKnowledge

```python
# Add learning progress and check for completion
completed = knowledge.add_progress(amount=5)
# Returns True if learning_progress >= entry.learn_threshold (auto-sets KNOWN status)

# Check if fully learned
knowledge.is_complete()  # True if status == KNOWN
```

### CodexTeachingOffer

```python
# Check if a learner can accept this offer
can_accept, reason = offer.can_accept(learner_tenure)
# Checks: not self-teaching, no existing knowledge, prerequisites met, AP affordable

# Accept the offer (atomic transaction)
knowledge = offer.accept(learner_tenure)
# Learner pays AP, teacher's banked AP consumed, creates UNCOVERED knowledge entry
# Raises ValueError if learner cannot accept

# Cancel offer and recover banked AP
restored_ap = offer.cancel()
# Unbanks AP to teacher's pool, deletes the offer
```

---

## API Endpoints

### Categories
- `GET /api/codex/categories/` - List all categories
- `GET /api/codex/categories/{id}/` - Get category detail
- `GET /api/codex/categories/tree/` - Categories with top-level subjects (lazy-loaded tree)

### Subjects
- `GET /api/codex/subjects/` - List subjects (filterable)
- `GET /api/codex/subjects/{id}/` - Get subject detail
- `GET /api/codex/subjects/{id}/children/` - Lazy-load children for tree expansion

**Query Parameters (subjects):**
- `category` - Filter by category ID
- `parent` - Filter by parent subject ID

### Entries
- `GET /api/codex/entries/` - List visible entries (public + character's known entries)
- `GET /api/codex/entries/{id}/` - Get entry detail (content gated by knowledge status)

**Query Parameters (entries):**
- `subject` - Filter by subject ID
- `category` - Filter by category ID (via subject)
- `search` - Search name, summary, lore/mechanics content (min 2 chars)

**Visibility Rules:**
- Anonymous users see only `is_public=True` entries
- Authenticated users see public entries + entries they have `CharacterCodexKnowledge` for
- Detail view gates `lore_content` and `mechanics_content` behind KNOWN status or `is_public`

---

## Admin

All models registered with filters, search, and inline editing:

- `CodexCategoryAdmin` - With inline subjects, shows subject count
- `CodexSubjectAdmin` - With inline entries, filterable by category
- `CodexEntryAdmin` - Full editing with fieldsets for content, costs, learning, prerequisites, and modifier type link; `filter_horizontal` for prerequisites
- `CharacterCodexKnowledgeAdmin` - Read-only debugging with status/progress fields
- `CodexClueAdmin` - Clue management with autocomplete to entries
- `CharacterClueKnowledgeAdmin` - Read-only debugging for found clues
- `CodexTeachingOfferAdmin` - Teaching offer management with visibility controls

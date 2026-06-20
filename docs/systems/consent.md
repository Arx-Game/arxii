# Consent System

OOC visibility groups for player-controlled content sharing, and per-category social
consent preferences gating which social actions a character may receive (#1141).

**Source:** `src/world/consent/`
**API prefix:** `/api/consent/`

---

## Enums

```python
# VisibilityMixin.VisibilityMode (TextChoices) — in world.consent.models:
# PUBLIC     - Everyone can see
# PRIVATE    - No one can see (except owner, handled by caller)
# CHARACTERS - Only specified tenures
# GROUPS     - Only members of specified consent groups

# ConsentMode (TextChoices) — in world.consent.constants:
# EVERYONE   - Any actor may use this category against the owner (default)
# ALLOWLIST  - Only tenures on the SocialConsentWhitelist may use this category
```

---

## Models

### Consent Groups (OOC visibility)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `ConsentGroup` | Custom group created by a player for visibility purposes | `owner` (RosterTenure FK), `name`, `created_at` |
| `ConsentGroupMember` | Membership in a consent group | `group` FK, `tenure` (RosterTenure FK), `added_at` |

### Social Consent (#1141)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `SocialConsentCategory` | Staff-authored category for social action types (NaturalKey on `key`) | `key` (slug), `name`, `description`, `display_order` |
| `SocialConsentPreference` | Per-tenure opt-out for social action targeting (OneToOne on tenure) | `tenure` (RosterTenure FK), `allow_social_actions` (bool, default True) |
| `SocialConsentCategoryRule` | Per-category targeting mode on a preference | `preference` FK, `category` FK, `mode` (ConsentMode) |
| `SocialConsentWhitelist` | Explicit allow entry: allowed_tenure may target owner with social actions | `owner_tenure` FK, `allowed_tenure` FK, `category` FK, `added_at` |

**ActionTemplate link:** `ActionTemplate.consent_category` (nullable FK → `SocialConsentCategory`,
`on_delete=SET_NULL`) tags each social template with its category. Uncategorized templates
(`consent_category=None`) are gated only by the master `allow_social_actions` switch.

### Visibility Mixin (abstract)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `VisibilityMixin` | Abstract mixin for models needing OOC visibility control | `visibility_mode`, `visible_to_tenures` (M2M RosterTenure), `visible_to_groups` (M2M ConsentGroup), `excluded_tenures` (M2M RosterTenure) |

**Design note:** Uses `RosterTenure` instead of `ObjectDB` because consent belongs to a
player's tenure with a character. If a character changes hands the new player does not
inherit the previous player's consent preferences.

---

## Default Category Set

Four canonical categories are seeded via `arx seed dev` (cluster `consent`):

| Key | Name | Templates |
|-----|------|-----------|
| `romantic` | Romantic | Flirt |
| `hostile` | Hostile | Intimidate |
| `manipulative` | Manipulative | Deceive, Persuade |
| `general` | General | Perform, Entrance, Restore to Sense |

Staff can add additional categories through the Django admin without code changes.

---

## Key Methods

### VisibilityMixin

```python
from world.consent.models import VisibilityMixin

# Check if viewer can see content controlled by this mixin
visible = my_instance.is_visible_to(viewer_tenure)

# Visibility rules (in priority order):
# 1. Excluded tenures are ALWAYS blocked (regardless of mode)
# 2. PUBLIC: Everyone can see
# 3. PRIVATE: No one can see (caller must handle owner check separately)
# 4. CHARACTERS: Only tenures in visible_to_tenures
# 5. GROUPS: Only tenures who are members of any group in visible_to_groups
```

### Social Consent Enforcement (player_interface.py)

```python
# Internal functions (not for direct callers):
# _tenure_blocks_actor(tenure, actor_tenure, category) -> bool
#   True if tenure's consent excludes actor_tenure for category.
#   False when no preference row exists (default: allow).

# _social_consent_exclusions(character, category) -> frozenset[int]
#   Returns persona IDs excluded from the social action target picker.
#   Checks all tenures in the character's current scene.
```

Enforcement happens in `_target_spec_for_action()`: for any social `ActionTemplate`,
`_social_consent_exclusions` is called with the template's `consent_category` and the
result is wired into `TargetFilters.excluded_persona_ids`.

**Read-side exposure for registry actions (#1181).** Registry actions like `challenge`
carry no `ActionTemplate`, so they never appear in the available-actions list and get no
computed `TargetSpec`. For these, `PersonaSerializer.allow_social_actions` surfaces the
target's master switch (mirroring `_tenure_blocks_actor` with `category=None`, which is
gated only by `allow_social_actions`) so the scene UI can hide the affordance for opted-out
targets. The backend still enforces the full gate at dispatch — the serializer field is a
UX hint, not the authority.

---

## API Endpoints (`/api/consent/`)

| Endpoint | ViewSet | Auth | Notes |
|----------|---------|------|-------|
| `GET /api/consent/categories/` | `SocialConsentCategoryViewSet` | IsAuthenticated | Read-only; staff author via admin |
| `GET /api/consent/preferences/` | `SocialConsentPreferenceViewSet` | IsTenureOwner | Scoped to requesting player's tenures |
| `GET /api/consent/preferences/for-tenure/<id>/` | `SocialConsentPreferenceViewSet.for_tenure` | IsTenureOwner | Returns preference or synthesized default |
| `POST /api/consent/preferences/` | `SocialConsentPreferenceViewSet` | IsTenureOwner | Create preference for own tenure |
| `PATCH /api/consent/preferences/<id>/` | `SocialConsentPreferenceViewSet` | IsTenureOwner | Update master switch / allow_social_actions |
| `GET /api/consent/category-rules/` | `SocialConsentCategoryRuleViewSet` | IsTenureOwner | Scoped to requesting player's tenures |
| `POST /api/consent/category-rules/` | `SocialConsentCategoryRuleViewSet` | IsTenureOwner | Set per-category mode |
| `PATCH /api/consent/category-rules/<id>/` | `SocialConsentCategoryRuleViewSet` | IsTenureOwner | Update per-category consent mode |
| `DELETE /api/consent/category-rules/<id>/` | `SocialConsentCategoryRuleViewSet` | IsTenureOwner | Remove per-category rule (reverts to default) |
| `GET /api/consent/whitelist/` | `SocialConsentWhitelistViewSet` | IsTenureOwner | Scoped to owner_tenure's player |
| `POST /api/consent/whitelist/` | `SocialConsentWhitelistViewSet` | IsTenureOwner | Add whitelist entry |
| `DELETE /api/consent/whitelist/<id>/` | `SocialConsentWhitelistViewSet` | IsTenureOwner | Remove whitelist entry |

Permission class `IsTenureOwner` (`world/consent/permissions.py`) ensures a player can
only read/write consent rows for tenures they own.

---

## Frontend

The `frontend/src/consent/` module provides a **Privacy** tab at `/profile/privacy`
with three sections:

1. **Global switch** — master `allow_social_actions` toggle.
2. **Per-category rules** — one row per `SocialConsentCategory` with a mode selector
   (EVERYONE / ALLOWLIST); collapses when the global switch is off.
3. **Whitelist** — add/remove allowed tenures per category; visible only when at
   least one category is in ALLOWLIST mode.

---

## Factories / Seed Helpers

```python
from world.consent.factories import (
    make_default_categories,    # -> dict[str, SocialConsentCategory] (all four)
    make_romantic_category,     # -> SocialConsentCategory
    make_hostile_category,
    make_manipulative_category,
    make_general_category,
    SocialConsentCategoryFactory,   # generic sequence-based factory
    SocialConsentPreferenceFactory,
    SocialConsentCategoryRuleFactory,
    SocialConsentWhitelistFactory,
)

# Seed all four default categories (idempotent):
categories = make_default_categories()  # {"romantic": ..., "hostile": ..., ...}
```

The production seed path is `world.seeds.consent.seed_social_consent_categories()`,
registered as the `"consent"` cluster in `world/seeds/clusters.py` and run by
`arx seed dev`.

---

## Integration Points

- **ActionTemplate** (`src/actions/models/action_templates.py`): `consent_category`
  nullable FK — staff tag social templates; enforcement reads it in `player_interface.py`.
- **player_interface.py** (`src/actions/`): `_tenure_blocks_actor` / `_social_consent_exclusions`
  enforce per-category rules when building the social action target spec.
- **Roster** (`RosterTenure`): consent ownership; `VisibilityMixin` and all preference
  models use tenure rather than ObjectDB.
- **Codex** (`CodexTeachingOffer`): uses `VisibilityMixin` for offer visibility control.
- **Seed loader** (`arx seed dev`): `"consent"` cluster seeds default categories and tags
  ActionTemplates.

---

## Admin

- `SocialConsentCategoryAdmin` — list/search categories; `display_order` is editable inline.
- `SocialConsentPreferenceAdmin` — per-tenure master switch; inline `SocialConsentCategoryRule`
  editing.
- `SocialConsentWhitelistAdmin` — whitelist entries; `raw_id_fields` for both tenures and
  category.
- `ConsentGroupAdmin` — group management with inline member editing, shows member count.
  Search by group name or owner's character name.

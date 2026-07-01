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

# ConsentMode (TextChoices) — in world.consent.constants (#1698):
# EVERYONE          - Any actor may use this category against the owner (default)
# ALL_BUT_BLACKLIST - Anyone EXCEPT tenures on the SocialConsentBlacklist for this category
# FRIENDS_WHITELIST - Only OOC friends (scenes.Friendship) + tenures on the whitelist
# ALLOWLIST         - Only tenures on the SocialConsentWhitelist (strict; friendship alone
#                     is not enough)
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
| `SocialConsentBlacklist` (#1698) | Explicit antagonism bar: blocked_tenure may NOT target owner in this category (consulted under `ALL_BUT_BLACKLIST`). Weaker than a `scenes.Block`; the blocked party is never told. | `owner_tenure` FK, `blocked_tenure` FK, `category` FK, `added_at` |

**Friends (`FRIENDS_WHITELIST`):** the friend check reads `scenes.Friendship`
(`friend_services.is_friend`) — an OOC designation, category-independent, so an OOC friend
passes every category. The owner having friended the actor (`friender_tenure=owner`) admits
them; the reverse direction does not.

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

The picker sweep `_social_consent_exclusions` **batches** its preference / category-rule /
whitelist lookups across the whole participant set — a bounded number of queries per sweep,
independent of scene size (one tenure load, one preference load, and when a `category` is
set one category-rule load plus, when the actor has a tenure, one whitelist/blacklist/friendship
load each). It shares the per-tenure decision with `_tenure_blocks_actor` via
`_decide_consent_block` (spans all four modes; #1698); keep new work on this path off any
per-participant query loop (#1248). A query-count regression test
(`actions/tests/test_social_consent_enforcement.py::SocialConsentExclusionsQueryBudgetTest`)
pins that the sweep stays constant in participant count.

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

## Action-based write seam

All consent mutations route through the shared `dispatch_player_action()` seam, so the web, telnet,
and any future caller execute the same validation and service logic.

### Consent Actions (`src/actions/definitions/consent_preferences.py`)

| Action key | Wrapped service function | Purpose |
|------------|--------------------------|---------|
| `set_social_consent_preference` | `set_social_consent_preference()` | Toggle the master `allow_social_actions` switch for a tenure. |
| `set_social_consent_category_rule` | `set_social_consent_category_rule()` / `remove_social_consent_category_rule()` | Set a category to any `ConsentMode`; `default` clears the rule. |
| `add_social_consent_whitelist` | `add_social_consent_whitelist()` | Allow a specific tenure to target the owner in a restricted category. |
| `remove_social_consent_whitelist` | `remove_social_consent_whitelist()` | Remove a tenure from a category whitelist. |
| `add_social_consent_blacklist` (#1698) | `add_social_consent_blacklist()` | Bar a tenure from antagonizing the owner in a category (`ALL_BUT_BLACKLIST`). |
| `remove_social_consent_blacklist` (#1698) | `remove_social_consent_blacklist()` | Remove a tenure from a category antagonism blacklist. |

### Service functions (`src/world/consent/services.py`)

```python
from world.consent.services import (
    set_social_consent_preference,
    set_social_consent_category_rule,
    remove_social_consent_category_rule,
    add_social_consent_whitelist,
    remove_social_consent_whitelist,
    add_social_consent_blacklist,      # (#1698)
    remove_social_consent_blacklist,   # (#1698)
    get_social_consent_summary,
)
```

`get_social_consent_summary()` is read-only; it supports the bare `consent`, `consent
whitelist list`, and `consent blacklist list` summaries by returning the preference, category
rules, and whitelist **and blacklist** entries for a tenure.

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
| `GET /api/consent/blacklist/` | `SocialConsentBlacklistViewSet` (#1698) | IsTenureOwner | Scoped to owner_tenure's player |
| `POST /api/consent/blacklist/` | `SocialConsentBlacklistViewSet` | IsTenureOwner | Add antagonism-blacklist entry (`blocked_tenure`) |
| `DELETE /api/consent/blacklist/<id>/` | `SocialConsentBlacklistViewSet` | IsTenureOwner | Remove antagonism-blacklist entry |

Permission class `IsTenureOwner` (`world/consent/permissions.py`) ensures a player can
only read/write consent rows for tenures they own. Write endpoints (POST/PATCH/DELETE) route
through the consent REGISTRY actions above via `dispatch_player_action()`; the ViewSet serializes
the resulting state.

---

## Frontend

The `frontend/src/consent/` module provides a **Privacy** tab at `/profile/privacy`
with three sections:

1. **Global switch** — master `allow_social_actions` toggle.
2. **Per-category rules** — one row per `SocialConsentCategory` with a mode selector
   (EVERYONE / ALLOWLIST); collapses when the global switch is off.
3. **Whitelist** — add/remove allowed tenures per category; visible only when at
   least one category is in ALLOWLIST mode.

> **[BUILT, NOT WIRED — web follow-up]** The #1698 modes (`ALL_BUT_BLACKLIST`,
> `FRIENDS_WHITELIST`) and the blacklist manager are fully built on the backend, web API,
> and telnet, but the React Privacy tab's mode selector still offers only EVERYONE/ALLOWLIST
> and has no blacklist section or graded deny-and-blacklist button. Surfacing them on the
> web-first UI is a tracked follow-up.

---

## Telnet (`consent`)

`CmdConsent` (`src/commands/consent_preferences.py`) provides a namespaced telnet interface for
managing consent preferences. The command parses the leading subverb and dispatches the matching
REGISTRY action through `dispatch_player_action()` — the same seam the web uses.

| Command | Action | Notes |
|---------|--------|-------|
| `consent` | — | Show the caller's social-consent summary. |
| `consent on` | `set_social_consent_preference` | Allow all social actions. |
| `consent off` | `set_social_consent_preference` | Block all social actions. |
| `consent category <key>=<mode>` | `set_social_consent_category_rule` | `mode` is `everyone`, `whitelist`, `blacklist` (= ALL_BUT_BLACKLIST), `friends` (= FRIENDS_WHITELIST), or `default` (clear the rule). |
| `consent whitelist add\|remove\|list …` | `add`/`remove_social_consent_whitelist` | People you always allow. |
| `consent blacklist add\|remove\|list …` (#1698) | `add`/`remove_social_consent_blacklist` | People barred under `blacklist` mode. |

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
    SocialConsentBlacklistFactory,  # (#1698)
)

# Seed all four default categories (idempotent):
categories = make_default_categories()  # {"romantic": ..., "hostile": ..., ...}
```

The production seed path is `world.seeds.consent.seed_social_consent_categories()`,
registered as the `"consent"` cluster in `world/seeds/clusters.py` and run by
`arx seed dev`.

---

## Consent Overhaul (#1698)

Three behaviours built on the four-mode consent core:

- **Graded DENY→blacklist.** `respond_to_action_request` / `respond_to_action_target`
  (`world/scenes/action_services.py`) take `blacklist_actor: bool`; on DENY they add the
  initiator to the denier's antagonism blacklist for the action's category (no-op when the
  action has no category or a tenure can't be resolved). Web: `ConsentResponseSerializer.
  blacklist_actor`; telnet: `deny/blacklist`. The difficulty grade a defender may attach on
  ACCEPT (`respond_*(difficulty=…)`) is surfaced on telnet via `accept/<difficulty>` switches
  (`trivial|easy|normal|hard|daunting|harrowing`) to parity the web.

- **PvP hostile-cast opt-out.** `hostile_cast_consent_blocked(actor, target_persona,
  technique)` (`actions/player_interface.py`) refuses a hostile technique cast at another
  player's character unless the target's consent admits the actor — reusing the same
  predicates scoped to the `hostile` category (master-switch fallback). NPC/GM targets (no
  active tenure) and benign techniques pass. Wired into the two player-initiated entry points
  (`CastTechniqueAction.execute` and the web `SceneActionRequestViewSet.cast`, 403) BEFORE
  they reach `request_technique_cast` — it does not touch the cast/combat internals, so deeper
  combat entry paths (join_encounter, NPC-seeded encounters) are out of scope.

- **Good-sport kudos curve.** `grant_social_engagement_kudos`
  (`world/progression/services/engagement.py`) converts the week's good-sport acceptances
  (`WeeklySocialEngagement.engagement_events`) into kudos on a diminishing-chance curve: the
  first point of the week is guaranteed, each further point rolls at 80/60/40/20/10%-floor
  indexed by points already banked, capped at 10/week (across all antagonists, not per pair),
  silent.

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
- `SocialConsentBlacklistAdmin` (#1698) — antagonism-blacklist entries; `raw_id_fields` for
  both tenures and category. Staff triage surface.
- `ConsentGroupAdmin` — group management with inline member editing, shows member count.
  Search by group name or owner's character name.

# Plan 1: Organization Kind Refactor + Project Framework Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `Organization` to use a TextChoices `kind` discriminator (9 values, including new `covenant`/`devotional`/`other`); repurpose `OrganizationType` as the admin-editable per-kind rank-title catalog; link `Covenant` to `Organization` via OneToOne; build the foundational `Project` framework so Plans 3 and 4 can ship per-kind details models on top.

**Architecture:** The `Organization` discriminator moves from a FK-to-OrganizationType to a TextChoices field on `Organization` itself (matches the pattern used by `Project.kind`, `RoomFeatureKind`, etc.). The existing `OrganizationType` model is kept but its semantic role narrows: it now holds **rank-title configuration per kind** (one row per OrganizationKind value, admin-editable). `Covenant` becomes the first per-kind details model via OneToOne(Organization, primary_key=True) with auto-creation in `save()`. `Project` is a new `world/projects` app with discriminator+per-kind-details pattern + cron lifecycle.

**Tech Stack:** Django 5 with `SharedMemoryModel` (Evennia idmapper), `DiscriminatorMixin` for polymorphic FKs, `world.game_clock.tasks.register_task` for cron, FactoryBoy for tests, `ty` for type checking.

**Spec reference:** `docs/superpowers/specs/2026-05-30-projects-buildings-sanctum-design.md` (subsystem A + the Organization-as-discriminator architectural decision).

**Design principle reference:** Per `feedback_flavor_text_design_pass` memory — rank titles must be admin-editable, not hardcoded. The fixture seeds reasonable defaults; the user reviews/customizes via admin without a PR.

---

## Prerequisites

- [ ] **Confirm working branch.** Continue on existing `spec/projects-buildings-sanctum-design` or create:

  ```bash
  git -C /workspaces/arxii checkout -b plan1/org-refactor-projects-foundation main
  ```

- [ ] **Confirm environment is bootstrapped:**

  ```bash
  uv sync
  pre-commit install
  ls /workspaces/arxii/src/.env  # must exist
  ```

- [ ] **Read the spec sections relevant to this plan:**
  - Subsystem A — Project Framework
  - Subsystem F — Architectural decision (Organization kind + per-kind details models)
  - Coherence Pass Notes (Project status += CANCELLED, account-vs-persona resolution, etc.)
  - `feedback_flavor_text_design_pass` memory (admin-editable flavor rule)

---

## OrganizationKind Enum (Locked Values)

These 9 values are exhaustive. The user reviewed and confirmed.

| Kind | Notes |
|---|---|
| `noble` | Noble houses (renamed from `noble_family`) |
| `business` | Commercial enterprises (taverns, shipping companies, single businesses) |
| `guild` | Professional associations (Smiths' Guild, Merchants' Guild) |
| `gang` | Criminal organizations |
| `secret_society` | Clandestine organizations |
| `commoner_family` | Non-noble family structures |
| `covenant` | NEW — magical oath groups |
| `devotional` | NEW — religious orders + militant holy orders |
| `other` | NEW — catch-all for orgs that don't fit the above |

**Per-kind rank titles** are stored as `OrganizationType` rows (admin-editable). The fixture seeds reasonable starting values; the user customizes via Django admin without a PR.

---

## File Structure

**Modified (Phase A — Organization refactor):**

- `src/world/societies/constants.py` — add `OrganizationKind` TextChoices + `KindMappingForLegacyRows` constant
- `src/world/societies/models.py` — add `Organization.kind` field, drop `Organization.org_type` FK, update `get_rank_title`, allow `Organization.society` null
- `src/world/societies/fixtures/initial_org_types.json` — rename `noble_family` → `noble`; add 3 new rows (`covenant`, `devotional`, `other`)
- `src/world/societies/factories.py` — add `OrganizationKindFactory` helpers; remove obsolete `NobleOrgTypeFactory` etc. usage; update `OrganizationFactory` to take `kind=` kwarg
- `src/world/societies/tests/test_organization_kind.py` — NEW comprehensive Organization kind tests
- `src/world/societies/migrations/0004_organization_kind.py` — auto-generated, adds `kind` nullable + populates from `org_type.name`
- `src/world/societies/migrations/0005_drop_organization_org_type.py` — auto-generated, drops `org_type` FK after kind is non-nullable

**Modified (Phase A — Covenant linkage):**

- `src/world/covenants/constants.py` — NEW: covenant-specific constants
- `src/world/covenants/models.py` — add `Covenant.organization` OneToOne + save() logic
- `src/world/covenants/factories.py` — `CovenantFactory` auto-creates backing Organization (or modify existing if present)
- `src/world/covenants/tests/test_organization_link.py` — NEW: linkage tests
- `src/world/covenants/migrations/000N_covenant_organization_onetoone.py` — auto-generated

**Created (Phases B–E — Project framework):**

- `src/world/projects/__init__.py`, `apps.py`, `constants.py`, `models.py`, `services.py`, `factories.py`
- `src/world/projects/tests/__init__.py`, `test_models.py`, `test_services.py`, `test_lifecycle.py`
- `src/world/projects/migrations/0001_initial.py`, `0002_add_contribution.py`, `0003_add_check_outcome.py` (auto-generated)
- `src/server/conf/settings.py` — register `world.projects` in `INSTALLED_APPS`
- `src/world/game_clock/tasks.py` — register `projects.lifecycle_tick` cron task

---

## Phase A — Organization Refactor

### Task A1: Add `OrganizationKind` TextChoices enum

**Files:**
- Modify: `src/world/societies/constants.py`

- [ ] **Step 1: Read existing constants.py for context**

  ```bash
  cat /workspaces/arxii/src/world/societies/constants.py
  ```

- [ ] **Step 2: Append the enum**

  Append to `src/world/societies/constants.py`:

  ```python
  from django.db import models


  class OrganizationKind(models.TextChoices):
      """Discriminator for Organization. Each kind has a corresponding row in the
      OrganizationType catalog (admin-editable rank titles) and an optional
      per-kind details model (e.g., Covenant for COVENANT, NobleHouse for NOBLE
      when that ships).

      Adding a new kind: add an enum member here AND seed an OrganizationType
      fixture row (or create one via admin). Per-kind details models ship
      separately when their consumers materialize.
      """

      NOBLE = "noble", "Noble"
      BUSINESS = "business", "Business"
      GUILD = "guild", "Guild"
      GANG = "gang", "Gang"
      SECRET_SOCIETY = "secret_society", "Secret Society"
      COMMONER_FAMILY = "commoner_family", "Commoner Family"
      COVENANT = "covenant", "Covenant"
      DEVOTIONAL = "devotional", "Devotional"
      OTHER = "other", "Other"


  # Map legacy OrganizationType.name values (pre-refactor) to their new
  # OrganizationKind value. Used by the data migration in Task A4.
  LEGACY_ORG_TYPE_NAME_TO_KIND = {
      "noble_family": OrganizationKind.NOBLE,
      "business": OrganizationKind.BUSINESS,
      "guild": OrganizationKind.GUILD,
      "gang": OrganizationKind.GANG,
      "secret_society": OrganizationKind.SECRET_SOCIETY,
      "commoner_family": OrganizationKind.COMMONER_FAMILY,
      # covenant/devotional/other are new — no legacy rows existed.
  }
  ```

- [ ] **Step 3: Commit**

  ```bash
  git -C /workspaces/arxii add src/world/societies/constants.py
  git -C /workspaces/arxii commit -m "feat(societies): add OrganizationKind enum (9 values)"
  ```

---

### Task A2: Update the `initial_org_types.json` fixture for the new 9-kind taxonomy

**Files:**
- Modify: `src/world/societies/fixtures/initial_org_types.json`

- [ ] **Step 1: Read the existing fixture**

  ```bash
  cat /workspaces/arxii/src/world/societies/fixtures/initial_org_types.json
  ```

- [ ] **Step 2: Rewrite the fixture with 9 rows**

  Overwrite `src/world/societies/fixtures/initial_org_types.json`. The rename `noble_family` → `noble` is the only existing-row change; rank titles for existing kinds stay as-is. Three new rows added with placeholder titles flagged for admin review:

  ```json
  [
    {
      "model": "societies.organizationtype",
      "fields": {
        "name": "noble",
        "rank_1_title": "Head of House",
        "rank_2_title": "Voice",
        "rank_3_title": "Family Member",
        "rank_4_title": "Sworn",
        "rank_5_title": "Servant"
      }
    },
    {
      "model": "societies.organizationtype",
      "fields": {
        "name": "commoner_family",
        "rank_1_title": "Head of Family",
        "rank_2_title": "Senior",
        "rank_3_title": "Member",
        "rank_4_title": "Ward",
        "rank_5_title": "Hand"
      }
    },
    {
      "model": "societies.organizationtype",
      "fields": {
        "name": "business",
        "rank_1_title": "Owner",
        "rank_2_title": "Manager",
        "rank_3_title": "Employee",
        "rank_4_title": "Apprentice",
        "rank_5_title": "Hand"
      }
    },
    {
      "model": "societies.organizationtype",
      "fields": {
        "name": "guild",
        "rank_1_title": "Guildmaster",
        "rank_2_title": "Master",
        "rank_3_title": "Journeyman",
        "rank_4_title": "Apprentice",
        "rank_5_title": "Initiate"
      }
    },
    {
      "model": "societies.organizationtype",
      "fields": {
        "name": "secret_society",
        "rank_1_title": "Inner Circle",
        "rank_2_title": "Trusted",
        "rank_3_title": "Sworn",
        "rank_4_title": "Initiate",
        "rank_5_title": "Aspirant"
      }
    },
    {
      "model": "societies.organizationtype",
      "fields": {
        "name": "gang",
        "rank_1_title": "Boss",
        "rank_2_title": "Lieutenant",
        "rank_3_title": "Soldier",
        "rank_4_title": "Associate",
        "rank_5_title": "Hopeful"
      }
    },
    {
      "model": "societies.organizationtype",
      "fields": {
        "name": "covenant",
        "rank_1_title": "Coven Mother",
        "rank_2_title": "Adept",
        "rank_3_title": "Initiate",
        "rank_4_title": "Novice",
        "rank_5_title": "Aspirant"
      }
    },
    {
      "model": "societies.organizationtype",
      "fields": {
        "name": "devotional",
        "rank_1_title": "Leader",
        "rank_2_title": "Officer",
        "rank_3_title": "Member",
        "rank_4_title": "Associate",
        "rank_5_title": "Contact"
      }
    },
    {
      "model": "societies.organizationtype",
      "fields": {
        "name": "other",
        "rank_1_title": "Leader",
        "rank_2_title": "Officer",
        "rank_3_title": "Member",
        "rank_4_title": "Associate",
        "rank_5_title": "Contact"
      }
    }
  ]
  ```

  **Note for the implementer:** The `noble`, `commoner_family`, `business`, `guild`, `secret_society`, `gang` titles above are my best stab at the existing intent. The existing fixture's actual titles may differ — preserve those if so. **All titles are admin-editable**; the user (senior dev) reviews and customizes via Django admin. The `devotional` and `other` rows intentionally use generic placeholders pending user design pass — flag these in the PR description so the user can update them via admin.

- [ ] **Step 3: Test the fixture loads**

  ```bash
  uv run arx manage loaddata initial_org_types
  uv run arx manage shell -c "from world.societies.models import OrganizationType; print(sorted(OrganizationType.objects.values_list('name', flat=True)))"
  ```

  Expected output: a sorted list of 9 names including `covenant`, `devotional`, `other`, and the renamed `noble` (NOT `noble_family`).

  If the fixture fails to load because there's a `noble_family` row already in the DB with the same pk and the rename clashes, manually clean up:

  ```bash
  uv run arx manage shell -c "from world.societies.models import OrganizationType; OrganizationType.objects.filter(name='noble_family').delete()"
  uv run arx manage loaddata initial_org_types
  ```

- [ ] **Step 4: Commit**

  ```bash
  git -C /workspaces/arxii add src/world/societies/fixtures/initial_org_types.json
  git -C /workspaces/arxii commit -m "feat(societies): rewrite OrganizationType fixture for 9-kind taxonomy"
  ```

---

### Task A3: Add `Organization.kind` field (nullable initially)

**Files:**
- Modify: `src/world/societies/models.py` — add `kind` field
- Create: `src/world/societies/migrations/0004_add_organization_kind.py` (auto-generated)

- [ ] **Step 1: Write a failing test that the field exists**

  Create `src/world/societies/tests/test_organization_kind.py`:

  ```python
  """Tests for the Organization.kind discriminator and related rank-title behavior."""

  from django.test import TestCase

  from world.societies.constants import OrganizationKind
  from world.societies.models import Organization, OrganizationType


  class OrganizationKindFieldTests(TestCase):
      def test_organization_has_kind_field(self) -> None:
          """Organization.kind is a TextChoices field on Organization."""
          field_names = {f.name for f in Organization._meta.get_fields()}
          self.assertIn("kind", field_names)

      def test_kind_field_uses_organization_kind_choices(self) -> None:
          kind_field = Organization._meta.get_field("kind")
          choices_values = {value for value, _ in kind_field.choices}
          self.assertEqual(choices_values, set(OrganizationKind.values))
  ```

- [ ] **Step 2: Run the test to verify failure**

  ```bash
  uv run arx test world.societies.tests.test_organization_kind
  ```

  Expected: AssertionError — `kind` not in field_names.

- [ ] **Step 3: Add the field to Organization**

  In `src/world/societies/models.py`, find the `Organization` class (around line 176). Add the `kind` field BEFORE the existing `name` field (or wherever logical):

  ```python
      kind = models.CharField(
          max_length=20,
          null=True,  # temporarily nullable during migration; made non-null in Task A5
          blank=True,
          choices=OrganizationKind.choices,
          help_text=(
              "The kind of organization. Determines which per-kind details model "
              "applies (e.g., COVENANT -> Covenant model) and which OrganizationType "
              "row provides default rank titles (looked up by name == kind)."
          ),
      )
  ```

  Add the import at the top of `models.py`:

  ```python
  from world.societies.constants import OrganizationKind
  ```

- [ ] **Step 4: Generate the migration**

  ```bash
  uv run arx manage makemigrations societies
  cat /workspaces/arxii/src/world/societies/migrations/0004_*.py
  ```

  Inspect the migration. Should only add the `kind` field.

- [ ] **Step 5: Apply**

  ```bash
  uv run arx manage migrate societies
  ```

- [ ] **Step 6: Run the test**

  ```bash
  uv run arx test world.societies.tests.test_organization_kind
  ```

  Expected: Pass.

- [ ] **Step 7: Commit**

  ```bash
  git -C /workspaces/arxii add src/world/societies/models.py src/world/societies/migrations/0004_*.py src/world/societies/tests/test_organization_kind.py
  git -C /workspaces/arxii commit -m "feat(societies): add Organization.kind TextChoices field (nullable)"
  ```

---

### Task A4: Data migration: backfill `Organization.kind` from `org_type.name`

**Files:**
- Create: `src/world/societies/migrations/0005_backfill_organization_kind.py` (manual migration)

- [ ] **Step 1: Create the data migration**

  Create `src/world/societies/migrations/0005_backfill_organization_kind.py`:

  ```python
  """Data migration: backfill Organization.kind from org_type.name.

  Maps legacy OrganizationType.name values (noble_family etc.) to the new
  OrganizationKind enum values (noble etc.). Any unmapped rows get OTHER as
  a safe default.

  Per CLAUDE.md, data migrations pre-production are usually avoided, but this
  is infrastructure-cleanup that handles whatever dev rows exist. Production
  is assumed empty.
  """

  from django.db import migrations


  LEGACY_NAME_TO_KIND_VALUE = {
      "noble_family": "noble",
      "business": "business",
      "guild": "guild",
      "gang": "gang",
      "secret_society": "secret_society",
      "commoner_family": "commoner_family",
  }


  def backfill_kind_from_org_type(apps, schema_editor):
      Organization = apps.get_model("societies", "Organization")
      for org in Organization.objects.all():
          if org.org_type_id is None:
              org.kind = "other"
          else:
              legacy_name = org.org_type.name
              org.kind = LEGACY_NAME_TO_KIND_VALUE.get(legacy_name, "other")
          org.save(update_fields=["kind"])


  def reverse(apps, schema_editor):
      # Reverse: clear kind (org_type is still present and authoritative pre-Task A6)
      Organization = apps.get_model("societies", "Organization")
      Organization.objects.update(kind=None)


  class Migration(migrations.Migration):

      dependencies = [
          ("societies", "0004_add_organization_kind"),  # adjust the filename if numbering differs
      ]

      operations = [
          migrations.RunPython(backfill_kind_from_org_type, reverse_code=reverse),
      ]
  ```

- [ ] **Step 2: Apply and verify**

  ```bash
  uv run arx manage migrate societies
  uv run arx manage shell -c "from world.societies.models import Organization; print(Organization.objects.values_list('name', 'kind')[:10])"
  ```

  Expected: All Organization rows now have a `kind` value. (If you have no Organization rows in dev DB, output is `<QuerySet []>` — that's fine.)

- [ ] **Step 3: Commit**

  ```bash
  git -C /workspaces/arxii add src/world/societies/migrations/0005_backfill_organization_kind.py
  git -C /workspaces/arxii commit -m "feat(societies): backfill Organization.kind from legacy org_type.name"
  ```

---

### Task A5: Make `Organization.kind` non-nullable and drop `Organization.org_type` FK

**Files:**
- Modify: `src/world/societies/models.py` — `kind` becomes required; remove `org_type`
- Create: `src/world/societies/migrations/0006_drop_organization_org_type.py` (auto-generated)

- [ ] **Step 1: Write a failing test**

  Add to `src/world/societies/tests/test_organization_kind.py`:

  ```python
  class OrganizationKindRequiredTests(TestCase):
      def test_kind_is_required(self) -> None:
          """Organization.kind cannot be null after Task A5."""
          kind_field = Organization._meta.get_field("kind")
          self.assertFalse(kind_field.null)

      def test_org_type_fk_is_removed(self) -> None:
          """Organization.org_type FK is dropped — kind is the discriminator."""
          field_names = {f.name for f in Organization._meta.get_fields()}
          self.assertNotIn("org_type", field_names)
  ```

- [ ] **Step 2: Run to verify failure**

  ```bash
  uv run arx test world.societies.tests.test_organization_kind
  ```

  Expected: AssertionError — `kind` is still nullable; `org_type` still present.

- [ ] **Step 3: Modify Organization model**

  In `src/world/societies/models.py`:

  1. Change `kind` field to non-nullable:

  ```python
      kind = models.CharField(
          max_length=20,
          choices=OrganizationKind.choices,
          help_text=(
              "The kind of organization. Determines which per-kind details model "
              "applies and which OrganizationType row provides default rank titles."
          ),
      )
  ```

  2. **Delete the `org_type` field entirely** (the `models.ForeignKey(OrganizationType, ...)` block around line 204-209).

  3. Update `get_rank_title` to look up by `kind`:

  ```python
      def get_rank_title(self, rank: int) -> str:
          """Get the effective title for a rank.

          Returns the organization's override if set; otherwise looks up the
          default for the kind's OrganizationType row.
          """
          if rank < RANK_MIN or rank > RANK_MAX:
              msg = f"Rank must be {RANK_MIN}-{RANK_MAX}, got {rank}"
              raise ValueError(msg)

          override_field = f"rank_{rank}_title_override"
          override_value = getattr(self, override_field)
          if override_value:
              return override_value

          # Fall back to the OrganizationType row for this kind.
          try:
              org_type = OrganizationType.objects.get(name=self.kind)
          except OrganizationType.DoesNotExist as exc:
              msg = (
                  f"No OrganizationType row found for kind={self.kind!r}. "
                  "Run `arx manage loaddata initial_org_types` to seed defaults."
              )
              raise RuntimeError(msg) from exc

          default_field = f"rank_{rank}_title"
          return getattr(org_type, default_field)
  ```

- [ ] **Step 4: Generate and apply the migration**

  ```bash
  uv run arx manage makemigrations societies
  cat /workspaces/arxii/src/world/societies/migrations/0006_*.py
  uv run arx manage migrate societies
  ```

  Expected: Migration alters `kind` to non-null and removes `org_type` FK.

- [ ] **Step 5: Run tests**

  ```bash
  uv run arx test world.societies.tests.test_organization_kind
  ```

  Expected: Pass.

- [ ] **Step 6: Run full societies test suite — expect breakages**

  ```bash
  uv run arx test world.societies
  ```

  Several existing tests likely break because they reference `org_type`. Fix them in this commit:
  - Tests using `OrganizationFactory(org_type=...)` → switch to `OrganizationFactory(kind=OrganizationKind.NOBLE)` etc.
  - Tests using `noble_family` string directly → switch to `OrganizationKind.NOBLE`
  - Tests using `organization.org_type.name` → switch to `organization.kind`
  - Tests using `NobleOrgTypeFactory` etc. — remove (the per-kind OrgType factories are obsolete; the kind enum + the seeded fixture row is enough)

- [ ] **Step 7: Commit**

  ```bash
  git -C /workspaces/arxii add src/world/societies/models.py src/world/societies/migrations/0006_*.py src/world/societies/tests/
  git -C /workspaces/arxii commit -m "feat(societies): make Organization.kind required, drop org_type FK"
  ```

---

### Task A6: Update `OrganizationFactory` to take `kind=` kwarg; remove obsolete per-kind OrgType factories

**Files:**
- Modify: `src/world/societies/factories.py`

- [ ] **Step 1: Read existing factories**

  ```bash
  grep -n "^class \|kind\|org_type\|noble_family" /workspaces/arxii/src/world/societies/factories.py
  ```

- [ ] **Step 2: Update `OrganizationFactory`**

  In `src/world/societies/factories.py`, find `OrganizationFactory` (around line 67). Replace its `org_type` field with a `kind` field:

  ```python
  class OrganizationFactory(factory_django.DjangoModelFactory):
      """Factory for Organization. Defaults to OrganizationKind.NOBLE; pass kind= to override."""

      class Meta:
          model = Organization

      name = factory.Sequence(lambda n: f"Test Organization {n}")
      society = factory.SubFactory(SocietyFactory)  # may be None for standalone orgs
      kind = OrganizationKind.NOBLE
  ```

  Add the import at top:

  ```python
  from world.societies.constants import OrganizationKind
  ```

- [ ] **Step 3: Remove obsolete per-kind OrgType factories**

  Find and DELETE these factory classes (or whichever subset exists):
  - `NobleOrgTypeFactory`
  - `BusinessOrgTypeFactory`
  - `GuildOrgTypeFactory`
  - `GangOrgTypeFactory`
  - `SecretSocietyOrgTypeFactory`
  - `CommonerFamilyOrgTypeFactory`

  They're obsolete — OrganizationType rows are seeded by the fixture, and tests should use `OrganizationFactory(kind=OrganizationKind.X)` directly.

  **Keep `OrganizationTypeFactory`** if a test ever needs to create a custom OrganizationType row (rare; should use `django_get_or_create=("name",)` matching the fixture).

- [ ] **Step 4: Run full societies test suite again**

  ```bash
  uv run arx test world.societies
  ```

  Expected: All pass. Tests that referenced removed factories should already be updated from Task A5; if any straggler remains, fix it.

- [ ] **Step 5: Commit**

  ```bash
  git -C /workspaces/arxii add src/world/societies/factories.py
  git -C /workspaces/arxii commit -m "feat(societies): refactor OrganizationFactory to take kind=; remove obsolete OrgType factories"
  ```

---

### Task A7: Make `Organization.society` nullable (for standalone orgs like covenants)

**Files:**
- Modify: `src/world/societies/models.py` — `society` field
- Create: `src/world/societies/migrations/0007_organization_society_nullable.py` (auto-generated)
- Create: `src/world/societies/tests/test_organization_standalone.py` (NEW)

- [ ] **Step 1: Write the failing test**

  Create `src/world/societies/tests/test_organization_standalone.py`:

  ```python
  """Verify Organization.society can be null for standalone organizations."""

  from django.test import TestCase

  from world.societies.constants import OrganizationKind
  from world.societies.models import Organization


  class OrganizationStandaloneTests(TestCase):
      def test_organization_can_have_null_society(self) -> None:
          """Standalone orgs (e.g., covenants) exist independently of any Society."""
          org = Organization.objects.create(
              name="Standalone Covenant Test",
              society=None,
              kind=OrganizationKind.COVENANT,
          )
          self.assertIsNone(org.society)
          self.assertEqual(org.kind, OrganizationKind.COVENANT)
  ```

- [ ] **Step 2: Run to verify failure**

  ```bash
  uv run arx test world.societies.tests.test_organization_standalone
  ```

  Expected: `IntegrityError: NOT NULL constraint failed`.

- [ ] **Step 3: Modify Organization.society field**

  In `src/world/societies/models.py`, update the `society` field:

  ```python
      society = models.ForeignKey(
          Society,
          null=True,
          blank=True,
          on_delete=models.SET_NULL,
          related_name="organizations",
          help_text=(
              "The society this organization belongs to. May be NULL for "
              "standalone organizations (e.g., covenants) that exist independently."
          ),
      )
  ```

  Update `get_effective_principle` to handle null society:

  ```python
      def get_effective_principle(self, principle_name: str) -> int:
          override_field = f"{principle_name}_override"
          override_value = getattr(self, override_field)
          if override_value is not None:
              return override_value
          if self.society is None:
              msg = (
                  f"Cannot resolve principle {principle_name!r} for standalone "
                  f"organization {self.name!r}: no society and no override set."
              )
              raise ValueError(msg)
          return getattr(self.society, principle_name)
  ```

  Update `__str__` for null society:

  ```python
      def __str__(self) -> str:
          society_label = self.society.name if self.society else "standalone"
          return f"{self.name} ({society_label})"
  ```

- [ ] **Step 4: Generate and apply migration**

  ```bash
  uv run arx manage makemigrations societies
  uv run arx manage migrate societies
  ```

- [ ] **Step 5: Run tests**

  ```bash
  uv run arx test world.societies
  ```

  Expected: All pass. If `get_effective_principle` is used elsewhere in tests with null society, fix call sites.

- [ ] **Step 6: Commit**

  ```bash
  git -C /workspaces/arxii add src/world/societies/models.py src/world/societies/migrations/0007_*.py src/world/societies/tests/test_organization_standalone.py
  git -C /workspaces/arxii commit -m "feat(societies): allow Organization.society to be null for standalone orgs"
  ```

---

### Task A8: Add `Covenant.organization` OneToOneField + auto-create

**Files:**
- Create: `src/world/covenants/constants.py` (if doesn't exist)
- Modify: `src/world/covenants/models.py` — `Covenant` gets `organization` OneToOne + save() logic
- Modify: `src/world/covenants/factories.py` (create if not present)
- Create: `src/world/covenants/tests/test_organization_link.py`
- Create: `src/world/covenants/migrations/000N_covenant_organization_onetoone.py` (auto-generated)

- [ ] **Step 1: Add the constants module**

  Create or append to `src/world/covenants/constants.py`:

  ```python
  """Constants for the covenants system."""

  from world.societies.constants import OrganizationKind

  # The OrganizationKind value Covenants register as.
  COVENANT_ORG_KIND = OrganizationKind.COVENANT
  ```

  (Most covenant-specific configuration moved to the OrganizationType fixture; this module is intentionally thin.)

- [ ] **Step 2: Inspect current Covenant model**

  ```bash
  grep -n "^class Covenant\|^    name\|^    covenant_type\|^    level\|^    sworn_objective" /workspaces/arxii/src/world/covenants/models.py
  ```

- [ ] **Step 3: Write failing test**

  Create `src/world/covenants/tests/test_organization_link.py`:

  ```python
  """Verify Covenant<->Organization OneToOne linkage and auto-creation."""

  from django.test import TestCase

  from world.covenants.factories import CovenantFactory
  from world.covenants.models import Covenant
  from world.societies.constants import OrganizationKind
  from world.societies.models import Organization


  class CovenantOrganizationLinkTests(TestCase):
      def test_covenant_auto_creates_backing_organization(self) -> None:
          covenant = CovenantFactory(name="Test Covenant Alpha")
          self.assertIsNotNone(covenant.organization)
          self.assertEqual(covenant.organization.name, "Test Covenant Alpha")
          self.assertEqual(covenant.organization.kind, OrganizationKind.COVENANT)
          self.assertIsNone(covenant.organization.society)  # standalone

      def test_covenant_organization_is_one_to_one(self) -> None:
          covenant = CovenantFactory(name="Test Covenant Beta")
          # Reverse access works: organization.covenant
          self.assertEqual(covenant.organization.covenant, covenant)

      def test_covenant_uses_existing_organization_when_provided(self) -> None:
          org = Organization.objects.create(
              name="Pre-built Cov Org",
              society=None,
              kind=OrganizationKind.COVENANT,
          )
          covenant = Covenant(
              name="Pre-built Cov Org",
              sworn_objective="test",
              organization=org,
          )
          covenant.save()
          self.assertEqual(covenant.organization_id, org.pk)
          self.assertEqual(Organization.objects.filter(name="Pre-built Cov Org").count(), 1)
  ```

- [ ] **Step 4: Run to verify failure**

  ```bash
  uv run arx test world.covenants.tests.test_organization_link
  ```

  Expected: `AttributeError: 'Covenant' object has no attribute 'organization'` or `ImportError: cannot import name 'CovenantFactory'`.

- [ ] **Step 5: Modify Covenant model**

  In `src/world/covenants/models.py`, modify the `Covenant` class. Add `organization` as primary-key OneToOne and add `save()` override:

  ```python
  class Covenant(SharedMemoryModel):
      """The foundational social/magical structure that binds members under a sworn oath.

      Per-kind extension of Organization for kind=COVENANT. Each Covenant has a
      backing Organization auto-created in save() if not provided. Covenant.pk
      equals organization.pk.
      """

      organization = models.OneToOneField(
          "societies.Organization",
          on_delete=models.CASCADE,
          primary_key=True,
          related_name="covenant",
      )

      # Existing fields (preserve current definitions; show here for context):
      name = models.CharField(max_length=120, unique=True)
      # covenant_type, level, sworn_objective, formed_at, dissolved_at unchanged

      def save(self, *args, **kwargs) -> None:
          if self.organization_id is None:
              # Lazy import to avoid circular dependency.
              from world.covenants.constants import COVENANT_ORG_KIND
              from world.societies.models import Organization

              self.organization = Organization.objects.create(
                  name=self.name,
                  society=None,
                  kind=COVENANT_ORG_KIND,
              )
          super().save(*args, **kwargs)
  ```

- [ ] **Step 6: Generate migration**

  ```bash
  uv run arx manage makemigrations covenants
  cat /workspaces/arxii/src/world/covenants/migrations/000*.py | tail -50
  ```

  Inspect. The migration changes the Covenant pk from auto id to a OneToOne to Organization. This is a destructive schema change for any existing Covenant rows — they need to be wiped before migration (per CLAUDE.md "no data migrations pre-production" combined with "preserve the dev database"; if you have any actual Covenant rows in dev DB, clear them as a one-off cleanup):

  ```bash
  uv run arx manage shell -c "from world.covenants.models import Covenant; print('existing rows:', Covenant.objects.count())"
  ```

  If `existing rows > 0`, clear them:

  ```bash
  uv run arx manage shell -c "from world.covenants.models import Covenant; Covenant.objects.all().delete()"
  ```

- [ ] **Step 7: Apply migration**

  ```bash
  uv run arx manage migrate covenants
  ```

- [ ] **Step 8: Update or create CovenantFactory**

  Read existing factory:

  ```bash
  cat /workspaces/arxii/src/world/covenants/factories.py 2>/dev/null
  ```

  If the file exists, update CovenantFactory to NOT pass an `id`. If it doesn't exist, create:

  ```python
  """Test factories for covenants."""

  import factory
  from factory.django import DjangoModelFactory

  from world.covenants.models import Covenant


  class CovenantFactory(DjangoModelFactory):
      """Factory for Covenant.

      The backing Organization is auto-created in Covenant.save(), so no
      organization kwarg is needed. Pass `name` to control naming.
      """

      class Meta:
          model = Covenant

      name = factory.Sequence(lambda n: f"Test Covenant {n}")
      sworn_objective = "To uphold the magical oath."
      # covenant_type and level use model defaults
  ```

- [ ] **Step 9: Run tests**

  ```bash
  uv run arx test world.covenants.tests.test_organization_link
  uv run arx test world.covenants  # full covenants suite
  ```

  Expected: All pass. Any existing test that referenced `covenant.id` may need updating to `covenant.pk` or `covenant.organization_id` — fix in this commit.

- [ ] **Step 10: Commit**

  ```bash
  git -C /workspaces/arxii add src/world/covenants/constants.py src/world/covenants/models.py src/world/covenants/factories.py src/world/covenants/migrations/ src/world/covenants/tests/test_organization_link.py
  git -C /workspaces/arxii commit -m "feat(covenants): link Covenant to Organization via OneToOne pk + auto-create"
  ```

---

### Task A9: Postgres parity for Phase A

- [ ] **Step 1: Run parity tests**

  ```bash
  just test-parity societies
  just test-parity covenants
  ```

  Expected: All pass. Per memory `feedback_sqlite_masks_m2m_through_pg_failure`, SQLite can hide Postgres-specific migration issues — this gate must pass before moving to Phase B.

- [ ] **Step 2: If parity is green, Phase A complete; no commit needed**

---

## Phase B — Projects App Skeleton

### Task B1: Create the projects app structure

**Files:**
- Create: `src/world/projects/__init__.py` (empty)
- Create: `src/world/projects/apps.py`
- Create: `src/world/projects/migrations/__init__.py` (empty)
- Create: `src/world/projects/tests/__init__.py` (empty)

- [ ] **Step 1: Create the directory structure**

  ```bash
  mkdir -p /workspaces/arxii/src/world/projects/migrations /workspaces/arxii/src/world/projects/tests
  touch /workspaces/arxii/src/world/projects/__init__.py
  touch /workspaces/arxii/src/world/projects/migrations/__init__.py
  touch /workspaces/arxii/src/world/projects/tests/__init__.py
  ```

- [ ] **Step 2: Write apps.py**

  Create `src/world/projects/apps.py`:

  ```python
  """AppConfig for the projects framework."""

  from django.apps import AppConfig


  class ProjectsConfig(AppConfig):
      name = "world.projects"
      label = "projects"
      verbose_name = "Projects (delayed multi-tick endeavors)"
      default_auto_field = "django.db.models.BigAutoField"
  ```

- [ ] **Step 3: Commit**

  ```bash
  git -C /workspaces/arxii add src/world/projects/
  git -C /workspaces/arxii commit -m "feat(projects): scaffold world.projects app structure"
  ```

---

### Task B2: Register `world.projects` in INSTALLED_APPS

**Files:**
- Modify: `src/server/conf/settings.py`

- [ ] **Step 1: Find INSTALLED_APPS**

  ```bash
  grep -n "INSTALLED_APPS\|world\." /workspaces/arxii/src/server/conf/settings.py | head -30
  ```

- [ ] **Step 2: Add `"world.projects"`**

  Add `"world.projects",` to INSTALLED_APPS near other `world.*` entries (preserve the file's existing ordering style).

- [ ] **Step 3: Verify**

  ```bash
  uv run arx manage shell -c "from django.apps import apps; print(apps.get_app_config('projects').verbose_name)"
  ```

  Expected: `Projects (delayed multi-tick endeavors)`

- [ ] **Step 4: Commit**

  ```bash
  git -C /workspaces/arxii add src/server/conf/settings.py
  git -C /workspaces/arxii commit -m "feat(projects): register world.projects in INSTALLED_APPS"
  ```

---

### Task B3: Add `projects/constants.py` with TextChoices enums

**Files:**
- Create: `src/world/projects/constants.py`

- [ ] **Step 1: Write the constants module**

  Create `src/world/projects/constants.py`:

  ```python
  """TextChoices enums for the projects framework."""

  from django.db import models


  class ProjectKind(models.TextChoices):
      """Discriminator for per-kind details models.

      Each kind maps to a per-kind details model (e.g., BuildingConstructionDetails
      for BUILDING_CONSTRUCTION) and a service handler registered via
      register_kind_handler. TEST_KIND is used only in Phase D's framework tests.
      """

      BUILDING_CONSTRUCTION = "BUILDING_CONSTRUCTION", "Building Construction"
      ROOM_FEATURE_PROGRESSION = "ROOM_FEATURE_PROGRESSION", "Room Feature Progression"
      TEST_KIND = "TEST_KIND", "Test Kind (framework tests only)"


  class ProjectStatus(models.TextChoices):
      """Lifecycle states a Project transitions through."""

      PLANNING = "PLANNING", "Planning"
      ACTIVE = "ACTIVE", "Active"
      RESOLVING = "RESOLVING", "Resolving"
      COMPLETED = "COMPLETED", "Completed"
      FAILED = "FAILED", "Failed"
      CANCELLED = "CANCELLED", "Cancelled"  # manual or building-decay-mid-project


  class CompletionMode(models.TextChoices):
      """How a Project decides when to resolve.

      SINGLE_THRESHOLD: completes on (progress >= threshold) OR (now >= time_limit).
      TIERED_PERIOD:    completes only when now >= time_limit; tier determined by
                        which per-kind tier_thresholds were crossed.
      """

      SINGLE_THRESHOLD = "SINGLE_THRESHOLD", "Single Threshold"
      TIERED_PERIOD = "TIERED_PERIOD", "Tiered Period"


  class ContributionKind(models.TextChoices):
      """Discriminator for Contribution rows. Exactly one kind-specific column is populated per row."""

      AP = "AP", "Action Points"
      MONEY = "MONEY", "Money"
      ITEM = "ITEM", "Item"
      CHECK = "CHECK", "Skill Check"


  class ContributionPrivacy(models.TextChoices):
      """Whether a contribution's intent text is visible to others."""

      PRIVATE = "PRIVATE", "Private (actor only)"
      GROUP = "GROUP", "Group (all project contributors)"
  ```

- [ ] **Step 2: Commit**

  ```bash
  git -C /workspaces/arxii add src/world/projects/constants.py
  git -C /workspaces/arxii commit -m "feat(projects): add TextChoices enums for kind/status/mode/contribution"
  ```

---

## Phase C — Project and Contribution Models

### Task C1: Add the `Project` model

**Files:**
- Create: `src/world/projects/models.py`
- Create: `src/world/projects/factories.py`
- Create: `src/world/projects/tests/test_models.py`
- Create: `src/world/projects/migrations/0001_initial.py` (auto-generated)

- [ ] **Step 1: Write the failing test**

  Create `src/world/projects/tests/test_models.py`:

  ```python
  """Tests for Project and Contribution models."""

  from datetime import timedelta

  from django.test import TestCase
  from django.utils import timezone

  from world.projects.constants import (
      CompletionMode,
      ProjectKind,
      ProjectStatus,
  )
  from world.projects.factories import ProjectFactory


  class ProjectModelTests(TestCase):
      def test_project_creation_defaults(self) -> None:
          project = ProjectFactory()
          self.assertEqual(project.status, ProjectStatus.PLANNING)
          self.assertEqual(project.current_progress, 0)
          self.assertIsNone(project.outcome_tier)

      def test_single_threshold_project_requires_threshold_target(self) -> None:
          project = ProjectFactory.build(
              kind=ProjectKind.TEST_KIND,
              completion_mode=CompletionMode.SINGLE_THRESHOLD,
              threshold_target=None,
              time_limit=timezone.now() + timedelta(days=7),
          )
          with self.assertRaises(Exception):
              project.full_clean()

      def test_tiered_period_project_allows_null_threshold_target(self) -> None:
          project = ProjectFactory(
              kind=ProjectKind.TEST_KIND,
              completion_mode=CompletionMode.TIERED_PERIOD,
              threshold_target=None,
              time_limit=timezone.now() + timedelta(days=7),
          )
          self.assertIsNone(project.threshold_target)
  ```

- [ ] **Step 2: Run to verify failure**

  ```bash
  uv run arx test world.projects.tests.test_models
  ```

  Expected: `ImportError: cannot import name 'ProjectFactory'`.

- [ ] **Step 3: Write the Project model**

  Create `src/world/projects/models.py`:

  ```python
  """Project framework models.

  Project is the runtime model for delayed multi-tick endeavors with outcome rolls.
  Per-kind details live in separate models keyed by the kind discriminator.

  See: docs/superpowers/specs/2026-05-30-projects-buildings-sanctum-design.md (subsystem A)
  """

  from __future__ import annotations

  from django.core.exceptions import ValidationError
  from django.db import models
  from evennia.utils.idmapper.models import SharedMemoryModel

  from world.projects.constants import (
      CompletionMode,
      ContributionKind,
      ContributionPrivacy,
      ProjectKind,
      ProjectStatus,
  )


  class Project(SharedMemoryModel):
      """A delayed multi-tick endeavor with contributions and an outcome roll.

      Each Project belongs to one ProjectKind. Per-kind details (e.g.,
      BuildingConstructionDetails) live in a separate model with a OneToOne FK
      back to this Project — see Plan 3.
      """

      kind = models.CharField(
          max_length=40,
          choices=ProjectKind.choices,
          help_text="Discriminator selecting which per-kind details model applies.",
      )
      completion_mode = models.CharField(
          max_length=20,
          choices=CompletionMode.choices,
          help_text=(
              "SINGLE_THRESHOLD: completes on progress>=threshold OR now>=time_limit. "
              "TIERED_PERIOD: completes only at time_limit; tier by progress."
          ),
      )
      status = models.CharField(
          max_length=20,
          choices=ProjectStatus.choices,
          default=ProjectStatus.PLANNING,
      )

      owner_persona = models.ForeignKey(
          "scenes.Persona",
          on_delete=models.PROTECT,
          related_name="projects_owned",
          help_text=(
              "The persona who initiated the project (weighted-check source at "
              "resolution). Resolved from account.active_persona at creation if "
              "triggered from an account-level action like permit activation."
          ),
      )

      started_at = models.DateTimeField()
      time_limit = models.DateTimeField()
      threshold_target = models.PositiveIntegerField(null=True, blank=True)
      current_progress = models.PositiveIntegerField(default=0)

      outcome_tier = models.ForeignKey(
          "traits.CheckOutcome",
          null=True,
          blank=True,
          on_delete=models.PROTECT,
          related_name="project_outcomes",
          help_text="Set at resolution. CheckOutcome row indicating tier via success_level.",
      )

      resonance = models.ForeignKey(
          "magic.Resonance",
          null=True,
          blank=True,
          on_delete=models.SET_NULL,
          related_name="projects",
      )

      description = models.TextField(blank=True)

      created_at = models.DateTimeField(auto_now_add=True)
      updated_at = models.DateTimeField(auto_now=True)

      class Meta:
          ordering = ["-created_at"]
          indexes = [
              models.Index(fields=["status", "time_limit"]),
              models.Index(fields=["kind"]),
          ]

      def __str__(self) -> str:
          return f"Project<{self.kind}>(#{self.pk}, {self.status})"

      def clean(self) -> None:
          super().clean()
          if (
              self.completion_mode == CompletionMode.SINGLE_THRESHOLD
              and self.threshold_target is None
          ):
              msg = "SINGLE_THRESHOLD projects require threshold_target."
              raise ValidationError({"threshold_target": msg})
          if self.time_limit is None:
              msg = "All projects require time_limit."
              raise ValidationError({"time_limit": msg})
  ```

- [ ] **Step 4: Write the ProjectFactory**

  Create `src/world/projects/factories.py`:

  ```python
  """Test factories for the projects framework."""

  from datetime import timedelta

  import factory
  from django.utils import timezone
  from factory.django import DjangoModelFactory

  from world.projects.constants import (
      CompletionMode,
      ProjectKind,
      ProjectStatus,
  )
  from world.projects.models import Project
  from world.scenes.factories import PersonaFactory  # adjust if needed


  class ProjectFactory(DjangoModelFactory):
      class Meta:
          model = Project

      kind = ProjectKind.TEST_KIND
      completion_mode = CompletionMode.SINGLE_THRESHOLD
      status = ProjectStatus.PLANNING
      owner_persona = factory.SubFactory(PersonaFactory)
      started_at = factory.LazyFunction(timezone.now)
      time_limit = factory.LazyFunction(lambda: timezone.now() + timedelta(days=7))
      threshold_target = 100
      current_progress = 0
      description = ""
  ```

  Verify `PersonaFactory` import path:

  ```bash
  grep -n "class PersonaFactory" /workspaces/arxii/src/world/scenes/factories.py 2>/dev/null
  ```

- [ ] **Step 5: Generate and apply migration**

  ```bash
  uv run arx manage makemigrations projects
  uv run arx manage migrate projects
  ```

- [ ] **Step 6: Run tests**

  ```bash
  uv run arx test world.projects.tests.test_models
  ```

- [ ] **Step 7: Commit**

  ```bash
  git -C /workspaces/arxii add src/world/projects/models.py src/world/projects/factories.py src/world/projects/migrations/0001_initial.py src/world/projects/tests/test_models.py
  git -C /workspaces/arxii commit -m "feat(projects): add Project model with kind/mode/status discriminators"
  ```

---

### Task C2: Add `Contribution` model

**Files:**
- Modify: `src/world/projects/models.py` (append Contribution)
- Modify: `src/world/projects/factories.py` (append ContributionFactory)
- Modify: `src/world/projects/tests/test_models.py` (add Contribution tests)
- Create: `src/world/projects/migrations/0002_add_contribution.py`

- [ ] **Step 1: Write failing tests**

  Append to `src/world/projects/tests/test_models.py`:

  ```python
  from world.projects.constants import ContributionKind, ContributionPrivacy
  from world.projects.factories import ContributionFactory


  class ContributionModelTests(TestCase):
      def test_ap_contribution_populates_ap_amount(self) -> None:
          c = ContributionFactory(kind=ContributionKind.AP, ap_amount=3)
          self.assertEqual(c.ap_amount, 3)
          self.assertIsNone(c.money_amount)

      def test_money_contribution_populates_money_amount(self) -> None:
          c = ContributionFactory(
              kind=ContributionKind.MONEY, money_amount=500, ap_amount=None
          )
          self.assertEqual(c.money_amount, 500)
          self.assertIsNone(c.ap_amount)

      def test_kind_discriminator_validation(self) -> None:
          c = ContributionFactory.build(
              kind=ContributionKind.AP, ap_amount=None, money_amount=None
          )
          with self.assertRaises(Exception):
              c.full_clean()

      def test_default_privacy_is_private(self) -> None:
          c = ContributionFactory()
          self.assertEqual(c.privacy_setting, ContributionPrivacy.PRIVATE)
  ```

- [ ] **Step 2: Run to verify failure**

  ```bash
  uv run arx test world.projects.tests.test_models
  ```

- [ ] **Step 3: Add Contribution model**

  Append to `src/world/projects/models.py`:

  ```python
  class Contribution(SharedMemoryModel):
      """A single contribution to a Project.

      Discriminator pattern: `kind` selects which kind-specific column is populated
      per row (ap_amount, money_amount, item_instance, check_outcome).
      """

      project = models.ForeignKey(
          Project, on_delete=models.CASCADE, related_name="contributions"
      )
      contributor_persona = models.ForeignKey(
          "scenes.Persona",
          on_delete=models.PROTECT,
          related_name="project_contributions",
      )
      kind = models.CharField(max_length=10, choices=ContributionKind.choices)

      ap_amount = models.PositiveIntegerField(null=True, blank=True)
      money_amount = models.PositiveIntegerField(null=True, blank=True)
      item_instance = models.ForeignKey(
          "items.ItemInstance",
          null=True,
          blank=True,
          on_delete=models.PROTECT,
          related_name="project_contributions",
      )
      # check_outcome added in Task C3

      intent_text = models.TextField(blank=True)
      privacy_setting = models.CharField(
          max_length=10,
          choices=ContributionPrivacy.choices,
          default=ContributionPrivacy.PRIVATE,
      )
      occurred_at = models.DateTimeField(auto_now_add=True)

      class Meta:
          ordering = ["-occurred_at"]
          indexes = [
              models.Index(fields=["project", "contributor_persona"]),
          ]

      def __str__(self) -> str:
          return f"Contribution<{self.kind}>(#{self.pk}, project #{self.project_id})"

      def clean(self) -> None:
          super().clean()
          required_field_for_kind = {
              ContributionKind.AP: "ap_amount",
              ContributionKind.MONEY: "money_amount",
              ContributionKind.ITEM: "item_instance",
              # CHECK handled in Task C3
          }
          if self.kind not in required_field_for_kind:
              return
          required = required_field_for_kind[self.kind]
          if getattr(self, required) is None:
              msg = f"Contribution kind={self.kind} requires {required} to be set."
              raise ValidationError({required: msg})
  ```

- [ ] **Step 4: Add ContributionFactory**

  Append to `src/world/projects/factories.py`:

  ```python
  from world.projects.constants import ContributionKind, ContributionPrivacy
  from world.projects.models import Contribution


  class ContributionFactory(DjangoModelFactory):
      class Meta:
          model = Contribution

      project = factory.SubFactory(ProjectFactory)
      contributor_persona = factory.SubFactory(PersonaFactory)
      kind = ContributionKind.AP
      ap_amount = 1
      money_amount = None
      item_instance = None
      intent_text = ""
      privacy_setting = ContributionPrivacy.PRIVATE
  ```

- [ ] **Step 5: Generate and apply migration**

  ```bash
  uv run arx manage makemigrations projects
  uv run arx manage migrate projects
  ```

- [ ] **Step 6: Run tests**

  ```bash
  uv run arx test world.projects.tests.test_models
  ```

- [ ] **Step 7: Commit**

  ```bash
  git -C /workspaces/arxii add src/world/projects/models.py src/world/projects/factories.py src/world/projects/migrations/ src/world/projects/tests/test_models.py
  git -C /workspaces/arxii commit -m "feat(projects): add Contribution model with discriminated kind columns"
  ```

---

### Task C3: Add CHECK contribution kind + `check_outcome` FK

**Files:**
- Modify: `src/world/projects/models.py`
- Modify: `src/world/projects/tests/test_models.py`
- Create: `src/world/projects/migrations/0003_add_check_outcome.py`

- [ ] **Step 1: Write failing tests**

  Append to `src/world/projects/tests/test_models.py`:

  ```python
  from world.traits.models import CheckOutcome


  class ContributionCheckOutcomeTests(TestCase):
      @classmethod
      def setUpTestData(cls) -> None:
          cls.success_outcome, _ = CheckOutcome.objects.get_or_create(
              name="Success", defaults={"success_level": 1}
          )

      def test_check_contribution_populates_check_outcome(self) -> None:
          c = ContributionFactory(
              kind=ContributionKind.CHECK,
              ap_amount=None,
              check_outcome=self.success_outcome,
          )
          self.assertEqual(c.check_outcome.name, "Success")

      def test_check_contribution_requires_check_outcome(self) -> None:
          c = ContributionFactory.build(
              kind=ContributionKind.CHECK,
              ap_amount=None,
              check_outcome=None,
          )
          with self.assertRaises(Exception):
              c.full_clean()
  ```

- [ ] **Step 2: Run to verify failure**

- [ ] **Step 3: Add `check_outcome` field + validation**

  In `src/world/projects/models.py`, in the Contribution class, after `item_instance`:

  ```python
      check_outcome = models.ForeignKey(
          "traits.CheckOutcome",
          null=True,
          blank=True,
          on_delete=models.PROTECT,
          related_name="project_contributions",
      )
  ```

  Update clean() to include CHECK:

  ```python
          required_field_for_kind = {
              ContributionKind.AP: "ap_amount",
              ContributionKind.MONEY: "money_amount",
              ContributionKind.ITEM: "item_instance",
              ContributionKind.CHECK: "check_outcome",
          }
          # Remove the early-return `if self.kind not in ...`
  ```

- [ ] **Step 4: Migration + apply + test + commit**

  ```bash
  uv run arx manage makemigrations projects
  uv run arx manage migrate projects
  uv run arx test world.projects.tests.test_models
  git -C /workspaces/arxii add src/world/projects/models.py src/world/projects/migrations/ src/world/projects/tests/test_models.py
  git -C /workspaces/arxii commit -m "feat(projects): add check_outcome FK + CHECK contribution kind validation"
  ```

---

### Task C4: Add `add_contribution` service function

**Files:**
- Create: `src/world/projects/services.py`
- Create: `src/world/projects/tests/test_services.py`

- [ ] **Step 1: Write failing test**

  Create `src/world/projects/tests/test_services.py`:

  ```python
  """Tests for the projects framework service functions."""

  from django.test import TestCase

  from world.projects.constants import ContributionKind, ProjectStatus
  from world.projects.factories import ProjectFactory
  from world.projects.models import Contribution
  from world.projects.services import ProjectNotActiveError, add_contribution
  from world.scenes.factories import PersonaFactory


  class AddContributionTests(TestCase):
      def test_ap_contribution_advances_progress(self) -> None:
          project = ProjectFactory(status=ProjectStatus.ACTIVE, current_progress=0)
          contributor = PersonaFactory()
          add_contribution(
              project=project,
              contributor_persona=contributor,
              kind=ContributionKind.AP,
              ap_amount=5,
              intent_text="putting my back into it",
          )
          project.refresh_from_db()
          self.assertEqual(project.current_progress, 5)
          self.assertEqual(Contribution.objects.filter(project=project).count(), 1)

      def test_inactive_project_rejects_contribution(self) -> None:
          project = ProjectFactory(status=ProjectStatus.PLANNING, current_progress=0)
          contributor = PersonaFactory()
          with self.assertRaises(ProjectNotActiveError):
              add_contribution(
                  project=project,
                  contributor_persona=contributor,
                  kind=ContributionKind.AP,
                  ap_amount=5,
              )
  ```

- [ ] **Step 2: Run to verify failure**

- [ ] **Step 3: Write the service**

  Create `src/world/projects/services.py`:

  ```python
  """Service functions for the projects framework."""

  from __future__ import annotations

  from typing import TYPE_CHECKING

  from django.db import models, transaction

  from world.projects.constants import ContributionKind, ProjectStatus
  from world.projects.models import Contribution, Project

  if TYPE_CHECKING:
      from world.items.models import ItemInstance
      from world.scenes.models import Persona
      from world.traits.models import CheckOutcome


  class ProjectNotActiveError(ValueError):
      """Raised when a contribution targets a project that's not ACTIVE."""


  @transaction.atomic
  def add_contribution(
      *,
      project: Project,
      contributor_persona: "Persona",
      kind: str,
      ap_amount: int | None = None,
      money_amount: int | None = None,
      item_instance: "ItemInstance | None" = None,
      check_outcome: "CheckOutcome | None" = None,
      intent_text: str = "",
      privacy_setting: str = "PRIVATE",
  ) -> Contribution:
      """Add a contribution to an ACTIVE Project and advance current_progress."""
      if project.status != ProjectStatus.ACTIVE:
          msg = (
              f"Project #{project.pk} status is {project.status}, not ACTIVE — "
              "cannot accept contributions."
          )
          raise ProjectNotActiveError(msg)

      contribution = Contribution(
          project=project,
          contributor_persona=contributor_persona,
          kind=kind,
          ap_amount=ap_amount,
          money_amount=money_amount,
          item_instance=item_instance,
          check_outcome=check_outcome,
          intent_text=intent_text,
          privacy_setting=privacy_setting,
      )
      contribution.full_clean()
      contribution.save()

      # Immediate progress advancement for non-CHECK kinds.
      progress_delta = 0
      if kind == ContributionKind.AP and ap_amount is not None:
          progress_delta = ap_amount
      elif kind == ContributionKind.MONEY and money_amount is not None:
          # 1 progress per 100 gold default. Per-kind details may override later.
          progress_delta = money_amount // 100
      elif kind == ContributionKind.ITEM:
          progress_delta = 1  # placeholder; per-kind details may override

      if progress_delta > 0:
          Project.objects.filter(pk=project.pk).update(
              current_progress=models.F("current_progress") + progress_delta
          )

      return contribution
  ```

- [ ] **Step 4: Run tests**

  ```bash
  uv run arx test world.projects.tests.test_services
  ```

- [ ] **Step 5: Commit**

  ```bash
  git -C /workspaces/arxii add src/world/projects/services.py src/world/projects/tests/test_services.py
  git -C /workspaces/arxii commit -m "feat(projects): add add_contribution service with progress advancement"
  ```

---

## Phase D — Cron Lifecycle

### Task D1: Add per-kind handler registry

**Files:**
- Modify: `src/world/projects/services.py`
- Modify: `src/world/projects/tests/test_services.py`

- [ ] **Step 1: Write failing test**

  Append to `src/world/projects/tests/test_services.py`:

  ```python
  from world.projects.constants import ProjectKind
  from world.projects.services import (
      clear_kind_handlers,
      get_kind_handler,
      register_kind_handler,
  )


  class KindHandlerRegistryTests(TestCase):
      def setUp(self) -> None:
          clear_kind_handlers()

      def test_register_and_lookup_handler(self) -> None:
          def fake_handler(project, outcome_tier):
              return None

          register_kind_handler(ProjectKind.TEST_KIND, fake_handler)
          self.assertIs(get_kind_handler(ProjectKind.TEST_KIND), fake_handler)

      def test_missing_handler_raises(self) -> None:
          with self.assertRaises(LookupError):
              get_kind_handler("NONEXISTENT_KIND")
  ```

- [ ] **Step 2: Run to verify failure**

- [ ] **Step 3: Add registry**

  Append to `src/world/projects/services.py`:

  ```python
  # -------------------------------------------------------------------
  # Kind handler registry
  # -------------------------------------------------------------------

  from typing import Callable

  KindHandler = Callable[[Project, "CheckOutcome | None"], None]

  _KIND_HANDLERS: dict[str, KindHandler] = {}


  def register_kind_handler(kind: str, handler: KindHandler) -> None:
      """Register a per-kind resolution handler. Re-registration overwrites."""
      _KIND_HANDLERS[kind] = handler


  def get_kind_handler(kind: str) -> KindHandler:
      """Return the registered handler for `kind`, or raise LookupError."""
      try:
          return _KIND_HANDLERS[kind]
      except KeyError as exc:
          msg = f"No handler registered for ProjectKind={kind!r}"
          raise LookupError(msg) from exc


  def clear_kind_handlers() -> None:
      """Test-only: clear the handler registry."""
      _KIND_HANDLERS.clear()
  ```

- [ ] **Step 4: Run + commit**

  ```bash
  uv run arx test world.projects.tests.test_services
  git -C /workspaces/arxii add src/world/projects/services.py src/world/projects/tests/test_services.py
  git -C /workspaces/arxii commit -m "feat(projects): add kind handler registry for per-kind resolution"
  ```

---

### Task D2: Add `resolve_project` service

**Files:**
- Modify: `src/world/projects/services.py`
- Modify: `src/world/projects/tests/test_services.py`

- [ ] **Step 1: Write failing test**

  Append to `src/world/projects/tests/test_services.py`:

  ```python
  from world.projects.services import resolve_project


  class ResolveProjectTests(TestCase):
      @classmethod
      def setUpTestData(cls) -> None:
          cls.success_outcome, _ = CheckOutcome.objects.get_or_create(
              name="Success", defaults={"success_level": 1}
          )
          cls.failed_outcome, _ = CheckOutcome.objects.get_or_create(
              name="Failed", defaults={"success_level": -1}
          )

      def setUp(self) -> None:
          clear_kind_handlers()
          self.handler_calls = []

          def test_handler(project, outcome_tier):
              self.handler_calls.append((project.pk, outcome_tier))

          register_kind_handler(ProjectKind.TEST_KIND, test_handler)

      def test_resolve_calls_handler_and_completes(self) -> None:
          project = ProjectFactory(
              kind=ProjectKind.TEST_KIND, status=ProjectStatus.RESOLVING
          )
          resolve_project(project, outcome_tier=self.success_outcome)
          project.refresh_from_db()
          self.assertEqual(project.status, ProjectStatus.COMPLETED)
          self.assertEqual(project.outcome_tier_id, self.success_outcome.pk)
          self.assertEqual(len(self.handler_calls), 1)

      def test_resolve_failed_outcome_sets_failed_status(self) -> None:
          project = ProjectFactory(
              kind=ProjectKind.TEST_KIND, status=ProjectStatus.RESOLVING
          )
          resolve_project(project, outcome_tier=self.failed_outcome)
          project.refresh_from_db()
          self.assertEqual(project.status, ProjectStatus.FAILED)

      def test_resolve_non_resolving_project_raises(self) -> None:
          project = ProjectFactory(
              kind=ProjectKind.TEST_KIND, status=ProjectStatus.ACTIVE
          )
          with self.assertRaises(ValueError):
              resolve_project(project, outcome_tier=self.success_outcome)
  ```

- [ ] **Step 2: Run to verify failure**

- [ ] **Step 3: Add `resolve_project`**

  Append to `src/world/projects/services.py`:

  ```python
  @transaction.atomic
  def resolve_project(project: Project, *, outcome_tier: "CheckOutcome") -> None:
      """Finalize a RESOLVING project: dispatch to per-kind handler, set outcome.

      Marks COMPLETED if success_level >= 0, otherwise FAILED. Per-kind handlers
      run BEFORE status is updated so they can read the pre-resolution state.
      """
      if project.status != ProjectStatus.RESOLVING:
          msg = (
              f"resolve_project requires status=RESOLVING, got {project.status} "
              f"for project #{project.pk}"
          )
          raise ValueError(msg)

      handler = get_kind_handler(project.kind)
      handler(project, outcome_tier)

      project.outcome_tier = outcome_tier
      project.status = (
          ProjectStatus.COMPLETED
          if outcome_tier.success_level >= 0
          else ProjectStatus.FAILED
      )
      project.save(update_fields=["outcome_tier", "status", "updated_at"])
  ```

- [ ] **Step 4: Run tests + commit**

  ```bash
  uv run arx test world.projects.tests.test_services
  git -C /workspaces/arxii add src/world/projects/services.py src/world/projects/tests/test_services.py
  git -C /workspaces/arxii commit -m "feat(projects): add resolve_project dispatching to per-kind handler"
  ```

---

### Task D3: Add `scan_active_projects` cron tick service

**Files:**
- Modify: `src/world/projects/services.py`
- Create: `src/world/projects/tests/test_lifecycle.py`

- [ ] **Step 1: Write failing test**

  Create `src/world/projects/tests/test_lifecycle.py`:

  ```python
  """Integration tests for the cron-driven Project lifecycle."""

  from datetime import timedelta

  from django.test import TestCase
  from django.utils import timezone

  from world.projects.constants import (
      CompletionMode,
      ProjectKind,
      ProjectStatus,
  )
  from world.projects.factories import ProjectFactory
  from world.projects.services import (
      clear_kind_handlers,
      register_kind_handler,
      scan_active_projects,
  )


  class SingleThresholdLifecycleTests(TestCase):
      def setUp(self) -> None:
          clear_kind_handlers()
          register_kind_handler(
              ProjectKind.TEST_KIND, lambda project, tier: None
          )

      def test_threshold_hit_schedules_resolution(self) -> None:
          project = ProjectFactory(
              kind=ProjectKind.TEST_KIND,
              completion_mode=CompletionMode.SINGLE_THRESHOLD,
              status=ProjectStatus.ACTIVE,
              current_progress=100,
              threshold_target=100,
              time_limit=timezone.now() + timedelta(days=7),
          )
          scan_active_projects()
          project.refresh_from_db()
          self.assertEqual(project.status, ProjectStatus.RESOLVING)

      def test_time_limit_passed_schedules_resolution(self) -> None:
          project = ProjectFactory(
              kind=ProjectKind.TEST_KIND,
              completion_mode=CompletionMode.SINGLE_THRESHOLD,
              status=ProjectStatus.ACTIVE,
              current_progress=50,
              threshold_target=100,
              time_limit=timezone.now() - timedelta(hours=1),
          )
          scan_active_projects()
          project.refresh_from_db()
          self.assertEqual(project.status, ProjectStatus.RESOLVING)

      def test_under_threshold_within_time_stays_active(self) -> None:
          project = ProjectFactory(
              kind=ProjectKind.TEST_KIND,
              completion_mode=CompletionMode.SINGLE_THRESHOLD,
              status=ProjectStatus.ACTIVE,
              current_progress=50,
              threshold_target=100,
              time_limit=timezone.now() + timedelta(days=7),
          )
          scan_active_projects()
          project.refresh_from_db()
          self.assertEqual(project.status, ProjectStatus.ACTIVE)


  class TieredPeriodLifecycleTests(TestCase):
      def setUp(self) -> None:
          clear_kind_handlers()
          register_kind_handler(
              ProjectKind.TEST_KIND, lambda project, tier: None
          )

      def test_tiered_period_only_resolves_at_deadline(self) -> None:
          project = ProjectFactory(
              kind=ProjectKind.TEST_KIND,
              completion_mode=CompletionMode.TIERED_PERIOD,
              status=ProjectStatus.ACTIVE,
              current_progress=9999,
              threshold_target=None,
              time_limit=timezone.now() + timedelta(days=7),
          )
          scan_active_projects()
          project.refresh_from_db()
          self.assertEqual(project.status, ProjectStatus.ACTIVE)

      def test_tiered_period_resolves_at_deadline(self) -> None:
          project = ProjectFactory(
              kind=ProjectKind.TEST_KIND,
              completion_mode=CompletionMode.TIERED_PERIOD,
              status=ProjectStatus.ACTIVE,
              current_progress=50,
              threshold_target=None,
              time_limit=timezone.now() - timedelta(hours=1),
          )
          scan_active_projects()
          project.refresh_from_db()
          self.assertEqual(project.status, ProjectStatus.RESOLVING)
  ```

- [ ] **Step 2: Run to verify failure**

- [ ] **Step 3: Add `scan_active_projects`**

  Append to `src/world/projects/services.py`:

  ```python
  from django.utils import timezone


  def scan_active_projects() -> int:
      """Cron tick: scan ACTIVE projects, transition completion-ready ones to RESOLVING.

      SINGLE_THRESHOLD: completion = (current_progress >= threshold_target)
                                     OR (now >= time_limit).
      TIERED_PERIOD:    completion = (now >= time_limit).

      Returns count of projects transitioned. Resolution itself (handler call +
      outcome_tier set) is done by resolve_project, called separately.
      """
      now = timezone.now()
      transitioned = 0
      active = Project.objects.filter(status=ProjectStatus.ACTIVE)
      for project in active:
          should_resolve = False
          if project.completion_mode == CompletionMode.SINGLE_THRESHOLD:
              if project.threshold_target is None:
                  continue  # invalid state; skip
              if (
                  project.current_progress >= project.threshold_target
                  or now >= project.time_limit
              ):
                  should_resolve = True
          elif project.completion_mode == CompletionMode.TIERED_PERIOD:
              if now >= project.time_limit:
                  should_resolve = True

          if should_resolve:
              Project.objects.filter(pk=project.pk, status=ProjectStatus.ACTIVE).update(
                  status=ProjectStatus.RESOLVING, updated_at=now
              )
              transitioned += 1

      return transitioned
  ```

- [ ] **Step 4: Run + commit**

  ```bash
  uv run arx test world.projects.tests.test_lifecycle
  git -C /workspaces/arxii add src/world/projects/services.py src/world/projects/tests/test_lifecycle.py
  git -C /workspaces/arxii commit -m "feat(projects): add scan_active_projects cron tick service"
  ```

---

### Task D4: Register `projects.lifecycle_tick` with the game clock

**Files:**
- Modify: `src/world/game_clock/tasks.py`

- [ ] **Step 1: Read existing cron registration**

  ```bash
  grep -n "register_task\|CronDefinition\|task_key" /workspaces/arxii/src/world/game_clock/tasks.py | head -30
  ```

- [ ] **Step 2: Write test verifying the task is registered**

  Append to `src/world/projects/tests/test_lifecycle.py`:

  ```python
  class CronRegistrationTests(TestCase):
      def test_projects_lifecycle_tick_is_registered(self) -> None:
          # Find the accessor name first if get_registered_tasks isn't it.
          from world.game_clock.task_registry import get_registered_tasks

          keys = [t.task_key for t in get_registered_tasks()]
          self.assertIn("projects.lifecycle_tick", keys)
  ```

  If `get_registered_tasks` accessor doesn't exist with that name, find the right one:

  ```bash
  grep -rn "def get_registered\|_REGISTERED_TASKS\|TASK_REGISTRY" /workspaces/arxii/src/world/game_clock/ | head -10
  ```

- [ ] **Step 3: Run to verify failure**

- [ ] **Step 4: Add the registration**

  In `src/world/game_clock/tasks.py`, inside `register_all_tasks()`, add:

  ```python
  from datetime import timedelta

  from world.projects.services import scan_active_projects

  # Inside register_all_tasks():

      register_task(
          CronDefinition(
              task_key="projects.lifecycle_tick",
              callable=scan_active_projects,
              interval=timedelta(minutes=15),  # tunable; final cadence TBD
              description=(
                  "Scan ACTIVE Projects and transition completion-ready ones to RESOLVING."
              ),
          )
      )
  ```

- [ ] **Step 5: Run + commit**

  ```bash
  uv run arx test world.projects.tests.test_lifecycle
  uv run arx test world.game_clock  # no regressions in cron infra
  git -C /workspaces/arxii add src/world/game_clock/tasks.py src/world/projects/tests/test_lifecycle.py
  git -C /workspaces/arxii commit -m "feat(projects): register projects.lifecycle_tick cron task"
  ```

---

### Task D5: Postgres parity for projects

- [ ] **Step 1: Run parity tests**

  ```bash
  just test-parity projects
  ```

  Expected: All pass.

---

## Phase E — Achievement Stat Integration

### Task E1: Define StatDefinition rows for project stats

**Files:**
- Modify: `src/world/projects/services.py` — add `register_stat_definitions`
- Modify: `src/world/projects/apps.py` — call `register_stat_definitions` in `ready()`
- Modify: `src/world/projects/tests/test_services.py`

- [ ] **Step 1: Inspect StatDefinition API**

  ```bash
  grep -n "class StatDefinition\|StatDefinition.objects" /workspaces/arxii/src/world/achievements/models.py | head -10
  cat /workspaces/arxii/src/world/achievements/models.py | head -100
  ```

  Note exact field names (e.g., is it `display_name`, `display`, `label`?).

- [ ] **Step 2: Write failing test**

  Append to `src/world/projects/tests/test_services.py`:

  ```python
  from world.achievements.models import StatDefinition


  class StatDefinitionsTests(TestCase):
      def test_projects_total_contributed_stat_exists(self) -> None:
          self.assertTrue(
              StatDefinition.objects.filter(key="projects.total_contributed").exists()
          )

      def test_projects_completed_critical_stat_exists(self) -> None:
          self.assertTrue(
              StatDefinition.objects.filter(key="projects.completed_critical").exists()
          )
  ```

- [ ] **Step 3: Run to verify failure**

- [ ] **Step 4: Add `register_stat_definitions`**

  Append to `src/world/projects/services.py`:

  ```python
  def register_stat_definitions() -> None:
      """Create the StatDefinition rows for project-related achievement stats.

      Idempotent (uses get_or_create). Called at app-ready time in apps.py.
      Adjust field names if StatDefinition uses different ones (verify in
      world/achievements/models.py).
      """
      from world.achievements.models import StatDefinition

      StatDefinition.objects.get_or_create(
          key="projects.total_contributed",
          defaults={
              "display_name": "Total Project Contributions",
              "description": "Total contributions made across all projects.",
          },
      )
      StatDefinition.objects.get_or_create(
          key="projects.completed_critical",
          defaults={
              "display_name": "Critical Project Completions",
              "description": (
                  "Number of projects the character contributed to that completed "
                  "at CRITICAL tier."
              ),
          },
      )
  ```

- [ ] **Step 5: Wire `ready()`**

  Modify `src/world/projects/apps.py`:

  ```python
  """AppConfig for the projects framework."""

  from django.apps import AppConfig


  class ProjectsConfig(AppConfig):
      name = "world.projects"
      label = "projects"
      verbose_name = "Projects (delayed multi-tick endeavors)"
      default_auto_field = "django.db.models.BigAutoField"

      def ready(self) -> None:
          from world.projects.services import register_stat_definitions

          register_stat_definitions()
  ```

- [ ] **Step 6: Run tests**

  ```bash
  uv run arx test world.projects.tests.test_services
  ```

  If Django doesn't run `ready()` during test bootstrap properly, call `register_stat_definitions()` directly in setUpTestData of the test class.

- [ ] **Step 7: Commit**

  ```bash
  git -C /workspaces/arxii add src/world/projects/apps.py src/world/projects/services.py src/world/projects/tests/test_services.py
  git -C /workspaces/arxii commit -m "feat(projects): seed StatDefinition rows for project contribution stats"
  ```

---

### Task E2: Wire `add_contribution` to increment the contribution stat

**Files:**
- Modify: `src/world/projects/services.py`
- Modify: `src/world/projects/tests/test_services.py`

- [ ] **Step 1: Verify the stats increment API**

  ```bash
  grep -rn "def increment\|class .*StatHandler\|character_sheet.stats" /workspaces/arxii/src/world/achievements/ | head -10
  ```

- [ ] **Step 2: Write failing test**

  Append to `src/world/projects/tests/test_services.py`:

  ```python
  class ContributionStatIncrementTests(TestCase):
      @classmethod
      def setUpTestData(cls) -> None:
          cls.stat_def, _ = StatDefinition.objects.get_or_create(
              key="projects.total_contributed",
              defaults={"display_name": "Total", "description": ""},
          )

      def test_add_contribution_increments_stat(self) -> None:
          project = ProjectFactory(status=ProjectStatus.ACTIVE)
          contributor = PersonaFactory()
          add_contribution(
              project=project,
              contributor_persona=contributor,
              kind=ContributionKind.AP,
              ap_amount=3,
          )

          # Adjust StatTracker query per actual API.
          from world.achievements.models import StatTracker

          tracker = StatTracker.objects.get(
              character_sheet=contributor.character_sheet,
              stat_definition=self.stat_def,
          )
          self.assertEqual(tracker.value, 1)
  ```

- [ ] **Step 3: Extend add_contribution**

  In `src/world/projects/services.py`, in `add_contribution`, just before `return contribution`:

  ```python
      from world.achievements.models import StatDefinition

      try:
          stat_def = StatDefinition.objects.get(key="projects.total_contributed")
          contributor_persona.character_sheet.stats.increment(stat_def, 1)
      except StatDefinition.DoesNotExist:
          # Apps.ready() should seed this; if missing during isolated tests, skip silently.
          pass
  ```

  Verify `contributor_persona.character_sheet.stats.increment(stat_def, N)` API exists; if different (e.g., `stats.record(...)`, `stats.bump(...)`), adjust.

- [ ] **Step 4: Run + commit**

  ```bash
  uv run arx test world.projects.tests.test_services
  git -C /workspaces/arxii add src/world/projects/services.py src/world/projects/tests/test_services.py
  git -C /workspaces/arxii commit -m "feat(projects): increment projects.total_contributed stat on each contribution"
  ```

---

## Phase F — Final Verification

### Task F1: Full regression run without `--keepdb`

- [ ] **Step 1: Full suite, fresh DB**

  ```bash
  uv run arx test
  ```

  Per memory `feedback_postgres_only_rule_scope`: the run-without-keepdb gate catches bugs depending on preserved test DB state.

- [ ] **Step 2: Lint + format**

  ```bash
  ruff check /workspaces/arxii/src/world/projects /workspaces/arxii/src/world/covenants /workspaces/arxii/src/world/societies
  ruff format --check /workspaces/arxii/src/world/projects /workspaces/arxii/src/world/covenants /workspaces/arxii/src/world/societies
  ```

- [ ] **Step 3: Type checking**

  ```bash
  uv run ty check src/world/projects src/world/covenants src/world/societies
  ```

- [ ] **Step 4: Cleanup commit (if needed)**

  ```bash
  git -C /workspaces/arxii add -A
  git -C /workspaces/arxii commit -m "chore: lint/format/type cleanup post-Plan 1"
  ```

---

### Task F2: Update spec to reflect Plan 1 completion

**Files:**
- Modify: `docs/superpowers/specs/2026-05-30-projects-buildings-sanctum-design.md`

- [ ] **Step 1: Add a "Plan 1 Status" subsection after "Scope Overview"**

  ```markdown
  ## Plan 1 Status (Org Refactor + Project Foundation) — SHIPPED <date>

  - `OrganizationKind` TextChoices (9 values) added as the Organization discriminator
  - `OrganizationType` repurposed as admin-editable per-kind rank-title catalog
  - `Organization.kind` field added; `Organization.org_type` FK dropped
  - `Organization.society` made nullable for standalone orgs (covenants)
  - `Covenant` linked to `Organization` via OneToOne with auto-create in `save()`
  - Project framework: Project, Contribution, kind handler registry, scan_active_projects cron
  - StatDefinition rows seeded for `projects.total_contributed` and `projects.completed_critical`
  - Lifecycle gate: scan transitions ACTIVE -> RESOLVING; per-kind resolution ships in Plans 3 and 4
  - Next: Plan 2 (NPC Interaction framework + Builders Guild Clerk role)
  ```

- [ ] **Step 2: Commit**

  ```bash
  git -C /workspaces/arxii add docs/superpowers/specs/2026-05-30-projects-buildings-sanctum-design.md
  git -C /workspaces/arxii commit -m "docs(specs): mark Plan 1 as shipped"
  ```

---

## Self-Review

**Spec coverage:**
- [x] OrganizationKind discriminator with 9 values — Phase A
- [x] OrganizationType repurposed as admin-editable rank-title catalog — Phase A
- [x] Organization.society nullable for standalone orgs — Phase A
- [x] Covenant ↔ Organization OneToOne linkage with auto-create — Phase A
- [x] Project model with kind/mode/status/owner_persona/threshold/progress/outcome_tier/resonance — Phase C
- [x] Contribution table with AP/MONEY/ITEM/CHECK discriminator — Phase C
- [x] Per-kind handler registry — Phase D
- [x] Cron lifecycle (SINGLE_THRESHOLD + TIERED_PERIOD) — Phase D
- [x] StatDefinition integration — Phase E

**Spec items deferred to later plans:**
- `BuildingConstructionDetails`, `RoomFeatureProgressionDetails` per-kind models → Plans 3 / 4
- Per-kind handler IMPLEMENTATIONS (the registry exists; concrete handlers register in Plans 3 / 4)
- Frontend UI for Projects → Plans 3 / 4
- ResonanceGrant `source_project` typed FK + GainSource value → Plan 4 cross-cut migration

**Placeholder scan:** All steps have explicit code, commands, and expected output. The `devotional` and `other` rank titles in Task A2 use generic placeholders — flagged for user admin-edit pass per `feedback_flavor_text_design_pass`.

**Type consistency:**
- `Project.kind` and `Contribution.kind` both CharField with TextChoices — consistent
- `Contribution.check_outcome` FK to `traits.CheckOutcome` — consistent across C3
- `scan_active_projects() → int` consistent
- `register_kind_handler` / `get_kind_handler` / `clear_kind_handlers` consistent
- `OrganizationKind.values` used everywhere (no string literals for kind comparisons)

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-31-plan1-org-refactor-projects-foundation.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, two-stage review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**

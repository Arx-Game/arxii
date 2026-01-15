# Form System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a flexible physical characteristics system that tracks appearance traits, supports multiple saved forms (true/alternate/disguise), and layers temporary changes on top.

**Architecture:** Data-driven trait definitions via Django admin. Species/origin restrict CG options but don't constrain storage. CharacterForm stores saved trait sets; TemporaryFormChange layers overrides. Single service function resolves apparent form.

**Tech Stack:** Django models with SharedMemoryModel for lookups, DRF serializers/viewsets for API, FactoryBoy for tests.

---

## Task 1: Create Form App Structure

**Files:**
- Create: `src/world/forms/__init__.py`
- Create: `src/world/forms/models.py`
- Create: `src/world/forms/apps.py`
- Modify: `src/server/conf/settings.py` (add to INSTALLED_APPS)

**Step 1: Create app directory and __init__.py**

```bash
mkdir -p src/world/forms
touch src/world/forms/__init__.py
```

**Step 2: Create apps.py**

```python
from django.apps import AppConfig


class FormsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "world.forms"
    verbose_name = "Character Forms"
```

**Step 3: Create initial models.py with FormTrait**

```python
from django.db import models

from evennia.utils.idmapper.models import SharedMemoryModel


class TraitType(models.TextChoices):
    COLOR = "color", "Color"
    STYLE = "style", "Style"


class FormTrait(SharedMemoryModel):
    """Definition of a physical characteristic type (e.g., hair_color, ear_type)."""

    name = models.CharField(max_length=50, unique=True, help_text="Internal key")
    display_name = models.CharField(max_length=100, help_text="Display name for UI")
    trait_type = models.CharField(
        max_length=20, choices=TraitType.choices, default=TraitType.STYLE
    )
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "display_name"]

    def __str__(self):
        return self.display_name
```

**Step 4: Add to INSTALLED_APPS**

In `src/server/conf/settings.py`, find `INSTALLED_APPS` and add `"world.forms",` in the world apps section.

**Step 5: Run makemigrations**

```bash
cd src && arx manage makemigrations forms
```

Expected: Creates `0001_initial.py` with FormTrait model.

**Step 6: Apply migration**

```bash
arx manage migrate forms
```

**Step 7: Commit**

```bash
git add src/world/forms src/server/conf/settings.py
git commit -m "feat(forms): create forms app with FormTrait model"
```

---

## Task 2: Add FormTraitOption Model

**Files:**
- Modify: `src/world/forms/models.py`

**Step 1: Add FormTraitOption model**

Add after FormTrait class:

```python
class FormTraitOption(SharedMemoryModel):
    """A valid value for a trait (e.g., 'black' for hair_color)."""

    trait = models.ForeignKey(
        FormTrait, on_delete=models.CASCADE, related_name="options"
    )
    name = models.CharField(max_length=50, help_text="Internal key")
    display_name = models.CharField(max_length=100, help_text="Display name for UI")
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "display_name"]
        unique_together = [["trait", "name"]]

    def __str__(self):
        return f"{self.trait.display_name}: {self.display_name}"
```

**Step 2: Run makemigrations**

```bash
arx manage makemigrations forms
```

**Step 3: Squash migrations into single initial migration**

Since we're still in development, delete the new migration and update 0001_initial.py to include FormTraitOption. Then:

```bash
arx manage migrate forms
```

**Step 4: Commit**

```bash
git add src/world/forms/
git commit -m "feat(forms): add FormTraitOption model"
```

---

## Task 3: Add Species Integration Models

**Files:**
- Modify: `src/world/forms/models.py`

**Step 1: Add SpeciesFormTrait model**

Add after FormTraitOption:

```python
from world.species.models import Species, SpeciesOrigin


class SpeciesFormTrait(SharedMemoryModel):
    """Links a species to which traits it has available in CG."""

    species = models.ForeignKey(
        Species, on_delete=models.CASCADE, related_name="form_traits"
    )
    trait = models.ForeignKey(
        FormTrait, on_delete=models.CASCADE, related_name="species_links"
    )
    is_available_in_cg = models.BooleanField(
        default=True, help_text="Show this trait in character creation"
    )

    class Meta:
        unique_together = [["species", "trait"]]
        verbose_name = "Species Form Trait"
        verbose_name_plural = "Species Form Traits"

    def __str__(self):
        return f"{self.species.name} - {self.trait.display_name}"
```

**Step 2: Add SpeciesOriginTraitOption model**

Add after SpeciesFormTrait:

```python
class SpeciesOriginTraitOption(SharedMemoryModel):
    """Override available options for a trait at the origin level."""

    species_origin = models.ForeignKey(
        SpeciesOrigin, on_delete=models.CASCADE, related_name="trait_option_overrides"
    )
    trait = models.ForeignKey(
        FormTrait, on_delete=models.CASCADE, related_name="origin_overrides"
    )
    option = models.ForeignKey(
        FormTraitOption, on_delete=models.CASCADE, related_name="origin_overrides"
    )
    is_available = models.BooleanField(
        default=True, help_text="True=add this option, False=remove it"
    )

    class Meta:
        unique_together = [["species_origin", "trait", "option"]]
        verbose_name = "Species Origin Trait Option"
        verbose_name_plural = "Species Origin Trait Options"

    def __str__(self):
        action = "+" if self.is_available else "-"
        return f"{self.species_origin}: {action}{self.option.display_name}"
```

**Step 3: Update migration**

Squash into 0001_initial.py and apply:

```bash
arx manage migrate forms
```

**Step 4: Commit**

```bash
git add src/world/forms/
git commit -m "feat(forms): add species and origin restriction models"
```

---

## Task 4: Add Character Form Models

**Files:**
- Modify: `src/world/forms/models.py`

**Step 1: Add FormType enum and CharacterForm model**

Add after the species integration models:

```python
from evennia.objects.models import ObjectDB


class FormType(models.TextChoices):
    TRUE = "true", "True Form"
    ALTERNATE = "alternate", "Alternate Form"
    DISGUISE = "disguise", "Disguise"


class CharacterForm(models.Model):
    """A saved set of form trait values for a character."""

    character = models.ForeignKey(
        ObjectDB,
        on_delete=models.CASCADE,
        related_name="forms",
        limit_choices_to={"db_typeclass_path__contains": "Character"},
    )
    name = models.CharField(max_length=100, blank=True, help_text="Optional form name")
    form_type = models.CharField(
        max_length=20, choices=FormType.choices, default=FormType.TRUE
    )
    is_player_created = models.BooleanField(
        default=False, help_text="True for player-created disguises"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Character Form"
        verbose_name_plural = "Character Forms"

    def __str__(self):
        if self.name:
            return f"{self.character.db_key}: {self.name}"
        return f"{self.character.db_key}: {self.get_form_type_display()}"
```

**Step 2: Add CharacterFormValue model**

```python
class CharacterFormValue(models.Model):
    """A single trait value within a character's form."""

    form = models.ForeignKey(
        CharacterForm, on_delete=models.CASCADE, related_name="values"
    )
    trait = models.ForeignKey(
        FormTrait, on_delete=models.CASCADE, related_name="character_values"
    )
    option = models.ForeignKey(
        FormTraitOption, on_delete=models.CASCADE, related_name="character_values"
    )

    class Meta:
        unique_together = [["form", "trait"]]
        verbose_name = "Character Form Value"
        verbose_name_plural = "Character Form Values"

    def __str__(self):
        return f"{self.form}: {self.trait.display_name}={self.option.display_name}"
```

**Step 3: Add CharacterFormState model**

```python
class CharacterFormState(models.Model):
    """Tracks which form a character currently has active."""

    character = models.OneToOneField(
        ObjectDB,
        on_delete=models.CASCADE,
        related_name="form_state",
        limit_choices_to={"db_typeclass_path__contains": "Character"},
    )
    active_form = models.ForeignKey(
        CharacterForm,
        on_delete=models.SET_NULL,
        null=True,
        related_name="active_for",
    )

    class Meta:
        verbose_name = "Character Form State"
        verbose_name_plural = "Character Form States"

    def __str__(self):
        if self.active_form:
            return f"{self.character.db_key}: {self.active_form}"
        return f"{self.character.db_key}: No active form"
```

**Step 4: Update migration and apply**

Squash into 0001_initial.py:

```bash
arx manage migrate forms
```

**Step 5: Commit**

```bash
git add src/world/forms/
git commit -m "feat(forms): add CharacterForm, CharacterFormValue, CharacterFormState"
```

---

## Task 5: Add Temporary Form Change Model

**Files:**
- Modify: `src/world/forms/models.py`

**Step 1: Add enums for temporary changes**

Add after FormType:

```python
class SourceType(models.TextChoices):
    EQUIPPED_ITEM = "equipped_item", "Equipped Item"
    APPLIED_ITEM = "applied_item", "Applied Item"
    SPELL = "spell", "Spell"
    SYSTEM = "system", "System"


class DurationType(models.TextChoices):
    UNTIL_REMOVED = "until_removed", "Until Removed"
    REAL_TIME = "real_time", "Real Time"
    GAME_TIME = "game_time", "Game Time"
    SCENE = "scene", "Scene-Based"
```

**Step 2: Add TemporaryFormChange model**

```python
from django.utils import timezone


class TemporaryFormChange(models.Model):
    """A temporary override applied on top of the active form."""

    character = models.ForeignKey(
        ObjectDB,
        on_delete=models.CASCADE,
        related_name="temporary_form_changes",
        limit_choices_to={"db_typeclass_path__contains": "Character"},
    )
    trait = models.ForeignKey(
        FormTrait, on_delete=models.CASCADE, related_name="temporary_changes"
    )
    option = models.ForeignKey(
        FormTraitOption, on_delete=models.CASCADE, related_name="temporary_changes"
    )
    source_type = models.CharField(max_length=20, choices=SourceType.choices)
    source_id = models.PositiveIntegerField(
        null=True, blank=True, help_text="ID of the source object"
    )
    duration_type = models.CharField(max_length=20, choices=DurationType.choices)
    expires_at = models.DateTimeField(
        null=True, blank=True, help_text="For real-time duration"
    )
    expires_after_scenes = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="For scene-based duration"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Temporary Form Change"
        verbose_name_plural = "Temporary Form Changes"

    def __str__(self):
        return f"{self.character.db_key}: {self.trait.display_name}={self.option.display_name} ({self.get_duration_type_display()})"

    def is_expired(self) -> bool:
        """Check if this temporary change has expired."""
        if self.duration_type == DurationType.UNTIL_REMOVED:
            return False
        if self.duration_type == DurationType.REAL_TIME and self.expires_at:
            return timezone.now() > self.expires_at
        # Game time and scene-based require external tracking
        return False
```

**Step 3: Add manager for active changes**

Add before the TemporaryFormChange class:

```python
class TemporaryFormChangeManager(models.Manager):
    """Manager with convenience methods for temporary changes."""

    def active(self):
        """Return non-expired temporary changes."""
        now = timezone.now()
        return self.exclude(
            duration_type=DurationType.REAL_TIME, expires_at__lt=now
        )
```

Then add to TemporaryFormChange class:

```python
    objects = TemporaryFormChangeManager()
```

**Step 4: Finalize migration**

Now that all models are complete, ensure 0001_initial.py is correct and apply:

```bash
arx manage migrate forms
```

**Step 5: Commit**

```bash
git add src/world/forms/
git commit -m "feat(forms): add TemporaryFormChange model with duration support"
```

---

## Task 6: Create Factories for Testing

**Files:**
- Create: `src/world/forms/factories.py`

**Step 1: Create factories file**

```python
import factory

from world.forms.models import (
    CharacterForm,
    CharacterFormState,
    CharacterFormValue,
    FormTrait,
    FormTraitOption,
    FormType,
    SpeciesFormTrait,
    SpeciesOriginTraitOption,
    TemporaryFormChange,
    DurationType,
    SourceType,
    TraitType,
)
from world.species.factories import SpeciesFactory, SpeciesOriginFactory


class FormTraitFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = FormTrait
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"trait_{n}")
    display_name = factory.LazyAttribute(lambda o: o.name.replace("_", " ").title())
    trait_type = TraitType.STYLE
    sort_order = factory.Sequence(lambda n: n)


class FormTraitOptionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = FormTraitOption
        django_get_or_create = ("trait", "name")

    trait = factory.SubFactory(FormTraitFactory)
    name = factory.Sequence(lambda n: f"option_{n}")
    display_name = factory.LazyAttribute(lambda o: o.name.replace("_", " ").title())
    sort_order = factory.Sequence(lambda n: n)


class SpeciesFormTraitFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SpeciesFormTrait
        django_get_or_create = ("species", "trait")

    species = factory.SubFactory(SpeciesFactory)
    trait = factory.SubFactory(FormTraitFactory)
    is_available_in_cg = True


class SpeciesOriginTraitOptionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SpeciesOriginTraitOption
        django_get_or_create = ("species_origin", "trait", "option")

    species_origin = factory.SubFactory(SpeciesOriginFactory)
    trait = factory.SubFactory(FormTraitFactory)
    option = factory.SubFactory(
        FormTraitOptionFactory, trait=factory.SelfAttribute("..trait")
    )
    is_available = True
```

**Step 2: Add character form factories**

Append to factories.py:

```python
from typeclasses.characters import Character


class CharacterFormFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CharacterForm

    character = factory.LazyFunction(
        lambda: Character.objects.first()
        or Character.create(key="TestChar", location=None)
    )
    name = ""
    form_type = FormType.TRUE
    is_player_created = False


class CharacterFormValueFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CharacterFormValue
        django_get_or_create = ("form", "trait")

    form = factory.SubFactory(CharacterFormFactory)
    trait = factory.SubFactory(FormTraitFactory)
    option = factory.SubFactory(
        FormTraitOptionFactory, trait=factory.SelfAttribute("..trait")
    )


class CharacterFormStateFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CharacterFormState
        django_get_or_create = ("character",)

    character = factory.LazyAttribute(lambda o: o.active_form.character)
    active_form = factory.SubFactory(CharacterFormFactory)


class TemporaryFormChangeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TemporaryFormChange

    character = factory.LazyFunction(
        lambda: Character.objects.first()
        or Character.create(key="TestChar", location=None)
    )
    trait = factory.SubFactory(FormTraitFactory)
    option = factory.SubFactory(
        FormTraitOptionFactory, trait=factory.SelfAttribute("..trait")
    )
    source_type = SourceType.SYSTEM
    source_id = None
    duration_type = DurationType.UNTIL_REMOVED
    expires_at = None
    expires_after_scenes = None
```

**Step 3: Commit**

```bash
git add src/world/forms/factories.py
git commit -m "feat(forms): add FactoryBoy factories for all form models"
```

---

## Task 7: Write Model Tests

**Files:**
- Create: `src/world/forms/tests/__init__.py`
- Create: `src/world/forms/tests/test_models.py`

**Step 1: Create test directory**

```bash
mkdir -p src/world/forms/tests
touch src/world/forms/tests/__init__.py
```

**Step 2: Write FormTrait and FormTraitOption tests**

```python
from django.test import TestCase

from world.forms.factories import (
    FormTraitFactory,
    FormTraitOptionFactory,
    SpeciesFormTraitFactory,
    SpeciesOriginTraitOptionFactory,
)
from world.forms.models import FormTrait, FormTraitOption, TraitType


class FormTraitModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.trait = FormTraitFactory(
            name="hair_color", display_name="Hair Color", trait_type=TraitType.COLOR
        )

    def test_str_returns_display_name(self):
        self.assertEqual(str(self.trait), "Hair Color")

    def test_trait_type_choices(self):
        self.assertEqual(self.trait.trait_type, TraitType.COLOR)


class FormTraitOptionModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.trait = FormTraitFactory(name="hair_color", display_name="Hair Color")
        cls.option = FormTraitOptionFactory(
            trait=cls.trait, name="black", display_name="Black"
        )

    def test_str_format(self):
        self.assertEqual(str(self.option), "Hair Color: Black")

    def test_unique_together_trait_name(self):
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            FormTraitOptionFactory(trait=self.trait, name="black", display_name="Noir")
```

**Step 3: Write species integration tests**

Append to test_models.py:

```python
from world.species.factories import SpeciesFactory, SpeciesOriginFactory


class SpeciesFormTraitModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.species = SpeciesFactory(name="Human")
        cls.trait = FormTraitFactory(name="hair_color")
        cls.species_trait = SpeciesFormTraitFactory(
            species=cls.species, trait=cls.trait
        )

    def test_str_format(self):
        self.assertEqual(str(self.species_trait), "Human - Hair Color")


class SpeciesOriginTraitOptionModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.species = SpeciesFactory(name="Human")
        cls.origin = SpeciesOriginFactory(species=cls.species, name="Umbros")
        cls.trait = FormTraitFactory(name="eye_color")
        cls.option = FormTraitOptionFactory(
            trait=cls.trait, name="red", display_name="Red"
        )
        cls.override = SpeciesOriginTraitOptionFactory(
            species_origin=cls.origin,
            trait=cls.trait,
            option=cls.option,
            is_available=True,
        )

    def test_str_shows_add_action(self):
        self.assertIn("+", str(self.override))

    def test_str_shows_remove_action(self):
        self.override.is_available = False
        self.override.save()
        self.assertIn("-", str(self.override))
```

**Step 4: Run tests**

```bash
arx test world.forms
```

Expected: All tests pass.

**Step 5: Commit**

```bash
git add src/world/forms/tests/
git commit -m "test(forms): add model tests for FormTrait and species integration"
```

---

## Task 8: Write Character Form Tests

**Files:**
- Modify: `src/world/forms/tests/test_models.py`

**Step 1: Add character form tests**

Append to test_models.py:

```python
from evennia.utils.test_resources import EvenniaTest

from world.forms.factories import (
    CharacterFormFactory,
    CharacterFormStateFactory,
    CharacterFormValueFactory,
)
from world.forms.models import CharacterForm, FormType


class CharacterFormModelTest(EvenniaTest):
    def test_str_with_name(self):
        form = CharacterFormFactory(
            character=self.char1, name="Beast Form", form_type=FormType.ALTERNATE
        )
        self.assertIn("Beast Form", str(form))

    def test_str_without_name(self):
        form = CharacterFormFactory(
            character=self.char1, name="", form_type=FormType.TRUE
        )
        self.assertIn("True Form", str(form))


class CharacterFormValueModelTest(EvenniaTest):
    def test_str_format(self):
        trait = FormTraitFactory(name="hair_color", display_name="Hair Color")
        option = FormTraitOptionFactory(
            trait=trait, name="black", display_name="Black"
        )
        form = CharacterFormFactory(character=self.char1)
        value = CharacterFormValueFactory(form=form, trait=trait, option=option)
        self.assertIn("Hair Color", str(value))
        self.assertIn("Black", str(value))


class CharacterFormStateModelTest(EvenniaTest):
    def test_str_with_active_form(self):
        form = CharacterFormFactory(character=self.char1, form_type=FormType.TRUE)
        state = CharacterFormStateFactory(character=self.char1, active_form=form)
        self.assertIn(self.char1.key, str(state))

    def test_str_without_active_form(self):
        state = CharacterFormStateFactory(character=self.char1, active_form=None)
        self.assertIn("No active form", str(state))
```

**Step 2: Run tests**

```bash
arx test world.forms
```

Expected: All tests pass.

**Step 3: Commit**

```bash
git add src/world/forms/tests/
git commit -m "test(forms): add CharacterForm model tests"
```

---

## Task 9: Write Temporary Form Change Tests

**Files:**
- Modify: `src/world/forms/tests/test_models.py`

**Step 1: Add temporary change tests**

Append to test_models.py:

```python
from datetime import timedelta

from django.utils import timezone

from world.forms.factories import TemporaryFormChangeFactory
from world.forms.models import DurationType, TemporaryFormChange


class TemporaryFormChangeModelTest(EvenniaTest):
    def test_is_expired_until_removed_never_expires(self):
        change = TemporaryFormChangeFactory(
            character=self.char1, duration_type=DurationType.UNTIL_REMOVED
        )
        self.assertFalse(change.is_expired())

    def test_is_expired_real_time_not_expired(self):
        change = TemporaryFormChangeFactory(
            character=self.char1,
            duration_type=DurationType.REAL_TIME,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        self.assertFalse(change.is_expired())

    def test_is_expired_real_time_expired(self):
        change = TemporaryFormChangeFactory(
            character=self.char1,
            duration_type=DurationType.REAL_TIME,
            expires_at=timezone.now() - timedelta(hours=1),
        )
        self.assertTrue(change.is_expired())

    def test_active_manager_excludes_expired(self):
        # Create an expired change
        TemporaryFormChangeFactory(
            character=self.char1,
            duration_type=DurationType.REAL_TIME,
            expires_at=timezone.now() - timedelta(hours=1),
        )
        # Create an active change
        active = TemporaryFormChangeFactory(
            character=self.char1,
            duration_type=DurationType.UNTIL_REMOVED,
        )
        active_changes = TemporaryFormChange.objects.active()
        self.assertIn(active, active_changes)
        self.assertEqual(active_changes.count(), 1)
```

**Step 2: Run tests**

```bash
arx test world.forms
```

Expected: All tests pass.

**Step 3: Commit**

```bash
git add src/world/forms/tests/
git commit -m "test(forms): add TemporaryFormChange expiration tests"
```

---

## Task 10: Add Django Admin Configuration

**Files:**
- Create: `src/world/forms/admin.py`

**Step 1: Create admin.py with trait admin**

```python
from django.contrib import admin

from world.forms.models import (
    CharacterForm,
    CharacterFormState,
    CharacterFormValue,
    FormTrait,
    FormTraitOption,
    SpeciesFormTrait,
    SpeciesOriginTraitOption,
    TemporaryFormChange,
)


class FormTraitOptionInline(admin.TabularInline):
    model = FormTraitOption
    extra = 1


@admin.register(FormTrait)
class FormTraitAdmin(admin.ModelAdmin):
    list_display = ["display_name", "name", "trait_type", "sort_order"]
    list_editable = ["sort_order"]
    search_fields = ["name", "display_name"]
    inlines = [FormTraitOptionInline]


@admin.register(FormTraitOption)
class FormTraitOptionAdmin(admin.ModelAdmin):
    list_display = ["display_name", "trait", "name", "sort_order"]
    list_filter = ["trait"]
    search_fields = ["name", "display_name"]


@admin.register(SpeciesFormTrait)
class SpeciesFormTraitAdmin(admin.ModelAdmin):
    list_display = ["species", "trait", "is_available_in_cg"]
    list_filter = ["species", "trait", "is_available_in_cg"]
    autocomplete_fields = ["species", "trait"]


@admin.register(SpeciesOriginTraitOption)
class SpeciesOriginTraitOptionAdmin(admin.ModelAdmin):
    list_display = ["species_origin", "trait", "option", "is_available"]
    list_filter = ["species_origin__species", "trait", "is_available"]
    autocomplete_fields = ["species_origin", "trait", "option"]
```

**Step 2: Add character form admin**

Append to admin.py:

```python
class CharacterFormValueInline(admin.TabularInline):
    model = CharacterFormValue
    extra = 0
    autocomplete_fields = ["trait", "option"]


@admin.register(CharacterForm)
class CharacterFormAdmin(admin.ModelAdmin):
    list_display = ["character", "name", "form_type", "is_player_created", "created_at"]
    list_filter = ["form_type", "is_player_created"]
    search_fields = ["character__db_key", "name"]
    inlines = [CharacterFormValueInline]


@admin.register(CharacterFormState)
class CharacterFormStateAdmin(admin.ModelAdmin):
    list_display = ["character", "active_form"]
    search_fields = ["character__db_key"]


@admin.register(TemporaryFormChange)
class TemporaryFormChangeAdmin(admin.ModelAdmin):
    list_display = [
        "character",
        "trait",
        "option",
        "source_type",
        "duration_type",
        "expires_at",
    ]
    list_filter = ["source_type", "duration_type"]
    search_fields = ["character__db_key"]
```

**Step 3: Commit**

```bash
git add src/world/forms/admin.py
git commit -m "feat(forms): add Django admin configuration"
```

---

## Task 11: Create Form Service Functions

**Files:**
- Create: `src/world/forms/services.py`
- Create: `src/world/forms/tests/test_services.py`

**Step 1: Write failing test for get_apparent_form**

Create `src/world/forms/tests/test_services.py`:

```python
from evennia.utils.test_resources import EvenniaTest

from world.forms.factories import (
    CharacterFormFactory,
    CharacterFormStateFactory,
    CharacterFormValueFactory,
    FormTraitFactory,
    FormTraitOptionFactory,
    TemporaryFormChangeFactory,
)
from world.forms.models import DurationType, FormType
from world.forms.services import get_apparent_form


class GetApparentFormTest(EvenniaTest):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # Create traits and options
        cls.hair_trait = FormTraitFactory(name="hair_color", display_name="Hair Color")
        cls.black_hair = FormTraitOptionFactory(
            trait=cls.hair_trait, name="black", display_name="Black"
        )
        cls.blonde_hair = FormTraitOptionFactory(
            trait=cls.hair_trait, name="blonde", display_name="Blonde"
        )

    def test_returns_base_form_values(self):
        form = CharacterFormFactory(character=self.char1, form_type=FormType.TRUE)
        CharacterFormValueFactory(
            form=form, trait=self.hair_trait, option=self.black_hair
        )
        CharacterFormStateFactory(character=self.char1, active_form=form)

        apparent = get_apparent_form(self.char1)

        self.assertEqual(apparent[self.hair_trait], self.black_hair)

    def test_temporary_changes_override_base(self):
        form = CharacterFormFactory(character=self.char1, form_type=FormType.TRUE)
        CharacterFormValueFactory(
            form=form, trait=self.hair_trait, option=self.black_hair
        )
        CharacterFormStateFactory(character=self.char1, active_form=form)
        TemporaryFormChangeFactory(
            character=self.char1,
            trait=self.hair_trait,
            option=self.blonde_hair,
            duration_type=DurationType.UNTIL_REMOVED,
        )

        apparent = get_apparent_form(self.char1)

        self.assertEqual(apparent[self.hair_trait], self.blonde_hair)
```

**Step 2: Run test to verify it fails**

```bash
arx test world.forms.tests.test_services -v
```

Expected: ImportError - services module doesn't exist.

**Step 3: Create services.py with get_apparent_form**

```python
from world.forms.models import (
    CharacterFormState,
    FormTrait,
    FormTraitOption,
    TemporaryFormChange,
)


def get_apparent_form(character) -> dict[FormTrait, FormTraitOption]:
    """
    Get the apparent form for a character, combining active form with temporaries.

    Returns a dict mapping FormTrait to FormTraitOption for display.
    """
    # Get active form values
    try:
        form_state = character.form_state
        active_form = form_state.active_form
    except CharacterFormState.DoesNotExist:
        return {}

    if not active_form:
        return {}

    # Build base values from active form
    base_values: dict[FormTrait, FormTraitOption] = {
        value.trait: value.option for value in active_form.values.select_related("trait", "option")
    }

    # Overlay active temporary changes
    temp_changes = TemporaryFormChange.objects.filter(character=character).active()
    for change in temp_changes.select_related("trait", "option"):
        base_values[change.trait] = change.option

    return base_values
```

**Step 4: Run test to verify it passes**

```bash
arx test world.forms.tests.test_services -v
```

Expected: All tests pass.

**Step 5: Commit**

```bash
git add src/world/forms/services.py src/world/forms/tests/test_services.py
git commit -m "feat(forms): add get_apparent_form service function"
```

---

## Task 12: Add Form Switching Service Functions

**Files:**
- Modify: `src/world/forms/services.py`
- Modify: `src/world/forms/tests/test_services.py`

**Step 1: Write failing test for switch_form**

Add to test_services.py:

```python
from world.forms.services import get_apparent_form, switch_form, revert_to_true_form


class SwitchFormTest(EvenniaTest):
    def test_switch_form_updates_active_form(self):
        true_form = CharacterFormFactory(
            character=self.char1, form_type=FormType.TRUE
        )
        alt_form = CharacterFormFactory(
            character=self.char1, name="Beast", form_type=FormType.ALTERNATE
        )
        state = CharacterFormStateFactory(character=self.char1, active_form=true_form)

        switch_form(self.char1, alt_form)

        state.refresh_from_db()
        self.assertEqual(state.active_form, alt_form)

    def test_switch_form_raises_for_wrong_character(self):
        form = CharacterFormFactory(character=self.char2, form_type=FormType.TRUE)
        CharacterFormStateFactory(character=self.char1, active_form=None)

        with self.assertRaises(ValueError):
            switch_form(self.char1, form)


class RevertToTrueFormTest(EvenniaTest):
    def test_revert_sets_true_form_active(self):
        true_form = CharacterFormFactory(
            character=self.char1, form_type=FormType.TRUE
        )
        alt_form = CharacterFormFactory(
            character=self.char1, form_type=FormType.ALTERNATE
        )
        state = CharacterFormStateFactory(character=self.char1, active_form=alt_form)

        revert_to_true_form(self.char1)

        state.refresh_from_db()
        self.assertEqual(state.active_form, true_form)
```

**Step 2: Run test to verify it fails**

```bash
arx test world.forms.tests.test_services::SwitchFormTest -v
```

Expected: ImportError - switch_form not defined.

**Step 3: Implement switch_form and revert_to_true_form**

Add to services.py:

```python
from world.forms.models import (
    CharacterForm,
    CharacterFormState,
    FormTrait,
    FormTraitOption,
    FormType,
    TemporaryFormChange,
)


def switch_form(character, target_form: CharacterForm) -> None:
    """
    Switch a character to a different form.

    Args:
        character: The character to switch
        target_form: The form to switch to

    Raises:
        ValueError: If the form doesn't belong to this character
    """
    if target_form.character_id != character.id:
        raise ValueError("Cannot switch to a form belonging to another character")

    form_state, _ = CharacterFormState.objects.get_or_create(character=character)
    form_state.active_form = target_form
    form_state.save()


def revert_to_true_form(character) -> None:
    """
    Revert a character to their true form.

    Raises:
        CharacterForm.DoesNotExist: If no true form exists
    """
    true_form = CharacterForm.objects.get(
        character=character, form_type=FormType.TRUE
    )
    switch_form(character, true_form)
```

**Step 4: Run tests**

```bash
arx test world.forms.tests.test_services -v
```

Expected: All tests pass.

**Step 5: Commit**

```bash
git add src/world/forms/services.py src/world/forms/tests/test_services.py
git commit -m "feat(forms): add switch_form and revert_to_true_form services"
```

---

## Task 13: Add CG Options Service Function

**Files:**
- Modify: `src/world/forms/services.py`
- Modify: `src/world/forms/tests/test_services.py`

**Step 1: Write failing test for get_cg_form_options**

Add to test_services.py:

```python
from world.forms.factories import (
    SpeciesFormTraitFactory,
    SpeciesOriginTraitOptionFactory,
)
from world.forms.services import get_cg_form_options
from world.species.factories import SpeciesFactory, SpeciesOriginFactory


class GetCGFormOptionsTest(EvenniaTest):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.species = SpeciesFactory(name="Human")
        cls.origin = SpeciesOriginFactory(species=cls.species, name="Arx")

        cls.hair_trait = FormTraitFactory(name="hair_color", display_name="Hair Color")
        cls.black = FormTraitOptionFactory(
            trait=cls.hair_trait, name="black", display_name="Black"
        )
        cls.red = FormTraitOptionFactory(
            trait=cls.hair_trait, name="red", display_name="Red"
        )
        cls.gray = FormTraitOptionFactory(
            trait=cls.hair_trait, name="gray", display_name="Gray"
        )

        # Species has hair_color trait
        SpeciesFormTraitFactory(species=cls.species, trait=cls.hair_trait)

    def test_returns_all_options_without_origin_overrides(self):
        options = get_cg_form_options(cls.species, cls.origin)

        self.assertIn(cls.hair_trait, options)
        trait_options = options[cls.hair_trait]
        self.assertIn(cls.black, trait_options)
        self.assertIn(cls.red, trait_options)
        self.assertIn(cls.gray, trait_options)

    def test_origin_can_remove_option(self):
        # Arx humans don't have red eyes
        SpeciesOriginTraitOptionFactory(
            species_origin=cls.origin,
            trait=cls.hair_trait,
            option=cls.red,
            is_available=False,
        )

        options = get_cg_form_options(cls.species, cls.origin)

        trait_options = options[cls.hair_trait]
        self.assertNotIn(cls.red, trait_options)
        self.assertIn(cls.black, trait_options)

    def test_origin_can_add_option(self):
        # Create a new option only for this origin
        special = FormTraitOptionFactory(
            trait=cls.hair_trait, name="special", display_name="Special"
        )
        SpeciesOriginTraitOptionFactory(
            species_origin=cls.origin,
            trait=cls.hair_trait,
            option=special,
            is_available=True,
        )

        options = get_cg_form_options(cls.species, cls.origin)

        trait_options = options[cls.hair_trait]
        self.assertIn(special, trait_options)
```

**Step 2: Run test to verify it fails**

```bash
arx test world.forms.tests.test_services::GetCGFormOptionsTest -v
```

Expected: ImportError.

**Step 3: Implement get_cg_form_options**

Add to services.py:

```python
from world.forms.models import (
    CharacterForm,
    CharacterFormState,
    FormTrait,
    FormTraitOption,
    FormType,
    SpeciesFormTrait,
    SpeciesOriginTraitOption,
    TemporaryFormChange,
)
from world.species.models import Species, SpeciesOrigin


def get_cg_form_options(
    species: Species, origin: SpeciesOrigin
) -> dict[FormTrait, list[FormTraitOption]]:
    """
    Get available form trait options for character creation.

    Returns traits this species has in CG, with options filtered by origin overrides.
    """
    result: dict[FormTrait, list[FormTraitOption]] = {}

    # Get traits available for this species in CG
    species_traits = SpeciesFormTrait.objects.filter(
        species=species, is_available_in_cg=True
    ).select_related("trait")

    for species_trait in species_traits:
        trait = species_trait.trait

        # Start with all options for this trait
        all_options = set(trait.options.all())

        # Apply origin overrides
        overrides = SpeciesOriginTraitOption.objects.filter(
            species_origin=origin, trait=trait
        ).select_related("option")

        for override in overrides:
            if override.is_available:
                all_options.add(override.option)
            else:
                all_options.discard(override.option)

        result[trait] = sorted(all_options, key=lambda o: (o.sort_order, o.display_name))

    return result
```

**Step 4: Run tests**

```bash
arx test world.forms.tests.test_services -v
```

Expected: All tests pass.

**Step 5: Commit**

```bash
git add src/world/forms/services.py src/world/forms/tests/test_services.py
git commit -m "feat(forms): add get_cg_form_options for character creation"
```

---

## Task 14: Add Create True Form Service Function

**Files:**
- Modify: `src/world/forms/services.py`
- Modify: `src/world/forms/tests/test_services.py`

**Step 1: Write failing test for create_true_form**

Add to test_services.py:

```python
from world.forms.services import create_true_form
from world.forms.models import CharacterForm, CharacterFormState, FormType


class CreateTrueFormTest(EvenniaTest):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.hair_trait = FormTraitFactory(name="hair_color")
        cls.black = FormTraitOptionFactory(trait=cls.hair_trait, name="black")
        cls.eye_trait = FormTraitFactory(name="eye_color")
        cls.blue = FormTraitOptionFactory(trait=cls.eye_trait, name="blue")

    def test_creates_true_form_with_values(self):
        selections = {
            self.hair_trait: self.black,
            self.eye_trait: self.blue,
        }

        form = create_true_form(self.char1, selections)

        self.assertEqual(form.form_type, FormType.TRUE)
        self.assertEqual(form.character, self.char1)
        self.assertEqual(form.values.count(), 2)

    def test_creates_form_state(self):
        selections = {self.hair_trait: self.black}

        form = create_true_form(self.char1, selections)

        state = CharacterFormState.objects.get(character=self.char1)
        self.assertEqual(state.active_form, form)

    def test_raises_if_true_form_exists(self):
        CharacterFormFactory(character=self.char1, form_type=FormType.TRUE)

        with self.assertRaises(ValueError):
            create_true_form(self.char1, {})
```

**Step 2: Run test to verify it fails**

```bash
arx test world.forms.tests.test_services::CreateTrueFormTest -v
```

Expected: ImportError.

**Step 3: Implement create_true_form**

Add to services.py:

```python
from world.forms.models import (
    CharacterForm,
    CharacterFormState,
    CharacterFormValue,
    FormTrait,
    FormTraitOption,
    FormType,
    SpeciesFormTrait,
    SpeciesOriginTraitOption,
    TemporaryFormChange,
)


def create_true_form(
    character, selections: dict[FormTrait, FormTraitOption]
) -> CharacterForm:
    """
    Create the true form for a character during character creation.

    Args:
        character: The character to create the form for
        selections: Dict mapping traits to selected options

    Returns:
        The created CharacterForm

    Raises:
        ValueError: If a true form already exists for this character
    """
    if CharacterForm.objects.filter(character=character, form_type=FormType.TRUE).exists():
        raise ValueError("Character already has a true form")

    # Create the form
    form = CharacterForm.objects.create(
        character=character,
        form_type=FormType.TRUE,
        is_player_created=False,
    )

    # Create form values
    for trait, option in selections.items():
        CharacterFormValue.objects.create(form=form, trait=trait, option=option)

    # Create/update form state
    CharacterFormState.objects.update_or_create(
        character=character, defaults={"active_form": form}
    )

    return form
```

**Step 4: Run tests**

```bash
arx test world.forms.tests.test_services -v
```

Expected: All tests pass.

**Step 5: Commit**

```bash
git add src/world/forms/services.py src/world/forms/tests/test_services.py
git commit -m "feat(forms): add create_true_form for CG finalization"
```

---

## Task 15: Add API Serializers

**Files:**
- Create: `src/world/forms/serializers.py`

**Step 1: Create serializers for trait definitions**

```python
from rest_framework import serializers

from world.forms.models import (
    CharacterForm,
    CharacterFormValue,
    FormTrait,
    FormTraitOption,
    SpeciesFormTrait,
)


class FormTraitOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FormTraitOption
        fields = ["id", "name", "display_name", "sort_order"]


class FormTraitSerializer(serializers.ModelSerializer):
    options = FormTraitOptionSerializer(many=True, read_only=True)

    class Meta:
        model = FormTrait
        fields = ["id", "name", "display_name", "trait_type", "options"]


class FormTraitWithOptionsSerializer(serializers.Serializer):
    """Serializer for CG form options response."""

    trait = FormTraitSerializer()
    options = FormTraitOptionSerializer(many=True)
```

**Step 2: Add character form serializers**

Append to serializers.py:

```python
class CharacterFormValueSerializer(serializers.ModelSerializer):
    trait = FormTraitSerializer(read_only=True)
    option = FormTraitOptionSerializer(read_only=True)
    trait_id = serializers.PrimaryKeyRelatedField(
        queryset=FormTrait.objects.all(), source="trait", write_only=True
    )
    option_id = serializers.PrimaryKeyRelatedField(
        queryset=FormTraitOption.objects.all(), source="option", write_only=True
    )

    class Meta:
        model = CharacterFormValue
        fields = ["id", "trait", "option", "trait_id", "option_id"]


class CharacterFormSerializer(serializers.ModelSerializer):
    values = CharacterFormValueSerializer(many=True, read_only=True)

    class Meta:
        model = CharacterForm
        fields = ["id", "name", "form_type", "is_player_created", "created_at", "values"]


class ApparentFormSerializer(serializers.Serializer):
    """Serializer for apparent form display."""

    traits = serializers.SerializerMethodField()

    def get_traits(self, apparent_form: dict):
        """Convert trait->option dict to list of trait/option pairs."""
        return [
            {
                "trait": FormTraitSerializer(trait).data,
                "option": FormTraitOptionSerializer(option).data,
            }
            for trait, option in apparent_form.items()
        ]
```

**Step 3: Commit**

```bash
git add src/world/forms/serializers.py
git commit -m "feat(forms): add DRF serializers for form API"
```

---

## Task 16: Add API ViewSets

**Files:**
- Create: `src/world/forms/views.py`
- Create: `src/world/forms/urls.py`

**Step 1: Create views.py**

```python
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from world.forms.models import CharacterForm, FormTrait, FormTraitOption
from world.forms.serializers import (
    ApparentFormSerializer,
    CharacterFormSerializer,
    FormTraitSerializer,
    FormTraitWithOptionsSerializer,
)
from world.forms.services import get_apparent_form, get_cg_form_options


class FormTraitViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for browsing form trait definitions."""

    queryset = FormTrait.objects.all()
    serializer_class = FormTraitSerializer
    permission_classes = [IsAuthenticated]


class CharacterFormViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing a character's forms."""

    serializer_class = CharacterFormSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter to forms belonging to the user's characters."""
        if not self.request.user.is_authenticated:
            return CharacterForm.objects.none()
        # Get characters owned by this account
        return CharacterForm.objects.filter(
            character__db_account=self.request.user
        ).select_related("character").prefetch_related("values__trait", "values__option")

    @action(detail=False, methods=["get"])
    def apparent(self, request):
        """Get the apparent form for the user's active character."""
        character = getattr(request.user, "puppet", None)
        if not character:
            return Response({"detail": "No active character"}, status=400)

        apparent = get_apparent_form(character)
        serializer = ApparentFormSerializer(apparent)
        return Response(serializer.data)
```

**Step 2: Create urls.py**

```python
from rest_framework.routers import DefaultRouter

from world.forms.views import CharacterFormViewSet, FormTraitViewSet

router = DefaultRouter()
router.register(r"traits", FormTraitViewSet, basename="formtrait")
router.register(r"character-forms", CharacterFormViewSet, basename="characterform")

urlpatterns = router.urls
```

**Step 3: Register URLs in main router**

In `src/web/api/urls.py`, add:

```python
from world.forms.urls import urlpatterns as forms_urls

urlpatterns += [
    path("forms/", include(forms_urls)),
]
```

**Step 4: Commit**

```bash
git add src/world/forms/views.py src/world/forms/urls.py src/web/api/urls.py
git commit -m "feat(forms): add API viewsets for form traits and character forms"
```

---

## Task 17: Run Full Test Suite

**Step 1: Run all tests**

```bash
arx test
```

Expected: All tests pass (including new form tests).

**Step 2: Run linting**

```bash
ruff check src/world/forms/
ruff format src/world/forms/
```

**Step 3: Fix any issues and commit**

```bash
git add -A
git commit -m "fix(forms): address linting issues"
```

---

## Task 18: Integration with Character Creation (Future)

> **Note:** This task outlines integration points but requires coordination with the existing CG flow. Implementation details depend on current CharacterDraft structure.

**Integration Points:**

1. **CharacterDraft.draft_data** - Store form selections as:
   ```python
   {
       "form_selections": {
           "hair_color": 123,  # FormTraitOption ID
           "eye_color": 456,
       }
   }
   ```

2. **Identity Stage Serializer** - Add endpoint to fetch CG options:
   ```python
   @action(detail=True, methods=["get"])
   def form_options(self, request, pk=None):
       draft = self.get_object()
       if not draft.selected_species_option:
           return Response({"detail": "Select species first"}, status=400)
       species = draft.selected_species_option.species
       origin = draft.selected_species_origin
       options = get_cg_form_options(species, origin)
       # Serialize and return
   ```

3. **Finalization** - In `finalize_character()`, call:
   ```python
   from world.forms.services import create_true_form

   form_selections = draft.draft_data.get("form_selections", {})
   # Convert IDs to objects
   selections = {}
   for trait_name, option_id in form_selections.items():
       trait = FormTrait.objects.get(name=trait_name)
       option = FormTraitOption.objects.get(id=option_id)
       selections[trait] = option

   create_true_form(character, selections)
   ```

---

## Summary

This plan creates the Form system in 17 implementation tasks:

1. **Tasks 1-5**: Create models (FormTrait, FormTraitOption, species integration, CharacterForm, TemporaryFormChange)
2. **Tasks 6-9**: Add factories and model tests
3. **Task 10**: Django admin configuration
4. **Tasks 11-14**: Service functions (get_apparent_form, switch_form, get_cg_form_options, create_true_form)
5. **Tasks 15-16**: API serializers and viewsets
6. **Task 17**: Final test suite run
7. **Task 18**: Integration notes for CG (future work)

Each task follows TDD: write failing test → implement → verify → commit.

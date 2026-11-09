"""Shared pieces of the item template authoring pages (#5041).

The all-kinds ``ItemTemplateAdmin`` and the four family pages (weapon, armor, shield,
clothing and jewelry) all build from these: the inline sections, the form hooks #5026
added, and what makes a family page a family page. This is not an admin module (it
registers nothing), so admin modules import from here and never from each other.

Every inline opens with no rows (``extra = 0``): staff add a row with "Add another"
instead of deleting blank ones they never asked for.
"""

from typing import Any

from django.contrib import admin
from django.contrib.auth import get_permission_codename
from django.db.models import Field, ManyToManyField, QuerySet
from django.forms import (
    CheckboxSelectMultiple,
    Field as FormField,
    ModelMultipleChoiceField,
    TypedChoiceField,
)
from django.http import HttpRequest

from world.admin_utils import OneRowPerFormSet
from world.items.constants import GearArchetype
from world.items.models import (
    DisguiseKitEffect,
    GarmentMitigation,
    ItemCheckModifier,
    ItemTemplateAppearanceEffect,
    ItemTemplateProperty,
    TemplateInteraction,
    TemplateSlot,
)


class TemplateSlotInline(admin.TabularInline):
    model = TemplateSlot
    formset = OneRowPerFormSet
    extra = 0


class TemplateInteractionInline(admin.TabularInline):
    model = TemplateInteraction
    formset = OneRowPerFormSet
    extra = 0


class ItemTemplateAppearanceEffectInline(admin.TabularInline):
    model = ItemTemplateAppearanceEffect
    formset = OneRowPerFormSet
    extra = 0
    autocomplete_fields = ["trait", "target_option"]
    verbose_name = "Appearance Effect"
    verbose_name_plural = "Appearance Effects"


class DisguiseKitEffectInline(admin.TabularInline):
    model = DisguiseKitEffect
    extra = 0
    verbose_name = "Disguise Kit Effect"
    verbose_name_plural = "Disguise Kit Effects"


class GarmentMitigationInline(admin.TabularInline):
    model = GarmentMitigation
    formset = OneRowPerFormSet
    extra = 0
    raw_id_fields = ["resonance"]


class ItemCheckModifierInline(admin.TabularInline):
    model = ItemCheckModifier
    formset = OneRowPerFormSet
    extra = 0
    autocomplete_fields = ["check_type"]
    verbose_name = "Check Modifier"
    verbose_name_plural = "Check Modifiers"


class ItemTemplatePropertyInline(admin.TabularInline):
    model = ItemTemplateProperty
    formset = OneRowPerFormSet
    extra = 0
    autocomplete_fields = ["property"]
    verbose_name = "Default Property"
    verbose_name_plural = "Default Properties"


class ItemTemplateAdminBase(admin.ModelAdmin):
    """The field widgets and labels every item template page shares (#5026)."""

    def formfield_for_manytomany(
        self, db_field: ManyToManyField, request: HttpRequest, **kwargs: Any
    ) -> ModelMultipleChoiceField | None:
        """The damage types armor also stops show as checkboxes (#5026): a short list, with
        Physical left out, since every piece of armor stops it."""
        if db_field.name == "also_protects_against":  # noqa: STRING_LITERAL - admin hook field name
            from world.conditions.models import DamageType  # noqa: PLC0415
            from world.vitals.services import get_vitals_consequence_config  # noqa: PLC0415

            kwargs["widget"] = CheckboxSelectMultiple
            kwargs["queryset"] = DamageType.objects.exclude(
                pk=get_vitals_consequence_config().physical_damage_type_id
            )
        return super().formfield_for_manytomany(db_field, request, **kwargs)

    def formfield_for_dbfield(
        self, db_field: Field, request: HttpRequest, **kwargs: Any
    ) -> FormField | None:
        """Staff read the throwable flag as the demo names it (#5026)."""
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "can_be_thrown" and formfield is not None:  # noqa: STRING_LITERAL - field name
            formfield.label = "Can also be thrown"
        return formfield


class FamilyGearArchetypeFilter(admin.SimpleListFilter):
    """The gear archetype list filter on a family page, offering only that family's kinds."""

    title = "gear archetype"
    parameter_name = "gear_archetype"

    def lookups(self, request: HttpRequest, model_admin: admin.ModelAdmin) -> list[tuple[str, str]]:  # noqa: ARG002
        return [(kind, GearArchetype(kind).label) for kind in model_admin.model.family_kinds]

    def queryset(self, request: HttpRequest, queryset: QuerySet) -> QuerySet:  # noqa: ARG002
        if self.value():
            return queryset.filter(gear_archetype=self.value())
        return queryset


class ItemTemplateFamilyAdminBase(ItemTemplateAdminBase):
    """What makes an admin a family authoring page (#5041).

    Its model is an ``ItemTemplate`` family proxy. The gear archetype picker offers only
    the family's kinds, with no preselected default, so a new template is never saved
    with a kind from another family by accident. Permissions are ``ItemTemplate``'s, so
    staff who can author item templates can use every family page without new grants.
    """

    def formfield_for_dbfield(
        self, db_field: Field, request: HttpRequest, **kwargs: Any
    ) -> FormField | None:
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "gear_archetype" and isinstance(formfield, TypedChoiceField):  # noqa: STRING_LITERAL - field name
            kinds = self.model.family_kinds
            formfield.choices = [
                ("", "---------"),
                *((kind, GearArchetype(kind).label) for kind in kinds),
            ]
        return formfield

    def get_changeform_initial_data(self, request: HttpRequest) -> dict[str, Any]:
        """A new family template starts with no gear archetype picked, never Other."""
        initial = super().get_changeform_initial_data(request)
        initial.setdefault("gear_archetype", "")
        return initial

    def _has_item_template_perm(self, request: HttpRequest, action: str) -> bool:
        opts = self.model._meta.concrete_model._meta  # noqa: SLF001
        codename = get_permission_codename(action, opts)
        return request.user.has_perm(f"{opts.app_label}.{codename}")

    # The ``obj`` argument is Django's hook signature; the grant is per model, not per row.
    def has_view_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ARG002
        return self._has_item_template_perm(request, "view") or self._has_item_template_perm(
            request, "change"
        )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return self._has_item_template_perm(request, "add")

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ARG002
        return self._has_item_template_perm(request, "change")

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ARG002
        return self._has_item_template_perm(request, "delete")

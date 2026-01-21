from django import forms
from django.contrib import admin
from django.db.models import Count, Prefetch

from world.forms.models import (
    Build,
    CharacterForm,
    CharacterFormState,
    CharacterFormValue,
    FormTrait,
    FormTraitOption,
    HeightBand,
    SpeciesFormTrait,
    TemporaryFormChange,
)


@admin.register(HeightBand)
class HeightBandAdmin(admin.ModelAdmin):
    list_display = [
        "display_name",
        "name",
        "min_inches",
        "max_inches",
        "is_cg_selectable",
        "hide_build",
        "sort_order",
    ]
    list_editable = ["sort_order", "is_cg_selectable", "hide_build"]
    list_filter = ["is_cg_selectable", "hide_build"]
    search_fields = ["name", "display_name"]
    ordering = ["sort_order", "min_inches"]


@admin.register(Build)
class BuildAdmin(admin.ModelAdmin):
    list_display = [
        "display_name",
        "name",
        "weight_factor",
        "is_cg_selectable",
        "sort_order",
    ]
    list_editable = ["sort_order", "weight_factor", "is_cg_selectable"]
    list_filter = ["is_cg_selectable"]
    search_fields = ["name", "display_name"]
    ordering = ["sort_order"]


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
    list_display = [
        "display_name",
        "trait",
        "name",
        "height_modifier_inches",
        "sort_order",
    ]
    list_filter = ["trait"]
    list_editable = ["height_modifier_inches"]
    search_fields = ["name", "display_name", "trait__name", "trait__display_name"]
    ordering = ["trait__sort_order", "trait__name", "sort_order", "name"]

    change_list_template = "admin/forms/formtraitoption/change_list.html"

    def changelist_view(self, request, extra_context=None):
        """Add grouped options to context."""
        extra_context = extra_context or {}

        # Optimized query: prefetch options and annotate counts in 2 queries
        traits = (
            FormTrait.objects.prefetch_related(
                Prefetch(
                    "options",
                    queryset=FormTraitOption.objects.order_by("sort_order", "name"),
                )
            )
            .annotate(option_count=Count("options"))
            .order_by("sort_order", "name")
        )

        traits_with_options = [
            {"trait": t, "options": t.options.all(), "count": t.option_count} for t in traits
        ]

        extra_context["traits_with_options"] = traits_with_options
        return super().changelist_view(request, extra_context=extra_context)


class SpeciesFormTraitAdminForm(forms.ModelForm):
    """Form that filters allowed_options to only show options for the selected trait."""

    class Meta:
        model = SpeciesFormTrait
        fields = ["species", "trait", "is_available_in_cg", "allowed_options"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter allowed_options to only show options for the selected trait
        if self.instance and self.instance.pk and self.instance.trait_id:
            self.fields["allowed_options"].queryset = FormTraitOption.objects.filter(
                trait_id=self.instance.trait_id
            ).order_by("sort_order", "display_name")
        else:
            # For new entries, show nothing until trait is selected and saved
            self.fields["allowed_options"].queryset = FormTraitOption.objects.none()


@admin.register(SpeciesFormTrait)
class SpeciesFormTraitAdmin(admin.ModelAdmin):
    """Admin for Species Form Traits with trait-filtered options."""

    form = SpeciesFormTraitAdminForm
    list_display = ["species", "trait", "is_available_in_cg", "option_count"]
    list_filter = ["species", "trait", "is_available_in_cg"]
    list_select_related = ["species", "trait"]
    search_fields = ["species__name", "trait__display_name"]
    ordering = ["species__name", "trait__sort_order"]
    filter_horizontal = ["allowed_options"]
    fieldsets = [
        (None, {"fields": ["species", "trait", "is_available_in_cg"]}),
        (
            "Allowed Options",
            {
                "fields": ["allowed_options"],
                "description": (
                    "Leave empty = all options available for this trait. "
                    "Save after changing trait to update the options list below."
                ),
            },
        ),
    ]

    def option_count(self, obj):
        """Show count of allowed options (or 'All' if unrestricted)."""
        count = obj.allowed_options.count()
        return f"{count} selected" if count > 0 else "All"

    option_count.short_description = "Options"


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

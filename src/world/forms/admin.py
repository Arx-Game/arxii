from django import forms
from django.contrib import admin
from django.db.models import Count, Prefetch

from world.admin_utils import OneRowPerFormSet
from world.forms.models import (
    ActiveAlternateSelf,
    AlternateSelf,
    Build,
    CharacterForm,
    CharacterFormState,
    CharacterFormValue,
    FormCombatProfile,
    FormCombatProfileEffect,
    FormMarking,
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


#: The colour picker's script (#5241). It pairs a browser colour input with every
#: text input marked ``data-swatch``; see the file for why the field stays text.
SWATCH_WIDGET_JS = "admin/js/swatch_widget.js"
#: The model field the picker belongs to.
SWATCH_FIELD = "color_hex"


class SwatchFieldMixin:
    """Draws ``color_hex`` as a short text input the colour picker script pairs with.

    Shared by the option's own admin page and its inline on the trait page. Each of
    those also lists ``SWATCH_WIDGET_JS`` in its own ``Media``.
    """

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == SWATCH_FIELD:
            kwargs["widget"] = forms.TextInput(
                attrs={"data-swatch": "1", "size": 8, "placeholder": "#rrggbb"}
            )
        return super().formfield_for_dbfield(db_field, request, **kwargs)


class FormTraitOptionInline(SwatchFieldMixin, admin.TabularInline):
    model = FormTraitOption
    formset = OneRowPerFormSet
    extra = 1

    class Media:
        js = (SWATCH_WIDGET_JS,)


@admin.register(FormTrait)
class FormTraitAdmin(admin.ModelAdmin):
    list_display = ["display_name", "name", "trait_type", "sort_order"]
    list_editable = ["sort_order"]
    search_fields = ["name", "display_name"]
    inlines = [FormTraitOptionInline]


@admin.register(FormTraitOption)
class FormTraitOptionAdmin(SwatchFieldMixin, admin.ModelAdmin):
    class Media:
        js = (SWATCH_WIDGET_JS,)

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
                    to_attr="cached_options",
                )
            )
            .annotate(option_count=Count("options"))
            .order_by("sort_order", "name")
        )

        traits_with_options = [
            {"trait": t, "options": t.cached_options, "count": t.option_count} for t in traits
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
    formset = OneRowPerFormSet
    extra = 0
    autocomplete_fields = ["trait", "option"]


class FormMarkingInline(admin.TabularInline):
    model = FormMarking
    extra = 0


@admin.register(CharacterForm)
class CharacterFormAdmin(admin.ModelAdmin):
    autocomplete_fields = ["character"]
    list_display = ["character", "name", "form_type", "is_player_created", "created_at"]
    list_filter = ["form_type", "is_player_created"]
    search_fields = ["character__db_key", "name"]
    inlines = [CharacterFormValueInline, FormMarkingInline]


@admin.register(FormMarking)
class FormMarkingAdmin(admin.ModelAdmin):
    list_display = ["form", "name", "kind", "body_region", "source", "created_at"]
    list_filter = ["kind", "source", "body_region"]
    search_fields = ["name", "form__character__db_key"]


@admin.register(CharacterFormState)
class CharacterFormStateAdmin(admin.ModelAdmin):
    autocomplete_fields = ["applied_kit_instance", "character"]
    list_display = ["character", "active_form"]
    search_fields = ["character__db_key"]


class FormCombatProfileEffectInline(admin.TabularInline):
    model = FormCombatProfileEffect
    extra = 0
    autocomplete_fields = ["target"]


@admin.register(FormCombatProfile)
class FormCombatProfileAdmin(admin.ModelAdmin):
    list_display = ["form", "display_name"]
    search_fields = ["form__character__db_key", "display_name"]
    inlines = [FormCombatProfileEffectInline]


@admin.register(AlternateSelf)
class AlternateSelfAdmin(admin.ModelAdmin):
    list_display = [
        "character",
        "display_name",
        "form",
        "persona",
        "combat_profile",
        "resonance",
        "revert_kind",
        "has_thumbnail",
    ]
    list_filter = ["form__form_type", "resonance__affinity", "revert_kind"]
    search_fields = ["character__character__db_key", "display_name"]
    autocomplete_fields = [
        "character",
        "form",
        "persona",
        "combat_profile",
        "techniques",
        "resonance",
        "emergence_condition",
    ]
    # Ultimates only (limit_choices_to on the field), the widget WorshippedBeingAdmin and
    # CompanionArchetypeAdmin use for their ultimate_techniques (#4731).
    filter_horizontal = ["ultimate_techniques"]

    @admin.display(boolean=True, description="Has Thumbnail")
    def has_thumbnail(self, obj):
        return bool(obj.thumbnail)

    def save_model(self, request, obj, form, change):
        """A staff-set Thumbnail reaches the pose picture too (#4889).

        Room state reads this self's thumbnail and poses read its persona's text copy, so
        the persona's two fields are set with it, the way a player's pick sets them. The
        private copies the self and its persona held before are deleted when nothing else
        wears them, as a player's own replace does.
        """
        # A form field name, not a discriminator.
        thumbnail_changed = "thumbnail" in form.changed_data  # noqa: STRING_LITERAL
        previous_id = form.initial.get("thumbnail")
        super().save_model(request, obj, form, change)
        if not thumbnail_changed:
            return
        from evennia_extensions.models import Media  # noqa: PLC0415
        from world.scenes.constants import PersonaType  # noqa: PLC0415
        from world.scenes.face_services import (  # noqa: PLC0415
            delete_unused_face_copies,
            sync_persona_portrait,
        )

        replaced = [Media.objects.filter(pk=previous_id).first()] if previous_id else []
        if obj.persona_id is not None and obj.persona.persona_type != PersonaType.PRIMARY:
            replaced.append(obj.persona.thumbnail)
            sync_persona_portrait(obj.persona, obj.thumbnail)
        delete_unused_face_copies(replaced)


@admin.register(ActiveAlternateSelf)
class ActiveAlternateSelfAdmin(admin.ModelAdmin):
    list_display = [
        "character",
        "alternate_self",
        "assumed_at_audere",
        "return_form",
        "return_persona",
    ]
    search_fields = ["character__character__db_key"]
    autocomplete_fields = ["character", "alternate_self", "return_form", "return_persona"]


@admin.register(TemporaryFormChange)
class TemporaryFormChangeAdmin(admin.ModelAdmin):
    autocomplete_fields = ["character"]
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

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

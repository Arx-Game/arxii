"""
Mechanics System Admin

Admin configuration for game mechanics models.
"""

from django.contrib import admin

from world.mechanics.models import (
    Application,
    ApproachConsequence,
    ChallengeApproach,
    ChallengeCategory,
    ChallengeInstance,
    ChallengeTemplate,
    ChallengeTemplateConsequence,
    ChallengeTemplateProperty,
    CharacterModifier,
    ModifierCategory,
    ModifierSource,
    ModifierTarget,
    ObjectProperty,
    PrerequisiteType,
    Property,
    PropertyCategory,
    SituationChallengeLink,
    SituationInstance,
    SituationTemplate,
    TraitCapabilityDerivation,
)

DESCRIPTION_TRUNCATE_LENGTH = 50


@admin.register(ModifierCategory)
class ModifierCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "description_truncated", "display_order"]
    search_fields = ["name", "description"]
    ordering = ["display_order", "name"]
    list_editable = ["display_order"]

    @admin.display(description="Description")
    def description_truncated(self, obj):
        if obj.description and len(obj.description) > DESCRIPTION_TRUNCATE_LENGTH:
            return obj.description[:DESCRIPTION_TRUNCATE_LENGTH] + "..."
        return obj.description or ""


@admin.register(ModifierTarget)
class ModifierTargetAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "display_order", "is_active"]
    list_filter = ["category", "is_active"]
    search_fields = ["name", "description"]
    ordering = ["category__display_order", "display_order", "name"]
    list_editable = ["display_order", "is_active"]
    list_select_related = ["category"]


@admin.register(ModifierSource)
class ModifierSourceAdmin(admin.ModelAdmin):
    list_display = ["id", "get_source_type", "source_display"]
    list_filter = [
        ("distinction_effect", admin.EmptyFieldListFilter),
    ]
    raw_id_fields = ["distinction_effect", "character_distinction"]

    @admin.display(description="Type")
    def get_source_type(self, obj):
        # Use model property, capitalize for display
        return obj.source_type.capitalize()


@admin.register(CharacterModifier)
class CharacterModifierAdmin(admin.ModelAdmin):
    list_display = [
        "character_name",
        "get_modifier_target",
        "value",
        "source",
        "expires_at",
        "created_at",
    ]
    list_filter = [
        "target__category",
        ("expires_at", admin.EmptyFieldListFilter),
    ]
    search_fields = ["character__character__db_key"]
    list_select_related = [
        "character",
        "character__character",
        "target",
        "target__category",
        "source",
    ]
    raw_id_fields = ["character", "source"]
    readonly_fields = ["created_at"]

    @admin.display(description="Character")
    def character_name(self, obj):
        return obj.character.character.db_key

    @admin.display(description="Modifier Target")
    def get_modifier_target(self, obj):
        return obj.target.name


# ---------------------------------------------------------------------------
# Property / Application layer
# ---------------------------------------------------------------------------


@admin.register(PrerequisiteType)
class PrerequisiteTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "description"]
    search_fields = ["name"]


@admin.register(PropertyCategory)
class PropertyCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "display_order"]
    list_editable = ["display_order"]
    search_fields = ["name"]


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ["name", "category"]
    list_filter = ["category"]
    search_fields = ["name"]
    list_select_related = ["category"]


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ["name", "capability", "target_property", "required_effect_property"]
    list_filter = ["capability"]
    search_fields = ["name"]
    list_select_related = ["capability", "target_property", "required_effect_property"]


# ---------------------------------------------------------------------------
# Trait → Capability derivation
# ---------------------------------------------------------------------------


@admin.register(TraitCapabilityDerivation)
class TraitCapabilityDerivationAdmin(admin.ModelAdmin):
    list_display = ["trait", "capability", "base_value", "trait_multiplier"]
    list_filter = ["capability"]
    list_select_related = ["trait", "capability"]


# ---------------------------------------------------------------------------
# Challenge system
# ---------------------------------------------------------------------------


class ChallengeTemplateConsequenceInline(admin.TabularInline):
    model = ChallengeTemplateConsequence
    extra = 1


class ChallengeApproachInline(admin.TabularInline):
    model = ChallengeApproach
    extra = 1


class ApproachConsequenceInline(admin.TabularInline):
    model = ApproachConsequence
    extra = 1


@admin.register(ChallengeCategory)
class ChallengeCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "display_order"]
    list_editable = ["display_order"]


class ChallengeTemplatePropertyInline(admin.TabularInline):
    model = ChallengeTemplateProperty
    extra = 1


@admin.register(ChallengeTemplate)
class ChallengeTemplateAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "challenge_type", "severity", "discovery_type"]
    list_filter = ["category", "challenge_type", "discovery_type"]
    search_fields = ["name"]
    inlines = [
        ChallengeTemplatePropertyInline,
        ChallengeApproachInline,
        ChallengeTemplateConsequenceInline,
    ]


@admin.register(ChallengeApproach)
class ChallengeApproachAdmin(admin.ModelAdmin):
    list_display = ["challenge_template", "application", "check_type", "display_name"]
    list_filter = ["challenge_template"]
    list_select_related = ["challenge_template", "application", "check_type"]
    inlines = [ApproachConsequenceInline]


@admin.register(ChallengeTemplateConsequence)
class ChallengeTemplateConsequenceAdmin(admin.ModelAdmin):
    list_display = [
        "challenge_template",
        "consequence",
        "resolution_type",
    ]
    list_filter = ["challenge_template", "resolution_type"]
    list_select_related = ["challenge_template", "consequence"]


@admin.register(ObjectProperty)
class ObjectPropertyAdmin(admin.ModelAdmin):
    list_display = ["object", "property", "value", "created_at"]
    list_filter = ["property"]
    raw_id_fields = ["object", "source_condition", "source_challenge"]


# ---------------------------------------------------------------------------
# Situation system
# ---------------------------------------------------------------------------


class SituationChallengeLinkInline(admin.TabularInline):
    model = SituationChallengeLink
    fk_name = "situation_template"
    extra = 1


@admin.register(SituationTemplate)
class SituationTemplateAdmin(admin.ModelAdmin):
    list_display = ["name", "category"]
    list_filter = ["category"]
    search_fields = ["name"]
    inlines = [SituationChallengeLinkInline]


@admin.register(SituationInstance)
class SituationInstanceAdmin(admin.ModelAdmin):
    list_display = ["template", "location", "is_active", "created_at"]
    list_filter = ["is_active"]
    raw_id_fields = ["location", "created_by", "scene"]


@admin.register(ChallengeInstance)
class ChallengeInstanceAdmin(admin.ModelAdmin):
    list_display = ["template", "location", "is_active", "is_revealed"]
    list_filter = ["is_active", "is_revealed"]
    raw_id_fields = ["location", "situation_instance"]

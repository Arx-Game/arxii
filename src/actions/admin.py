"""Django admin registrations for actions app models."""

from django.contrib import admin

from actions.models import (
    ActionEnhancement,
    ActionTemplate,
    ActionTemplateGate,
    AddModifierConfig,
    ConditionOnCheckConfig,
    ConsequencePool,
    ConsequencePoolEntry,
    ModifyKwargsConfig,
    RemoveConditionOnCheckConfig,
)


class ConsequencePoolEntryInline(admin.TabularInline):
    model = ConsequencePoolEntry
    extra = 1
    raw_id_fields = ("consequence",)


@admin.register(ConsequencePool)
class ConsequencePoolAdmin(admin.ModelAdmin):
    list_display = ("name", "parent")
    list_filter = ("parent",)
    search_fields = ("name",)
    inlines = [ConsequencePoolEntryInline]


class ActionTemplateGateInline(admin.TabularInline):
    model = ActionTemplateGate
    extra = 0
    raw_id_fields = ("consequence_pool",)


@admin.register(ActionTemplate)
class ActionTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "pipeline", "check_type", "consequence_pool", "category")
    list_filter = ("pipeline", "category")
    search_fields = ("name",)
    raw_id_fields = ("consequence_pool",)
    inlines = [ActionTemplateGateInline]


@admin.register(ActionEnhancement)
class ActionEnhancementAdmin(admin.ModelAdmin):
    """#3831 - "this source modifies this base action in this way" authored row."""

    list_display = (
        "base_action_key",
        "variant_name",
        "source_type",
        "is_involuntary",
    )
    list_filter = ("source_type", "is_involuntary")
    search_fields = ("base_action_key", "variant_name")
    autocomplete_fields = ("distinction", "condition", "technique")


@admin.register(ModifyKwargsConfig)
class ModifyKwargsConfigAdmin(admin.ModelAdmin):
    """#3831 - a named transform applied to one action kwarg."""

    list_display = ("enhancement", "kwarg_name", "transform", "execution_order")
    list_filter = ("transform",)
    search_fields = ("kwarg_name", "enhancement__base_action_key")
    list_select_related = ("enhancement",)
    autocomplete_fields = ("enhancement",)


@admin.register(AddModifierConfig)
class AddModifierConfigAdmin(admin.ModelAdmin):
    """#3831 - a key/value modifier added to the action context."""

    list_display = ("enhancement", "modifier_key", "modifier_value", "execution_order")
    search_fields = ("modifier_key", "enhancement__base_action_key")
    list_select_related = ("enhancement",)
    autocomplete_fields = ("enhancement",)


@admin.register(ConditionOnCheckConfig)
class ConditionOnCheckConfigAdmin(admin.ModelAdmin):
    """#3831 - apply a condition to the target, gated by a check roll."""

    list_display = (
        "enhancement",
        "check_type",
        "condition",
        "severity",
        "duration_rounds",
    )
    list_select_related = ("enhancement", "check_type", "condition")
    autocomplete_fields = (
        "enhancement",
        "check_type",
        "resistance_check_type",
        "condition",
        "immunity_condition",
    )
    search_fields = ("enhancement__base_action_key", "source_description")


@admin.register(RemoveConditionOnCheckConfig)
class RemoveConditionOnCheckConfigAdmin(admin.ModelAdmin):
    """#3831 - remove a condition from the target, gated by a check roll."""

    list_display = ("enhancement", "check_type", "condition")
    list_select_related = ("enhancement", "check_type", "condition")
    autocomplete_fields = ("enhancement", "check_type", "resistance_check_type", "condition")
    search_fields = ("enhancement__base_action_key",)

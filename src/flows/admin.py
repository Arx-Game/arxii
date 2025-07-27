"""Django admin configuration for the flows app."""

from django.contrib import admin

from flows.models import (
    Event,
    FlowDefinition,
    FlowStepDefinition,
    Trigger,
    TriggerData,
    TriggerDefinition,
)


class FlowStepDefinitionInline(admin.StackedInline):
    """Inline for displaying flow steps within a FlowDefinition."""

    model = FlowStepDefinition
    extra = 1
    fields = ["parent", "action", "variable_name", "parameters"]
    autocomplete_fields = ["parent"]


@admin.register(FlowDefinition)
class FlowDefinitionAdmin(admin.ModelAdmin):
    list_display = ["name", "description"]
    search_fields = ["name"]
    inlines = [FlowStepDefinitionInline]


@admin.register(FlowStepDefinition)
class FlowStepDefinitionAdmin(admin.ModelAdmin):
    list_display = ["flow", "parent", "action", "variable_name"]
    list_filter = ["flow", "action"]
    search_fields = ["variable_name"]
    autocomplete_fields = ["flow", "parent"]


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ["name", "label"]
    search_fields = ["name", "label"]


@admin.register(TriggerDefinition)
class TriggerDefinitionAdmin(admin.ModelAdmin):
    list_display = ["name", "event", "flow_definition", "priority"]
    list_filter = ["event", "priority"]
    search_fields = ["name"]
    autocomplete_fields = ["event", "flow_definition"]


@admin.register(Trigger)
class TriggerAdmin(admin.ModelAdmin):
    list_display = ["trigger_definition", "obj"]
    list_filter = ["trigger_definition"]
    search_fields = ["obj__db_key", "trigger_definition__name"]
    autocomplete_fields = ["trigger_definition"]
    raw_id_fields = ["obj"]


@admin.register(TriggerData)
class TriggerDataAdmin(admin.ModelAdmin):
    list_display = ["trigger", "key", "value"]
    search_fields = ["key", "value"]
    autocomplete_fields = ["trigger"]

"""Django admin configuration for the flows app."""

from django.contrib import admin

from flows.models import (
    Event,
    FlowDefinition,
    FlowStepDefinition,
    Trigger,
    TriggerDefinition,
)


class FlowStepDefinitionInline(admin.StackedInline):
    """Inline for displaying flow steps within a FlowDefinition."""

    model = FlowStepDefinition
    extra = 1
    fields = ["parent", "action", "variable_name", "parameters"]
    raw_id_fields = ["parent"]


@admin.register(FlowDefinition)
class FlowDefinitionAdmin(admin.ModelAdmin):
    list_display = ["name", "description"]
    search_fields = ["name"]
    inlines = [FlowStepDefinitionInline]


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

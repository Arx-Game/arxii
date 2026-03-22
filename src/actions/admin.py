"""Django admin registrations for actions app models."""

from django.contrib import admin

from actions.models import (
    ActionTemplate,
    ActionTemplateGate,
    ConsequencePool,
    ConsequencePoolEntry,
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

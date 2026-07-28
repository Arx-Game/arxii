"""Admin registrations for the tasking app."""

from django.contrib import admin

from world.tasking.models import OrgTask, TaskFulfillment, TaskOutcomeRoute, TaskTemplate


class TaskOutcomeRouteInline(admin.TabularInline):
    model = TaskOutcomeRoute
    extra = 0
    raw_id_fields = ("outcome_tier", "clue_pool")


@admin.register(TaskTemplate)
class TaskTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "check_type", "check_difficulty", "duration", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("name",)
    raw_id_fields = ("check_type", "mission_template", "consequence_pool")
    inlines = [TaskOutcomeRouteInline]


@admin.register(TaskOutcomeRoute)
class TaskOutcomeRouteAdmin(admin.ModelAdmin):
    list_display = ("template", "outcome_tier", "money_reward", "clue_pool")
    list_filter = ("template__category",)
    raw_id_fields = ("template", "outcome_tier", "clue_pool")


@admin.register(OrgTask)
class OrgTaskAdmin(admin.ModelAdmin):
    list_display = ("id", "template", "org", "status", "target_kind", "deadline", "created_at")
    list_filter = ("status", "target_kind")
    raw_id_fields = (
        "template",
        "org",
        "issued_by",
        "target_room",
        "target_org",
        "target_domain",
        "target_persona",
    )


@admin.register(TaskFulfillment)
class TaskFulfillmentAdmin(admin.ModelAdmin):
    list_display = ("id", "task", "handler", "npc_asset", "is_active", "resolved_at")
    list_filter = ("is_active",)
    raw_id_fields = (
        "task",
        "npc_asset",
        "mission_instance",
        "handler",
        "handler_check_outcome",
        "resolved_outcome",
    )

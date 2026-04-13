"""GM admin configuration."""

from django.contrib import admin

from world.gm.models import GMApplication, GMProfile, GMTable, GMTableMembership


@admin.register(GMProfile)
class GMProfileAdmin(admin.ModelAdmin):
    list_display = ["account", "level", "approved_at"]
    list_filter = ["level"]
    raw_id_fields = ["account", "approved_by"]


@admin.register(GMApplication)
class GMApplicationAdmin(admin.ModelAdmin):
    list_display = ["account", "status", "created_at", "reviewed_by"]
    list_filter = ["status"]
    raw_id_fields = ["account", "reviewed_by"]


@admin.register(GMTable)
class GMTableAdmin(admin.ModelAdmin):
    list_display = ["name", "gm", "status", "created_at"]
    list_filter = ["status"]
    raw_id_fields = ["gm"]


@admin.register(GMTableMembership)
class GMTableMembershipAdmin(admin.ModelAdmin):
    list_display = ["table", "persona", "joined_at", "left_at"]
    list_filter = ["left_at"]
    raw_id_fields = ["table", "persona"]

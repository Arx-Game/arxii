from django.contrib import admin

from world.instances.models import InstancedRoom


@admin.register(InstancedRoom)
class InstancedRoomAdmin(admin.ModelAdmin):
    list_display = ["room", "owner", "status", "source_key", "created_at"]
    list_filter = ["status"]
    search_fields = ["room__db_key", "source_key"]
    readonly_fields = ["created_at", "completed_at"]

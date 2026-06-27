from django.contrib import admin

from world.weather.models import Climate


@admin.register(Climate)
class ClimateAdmin(admin.ModelAdmin):
    list_display = ["name", "temperature", "moisture", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name"]

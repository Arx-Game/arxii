"""Django admin for the agriculture system."""

from django.contrib import admin

from world.agriculture.models import (
    CropType,
    FieldDetails,
    FoodConfig,
    FoodStockpile,
    GranaryDetails,
)


@admin.register(CropType)
class CropTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "base_production"]
    search_fields = ["name"]


class FieldDetailsInline(admin.StackedInline):
    model = FieldDetails
    extra = 0


class GranaryDetailsInline(admin.StackedInline):
    model = GranaryDetails
    extra = 0


@admin.register(FoodStockpile)
class FoodStockpileAdmin(admin.ModelAdmin):
    list_display = ["domain", "stored", "last_collected_at"]
    readonly_fields = ["last_collected_at"]


@admin.register(FoodConfig)
class FoodConfigAdmin(admin.ModelAdmin):
    list_display = [
        "production_rate_multiplier",
        "consumption_per_capita",
        "shortage_unrest_penalty",
        "shortage_prosperity_penalty",
        "granary_capacity_per_level",
        "army_food_per_member",
        "max_provisioning_morale_penalty",
        "max_provisioning_strength_penalty",
    ]

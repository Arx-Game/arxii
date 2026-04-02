from django.contrib import admin

from world.fatigue.models import FatiguePool


@admin.register(FatiguePool)
class FatiguePoolAdmin(admin.ModelAdmin):
    list_display = [
        "character",
        "physical_current",
        "social_current",
        "mental_current",
        "well_rested",
    ]
    list_filter = ["well_rested", "rested_today", "dawn_deferred"]

from django.contrib import admin

from world.weather.models import (
    Climate,
    FeastDay,
    RegionWeatherState,
    WeatherEmit,
    WeatherType,
    WeatherTypeExposure,
)


@admin.register(Climate)
class ClimateAdmin(admin.ModelAdmin):
    list_display = ["name", "temperature", "moisture", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name"]


class WeatherTypeExposureInline(admin.TabularInline):
    model = WeatherTypeExposure
    extra = 1


@admin.register(WeatherType)
class WeatherTypeAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "is_automated",
        "selection_weight",
        "min_temperature",
        "max_temperature",
        "is_active",
    ]
    list_filter = ["is_automated", "is_active"]
    search_fields = ["name"]
    inlines = [WeatherTypeExposureInline]


@admin.register(WeatherEmit)
class WeatherEmitAdmin(admin.ModelAdmin):
    list_display = ["weather_type", "weight", "text"]
    list_filter = [
        "weather_type",
        "in_spring",
        "in_summer",
        "in_autumn",
        "in_winter",
        "at_dawn",
        "at_day",
        "at_dusk",
        "at_night",
    ]
    search_fields = ["text", "gm_notes"]


@admin.register(RegionWeatherState)
class RegionWeatherStateAdmin(admin.ModelAdmin):
    list_display = ["area", "weather_type", "changed_at"]
    list_filter = ["weather_type"]
    search_fields = ["area__name"]


@admin.register(FeastDay)
class FeastDayAdmin(admin.ModelAdmin):
    list_display = ["name", "ic_month", "ic_day", "weather_type", "is_active"]
    list_filter = ["is_active", "weather_type"]
    search_fields = ["name"]

from django.contrib import admin
from django.http import HttpRequest

from world.admin_utils import OneRowPerFormSet
from world.ceremonies.models import (
    Ceremony,
    CeremonyConfig,
    CeremonyHonoree,
    CeremonyOffering,
    CeremonySpeech,
    CeremonyType,
    OfferingSignal,
)


class CeremonyHonoreeInline(admin.TabularInline):
    model = CeremonyHonoree
    formset = OneRowPerFormSet
    extra = 0
    raw_id_fields = ("honoree_sheet",)


class CeremonyOfferingInline(admin.TabularInline):
    model = CeremonyOffering
    extra = 0
    raw_id_fields = ("offered_by", "worship_grant")


class OfferingSignalInline(admin.TabularInline):
    """The item's meaning at the moment it was given up (#4500): read-only, computed."""

    model = OfferingSignal
    extra = 0
    can_delete = False
    readonly_fields = ("kind", "points", "detail")

    def has_add_permission(self, request: HttpRequest, obj: object = None) -> bool:
        del request, obj  # signals are computed at sacrifice time, never added by hand
        return False


@admin.register(CeremonyOffering)
class CeremonyOfferingAdmin(admin.ModelAdmin):
    """A sacrifice or ceremony offering with its meaning signals inline (#4500)."""

    list_display = ("item_name", "offered_by", "being", "ceremony", "outcome_tier", "counted")
    list_filter = ("counted",)
    raw_id_fields = ("ceremony", "being", "pledge_details", "offered_by", "worship_grant")
    readonly_fields = ("outcome_tier", "game_week", "counted", "item_value", "item_legend_value")
    inlines = [OfferingSignalInline]


class CeremonySpeechInline(admin.TabularInline):
    model = CeremonySpeech
    extra = 0
    raw_id_fields = ("speaker", "target_honoree")


@admin.register(CeremonyType)
class CeremonyTypeAdmin(admin.ModelAdmin):
    list_display = ("key", "name")


@admin.register(Ceremony)
class CeremonyAdmin(admin.ModelAdmin):
    autocomplete_fields = ["location"]  # rooms are searched, never scrolled
    list_display = ("ceremony_type", "officiant", "location", "status", "opened_at")
    list_filter = ("ceremony_type", "status")
    raw_id_fields = [
        "officiant",
        "being",
        "presented_being",
        "scene",
        "event",
        "title",
        "worship_rite",
    ]
    inlines = [CeremonyHonoreeInline, CeremonyOfferingInline, CeremonySpeechInline]


@admin.register(CeremonyConfig)
class CeremonyConfigAdmin(admin.ModelAdmin):
    list_display = ("pk", "officiant_cut_percent", "base_honoree_prestige")

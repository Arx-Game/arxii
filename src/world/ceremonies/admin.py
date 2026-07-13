from django.contrib import admin

from world.ceremonies.models import (
    Ceremony,
    CeremonyConfig,
    CeremonyHonoree,
    CeremonyOffering,
    CeremonySpeech,
    CeremonyType,
)


class CeremonyHonoreeInline(admin.TabularInline):
    model = CeremonyHonoree
    extra = 0
    raw_id_fields = ("honoree_sheet",)


class CeremonyOfferingInline(admin.TabularInline):
    model = CeremonyOffering
    extra = 0
    raw_id_fields = ("offered_by", "worship_grant")


class CeremonySpeechInline(admin.TabularInline):
    model = CeremonySpeech
    extra = 0
    raw_id_fields = ("speaker", "target_honoree")


@admin.register(CeremonyType)
class CeremonyTypeAdmin(admin.ModelAdmin):
    list_display = ("key", "name")


@admin.register(Ceremony)
class CeremonyAdmin(admin.ModelAdmin):
    list_display = ("ceremony_type", "officiant", "location", "status", "opened_at")
    list_filter = ("ceremony_type", "status")
    raw_id_fields = ("officiant", "being", "presented_being", "location", "scene", "event")
    inlines = [CeremonyHonoreeInline, CeremonyOfferingInline, CeremonySpeechInline]


@admin.register(CeremonyConfig)
class CeremonyConfigAdmin(admin.ModelAdmin):
    list_display = ("pk", "officiant_cut_percent", "base_honoree_prestige")

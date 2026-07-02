from django.contrib import admin

from world.justice.models import AreaLaw, CrimeKind, DeedCrimeTag, HeatSource, PersonaHeat


@admin.register(CrimeKind)
class CrimeKindAdmin(admin.ModelAdmin):
    list_display = ("slug", "name")
    search_fields = ("slug", "name")


@admin.register(AreaLaw)
class AreaLawAdmin(admin.ModelAdmin):
    list_display = ("area", "crime_kind", "heat_weight", "exempts")
    list_filter = ("exempts", "crime_kind")
    search_fields = ("area__name", "crime_kind__name")
    raw_id_fields = ("area",)


@admin.register(DeedCrimeTag)
class DeedCrimeTagAdmin(admin.ModelAdmin):
    list_display = ("deed", "crime_kind")
    raw_id_fields = ("deed",)


@admin.register(PersonaHeat)
class PersonaHeatAdmin(admin.ModelAdmin):
    list_display = ("persona", "area", "society", "value", "updated_date")
    raw_id_fields = ("persona", "area", "society")


@admin.register(HeatSource)
class HeatSourceAdmin(admin.ModelAdmin):
    list_display = ("heat", "deed", "amount", "created_date")
    raw_id_fields = ("heat", "deed")

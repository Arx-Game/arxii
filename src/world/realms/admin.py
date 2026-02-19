from django.contrib import admin

from world.realms.models import Realm


@admin.register(Realm)
class RealmAdmin(admin.ModelAdmin):
    list_display = ["name", "theme"]
    search_fields = ["name"]

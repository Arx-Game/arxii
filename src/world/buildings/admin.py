"""Admin registrations for buildings lookup tables (#670).

Only the tuning lookups are registered — Buildings themselves are
game-state mutated through services, not hand-edited.
"""

from typing import ClassVar

from django.contrib import admin

from world.buildings.models import BuildingSizeTier


@admin.register(BuildingSizeTier)
class BuildingSizeTierAdmin(admin.ModelAdmin):
    list_display: ClassVar[list[str]] = ["tier", "name", "space_budget"]
    ordering: ClassVar[list[str]] = ["tier"]

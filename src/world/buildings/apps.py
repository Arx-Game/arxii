"""AppConfig for the buildings system."""

from django.apps import AppConfig


class BuildingsConfig(AppConfig):
    name = "world.buildings"
    label = "buildings"
    verbose_name = "Buildings (permits + construction + materials)"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # Two cross-app registrations:
        #   1. Replace Plan 2's stub PERMIT effect handler with Plan 3's
        #      real `issue_permit`.
        #   2. Register `complete_building_construction` as the project
        #      framework's handler for BUILDING_CONSTRUCTION so resolving
        #      a completed construction project spawns the Building.
        # Both go through helper functions so tests can roll back via
        # reset_offer_effect_handlers / clear_kind_handlers.
        from world.buildings.services import (  # noqa: PLC0415
            complete_building_construction,
            issue_permit,
        )
        from world.npc_services.constants import OfferKind  # noqa: PLC0415
        from world.npc_services.effects import register_offer_effect_handler  # noqa: PLC0415
        from world.projects.constants import ProjectKind  # noqa: PLC0415
        from world.projects.services import register_kind_handler  # noqa: PLC0415

        register_offer_effect_handler(OfferKind.PERMIT.value, issue_permit)
        register_kind_handler(ProjectKind.BUILDING_CONSTRUCTION, complete_building_construction)

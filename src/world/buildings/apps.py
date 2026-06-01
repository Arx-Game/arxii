"""AppConfig for the buildings system."""

from django.apps import AppConfig


class BuildingsConfig(AppConfig):
    name = "world.buildings"
    label = "buildings"
    verbose_name = "Buildings (permits + construction + materials)"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # Replace the npc_services stub PERMIT effect handler with the
        # real implementation from world.buildings.services. Plan 2
        # shipped a stub; Plan 3 owns the real handler since permit
        # issuance creates a BuildingPermit + BuildingPermitDetails.
        from world.buildings.services import issue_permit  # noqa: PLC0415
        from world.npc_services.constants import OfferKind  # noqa: PLC0415
        from world.npc_services.effects import OFFER_EFFECT_HANDLERS  # noqa: PLC0415

        OFFER_EFFECT_HANDLERS[OfferKind.PERMIT.value] = issue_permit

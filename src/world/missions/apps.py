from django.apps import AppConfig


class MissionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "world.missions"
    verbose_name = "Missions"

    def ready(self) -> None:
        """Register the MISSION effect handler with the unified offer framework (#686).

        Late-imported so models / handlers are loaded only after Django's
        app registry is ready; matches the pattern Plan 3's BuildingsConfig
        uses for ``issue_permit``.
        """
        from world.missions.services.offer_handler import issue_mission  # noqa: PLC0415
        from world.npc_services.constants import OfferKind  # noqa: PLC0415
        from world.npc_services.effects import register_offer_effect_handler  # noqa: PLC0415

        # str() coerces around ty's TextChoices-value mis-inference (sees it
        # as the (value, label) tuple literal instead of the Enum member's str).
        register_offer_effect_handler(str(OfferKind.MISSION.value), issue_mission)

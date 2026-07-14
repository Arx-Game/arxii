from django.apps import AppConfig


class AssetsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "world.assets"
    verbose_name = "Assets"

    def ready(self) -> None:
        """Register the promotion effect handlers (#1872).

        Late-imported so models/handlers load only after Django's app
        registry is ready; mirrors world.missions.apps.MissionsConfig.ready.
        """
        from world.assets.effects import (  # noqa: PLC0415
            promote_as_contact,
            promote_as_fan,
            promote_as_guard,
            promote_as_informant,
            promote_as_minor_ally,
            promote_as_personal_favor,
            run_asset_collect_task,
            run_asset_intel_task,
        )
        from world.npc_services.constants import OfferKind  # noqa: PLC0415
        from world.npc_services.effects import register_offer_effect_handler  # noqa: PLC0415

        register_offer_effect_handler(str(OfferKind.INFORMANT.value), promote_as_informant)
        register_offer_effect_handler(str(OfferKind.CONTACT.value), promote_as_contact)
        register_offer_effect_handler(
            str(OfferKind.PERSONAL_FAVOR.value), promote_as_personal_favor
        )
        register_offer_effect_handler(str(OfferKind.GUARD.value), promote_as_guard)
        register_offer_effect_handler(str(OfferKind.FAN.value), promote_as_fan)
        register_offer_effect_handler(str(OfferKind.MINOR_ALLY.value), promote_as_minor_ally)
        register_offer_effect_handler(str(OfferKind.ASSET_TASK_INTEL.value), run_asset_intel_task)
        register_offer_effect_handler(
            str(OfferKind.ASSET_TASK_COLLECT.value), run_asset_collect_task
        )

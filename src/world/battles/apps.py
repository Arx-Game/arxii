"""App configuration for the battles system."""

from django.apps import AppConfig


class BattlesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "world.battles"
    verbose_name = "Battles"

    def ready(self) -> None:
        from world.battles.city_defense_services import (  # noqa: PLC0415
            complete_city_defense,
            resolve_city_defense,
        )
        from world.battles.conclusion_hooks import register_battle_conclusion_hook  # noqa: PLC0415
        from world.battles.legend_wiring import apply_battle_legend_awards  # noqa: PLC0415
        from world.projects.constants import ProjectKind  # noqa: PLC0415
        from world.projects.services import (  # noqa: PLC0415
            register_kind_handler,
            register_tiered_resolver,
        )

        register_battle_conclusion_hook(apply_battle_legend_awards)

        # #1892 — register the CITY_DEFENSE kind handler + tiered resolver.
        register_kind_handler(ProjectKind.CITY_DEFENSE, complete_city_defense)
        register_tiered_resolver(ProjectKind.CITY_DEFENSE, resolve_city_defense)

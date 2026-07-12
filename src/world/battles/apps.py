"""App configuration for the battles system."""

from django.apps import AppConfig


class BattlesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "world.battles"
    verbose_name = "Battles"

    def ready(self) -> None:
        from world.battles.conclusion_hooks import register_battle_conclusion_hook  # noqa: PLC0415
        from world.battles.legend_wiring import apply_battle_legend_awards  # noqa: PLC0415

        register_battle_conclusion_hook(apply_battle_legend_awards)

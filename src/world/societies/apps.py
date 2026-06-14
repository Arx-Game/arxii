"""Django app configuration for the societies system."""

from django.apps import AppConfig


class SocietiesConfig(AppConfig):
    """Configuration for the societies app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "world.societies"
    verbose_name = "Societies"

    def ready(self) -> None:
        # Import for side effect: registers the spread_a_tale scene-action resolver.
        # Register the SPREAD_ASSIST reaction kind (#915) so the scenes
        # reaction framework can settle acclaim on tellings.
        from world.scenes.constants import ReactionWindowKind  # noqa: PLC0415
        from world.scenes.reaction_services import register_reaction_kind  # noqa: PLC0415
        from world.societies import spread_services  # noqa: F401, PLC0415
        from world.societies.reaction_kinds import SPREAD_ASSIST_KIND  # noqa: PLC0415

        register_reaction_kind(ReactionWindowKind.SPREAD_ASSIST, SPREAD_ASSIST_KIND)

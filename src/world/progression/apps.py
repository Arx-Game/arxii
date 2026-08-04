from django.apps import AppConfig


class ProgressionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "world.progression"
    verbose_name = "Progression"

    def ready(self) -> None:
        ready()


def ready() -> None:
    """Register the KUDOS reaction kind.

    Extracted to module level (#2906) so the single-app aggregator
    (``world.apps.ArxiiConfig.ready``) can call it directly once
    ``world.progression`` stops being its own installed app.
    """
    from world.progression.reaction_kinds import KUDOS_KIND  # noqa: PLC0415
    from world.scenes.constants import ReactionWindowKind  # noqa: PLC0415
    from world.scenes.reaction_services import register_reaction_kind  # noqa: PLC0415

    register_reaction_kind(ReactionWindowKind.KUDOS, KUDOS_KIND)

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

        # #1511 — register the org invitation offer handler.
        from commands.offer_registry import register_offer_handler  # noqa: PLC0415
        from world.societies.offer_handlers import OrgInviteHandler  # noqa: PLC0415

        register_offer_handler(OrgInviteHandler())

        # #1891 — register the GANG_TURF kind handler + tiered resolver.
        from world.projects.constants import ProjectKind  # noqa: PLC0415
        from world.projects.services import (  # noqa: PLC0415
            register_kind_handler,
            register_tiered_resolver,
        )
        from world.societies.gang_turf import complete_gang_turf, resolve_gang_turf  # noqa: PLC0415
        from world.societies.org_capability import resolve_organization_capability  # noqa: PLC0415

        register_kind_handler(ProjectKind.GANG_TURF, complete_gang_turf)
        register_tiered_resolver(ProjectKind.GANG_TURF, resolve_gang_turf)
        register_kind_handler(
            ProjectKind.ORGANIZATION_CAPABILITY,
            resolve_organization_capability,
        )

        # #1884 — register the DOMAIN_IMPROVEMENT kind handler.
        from world.societies.houses.services import complete_domain_improvement  # noqa: PLC0415

        register_kind_handler(ProjectKind.DOMAIN_IMPROVEMENT, complete_domain_improvement)

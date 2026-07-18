from django.apps import AppConfig


class MagicConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "world.magic"
    verbose_name = "Magic System"

    def ready(self) -> None:
        # Trigger registration of action resolvers and menu contributors.
        from world.magic.services import anima_ritual_action  # noqa: F401, PLC0415

        # Register Sanctum as the SANCTUM service strategy for the
        # ROOM_FEATURE_PROGRESSION ProjectKind handler (Plan 4 §F).
        from world.magic.services.sanctum import handle_progression  # noqa: PLC0415
        from world.room_features.constants import (  # noqa: PLC0415
            RoomFeatureServiceStrategy,
        )
        from world.room_features.services import (  # noqa: PLC0415
            register_room_feature_strategy,
        )

        register_room_feature_strategy(
            RoomFeatureServiceStrategy.SANCTUM,
            handle_progression,
            as_default=True,
        )

        # Register Make an Entrance as a reaction-window kind (#904) —
        # scenes owns the primitive; magic owns the entrance behavior.
        from world.magic.reaction_kinds import ENTRANCE_KIND  # noqa: PLC0415
        from world.scenes.constants import ReactionWindowKind  # noqa: PLC0415
        from world.scenes.reaction_services import register_reaction_kind  # noqa: PLC0415

        register_reaction_kind(ReactionWindowKind.ENTRANCE, ENTRANCE_KIND)

        # Register offer handlers for telnet accept/decline routing (#1344).
        from commands.offer_registry import register_offer_handler  # noqa: PLC0415
        from world.magic.offer_handlers import (  # noqa: PLC0415
            CrossingOfferHandler,
            SoulfrayPendingHandler,
            SurgeOfferHandler,
        )

        register_offer_handler(SurgeOfferHandler())
        register_offer_handler(CrossingOfferHandler())
        register_offer_handler(SoulfrayPendingHandler())

        # Register crossing-ceremony handlers (ADR-0094, #1987).
        # Each TargetKind dispatches to a handler when a thread crosses a
        # PathStage crossing level (3, 6, 11, 16, 21).
        from world.magic.crossing.handlers import (  # noqa: PLC0415
            CovenantRoleCrossingHandler,
            FacetCrossingHandler,
            GiftCrossingHandler,
            MantleCrossingHandler,
            OrganizationCrossingHandler,
            RelationshipCapstoneCrossingHandler,
            RelationshipTrackCrossingHandler,
            SanctumCrossingHandler,
            TechniqueCrossingHandler,
            TraitCrossingHandler,
        )
        from world.magic.crossing.registry import register_crossing_handler  # noqa: PLC0415

        register_crossing_handler(GiftCrossingHandler())
        register_crossing_handler(OrganizationCrossingHandler())
        register_crossing_handler(CovenantRoleCrossingHandler())
        register_crossing_handler(TechniqueCrossingHandler())
        register_crossing_handler(TraitCrossingHandler())
        register_crossing_handler(FacetCrossingHandler())
        register_crossing_handler(RelationshipTrackCrossingHandler())
        register_crossing_handler(RelationshipCapstoneCrossingHandler())
        register_crossing_handler(MantleCrossingHandler())
        register_crossing_handler(SanctumCrossingHandler())

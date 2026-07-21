"""AppConfig for the room_features system."""

from django.apps import AppConfig


class RoomFeaturesConfig(AppConfig):
    name = "world.room_features"
    label = "room_features"
    verbose_name = "Room Features (Sanctum, Library, Training Room, …)"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # Register the ROOM_FEATURE_PROGRESSION Project handler so resolving
        # a completed install/upgrade project dispatches to the per-kind
        # service strategy. The strategy registry itself is populated by
        # each feature's home app (Sanctum: world.magic.services.sanctum).
        from world.projects.constants import ProjectKind  # noqa: PLC0415
        from world.projects.services import register_kind_handler  # noqa: PLC0415
        from world.room_features.services import (  # noqa: PLC0415
            complete_room_feature_progression,
        )

        register_kind_handler(
            ProjectKind.ROOM_FEATURE_PROGRESSION,
            complete_room_feature_progression,
        )

        # COMMAND_CENTER (#930) is a generic feature — this app IS its home,
        # so its strategy registers here (Sanctum's registers from world.magic).
        from world.room_features.constants import (  # noqa: PLC0415
            RoomFeatureServiceStrategy,
        )
        from world.room_features.services import (  # noqa: PLC0415
            handle_command_center_progression,
            register_room_feature_strategy,
        )

        register_room_feature_strategy(
            RoomFeatureServiceStrategy.COMMAND_CENTER,
            handle_command_center_progression,
            as_default=True,
        )

        # Bank access (#2540 Layer 4) is likewise generic — home app is here.
        from world.room_features.services import (  # noqa: PLC0415
            handle_bank_progression,
        )

        register_room_feature_strategy(
            RoomFeatureServiceStrategy.BANK,
            handle_bank_progression,
            as_default=True,
        )

        # Civic-hub readers (#1450) are likewise generic — home app is here.
        from world.room_features.services import (  # noqa: PLC0415
            handle_notice_board_progression,
            handle_town_crier_progression,
        )

        register_room_feature_strategy(
            RoomFeatureServiceStrategy.NOTICE_BOARD,
            handle_notice_board_progression,
            as_default=True,
        )
        register_room_feature_strategy(
            RoomFeatureServiceStrategy.TOWN_CRIER,
            handle_town_crier_progression,
            as_default=True,
        )

        # #675 feature kinds — generic; home app is here.
        from world.room_features.services import (  # noqa: PLC0415
            handle_captains_quarters_progression,
            handle_library_progression,
            handle_siege_deck_progression,
            handle_training_room_progression,
        )

        register_room_feature_strategy(
            RoomFeatureServiceStrategy.LIBRARY,
            handle_library_progression,
            as_default=True,
        )
        register_room_feature_strategy(
            RoomFeatureServiceStrategy.TRAINING_ROOM,
            handle_training_room_progression,
            as_default=True,
        )
        register_room_feature_strategy(
            RoomFeatureServiceStrategy.SIEGE_DECK,
            handle_siege_deck_progression,
            as_default=True,
        )
        register_room_feature_strategy(
            RoomFeatureServiceStrategy.CAPTAINS_QUARTERS,
            handle_captains_quarters_progression,
            as_default=True,
        )

        # Owner-upgradeable social hub (#1694) — generic; home app is here.
        from world.room_features.services import (  # noqa: PLC0415
            handle_social_hub_progression,
        )

        register_room_feature_strategy(
            RoomFeatureServiceStrategy.SOCIAL_HUB,
            handle_social_hub_progression,
            as_default=True,
        )

        # #2179 — Vault room feature (secure storage + access list).
        from world.room_features.vault_services import (  # noqa: PLC0415
            handle_vault_progression,
        )

        register_room_feature_strategy(
            RoomFeatureServiceStrategy.VAULT,
            handle_vault_progression,
            as_default=True,
        )

        # #1825 — Workshop of Iniquity (criminal-projects gate; frame jobs).
        from world.room_features.services import (  # noqa: PLC0415
            handle_workshop_of_iniquity_progression,
        )

        register_room_feature_strategy(
            RoomFeatureServiceStrategy.WORKSHOP_OF_INIQUITY,
            handle_workshop_of_iniquity_progression,
            as_default=True,
        )

        # #1862 — Brig room feature (ship holding cell for captured characters).
        from world.room_features.brig_services import (  # noqa: PLC0415
            handle_brig_progression,
        )

        register_room_feature_strategy(
            RoomFeatureServiceStrategy.BRIG,
            handle_brig_progression,
            as_default=True,
        )

        # Installable exit/room defenses (#2177) -- independent of
        # RoomFeatureKind/RoomFeatureInstance (Decision 1); its own Project kind.
        from world.room_features.services import (  # noqa: PLC0415
            complete_defense_installation,
        )

        register_kind_handler(
            ProjectKind.ROOM_DEFENSE_INSTALLATION,
            complete_defense_installation,
        )

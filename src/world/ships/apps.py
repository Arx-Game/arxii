"""Startup hook for the ships system (#1832), called from world/apps.py."""


def ready() -> None:
    """Register ship project-kind handlers + the battle conclusion hook.

    Extracted to module level (#2906) so the single-app aggregator
    (``world.apps.ArxiiConfig.ready``) can call it directly once
    ``world.ships`` stops being its own installed app.
    """
    from world.battles.conclusion_hooks import register_battle_conclusion_hook  # noqa: PLC0415
    from world.projects.constants import ProjectKind  # noqa: PLC0415
    from world.projects.services import register_kind_handler  # noqa: PLC0415
    from world.ships.battle_wiring import apply_ship_battle_outcome  # noqa: PLC0415
    from world.ships.services import (  # noqa: PLC0415
        complete_ship_construction,
        complete_ship_repair,
        complete_ship_upgrade,
    )

    register_kind_handler(ProjectKind.SHIP_CONSTRUCTION, complete_ship_construction)
    register_kind_handler(ProjectKind.SHIP_UPGRADE, complete_ship_upgrade)
    register_kind_handler(ProjectKind.SHIP_REPAIR, complete_ship_repair)
    register_battle_conclusion_hook(apply_ship_battle_outcome)

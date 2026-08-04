def ready() -> None:
    """Register the MISSION effect handler with the unified offer framework (#686).

    Late-imported so models / handlers are loaded only after Django's
    app registry is ready; matches the pattern Plan 3's BuildingsConfig
    uses for ``issue_permit``.

    Extracted to module level (#2906) so the single-app aggregator
    (``world.apps.ArxiiConfig.ready``) can call it directly once
    ``world.missions`` stops being its own installed app.
    """
    from world.missions.services.offer_handler import issue_mission  # noqa: PLC0415
    from world.npc_services.constants import OfferKind  # noqa: PLC0415
    from world.npc_services.effects import register_offer_effect_handler  # noqa: PLC0415

    # ty sees `OfferKind.MISSION.value` as the `(value, label)` literal tuple
    # rather than the TextChoices member's resolved str. Wrapping in `str()`
    # bridges the inference gap; the runtime value is already `"mission"`,
    # so this is a no-op at runtime.
    register_offer_effect_handler(str(OfferKind.MISSION.value), issue_mission)

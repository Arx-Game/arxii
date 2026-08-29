"""AppConfig for the single collapsed ``world`` app (#2906).

``world`` is becoming one Django app (label ``arxii``) replacing the 66
separate ``world.*`` apps. Django derives ``app_label`` from package
containment, so every ``world.<pkg>.models`` module keeps working with no
import rewrites once this AppConfig is the one installed in
``INSTALLED_APPS`` (a later task flips that switch — this file is inert
until then).

Because the 66 sub-packages stop being their own installed apps, Django's
per-app autodiscovery (models/admin import + ``ready()``) stops firing for
them. ``ready()`` below re-centralises the ``ready()`` half of that
contract; ``world/models.py`` and ``world/admin.py`` re-centralise the
other two.

**Ordering is load-bearing.** These 20 ``ready()`` hooks are cross-app
registration handshakes — most prominently, ``world.buildings.apps.ready``
deliberately replaces a stub offer-effect handler
``world.npc_services.effects`` registers at import time. The call order
below is the sub-packages' relative order in ``INSTALLED_APPS`` (captured
2026-08-04; regenerate by listing ``apps.get_app_configs()`` filtered to
``world.*`` names if the app list ever changes before the flip lands).
Reordering this list silently changes which handler wins — never
alphabetize or glob it.

**Why delegate instead of inlining the 20 hook bodies:** each sub-package's
``apps.py`` keeps its own ``ready()`` logic as a module-level ``ready()``
function (with the ``AppConfig.ready(self)`` method delegating to it, so
today's per-app behavior is byte-identical while ``world.*`` are still
separately installed). This aggregator imports and calls each module-level
function directly — registration logic stays next to the code it
registers, sub-app tests can still exercise a single hook in isolation, and
this method stays a short, auditable call list instead of an 80+-line
merged body.
"""

from django.apps import AppConfig


def _register_flow_service_functions() -> None:
    """Register world-side flow verbs under short names (#3417).

    ``flows`` must not import ``world.*``, so out-of-app verbs like the
    conditions services register themselves here instead of living in a
    ``hooks`` dict alongside an in-app ``flows.service_functions`` module.
    """
    from flows.service_functions import register_service_function  # noqa: PLC0415
    from world.conditions import services as condition_services  # noqa: PLC0415

    register_service_function("apply_condition_by_name", condition_services.apply_condition_by_name)
    register_service_function("advance_condition_stage", condition_services.advance_condition_stage)
    register_service_function(
        "remove_condition_by_name", condition_services.remove_condition_by_name
    )


class ArxiiConfig(AppConfig):
    """AppConfig for the collapsed ``world`` package."""

    name = "world"
    label = "arxii"
    verbose_name = "Arx II"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        """Run every ``world.*`` sub-package's ``ready()`` hook, in order."""
        import world.agriculture.apps as agriculture_apps  # noqa: PLC0415
        import world.areas.apps as areas_apps  # noqa: PLC0415
        import world.assets.apps as assets_apps  # noqa: PLC0415
        import world.battles.apps as battles_apps  # noqa: PLC0415
        import world.buildings.apps as buildings_apps  # noqa: PLC0415
        import world.captivity.apps as captivity_apps  # noqa: PLC0415
        import world.clues.apps as clues_apps  # noqa: PLC0415
        import world.companions.apps as companions_apps  # noqa: PLC0415
        import world.gm.apps as gm_apps  # noqa: PLC0415
        import world.items.apps as items_apps  # noqa: PLC0415
        import world.justice.apps as justice_apps  # noqa: PLC0415
        import world.magic.apps as magic_apps  # noqa: PLC0415
        import world.missions.apps as missions_apps  # noqa: PLC0415
        import world.progression.apps as progression_apps  # noqa: PLC0415
        import world.projects.apps as projects_apps  # noqa: PLC0415
        import world.room_features.apps as room_features_apps  # noqa: PLC0415
        import world.roster.apps as roster_apps  # noqa: PLC0415
        import world.scenes.apps as scenes_apps  # noqa: PLC0415
        import world.ships.apps as ships_apps  # noqa: PLC0415
        import world.societies.apps as societies_apps  # noqa: PLC0415
        import world.tasking.apps as tasking_apps  # noqa: PLC0415

        # INSTALLED_APPS order (world.* slice, captured 2026-08-04) — do not
        # reorder; see the class docstring.
        roster_apps.ready()
        progression_apps.ready()
        magic_apps.ready()
        scenes_apps.ready()
        societies_apps.ready()
        agriculture_apps.ready()
        companions_apps.ready()
        assets_apps.ready()
        clues_apps.ready()
        areas_apps.ready()
        justice_apps.ready()
        captivity_apps.ready()
        items_apps.ready()
        battles_apps.ready()
        missions_apps.ready()
        projects_apps.ready()
        tasking_apps.ready()
        buildings_apps.ready()
        ships_apps.ready()
        room_features_apps.ready()
        # #3071 — new registration, no ordering dependency on the handshakes above.
        gm_apps.ready()
        # #3417 — new registration, no ordering dependency on the handshakes above.
        _register_flow_service_functions()

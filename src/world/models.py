"""Model aggregator for the single collapsed ``world`` app (#2906).

Django's autodiscovery imports ``<app>.models`` once per installed app. Once
the 66 ``world.*`` sub-packages stop being separate installed apps (a later
task flips ``INSTALLED_APPS``), nothing imports their individual ``models``
modules automatically any more — so this file imports every one of them
directly to keep every model in the schema.

The import order below is alphabetical, not ``INSTALLED_APPS`` order — ruff's
isort rule (``select = ["ALL"]``, no ``I001`` exemption) enforces it on save.
That's fine: unlike ``world/apps.py``'s ``ready()`` order, import order here
carries no runtime effect — each ``import world.<pkg>.models`` is independent
of the others, so any order registers every model with Django the same way.

**Completeness is guarded by a test**, not by convention:
``world/tests/test_aggregators.py`` walks the ``world`` package with
``pkgutil``, finds every sub-package that actually defines a ``models``
module, and asserts each one is imported here. If a sub-package is ever
missing from this file, its models silently vanish from the schema — add
the missing import here (and check whether ``world/apps.py`` also needs a
``ready()`` entry) rather than suppressing the test.

Sub-packages with no ``models`` module at all (as of 2026-08-04:
``predicates``, ``staff_inbox``, ``tidings``) are intentionally absent.
"""

import world.achievements.models
import world.action_points.models
import world.agriculture.models
import world.areas.models
import world.assets.models
import world.battles.models
import world.beta_reset.models
import world.boundaries.models
import world.buildings.models
import world.captivity.models
import world.ceremonies.models
import world.character_creation.models
import world.character_sheets.models
import world.checks.models
import world.classes.models
import world.clues.models
import world.codex.models
import world.combat.models
import world.companions.models
import world.conditions.models
import world.consent.models
import world.contributors.models
import world.covenants.models
import world.currency.models
import world.distinctions.models
import world.downtime.models
import world.dreams.models
import world.estates.models
import world.events.models
import world.fatigue.models
import world.forms.models
import world.game_clock.models
import world.gm.models
import world.goals.models
import world.instances.models
import world.items.models
import world.journals.models
import world.justice.models
import world.locations.models
import world.magic.models
import world.mechanics.models
import world.military.models
import world.missions.models
import world.narrative.models
import world.npc_services.models
import world.player_submissions.models
import world.predators.models
import world.progression.models
import world.projects.models
import world.realms.models
import world.registration.models
import world.relationships.models
import world.room_features.models
import world.roster.models
import world.scenes.models
import world.secrets.models
import world.ships.models
import world.skills.models
import world.societies.models
import world.species.models
import world.stories.models
import world.tarot.models
import world.tasking.models
import world.traits.models
import world.travel.models
import world.vitals.models
import world.weather.models
import world.worship.models  # noqa: F401

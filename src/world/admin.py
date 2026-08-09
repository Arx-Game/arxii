"""Admin aggregator for the single collapsed ``world`` app (#2906).

Django's autodiscovery imports ``<app>.admin`` once per installed app. Once
the 66 ``world.*`` sub-packages stop being separate installed apps (a later
task flips ``INSTALLED_APPS``), nothing imports their individual ``admin``
modules automatically any more — so this file imports every one of them
directly to keep every admin registration live.

The import order below is alphabetical, not ``INSTALLED_APPS`` order — ruff's
isort rule (``select = ["ALL"]``, no ``I001`` exemption) enforces it on save.
That's fine: unlike ``world/apps.py``'s ``ready()`` order, import order here
carries no runtime effect — each ``import world.<pkg>.admin`` is independent
of the others, so any order registers every admin class with Django the same
way.

**Completeness is guarded by a test**, not by convention:
``world/tests/test_aggregators.py`` walks the ``world`` package with
``pkgutil``, finds every sub-package that actually defines an ``admin``
module (a bare ``admin.py`` or an ``admin/`` package), and asserts each one
is imported here. If a sub-package is ever missing from this file, its
admin registrations silently vanish — add the missing import here rather
than suppressing the test.

Sub-packages with no ``admin`` module at all (as of 2026-08-04:
``missions``, ``npc_services``, ``predicates``, ``staff_inbox``,
``tidings``) are intentionally absent.
"""

import world.achievements.admin
import world.action_points.admin
import world.agriculture.admin
import world.areas.admin
import world.assets.admin
import world.battles.admin
import world.boundaries.admin
import world.buildings.admin
import world.captivity.admin
import world.ceremonies.admin
import world.character_creation.admin
import world.character_sheets.admin
import world.checks.admin
import world.classes.admin
import world.clues.admin
import world.codex.admin
import world.combat.admin
import world.companions.admin
import world.conditions.admin
import world.consent.admin
import world.contributors.admin
import world.covenants.admin
import world.currency.admin
import world.distinctions.admin
import world.dreams.admin
import world.estates.admin
import world.events.admin
import world.fatigue.admin
import world.forms.admin
import world.game_clock.admin
import world.gm.admin
import world.goals.admin
import world.instances.admin
import world.items.admin
import world.journals.admin
import world.justice.admin
import world.locations.admin
import world.magic.admin
import world.mechanics.admin
import world.military.admin
import world.narrative.admin
import world.player_submissions.admin
import world.progression.admin
import world.projects.admin
import world.realms.admin
import world.registration.admin
import world.relationships.admin
import world.room_features.admin
import world.roster.admin
import world.scenes.admin
import world.secrets.admin
import world.ships.admin
import world.skills.admin
import world.societies.admin
import world.species.admin
import world.stories.admin
import world.tarot.admin
import world.tasking.admin
import world.traits.admin
import world.travel.admin
import world.vitals.admin
import world.weather.admin
import world.worship.admin  # noqa: F401

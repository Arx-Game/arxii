"""Tests for the starter GM battle-staging catalog seed (#2010).

Mirrors ``world/missions/tests/test_seed_missions.py``'s shape: proves the
"battles" cluster's starter blueprint/template catalog shape, plus the two
acceptance criteria every content seed must clear — re-running on a populated
DB is a no-op, and a staff edit to a seeded row survives a rerun. Uses
``seed_dev_database()`` (the Big Button) rather than calling
``seed_battle_staging_catalog()`` in isolation, exactly as a real deploy seeds
it (cluster ordering in ``world.seeds.clusters``).
"""

from __future__ import annotations

from django.test import TestCase

from world.battles.constants import BattleSideRole, FortificationKind, UnitQuality
from world.battles.models import (
    BattleMapBlueprint,
    BattleUnitTemplate,
    BlueprintBattlePlace,
    BlueprintFortification,
)
from world.seeds.database import seed_dev_database


class SeedBattleStagingCatalogTests(TestCase):
    """The "battles" cluster's starter staging catalog row shape."""

    def test_seeds_river_crossing_blueprint(self) -> None:
        seed_dev_database()

        blueprint = BattleMapBlueprint.objects.get(name="River Crossing")
        self.assertTrue(blueprint.is_active)
        places = {place.name: place for place in blueprint.places.all()}
        self.assertEqual(set(places), {"West Bank", "The Ford", "East Bank"})

        east_bank = places["East Bank"]
        fortification = east_bank.fortifications.get()
        self.assertEqual(fortification.defending_side_role, BattleSideRole.DEFENDER)

        # West Bank / The Ford carry no fortification of their own.
        self.assertFalse(places["West Bank"].fortifications.exists())
        self.assertFalse(places["The Ford"].fortifications.exists())

    def test_seeds_city_gates_blueprint(self) -> None:
        seed_dev_database()

        blueprint = BattleMapBlueprint.objects.get(name="City Gates")
        self.assertTrue(blueprint.is_active)
        places = {place.name: place for place in blueprint.places.all()}
        self.assertEqual(set(places), {"Gate Approach", "The Gates", "Inner Court"})

        the_gates = places["The Gates"]
        fortification = the_gates.fortifications.get()
        self.assertEqual(fortification.kind, FortificationKind.WALL)
        self.assertEqual(fortification.defending_side_role, BattleSideRole.DEFENDER)

        self.assertFalse(places["Gate Approach"].fortifications.exists())
        self.assertFalse(places["Inner Court"].fortifications.exists())

    def test_seeds_three_unit_templates_with_distinct_quality(self) -> None:
        seed_dev_database()

        names = ["Levy Spears", "Veteran Pikemen", "Raider Skirmishers"]
        templates = {t.name: t for t in BattleUnitTemplate.objects.filter(name__in=names)}
        self.assertEqual(len(templates), 3)

        qualities = {t.quality for t in templates.values()}
        self.assertEqual(len(qualities), 3, "quality must be distinct across the 3 templates")
        self.assertEqual(templates["Levy Spears"].quality, UnitQuality.LEVY)
        self.assertEqual(templates["Veteran Pikemen"].quality, UnitQuality.VETERAN)
        self.assertEqual(templates["Raider Skirmishers"].quality, UnitQuality.MILITIA)

        for template in templates.values():
            self.assertTrue(template.is_active)
            self.assertTrue(
                template.properties.exists(), f"{template.name} must carry at least 1 property"
            )
            self.assertTrue(
                template.capability_values.exists(),
                f"{template.name} must carry at least 1 capability value",
            )

    def test_rerun_is_idempotent_no_op(self) -> None:
        seed_dev_database()
        blueprint_count = BattleMapBlueprint.objects.count()
        place_count = BlueprintBattlePlace.objects.count()
        fortification_count = BlueprintFortification.objects.count()
        template_count = BattleUnitTemplate.objects.count()

        seed_dev_database()

        self.assertEqual(BattleMapBlueprint.objects.count(), blueprint_count)
        self.assertEqual(BlueprintBattlePlace.objects.count(), place_count)
        self.assertEqual(BlueprintFortification.objects.count(), fortification_count)
        self.assertEqual(BattleUnitTemplate.objects.count(), template_count)

    def test_rerun_preserves_staff_edit_to_template_strength(self) -> None:
        seed_dev_database()
        template = BattleUnitTemplate.objects.get(name="Levy Spears")
        template.strength = 999
        template.save(update_fields=["strength"])

        seed_dev_database()

        template.refresh_from_db()
        self.assertEqual(template.strength, 999)

    def test_rerun_preserves_staff_edit_to_blueprint_description(self) -> None:
        seed_dev_database()
        blueprint = BattleMapBlueprint.objects.get(name="River Crossing")
        blueprint.description = "Staff-rewritten description."
        blueprint.save(update_fields=["description"])

        seed_dev_database()

        blueprint.refresh_from_db()
        self.assertEqual(blueprint.description, "Staff-rewritten description.")

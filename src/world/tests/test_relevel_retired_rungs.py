"""The #4085 re-level keeps every child strictly below its parent.

The first version sent every retired row to Barony and failed the 2026-10-03 deploy on
production's Arvum (Region) over Arx (City). ``relevel()`` runs against the historical
``apps`` registry, as in ``test_backfill_sets_allegiance``; retired levels are written
with ``update()`` because ``Area.save`` runs ``full_clean`` and refuses them.
"""

from importlib import import_module

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, override_settings

from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.areas.models import Area

_migration = import_module("world.migrations.0170_relevel_retired_rungs")


def _historical_apps():
    """The historical ``apps`` registry as of this migration (see the 0198 test)."""
    with override_settings(MIGRATION_MODULES={}):
        loader = MigrationExecutor(connection).loader
        return loader.project_state(("arxii", "0170_relevel_retired_rungs")).apps


def _retire(area, level):
    Area.objects.filter(pk=area.pk).update_with_reason(
        reason="a retired level Area.save refuses", level=level
    )


def _level(area):
    Area.flush_instance_cache()
    return Area.objects.get(pk=area.pk).level


class RelevelTests(TestCase):
    def test_retired_row_without_a_large_child_becomes_a_barony(self):
        seat = AreaFactory(level=AreaLevel.CONTINENT)
        ward = AreaFactory(level=AreaLevel.WARD, parent=seat)
        _retire(seat, 50)
        _migration.relevel(_historical_apps(), None)
        assert _level(seat) == AreaLevel.BARONY
        assert _level(ward) == AreaLevel.WARD

    def test_retired_region_over_a_city_rises_above_it(self):
        region = AreaFactory(level=AreaLevel.CONTINENT)
        city = AreaFactory(level=AreaLevel.BARONY, parent=region)
        _retire(region, 50)
        _migration.relevel(_historical_apps(), None)
        assert _level(region) == AreaLevel.COUNTY
        assert _level(city) == AreaLevel.BARONY

    def test_retired_rows_stacked_are_relevelled_deepest_first(self):
        region = AreaFactory(level=AreaLevel.CONTINENT)
        old_barony = AreaFactory(level=AreaLevel.KINGDOM, parent=region)
        city = AreaFactory(level=AreaLevel.BARONY, parent=old_barony)
        _retire(region, 50)
        _retire(old_barony, 46)
        _migration.relevel(_historical_apps(), None)
        assert _level(city) == AreaLevel.BARONY
        assert _level(old_barony) == AreaLevel.COUNTY
        assert _level(region) == AreaLevel.DUCHY

    def test_retired_row_between_a_city_and_a_county_still_stops_the_deploy(self):
        county = AreaFactory(level=AreaLevel.COUNTY)
        region = AreaFactory(level=AreaLevel.BARONY, parent=county)
        city = AreaFactory(level=AreaLevel.WARD, parent=region)
        _retire(region, 50)
        _retire(city, AreaLevel.BARONY)
        with self.assertRaises(RuntimeError):
            _migration.relevel(_historical_apps(), None)

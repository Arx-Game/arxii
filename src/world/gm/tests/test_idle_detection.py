"""Tests for idle-table detection (#2004): staleness query + StaffWorkload section."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from world.gm.factories import GMProfileFactory, GMTableFactory
from world.gm.services import idle_tables, touch_gm_activity


class IdleTablesQueryTests(TestCase):
    def test_active_table_with_recent_activity_is_not_idle(self) -> None:
        gm = GMProfileFactory()
        touch_gm_activity(gm)
        GMTableFactory(gm=gm)
        self.assertEqual(idle_tables().count(), 0)

    def test_active_table_with_null_last_active_is_idle(self) -> None:
        gm = GMProfileFactory()  # last_active_at is None
        GMTableFactory(gm=gm)
        self.assertEqual(idle_tables().count(), 1)

    def test_active_table_with_old_activity_is_idle(self) -> None:
        gm = GMProfileFactory()
        gm.last_active_at = timezone.now() - timedelta(days=30)
        gm.save(update_fields=["last_active_at"])
        GMTableFactory(gm=gm)
        self.assertEqual(idle_tables().count(), 1)

    def test_archived_table_is_not_idle(self) -> None:
        from world.gm.constants import GMTableStatus

        gm = GMProfileFactory()  # never active
        GMTableFactory(gm=gm, status=GMTableStatus.ARCHIVED)
        self.assertEqual(idle_tables().count(), 0)

    def test_threshold_is_configurable(self) -> None:
        gm = GMProfileFactory()
        gm.last_active_at = timezone.now() - timedelta(days=5)
        gm.save(update_fields=["last_active_at"])
        GMTableFactory(gm=gm)
        # 5 days ago is idle at threshold=4, not idle at threshold=7
        self.assertEqual(idle_tables(threshold_days=4).count(), 1)
        self.assertEqual(idle_tables(threshold_days=7).count(), 0)

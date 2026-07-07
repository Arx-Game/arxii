"""Tests for GMLevelCap + GMLevelChange models and the default-cap seed."""

from django.db import IntegrityError
from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.gm.constants import GM_LEVEL_ORDER, GMLevel, gm_level_index
from world.gm.factories import GMProfileFactory, seed_default_gm_level_caps
from world.gm.models import GMLevelCap, GMLevelChange
from world.societies.constants import RenownRisk


class GmLevelIndexTest(TestCase):
    def test_ordering(self) -> None:
        assert gm_level_index(GMLevel.STARTING) < gm_level_index(GMLevel.JUNIOR)
        assert gm_level_index(GMLevel.JUNIOR) < gm_level_index(GMLevel.GM)
        assert gm_level_index(GMLevel.GM) < gm_level_index(GMLevel.EXPERIENCED)
        assert gm_level_index(GMLevel.EXPERIENCED) < gm_level_index(GMLevel.SENIOR)

    def test_matches_gm_level_order(self) -> None:
        for i, level in enumerate(GM_LEVEL_ORDER):
            assert gm_level_index(level) == i


class SeedDefaultGmLevelCapsTest(TestCase):
    def test_creates_five_rows_with_ratified_defaults(self) -> None:
        caps = seed_default_gm_level_caps()
        assert GMLevelCap.objects.count() == 5
        assert set(caps.keys()) == set(GMLevel.values)

        assert caps[GMLevel.STARTING].max_beat_risk == RenownRisk.LOW
        assert caps[GMLevel.JUNIOR].max_beat_risk == RenownRisk.MODERATE
        assert caps[GMLevel.GM].max_beat_risk == RenownRisk.HIGH
        assert caps[GMLevel.EXPERIENCED].max_beat_risk == RenownRisk.EXTREME
        assert caps[GMLevel.SENIOR].max_beat_risk == RenownRisk.EXTREME

        for level in (GMLevel.STARTING, GMLevel.JUNIOR, GMLevel.GM, GMLevel.EXPERIENCED):
            assert caps[level].allow_custom_stakes is False
        assert caps[GMLevel.SENIOR].allow_custom_stakes is True

        for level in GMLevel.values:
            assert caps[level].allow_global_scope_authoring is False

    def test_auto_clear_regional_for_experienced_and_senior(self) -> None:
        caps = seed_default_gm_level_caps()

        for level in (GMLevel.STARTING, GMLevel.JUNIOR, GMLevel.GM):
            assert caps[level].auto_clear_regional is False
        assert caps[GMLevel.EXPERIENCED].auto_clear_regional is True
        assert caps[GMLevel.SENIOR].auto_clear_regional is True

    def test_idempotent(self) -> None:
        first = seed_default_gm_level_caps()
        first_pks = {level: cap.pk for level, cap in first.items()}

        second = seed_default_gm_level_caps()

        assert GMLevelCap.objects.count() == 5
        for level, cap in second.items():
            assert cap.pk == first_pks[level]


class GMLevelCapModelTest(TestCase):
    def test_unique_per_level(self) -> None:
        GMLevelCap.objects.create(level=GMLevel.GM)
        with self.assertRaises(IntegrityError):
            GMLevelCap.objects.create(level=GMLevel.GM)


class GMLevelChangeModelTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.profile = GMProfileFactory()
        cls.staff = AccountFactory()

    def test_str(self) -> None:
        change = GMLevelChange.objects.create(
            profile=self.profile,
            old_level=GMLevel.STARTING,
            new_level=GMLevel.JUNIOR,
            changed_by=self.staff,
            reason="Demonstrated good judgment across several tables.",
        )
        result = str(change)
        assert "GMLevelChange(" in result
        assert self.profile.account.username in result
        assert GMLevel.STARTING in result
        assert GMLevel.JUNIOR in result

    def test_ordering_newest_first(self) -> None:
        older = GMLevelChange.objects.create(
            profile=self.profile,
            old_level=GMLevel.STARTING,
            new_level=GMLevel.JUNIOR,
            changed_by=self.staff,
            reason="First promotion.",
        )
        newer = GMLevelChange.objects.create(
            profile=self.profile,
            old_level=GMLevel.JUNIOR,
            new_level=GMLevel.GM,
            changed_by=self.staff,
            reason="Second promotion.",
        )
        assert list(GMLevelChange.objects.all()) == [newer, older]

    def test_related_name_on_profile(self) -> None:
        change = GMLevelChange.objects.create(
            profile=self.profile,
            old_level=GMLevel.STARTING,
            new_level=GMLevel.JUNIOR,
            changed_by=self.staff,
            reason="Reachable via profile.level_changes.",
        )
        assert list(self.profile.level_changes.all()) == [change]

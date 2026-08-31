"""Tests for the ``AreaBuildGrant`` warrant model and ``has_build_warrant`` (#3477).

``has_build_warrant`` checks a direct area match before ever touching
``AreaClosure`` (a Postgres materialized view, see ``world/areas/models.py``) —
the "no grant at all" and "grant matches the target area directly" and
"grant's level is too low" cases all resolve without a closure query, so they
run untagged on SQLite. Only subtree descent (the grant sits on an ancestor
area, not the target area itself) needs the closure walk, so those cases are
``@tag("postgres")``.
"""

from __future__ import annotations

from django.test import TestCase, tag

from evennia_extensions.factories import AccountFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.gm.factories import AreaBuildGrantFactory
from world.gm.models import AreaBuildGrant
from world.gm.services import has_build_warrant


class AreaBuildGrantModelTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.grant = AreaBuildGrantFactory()

    def test_creation(self) -> None:
        assert self.grant.pk is not None
        assert self.grant.max_level == AreaLevel.BUILDING
        assert self.grant.room_budget is None

    def test_str(self) -> None:
        result = str(self.grant)
        assert "AreaBuildGrant(" in result
        assert self.grant.account.username in result
        assert self.grant.area.name in result

    def test_room_budget_optional(self) -> None:
        grant = AreaBuildGrantFactory(room_budget=25)
        assert grant.room_budget == 25

    def test_multiple_grants_same_account_and_area_allowed(self) -> None:
        """No uniqueness constraint — a widened cap layers on top, doesn't replace."""
        AreaBuildGrantFactory(account=self.grant.account, area=self.grant.area)
        assert (
            AreaBuildGrant.objects.filter(account=self.grant.account, area=self.grant.area).count()
            == 2
        )


class HasBuildWarrantStaffAndNoGrantTests(TestCase):
    """Staff bypass and the no-grant refusal — neither touches AreaClosure."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.area = AreaFactory(level=AreaLevel.WARD)

    def test_staff_passes_with_no_grant(self) -> None:
        staff = AccountFactory(username="staff_builder", is_staff=True)
        assert has_build_warrant(staff, area=self.area, level=AreaLevel.BUILDING) is True

    def test_none_account_refused(self) -> None:
        assert has_build_warrant(None, area=self.area, level=AreaLevel.BUILDING) is False

    def test_no_grant_non_staff_refused(self) -> None:
        gm_account = AccountFactory(username="no_grant_gm", is_staff=False)
        assert has_build_warrant(gm_account, area=self.area, level=AreaLevel.BUILDING) is False


class HasBuildWarrantDirectAreaTests(TestCase):
    """Grant's area IS the target area — resolves on the direct-match fast path."""

    def test_direct_area_grant_passes(self) -> None:
        area = AreaFactory(level=AreaLevel.WARD)
        grant = AreaBuildGrantFactory(area=area, max_level=AreaLevel.WARD)
        assert has_build_warrant(grant.account, area=area, level=AreaLevel.BUILDING) is True

    def test_max_level_ceiling_refuses_direct(self) -> None:
        """A grant capped at BUILDING can't authorize a WARD-level create."""
        area = AreaFactory(level=AreaLevel.WARD)
        grant = AreaBuildGrantFactory(area=area, max_level=AreaLevel.BUILDING)
        assert has_build_warrant(grant.account, area=area, level=AreaLevel.WARD) is False

    def test_max_level_ceiling_exact_match_passes(self) -> None:
        area = AreaFactory(level=AreaLevel.WARD)
        grant = AreaBuildGrantFactory(area=area, max_level=AreaLevel.BUILDING)
        assert has_build_warrant(grant.account, area=area, level=AreaLevel.BUILDING) is True

    def test_grant_for_different_account_does_not_leak(self) -> None:
        area = AreaFactory(level=AreaLevel.WARD)
        AreaBuildGrantFactory(area=area, max_level=AreaLevel.WARD)
        other_account = AccountFactory(username="unrelated_gm", is_staff=False)
        assert has_build_warrant(other_account, area=area, level=AreaLevel.BUILDING) is False


class HasBuildWarrantSubtreeDescentTests(TestCase):
    """Grant sits on an ancestor area — requires the AreaClosure walk (Postgres-only)."""

    @tag("postgres")
    def test_ward_level_grant_passes_for_child_building(self) -> None:
        ward = AreaFactory(level=AreaLevel.WARD)
        building = AreaFactory(level=AreaLevel.BUILDING, parent=ward)
        grant = AreaBuildGrantFactory(area=ward, max_level=AreaLevel.WARD)

        assert has_build_warrant(grant.account, area=building, level=AreaLevel.BUILDING) is True

    @tag("postgres")
    def test_fails_outside_the_subtree(self) -> None:
        ward = AreaFactory(level=AreaLevel.WARD)
        other_ward = AreaFactory(level=AreaLevel.WARD)
        outside_building = AreaFactory(level=AreaLevel.BUILDING, parent=other_ward)
        grant = AreaBuildGrantFactory(area=ward, max_level=AreaLevel.WARD)

        assert (
            has_build_warrant(grant.account, area=outside_building, level=AreaLevel.BUILDING)
            is False
        )

    @tag("postgres")
    def test_descent_still_respects_max_level_ceiling(self) -> None:
        """A BUILDING-capped grant covers a child building at BUILDING level..."""
        ward = AreaFactory(level=AreaLevel.WARD)
        building = AreaFactory(level=AreaLevel.BUILDING, parent=ward)
        grant = AreaBuildGrantFactory(area=ward, max_level=AreaLevel.BUILDING)
        assert has_build_warrant(grant.account, area=building, level=AreaLevel.BUILDING) is True

        # ...but the same grant can't authorize a WARD-level create anywhere in
        # its own subtree, including the ward it's rooted on.
        assert has_build_warrant(grant.account, area=ward, level=AreaLevel.WARD) is False

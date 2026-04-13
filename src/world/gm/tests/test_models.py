"""Tests for GM system models."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from world.gm.constants import GMApplicationStatus, GMLevel, GMTableStatus
from world.gm.factories import (
    GMApplicationFactory,
    GMProfileFactory,
    GMTableFactory,
    GMTableMembershipFactory,
)


class GMProfileModelTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.profile = GMProfileFactory()

    def test_creation(self) -> None:
        assert self.profile.pk is not None
        assert self.profile.level == GMLevel.STARTING

    def test_str(self) -> None:
        result = str(self.profile)
        assert "GMProfile(" in result
        assert self.profile.account.username in result

    def test_one_profile_per_account(self) -> None:
        """Duplicate profile for same account raises IntegrityError."""
        with self.assertRaises(IntegrityError):
            GMProfileFactory(account=self.profile.account)

    def test_default_level(self) -> None:
        assert self.profile.level == GMLevel.STARTING


class GMApplicationModelTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.application = GMApplicationFactory()

    def test_creation(self) -> None:
        assert self.application.pk is not None
        assert self.application.status == GMApplicationStatus.PENDING

    def test_str(self) -> None:
        result = str(self.application)
        assert "GMApplication(" in result
        assert self.application.account.username in result

    def test_default_status(self) -> None:
        assert self.application.status == GMApplicationStatus.PENDING

    def test_staff_response_blank_by_default(self) -> None:
        assert self.application.staff_response == ""


class GMTableModelTest(TestCase):
    def test_creation(self) -> None:
        table = GMTableFactory()
        assert table.pk is not None
        assert table.status == GMTableStatus.ACTIVE
        assert table.archived_at is None

    def test_str_contains_name_and_gm(self) -> None:
        table = GMTableFactory()
        result = str(table)
        assert "GMTable(" in result
        assert table.name in result
        assert table.gm.account.username in result


class GMTableMembershipModelTest(TestCase):
    def test_creation(self) -> None:
        membership = GMTableMembershipFactory()
        assert membership.pk is not None
        assert membership.left_at is None

    def test_temporary_persona_rejected(self) -> None:
        from world.gm.models import GMTableMembership
        from world.scenes.constants import PersonaType
        from world.scenes.factories import PersonaFactory

        table = GMTableFactory()
        temp_persona = PersonaFactory(persona_type=PersonaType.TEMPORARY)
        m = GMTableMembership(table=table, persona=temp_persona)
        with self.assertRaises(ValidationError):
            m.clean()

    def test_unique_active_membership_constraint(self) -> None:
        m1 = GMTableMembershipFactory()
        with self.assertRaises(IntegrityError):
            GMTableMembershipFactory(table=m1.table, persona=m1.persona)

    def test_can_rejoin_after_leaving(self) -> None:
        m1 = GMTableMembershipFactory()
        m1.left_at = timezone.now()
        m1.save()
        # Should not raise — unique constraint only applies to active memberships
        m2 = GMTableMembershipFactory(table=m1.table, persona=m1.persona)
        assert m2.pk is not None
        assert m2.left_at is None

"""Tests for GMTable and GMTableMembership ViewSets."""

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.gm.constants import GMTableStatus
from world.gm.factories import (
    GMProfileFactory,
    GMTableFactory,
    GMTableMembershipFactory,
)
from world.scenes.constants import PersonaType
from world.scenes.factories import PersonaFactory


class GMTableListPermissionTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(is_superuser=True)
        cls.gm_account = AccountFactory()
        cls.gm = GMProfileFactory(account=cls.gm_account)
        cls.other_gm = GMProfileFactory()
        cls.my_table = GMTableFactory(gm=cls.gm)
        cls.other_table = GMTableFactory(gm=cls.other_gm)

    def setUp(self) -> None:
        self.client = APIClient()

    def test_staff_sees_all_tables(self) -> None:
        self.client.force_authenticate(user=self.staff)
        url = reverse("gm:gm-table-list")
        resp = self.client.get(url)
        assert resp.status_code == 200
        ids = {item["id"] for item in resp.data["results"]}
        assert self.my_table.pk in ids
        assert self.other_table.pk in ids

    def test_gm_sees_only_their_own_tables(self) -> None:
        self.client.force_authenticate(user=self.gm_account)
        url = reverse("gm:gm-table-list")
        resp = self.client.get(url)
        assert resp.status_code == 200
        ids = {item["id"] for item in resp.data["results"]}
        assert self.my_table.pk in ids
        assert self.other_table.pk not in ids


class GMTableArchiveTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(is_superuser=True)
        cls.user = AccountFactory()

    def setUp(self) -> None:
        self.client = APIClient()
        # Create fresh table per-test to avoid SharedMemoryModel cache carrying
        # status across rolled-back transactions.
        self.table = GMTableFactory()

    def test_staff_can_archive(self) -> None:
        self.client.force_authenticate(user=self.staff)
        url = reverse("gm:gm-table-archive", args=[self.table.pk])
        resp = self.client.post(url)
        assert resp.status_code == 200
        self.table.refresh_from_db()
        assert self.table.status == GMTableStatus.ARCHIVED

    def test_non_staff_cannot_archive(self) -> None:
        self.client.force_authenticate(user=self.user)
        url = reverse("gm:gm-table-archive", args=[self.table.pk])
        resp = self.client.post(url)
        assert resp.status_code == 403


class GMTableTransferOwnershipTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(is_superuser=True)

    def setUp(self) -> None:
        self.client = APIClient()
        self.table = GMTableFactory()
        self.new_gm = GMProfileFactory()

    def test_staff_can_transfer(self) -> None:
        self.client.force_authenticate(user=self.staff)
        url = reverse("gm:gm-table-transfer-ownership", args=[self.table.pk])
        resp = self.client.post(url, {"new_gm": self.new_gm.pk}, format="json")
        assert resp.status_code == 200
        self.table.refresh_from_db()
        assert self.table.gm == self.new_gm

    def test_missing_new_gm_returns_400(self) -> None:
        self.client.force_authenticate(user=self.staff)
        url = reverse("gm:gm-table-transfer-ownership", args=[self.table.pk])
        resp = self.client.post(url, {}, format="json")
        assert resp.status_code == 400
        assert "new_gm" in resp.data


class GMTableMembershipCreateTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(is_superuser=True)

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.staff)
        self.table = GMTableFactory()

    def test_create_membership(self) -> None:
        persona = PersonaFactory()
        url = reverse("gm:gm-table-membership-list")
        resp = self.client.post(
            url,
            {"table": self.table.pk, "persona": persona.pk},
            format="json",
        )
        assert resp.status_code == 201

    def test_temporary_persona_rejected(self) -> None:
        temp_persona = PersonaFactory(persona_type=PersonaType.TEMPORARY)
        url = reverse("gm:gm-table-membership-list")
        resp = self.client.post(
            url,
            {"table": self.table.pk, "persona": temp_persona.pk},
            format="json",
        )
        # Could be 400 or 422 depending on how DRF surfaces the ValidationError
        assert resp.status_code in (400, 422)


class GMTableMembershipDestroyTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(is_superuser=True)

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.staff)

    def test_destroy_soft_leaves(self) -> None:
        membership = GMTableMembershipFactory()
        url = reverse("gm:gm-table-membership-detail", args=[membership.pk])
        resp = self.client.delete(url)
        assert resp.status_code == 204
        membership.refresh_from_db()
        assert membership.left_at is not None

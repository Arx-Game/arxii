"""API tests for ``NPCRoleViewSet`` is_active editability (#728 residual).

The deleted D3 giver pages let staff disable a giver; the unified-offer Mission Studio
regressed that — ``NPCRole.is_active`` existed on the model but was absent from the
serializer, so the web editor couldn't toggle it. This locks the exposure + the PATCH path.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.npc_services.factories import NPCRoleFactory


def _staff_account(name: str):
    """An Account flagged is_staff for IsAdminUser checks."""
    account = AccountFactory(username=name)
    account.is_staff = True
    account.save(update_fields=["is_staff"])
    return account


class NPCRoleIsActiveTests(TestCase):
    URL = "/api/npc-services/roles/"

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = _staff_account("staff-roles-api")
        cls.role = NPCRoleFactory(name="role-active-test")

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def test_serializer_exposes_is_active(self) -> None:
        response = self.client.get(f"{self.URL}{self.role.pk}/")
        assert response.status_code == 200
        assert response.data["is_active"] is True

    def test_patch_can_deactivate_a_role(self) -> None:
        response = self.client.patch(
            f"{self.URL}{self.role.pk}/", {"is_active": False}, format="json"
        )
        assert response.status_code == 200
        self.role.refresh_from_db()
        assert self.role.is_active is False

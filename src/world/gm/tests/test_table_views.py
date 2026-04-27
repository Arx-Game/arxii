"""Tests for GMTable and GMTableMembership ViewSets."""

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.constants import GMTableStatus
from world.gm.factories import (
    GMProfileFactory,
    GMTableFactory,
    GMTableMembershipFactory,
)
from world.scenes.constants import PersonaType
from world.scenes.factories import PersonaFactory
from world.stories.factories import StoryFactory, StoryParticipationFactory


def _linked_persona(account):
    """Create a Persona linked to account via character_sheet -> character -> db_account.

    This is the canonical chain for GMTableMembership visibility checks:
    GMTableMembership.persona -> Persona.character_sheet
    -> CharacterSheet.character (ObjectDB) -> ObjectDB.db_account
    """
    char = CharacterFactory()
    char.db_account = account
    char.save()
    sheet = CharacterSheetFactory(character=char)
    return PersonaFactory(character_sheet=sheet), char


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


# ────────────────────────────────────────────────────────────────────────────────
# Wave 1 Gap 1: Player-facing table visibility via GMTableMembership
# ────────────────────────────────────────────────────────────────────────────────


class GMTablePlayerVisibilityTest(TestCase):
    """Gap 1: Players who are members of a table can see it in the list."""

    @classmethod
    def setUpTestData(cls) -> None:
        # GM and their table
        cls.gm_account = AccountFactory()
        cls.gm_profile = GMProfileFactory(account=cls.gm_account)
        cls.table = GMTableFactory(gm=cls.gm_profile)

        # Player with an active membership via linked persona
        cls.member_account = AccountFactory()
        cls.member_persona, cls.member_char = _linked_persona(cls.member_account)
        cls.membership = GMTableMembershipFactory(
            table=cls.table,
            persona=cls.member_persona,
        )

        # Unrelated account — no relationship to the table
        cls.outsider_account = AccountFactory()

        # Staff account
        cls.staff = AccountFactory(is_superuser=True)

        # Another table the member does NOT belong to
        cls.other_gm = GMProfileFactory()
        cls.other_table = GMTableFactory(gm=cls.other_gm)

    def setUp(self) -> None:
        self.client = APIClient()

    def _table_ids(self, account) -> set:
        self.client.force_authenticate(user=account)
        resp = self.client.get(reverse("gm:gm-table-list"))
        assert resp.status_code == 200
        return {item["id"] for item in resp.data["results"]}

    def test_member_can_see_their_table(self) -> None:
        ids = self._table_ids(self.member_account)
        assert self.table.pk in ids

    def test_member_cannot_see_unjoined_table(self) -> None:
        ids = self._table_ids(self.member_account)
        assert self.other_table.pk not in ids

    def test_outsider_cannot_see_table(self) -> None:
        ids = self._table_ids(self.outsider_account)
        assert self.table.pk not in ids
        assert self.other_table.pk not in ids

    def test_gm_sees_own_table(self) -> None:
        ids = self._table_ids(self.gm_account)
        assert self.table.pk in ids

    def test_staff_sees_all_tables(self) -> None:
        ids = self._table_ids(self.staff)
        assert self.table.pk in ids
        assert self.other_table.pk in ids

    def test_left_member_loses_visibility(self) -> None:
        """After soft-leaving, the member should no longer see the table."""
        # Create a separate account/persona/membership for this test to avoid
        # cross-test contamination — setUpTestData is class-level.
        leaver_account = AccountFactory()
        leaver_persona, _ = _linked_persona(leaver_account)
        membership = GMTableMembershipFactory(table=self.table, persona=leaver_persona)

        # Confirm visible before leaving
        self.client.force_authenticate(user=leaver_account)
        ids_before = {
            item["id"] for item in self.client.get(reverse("gm:gm-table-list")).data["results"]
        }
        assert self.table.pk in ids_before

        # Soft-leave
        resp = self.client.delete(reverse("gm:gm-table-membership-detail", args=[membership.pk]))
        assert resp.status_code == 204

        ids_after = {
            item["id"] for item in self.client.get(reverse("gm:gm-table-list")).data["results"]
        }
        assert self.table.pk not in ids_after


# ────────────────────────────────────────────────────────────────────────────────
# Wave 1 Gap 2: GMTableSerializer computed fields
# ────────────────────────────────────────────────────────────────────────────────


class GMTableComputedFieldsTest(TestCase):
    """Gap 2: member_count, story_count, viewer_role on GMTableSerializer."""

    @classmethod
    def setUpTestData(cls) -> None:
        # GM setup
        cls.gm_account = AccountFactory()
        cls.gm_profile = GMProfileFactory(account=cls.gm_account)
        cls.table = GMTableFactory(gm=cls.gm_profile)

        # Active member
        cls.member_account = AccountFactory()
        cls.member_persona, cls.member_char = _linked_persona(cls.member_account)
        GMTableMembershipFactory(table=cls.table, persona=cls.member_persona)

        # A second member (to verify member_count > 1)
        cls.member2_account = AccountFactory()
        cls.member2_persona, cls.member2_char = _linked_persona(cls.member2_account)
        GMTableMembershipFactory(table=cls.table, persona=cls.member2_persona)

        # Guest: story participant at this table but NOT a table member
        cls.guest_account = AccountFactory()
        cls.guest_char = CharacterFactory()
        cls.guest_char.db_account = cls.guest_account
        cls.guest_char.save()
        cls.guest_story = StoryFactory(primary_table=cls.table)
        cls.guest_participation = StoryParticipationFactory(
            story=cls.guest_story,
            character=cls.guest_char,
            is_active=True,
        )

        # Story at this table (story_count)
        cls.story = StoryFactory(primary_table=cls.table)

        # Staff
        cls.staff = AccountFactory(is_superuser=True)

        # Outsider with no relationship
        cls.outsider_account = AccountFactory()

    def setUp(self) -> None:
        self.client = APIClient()

    def _get_table_data(self, account) -> dict:
        self.client.force_authenticate(user=account)
        resp = self.client.get(reverse("gm:gm-table-detail", args=[self.table.pk]))
        assert resp.status_code == 200
        return resp.data

    def test_member_count(self) -> None:
        data = self._get_table_data(self.staff)
        assert data["member_count"] == 2

    def test_story_count(self) -> None:
        data = self._get_table_data(self.staff)
        # Two stories: cls.guest_story and cls.story both have primary_table=cls.table
        assert data["story_count"] == 2

    def test_viewer_role_gm(self) -> None:
        data = self._get_table_data(self.gm_account)
        assert data["viewer_role"] == "gm"

    def test_viewer_role_staff(self) -> None:
        data = self._get_table_data(self.staff)
        assert data["viewer_role"] == "staff"

    def test_viewer_role_member(self) -> None:
        data = self._get_table_data(self.member_account)
        assert data["viewer_role"] == "member"

    def test_viewer_role_guest(self) -> None:
        # Staff retrieves on behalf isn't the right call — we need the guest to be
        # able to reach the endpoint. Guests won't be in get_queryset unless they're
        # also in a story at the table — but get_queryset only adds tables where the
        # user is a GM or an active GMTableMembership holder.
        # Guests are NOT in get_queryset, so we use staff to retrieve and test the
        # serializer logic directly via the serializer context.
        from world.gm.models import GMTable
        from world.gm.serializers import GMTableSerializer

        table = GMTable.objects.get(pk=self.table.pk)

        class FakeRequest:
            user = self.guest_account

        serializer = GMTableSerializer(table, context={"request": FakeRequest()})
        assert serializer.data["viewer_role"] == "guest"

    def test_viewer_role_none(self) -> None:
        from world.gm.models import GMTable
        from world.gm.serializers import GMTableSerializer

        table = GMTable.objects.get(pk=self.table.pk)

        class FakeRequest:
            user = self.outsider_account

        serializer = GMTableSerializer(table, context={"request": FakeRequest()})
        assert serializer.data["viewer_role"] == "none"


# ────────────────────────────────────────────────────────────────────────────────
# Wave 1 Gap 3: Player-facing membership visibility
# ────────────────────────────────────────────────────────────────────────────────


class GMTableMembershipPlayerVisibilityTest(TestCase):
    """Gap 3: Active members can list memberships at tables they belong to."""

    @classmethod
    def setUpTestData(cls) -> None:
        # GM and table
        cls.gm_account = AccountFactory()
        cls.gm_profile = GMProfileFactory(account=cls.gm_account)
        cls.table = GMTableFactory(gm=cls.gm_profile)

        # Two members
        cls.member_a_account = AccountFactory()
        cls.member_a_persona, _ = _linked_persona(cls.member_a_account)
        cls.membership_a = GMTableMembershipFactory(table=cls.table, persona=cls.member_a_persona)

        cls.member_b_account = AccountFactory()
        cls.member_b_persona, _ = _linked_persona(cls.member_b_account)
        cls.membership_b = GMTableMembershipFactory(table=cls.table, persona=cls.member_b_persona)

        # Unrelated table and its membership (outsider should NOT see this)
        cls.outsider_account = AccountFactory()
        cls.other_gm = GMProfileFactory()
        cls.other_table = GMTableFactory(gm=cls.other_gm)
        cls.other_persona, _ = _linked_persona(cls.outsider_account)
        cls.other_membership = GMTableMembershipFactory(
            table=cls.other_table, persona=cls.other_persona
        )

        cls.staff = AccountFactory(is_superuser=True)

    def setUp(self) -> None:
        self.client = APIClient()

    def _membership_ids(self, account) -> set:
        self.client.force_authenticate(user=account)
        resp = self.client.get(reverse("gm:gm-table-membership-list"))
        assert resp.status_code == 200
        return {item["id"] for item in resp.data["results"]}

    def test_member_can_see_own_membership(self) -> None:
        ids = self._membership_ids(self.member_a_account)
        assert self.membership_a.pk in ids

    def test_member_can_see_other_member_at_same_table(self) -> None:
        """Members see the full roster for their table (needed for Wave 4 Members tab)."""
        ids = self._membership_ids(self.member_a_account)
        assert self.membership_b.pk in ids

    def test_member_cannot_see_memberships_at_other_table(self) -> None:
        """Member A cannot see memberships at unrelated tables."""
        ids = self._membership_ids(self.member_a_account)
        assert self.other_membership.pk not in ids

    def test_gm_sees_all_memberships_at_their_table(self) -> None:
        ids = self._membership_ids(self.gm_account)
        assert self.membership_a.pk in ids
        assert self.membership_b.pk in ids

    def test_gm_cannot_see_memberships_at_another_gms_table(self) -> None:
        ids = self._membership_ids(self.gm_account)
        assert self.other_membership.pk not in ids

    def test_staff_sees_all_memberships(self) -> None:
        ids = self._membership_ids(self.staff)
        assert self.membership_a.pk in ids
        assert self.membership_b.pk in ids
        assert self.other_membership.pk in ids

    def test_outsider_cannot_see_memberships_they_dont_belong_to(self) -> None:
        """Account with no active membership at cls.table cannot see cls.membership_a."""
        # The outsider_account has membership at other_table, not at cls.table
        ids = self._membership_ids(self.outsider_account)
        assert self.membership_a.pk not in ids
        assert self.membership_b.pk not in ids

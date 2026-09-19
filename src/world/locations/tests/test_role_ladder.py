"""The access ladder: guest, tenant, trustee, owner (#3902).

These are the tests the sweep needed and did not have. Every call site that used to
read ``is_owner(p, r) or is_tenant(p, r)`` now names a rung, and the thing worth
pinning is not any one of those sites but the comparison underneath them: that a
guest clears passage and nothing else, that a tenant stops short of granting tenancy,
that a trustee stops short of the deed, and that an owner clears all of it without
holding a grant at all.

They run on Postgres because the cascade walks ``AreaClosure``, a materialized view
that does not exist in the SQLite tier.
"""

from datetime import timedelta

from django.test import TestCase, tag
from django.utils import timezone

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.locations.constants import OWNER_RANK, HolderType, LocationParentType, LocationRole
from world.locations.models import LocationOwnership, LocationTenancy
from world.locations.services import (
    TenancyGrantNotPermitted,
    assign_room_tenant,
    can_grant,
    end_room_tenancy,
    grant_tenancy,
    has_standing,
    role_at,
)
from world.scenes.factories import PersonaFactory
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory


@tag("postgres")
class RoleLadderTests(TestCase):
    """What each rung clears, read straight off ``has_standing``."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.area = AreaFactory(level=AreaLevel.WARD)
        cls.profile = RoomProfileFactory(area=cls.area)
        cls.room = cls.profile.objectdb

        cls.owner = PersonaFactory()
        LocationOwnership.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=cls.profile,
            holder_type=HolderType.PERSONA,
            holder_persona=cls.owner,
        )
        cls.guest = PersonaFactory()
        cls.tenant = PersonaFactory()
        cls.trustee = PersonaFactory()
        for persona, kind in (
            (cls.guest, LocationRole.GUEST),
            (cls.tenant, LocationRole.TENANT),
            (cls.trustee, LocationRole.TRUSTEE),
        ):
            LocationTenancy.objects.create(
                parent_type=LocationParentType.ROOM,
                room_profile=cls.profile,
                tenant_type=HolderType.PERSONA,
                tenant_persona=persona,
                kind=kind,
            )
        cls.stranger = PersonaFactory()

    def test_a_guest_clears_passage_and_nothing_above_it(self) -> None:
        assert has_standing(self.guest, self.room, at_least=LocationRole.GUEST)
        assert not has_standing(self.guest, self.room, at_least=LocationRole.TENANT)
        assert not has_standing(self.guest, self.room, at_least=LocationRole.TRUSTEE)

    def test_a_tenant_clears_passage_and_the_house_but_not_home_state(self) -> None:
        assert has_standing(self.tenant, self.room, at_least=LocationRole.GUEST)
        assert has_standing(self.tenant, self.room, at_least=LocationRole.TENANT)
        assert not has_standing(self.tenant, self.room, at_least=LocationRole.TRUSTEE)

    def test_a_trustee_clears_every_rung(self) -> None:
        for rung in (LocationRole.GUEST, LocationRole.TENANT, LocationRole.TRUSTEE):
            assert has_standing(self.trustee, self.room, at_least=rung)

    def test_an_owner_clears_every_rung_while_holding_no_grant(self) -> None:
        """The deed is a different row, and it outranks anything on the ladder."""
        assert not LocationTenancy.objects.filter(tenant_persona=self.owner).exists()
        for rung in (LocationRole.GUEST, LocationRole.TENANT, LocationRole.TRUSTEE):
            assert has_standing(self.owner, self.room, at_least=rung)
        assert role_at(self.owner, self.room) == OWNER_RANK

    def test_a_stranger_clears_nothing_and_a_none_persona_is_not_a_crash(self) -> None:
        assert not has_standing(self.stranger, self.room, at_least=LocationRole.GUEST)
        assert role_at(self.stranger, self.room) is None
        assert not has_standing(None, self.room, at_least=LocationRole.GUEST)
        assert role_at(None, self.room) is None

    def test_role_at_reports_the_highest_of_several_concurrent_grants(self) -> None:
        """Concurrent grants are legal by design, so the answer is the max, not the first."""
        LocationTenancy.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=self.profile,
            tenant_type=HolderType.PERSONA,
            tenant_persona=self.guest,
            kind=LocationRole.TRUSTEE,
        )
        assert has_standing(self.guest, self.room, at_least=LocationRole.TRUSTEE)

    def test_an_expired_grant_confers_nothing(self) -> None:
        lapsed = PersonaFactory()
        LocationTenancy.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=self.profile,
            tenant_type=HolderType.PERSONA,
            tenant_persona=lapsed,
            kind=LocationRole.TRUSTEE,
            ends_at=timezone.now() - timedelta(days=1),
        )
        assert not has_standing(lapsed, self.room, at_least=LocationRole.GUEST)


@tag("postgres")
class RoleLadderThroughOrganizationTests(TestCase):
    """A grant held by an organization carries its rung to the org's current members."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.area = AreaFactory(level=AreaLevel.WARD)
        cls.profile = RoomProfileFactory(area=cls.area)
        cls.room = cls.profile.objectdb
        cls.house = OrganizationFactory()
        LocationTenancy.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=cls.profile,
            tenant_type=HolderType.ORGANIZATION,
            tenant_organization=cls.house,
            kind=LocationRole.TRUSTEE,
        )
        cls.member = PersonaFactory()
        OrganizationMembershipFactory(organization=cls.house, persona=cls.member)
        cls.outsider = PersonaFactory()

    def test_a_member_inherits_the_org_grants_rung(self) -> None:
        assert has_standing(self.member, self.room, at_least=LocationRole.TRUSTEE)

    def test_an_outsider_inherits_nothing(self) -> None:
        assert not has_standing(self.outsider, self.room, at_least=LocationRole.GUEST)


@tag("postgres")
class GrantAuthorizationTests(TestCase):
    """Who may hand out what, and who may take it back."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.area = AreaFactory(level=AreaLevel.WARD)
        cls.profile = RoomProfileFactory(area=cls.area)
        cls.room = cls.profile.objectdb
        cls.owner = PersonaFactory()
        LocationOwnership.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=cls.profile,
            holder_type=HolderType.PERSONA,
            holder_persona=cls.owner,
        )
        cls.tenant = PersonaFactory()
        LocationTenancy.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=cls.profile,
            tenant_type=HolderType.PERSONA,
            tenant_persona=cls.tenant,
            kind=LocationRole.TENANT,
        )
        cls.trustee = PersonaFactory()
        LocationTenancy.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=cls.profile,
            tenant_type=HolderType.PERSONA,
            tenant_persona=cls.trustee,
            kind=LocationRole.TRUSTEE,
        )
        cls.guest = PersonaFactory()
        LocationTenancy.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=cls.profile,
            tenant_type=HolderType.PERSONA,
            tenant_persona=cls.guest,
            kind=LocationRole.GUEST,
        )

    def test_a_tenant_may_hand_out_a_key_but_not_a_tenancy(self) -> None:
        assert can_grant(self.tenant, self.room, LocationRole.GUEST)
        assert not can_grant(self.tenant, self.room, LocationRole.TENANT)
        assert not can_grant(self.tenant, self.room, LocationRole.TRUSTEE)

    def test_a_trustee_may_hand_out_a_tenancy(self) -> None:
        assert can_grant(self.trustee, self.room, LocationRole.GUEST)
        assert can_grant(self.trustee, self.room, LocationRole.TENANT)
        assert can_grant(self.trustee, self.room, LocationRole.TRUSTEE)

    def test_a_guest_may_hand_out_nothing(self) -> None:
        assert not can_grant(self.guest, self.room, LocationRole.GUEST)

    def test_grant_tenancy_enforces_the_ladder_rather_than_trusting_its_caller(self) -> None:
        """The old docstring deferred this to callers who did not do it (#3902)."""
        with self.assertRaises(TenancyGrantNotPermitted):
            grant_tenancy(
                kind=LocationRole.TENANT,
                room_profile=self.profile,
                tenant_persona=PersonaFactory(),
                granted_by=self.tenant,
            )

    def test_a_system_grant_passes_no_granter_and_is_allowed(self) -> None:
        """Character generation, admin and seeds have no granting persona."""
        row = grant_tenancy(
            kind=LocationRole.TENANT,
            room_profile=self.profile,
            tenant_persona=PersonaFactory(),
        )
        assert row.granted_by is None

    def test_assign_room_tenant_records_who_handed_it_over(self) -> None:
        row = assign_room_tenant(
            persona=self.tenant,
            room=self.room,
            tenant_persona=PersonaFactory(),
            kind=LocationRole.GUEST,
        )
        assert row.kind == LocationRole.GUEST
        assert row.granted_by == self.tenant

    def test_a_holder_may_always_end_their_own_grant(self) -> None:
        row = LocationTenancy.objects.get(tenant_persona=self.guest)
        ended = end_room_tenancy(persona=self.guest, tenancy=row)
        assert ended.ends_at is not None

    def test_revoking_a_trustee_is_the_owners_alone(self) -> None:
        row = LocationTenancy.objects.get(tenant_persona=self.trustee)
        with self.assertRaises(Exception) as caught:
            end_room_tenancy(persona=self.tenant, tenancy=row)
        assert "trustee" in str(caught.exception).lower()
        assert end_room_tenancy(persona=self.owner, tenancy=row).ends_at is not None

    def test_a_tenant_may_revoke_the_key_they_could_have_granted(self) -> None:
        row = LocationTenancy.objects.get(tenant_persona=self.guest)
        assert end_room_tenancy(persona=self.tenant, tenancy=row).ends_at is not None

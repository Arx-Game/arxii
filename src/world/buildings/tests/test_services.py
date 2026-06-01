"""Tests for the buildings service layer."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import CharacterFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.buildings.constants import PermitEligibility
from world.buildings.factories import (
    BuildingPermitDetailsFactory,
)
from world.buildings.seeds import ensure_building_permit_template, ensure_house_kind
from world.buildings.services import (
    MATERIAL_BASE_BOOST,
    PermitAlreadyConsumedError,
    PermitHolderMismatchError,
    PermitIssuanceError,
    PermitKindNotAllowedError,
    PermitSiteNotOutdoorError,
    PermitSizeExceedsCapError,
    PermitWardNotApprovedError,
    contribution_value_for_construction,
    issue_permit,
    validate_permit_site,
)
from world.character_sheets.factories import CharacterSheetFactory


def _pc():
    """A Character + sheet (auto-PRIMARY persona) ready for tests."""
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    return character, sheet.primary_persona


class IssuePermitTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        # Seed the BuildingPermit template + House kind.
        cls.template = ensure_building_permit_template()
        cls.house = ensure_house_kind()

    def _offer_with_details(self):
        """Create an NPCServiceOffer (PERMIT) + PermitOfferDetails pointing at House."""
        from world.npc_services.constants import DrawMode, OfferKind
        from world.npc_services.factories import (
            NPCRoleFactory,
            NPCServiceOfferFactory,
            PermitOfferDetailsFactory,
        )

        role = NPCRoleFactory(name="clerk")
        offer = NPCServiceOfferFactory(role=role, kind=OfferKind.PERMIT, draw_mode=DrawMode.MENU)
        details = PermitOfferDetailsFactory(
            offer=offer, building_kind=self.house, default_max_target_size=8
        )
        return offer, details

    def test_issue_permit_creates_instance_and_details(self) -> None:
        offer, _details = self._offer_with_details()
        _character, persona = _pc()
        result = issue_permit(offer, persona)
        self.assertEqual(result.payload["holder_persona_pk"], persona.pk)
        permit_pk = result.payload["permit_pk"]
        from world.buildings.models import BuildingPermitDetails

        permit = BuildingPermitDetails.objects.get(pk=permit_pk)
        self.assertEqual(permit.holder_persona_id, persona.pk)
        self.assertEqual(permit.building_kind, self.house)
        self.assertEqual(permit.max_target_size, 8)
        self.assertIsNone(permit.consumed_at)

    def test_issue_permit_raises_when_details_missing_kind(self) -> None:
        from world.npc_services.constants import OfferKind
        from world.npc_services.factories import (
            NPCRoleFactory,
            NPCServiceOfferFactory,
            PermitOfferDetailsFactory,
        )

        role = NPCRoleFactory(name="bad-clerk")
        offer = NPCServiceOfferFactory(role=role, kind=OfferKind.PERMIT)
        PermitOfferDetailsFactory(offer=offer, building_kind=None)
        _character, persona = _pc()
        with self.assertRaises(PermitIssuanceError):
            issue_permit(offer, persona)


class ValidatePermitSiteTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.house = ensure_house_kind()

    def _ward_with_permit_policy(self, *, allow_house=True, eligibility=PermitEligibility.OPEN):
        ward = AreaFactory(level=AreaLevel.WARD, name="Test Ward")
        ward.permit_eligibility = eligibility
        ward.save(update_fields=["permit_eligibility"])
        if allow_house:
            ward.allowed_building_kinds.add(self.house)
        return ward

    def _outdoor_room_in_ward(self, ward):
        from evennia_extensions.factories import ObjectDBFactory
        from evennia_extensions.models import RoomProfile

        site_area = AreaFactory(level=AreaLevel.NEIGHBORHOOD, parent=ward)
        room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        # Room's at_object_creation may have auto-created the profile; use
        # update_or_create so we own the area + is_outdoor flag.
        RoomProfile.objects.update_or_create(
            objectdb=room, defaults={"area": site_area, "is_outdoor": True}
        )
        return room

    def test_consumed_permit_rejected(self) -> None:
        ward = self._ward_with_permit_policy()
        room = self._outdoor_room_in_ward(ward)
        _character, persona = _pc()
        permit = BuildingPermitDetailsFactory(
            holder_persona=persona,
            building_kind=self.house,
            consumed_at=timezone.now() - timedelta(days=1),
        )
        with self.assertRaises(PermitAlreadyConsumedError):
            validate_permit_site(permit, room, persona, target_size=5)

    def test_wrong_persona_rejected(self) -> None:
        ward = self._ward_with_permit_policy()
        room = self._outdoor_room_in_ward(ward)
        _character_a, persona_a = _pc()
        _character_b, persona_b = _pc()
        permit = BuildingPermitDetailsFactory(holder_persona=persona_a, building_kind=self.house)
        permit.approved_wards.add(ward)
        with self.assertRaises(PermitHolderMismatchError):
            validate_permit_site(permit, room, persona_b, target_size=5)

    def test_indoor_room_rejected(self) -> None:
        from evennia_extensions.factories import ObjectDBFactory
        from evennia_extensions.models import RoomProfile

        ward = self._ward_with_permit_policy()
        site_area = AreaFactory(level=AreaLevel.NEIGHBORHOOD, parent=ward)
        room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        RoomProfile.objects.update_or_create(
            objectdb=room, defaults={"area": site_area, "is_outdoor": False}
        )
        _character, persona = _pc()
        permit = BuildingPermitDetailsFactory(holder_persona=persona, building_kind=self.house)
        permit.approved_wards.add(ward)
        with self.assertRaises(PermitSiteNotOutdoorError):
            validate_permit_site(permit, room, persona, target_size=5)

    def test_unapproved_ward_rejected(self) -> None:
        ward = self._ward_with_permit_policy()
        room = self._outdoor_room_in_ward(ward)
        _character, persona = _pc()
        permit = BuildingPermitDetailsFactory(holder_persona=persona, building_kind=self.house)
        # Permit does NOT include this ward in approved_wards
        with self.assertRaises(PermitWardNotApprovedError):
            validate_permit_site(permit, room, persona, target_size=5)

    def test_ward_kind_not_allowed_rejected(self) -> None:
        ward = self._ward_with_permit_policy(allow_house=False)
        room = self._outdoor_room_in_ward(ward)
        _character, persona = _pc()
        permit = BuildingPermitDetailsFactory(holder_persona=persona, building_kind=self.house)
        permit.approved_wards.add(ward)
        with self.assertRaises(PermitKindNotAllowedError):
            validate_permit_site(permit, room, persona, target_size=5)

    def test_size_over_cap_rejected(self) -> None:
        ward = self._ward_with_permit_policy()
        room = self._outdoor_room_in_ward(ward)
        _character, persona = _pc()
        permit = BuildingPermitDetailsFactory(
            holder_persona=persona, building_kind=self.house, max_target_size=5
        )
        permit.approved_wards.add(ward)
        with self.assertRaises(PermitSizeExceedsCapError):
            validate_permit_site(permit, room, persona, target_size=10)

    def test_valid_permit_passes(self) -> None:
        ward = self._ward_with_permit_policy()
        room = self._outdoor_room_in_ward(ward)
        _character, persona = _pc()
        permit = BuildingPermitDetailsFactory(
            holder_persona=persona, building_kind=self.house, max_target_size=10
        )
        permit.approved_wards.add(ward)
        result = validate_permit_site(permit, room, persona, target_size=5)
        self.assertEqual(result.ward, ward)
        self.assertEqual(result.permit, permit)


class ContributionValueTests(TestCase):
    """Material contributions are inherently superior to raw money."""

    def test_money_face_value(self) -> None:
        from world.projects.constants import ContributionKind
        from world.projects.factories import ContributionFactory

        contribution = ContributionFactory(kind=ContributionKind.MONEY, money_amount=500)
        self.assertEqual(contribution_value_for_construction(contribution), 500)

    def test_baseline_material_above_face_value(self) -> None:
        from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
        from world.projects.constants import ContributionKind
        from world.projects.factories import ContributionFactory

        template = ItemTemplateFactory(value=100, is_stackable=True, max_stack_size=100)
        instance = ItemInstanceFactory(template=template, quantity=10, lore_value=0)
        contribution = ContributionFactory(kind=ContributionKind.ITEM, item_instance=instance)
        # value=100, quantity=10, lore_value=0: 100 * 1.0 * 1.10 * 10 = 1100
        expected = int(100 * MATERIAL_BASE_BOOST * 10)
        self.assertEqual(contribution_value_for_construction(contribution), expected)

    def test_lore_value_scales_construction_value(self) -> None:
        from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
        from world.projects.constants import ContributionKind
        from world.projects.factories import ContributionFactory

        template = ItemTemplateFactory(value=100, is_stackable=True, max_stack_size=100)
        # lore_value=900: multiplier = 1 + 900/100 = 10x on top of base 1.1
        instance = ItemInstanceFactory(template=template, quantity=10, lore_value=900)
        contribution = ContributionFactory(kind=ContributionKind.ITEM, item_instance=instance)
        # 100 * (1 + 900/100) * 1.10 * 10 = 100 * 10 * 1.10 * 10 = 11000
        expected = int(100 * 10 * MATERIAL_BASE_BOOST * 10)
        self.assertEqual(contribution_value_for_construction(contribution), expected)

    def test_ap_zero_value(self) -> None:
        from world.projects.constants import ContributionKind
        from world.projects.factories import ContributionFactory

        contribution = ContributionFactory(kind=ContributionKind.AP, ap_amount=10)
        self.assertEqual(contribution_value_for_construction(contribution), 0)


class ActivatePermitRoundtripTests(TestCase):
    """End-to-end: issue → activate → complete. Catches broken imports
    + missing handler registration that the per-function tests miss.
    """

    def _outdoor_room_in_ward(self, ward):
        from evennia_extensions.factories import ObjectDBFactory
        from evennia_extensions.models import RoomProfile

        site_area = AreaFactory(level=AreaLevel.NEIGHBORHOOD, parent=ward)
        room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        RoomProfile.objects.update_or_create(
            objectdb=room, defaults={"area": site_area, "is_outdoor": True}
        )
        return room

    def test_full_roundtrip_issue_activate_complete(self) -> None:
        from world.buildings.models import Building
        from world.buildings.services import activate_permit, complete_building_construction
        from world.items.constants import OwnershipEventType
        from world.items.models import OwnershipEvent

        ensure_building_permit_template()
        house = ensure_house_kind()
        ward = AreaFactory(level=AreaLevel.WARD, name="roundtrip-ward")
        ward.permit_eligibility = PermitEligibility.OPEN
        ward.save(update_fields=["permit_eligibility"])
        ward.allowed_building_kinds.add(house)

        room = self._outdoor_room_in_ward(ward)
        _character, persona = _pc()
        permit = BuildingPermitDetailsFactory(
            holder_persona=persona, building_kind=house, max_target_size=10
        )
        permit.approved_wards.add(ward)

        # Activate — exercises the previously-broken import path.
        project = activate_permit(
            permit_details=permit,
            site_room=room,
            acting_persona=persona,
            target_size=5,
            target_grandeur=5,
        )
        self.assertIsNotNone(project)
        permit.refresh_from_db()
        self.assertIsNotNone(permit.consumed_at)
        # ACTIVATED + CONSUMED audit rows.
        self.assertTrue(
            OwnershipEvent.objects.filter(
                item_instance=permit.item_instance,
                event_type=OwnershipEventType.ACTIVATED,
            ).exists()
        )
        self.assertTrue(
            OwnershipEvent.objects.filter(
                item_instance=permit.item_instance,
                event_type=OwnershipEventType.CONSUMED,
            ).exists()
        )

        # Complete — exercises the previously-unregistered project handler.
        building = complete_building_construction(project)
        self.assertEqual(building.kind, house)
        self.assertEqual(building.target_size, 5)
        self.assertEqual(building.max_rooms, house.rooms_per_size_tier * 5)
        # Idempotent — second call returns the existing Building.
        again = complete_building_construction(project)
        self.assertEqual(building.pk, again.pk)
        self.assertEqual(Building.objects.filter(source_project=project).count(), 1)

    def test_activate_permit_concurrent_via_select_for_update(self) -> None:
        """Second activation after first commit raises PermitAlreadyConsumedError."""
        from world.buildings.services import activate_permit

        ensure_building_permit_template()
        house = ensure_house_kind()
        ward = AreaFactory(level=AreaLevel.WARD, name="serialised-ward")
        ward.permit_eligibility = PermitEligibility.OPEN
        ward.save(update_fields=["permit_eligibility"])
        ward.allowed_building_kinds.add(house)
        room = self._outdoor_room_in_ward(ward)
        _character, persona = _pc()
        permit = BuildingPermitDetailsFactory(
            holder_persona=persona, building_kind=house, max_target_size=10
        )
        permit.approved_wards.add(ward)

        activate_permit(
            permit_details=permit,
            site_room=room,
            acting_persona=persona,
            target_size=5,
            target_grandeur=5,
        )
        # Re-activation must fail because the first call committed
        # consumed_at; the select_for_update would just serialize
        # but the consumed-at check still rejects.
        with self.assertRaises(PermitAlreadyConsumedError):
            activate_permit(
                permit_details=permit,
                site_room=room,
                acting_persona=persona,
                target_size=5,
                target_grandeur=5,
            )


class MaterialLoreEffectGuardTests(TestCase):
    """units_per_tier=0 must be rejected by validation + DB constraint."""

    def test_units_per_tier_zero_rejected_by_check_constraint(self) -> None:
        from django.db import IntegrityError

        from world.buildings.models import MaterialLoreEffect
        from world.items.factories import ItemTemplateFactory

        template = ItemTemplateFactory()
        with self.assertRaises(IntegrityError):
            MaterialLoreEffect.objects.create(
                template=template,
                target_stat="resonance_amp",
                units_per_tier=0,
                magnitude_per_tier=1,
            )

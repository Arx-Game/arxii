"""Natural weapons refused where no journey seam reaches (#4898, slice 4 of #4844).

Each path that can take an item off its holder or use it up must refuse a natural weapon
with a plain message, or, for a system sweep, leave it alone. These are service-level
checks for paths the journeys in ``integration_tests/test_natural_weapons_journeys.py`` do
not drive: a fence sale, an org vault deposit, a boon ask and its fulfilment, recycling,
the confiscation sentence, an estate's settlement, a stake forfeit, a rite gift, material
spending, and a construction project's item contributions.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.buildings.tests.test_services import _ContributionProjectMixin
from world.character_sheets.factories import CharacterSheetFactory
from world.items.constants import BodyRegion, EquipmentLayer, GearArchetype
from world.items.exceptions import NaturalWeaponNotRemovable
from world.items.factories import ItemTemplateFactory, TemplateSlotFactory
from world.items.models import EquippedItem, ItemInstance
from world.items.services.natural_weapons import provision_natural_weapon
from world.justice.tests.test_sentence_enforcement import _SentenceCaseMixin
from world.magic.constants import GiftKind
from world.magic.factories import GiftFactory

REFUSED = NaturalWeaponNotRemovable.user_message


def clawed_gift():
    template = ItemTemplateFactory(
        name="Refusal Claws", gear_archetype=GearArchetype.UNARMED, base_weapon_damage=5
    )
    for region in (BodyRegion.LEFT_HAND, BodyRegion.RIGHT_HAND):
        TemplateSlotFactory(
            template=template, body_region=region, equipment_layer=EquipmentLayer.SKIN
        )
    template.__dict__.pop("cached_slots", None)
    return GiftFactory(name="Refusal Claws", kind=GiftKind.MINOR, natural_weapon_template=template)


def claws_on(sheet) -> ItemInstance:
    return provision_natural_weapon(sheet, clawed_gift())


def still_held(test: TestCase, claws: ItemInstance, sheet) -> None:
    fresh = ItemInstance.objects.get(pk=claws.pk)
    test.assertIsNone(fresh.destroyed_at)
    test.assertEqual(fresh.holder_character_sheet_id, sheet.pk)
    test.assertIsNotNone(fresh.natural_weapon_gift_id)
    test.assertEqual(EquippedItem.objects.filter(item_instance=fresh).count(), 2)


class TransfersRefuseClaws(TestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.persona = self.sheet.primary_persona
        self.claws = claws_on(self.sheet)

    def test_a_fence_will_not_buy_them(self) -> None:
        from world.areas.models import Area
        from world.items.market.models import MarketSquare, MarketStall
        from world.items.market.services import MarketServiceError, sell_to_fence

        area = Area.objects.create(name="Refusal Docks", level=20)
        stall = MarketStall.objects.create(
            square=MarketSquare.objects.create(name="Refusal Market", area=area),
            name="The Back Door",
            stall_kind=MarketStall.StallKind.FENCE,
        )

        with self.assertRaises(MarketServiceError) as caught:
            sell_to_fence(self.persona, stall, self.claws)

        self.assertEqual(caught.exception.user_message, REFUSED)
        still_held(self, self.claws, self.sheet)

    def test_an_org_vault_will_not_take_them(self) -> None:
        from world.items.services.org_vault import deposit_item_to_vault
        from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory

        org = OrganizationFactory()
        OrganizationMembershipFactory(persona=self.persona, organization=org, rank=5)

        with self.assertRaises(ValidationError) as caught:
            deposit_item_to_vault(organization=org, persona=self.persona, item_instance=self.claws)

        self.assertEqual(caught.exception.messages, [REFUSED])
        still_held(self, self.claws, self.sheet)

    def test_nobody_can_ask_for_them_as_a_boon(self) -> None:
        from world.scenes.boon_services import _validate_held_item_ask

        asker = CharacterSheetFactory()
        ask = SimpleNamespace(item_instance_id=self.claws.pk)
        # The asker knows of the claws; the pointer gate is not what is under test.
        with (
            patch("world.scenes.boon_services.character_has_item_pointer", return_value=True),
            self.assertRaises(ValidationError) as caught,
        ):
            _validate_held_item_ask(ask, self.persona, asker)

        self.assertEqual(caught.exception.messages, [REFUSED])

    def test_a_granted_boon_cannot_hand_them_over(self) -> None:
        # The fulfilment raises ValidationError, which _resolve_boon catches and logs.
        from world.scenes.boon_services import _fulfill_held_item

        asker = CharacterSheetFactory()
        boon = SimpleNamespace(item_instance_id=self.claws.pk)
        request = SimpleNamespace(
            target_persona=self.persona, initiator_persona=asker.primary_persona
        )

        with self.assertRaises(ValidationError) as caught:
            _fulfill_held_item(boon, request)

        self.assertEqual(caught.exception.messages, [REFUSED])
        still_held(self, self.claws, self.sheet)

    def test_recycling_them_is_refused_before_any_salvage(self) -> None:
        from world.items.services.recycle import recycle_item

        before = ItemInstance.objects.count()

        with self.assertRaises(NaturalWeaponNotRemovable):
            recycle_item(item_instance=self.claws, actor_sheet=self.sheet)

        self.assertEqual(ItemInstance.objects.count(), before)
        still_held(self, self.claws, self.sheet)


class SweepsLeaveClawsAlone(TestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.claws = claws_on(self.sheet)

    def test_an_estate_neither_counts_nor_hands_them_on(self) -> None:
        from world.estates.services import _estate_has_assets, _sweep_residuary_items

        heir = CharacterSheetFactory().primary_persona

        self.assertFalse(_estate_has_assets(self.sheet))
        _sweep_residuary_items(self.sheet, heir, set())

        still_held(self, self.claws, self.sheet)

    def test_a_lost_stake_skips_them(self) -> None:
        from world.stories.services.stake_resolution import _write_item_forfeit

        _write_item_forfeit(
            SimpleNamespace(pk=1, column="lost"), SimpleNamespace(pk=2, subject_item=self.claws)
        )

        still_held(self, self.claws, self.sheet)

    def test_a_rite_will_not_take_them(self) -> None:
        from world.worship.exceptions import RiteGiftIsPartOfTheBody
        from world.worship.rite_services import read_rite_gifts

        with self.assertRaises(RiteGiftIsPartOfTheBody) as caught:
            read_rite_gifts(self.sheet, SimpleNamespace(being_id=None), [self.claws])

        self.assertEqual(caught.exception.user_message, REFUSED)

    def test_materials_never_spend_them(self) -> None:
        from world.items.exceptions import InsufficientMaterials
        from world.items.services.materials import consume_materials, gather_consumable_pks

        requirement = SimpleNamespace(
            item_template_id=self.claws.template_id,
            item_template=self.claws.template,
            material_category_id=None,
            material_category=None,
            min_quality_tier_id=None,
            min_quality_tier=None,
            quantity=1,
        )
        with self.assertRaises(InsufficientMaterials):
            gather_consumable_pks(available=[self.claws], requirements=[requirement])

        consume_materials([(self.claws, 1)])

        still_held(self, self.claws, self.sheet)


class ConfiscationLeavesClaws(_SentenceCaseMixin, TestCase):
    def test_a_confiscation_seizes_the_pack_but_not_the_claws(self) -> None:
        from evennia_extensions.factories import ObjectDBFactory
        from world.justice.constants import HUNTED_VALUE_FLOOR
        from world.justice.sentences import apply_confiscation

        brig_room = self._brig_room(self.kingdom)
        case = self._case(weight=HUNTED_VALUE_FLOOR)
        self._hold(case)
        sheet = case.persona.character_sheet
        character = sheet.character
        claws = claws_on(sheet)
        pack = ObjectDBFactory(db_typeclass_path="typeclasses.objects.Object", location=character)

        apply_confiscation(case)

        pack.refresh_from_db()
        self.assertEqual(pack.location, brig_room)
        self.assertEqual(ItemInstance.objects.get(pk=claws.pk).game_object.location, character)
        still_held(self, claws, sheet)


class ProjectsRefuseClaws(_ContributionProjectMixin, TestCase):
    def test_claws_cannot_be_contributed(self) -> None:
        from world.projects.constants import ContributionKind, ProjectStatus
        from world.projects.services import add_contribution

        project, _character, persona = self._project()
        project.status = ProjectStatus.ACTIVE
        project.save(update_fields=["status"])
        claws = claws_on(persona.character_sheet)

        with self.assertRaises(ValidationError) as caught:
            add_contribution(
                project=project,
                contributor_persona=persona,
                kind=ContributionKind.ITEM,
                item_instance=claws,
            )

        self.assertEqual(caught.exception.message_dict, {"item_instance": [REFUSED]})

    def test_completion_leaves_contributed_claws_alone(self) -> None:
        # A contribution row from before the refusal: the sweep skips it, never raises.
        from world.buildings.models import BuildingMaterial
        from world.buildings.services import complete_building_construction

        project, character, persona = self._project()
        gift = clawed_gift()
        claws = self._contribute(project, character, persona, natural_weapon_gift=gift)
        plain = self._contribute(project, character, persona)

        complete_building_construction(project)

        self.assertFalse(BuildingMaterial.objects.filter(item_instance_pk=claws.pk).exists())
        self.assertIsNone(ItemInstance.objects.get(pk=claws.pk).destroyed_at)
        self.assertIsNotNone(ItemInstance.objects.get(pk=plain.pk).destroyed_at)


class DeletingTheBodyTakesTheClaws(TestCase):
    """A deleted character or sheet leaves no marked claws behind, held by nobody."""

    def _marked_left(self, claws: ItemInstance) -> bool:
        return ItemInstance.objects.filter(pk=claws.pk, natural_weapon_gift__isnull=False).exists()

    def test_deleting_the_character_takes_the_claws(self) -> None:
        sheet = CharacterSheetFactory()
        claws = claws_on(sheet)
        gift = claws.natural_weapon_gift

        sheet.character.delete()

        self.assertFalse(self._marked_left(claws))
        gift.delete()  # nothing left to PROTECT it

    def test_deleting_the_sheet_in_the_admin_takes_the_claws(self) -> None:
        from evennia_extensions.factories import AccountFactory

        staff = AccountFactory(is_staff=True, is_superuser=True)
        sheet = CharacterSheetFactory()
        claws = claws_on(sheet)
        self.client.force_login(staff)

        response = self.client.post(
            f"/admin/arxii/charactersheet/{sheet.pk}/delete/", {"post": "yes"}
        )

        self.assertEqual(response.status_code, 302, response.content[:500])
        self.assertFalse(self._marked_left(claws))

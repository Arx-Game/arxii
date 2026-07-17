"""Golden Hare favor tokens (#2428): item-backed, deed-provenance, mint/redeem."""

from django.core.exceptions import ValidationError
from django.test import TestCase
from evennia.objects.models import ObjectDB

from world.character_sheets.factories import CharacterSheetFactory
from world.currency.models import FavorTokenDetails
from world.currency.services import mint_favor_token, redeem_favor_token
from world.items.constants import OwnershipEventType
from world.items.models import ItemInstance, OwnershipEvent
from world.societies.factories import OrganizationFactory


class MintFavorTokenTests(TestCase):
    """Per-test setUp (not setUpTestData): Evennia typeclass instances are not
    deepcopy-safe as class-level test data, and these tests walk
    ``sheet.character``."""

    def setUp(self):
        self.org = OrganizationFactory()
        self.recipient = CharacterSheetFactory()

    def test_mint_creates_item_in_inventory_and_detail_row(self):
        token = mint_favor_token(
            self.org,
            self.recipient,
            provenance_note="Cleared the Thornwood ambush",
        )
        self.assertIsInstance(token, FavorTokenDetails)
        self.assertEqual(token.issuing_organization_id, self.org.pk)
        self.assertEqual(token.provenance_note, "Cleared the Thornwood ambush")
        self.assertIsNotNone(token.minted_at)
        self.assertIsNone(token.redeemed_at)

        instance = token.item_instance
        self.assertEqual(instance.holder_character_sheet_id, self.recipient.pk)
        self.assertIsNotNone(instance.game_object)
        self.assertEqual(instance.game_object.location, self.recipient.character)
        self.assertEqual(instance.template.name, "Golden Hare")

    def test_mint_reuses_the_golden_hare_template(self):
        first = mint_favor_token(self.org, self.recipient, provenance_note="Deed one")
        second = mint_favor_token(self.org, self.recipient, provenance_note="Deed two")
        self.assertEqual(first.item_instance.template_id, second.item_instance.template_id)


class RedeemFavorTokenTests(TestCase):
    def setUp(self):
        self.org = OrganizationFactory()
        self.other_org = OrganizationFactory()
        self.recipient = CharacterSheetFactory()
        self.token = mint_favor_token(
            self.org,
            self.recipient,
            provenance_note="Escorted the caravan",
        )

    def test_redeem_marks_row_and_disposes_item(self):
        instance_pk = self.token.item_instance_id
        game_object_pk = self.token.item_instance.game_object.pk

        redeem_favor_token(self.token, redeemer_org=self.org)

        # Row survives — deed-provenance is never hard-deleted.
        row = FavorTokenDetails.objects.get(pk=self.token.pk)
        self.assertIsNotNone(row.redeemed_at)
        self.assertTrue(ItemInstance.objects.filter(pk=instance_pk).exists())
        instance = ItemInstance.objects.get(pk=instance_pk)
        self.assertIsNotNone(instance.destroyed_at)
        # Physical object leaves play but is not hard-deleted either.
        self.assertTrue(ObjectDB.objects.filter(pk=game_object_pk).exists())
        self.assertIsNone(ObjectDB.objects.get(pk=game_object_pk).location)

        event = OwnershipEvent.objects.filter(
            item_instance_id=instance_pk,
            event_type=OwnershipEventType.CONSUMED,
        ).first()
        self.assertIsNotNone(event)

    def test_double_redeem_raises(self):
        redeem_favor_token(self.token, redeemer_org=self.org)
        with self.assertRaises(ValidationError):
            redeem_favor_token(self.token, redeemer_org=self.org)

    def test_redeem_by_non_issuer_raises(self):
        with self.assertRaises(ValidationError):
            redeem_favor_token(self.token, redeemer_org=self.other_org)
        # Refused redemption leaves the token outstanding.
        row = FavorTokenDetails.objects.get(pk=self.token.pk)
        self.assertIsNone(row.redeemed_at)


class FavorTokenTradeableTests(TestCase):
    """A Golden Hare is an ordinary item once minted: no ownership coupling
    on the detail row (#2428 ruling — tradeable via existing item give/trade,
    no market machinery)."""

    def setUp(self):
        self.org = OrganizationFactory()
        self.giver = CharacterSheetFactory()
        self.receiver = CharacterSheetFactory()
        self.token = mint_favor_token(
            self.org,
            self.giver,
            provenance_note="Recovered the stolen relic",
        )

    def test_reassigning_the_item_does_not_touch_the_detail_row(self):
        instance = self.token.item_instance
        instance.holder_character_sheet = self.receiver
        instance.save(update_fields=["holder_character_sheet"])

        row = FavorTokenDetails.objects.get(pk=self.token.pk)
        self.assertEqual(row.issuing_organization_id, self.org.pk)
        self.assertEqual(row.provenance_note, "Recovered the stolen relic")
        self.assertIsNone(row.redeemed_at)

    def test_new_holder_can_still_redeem_with_the_issuer(self):
        instance = self.token.item_instance
        instance.holder_character_sheet = self.receiver
        instance.save(update_fields=["holder_character_sheet"])

        redeem_favor_token(self.token, redeemer_org=self.org)
        row = FavorTokenDetails.objects.get(pk=self.token.pk)
        self.assertIsNotNone(row.redeemed_at)

"""Independent item-use reads and retained complete service/REST behavior."""

from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from actions.factories import ConsequencePoolFactory
from evennia_extensions.factories import AccountFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.forms.factories import (
    CharacterFormFactory,
    CharacterFormValueFactory,
    FormTraitFactory,
    FormTraitOptionFactory,
)
from world.forms.services import learn_style
from world.items.exceptions import (
    BlendNotSupported,
    ItemNotAttuned,
    ItemNotUsable,
    MakeoverNotPermitted,
    NoChargesRemaining,
    StyleChoiceRequired,
    StyleNotKnown,
)
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.models import ItemTemplateAppearanceEffect, OwnershipEvent
from world.items.services import usage
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory


class UsageValidatorTests(TestCase):
    def setUp(self):
        self.sheet = CharacterSheetFactory()
        self.user = self.sheet.character
        self.trait = FormTraitFactory(is_cosmetic=True, composite_option=None)
        self.old = FormTraitOptionFactory(trait=self.trait)
        self.option = FormTraitOptionFactory(trait=self.trait, requires_teaching=False)
        self.exotic = FormTraitOptionFactory(trait=self.trait, requires_teaching=True)
        self.template = ItemTemplateFactory(
            is_consumable=True,
            max_charges=2,
            on_use_pool=None,
            requires_attunement=False,
        )
        self.effect = ItemTemplateAppearanceEffect.objects.create(
            item_template=self.template,
            trait=self.trait,
            target_option=None,
        )
        self.item = ItemInstanceFactory(
            template=self.template,
            holder_character_sheet=self.sheet,
            game_object=None,
            charges=2,
            quality_tier=None,
        )
        self.form = CharacterFormFactory(character=self.sheet)
        CharacterFormValueFactory(form=self.form, trait=self.trait, option=self.old)

    def bound(self):
        return usage.validate_item_use_bound(item_instance=self.item, user=self.user)

    def option_read(self, option_id):
        return usage.validate_item_use_option(
            item_instance=self.item,
            user=self.user,
            option_id=option_id,
        )

    def test_bound_checks_need_neither_target_nor_option(self):
        self.bound()
        self.item.charges = 0
        self.item.save(update_fields=["charges"])
        with self.assertRaises(NoChargesRemaining):
            self.bound()
        self.item.charges = 2
        self.item.save(update_fields=["charges"])
        self.template.requires_attunement = True
        self.template.save(update_fields=["requires_attunement"])
        with self.assertRaises(ItemNotAttuned):
            self.bound()
        self.item.attuned_to_character_sheet = self.sheet
        self.item.save(update_fields=["attuned_to_character_sheet"])
        self.bound()

    def test_unusable_bound_refusal(self):
        self.effect.delete()
        with self.assertRaises(ItemNotUsable):
            self.bound()

    def test_option_and_knowledge_need_no_target(self):
        self.assertEqual(self.option_read(self.option.pk), self.option)
        for option_id in (None, FormTraitOptionFactory().pk):
            with self.subTest(option_id=option_id), self.assertRaises(StyleChoiceRequired):
                self.option_read(option_id)
        with self.assertRaises(StyleNotKnown):
            self.option_read(self.exotic.pk)
        learn_style(self.sheet, self.exotic, taught_by_label="Fixture teacher")
        self.assertEqual(self.option_read(self.exotic.pk), self.exotic)

    def test_target_consent_need_no_option(self):
        # A room has no character sheet: current consent gate must refuse it.
        room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        with self.assertRaises(MakeoverNotPermitted):
            usage.validate_item_use_target(
                item_instance=self.item,
                user=self.user,
                target=room,
            )
        for target in (None, self.user):
            usage.validate_item_use_target(
                item_instance=self.item,
                user=self.user,
                target=target,
            )

    def test_blend_needs_neither_target_nor_option(self):
        with self.assertRaises(BlendNotSupported):
            usage.validate_item_use_blend(item_instance=self.item, blend=True)
        usage.validate_item_use_blend(item_instance=self.item, blend=False)
        self.trait.composite_option = self.option
        self.trait.save(update_fields=["composite_option"])
        usage.validate_item_use_blend(item_instance=self.item, blend=True)
        other = FormTraitFactory(is_cosmetic=True, composite_option=None)
        ItemTemplateAppearanceEffect.objects.create(
            item_template=self.template,
            trait=other,
            target_option=FormTraitOptionFactory(trait=other),
        )
        with self.assertRaises(BlendNotSupported):
            usage.validate_item_use_blend(item_instance=self.item, blend=True)

    def test_fixed_and_noncosmetic_choices_retain_existing_semantics(self):
        self.effect.target_option = self.option
        self.effect.save(update_fields=["target_option"])
        self.assertIsNone(self.option_read(None))
        self.assertIsNone(self.option_read(self.exotic.pk))
        self.effect.delete()
        self.template.on_use_pool = ConsequencePoolFactory()
        self.template.save(update_fields=["on_use_pool"])
        self.bound()
        self.assertIsNone(self.option_read(self.exotic.pk))
        usage.validate_item_use_blend(item_instance=self.item, blend=True)

    def test_reads_have_no_writes_locks_effects_or_events(self):
        before = OwnershipEvent.objects.count()
        with patch("flows.emit.emit_event") as emit, CaptureQueriesContext(connection) as queries:
            for target in (None, self.user):
                self.bound()
                self.option_read(self.option.pk)
                usage.validate_item_use_target(
                    item_instance=self.item,
                    user=self.user,
                    target=target,
                )
                usage.validate_item_use_blend(item_instance=self.item, blend=False)
        emit.assert_not_called()
        for query in queries.captured_queries:
            sql = query["sql"].strip().upper()
            self.assertFalse(sql.startswith(("INSERT", "UPDATE", "DELETE")), sql)
            self.assertNotIn("FOR UPDATE", sql)
        self.assertEqual(OwnershipEvent.objects.count(), before)
        self.assertEqual(self.item.charges, 2)
        self.assertEqual(self.form.values.get(trait=self.trait).option, self.old)

    def test_complete_gate_uses_the_same_validators_in_original_order(self):
        calls = []
        with (
            patch.object(
                usage, "validate_item_use_bound", side_effect=lambda **_kw: calls.append("bound")
            ),
            patch.object(
                usage, "validate_item_use_target", side_effect=lambda **_kw: calls.append("target")
            ),
            patch.object(
                usage,
                "validate_item_use_option",
                side_effect=lambda **_kw: calls.append("option") or self.option,
            ),
            patch.object(
                usage, "validate_item_use_blend", side_effect=lambda **_kw: calls.append("blend")
            ),
        ):
            chosen = usage._run_pre_charge_gates(
                locked=self.item,
                user=self.user,
                target=None,
                option_id=self.option.pk,
                blend=True,
            )
        self.assertEqual(calls, ["bound", "target", "option", "blend"])
        self.assertEqual(chosen, self.option)

    def test_complete_refusals_do_not_consume_or_apply(self):
        before = OwnershipEvent.objects.count()
        for kwargs, error in (
            ({}, StyleChoiceRequired),
            ({"option_id": self.exotic.pk}, StyleNotKnown),
            ({"option_id": self.option.pk, "blend": True}, BlendNotSupported),
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(error):
                usage.use_item(item_instance=self.item, user=self.user, **kwargs)
        self.assertEqual(self.item.charges, 2)
        self.assertEqual(OwnershipEvent.objects.count(), before)
        self.assertEqual(self.form.values.get(trait=self.trait).option, self.old)

    def test_successful_read_does_not_authorize_stale_charge_or_attunement(self):
        self.bound()
        self.option_read(self.option.pk)
        self.item.charges = 0
        self.item.save(update_fields=["charges"])
        with self.assertRaises(NoChargesRemaining):
            usage.use_item(item_instance=self.item, user=self.user, option_id=self.option.pk)
        self.item.charges = 2
        self.item.save(update_fields=["charges"])
        self.template.requires_attunement = True
        self.template.save(update_fields=["requires_attunement"])
        with self.assertRaises(ItemNotAttuned):
            usage.use_item(item_instance=self.item, user=self.user, option_id=self.option.pk)
        self.assertEqual(self.form.values.get(trait=self.trait).option, self.old)

    def test_complete_row_only_service_retains_current_effect_and_charge_behavior(self):
        result = usage.use_item(
            item_instance=self.item,
            user=self.user,
            option_id=self.option.pk,
        )
        self.assertEqual(result.charges_remaining, 1)
        self.assertEqual(self.form.values.get(trait=self.trait).option, self.option)

    def test_existing_inventory_rest_success_and_real_refusal(self):
        room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.user.location = room
        self.user.save()
        account = AccountFactory(is_staff=False)
        RosterTenureFactory(
            roster_entry=RosterEntryFactory(character_sheet=self.sheet),
            player_data=PlayerDataFactory(account=account),
            end_date=None,
        )
        obj = ObjectDBFactory(db_typeclass_path="typeclasses.objects.Object", location=self.user)
        self.item.game_object = obj
        self.item.save(update_fields=["game_object"])
        client = APIClient()
        client.force_authenticate(user=account)
        url = f"/api/items/inventory/{self.item.pk}/use/"
        response = client.post(url, {}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.item.charges, 2)
        response = client.post(url, {"option_id": self.option.pk}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["charges_remaining"], 1)
        self.assertEqual(self.form.values.get(trait=self.trait).option, self.option)

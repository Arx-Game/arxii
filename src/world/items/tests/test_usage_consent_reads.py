"""Read-safe cosmetic consent and repeated execution checks."""

from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from evennia.objects.models import ObjectDB
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.consent.constants import ConsentMode
from world.consent.factories import (
    SocialConsentBlacklistFactory,
    SocialConsentCategoryFactory,
    SocialConsentCategoryRuleFactory,
    SocialConsentPreferenceFactory,
    SocialConsentWhitelistFactory,
)
from world.consent.models import SocialConsentCategory
from world.forms.factories import (
    CharacterFormFactory,
    CharacterFormValueFactory,
    FormTraitFactory,
    FormTraitOptionFactory,
)
from world.items.exceptions import MakeoverNotPermitted
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.models import ItemTemplateAppearanceEffect, OwnershipEvent
from world.items.services import usage
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.roster.models import RosterTenure


class UsageConsentReadTests(TestCase):
    def setUp(self) -> None:
        self.account = AccountFactory(is_staff=False)
        self.actor_sheet = CharacterSheetFactory()
        self.actor = self.actor_sheet.character
        self.actor_tenure = RosterTenureFactory(
            roster_entry=RosterEntryFactory(character_sheet=self.actor_sheet),
            player_data=PlayerDataFactory(account=self.account),
            end_date=None,
        )
        self.target_sheet = CharacterSheetFactory()
        self.target = self.target_sheet.character
        self.owner = RosterTenureFactory(
            roster_entry=RosterEntryFactory(character_sheet=self.target_sheet),
            end_date=None,
        )
        SocialConsentCategory.objects.filter(key="makeover").delete()
        self.trait = FormTraitFactory(is_cosmetic=True, composite_option=None)
        self.old = FormTraitOptionFactory(trait=self.trait)
        self.option = FormTraitOptionFactory(trait=self.trait, requires_teaching=False)
        self.template = ItemTemplateFactory(
            is_consumable=True,
            max_charges=2,
            on_use_pool=None,
            requires_attunement=False,
        )
        ItemTemplateAppearanceEffect.objects.create(
            item_template=self.template,
            trait=self.trait,
            target_option=None,
        )
        self.item = ItemInstanceFactory(
            template=self.template,
            holder_character_sheet=self.actor_sheet,
            game_object=None,
            charges=2,
            quality_tier=None,
        )
        self.form = CharacterFormFactory(character=self.target_sheet)
        CharacterFormValueFactory(form=self.form, trait=self.trait, option=self.old)

    def category(self, *, parent: SocialConsentCategory | None = None) -> SocialConsentCategory:
        return SocialConsentCategoryFactory(
            key="makeover",
            default_mode=ConsentMode.ALLOWLIST,
            parent=parent,
        )

    def read(self, target: ObjectDB | None, *, blocked: bool = False) -> None:
        before = OwnershipEvent.objects.count()
        with (
            patch.object(usage, "_apply_on_use_pool") as pool,
            patch("flows.emit.emit_event") as emit,
            CaptureQueriesContext(connection) as queries,
        ):
            if blocked:
                with self.assertRaises(MakeoverNotPermitted):
                    usage.validate_item_use_target(
                        item_instance=self.item,
                        user=self.actor,
                        target=target,
                    )
            else:
                usage.validate_item_use_target(
                    item_instance=self.item,
                    user=self.actor,
                    target=target,
                )
        pool.assert_not_called()
        emit.assert_not_called()
        for query in queries.captured_queries:
            sql = query["sql"].strip().upper()
            self.assertFalse(sql.startswith(("INSERT", "UPDATE", "DELETE")), sql)
            self.assertNotIn("FOR UPDATE", sql)
        self.assertEqual(OwnershipEvent.objects.count(), before)
        self.assertEqual(self.item.charges, 2)
        self.assertEqual(self.form.values.get(trait=self.trait).option, self.old)

    def test_missing_category_denies_without_seeding_or_unrelated_grants(self) -> None:
        SocialConsentPreferenceFactory(tenure=self.owner, allow_social_actions=True)
        SocialConsentWhitelistFactory(
            owner_tenure=self.owner,
            allowed_tenure=self.actor_tenure,
        )
        self.read(self.target, blocked=True)
        self.assertFalse(SocialConsentCategory.objects.filter(key="makeover").exists())

    def test_null_self_npc_and_invalid_target_are_read_safe(self) -> None:
        npc = CharacterSheetFactory().character
        room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        for target in (None, self.actor, npc):
            with self.subTest(target=target):
                self.read(target)
        self.read(room, blocked=True)
        self.assertFalse(SocialConsentCategory.objects.filter(key="makeover").exists())

    def test_existing_allowlist_without_preference_and_master_switch(self) -> None:
        category = self.category()
        self.read(self.target, blocked=True)
        SocialConsentWhitelistFactory(
            owner_tenure=self.owner,
            allowed_tenure=self.actor_tenure,
            category=category,
        )
        self.read(self.target)
        SocialConsentPreferenceFactory(tenure=self.owner, allow_social_actions=False)
        self.read(self.target, blocked=True)

    def test_actor_without_active_tenure_preserves_existing_category_decisions(self) -> None:
        self.actor_tenure.end_date = timezone.now()
        self.actor_tenure.save(update_fields=["end_date"])
        self.assertFalse(
            RosterTenure.objects.filter(
                roster_entry__character_sheet=self.actor_sheet,
                end_date__isnull=True,
            ).exists()
        )
        self.assertTrue(
            RosterTenure.objects.filter(
                roster_entry__character_sheet=self.target_sheet,
                end_date__isnull=True,
            ).exists()
        )
        category = self.category()
        self.read(self.target, blocked=True)
        SocialConsentWhitelistFactory(
            owner_tenure=self.owner,
            allowed_tenure=self.actor_tenure,
            category=category,
        )
        self.read(self.target, blocked=True)
        category.default_mode = ConsentMode.EVERYONE
        category.save(update_fields=["default_mode"])
        self.read(self.target)
        category.default_mode = ConsentMode.ALL_BUT_BLACKLIST
        category.save(update_fields=["default_mode"])
        self.read(self.target)
        SocialConsentPreferenceFactory(tenure=self.owner, allow_social_actions=False)
        self.read(self.target, blocked=True)

    def test_existing_pc_category_reads_emit_no_dml_or_for_update_on_each_backend(self) -> None:
        # This same test runs on SQLite locally and PostgreSQL in CI.
        category = self.category()
        self.read(self.target, blocked=True)
        SocialConsentWhitelistFactory(
            owner_tenure=self.owner,
            allowed_tenure=self.actor_tenure,
            category=category,
        )
        self.read(self.target)

    def test_hierarchy_parent_grant_and_nearest_leaf_override(self) -> None:
        parent = SocialConsentCategoryFactory(default_mode=ConsentMode.ALLOWLIST)
        category = self.category(parent=parent)
        self.read(self.target, blocked=True)
        grant = SocialConsentWhitelistFactory(
            owner_tenure=self.owner,
            allowed_tenure=self.actor_tenure,
            category=parent,
        )
        self.read(self.target)
        grant.delete()
        pref = SocialConsentPreferenceFactory(tenure=self.owner)
        SocialConsentCategoryRuleFactory(
            preference=pref,
            category=parent,
            mode=ConsentMode.EVERYONE,
        )
        self.read(self.target)
        SocialConsentCategoryRuleFactory(
            preference=pref,
            category=category,
            mode=ConsentMode.ALLOWLIST,
        )
        self.read(self.target, blocked=True)

    def test_parent_blacklist_and_root_default_are_preserved(self) -> None:
        parent = SocialConsentCategoryFactory(default_mode=ConsentMode.ALL_BUT_BLACKLIST)
        self.category(parent=parent)
        self.read(self.target)
        SocialConsentBlacklistFactory(
            owner_tenure=self.owner,
            blocked_tenure=self.actor_tenure,
            category=parent,
        )
        self.read(self.target, blocked=True)

    def test_revoked_consent_is_rechecked_before_effects_and_charges(self) -> None:
        category = self.category()
        grant = SocialConsentWhitelistFactory(
            owner_tenure=self.owner,
            allowed_tenure=self.actor_tenure,
            category=category,
        )
        self.read(self.target)
        grant.delete()
        before = OwnershipEvent.objects.count()
        with self.assertRaises(MakeoverNotPermitted):
            usage.use_item(
                item_instance=self.item,
                user=self.actor,
                target=self.target,
                option_id=self.option.pk,
            )
        self.assertEqual(self.item.charges, 2)
        self.assertEqual(OwnershipEvent.objects.count(), before)
        self.assertEqual(self.form.values.get(trait=self.trait).option, self.old)
        self.assertTrue(SocialConsentCategory.objects.filter(pk=category.pk).exists())

    def test_missing_category_execution_denies_without_effects_or_seeding(self) -> None:
        before = OwnershipEvent.objects.count()
        with self.assertRaises(MakeoverNotPermitted):
            usage.use_item(
                item_instance=self.item,
                user=self.actor,
                target=self.target,
                option_id=self.option.pk,
            )
        self.assertFalse(SocialConsentCategory.objects.filter(key="makeover").exists())
        self.assertEqual(self.item.charges, 2)
        self.assertEqual(OwnershipEvent.objects.count(), before)
        self.assertEqual(self.form.values.get(trait=self.trait).option, self.old)

    def test_allowed_row_only_execution_applies_and_spends_one_charge(self) -> None:
        category = self.category()
        SocialConsentWhitelistFactory(
            owner_tenure=self.owner,
            allowed_tenure=self.actor_tenure,
            category=category,
        )
        result = usage.use_item(
            item_instance=self.item,
            user=self.actor,
            target=self.target,
            option_id=self.option.pk,
        )
        self.assertEqual(result.charges_remaining, 1)
        self.assertEqual(self.item.charges, 1)
        self.assertEqual(self.form.values.get(trait=self.trait).option, self.option)

    def test_existing_real_inventory_rest_contract_remains_self_use(self) -> None:
        room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.actor.location = room
        self.actor.save()
        obj = ObjectDBFactory(db_typeclass_path="typeclasses.objects.Object", location=self.actor)
        self.item.game_object = obj
        self.item.save(update_fields=["game_object"])
        actor_form = CharacterFormFactory(character=self.actor_sheet)
        CharacterFormValueFactory(form=actor_form, trait=self.trait, option=self.old)
        client = APIClient()
        client.force_authenticate(user=self.account)
        url = f"/api/items/inventory/{self.item.pk}/use/"
        response = client.post(url, {}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.item.charges, 2)
        response = client.post(url, {"option_id": self.option.pk}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["charges_remaining"], 1)
        self.assertEqual(actor_form.values.get(trait=self.trait).option, self.option)
        self.assertEqual(self.form.values.get(trait=self.trait).option, self.old)
        self.assertFalse(SocialConsentCategory.objects.filter(key="makeover").exists())

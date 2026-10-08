"""UseItemAction records a makeover ask instead of restyling on Ask me (#4187)."""

from django.test import TestCase
from rest_framework.test import APIClient

from actions.constants import TargetKind
from actions.definitions.items import UseItemAction
from evennia_extensions.factories import AccountFactory, ObjectDBFactory
from world.consent.constants import ConsentMode
from world.consent.factories import (
    SocialConsentCategoryFactory,
    SocialConsentCategoryRuleFactory,
    SocialConsentPreferenceFactory,
)
from world.consent.models import SocialConsentCategory
from world.consent.services import add_social_consent_blacklist, add_social_consent_whitelist
from world.forms.factories import (
    CharacterFormFactory,
    CharacterFormValueFactory,
    FormTraitFactory,
    FormTraitOptionFactory,
)
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.models import ItemTemplateAppearanceEffect, MakeoverConsentRequest
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.action_constants import ActionRequestStatus


class MakeoverAskActionTests(TestCase):
    def setUp(self):
        self.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        entry = RosterEntryFactory()
        self.sheet = entry.character_sheet
        self.actor = self.sheet.character
        self.actor.location = self.room
        self.account = AccountFactory(is_staff=False)
        self.actor_tenure = RosterTenureFactory(
            roster_entry=entry, player_data=PlayerDataFactory(account=self.account), end_date=None
        )
        other = RosterEntryFactory()
        self.other_sheet = other.character_sheet
        self.other = self.other_sheet.character
        self.other.location = self.room
        self.other_tenure = RosterTenureFactory(roster_entry=other, end_date=None)
        SocialConsentCategory.objects.filter(key="makeover").delete()
        self.category = SocialConsentCategoryFactory(
            key="makeover", default_mode=ConsentMode.ASK, asks_before_acting=True
        )
        self.trait = FormTraitFactory(is_cosmetic=True, composite_option=None)
        self.old = FormTraitOptionFactory(trait=self.trait, requires_teaching=False)
        self.option = FormTraitOptionFactory(trait=self.trait, requires_teaching=False)
        self.template = ItemTemplateFactory(
            on_use_pool=None,
            is_consumable=True,
            max_charges=8,
            requires_attunement=False,
            on_use_target_kind=TargetKind.CHARACTER,
        )
        ItemTemplateAppearanceEffect.objects.create(
            item_template=self.template, trait=self.trait, target_option=None
        )
        self.item = ItemInstanceFactory(
            template=self.template,
            charges=8,
            quality_tier=None,
            holder_character_sheet=self.sheet,
            contained_in=None,
            game_object=ObjectDBFactory(
                db_typeclass_path="typeclasses.objects.Object", location=self.actor
            ),
        )
        self.form = CharacterFormFactory(character=self.other_sheet)
        CharacterFormValueFactory(form=self.form, trait=self.trait, option=self.old)
        self.action = UseItemAction()

    def values(self):
        return {
            "menu_target": {"kind": "items", "target_id": self.item.pk},
            "use_target": {"kind": "objects", "target_id": self.other.pk},
            "option_id": self.option.pk,
        }

    def use(self):
        return self.action.execute(self.actor, **self.values())

    def rule(self, mode):
        pref = SocialConsentPreferenceFactory(tenure=self.other_tenure)
        SocialConsentCategoryRuleFactory(preference=pref, category=self.category, mode=mode)

    def charges(self):
        self.item.refresh_from_db()
        return self.item.charges

    def test_ask_me_records_the_offer_and_spends_nothing(self):
        result = self.use()
        self.assertTrue(result.success, result.message)
        self.assertTrue(result.message.startswith("You offer"), result.message)
        self.assertEqual(self.charges(), 8)
        request = MakeoverConsentRequest.objects.get()
        self.assertEqual(request.status, ActionRequestStatus.PENDING)
        self.assertEqual(result.data["makeover_request_id"], request.pk)

    def test_ask_me_is_available_to_the_menu(self):
        checked = self.action.check_availability(
            self.actor, context={"kwargs": self.values()}, pending_inputs=frozenset()
        )
        self.assertTrue(checked.available, checked.reasons)

    def test_always_allow_restyles_at_once(self):
        self.rule(ConsentMode.EVERYONE)
        result = self.use()
        self.assertTrue(result.success, result.message)
        self.assertEqual(self.charges(), 7)
        self.assertFalse(MakeoverConsentRequest.objects.exists())

    def test_never_refuses(self):
        self.rule(ConsentMode.ALLOWLIST)
        result = self.use()
        self.assertFalse(result.success)
        self.assertEqual(result.message, "They are not letting you restyle them.")
        self.assertEqual(self.charges(), 8)

    def test_whitelisted_stylist_skips_the_ask(self):
        add_social_consent_whitelist(self.other_tenure, self.actor_tenure, self.category)
        result = self.use()
        self.assertTrue(result.success, result.message)
        self.assertEqual(self.charges(), 7)
        self.assertFalse(MakeoverConsentRequest.objects.exists())

    def test_blacklisted_stylist_is_refused_without_being_told_why(self):
        add_social_consent_blacklist(self.other_tenure, self.actor_tenure, self.category)
        result = self.use()
        self.assertFalse(result.success)
        self.assertEqual(result.message, "They are not letting you restyle them.")

    def test_second_ask_is_refused(self):
        self.use()
        result = self.use()
        self.assertFalse(result.success)
        self.assertEqual(result.message, "You've already asked.")
        self.assertEqual(MakeoverConsentRequest.objects.count(), 1)

    def test_rest_dispatch_returns_the_offer_line(self):
        client = APIClient()
        client.force_authenticate(user=self.account)
        response = client.post(
            f"/api/actions/characters/{self.actor.pk}/dispatch/",
            {"ref": {"backend": "registry", "registry_key": "use_item"}, "kwargs": self.values()},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["success"], response.data)
        self.assertTrue(response.data["message"].startswith("You offer"), response.data)
        self.assertEqual(self.charges(), 8)

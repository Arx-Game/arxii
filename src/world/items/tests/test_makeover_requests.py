"""The makeover ask: offer, grant, decline, lapse (#4187)."""

from unittest.mock import patch

from django.test import TestCase

from actions.constants import TargetKind
from evennia_extensions.factories import AccountFactory, ObjectDBFactory
from world.consent.constants import ConsentMode, ConsentOutcome
from world.consent.factories import SocialConsentCategoryFactory
from world.consent.models import (
    SocialConsentBlacklist,
    SocialConsentCategory,
    SocialConsentWhitelist,
)
from world.forms.factories import (
    CharacterFormFactory,
    CharacterFormValueFactory,
    FormTraitFactory,
    FormTraitOptionFactory,
)
from world.items.exceptions import (
    MakeoverAlreadyAsked,
    MakeoverRequestLapsed,
    MakeoverRequestResolved,
    MakeoverRequiresConsent,
)
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.models import ItemTemplateAppearanceEffect, MakeoverConsentRequest
from world.items.services import usage
from world.items.services.makeover_requests import (
    describe_offer,
    offer_line,
    offer_makeover,
    pending_makeover_requests_for,
    respond_to_makeover_request,
)
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.action_constants import ActionRequestStatus
from world.scenes.services import create_mask, set_active_persona


class MakeoverAskFixture(TestCase):
    """Nyx (actor) holds a choose-at-use styling kit; Tehom (other) is in the room on Ask me."""

    def setUp(self):
        self.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.remote = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
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
        self.other_account = AccountFactory(is_staff=False)
        self.other_tenure = RosterTenureFactory(
            roster_entry=other,
            player_data=PlayerDataFactory(account=self.other_account),
            end_date=None,
        )
        SocialConsentCategory.objects.filter(key="makeover").delete()
        self.category = SocialConsentCategoryFactory(
            key="makeover", default_mode=ConsentMode.ASK, asks_before_acting=True
        )
        self.trait = FormTraitFactory(is_cosmetic=True, composite_option=None, display_name="hair")
        self.old = FormTraitOptionFactory(trait=self.trait, requires_teaching=False)
        self.option = FormTraitOptionFactory(
            trait=self.trait, requires_teaching=False, display_name="crimson"
        )
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

    def use(self, **overrides):
        values = {
            "item_instance": self.item,
            "user": self.actor,
            "target": self.other,
            "option_id": self.option.pk,
        }
        values.update(overrides)
        return usage.use_item(**values)

    def offer(self):
        return offer_makeover(
            user=self.actor,
            target=self.other,
            item_instance=self.item,
            option_id=self.option.pk,
            blend=False,
            descriptor=None,
        )

    def charges(self):
        self.item.refresh_from_db()
        return self.item.charges

    def current_option(self):
        return self.form.values.get(trait=self.trait).option


class UseItemAsksTests(MakeoverAskFixture):
    def test_use_item_asks_when_outcome_is_ask(self):
        with self.assertRaises(MakeoverRequiresConsent):
            self.use()
        self.assertEqual(self.charges(), 8)
        self.assertEqual(self.current_option(), self.old)

    def test_outcome_is_ask_by_default(self):
        self.assertEqual(usage.makeover_outcome(self.actor, self.other), ConsentOutcome.ASK)

    def test_forged_consent_is_ignored(self):
        with self.assertRaises(MakeoverRequiresConsent):
            self.use(consent="yes")
        self.assertEqual(self.charges(), 8)

    def test_accepted_request_for_another_item_is_not_proof(self):
        other_item = ItemInstanceFactory(template=self.template, charges=3, quality_tier=None)
        request = self.offer()
        request.status = ActionRequestStatus.ACCEPTED
        request.item_instance = other_item
        request.save(update_fields=["status", "item_instance"])
        with self.assertRaises(MakeoverRequiresConsent):
            self.use(consent=request)
        self.assertEqual(self.charges(), 8)


class OfferAndRespondTests(MakeoverAskFixture):
    def test_offer_records_a_pending_ask_and_tells_the_target(self):
        with patch.object(type(self.other), "msg") as msg:
            request = self.offer()
        self.assertEqual(request.status, ActionRequestStatus.PENDING)
        self.assertEqual(request.option, self.option)
        self.assertEqual(self.charges(), 8)
        self.assertIn("crimson", msg.call_args.args[0])
        self.assertIn("accept makeover", msg.call_args.args[0])

    def test_offer_and_describe_lines_name_the_style(self):
        request = self.offer()
        self.assertIn("hair", offer_line(request))
        self.assertIn("crimson", offer_line(request))
        self.assertNotIn("Waiting", offer_line(request))
        self.assertIn("hair", describe_offer(request))
        self.assertIn(self.item.display_name, describe_offer(request))

    def test_second_ask_to_the_same_person_is_refused(self):
        self.offer()
        with self.assertRaises(MakeoverAlreadyAsked):
            self.offer()
        self.assertEqual(MakeoverConsentRequest.objects.count(), 1)

    def test_grant_runs_the_restyle_and_spends_a_charge(self):
        request = self.offer()
        respond_to_makeover_request(request, accept=True)
        request.refresh_from_db()
        self.assertEqual(request.status, ActionRequestStatus.ACCEPTED)
        self.assertIsNotNone(request.responded_at)
        self.assertEqual(self.charges(), 7)
        self.assertEqual(self.current_option(), self.option)

    def test_decline_spends_nothing_and_tells_the_stylist(self):
        request = self.offer()
        with patch.object(type(self.actor), "msg") as msg:
            respond_to_makeover_request(request, accept=False)
        request.refresh_from_db()
        self.assertEqual(request.status, ActionRequestStatus.DENIED)
        self.assertEqual(self.charges(), 8)
        self.assertEqual(self.current_option(), self.old)
        self.assertIn("declined", msg.call_args.args[0])

    def test_decline_with_never_blacklists_the_stylist(self):
        request = self.offer()
        respond_to_makeover_request(request, accept=False, remember="never")
        self.assertTrue(
            SocialConsentBlacklist.objects.filter(
                owner_tenure=self.other_tenure,
                blocked_tenure=self.actor_tenure,
                category=self.category,
            ).exists()
        )
        self.assertEqual(usage.makeover_outcome(self.actor, self.other), ConsentOutcome.REFUSE)

    def test_grant_with_always_whitelists_the_stylist(self):
        request = self.offer()
        respond_to_makeover_request(request, accept=True, remember="always")
        self.assertTrue(
            SocialConsentWhitelist.objects.filter(
                owner_tenure=self.other_tenure,
                allowed_tenure=self.actor_tenure,
                category=self.category,
            ).exists()
        )
        # The next use needs no ask at all.
        self.use()
        self.assertEqual(self.charges(), 6)

    def test_answering_twice_is_refused(self):
        request = self.offer()
        respond_to_makeover_request(request, accept=False)
        with self.assertRaises(MakeoverRequestResolved):
            respond_to_makeover_request(request, accept=True)
        self.assertEqual(self.charges(), 8)


class LapseTests(MakeoverAskFixture):
    def test_grant_after_stylist_left_lapses(self):
        request = self.offer()
        self.actor.location = self.remote
        with self.assertRaises(MakeoverRequestLapsed):
            respond_to_makeover_request(request, accept=True)
        request.refresh_from_db()
        self.assertEqual(request.status, ActionRequestStatus.EXPIRED)
        self.assertEqual(self.charges(), 8)

    def test_grant_after_kit_is_spent_lapses(self):
        request = self.offer()
        self.item.charges = 0
        self.item.save(update_fields=["charges"])
        with self.assertRaises(MakeoverRequestLapsed):
            respond_to_makeover_request(request, accept=True)
        request.refresh_from_db()
        self.assertEqual(request.status, ActionRequestStatus.EXPIRED)
        self.assertEqual(self.current_option(), self.old)

    def test_pending_list_drops_a_lapsed_ask(self):
        request = self.offer()
        self.assertEqual(pending_makeover_requests_for(self.other_sheet), [request])
        self.actor.location = self.remote
        self.assertEqual(pending_makeover_requests_for(self.other_sheet), [])
        request.refresh_from_db()
        self.assertEqual(request.status, ActionRequestStatus.EXPIRED)

    def test_a_new_ask_replaces_a_lapsed_one(self):
        first = self.offer()
        self.actor.location = self.remote
        self.actor.location = self.room
        # The stylist left and came back: the old ask is still pending in the table.
        # Lapse is judged on the current rooms, so it is still live and blocks a second.
        with self.assertRaises(MakeoverAlreadyAsked):
            self.offer()
        first.status = ActionRequestStatus.EXPIRED
        first.save(update_fields=["status"])
        second = self.offer()
        self.assertNotEqual(first.pk, second.pk)


class MaskedStylistTests(MakeoverAskFixture):
    """A stylist asking under a mask: the ask shows the mask, and the remember shortcut
    must not write a tenure-keyed list row the Privacy page would show under the real name."""

    def setUp(self):
        super().setUp()
        self.mask = create_mask(self.sheet, name="Veiled stranger")
        set_active_persona(self.sheet, self.mask)

    def test_the_ask_names_the_mask(self):
        request = self.offer()
        self.assertEqual(request.stylist_persona, self.mask)
        self.assertIn("Veiled stranger", describe_offer(request))

    def test_always_on_a_masked_stylist_writes_no_whitelist_row(self):
        request = self.offer()
        respond_to_makeover_request(request, accept=True, remember="always")
        self.assertFalse(
            SocialConsentWhitelist.objects.filter(owner_tenure=self.other_tenure).exists()
        )
        # The grant itself still happened.
        self.assertEqual(self.charges(), 7)

    def test_never_on_a_masked_stylist_writes_no_blacklist_row(self):
        request = self.offer()
        respond_to_makeover_request(request, accept=False, remember="never")
        self.assertFalse(
            SocialConsentBlacklist.objects.filter(owner_tenure=self.other_tenure).exists()
        )
        request.refresh_from_db()
        self.assertEqual(request.status, ActionRequestStatus.DENIED)

"""Journeys for the actions tranche (#3657, tranche 2, step 2): hosting a gathering,
rising and falling in a covenant, keeping a vault, banking with the house, and
trading in the market square. Each types what a player types or sends what the
web client sends, and asserts what the player was told."""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone
from evennia.utils.ansi import strip_ansi

from integration_tests.harness import JourneyCase
from world.areas.factories import AreaFactory
from world.covenants.constants import BattleBinding, CovenantType
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantManagerRankFactory,
    CovenantRankFactory,
    CovenantRoleFactory,
)
from world.covenants.models import CharacterCovenantRole
from world.covenants.treasury import covenant_treasury
from world.currency.services import get_or_create_purse, get_or_create_treasury, transfer
from world.events.constants import InvitationResponse
from world.events.models import Event, EventInvitation
from world.events.services import create_event
from world.items.factories import (
    ItemInstanceFactory,
    ItemTemplateFactory,
    MaterialBucketFactory,
    MaterialCategoryFactory,
)
from world.items.market.models import FinishingPass, MarketSquare, MarketStall
from world.items.market.services import MATERIAL_SALE_RATE_PCT
from world.items.models import ItemInstance
from world.locations.factories import LocationOwnershipFactory
from world.room_features.constants import VAULT_MAX_ITEMS_PER_LEVEL, RoomFeatureServiceStrategy
from world.room_features.factories import RoomFeatureInstanceFactory, RoomFeatureKindFactory
from world.room_features.models import VaultDetails
from world.scenes.models import Scene
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory


def persona_of(character):
    return character.sheet_data.primary_persona


def sheet_of(character):
    return character.sheet_data


def profile_of(room):
    return room.room_profile


def give_coppers(character, amount: int) -> None:
    transfer(
        amount=amount, reason="journey seed", to_purse=get_or_create_purse(sheet_of(character))
    )


def purse_balance(character) -> int:
    purse = get_or_create_purse(sheet_of(character))
    purse.refresh_from_db()
    return purse.balance


class HostingAGathering(JourneyCase):
    """Ysmay hosts the Grand Gala; Hobb is invited, answers, and the evening runs its course."""

    def setUp(self) -> None:
        super().setUp()
        self.hall = self.make_room("The Feast Hall")
        self.ysmay = self.make_player("Ysmay", room=self.hall)
        self.hobb = self.make_player("Hobb", room=self.hall)
        self.watch(self.hobb)
        self.gala = create_event(
            name="The Grand Gala",
            location_id=profile_of(self.hall).pk,
            scheduled_real_time=timezone.now() + timedelta(days=7),
            host_persona=persona_of(self.ysmay),
        )

    def invitation_for(self, character) -> EventInvitation:
        return EventInvitation.objects.get(event=self.gala, target_persona=persona_of(character))

    def test_an_evening_from_invitation_to_the_last_guest_leaving(self) -> None:
        told = self.telnet(self.ysmay, f"event invite {self.gala.pk} persona=Hobb")
        self.assertIn("You invite Hobb to 'The Grand Gala'.", told)
        invitation = self.invitation_for(self.hobb)
        self.assertTold(
            self.hobb,
            f"Ysmay invites you to 'The Grand Gala'. event rsvp {invitation.pk} accept to "
            f"attend, event rsvp {invitation.pk} decline to refuse.",
        )

        told = self.telnet(self.hobb, f"event show {self.gala.pk}")
        self.assertIn(f"Event #{self.gala.pk}: The Grand Gala", told)
        self.assertIn(f"[#{invitation.pk}] Persona Hobb", told)
        self.assertIn("pending", told)

        told = self.telnet(self.hobb, f"event rsvp {invitation.pk} accept")
        self.assertIn("You accept the invitation to 'The Grand Gala'.", told)
        invitation.refresh_from_db()
        self.assertEqual(invitation.response, InvitationResponse.ACCEPTED)

        told = self.telnet(self.ysmay, f"event schedule {self.gala.pk}")
        self.assertIn("'The Grand Gala' is now scheduled.", told)
        told = self.telnet(self.ysmay, f"event start {self.gala.pk}")
        self.assertIn("'The Grand Gala' has started.", told)
        self.assertTrue(Scene.objects.filter(event=self.gala, is_active=True).exists())

        told = self.telnet(self.hobb, f"event rsvp {invitation.pk} decline")
        self.assertIn("Cannot RSVP to an invitation for an active or finished event.", told)

        told = self.telnet(self.ysmay, f"event complete {self.gala.pk}")
        self.assertIn("'The Grand Gala' is complete.", told)
        self.assertFalse(Scene.objects.filter(event=self.gala, is_active=True).exists())

    def test_the_host_creates_the_event_by_typing_it(self) -> None:
        when = timezone.localtime(timezone.now() + timedelta(days=12)).strftime("%Y-%m-%d %H:%M")
        told = self.telnet(
            self.ysmay, f"event create name=Midwinter Salon room=The Feast Hall when={when}"
        )
        salon = Event.objects.get(name="Midwinter Salon")
        self.assertIn(f"You create the event 'Midwinter Salon' (#{salon.pk}, draft).", told)
        self.assertTrue(
            salon.hosts.filter(persona=persona_of(self.ysmay), is_primary=True).exists()
        )

        told = self.telnet(self.ysmay, "event create name=Nowhere room=The Feast Hall when=soon")
        self.assertIn("Could not parse when='soon'.", told)

    def test_a_guest_cannot_run_the_host_s_event(self) -> None:
        told = self.telnet(self.hobb, f"event schedule {self.gala.pk}")
        self.assertIn("Only the event host or staff can do that.", told)
        told = self.telnet(self.hobb, f"event invite {self.gala.pk} persona=Ysmay")
        self.assertIn("Only the event host or staff can invite.", told)
        told = self.telnet(self.hobb, f"event cancel {self.gala.pk}")
        self.assertIn("Only the event host or staff can do that.", told)

        told = self.telnet(self.ysmay, f"event cancel {self.gala.pk}")
        self.assertIn("'The Grand Gala' has been cancelled.", told)
        told = self.telnet(self.ysmay, f"event cancel {self.gala.pk}")
        self.assertIn("Cannot cancel a completed or already-cancelled event.", told)

    def test_an_invitation_is_only_its_invitee_s_to_answer(self) -> None:
        self.telnet(self.ysmay, f"event invite {self.gala.pk} persona=Hobb")
        invitation = self.invitation_for(self.hobb)
        told = self.telnet(self.ysmay, f"event rsvp {invitation.pk} accept")
        self.assertIn("That invitation is not yours to respond to.", told)
        told = self.telnet(self.ysmay, f"event invite {self.gala.pk} persona=Hobb")
        self.assertIn("This target is already invited.", told)

    def test_an_unknown_event_is_named_back(self) -> None:
        told = self.telnet(self.ysmay, "event show 999999")
        self.assertIn("No event #999999 found.", told)
        told = self.telnet(self.ysmay, "event schedule 999999")
        self.assertIn("Which event? Provide an event id.", told)
        told = self.telnet(self.ysmay, "event schedule")
        self.assertIn("Usage: event schedule <id>", told)

    def test_the_web_rsvp_is_the_same_action(self) -> None:
        self.telnet(self.ysmay, f"event invite {self.gala.pk} persona=Hobb")
        invitation = self.invitation_for(self.hobb)
        result = self.web(
            self.hobb,
            "respond_invitation",
            invitation_id=invitation.pk,
            response=InvitationResponse.DECLINED,
        )
        self.assertTrue(result.detail.success, result.detail.message)
        self.assertIn("You decline the invitation to 'The Grand Gala'.", result.detail.message)
        invitation.refresh_from_db()
        self.assertEqual(invitation.response, InvitationResponse.DECLINED)


class RisingAndFallingInACovenant(JourneyCase):
    """Ysmay commands the Iron Banner; Hobb serves in it, rises, and is cast out."""

    def setUp(self) -> None:
        super().setUp()
        self.room = self.make_room("The Mustering Yard")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.hobb = self.make_player("Hobb", room=self.room)
        self.banner = CovenantFactory(
            name="The Iron Banner",
            covenant_type=CovenantType.BATTLE,
            battle_binding=BattleBinding.STANDING,
            is_dormant=False,
        )
        self.role = CovenantRoleFactory(name="Shieldbearer", covenant_type=CovenantType.BATTLE)
        self.commander = CovenantManagerRankFactory(covenant=self.banner, name="Commander", tier=1)
        self.veteran = CovenantRankFactory(covenant=self.banner, name="Veteran", tier=2)
        self.soldier = CovenantRankFactory(covenant=self.banner, name="Soldier", tier=3)
        self.ysmay_vow = CharacterCovenantRoleFactory(
            character_sheet=sheet_of(self.ysmay),
            covenant=self.banner,
            covenant_role=self.role,
            rank=self.commander,
        )
        self.hobb_vow = CharacterCovenantRoleFactory(
            character_sheet=sheet_of(self.hobb),
            covenant=self.banner,
            covenant_role=self.role,
            rank=self.soldier,
        )

    def rank_of(self, character) -> str | None:
        row = CharacterCovenantRole.objects.filter(
            character_sheet=sheet_of(character), covenant=self.banner, left_at__isnull=True
        ).first()
        return None if row is None else row.rank.name

    def test_a_soldier_rises_and_is_cast_out(self) -> None:
        told = self.telnet(self.hobb, "covenant")
        self.assertIn("The Iron Banner", told)
        self.assertIn("[Rank: Soldier]", told)

        told = self.telnet(self.hobb, "covenant rank Ysmay Soldier")
        self.assertIn("You lack the authority to assign ranks in that covenant.", told)
        self.assertEqual(self.rank_of(self.ysmay), "Commander")

        told = self.telnet(self.ysmay, "covenant rank Hobb Veteran")
        self.assertIn("Rank assigned.", told)
        self.assertEqual(self.rank_of(self.hobb), "Veteran")

        told = self.telnet(self.ysmay, "covenant rank Hobb Marshal")
        self.assertIn("No rank called 'Marshal' in that covenant.", told)

        told = self.telnet(self.hobb, "covenant kick Ysmay")
        self.assertIn("You lack the authority to remove members from that covenant.", told)

        told = self.telnet(self.ysmay, "covenant kick Hobb")
        self.assertIn("You remove them from the covenant.", told)
        self.assertIsNone(self.rank_of(self.hobb))
        told = self.telnet(self.hobb, "covenant")
        self.assertIn("You are not a member of any covenant.", told)

    def test_command_passes_before_the_commander_may_leave(self) -> None:
        told = self.telnet(self.ysmay, "covenant leave")
        self.assertIn("The covenant must keep at least one member who can manage ranks.", told)
        self.assertEqual(self.rank_of(self.ysmay), "Commander")

        told = self.telnet(self.ysmay, "covenant transfer Hobb")
        self.assertIn("The top rank passes to them.", told)
        self.assertEqual(self.rank_of(self.hobb), "Commander")
        self.assertEqual(self.rank_of(self.ysmay), "Soldier")

        told = self.telnet(self.ysmay, "covenant leave")
        self.assertIn("You leave the covenant.", told)
        self.assertIsNone(self.rank_of(self.ysmay))

    def test_the_banners_are_raised_and_lowered(self) -> None:
        told = self.telnet(self.ysmay, "covenant engage")
        self.assertIn("You engage your covenant role.", told)
        told = self.telnet(self.ysmay, "covenant disengage")
        self.assertIn("You disengage your covenant role.", told)
        told = self.telnet(self.ysmay, "covenant standdown")
        self.assertIn("The banners are lowered; the covenant stands down.", told)
        told = self.telnet(self.ysmay, "covenant engage")
        self.assertIn("No covenant members present to engage with.", told)

    def test_the_coffers_take_from_anyone_and_pay_out_by_rank(self) -> None:
        give_coppers(self.hobb, 500)
        told = self.telnet(self.hobb, "covenant deposit 200")
        self.assertIn("You add your coin to the covenant's coffers.", told)
        self.assertEqual(purse_balance(self.hobb), 300)
        treasury = covenant_treasury(self.banner)
        treasury.refresh_from_db()
        self.assertEqual(treasury.balance, 200)

        told = self.telnet(self.hobb, "covenant withdraw 100")
        self.assertIn(
            "Your rank does not carry the authority to spend from the covenant treasury.", told
        )
        told = self.telnet(self.ysmay, "covenant withdraw 100")
        self.assertIn("You draw coin from the covenant's coffers.", told)
        self.assertEqual(purse_balance(self.ysmay), 100)

        told = self.telnet(self.hobb, "covenant deposit 900")
        self.assertIn("The covenant treasury transfer could not be completed.", told)
        self.assertEqual(purse_balance(self.hobb), 300)
        told = self.telnet(self.hobb, "covenant deposit a-purse")
        self.assertIn("Usage: covenant deposit <amount> [in <covenant>]", told)

        result = self.web(
            self.hobb, "deposit_covenant_funds", covenant_id=self.banner.pk, amount=50
        )
        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(purse_balance(self.hobb), 250)

    def test_an_outsider_has_no_covenant_to_act_in(self) -> None:
        tam = self.make_player("Tam", room=self.room)
        told = self.telnet(tam, "covenant")
        self.assertIn("You are not a member of any covenant.", told)
        told = self.telnet(tam, "covenant deposit 10")
        self.assertIn("You are not a member of any covenant.", told)


class KeepingAVault(JourneyCase):
    """Ysmay founded the vault in her own strongroom; who may open it is hers to say."""

    def setUp(self) -> None:
        super().setUp()
        self.strongroom = self.make_room("The Strongroom")
        self.ysmay = self.make_player("Ysmay", room=self.strongroom)
        self.hobb = self.make_player("Hobb", room=self.strongroom)
        LocationOwnershipFactory(
            on_room=True,
            room_profile=profile_of(self.strongroom),
            holder_persona=persona_of(self.ysmay),
        )
        kind = RoomFeatureKindFactory(service_strategy=RoomFeatureServiceStrategy.VAULT)
        instance = RoomFeatureInstanceFactory(
            room_profile=profile_of(self.strongroom), feature_kind=kind, level=1
        )
        self.vault = VaultDetails.objects.create(
            feature_instance=instance,
            founder_persona=persona_of(self.ysmay),
            max_items=VAULT_MAX_ITEMS_PER_LEVEL,
        )
        self.guild = OrganizationFactory(name="The Lantern Guild")

    def test_the_founder_grants_and_revokes_access(self) -> None:
        told = self.telnet(self.ysmay, "vault status")
        self.assertIn("Vault (Level 1): 0/20 items. Founder: Ysmay.", told)

        told = self.telnet(self.ysmay, "vault access add Hobb")
        self.assertIn("Access granted to Hobb.", told)
        told = self.telnet(self.ysmay, "vault access add/org The Lantern Guild")
        self.assertIn("Access granted to The Lantern Guild.", told)
        told = self.telnet(self.ysmay, "vault access list")
        self.assertIn("Vault access list (2 entries):", told)

        told = self.telnet(self.ysmay, "vault access remove Hobb")
        self.assertIn("Access revoked from Hobb.", told)
        told = self.telnet(self.ysmay, "vault access remove Hobb")
        self.assertIn("That persona or organization was not on the access list.", told)
        told = self.telnet(self.ysmay, "vault access add Nobody")
        self.assertIn("No persona named 'Nobody' was found.", told)

    def test_only_the_room_s_holder_controls_the_vault(self) -> None:
        told = self.telnet(self.hobb, "vault access add Hobb")
        self.assertIn("You do not control this vault.", told)
        told = self.telnet(self.hobb, "vault access list")
        self.assertIn("You do not control this vault.", told)

    def test_a_room_without_a_vault_says_so(self) -> None:
        parlour = self.make_room("The Parlour")
        self.hobb.location = parlour
        told = self.telnet(self.hobb, "vault status")
        self.assertIn("There is no vault here.", told)
        told = self.telnet(self.hobb, "vault access add Ysmay")
        self.assertIn("There is no vault here.", told)


class BankingWithTheHouse(JourneyCase):
    """House Coffers keeps its vault and treasury behind a bank; rank decides who draws.

    These actions have no telnet verb; the web client dispatches them.
    """

    def setUp(self) -> None:
        super().setUp()
        self.bank = self.make_room("The Counting House")
        self.parlour = self.make_room("The Parlour")
        self.ysmay = self.make_player("Ysmay", room=self.bank)
        self.hobb = self.make_player("Hobb", room=self.bank)
        self.house = OrganizationFactory(name="House Coffers")
        OrganizationMembershipFactory(
            organization=self.house, persona=persona_of(self.ysmay), rank=1
        )
        OrganizationMembershipFactory(
            organization=self.house, persona=persona_of(self.hobb), rank=5
        )
        kind = RoomFeatureKindFactory(
            name="Bank Access", service_strategy=RoomFeatureServiceStrategy.BANK
        )
        RoomFeatureInstanceFactory(room_profile=profile_of(self.bank), feature_kind=kind, level=1)
        self.ring = ItemInstanceFactory(
            template=ItemTemplateFactory(name="Signet Ring"),
            holder_character_sheet=sheet_of(self.ysmay),
        )

    def test_an_item_goes_into_the_vault_and_comes_back_out_by_rank(self) -> None:
        self.ysmay.location = self.parlour
        result = self.web(
            self.ysmay,
            "vault_deposit",
            organization_id=self.house.pk,
            item_instance_id=self.ring.pk,
        )
        self.assertFalse(result.detail.success)
        self.assertIn("There is no bank access here.", result.detail.message)

        self.ysmay.location = self.bank
        result = self.web(
            self.ysmay,
            "vault_deposit",
            organization_id=self.house.pk,
            item_instance_id=self.ring.pk,
        )
        self.assertTrue(result.detail.success, result.detail.message)
        self.assertIn("is now in House Coffers's vault.", result.detail.message)
        self.ring.refresh_from_db()
        self.assertIsNone(self.ring.holder_character_sheet)

        result = self.web(
            self.hobb,
            "vault_withdraw",
            organization_id=self.house.pk,
            item_instance_id=self.ring.pk,
        )
        self.assertFalse(result.detail.success)
        self.assertIn(
            "You do not have the standing to withdraw from this vault.", result.detail.message
        )

        result = self.web(
            self.ysmay,
            "vault_withdraw",
            organization_id=self.house.pk,
            item_instance_id=self.ring.pk,
        )
        self.assertTrue(result.detail.success, result.detail.message)
        self.assertIn("from House Coffers's vault.", result.detail.message)
        self.ring.refresh_from_db()
        self.assertEqual(self.ring.holder_character_sheet_id, sheet_of(self.ysmay).pk)

    def test_the_treasury_pays_out_to_the_head_of_house_only(self) -> None:
        transfer(amount=500, reason="journey seed", to_treasury=get_or_create_treasury(self.house))
        result = self.web(self.hobb, "treasury_withdraw", organization_id=self.house.pk, amount=100)
        self.assertFalse(result.detail.success)
        self.assertIn(
            "You do not have the standing to spend from this treasury.", result.detail.message
        )

        result = self.web(
            self.ysmay, "treasury_withdraw", organization_id=self.house.pk, amount=100
        )
        self.assertTrue(result.detail.success, result.detail.message)
        self.assertIn("from House Coffers's treasury.", result.detail.message)
        self.assertEqual(purse_balance(self.ysmay), 100)

        result = self.web(self.ysmay, "treasury_withdraw", organization_id=self.house.pk, amount=-5)
        self.assertFalse(result.detail.success)
        self.assertIn("amount must be a positive whole number.", result.detail.message)
        result = self.web(
            self.ysmay, "treasury_withdraw", organization_id=self.house.pk, amount=5000
        )
        self.assertFalse(result.detail.success)
        self.assertIn("Insufficient funds", result.detail.message)


class TradingInTheSquare(JourneyCase):
    """Lantern Square: Ysmay buys nails from the ironmonger and sells a ring of her own make."""

    def setUp(self) -> None:
        super().setUp()
        self.square_room = self.make_room("Lantern Square")
        profile = profile_of(self.square_room)
        profile.area = AreaFactory(level=20)
        profile.save()
        self.ysmay = self.make_player("Ysmay", room=self.square_room)
        self.hobb = self.make_player("Hobb", room=self.square_room)
        self.square = MarketSquare.objects.create(name="Lantern Square", area=profile.area)
        self.ironmonger = MarketStall.objects.create(square=self.square, name="The Ironmonger")
        self.nails = self.ironmonger.stock_listings.create(
            template=ItemTemplateFactory(name="Iron Nails"), price=30
        )

    def test_browsing_and_buying_stock(self) -> None:
        give_coppers(self.ysmay, 100)
        # The browse is coloured for telnet; read it as the player sees it.
        told = strip_ansi(self.telnet(self.ysmay, "market"))
        self.assertIn("Lantern Square", told)
        self.assertIn(f"The Ironmonger (stall #{self.ironmonger.pk})", told)
        self.assertIn(f"[{self.nails.pk}] Iron Nails", told)
        self.assertIn("30c", told)

        told = self.telnet(self.ysmay, f"market/buy {self.nails.pk}")
        self.assertIn("You buy Iron Nails for 30 coppers.", told)
        self.assertEqual(purse_balance(self.ysmay), 70)
        self.assertTrue(
            ItemInstance.objects.filter(
                holder_character_sheet=sheet_of(self.ysmay), template__name="Iron Nails"
            ).exists()
        )

        told = self.telnet(self.hobb, f"market/buy {self.nails.pk}")
        self.assertIn("Insufficient funds", told)
        told = self.telnet(self.hobb, "market/buy 999999")
        self.assertIn("No such stock listing.", told)
        told = self.telnet(self.hobb, "market/buy")
        self.assertIn("Usage: market/buy <listing-id>", told)

    def test_a_ware_of_her_own_make_changes_hands(self) -> None:
        give_coppers(self.hobb, 100)
        bench = MarketStall.objects.create(
            square=self.square, name="Ysmay's Bench", owner_persona=persona_of(self.ysmay)
        )
        ring = ItemInstanceFactory(
            template=ItemTemplateFactory(name="Plain Ring"),
            holder_character_sheet=sheet_of(self.ysmay),
            crafter_character_sheet=sheet_of(self.ysmay),
        )

        told = self.telnet(self.ysmay, f"market/list {bench.pk}={ring.pk},40")
        self.assertIn("Plain Ring listed at 40 coppers.", told)
        listing = bench.ware_listings.get(item_instance=ring)

        told = self.telnet(self.ysmay, f"market/buyware {listing.pk}")
        self.assertIn("It is already yours.", told)

        told = self.telnet(self.hobb, f"market/buyware {listing.pk}")
        self.assertIn("You buy Plain Ring for 40 coppers.", told)
        finishing_pass = FinishingPass.objects.get(listing=listing)
        self.assertIn(f"finish it with 'market/finish {finishing_pass.pk}'", told)
        self.assertEqual(purse_balance(self.hobb), 60)
        self.assertEqual(purse_balance(self.ysmay), 40)

        told = self.telnet(
            self.hobb,
            f"market/finish {finishing_pass.pk}=The Moth Ring;A ring stamped with a moth.",
        )
        self.assertIn("The Moth Ring is finished.", told)
        ring.refresh_from_db()
        self.assertEqual(ring.custom_name, "The Moth Ring")
        self.assertEqual(ring.holder_character_sheet_id, sheet_of(self.hobb).pk)

        told = self.telnet(self.hobb, f"market/finish {finishing_pass.pk}=Again;Twice.")
        self.assertIn("That piece is already finished.", told)

    def test_there_is_no_market_in_the_parlour(self) -> None:
        parlour = self.make_room("The Parlour")
        self.hobb.location = parlour
        told = self.telnet(self.hobb, "market")
        self.assertIn("There is no market square here.", told)

    def test_bulk_materials_sell_from_anywhere(self) -> None:
        cordwood = MaterialCategoryFactory(name="Cordwood")
        MaterialBucketFactory(
            character_sheet=sheet_of(self.ysmay), material_category=cordwood, value=500
        )
        coins = 200 * MATERIAL_SALE_RATE_PCT // 100
        result = self.web(
            self.ysmay, "sell_materials", material_category_id=cordwood.pk, amount=200
        )
        self.assertTrue(result.detail.success, result.detail.message)
        self.assertIn(f"You sell 200 worth of Cordwood for {coins} coppers.", result.detail.message)
        self.assertEqual(purse_balance(self.ysmay), coins)

        result = self.web(
            self.ysmay, "sell_materials", material_category_id=cordwood.pk, amount=5000
        )
        self.assertFalse(result.detail.success)
        self.assertTrue(result.detail.message.strip(), "the refusal said nothing")
        result = self.web(self.ysmay, "sell_materials", material_category_id=cordwood.pk, amount=0)
        self.assertFalse(result.detail.success)
        self.assertIn("Sell how much?", result.detail.message)

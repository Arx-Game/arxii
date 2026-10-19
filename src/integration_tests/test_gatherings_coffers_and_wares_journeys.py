"""Journeys for the actions tranche (#3657, tranche 2, step 2): hosting a gathering,
rising and falling in a covenant, keeping a vault, banking with the house, and
trading in the market square. Each types what a player types or sends what the
web client sends, and asserts what the player was told."""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone
from evennia.utils.ansi import strip_ansi

from evennia_extensions.factories import ObjectDBFactory
from integration_tests.harness import JourneyCase
from world.areas.factories import AreaFactory
from world.consent.constants import ConsentMode
from world.consent.factories import SocialConsentCategoryFactory
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
from world.events.constants import EventStatus, InvitationResponse
from world.events.models import Event, EventGrandeurContribution, EventInvitation
from world.events.services import create_event
from world.gm.constants import GMTableStatus
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.gm.models import GMTableMembership
from world.items.factories import (
    ItemInstanceFactory,
    ItemTemplateFactory,
    MaterialBucketFactory,
    MaterialCategoryFactory,
)
from world.items.market.models import FinishingPass, MarketSquare, MarketStall
from world.items.market.services import MATERIAL_SALE_RATE_PCT
from world.items.models import ItemInstance
from world.items.org_vault_models import VaultHolding, VaultTransit
from world.items.services.org_vault import get_or_create_org_vault
from world.locations.factories import LocationOwnershipFactory
from world.room_features.constants import VAULT_MAX_ITEMS_PER_LEVEL, RoomFeatureServiceStrategy
from world.room_features.factories import RoomFeatureInstanceFactory, RoomFeatureKindFactory
from world.room_features.models import VaultDetails
from world.scenes.factories import SceneParticipationFactory
from world.scenes.models import Interaction, Scene
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory
from world.stories.constants import GroupStoryRequestStatus, StoryScope
from world.stories.models import GroupStoryProgress, GroupStoryRequest


def persona_of(character):
    return character.sheet_data.primary_persona


def sheet_of(character):
    return character.sheet_data


def profile_of(room):
    return room.room_profile


def held_item(character, name: str) -> ItemInstance:
    """An item in *character*'s hands as play makes one: a game object in their inventory
    and a row they hold (#4474; an item with no game object never reaches the deposit's
    object branch)."""
    return ItemInstanceFactory(
        template=ItemTemplateFactory(name=name),
        game_object=ObjectDBFactory(db_key=name, location=character),
        holder_character_sheet=sheet_of(character),
    )


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
        # A line spoken before the event begins once left the room remembering "no
        # scene", so nothing said after the start was recorded in the event's scene.
        self.telnet(self.hobb, "say Is it time yet?")
        told = self.telnet(self.ysmay, f"event start {self.gala.pk}")
        self.assertIn("'The Grand Gala' has started.", told)
        gala_scene = Scene.objects.get(event=self.gala, is_active=True)
        self.telnet(self.hobb, "say Welcome, all of you.")
        self.assertTrue(
            Interaction.objects.filter(scene=gala_scene, content="Welcome, all of you.").exists()
        )

        # Grandeur comes out of the host's own purse; an empty purse buys none.
        self.assertIn("Usage: event grandeur <id>", self.telnet(self.ysmay, "event grandeur"))
        self.assertIn(
            "You cannot afford that much grandeur investment.",
            self.telnet(self.ysmay, f"event grandeur {self.gala.pk} category=venue amount=4000"),
        )
        self.assertFalse(EventGrandeurContribution.objects.filter(event=self.gala).exists())
        give_coppers(self.ysmay, 10_000)
        self.assertIn(
            "You invest in the venue of 'The Grand Gala'.",
            self.telnet(self.ysmay, f"event grandeur {self.gala.pk} category=venue amount=4000"),
        )
        spent = EventGrandeurContribution.objects.get(event=self.gala)
        self.assertEqual((spent.category, spent.amount_spent), ("venue", 4000))
        self.assertEqual(purse_balance(self.ysmay), 6000)

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
        self.gala.refresh_from_db()
        self.assertEqual(self.gala.status, EventStatus.DRAFT)

        told = self.telnet(self.ysmay, f"event cancel {self.gala.pk}")
        self.assertIn("'The Grand Gala' has been cancelled.", told)
        told = self.telnet(self.ysmay, f"event cancel {self.gala.pk}")
        self.assertIn("Cannot cancel a completed or already-cancelled event.", told)

    def test_an_invitation_is_only_its_invitee_s_to_answer(self) -> None:
        self.telnet(self.ysmay, f"event invite {self.gala.pk} persona=Hobb")
        invitation = self.invitation_for(self.hobb)
        told = self.telnet(self.ysmay, f"event rsvp {invitation.pk} accept")
        self.assertIn("That invitation is not yours to respond to.", told)
        invitation.refresh_from_db()
        self.assertEqual(invitation.response, InvitationResponse.PENDING)
        told = self.telnet(self.ysmay, f"event invite {self.gala.pk} persona=Hobb")
        self.assertIn("This target is already invited.", told)

        # A guild's invitation is nobody's to answer, and an invitation that is not there
        # is named back.
        guild = OrganizationFactory(name="The Lantern Guild")
        told = self.telnet(self.ysmay, f"event invite {self.gala.pk} org={guild.pk}")
        self.assertIn("You invite The Lantern Guild to 'The Grand Gala'.", told)
        guild_invitation = EventInvitation.objects.get(event=self.gala, target_organization=guild)
        told = self.telnet(self.hobb, f"event rsvp {guild_invitation.pk} accept")
        self.assertIn("Only persona invitations can be RSVP'd.", told)
        told = self.telnet(self.hobb, "event rsvp 999999 accept")
        self.assertIn("Which invitation? Provide an invitation id.", told)

    def test_staff_and_the_scene_s_gm_may_run_it_too(self) -> None:
        marrow = self.make_player("Marrow", room=self.hall)
        staff = self.account_of(marrow)
        staff.is_staff = True
        staff.save(update_fields=["is_staff"])
        told = self.telnet(marrow, f"event schedule {self.gala.pk}")
        self.assertIn("'The Grand Gala' is now scheduled.", told)

        self.telnet(self.ysmay, f"event start {self.gala.pk}")
        gala_scene = Scene.objects.get(event=self.gala, is_active=True)
        told = self.telnet(self.hobb, f"event complete {self.gala.pk}")
        self.assertIn("Only the host, a scene GM, or staff can do that.", told)
        SceneParticipationFactory(scene=gala_scene, account=self.account_of(self.hobb), is_gm=True)
        told = self.telnet(self.hobb, f"event complete {self.gala.pk}")
        self.assertIn("'The Grand Gala' is complete.", told)
        self.gala.refresh_from_db()
        self.assertEqual(self.gala.status, EventStatus.COMPLETED)

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
        give_coppers(tam, 50)
        result = self.web(tam, "deposit_covenant_funds", covenant_id=self.banner.pk, amount=10)
        self.assertFalse(result.detail.success)
        self.assertIn(
            "Only an active covenant member may use the covenant treasury.", result.detail.message
        )
        self.assertEqual(purse_balance(tam), 50)

    def test_the_web_names_the_covenant_and_never_the_vow(self) -> None:
        # The web client sends only the covenant and the amount; a vow named on the wire
        # (as the telnet path passes it) is not trusted, since a forged POST could name
        # anyone's.
        treasury = covenant_treasury(self.banner)
        treasury.balance = 500
        treasury.save(update_fields=["balance"])
        result = self.web(
            self.ysmay, "withdraw_covenant_funds", covenant_id=self.banner.pk, amount=25
        )
        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(purse_balance(self.ysmay), 25)
        treasury.refresh_from_db()
        self.assertEqual(treasury.balance, 475)

        refusal = "Only an active covenant member may use the covenant treasury."
        for key in ("deposit_covenant_funds", "withdraw_covenant_funds"):
            result = self.web(self.ysmay, key, membership=self.ysmay_vow.pk, amount=10)
            self.assertFalse(result.detail.success, key)
            self.assertIn(refusal, result.detail.message)
        treasury.refresh_from_db()
        self.assertEqual(treasury.balance, 475)

    def test_the_covenant_asks_for_a_gm_and_one_answers(self) -> None:
        self.assertIn(
            "You lack the authority to request a GM for this covenant.",
            self.telnet(self.hobb, "covenant request-gm We need a GM"),
        )
        told = self.telnet(self.ysmay, "covenant request-gm We need a GM to run our story")
        request = GroupStoryRequest.objects.get(covenant=self.banner)
        self.assertIn(f"Your covenant's request for a GM has been posted (#{request.pk}).", told)
        self.assertEqual(request.status, GroupStoryRequestStatus.PENDING)
        self.assertEqual(request.message, "We need a GM to run our story")
        self.assertEqual(request.requested_by_account_id, self.ysmay.db_account.pk)
        self.assertIn(
            "You lack the authority to withdraw this covenant's GM request.",
            self.telnet(self.hobb, "covenant withdraw-gm-request"),
        )

        # Every GM sees the open ask in the queue; one with an active table answers it.
        ravenna = self.make_player("Ravenna", room=self.room)
        table = GMTableFactory(
            gm=GMProfileFactory(account=ravenna.db_account), status=GMTableStatus.ACTIVE
        )
        queue = self.api(ravenna.db_account).get("/api/stories/gm-queue/")
        self.assertEqual(queue.status_code, 200, queue.content)
        self.assertIn(request.pk, [row["request_id"] for row in queue.data["open_group_requests"]])
        # The same queue on the line: the dashboard counts the open ask and names the banner.
        told = strip_ansi(self.telnet(ravenna, "gm dashboard"))
        self.assertIn("GM Dashboard:", told)
        self.assertIn(f"[{table.pk}] {table.name}", told)
        self.assertIn("Open group requests: 1", told)
        self.assertIn(f"[{request.pk}] The Iron Banner", told)
        self.assertIn("Usage: gm dashboard", self.telnet(ravenna, "gm frobnicate"))
        self.assertIn("Usage: gm claim <request-id>", self.telnet(ravenna, "gm claim"))
        tam = self.make_player("Tam", room=self.room)
        self.assertIn(
            "You must have a GM profile to use this command.", self.telnet(tam, "gm dashboard")
        )
        # Staff see which tables sit idle; a player has no such verb.
        self.assertIn("is not available", self.telnet(tam, "gmidle"))
        marrow = self.make_player("Marrow", room=self.room)
        staff = self.account_of(marrow)
        staff.is_staff = True
        staff.save(update_fields=["is_staff"])
        # The verb's lock reads the account's permissions ahead of the character's.
        staff.permissions.add("Admin")
        self.assertIn(f"[{table.pk}] {table.name}", strip_ansi(self.telnet(marrow, "gmidle")))
        self.assertIn(
            "You must have a GM profile to claim a group story request.",
            self.telnet(tam, f"gm claim {request.pk}"),
        )
        self.assertIn("Usage: gm claim <request-id>", self.telnet(ravenna, "gm claim abc"))
        told = self.telnet(ravenna, f"gm claim {request.pk}")
        self.assertIn("You claim The Iron Banner's request;", told)
        request.refresh_from_db()
        self.assertEqual(request.status, GroupStoryRequestStatus.ACCEPTED)
        self.assertEqual(request.claimed_by_id, table.gm_id)
        story = request.created_story
        self.assertEqual((story.scope, story.primary_table_id), (StoryScope.GROUP, table.pk))
        self.assertTrue(GroupStoryProgress.objects.filter(story=story, gm_table=table).exists())
        seated = set(
            GMTableMembership.objects.filter(table=table, left_at__isnull=True).values_list(
                "persona_id", flat=True
            )
        )
        self.assertIn(persona_of(self.ysmay).pk, seated)
        self.assertIn(persona_of(self.hobb).pk, seated)

        # A later ask can be taken back by whoever posted it, and only while it is open.
        self.telnet(self.ysmay, "covenant request-gm Round two")
        self.assertIn(
            "You withdraw The Iron Banner's request for a GM.",
            self.telnet(self.ysmay, "covenant withdraw-gm-request"),
        )
        self.assertEqual(
            GroupStoryRequest.objects.filter(
                covenant=self.banner, status=GroupStoryRequestStatus.WITHDRAWN
            ).count(),
            1,
        )
        self.assertIn(
            "That covenant has no open request for a GM.",
            self.telnet(self.ysmay, "covenant withdraw-gm-request"),
        )

    def test_an_equal_is_not_hers_to_remove(self) -> None:
        self.hobb_vow.rank = self.commander
        self.hobb_vow.save(update_fields=["rank"])
        told = self.telnet(self.ysmay, "covenant kick Hobb")
        self.assertIn("You can only remove members ranked below you.", told)
        self.assertEqual(self.rank_of(self.hobb), "Commander")

    def test_the_lines_that_go_nowhere(self) -> None:
        self.assertIn(
            "Usage: covenant [list|engage|disengage|leave|kick|rank|transfer|standdown|",
            self.telnet(self.ysmay, "covenant frobnicate"),
        )
        self.assertIn(
            "You are not a member of a covenant named 'The Velvet Hand'.",
            self.telnet(self.ysmay, "covenant engage The Velvet Hand"),
        )
        self.assertIn(
            "Kick whom? (covenant kick <char> [in <covenant>])",
            self.telnet(self.ysmay, "covenant kick"),
        )
        self.assertIn(
            "Usage: covenant rank <char> <rank> [in <covenant>]",
            self.telnet(self.ysmay, "covenant rank"),
        )
        self.assertIn(
            "Transfer to whom? (covenant transfer <char> [in <covenant>])",
            self.telnet(self.ysmay, "covenant transfer"),
        )
        # Sworn to two banners, she must say which one she means.
        second = CovenantFactory(
            name="The Second Banner",
            covenant_type=CovenantType.BATTLE,
            battle_binding=BattleBinding.STANDING,
            is_dormant=False,
        )
        CharacterCovenantRoleFactory(
            character_sheet=sheet_of(self.ysmay),
            covenant=second,
            covenant_role=self.role,
            rank=CovenantRankFactory(covenant=second, name="Marcher", tier=3),
        )
        self.assertIn(
            "Which covenant? You are in: The Iron Banner, The Second Banner",
            self.telnet(self.ysmay, "covenant engage"),
        )
        self.assertIn(
            "You engage your covenant role.",
            self.telnet(self.ysmay, "covenant engage The Second Banner"),
        )
        self.assertTrue(
            CharacterCovenantRole.objects.filter(
                character_sheet=sheet_of(self.ysmay), covenant=second, engaged=True
            ).exists()
        )

    def test_a_dormant_banner_cannot_be_raised(self) -> None:
        self.banner.is_dormant = True
        self.banner.save(update_fields=["is_dormant"])
        told = self.telnet(self.ysmay, "covenant engage")
        self.assertIn("No covenant members present to engage with.", told)
        engaged = CharacterCovenantRole.objects.filter(pk=self.ysmay_vow.pk).values_list(
            "engaged", flat=True
        )
        self.assertEqual(list(engaged), [False])


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
        self.ring = held_item(self.ysmay, "Signet Ring")

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
        self.assertIsNone(self.ring.game_object)  # custody is the row; the ring is still there
        self.assertEqual(list(self.ysmay.carried_items), [])

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
        self.assertEqual(self.ring.game_object.location, self.ysmay)  # back in her hands
        self.assertEqual(list(self.ysmay.carried_items), [self.ring])

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
        for bad_amount in ("abc", None):
            result = self.web(
                self.ysmay, "treasury_withdraw", organization_id=self.house.pk, amount=bad_amount
            )
            self.assertFalse(result.detail.success, bad_amount)
            self.assertIn("amount must be a positive whole number.", result.detail.message)

        self.ysmay.location = self.parlour
        result = self.web(self.ysmay, "treasury_withdraw", organization_id=self.house.pk, amount=10)
        self.assertFalse(result.detail.success)
        self.assertIn("There is no bank access here.", result.detail.message)
        self.assertEqual(purse_balance(self.ysmay), 100)

    def test_only_what_she_holds_goes_into_the_vault(self) -> None:
        stranger_ring = ItemInstanceFactory(template=ItemTemplateFactory(name="Stranger's Ring"))
        result = self.web(
            self.ysmay,
            "vault_deposit",
            organization_id=self.house.pk,
            item_instance_id=stranger_ring.pk,
        )
        self.assertFalse(result.detail.success)
        self.assertIn("You can only deposit an item you hold.", result.detail.message)
        result = self.web(
            self.ysmay, "vault_deposit", organization_id=self.house.pk, item_instance_id=999999
        )
        self.assertFalse(result.detail.success)
        self.assertIn("No such item.", result.detail.message)
        result = self.web(
            self.ysmay, "vault_deposit", organization_id=999999, item_instance_id=self.ring.pk
        )
        self.assertFalse(result.detail.success)
        self.assertIn("No such organization.", result.detail.message)
        self.assertFalse(VaultHolding.objects.exists())

    def open_transit(self, carrier, name: str) -> ItemInstance:
        """A stone the house's collector carries home, owed to its vault."""
        stone = held_item(carrier, name)
        VaultTransit.objects.create(
            vault=self.vault, item_instance=stone, carrier_character_sheet=sheet_of(carrier)
        )
        return stone

    def open_transits(self):
        return VaultTransit.objects.filter(vault=self.vault, resolved_at__isnull=True)

    def deliver(self, carrier, **kwargs):
        return self.web(carrier, "deliver_collection", organization_id=self.house.pk, **kwargs)

    def test_the_collector_brings_the_take_home(self) -> None:  # noqa: PLR0915
        self.vault = get_or_create_org_vault(self.house)
        self.ysmay.location = self.parlour
        result = self.deliver(self.ysmay)
        self.assertFalse(result.detail.success)
        self.assertIn("There is no bank access here.", result.detail.message)

        self.ysmay.location = self.bank
        result = self.deliver(self.ysmay)
        self.assertFalse(result.detail.success)
        self.assertIn("You carry nothing owed to House Coffers.", result.detail.message)

        first = self.open_transit(self.ysmay, "Garnet")
        second = self.open_transit(self.ysmay, "Jasper")
        result = self.deliver(self.ysmay)
        self.assertTrue(result.detail.success, result.detail.message)
        self.assertIn("You deliver 2 item(s) to House Coffers's vault.", result.detail.message)
        self.assertEqual(VaultHolding.objects.filter(vault=self.vault).count(), 2)
        self.assertFalse(self.open_transits().exists())
        first.refresh_from_db()
        self.assertIsNone(first.holder_character_sheet)
        self.assertIsNone(first.game_object)  # the stone survives as a row in the vault

        # Keeping a stone back needs the house's consent as well as her own nerve; with no
        # embezzlement consent category seeded, nobody can give it.
        kept = self.open_transit(self.ysmay, "Opal")
        honest = self.open_transit(self.ysmay, "Agate")
        result = self.deliver(self.ysmay, keep_item_ids=[kept.pk])
        self.assertFalse(result.detail.success)
        self.assertIn(
            "Skimming this house's collection is not on the table.", result.detail.message
        )
        self.assertEqual(self.open_transits().count(), 2)

        # The carrier never answers for herself: the highest-ranked piloted member
        # besides her decides, and that is Hobb. His list is empty, so he refuses until he
        # puts her on it.
        SocialConsentCategoryFactory(key="embezzlement", default_mode=ConsentMode.ALLOWLIST)
        result = self.deliver(self.ysmay, keep_item_ids=[kept.pk])
        self.assertFalse(result.detail.success)
        self.assertIn(
            "Skimming this house's collection is not on the table.", result.detail.message
        )
        told = self.telnet(self.hobb, "consent whitelist add Ysmay to embezzlement")
        self.assertIn("Ysmay", told)
        result = self.deliver(self.ysmay, keep_item_ids=[second.pk])
        self.assertFalse(result.detail.success)
        self.assertIn("cannot keep what you are not carrying for this house", result.detail.message)
        self.assertEqual(self.open_transits().count(), 2)
        result = self.deliver(self.ysmay, keep_item_ids=[kept.pk])
        self.assertTrue(result.detail.success, result.detail.message)
        self.assertIn("You deliver 1 item(s) to House Coffers's vault.", result.detail.message)
        kept.refresh_from_db()
        self.assertEqual(kept.holder_character_sheet_id, sheet_of(self.ysmay).pk)
        honest.refresh_from_db()
        self.assertIsNone(honest.holder_character_sheet)
        self.assertEqual(VaultHolding.objects.filter(vault=self.vault).count(), 3)

        # A stone sold on the way home is not yanked out of the buyer's hands.
        sold = self.open_transit(self.ysmay, "Beryl")
        sold.holder_character_sheet = sheet_of(self.hobb)
        sold.save(update_fields=["holder_character_sheet"])
        result = self.deliver(self.ysmay)
        self.assertFalse(result.detail.success)
        self.assertIn("you no longer carry all of the take", result.detail.message)
        self.assertEqual(self.open_transits().count(), 1)
        sold.holder_character_sheet = sheet_of(self.ysmay)
        sold.save(update_fields=["holder_character_sheet"])

        # A plain deposit before the delivery leaves the transit to close cleanly.
        result = self.web(
            self.ysmay, "vault_deposit", organization_id=self.house.pk, item_instance_id=sold.pk
        )
        self.assertTrue(result.detail.success, result.detail.message)
        result = self.deliver(self.ysmay)
        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(VaultHolding.objects.filter(item_instance=sold).count(), 1)
        self.assertFalse(self.open_transits().exists())


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
        self.assertIn("don't have enough", result.detail.message)
        for bad_amount in (0, "lots", None):
            result = self.web(
                self.ysmay, "sell_materials", material_category_id=cordwood.pk, amount=bad_amount
            )
            self.assertFalse(result.detail.success, bad_amount)
            self.assertIn("Sell how much?", result.detail.message)
        result = self.web(self.ysmay, "sell_materials", amount=100)
        self.assertFalse(result.detail.success)
        self.assertIn("Sell what?", result.detail.message)
        self.assertEqual(purse_balance(self.ysmay), coins)

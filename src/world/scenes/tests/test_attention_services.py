"""Per-character attention counting (#3774).

Every test here is a counting rule the badge has to get right. The service is
the highest seam for these: the serializer and the client both just carry its
answer.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from evennia import create_object

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)
from world.scenes.attention_services import account_attention
from world.scenes.constants import DIRECTED_UNREAD_DAYS, InteractionMode, InteractionVisibility
from world.scenes.factories import (
    InteractionFactory,
    SceneFactory,
    SceneParticipationFactory,
)
from world.scenes.models import Interaction, InteractionReadReceipt, InteractionTargetPersona
from world.scenes.place_models import InteractionReceiver


class AccountAttentionTests(TestCase):
    """Two characters on one account, plus two unrelated speakers."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        cls.player_data = PlayerDataFactory(account=cls.account)

        cls.sheet_one = CharacterSheetFactory()
        cls.persona_one = cls.sheet_one.primary_persona
        cls.entry_one = RosterEntryFactory(character_sheet=cls.sheet_one)
        RosterTenureFactory(player_data=cls.player_data, roster_entry=cls.entry_one)

        cls.sheet_two = CharacterSheetFactory()
        cls.persona_two = cls.sheet_two.primary_persona
        cls.entry_two = RosterEntryFactory(character_sheet=cls.sheet_two)
        RosterTenureFactory(player_data=cls.player_data, roster_entry=cls.entry_two)

        cls.entries = [cls.entry_one, cls.entry_two]
        cls.sheet_one_id = cls.sheet_one.pk
        cls.sheet_two_id = cls.sheet_two.pk

        # Two unrelated speakers, neither belonging to this account.
        cls.outsider = CharacterSheetFactory().primary_persona
        cls.other_outsider = CharacterSheetFactory().primary_persona

        # One open scene both of the account's characters are already "in":
        # each has posed once, which is how the service attributes an open
        # scene back to a specific character (SceneParticipation is
        # account-scoped, not character-scoped). Neither opening pose counts
        # toward ambient itself, since a character's own poses are always
        # excluded. The scene has a real room (rather than location=None) so
        # the presence-derived attribution query (Finding 1, #3774 final
        # review) always runs, even though neither character's ObjectDB
        # actually sits in that room - pose attribution alone already covers
        # both, so the presence path adds a query but no sheets here.
        cls.room = create_object("typeclasses.rooms.Room", key="Attention Test Room", nohome=True)
        cls.scene = SceneFactory(location=cls.room)
        SceneParticipationFactory(scene=cls.scene, account=cls.account)
        InteractionFactory(scene=cls.scene, persona=cls.persona_one, mode=InteractionMode.POSE)
        InteractionFactory(scene=cls.scene, persona=cls.persona_two, mode=InteractionMode.POSE)

    def test_whisper_to_one_character_counts_direct_for_that_character_only(self) -> None:
        whisper = InteractionFactory(
            scene=self.scene,
            persona=self.outsider,
            mode=InteractionMode.WHISPER,
        )
        InteractionReceiver.objects.create(
            interaction=whisper,
            timestamp=whisper.timestamp,
            persona=self.persona_one,
        )

        result = account_attention(account=self.account, entries=self.entries)

        self.assertEqual(result.by_character[self.sheet_one_id].direct, 1)
        self.assertEqual(result.by_character[self.sheet_two_id].direct, 0)

    def test_targeted_pose_counts_direct(self) -> None:
        pose = InteractionFactory(
            scene=self.scene,
            persona=self.outsider,
            mode=InteractionMode.POSE,
        )
        InteractionTargetPersona.objects.create(
            interaction=pose,
            timestamp=pose.timestamp,
            persona=self.persona_two,
        )

        result = account_attention(account=self.account, entries=self.entries)

        self.assertEqual(result.by_character[self.sheet_two_id].direct, 1)
        self.assertEqual(result.by_character[self.sheet_one_id].direct, 0)

    def test_own_authored_pose_never_counts(self) -> None:
        # persona_one whispers to persona_two - both belong to this account,
        # so this must never register as unread attention for either.
        whisper = InteractionFactory(
            scene=self.scene,
            persona=self.persona_one,
            mode=InteractionMode.WHISPER,
        )
        InteractionReceiver.objects.create(
            interaction=whisper,
            timestamp=whisper.timestamp,
            persona=self.persona_two,
        )

        result = account_attention(account=self.account, entries=self.entries)

        self.assertEqual(result.by_character[self.sheet_two_id].direct, 0)
        self.assertEqual(result.by_character[self.sheet_one_id].direct, 0)

    def test_already_receipted_pose_does_not_count(self) -> None:
        whisper = InteractionFactory(
            scene=self.scene,
            persona=self.outsider,
            mode=InteractionMode.WHISPER,
        )
        InteractionReceiver.objects.create(
            interaction=whisper,
            timestamp=whisper.timestamp,
            persona=self.persona_one,
        )
        InteractionReadReceipt.objects.create(
            interaction=whisper,
            timestamp=whisper.timestamp,
            account=self.account,
        )

        result = account_attention(account=self.account, entries=self.entries)

        self.assertEqual(result.by_character[self.sheet_one_id].direct, 0)

    def test_directed_pose_older_than_the_window_does_not_count(self) -> None:
        whisper = InteractionFactory(
            scene=self.scene,
            persona=self.outsider,
            mode=InteractionMode.WHISPER,
        )
        old = timezone.now() - timedelta(days=DIRECTED_UNREAD_DAYS + 1)
        Interaction.objects.filter(pk=whisper.pk).update(timestamp=old)
        Interaction.flush_cached_instance(whisper, force=True)
        InteractionReceiver.objects.create(
            interaction=whisper,
            timestamp=old,
            persona=self.persona_one,
        )

        result = account_attention(account=self.account, entries=self.entries)

        self.assertEqual(result.by_character[self.sheet_one_id].direct, 0)

    def test_room_heard_pose_in_an_open_scene_sets_ambient(self) -> None:
        InteractionFactory(
            scene=self.scene,
            persona=self.outsider,
            mode=InteractionMode.POSE,
            visibility=InteractionVisibility.DEFAULT,
        )

        result = account_attention(account=self.account, entries=self.entries)

        self.assertTrue(result.by_character[self.sheet_one_id].ambient)
        self.assertTrue(result.by_character[self.sheet_two_id].ambient)

    def test_private_aside_in_the_same_scene_does_not_set_ambient(self) -> None:
        aside = InteractionFactory(
            scene=self.scene,
            persona=self.outsider,
            mode=InteractionMode.WHISPER,
        )
        InteractionReceiver.objects.create(
            interaction=aside,
            timestamp=aside.timestamp,
            persona=self.other_outsider,
        )

        result = account_attention(account=self.account, entries=self.entries)

        self.assertFalse(result.by_character[self.sheet_one_id].ambient)
        self.assertFalse(result.by_character[self.sheet_two_id].ambient)

    def test_scene_the_account_has_left_does_not_set_ambient(self) -> None:
        left_scene = SceneFactory()
        SceneParticipationFactory(scene=left_scene, account=self.account, left_at=timezone.now())
        InteractionFactory(scene=left_scene, persona=self.persona_one, mode=InteractionMode.POSE)
        InteractionFactory(scene=left_scene, persona=self.outsider, mode=InteractionMode.POSE)

        result = account_attention(account=self.account, entries=self.entries)

        self.assertFalse(result.by_character[self.sheet_one_id].ambient)

    def test_finished_scene_does_not_set_ambient(self) -> None:
        finished_scene = SceneFactory(is_active=False, date_finished=timezone.now())
        SceneParticipationFactory(scene=finished_scene, account=self.account)
        InteractionFactory(
            scene=finished_scene, persona=self.persona_one, mode=InteractionMode.POSE
        )
        InteractionFactory(scene=finished_scene, persona=self.outsider, mode=InteractionMode.POSE)

        result = account_attention(account=self.account, entries=self.entries)

        self.assertFalse(result.by_character[self.sheet_one_id].ambient)

    def test_staff_account_counts_the_same_as_a_player_in_the_same_position(self) -> None:
        def build_position(*, is_staff: bool) -> tuple:
            account = AccountFactory(is_staff=is_staff)
            player_data = PlayerDataFactory(account=account)
            sheet = CharacterSheetFactory()
            persona = sheet.primary_persona
            entry = RosterEntryFactory(character_sheet=sheet)
            RosterTenureFactory(player_data=player_data, roster_entry=entry)

            scene = SceneFactory()
            SceneParticipationFactory(scene=scene, account=account)
            InteractionFactory(scene=scene, persona=persona, mode=InteractionMode.POSE)

            whisper = InteractionFactory(
                scene=scene, persona=self.outsider, mode=InteractionMode.WHISPER
            )
            InteractionReceiver.objects.create(
                interaction=whisper, timestamp=whisper.timestamp, persona=persona
            )
            InteractionFactory(scene=scene, persona=self.outsider, mode=InteractionMode.POSE)

            return account, [entry], sheet.pk

        player_account, player_entries, player_sheet_id = build_position(is_staff=False)
        staff_account, staff_entries, staff_sheet_id = build_position(is_staff=True)

        player_result = account_attention(account=player_account, entries=player_entries)
        staff_result = account_attention(account=staff_account, entries=staff_entries)

        self.assertEqual(
            player_result.by_character[player_sheet_id].direct,
            staff_result.by_character[staff_sheet_id].direct,
        )
        self.assertEqual(
            player_result.by_character[player_sheet_id].ambient,
            staff_result.by_character[staff_sheet_id].ambient,
        )

    def test_query_count_is_flat_as_characters_are_added(self) -> None:
        # Five queries, none per character: (1) directed-unread UNION,
        # (2) open SceneParticipation rows (+ each scene's location id),
        # (3) pose-derived scene attribution, (4) presence-derived scene
        # attribution (Finding 1, #3774 final review - who is standing in an
        # open scene's room right now, posed or not), (5) room-heard ambient
        # aggregation. Query 4 is the new one: it always runs once cls.scene
        # has a location, whether or not it finds anyone there.
        InteractionFactory(scene=self.scene, persona=self.outsider, mode=InteractionMode.POSE)

        with self.assertNumQueries(5):
            account_attention(account=self.account, entries=self.entries[:1])
        with self.assertNumQueries(5):
            account_attention(account=self.account, entries=self.entries)

    def test_silent_participant_in_an_open_scene_gets_ambient(self) -> None:
        # A character can end up an open participant in a scene without ever
        # posing: `add_present_as_co_owners()` and `ensure_scene_participation()`
        # (combat-encounter join) both create a `SceneParticipation` row for
        # everyone physically present, with zero posing required. Pose-only
        # attribution silently drops exactly this character - the quiet one
        # most likely to have something unread (Finding 1, #3774 final review).
        sheet_three = CharacterSheetFactory()
        entry_three = RosterEntryFactory(character_sheet=sheet_three)
        RosterTenureFactory(player_data=self.player_data, roster_entry=entry_three)
        sheet_three.character.move_to(self.room, quiet=True)

        InteractionFactory(
            scene=self.scene,
            persona=self.outsider,
            mode=InteractionMode.POSE,
            visibility=InteractionVisibility.DEFAULT,
        )

        result = account_attention(account=self.account, entries=[*self.entries, entry_three])

        self.assertTrue(result.by_character[sheet_three.pk].ambient)

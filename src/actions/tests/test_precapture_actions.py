"""Journey tests for pre-scene RP capture through the real action seam (#3069).

StartSceneAction is the single chokepoint both telnet (``scene start``) and web
(``SceneViewSet.perform_create``) dispatch through (#3074) — these tests exercise
capture and truncation through ``.run()`` (the full prerequisite/execute path), not
the bare service functions, to prove the telnet+web convergence actually holds.
"""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from actions.definitions.scenes import StartSceneAction, TruncatePrecaptureAction
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.action_constants import ActionRequestStatus
from world.scenes.factories import InteractionFactory
from world.scenes.models import Interaction, PrecaptureConsentRequest, Scene


def _make_room(label: str) -> ObjectDBFactory:
    return ObjectDBFactory(db_key=label, db_typeclass_path="typeclasses.rooms.Room")


def _pc_with_account(db_key: str, location=None):
    kwargs: dict = {"db_key": db_key}
    if location is not None:
        kwargs["location"] = location
    char = CharacterFactory(**kwargs)
    sheet = CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet=sheet)
    tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
    account = tenure.player_data.account
    return char, sheet, account


def _backdate(interaction: Interaction, when) -> None:
    Interaction.objects.filter(pk=interaction.pk).update(timestamp=when)


class StartSceneActionCaptureIntegrationTests(TestCase):
    """StartSceneAction.run() folds in prior unattached RP on scene creation."""

    def test_run_attaches_present_authors_and_opens_consent_for_absent(self):
        room = _make_room("Garden")
        elsewhere = _make_room("Faraway")
        starter, starter_sheet, starter_account = _pc_with_account("Ivy", location=room)
        _absent_actor, absent_sheet, absent_account = _pc_with_account("Jasper", location=elsewhere)

        member_pose = InteractionFactory(
            persona=starter_sheet.primary_persona, writer_account=starter_account, scene=None
        )
        _backdate(member_pose, timezone.now() - timedelta(minutes=15))
        non_member_pose = InteractionFactory(
            persona=absent_sheet.primary_persona, writer_account=absent_account, scene=None
        )
        _backdate(non_member_pose, timezone.now() - timedelta(minutes=15))

        result = StartSceneAction().run(actor=starter)

        assert result.success is True
        scene = Scene.objects.get(location=room, is_active=True)
        member_pose.refresh_from_db()
        non_member_pose.refresh_from_db()
        assert member_pose.scene_id == scene.pk
        assert non_member_pose.scene_id is None
        assert PrecaptureConsentRequest.objects.filter(
            scene=scene, account=absent_account, status=ActionRequestStatus.PENDING
        ).exists()
        assert "1 other" in result.message

    def test_mid_scene_join_never_captures(self):
        """Capture only runs on scene CREATION, never the mid-scene join branch."""
        room = _make_room("Courtyard")
        starter, _starter_sheet, _starter_account = _pc_with_account("Karl", location=room)
        joiner, joiner_sheet, joiner_account = _pc_with_account("Liu", location=room)

        StartSceneAction().run(actor=starter)

        # A pose recorded (unattached, hypothetically) between start and join should
        # NOT be swept up by the join branch.
        late_pose = InteractionFactory(
            persona=joiner_sheet.primary_persona, writer_account=joiner_account, scene=None
        )
        _backdate(late_pose, timezone.now() - timedelta(minutes=1))

        result = StartSceneAction().run(actor=joiner)

        assert result.success is True
        assert "already active" in result.message
        late_pose.refresh_from_db()
        assert late_pose.scene_id is None


class TruncatePrecaptureActionTests(TestCase):
    """TruncatePrecaptureAction: permissions, telnet listing, web scene_id resolution."""

    def _scene_with_captured_poses(self):
        room = _make_room("Hall")
        starter, sheet, account = _pc_with_account("Mira", location=room)

        # Poses recorded before anyone remembered to start the scene — same ordering
        # as the real gap this feature closes: interactions first, scene start second.
        now = timezone.now()
        interactions = []
        for i in range(2):
            ia = InteractionFactory(persona=sheet.primary_persona, writer_account=account)
            _backdate(ia, now - timedelta(minutes=20 - i * 10))
            interactions.append(ia)

        StartSceneAction().run(actor=starter)
        scene = Scene.objects.get(location=room, is_active=True)
        return room, scene, starter, interactions

    def test_non_owner_cannot_truncate(self):
        room, scene, _starter, interactions = self._scene_with_captured_poses()
        outsider, _sheet, _account = _pc_with_account("Nora", location=room)

        result = TruncatePrecaptureAction().run(actor=outsider)

        assert result.success is False
        interactions[0].refresh_from_db()
        assert interactions[0].scene_id == scene.pk  # untouched

    def test_owner_lists_via_telnet_room_resolution(self):
        room, _scene, starter, _interactions = self._scene_with_captured_poses()
        assert starter.db_location_id == room.pk

        result = TruncatePrecaptureAction().run(actor=starter)

        assert result.success is True
        assert "Pre-scene captured poses" in result.message
        assert "1. " in result.message
        assert "2. " in result.message

    def test_owner_truncates_via_explicit_scene_id_web_path(self):
        """The web path passes scene_id explicitly — must work even if the actor's
        current room is used only as a fallback, proving telnet+web convergence on
        the same Action."""
        _room, scene, starter, interactions = self._scene_with_captured_poses()

        result = TruncatePrecaptureAction().run(
            actor=starter, scene_id=scene.pk, interaction_id=interactions[1].pk
        )

        assert result.success is True
        interactions[0].refresh_from_db()
        interactions[1].refresh_from_db()
        assert interactions[0].scene_id is None
        assert interactions[1].scene_id == scene.pk

    def test_truncate_by_position_via_telnet_style_kwarg(self):
        _room, scene, starter, interactions = self._scene_with_captured_poses()

        result = TruncatePrecaptureAction().run(actor=starter, position=2)

        assert result.success is True
        interactions[0].refresh_from_db()
        interactions[1].refresh_from_db()
        assert interactions[0].scene_id is None
        assert interactions[1].scene_id == scene.pk

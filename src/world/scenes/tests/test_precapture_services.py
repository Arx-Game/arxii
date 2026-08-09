"""Tests for pre-scene RP capture (#3069 sub-item 4)."""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.action_constants import ActionRequestStatus
from world.scenes.factories import InteractionFactory, SceneFactory
from world.scenes.models import Interaction, PrecaptureConsentRequest
from world.scenes.precapture_services import (
    PRECAPTURE_WINDOW,
    capture_prescene_interactions,
    list_precaptured,
    respond_to_precapture_consent,
    truncate_precaptured,
)


def _make_room(label: str = "Room") -> ObjectDBFactory:
    return ObjectDBFactory(db_key=label, db_typeclass_path="typeclasses.rooms.Room")


def _pc_with_account(db_key: str, location=None):
    """A PC with an active roster tenure (so active_account/writer_account resolve)."""
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


class CapturePrescreneInteractionsTests(TestCase):
    """capture_prescene_interactions: present authors attach, absent authors pend."""

    def test_present_author_interaction_attaches_immediately(self):
        room = _make_room("Tavern")
        _actor, sheet, account = _pc_with_account("Alice", location=room)
        interaction = InteractionFactory(
            persona=sheet.primary_persona, writer_account=account, scene=None
        )
        _backdate(interaction, timezone.now() - timedelta(minutes=10))

        scene = SceneFactory(location=room, is_active=True)
        result = capture_prescene_interactions(scene, room)

        interaction.refresh_from_db()
        assert interaction.scene_id == scene.pk
        assert result.attached_count == 1
        assert result.pending_consent_count == 0

    def test_absent_author_interaction_opens_consent_request_not_attached(self):
        room = _make_room("Tavern2")
        other_room = _make_room("Elsewhere")
        _present_actor, _present_sheet, _present_account = _pc_with_account("Bob", location=room)
        _absent_actor, absent_sheet, absent_account = _pc_with_account("Carol", location=other_room)
        interaction = InteractionFactory(
            persona=absent_sheet.primary_persona, writer_account=absent_account, scene=None
        )
        _backdate(interaction, timezone.now() - timedelta(minutes=10))

        scene = SceneFactory(location=room, is_active=True)
        result = capture_prescene_interactions(scene, room)

        interaction.refresh_from_db()
        assert interaction.scene_id is None
        assert result.attached_count == 0
        assert result.pending_consent_count == 1
        assert PrecaptureConsentRequest.objects.filter(
            scene=scene, account=absent_account, status=ActionRequestStatus.PENDING
        ).exists()

    def test_interaction_outside_window_is_never_a_candidate(self):
        room = _make_room("Tavern3")
        _actor, sheet, account = _pc_with_account("Dave", location=room)
        interaction = InteractionFactory(
            persona=sheet.primary_persona, writer_account=account, scene=None
        )
        _backdate(interaction, timezone.now() - PRECAPTURE_WINDOW - timedelta(minutes=1))

        scene = SceneFactory(location=room, is_active=True)
        result = capture_prescene_interactions(scene, room)

        interaction.refresh_from_db()
        assert interaction.scene_id is None
        assert result.attached_count == 0
        assert result.pending_consent_count == 0

    def test_interaction_with_no_writer_account_is_skipped(self):
        room = _make_room("Tavern4")
        _actor, sheet, _account = _pc_with_account("Erin", location=room)
        interaction = InteractionFactory(
            persona=sheet.primary_persona, writer_account=None, scene=None
        )
        _backdate(interaction, timezone.now() - timedelta(minutes=5))

        scene = SceneFactory(location=room, is_active=True)
        result = capture_prescene_interactions(scene, room)

        interaction.refresh_from_db()
        assert interaction.scene_id is None
        assert result.attached_count == 0
        assert result.pending_consent_count == 0


class RespondToPrecaptureConsentTests(TestCase):
    """Accepting attaches every qualifying interaction; declining leaves them unattached."""

    def _setup_pending(self, minutes_ago: int = 10):
        room = _make_room("Salon")
        other_room = _make_room("Away")
        _present_actor, _present_sheet, _present_account = _pc_with_account("Fiona", location=room)
        _absent_actor, absent_sheet, absent_account = _pc_with_account(
            "Gareth", location=other_room
        )
        interaction = InteractionFactory(
            persona=absent_sheet.primary_persona, writer_account=absent_account, scene=None
        )
        _backdate(interaction, timezone.now() - timedelta(minutes=minutes_ago))
        scene = SceneFactory(location=room, is_active=True)
        capture_prescene_interactions(scene, room)
        request = PrecaptureConsentRequest.objects.get(scene=scene, account=absent_account)
        return request, interaction

    def test_accept_attaches_and_marks_accepted(self):
        request, interaction = self._setup_pending()

        attached = respond_to_precapture_consent(request, accept=True)

        interaction.refresh_from_db()
        request.refresh_from_db()
        assert attached == 1
        assert interaction.scene_id == request.scene_id
        assert request.status == ActionRequestStatus.ACCEPTED
        assert request.responded_at is not None

    def test_decline_leaves_unattached_and_marks_denied(self):
        request, interaction = self._setup_pending()

        attached = respond_to_precapture_consent(request, accept=False)

        interaction.refresh_from_db()
        request.refresh_from_db()
        assert attached == 0
        assert interaction.scene_id is None
        assert request.status == ActionRequestStatus.DENIED

    def test_double_respond_is_a_no_op(self):
        request, interaction = self._setup_pending()
        respond_to_precapture_consent(request, accept=True)

        second_attached = respond_to_precapture_consent(request, accept=False)

        interaction.refresh_from_db()
        assert second_attached == 0
        assert interaction.scene_id is not None  # still attached from the first accept


class TruncatePrecapturedTests(TestCase):
    """list_precaptured / truncate_precaptured: the starter's cutoff control."""

    def _captured_scene(self):
        room = _make_room("Ballroom")
        _actor, sheet, account = _pc_with_account("Helen", location=room)
        scene = SceneFactory(location=room, is_active=True)
        interactions = []
        for i in range(3):
            ia = InteractionFactory(persona=sheet.primary_persona, writer_account=account)
            _backdate(ia, scene.date_started - timedelta(minutes=30 - i * 10))
            interactions.append(ia)
        capture_prescene_interactions(scene, room)
        return scene, interactions

    def test_list_precaptured_is_oldest_first(self):
        scene, interactions = self._captured_scene()

        listed = list(list_precaptured(scene))

        assert [ia.pk for ia in listed] == [ia.pk for ia in interactions]

    def test_truncate_by_interaction_id_drops_everything_before(self):
        scene, interactions = self._captured_scene()

        count = truncate_precaptured(scene, interaction_id=interactions[1].pk)

        assert count == 1
        interactions[0].refresh_from_db()
        interactions[1].refresh_from_db()
        interactions[2].refresh_from_db()
        assert interactions[0].scene_id is None
        assert interactions[1].scene_id == scene.pk
        assert interactions[2].scene_id == scene.pk

    def test_truncate_by_position(self):
        scene, interactions = self._captured_scene()

        count = truncate_precaptured(scene, position=3)

        assert count == 2
        interactions[0].refresh_from_db()
        interactions[1].refresh_from_db()
        interactions[2].refresh_from_db()
        assert interactions[0].scene_id is None
        assert interactions[1].scene_id is None
        assert interactions[2].scene_id == scene.pk

    def test_truncate_never_touches_a_live_pose(self):
        """A pose recorded AFTER scene start (timestamp >= date_started) is never captured."""
        scene, interactions = self._captured_scene()
        live_pose = InteractionFactory(
            persona=interactions[0].persona,
            writer_account=interactions[0].writer_account,
            scene=scene,
        )
        assert live_pose.timestamp >= scene.date_started

        # Truncating everything (position beyond the captured set is invalid,
        # so use the last captured row) must not detach the live pose.
        truncate_precaptured(scene, position=len(interactions))

        live_pose.refresh_from_db()
        assert live_pose.scene_id == scene.pk

    def test_truncate_with_unknown_interaction_id_raises(self):
        scene, _interactions = self._captured_scene()
        other = InteractionFactory()

        with self.assertRaises(ValueError):
            truncate_precaptured(scene, interaction_id=other.pk)

    def test_truncate_with_out_of_range_position_raises(self):
        scene, _interactions = self._captured_scene()

        with self.assertRaises(ValueError):
            truncate_precaptured(scene, position=99)

    def test_truncate_with_nothing_captured_returns_zero(self):
        room = _make_room("EmptyRoom")
        scene = SceneFactory(location=room, is_active=True)

        assert truncate_precaptured(scene, position=1) == 0

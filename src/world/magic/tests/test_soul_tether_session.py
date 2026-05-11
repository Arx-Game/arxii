"""Tests for accept_soul_tether_via_session wrapper (Slice B §4.15).

These tests verify the role-discrimination and guard logic in the wrapper
itself. The underlying accept_soul_tether service's preconditions (affinity
gates, unlock gates, etc.) are covered by the existing soul-tether service
tests, which call accept_soul_tether directly.
"""

from datetime import UTC, datetime, timedelta

from django.test import TestCase


class AcceptSoulTetherViaSessionTests(TestCase):
    def _build_bilateral_session(
        self,
        *,
        initiator_role: str = "SINEATER",
        invitee_role: str = "SINNER",
        omit_invitee_role: bool = False,
    ):
        """Helper: build a BILATERAL session with both participants ACCEPTED
        and their soul_tether_role choices in participant_kwargs."""
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.constants import ParticipantState, ParticipationRule
        from world.magic.factories import RitualFactory
        from world.magic.models.sessions import (
            RitualSession,
            RitualSessionParticipant,
        )

        ritual = RitualFactory(
            participation_rule=ParticipationRule.BILATERAL,
            min_participants=2,
            max_participants=2,
        )
        initiator = CharacterSheetFactory()
        invitee = CharacterSheetFactory()
        session = RitualSession.objects.create(
            ritual=ritual,
            initiator=initiator,
            session_kwargs={},
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        RitualSessionParticipant.objects.create(
            session=session,
            character_sheet=initiator,
            state=ParticipantState.ACCEPTED,
            participant_kwargs={"soul_tether_role": initiator_role},
        )
        invitee_kwargs = {} if omit_invitee_role else {"soul_tether_role": invitee_role}
        RitualSessionParticipant.objects.create(
            session=session,
            character_sheet=invitee,
            state=ParticipantState.ACCEPTED,
            participant_kwargs=invitee_kwargs,
        )
        return session, initiator, invitee

    def test_role_conflict_raises_bilateral_role_conflict(self):
        from world.magic.exceptions import BilateralRoleConflictError
        from world.magic.services.soul_tether import accept_soul_tether_via_session

        session, _, _ = self._build_bilateral_session(
            initiator_role="SINEATER",
            invitee_role="SINEATER",
        )
        with self.assertRaises(BilateralRoleConflictError):
            accept_soul_tether_via_session(session=session)

    def test_missing_role_choice_raises_required_reference_missing(self):
        from world.magic.exceptions import RequiredReferenceMissingError
        from world.magic.services.soul_tether import accept_soul_tether_via_session

        session, _, _ = self._build_bilateral_session(omit_invitee_role=True)
        with self.assertRaises(RequiredReferenceMissingError):
            accept_soul_tether_via_session(session=session)

    def test_invalid_role_value_raises_required_reference_missing(self):
        from world.magic.exceptions import RequiredReferenceMissingError
        from world.magic.services.soul_tether import accept_soul_tether_via_session

        session, _, _ = self._build_bilateral_session(invitee_role="bogus_role")
        with self.assertRaises(RequiredReferenceMissingError):
            accept_soul_tether_via_session(session=session)

    def test_wrong_participant_count_raises_required_reference_missing(self):
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.constants import ParticipantState, ParticipationRule
        from world.magic.exceptions import RequiredReferenceMissingError
        from world.magic.factories import RitualFactory
        from world.magic.models.sessions import RitualSession, RitualSessionParticipant
        from world.magic.services.soul_tether import accept_soul_tether_via_session

        ritual = RitualFactory(
            participation_rule=ParticipationRule.BILATERAL,
            min_participants=2,
            max_participants=2,
        )
        initiator = CharacterSheetFactory()
        session = RitualSession.objects.create(
            ritual=ritual,
            initiator=initiator,
            session_kwargs={},
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        RitualSessionParticipant.objects.create(
            session=session,
            character_sheet=initiator,
            state=ParticipantState.ACCEPTED,
            participant_kwargs={"soul_tether_role": "SINEATER"},
        )
        # Only one ACCEPTED participant — wrapper should refuse.
        with self.assertRaises(RequiredReferenceMissingError):
            accept_soul_tether_via_session(session=session)

"""Multi-participant ritual session lifecycle services.

See `docs/superpowers/specs/2026-05-10-covenants-slice-b-design.md` §4.5.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
import importlib

from django.db import transaction
from django.utils import timezone

from world.character_sheets.models import CharacterSheet
from world.magic.constants import (
    ParticipantState,
    ParticipationRule,
)
from world.magic.exceptions import (
    ParticipantCountError,
    SessionNotInPendingError,
    ThresholdNotMetError,
)
from world.magic.models.rituals import Ritual
from world.magic.models.sessions import (
    RitualSession,
    RitualSessionParticipant,
    RitualSessionReference,
)
from world.magic.types.sessions import RitualSessionReferenceSpec

_FORMATION_MIN_PARTICIPANTS = 2
"""FORMATION rituals require at least this many participants even without explicit bounds."""


def draft_session(  # noqa: PLR0913 — kw-only args; each session parameter is distinct
    *,
    ritual: Ritual,
    initiator: CharacterSheet,
    proposed_terms: str,
    session_kwargs: dict,
    invitee_sheets: Sequence[CharacterSheet],
    session_references: Sequence[RitualSessionReferenceSpec],
    initiator_participant_kwargs: dict,
    initiator_references: Sequence[RitualSessionReferenceSpec],
    expires_at: datetime,
) -> RitualSession:
    """Create a session, all participant rows, and any pre-existing references.

    Initiator is auto-created as ACCEPTED with their participant_kwargs +
    references. Invitees start as INVITED.

    Raises ParticipantCountError if the ritual's min/max_participants bounds
    are violated by the total participant count (initiator + invitees).
    """
    # Deduplicate the invitee list against the initiator (idiomatic — drafting
    # services shouldn't double-count the initiator if a caller passes them in).
    deduped_invitees = [s for s in invitee_sheets if s != initiator]
    total_participants = 1 + len(deduped_invitees)
    if ritual.min_participants is not None and total_participants < ritual.min_participants:
        raise ParticipantCountError
    if ritual.max_participants is not None and total_participants > ritual.max_participants:
        raise ParticipantCountError
    # FORMATION minimum 2 enforced even without bounds set:
    if (
        ritual.participation_rule == ParticipationRule.FORMATION
        and total_participants < _FORMATION_MIN_PARTICIPANTS
    ):
        raise ParticipantCountError

    with transaction.atomic():
        session = RitualSession.objects.create(
            ritual=ritual,
            initiator=initiator,
            proposed_terms=proposed_terms,
            session_kwargs=session_kwargs,
            expires_at=expires_at,
        )
        # Initiator participant — auto-accepted.
        initiator_p = RitualSessionParticipant.objects.create(
            session=session,
            character_sheet=initiator,
            state=ParticipantState.ACCEPTED,
            participant_kwargs=initiator_participant_kwargs,
        )
        for sheet in deduped_invitees:
            RitualSessionParticipant.objects.create(
                session=session,
                character_sheet=sheet,
                state=ParticipantState.INVITED,
            )
        # Session-level references.
        for spec in session_references:
            _create_reference_from_spec(session=session, participant=None, spec=spec)
        # Initiator's references (e.g., chosen covenant role).
        for spec in initiator_references:
            _create_reference_from_spec(
                session=session,
                participant=initiator_p,
                spec=spec,
            )
        return session


def accept_session(
    *,
    participant: RitualSessionParticipant,
    participant_kwargs: dict,
    references: Sequence[RitualSessionReferenceSpec],
) -> None:
    """Transition participant INVITED→ACCEPTED, creating their references.

    Race prevented: two concurrent accepts on the same participant row.
    select_for_update locks the participant; second accept sees ACCEPTED
    state and raises SessionNotInPendingError.
    """
    with transaction.atomic():
        # Lock the participant row so concurrent accepts serialize.
        # refresh_from_db ensures the SharedMemoryModel-cached instance
        # reflects the just-locked row's state.
        locked = RitualSessionParticipant.objects.select_for_update().get(pk=participant.pk)
        locked.refresh_from_db()
        if locked.state != ParticipantState.INVITED:
            raise SessionNotInPendingError
        locked.state = ParticipantState.ACCEPTED
        locked.participant_kwargs = participant_kwargs
        locked.responded_at = timezone.now()
        locked.save()
        for spec in references:
            _create_reference_from_spec(
                session=locked.session,
                participant=locked,
                spec=spec,
            )


def decline_session(*, participant: RitualSessionParticipant) -> None:
    """Transition participant INVITED→DECLINED.

    If the decline drops accepts below the ritual's threshold, the entire
    session is deleted in the same transaction (CASCADE wipes participants
    and references).

    Race prevented: two concurrent declines on the same participant.
    select_for_update on the participant row serializes; second decline sees
    DECLINED state and raises SessionNotInPendingError.
    """
    with transaction.atomic():
        locked = RitualSessionParticipant.objects.select_for_update().get(pk=participant.pk)
        locked.refresh_from_db()
        if locked.state != ParticipantState.INVITED:
            raise SessionNotInPendingError
        locked.state = ParticipantState.DECLINED
        locked.responded_at = timezone.now()
        locked.save()
        if not _threshold_can_still_be_met(locked.session):
            locked.session.delete()


def _threshold_can_still_be_met(session: RitualSession) -> bool:
    """Determine whether the session has any path to a successful fire.

    Called inside the decline_session transaction after a state change. The
    .values_list call is on the participants related manager but it's
    intentional in-mutator iteration — we need fresh DB state, not cached
    handler reads (per spec §3.9 carve-out for in-transaction iteration).
    """
    rule = session.ritual.participation_rule
    states = list(session.participants.values_list("state", flat=True))
    accepts = sum(1 for s in states if s == ParticipantState.ACCEPTED)
    declines = sum(1 for s in states if s == ParticipantState.DECLINED)
    invited = sum(1 for s in states if s == ParticipantState.INVITED)
    if rule == ParticipationRule.FORMATION:
        # All must accept; any decline kills it; ≥2 accepts required:
        if declines > 0:
            return False
        return accepts + invited >= _FORMATION_MIN_PARTICIPANTS
    if rule == ParticipationRule.INDUCTION:
        # Majority of respondents, ≥2 accepts. Best-case = current accepts +
        # all remaining INVITED accept:
        best_accepts = accepts + invited
        return best_accepts >= _FORMATION_MIN_PARTICIPANTS and best_accepts > declines
    if rule == ParticipationRule.BILATERAL:
        # Exactly 2; any decline kills it.
        if declines > 0:
            return False
        return accepts + invited == _FORMATION_MIN_PARTICIPANTS
    return True  # SINGLE_ACTOR sessions shouldn't exist; permissive default


def fire_session(*, session: RitualSession) -> object:
    """Dispatch the ritual's service_function_path and delete the session.

    Race prevented: two concurrent fires creating duplicate domain rows.
    select_for_update on the session row serializes; loser sees DoesNotExist
    when it tries to acquire the lock on a row that's been deleted.
    """
    with transaction.atomic():
        locked = RitualSession.objects.select_for_update().get(pk=session.pk)
        locked.refresh_from_db()
        # Threshold check using the locked row's current participant states:
        if not _threshold_currently_met(locked):
            raise ThresholdNotMetError
        # Resolve the dispatched service via importlib:
        module_path, _, fn_name = locked.ritual.service_function_path.rpartition(".")
        module = importlib.import_module(module_path)
        fn = getattr(module, fn_name)  # noqa: GETATTR_LITERAL — service path is data
        # Call the dispatched service. If it raises, transaction rolls back
        # and the session stays alive for the initiator to retry or cancel.
        result = fn(session=locked)
        # Delete the session in the same transaction (CASCADE wipes participants
        # and references):
        locked.delete()
        return result


def _threshold_currently_met(session: RitualSession) -> bool:
    """The companion to _threshold_can_still_be_met — checks current state.

    .values_list() is intentional in-mutator iteration per spec §3.9 carve-out.
    """
    rule = session.ritual.participation_rule
    states = list(session.participants.values_list("state", flat=True))
    accepts = sum(1 for s in states if s == ParticipantState.ACCEPTED)
    declines = sum(1 for s in states if s == ParticipantState.DECLINED)
    invited = sum(1 for s in states if s == ParticipantState.INVITED)
    if rule == ParticipationRule.FORMATION:
        return invited == 0 and declines == 0 and accepts >= _FORMATION_MIN_PARTICIPANTS
    if rule == ParticipationRule.INDUCTION:
        return accepts > declines and accepts >= _FORMATION_MIN_PARTICIPANTS
    if rule == ParticipationRule.BILATERAL:
        return invited == 0 and declines == 0 and accepts == _FORMATION_MIN_PARTICIPANTS
    return False  # SINGLE_ACTOR shouldn't reach here


def _create_reference_from_spec(
    *,
    session: RitualSession,
    participant: RitualSessionParticipant | None,
    spec: RitualSessionReferenceSpec,
) -> RitualSessionReference:
    return RitualSessionReference.objects.create(
        session=session,
        participant=participant,
        kind=spec.kind,
        ref_covenant=spec.ref_covenant,
        ref_covenant_role=spec.ref_covenant_role,
    )

"""Multi-participant ritual session lifecycle services.

See `docs/superpowers/specs/2026-05-10-covenants-slice-b-design.md` §4.5.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from django.db import transaction

from world.character_sheets.models import CharacterSheet
from world.magic.constants import (
    ParticipantState,
    ParticipationRule,
)
from world.magic.exceptions import ParticipantCountError
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

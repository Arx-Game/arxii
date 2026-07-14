"""Frame jobs (#1825) — perverting real crime evidence into an anchored L3 accusation.

The heavy tier of the accusation counter-play. There is no fabricating a frame from
nothing: you gather a real crime's evidence, take it to a **Workshop of Iniquity**, and
open a FRAME_JOB ``Project`` advanced with Forgery checks (the seeded contribution
method). On a successful completion the evidence is perverted — the anchored L3
accusation files (``real_deed`` = the actual crime), heat lands where the crime
happened, the tamper craft becomes the counter-investigation's difficulty, and the
evidence goes **off-grid** into the case file. Consent against a PC patsy is checked at
start AND re-checked at completion. All magnitudes PLACEHOLDER.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.utils import timezone

from world.justice.constants import EvidenceState
from world.justice.evidence import EvidenceError, _destroy_evidence_item, _holds_evidence
from world.justice.models import CrimeEvidence, DeedCrimeTag, FrameJobDetails

if TYPE_CHECKING:
    from datetime import timedelta

    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.justice.models import CrimeKind
    from world.projects.models import Project
    from world.traits.models import CheckOutcome

logger = logging.getLogger(__name__)

# PLACEHOLDER magnitudes — tuned in a later author pass.
FRAME_JOB_THRESHOLD = 15
FRAME_TAMPER_BASE_QUALITY = 10

_NOT_HELD = "You are not holding that evidence."
_NOT_GATHERED = "That evidence isn't in a state to doctor."
_WRONG_CRIME = "The evidence doesn't speak to that crime."
_NO_SELF_FRAME = "Pinning your own crime on yourself is just a confession."
_NOT_A_FRAME = "They actually did it — that's not a frame, that's evidence."
_NO_WORKSHOP = "Doctoring evidence takes a Workshop of Iniquity."
_CONSENT_BLOCKED = (
    "They have not opened themselves to being antagonised. You can't pin a crime on them."
)


def start_frame_job(  # noqa: PLR0913 — keyword-only; each arg is a distinct frame field
    character: ObjectDB,
    *,
    evidence: CrimeEvidence,
    subject_sheet: CharacterSheet,
    crime_kind: CrimeKind,
    content: str,
    duration: timedelta | None = None,
) -> Project:
    """Open the assemble-false-evidence Project in a Workshop of Iniquity.

    Guards: the framer holds the GATHERED evidence and stands in a workshop; the
    alleged crime is one the evidence's deed is really tagged with; the patsy is
    neither the framer nor the deed's actual culprit; and the patsy's ``hostile``
    consent category admits the framer (re-checked again at completion).
    """
    from datetime import timedelta as _timedelta  # noqa: PLC0415

    from world.projects.constants import CompletionMode, ProjectKind, ProjectStatus  # noqa: PLC0415
    from world.projects.models import Project  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415
    from world.secrets.services import accusation_permitted  # noqa: PLC0415

    if evidence.state != EvidenceState.GATHERED:
        raise EvidenceError(_NOT_GATHERED)
    if not _holds_evidence(character, evidence):
        raise EvidenceError(_NOT_HELD)
    if not DeedCrimeTag.objects.filter(deed=evidence.deed, crime_kind=crime_kind).exists():
        raise EvidenceError(_WRONG_CRIME)

    framer_sheet = character.sheet_data  # type: ignore[attr-defined] — typeclass extension
    if subject_sheet.pk == framer_sheet.pk:
        raise EvidenceError(_NO_SELF_FRAME)
    culprit = evidence.deed.persona
    if culprit is not None and culprit.character_sheet_id == subject_sheet.pk:
        raise EvidenceError(_NOT_A_FRAME)
    if not accusation_permitted(framer_sheet=framer_sheet, target_sheet=subject_sheet):
        raise EvidenceError(_CONSENT_BLOCKED)
    if not _workshop_in_room(character):
        raise EvidenceError(_NO_WORKSHOP)

    now = timezone.now()
    project = Project.objects.create(
        kind=ProjectKind.FRAME_JOB,
        completion_mode=CompletionMode.SINGLE_THRESHOLD,
        status=ProjectStatus.ACTIVE,
        owner_persona=active_persona_for_sheet(framer_sheet),
        started_at=now,
        time_limit=now + (duration or _timedelta(days=30)),
        threshold_target=FRAME_JOB_THRESHOLD,
    )
    FrameJobDetails.objects.create(
        project=project,
        evidence=evidence,
        subject_sheet=subject_sheet,
        crime_kind=crime_kind,
        content=content,
    )
    evidence.state = EvidenceState.TAMPERING
    evidence.save(update_fields=["state"])
    return project


def resolve_frame_job(project: Project, outcome_tier: CheckOutcome | None) -> None:
    """FRAME_JOB kind handler: pervert the evidence and file the anchored frame.

    Registered with the projects framework at app-ready. A failed/expired outcome
    quietly hands the evidence back (GATHERED). On success, consent is RE-CHECKED
    (the patsy may have locked down since the start) — a block fails the frame the
    same as a bad outcome, never overriding the gate.
    """
    from world.secrets.constants import SecretLevel  # noqa: PLC0415
    from world.secrets.services import accusation_permitted  # noqa: PLC0415

    details = project.frame_job_details
    evidence = details.evidence

    def _hand_back() -> None:
        if evidence.state == EvidenceState.TAMPERING:
            evidence.state = EvidenceState.GATHERED
            evidence.save(update_fields=["state"])

    if outcome_tier is None or outcome_tier.success_level < 0:
        _hand_back()
        return

    framer_sheet = (
        project.owner_persona.character_sheet if project.owner_persona is not None else None
    )
    if framer_sheet is None or not accusation_permitted(
        framer_sheet=framer_sheet, target_sheet=details.subject_sheet
    ):
        logger.info(
            "frame job %s abandoned at completion: consent no longer permits the frame.",
            project.pk,
        )
        _hand_back()
        return

    from world.justice.services import file_criminal_accusation  # noqa: PLC0415

    secret = file_criminal_accusation(
        accuser_persona=project.owner_persona,
        subject_sheet=details.subject_sheet,
        content=details.content,
        crime_kind=details.crime_kind,
        level=SecretLevel.CAREFULLY_KEPT,
        real_deed=evidence.deed,
        area=evidence.room_profile.area,
    )
    tamper_quality = FRAME_TAMPER_BASE_QUALITY + project.current_progress
    _destroy_evidence_item(evidence)
    evidence.state = EvidenceState.OFF_GRID
    evidence.tamper_quality = tamper_quality
    evidence.save(update_fields=["item_instance", "state", "tamper_quality"])
    _plant_frame_counter_clue(secret, evidence, tamper_quality)


def _plant_frame_counter_clue(secret, evidence: CrimeEvidence, difficulty: int) -> None:
    """The frame's disprove trail, seeded from the tamper craft (best-effort on region)."""
    from world.areas.constants import AreaLevel  # noqa: PLC0415
    from world.areas.services import get_ancestor_at_level  # noqa: PLC0415
    from world.clues.services import create_accusation_counter_clue  # noqa: PLC0415

    area = evidence.room_profile.area
    if area is None:
        return
    region = get_ancestor_at_level(area, AreaLevel.REGION)
    if region is None:
        return
    create_accusation_counter_clue(secret, region=region, difficulty=difficulty)


def _workshop_in_room(character: ObjectDB) -> bool:
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415
    from world.room_features.constants import RoomFeatureServiceStrategy  # noqa: PLC0415
    from world.room_features.models import RoomFeatureInstance  # noqa: PLC0415

    room = character.location
    if room is None:
        return False
    try:
        room_profile = room.room_profile
    except RoomProfile.DoesNotExist:
        return False
    return (
        RoomFeatureInstance.objects.filter(
            room_profile=room_profile,
            feature_kind__service_strategy=RoomFeatureServiceStrategy.WORKSHOP_OF_INIQUITY,
        )
        .active()
        .exists()
    )

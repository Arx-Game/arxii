"""Case file (#1825) — produce filed frame evidence and physically examine it.

When a frame files, its perverted evidence goes **off-grid** — consumed into the case
file that makes the accusation stick. The counter-move: an investigator with **local
authority** (membership in an organization under the room's enforcing society —
PLACEHOLDER predicate, refined when the justice pipeline lands, #2378) may **produce**
the evidence back out of storage, and any holder may **examine** it — a Scrutinize
Evidence check against the framer's recorded tamper craft. Only piloted characters do
this; nothing automated examines evidence. Unless someone contests the frame, it
stands on the framer's roll.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from world.justice.constants import SCRUTINIZE_EVIDENCE_CHECK_NAME, EvidenceState
from world.justice.evidence import EvidenceError, EvidenceResult, _holds_evidence
from world.justice.models import AccusationCrimeClaim, CrimeEvidence

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.secrets.models import Secret

_NO_AUTHORITY = "The case file only opens for someone with standing under the local law."
_NO_CASE = "No filed case anchors that accusation."
_NOT_PRODUCIBLE = "That evidence isn't sitting in any case file."
_NOT_HOLDER = "You are not holding that evidence."
_NOT_EXAMINABLE = "There's nothing produced to examine."


def has_local_authority(sheet: CharacterSheet, room: ObjectDB) -> bool:
    """PLACEHOLDER authority predicate: standing under the room's enforcing society.

    True when any of the sheet's personas holds an active membership in an
    organization belonging to the enforcing society where the character stands.
    The real gate (offices, warrants, ranks) is #2378's design; this is the
    mechanism with an editable default.
    """
    from world.justice.services import area_for_room, enforcing_society_for  # noqa: PLC0415
    from world.societies.models import OrganizationMembership  # noqa: PLC0415

    society = enforcing_society_for(area_for_room(room))
    if society is None:
        return False
    return OrganizationMembership.objects.filter(
        persona__character_sheet=sheet,
        organization__society=society,
        left_at__isnull=True,
        exiled_at__isnull=True,
    ).exists()


def produce_case_evidence(character: ObjectDB, secret: Secret) -> CrimeEvidence:
    """Pull a filed frame's evidence back out of the case file for scrutiny.

    Requires local authority where the character stands. The evidence
    re-materializes as a real item in the producer's hands (PRODUCED) — from
    there it can be examined, handed to a specialist, or stolen back.
    """
    from world.items.models import ItemInstance  # noqa: PLC0415
    from world.items.services.materialize import materialize_item_game_object  # noqa: PLC0415
    from world.justice.evidence import _evidence_template  # noqa: PLC0415

    claim = AccusationCrimeClaim.objects.filter(secret=secret).select_related("real_deed").first()
    if claim is None or claim.real_deed is None:
        raise EvidenceError(_NO_CASE)
    evidence = CrimeEvidence.objects.filter(deed=claim.real_deed).first()
    if evidence is None or evidence.state != EvidenceState.OFF_GRID:
        raise EvidenceError(_NOT_PRODUCIBLE)
    sheet = character.sheet_data  # type: ignore[attr-defined] — typeclass extension
    room = character.location
    if room is None or not has_local_authority(sheet, room):
        raise EvidenceError(_NO_AUTHORITY)

    with transaction.atomic():
        instance = ItemInstance.objects.create(
            template=_evidence_template(),
            holder_character_sheet=sheet,
        )
        evidence.item_instance = instance
        evidence.state = EvidenceState.PRODUCED
        evidence.save(update_fields=["item_instance", "state"])
        materialize_item_game_object(instance, sheet)
    return evidence


def examine_evidence(character: ObjectDB, evidence: CrimeEvidence) -> EvidenceResult:
    """Scrutinize produced evidence — a check against the framer's tamper craft.

    Success on tampered evidence surfaces the accusation's counter-clue directly
    (the physical proof IS a lead) — a head start into the investigation project.
    Untampered evidence examines clean: the check runs against its base quality
    and success simply confirms nothing is off.
    """
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.checks.services import perform_check  # noqa: PLC0415

    if evidence.state != EvidenceState.PRODUCED:
        raise EvidenceError(_NOT_EXAMINABLE)
    if not _holds_evidence(character, evidence):
        raise EvidenceError(_NOT_HOLDER)

    difficulty = (
        evidence.tamper_quality if evidence.tamper_quality is not None else evidence.quality
    )
    check_type = CheckType.objects.get(name=SCRUTINIZE_EVIDENCE_CHECK_NAME)
    result = perform_check(character, check_type, target_difficulty=difficulty)
    if result.success_level < 0:
        return EvidenceResult(success=False, evidence_id=evidence.pk)
    if evidence.tamper_quality is not None:
        _grant_counter_clue(character, evidence)
    return EvidenceResult(success=True, evidence_id=evidence.pk)


def _grant_counter_clue(character: ObjectDB, evidence: CrimeEvidence) -> None:
    """A beaten tamper roll hands the examiner the accusation's investigable lead."""
    from world.clues.constants import ClueTargetKind  # noqa: PLC0415
    from world.clues.models import Clue  # noqa: PLC0415
    from world.clues.services import acquire_clue  # noqa: PLC0415
    from world.roster.models import RosterEntry  # noqa: PLC0415

    claim = AccusationCrimeClaim.objects.filter(real_deed=evidence.deed).first()
    if claim is None:
        return
    clue = Clue.objects.filter(
        target_kind=ClueTargetKind.SECRET, target_secret=claim.secret
    ).first()
    if clue is None:
        return
    sheet = character.sheet_data  # type: ignore[attr-defined] — typeclass extension
    entry = RosterEntry.objects.filter(character_sheet=sheet).first()
    if entry is not None:
        acquire_clue(entry, clue)

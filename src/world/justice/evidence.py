"""Crime evidence services (#1825) — generate, gather, dispose.

The physical-evidence half of the accusation counter-play. A crime-tagged deed
with a located scene leaves ``CrimeEvidence`` there (``generate_crime_evidence``,
called by ``tag_deed_crimes``). Anyone standing at the scene may **gather** it
(a Skulduggery check that mints a real inventory item); its holder may
**dispose** of it (destroying the trail — deed-knowledge heat is dampened, see
``accrue_for_deed_knowledge``) or pervert it through a frame-job project
(``world.justice.frame_jobs``). All magnitudes PLACEHOLDER.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import transaction

from world.justice.constants import GATHER_EVIDENCE_CHECK_NAME, EvidenceState
from world.justice.models import CrimeEvidence

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.societies.models import LegendEntry

_NOT_AT_SCENE = "You must be standing where the crime happened to do that."
_ALREADY_GATHERED = "There is no evidence left to gather here."
_NOT_HOLDER = "You are not holding that evidence."
_NOT_DISPOSABLE = "That evidence is beyond disposing of now."


class EvidenceError(Exception):
    """An evidence action could not proceed (carries a user-facing message)."""

    def __init__(self, message: str, *, user_message: str | None = None) -> None:
        super().__init__(message)
        self.user_message = user_message or message


@dataclass(frozen=True)
class EvidenceResult:
    """Outcome of a gather/dispose attempt — ``success`` = the check landed."""

    success: bool
    evidence_id: int


def generate_crime_evidence(deed: LegendEntry) -> CrimeEvidence | None:
    """Leave evidence at the scene of a crime-tagged deed (idempotent, one per deed).

    Called by ``tag_deed_crimes``. A deed without a located scene leaves no
    evidence — there is no "there" for it to lie at.
    """
    from world.areas.services import get_room_profile  # noqa: PLC0415

    scene = deed.scene
    if scene is None or scene.location is None:
        return None
    room_profile = get_room_profile(scene.location)
    evidence, _ = CrimeEvidence.objects.get_or_create(deed=deed, room_profile=room_profile)
    return evidence


def _gather_check_type():
    from world.checks.models import CheckType  # noqa: PLC0415

    return CheckType.objects.get(name=GATHER_EVIDENCE_CHECK_NAME)


def _sheet_for(character: ObjectDB):
    return character.sheet_data  # type: ignore[attr-defined] — ObjectDB typeclass extension


def gather_evidence(character: ObjectDB, evidence: CrimeEvidence) -> EvidenceResult:
    """Claim the evidence at the scene — a Skulduggery check that mints a real item.

    Guards: the evidence is still AT_SCENE and the character stands in its room.
    On success the evidence becomes a physical inventory item (holdable, givable,
    stealable); on failure it stays where it lies.
    """
    from world.checks.services import perform_check  # noqa: PLC0415
    from world.items.services.materialize import materialize_item_game_object  # noqa: PLC0415

    if evidence.state != EvidenceState.AT_SCENE:
        raise EvidenceError(_ALREADY_GATHERED)
    if character.location != evidence.room_profile.objectdb:
        raise EvidenceError(_NOT_AT_SCENE)

    result = perform_check(character, _gather_check_type(), target_difficulty=evidence.quality)
    if result.success_level < 0:
        return EvidenceResult(success=False, evidence_id=evidence.pk)

    from world.items.models import ItemInstance  # noqa: PLC0415

    sheet = _sheet_for(character)
    with transaction.atomic():
        instance = ItemInstance.objects.create(
            template=_evidence_template(),
            holder_character_sheet=sheet,
        )
        evidence.item_instance = instance
        evidence.state = EvidenceState.GATHERED
        evidence.save(update_fields=["item_instance", "state"])
        materialize_item_game_object(instance, sheet)
    return EvidenceResult(success=True, evidence_id=evidence.pk)


def dispose_evidence(character: ObjectDB, evidence: CrimeEvidence) -> EvidenceResult:
    """Destroy gathered evidence — a Skulduggery check; success erases the trail.

    Disposal is why the dampener in ``accrue_for_deed_knowledge`` exists: a deed
    whose every evidence row is DISPOSED spreads far less pursuit heat.
    """
    from world.checks.services import perform_check  # noqa: PLC0415

    if evidence.state != EvidenceState.GATHERED:
        raise EvidenceError(_NOT_DISPOSABLE)
    if not _holds_evidence(character, evidence):
        raise EvidenceError(_NOT_HOLDER)

    result = perform_check(character, _gather_check_type(), target_difficulty=evidence.quality)
    if result.success_level < 0:
        return EvidenceResult(success=False, evidence_id=evidence.pk)

    with transaction.atomic():
        _destroy_evidence_item(evidence)
        evidence.state = EvidenceState.DISPOSED
        evidence.save(update_fields=["item_instance", "state"])
    return EvidenceResult(success=True, evidence_id=evidence.pk)


def _holds_evidence(character: ObjectDB, evidence: CrimeEvidence) -> bool:
    instance = evidence.item_instance
    return instance is not None and instance.holder_character_sheet == _sheet_for(character)


def _destroy_evidence_item(evidence: CrimeEvidence) -> None:
    """Delete the evidence's physical item.

    Deleting the game object can cascade to the ItemInstance row (its FK), which
    zeroes the cached instance's pk — guard before the row delete.
    """
    instance = evidence.item_instance
    if instance is None:
        return
    game_object = instance.game_object
    if game_object is not None:
        game_object.delete()
    if instance.pk is not None:
        instance.delete()
    evidence.item_instance = None


def _evidence_template():
    """Lazy ItemTemplate for evidence items (same precedent as currency's templates)."""
    from world.items.models import ItemTemplate  # noqa: PLC0415

    template, _ = ItemTemplate.objects.get_or_create(
        name="Incriminating evidence",
        defaults={
            "description": (
                "PLACEHOLDER Traces of a crime — the kind of thing someone would "
                "rather no one else ever held."
            )
        },
    )
    return template

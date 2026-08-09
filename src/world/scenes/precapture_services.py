"""Pre-scene RP capture services (#3069 sub-item 4).

Before this feature, ``record_interaction`` wrote ``scene=None`` whenever no scene was
active at the room (``interaction_services.py``), and nothing ever attached those rows
once a scene finally started — lead-in RP just vanished from the persisted log
(#3069 audit finding 4).

Tehom's ruling (2026-08-08): on scene start, capture the prior unattached interactions
of the people who are IN the new scene by default; anyone NOT in the new scene needs
explicit consent first; the starter gets truncate/cutoff controls.

Three public surfaces:
  - ``capture_prescene_interactions`` — called once from ``StartSceneAction.execute``'s
    new-scene branch (the single seam telnet and web both reach, post #3074). Attaches
    present authors' unattached poses immediately and opens a ``PrecaptureConsentRequest``
    for everyone else.
  - ``respond_to_precapture_consent`` — accept/decline a pending request. Shared by the
    web ``PrecaptureConsentRequestViewSet`` and the telnet offer-registry handler
    (``PrecaptureConsentOfferHandler``).
  - ``list_precaptured`` / ``truncate_precaptured`` — the starter's cutoff control.

Design note — no ``room`` field on ``Interaction``: organic (no-scene, no-place) grid
RP carries no location reference at all, so "prior interactions in this room" can't be
queried directly. This module approximates it as "prior interactions by someone
CURRENTLY present in this room" (present-account membership at scene-start time),
bounded by ``PRECAPTURE_WINDOW`` so a long-departed account's old poses are never
candidates. This is a deliberate approximation, not a precision guarantee — the
starter's truncate control is the real correctness backstop for anything captured
that shouldn't have been.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

from world.scenes.action_constants import ActionRequestStatus
from world.scenes.models import Interaction, PrecaptureConsentRequest, Scene

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from evennia.objects.models import ObjectDB

# How far back a candidate pre-scene interaction may date from scene start. An
# implementation constant, not a tuning knob — it only keeps the candidate list
# sane; the starter's truncate control (``truncate_precaptured``) is the real
# cutoff mechanism players use to shape what actually stays captured.
PRECAPTURE_WINDOW = timedelta(hours=24)


@dataclass(frozen=True)
class PrecaptureResult:
    """Outcome of one ``capture_prescene_interactions`` call, for the starter's message."""

    attached_count: int
    pending_consent_count: int


def _present_account_ids(room: ObjectDB) -> set[int]:
    """Accounts controlling a present character with a ``CharacterSheet`` (#3069).

    Mirrors the room walk ``scene_admin_services.add_present_as_co_owners`` already
    does for co-ownership — kept as its own walk here (rather than refactored into a
    shared helper) to avoid touching that already-tested function in this PR; the
    duplication is small and the two walks are read-only.
    """
    ids: set[int] = set()
    for obj in room.contents:
        try:
            obj.sheet_data  # noqa: B018 - attribute access guards NPC/prop skip
        except (AttributeError, ObjectDoesNotExist):
            continue
        account = obj.active_account
        if account is not None:
            ids.add(account.pk)
    return ids


def capture_prescene_interactions(scene: Scene, room: ObjectDB) -> PrecaptureResult:
    """Fold prior unattached RP into a just-started scene (#3069 sub-item 4).

    Called once, immediately after ``Scene`` creation, from the new-scene branch of
    ``StartSceneAction.execute`` — never from the mid-scene "join" branch; capture is a
    start-of-scene event only, so a room's first scene of the "session" is the only one
    that ever sweeps for lead-in RP.

    Candidates: ``Interaction`` rows with ``scene=None``, timestamped in
    ``[scene.date_started - PRECAPTURE_WINDOW, scene.date_started)``. A candidate whose
    pinned ``writer_account`` (#1219) controls a character present in ``room`` right now
    attaches immediately (the ruling's ease-of-use default); everyone else gets a
    ``PrecaptureConsentRequest`` instead, and their poses stay unattached — never visible
    in the scene log — until they explicitly accept.

    A candidate with no ``writer_account`` (interactions predating #1219, or ones by an
    account-less NPC-only persona) can't be attributed to any player for a consent ask,
    so it is skipped outright — left unattached forever rather than guessed into either
    bucket.
    """
    present_account_ids = _present_account_ids(room)

    window_start = scene.date_started - PRECAPTURE_WINDOW
    candidates = Interaction.objects.filter(
        scene__isnull=True,
        timestamp__gte=window_start,
        timestamp__lt=scene.date_started,
    ).select_related("writer_account")

    attached_count = 0
    pending_account_ids: set[int] = set()
    for interaction in candidates:
        account_id = interaction.writer_account_id
        if account_id is None:
            continue
        if account_id in present_account_ids:
            interaction.scene = scene
            interaction.save(update_fields=["scene"])
            attached_count += 1
        else:
            pending_account_ids.add(account_id)

    for account_id in pending_account_ids:
        PrecaptureConsentRequest.objects.get_or_create(scene=scene, account_id=account_id)

    return PrecaptureResult(
        attached_count=attached_count,
        pending_consent_count=len(pending_account_ids),
    )


def precapture_candidates_for(request: PrecaptureConsentRequest) -> QuerySet[Interaction]:
    """The exact candidate interactions ``request`` would attach if accepted.

    Reproduces ``capture_prescene_interactions``'s window against the SAME
    ``scene.date_started`` anchor, so this always matches what was actually swept up at
    scene-start time — no separate window needs to be stored on the request row. Used
    both for the accept-time attach query and for previewing "what would be captured"
    to the requester (their own content only, per the #3069 privacy invariant).
    """
    window_start = request.scene.date_started - PRECAPTURE_WINDOW
    return Interaction.objects.filter(
        scene__isnull=True,
        writer_account_id=request.account_id,
        timestamp__gte=window_start,
        timestamp__lt=request.scene.date_started,
    ).order_by("timestamp")


def respond_to_precapture_consent(request: PrecaptureConsentRequest, *, accept: bool) -> int:
    """Resolve a pending precapture consent request. Returns the count attached.

    A no-op (returns 0) if ``request`` isn't PENDING — idempotent against a
    double-submit. On decline, nothing is attached; the candidate interactions simply
    stay unattached (``scene`` stays ``None``), so they were never exposed either way.
    """
    if request.status != ActionRequestStatus.PENDING:
        return 0

    attached = 0
    if accept:
        for interaction in precapture_candidates_for(request):
            interaction.scene = request.scene
            interaction.save(update_fields=["scene"])
            attached += 1

    request.status = ActionRequestStatus.ACCEPTED if accept else ActionRequestStatus.DENIED
    request.responded_at = timezone.now()
    request.save(update_fields=["status", "responded_at"])
    return attached


def list_precaptured(scene: Scene) -> QuerySet[Interaction]:
    """Pre-scene-captured interactions on ``scene``, oldest first.

    "Pre-scene-captured" == attached to this scene but authored before it started
    (``timestamp < scene.date_started``). No separate "was captured" flag is needed:
    ``record_interaction`` always resolves a live pose's scene via
    ``get_active_scene(character.location)`` at write time, so a live pose's timestamp
    is always >= ``scene.date_started`` by construction — only capture (this module)
    ever backdates a pose's ``scene`` FK to before that line, and it never rewrites the
    original ``timestamp``. This invariant is what makes truncation safe: it can only
    ever touch pre-scene-captured rows, never a live in-scene pose.
    """
    return scene.interactions.filter(timestamp__lt=scene.date_started).order_by("timestamp", "pk")


def truncate_precaptured(
    scene: Scene,
    *,
    interaction_id: int | None = None,
    position: int | None = None,
) -> int:
    """Detach every pre-scene-captured interaction before the kept one ("start from here").

    Exactly one of ``interaction_id`` (web: the exact row the starter clicked) or
    ``position`` (telnet: 1-indexed into the same oldest-first ordering ``scene capture``
    just printed) must be given. Detaching sets ``scene=None`` — the interaction reverts
    to plain unattached RP, exactly the state it was in before capture; it is never
    deleted. Returns the count detached (0 if there was nothing to drop).

    Raises ``ValueError`` if there's nothing captured, ``interaction_id`` doesn't belong
    to this scene's captured set, or ``position`` is out of range.
    """
    captured = list(list_precaptured(scene))
    if not captured:
        return 0

    if interaction_id is not None:
        keep_index = next((i for i, ia in enumerate(captured) if ia.pk == interaction_id), None)
        if keep_index is None:
            msg = "That interaction is not a pre-scene-captured pose in this scene."
            raise ValueError(msg)
    elif position is not None:
        if position < 1 or position > len(captured):
            msg = f"Position must be between 1 and {len(captured)}."
            raise ValueError(msg)
        keep_index = position - 1
    else:
        msg = "Specify interaction_id or position."
        raise ValueError(msg)

    to_detach = captured[:keep_index]
    for interaction in to_detach:
        interaction.scene = None
        interaction.save(update_fields=["scene"])
    return len(to_detach)

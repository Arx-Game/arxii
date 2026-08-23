"""Error-capture services (#1164) + staff-contact petitions (#2288).

``run_safely`` is the boundary for optional / best-effort work: run it, and on failure
capture a deduplicated ``SystemErrorReport`` (so a real fault reaches staff with a traceback
instead of vanishing into the logs) and tell the actor — instead of silently swallowing the
error or letting it break the player's action. Replaces the ad-hoc
``try/except Exception: logger.exception`` blocks (#1162/#1163).
"""

from __future__ import annotations

import hashlib
import logging
import traceback as traceback_module
from typing import TYPE_CHECKING, cast

from django.utils import timezone

from world.player_submissions.constants import PetitionCategory, SubmissionStatus
from world.player_submissions.models import Petition, SubmitterStanding, SystemErrorReport

if TYPE_CHECKING:
    from collections.abc import Callable

    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB

    from typeclasses.characters import Character
    from world.player_submissions.models import PlayerReport
    from world.scenes.models import Persona, Scene

logger = logging.getLogger(__name__)

# Shown to a player whose action hit an unexpected error. Functional UI string.
PLAYER_ERROR_MESSAGE = (
    "An unexpected error has occurred. Staff has been notified, but please feel free to "
    "leave a bug report under the account menu."
)


def run_safely(label: str, fn: Callable[[], object], *, actor: ObjectDB | None = None) -> object:
    """Run an optional / best-effort callable; on failure capture + notify, never raise.

    Returns ``fn()``'s result, or ``None`` if it raised. A raised exception is captured as a
    deduplicated ``SystemErrorReport`` (visible to staff) and, when ``actor`` is given, the
    generic error line is surfaced to that player — so the failure is neither swallowed
    silently nor allowed to break the player's primary action.
    """
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 — this IS the central catch-all boundary, by design
        report_error(exc, label=label, actor=actor)
        if actor is not None:
            _notify_actor(actor)
        return None


def report_error(exc: BaseException, *, label: str, actor: ObjectDB | None = None) -> None:
    """Capture an exception as a deduplicated ``SystemErrorReport`` + a structured log.

    Must never raise — it is the last line of defense. Dedup is by a signature over the
    exception type and the deepest in-app frame, so repeats increment a count instead of
    spawning rows.
    """
    logger.exception("Captured error in %s", label)
    try:
        tb_text = "".join(traceback_module.format_exception(type(exc), exc, exc.__traceback__))
        signature = _signature(exc, label)
        report, created = SystemErrorReport.objects.get_or_create(
            signature=signature,
            defaults={
                "label": label[:200],
                "exception_type": type(exc).__name__[:200],
                "message": str(exc)[:2000],
                "traceback": tb_text,
                "actor_persona": _persona_for(actor),
            },
        )
        if not created:
            # Read-modify-write via save() (not F()+update()) so the cached
            # SharedMemoryModel instance stays in sync — an F-expression .update()
            # leaves later reads of this row stale (idmapper).
            report.occurrence_count += 1
            report.last_seen = timezone.now()
            report.save(update_fields=["occurrence_count", "last_seen"])
    except Exception:
        logger.exception("Failed to record SystemErrorReport for %s", label)


def _notify_actor(actor: ObjectDB) -> None:
    """Push the generic error line to the player; never raise."""
    try:
        actor.msg(PLAYER_ERROR_MESSAGE)
    except Exception:
        logger.exception("Failed to notify actor of error")


def _signature(exc: BaseException, label: str) -> str:
    """Dedup hash: exception type + the deepest frame inside our codebase (else the label)."""
    frame_id = label
    tb = exc.__traceback__
    while tb is not None:
        if "/src/" in tb.tb_frame.f_code.co_filename:
            frame_id = f"{tb.tb_frame.f_code.co_filename.split('/src/')[-1]}:{tb.tb_lineno}"
        tb = tb.tb_next
    return hashlib.sha256(f"{type(exc).__name__}|{frame_id}".encode()).hexdigest()[:64]


def _persona_for(actor: ObjectDB | None) -> object | None:
    """Best-effort presented persona for the actor, or ``None``.

    Returns ``None`` unless the resolver yields a genuine ``Persona`` — the FK assignment
    is otherwise the one thing that can make capture itself fail, so it must never trust
    a non-``Persona`` (e.g. a test mock) through to ``actor_persona``.
    """
    if actor is None:
        return None
    try:
        from world.scenes.models import Persona  # noqa: PLC0415
        from world.scenes.services import persona_for_character  # noqa: PLC0415

        persona = persona_for_character(cast("Character", actor))
    except Exception:  # noqa: BLE001 — persona resolution is best-effort context only
        return None
    return persona if isinstance(persona, Persona) else None


class StaffContactError(Exception):
    """A staff-contact rule was violated. Carries a safe user message."""

    def __init__(self, msg: str, *, user_message: str) -> None:
        super().__init__(msg)
        self.user_message = user_message


# Per-category required references — structure over prose (#2288).
_CATEGORY_REQUIRES = {
    PetitionCategory.UNFAIR_DEATH: ("subject_character",),
    PetitionCategory.SCENE_CONDUCT_EMERGENCY: ("scene",),
    PetitionCategory.STUCK_UNPLAYABLE: ("subject_character",),
    PetitionCategory.OTHER_EMERGENCY: (),
}


def submit_petition(
    account: AccountDB,
    *,
    category: str,
    description: str,
    scene: Scene | None = None,
    subject_character: ObjectDB | None = None,
) -> Petition:
    """File the one open petition an account may hold — emergency-only.

    The one-open rule is the structural rate-limit that keeps "emergency"
    legible; per-category required references keep it specific.
    """
    if Petition.objects.filter(account=account, status=SubmissionStatus.OPEN).exists():
        msg = f"account {account.pk} already holds an open petition"
        raise StaffContactError(
            msg,
            user_message="You already have an open petition — one at a time.",
        )
    refs = {"scene": scene, "subject_character": subject_character}
    for required in _CATEGORY_REQUIRES.get(category, ()):
        if refs.get(required) is None:
            msg = f"petition category {category} requires {required}"
            raise StaffContactError(
                msg,
                user_message="That kind of petition needs the thing it is about attached.",
            )
    return Petition.objects.create(
        account=account,
        category=category,
        description=description[:1000],
        scene=scene,
        subject_character=(subject_character.sheet_data if subject_character is not None else None),
    )


def standing_for(account: AccountDB) -> SubmitterStanding:
    standing, _ = SubmitterStanding.objects.get_or_create(account=account)
    return standing


def record_resolution(account: AccountDB, status: str) -> SubmitterStanding:
    """Stamp the submitter's track record when staff resolve their submission."""
    standing = standing_for(account)
    if status == SubmissionStatus.REVIEWED:
        standing.actioned_count += 1
        standing.save(update_fields=["actioned_count"])
    elif status == SubmissionStatus.DISMISSED:
        standing.dismissed_count += 1
        standing.save(update_fields=["dismissed_count"])
    return standing


def resolve_petition(petition: Petition, *, status: str, staff_notes: str = "") -> Petition:
    """Staff close a petition; the outcome feeds the track record."""
    if petition.status != SubmissionStatus.OPEN:
        msg = f"petition {petition.pk} is not open"
        raise StaffContactError(msg, user_message="That petition is already resolved.")
    petition.status = status
    petition.staff_notes = staff_notes
    petition.resolved_at = timezone.now()
    petition.save(update_fields=["status", "staff_notes", "resolved_at"])
    record_resolution(petition.account, status)
    return petition


def set_ignored(account: AccountDB, *, ignored: bool) -> SubmitterStanding:
    """The perma-ignore bit: submissions persist but never surface. Silent."""
    standing = standing_for(account)
    standing.is_ignored = ignored
    if ignored:
        standing.ignored_count += 1
    standing.save(update_fields=["is_ignored", "ignored_count"])
    return standing


def kudos_total_for(account: AccountDB) -> int:
    """The sender's kudos total — the staff inbox's sort key (#2288)."""
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    try:
        return account.kudos_points_data.total_earned
    except (AttributeError, ObjectDoesNotExist):
        return 0


def sender_context(account: AccountDB) -> dict:
    """Kudos + standing columns shown beside every submission."""
    standing = standing_for(account)
    return {
        "kudos_total": kudos_total_for(account),
        "actioned_count": standing.actioned_count,
        "dismissed_count": standing.dismissed_count,
        "is_ignored": standing.is_ignored,
    }


class HiddenPresenceReportError(Exception):
    """No reportable hidden presence at the reporter's location. Safe user message."""

    def __init__(self, msg: str, *, user_message: str) -> None:
        super().__init__(msg)
        self.user_message = user_message


def report_hidden_presence(
    *,
    reporter_account: AccountDB,
    reporter_persona: Persona,
    behavior_description: str,
    category: str,
) -> list[PlayerReport]:
    """File PlayerReports against the concealed occupants of the reporter's room (#3288).

    The "hidden identity, disclosed presence" ruling's enforcement half: anyone can
    report an unseen presence without learning who it is. Identity resolution happens
    entirely server-side — one PlayerReport per concealed occupant currently in the
    reporter's room, anchored on that occupant's ACTIVE persona (never surfaced to
    the reporter; staff reads it from the submissions queue).

    Raises HiddenPresenceReportError when the reporter has no location, no concealed
    occupant is present, or a concealed occupant can't be resolved to a persona.
    """
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415
    from evennia.objects.models import ObjectDB  # noqa: PLC0415

    from world.conditions.models import ConditionInstance  # noqa: PLC0415
    from world.player_submissions.models import PlayerReport  # noqa: PLC0415
    from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    location_id = (
        ObjectDB.objects.filter(pk=reporter_persona.character_sheet_id)
        .values_list("db_location_id", flat=True)
        .first()
    )
    if location_id is None:
        msg = "reporter has no location"
        raise HiddenPresenceReportError(msg, user_message="You aren't anywhere reportable.")

    occupant_ids = list(
        ObjectDB.objects.filter(db_location_id=location_id).values_list("pk", flat=True)
    )
    concealed_ids = set(
        ConditionInstance.objects.filter(
            target_id__in=occupant_ids,
            condition__category__conceals_from_perception=True,
            is_suppressed=False,
            resolved_at__isnull=True,
        ).values_list("target_id", flat=True)
    )
    concealed_ids.discard(reporter_persona.character_sheet_id)
    if not concealed_ids:
        msg = "no concealed occupant present"
        raise HiddenPresenceReportError(
            msg, user_message="There is no hidden presence here to report."
        )

    location = ObjectDB.objects.filter(pk=location_id).first()
    scene = get_active_scene(location) if location is not None else None

    reports: list[PlayerReport] = []
    for concealed in ObjectDB.objects.filter(pk__in=concealed_ids):
        try:
            sheet = concealed.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            continue
        reported_persona = active_persona_for_sheet(sheet)
        if reported_persona is None or reported_persona.pk == reporter_persona.pk:
            continue
        try:
            entry = sheet.roster_entry
            tenure = entry.current_tenure
        except ObjectDoesNotExist:
            tenure = None
        if tenure is None:
            continue
        reports.append(
            PlayerReport.objects.create(
                reporter_account=reporter_account,
                reported_account_id=tenure.player_data.account_id,
                reporter_persona=reporter_persona,
                reported_persona=reported_persona,
                behavior_description=behavior_description,
                category=category,
                scene=scene,
                location_id=location_id,
            )
        )
    if not reports:
        msg = "concealed occupants unresolvable to played personas"
        raise HiddenPresenceReportError(
            msg, user_message="There is no hidden presence here to report."
        )
    return reports

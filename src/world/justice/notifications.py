"""Justice notifications (#2378 Task 6) — verdict deliveries + brig visitation advert.

:func:`notify_verdict` fans out a NarrativeMessage (category ``justice``) to the case's
reachable audience: every :class:`~world.justice.models.ExculpatoryEvidence` submitter's
sheet on the case, plus the accused's own sheet. Called (via the best-effort
:func:`notify_verdict_safely` wrapper) from the end of both
:func:`world.justice.pipeline.initiate_trial` paths (acquittal and sentence, ``reason``
defaults to ``"verdict"``) and from :func:`world.justice.sentences.sentence_sweep_tick`
when a terminal sentence is carried out (``reason="carried_out"``) or voided
(``reason="voided"``). The three reasons produce DISTINCT body text (fix round 1,
#2378 Task 6 review) — a voided/rescued terminal must never re-send sentence-affirming
copy ("ruled: guilty - sentence: execution") to a recipient whose sentence was in fact
NOT carried out.

NOTE — accuser routing gap: ``AccusationCrimeClaim`` keys on ``Secret``, not
``JusticeCase`` — there is no queryable path from a case back to the claim(s) that
seeded it (VERIFIED ABSENT, #2378 Task 6). The original accuser(s) are therefore NOT
reachable from a case and are NOT part of this audience; exculpatory submitters are the
only case-connected participants besides the accused. Do not build a claims join here —
if accuser routing becomes a requirement, it needs its own case-carrying link, not a
reach-through ``AccusationCrimeClaim`` query.

:func:`notify_brig_visitation` advertises a served BRIG_TERM sentence to the accused's
active friends via their account (OOC), mirroring
:func:`world.scenes.friend_services.notify_friends_of_status`'s inbound-friend
enumeration. Called from :func:`world.justice.sentences.schedule_sentence`'s BRIG_TERM
branch.

``notify_verdict``/``notify_brig_visitation`` are called directly (never deferred to
``transaction.on_commit``). :func:`notify_verdict_safely` is the ONE shared best-effort
wrapper for ``notify_verdict`` — pipeline.py and sentences.py both call it rather than
each defining their own (fix round 1: they previously duplicated an identical
``_notify_verdict`` wrapper) — logging and swallowing any failure, mirroring
``world.societies.renown.fire_renown_award``'s notify guard: a notification failure
must never break the trial/sentence path. ``notify_brig_visitation`` keeps its own
best-effort wrapper in ``sentences.py`` (``_notify_brig_visitation``) since it has
exactly one call site.
"""

from __future__ import annotations

import logging

from world.justice.constants import SentenceKind, Verdict, VerdictNotifyReason
from world.justice.models import JusticeCase

logger = logging.getLogger(__name__)


def notify_verdict(case: JusticeCase, *, reason: str = VerdictNotifyReason.VERDICT) -> int:
    """Deliver a verdict/sentence-outcome notice to the case's reachable audience (#2378).

    Recipients (CharacterSheets, deduped by pk): every ExculpatoryEvidence submitter's
    sheet on this case, plus the accused's own sheet. See the module docstring for why
    accusers are out of scope. Returns the recipient count.

    ``reason`` selects DISTINCT, non-reaffirming body text (fix round 1):

    - ``"verdict"`` (default, trial-time): announces the verdict, plus the sentence kind
      when one was handed down.
    - ``"carried_out"`` (terminal sentence served by the sweep): announces only that the
      sentence has been carried out — no verdict/sentence-kind repeat.
    - ``"voided"`` (terminal sentence rescued/pardoned before the sweep could act):
      announces only that the sentence was NOT carried out — never repeats the earlier
      sentence-affirming text.
    """
    if reason not in VerdictNotifyReason.values:
        msg = f"unknown notify_verdict reason: {reason!r}"
        raise ValueError(msg)

    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415
    from world.narrative.services import send_narrative_message  # noqa: PLC0415

    sheets_by_pk = {}
    accused_sheet = case.persona.character_sheet
    if accused_sheet is not None:
        sheets_by_pk[accused_sheet.pk] = accused_sheet

    submissions = case.exculpatory_evidence.select_related("submitter_persona__character_sheet")
    for evidence in submissions:
        sheet = evidence.submitter_persona.character_sheet
        if sheet is not None:
            sheets_by_pk[sheet.pk] = sheet

    if not sheets_by_pk:
        return 0

    body = _verdict_body(case, reason)

    send_narrative_message(
        recipients=list(sheets_by_pk.values()),
        body=body,
        category=NarrativeCategory.JUSTICE,
    )
    return len(sheets_by_pk)


def _verdict_body(case: JusticeCase, reason: str) -> str:
    """The reason-specific PLACEHOLDER body — never reaffirms a voided sentence."""
    if reason == VerdictNotifyReason.CARRIED_OUT:
        return (
            f"PLACEHOLDER: The magistrates of {case.area.name} report the sentence "
            "has been carried out."
        )
    if reason == VerdictNotifyReason.VOIDED:
        return (
            f"PLACEHOLDER: The magistrates of {case.area.name} report the sentence "
            "was not carried out."
        )

    verdict_label = Verdict(case.verdict).label
    body = f"PLACEHOLDER: The magistrates of {case.area.name} have ruled: {verdict_label}"
    if case.sentence_kind:
        body += f" - sentence: {SentenceKind(case.sentence_kind).label}"
    return body


def notify_verdict_safely(case: JusticeCase, *, reason: str = VerdictNotifyReason.VERDICT) -> None:
    """Best-effort ``notify_verdict`` — never breaks the trial/sentence-sweep path.

    Shared by :func:`world.justice.pipeline.initiate_trial` (default ``reason``) and
    :func:`world.justice.sentences._sweep_terminals`'s carry-out/void branches (fix
    round 1: the two apps previously duplicated this wrapper). Mirrors
    ``world.societies.renown.fire_renown_award``'s notify guard: the notification is a
    UX nicety, the verdict/sentence write is the source of truth.
    """
    try:
        notify_verdict(case, reason=reason)
    except Exception:  # best-effort notify; never break the trial/sweep path
        logger.exception("justice.notify_verdict failed for case %s (reason=%s)", case.pk, reason)


def notify_brig_visitation(case: JusticeCase) -> int:
    """Advertise a served BRIG_TERM sentence to the accused's active friends (#2378 Task 6).

    Mirrors ``notify_friends_of_status``'s inbound-friend enumeration: RosterTenure rows
    that have friended the accused's current tenure and are still active
    (``end_date__isnull=True``), deduped by account pk. Sends an OOC line via
    ``account.msg`` — never an IC push. Returns the count of accounts notified (0 when
    the accused has no character/tenure to visit, e.g. a bodiless persona or a
    test/NPC sheet outside the roster flow).
    """
    from world.roster.models import RosterTenure  # noqa: PLC0415

    sheet = case.persona.character_sheet
    entry = sheet.roster_entry_or_none if sheet is not None else None
    tenure = entry.current_tenure if entry is not None else None
    if tenure is None:
        return 0

    message = (
        f"PLACEHOLDER (OOC): {case.persona.name} is imprisoned in "
        f"{case.area.name} and can be visited."
    )
    friender_tenures = (
        RosterTenure.objects.filter(friendships_made__friend_tenure=tenure, end_date__isnull=True)
        .select_related("player_data__account")
        .distinct()
    )
    seen: set[int] = set()
    for friender in friender_tenures:
        account = friender.player_data.account
        if account is None or account.pk in seen:
            continue
        seen.add(account.pk)
        account.msg(message)
    return len(seen)

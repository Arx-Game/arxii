"""The GM prompt queue: route narratable events to GMs, or deliver as today (#4101).

``route_narratable_event`` is the one seam every event source calls. It asks
``prompt_recipients`` which GMs want this kind; with any, it records one PENDING
GMPrompt per GM and pushes it live; with none, it runs the caller's
``deliver_unprompted`` (exactly what the source did before #4101).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING
import uuid

from django.db import transaction

from world.gm.constants import (
    NARRATION_PROMPT_KINDS,
    PROMPT_GROUP_FOR_KIND,
    GMPromptStatus,
)
from world.gm.exceptions import GMPromptError
from world.gm.models import GMPrompt, GMPromptFilter
from world.scenes.interaction_services import (
    broadcast_scene_emit,
    narrate_privately,
    non_web_sessions,
)
from world.scenes.models import Persona

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.gm.types import NarratableEvent
    from world.scenes.models import Scene

_MSG_NOT_NARRATION = "That prompt is not one you narrate."
_MSG_RESOLVED = "That prompt has already been dealt with."


def scene_gm_accounts(scene: Scene | None) -> list[AccountDB]:
    """Accounts currently GMing ``scene``: ``is_gm`` participations not yet left."""
    if scene is None:
        return []
    return [
        part.account for part in scene.participations_cached if part.is_gm and part.left_at is None
    ]


def _muted_account_ids(account_ids: list[int], kind: str) -> set[int]:
    return set(
        GMPromptFilter.objects.filter(
            account_id__in=account_ids, group=PROMPT_GROUP_FOR_KIND[kind], enabled=False
        ).values_list("account_id", flat=True)
    )


def prompts_enabled(account: AccountDB, kind: str) -> bool:
    """True unless ``account`` muted the group ``kind`` belongs to."""
    return account.pk not in _muted_account_ids([account.pk], kind)


def prompt_recipients(
    scene: Scene | None, kind: str, *, candidates: list[AccountDB] | None = None
) -> list[AccountDB]:
    """The GMs a ``kind`` event should prompt: candidates (default: scene GMs) minus muted."""
    pool = scene_gm_accounts(scene) if candidates is None else candidates
    if not pool:
        return []
    muted = _muted_account_ids([a.pk for a in pool], kind)
    return [a for a in pool if a.pk not in muted]


def route_narratable_event(
    event: NarratableEvent,
    *,
    deliver_unprompted: Callable[[], None] | None = None,
    candidates: list[AccountDB] | None = None,
) -> list[GMPrompt]:
    """Prompt each opted-in GM, or deliver the authored text as today (spec decision 7).

    Every created prompt shares one ``event_group`` (#4101 fix round 1) -- they are
    siblings of the SAME event, one copy per addressed GM. ``dismiss_gm_prompt``
    groups on this field to release the event's authored defaults exactly once,
    when the last sibling leaves PENDING, rather than once per GM.
    """
    recipients = prompt_recipients(event.scene, event.kind, candidates=candidates)
    if not recipients:
        if deliver_unprompted is not None:
            deliver_unprompted()
        return []
    event_group = uuid.uuid4()
    prompts = [
        GMPrompt.objects.create(
            kind=event.kind,
            event_group=event_group,
            scene=event.scene,
            character_sheet=event.character_sheet,
            addressed_to=account,
            room_text=event.room_text,
            private_text=event.private_text,
            prepared_for_character=event.prepared_for_character,
            technique=event.technique,
            stake_outcome=event.stake_outcome,
        )
        for account in recipients
    ]
    for prompt in prompts:
        transaction.on_commit(lambda p=prompt: notify_gm_prompt(p))
    return prompts


def prompt_subject_name(prompt: GMPrompt) -> str:
    """The name the GM sees for who this concerns (primary persona), or ''."""
    sheet = prompt.character_sheet
    if sheet is None:
        return ""
    try:
        return sheet.primary_persona.name
    except Persona.DoesNotExist:
        return ""


def _telnet_line(prompt: GMPrompt) -> str:
    subject = prompt_subject_name(prompt)
    head = f"GM prompt [{prompt.pk}] {prompt.get_kind_display()}"
    head = f"{head}: {subject}." if subject else f"{head}."
    return (
        f"{head} emit/prompt {prompt.pk} <text> | pemit/prompt {prompt.pk} <names>=<text>"
        f" | gm prompt send {prompt.pk} | gm prompt dismiss {prompt.pk}"
    )


def notify_gm_prompt(prompt: GMPrompt) -> None:
    """Push a new prompt to its GM: a ``gm_prompt`` frame for web, one line for telnet."""
    account = prompt.addressed_to
    if account is None:
        return
    account.msg(
        gm_prompt=((), {"prompt_id": prompt.pk, "scene_id": prompt.scene_id, "kind": prompt.kind})
    )
    telnet = non_web_sessions(account)
    if telnet:
        account.msg(_telnet_line(prompt), session=telnet)


def release_prompt_defaults(prompt: GMPrompt) -> None:
    """Deliver a prompt's authored defaults the unprompted way (no GM narrated it).

    Releases against the prompt's OWN scene (``prompt.scene``), never one
    re-derived from the character's current location (#4101 fix round 1) -- a
    character who moved rooms between the prompt's creation and its release
    must still get the room/private line attributed to the scene the event
    actually happened in.
    """
    sheet = prompt.character_sheet
    if sheet is None:
        return
    character = sheet.character
    if prompt.room_text.strip():
        broadcast_scene_emit(character, prompt.room_text, scene=prompt.scene)
    if prompt.private_text.strip():
        narrate_privately(character, prompt.private_text, scene=prompt.scene)


def _resolve_narration_prompt(
    prompt: GMPrompt, *, new_status: str, resolver: AccountDB | None
) -> GMPrompt:
    """Resolve one narration prompt and release its event's defaults exactly once.

    Siblings routed from the same event (shared ``event_group``) are locked for
    the duration of the transaction via ``select_for_update`` -- a dismiss racing
    scene end's own ``expire_scene_prompts`` sweep, or two tabs dismissing the
    same prompt, serializes against this instead of double-sending (#4101 fix
    round 1). The event's authored defaults release only once every sibling has
    left PENDING, and only when none of them ended up NARRATED -- a GM's own
    narration of the event replaces the default, it doesn't compete with it.
    """
    with transaction.atomic():
        siblings = list(GMPrompt.objects.select_for_update().filter(event_group=prompt.event_group))
        this = next(s for s in siblings if s.pk == prompt.pk)
        if this.status != GMPromptStatus.PENDING:
            raise GMPromptError(_MSG_RESOLVED)
        this.status = new_status
        this.resolved_by = resolver
        this.save(update_fields=["status", "resolved_by"])
        still_pending = any(s.status == GMPromptStatus.PENDING for s in siblings if s.pk != this.pk)
        if still_pending:
            return this
        if not any(s.status == GMPromptStatus.NARRATED for s in siblings):
            release_prompt_defaults(this)
        return this


def dismiss_gm_prompt(prompt: GMPrompt, *, resolver: AccountDB | None) -> GMPrompt:
    """Close a PENDING narration prompt.

    Its event's authored defaults go out exactly once -- when every sibling GM's
    own copy of the event has also left PENDING with no narration among them
    (see ``_resolve_narration_prompt``) -- never once per dismissing GM.

    Authorization (who may dismiss this prompt) is the CALLER's job -- this
    function only enforces that the prompt is a narration kind and still open.
    Task 9's action is where the real GM/addressee gate lives.
    """
    if prompt.kind not in NARRATION_PROMPT_KINDS:
        raise GMPromptError(_MSG_NOT_NARRATION)
    return _resolve_narration_prompt(prompt, new_status=GMPromptStatus.DISMISSED, resolver=resolver)


def expire_scene_prompts(scene: Scene) -> int:
    """Scene finished: dismiss its pending narration prompts so no default is lost.

    Tolerates a prompt a concurrent dismiss already resolved out from under this
    sweep (``GMPromptError`` from ``_resolve_narration_prompt``'s fresh re-check
    under lock) -- that race is a lost race, not a failure to report.
    """
    pending = list(
        GMPrompt.objects.filter(
            scene=scene, status=GMPromptStatus.PENDING, kind__in=NARRATION_PROMPT_KINDS
        ).select_related("character_sheet__character")
    )
    expired = 0
    for prompt in pending:
        try:
            dismiss_gm_prompt(prompt, resolver=None)
        except GMPromptError:
            continue
        expired += 1
    return expired


__all__ = [
    "dismiss_gm_prompt",
    "expire_scene_prompts",
    "notify_gm_prompt",
    "prompt_recipients",
    "prompt_subject_name",
    "prompts_enabled",
    "release_prompt_defaults",
    "route_narratable_event",
    "scene_gm_accounts",
]

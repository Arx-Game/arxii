"""The GM prompt queue: route narratable events to GMs, or deliver as today (#4101).

``route_narratable_event`` is the one seam every event source calls. It asks
``prompt_recipients`` which GMs want this kind; with any, it records one PENDING
GMPrompt per GM and pushes it live; with none, it runs the caller's
``deliver_unprompted`` (exactly what the source did before #4101).
"""

from __future__ import annotations

from collections.abc import Callable
import contextlib
from typing import TYPE_CHECKING
import uuid

from django.db import DatabaseError, transaction

from world.gm.constants import (
    NARRATION_PROMPT_KINDS,
    PROMPT_GROUP_FOR_KIND,
    GMPromptStatus,
)
from world.gm.exceptions import GMPromptError
from world.gm.models import GMPrompt, GMPromptFilter, GMPromptNarration
from world.scenes.interaction_services import (
    broadcast_scene_emit,
    get_active_scene,
    narrate_privately,
    non_web_sessions,
)
from world.scenes.models import Persona

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB

    from world.gm.types import NarratableEvent
    from world.scenes.models import Interaction, Scene
    from world.scenes.types import NarratedEventPayload

_MSG_NOT_NARRATION = "That prompt is not one you narrate."
_MSG_RESOLVED = "That prompt has already been dealt with."
_MSG_NO_PROMPT = "There is no such GM prompt."
_MSG_NOT_YOURS = "That prompt is not addressed to you."
_MSG_WRONG_SCENE = "Narrate that prompt from the scene it happened in."
_NARRATABLE_STATUSES = (GMPromptStatus.PENDING, GMPromptStatus.NARRATED)


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


def narrated_event_payload(interaction: Interaction) -> NarratedEventPayload | None:
    """The "part of X's Crossing" tag for a row, from the PEEKED link cache only (#4101).

    Reads ``interaction.__dict__`` directly rather than the
    ``cached_prompt_narrations`` property -- a cache miss there would run its
    own query, which this seam must never do (it runs on every live push).
    ``link_prompt_narration`` seeds that same cache key synchronously on the
    just-created row, so the live push always finds it already populated.
    """
    links = interaction.__dict__.get("cached_prompt_narrations") or []
    if not links:
        return None
    prompt = links[0].prompt
    sheet = prompt.character_sheet
    subject_persona_id = None
    if sheet is not None:
        try:
            subject_persona_id = sheet.primary_persona.pk
        except Persona.DoesNotExist:
            subject_persona_id = None
    return {
        "prompt_id": prompt.pk,
        "kind": prompt.kind,
        "kind_label": prompt.get_kind_display(),
        "subject_name": prompt_subject_name(prompt),
        "subject_persona_id": subject_persona_id,
    }


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


def narration_prompt_for(
    account: AccountDB | None,
    *,
    location: ObjectDB | None,  # noqa: OBJECTDB_PARAM - any room the GM stands in
    prompt_id: object,
) -> GMPrompt:
    """The prompt ``account`` may narrate right now from ``location``, or GMPromptError.

    Staff bypass the addressed-to gate, like every other GM tool (#4101 Task 3
    controller ruling) -- everything else (kind, status, scene binding) applies
    the same to staff and the addressed GM alike. ``_NARRATABLE_STATUSES``
    includes NARRATED, not just PENDING: repeat narrations are allowed, NO CAP
    BY DESIGN (#4101 fix round 1 ruling) -- a GM may add several lines to one
    prompt (a room line, then one or more private lines to different
    recipients), and ``EmitAction``/``PemitAction`` each resolve this
    independently before linking their own Interaction.
    """
    from core_management.permissions import is_staff_observer  # noqa: PLC0415

    try:
        prompt = GMPrompt.objects.select_related("character_sheet").get(pk=int(prompt_id))
    except (GMPrompt.DoesNotExist, TypeError, ValueError):
        raise GMPromptError(_MSG_NO_PROMPT) from None
    if prompt.kind not in NARRATION_PROMPT_KINDS:
        raise GMPromptError(_MSG_NOT_NARRATION)
    if not is_staff_observer(account) and (account is None or prompt.addressed_to_id != account.pk):
        raise GMPromptError(_MSG_NOT_YOURS)
    if prompt.status not in _NARRATABLE_STATUSES:
        raise GMPromptError(_MSG_RESOLVED)
    if prompt.scene_id is not None:
        here = get_active_scene(location)
        if here is None or here.pk != prompt.scene_id:
            raise GMPromptError(_MSG_WRONG_SCENE)
    return prompt


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

    The still-PENDING/NARRATED re-check above reads ``siblings`` -- the
    ``select_for_update()`` result, i.e. the identity map's live Python objects,
    not a fresh row-by-row re-query of the database. That is correct *because*
    every status change to a GMPrompt goes through this same function under the
    same lock: no writer can mutate a sibling's status without first taking this
    exact lock, so the in-memory objects the lock hands back are never stale
    relative to each other (#4101 fix round 2).

    ``release_prompt_defaults`` is deferred to ``transaction.on_commit`` (#4101
    fix round 2) -- GMPrompt is idmapper-cached, so a Python-level attribute
    mutation (``this.status = new_status``) is not automatically undone by a
    database rollback the way the DB row is. Running delivery (which can raise)
    *inside* this atomic block risked a delivery failure rolling back the DB
    write while leaving the cached instance's ``status`` stuck at
    DISMISSED/NARRATED in memory -- from then on every future dismiss attempt on
    that same cached object would see a non-PENDING status and refuse
    (``_MSG_RESOLVED``), and ``expire_scene_prompts`` would never find it PENDING
    again either, silently losing the release forever. Deferring to
    ``transaction.on_commit`` means delivery only ever runs after the status
    change has safely committed, so a failed send can no longer corrupt prompt
    state -- it can only fail to deliver.

    Separately, a database-level failure writing the status change (e.g. a
    constraint violation on ``save()``) still mutated ``this`` in Python
    first, so the ``except`` below puts ``status``/``resolved_by`` back
    before re-raising, keeping the cached instance consistent with the
    database row the transaction rollback restores.
    """
    with transaction.atomic():
        siblings = list(GMPrompt.objects.select_for_update().filter(event_group=prompt.event_group))
        this = next(s for s in siblings if s.pk == prompt.pk)
        if this.status != GMPromptStatus.PENDING:
            raise GMPromptError(_MSG_RESOLVED)
        previous_status, previous_resolver = this.status, this.resolved_by
        this.status = new_status
        this.resolved_by = resolver
        try:
            this.save(update_fields=["status", "resolved_by"])
        except DatabaseError:
            this.status = previous_status
            this.resolved_by = previous_resolver
            raise
        still_pending = any(s.status == GMPromptStatus.PENDING for s in siblings if s.pk != this.pk)
        if not still_pending and not any(s.status == GMPromptStatus.NARRATED for s in siblings):
            transaction.on_commit(lambda p=this: release_prompt_defaults(p))
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


def link_prompt_narration(prompt: GMPrompt, interaction: Interaction) -> GMPromptNarration:
    """Record ``interaction`` as narrating ``prompt`` (#4101 Task 3).

    Repeat narrations are allowed, NO CAP BY DESIGN (fix round 1 ruling): a GM
    may send several lines for one event (a room line, then one or more
    private lines to different recipients); each is its own Interaction, each
    gets its own ``GMPromptNarration`` row linked back to the same prompt.

    The FIRST narration of a still-PENDING prompt resolves it to NARRATED
    through ``_resolve_narration_prompt``, under the same per-event lock
    ``dismiss_gm_prompt``/``expire_scene_prompts`` use: the narrating sibling
    then counts as "narrated" in that function's own re-check, so the event's
    authored defaults never release once this row exists. A LATER narration
    of an already-NARRATED prompt is a plain link with no status change --
    ``narration_prompt_for`` already let it through via
    ``_NARRATABLE_STATUSES``.

    ``prompt.status`` above is read before the lock ``_resolve_narration_prompt``
    takes, so it can be stale (fix round 1): a sibling dismiss, scene-end
    expiry, or a second concurrent narration of the SAME prompt can resolve it
    out from under this check between the read and the lock. When that
    happens, ``_resolve_narration_prompt`` raises ``GMPromptError`` for a
    prompt it finds already resolved under the lock -- a LOST RACE, not a
    failure. The narration was already sent (the ``Interaction`` row exists),
    so it must still be delivered: the exception is swallowed here, and the
    link row stands regardless of which branch ran. The link-row write and the
    resolve attempt share one ``transaction.atomic()`` block so they commit
    together (or roll back together on a genuine ``DatabaseError``, which
    ``_resolve_narration_prompt`` still re-raises past this function) --
    delivery (the caller's ``record_interaction`` -> ``push_interaction``)
    always runs after this function returns, following Task 2's
    ``on_commit`` pattern for ``release_prompt_defaults``.
    """
    with transaction.atomic():
        link = GMPromptNarration.objects.create(
            prompt=prompt, interaction=interaction, interaction_timestamp=interaction.timestamp
        )
        # Seed (never read back) the cache so push_interaction's peek finds it with no query.
        interaction.cached_prompt_narrations = [link]
        if prompt.status == GMPromptStatus.PENDING:
            with contextlib.suppress(GMPromptError):
                _resolve_narration_prompt(
                    prompt, new_status=GMPromptStatus.NARRATED, resolver=prompt.addressed_to
                )
    return link


def expire_scene_prompts(scene: Scene) -> int:
    """Scene finished: dismiss its pending narration prompts so no default is lost.

    Tolerates a prompt a concurrent dismiss already resolved out from under this
    sweep (``GMPromptError`` from ``_resolve_narration_prompt``'s identity-map
    re-check under lock -- see that function's docstring for why reading the
    cache there is correct) -- that race is a lost race, not a failure to
    report.
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
    "link_prompt_narration",
    "narrated_event_payload",
    "narration_prompt_for",
    "notify_gm_prompt",
    "prompt_recipients",
    "prompt_subject_name",
    "prompts_enabled",
    "release_prompt_defaults",
    "route_narratable_event",
    "scene_gm_accounts",
]

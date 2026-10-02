"""The GM prompt queue: route narratable events to GMs, or deliver as today (#4101).

``route_narratable_event`` is the one seam every event source calls. It asks
``prompt_recipients`` which GMs want this kind (minus the event's own subject,
see below); with any, it records one PENDING GMPrompt per GM and pushes it
live; with none, it returns an empty list and leaves delivery to the caller
(#4101 fix round 2 -- see the function's own docstring for why).
"""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING
import uuid

from django.db import DatabaseError, transaction
from django.db.models import Exists, OuterRef, Q, QuerySet

from world.gm.constants import (
    NARRATION_PROMPT_KINDS,
    PROMPT_GROUP_FOR_KIND,
    GMPromptKind,
    GMPromptStatus,
)
from world.gm.exceptions import GMPromptError
from world.gm.models import GMPrompt, GMPromptFilter, GMPromptNarration
from world.roster.selectors import get_account_for_character
from world.scenes.constants import InteractionMode
from world.scenes.interaction_services import (
    broadcast_scene_emit,
    get_active_scene,
    narrate_privately,
    non_web_sessions,
)
from world.scenes.models import Persona
from world.scenes.place_models import InteractionReceiver
from world.scenes.services import active_persona_for_sheet

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.gm.types import NarratableEvent
    from world.scenes.models import Interaction, Scene
    from world.scenes.types import NarratedEventPayload

logger = logging.getLogger(__name__)

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


def account_can_gm_scene(account: AccountDB, scene: Scene) -> bool:
    """Staff, the scene's GM, or the scene's owner -- mirrors ``IsSceneGMOrOwnerOrStaff``
    / ``SceneListSerializer.get_viewer_can_gm`` (#4101)."""
    return bool(account.is_staff or scene.is_gm(account) or scene.is_owner(account))


def _prompt_visibility_query(account: AccountDB, scene: Scene | None) -> Q:
    """The identity/kind/scene-permission shape ``account`` may act within -- status-agnostic.

    Split out from ``visible_prompts_for`` (#4101 fix round 2, finding 6) so
    ``prompt_visible_to`` can reuse the SAME eligibility shape without also
    baking in the PENDING/NARRATED status filter -- an already-resolved prompt
    (e.g. re-confirming a CONFIRMED dramatic moment) must still reach the
    action for its own "already resolved" message, not 404 here first.

    ``scene=None`` (#4101 fix round 1, ruling R12-2): a GM standing outside any
    scene still sees their own scene-less narration prompts (stake outcomes
    follow their GM everywhere), so the narration half narrows to scene-less
    only. The dramatic_moment branch always needs a real scene to gate
    ``account_can_gm_scene`` against, so it contributes nothing when ``scene``
    is ``None``.
    """
    narration = Q(kind__in=NARRATION_PROMPT_KINDS, addressed_to=account)
    if scene is not None:
        narration &= Q(scene=scene) | Q(scene__isnull=True)
    else:
        narration &= Q(scene__isnull=True)
    query = narration
    if (
        scene is not None
        and account_can_gm_scene(account, scene)
        and prompts_enabled(account, GMPromptKind.DRAMATIC_MOMENT)
    ):
        query |= Q(kind=GMPromptKind.DRAMATIC_MOMENT, scene=scene)
    return query


def visible_prompts_for(account: AccountDB, *, scene: Scene | None) -> QuerySet[GMPrompt]:
    """OPEN (PENDING or NARRATED) prompts ``account`` may act on in ``scene``'s queue (#4101).

    Narration kinds: only the addressed GM, for this scene or scene-less (stake
    outcomes follow their GM into any scene they run). Dramatic moments: the
    unchanged #2183 gate (scene GM, owner or staff), minus a GM who muted the
    group. Controller amendment R6-2: a NARRATED prompt stays in the queue (it is
    released only on close, via ``dismiss_gm_prompt``/``expire_scene_prompts``), so
    this filters on ``_NARRATABLE_STATUSES`` rather than PENDING alone -- a
    dramatic_moment prompt never reaches NARRATED in practice (only a narration
    kind transitions there), so this is a no-op widening for that half of the query.

    ``scene=None`` (#4101 fix round 1, ruling R12-2): returns only ``account``'s
    own scene-less narration prompts -- see ``_prompt_visibility_query``. This is
    the ONE visibility source for every GM-prompt listing surface, REST
    (``GMPromptViewSet.get_queryset``) and telnet (``visible_prompts_for_location``)
    alike, so a muted GM, or one standing outside any scene, sees the same thing
    everywhere.
    """
    return (
        GMPrompt.objects.filter(
            _prompt_visibility_query(account, scene), status__in=_NARRATABLE_STATUSES
        )
        .select_related(
            "character_sheet", "moment_type", "technique", "stake_outcome__stake", "scene"
        )
        .order_by("-created_at")
    )


def visible_prompts_for_location(
    account: AccountDB,
    location: ObjectDB | None,  # noqa: OBJECTDB_PARAM - any room the GM stands in
) -> QuerySet[GMPrompt]:
    """``visible_prompts_for``, scoped to whatever scene is active at ``location`` (#4101
    fix round 1, ruling R12-2).

    The telnet seam for every GM-prompt listing that isn't already handed a
    specific scene id: resolves the active scene at ``location`` the same way
    every other GM-prompt command does (``get_active_scene``), then defers
    entirely to ``visible_prompts_for`` -- the one visibility source the REST
    queue (``GET /api/gm/prompts/?scene=``) already uses -- rather than a
    second, hand-rolled query. A GM standing outside any scene
    (``get_active_scene`` returns ``None``) still sees their own scene-less
    prompts, never a crash and never everything.
    """
    return visible_prompts_for(account, scene=get_active_scene(location))


def prompt_visible_to(account: AccountDB, prompt: GMPrompt) -> bool:
    """Scene-agnostic IDOR scope for a single prompt (#4101 fix round 2, finding 6).

    ``confirm``/``dismiss``/``narrate`` act on one prompt by id, not a scene's
    whole queue, so they scope their object lookup through this rather than a
    bare ``get_object_or_404(GMPrompt, pk=pk)`` -- an id outside ``account``'s
    visible queue must 404 regardless of kind, the same way an invisible row
    never appears in ``GET .../prompts/?scene=``. Deliberately status-agnostic
    (see ``_prompt_visibility_query``'s own docstring) -- re-confirming an
    already-CONFIRMED prompt the account genuinely owns must still reach the
    action for its "already resolved" message, not 404 here first.

    Staff bypass unconditionally (#4101 fix round 3, finding M2) -- the ONE
    place that decision lives now, matching ``narration_prompt_for``'s own
    staff bypass for narrate and ``DismissGMPromptAction``'s for dismiss. This
    is deliberately narrower than ``visible_prompts_for``'s own LISTING
    semantics (which never widens for staff): a per-object lookup by a known id
    is not the same question as "dump every other GM's narration prompts into
    a scene queue a staff member is merely browsing."

    A scene-less prompt is always a narration kind addressed to one GM (the
    model's own ``gm_prompt_narration_is_addressed`` CheckConstraint), so
    there is no dramatic_moment branch to gate and no scene to pass --
    visibility there is just "am I the addressed GM."
    """
    if account.is_staff:
        return True
    if prompt.scene_id is not None:
        query = _prompt_visibility_query(account, prompt.scene)
        return GMPrompt.objects.filter(query, pk=prompt.pk).exists()
    return prompt.kind in NARRATION_PROMPT_KINDS and prompt.addressed_to_id == account.pk


def prompt_recipients(
    scene: Scene | None, kind: str, *, candidates: list[AccountDB] | None = None
) -> list[AccountDB]:
    """The GMs a ``kind`` event should prompt: candidates (default: scene GMs) minus muted."""
    pool = scene_gm_accounts(scene) if candidates is None else candidates
    if not pool:
        return []
    muted = _muted_account_ids([a.pk for a in pool], kind)
    return [a for a in pool if a.pk not in muted]


def recipients_excluding_subject(
    scene: Scene | None,
    kind: str,
    sheet: CharacterSheet | None,
    *,
    candidates: list[AccountDB] | None = None,
) -> list[AccountDB]:
    """``prompt_recipients``, minus ``sheet``'s own currently-playing account.

    #4101 fix round 2, ruling R7-1: the shared subject-exclusion seam -- a
    player who also GMs their own scene is never counted as a recipient for
    their own event, whether the caller is about to actually create prompts
    (``route_narratable_event``, below) or is only asking the same "would a
    REAL GM be prompted" question ahead of time to decide whether to withhold
    something now (e.g. ``maybe_create_audere_majora_offer``'s withhold-or-
    deliver-now gate in ``world/magic/audere_majora.py``). Both must agree, or
    the gate can withhold a line that the real routing later decides nobody
    was ever going to see, delaying it for no reason.

    The subject's player is ``get_account_for_character`` (the roster's active
    tenure walk). It works on any character object, not only the ``Character``
    typeclass, which is the only one with ``active_account``.
    """
    recipients = prompt_recipients(scene, kind, candidates=candidates)
    subject_account = get_account_for_character(sheet.character) if sheet is not None else None
    if subject_account is not None:
        recipients = [a for a in recipients if a.pk != subject_account.pk]
    return recipients


def route_narratable_event(
    event: NarratableEvent,
    *,
    candidates: list[AccountDB] | None = None,
) -> list[GMPrompt]:
    """Prompt each opted-in GM; returns ``[]`` when none want it (spec decision 7).

    The event's own subject -- ``event.character_sheet``'s currently-playing
    account -- is always dropped from recipients, via ``recipients_excluding_
    subject`` above (#4101 fix round 2, ruling R7-1): a player who also GMs
    their own scene must never be prompted about their own event. Centralized
    here (rather than duplicated per call site, as ``_crossing_prompt_candidates``/
    ``gm_prompt_candidates_excluding_subject`` did through fix round 1) so every
    narratable-event source gets the exclusion for free, including ones not yet
    written.

    Every created prompt shares one ``event_group`` (#4101 fix round 1) -- they are
    siblings of the SAME event, one copy per addressed GM. ``dismiss_gm_prompt``
    groups on this field to release the event's authored defaults exactly once,
    when the last sibling closes, rather than once per GM.

    The creates run inside one ``transaction.atomic()`` (#4101 fix round 2,
    must-fix 3) -- without it, a failure partway through the list (e.g. a
    constraint violation on the Nth recipient) would leave the first N-1
    prompts committed with no sibling ever able to release their event's
    defaults: orphaned PENDING rows nothing resolves. Wrapping the whole batch
    means a mid-batch failure rolls every prompt back together, and the
    ``on_commit`` notify registrations below are discarded along with it
    (Django clears pending ``on_commit`` callbacks on rollback) -- so a raise
    here never leaves a live notify for a prompt that no longer exists.

    No longer accepts a ``deliver_unprompted`` callback (#4101 fix round 2,
    ruling R7-2): delivering the event's own default lines when this returns
    ``[]`` is the CALLER's job now. A caller that needs its delivery to survive
    a ``DatabaseError`` raised from in here, or to run exactly once across both
    the no-recipients path and a recovery path, can only guarantee that by
    owning the one call site itself -- see ``_route_crossing``
    (``world/magic/audere_majora.py``) for the pattern every caller follows.

    ``subject_persona`` (#4101 fix round 3, ruling R9-3) freezes the face the
    subject was presenting as AT EVENT TIME, resolved once here via
    ``active_persona_for_sheet`` -- never per sibling -- so every GM's own copy
    of the event shares one frozen identity. A later persona switch (removing a
    mask, putting on a different one) must never rewrite what an already-routed
    prompt says about who it concerns. ``Persona.DoesNotExist`` (the PRIMARY
    invariant broken) degrades to ``None`` rather than raising -- routing a
    narratable event must never fail because of this.
    """
    recipients = recipients_excluding_subject(
        event.scene, event.kind, event.character_sheet, candidates=candidates
    )
    if not recipients:
        return []
    subject_persona = None
    if event.character_sheet is not None:
        with contextlib.suppress(Persona.DoesNotExist):
            subject_persona = active_persona_for_sheet(event.character_sheet)
    event_group = uuid.uuid4()
    with transaction.atomic():
        prompts = [
            GMPrompt.objects.create(
                kind=event.kind,
                event_group=event_group,
                scene=event.scene,
                character_sheet=event.character_sheet,
                subject_persona=subject_persona,
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
    """The name the GM sees for who this concerns (primary persona), or ''.

    GM-only (the GM prompt queue, telnet notify line): deliberately the real
    primary persona, never masked -- a GM resolving an event needs to know who
    it actually concerns. The player-facing sibling is ``narrated_event_payload``
    below, which must NOT unmask a disguise (#4101 fix round 2, ruling R9-1).
    """
    sheet = prompt.character_sheet
    if sheet is None:
        return ""
    try:
        return sheet.primary_persona.name
    except Persona.DoesNotExist:
        return ""


def narrated_event_subject_persona(interaction: Interaction) -> Persona | None:
    """The FROZEN subject persona of ``interaction``'s linked narration, if any (#4101 R9-3).

    Peek-only, from the same ``cached_prompt_narrations`` link cache
    ``narrated_event_payload`` reads -- never queries. Separated out from that
    function so the interaction feed's per-viewer display-map builder
    (``InteractionListSerializer._persona_display_map``) can fold this persona
    into the page's one batched discovery query instead of reading the name off
    it unmasked -- see that method's docstring for why.
    """
    links = interaction.__dict__.get("cached_prompt_narrations") or []
    if not links:
        return None
    return links[0].prompt.subject_persona


def narrated_event_payload(interaction: Interaction) -> NarratedEventPayload | None:
    """The "part of X's Crossing" tag for a row, from the PEEKED link cache only (#4101).

    Reads ``interaction.__dict__`` directly rather than the
    ``cached_prompt_narrations`` property -- a cache miss there would run its
    own query, which this seam must never do (it runs on every live push).
    ``link_prompt_narration`` seeds that same cache key synchronously on the
    just-created row, so the live push always finds it already populated.

    ``subject_name``/``subject_persona_id`` come from ``GMPrompt.subject_persona``
    -- the face FROZEN at event-routing time (#4101 fix round 3, ruling R9-3) --
    never the subject's current or primary face: a later persona switch
    (undisguising, wearing a different mask) must not rewrite what an
    already-narrated row says. This is the unmasked value used by the live
    WebSocket push (which has no per-viewer concept at all, same as every other
    field on that payload); the REST feed's ``InteractionListSerializer
    .get_narrates`` overrides ``subject_name`` with the page's per-viewer
    display-map resolution before returning it, so is_fake_name/undiscovered
    faces read exactly as the rest of the feed shows them. When no sheet was
    attached at event time (a STAKE_OUTCOME prompt) or the persona was since
    deleted (``subject_persona`` is ``SET_NULL``), both keys are omitted
    entirely rather than sent empty/null -- the payload then carries
    ``kind``/``kind_label`` only.
    """
    links = interaction.__dict__.get("cached_prompt_narrations") or []
    if not links:
        return None
    prompt = links[0].prompt
    payload: NarratedEventPayload = {
        "prompt_id": prompt.pk,
        "kind": prompt.kind,
        "kind_label": prompt.get_kind_display(),
    }
    subject = prompt.subject_persona
    if subject is not None:
        payload["subject_name"] = subject.name
        payload["subject_persona_id"] = subject.pk
    return payload


def _telnet_line(prompt: GMPrompt) -> str:
    subject = prompt_subject_name(prompt)
    head = f"GM prompt [{prompt.pk}] {prompt.get_kind_display()}"
    head = f"{head}: {subject}." if subject else f"{head}."
    return (
        f"{head} emit/prompt {prompt.pk} <text> | pemit/prompt {prompt.pk} <names>=<text>"
        f" | gm prompt send {prompt.pk} | gm prompt dismiss {prompt.pk}"
        f" | gm prompt done {prompt.pk}"
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


def _narration_coverage(event_group: uuid.UUID) -> tuple[bool, bool]:
    """Whether this event's own narrations already cover the room line / the private line.

    Reads every ``GMPromptNarration`` linked to any sibling prompt sharing
    ``event_group`` (#4101 fix round 1, controller ruling I2). A room EMIT (no
    receivers) covers the room line; a receiver-scoped EMIT (pemit) whose
    receivers include the event's own subject, or a WHISPER to that subject,
    covers the private line -- the two legs are independent, so a GM who only
    sends a room line leaves the private default (e.g. a Crossing's vision) to
    release on its own, and the reverse holds too.

    A receiver-scoped EMIT to someone OTHER than the subject (an unrelated
    pemit the GM happens to send while this prompt is open) covers neither leg
    (#4101 fix round 2, minor fix 6) -- it must never be mistaken for private
    coverage of THIS event. ``has_subject_receiver``/``has_any_receiver`` are
    ``Exists`` subquery annotations rather than a per-row ``.exists()`` call,
    so this runs in one query regardless of how many lines were narrated.
    """
    narrations = GMPromptNarration.objects.filter(prompt__event_group=event_group)
    first = narrations.select_related("prompt__character_sheet").first()
    if first is None:
        return False, False

    sheet = first.prompt.character_sheet
    subject_persona_id = None
    if sheet is not None:
        with contextlib.suppress(Persona.DoesNotExist):
            subject_persona_id = sheet.primary_persona.pk

    receiver_qs = InteractionReceiver.objects.filter(interaction_id=OuterRef("interaction_id"))
    subject_receiver_qs = (
        receiver_qs.filter(persona_id=subject_persona_id)
        if subject_persona_id is not None
        else receiver_qs.none()
    )
    annotated = narrations.select_related("interaction").annotate(
        has_any_receiver=Exists(receiver_qs),
        has_subject_receiver=Exists(subject_receiver_qs),
    )

    room = False
    private = False
    for link in annotated:
        interaction = link.interaction
        if interaction.mode == InteractionMode.WHISPER:
            if link.has_subject_receiver:
                private = True
        elif interaction.mode == InteractionMode.EMIT:
            if not link.has_any_receiver:
                room = True
            elif link.has_subject_receiver:
                private = True
        if room and private:
            break
    return room, private


def prompt_narration_coverage(prompt: GMPrompt) -> tuple[bool, bool]:
    """Public ``(room_covered, private_covered)`` wrapper over ``_narration_coverage``
    (#4101 fix round 1, ruling R12-3).

    The one coverage computation every caller that needs to know "has this leg
    already gone out" reads -- never re-derived. Telnet's ``gm prompt send``
    calls this before narrating so a re-run after a partial failure (e.g. the
    room EMIT landed, then something interrupted before the pemit) narrates
    only the leg that's still missing, the same rule
    ``_resolve_narration_prompt`` already applies when deciding what a close
    releases.
    """
    return _narration_coverage(prompt.event_group)


def narration_location_for(
    prompt: GMPrompt,
    actor: ObjectDB,  # noqa: OBJECTDB_PARAM - any room the GM stands in
) -> ObjectDB | None:
    """The room to test physical presence against for ``prompt`` (#4101 fix round 1).

    The prompt's own scene location, falling back to ``actor``'s current
    location when the scene has none (a location-less Battle scene, fix round
    3 finding N3) or the prompt is scene-less entirely. Shared by the REST
    ``GMPromptViewSet.narrate`` chosen-receiver presence check and telnet's
    ``gm prompt send`` subject-presence check -- the one place this resolution
    is written, not re-derived per call site.
    """
    scene_location = prompt.scene.location if prompt.scene_id else None
    return scene_location or actor.location


def present_characters_in_room(
    character_sheet_ids: list[int],
    location: ObjectDB | None,  # noqa: OBJECTDB_PARAM - any room to test presence against
) -> dict[int, ObjectDB]:
    """Sheet id (== ObjectDB pk, #2608) -> ObjectDB, for each of ``character_sheet_ids``
    physically present in ``location`` (#4101 fix round 1).

    One batched query, not one per character -- shared by the REST
    ``NarrateGMPromptSerializer`` chosen-receiver presence check and telnet's
    ``gm prompt send`` subject-presence check, so "is this character actually
    in the room" is answered the same way everywhere rather than re-derived.
    ``location=None`` (no room to test against) answers "nobody is present."
    """
    from evennia.objects.models import ObjectDB  # noqa: PLC0415

    if location is None or not character_sheet_ids:
        return {}
    return {
        obj.pk: obj
        for obj in ObjectDB.objects.filter(pk__in=character_sheet_ids, db_location_id=location.pk)
    }


def release_prompt_defaults(
    prompt: GMPrompt, *, room: bool = True, private: bool = True, push_live: bool | None = None
) -> None:
    """Deliver a prompt's authored defaults the unprompted way (no GM covered them).

    Releases against the prompt's OWN scene (``prompt.scene``), never one
    re-derived from the character's current location (#4101 fix round 1) -- a
    character who moved rooms between the prompt's creation and its release
    must still get the room/private line attributed to the scene the event
    actually happened in.

    ``room``/``private`` (#4101 fix round 1, controller ruling I2) let a caller
    release only the leg no sibling narrated -- a GM who sent only a room line
    still leaves the private default (e.g. a Crossing's vision) to go out on
    its own, and vice versa. Both default True so a direct call with no kwargs
    behaves like the old all-or-nothing release.

    The room EMIT's live push is scene-scoped (``scene_scoped_push=True``, #4101
    fix round 2, must-fix 2) -- it targets ``prompt.scene``'s own location
    (never a location-less one, ruling N3), never wherever the character
    currently stands. ``push_live`` (#4101 fix round 3, ruling N4) is the
    caller's OWN decision, made at the moment release was decided under the
    sibling lock in ``_resolve_narration_prompt`` -- forwarded as-is rather
    than letting ``broadcast_scene_emit`` re-derive ``scene.is_active`` live
    here, since this function itself typically runs inside
    ``transaction.on_commit``, well after that decision point, by which time
    something else in the same call chain (scene finish, right after expire)
    may have already flipped the scene inactive.
    """
    sheet = prompt.character_sheet
    if sheet is None:
        return
    character = sheet.character
    if room and prompt.room_text.strip():
        broadcast_scene_emit(
            character,
            prompt.room_text,
            scene=prompt.scene,
            scene_scoped_push=True,
            push_live=push_live,
        )
    if private and prompt.private_text.strip():
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


def _lock_siblings(prompt: GMPrompt) -> list[GMPrompt]:
    """Lock every prompt of ``prompt``'s event, always in pk order.

    Siblings are created together and can share ``created_at``, so the model's
    default ordering does not fix the lock order; pk order does, which keeps a
    close and a narration from taking the rows in opposite orders.
    """
    return list(
        GMPrompt.objects.select_for_update().filter(event_group=prompt.event_group).order_by("pk")
    )


def _resolve_narration_prompt(
    prompt: GMPrompt, *, new_status: str, resolver: AccountDB | None
) -> GMPrompt:
    """Resolve one narration prompt; release its event's defaults only when it CLOSES.

    Siblings routed from the same event (shared ``event_group``) are locked for
    the duration of the transaction via ``select_for_update`` -- a dismiss racing
    scene end's own ``expire_scene_prompts`` sweep, or two tabs dismissing the
    same prompt, serializes against this instead of double-sending (#4101 fix
    round 1).

    ``new_status`` is either NARRATED (a GM's narration; the prompt stays OPEN
    for more lines) or DISMISSED (the prompt CLOSES -- explicitly dismissed, or
    marked done after narrating, or expired at scene end). A transition to
    NARRATED never triggers release: a GM's first narration does not decide the
    release on its own (#4101 fix round 2, controller ruling R6-1) -- it would
    double-send a line the GM is still in the middle of covering (e.g. a room
    line now, a private line a moment later, on the SAME prompt). Only a
    transition to DISMISSED evaluates release, and only once every sibling in
    the event has ALSO reached DISMISSED -- a sibling merely NARRATED is still
    open, so the event isn't closed yet. The gate below accepts either PENDING
    or NARRATED as the prompt's pre-transition state (``_NARRATABLE_STATUSES``)
    -- a NARRATED prompt may still be dismissed (closed) once the GM is done
    adding lines to it.

    Release itself stays per-line (#4101 fix round 1, controller ruling I2): the
    room default releases unless some sibling narrated a room line, and the
    private default releases unless some sibling narrated privately --
    re-derived fresh from the linked ``GMPromptNarration`` rows at CLOSE time,
    not decided by whichever narration happened to resolve this specific
    prompt's own status.

    The still-open re-check below reads ``siblings`` -- the ``select_for_update()``
    result, i.e. the identity map's live Python objects, not a fresh row-by-row
    re-query of the database. That is correct *because* every status change to a
    GMPrompt goes through this same function under the same lock: no writer can
    mutate a sibling's status without first taking this exact lock, so the
    in-memory objects the lock hands back are never stale relative to each other
    (#4101 fix round 2).

    ``release_prompt_defaults`` is deferred to ``transaction.on_commit`` (#4101
    fix round 2) -- GMPrompt is idmapper-cached, so a Python-level attribute
    mutation (``this.status = new_status``) is not automatically undone by a
    database rollback the way the DB row is. Running delivery (which can raise)
    *inside* this atomic block risked a delivery failure rolling back the DB
    write while leaving the cached instance's ``status`` stuck at
    DISMISSED/NARRATED in memory -- from then on every future dismiss attempt on
    that same cached object would see a non-open status and refuse
    (``_MSG_RESOLVED``), and ``expire_scene_prompts`` would never find it open
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
        siblings = _lock_siblings(prompt)
        this = next(s for s in siblings if s.pk == prompt.pk)
        if this.status not in _NARRATABLE_STATUSES:
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
        if new_status == GMPromptStatus.DISMISSED:
            still_open = any(s.status != GMPromptStatus.DISMISSED for s in siblings)
            if not still_open:
                room_covered, private_covered = _narration_coverage(prompt.event_group)
                release_room = not room_covered
                release_private = not private_covered
                if release_room or release_private:
                    # #4101 fix round 3 (N4): decide push-live eligibility HERE,
                    # under the lock, while the scene's current ``is_active`` is
                    # still authoritative for "was it active when release was
                    # decided" -- not inside the on_commit callback below, which
                    # runs later and could find the scene already finished by
                    # something else in the same call chain (e.g.
                    # finish_scene_full/_finish_event_scenes calling
                    # scene.finish_scene() right after this very dismiss).
                    push_live = this.scene is not None and this.scene.is_active
                    transaction.on_commit(
                        lambda p=this, r=release_room, pv=release_private, pl=push_live: (
                            release_prompt_defaults(p, room=r, private=pv, push_live=pl)
                        )
                    )
    return this


def dismiss_gm_prompt(prompt: GMPrompt, *, resolver: AccountDB | None) -> GMPrompt:
    """Close an OPEN (PENDING or NARRATED) narration prompt.

    This is the one entry point for BOTH closure shapes (#4101 fix round 2,
    controller ruling R6-1): dismissing a still-PENDING prompt nobody ever
    narrated, and marking a NARRATED prompt done once the GM has sent every
    line they're going to -- the backend close path is identical either way,
    only the GM-facing wording differs (a UI/telnet concern, not this
    function's). A NARRATED prompt stays open for MORE narrations until this
    is called; narrating never closes it by itself.

    Each of its event's authored defaults (room line, private line) goes out at
    most once, independently -- when every sibling GM's own copy of the event
    has ALSO closed (reached DISMISSED), and only for the leg no sibling
    narrated (see ``_resolve_narration_prompt`` / controller ruling I2) --
    never once per dismissing GM, and never merely because a GM narrated.

    Authorization (who may dismiss this prompt) is the CALLER's job -- this
    function only enforces that the prompt is a narration kind and still open.
    Task 9's action is where the real GM/addressee gate lives.
    """
    if prompt.kind not in NARRATION_PROMPT_KINDS:
        raise GMPromptError(_MSG_NOT_NARRATION)
    return _resolve_narration_prompt(prompt, new_status=GMPromptStatus.DISMISSED, resolver=resolver)


def link_prompt_narration(prompt: GMPrompt, interaction: Interaction) -> GMPromptNarration | None:
    """Record ``interaction`` as narrating ``prompt``; None when the prompt has closed (#4101).

    Repeat narrations are allowed, NO CAP BY DESIGN (fix round 1 ruling): a GM
    may send several lines for one event (a room line, then one or more
    private lines to different recipients); each is its own Interaction, each
    gets its own ``GMPromptNarration`` row linked back to the same prompt.

    ONE lock-first path for every call, whatever the prompt's status looked
    like when the caller resolved it (#4101 fix round 4): atomic -> lock every
    sibling of the event (``event_group``) with ``select_for_update``, the same
    lock and order ``_resolve_narration_prompt`` takes for a close -> re-read
    THIS prompt's status from the locked siblings -> only if it is still open
    (PENDING or NARRATED) insert the link row and, for a PENDING prompt, move
    it to NARRATED. The link row is therefore never written before the lock:
    a close racing this narration either runs first (and this call then finds
    the prompt DISMISSED and refuses to link) or waits on the lock and, once
    granted, counts this committed link as real coverage in
    ``_narration_coverage`` -- the default line can never go out alongside a
    narration that covers it. Taking the lock before the insert also keeps the
    insert's FK key-share lock on the prompt row from ever being held ahead of
    a close's ``FOR UPDATE`` on the same rows.

    A refused narration (the prompt is DISMISSED by the time the lock is
    granted -- a sibling dismiss, scene-end expiry, or a narration arriving
    after the GM closed it) returns None and links nothing. It never raises:
    this runs as ``record_interaction``'s ``on_created`` hook, after the
    telnet line already went out, and the caller must still push the
    Interaction as plain narration. The caller decides what (if anything) to
    tell the GM.

    The NARRATED transition never releases a default (controller ruling
    R6-1); only a close does, see ``_resolve_narration_prompt``.
    """
    with transaction.atomic():
        siblings = _lock_siblings(prompt)
        this = next(s for s in siblings if s.pk == prompt.pk)
        if this.status not in _NARRATABLE_STATUSES:
            logger.info(
                "GM prompt %s closed before narration %s could link; sent as plain narration.",
                this.pk,
                interaction.pk,
            )
            return None
        link = GMPromptNarration.objects.create(
            prompt=this, interaction=interaction, interaction_timestamp=interaction.timestamp
        )
        # Seed (never read back) the cache so push_interaction's peek finds it with no query.
        interaction.cached_prompt_narrations = [link]
        if this.status == GMPromptStatus.PENDING:
            # Re-takes the lock this transaction already holds (a no-op wait) and
            # re-checks the status it just read under it, so this cannot be refused.
            _resolve_narration_prompt(
                this, new_status=GMPromptStatus.NARRATED, resolver=this.addressed_to
            )
    return link


def expire_scene_prompts(scene: Scene) -> int:
    """Scene finished: close its still-open narration prompts so no default is lost.

    Closes BOTH PENDING (never narrated) and NARRATED (narrated but left open
    for more lines) prompts (#4101 fix round 2, controller ruling R6-1) -- a
    GM who sent a room line and then the scene ended before they sent the
    private line must still have that uncovered line released; a NARRATED
    prompt is not itself a closed event.

    Tolerates a prompt a concurrent dismiss already resolved out from under this
    sweep (``GMPromptError`` from ``_resolve_narration_prompt``'s identity-map
    re-check under lock -- see that function's docstring for why reading the
    cache there is correct) -- that race is a lost race, not a failure to
    report.
    """
    open_prompts = list(
        GMPrompt.objects.filter(
            scene=scene, status__in=_NARRATABLE_STATUSES, kind__in=NARRATION_PROMPT_KINDS
        ).select_related("character_sheet__character")
    )
    expired = 0
    for prompt in open_prompts:
        try:
            dismiss_gm_prompt(prompt, resolver=None)
        except GMPromptError:
            continue
        expired += 1
    return expired


__all__ = [
    "account_can_gm_scene",
    "dismiss_gm_prompt",
    "expire_scene_prompts",
    "link_prompt_narration",
    "narrated_event_payload",
    "narrated_event_subject_persona",
    "narration_location_for",
    "narration_prompt_for",
    "notify_gm_prompt",
    "present_characters_in_room",
    "prompt_narration_coverage",
    "prompt_recipients",
    "prompt_subject_name",
    "prompt_visible_to",
    "prompts_enabled",
    "recipients_excluding_subject",
    "release_prompt_defaults",
    "route_narratable_event",
    "scene_gm_accounts",
    "visible_prompts_for",
    "visible_prompts_for_location",
]

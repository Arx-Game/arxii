"""Communication-related actions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from django.core.exceptions import ObjectDoesNotExist

from actions.base import Action
from actions.constants import ActionCategory, TargetKind
from actions.definitions.sineating import run_pose_sineating
from actions.prerequisites import (
    GhostWindowPrerequisite,
    MinimumGMLevelPrerequisite,
    Prerequisite,
)
from actions.types import ActionContext, ActionResult, TargetFilters, TargetType
from flows.scene_data_manager import SceneDataManager
from flows.service_functions.communication import message_location, send_message
from world.gm.constants import GMLevel
from world.scenes.constants import InteractionMode
from world.scenes.interaction_services import record_interaction, record_whisper_interaction
from world.scenes.line_rendering import render_line
from world.scenes.thread_services import (
    InteractionThreadError,
    ReplyTarget,
    coerce_reply_target,
)


def _parse_reply_target(kwargs: dict[str, Any]) -> tuple[ReplyTarget | None, ActionResult | None]:
    """Parse the optional serializer-shaped target used by communication actions."""
    try:
        return coerce_reply_target(kwargs.get("reply_to")), None
    except InteractionThreadError:
        return None, ActionResult(
            success=False,
            message="Cannot reply to that interaction.",
        )


if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from flows.object_states.base_state import BaseState
    from world.gm.models import GMPrompt
    from world.magic.types.kindling import PendingReach
    from world.magic.types.marking import PendingMark
    from world.magic.types.reflection import PendingReflection
    from world.magic.types.soul_tether import PendingSineating
    from world.scenes.models import Interaction, Persona, Scene
    from world.scenes.place_models import Place
    from world.species.language_constants import Fluency
    from world.species.models import Language


def _narration_prompt(
    actor: ObjectDB, kwargs: dict[str, Any]
) -> tuple[GMPrompt | None, ActionResult | None]:
    """Resolve the optional ``gm_prompt_id`` this emit/pemit narrates (#4101).

    Runs before any message is sent (both ``EmitAction``/``PemitAction`` call this
    ahead of ``message_location``/``send_message``), so a refused narration delivers
    nothing. ``NarratesOwnPromptPrerequisite`` already gates this same question in
    ``check_availability()`` -- this second call is needed because ``execute()``
    wants the actual resolved ``GMPrompt`` to link, not just a yes/no.
    """
    prompt_id = kwargs.get("gm_prompt_id")
    if prompt_id is None:
        return None, None
    from world.gm.exceptions import GMPromptError  # noqa: PLC0415
    from world.gm.prompt_services import narration_prompt_for  # noqa: PLC0415

    try:
        prompt = narration_prompt_for(actor.account, location=actor.location, prompt_id=prompt_id)
    except GMPromptError as exc:
        return None, ActionResult(success=False, message=exc.user_message)
    return prompt, None


_MSG_PROMPT_CLOSED_MEANWHILE = (
    "That prompt was closed before your line landed; it went out as plain narration."
)


@dataclass
class _PromptLinker:
    """``record_interaction``'s ``on_created`` hook that links the row to its prompt (#4101).

    ``link_prompt_narration`` refuses (returns None, never raises) when the prompt
    closed between ``_narration_prompt`` resolving it and the row being created --
    the line has already gone out, so the action still succeeds and delivers in
    full; ``refused`` records that so ``execute()`` can tell the GM.
    """

    prompt: GMPrompt
    refused: bool = False

    def __call__(self, interaction: Interaction) -> None:
        from world.gm.prompt_services import link_prompt_narration  # noqa: PLC0415

        self.refused = link_prompt_narration(self.prompt, interaction) is None

    def result(self) -> ActionResult:
        """The action's success result, noting a refused link to the GM."""
        if self.refused:
            return ActionResult(success=True, message=_MSG_PROMPT_CLOSED_MEANWHILE)
        return ActionResult(success=True)


def _prompt_linker(prompt: GMPrompt | None) -> _PromptLinker | None:
    """A ``_PromptLinker`` for ``prompt``, or None for a plain emit/pemit (#4101)."""
    if prompt is None:
        return None
    return _PromptLinker(prompt)


@dataclass
class NarratesOwnPromptPrerequisite(Prerequisite):
    """Refuses an emit/pemit's optional ``gm_prompt_id`` kwarg the actor may not narrate (#4101).

    No-ops when the kwarg is absent, so plain emit/pemit stay unaffected. Delegates to
    ``narration_prompt_for`` -- the same seam ``_narration_prompt`` calls inside
    ``execute()`` -- so availability and the real resolve can never drift apart; staff
    bypass the addressed-to gate there, the same as every other GM tool.
    """

    def is_met(
        self,
        actor: ObjectDB,
        target: ObjectDB | None = None,
        context: dict | None = None,
    ) -> tuple[bool, str]:
        prompt_id = (context or {}).get("kwargs", {}).get("gm_prompt_id")
        if prompt_id is None:
            return True, ""
        from world.gm.exceptions import GMPromptError  # noqa: PLC0415
        from world.gm.prompt_services import narration_prompt_for  # noqa: PLC0415

        try:
            narration_prompt_for(actor.account, location=actor.location, prompt_id=prompt_id)
        except GMPromptError as exc:
            return False, exc.user_message
        return True, ""


# Module-level filter constants used as dataclass defaults (RUF009: no calls in defaults).
# TargetFilters is frozen, so sharing a single instance is safe.
_WHISPER_TARGET_FILTERS = TargetFilters(in_same_scene=True, exclude_self=True)


def _characters_to_active_personas(characters: list[ObjectDB]) -> list[Persona] | None:
    """Resolve character objects to their active personas.

    Returns None if no characters could be resolved (callers treat None as
    'no explicit targets'). Thin alias over the shared
    ``world.scenes.interaction_services.personas_for_characters`` helper — the
    REST submit-pose path (#2156) resolves directed-pose targets through the
    same function, so both surfaces derive InteractionTargetPersona rows identically.
    """
    from world.scenes.interaction_services import personas_for_characters  # noqa: PLC0415

    return personas_for_characters(characters)


def _flag_blocked_contact_for_targets(
    actor: ObjectDB,
    targets: list[ObjectDB],
    *,
    scene: Scene | None = None,
) -> None:
    """Fire BlockContactFlag for any blocked-pair contact in a communication action (#1278).

    Resolves the actor's and each target's active persona, then calls
    ``flag_blocked_contact_attempt``. The service is a no-op when no active block
    exists (target did not block the initiator), and dedupes per (blocker, blocked,
    scene) — so calling it unconditionally is safe. Zero signal to either player.
    """
    try:
        initiator_persona = actor.sheet_data.primary_persona
    except (AttributeError, ObjectDoesNotExist):
        return
    if initiator_persona is None:
        return
    from world.scenes.block_services import flag_blocked_contact_attempt  # noqa: PLC0415

    for target in targets:
        try:
            target_persona = target.sheet_data.primary_persona
        except (AttributeError, ObjectDoesNotExist):
            continue
        if target_persona is not None:
            flag_blocked_contact_attempt(
                initiator_persona=initiator_persona,
                target_persona=target_persona,
                scene=scene,
            )


def _active_scene_for(actor: ObjectDB) -> Scene | None:
    """Resolve the active scene at the actor's location, if any."""
    from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415

    return get_active_scene(actor.location)


def _resolve_pose_place(actor: ObjectDB, place: object) -> tuple[Place | None, ActionResult | None]:
    """Resolve the `place` kwarg for a pose/tabletalk dispatch (#3760 Task 10).

    Telnet's `CmdTabletalk` always resolves the CALLER'S OWN current place
    server-side (`_get_current_place`, `commands/evennia_overrides/
    communication.py`) -- it never accepts a place by id from the client. The
    web composer has no equivalent command-layer resolution step
    (`execute_action`'s generic `_resolve_registry_kwargs`,
    `server/conf/inputfuncs.py`, only resolves ObjectDB `<field>_id` kwargs;
    `Place` isn't an ObjectDB), so this mirrors the established
    `_resolve_room()` REST/WS-dispatch pattern (`actions/definitions/
    locations.py`, see `src/actions/CLAUDE.md`): an already-resolved `Place`
    instance (the telnet/legacy call shape) passes through unchanged, and a
    raw int pk (the WS dispatch shape) is resolved here.

    Unlike `_resolve_room()`, this ALSO requires the actor's active persona to
    have a genuine `PlacePresence` at the resolved place -- a plain pk lookup
    alone would let a client assert presence at an arbitrary table by
    guessing its id, which the telnet path never allows (it only ever
    resolves wherever the caller actually is). Returns `(place, None)` on
    success, or `(None, error_result)` on any failure -- not-found and
    not-present collapse to the same message, mirroring
    `_resolve_registry_kwargs`'s "Object not found" collapse for ObjectDB
    targets (no existence probe).
    """
    if place is None or hasattr(place, "pk"):
        return place, None  # type: ignore[return-value]

    from world.scenes.place_models import Place, PlacePresence  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    persona = active_persona_for_sheet(actor.character_sheet)
    resolved = Place.objects.filter(pk=place).first()
    if (
        resolved is None
        or not PlacePresence.objects.filter(place=resolved, persona=persona).exists()
    ):
        return None, ActionResult(success=False, message="You are not at that place.")
    return resolved, None


def _resolve_spoken_language(
    actor: ObjectDB, kwargs: dict[str, Any]
) -> tuple[Language | None, ActionResult | None]:
    """The language this utterance is in (#2993).

    Explicit ``language_id`` kwarg wins; otherwise falls back to the sheet's
    sticky ``current_language``. ``(None, None)`` means the universal default
    (no language tag) -- the legacy byte-identical broadcast path. Returns an
    error result when the speaker names (or is stuck with) a language they
    don't actually know (no linked trait row, or fluency below 1).
    """
    from world.species.language_services import fluency_value  # noqa: PLC0415
    from world.species.models import Language  # noqa: PLC0415

    unknown_tongue = ActionResult(success=False, message="You don't know that tongue.")

    language_id = kwargs.get("language_id")
    if language_id is not None:
        language = Language.objects.filter(pk=language_id).first()
        if language is None:
            return None, unknown_tongue
    else:
        try:
            language = actor.sheet_data.current_language
        except ObjectDoesNotExist:
            language = None
        if language is None:
            return None, None

    if language.is_universal:
        # Explicitly picking a universal language (via language_id or a sticky
        # current_language) is the same in-fiction outcome as the untagged
        # default -- normalize to None so Interaction.language stays null (the
        # "null = universal/untagged" contract) and skip the fluency gate
        # entirely: a universal tongue needs no fluency to speak, so a
        # zero-fluency speaker can still explicitly select it (#2993
        # final-review M3).
        return None, None

    try:
        sheet = actor.sheet_data
    except ObjectDoesNotExist:
        return None, unknown_tongue

    if fluency_value(sheet, language) < 1:
        return None, unknown_tongue

    return language, None


def _render_speech_for_listener(
    obj: ObjectDB,
    text: str,
    *,
    language: Language,
    speaker_band: Fluency,
    listener_values: dict[int, int],
) -> str:
    """Per-listener comprehension render for live telnet delivery (#2993).

    Mirrors ``world.scenes.interaction_services._language_render_for``'s
    ordering: the writer (handled by the caller) and staff always get ground truth; an
    object with no
    resolvable CharacterSheet (a prop, an NPC) also gets ground truth rather
    than a garbled read. The listener reads comprehension (trained plus
    active-condition bonuses, #4090) from ``listener_values``, computed once for the
    whole room by ``comprehension_values``; the speaker's band stays on trained fluency.
    """
    account = obj.account
    if account is not None and account.is_staff:
        return text
    try:
        sheet = obj.sheet_data
    except ObjectDoesNotExist:
        return text

    from world.species.language_services import render_speech  # noqa: PLC0415

    return render_speech(
        text,
        language=language,
        speaker_band=speaker_band,
        listener_value=listener_values.get(sheet.pk, 0),
    )


def _deliver_say_to_object(  # noqa: PLR0913 - cohesive per-recipient say-delivery params
    obj: ObjectDB,
    actor: ObjectDB,
    text: str,
    language: Language,
    speaker_band: Fluency,
    excluded_ids: set[int],
    sdm: SceneDataManager,
    listener_values: dict[int, int],
) -> None:
    if not hasattr(obj, "msg"):
        return
    if obj.pk in excluded_ids:
        return
    rendered = (
        text
        if obj.pk == actor.pk
        else _render_speech_for_listener(
            obj,
            text,
            language=language,
            speaker_band=speaker_band,
            listener_values=listener_values,
        )
    )
    obj_state = sdm.initialize_state_for_object(obj)
    if obj.pk == actor.pk:
        # Speaker's own echo stays second-person, matching the
        # $You() $conj(say) voice of the universal-language branch
        # above (#2993 final-review M2).
        send_message(
            obj_state, f'You say in {language.name}, "{rendered}"', echo_of=InteractionMode.SAY
        )
    else:
        send_message(
            obj_state,
            f'{actor.key} says in {language.name}, "{rendered}"',
            echo_of=InteractionMode.SAY,
        )


def _deliver_language_tagged_say(
    actor: ObjectDB, text: str, language: Language, sdm: SceneDataManager
) -> None:
    # Per-recipient telnet delivery (#2993): the writer and every other
    # character-with-sheet listener gets a comprehension-graded read of
    # the same tagged line -- the language name is always visible
    # (ratified default #3), only the spoken content garbles.
    from world.species.language_constants import fluency_band  # noqa: PLC0415
    from world.species.language_services import (  # noqa: PLC0415
        comprehension_values,
        fluency_value,
    )

    speaker_band = fluency_band(fluency_value(actor.sheet_data, language))
    location = actor.location
    if location is None:
        return

    # #2287 parity (C2 final-review fix), routed through the Axis-1
    # broadcast-exclusion registry (#2997): the per-recipient loop below
    # hand-rolls room delivery instead of going through
    # message_location()/msg_contents, so it must apply the same
    # room-broadcast exclusions by hand or a dreamside-perceiving (or any
    # other registered-exclusion) character illegitimately hears
    # waking-room language-tagged says. Calling the registry union
    # (not `_dreamside_occupants` by name) means a second registered
    # resolver (a haunting/vision/glamour) is honored here too, not
    # just at `message_location`'s call site.
    from flows.service_functions.perception_registry import (  # noqa: PLC0415
        resolve_broadcast_exclusions,
    )

    excluded_ids = {obj.pk for obj in resolve_broadcast_exclusions(location)}
    contents = list(location.contents)
    # #4090: every listener's comprehension in one batched read (CharacterSheet shares
    # ObjectDB's pk), never a per-listener query inside the loop below.
    listener_values = comprehension_values(
        [obj.pk for obj in contents if obj.pk != actor.pk and obj.pk not in excluded_ids],
        language,
    )
    for obj in contents:
        _deliver_say_to_object(
            obj, actor, text, language, speaker_band, excluded_ids, sdm, listener_values
        )


def _record_say_submission(  # noqa: PLR0913
    actor: ObjectDB,
    *,
    text: str,
    language: Language | None,
    target_personas: list[Persona] | None,
    reply_to: ReplyTarget | None,
    broadcast: Callable[[], None],
    client_request_id: object,
) -> ActionResult | None:
    """Record an idempotent say and broadcast only on first acceptance."""
    from world.scenes.interaction_services import idempotent_record_interaction  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    result = idempotent_record_interaction(
        persona=active_persona_for_sheet(actor.character_sheet),
        client_request_id=client_request_id,
        comparison_fields={"content": text},
        character=actor,
        content=text,
        mode=InteractionMode.SAY,
        target_personas=target_personas,
        language=language,
        reply_to=reply_to,
    )
    if result.conflict:
        return ActionResult(
            success=False, message="This request id was already used for different text."
        )
    if not result.replayed:
        broadcast()
    return None


def _broadcast_pose(actor: ObjectDB, caller_state: Any, text: str, place: Place | None) -> None:
    """Render and broadcast a pose using the actor's currently visible name."""
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    sheet = actor.character_sheet
    actor_name = active_persona_for_sheet(sheet).name if sheet is not None else actor.key
    # Place-scoped interactions are receiver-scoped while this room line is not,
    # so it stays untagged there until room delivery is place-aware (#3933).
    message_location(
        caller_state,
        render_line(
            "{caller}",
            InteractionMode.POSE,
            text,
            place_name=place.name if place is not None else None,
            actor_name=actor_name,
        ),
        echo_of=InteractionMode.POSE if place is None else None,
    )


def _record_pose_submission(  # noqa: PLR0913
    actor: ObjectDB,
    *,
    text: str,
    place: Place | None,
    target_personas: list[Persona] | None,
    reply_to: ReplyTarget | None,
    broadcast: Callable[[], None],
    client_request_id: object,
    after_first_acceptance: Callable[[Interaction | None], None] | None = None,
) -> ActionResult | None:
    """Record an idempotent pose and broadcast only on first acceptance.

    ``after_first_acceptance`` runs with the recorded row (None in an ephemeral scene) on first
    acceptance only, never on a replay: a retried pose must not record its reflection twice.
    """
    from world.scenes.interaction_services import idempotent_record_interaction  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    target_pks = frozenset(p.pk for p in target_personas) if target_personas else frozenset()
    result = idempotent_record_interaction(
        persona=active_persona_for_sheet(actor.character_sheet),
        client_request_id=client_request_id,
        comparison_fields={
            "content": text,
            "place_id": place.pk if place is not None else None,
            "target": lambda stored: (
                frozenset(p.pk for p in stored.target_personas.all()) == target_pks
            ),
        },
        character=actor,
        content=text,
        mode=InteractionMode.POSE,
        target_personas=target_personas,
        place=place,
        reply_to=reply_to,
    )
    if result.conflict:
        return ActionResult(
            success=False, message="This request id was already used for different text."
        )
    if not result.replayed:
        broadcast()
        if after_first_acceptance is not None:
            after_first_acceptance(result.interaction)
    return None


def _deliver_mutter(
    actor: ObjectDB, receivers: list[ObjectDB], *, text: str, fragment: str, sdm: SceneDataManager
) -> None:
    """Deliver full mutter text to receivers, a fragment to bystanders, and the
    mutterer their own echo (#3657: telnet showed them nothing; the web drops it)."""
    receiver_ids = {receiver.pk for receiver in receivers}
    for receiver in receivers:
        receiver_state = sdm.initialize_state_for_object(receiver)
        send_message(
            receiver_state,
            render_line(actor.key, InteractionMode.MUTTER, text),
            echo_of=InteractionMode.MUTTER,
        )
    listeners = ", ".join(receiver.key for receiver in receivers)
    send_message(
        sdm.initialize_state_for_object(actor),
        f'You mutter to {listeners}, "{text}"',
        echo_of=InteractionMode.MUTTER,
    )
    location = actor.location
    if location is None:
        return
    for obj in location.contents:
        if obj.pk in receiver_ids or obj.pk == actor.pk:
            continue
        if not hasattr(obj, "msg"):
            continue
        bystander_state = sdm.initialize_state_for_object(obj)
        send_message(
            bystander_state,
            render_line(actor.key, InteractionMode.MUTTER, fragment),
            echo_of=InteractionMode.MUTTER,
        )


@dataclass
class SayAction(Action):
    """Say something to the room."""

    key: str = "say"
    name: str = "Say"
    icon: str = "chat"
    category: str = "communication"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.AREA

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        text = kwargs.get("text", "")
        reply_to, reply_error = _parse_reply_target(kwargs)
        if reply_error is not None:
            return reply_error
        if not text:
            return ActionResult(success=False, message="Say what?")
        language, error = _resolve_spoken_language(actor, kwargs)
        if error is not None:
            return error
        sdm = context.scene_data if context else SceneDataManager()
        caller_state = sdm.initialize_state_for_object(actor)
        targets: list[ObjectDB] = kwargs.get("targets", [])
        target_personas = _characters_to_active_personas(targets) if targets else None

        def _broadcast() -> None:
            if language is None or language.is_universal:
                message_location(
                    caller_state, f'$You() $conj(say) "{text}"', echo_of=InteractionMode.SAY
                )
            else:
                _deliver_language_tagged_say(actor, text, language, sdm)

        client_request_id = kwargs.get("client_request_id")
        if client_request_id is not None:
            failure = _record_say_submission(
                actor,
                text=text,
                language=language,
                target_personas=target_personas,
                reply_to=reply_to,
                broadcast=_broadcast,
                client_request_id=client_request_id,
            )
            if failure is not None:
                return failure
        else:
            _broadcast()
            record_interaction(
                character=actor,
                content=text,
                mode=InteractionMode.SAY,
                target_personas=target_personas,
                language=language,
                reply_to=reply_to,
            )
        if targets:
            _flag_blocked_contact_for_targets(actor, targets, scene=_active_scene_for(actor))
        return ActionResult(success=True)


#: What ``ooc`` with nothing to say answers, on telnet and the web alike.
OOC_USAGE = "Usage: ooc <message>"


def _ooc_muters_in(location: ObjectDB, speaker: ObjectDB) -> list[ObjectDB]:
    """Who in ``location`` has OOC-muted the face ``speaker`` is wearing (#2087)."""
    from world.scenes.models import Persona  # noqa: PLC0415
    from world.scenes.mute_services import ooc_muter_account_ids  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    sheet = speaker.character_sheet
    if sheet is None:
        return []
    try:
        persona = active_persona_for_sheet(sheet)
    except Persona.DoesNotExist:
        return []
    muters = ooc_muter_account_ids(persona=persona)
    if not muters:
        return []
    return [obj for obj in location.contents if obj.db_account_id in muters]


@dataclass
class OOCSayAction(Action):
    """Speak out of character to everyone in the room (#4337).

    Arx 1's ``ooc``: ``<OOC> Name says: text``, the unmistakable way to tell a room
    something that is not the character talking (a hello, a question about the
    scene, a call for a GM). It replaced Evennia's ``ooc``, which unpuppeted the
    character into the stock account screen; nobody steps out of character on
    purpose any more, since login always puppets (ADR-0294).

    The audience is ``say``'s: the room, through the broadcast-exclusion seam, so
    a dreamside occupant does not hear the waking room. Anyone who has OOC-muted
    the face the speaker is wearing is left out; an account-level mute does not
    follow the player to another face here, because the room would notice the
    gap (``ooc_muter_account_ids``). Each listener sees their own name for the
    speaker, so a mask shows the mask. The line is typed ``ooc`` for the web
    feed and is not written to the scene log.
    """

    key: str = "ooc"
    name: str = "OOC"
    icon: str = "chat"
    category: str = "communication"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.AREA

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from core.wire_options import TextFrameType  # noqa: PLC0415
        from flows.service_functions.perception_registry import (  # noqa: PLC0415
            resolve_broadcast_exclusions,
        )

        text = (kwargs.get("text") or "").strip()
        if not text:
            return ActionResult(success=False, message=OOC_USAGE)
        location = actor.location
        if location is None:
            return ActionResult(success=False, message="There is nobody here to hear you.")
        options = {"type": TextFrameType.OOC.value}
        location.msg_contents(
            ("<OOC> {name} says: {message}", options),
            exclude=[
                actor,
                *resolve_broadcast_exclusions(location),
                *_ooc_muters_in(location, actor),
            ],
            from_obj=actor,
            mapping={"name": actor, "message": text},
        )
        actor.msg((f"<OOC> You say: {text}", options))
        return ActionResult(success=True)


@dataclass
class PoseAction(Action):
    """Pose/emote to the room.

    An optional Sineating (#5177) rides with the pose instead: ``sineating_role`` (``entreat``
    or ``perform``), ``sineating_partner_id`` (the other character's sheet id) and
    ``sineating_units``. It is checked before the pose posts and carried out once it has; the
    two parties are told privately and the room sees only the pose. A pose carries a
    reflection or a Sineating, not both.

    A reach (#5308) names the resonance the pose reaches for: ``reach_resonance_id``, any
    resonance, held or not. It is checked before the pose posts and written against the pose
    once it has; an endorsement of the pose pays that resonance. Only the poser sets it, and
    only as they pose.

    A mark (#5327) is a reach that also points at an act: ``reach_act_id`` is one of the poser's
    recorded acts, beside ``reach_resonance_id``. The pair is checked before the pose posts,
    and once it has the resonance is paid at once and the act is marked (no reach is written).
    The poser reads one private line; a mark that cannot pay leaves the pose standing and says
    why. In an ephemeral scene a mark pays nothing and the act stays pointable.

    An optional reflection (#5124) rides with the pose: ``reflect_choice`` (``EMBRACE`` or
    ``DISOWN``, or ``ABSOLVE``, ``CONDEMN`` or ``SUCCUMB`` for a burden) with one of
    ``reflect_grant_id`` (a kindled or succumbed-to-the-Mire deed), ``reflect_resonance_id``
    (the resonance unsettling the poser) or ``reflect_tether_id`` (the Mire the poser carries
    for one Sinner, #5177). It is checked before anything is posted, recorded once the pose
    is, and never reaches the room: only the pose text is broadcast.
    """

    key: str = "pose"
    name: str = "Pose"
    icon: str = "theater"
    category: str = "communication"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.AREA

    def get_prerequisites(self) -> list[Prerequisite]:
        # #2287 — a dead poser is bounded to the ghost emit window.
        return [GhostWindowPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        text = kwargs.get("text", "")
        reply_to, reply_error = _parse_reply_target(kwargs)
        if reply_error is not None:
            return reply_error
        targets = _pose_targets(actor, kwargs)
        place, place_error = _resolve_pose_place(actor, kwargs.get("place"))
        if place_error is not None:
            return place_error
        if not text:
            return ActionResult(success=False, message="Pose what?")
        pending, sineating, reach, mark, attachment_error = _pending_pose_attachment(actor, kwargs)
        if attachment_error is not None:
            return attachment_error
        sdm = context.scene_data if context else SceneDataManager()
        caller_state = sdm.initialize_state_for_object(actor)
        target_personas = _characters_to_active_personas(targets) if targets else None

        told: list[tuple[str, bool]] = []
        sineated: list[tuple[str, bool]] = []
        marked: list[tuple[str, bool]] = []

        first_pose: list[bool] = []

        def _reflect(interaction: Interaction | None) -> None:
            # Both ways of posting (with and without a request id) end here, once, and a
            # replayed request never gets here.
            _carry_attachments(actor, pending, sineating, interaction, told, sineated)
            _record_pose_reach(interaction, reach)
            _carry_pose_mark(actor, mark, interaction, marked)
            first_pose.append(True)

        client_request_id = kwargs.get("client_request_id")
        if client_request_id is not None:
            failure = _record_pose_submission(
                actor,
                text=text,
                place=place,
                target_personas=target_personas,
                reply_to=reply_to,
                broadcast=lambda: _broadcast_pose(actor, caller_state, text, place),
                client_request_id=client_request_id,
                after_first_acceptance=_reflect,
            )
            if failure is not None:
                return failure
        else:
            _broadcast_pose(actor, caller_state, text, place)
            interaction = record_interaction(
                character=actor,
                content=text,
                mode=InteractionMode.POSE,
                target_personas=target_personas,
                place=place,
                reply_to=reply_to,
            )
            _reflect(interaction)
        if targets:
            _flag_blocked_contact_for_targets(actor, targets, scene=_active_scene_for(actor))
        if first_pose:
            # #5177: a pose in a scene is when what the character carries pulls at them. Last,
            # and failure-safe, so it can never skip the attachments or the contact flag above.
            from world.magic.services.impulses import (  # noqa: PLC0415
                safe_refresh_impulses_for_character,
            )

            safe_refresh_impulses_for_character(actor)
        return _pose_result(told, sineated, marked)


def _pose_result(
    told: list[tuple[str, bool]],
    sineated: list[tuple[str, bool]] | None = None,
    marked: list[tuple[str, bool]] | None = None,
) -> ActionResult:
    """The pose's result: bare when it carried no reflection, Sineating or mark, else the lines
    the poser reads.

    The pose posted either way; ``reflection_recorded`` (or ``sineating_recorded``,
    ``mark_recorded``) tells a client whether to show the line as a success or as the error it
    is. ``mark_line`` is the mark's own line alone (empty when the pose carried no mark), so a
    client never has to pick it out of the joined message.
    """
    lines: list[str] = []
    data: dict[str, Any] = {}
    if sineated:
        line, happened = sineated[0]
        lines.append(line)
        data["sineating_recorded"] = happened
    elif told:
        line, recorded = told[0]
        lines.append(line)
        data["reflection_recorded"] = recorded
    if marked:
        line, paid = marked[0]
        lines.append(line)
        data["mark_recorded"] = paid
        data["mark_line"] = line
    elif lines:
        data["mark_line"] = ""
    if not lines:
        return ActionResult(success=True)
    return ActionResult(success=True, message="\n".join(lines), data=data)


def _pose_targets(actor: ObjectDB, kwargs: dict[str, Any]) -> list[ObjectDB]:
    """The characters a pose is directed at: ``targets``, plus any ``target_names`` a
    structured sender typed (the web composer's "@Name" targets), resolved the way the telnet
    "@Name" parser and the REST pose resolve them (#5124)."""
    from world.scenes.interaction_services import resolve_characters_by_name  # noqa: PLC0415

    targets: list[ObjectDB] = list(kwargs.get("targets", []))
    target_names = kwargs.get("target_names")
    if target_names and actor.location is not None:
        targets.extend(resolve_characters_by_name(target_names, actor.location))
    return targets


def _pending_pose_reflection(
    actor: ObjectDB, kwargs: dict[str, Any]
) -> tuple[PendingReflection | None, ActionResult | None]:
    """The checked reflection a pose asked for, or the refusal that stops the pose.

    A retry of a pose that already landed (its ``client_request_id`` is on the ledger) asks
    for no check: it is answered as the replay it is, and the reflection recorded the first
    time is not recorded again.
    """
    from world.magic.exceptions import ReflectionError  # noqa: PLC0415
    from world.magic.services.reflection import pending_reflection_from  # noqa: PLC0415
    from world.scenes.interaction_services import pose_already_submitted  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    request_id = kwargs.get("client_request_id")
    if request_id is not None and actor.character_sheet is not None:
        persona = active_persona_for_sheet(actor.character_sheet)
        if persona is not None and pose_already_submitted(persona, request_id):
            return None, None
    try:
        return pending_reflection_from(actor.character_sheet, kwargs), None
    except ReflectionError as exc:
        return None, ActionResult(success=False, message=exc.user_message)


def _carry_attachments(  # noqa: PLR0913 - the actor, both attachments, the row, both result lists
    actor: ObjectDB,
    reflection: PendingReflection | None,
    sineating: PendingSineating | None,
    interaction: Interaction | None,
    told: list[tuple[str, bool]],
    sineated: list[tuple[str, bool]],
) -> None:
    """Carry out whatever a posted pose carried, collecting the line the poser reads."""
    if reflection is not None:
        told.append(_record_pose_reflection(actor, reflection, interaction))
    if sineating is not None:
        sineated.append(run_pose_sineating(actor, sineating))


def _pending_pose_attachment(
    actor: ObjectDB, kwargs: dict[str, Any]
) -> tuple[
    PendingReflection | None,
    PendingSineating | None,
    PendingReach | None,
    PendingMark | None,
    ActionResult | None,
]:
    """The checked reflection or Sineating, the reach (#5308) and the mark (#5327), a pose
    carries, or the refusal that stops the pose."""
    reflection, refusal = _pending_pose_reflection(actor, kwargs)
    if refusal is not None:
        return None, None, None, None, refusal
    sineating, refusal = _pending_pose_sineating(actor, kwargs, reflection)
    if refusal is not None:
        return None, None, None, None, refusal
    reach, refusal = _pending_pose_reach(actor, kwargs)
    if refusal is not None:
        return None, None, None, None, refusal
    mark, refusal = _pending_pose_mark(actor, kwargs)
    if refusal is not None:
        return None, None, None, None, refusal
    return reflection, sineating, reach, mark, None


def _record_pose_reach(interaction: Interaction | None, reach: PendingReach | None) -> None:
    """Write the reach a posted pose carried (#5308). A pose in an ephemeral scene leaves no
    row to reach from, so nothing is written."""
    from world.magic.services.reach import record_pending_reach  # noqa: PLC0415

    if reach is not None and interaction is not None:
        record_pending_reach(interaction, reach)


def _pending_pose_reach(
    actor: ObjectDB, kwargs: dict[str, Any]
) -> tuple[PendingReach | None, ActionResult | None]:
    """The checked reach a pose asked for, or the refusal that stops the pose (#5308).

    A replayed ``client_request_id`` asks for no check: what the first send did stands.
    """
    from world.magic.exceptions import ReachError  # noqa: PLC0415
    from world.magic.services.reach import pending_reach_from  # noqa: PLC0415
    from world.scenes.interaction_services import pose_already_submitted  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    if kwargs.get("reach_resonance_id") is None:
        return None, None
    sheet = actor.character_sheet
    request_id = kwargs.get("client_request_id")
    if sheet is not None and request_id is not None:
        persona = active_persona_for_sheet(sheet)
        if persona is not None and pose_already_submitted(persona, request_id):
            return None, None
    try:
        return pending_reach_from(kwargs), None
    except ReachError as exc:
        return None, ActionResult(success=False, message=exc.user_message)


def _carry_pose_mark(
    actor: ObjectDB,
    mark: PendingMark | None,
    interaction: Interaction | None,
    marked: list[tuple[str, bool]],
) -> None:
    """Record the mark a posted pose carried, if any, collecting the line the poser reads."""
    if mark is not None:
        marked.append(_record_pose_mark(actor, mark, interaction))


def _record_pose_mark(
    actor: ObjectDB, mark: PendingMark, interaction: Interaction | None
) -> tuple[str, bool]:
    """Record the mark a posted pose carried (#5327); returns the line the poser reads and
    whether the mark paid.

    The pose cannot be un-posted, so it stands whatever happens: a mark that cannot pay says
    why and leaves the act on the poser's list. A pose in an ephemeral scene has no row to
    carry the mark, so it pays nothing.
    """
    from world.magic.exceptions import MarkError  # noqa: PLC0415
    from world.magic.services.marking import record_pending_mark  # noqa: PLC0415

    try:
        result = record_pending_mark(actor.character_sheet, mark, interaction=interaction)
    except MarkError as exc:
        return exc.user_message, False
    return result.line, result.paid


def _pending_pose_mark(
    actor: ObjectDB, kwargs: dict[str, Any]
) -> tuple[PendingMark | None, ActionResult | None]:
    """The checked mark a pose asked for, or the refusal that stops the pose (#5327).

    A replayed ``client_request_id`` asks for no check: what the first send did stands.
    """
    from world.magic.exceptions import MarkError  # noqa: PLC0415
    from world.magic.services.marking import pending_mark_from  # noqa: PLC0415
    from world.scenes.interaction_services import pose_already_submitted  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    if kwargs.get("reach_act_id") is None:
        return None, None
    sheet = actor.character_sheet
    if sheet is None:
        return None, ActionResult(success=False, message="You need a character to mark an act.")
    request_id = kwargs.get("client_request_id")
    if request_id is not None:
        persona = active_persona_for_sheet(sheet)
        if persona is not None and pose_already_submitted(persona, request_id):
            return None, None
    try:
        return pending_mark_from(sheet, kwargs), None
    except MarkError as exc:
        return None, ActionResult(success=False, message=exc.user_message)


def _pending_pose_sineating(
    actor: ObjectDB, kwargs: dict[str, Any], reflection: PendingReflection | None
) -> tuple[PendingSineating | None, ActionResult | None]:
    """The checked Sineating a pose asked for, or the refusal that stops the pose (#5177).

    Checked before anything is posted, as a reflection is: a plea or a ritual that cannot
    happen costs the writer nothing. A pose carries a reflection or a Sineating, not both.
    A replayed ``client_request_id`` asks for no check; what the first send did stands.
    """
    from world.magic.exceptions import SoulTetherError  # noqa: PLC0415
    from world.magic.services.sineating import (  # noqa: PLC0415
        BOTH_REFLECTION_AND_SINEATING,
        pending_sineating_from,
    )
    from world.scenes.interaction_services import pose_already_submitted  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    request_id = kwargs.get("client_request_id")
    if request_id is not None and actor.character_sheet is not None:
        persona = active_persona_for_sheet(actor.character_sheet)
        if persona is not None and pose_already_submitted(persona, request_id):
            return None, None
    try:
        pending = pending_sineating_from(actor.character_sheet, kwargs)
    except SoulTetherError as exc:
        return None, ActionResult(success=False, message=exc.user_message)
    if pending is not None and reflection is not None:
        return None, ActionResult(success=False, message=BOTH_REFLECTION_AND_SINEATING)
    return pending, None


def _record_pose_reflection(
    actor: ObjectDB, pending: PendingReflection, interaction: Interaction | None
) -> tuple[str, bool]:
    """Record the reflection a pose carried, once the pose itself is down; returns the line
    the poser reads and whether the reflection was recorded."""
    from world.magic.exceptions import ReflectionError  # noqa: PLC0415
    from world.magic.services.reflection import (  # noqa: PLC0415
        record_pending_reflection,
        recorded_line,
    )

    try:
        reflection = record_pending_reflection(actor.character_sheet, pending, writing=interaction)
    except ReflectionError as exc:
        # The pose cannot be un-posted, so it stands and the poser is told why the
        # reflection was not recorded.
        line = f"Your pose was posted, but your reflection was not recorded: {exc.user_message}"
        return line, False
    return recorded_line(reflection), True


@dataclass
class EmitAction(Action):
    """Emit raw text to the room (no character name prepended).

    Classic MUSH emit: the text appears as-is in the scene feed. The interaction
    metadata still records who wrote it (persona, thumbnail, etc.), but the
    content itself has no automatic name prefix — the writer controls the
    entire text. ``gm_prompt_id`` (#4101) links the row to the GM prompt it
    narrates.
    """

    key: str = "emit"
    name: str = "Emit"
    icon: str = "scroll"
    category: str = "communication"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.AREA

    def get_prerequisites(self) -> list[Prerequisite]:
        # #2287 — a dead emitter is bounded to the ghost emit window.
        return [GhostWindowPrerequisite(), NarratesOwnPromptPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        text = kwargs.get("text", "")
        reply_to, reply_error = _parse_reply_target(kwargs)
        if reply_error is not None:
            return reply_error
        prompt, prompt_error = _narration_prompt(actor, kwargs)
        if prompt_error is not None:
            return prompt_error
        targets: list[ObjectDB] = kwargs.get("targets", [])
        place = kwargs.get("place")
        if not text:
            return ActionResult(success=False, message="Emit what?")

        sdm = context.scene_data if context else SceneDataManager()
        caller_state = sdm.initialize_state_for_object(actor)

        target_personas = _characters_to_active_personas(targets) if targets else None

        # Broadcast raw text — no funcparser, no name prepend.
        # A place-scoped row is receiver-scoped (record_interaction fills its
        # receivers from PlacePresence) while this room line is not, so the line
        # stays untagged there until room delivery is place-aware (#3933).
        linker = _prompt_linker(prompt)
        message_location(
            caller_state, text, echo_of=InteractionMode.EMIT if place is None else None
        )
        record_interaction(
            character=actor,
            content=text,
            mode=InteractionMode.EMIT,
            target_personas=target_personas,
            place=place,
            reply_to=reply_to,
            on_created=linker,
        )

        return linker.result() if linker is not None else ActionResult(success=True)


@dataclass
class MutterAction(Action):
    """Mutter to specific listeners; the room catches a fragment (#905).

    Receivers hear (and their feed records) the full text; everyone else
    in the room hears a random-word fragment — which is also what the
    public log shows, preserving the never-more-than-the-room-heard
    invariant. Risky by design: the wrong word can leak.
    """

    key: str = "mutter"
    name: str = "Mutter"
    icon: str = "whisper"
    category: str = "communication"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.AREA

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.scenes.interaction_services import (  # noqa: PLC0415
            mutter_fragment,
            record_mutter_interaction,
        )

        text = kwargs.get("text", "")
        reply_to, reply_error = _parse_reply_target(kwargs)
        if reply_error is not None:
            return reply_error
        receivers: list[ObjectDB] = kwargs.get("receivers", [])
        if not text:
            return ActionResult(success=False, message="Mutter what?")
        if not receivers:
            return ActionResult(success=False, message="Mutter to whom?")
        language, error = _resolve_spoken_language(actor, kwargs)
        if error is not None:
            return error
        sdm = context.scene_data if context else SceneDataManager()
        _deliver_mutter(
            actor,
            receivers,
            text=text,
            fragment=mutter_fragment(text),
            sdm=sdm,
        )
        record_mutter_interaction(
            character=actor,
            receivers=receivers,
            content=text,
            language=language,
            reply_to=reply_to,
        )
        return ActionResult(success=True)


@dataclass
class PemitAction(Action):
    """STARTING-tier GM private narrative emit to an explicit receiver list (#906).

    The Arx 1 "pemit": GM narration delivered only to the listed characters.
    Rides the receiver-scoped EMIT path — the persisted interaction carries
    receiver rows, so the feed shows it only to those receivers (and the
    scene log never shows more than the room heard). Works inside scenes
    (record_interaction resolves the active scene from the room) and at
    room level outside scenes (persists scene-less), per the #906 ruling.

    Gated on ``MinimumGMLevelPrerequisite(GMLevel.STARTING)`` (#2117; staff
    bypass preserved) -- pure private narration, no state change beyond a
    receiver-scoped Interaction row, same risk class as staging. ``gm_prompt_id``
    (#4101) links the row to the GM prompt it narrates.
    """

    key: str = "pemit"
    name: str = "Private Emit"
    icon: str = "scroll"
    category: str = "communication"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.AREA

    def get_prerequisites(self) -> list[Prerequisite]:
        return [MinimumGMLevelPrerequisite(GMLevel.STARTING), NarratesOwnPromptPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        text = kwargs.get("text", "")
        reply_to, reply_error = _parse_reply_target(kwargs)
        if reply_error is not None:
            return reply_error
        prompt, prompt_error = _narration_prompt(actor, kwargs)
        if prompt_error is not None:
            return prompt_error
        receivers: list[ObjectDB] = kwargs.get("receivers", [])
        if not text:
            return ActionResult(success=False, message="Pemit what?")
        if not receivers:
            return ActionResult(success=False, message="Pemit to whom?")

        receiver_personas = _characters_to_active_personas(receivers)
        if receiver_personas is None:
            return ActionResult(success=False, message="No valid receivers found.")

        sdm = context.scene_data if context else SceneDataManager()

        linker = _prompt_linker(prompt)
        # Direct delivery to each receiver only — never the whole room.
        for receiver in receivers:
            receiver_state = sdm.initialize_state_for_object(receiver)
            send_message(receiver_state, text, echo_of=InteractionMode.EMIT)
        # The narrator's own echo (#3657: telnet showed the GM nothing; the web
        # drops it as an echo of the receiver-scoped row it already has).
        names = ", ".join(persona.name for persona in receiver_personas)
        send_message(
            sdm.initialize_state_for_object(actor),
            f"You narrate to {names}: {text}",
            echo_of=InteractionMode.EMIT,
        )

        record_interaction(
            character=actor,
            content=text,
            mode=InteractionMode.EMIT,
            receivers=receiver_personas,
            reply_to=reply_to,
            on_created=linker,
        )

        return linker.result() if linker is not None else ActionResult(success=True)


def _deliver_whisper(
    caller_state: BaseState,
    target_state: BaseState,
    text: str,
    language: Language | None,
) -> None:
    """Deliver the private telnet line and the sender's echo once."""
    # Direct message: Evennia msg() to the target only, for telnet clients.
    # Web clients receive this as a TEXT message but should prefer the
    # structured INTERACTION payload from push_interaction. Receiver-scoped
    # trust (#2993): the chosen audience always gets the full text, never garbled.
    language_name = None if language is None or language.is_universal else language.name
    send_message(
        target_state,
        render_line(
            caller_state.get_display_name(looker=target_state),
            InteractionMode.WHISPER,
            text,
            language_name=language_name,
        ),
        echo_of=InteractionMode.WHISPER,
    )
    # The whisperer's own echo (#3657: telnet showed them nothing; the web
    # drops it as an echo of the row it already has).
    spoken_in = f" in {language_name}" if language_name else ""
    send_message(
        caller_state,
        f'You whisper to {target_state.get_display_name(looker=caller_state)}{spoken_in}, "{text}"',
        echo_of=InteractionMode.WHISPER,
    )


@dataclass
class WhisperAction(Action):
    """Whisper to a specific target."""

    key: str = "whisper"
    name: str = "Whisper"
    icon: str = "whisper"
    category: str = "communication"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SINGLE
    target_kind: TargetKind | None = TargetKind.PERSONA
    target_filters: TargetFilters | None = _WHISPER_TARGET_FILTERS

    objectdb_target_kwargs: ClassVar[frozenset[str]] = frozenset({"target"})

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        target = kwargs.get("target")
        text = kwargs.get("text", "")
        reply_to, reply_error = _parse_reply_target(kwargs)
        if reply_error is not None:
            return reply_error
        if target is None or not text:
            return ActionResult(success=False, message="Whisper what to whom?")

        language, error = _resolve_spoken_language(actor, kwargs)
        if error is not None:
            return error

        sdm = context.scene_data if context else SceneDataManager()
        caller_state = sdm.initialize_state_for_object(actor)
        target_state = sdm.initialize_state_for_object(target)

        client_request_id = kwargs.get("client_request_id")
        if client_request_id is not None:
            from world.scenes.interaction_services import (  # noqa: PLC0415
                idempotent_record_interaction,
            )

            # Whisper authorship is the primary persona, never the active/worn face
            # (mirrors record_whisper_interaction's own resolution -- #981's
            # active-persona substitution is not applied here, unlike say/pose).
            persona = actor.sheet_data.primary_persona
            # Target identity (#3760 review fix): a plain content-only comparison
            # silently misclassified "same text, different target" as a
            # legitimate replay -- nothing (re-)delivered to the new intended
            # target, caller told it succeeded. target_personas is M2M (via
            # InteractionTargetPersona), so it can't be a plain
            # getattr(stored, field) == value comparison; see
            # idempotent_record_interaction's _comparison_fields_match.
            target_persona_pk = target.sheet_data.primary_persona.pk
            result = idempotent_record_interaction(
                persona=persona,
                client_request_id=client_request_id,
                comparison_fields={
                    "content": text,
                    "target": lambda stored: (
                        frozenset(p.pk for p in stored.target_personas.all()) == {target_persona_pk}
                    ),
                },
                # record_whisper_interaction, not record_interaction: its
                # ephemeral-scene branch scopes the real-time push to
                # [character, target] rather than broadcasting to the whole
                # scene, which record_interaction would do (a privacy leak
                # for a whisper) -- see idempotent_record_interaction's
                # record_fn docstring.
                record_fn=record_whisper_interaction,
                character=actor,
                target=target,
                content=text,
                language=language,
                reply_to=reply_to,
            )
            if result.conflict:
                return ActionResult(
                    success=False, message="This request id was already used for different text."
                )
            # Broadcast AFTER recording, gated on `not result.replayed` -- same
            # fix as submit_pose (#3760): a retry must not double-deliver even
            # though the DB side is correctly deduped.
            if not result.replayed:
                _deliver_whisper(caller_state, target_state, text, language)
        else:
            # Record + push: creates DB record and sends structured WebSocket payload.
            # Web clients use this for the scene feed display.
            _deliver_whisper(caller_state, target_state, text, language)
            record_whisper_interaction(
                character=actor,
                target=target,
                content=text,
                language=language,
                reply_to=reply_to,
            )

        # #1278/#2088 — flag circumvention attempts: a blocked player whispering the
        # blocker via another identity. No-op when no active block exists.
        _flag_blocked_contact_for_targets(actor, [target], scene=_active_scene_for(actor))

        return ActionResult(success=True)

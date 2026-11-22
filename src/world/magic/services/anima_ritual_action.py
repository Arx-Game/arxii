"""Anima ritual resolver registration, and the ritual with a partner (#5181).

Registers the "anima_ritual" action_key with the scenes resolver registry.
On accept, applies the check outcome via apply_anima_ritual_outcome(), then earns the
ritual's resonance and touches the partner's fatigue via apply_ritual_bond().

A player asks a partner to take part with ``start_partner_ritual`` (the web scene-action
create and telnet ``ritual anima <partner>`` both call it). The request is the ordinary
``SceneActionRequest`` consent flow; a request with no ActionTemplate (which is what a ritual
has: it rolls its own check) is resolved by ``resolve_ritual_request``.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from world.magic.models import CharacterAnima
from world.scenes.action_resolvers import register_resolver

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import Ritual
    from world.magic.types.ritual import RitualBond, RitualOutcome
    from world.scenes.action_models import SceneActionRequest
    from world.scenes.models import Persona, Scene
    from world.scenes.types import EnhancedSceneActionResult

ANIMA_RITUAL_ACTION_KEY = "anima_ritual"
_NO_RITUAL = "You have no anima ritual to perform."
_NOT_SET_UP = "Your anima ritual is not set up yet."
_NEEDS_PARTNER = "Name someone else to take part in your ritual."
_ALREADY_PERFORMED = "You have already performed your anima ritual in this scene."
_ALREADY_ASKED = "You already have a ritual waiting for an answer in this scene."
_NOT_TOGETHER = "You and your partner must both be in this scene, in the same place."
_ONE_PLAYER = "You cannot perform your ritual with another character you play."


def _in_scene_together(
    initiator_sheet: CharacterSheet, partner_sheet: CharacterSheet, scene: Scene
) -> bool:
    """True when both characters stand in the same place and ``scene`` is the live scene
    there. Reads the one rule Sineating uses (``shared_active_scene``)."""
    from world.magic.services.soul_tether import shared_active_scene  # noqa: PLC0415

    shared = shared_active_scene(initiator_sheet, partner_sheet)
    return shared is not None and shared.pk == scene.pk


def check_partner_ritual(
    *, initiator_persona: Persona, target_persona: Persona | None, scene: Scene
) -> Ritual:
    """The initiator's own anima ritual, after every refusal a request for a partner can meet.

    Raises:
        ValidationError: no ritual or one not set up, no partner or the performer themselves,
            a partner who is not in this scene and the same place, a partner the same account
            plays, the ritual already performed in this scene, or already asked of someone and
            waiting.
    """
    from world.magic.services.anima import (  # noqa: PLC0415
        get_character_anima_ritual,
        has_performed_anima_ritual_in_scene,
    )
    from world.roster.services.npc_lending import played_by_one_account  # noqa: PLC0415
    from world.scenes.action_constants import ActionRequestStatus  # noqa: PLC0415
    from world.scenes.action_models import SceneActionRequest  # noqa: PLC0415

    sheet = initiator_persona.character_sheet
    ritual = get_character_anima_ritual(sheet.character)
    if ritual is None:
        raise ValidationError(_NO_RITUAL)
    config = ritual.check_config_or_none
    if config is None or config.check_type is None:
        raise ValidationError(_NOT_SET_UP)
    if target_persona is None or target_persona.character_sheet_id == sheet.pk:
        raise ValidationError(_NEEDS_PARTNER)
    partner_sheet = target_persona.character_sheet
    if not _in_scene_together(sheet, partner_sheet, scene):
        raise ValidationError(_NOT_TOGETHER)
    if played_by_one_account(sheet, partner_sheet):
        raise ValidationError(_ONE_PLAYER)
    if has_performed_anima_ritual_in_scene(ritual=ritual, scene=scene):
        raise ValidationError(_ALREADY_PERFORMED)
    waiting = SceneActionRequest.objects.filter(
        scene=scene,
        initiator_persona__character_sheet=sheet,
        action_key=ANIMA_RITUAL_ACTION_KEY,
        status=ActionRequestStatus.PENDING,
    )
    if waiting.exists():
        raise ValidationError(_ALREADY_ASKED)
    return ritual


def start_partner_ritual(
    *, scene: Scene, initiator_persona: Persona, target_persona: Persona | None
) -> SceneActionRequest:
    """Ask ``target_persona`` to take part in the initiator's anima ritual.

    Checks the refusals (``check_partner_ritual``), then opens the ordinary consent request
    carrying the ritual's check as its snapshot. A partner who is an NPC answers at once, as
    for any request; a player's partner is asked and the request waits.

    Raises:
        ValidationError: see ``check_partner_ritual``, and the request's own refusals.
    """
    from world.scenes.action_services import create_action_request  # noqa: PLC0415

    ritual = check_partner_ritual(
        initiator_persona=initiator_persona, target_persona=target_persona, scene=scene
    )
    return create_action_request(
        scene=scene,
        initiator_persona=initiator_persona,
        target_persona=target_persona,
        action_key=ANIMA_RITUAL_ACTION_KEY,
        ritual_id=ritual.pk,
    )


def ritual_consent_sentence(action_request: SceneActionRequest) -> str:
    """The sentence a partner's consent prompt carries about their fatigue, or blank (#5181).

    Only a ritual request names a resonance, so any other request reads blank. The resonance
    read is ``snapshot_resonance``, the ritual's outward pick (Celestial or Abyssal): the one
    that reaches the partner (#5280).
    """
    from world.magic.services.ritual_bond import (  # noqa: PLC0415
        performer_holds,
        ritual_partner_effect_sentence,
    )

    if action_request.action_key != ANIMA_RITUAL_ACTION_KEY:
        return ""
    resonance = action_request.snapshot_resonance
    # A resonance the performer does not hold does nothing to the partner, so say nothing.
    if not performer_holds(action_request.initiator_persona.character_sheet, resonance):
        return ""
    return ritual_partner_effect_sentence(resonance)


def is_templateless_ritual_request(action_request: SceneActionRequest) -> bool:
    """True for a ritual request that rolls the ritual's own check instead of a template's."""
    return (
        action_request.action_key == ANIMA_RITUAL_ACTION_KEY
        and action_request.snapshot_ritual_id is not None
        and action_request.action_template_id is None
    )


def resolve_ritual_request(action_request: SceneActionRequest) -> None:
    """Resolve an accepted ritual request: roll the ritual's own check and apply it.

    The ritual's check type and difficulty were snapshotted when the request was made. The
    request is marked resolved; the performer and the partner are told privately once the
    surrounding transaction commits. A ritual already performed in the scene since (two
    requests raced) is resolved with no effect, and so is one whose partner is no longer in the
    scene and the same place as the performer.
    """
    from world.checks.services import perform_check_with_modifiers  # noqa: PLC0415
    from world.magic.constants import MagicActivity  # noqa: PLC0415
    from world.magic.exceptions import RitualAlreadyPerformedThisScene  # noqa: PLC0415
    from world.magic.services.anima import has_performed_anima_ritual_in_scene  # noqa: PLC0415
    from world.magic.services.magic_skills import activity_skill_terms  # noqa: PLC0415
    from world.scenes.action_constants import ActionRequestStatus  # noqa: PLC0415

    ritual = action_request.snapshot_ritual
    sheet = action_request.initiator_persona.character_sheet
    difficulty = action_request.snapshot_target_difficulty or 0
    target = action_request.target_persona
    together = target is None or _in_scene_together(
        sheet, target.character_sheet, action_request.scene
    )
    if together and not has_performed_anima_ritual_in_scene(
        ritual=ritual, scene=action_request.scene
    ):
        check_result = perform_check_with_modifiers(
            sheet.character,
            check_type=action_request.snapshot_check_type,
            target_difficulty=difficulty,
            scene=action_request.scene,
            extra_traits=activity_skill_terms(MagicActivity.ANIMA_RITUAL),
        )
        # A request that raced this one and won the once-per-scene rule inside the lock pays
        # nothing; this one is resolved with no effect.
        with contextlib.suppress(RitualAlreadyPerformedThisScene):
            apply_ritual_to_request(action_request, ritual, check_result.outcome)
    action_request.status = ActionRequestStatus.RESOLVED
    action_request.resolved_at = timezone.now()
    action_request.resolved_difficulty = difficulty
    action_request.save(update_fields=["status", "resolved_at", "resolved_difficulty"])


def apply_ritual_to_request(
    action_request: SceneActionRequest, ritual: Ritual, outcome: object
) -> tuple[RitualOutcome, RitualBond | None]:
    """Apply a rolled outcome for ``action_request``: anima and Soulfray, then the bond.

    The partner is the request's target. The bond (resonance earned, the partner's fatigue)
    runs after the anima outcome, and only when there is a partner. Both are told privately
    after commit.
    """
    from world.magic.services.anima import apply_anima_ritual_outcome  # noqa: PLC0415
    from world.magic.services.ritual_bond import apply_ritual_bond  # noqa: PLC0415

    performer = action_request.initiator_persona.character_sheet
    target = action_request.target_persona
    partner = target.character_sheet if target is not None else None
    with transaction.atomic():
        ritual_outcome = apply_anima_ritual_outcome(
            ritual=ritual,
            outcome=outcome,
            scene=action_request.scene,
            character_sheet=performer,
            partner_sheet=partner,
        )
        bond = None
        if partner is not None:
            bond = apply_ritual_bond(
                performer, partner, ritual, outcome, action_request.snapshot_resonance
            )
            _tell_both(action_request, performer, partner, bond)
    return ritual_outcome, bond


def _tell_both(
    action_request: SceneActionRequest,
    performer: CharacterSheet,
    partner: CharacterSheet,
    bond: RitualBond,
) -> None:
    """Tell the performer what their ritual did and the partner what it did to them, privately,
    once the transaction commits. The room is told nothing: the performance is the pose."""
    from world.magic.services.ritual_bond import (  # noqa: PLC0415
        partner_ritual_line,
        performer_ritual_line,
    )
    from world.magic.services.soul_tether import send_stored_notice  # noqa: PLC0415

    initiator_name = action_request.initiator_persona.name
    partner_name = action_request.target_persona.name
    performer_line = performer_ritual_line(bond, partner_name)
    if performer_line:
        send_stored_notice(performer, performer_line, ooc_note="Anima ritual")
    partner_line = partner_ritual_line(bond, initiator_name)
    if partner_line:
        send_stored_notice(partner, partner_line, ooc_note="Anima ritual")


def _resolve_anima_ritual(
    action_request: SceneActionRequest,
    result: EnhancedSceneActionResult,
) -> None:
    """Apply anima ritual outcome when an accepted request has action_key='anima_ritual'.

    Reads the Ritual from action_request.snapshot_ritual (populated at request
    creation time). Falls back to looking up the initiator's authored SCENE_ACTION
    Ritual when snapshot_ritual is absent (legacy requests).
    """
    from world.magic.constants import RitualExecutionKind  # noqa: PLC0415
    from world.magic.models.rituals import Ritual  # noqa: PLC0415

    initiator_sheet = action_request.initiator_persona.character_sheet

    # Prefer the snapshot copy; fall back to live authorship lookup.
    ritual = action_request.snapshot_ritual
    if ritual is None:
        ritual = (
            Ritual.objects.filter(
                author_account=initiator_sheet.character.db_account,
                execution_kind=RitualExecutionKind.SCENE_ACTION,
            )
            .select_related("check_config")
            .first()
        )

    if ritual is None:
        return  # silently no-op on malformed request

    # Ensure the config is loaded (may already be via select_related above).
    if ritual.check_config_or_none is None:
        return  # SCENE_ACTION ritual missing config — skip

    main_result = result.action_resolution.main_result
    if main_result is None or main_result.check_result is None:
        return  # no check outcome to apply

    outcome = main_result.check_result.outcome

    from world.magic.exceptions import RitualAlreadyPerformedThisScene  # noqa: PLC0415

    try:
        ritual_outcome, _bond = apply_ritual_to_request(action_request, ritual, outcome)
    except RitualAlreadyPerformedThisScene:
        return  # a racing request already performed it this scene; this one pays nothing

    # Attach a transient payload so the response serializer can include
    # anima_recovery for the initiator without a second DB query.
    anima = CharacterAnima.objects.get(character=initiator_sheet)
    action_request._anima_recovery_payload = {  # noqa: SLF001
        "recovered": ritual_outcome.anima_recovered,
        "soulfray_reduced": ritual_outcome.severity_reduced,
        "new_pool": anima.current,
        "patron_bonus": ritual_outcome.patron_bonus,
        "patron_name": ritual_outcome.patron_name,
    }


register_resolver("anima_ritual", _resolve_anima_ritual)

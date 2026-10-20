"""Worship actions (#3777): performing a being's rite in a live scene."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from evennia.objects.models import ObjectDB

from actions.base import Action, ActionResult
from actions.types import ActionContext, TargetType


def _resolve_rite(kwargs: dict[str, Any]):
    """(rite, error): a ``rite`` object wins; else ``rite_name`` (+ ``being_name``)."""
    from world.worship.models import WorshipRite  # noqa: PLC0415

    rite = kwargs.get("rite")
    if rite is not None:
        return rite, None
    name = (kwargs.get("rite_name") or "").strip()
    if not name:
        return None, ActionResult(success=False, message="Perform which rite?")
    rites = WorshipRite.objects.filter(name__iexact=name, is_active=True, being__is_active=True)
    being_name = (kwargs.get("being_name") or "").strip()
    if being_name:
        rites = rites.filter(being__name__iexact=being_name)
    rites = list(rites.select_related("being", "kind")[:2])
    if not rites:
        return None, ActionResult(success=False, message="No such rite.")
    if len(rites) > 1:
        return None, ActionResult(
            success=False, message="More than one being has a rite by that name; name the being."
        )
    return rites[0], None


@dataclass
class PerformWorshipRiteAction(Action):
    """Perform one of a being's rites in the scene you stand in (#3777).

    kwargs:
        rite: A ``WorshipRite`` (required unless ``rite_name`` is given).
        rite_name: The rite's name; ``being_name`` narrows it when two beings
            share one.
    """

    key: str = "worship_rite"
    name: str = "Perform Rite"
    icon: str = "flame"
    category: str = "worship"
    target_type: TargetType = TargetType.SELF

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415
        from world.worship.exceptions import WorshipRiteError  # noqa: PLC0415
        from world.worship.live_services import route_live_answer  # noqa: PLC0415
        from world.worship.rite_services import perform_worship_rite  # noqa: PLC0415

        rite, error = _resolve_rite(kwargs)
        if error is not None:
            return error
        try:
            sheet = actor.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            sheet = None
        if sheet is None:
            return ActionResult(
                success=False, message="You have no character sheet to worship with."
            )
        scene = get_active_scene(actor.location)
        if scene is None:
            return ActionResult(success=False, message="A rite is performed in a live scene.")
        try:
            outcome = perform_worship_rite(sheet, rite, scene=scene)
        except WorshipRiteError as exc:
            return ActionResult(success=False, message=exc.user_message)
        _broadcast_rite_line(sheet, rite, actor)
        # #4333 slice 5: a GM running the scene may answer the rite live. A pledge's
        # closing rite never comes through here (ClosePledgeAction), so it never prompts.
        route_live_answer(outcome.performance, scene)
        parts = [
            f"You perform {rite.name} in the name of {rite.being.name}: {outcome.outcome_name}."
        ]
        if outcome.resonance_granted:
            parts.append(f"+{outcome.resonance_granted} {rite.resonance.resonance.name} resonance.")
        if outcome.favor_granted:
            parts.append(f"+{outcome.favor_granted} favor with {rite.being.name}.")
        elif outcome.favor_capped:
            parts.append(f"{rite.being.name} has already marked this rite of yours this week.")
        return ActionResult(
            success=True,
            message=" ".join(parts),
            data={
                "outcome": outcome.outcome_name,
                "resonance_granted": outcome.resonance_granted,
                "favor_granted": outcome.favor_granted,
                "favor_capped": outcome.favor_capped,
            },
        )


def _resolve_being(kwargs: dict[str, Any]):
    from world.worship.models import WorshippedBeing  # noqa: PLC0415

    being = kwargs.get("being")
    if isinstance(being, WorshippedBeing):
        return being, None
    if being not in (None, ""):
        # The web dispatches the being's pk (``PrayDialog``, the pledge and
        # sacrifice dialogs); telnet names it.
        row = WorshippedBeing.objects.filter(pk=being, is_active=True).first()
        if row is None:
            return None, ActionResult(success=False, message="No such being is known.")
        return row, None
    name = (kwargs.get("being_name") or "").strip()
    if not name:
        return None, ActionResult(success=False, message="Name the being.")
    being = WorshippedBeing.objects.filter(name__iexact=name, is_active=True).first()
    if being is None:
        return None, ActionResult(success=False, message=f"No being '{name}' is known.")
    return being, None


def _actor_persona_and_room(actor: ObjectDB):
    """(persona, room_profile, error) for the room the actor stands in."""
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    try:
        sheet = actor.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        sheet = None
    if sheet is None:
        return None, None, ActionResult(success=False, message="You have no character sheet.")
    try:
        persona = active_persona_for_sheet(sheet)
    except ObjectDoesNotExist:
        persona = None
    if persona is None:
        return None, None, ActionResult(success=False, message="You have no persona to act as.")
    location = actor.location
    profile = location.room_profile_or_none if location is not None else None
    if profile is None:
        return (
            None,
            None,
            ActionResult(success=False, message="This place has no room to consecrate."),
        )
    return persona, profile, None


@dataclass
class FoundShrineAction(Action):
    """Found a shrine of a being in a room you own (#3778). kwargs: ``being`` or ``being_name``."""

    key: str = "shrine_found"
    name: str = "Found Shrine"
    icon: str = "candle"
    category: str = "worship"
    target_type: TargetType = TargetType.SELF

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.worship.consecration_services import found_shrine  # noqa: PLC0415
        from world.worship.exceptions import ConsecrationError  # noqa: PLC0415

        persona, profile, error = _actor_persona_and_room(actor)
        if error is not None:
            return error
        being, error = _resolve_being(kwargs)
        if error is not None:
            return error
        try:
            found_shrine(profile, being, persona)
        except ConsecrationError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, message=f"You found a shrine of {being.name} here.")


@dataclass
class DissolveShrineAction(Action):
    """Dissolve the shrine in the room you stand in (#3778): its founder or the room's holder."""

    key: str = "shrine_dissolve"
    name: str = "Dissolve Shrine"
    icon: str = "candle-off"
    category: str = "worship"
    target_type: TargetType = TargetType.SELF

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.worship.consecration_services import dissolve_shrine, shrine_at  # noqa: PLC0415
        from world.worship.exceptions import ConsecrationError  # noqa: PLC0415

        persona, profile, error = _actor_persona_and_room(actor)
        if error is not None:
            return error
        shrine = shrine_at(profile)
        if shrine is None:
            return ActionResult(success=False, message="There is no shrine here.")
        try:
            dissolve_shrine(shrine, persona)
        except ConsecrationError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True, message=f"The shrine of {shrine.being.name} is dissolved."
        )


@dataclass
class DedicateTempleAction(Action):
    """Dedicate the building you stand in to a being (#3778): ``being`` or ``being_name``."""

    key: str = "temple_dedicate"
    name: str = "Dedicate Temple"
    icon: str = "church"
    category: str = "worship"
    target_type: TargetType = TargetType.SELF

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.worship.consecration_services import (  # noqa: PLC0415
            building_over,
            dedicate_temple,
        )
        from world.worship.exceptions import ConsecrationError  # noqa: PLC0415

        persona, profile, error = _actor_persona_and_room(actor)
        if error is not None:
            return error
        building = building_over(profile)
        if building is None:
            return ActionResult(success=False, message="This room is not inside a building.")
        being, error = _resolve_being(kwargs)
        if error is not None:
            return error
        try:
            dedicate_temple(building, being, persona)
        except ConsecrationError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True, message=f"You dedicate {building.area.name} as a temple of {being.name}."
        )


@dataclass
class RevokeTempleAction(Action):
    """Revoke the temple dedication of the building you stand in (#3778)."""

    key: str = "temple_revoke"
    name: str = "Revoke Temple"
    icon: str = "church-off"
    category: str = "worship"
    target_type: TargetType = TargetType.SELF

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.worship.consecration_services import revoke_temple, temple_over  # noqa: PLC0415
        from world.worship.exceptions import ConsecrationError  # noqa: PLC0415

        persona, profile, error = _actor_persona_and_room(actor)
        if error is not None:
            return error
        dedication = temple_over(profile)
        if dedication is None:
            return ActionResult(success=False, message="This building is not a temple.")
        try:
            revoke_temple(dedication, persona)
        except ConsecrationError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True, message=f"The temple of {dedication.being.name} is no longer dedicated."
        )


def _sheet_of(actor: ObjectDB):
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    try:
        return actor.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return None


@dataclass
class PrayAction(Action):
    """Pray to a being in your own words (#3779).

    kwargs:
        being / being_name: whom the prayer is to.
        text: the words.
    """

    key: str = "pray"
    name: str = "Pray"
    icon: str = "hands"
    category: str = "worship"
    target_type: TargetType = TargetType.SELF

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.worship.exceptions import PrayerError  # noqa: PLC0415
        from world.worship.prayer_services import pray  # noqa: PLC0415

        being, error = _resolve_being(kwargs)
        if error is not None:
            return error
        sheet = _sheet_of(actor)
        if sheet is None:
            return ActionResult(success=False, message="You have no character sheet to pray with.")
        try:
            outcome = pray(sheet, being, str(kwargs.get("text") or ""))
        except PrayerError as exc:
            return ActionResult(success=False, message=exc.user_message)
        parts = [f"You pray to {being.name}."]
        if outcome.devotion_granted:
            parts.append(f"An act of devotion: +{outcome.devotion_granted} favor.")
        if outcome.intervention is not None:
            parts.append(f"{being.name} answers.")
        return ActionResult(
            success=True,
            message=" ".join(parts),
            data={
                "prayer_id": outcome.prayer.pk,
                "devotion_granted": outcome.devotion_granted,
                "at_holy_site": outcome.at_holy_site,
                "dire_straits": outcome.dire_straits.kind,
                "answered": outcome.intervention is not None,
            },
        )


def _resolve_recipient(kwargs: dict[str, Any]):
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415

    recipient = kwargs.get("recipient")
    if recipient is not None:
        return recipient, None
    name = (kwargs.get("recipient_name") or "").strip()
    if not name:
        return None, ActionResult(success=False, message="Name the recipient.")
    sheet = CharacterSheet.objects.filter(character__db_key__iexact=name).first()
    if sheet is None:
        return None, ActionResult(success=False, message=f"No character '{name}' is known.")
    return sheet, None


def _optional_row(model, kwargs: dict[str, Any], key: str):
    """The row for ``kwargs[key]`` (an instance or a pk), None when absent, or an error."""
    value = kwargs.get(key)
    if value is None or value == "":
        return None, None
    if isinstance(value, model):
        return value, None
    row = model.objects.filter(pk=value).first()
    if row is None:
        return None, ActionResult(success=False, message=f"No {key} with id {value}.")
    return row, None


@dataclass
class SendVisionAction(Action):
    """A GM sends a character a vision from a being (#3779). Staff only.

    kwargs:
        recipient / recipient_name, being / being_name, body,
        reveal_source (bool), prayer (id), clue (id), episode (id).
    """

    key: str = "vision_send"
    name: str = "Send Vision"
    icon: str = "eye"
    category: str = "worship"
    target_type: TargetType = TargetType.SELF

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from evennia.accounts.models import AccountDB  # noqa: PLC0415

        from world.clues.models import Clue  # noqa: PLC0415
        from world.stories.models import Episode  # noqa: PLC0415
        from world.worship.exceptions import VisionError  # noqa: PLC0415
        from world.worship.models import Prayer  # noqa: PLC0415
        from world.worship.prayer_services import send_vision  # noqa: PLC0415

        # An actor's own account outranks a supplied one; the kwarg exists for the
        # account-scoped telnet face and tests, never for a client to assert staff.
        account = actor.account if actor is not None else kwargs.get("account")
        if not isinstance(account, AccountDB) or not account.is_staff:
            return ActionResult(success=False, message="Only staff send visions.")
        recipient, error = _resolve_recipient(kwargs)
        if error is not None:
            return error
        being, error = _resolve_being(kwargs)
        if error is not None:
            return error
        prayer, error = _optional_row(Prayer, kwargs, "prayer")
        if error is not None:
            return error
        clue, error = _optional_row(Clue, kwargs, "clue")
        if error is not None:
            return error
        episode, error = _optional_row(Episode, kwargs, "episode")
        if error is not None:
            return error
        try:
            vision = send_vision(
                recipient=recipient,
                being=being,
                body=str(kwargs.get("body") or ""),
                sent_by=account,
                reveal_source=bool(kwargs.get("reveal_source", False)),
                prayer=prayer,
                clue=clue,
                episode=episode,
            )
        except VisionError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=f"A vision from {being.name} reaches {recipient.character.key}.",
            data={"vision_id": vision.pk},
        )


def _broadcast_rite_line(sheet, rite, actor: ObjectDB) -> None:
    """The room line every performed rite gets (#4333): "<name> performs <rite>."
    It says nothing of the roll, the reward or a pledge the rite closes."""
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415
    from world.worship.pledge_services import broadcast_room_line  # noqa: PLC0415

    persona = active_persona_for_sheet(sheet)
    broadcast_room_line(persona, f"{persona.name} performs {rite.name}.", location=actor.location)


def _answer_live_rite(prompt, account, answer, kwargs: dict[str, Any]) -> ActionResult:
    """The scene GM answers a rite live: one answer, or one miracle (#4333 slice 5)."""
    from world.worship.exceptions import StewardAnswerError  # noqa: PLC0415
    from world.worship.live_services import send_live_answer  # noqa: PLC0415
    from world.worship.models import Miracle  # noqa: PLC0415

    miracle, error = _optional_row(Miracle, {"miracle": kwargs.get("miracle_id")}, "miracle")
    if error is not None:
        return error
    try:
        sent = send_live_answer(
            prompt,
            resolver=account,
            answer=answer,
            miracle=miracle,
            text=str(kwargs.get("text") or ""),
        )
    except StewardAnswerError as exc:
        return ActionResult(success=False, message=exc.user_message)
    if sent.vision is not None:
        _broadcast_live_onlooker_line(sent)
        message = f"Sent as a vision from {sent.being.name}."
    else:
        message = f"{sent.being.name} worked a miracle: {sent.miracle.name}."
    return ActionResult(
        success=True,
        message=message,
        data={
            "prompt_id": prompt.pk,
            "vision_id": sent.vision.pk if sent.vision is not None else None,
            "miracle_performance_id": sent.performance.pk if sent.performance else None,
            "held": False,
        },
    )


def _broadcast_live_onlooker_line(sent) -> None:
    """A live answer's ``onlooker_line``: the one room line others see of it, in the
    room the rite was performed in. Staff-authored, so a secret faith carries no
    player text."""
    line = sent.answer.onlooker_line.strip() if sent.answer is not None else ""
    character = sent.sheet.character
    if not line or character.location is None:
        return
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415
    from world.worship.pledge_services import broadcast_room_line  # noqa: PLC0415

    broadcast_room_line(active_persona_for_sheet(sent.sheet), line, location=character.location)


def _broadcast_onlooker_line(sheet, delivery, actor: ObjectDB) -> None:
    """An answer's ``onlooker_line`` (#4333 slice 3): the one room line others see
    of an answer, after the rite line, when the vision was delivered at the rite.
    It is staff-authored, so a secret faith's close still carries no player text;
    a held answer sends no room line when the pool later pays for it."""
    if delivery is None or delivery.vision is None or delivery.answer is None:
        return
    line = delivery.answer.onlooker_line.strip()
    if not line:
        return
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415
    from world.worship.pledge_services import broadcast_room_line  # noqa: PLC0415

    broadcast_room_line(active_persona_for_sheet(sheet), line, location=actor.location)


def _resolve_pledge(kwargs: dict[str, Any]):
    """(pledge, error): a ``pledge`` object or pk wins; else ``pledge_name`` + ``being_name``."""
    from world.worship.models import Pledge  # noqa: PLC0415

    pledge = kwargs.get("pledge")
    if isinstance(pledge, Pledge):
        return pledge, None
    if pledge not in (None, ""):
        row = Pledge.objects.filter(pk=pledge).select_related("being").first()
        if row is None:
            return None, ActionResult(success=False, message="No such pledge.")
        return row, None
    name = (kwargs.get("pledge_name") or "").strip()
    being_name = (kwargs.get("being_name") or "").strip()
    if not name or not being_name:
        return None, ActionResult(success=False, message="Name the being and the pledge.")
    row = (
        Pledge.objects.filter(name__iexact=name, being__name__iexact=being_name, is_active=True)
        .select_related("being")
        .first()
    )
    if row is None:
        return None, ActionResult(
            success=False, message=f"{being_name} offers no pledge called '{name}'."
        )
    return row, None


@dataclass
class TakePledgeAction(Action):
    """Pledge yourself to a being (#4333 slice 2).

    kwargs:
        pledge: a ``Pledge`` or its pk; or ``pledge_name`` with ``being_name``.
        prayer: optional words to the being, logged as a Prayer.
    """

    key: str = "pledge_take"
    name: str = "Pledge Yourself"
    icon: str = "hand-heart"
    category: str = "worship"
    target_type: TargetType = TargetType.SELF

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.worship.exceptions import PledgeError  # noqa: PLC0415
        from world.worship.pledge_services import (  # noqa: PLC0415
            earning_rate_breakdown,
            take_pledge,
        )

        pledge, error = _resolve_pledge(kwargs)
        if error is not None:
            return error
        sheet = _sheet_of(actor)
        if sheet is None:
            return ActionResult(success=False, message="You have no character sheet.")
        try:
            details = take_pledge(sheet, pledge, prayer_text=str(kwargs.get("prayer") or ""))
        except PledgeError as exc:
            return ActionResult(success=False, message=exc.user_message)
        rate = earning_rate_breakdown(sheet, pledge.being)
        weeks = "game week" if pledge.span_weeks == 1 else "game weeks"
        rate_parts = f"{rate.base}%"
        if rate.chosen_bonus:
            rate_parts += f" + {rate.chosen_bonus}% Chosen"
        if rate.modifiers:
            rate_parts += f" + {rate.modifiers}% favor earning modifiers"
        message = (
            f"You pledge yourself to {pledge.being.name}: {pledge.name}. "
            f"Favor target {pledge.favor_target} within {pledge.span_weeks} {weeks}. "
            f"Your earning rate with {pledge.being.name}: {rate.total}% ({rate_parts})."
        )
        return ActionResult(
            success=True,
            message=message,
            data={"pledge_details_id": details.pk, "project_id": details.project_id},
        )


@dataclass
class ClosePledgeAction(Action):
    """Close your open pledge with its closing rite (#4333 slice 2, design 3).

    Needs the favor target reached. Performed in the live scene where you stand;
    one is started if none runs. No shrine is required.
    """

    key: str = "pledge_close"
    name: str = "Close Pledge"
    icon: str = "flame"
    category: str = "worship"
    target_type: TargetType = TargetType.SELF

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.worship.exceptions import PledgeError, WorshipRiteError  # noqa: PLC0415
        from world.worship.pledge_services import (  # noqa: PLC0415
            close_pledge,
            open_pledge_for,
        )

        sheet = _sheet_of(actor)
        if sheet is None:
            return ActionResult(success=False, message="You have no character sheet.")
        details = open_pledge_for(sheet)
        if details is None:
            return ActionResult(success=False, message="You hold no open pledge.")
        project = details.project
        if project.current_progress < (project.threshold_target or 0):
            return ActionResult(
                success=False, message="Your pledge has not reached its favor target yet."
            )
        scene, error = _scene_to_close_in(actor, sheet)
        if error is not None:
            return error
        try:
            outcome = close_pledge(sheet, scene=scene)
        except (PledgeError, WorshipRiteError) as exc:
            return ActionResult(success=False, message=exc.user_message)
        _broadcast_rite_line(sheet, outcome.rite, actor)
        _broadcast_onlooker_line(sheet, outcome.delivery, actor)
        being = details.pledge.being.name
        if not outcome.resolved:
            message = (
                f"You close your pledge with {outcome.rite.name}: {outcome.outcome_name}. "
                f"{being} has not accepted it yet; you may try once more within the span."
            )
        else:
            message = (
                f"You close your pledge with {outcome.rite.name}: {outcome.outcome_name}. "
                f"Closing award for {outcome.outcome_name}: {outcome.award_base} base, at "
                f"{outcome.earning_rate_percent}% = +{outcome.award} favor with {being}."
                if outcome.award
                else f"You close your pledge with {outcome.rite.name}: {outcome.outcome_name}."
            )
        awaiting = outcome.delivery is not None and outcome.delivery.awaiting_steward
        if awaiting:
            # A stewarded being's table GM answers it (slice 4); the vision comes later.
            message += f" {being}'s answer will come later."
        return ActionResult(
            success=True,
            message=message,
            data={
                "outcome": outcome.outcome_name,
                "resolved": outcome.resolved,
                "award": outcome.award,
                "awaiting_steward": awaiting,
            },
        )


def _scene_to_close_in(actor: ObjectDB, sheet):
    """(scene, error): the room's live scene with the actor in it, starting or
    joining one through ``StartSceneAction`` when needed."""
    from actions.definitions.scenes import StartSceneAction  # noqa: PLC0415
    from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415
    from world.worship.rite_services import scene_participant  # noqa: PLC0415

    scene = get_active_scene(actor.location)
    if scene is None or not scene_participant(scene, sheet):
        started = StartSceneAction().run(actor=actor)
        if not started.success:
            return None, started
        scene = get_active_scene(actor.location)
    if scene is None:
        return None, ActionResult(success=False, message="A pledge is closed in a live scene.")
    return scene, None


@dataclass
class SacrificeAction(Action):
    """Sacrifice items you carry at a being's shrine or temple (#4333 slice 2).

    kwargs:
        item_ids: ItemInstance pks (web), or item_names to search your inventory (telnet).
        being / being_name: optional, when the place is holy to two beings.
    """

    key: str = "sacrifice"
    name: str = "Sacrifice"
    icon: str = "flame"
    category: str = "worship"
    target_type: TargetType = TargetType.SELF

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.ceremonies.services import sacrifice_items  # noqa: PLC0415
        from world.worship.exceptions import PledgeError  # noqa: PLC0415

        sheet = _sheet_of(actor)
        if sheet is None:
            return ActionResult(success=False, message="You have no character sheet.")
        being = None
        if kwargs.get("being") or kwargs.get("being_name"):
            being, error = _resolve_being(kwargs)
            if error is not None:
                return error
        items, error = _carried_items(actor, kwargs)
        if error is not None:
            return error
        try:
            outcome = sacrifice_items(sheet, items, being=being)
        except PledgeError as exc:
            return ActionResult(success=False, message=exc.user_message)
        where = (
            f"at {outcome.being.name}'s {outcome.site}"
            if outcome.site
            else f"to {outcome.being.name}"
        )
        lines = [
            f"You sacrifice {item.name} {where}. {item.calculation}." for item in outcome.items
        ]
        return ActionResult(
            success=True,
            message="\n".join(lines),
            data={"credited": sum(item.credited for item in outcome.items)},
        )


def _carried_items(actor: ObjectDB, kwargs: dict[str, Any]):
    """(items, error): ``item_ids`` the actor carries, or ``item_names`` found in
    their inventory."""
    from world.items.models import ItemInstance  # noqa: PLC0415

    ids = kwargs.get("item_ids") or []
    names: list[str] = kwargs.get("item_names") or []
    if ids:
        try:
            pks = [int(pk) for pk in ids]
        except (TypeError, ValueError):
            return None, ActionResult(success=False, message="Choose items to sacrifice.")
        items = list(
            ItemInstance.objects.filter(pk__in=pks, game_object__db_location=actor).select_related(
                "template", "game_object"
            )
        )
        if len(items) != len(set(pks)):
            return None, ActionResult(success=False, message="You are not carrying all of those.")
        return items, None
    if not names:
        return None, ActionResult(success=False, message="Sacrifice what?")
    items = []
    for name in names:
        found = actor.search(name, location=actor, quiet=True)
        obj = found[0] if found else None
        instance = ItemInstance.objects.filter(game_object=obj).first() if obj else None
        if instance is None:
            return None, ActionResult(success=False, message=f"You carry no '{name}'.")
        items.append(instance)
    return items, None


@dataclass
class AnswerBeingPromptAction(Action):
    """A stewarded being's table GM answers a closed pledge (#4333 slice 4).

    Account-authorized like the other GM prompt actions: ``actor`` may be None
    (the web dispatches with the request's account). Only the GM the prompt is
    addressed to, or staff, may answer.

    kwargs:
        account: the answering GM's account.
        prompt_id: the ``BEING_ANSWER`` prompt.
        answer_id: one of the being's authored answers at or below the tier; or
        text: the GM's own words (Success and Critical Success only), with
        clue_id: optional, one of the clues the being's answers already link.

    A prompt raised by a rite in a GM-run scene (#4333 slice 5) is answered live
    instead: ``answer_id`` (with ``text`` to edit its main text, for a GM level that
    may adapt answers) or ``miracle_id``.
    """

    key: str = "gm_being_answer"
    name: str = "Answer for a being"
    icon: str = "sparkles"
    category: str = "worship"
    target_type: TargetType = TargetType.SELF

    def execute(
        self, actor: ObjectDB | None, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from core_management.permissions import is_staff_observer  # noqa: PLC0415
        from world.clues.models import Clue  # noqa: PLC0415
        from world.gm.models import GMPrompt  # noqa: PLC0415
        from world.worship.exceptions import StewardAnswerError  # noqa: PLC0415
        from world.worship.models import Answer  # noqa: PLC0415
        from world.worship.steward_services import send_steward_answer  # noqa: PLC0415

        account = kwargs.get("account")
        if account is None and actor is not None:
            from commands.utils.gm_resolution import resolve_account_or_none  # noqa: PLC0415

            account = resolve_account_or_none(actor)
        prompt = GMPrompt.objects.filter(pk=kwargs.get("prompt_id")).first()
        not_yours = "That prompt is not addressed to you."
        if prompt is None or account is None:
            return ActionResult(success=False, message=not_yours)
        if not is_staff_observer(account) and prompt.addressed_to_id != account.pk:
            return ActionResult(success=False, message=not_yours)
        answer, error = _optional_row(Answer, {"answer": kwargs.get("answer_id")}, "answer")
        if error is not None:
            return error
        if prompt.rite_performance_id is not None:
            return _answer_live_rite(prompt, account, answer, kwargs)
        clue, error = _optional_row(Clue, {"clue": kwargs.get("clue_id")}, "clue")
        if error is not None:
            return error
        try:
            delivery = send_steward_answer(
                prompt,
                resolver=account,
                answer=answer,
                text=str(kwargs.get("text") or ""),
                clue=clue,
            )
        except StewardAnswerError as exc:
            return ActionResult(success=False, message=exc.user_message)
        being = prompt.pledge.pledge.being.name
        if delivery.held:
            message = f"Sent. {being}'s worship pool is short; the vision goes out once it can pay."
        else:
            message = f"Sent as a vision from {being}."
        return ActionResult(
            success=True,
            message=message,
            data={
                "prompt_id": prompt.pk,
                "vision_id": delivery.vision.pk if delivery.vision is not None else None,
                "held": delivery.held,
            },
        )

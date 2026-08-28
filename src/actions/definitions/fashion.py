"""Fashion presentation actions: present_outfit, judge_presentation (#514)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.db.models import Prefetch

from actions.base import Action
from actions.types import ActionContext, ActionResult, TargetType
from flows.scene_data_manager import SceneDataManager
from flows.service_functions.communication import message_location
from world.events.models import Event
from world.items.exceptions import FashionPresentationError
from world.items.models import FashionPresentation, Outfit
from world.items.services.fashion_presentation import (
    judge_presentation as judge_presentation_service,
    present_outfit as present_outfit_service,
)

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

# ShowcaseAction mode token for clearing the toggle (piece/ensemble ride ShowcaseMode).
_MODE_OFF = "off"


@dataclass
class PresentOutfitAction(Action):
    """Present an outfit at an event hosted by a society.

    The host society's current fashion-style taste shapes the check difficulty.
    The graded outcome sets the presentation's base_score (and initial acclaim).
    An optional outfit FK is recorded for bookkeeping; the check reads
    equipped items, not that FK.
    """

    key: str = "present_outfit"
    name: str = "Present Outfit"
    icon: str = "runway"
    category: str = "items"
    target_type: TargetType = TargetType.SINGLE

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        event_id = kwargs.get("event_id")
        if event_id is None:
            return ActionResult(success=False, message="Present at which event?")
        try:
            event = Event.objects.get(pk=event_id)
        except Event.DoesNotExist:
            return ActionResult(success=False, message="That event no longer exists.")

        outfit_id = kwargs.get("outfit_id")
        outfit: Outfit | None = None
        if outfit_id is not None:
            try:
                outfit = Outfit.objects.get(pk=outfit_id)
            except Outfit.DoesNotExist:
                return ActionResult(success=False, message="That outfit no longer exists.")

        presenter = actor.sheet_data

        try:
            presentation = present_outfit_service(presenter, event, outfit)
        except FashionPresentationError as exc:
            return ActionResult(success=False, message=exc.user_message)

        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        message_location(actor_state, "$You() $conj(present) your look.")
        # Carry the created presentation so the web viewset can serialize the response
        # without re-querying — telnet ignores it (#1508).
        return ActionResult(success=True, data={"presentation": presentation})


@dataclass
class JudgePresentationAction(Action):
    """Endorse a peer's fashion presentation at an event.

    The judge must not be the presenter or an alt of the presenter.  Each
    judge may endorse a given presentation only once.  A successful endorsement
    recomputes the presentation's acclaim and rolls it into the presenter's
    primary persona's fashion prestige.
    """

    key: str = "judge_presentation"
    name: str = "Judge Presentation"
    icon: str = "gavel"
    category: str = "items"
    target_type: TargetType = TargetType.SINGLE

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        presentation_id = kwargs.get("presentation_id")
        if presentation_id is None:
            return ActionResult(success=False, message="Judge which presentation?")
        try:
            presentation = FashionPresentation.objects.get(pk=presentation_id)
        except FashionPresentation.DoesNotExist:
            return ActionResult(success=False, message="That presentation no longer exists.")

        judge = actor.sheet_data

        try:
            endorsement = judge_presentation_service(judge, presentation)
        except FashionPresentationError as exc:
            return ActionResult(success=False, message=exc.user_message)

        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        message_location(actor_state, "$You() $conj(nod) approvingly at the presentation.")
        return ActionResult(success=True, data={"endorsement": endorsement})


@dataclass
class ShowcaseAction(Action):
    """Set or clear the persistent showcase toggle (#2907).

    ``mode`` selects what the character is presenting: ``piece`` (one owned
    item — heavy acclaim, pushes its style AND silhouette), ``ensemble`` (a
    saved outfit — acclaim to the outfit, pushes its style), or ``off``.
    Cachet then auto-spends whenever the character makes an entrance while
    the toggle is active; settlement is at the weekly cron.
    """

    key: str = "showcase"
    name: str = "Showcase"
    icon: str = "star"
    category: str = "items"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.items.constants import ShowcaseMode  # noqa: PLC0415
        from world.items.models import ItemInstance  # noqa: PLC0415
        from world.items.services.fashion_showcase import (  # noqa: PLC0415
            clear_showcase,
            set_showcase_ensemble,
            set_showcase_piece,
        )

        sheet = actor.sheet_data
        mode = kwargs.get("mode")
        if mode == _MODE_OFF:
            was_on = clear_showcase(sheet)
            msg = "You stop showcasing." if was_on else "You weren't showcasing anything."
            return ActionResult(success=True, message=msg)
        if mode == ShowcaseMode.PIECE:
            item_id = kwargs.get("item_id")
            item = ItemInstance.objects.filter(pk=item_id, holder_character_sheet=sheet).first()
            if item is None:
                return ActionResult(success=False, message="You don't hold that piece.")
            set_showcase_piece(sheet, item)
            return ActionResult(
                success=True,
                message=f"You begin showcasing {item.display_name} — your entrances "
                "now stake cachet on it.",
            )
        if mode == ShowcaseMode.ENSEMBLE:
            outfit_id = kwargs.get("outfit_id")
            outfit = Outfit.objects.filter(pk=outfit_id, character_sheet=sheet).first()
            if outfit is None:
                return ActionResult(success=False, message="You have no such outfit.")
            set_showcase_ensemble(sheet, outfit)
            return ActionResult(
                success=True,
                message=f"You begin showcasing the {outfit.name} ensemble — your "
                "entrances now stake cachet on it.",
            )
        return ActionResult(success=False, message="Showcase what? (a piece, an ensemble, or off)")


@dataclass
class RevealAction(Action):
    """Show a body part, worn piece, or marking (#2985) — alias: show.

    Declarative by target: the player names the GOAL and the layer walk
    computes which covering garments to part. ``body_region`` bares the skin
    there (every blocking layer at the region is worn open — coat parts,
    doublet opens, the runes show); ``item_id`` opens only the layers above
    that piece (the hot doublet shows, the skin stays covered);
    ``marking_id`` is the region path with the marking's name in the echo.
    State lives on the covering garments (``EquippedItem.opened_at``), never
    on the hidden thing; dressing at the region re-closes it.
    """

    key: str = "reveal"
    name: str = "Show"
    icon: str = "eye"
    category: str = "items"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from actions.prerequisites import resolve_actor_sheet  # noqa: PLC0415

        sheet = resolve_actor_sheet(actor)
        if sheet is None or sheet.character_id is None:
            return ActionResult(success=False, message="You have nothing to show.")
        marking_id = kwargs.get("marking_id")
        if marking_id is not None:
            return self._show_marking(actor, sheet, marking_id, context)
        body_region = kwargs.get("body_region")
        if body_region is not None:
            return self._show_region(actor, sheet, body_region, context, label=None)
        item_id = kwargs.get("item_id")
        if item_id is not None:
            return self._show_item(actor, sheet, item_id, context)
        return ActionResult(
            success=False, message="Show what? (a body part, a worn piece, or a marking)"
        )

    def _show_region(
        self,
        actor: ObjectDB,
        sheet: Any,
        body_region: str,
        context: ActionContext | None,
        *,
        label: str | None,
    ) -> ActionResult:
        from world.items.constants import BodyRegion  # noqa: PLC0415
        from world.items.services.visibility import is_see_through  # noqa: PLC0415

        if body_region not in BodyRegion.values:
            return ActionResult(success=False, message="You have no such body part.")
        rows = _equipped_rows(sheet)
        blockers = [
            row for row in rows if row.body_region == body_region and not is_see_through(row)
        ]
        region_label = BodyRegion(body_region).label.lower()
        shown = label or f"your {region_label}"
        if not blockers:
            return ActionResult(success=False, message="That is already plainly visible.")
        _open_rows(blockers)
        _refresh_equipment(actor)
        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        message_location(
            actor_state,
            f"$You() $conj(part) $pron(your) clothing, baring {label or region_label}.",
        )
        return ActionResult(success=True, message=f"You bare {shown} for all to see.")

    def _show_item(
        self,
        actor: ObjectDB,
        sheet: Any,
        item_id: Any,
        context: ActionContext | None,
    ) -> ActionResult:
        rows = _equipped_rows(sheet)
        mine = [row for row in rows if row.item_instance_id == item_id]
        if not mine:
            return ActionResult(success=False, message="You aren't wearing that.")
        blockers = _blockers_above(rows, mine)
        if not blockers:
            return ActionResult(success=False, message="That is already plainly visible.")
        _open_rows(blockers)
        _refresh_equipment(actor)
        piece = mine[0].item_instance
        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        message_location(
            actor_state,
            f"$You() $conj(part) $pron(your) outer layers, revealing {piece.display_name}.",
        )
        return ActionResult(
            success=True,
            message=f"You show {piece.display_name} — it counts for all to see now.",
        )

    def _show_marking(
        self,
        actor: ObjectDB,
        sheet: Any,
        marking_id: Any,
        context: ActionContext | None,
    ) -> ActionResult:
        marking = _own_marking(sheet, marking_id)
        if marking is None:
            return ActionResult(success=False, message="You bear no such marking.")
        return self._show_region(actor, sheet, marking.body_region, context, label=marking.name)


@dataclass
class CoverUpAction(Action):
    """Conceal a body part, worn piece, or marking (#2985) — alias: conceal.

    The inverse of show: closes the worn-open layers back up. Honest when
    fabric cannot help — if nothing worn covers the region (a plunging cut,
    sheer cloth, bare skin), it says so instead of pretending.
    """

    key: str = "cover"
    name: str = "Conceal"
    icon: str = "eye-off"
    category: str = "items"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from actions.prerequisites import resolve_actor_sheet  # noqa: PLC0415

        sheet = resolve_actor_sheet(actor)
        if sheet is None or sheet.character_id is None:
            return ActionResult(success=False, message="You have nothing to conceal.")
        marking_id = kwargs.get("marking_id")
        if marking_id is not None:
            marking = _own_marking(sheet, marking_id)
            if marking is None:
                return ActionResult(success=False, message="You bear no such marking.")
            return self._conceal_region(
                actor, sheet, marking.body_region, context, label=marking.name
            )
        body_region = kwargs.get("body_region")
        if body_region is not None:
            return self._conceal_region(actor, sheet, body_region, context, label=None)
        item_id = kwargs.get("item_id")
        if item_id is not None:
            return self._conceal_item(actor, sheet, item_id, context)
        return ActionResult(
            success=False, message="Conceal what? (a body part, a worn piece, or a marking)"
        )

    def _conceal_region(
        self,
        actor: ObjectDB,
        sheet: Any,
        body_region: str,
        context: ActionContext | None,
        *,
        label: str | None,
    ) -> ActionResult:
        from world.items.constants import BodyRegion  # noqa: PLC0415
        from world.items.services.visibility import is_see_through  # noqa: PLC0415

        if body_region not in BodyRegion.values:
            return ActionResult(success=False, message="You have no such body part.")
        rows = _equipped_rows(sheet)
        at_region = [row for row in rows if row.body_region == body_region]
        opened = [row for row in at_region if row.opened_at is not None]
        _close_rows(opened)
        _refresh_equipment(actor)
        region_label = BodyRegion(body_region).label.lower()
        covered = any(not is_see_through(row) for row in at_region)
        target = label or f"your {region_label}"
        if not covered:
            return ActionResult(
                success=False,
                message=f"Nothing you wear covers {target} — it shows regardless.",
            )
        if not opened:
            return ActionResult(success=False, message="That is already covered.")
        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        message_location(
            actor_state,
            "$You() $conj(close) $pron(your) clothing back up.",
        )
        return ActionResult(success=True, message=f"You cover {target} back up.")

    def _conceal_item(
        self,
        actor: ObjectDB,
        sheet: Any,
        item_id: Any,
        context: ActionContext | None,
    ) -> ActionResult:
        from world.items.services.visibility import compute_worn_visibility  # noqa: PLC0415

        rows = _equipped_rows(sheet)
        mine = [row for row in rows if row.item_instance_id == item_id]
        if not mine:
            return ActionResult(success=False, message="You aren't wearing that.")
        opened_above = _blockers_above(rows, mine, opened_only=True)
        _close_rows(opened_above)
        _refresh_equipment(actor)
        piece = mine[0].item_instance
        if compute_worn_visibility(rows).is_visible(item_id):
            return ActionResult(
                success=False,
                message=(f"Nothing you wear covers {piece.display_name} — it shows regardless."),
            )
        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        message_location(
            actor_state,
            f"$You() $conj(close) $pron(your) outer layers over {piece.display_name}.",
        )
        return ActionResult(success=True, message=f"You cover {piece.display_name} back up.")


def _equipped_rows(sheet: Any) -> list:
    """The wearer's EquippedItem rows with the walk's prefetch chain warm."""
    from world.items.models import EquippedItem, TemplateSlot  # noqa: PLC0415

    return list(
        EquippedItem.objects.filter(character_id=sheet.character_id)
        .select_related("item_instance__template")
        .prefetch_related(
            Prefetch(
                "item_instance__template__slots",
                queryset=TemplateSlot.objects.all(),
                to_attr="cached_slots",
            )
        )
    )


def _blockers_above(rows: list, mine: list, *, opened_only: bool = False) -> list:
    """Rows above any of ``mine``'s slots that block (or, for conceal, are open)."""
    from world.items.services.appearance import LAYER_RANK  # noqa: PLC0415

    blockers = []
    for target_row in mine:
        rank = LAYER_RANK.get(target_row.equipment_layer, 99)
        for row in rows:
            if _blocks_target(row, target_row, rank, opened_only=opened_only) and (
                row not in blockers
            ):
                blockers.append(row)
    return blockers


def _blocks_target(row: Any, target_row: Any, rank: int, *, opened_only: bool) -> bool:
    """Whether ``row`` sits above ``target_row``'s layer and blocks (or, for conceal, is open)."""
    from world.items.services.appearance import LAYER_RANK  # noqa: PLC0415
    from world.items.services.visibility import is_see_through  # noqa: PLC0415

    if row.body_region != target_row.body_region or row.pk == target_row.pk:
        return False
    if LAYER_RANK.get(row.equipment_layer, 99) <= rank:
        return False
    if opened_only:
        return row.opened_at is not None
    return not is_see_through(row)


def _open_rows(rows: list) -> None:
    from django.utils import timezone  # noqa: PLC0415

    now = timezone.now()
    for row in rows:
        row.opened_at = now
        row.save(update_fields=["opened_at"])


def _close_rows(rows: list) -> None:
    for row in rows:
        row.opened_at = None
        row.save(update_fields=["opened_at"])


def _refresh_equipment(actor: ObjectDB) -> None:
    """Invalidate the wearer's cached equipment handler after state changes."""
    actor.equipped_items.invalidate()


def _own_marking(sheet: Any, marking_id: Any) -> Any:
    """One of the wearer's own TRUE-form markings, or None."""
    from world.forms.models import FormMarking, FormType  # noqa: PLC0415

    return FormMarking.objects.filter(
        pk=marking_id, form__character=sheet, form__form_type=FormType.TRUE
    ).first()

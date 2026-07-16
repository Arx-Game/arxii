from typing import TYPE_CHECKING

from evennia.utils.utils import iter_to_str

from flows.object_states.base_state import BaseState
from world.items.services.appearance import visible_worn_items_for

if TYPE_CHECKING:
    from commands.types import Kwargs


class CharacterState(BaseState):
    """CharacterState represents the state for character objects."""

    @property
    def appearance_template(self) -> str:
        """Template for ``return_appearance``.

        Renders name, description, then optional status and worn sections.
        Each optional section is omitted entirely when its display method
        returns an empty string.
        """
        return "{name}\n{desc}{status_section}{worn_section}"

    def get_categories(self) -> dict:
        # For now, no extra character-specific categories.
        return {}

    # ------------------------------------------------------------------
    # Identity rendering (#1109) — the look / room-contents / examine name
    # ------------------------------------------------------------------

    def _base_display_name(self, looker_state: "BaseState | None") -> str:
        """Render this character's presented persona, resolved per viewer (#1109).

        The active face renders by real name to its owner and for any named-public face; a viewer
        who has discovered an anonymous face sees the reveal ("Mask (Real)"); otherwise an
        anonymous face renders as a composed sdesc ("a man wearing a stag mask"). Falls back to the
        default name when there is no sheet/persona (NPCs, objects mid-setup).
        """
        resolved = self._presented_persona_name(looker_state)
        if resolved is not None:
            return resolved
        return super()._base_display_name(looker_state)

    def _presented_persona_name(self, looker_state: "BaseState | None") -> str | None:
        from world.scenes.models import Persona  # noqa: PLC0415
        from world.scenes.persona_display import resolve_display_for_viewer  # noqa: PLC0415
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        sheet = self.obj.character_sheet
        if sheet is None:
            return None
        try:
            persona = active_persona_for_sheet(sheet)
        except Persona.DoesNotExist:
            return None
        viewer_persona_ids, viewer_sheet_ids = (
            looker_state._viewer_persona_context()  # noqa: SLF001 — same-class look context
            if isinstance(looker_state, CharacterState)
            else (set(), set())
        )
        is_staff = bool(
            looker_state is not None
            and isinstance(looker_state, CharacterState)
            and looker_state._viewer_is_staff()  # noqa: SLF001
        )
        name, _is_discovered = resolve_display_for_viewer(
            persona,
            viewer_persona_ids=viewer_persona_ids,
            viewer_sheet_ids=viewer_sheet_ids,
            is_staff=is_staff,
        )
        return name

    def _viewer_persona_context(self) -> tuple[set[int], set[int]]:
        """This looker's account's ``(owned_persona_ids, owned_sheet_ids)``, cached for the look.

        Cached on the state so listing a room's occupants resolves the looker's context once, not
        once per occupant.
        """
        # Suppression justified: lazy memoization slot, absent until first compute.
        if getattr(self, "_viewer_persona_ctx", None) is None:  # noqa: GETATTR_LITERAL
            from world.scenes.persona_display import viewer_context_for_account  # noqa: PLC0415

            account = self.obj.db_account
            self._viewer_persona_ctx = (
                viewer_context_for_account(account) if account is not None else (set(), set())
            )
        return self._viewer_persona_ctx

    def _viewer_is_staff(self) -> bool:
        """Whether the looker's account is staff (#1279 — universal identity-sight)."""
        account = self.obj.db_account
        return bool(account and account.is_staff)

    # ------------------------------------------------------------------
    # Permission helpers
    # ------------------------------------------------------------------

    def can_move(
        self,
        actor: "BaseState | None" = None,
        dest: "BaseState | None" = None,
    ) -> bool:
        """Return True only if ``actor`` is moving themselves to ``dest``."""

        if actor is not self:
            return False
        return super().can_move(actor=actor, dest=dest)

    # ------------------------------------------------------------------
    # Appearance display components
    # ------------------------------------------------------------------

    def get_display_worn(
        self,
        looker: "BaseState | object | None" = None,
        **kwargs: "Kwargs",
    ) -> str:
        """Return the visible worn equipment as look-output text.

        Empty string when nothing visible is worn — the appearance template
        omits the section in that case.
        """
        observer = looker.obj if looker is not None and hasattr(looker, "obj") else None
        visible = visible_worn_items_for(self.obj, observer=observer)
        if not visible:
            return ""
        names = iter_to_str(
            [v.item_instance.display_name for v in visible],
            endsep=", and",
        )
        return f"|wWearing:|n {names}."

    def get_display_status(
        self,
        looker: "BaseState | object | None" = None,
        **kwargs: "Kwargs",
    ) -> str:
        """Return a narrative status line from vitals, fatigue, and conditions.

        Composes, in order: the wound-severity descriptor (suppressed when
        healthy), the worst non-FRESH fatigue zone across the three pools, and
        the observer text of each visible active condition (priority-ordered).
        Returns ``""`` when there is nothing to report — the appearance
        template then omits the section, matching ``get_display_worn``.

        All reads go through the character's identity-mapped ``CharacterSheet``
        and its cached relations; no rows are created on look.
        """
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from actions.constants import ActionCategory  # noqa: PLC0415
        from world.conditions.services import get_active_conditions  # noqa: PLC0415
        from world.fatigue.constants import FatigueZone  # noqa: PLC0415
        from world.fatigue.services import get_fatigue_zone  # noqa: PLC0415
        from world.vitals.constants import WOUND_DESCRIPTIONS  # noqa: PLC0415

        try:
            sheet = self.obj.sheet_data
        except ObjectDoesNotExist:
            return ""

        clauses: list[str] = []

        # Wounds — suppress the healthy band (>= 0.9 → "healthy appearance").
        try:
            vitals = sheet.vitals
        except ObjectDoesNotExist:
            vitals = None
        # The top WOUND_DESCRIPTIONS band ("healthy appearance") contributes no
        # clause — only show a wound descriptor below that authored threshold.
        healthy_floor = WOUND_DESCRIPTIONS[0][0]
        if vitals is not None and vitals.health_percentage < healthy_floor:
            clauses.append(vitals.wound_description)

        # Fatigue — only when a pool already exists (never create one on look).
        # The reverse OneToOne raises an AttributeError subclass when unset, so
        # getattr-with-default reads it without a query-creating get_or_create.
        fatigue_pool = sheet.fatigue_or_none
        if fatigue_pool is not None:
            zone_order = [
                FatigueZone.FRESH,
                FatigueZone.STRAINED,
                FatigueZone.TIRED,
                FatigueZone.OVEREXERTED,
                FatigueZone.EXHAUSTED,
            ]
            worst_rank = 0
            for category in ActionCategory.values:
                worst_rank = max(worst_rank, zone_order.index(get_fatigue_zone(sheet, category)))
            if worst_rank > 0:
                clauses.append(str(zone_order[worst_rank].label).lower())

        # Visible conditions, most prominent first.
        visible = sorted(
            (c for c in get_active_conditions(self.obj) if c.condition.is_visible_to_others),
            key=lambda c: c.condition.display_priority,
            reverse=True,
        )
        clauses.extend(
            c.condition.observer_description.strip()
            for c in visible
            if c.condition.observer_description.strip()
        )

        if not clauses:
            return ""
        return f"|wStatus:|n {iter_to_str(clauses, endsep=', and')}."

    def return_appearance(
        self,
        mode: str = "look",
        **kwargs: "Kwargs",
    ) -> str:
        """Render character appearance with optional worn/status sections.

        ``looker`` is propagated via ``**kwargs`` so it binds to each
        display-component method's first positional parameter, matching the
        pattern used by ``BaseState.return_appearance``.
        """
        name = self.get_display_name(**kwargs)
        desc = self.get_display_desc(mode=mode, **kwargs)
        worn = self.get_display_worn(**kwargs)
        status = self.get_display_status(**kwargs)

        appearance = self.appearance_template.format(
            name=name,
            desc=desc,
            status_section=f"\n{status}" if status else "",
            worn_section=f"\n{worn}" if worn else "",
        )
        return self.format_appearance(appearance, **kwargs)

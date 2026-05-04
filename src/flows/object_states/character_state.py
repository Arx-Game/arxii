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
        """Placeholder for narrative status (parked in combat roadmap).

        Returns empty string until the follow-up PR wires vitals/fatigue/
        conditions into the appearance output.
        """
        return ""

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

from typing import TYPE_CHECKING

from evennia_extensions.constants import ExitKind
from evennia_extensions.models import ExitProfile
from flows.object_states.base_state import BaseState

if TYPE_CHECKING:
    from evennia.objects.objects import DefaultObject


class ExitState(BaseState):
    """State wrapper for exit objects."""

    # ------------------------------------------------------------------
    # Permission helpers
    # ------------------------------------------------------------------

    def can_move(
        self,
        actor: "BaseState | None" = None,
        dest: "BaseState | None" = None,
    ) -> bool:
        """Return ``False`` to prevent moving exits."""

        return False

    @staticmethod
    def _actor_lacks_room_standing(actor: "BaseState", room: "DefaultObject") -> bool:
        """True when ``actor`` lacks owner/tenant standing at ``room``.

        Shared owner/tenant-standing lookup for ``can_traverse``'s lock-gate and
        bars-gate blocks (#2177 whole-branch review, Minor #5) — the two gates
        stay independent guard clauses; only this boilerplate (imports, sheet/
        persona resolution, the ``is_owner(...) or is_tenant(...)`` check) is
        deduplicated. An actor with no ``sheet_data`` counts as lacking standing.
        """
        from world.locations.services import is_owner, is_tenant  # noqa: PLC0415
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        sheet = getattr(actor.obj, "sheet_data", None)  # noqa: GETATTR_LITERAL
        if sheet is None:
            return True
        persona = active_persona_for_sheet(sheet)
        return not (is_owner(persona, room) or is_tenant(persona, room))

    def _bars_block_actor(self, profile: "ExitProfile", actor: "BaseState") -> bool:
        """True when an active ``ExitBarsDetails`` gate blocks ``actor``.

        #2177 — bars block traversal for anyone who isn't the source room's
        owner or tenant, independent of the ``db.locked`` gate.
        """
        from world.room_features.models import ExitBarsDetails  # noqa: PLC0415

        bars = ExitBarsDetails.objects.filter(exit_profile=profile).active().first()
        if bars is None:
            return False
        room = self.obj.location
        return room is not None and self._actor_lacks_room_standing(actor, room)

    def can_traverse(self, actor: "BaseState | None" = None) -> bool:
        """Return ``True`` if ``actor`` may traverse this exit.

        A locked exit (``db.locked``) blocks traversal for anyone who isn't
        the source room's owner or tenant (#1866) — checked before the
        package-hook delegation so a locked door can't be overridden by an
        unrelated hook. An active ``ExitBarsDetails`` row (#2177) applies the
        same owner/tenant gate independently — bars block regardless of
        whether ``db.locked`` is also set. Deliberately not merged into the
        lock-check block above: the two gates are separate installable
        defenses with independent lifecycles.

        Args:
            actor: State attempting the action.

        Returns:
            bool: Whether traversal is permitted.
        """
        profile = ExitProfile.objects.filter(objectdb=self.obj).first()
        if profile and profile.exit_kind == ExitKind.WINDOW and not profile.is_open:
            return False

        if self.obj.db.locked and actor is not None:
            room = self.obj.location
            if room is not None and self._actor_lacks_room_standing(actor, room):
                return False

        if profile is not None and actor is not None and self._bars_block_actor(profile, actor):
            return False

        result = self._run_package_hook("can_traverse", actor)
        if result is not None:
            return bool(result)
        return True

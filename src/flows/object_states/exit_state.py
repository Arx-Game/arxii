from evennia_extensions.constants import ExitKind
from evennia_extensions.models import ExitProfile
from flows.object_states.base_state import BaseState


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

    def can_traverse(  # noqa: PLR0911, C901 - lock and bars gates read clearest as parallel guard clauses
        self, actor: "BaseState | None" = None
    ) -> bool:
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
            from world.locations.services import is_owner, is_tenant  # noqa: PLC0415
            from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

            room = self.obj.location
            sheet = getattr(actor.obj, "sheet_data", None)  # noqa: GETATTR_LITERAL
            if room is not None and sheet is not None:
                persona = active_persona_for_sheet(sheet)
                if not (is_owner(persona, room) or is_tenant(persona, room)):
                    return False
            elif room is not None:
                return False

        if profile is not None and actor is not None:
            from world.room_features.models import ExitBarsDetails  # noqa: PLC0415

            bars = ExitBarsDetails.objects.filter(exit_profile=profile).active().first()
            if bars is not None:
                from world.locations.services import is_owner, is_tenant  # noqa: PLC0415
                from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

                room = self.obj.location
                sheet = getattr(actor.obj, "sheet_data", None)  # noqa: GETATTR_LITERAL
                if room is not None and sheet is not None:
                    persona = active_persona_for_sheet(sheet)
                    if not (is_owner(persona, room) or is_tenant(persona, room)):
                        return False
                elif room is not None:
                    return False

        result = self._run_package_hook("can_traverse", actor)
        if result is not None:
            return bool(result)
        return True

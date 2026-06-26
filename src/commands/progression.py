"""Progression telnet commands — training allocation and unlock purchase.

``training`` and ``progression`` are thin telnet shells over the same
``dispatch_player_action`` seam the web ViewSets use. All business logic lives in
``ManageTrainingAction``, ``PurchaseUnlockAction``, and the read-only service
functions they call.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from actions.constants import ActionBackend
from commands.command import DispatchCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from actions.types import ActionRef

# Telnet argument keys used by both commands.
_KEY_SKILL = "skill"
_KEY_SPEC = "spec"
_KEY_SPECIALIZATION = "specialization"
_KEY_AP = "ap"
_KEY_MENTOR = "mentor"
_KEY_ID = "id"
_KEY_CLASS = "class"
_KEY_THREAD = "thread"
_KEY_LEVEL = "level"

# Subverbs
_SUBVERB_LIST = "list"
_SUBVERB_ADD = "add"
_SUBVERB_UPDATE = "update"
_SUBVERB_REMOVE = "remove"
_SUBVERB_UNLOCKS = "unlocks"
_SUBVERB_UNLOCK = "unlock"

# ManageTrainingAction operation identifiers.
_OPERATION_ADD = "add"
_OPERATION_UPDATE = "update"
_OPERATION_REMOVE = "remove"

# PurchaseUnlockAction unlock types.
_UNLOCK_TYPE_CLASS_LEVEL = "class_level"
_UNLOCK_TYPE_THREAD_XP_LOCK = "thread_xp_lock"

# Keys returned by get_available_unlocks_for_character.
_AVAILABLE_KEY = "available"
_LOCKED_KEY = "locked"
_UNLOCK_KEY = "unlock"
_XP_COST_KEY = "xp_cost"
_REQUIREMENTS_MET_KEY = "requirements_met"
_FAILED_REQUIREMENTS_KEY = "failed_requirements"


class CmdTraining(DispatchCommand):
    """Manage your weekly skill-training allocations.

    Usage:
        training                       — list current allocations and AP budget
        training list                  — same as bare ``training``
        training add skill=<id> ap=<n> [mentor=<id>]
        training add spec=<id> ap=<n> [mentor=<id>]
        training update id=<id> ap=<n> [mentor=<id>]
        training remove id=<id>

    ``spec`` is an alias for ``specialization``. Omitting ``mentor`` on update
    leaves the mentor unchanged; ``mentor=`` (empty) clears it.
    """

    key = "training"
    locks = "cmd:all()"

    _VALID_SUBVERBS = {_SUBVERB_LIST, _SUBVERB_ADD, _SUBVERB_UPDATE, _SUBVERB_REMOVE}

    _subverb: str = ""
    _rest: str = ""

    def func(self) -> None:
        """Route: bare/list → listing; subverb → dispatch."""
        raw = (self.args or "").strip()
        if not raw or raw.lower() == _SUBVERB_LIST:
            self._show_listing()
            return

        parts = raw.split(maxsplit=1)
        self._subverb = parts[0].lower()
        self._rest = parts[1].strip() if len(parts) > 1 else ""

        if self._subverb not in self._VALID_SUBVERBS:
            options = ", ".join(sorted(self._VALID_SUBVERBS))
            self.msg(f"Unknown training command '{self._subverb}'. Try: {options}.")
            return

        super().func()  # resolve_action_ref + resolve_action_args + dispatch

    def resolve_action_ref(self) -> ActionRef:
        """Build a REGISTRY ActionRef for ``manage_training``."""
        from actions.types import ActionRef  # noqa: PLC0415

        return ActionRef(backend=ActionBackend.REGISTRY, registry_key="manage_training")

    def resolve_action_args(self) -> dict[str, Any]:
        """Translate parsed telnet tokens into ``ManageTrainingAction`` kwargs."""
        parsed = self._parse_assignment_args(self._rest)
        if self._subverb == _SUBVERB_ADD:
            return self._resolve_add_args(parsed)
        if self._subverb == _SUBVERB_UPDATE:
            return self._resolve_update_args(parsed)
        if self._subverb == _SUBVERB_REMOVE:
            return self._resolve_remove_args(parsed)
        return {}

    # -- helpers ------------------------------------------------------------------

    def _resolve_add_args(self, parsed: dict[str, str | None]) -> dict[str, Any]:
        """Build kwargs for operation="add"."""
        kwargs: dict[str, Any] = {"operation": _OPERATION_ADD}

        skill_id = parsed.get(_KEY_SKILL)
        spec_id = parsed.get(_KEY_SPEC) or parsed.get(_KEY_SPECIALIZATION)

        has_skill = skill_id is not None
        has_spec = spec_id is not None
        if has_skill and has_spec:
            msg = "Provide either skill=<id> or spec=<id>, not both."
            raise CommandError(msg)
        if not has_skill and not has_spec:
            msg = "Provide either skill=<id> or spec=<id>."
            raise CommandError(msg)

        if has_skill:
            kwargs["skill_id"] = self._require_positive_int(skill_id, _KEY_SKILL)
        else:
            kwargs["specialization_id"] = self._require_positive_int(spec_id, _KEY_SPEC)

        ap_amount = parsed.get(_KEY_AP)
        kwargs["ap_amount"] = self._require_positive_int(ap_amount, _KEY_AP)

        mentor = parsed.get(_KEY_MENTOR)
        if mentor is not None:
            kwargs["mentor_persona_id"] = self._parse_optional_id(mentor, _KEY_MENTOR)

        return kwargs

    def _resolve_update_args(self, parsed: dict[str, str | None]) -> dict[str, Any]:
        """Build kwargs for operation="update"."""
        kwargs: dict[str, Any] = {"operation": _OPERATION_UPDATE}

        allocation_id = parsed.get(_KEY_ID)
        kwargs["allocation_id"] = self._require_positive_int(allocation_id, _KEY_ID)

        ap_amount = parsed.get(_KEY_AP)
        if ap_amount is not None:
            kwargs["ap_amount"] = self._require_positive_int(ap_amount, _KEY_AP)

        if _KEY_MENTOR in parsed:
            kwargs["mentor_persona_id"] = self._parse_optional_id(parsed[_KEY_MENTOR], _KEY_MENTOR)

        return kwargs

    def _resolve_remove_args(self, parsed: dict[str, str | None]) -> dict[str, Any]:
        """Build kwargs for operation="remove"."""
        allocation_id = parsed.get(_KEY_ID)
        return {
            "operation": _OPERATION_REMOVE,
            "allocation_id": self._require_positive_int(allocation_id, _KEY_ID),
        }

    def _show_listing(self) -> None:
        """Render the caller's training allocations and weekly AP budget."""
        from django.db.models import Prefetch  # noqa: PLC0415

        from world.action_points.models import ActionPointConfig  # noqa: PLC0415
        from world.skills.models import (  # noqa: PLC0415
            Specialization,
            TrainingAllocation,
        )

        allocations = (
            TrainingAllocation.objects.filter(character=self.caller)
            .select_related(
                "skill__trait",
                "specialization__parent_skill__trait",
                "mentor",
            )
            .prefetch_related(
                Prefetch(
                    "skill__specializations",
                    queryset=Specialization.objects.all(),
                    to_attr="cached_specializations",
                ),
            )
        )

        total_ap = sum(allocation.ap_amount for allocation in allocations)
        weekly_budget = ActionPointConfig.get_weekly_regen()
        remaining = max(0, weekly_budget - total_ap)

        lines = [f"Weekly training budget: {total_ap}/{weekly_budget} AP used ({remaining} left)"]
        if not allocations:
            lines.append("No training allocations set.")
        else:
            for allocation in allocations:
                if allocation.skill is not None:
                    target = allocation.skill.name
                else:
                    target = allocation.specialization.name
                mentor = f" (mentor: {allocation.mentor.name})" if allocation.mentor else ""
                lines.append(f"[{allocation.pk}] {target}: {allocation.ap_amount} AP{mentor}")

        self.msg("\n".join(lines))

    @staticmethod
    def _parse_assignment_args(args: str) -> dict[str, str | None]:
        """Parse ``key=value`` tokens into a dict.

        Values may be empty (``mentor=``), in which case the value is ``None``.
        """
        result: dict[str, str | None] = {}
        for token in args.split():
            if "=" not in token:
                msg = f"Expected key=value, got: {token}"
                raise CommandError(msg)
            key, value = token.split("=", 1)
            result[key] = value if value else None
        return result

    def _require_positive_int(self, value: str | None, name: str) -> int:
        """Return *value* as a positive int, or raise CommandError."""
        if value is None or not value.isdigit() or int(value) <= 0:
            msg = f"{name} must be a positive integer."
            raise CommandError(msg)
        return int(value)

    def _parse_optional_id(self, value: str | None, name: str) -> int | None:
        """Return an int id, None for empty, or raise CommandError for bad input."""
        if value is None or value == "":
            return None
        if not value.isdigit() or int(value) <= 0:
            msg = f"{name} must be a positive integer or empty."
            raise CommandError(msg)
        return int(value)


class CmdProgressionUnlock(DispatchCommand):
    """Browse and purchase progression unlocks with XP.

    Usage:
        progression unlocks             — list available class-level and thread XP-lock unlocks
        progression unlock class=<id>   — purchase a class-level unlock
        progression unlock thread=<id> level=<n>
                                        — purchase a thread XP-lock boundary
    """

    key = "progression"
    locks = "cmd:all()"

    _subverb: str = ""
    _rest: str = ""

    def func(self) -> None:
        """Route: bare/unlocks/list → listing; unlock → dispatch."""
        raw = (self.args or "").strip()
        if not raw or raw.lower() in {_SUBVERB_UNLOCKS, _SUBVERB_LIST}:
            self._show_listing()
            return

        parts = raw.split(maxsplit=1)
        self._subverb = parts[0].lower()
        self._rest = parts[1].strip() if len(parts) > 1 else ""

        if self._subverb != _SUBVERB_UNLOCK:
            self.msg(
                "Unknown progression command. Try: unlocks, unlock class=<id>, "
                "unlock thread=<id> level=<n>."
            )
            return

        super().func()

    def resolve_action_ref(self) -> ActionRef:
        """Build a REGISTRY ActionRef for ``purchase_unlock``."""
        from actions.types import ActionRef  # noqa: PLC0415

        return ActionRef(backend=ActionBackend.REGISTRY, registry_key="purchase_unlock")

    def resolve_action_args(self) -> dict[str, Any]:
        """Translate parsed telnet tokens into ``PurchaseUnlockAction`` kwargs."""
        parsed = self._parse_assignment_args(self._rest)
        class_id = parsed.get(_KEY_CLASS)
        thread_id = parsed.get(_KEY_THREAD)
        level = parsed.get(_KEY_LEVEL)

        has_class = class_id is not None
        has_thread = thread_id is not None

        if has_class and has_thread:
            msg = "Provide either class=<id> or thread=<id>, not both."
            raise CommandError(msg)
        if has_class:
            return {
                "unlock_type": _UNLOCK_TYPE_CLASS_LEVEL,
                "class_level_unlock_id": self._require_positive_int(class_id, _KEY_CLASS),
            }
        if has_thread:
            return {
                "unlock_type": _UNLOCK_TYPE_THREAD_XP_LOCK,
                "thread_id": self._require_positive_int(thread_id, _KEY_THREAD),
                "boundary_level": self._require_positive_int(level, _KEY_LEVEL),
            }
        msg = "Provide class=<id> or thread=<id> level=<n>."
        raise CommandError(msg)

    def _show_listing(self) -> None:
        """Render available class-level and thread XP-lock unlocks."""
        from world.magic.services.threads import near_xp_lock_threads  # noqa: PLC0415
        from world.progression.services.spends import (  # noqa: PLC0415
            get_available_unlocks_for_character,
        )

        character = self.caller
        try:
            sheet = character.sheet_data
        except AttributeError:
            sheet = None

        lines = ["Available progression unlocks:"]

        available = get_available_unlocks_for_character(character)
        entries = list(available[_AVAILABLE_KEY]) + list(available[_LOCKED_KEY])
        if entries:
            for entry in entries:
                unlock = entry[_UNLOCK_KEY]
                failed = entry.get(_FAILED_REQUIREMENTS_KEY, [])
                status = "" if entry[_REQUIREMENTS_MET_KEY] else " (locked)"
                reason = "; ".join(failed) if failed else ""
                lines.append(
                    f"[class] {unlock.character_class.name} level {unlock.target_level}: "
                    f"{entry[_XP_COST_KEY]} XP{status}"
                )
                if reason:
                    lines.append(f"        {reason}")
        else:
            lines.append("No class-level unlocks available.")

        if sheet is not None:
            thread_prospects = near_xp_lock_threads(sheet)
            if thread_prospects:
                lines.append("")
                lines.append("Thread XP-lock boundaries:")
                for prospect in thread_prospects:
                    thread = prospect.thread
                    thread_name = thread.name or "Unnamed Thread"
                    lines.append(
                        f"[thread] {thread_name} level {prospect.boundary_level}: "
                        f"{prospect.xp_cost} XP"
                    )
            elif not entries:
                lines.append("No thread XP-lock boundaries available.")

        self.msg("\n".join(lines))

    @staticmethod
    def _parse_assignment_args(args: str) -> dict[str, str | None]:
        """Parse ``key=value`` tokens into a dict; empty values become ``None``."""
        result: dict[str, str | None] = {}
        for token in args.split():
            if "=" not in token:
                msg = f"Expected key=value, got: {token}"
                raise CommandError(msg)
            key, value = token.split("=", 1)
            result[key] = value if value else None
        return result

    def _require_positive_int(self, value: str | None, name: str) -> int:
        """Return *value* as a positive int, or raise CommandError."""
        if value is None or not value.isdigit() or int(value) <= 0:
            msg = f"{name} must be a positive integer."
            raise CommandError(msg)
        return int(value)

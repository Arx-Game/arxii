"""Telnet face of the sticky-language switch + weekly language training (#2993).

Thin `ArxCommand` shells over `SetLanguageAction`/`TrainLanguageAction`
(`actions/definitions/language.py`) — no business logic lives here, only
name-to-pk resolution.
"""

from __future__ import annotations

from typing import Any

from actions.definitions.language import SetLanguageAction, TrainLanguageAction
from commands.command import ArxCommand
from commands.exceptions import CommandError


class CmdSpeak(ArxCommand):
    """Switch your sticky spoken language.

    Usage:
      speak <language>   - speak <language> by default from now on
      speak              - reset to the universal tongue
    """

    key = "speak"
    locks = "cmd:all()"
    action = SetLanguageAction()

    def resolve_action_args(self) -> dict[str, Any]:
        name = (self.args or "").strip()
        if not name:
            return {}

        from world.species.models import Language  # noqa: PLC0415

        language = Language.objects.filter(name__iexact=name).first()
        if language is None:
            msg = f"There is no language called '{name}'."
            raise CommandError(msg)
        return {"language_id": language.pk}


class CmdTrainLanguage(ArxCommand):
    """Invest a weekly session studying a language.

    Usage:
      train_language <language>
      train_language <language>=<teacher>

    A co-located, FLUENT teacher yields a bigger session than self-study.
    Only one session per language per game week.
    """

    key = "train_language"
    locks = "cmd:all()"
    action = TrainLanguageAction()

    def resolve_action_args(self) -> dict[str, Any]:
        raw = self.require_args("Usage: train_language <language>[=<teacher>].")
        name_part, _sep, teacher_part = raw.partition("=")
        name = name_part.strip()
        if not name:
            msg = "Usage: train_language <language>[=<teacher>]."
            raise CommandError(msg)

        from world.species.models import Language  # noqa: PLC0415

        language = Language.objects.filter(name__iexact=name).first()
        if language is None:
            msg = f"There is no language called '{name}'."
            raise CommandError(msg)

        kwargs: dict[str, Any] = {"language_id": language.pk}
        teacher_name = teacher_part.strip()
        if teacher_name:
            teacher = self.search_or_raise(teacher_name)
            kwargs["teacher_id"] = teacher.pk
        return kwargs

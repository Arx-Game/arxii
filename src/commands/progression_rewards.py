"""Telnet progression-reward commands (#1348).

Thin namespaced commands that dispatch to the reward actions
(``action.run()``) — the same seam the web views use. Business logic lives in
the actions/services, never here.
"""

from __future__ import annotations

from typing import ClassVar

from actions.definitions.progression_rewards import (
    CastVoteAction,
    ClaimKudosAction,
    ClaimRandomSceneAction,
    ClearPathIntentAction,
    RemoveVoteAction,
    RerollRandomSceneAction,
    SetPathIntentAction,
)
from commands.command import ArxCommand
from commands.exceptions import CommandError
from world.progression.constants import VoteTargetType

_VOTE_TYPES = {
    "interaction": VoteTargetType.INTERACTION,
    "participation": VoteTargetType.SCENE_PARTICIPATION,
    "journal": VoteTargetType.JOURNAL,
}

# Argument-count constants (avoids PLR2004 magic-value comparisons).
_KUDOS_CLAIM_ARGC = 3
_VOTE_TARGET_ARGC = 2
_RANDOMSCENE_ARGC = 2


class CmdKudos(ArxCommand):
    """Claim kudos for XP.

    Usage:
      kudos                       - show your kudos balance and claim categories
      kudos claim <category> <n>  - claim <n> kudos via category id for XP
    """

    key = "kudos"
    aliases: ClassVar[list[str]] = []
    locks = "cmd:all()"
    help_category = "Progression"
    action = None

    def func(self) -> None:
        try:
            self._dispatch()
        except CommandError as err:
            self.msg(str(err))

    def _dispatch(self) -> None:
        raw = (self.args or "").strip()
        if not raw or raw.lower() == "balance":  # noqa: STRING_LITERAL
            self._show_balance()
            return
        parts = raw.split()
        if parts[0].lower() != "claim" or len(parts) != _KUDOS_CLAIM_ARGC:  # noqa: STRING_LITERAL
            msg = "Usage: kudos claim <category_id> <amount>"
            raise CommandError(msg)
        try:
            category_id = int(parts[1])
            amount = int(parts[2])
        except ValueError as exc:
            msg = "Category id and amount must be numbers."
            raise CommandError(msg) from exc
        result = ClaimKudosAction().run(
            actor=self.caller, claim_category_id=category_id, amount=amount
        )
        self.msg(result.message)

    def _show_balance(self) -> None:
        from world.progression.models import KudosClaimCategory, KudosPointsData  # noqa: PLC0415
        from world.roster.selectors import get_account_for_character  # noqa: PLC0415

        account = get_account_for_character(self.caller)
        if account is None:
            msg = "You have no active character on the roster."
            raise CommandError(msg)
        points = KudosPointsData.objects.filter(account=account).first()
        available = points.current_available if points else 0
        lines = [f"Kudos available: {available}", "Claim categories:"]
        lines.extend(
            f"  [{cat.pk}] {cat.display_name} — {cat.kudos_cost} kudos → {cat.reward_amount} XP"
            for cat in KudosClaimCategory.objects.filter(is_active=True).order_by("name")
        )
        self.msg("\n".join(lines))


class CmdVote(ArxCommand):
    """Cast or remove weekly votes on other players' content.

    Usage:
      vote                            - list your current votes and budget
      vote <type> <id>                - cast a vote (type: interaction|participation|journal)
      vote remove <type> <id>         - remove a vote
    """

    key = "vote"
    aliases: ClassVar[list[str]] = []
    locks = "cmd:all()"
    help_category = "Progression"
    action = None

    def func(self) -> None:
        try:
            self._dispatch()
        except CommandError as err:
            self.msg(str(err))

    def _dispatch(self) -> None:
        parts: list[str] = list((self.args or "").strip().split())
        if not parts or parts[0].lower() == "list":  # noqa: STRING_LITERAL
            self._show_votes()
            return
        if parts[0].lower() == "remove":  # noqa: STRING_LITERAL
            target_type, target_id = self._parse_target(parts[1:])
            result = RemoveVoteAction().run(
                actor=self.caller, target_type=target_type, target_id=target_id
            )
        else:
            target_type, target_id = self._parse_target(parts)
            result = CastVoteAction().run(
                actor=self.caller, target_type=target_type, target_id=target_id
            )
        self.msg(result.message)

    def _parse_target(self, parts: list[str]) -> tuple[str, int]:
        if len(parts) != _VOTE_TARGET_ARGC:
            msg = "Usage: vote [remove] <interaction|participation|journal> <id>"
            raise CommandError(msg)
        target_type = _VOTE_TYPES.get(parts[0].lower())
        if target_type is None:
            msg = "Target type must be one of: interaction, participation, journal."
            raise CommandError(msg)
        try:
            return target_type, int(parts[1])
        except ValueError as exc:
            msg = "Target id must be a number."
            raise CommandError(msg) from exc

    def _show_votes(self) -> None:
        from world.progression.services.voting import (  # noqa: PLC0415
            get_or_create_vote_budget,
            get_votes_by_voter,
        )
        from world.roster.selectors import get_account_for_character  # noqa: PLC0415

        account = get_account_for_character(self.caller)
        if account is None:
            msg = "You have no active character on the roster."
            raise CommandError(msg)
        budget = get_or_create_vote_budget(account)
        votes = get_votes_by_voter(account)
        lines = [f"Votes remaining: {budget.votes_remaining}", "Your votes this week:"]
        vote_lines = [f"  {v.target_type} #{v.target_id}" for v in votes]
        lines.extend(vote_lines or ["  (none)"])
        self.msg("\n".join(lines))


class CmdRandomScene(ArxCommand):
    """View, claim, and reroll your weekly random-scene targets.

    Usage:
      randomscene                 - list your weekly targets
      randomscene claim <id>      - claim a target you have shared a scene with
      randomscene reroll <id>     - reroll a target slot (once per week)
    """

    key = "randomscene"
    aliases: ClassVar[list[str]] = ["rscene"]
    locks = "cmd:all()"
    help_category = "Progression"
    action = None

    def func(self) -> None:
        try:
            self._dispatch()
        except CommandError as err:
            self.msg(str(err))

    def _dispatch(self) -> None:
        parts = (self.args or "").strip().split()
        if not parts or parts[0].lower() == "list":  # noqa: STRING_LITERAL
            self._show_targets()
            return
        sub = parts[0].lower()
        if sub not in {"claim", "reroll"} or len(parts) != _RANDOMSCENE_ARGC:  # noqa: STRING_LITERAL
            msg = "Usage: randomscene [claim|reroll] <id>"
            raise CommandError(msg)
        try:
            target_id = int(parts[1])
        except ValueError as exc:
            msg = "Target id must be a number."
            raise CommandError(msg) from exc
        action = ClaimRandomSceneAction() if sub == "claim" else RerollRandomSceneAction()  # noqa: STRING_LITERAL
        result = action.run(actor=self.caller, target_id=target_id)
        self.msg(result.message)

    def _show_targets(self) -> None:
        from world.game_clock.week_services import get_current_game_week  # noqa: PLC0415
        from world.progression.models import RandomSceneTarget  # noqa: PLC0415
        from world.roster.selectors import get_account_for_character  # noqa: PLC0415

        account = get_account_for_character(self.caller)
        if account is None:
            msg = "You have no active character on the roster."
            raise CommandError(msg)
        targets = (
            RandomSceneTarget.objects.filter(account=account, game_week=get_current_game_week())
            .select_related("target_persona")
            .order_by("slot_number")
        )
        if not targets:
            self.msg("You have no random-scene targets this week.")
            return
        lines = ["Your random-scene targets this week:"]
        lines.extend(
            f"  [{t.pk}] slot {t.slot_number}: {t.target_persona.name}"
            f" ({'claimed' if t.claimed else 'open'})"
            for t in targets
        )
        self.msg("\n".join(lines))


class CmdPathIntent(ArxCommand):
    """Declare which path you intend to take at your next crossing.

    Usage:
      pathintent              - show your current path and the options
      pathintent <path_id>    - declare your intended next path
      pathintent clear        - clear your declared intent
    """

    key = "pathintent"
    aliases: ClassVar[list[str]] = []
    locks = "cmd:all()"
    help_category = "Progression"
    action = None

    def func(self) -> None:
        try:
            self._dispatch()
        except CommandError as err:
            self.msg(str(err))

    def _dispatch(self) -> None:
        raw = (self.args or "").strip()
        if not raw:
            self._show_options()
            return
        if raw.lower() == "clear":  # noqa: STRING_LITERAL
            result = ClearPathIntentAction().run(actor=self.caller)
            self.msg(result.message)
            return
        try:
            path_id = int(raw)
        except ValueError as exc:
            msg = "Usage: pathintent <path_id> | pathintent clear"
            raise CommandError(msg) from exc
        result = SetPathIntentAction().run(actor=self.caller, path_id=path_id)
        self.msg(result.message)

    def _show_options(self) -> None:
        from world.progression.selectors import (  # noqa: PLC0415
            current_path_for_character,
            next_path_options,
        )

        current = current_path_for_character(self.caller)
        lines = [f"Current path: {current.name if current else '(none)'}", "Next-path options:"]
        options = next_path_options(self.caller)
        path_lines = [f"  [{p.pk}] {p.name}" for p in options]
        lines.extend(path_lines or ["  (none available yet)"])
        self.msg("\n".join(lines))

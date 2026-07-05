"""Telnet command for playing missions (#1349).

Thin telnet face of the mission play services in ``world.missions.services.play``
(+ ``services.journal``). Both the web ``MissionJournalViewSet`` and this command
converge on the *same* service functions — there is no separate Action; the
command only parses text and reports results (mirrors ``CmdRitual``'s session
subcommands and the #1449 soul-tether command).

    ``mission`` / ``mission list``        — list your mission journal
    ``mission beat <id>``                 — show the current beat + numbered options
    ``mission resolve <id> <n>``          — resolve a single-player beat (option n)
    ``mission abandon <id>``              — abandon an ACTIVE run (contract holder)
    ``mission pick <id> <n>``             — group stage 1: submit your pick
    ``mission vote <id> <n>``             — group stage 2: cast your vote

Options are referenced by the small ordinal shown in ``mission beat`` (1..N), not
raw option ids; the presented list already fans out one entry per challenge
approach, so the ordinal fully specifies the choice.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from commands.command import ArxCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from world.missions.models import MissionInstance
    from world.missions.types import BeatOption

_SUBVERBS = frozenset(
    {"list", "beat", "resolve", "abandon", "pick", "vote", "report", "invite", "accept", "decline"}
)
_USAGE = (
    "Usage: mission | mission beat <id> | mission resolve <id> <n> | "
    "mission abandon <id> | mission pick <id> <n> | mission vote <id> <n> | "
    "mission report <id> <style> | mission invite <id> <name> | "
    "mission accept <invite-id> | mission decline <invite-id>"
)
_ERR_NOT_PARTICIPANT = "You are not part of that mission."
_ERR_CHOOSE_NUMBER = "Choose an option by its number, e.g. 'mission resolve <id> 1'."


class CmdMission(ArxCommand):
    """Play a mission: inspect your journal, resolve beats, or run a group decision.

    **Read:**
        ``mission`` / ``mission list``   — your mission journal
        ``mission beat <id>``            — the current beat + numbered options

    **Single-player:**
        ``mission resolve <id> <n>``     — choose option n at the current beat
        ``mission abandon <id>``         — abandon an ACTIVE run (contract holder)

    **Group decision (two stages):**
        ``mission pick <id> <n>``        — submit your stage-1 pick
        ``mission vote <id> <n>``        — cast your stage-2 vote
    """

    key = "mission"
    locks = "cmd:all()"

    def _execute(self) -> None:
        """Route the leading subverb; bare ``mission`` lists the journal."""
        raw = (self.args or "").strip()
        if not raw:
            self._handle_journal()
            return
        parts = raw.split(maxsplit=1)
        subverb = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""
        if subverb not in _SUBVERBS:
            msg = f"Unknown mission action '{subverb}'. {_USAGE}"
            raise CommandError(msg)
        _DISPATCH = {
            "list": lambda: self._handle_journal(),
            "beat": lambda: self._handle_beat(rest),
            "resolve": lambda: self._handle_resolve(rest),
            "abandon": lambda: self._handle_abandon(rest),
            "pick": lambda: self._handle_pick(rest),
            "vote": lambda: self._handle_vote(rest),
            "report": lambda: self._handle_report(rest),
            "invite": lambda: self._handle_invite(rest),
            "accept": lambda: self._handle_respond(rest, accept=True),
            "decline": lambda: self._handle_respond(rest, accept=False),
        }
        _DISPATCH[subverb]()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def _handle_journal(self) -> None:
        from world.missions.services.journal import journal_for  # noqa: PLC0415

        entries = journal_for(self.caller)
        if not entries:
            lines = ["|wYour missions:|n", "  (none)"]
        else:
            lines = ["|wYour missions:|n"]
            for entry in entries:
                node = f" — at {entry.current_node_key}" if entry.current_node_key else ""
                lines.append(
                    f"  [#{entry.instance_id}] {entry.template_name} ({entry.status}){node}"
                )
        self._append_pending_invites(lines)
        self.msg("\n".join(lines))

    def _append_pending_invites(self, lines: list[str]) -> None:
        """Append pending mission invites addressed to the caller's persona (#887)."""
        from world.missions.models import MissionInvite  # noqa: PLC0415

        persona = getattr(self.caller.sheet_data, "primary_persona", None)  # noqa: GETATTR_LITERAL
        if persona is None:
            return
        pending = (
            MissionInvite.objects.filter(
                target_persona=persona, response=MissionInvite.Response.PENDING
            )
            .select_related("instance__template")
            .values_list("pk", "instance__template__name")
        )
        lines.extend(
            f"  [invite #{pk}] {name} — 'mission accept {pk}' / 'mission decline {pk}'"
            for pk, name in pending
        )

    def _handle_beat(self, rest: str) -> None:
        from world.missions.services.play import (  # noqa: PLC0415
            BeatActionError,
            beat_for,
            group_beat,
        )

        instance, _ = self._instance_or_raise(rest)
        node = instance.current_node
        if node is None:
            self.msg(f"Mission #{instance.pk} has concluded.")
            return
        try:
            if self._is_group_beat(instance, node):
                self._render_group_result(instance, group_beat(instance, self.caller))
            else:
                beat = beat_for(instance, self.caller)
                if beat is None:
                    self.msg(f"Mission #{instance.pk} has concluded.")
                    return
                self._render_beat(instance, beat)
        except BeatActionError as exc:
            raise CommandError(exc.user_message) from exc

    # ------------------------------------------------------------------
    # Single-player
    # ------------------------------------------------------------------

    def _handle_resolve(self, rest: str) -> None:
        from world.missions.services.play import (  # noqa: PLC0415
            BeatActionError,
            beat_for,
            resolve_beat_option,
        )

        instance, remainder = self._instance_or_raise(rest)
        node = instance.current_node
        if node is not None and self._is_group_beat(instance, node):
            msg = (
                f"Mission #{instance.pk} is a group decision — use "
                f"'mission pick {instance.pk} <n>' then 'mission vote {instance.pk} <n>'."
            )
            raise CommandError(msg)
        ordinal = self._choice_ordinal(remainder)
        try:
            beat = beat_for(instance, self.caller)
            if beat is None:
                msg = f"Mission #{instance.pk} has concluded."
                raise CommandError(msg)
            option = self._option_at(beat.options, ordinal)
            resolved = resolve_beat_option(
                instance,
                self.caller,
                option_id=option.option_id,
                approach_id=option.approach_id,
            )
        except BeatActionError as exc:
            raise CommandError(exc.user_message) from exc
        self._render_resolved(instance, resolved)

    def _handle_abandon(self, rest: str) -> None:
        from world.missions.services.play import BeatActionError, abandon_mission  # noqa: PLC0415

        instance, _ = self._instance_or_raise(rest)
        try:
            result = abandon_mission(instance, self.caller)
        except BeatActionError as exc:
            raise CommandError(exc.user_message) from exc
        self.msg(f"You abandon {result.template.name} (#{result.pk}). Status: {result.status}.")

    def _handle_report(self, rest: str) -> None:
        """``mission report <id> <style>`` — report a RESOLVED run's outcome (#1753)."""
        from world.missions.services.report import (  # noqa: PLC0415
            MissionReportError,
            report_mission,
        )

        instance, remainder = self._instance_or_raise(rest)
        style = remainder.strip().lower().replace("-", "_")
        if not style:
            msg = "Choose how to report: humble, accurate, or embellished."
            raise CommandError(msg)
        try:
            result = report_mission(instance=instance, style=style, reporter=self.caller)
        except MissionReportError as exc:
            raise CommandError(exc.user_message) from exc
        line = (
            f"You report {result.instance.template.name} (#{result.instance.pk}) — {result.style}."
        )
        if result.embellish_success is False:
            line += " Your embellishment falls flat."
        self.msg(line)

    # ------------------------------------------------------------------
    # Invite / respond (#887)
    # ------------------------------------------------------------------

    def _handle_invite(self, rest: str) -> None:
        """``mission invite <id> <name>`` — invite a co-located character."""
        from world.missions.services.run import (  # noqa: PLC0415
            InviteError,
            invite_to_mission,
        )

        instance, remainder = self._instance_or_raise(rest)
        name = remainder.strip()
        if not name:
            msg = "Invite whom? Usage: mission invite <id> <name>"
            raise CommandError(msg)
        target = self.caller.search(name)
        if target is None:
            return  # search already sent a "not found" message
        holder_persona = getattr(self.caller.sheet_data, "primary_persona", None)  # noqa: GETATTR_LITERAL
        invitee_persona = getattr(target.sheet_data, "primary_persona", None)  # noqa: GETATTR_LITERAL
        if holder_persona is None or invitee_persona is None:
            msg = "Both characters need a persona."
            raise CommandError(msg)
        try:
            invite = invite_to_mission(instance, holder_persona, invitee_persona)
        except InviteError as exc:
            raise CommandError(exc.user_message) from exc
        self.msg(f"You invite {target.key} to join mission #{instance.pk} (invite #{invite.pk}).")

    def _handle_respond(self, rest: str, *, accept: bool) -> None:
        """``mission accept|decline <invite-id>`` — respond to an invitation."""
        from world.missions.models import MissionInvite  # noqa: PLC0415
        from world.missions.services.run import (  # noqa: PLC0415
            InviteError,
            respond_to_mission_invite,
        )

        token = rest.strip()
        if not token.isdigit():
            msg = "Which invitation? Usage: mission accept <invite-id>"
            raise CommandError(msg)
        persona = getattr(self.caller.sheet_data, "primary_persona", None)  # noqa: GETATTR_LITERAL
        if persona is None:
            msg = "You have no active persona."
            raise CommandError(msg)
        invite = MissionInvite.objects.filter(pk=int(token), target_persona=persona).first()
        if invite is None:
            raise CommandError(_ERR_NOT_PARTICIPANT)
        decision = MissionInvite.Response.ACCEPTED if accept else MissionInvite.Response.DECLINED
        try:
            respond_to_mission_invite(invite, decision)
        except InviteError as exc:
            raise CommandError(exc.user_message) from exc
        verb = "accept" if accept else "decline"
        self.msg(f"You {verb} the invitation to mission #{invite.instance_id}.")

    # ------------------------------------------------------------------
    # Group decision
    # ------------------------------------------------------------------

    def _handle_pick(self, rest: str) -> None:
        from world.missions.services.play import (  # noqa: PLC0415
            BeatActionError,
            group_beat,
            submit_group_pick,
        )

        instance, remainder = self._require_group_beat(rest)
        ordinal = self._choice_ordinal(remainder)
        try:
            option = self._group_option_at(instance, group_beat, ordinal)
            result = submit_group_pick(
                instance,
                self.caller,
                option_id=option.option_id,
                approach_id=option.approach_id,
            )
        except BeatActionError as exc:
            raise CommandError(exc.user_message) from exc
        self.msg(f"You pick '{option.label}'.")
        self._render_group_result(instance, result)

    def _handle_vote(self, rest: str) -> None:
        from world.missions.services.play import (  # noqa: PLC0415
            BeatActionError,
            cast_group_vote,
            group_beat,
        )

        instance, remainder = self._require_group_beat(rest)
        ordinal = self._choice_ordinal(remainder)
        try:
            option = self._group_option_at(instance, group_beat, ordinal)
            result = cast_group_vote(instance, self.caller, option_id=option.option_id)
        except BeatActionError as exc:
            raise CommandError(exc.user_message) from exc
        self.msg(f"You vote for '{option.label}'.")
        self._render_group_result(instance, result)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _instance_or_raise(self, rest: str) -> tuple[MissionInstance, str]:
        """Parse the leading id as a participant-scoped instance; return (instance, rest)."""
        from world.missions.models import MissionInstance  # noqa: PLC0415

        rest = rest.strip()
        if not rest:
            raise CommandError(_USAGE)
        token, _, remainder = rest.partition(" ")
        if not token.isdigit():
            msg = f"Mission id must be a number. {_USAGE}"
            raise CommandError(msg)
        instance = MissionInstance.objects.filter(
            pk=int(token), participants__character=self.caller
        ).first()
        if instance is None:
            # Same message whether it doesn't exist or you're not on it — a
            # non-participant must not learn which instance ids exist.
            raise CommandError(_ERR_NOT_PARTICIPANT)
        return instance, remainder.strip()

    def _require_group_beat(self, rest: str) -> tuple[MissionInstance, str]:
        instance, remainder = self._instance_or_raise(rest)
        node = instance.current_node
        if node is None or not self._is_group_beat(instance, node):
            msg = (
                f"Mission #{instance.pk} isn't a group decision — use "
                f"'mission resolve {instance.pk} <n>'."
            )
            raise CommandError(msg)
        return instance, remainder

    @staticmethod
    def _is_group_beat(instance: MissionInstance, node: Any) -> bool:
        """True when the node resolves as a group decision and the run is shared."""
        from world.missions.constants import ConflictMode  # noqa: PLC0415

        return (
            node.conflict_mode in (ConflictMode.GROUP_VOTE, ConflictMode.JOINT)
            and instance.participants.count() > 1
        )

    def _choice_ordinal(self, remainder: str) -> int:
        token = remainder.strip().split()[0] if remainder.strip() else ""
        if not token.isdigit():
            raise CommandError(_ERR_CHOOSE_NUMBER)
        return int(token)

    def _option_at(self, options: tuple[BeatOption, ...], ordinal: int) -> BeatOption:
        if ordinal < 1 or ordinal > len(options):
            msg = (
                f"There is no option {ordinal} here (choose 1-{len(options)})."
                if options
                else "There are no options to choose at this beat."
            )
            raise CommandError(msg)
        return options[ordinal - 1]

    def _group_option_at(
        self, instance: MissionInstance, group_beat: Any, ordinal: int
    ) -> BeatOption:
        result = group_beat(instance, self.caller)
        if result.group_beat is None:
            msg = f"Mission #{instance.pk} is no longer at a group decision."
            raise CommandError(msg)
        return self._option_at(result.group_beat.options, ordinal)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render_beat(self, instance: MissionInstance, beat: Any) -> None:
        lines = [f"|w{beat.template_name} — {beat.node_key}|n"]
        if beat.flavor_text:
            lines.append(beat.flavor_text)
        if not beat.options:
            lines.append("(No options here — follow where the compass points.)")
        for i, opt in enumerate(beat.options, 1):
            suffix = f" [{opt.check_type_name}]" if opt.check_type_name else ""
            lines.append(f"  {i}) {opt.label}{suffix}")
        if beat.options:
            lines.append(f"Use 'mission resolve {instance.pk} <n>' to choose.")
        self.msg("\n".join(lines))

    def _render_resolved(self, instance: MissionInstance, resolved: Any) -> None:
        lines = [resolved.story_text]
        if resolved.outcome_name:
            lines.append(f"Outcome: {resolved.outcome_name}.")
        if resolved.is_terminal:
            if resolved.epilogue:
                lines.append(resolved.epilogue)
            lines.append("This mission is complete.")
        else:
            lines.append(f"Use 'mission beat {instance.pk}' to see what comes next.")
        self.msg("\n".join(lines))

    def _render_group_result(self, instance: MissionInstance, result: Any) -> None:
        from world.missions.services.play import PHASE_VOTE  # noqa: PLC0415

        if result.resolved is not None:
            self.msg("The group decides.")
            self._render_resolved(instance, result.resolved)
            return
        view = result.group_beat
        if view is None:
            self.msg(f"Mission #{instance.pk} group decision updated.")
            return
        lines = [f"|wGroup decision — {view.node_key}|n (phase: {view.phase})"]
        if view.flavor_text:
            lines.append(view.flavor_text)
        for i, opt in enumerate(view.options, 1):
            lines.append(f"  {i}) {opt.label}")
        verb = "vote" if view.phase == PHASE_VOTE else "pick"  # noqa: STRING_LITERAL
        lines.append(f"Use 'mission {verb} {instance.pk} <n>'.")
        self.msg("\n".join(lines))

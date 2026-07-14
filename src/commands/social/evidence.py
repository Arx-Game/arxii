"""Telnet ``evidence`` command (#1825) — the physical-evidence namespace.

Thin over the evidence Actions (the same seams the web dispatches): **gather** what a
crime left at this scene, **dispose** of what you hold, **produce** a filed frame's
evidence from the case file (authority-gated), **examine** what you're holding against
the forger's craft. No business logic in the command.
"""

from __future__ import annotations

from typing import Any

from commands.command import ArxCommand
from commands.exceptions import CommandError

_USAGE = "Usage: evidence [gather [<id>] | dispose <id> | produce <#> | examine <id>]"

_GATHER = "gather"
_DISPOSE = "dispose"
_PRODUCE = "produce"
_EXAMINE = "examine"
_LIST = "list"


class CmdEvidence(ArxCommand):
    """Work the physical evidence a crime leaves behind.

    Usage:
      evidence               — evidence at this scene (of your own deeds) + what you hold
      evidence gather [<id>] — claim evidence lying at this scene (Skulduggery)
      evidence dispose <id>  — destroy evidence you hold (Skulduggery)
      evidence produce <#>   — pull a filed case's evidence from storage (needs authority)
      evidence examine <id>  — scrutinize produced evidence for tampering
    """

    key = "evidence"
    locks = "cmd:all()"
    action = None

    def _execute(self) -> None:
        raw = (self.args or "").strip()
        if not raw or raw.lower() == _LIST:
            self._show()
            return
        verb, _, rest = raw.partition(" ")
        verb, rest = verb.lower(), rest.strip()
        if verb == _GATHER:
            self._gather(rest)
        elif verb == _DISPOSE:
            self._dispatch_by_id("dispose_evidence", rest)
        elif verb == _EXAMINE:
            self._dispatch_by_id("examine_evidence", rest)
        elif verb == _PRODUCE:
            self._produce(rest)
        else:
            self.msg(_USAGE)

    def _own_evidence_here(self) -> list[Any]:
        """AT_SCENE evidence in this room from the caller's own deeds — you know
        what your crime left behind; finding someone else's is discovery's job."""
        from world.justice.constants import EvidenceState  # noqa: PLC0415
        from world.justice.models import CrimeEvidence  # noqa: PLC0415

        sheet = self.caller.character_sheet
        room = self.caller.location
        if sheet is None or room is None:
            return []
        return list(
            CrimeEvidence.objects.filter(
                state=EvidenceState.AT_SCENE,
                room_profile__objectdb=room,
                deed__persona__character_sheet=sheet,
            )
        )

    def _held_evidence(self) -> list[Any]:
        from world.justice.models import CrimeEvidence  # noqa: PLC0415

        sheet = self.caller.character_sheet
        if sheet is None:
            return []
        return list(
            CrimeEvidence.objects.filter(
                item_instance__holder_character_sheet=sheet
            ).select_related("deed")
        )

    def _show(self) -> None:
        lines: list[str] = []
        here = self._own_evidence_here()
        if here:
            lines.append("|wYour crime's leavings, here:|n")
            lines += [f"  {evidence.pk}. traces of: {evidence.deed.title}" for evidence in here]
        held = self._held_evidence()
        if held:
            lines.append("|wEvidence you hold:|n")
            lines += [
                f"  {evidence.pk}. {evidence.deed.title} ({evidence.get_state_display()})"
                for evidence in held
            ]
        if not lines:
            self.msg("No evidence of yours lies here, and you hold none.")
            return
        self.msg("\n".join(lines))

    def _resolve_id(self, arg: str) -> int:
        try:
            return int(arg)
        except (ValueError, TypeError):
            raise CommandError(_USAGE) from None

    def _gather(self, arg: str) -> None:
        from actions.registry import ACTIONS_BY_KEY  # noqa: PLC0415

        if arg:
            evidence_id = self._resolve_id(arg)
        else:
            here = self._own_evidence_here()
            if len(here) != 1:
                self.msg("Name the evidence: |wevidence gather <id>|n (see |wevidence|n).")
                return
            evidence_id = here[0].pk
        result = ACTIONS_BY_KEY["gather_evidence"].run(self.caller, evidence_id=evidence_id)
        self.msg(result.message)

    def _dispatch_by_id(self, action_key: str, arg: str) -> None:
        from actions.registry import ACTIONS_BY_KEY  # noqa: PLC0415

        evidence_id = self._resolve_id(arg)
        result = ACTIONS_BY_KEY[action_key].run(self.caller, evidence_id=evidence_id)
        self.msg(result.message)

    def _produce(self, arg: str) -> None:
        """`evidence produce <#>` — # indexes your known frame-anchored accusations."""
        from actions.registry import ACTIONS_BY_KEY  # noqa: PLC0415
        from world.justice.models import AccusationCrimeClaim  # noqa: PLC0415
        from world.roster.models import RosterEntry  # noqa: PLC0415
        from world.secrets.services import known_secrets_for  # noqa: PLC0415

        sheet = self.caller.character_sheet
        if sheet is None:
            self.msg("You have no character identity.")
            return
        try:
            entry = sheet.roster_entry
        except RosterEntry.DoesNotExist:
            self.msg("You have no roster identity.")
            return
        anchored = [
            knowledge.secret
            for knowledge in known_secrets_for(entry)
            if AccusationCrimeClaim.objects.filter(
                secret=knowledge.secret, real_deed__isnull=False
            ).exists()
        ]
        if not arg:
            if not anchored:
                self.msg("You know of no filed cases with evidence to produce.")
                return
            lines = ["|wFiled cases you could pull evidence from:|n"]
            lines += [f"  {index}. {secret.content}" for index, secret in enumerate(anchored, 1)]
            lines.append("Use |wevidence produce <#>|n (needs standing with the local law).")
            self.msg("\n".join(lines))
            return
        position = self._resolve_id(arg) - 1
        if not 0 <= position < len(anchored):
            self.msg(f"No case #{arg}. See |wevidence produce|n for the list.")
            return
        result = ACTIONS_BY_KEY["produce_case_evidence"].run(
            self.caller, secret_id=anchored[position].pk
        )
        self.msg(result.message)

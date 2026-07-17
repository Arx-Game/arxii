"""Telnet ``gm dashboard`` + ``gm idle`` commands (#2004).

Thin over the same services the web ``GMDashboardView`` and
``StaffWorkloadView`` call. ``gm dashboard`` is GM-gated; ``gm idle`` is
staff-only (``perm(Admin)``).

``gm check``/``gm award``/``gm condition`` (#2118) are the GM adjudication
toolkit's telnet face — thin ``resolve_action_args()``-style parsing +
``action.run()`` over ``InvokeCatalogCheckAction``/``GMAwardAction``/
``GMApplyConditionAction`` (``actions/definitions/gm_adjudication.py``), the
same seam the web available-actions dispatcher uses.

``gm suggest <kind>=<text>`` (#2127) is the scenario catalog's suggestion
inbox verb — thin over ``SubmitCatalogSuggestionAction``
(``actions/definitions/gm_catalog.py``), landing in the same staff inbox
``GMApplication`` already routes through.
"""

from __future__ import annotations

from typing import Any

from commands.command import ArxCommand
from commands.exceptions import CommandError
from commands.parsing import parse_kv_and_flags
from commands.utils.gm_resolution import resolve_character_sheet_in_room

_USAGE_DASHBOARD = "Usage: gm dashboard"
_USAGE_IDLE = "Usage: gm idle"
_USAGE_CLAIM = "Usage: gm claim <request-id>"
_USAGE_CHECK = (
    "Usage: gm check [find <term>] | gm check <character> <check-type>=<band>"
    " [edge=<reason>|setback=<reason>]"
)
_USAGE_AWARD = (
    "Usage: gm award <character> xp=<amount> [reason=<text>]"
    " | gm award <character> dev=<trait> amount=<n> [reason=<text>]"
    " | gm award <character> hare=<organization> reason=<text>"
)
_USAGE_CONDITION = (
    "Usage: gm condition <character> condition=<name> [severity=<n>] [duration=<n>] [note=<text>]"
)
_USAGE_SUGGEST = (
    "Usage: gm suggest <kind>=<text>"
    " (kind: new_situation|check_fit|difficulty_guide|pool_guide|other)"
)

# parse_kv_and_flags key names -- module constants so the STRING_LITERAL lint's
# comparison/membership check doesn't see bare identifier-shaped literals.
_KEY_XP = "xp"
_KEY_DEV = "dev"
_KEY_HARE = "hare"
_KEY_SEVERITY = "severity"
_KEY_DURATION = "duration"
_KEY_NOTE = "note"


class CmdGMDashboard(ArxCommand):
    """Show the GM dashboard — tables, sessions, stories needing attention (#2004).

    Usage:
      gm dashboard
      gm claim <request-id>
      gm check [find <term>]
      gm check <character> <check-type>=<band> [edge=<reason>|setback=<reason>]
      gm award <character> xp=<amount> [reason=<text>]
      gm award <character> dev=<trait> amount=<n> [reason=<text>]
      gm award <character> hare=<organization> reason=<text>
      gm condition <character> condition=<name> [severity=<n>] [duration=<n>] [note=<text>]
      gm suggest <kind>=<text>
    """

    key = "gm"
    aliases = ("gmdashboard",)
    locks = "cmd:all()"
    help_category = "GM"
    action = None

    def func(self) -> None:
        """Route the leading subverb, falling back to the dashboard render."""
        try:
            raw = (self.args or "").strip()
            tokens = raw.split(maxsplit=1)
            first = tokens[0].lower() if tokens else ""
            rest = tokens[1].strip() if len(tokens) > 1 else ""
            if first == "claim":  # noqa: STRING_LITERAL
                self._claim(rest)
            elif first == "check":  # noqa: STRING_LITERAL
                self._handle_check(rest)
            elif first == "award":  # noqa: STRING_LITERAL
                self._handle_award(rest)
            elif first == "condition":  # noqa: STRING_LITERAL
                self._handle_condition(rest)
            elif first == "suggest":  # noqa: STRING_LITERAL
                self._handle_suggest(rest)
            else:
                self._render()
        except CommandError as err:
            self.msg(str(err))

    def _claim(self, rest: str) -> None:
        """``gm claim <request-id>`` — claim an open group story request (#2119)."""
        rest = rest.strip()
        if not rest.isdigit():
            raise CommandError(_USAGE_CLAIM)
        from actions.definitions.gm_stories import ClaimGroupStoryRequestAction  # noqa: PLC0415

        result = ClaimGroupStoryRequestAction().run(actor=self.caller, request_id=int(rest))
        self.msg(result.message)

    def _resolve_target(self, name: str) -> Any:
        """Resolve a co-located character by name; raises CommandError if absent."""
        room = self.caller.location
        if room is None:
            msg = "You are not in a room."
            raise CommandError(msg)
        sheet = resolve_character_sheet_in_room(self.caller, name, room=room)
        return sheet.character

    def _handle_check(self, rest: str) -> None:
        """Dispatch InvokeCatalogCheckAction -- find/list mode or invoke mode."""
        from actions.definitions.gm_adjudication import InvokeCatalogCheckAction  # noqa: PLC0415

        tokens = rest.split(maxsplit=1)
        first = tokens[0] if tokens else ""
        if first in ("", "find"):  # noqa: STRING_LITERAL
            query = tokens[1].strip() if len(tokens) > 1 else ""
            result = InvokeCatalogCheckAction().run(actor=self.caller, query=query)
            if result.message:
                self.msg(result.message)
            return

        char_name = first
        kv_rest = tokens[1] if len(tokens) > 1 else ""
        # The check-type reference IS the key (e.g. "Grapple=hard") -- it can't be
        # pre-registered as a multiword key since it's arbitrary/unknown ahead of
        # parsing, so a multi-word check name must be referenced by pk here (mirrors
        # the documented multi-word-name limitation in parse_targets_from_text).
        try:
            kwargs, _flags = parse_kv_and_flags(
                kv_rest,
                multiword_keys=frozenset({"edge", "setback"}),
                known_flags=frozenset(),
            )
        except CommandError:
            raise CommandError(_USAGE_CHECK) from None
        edge_reason = kwargs.pop("edge", None)
        setback_reason = kwargs.pop("setback", None)
        if len(kwargs) != 1:
            raise CommandError(_USAGE_CHECK)
        ((check_type_ref, difficulty),) = kwargs.items()

        target = self._resolve_target(char_name)
        run_kwargs: dict[str, Any] = {
            "target": target,
            "check_type_ref": check_type_ref,
            "difficulty": difficulty,
        }
        if edge_reason:
            run_kwargs["edge_reason"] = edge_reason
        if setback_reason:
            run_kwargs["setback_reason"] = setback_reason

        result = InvokeCatalogCheckAction().run(actor=self.caller, **run_kwargs)
        if result.message:
            self.msg(result.message)

    def _handle_award(self, rest: str) -> None:
        """Dispatch GMAwardAction -- xp=<amount>, dev=<trait> amount=<n>, or hare=<org>."""
        from actions.definitions.gm_adjudication import GMAwardAction  # noqa: PLC0415

        tokens = rest.split(maxsplit=1)
        if not tokens:
            raise CommandError(_USAGE_AWARD)
        char_name = tokens[0]
        kv_rest = tokens[1] if len(tokens) > 1 else ""
        kwargs, _flags = parse_kv_and_flags(
            kv_rest,
            multiword_keys=frozenset({"reason", _KEY_HARE}),
            known_flags=frozenset(),
        )
        reason = kwargs.pop("reason", "")

        target = self._resolve_target(char_name)
        run_kwargs: dict[str, Any] = {"target": target, "description": reason}
        if _KEY_XP in kwargs:
            run_kwargs["award_type"] = "xp"
            run_kwargs["amount"] = kwargs[_KEY_XP]
        elif _KEY_DEV in kwargs:
            run_kwargs["award_type"] = "development"
            run_kwargs["trait_ref"] = kwargs[_KEY_DEV]
            run_kwargs["amount"] = kwargs.get("amount")
        elif _KEY_HARE in kwargs:
            run_kwargs["award_type"] = "favor_token"
            run_kwargs["org_ref"] = kwargs[_KEY_HARE]
        else:
            raise CommandError(_USAGE_AWARD)

        result = GMAwardAction().run(actor=self.caller, **run_kwargs)
        if result.message:
            self.msg(result.message)

    def _handle_condition(self, rest: str) -> None:
        """Dispatch GMApplyConditionAction -- condition=<name> [severity=][duration=][note=]."""
        from actions.definitions.gm_adjudication import GMApplyConditionAction  # noqa: PLC0415

        tokens = rest.split(maxsplit=1)
        if not tokens:
            raise CommandError(_USAGE_CONDITION)
        char_name = tokens[0]
        kv_rest = tokens[1] if len(tokens) > 1 else ""
        kwargs, _flags = parse_kv_and_flags(
            kv_rest,
            multiword_keys=frozenset({"condition", "note"}),
            known_flags=frozenset(),
        )
        condition_ref = kwargs.get("condition")
        if not condition_ref:
            raise CommandError(_USAGE_CONDITION)

        target = self._resolve_target(char_name)
        run_kwargs: dict[str, Any] = {
            "target": target,
            "condition_ref": condition_ref,
        }
        if _KEY_SEVERITY in kwargs:
            run_kwargs["severity"] = kwargs[_KEY_SEVERITY]
        if _KEY_DURATION in kwargs:
            run_kwargs["duration_rounds"] = kwargs[_KEY_DURATION]
        if _KEY_NOTE in kwargs:
            run_kwargs["note"] = kwargs[_KEY_NOTE]

        result = GMApplyConditionAction().run(actor=self.caller, **run_kwargs)
        if result.message:
            self.msg(result.message)

    def _handle_suggest(self, rest: str) -> None:
        """Dispatch SubmitCatalogSuggestionAction -- <kind>=<text> (#2127)."""
        from actions.definitions.gm_catalog import SubmitCatalogSuggestionAction  # noqa: PLC0415

        if "=" not in rest:
            raise CommandError(_USAGE_SUGGEST)
        kind, _, text = rest.partition("=")
        proposal_kind = kind.strip().lower()
        proposal_text = text.strip()
        if not proposal_kind or not proposal_text:
            raise CommandError(_USAGE_SUGGEST)

        result = SubmitCatalogSuggestionAction().run(
            actor=self.caller,
            proposal_kind=proposal_kind,
            proposal_text=proposal_text,
        )
        if result.message:
            self.msg(result.message)

    def _render(self) -> None:
        raw = (self.args or "").strip().lower()
        if raw and raw != "dashboard":  # noqa: STRING_LITERAL
            raise CommandError(_USAGE_DASHBOARD)
        from world.gm.models import GMProfile  # noqa: PLC0415

        try:
            gm_profile = self.caller.account.gm_profile
        except GMProfile.DoesNotExist:
            msg = "You must have a GM profile to use this command."
            raise CommandError(msg) from None

        from world.gm.constants import GMTableStatus  # noqa: PLC0415
        from world.gm.models import GMTable  # noqa: PLC0415
        from world.gm.services import gm_evidence_summary  # noqa: PLC0415
        from world.stories.constants import (  # noqa: PLC0415
            StoryGMOfferStatus,
        )
        from world.stories.models import (  # noqa: PLC0415
            StoryGMOffer,
        )
        from world.stories.views import _collect_gm_queue  # noqa: PLC0415

        buckets = _collect_gm_queue(gm_profile)
        lines = ["GM Dashboard:"]
        lines.append(f"  Episodes ready to run: {len(buckets.episodes_ready)}")
        lines.append(f"  Pending AGM claims: {len(buckets.pending_claims)}")
        lines.append(f"  Assigned sessions: {len(buckets.assigned_requests)}")
        lines.append(f"  Stories waiting on you: {len(buckets.waiting_for_gm)}")

        my_tables = GMTable.objects.filter(gm=gm_profile, status=GMTableStatus.ACTIVE)
        lines.append(f"  Active tables: {my_tables.count()}")
        lines.extend(f"    [{table.pk}] {table.name}" for table in my_tables)

        pending_offers = StoryGMOffer.objects.filter(
            offered_to=gm_profile, status=StoryGMOfferStatus.PENDING
        ).count()
        lines.append(f"  Pending story offers: {pending_offers}")

        lines.append(f"  Open group requests: {len(buckets.open_group_requests)}")
        lines.extend(
            f"    [{req['request_id']}] {req['covenant_name']}"
            for req in buckets.open_group_requests
        )

        evidence = gm_evidence_summary(gm_profile)
        lines.append(f"  Level: {evidence.level} | Stories running: {evidence.stories_running}")
        self.msg("\n".join(lines))


class CmdGMIdle(ArxCommand):
    """List idle GM tables (staff-only, #2004).

    Usage:
      gm idle
    """

    key = "gmidle"
    aliases = ()
    locks = "cmd:perm(Admin)"
    help_category = "Staff"
    action = None

    def func(self) -> None:
        """List idle tables whose GM hasn't been active recently."""
        from world.gm.services import idle_tables  # noqa: PLC0415

        tables = list(idle_tables())
        if not tables:
            self.msg("No idle tables.")
            return
        lines = [f"Idle tables ({len(tables)}):"]
        for table in tables:
            gm_name = table.gm.account.username
            last = table.gm.last_active_at
            last_str = last.strftime("%Y-%m-%d") if last else "never"
            lines.append(f"  [{table.pk}] {table.name} — GM: {gm_name} (last active: {last_str})")
        self.msg("\n".join(lines))

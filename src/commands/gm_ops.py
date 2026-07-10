"""Telnet ``gm dashboard`` + ``gm idle`` commands (#2004).

Thin over the same services the web ``GMDashboardView`` and
``StaffWorkloadView`` call. ``gm dashboard`` is GM-gated; ``gm idle`` is
staff-only (``perm(Admin)``).
"""

from __future__ import annotations

from commands.command import ArxCommand
from commands.exceptions import CommandError

_USAGE_DASHBOARD = "Usage: gm dashboard"
_USAGE_IDLE = "Usage: gm idle"
_USAGE_CLAIM = "Usage: gm claim <request-id>"


class CmdGMDashboard(ArxCommand):
    """Show the GM dashboard — tables, sessions, stories needing attention (#2004).

    Usage:
      gm dashboard
      gm claim <request-id>
    """

    key = "gm"
    aliases = ("gmdashboard",)
    locks = "cmd:all()"
    help_category = "GM"
    action = None

    def func(self) -> None:
        """Render a text summary of the GM dashboard, or claim a group story request."""
        try:
            raw = (self.args or "").strip()
            tokens = raw.split(None, 1)
            if tokens and tokens[0].lower() == "claim":  # noqa: STRING_LITERAL
                self._claim(tokens[1] if len(tokens) > 1 else "")
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

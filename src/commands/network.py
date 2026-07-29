"""Telnet command for org tasking + spy networks (#2820).

    network                      - board hub: tasks, agents listening, harvests
    network issue <template> org=<org> [target=<room|org|char>]
    network assign <task-id> = <agent>
    network accept <task-id>
    network post <agent>         - post an agent as this room's listener
    network collect              - collect from your listener here (in person)
    network sweep                - search this room for informants
    network clear                - usher listeners out (room authority)
    network suppress             - intimidate this room's sitting listener
    network flip                 - turn this room's sitting listener
    network plant <post-id> <character> = <the lie>

Thin over the REGISTRY actions in ``actions/definitions/tasking.py`` — the
same seam the web tasking board uses. Name→pk resolution is the only work
done here; all gating (leadership, membership, consent, presence, checks)
lives in the actions and services.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from commands.command import ArxCommand

if TYPE_CHECKING:
    from world.assets.models import NPCAsset
    from world.scenes.models import Persona

_USAGE = (
    "Usage: network | network issue <template> org=<org> | "
    "network assign <task-id> = <agent> | network accept <task-id> | "
    "network post <agent> | network collect | network sweep | network clear | "
    "network suppress | network flip | network plant <post-id> <char> = <lie>"
)


class CmdNetwork(ArxCommand):
    """Run your spy network: tasks, listeners, and counter-intelligence.

    Usage:
        network
        network issue <template> org=<org>
        network assign <task id> = <agent name>
        network accept <task id>
        network post <agent name>
        network collect
        network sweep
        network clear
        network suppress
        network flip
        network plant <post id> <character> = <the lie>

    Bare `network` shows your board. Dispatching an agent rolls YOUR
    handling check now; the agent's own roll resolves offscreen at the
    deadline. Collection means going to your agent in person.
    """

    key = "network"
    aliases = ("spynet",)
    locks = "cmd:all()"
    help_category = "Social"
    action = None  # routes to multiple actions

    def func(self) -> None:
        args = (self.args or "").strip()
        if not args:
            self._run("list_org_tasks")
            return
        subverb, _, rest = args.partition(" ")
        handler = {
            "board": lambda r: self._run("list_org_tasks"),  # noqa: ARG005
            "issue": self._issue,
            "assign": self._assign,
            "accept": self._accept,
            "post": self._post,
            "collect": lambda r: self._run("collect_harvest"),  # noqa: ARG005
            "sweep": lambda r: self._run("detect_listeners"),  # noqa: ARG005
            "clear": lambda r: self._run("clear_room_listeners"),  # noqa: ARG005
            "suppress": lambda r: self._run("suppress_listener"),  # noqa: ARG005
            "flip": lambda r: self._run("flip_listener"),  # noqa: ARG005
            "plant": self._plant,
        }.get(subverb.lower())
        if handler is None:
            self.msg(_USAGE)
            return
        handler(rest.strip())

    def _run(self, action_key: str, **kwargs: Any) -> None:
        from actions.registry import get_action  # noqa: PLC0415

        result = get_action(action_key).run(self.caller, **kwargs)
        self.msg(result.message)

    def _issue(self, rest: str) -> None:
        from world.societies.models import Organization  # noqa: PLC0415
        from world.tasking.models import TaskTemplate  # noqa: PLC0415

        head, _, org_part = rest.partition("org=")
        template_name = head.strip()
        org_name = org_part.strip()
        if not template_name or not org_name:
            self.msg("Usage: network issue <template> org=<org>")
            return
        template = self._by_pk_or_name(TaskTemplate, template_name)
        org = self._by_pk_or_name(Organization, org_name)
        if template is None or org is None:
            self.msg("No such template or organization.")
            return
        self._run("issue_org_task", template_id=template.pk, org_id=org.pk)

    def _assign(self, rest: str) -> None:
        task_id, _, agent_name = rest.partition("=")
        task_id = task_id.strip()
        agent = self._resolve_agent(agent_name.strip())
        if not task_id.isdigit() or agent is None:
            self.msg("Usage: network assign <task id> = <agent name>")
            return
        self._run("assign_task_agent", task_id=int(task_id), npc_asset_id=agent.pk)

    def _accept(self, rest: str) -> None:
        if not rest.isdigit():
            self.msg("Usage: network accept <task id>")
            return
        self._run("accept_org_task", task_id=int(rest))

    def _post(self, rest: str) -> None:
        agent = self._resolve_agent(rest)
        if agent is None:
            self.msg("Usage: network post <agent name> (one of your agents)")
            return
        self._run("post_listener", npc_asset_id=agent.pk)

    def _plant(self, rest: str) -> None:
        head, _, content = rest.partition("=")
        post_id, _, char_name = head.strip().partition(" ")
        content = content.strip()
        char_name = char_name.strip()
        if not post_id.isdigit() or not char_name or not content:
            self.msg("Usage: network plant <post id> <character> = <the lie>")
            return
        target = self.caller.search(char_name, global_search=True, quiet=True)
        target = target[0] if target else None
        try:
            sheet = target.sheet_data if target else None
        except AttributeError:
            sheet = None
        if sheet is None:
            self.msg("No such character.")
            return
        self._run(
            "plant_red_herring",
            post_id=int(post_id),
            subject_sheet_id=sheet.pk,
            content=content,
        )

    def _resolve_agent(self, name: str) -> NPCAsset | None:
        """Resolve one of the caller's reachable agents by name or pk.

        Own assets first, then assets held by orgs the caller belongs to.
        """
        from world.assets.constants import AssetStatus  # noqa: PLC0415
        from world.assets.models import NPCAsset  # noqa: PLC0415
        from world.societies.models import OrganizationMembership  # noqa: PLC0415

        if not name:
            return None
        persona = self._active_persona()
        if persona is None:
            return None
        reachable = NPCAsset.objects.filter(status=AssetStatus.ACTIVE)
        member_org_ids = OrganizationMembership.objects.filter(
            persona=persona,
            left_at__isnull=True,
            exiled_at__isnull=True,
        ).values_list("organization_id", flat=True)
        from django.db.models import Q  # noqa: PLC0415

        reachable = reachable.filter(
            Q(promoter_persona=persona) | Q(promoter_org_id__in=member_org_ids)
        )
        if name.isdigit():
            return reachable.filter(pk=int(name)).first()
        return reachable.filter(asset_persona__name__iexact=name).first()

    def _active_persona(self) -> Persona | None:
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        try:
            sheet = self.caller.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            return None
        return active_persona_for_sheet(sheet)

    @staticmethod
    def _by_pk_or_name(model: type, token: str) -> Any:
        if token.isdigit():
            return model.objects.filter(pk=int(token)).first()
        return model.objects.filter(name__iexact=token).first()

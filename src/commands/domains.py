"""Telnet domain-management namespace command (#2239).

One ``domain`` command routes a leading subverb to the four in-play domain
Actions — holding/improve/appoint/vacate — plus read-only ``list``/``offices``.
No business logic lives here: parse, resolve model instances, call the Action;
authorization is re-checked in the Action layer.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from commands.command import ArxCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from world.societies.houses.models import Domain

_MIN_APPOINT_ARGS = 2  # domain appoint <domain> <char> requires at least two tokens


def _parse_kwargs(tokens: list[str]) -> tuple[list[str], dict[str, str]]:
    """Split positional tokens from ``key=value`` ones (values run to next ``key=``).

    Positionals must precede kwargs. Once a ``key=`` token is seen, every bare
    token after it appends to that value — so ``name=South Fields`` parses as one
    value — until the next ``key=`` starts a fresh key (the codebase convention,
    mirroring ``CmdJournal``/``CmdRelationship``'s free-text values).
    """
    positional: list[str] = []
    kwargs: dict[str, str] = {}
    current_key: str | None = None
    for token in tokens:
        if "=" in token:
            key, _, value = token.partition("=")
            current_key = key.lower()
            kwargs[current_key] = value
        elif current_key is not None:
            kwargs[current_key] += f" {token}"
        else:
            positional.append(token)
    return positional, kwargs


class CmdDomain(ArxCommand):
    """Run one of your house's domains.

    Syntax:
        domain [list]
        domain offices <domain>
        domain holding <domain> <holding-kind> [name=<text>]
        domain improve <domain> cost=<n> [gross=<n>] [prosperity=<n>] [holding=<id>]
        domain appoint <domain> <char> [title=<text>] [check=<trait>]
        domain vacate <domain>
        domain transfer <source-domain> <target-domain> amount=<n>

    ``holding``/``improve``/``transfer`` require house leadership OR the
    domain-steward office; ``appoint``/``vacate`` require leadership. Omit
    ``<domain>`` when you run exactly one.
    """

    key = "domain"
    locks = "cmd:all()"
    action = None  # routes to multiple actions

    def func(self) -> None:
        try:
            self._dispatch()
        except CommandError as err:
            self.msg(str(err))

    # ------------------------------------------------------------------
    # Dispatch

    def _dispatch(self) -> None:
        args = (self.args or "").strip()
        tokens = args.split()
        if not tokens or tokens[0].lower() == "list":  # noqa: STRING_LITERAL
            self._list()
            return
        first = tokens[0].lower()
        rest = tokens[1:]
        handlers: dict[str, Callable[[list[str]], None]] = {
            "offices": self._offices,
            "holding": self._holding,
            "improve": self._improve,
            "appoint": self._appoint,
            "vacate": self._vacate,
            "transfer": self._transfer,
        }
        handler = handlers.get(first)
        if handler is None:
            msg = "Usage: domain [list|offices|holding|improve|appoint|vacate|transfer] ..."
            raise CommandError(msg)
        handler(rest)

    # ------------------------------------------------------------------
    # Resolution helpers

    def _active_persona(self) -> Any:
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        sheet = self.caller.character_sheet
        if sheet is None:
            msg = "You have no character sheet."
            raise CommandError(msg)
        return active_persona_for_sheet(sheet)

    def _administrable_domains(self) -> list[Domain]:
        """Every domain the caller's active persona may run in play."""
        from world.societies.houses.models import Domain  # noqa: PLC0415
        from world.societies.houses.services import can_administer_domain  # noqa: PLC0415

        persona = self._active_persona()
        domains = Domain.objects.select_related("owner_org").all()
        return [d for d in domains if can_administer_domain(persona, d)]

    def _resolve_domain(self, name: str | None) -> Domain:
        """Resolve a domain the caller administers by name (or the sole one)."""
        domains = self._administrable_domains()
        if not domains:
            msg = "You don't run any domains."
            raise CommandError(msg)
        if name is None:
            if len(domains) == 1:
                return domains[0]
            names = ", ".join(d.name for d in domains)
            msg = f"Which domain? You run: {names}"
            raise CommandError(msg)
        for domain in domains:
            if domain.name.lower() == name.lower():
                return domain
        msg = f"You don't run a domain named '{name}'."
        raise CommandError(msg)

    def _send(self, result: Any) -> None:
        self.msg(result.message)

    # ------------------------------------------------------------------
    # Subverb handlers

    def _list(self) -> None:
        domains = self._administrable_domains()
        if not domains:
            self.msg("You don't run any domains.")
            return
        lines = ["Domains you run:"]
        lines.extend(
            f"  {d.name}  [prosperity {d.prosperity} / unrest {d.unrest} / pop {d.population}]"
            for d in domains
        )
        self.msg("\n".join(lines))

    def _offices(self, rest: list[str]) -> None:
        from world.societies.models import OrganizationOffice  # noqa: PLC0415

        domain = self._resolve_domain(" ".join(rest).strip() or None)
        offices = OrganizationOffice.objects.filter(organization=domain.owner_org).select_related(
            "holder"
        )
        if not offices:
            self.msg(f"{domain.owner_org} has no offices.")
            return
        lines = [f"Offices of {domain.owner_org}:"]
        for office in offices:
            holder = office.holder.name if office.holder else "vacant"
            lines.append(f"  {office.title or office.slug}: {holder}")
        self.msg("\n".join(lines))

    def _holding(self, rest: list[str]) -> None:
        from actions.definitions.domains import AddDomainHoldingAction  # noqa: PLC0415
        from world.societies.houses.models import HoldingKind  # noqa: PLC0415

        positional, kwargs = _parse_kwargs(rest)
        if not positional:
            msg = "Usage: domain holding <domain> <holding-kind> [name=<text>]"
            raise CommandError(msg)
        # Last positional token is the kind; the rest name the domain.
        kind_name = positional[-1]
        domain = self._resolve_domain(" ".join(positional[:-1]).strip() or None)
        kind = HoldingKind.objects.filter(name__iexact=kind_name).first()
        if kind is None:
            msg = f"No holding kind called '{kind_name}'."
            raise CommandError(msg)
        result = AddDomainHoldingAction().run(
            actor=self.caller,
            domain_id=domain.pk,
            holding_kind_id=kind.pk,
            name=kwargs.get("name", ""),
        )
        self._send(result)

    def _improve(self, rest: list[str]) -> None:
        from actions.definitions.domains import StartDomainImprovementAction  # noqa: PLC0415

        positional, kwargs = _parse_kwargs(rest)
        domain = self._resolve_domain(" ".join(positional).strip() or None)
        if "cost" not in kwargs or not kwargs["cost"].isdigit():  # noqa: STRING_LITERAL
            msg = (
                "Usage: domain improve <domain> cost=<n> [gross=<n>] "
                "[prosperity=<n>] [holding=<id>]"
            )
            raise CommandError(msg)
        result = StartDomainImprovementAction().run(
            actor=self.caller,
            domain_id=domain.pk,
            cost=int(kwargs["cost"]),
            gross_increase=int(kwargs.get("gross", "0") or "0"),
            prosperity_increase=int(kwargs.get("prosperity", "0") or "0"),
            holding_id=int(kwargs["holding"]) if kwargs.get("holding", "").isdigit() else None,
        )
        self._send(result)

    def _appoint(self, rest: list[str]) -> None:
        from actions.definitions.domains import AppointDomainOfficeAction  # noqa: PLC0415
        from world.traits.models import Trait  # noqa: PLC0415

        positional, kwargs = _parse_kwargs(rest)
        if len(positional) < _MIN_APPOINT_ARGS:
            msg = "Usage: domain appoint <domain> <char> [title=<text>] [check=<trait>]"
            raise CommandError(msg)
        char_name = positional[-1]
        domain = self._resolve_domain(" ".join(positional[:-1]).strip() or None)
        holder = self._resolve_holder_persona(char_name)
        check_id = None
        check_name = kwargs.get("check")
        if check_name:
            trait = Trait.objects.filter(name__iexact=check_name).first()
            if trait is None:
                msg = f"No trait called '{check_name}'."
                raise CommandError(msg)
            check_id = trait.pk
        result = AppointDomainOfficeAction().run(
            actor=self.caller,
            domain_id=domain.pk,
            holder_persona_id=holder.pk,
            title=kwargs.get("title", ""),
            feeds_check_id=check_id,
        )
        self._send(result)

    def _resolve_holder_persona(self, char_name: str) -> Any:
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        target = self.caller.search(char_name, global_search=True)
        if not target:
            msg = f"Could not find '{char_name}'."
            raise CommandError(msg)
        sheet = target.character_sheet
        if sheet is None:
            msg = f"'{char_name}' has no character sheet."
            raise CommandError(msg)
        return active_persona_for_sheet(sheet)

    def _vacate(self, rest: list[str]) -> None:
        from actions.definitions.domains import VacateDomainOfficeAction  # noqa: PLC0415

        domain = self._resolve_domain(" ".join(rest).strip() or None)
        result = VacateDomainOfficeAction().run(actor=self.caller, domain_id=domain.pk)
        self._send(result)

    def _transfer(self, rest: list[str]) -> None:
        from actions.definitions.domains import TransferFoodAction  # noqa: PLC0415

        positional, kwargs = _parse_kwargs(rest)
        if not positional or "amount" not in kwargs:  # noqa: STRING_LITERAL
            msg = "Usage: domain transfer <source-domain> <target-domain> amount=<n>"
            raise CommandError(msg)
        if not kwargs["amount"].isdigit():  # noqa: STRING_LITERAL
            msg = "Amount must be a positive number."
            raise CommandError(msg)
        # Last positional token is the target domain; the rest name the source.
        target_name = positional[-1]
        source_name = " ".join(positional[:-1]).strip() or None
        source = self._resolve_domain(source_name)
        # Target resolves among ALL domains, not just the caller's administrable ones.
        from world.societies.houses.models import Domain  # noqa: PLC0415

        target = Domain.objects.filter(name__iexact=target_name).first()
        if target is None:
            msg = f"No domain named '{target_name}'."
            raise CommandError(msg)
        result = TransferFoodAction().run(
            actor=self.caller,
            source_domain_id=source.pk,
            target_domain_id=target.pk,
            amount=int(kwargs["amount"]),
        )
        self._send(result)

"""Telnet pact/betrothal namespace command (#2999).

Thin parse-and-dispatch over ``world.societies.houses.pact_services`` — no
business logic here; authorization is re-checked in the services.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from commands.command import ArxCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from world.societies.models import Organization


class CmdPact(ArxCommand):
    """Diplomacy between organizations, and promised unions.

    Syntax:
        pact list
        pact propose <my-org> to <their-org> kind=<pact kind>
        pact ratify <id>
        pact dissolve <id>
        pact betroth a=<kinsperson> b=<kinsperson> senior=<org> junior=<org>
        pact breakvow <betrothal-id> house=<org>
        pact divorce <union-id>

    Proposing/ratifying/dissolving requires leadership rank in the acting
    org; the services re-check everything. A betrothal previews the
    alliance at a fraction; the WEDDING ceremony solemnizes it. Either
    spouse may divorce unilaterally — both take a prestige hit, the
    initiator's steeper (#2358).
    """

    key = "pact"
    locks = "cmd:all()"
    help_category = "Organizations"

    def func(self) -> None:
        try:
            self._dispatch()
        except CommandError as exc:
            self.msg(str(exc))

    def _dispatch(self) -> None:
        tokens = (self.args or "").strip().split()
        if not tokens or tokens[0].lower() == "list":  # noqa: STRING_LITERAL
            self._list()
            return
        first = tokens[0].lower()
        rest = tokens[1:]
        handlers = {
            "propose": self._propose,
            "ratify": self._ratify,
            "dissolve": self._dissolve,
            "betroth": self._betroth,
            "breakvow": self._breakvow,
            "divorce": self._divorce,
        }
        handler = handlers.get(first)
        if handler is None:
            msg = "Usage: pact [list|propose|ratify|dissolve|betroth|breakvow|divorce] ..."
            raise CommandError(msg)
        handler(rest)

    # ------------------------------------------------------------------

    def _active_persona(self) -> Any:
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        sheet = self.caller.character_sheet
        if sheet is None:
            msg = "You have no character sheet."
            raise CommandError(msg)
        return active_persona_for_sheet(sheet)

    def _resolve_org(self, name: str) -> Organization:
        from world.societies.models import Organization  # noqa: PLC0415

        org = Organization.objects.filter(name__iexact=name).first()
        if org is None:
            msg = f"No organization named '{name}'."
            raise CommandError(msg)
        return org

    def _resolve_kin(self, name: str) -> Any:
        from world.roster.models import Kinsperson  # noqa: PLC0415

        kin = Kinsperson.objects.filter(name__iexact=name).first()
        if kin is None:
            msg = f"No kinsperson named '{name}'."
            raise CommandError(msg)
        return kin

    def _parse_kwargs(self, tokens: list[str]) -> tuple[list[str], dict[str, str]]:
        from commands.domains import _parse_kwargs  # noqa: PLC0415

        return _parse_kwargs(tokens)

    def _service_call(self, fn: Any, /, *args: Any, **kwargs: Any) -> Any:
        from world.societies.houses.services import HousesServiceError  # noqa: PLC0415

        try:
            return fn(*args, **kwargs)
        except HousesServiceError as exc:
            raise CommandError(exc.user_message) from exc

    # ------------------------------------------------------------------

    def _list(self) -> None:
        from world.societies.houses.models import Betrothal, OrgPact  # noqa: PLC0415

        lines = []
        pacts = OrgPact.objects.filter(dissolved_at__isnull=True).select_related(
            "kind", "party_a", "party_b"
        )[:20]
        for pact in pacts:
            state = "standing" if pact.ratified_at else "awaiting ratification"
            lines.append(
                f"  #{pact.pk} {pact.kind.name}: {pact.party_a.name} & "
                f"{pact.party_b.name} ({state})"
            )
        vows = Betrothal.objects.filter(broken_at__isnull=True, wed_at__isnull=True).select_related(
            "kinsperson_a", "kinsperson_b"
        )[:20]
        lines.extend(
            f"  vow #{vow.pk}: {vow.kinsperson_a.display_name} to {vow.kinsperson_b.display_name}"
            for vow in vows
        )
        self.msg("Pacts and promises:\n" + "\n".join(lines) if lines else "No pacts stand.")

    def _propose(self, rest: list[str]) -> None:
        from world.societies.houses.models import PactKind  # noqa: PLC0415
        from world.societies.houses.pact_services import propose_org_pact  # noqa: PLC0415

        positional, kwargs = self._parse_kwargs(rest)
        if "to" not in [p.lower() for p in positional] or "kind" not in kwargs:  # noqa: STRING_LITERAL
            msg = "Usage: pact propose <my-org> to <their-org> kind=<pact kind>"
            raise CommandError(msg)
        split = [p.lower() for p in positional].index("to")  # noqa: STRING_LITERAL
        mine = self._resolve_org(" ".join(positional[:split]))
        theirs = self._resolve_org(" ".join(positional[split + 1 :]))
        kind = PactKind.objects.filter(name__iexact=kwargs["kind"]).first()  # noqa: STRING_LITERAL
        if kind is None:
            msg = f"No pact kind named '{kwargs['kind']}'."
            raise CommandError(msg)
        pact = self._service_call(
            propose_org_pact,
            kind=kind,
            proposer=self._active_persona(),
            party_a=mine,
            party_b=theirs,
        )
        self.msg(f"Proposed: #{pact.pk} {kind.name} to {theirs.name}. They must ratify.")

    def _ratify(self, rest: list[str]) -> None:
        from world.societies.houses.models import OrgPact  # noqa: PLC0415
        from world.societies.houses.pact_services import ratify_org_pact  # noqa: PLC0415

        pact = self._resolve_pact(rest, OrgPact)
        self._service_call(ratify_org_pact, pact, ratifier=self._active_persona())
        self.msg(f"Ratified: {pact}. The alliance is news.")

    def _dissolve(self, rest: list[str]) -> None:
        from world.societies.houses.constants import OrgPactDissolutionReason  # noqa: PLC0415
        from world.societies.houses.models import OrgPact  # noqa: PLC0415
        from world.societies.houses.pact_services import dissolve_org_pact  # noqa: PLC0415
        from world.societies.houses.services import is_org_leader  # noqa: PLC0415

        pact = self._resolve_pact(rest, OrgPact)
        persona = self._active_persona()
        if not (is_org_leader(persona, pact.party_a) or is_org_leader(persona, pact.party_b)):
            msg = "Only a party's leadership may dissolve a pact."
            raise CommandError(msg)
        self._service_call(dissolve_org_pact, pact, reason=OrgPactDissolutionReason.DISSOLVED)
        self.msg(f"Dissolved: {pact}.")

    def _resolve_pact(self, rest: list[str], model: Any) -> Any:
        if not rest or not rest[0].lstrip("#").isdigit():
            msg = "Name the pact by number (see 'pact list')."
            raise CommandError(msg)
        pact = model.objects.filter(pk=int(rest[0].lstrip("#"))).first()
        if pact is None:
            msg = "No such pact."
            raise CommandError(msg)
        return pact

    def _betroth(self, rest: list[str]) -> None:
        from world.societies.houses.pact_services import propose_betrothal  # noqa: PLC0415

        _positional, kwargs = self._parse_kwargs(rest)
        needed = ("a", "b", "senior", "junior")
        if any(key not in kwargs for key in needed):
            msg = "Usage: pact betroth a=<kinsperson> b=<kinsperson> senior=<org> junior=<org>"
            raise CommandError(msg)
        betrothal = self._service_call(
            propose_betrothal,
            proposer=self._active_persona(),
            kinsperson_a=self._resolve_kin(kwargs["a"]),  # noqa: STRING_LITERAL
            kinsperson_b=self._resolve_kin(kwargs["b"]),  # noqa: STRING_LITERAL
            senior_house=self._resolve_org(kwargs["senior"]),  # noqa: STRING_LITERAL
            junior_house=self._resolve_org(kwargs["junior"]),  # noqa: STRING_LITERAL
        )
        self.msg(f"Promised: vow #{betrothal.pk}. A wedding rite will solemnize it.")

    def _breakvow(self, rest: list[str]) -> None:
        from world.societies.houses.models import Betrothal  # noqa: PLC0415
        from world.societies.houses.pact_services import break_betrothal  # noqa: PLC0415
        from world.societies.houses.services import is_org_leader  # noqa: PLC0415

        positional, kwargs = self._parse_kwargs(rest)
        if not positional or "house" not in kwargs:  # noqa: STRING_LITERAL
            msg = "Usage: pact breakvow <betrothal-id> house=<your-org>"
            raise CommandError(msg)
        betrothal = self._resolve_pact(positional, Betrothal)
        house = self._resolve_org(kwargs["house"])  # noqa: STRING_LITERAL
        if not is_org_leader(self._active_persona(), house):
            msg = "Only your house's leadership may break its word."
            raise CommandError(msg)
        if house.pk not in (betrothal.senior_house_id, betrothal.junior_house_id):
            msg = "That house is no party to this vow."
            raise CommandError(msg)
        self._service_call(break_betrothal, betrothal, breaking_house=house)
        self.msg("The promise is broken. The realm will hear of it.")

    def _divorce(self, rest: list[str]) -> None:
        from actions.definitions.divorce import InitiateDivorceAction  # noqa: PLC0415

        if not rest or not rest[0].lstrip("#").isdigit():
            msg = "Usage: pact divorce <union-id>"
            raise CommandError(msg)
        result = InitiateDivorceAction().run(actor=self.caller, union_id=int(rest[0].lstrip("#")))
        if result.message:
            self.msg(result.message)

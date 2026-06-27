"""Telnet ``technique`` command — staff/GM technique authoring workbench (#1496).

Staff-locked (``cmd:perm(Builder)``) subcommand namespace that drives the
draft → set → payloads → price → author flow.  Each subcommand is a thin shell
over the Task-3 draft services (``world.magic.services.technique_draft``) and
the Task-2 ``AuthorTechniqueAction``.

Grammar::

    technique draft <name>
    technique show
    technique set <field>=<value> [<field>=<value> …]
    technique restrict add|remove <name or id>
    technique grant add capability=<n> base=<n> mult=<f>
    technique grant remove <row-id>
    technique damage add type=<n> base=<n> mult=<f>
    technique damage remove <row-id>
    technique condition add template=<n> severity=<n> [duration=<n>]
    technique condition remove <row-id>
    technique price
    technique author
    technique discard
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from commands.command import ArxCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import TechniqueDraft

_USAGE = (
    "technique draft <name>          — start/replace draft\n"
    "  technique show                  — show current draft + live price\n"
    "  technique set <field>=<v> ...   — set one or more draft fields\n"
    "    (fields: name, description, gift, style, effect_type,\n"
    "             action_category, tier, intensity, control, anima_cost)\n"
    "    (put name= / description= LAST — they consume the rest of the line)\n"
    "  technique restrict add|remove <name>\n"
    "  technique grant add capability=<n> base=<n> mult=<f>\n"
    "  technique grant remove <row-id>\n"
    "  technique damage add type=<n> base=<n> mult=<f>\n"
    "  technique damage remove <row-id>\n"
    "  technique condition add template=<n> severity=<n> [duration=<n>]\n"
    "  technique condition remove <row-id>\n"
    "  technique price                 — dry-run budget check\n"
    "  technique author                — author the technique (staff path)\n"
    "  technique discard               — discard current draft"
)

_SET_FIELDS = frozenset(
    {
        "name",
        "description",
        "gift",
        "style",
        "effect_type",
        "action_category",
        "tier",
        "intensity",
        "control",
        "anima_cost",
    }
)

# Subcommands that forward their rest-of-line argument to the handler.
_REST_SUBCMDS = frozenset({"draft", "set", "restrict", "grant", "damage", "condition"})
# Subcommands that take no argument.
_NO_ARG_SUBCMDS = frozenset({"show", "price", "author", "discard"})


class CmdTechnique(ArxCommand):
    """Staff/GM technique authoring workbench.

    Routes a leading subcommand (``draft``, ``show``, ``set``, ``restrict``,
    ``grant``, ``damage``, ``condition``, ``price``, ``author``, ``discard``) to
    the matching handler.  Each handler delegates to the draft services in
    ``world.magic.services.technique_draft`` or to ``AuthorTechniqueAction``
    for the ``author`` step.
    """

    key = "technique"
    locks = "cmd:perm(Builder)"
    help_category = "Staff"
    action = None  # multi-subcommand; no single backing Action

    def func(self) -> None:
        """Route subcommands; emit ``CommandError`` as a player message."""
        args = (self.args or "").strip()
        first = args.split()[0].lower() if args.strip() else ""
        rest = args[len(first) :].strip() if first else ""
        try:
            self._route(first, rest)
        except CommandError as err:
            self.caller.msg(str(err))

    def _route(self, first: str, rest: str) -> None:
        """Dispatch to the subcommand handler for *first*.

        Splits to two helpers to keep McCabe complexity below the project
        ceiling: ``_route_rest`` covers subcommands that forward *rest*;
        ``_route_no_arg`` covers the argument-free ones.
        """
        if first in _REST_SUBCMDS:
            self._route_rest(first, rest)
        elif first in _NO_ARG_SUBCMDS:
            self._route_no_arg(first)
        else:
            self.caller.msg(_USAGE)

    def _route_rest(self, first: str, rest: str) -> None:
        """Handle subcommands that forward a *rest* argument."""
        if first == "draft":  # noqa: STRING_LITERAL
            self._handle_draft(rest)
        elif first == "set":  # noqa: STRING_LITERAL
            self._handle_set(rest)
        elif first == "restrict":  # noqa: STRING_LITERAL
            self._handle_restrict(rest)
        elif first == "grant":  # noqa: STRING_LITERAL
            self._handle_grant(rest)
        elif first == "damage":  # noqa: STRING_LITERAL
            self._handle_damage(rest)
        elif first == "condition":  # noqa: STRING_LITERAL
            self._handle_condition(rest)

    def _route_no_arg(self, first: str) -> None:
        """Handle subcommands that take no argument."""
        if first == "show":  # noqa: STRING_LITERAL
            self._handle_show()
        elif first == "price":  # noqa: STRING_LITERAL
            self._handle_price()
        elif first == "author":  # noqa: STRING_LITERAL
            self._handle_author()
        elif first == "discard":  # noqa: STRING_LITERAL
            self._handle_discard()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_sheet(self) -> CharacterSheet:
        """Return the caller's CharacterSheet."""
        return self.caller.sheet_data

    def _get_draft(self) -> TechniqueDraft:
        """Return the caller's active TechniqueDraft or raise CommandError."""
        from world.magic.exceptions import NoActiveTechniqueDraft  # noqa: PLC0415
        from world.magic.services.technique_draft import get_active_draft  # noqa: PLC0415

        try:
            return get_active_draft(self._get_sheet())
        except NoActiveTechniqueDraft as exc:
            raise CommandError(exc.user_message) from exc

    @staticmethod
    def _parse_simple_kwargs(args: str) -> dict[str, str]:
        """Parse space-delimited ``key=value`` tokens into a string dict."""
        out: dict[str, str] = {}
        for token in args.split():
            if "=" in token:
                key, _, value = token.partition("=")
                out[key.lower()] = value
        return out

    @staticmethod
    def _int_required(value: str, label: str) -> int:
        """Parse *value* as int; raise ``CommandError`` on failure."""
        try:
            return int(value)
        except (ValueError, TypeError) as exc:
            msg = f"'{label}' must be an integer."
            raise CommandError(msg) from exc

    @staticmethod
    def _float_required(value: str, label: str) -> float:
        """Parse *value* as float; raise ``CommandError`` on failure."""
        try:
            return float(value)
        except (ValueError, TypeError) as exc:
            msg = f"'{label}' must be a number."
            raise CommandError(msg) from exc

    # ------------------------------------------------------------------
    # Subcommand handlers
    # ------------------------------------------------------------------

    def _handle_draft(self, rest: str) -> None:
        """Start or replace the caller's draft."""
        from world.magic.services.technique_draft import start_technique_draft  # noqa: PLC0415

        name = rest.strip()
        if not name:
            msg = "Usage: technique draft <name>"
            raise CommandError(msg)
        draft = start_technique_draft(self._get_sheet(), name=name)
        self.caller.msg(f"Draft started: '{draft.name}'. Use |wtechnique set|n to configure it.")

    def _handle_show(self) -> None:
        """Render the caller's current draft plus a live price line."""
        from world.magic.exceptions import TechniqueDraftIncomplete  # noqa: PLC0415
        from world.magic.services.technique_builder import (  # noqa: PLC0415
            StaffPolicy,
            enforce_policy,
        )
        from world.magic.services.technique_draft import draft_to_design  # noqa: PLC0415

        draft = self._get_draft()
        tier_text = str(draft.tier) if draft.tier is not None else "(unset)"
        lines = [
            f"|wTechnique Draft:|n {draft.name or '(unnamed)'}",
            f"  Description : {draft.description or '(none)'}",
            f"  Gift        : {draft.gift or '(unset)'}",
            f"  Style       : {draft.style or '(unset)'}",
            f"  Effect type : {draft.effect_type or '(unset)'}",
            f"  Category    : {draft.action_category or '(unset)'}",
            f"  Tier        : {tier_text}",
            f"  Intensity   : {draft.intensity}",
            f"  Control     : {draft.control}",
            f"  Anima cost  : {draft.anima_cost}",
        ]
        restrictions = list(draft.restrictions.all())
        if restrictions:
            lines.append(f"  Restrictions: {', '.join(str(r) for r in restrictions)}")
        for idx, g in enumerate(draft.capability_grants.all().select_related("capability"), 1):
            lines.append(
                f"  Grant [{idx}]: {g.capability}  base={g.base_value}"
                f"  mult={g.intensity_multiplier}"
            )
        for idx, p in enumerate(draft.damage_profiles.all().select_related("damage_type"), 1):
            lines.append(
                f"  Damage [{idx}]: {p.damage_type}  base={p.base_damage}"
                f"  mult={p.damage_intensity_multiplier}"
            )
        for idx, c in enumerate(draft.applied_conditions.all().select_related("condition"), 1):
            dur_text = f"  duration={c.base_duration_rounds}" if c.base_duration_rounds else ""
            lines.append(
                f"  Condition [{idx}]: {c.condition}  severity={c.base_severity}{dur_text}"
            )
        try:
            design = draft_to_design(draft)
            breakdown = enforce_policy(design, StaffPolicy(), self._get_sheet())
            budget_label = "|gwithin budget|n" if breakdown.within_budget else "|rover budget|n"
            lines.append(f"  |wPrice:|n {breakdown.total_cost}/{breakdown.budget} ({budget_label})")
        except TechniqueDraftIncomplete:
            lines.append("  |wPrice:|n (incomplete — set all required fields to preview)")
        self.caller.msg("\n".join(lines))

    def _handle_set(self, rest: str) -> None:
        """Set one or more draft fields via ``key=value`` tokens."""
        from world.magic.services.technique_draft import set_draft_fields  # noqa: PLC0415

        if not rest:
            msg = "Usage: technique set <field>=<value> [<field>=<value> …]"
            raise CommandError(msg)
        parsed = self._parse_set_kwargs(rest)
        fields = self._resolve_set_fields(parsed)
        draft = self._get_draft()
        set_draft_fields(draft, **fields)
        self.caller.msg(f"Draft updated: {', '.join(sorted(fields))}.")

    def _parse_set_kwargs(self, args: str) -> dict[str, str]:
        """Parse the ``set`` arg string.

        ``name`` and ``description`` consume the remainder of the line (so
        they may contain spaces).  All other fields are single whitespace-delimited
        tokens.
        """
        out: dict[str, str] = {}
        tokens = args.split()
        idx = 0
        while idx < len(tokens):
            token = tokens[idx]
            if "=" not in token:
                idx += 1
                continue
            key, _, value = token.partition("=")
            key = key.lower()
            if key in ("name", "description"):
                # Consume the rest of the line so values may contain spaces.
                out[key] = " ".join([value, *tokens[idx + 1 :]]).strip()
                break
            out[key] = value
            idx += 1
        return out

    def _resolve_set_fields(self, parsed: dict[str, str]) -> dict:
        """Translate string-keyed tokens into typed model field kwargs."""
        from world.magic.models import EffectType, Gift, TechniqueStyle  # noqa: PLC0415

        fields: dict = {}
        for key, value in parsed.items():
            if key not in _SET_FIELDS:
                msg = f"Unknown field '{key}'. Valid fields: {', '.join(sorted(_SET_FIELDS))}"
                raise CommandError(msg)
            if key in ("name", "description"):
                fields[key] = value
            elif key == "gift":  # noqa: STRING_LITERAL
                fields["gift"] = self.resolve_by_name_or_id(
                    Gift, value, not_found_msg=f"No gift found for '{value}'."
                )
            elif key == "style":  # noqa: STRING_LITERAL
                fields["style"] = self.resolve_by_name_or_id(
                    TechniqueStyle, value, not_found_msg=f"No style found for '{value}'."
                )
            elif key == "effect_type":  # noqa: STRING_LITERAL
                fields["effect_type"] = self.resolve_by_name_or_id(
                    EffectType, value, not_found_msg=f"No effect type found for '{value}'."
                )
            elif key == "action_category":  # noqa: STRING_LITERAL
                fields["action_category"] = self._resolve_action_category(value)
            elif key in ("tier", "intensity", "control", "anima_cost"):
                fields[key] = self._int_required(value, key)
        if not fields:
            msg = "No valid fields found. Usage: technique set <field>=<value> …"
            raise CommandError(msg)
        return fields

    def _resolve_action_category(self, value: str) -> str:
        """Validate and return a normalised ActionCategory string."""
        from actions.constants import ActionCategory  # noqa: PLC0415

        valid = {c.value for c in ActionCategory}
        if value.lower() not in valid:
            msg = f"Invalid action_category '{value}'. Valid: {', '.join(sorted(valid))}"
            raise CommandError(msg)
        return value.lower()

    def _handle_restrict(self, rest: str) -> None:
        """Add or remove a Restriction from the draft."""
        from world.magic.models import Restriction  # noqa: PLC0415
        from world.magic.services.technique_draft import (  # noqa: PLC0415
            add_draft_restriction,
            remove_draft_restriction,
        )

        tokens = rest.split(None, 1)
        action_part = tokens[0].lower() if tokens else ""
        name_part = tokens[1].strip() if len(tokens) > 1 else ""
        if not action_part or not name_part:
            msg = "Usage: technique restrict add|remove <name or id>"
            raise CommandError(msg)
        action, name = action_part, name_part
        if action not in ("add", "remove"):
            msg = "Usage: technique restrict add|remove <name or id>"
            raise CommandError(msg)
        draft = self._get_draft()
        restriction = self.resolve_by_name_or_id(
            Restriction, name, not_found_msg=f"No restriction found for '{name}'."
        )
        if action == "add":  # noqa: STRING_LITERAL
            add_draft_restriction(draft, restriction)
            self.caller.msg(f"Restriction '{restriction}' added.")
        else:
            remove_draft_restriction(draft, restriction)
            self.caller.msg(f"Restriction '{restriction}' removed.")

    def _handle_grant(self, rest: str) -> None:
        """Add or remove a capability grant from the draft."""
        from world.conditions.models import CapabilityType  # noqa: PLC0415
        from world.magic.services.technique_draft import (  # noqa: PLC0415
            add_draft_capability_grant,
            remove_draft_capability_grant,
        )

        tokens = rest.split(None, 1)
        if not tokens:
            msg = (
                "Usage: technique grant add capability=<n> base=<n> mult=<f>"
                " | technique grant remove <row-id>"
            )
            raise CommandError(msg)
        action = tokens[0].lower()
        args = tokens[1].strip() if len(tokens) > 1 else ""
        draft = self._get_draft()

        if action == "add":  # noqa: STRING_LITERAL
            kw = self._parse_simple_kwargs(args)
            if "capability" not in kw:  # noqa: STRING_LITERAL
                msg = "Missing 'capability=<name or id>'."
                raise CommandError(msg)
            capability = self.resolve_by_name_or_id(
                CapabilityType,
                kw["capability"],
                not_found_msg=f"No capability type found for '{kw['capability']}'.",
            )
            base = self._int_required(kw.get("base", "0"), "base")
            mult = self._float_required(kw.get("mult", "0"), "mult")
            row = add_draft_capability_grant(
                draft,
                capability=capability,
                base_value=base,
                intensity_multiplier=mult,
            )
            self.caller.msg(
                f"Capability grant added [#{row.pk}]: {capability}  base={base}  mult={mult}"
            )
        elif action == "remove":  # noqa: STRING_LITERAL
            row_id = self._int_required(args.strip(), "row-id")
            remove_draft_capability_grant(row_id)
            self.caller.msg(f"Capability grant #{row_id} removed.")
        else:
            msg = "Usage: technique grant add|remove …"
            raise CommandError(msg)

    def _handle_damage(self, rest: str) -> None:
        """Add or remove a damage profile from the draft."""
        from world.conditions.models import DamageType  # noqa: PLC0415
        from world.magic.services.technique_draft import (  # noqa: PLC0415
            add_draft_damage_profile,
            remove_draft_damage_profile,
        )

        tokens = rest.split(None, 1)
        if not tokens:
            msg = (
                "Usage: technique damage add type=<n> base=<n> mult=<f>"
                " | technique damage remove <row-id>"
            )
            raise CommandError(msg)
        action = tokens[0].lower()
        args = tokens[1].strip() if len(tokens) > 1 else ""
        draft = self._get_draft()

        if action == "add":  # noqa: STRING_LITERAL
            kw = self._parse_simple_kwargs(args)
            if "type" not in kw:  # noqa: STRING_LITERAL
                msg = "Missing 'type=<name or id>'."
                raise CommandError(msg)
            damage_type = self.resolve_by_name_or_id(
                DamageType,
                kw["type"],
                not_found_msg=f"No damage type found for '{kw['type']}'.",
            )
            base = self._int_required(kw.get("base", "0"), "base")
            mult = self._float_required(kw.get("mult", "0"), "mult")
            row = add_draft_damage_profile(
                draft,
                damage_type=damage_type,
                base_damage=base,
                damage_intensity_multiplier=mult,
            )
            self.caller.msg(
                f"Damage profile added [#{row.pk}]: {damage_type}  base={base}  mult={mult}"
            )
        elif action == "remove":  # noqa: STRING_LITERAL
            row_id = self._int_required(args.strip(), "row-id")
            remove_draft_damage_profile(row_id)
            self.caller.msg(f"Damage profile #{row_id} removed.")
        else:
            msg = "Usage: technique damage add|remove …"
            raise CommandError(msg)

    def _handle_condition(self, rest: str) -> None:
        """Add or remove an applied condition from the draft."""
        from world.conditions.models import ConditionTemplate  # noqa: PLC0415
        from world.magic.services.technique_draft import (  # noqa: PLC0415
            add_draft_applied_condition,
            remove_draft_applied_condition,
        )

        tokens = rest.split(None, 1)
        if not tokens:
            msg = (
                "Usage: technique condition add template=<n> severity=<n> [duration=<n>]"
                " | technique condition remove <row-id>"
            )
            raise CommandError(msg)
        action = tokens[0].lower()
        args = tokens[1].strip() if len(tokens) > 1 else ""
        draft = self._get_draft()

        if action == "add":  # noqa: STRING_LITERAL
            kw = self._parse_simple_kwargs(args)
            if "template" not in kw:  # noqa: STRING_LITERAL
                msg = "Missing 'template=<name or id>'."
                raise CommandError(msg)
            condition = self.resolve_by_name_or_id(
                ConditionTemplate,
                kw["template"],
                not_found_msg=f"No condition template found for '{kw['template']}'.",
            )
            severity = self._int_required(kw.get("severity", "1"), "severity")
            duration: int | None = None
            if "duration" in kw:  # noqa: STRING_LITERAL
                duration = self._int_required(kw["duration"], "duration")
            row = add_draft_applied_condition(
                draft,
                condition=condition,
                base_severity=severity,
                base_duration_rounds=duration,
            )
            self.caller.msg(
                f"Applied condition added [#{row.pk}]: {condition}  severity={severity}"
            )
        elif action == "remove":  # noqa: STRING_LITERAL
            row_id = self._int_required(args.strip(), "row-id")
            remove_draft_applied_condition(row_id)
            self.caller.msg(f"Applied condition #{row_id} removed.")
        else:
            msg = "Usage: technique condition add|remove …"
            raise CommandError(msg)

    def _handle_price(self) -> None:
        """Show a live budget breakdown for the current draft."""
        from world.magic.exceptions import TechniqueDraftIncomplete  # noqa: PLC0415
        from world.magic.services.technique_builder import (  # noqa: PLC0415
            StaffPolicy,
            enforce_policy,
        )
        from world.magic.services.technique_draft import draft_to_design  # noqa: PLC0415

        draft = self._get_draft()
        try:
            design = draft_to_design(draft)
        except TechniqueDraftIncomplete as exc:
            raise CommandError(exc.user_message) from exc

        breakdown = enforce_policy(design, StaffPolicy(), self._get_sheet())
        lines = [f"|wPrice breakdown for '{design.name}' (Tier {design.tier}):|n"]
        lines.extend(f"  {line.label}: {line.power_cost}" for line in breakdown.lines)
        lines.append(f"  Gross: {breakdown.gross_cost}")
        if breakdown.refund:
            lines.append(f"  Restriction refund: -{breakdown.refund}")
        budget_label = "|gwithin budget|n" if breakdown.within_budget else "|rover budget|n"
        lines.append(f"  |wTotal: {breakdown.total_cost}/{breakdown.budget}|n ({budget_label})")
        self.caller.msg("\n".join(lines))

    def _handle_author(self) -> None:
        """Author the technique via the staff path; discard draft on success."""
        from actions.definitions.technique_authoring import AuthorTechniqueAction  # noqa: PLC0415
        from world.magic.exceptions import TechniqueDraftIncomplete  # noqa: PLC0415
        from world.magic.services.technique_draft import (  # noqa: PLC0415
            discard_draft,
            draft_to_design,
        )

        draft = self._get_draft()
        try:
            design = draft_to_design(draft)
        except TechniqueDraftIncomplete as exc:
            raise CommandError(exc.user_message) from exc

        result = AuthorTechniqueAction().run(actor=self.caller, design=design, as_staff=True)
        if result.message:
            self.caller.msg(result.message)
        if result.success:
            discard_draft(self._get_sheet())

    def _handle_discard(self) -> None:
        """Delete the caller's current draft."""
        from world.magic.services.technique_draft import discard_draft  # noqa: PLC0415

        discard_draft(self._get_sheet())
        self.caller.msg("Draft discarded.")

"""Telnet commands for the Soul Tether bond lifecycle (#1343).

Direct-service seam: CmdTether and CmdSineater call the same service functions as the
web APIViews. All validation lives in the service layer; these commands only parse telnet
text and surface user_message errors.

Sineating itself is a pose (``pose/entreat``, ``pose/sineat``, #5177), handled by the pose
command and the Sineating actions, not here.

Convergence:
  Telnet  CmdTether/CmdSineater  →  world.magic.services.soul_tether.*
  Web     SoulTetherAcceptView / etc.  →  same services
"""

from __future__ import annotations

from typing import Any

from actions.definitions.sineating import DeclineSineatingAction
from commands.command import ArxCommand
from commands.exceptions import CommandError
from world.magic.constants import SoulTetherRole as _SoulTetherRoleDB, TargetKind
from world.magic.exceptions import SoulTetherError
from world.magic.models import Thread
from world.magic.models.affinity import Resonance
from world.magic.models.soul_tether import (
    MireHolding,
    PendingStageAdvanceOffer,
    SineatingPendingOffer,
)
from world.magic.services.soul_tether import (
    accept_soul_tether,
    dissolve_soul_tether,
    perform_soul_tether_rescue,
    resolve_stage_advance_prompt_from_db,
)
from world.magic.types.soul_tether import SoulTetherRole as _SoulTetherRoleEnum
from world.relationships.models import CharacterRelationship
from world.scenes.interaction_services import get_active_scene

_RESONANCE_KWARG = "resonance"
_SINEATER_RESONANCE_KWARG = "sineater_resonance"
_SINS_KWARG = "sins"


# ---------------------------------------------------------------------------
# Module-level helpers shared by both command classes
# ---------------------------------------------------------------------------


def _split_first(args: str) -> tuple[str, str]:
    """Split the first whitespace-delimited token from the rest of *args*."""
    parts = args.split(None, 1)
    return (parts[0] if parts else ""), (parts[1] if len(parts) > 1 else "")


def _parse_kwargs(args: str) -> dict[str, str]:
    """Parse ``key=value`` tokens left to right."""
    out: dict[str, str] = {}
    for token in args.split():
        if "=" not in token:
            continue
        key, _, value = token.partition("=")
        out[key] = value
    return out


def _get_sheet(character: Any) -> Any:
    """Return the CharacterSheet for *character* or raise ``CommandError``."""
    sheet = character.character_sheet
    if sheet is None:
        msg = f"{character} has no character sheet."
        raise CommandError(msg)
    return sheet


def _resolve_tether_resonance(sinner_sheet: Any, sineater_sheet: Any) -> Any:
    """Return the Resonance from the active Soul Tether between a Sinner/Sineater pair.

    Walks Sinner-side CharacterRelationship → ritual RelationshipCapstone →
    non-retired RELATIONSHIP_CAPSTONE Thread → Thread.resonance.
    Raises ``CommandError`` when any step is missing.
    """
    rel = CharacterRelationship.objects.filter(
        source=sinner_sheet,
        target=sineater_sheet,
        is_soul_tether=True,
        soul_tether_role=_SoulTetherRoleDB.SINNER,
    ).first()
    if rel is None:
        msg = "No active Soul Tether exists between you and that character."
        raise CommandError(msg)

    capstone = rel.capstones.filter(is_ritual_capstone=True).first()
    if capstone is None:
        msg = "Soul Tether bond is not fully formed."
        raise CommandError(msg)

    thread = Thread.objects.filter(
        owner=sinner_sheet,
        target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
        target_capstone=capstone,
        retired_at__isnull=True,
    ).first()
    if thread is None:
        msg = "Soul Tether bond is missing its resonance thread."
        raise CommandError(msg)

    return thread.resonance


# ---------------------------------------------------------------------------
# CmdTether — Sinner-side and formation commands
# ---------------------------------------------------------------------------


class CmdTether(ArxCommand):
    """Soul Tether bond commands.

    Usage:
        tether burden <partner> resonance=<name>
        tether bear <partner> resonance=<name>
        tether dissolve [<partner>]

    ``burden`` - you are the Sinner; your partner becomes the Sineater.
    ``bear``    - you are the Sineater; your partner is the Sinner.
    ``dissolve``- sever the bond (specify partner if you have more than one).

    To ask your Sineater to take on your sins, pose it: ``pose/entreat <sineater>=<units>
    <text>``.
    """

    key = "tether"
    locks = "cmd:all()"
    action = None

    def func(self) -> None:
        tokens = (self.args or "").split(None, 1)
        if not tokens:
            self.msg("Usage: tether burden|bear|dissolve ...")
            return
        subcommand = tokens[0].lower()
        rest = tokens[1] if len(tokens) > 1 else ""

        dispatch = {
            "burden": self._do_burden,
            "bear": self._do_bear,
            "dissolve": self._do_dissolve,
        }
        handler = dispatch.get(subcommand)
        if handler is None:
            self.msg(f"Unknown tether subcommand '{subcommand}'. Use: burden, bear, dissolve.")
            return
        try:
            handler(rest)
        except CommandError as err:
            self.msg(str(err))

    # ------------------------------------------------------------------
    # Subcommand handlers
    # ------------------------------------------------------------------

    def _do_burden(self, args: str) -> None:
        """Form the tether as the Sinner."""
        self._form_tether(
            args,
            verb="burden",
            usage="  tether burden <partner> resonance=<name> [sineater_resonance=<name>]",
            sinner_role=_SoulTetherRoleEnum.SINNER,
            success_fmt="The burden is bound. A Soul Tether forms between you and {partner}.",
        )

    def _do_bear(self, args: str) -> None:
        """Form the tether as the Sineater."""
        self._form_tether(
            args,
            verb="bear",
            usage="  tether bear <partner> resonance=<name> [sineater_resonance=<name>]",
            sinner_role=_SoulTetherRoleEnum.SINEATER,
            success_fmt="You bear the burden. A Soul Tether forms between you and {partner}.",
        )

    def _form_tether(
        self,
        args: str,
        *,
        verb: str,
        usage: str,
        sinner_role: _SoulTetherRoleEnum,
        success_fmt: str,
    ) -> None:
        """Shared core for ``burden`` and ``bear`` — only role and messages differ."""
        if not args.strip():
            msg = f"{verb.capitalize()} a partner to form a Soul Tether.\n{usage}"
            raise CommandError(msg)
        partner_name, rest = _split_first(args)
        kwargs = _parse_kwargs(rest)

        partner_char = self.search_or_raise(partner_name)
        partner_sheet = _get_sheet(partner_char)
        caller_sheet = _get_sheet(self.caller)

        resonance_name = kwargs.get(_RESONANCE_KWARG, "").strip()
        if not resonance_name:
            msg = "Specify a resonance: resonance=<name>."
            raise CommandError(msg)

        resonance = Resonance.objects.filter(name__iexact=resonance_name).first()
        if resonance is None:
            msg = f"No resonance named '{resonance_name}'."
            raise CommandError(msg)

        sineater_resonance = None
        sineater_resonance_name = kwargs.get(_SINEATER_RESONANCE_KWARG, "").strip()
        if sineater_resonance_name:
            sineater_resonance = Resonance.objects.filter(
                name__iexact=sineater_resonance_name
            ).first()
            if sineater_resonance is None:
                msg = f"No resonance named '{sineater_resonance_name}'."
                raise CommandError(msg)

        try:
            accept_soul_tether(
                initiator_sheet=caller_sheet,
                partner_sheet=partner_sheet,
                sinner_role=sinner_role,
                resonance=resonance,
                ritual_components=[],
                sineater_resonance=sineater_resonance,
            )
        except SoulTetherError as exc:
            raise CommandError(exc.user_message) from exc

        self.msg(success_fmt.format(partner=partner_char))

    def _do_dissolve(self, args: str) -> None:
        """Sever the Soul Tether bond."""
        caller_sheet = _get_sheet(self.caller)

        if args.strip():
            partner_char = self.search_or_raise(args.strip())
            partner_sheet = _get_sheet(partner_char)
            rel = (
                CharacterRelationship.objects.filter(
                    source=caller_sheet,
                    target=partner_sheet,
                    is_soul_tether=True,
                ).first()
                or CharacterRelationship.objects.filter(
                    source=partner_sheet,
                    target=caller_sheet,
                    is_soul_tether=True,
                ).first()
            )
            if rel is None:
                msg = f"No active Soul Tether with {partner_char}."
                raise CommandError(msg)
        else:
            rels = list(
                CharacterRelationship.objects.filter(source=caller_sheet, is_soul_tether=True)
            ) or list(
                CharacterRelationship.objects.filter(target=caller_sheet, is_soul_tether=True)
            )
            if not rels:
                msg = "You have no active Soul Tether to dissolve."
                raise CommandError(msg)
            if len(rels) > 1:
                msg = (
                    "You have multiple Soul Tethers. Specify a partner: tether dissolve <partner>."
                )
                raise CommandError(msg)
            rel = rels[0]

        try:
            dissolve_soul_tether(rel.pk, caller_sheet)
        except SoulTetherError as exc:
            raise CommandError(exc.user_message) from exc

        self.msg("The tether dissolves. The bond is severed.")


# ---------------------------------------------------------------------------
# CmdSineater — Sineater-side response commands
# ---------------------------------------------------------------------------


class CmdSineater(ArxCommand):
    """Soul Tether Sineater commands.

    Usage:
        sineater pleas
        sineater decline <sinner>
        sineater brace <sinner> [sins=<n>]
        sineater rescue <sinner>

    ``pleas``   - list the pleas awaiting your answer, and what you carry for each Sinner.
    ``decline`` - turn a Sinner's plea down.
    ``brace``   - pledge against a Sinner's stage-advance darkening (sins=0 to decline).
    ``rescue``  - perform the stage-3+ corruption rescue ritual.

    To answer a plea, pose it: ``pose/sineat <sinner>=<units> <text>``.
    """

    key = "sineater"
    locks = "cmd:all()"
    action = None

    def func(self) -> None:
        tokens = (self.args or "").split(None, 1)
        if not tokens:
            self.msg("Usage: sineater pleas|decline|brace|rescue ...")
            return
        subcommand = tokens[0].lower()
        rest = tokens[1] if len(tokens) > 1 else ""

        dispatch = {
            "decline": self._do_decline,
            "brace": self._do_brace,
            "rescue": self._do_rescue,
            "pleas": self._do_pleas,
        }
        handler = dispatch.get(subcommand)
        if handler is None:
            self.msg(
                f"Unknown sineater subcommand '{subcommand}'. Use: pleas, decline, brace, rescue."
            )
            return
        try:
            handler(rest)
        except CommandError as err:
            self.msg(str(err))

    # ------------------------------------------------------------------
    # Subcommand handlers
    # ------------------------------------------------------------------

    def _do_decline(self, args: str) -> None:
        """Turn down a pending sineat plea."""
        if not args.strip():
            msg = "Decline whose plea?\n  sineater decline <sinner>"
            raise CommandError(msg)
        sinner_char = self.search_or_raise(args.strip())
        result = DeclineSineatingAction().run(
            self.caller, partner_sheet_id=_get_sheet(sinner_char).pk
        )
        if not result.success:
            raise CommandError(result.message)
        self.msg(result.message)

    def _do_brace(self, args: str) -> None:
        """Respond to a stage-advance bonus offer."""
        if not args.strip():
            msg = (
                "Pledge against whose darkening?\n"
                "  sineater brace <sinner> [sins=<n>]  (sins=0 to decline)"
            )
            raise CommandError(msg)
        sinner_name, rest = _split_first(args)
        kwargs = _parse_kwargs(rest)

        sinner_char = self.search_or_raise(sinner_name)
        sinner_sheet = _get_sheet(sinner_char)
        caller_sheet = _get_sheet(self.caller)

        sins_str = kwargs.get(_SINS_KWARG, "").strip()
        if sins_str:
            if not sins_str.isdigit():
                msg = "sins= must be a number (sins=0 to decline)."
                raise CommandError(msg)
            units_committed = int(sins_str)
        else:
            pending = PendingStageAdvanceOffer.objects.filter(
                sinner_sheet=sinner_sheet,
                sineater_sheet=caller_sheet,
            ).first()
            if pending is None:
                msg = f"No pending stage-advance offer from {sinner_char}."
                raise CommandError(msg)
            units_committed = pending.commit_units_max

        try:
            result = resolve_stage_advance_prompt_from_db(
                sinner_sheet=sinner_sheet,
                sineater_sheet=caller_sheet,
                units_committed=units_committed,
            )
        except SoulTetherError as exc:
            raise CommandError(exc.user_message) from exc

        if result.declined:
            self.msg(f"You decline the stage-advance pledge for {sinner_char}.")
        else:
            self.msg(
                f"You pledge against {sinner_char}'s darkening. "
                f"{result.hollow_drained} sins consumed, "
                f"{result.strain_severity_added} strain borne."
            )

    def _do_rescue(self, args: str) -> None:
        """Perform the stage-3+ corruption rescue ritual."""
        if not args.strip():
            msg = "Rescue whom?\n  sineater rescue <sinner>"
            raise CommandError(msg)
        sinner_char = self.search_or_raise(args.strip())
        sinner_sheet = _get_sheet(sinner_char)
        caller_sheet = _get_sheet(self.caller)

        scene = get_active_scene(self.caller.location)
        if scene is None:
            msg = "You are not in an active scene."
            raise CommandError(msg)

        resonance = _resolve_tether_resonance(sinner_sheet, caller_sheet)

        try:
            result = perform_soul_tether_rescue(
                sineater_sheet=caller_sheet,
                sinner_sheet=sinner_sheet,
                resonance=resonance,
                components=[],
                scene=scene,
            )
        except SoulTetherError as exc:
            raise CommandError(exc.user_message) from exc

        self.msg(
            f"You pull {sinner_char} back from the edge. "
            f"Corruption severity reduced by {result.severity_reduced}. "
            f"The strain on the tether takes {result.sineater_strain_taken} of your resolve."
        )

    def _do_pleas(self, args: str) -> None:
        """List the pleas awaiting your answer and what you carry for each Sinner."""
        _ = args  # unused; subcommand takes no arguments
        caller_sheet = _get_sheet(self.caller)
        offers = SineatingPendingOffer.objects.filter(
            sineater_sheet=caller_sheet,
        ).select_related("sinner_sheet__character", "resonance")
        holdings = MireHolding.objects.filter(
            relationship__source=caller_sheet, amount__gt=0
        ).select_related("relationship__target__character", "resonance")

        lines = []
        if offers:
            lines.append("Pending pleas (answer with pose/sineat <name>=<units> <text>):")
            lines.extend(
                f"  {offer.sinner_sheet.character.key} - {offer.units_offered} sins in "
                f"{offer.resonance.name}."
                for offer in offers
            )
        if holdings:
            lines.append("You carry:")
            lines.extend(
                f"  {holding.amount} of {holding.relationship.target.character.key}'s "
                f"corruption in {holding.resonance.name}."
                for holding in holdings
            )
        self.msg("\n".join(lines) if lines else "No pleas await you, and you carry nothing.")

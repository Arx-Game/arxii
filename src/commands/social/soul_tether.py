"""Telnet commands for the Soul Tether bond lifecycle (#1343).

Direct-service seam: CmdTether and CmdSineater call the same six service
functions as the 8 web APIViews. All validation lives in the service layer;
these commands only parse telnet text and surface user_message errors.

Convergence:
  Telnet  CmdTether/CmdSineater  →  world.magic.services.soul_tether.*
  Web     SoulTetherAcceptView / SineatingRequestView / etc.  →  same services
"""

from __future__ import annotations

from typing import Any

from commands.command import ArxCommand
from commands.exceptions import CommandError
from world.magic.constants import SoulTetherRole as _SoulTetherRoleDB, TargetKind
from world.magic.exceptions import SoulTetherError
from world.magic.models import Thread
from world.magic.models.affinity import Resonance
from world.magic.models.soul_tether import PendingStageAdvanceOffer, SineatingPendingOffer
from world.magic.services.soul_tether import (
    accept_soul_tether,
    dissolve_soul_tether,
    perform_soul_tether_rescue,
    request_sineating,
    resolve_sineating_from_db,
    resolve_stage_advance_prompt_from_db,
)
from world.magic.types.soul_tether import SoulTetherRole as _SoulTetherRoleEnum
from world.relationships.models import CharacterRelationship
from world.scenes.interaction_services import get_active_scene

_RESONANCE_KWARG = "resonance"
_SINS_KWARG = "sins"
_WRITEUP_KWARG = "writeup"


# ---------------------------------------------------------------------------
# Module-level helpers shared by both command classes
# ---------------------------------------------------------------------------


def _split_first(args: str) -> tuple[str, str]:
    """Split the first whitespace-delimited token from the rest of *args*."""
    parts = args.split(None, 1)
    return (parts[0] if parts else ""), (parts[1] if len(parts) > 1 else "")


def _parse_kwargs(args: str) -> dict[str, str]:
    """Parse ``key=value`` tokens left to right.

    ``writeup=`` greedily consumes the remainder of the line (including spaces)
    so narrative descriptions may contain spaces.
    """
    out: dict[str, str] = {}
    tokens = args.split()
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if "=" not in token:
            index += 1
            continue
        key, _, value = token.partition("=")
        if key == _WRITEUP_KWARG:
            out[_WRITEUP_KWARG] = " ".join([value, *tokens[index + 1 :]]).strip()
            break
        out[key] = value
        index += 1
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
        tether burden <partner> resonance=<name> writeup=<narrative>
        tether bear <partner> resonance=<name> writeup=<narrative>
        tether dissolve [<partner>]
        tether entreat <sineater> sins=<n>

    ``burden`` — you are the Sinner; your partner becomes the Sineater.
    ``bear``    — you are the Sineater; your partner is the Sinner.
    ``dissolve``— sever the bond (specify partner if you have more than one).
    ``entreat`` — request your Sineater consume sins from your Hollow.
    """

    key = "tether"
    locks = "cmd:all()"
    action = None

    def func(self) -> None:
        tokens = (self.args or "").split(None, 1)
        if not tokens:
            self.msg("Usage: tether burden|bear|dissolve|entreat ...")
            return
        subcommand = tokens[0].lower()
        rest = tokens[1] if len(tokens) > 1 else ""

        dispatch = {
            "burden": self._do_burden,
            "bear": self._do_bear,
            "dissolve": self._do_dissolve,
            "entreat": self._do_entreat,
        }
        handler = dispatch.get(subcommand)
        if handler is None:
            self.msg(
                f"Unknown tether subcommand '{subcommand}'. Use: burden, bear, dissolve, entreat."
            )
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
            usage="  tether burden <partner> resonance=<name> writeup=<narrative>",
            sinner_role=_SoulTetherRoleEnum.SINNER,
            success_fmt="The burden is bound. A Soul Tether forms between you and {partner}.",
        )

    def _do_bear(self, args: str) -> None:
        """Form the tether as the Sineater."""
        self._form_tether(
            args,
            verb="bear",
            usage="  tether bear <partner> resonance=<name> writeup=<narrative>",
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

        writeup = kwargs.get(_WRITEUP_KWARG, "").strip()
        if not writeup:
            msg = "Describe the bond: writeup=<narrative>."
            raise CommandError(msg)

        resonance = Resonance.objects.filter(name__iexact=resonance_name).first()
        if resonance is None:
            msg = f"No resonance named '{resonance_name}'."
            raise CommandError(msg)

        try:
            accept_soul_tether(
                initiator_sheet=caller_sheet,
                partner_sheet=partner_sheet,
                sinner_role=sinner_role,
                resonance=resonance,
                writeup=writeup,
                ritual_components=[],
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

    def _do_entreat(self, args: str) -> None:
        """Request your Sineater consume sins from your Hollow."""
        if not args.strip():
            msg = (
                "Entreat your Sineater to consume your sins.\n  tether entreat <sineater> sins=<n>"
            )
            raise CommandError(msg)
        sineater_name, rest = _split_first(args)
        kwargs = _parse_kwargs(rest)

        sins_str = kwargs.get(_SINS_KWARG, "").strip()
        if not sins_str or not sins_str.isdigit():
            msg = "Specify how many sins to offer: sins=<n>."
            raise CommandError(msg)
        max_units = int(sins_str)

        sineater_char = self.search_or_raise(sineater_name)
        sineater_sheet = _get_sheet(sineater_char)
        caller_sheet = _get_sheet(self.caller)

        scene = get_active_scene(
            getattr(self.caller, "location", None)  # noqa: GETATTR_LITERAL
        )
        if scene is None:
            msg = "You are not in an active scene."
            raise CommandError(msg)

        resonance = _resolve_tether_resonance(caller_sheet, sineater_sheet)

        try:
            offer = request_sineating(
                sinner_sheet=caller_sheet,
                sineater_sheet=sineater_sheet,
                resonance=resonance,
                max_units=max_units,
                scene=scene,
            )
        except SoulTetherError as exc:
            raise CommandError(exc.user_message) from exc

        self.msg(
            f"You entreat {sineater_char} to consume your sins. "
            f"{offer.max_units_offered} sins await their answer."
        )


# ---------------------------------------------------------------------------
# CmdSineater — Sineater-side response commands
# ---------------------------------------------------------------------------


class CmdSineater(ArxCommand):
    """Soul Tether Sineater commands.

    Usage:
        sineater consume <sinner> [sins=<n>]
        sineater mire <sinner> [sins=<n>]
        sineater rescue <sinner>
        sineater pleas

    ``consume`` — accept/decline a pending sineat plea (sins=0 to decline).
    ``mire``    — pledge against a Sinner's stage-advance darkening (sins=0 to decline).
    ``rescue``  — perform the stage-3+ corruption rescue ritual.
    ``pleas``   — list pending sineat pleas awaiting your response.
    """

    key = "sineater"
    locks = "cmd:all()"
    action = None

    def func(self) -> None:
        tokens = (self.args or "").split(None, 1)
        if not tokens:
            self.msg("Usage: sineater consume|mire|rescue|pleas ...")
            return
        subcommand = tokens[0].lower()
        rest = tokens[1] if len(tokens) > 1 else ""

        dispatch = {
            "consume": self._do_consume,
            "mire": self._do_mire,
            "rescue": self._do_rescue,
            "pleas": self._do_pleas,
        }
        handler = dispatch.get(subcommand)
        if handler is None:
            self.msg(
                f"Unknown sineater subcommand '{subcommand}'. Use: consume, mire, rescue, pleas."
            )
            return
        try:
            handler(rest)
        except CommandError as err:
            self.msg(str(err))

    # ------------------------------------------------------------------
    # Subcommand handlers
    # ------------------------------------------------------------------

    def _do_consume(self, args: str) -> None:
        """Accept or decline a pending sineat plea."""
        if not args.strip():
            msg = "Consume whose sins?\n  sineater consume <sinner> [sins=<n>]  (sins=0 to decline)"
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
            units_accepted = int(sins_str)
        else:
            pending = SineatingPendingOffer.objects.filter(
                sinner_sheet=sinner_sheet,
                sineater_sheet=caller_sheet,
            ).first()
            if pending is None:
                msg = f"No pending plea from {sinner_char}."
                raise CommandError(msg)
            units_accepted = pending.units_offered

        try:
            result = resolve_sineating_from_db(
                sinner_sheet=sinner_sheet,
                sineater_sheet=caller_sheet,
                units_accepted=units_accepted,
            )
        except SoulTetherError as exc:
            raise CommandError(exc.user_message) from exc

        if result.declined:
            self.msg(f"You decline {sinner_char}'s plea.")
        else:
            self.msg(f"You consume {result.units_accepted} sins from {sinner_char}.")

    def _do_mire(self, args: str) -> None:
        """Respond to a stage-advance bonus offer."""
        if not args.strip():
            msg = (
                "Pledge against whose darkening?\n"
                "  sineater mire <sinner> [sins=<n>]  (sins=0 to decline)"
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
            msg = "Rescue whom from the Mire?\n  sineater rescue <sinner>"
            raise CommandError(msg)
        sinner_char = self.search_or_raise(args.strip())
        sinner_sheet = _get_sheet(sinner_char)
        caller_sheet = _get_sheet(self.caller)

        scene = get_active_scene(
            getattr(self.caller, "location", None)  # noqa: GETATTR_LITERAL
        )
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
            f"The Mire claims {result.sineater_strain_taken} of your resolve."
        )

    def _do_pleas(self, args: str) -> None:
        """List pending sineat pleas awaiting your response."""
        _ = args  # unused; subcommand takes no arguments
        caller_sheet = _get_sheet(self.caller)
        offers = SineatingPendingOffer.objects.filter(
            sineater_sheet=caller_sheet,
        ).select_related("sinner_sheet__character", "resonance")

        if not offers.exists():
            self.msg("No pending pleas await you.")
            return

        lines = ["Pending pleas:"]
        lines.extend(
            f"  {offer.sinner_sheet} — {offer.units_offered} sins in {offer.resonance.name}."
            for offer in offers
        )
        self.msg("\n".join(lines))

"""Telnet commands for the scene-entrance + entry-flourish loop (#1339)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from actions.definitions.social import EntranceAction, ResolveFlourishOfferAction
from commands.command import ArxCommand
from commands.exceptions import CommandError
from world.magic.entry_flourish import PendingEntryFlourishOffer

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.magic.models import Resonance


def _resolve_resonance(arg: str, sheet: CharacterSheet) -> Resonance:
    """Resolve a resonance by numeric ID or name from the character's claimed set.

    - If `arg` is numeric: try exact PK match first.
    - Otherwise (or if PK miss): case-insensitive name match.
    - On miss: list the character's claimed resonance names and raise CommandError.
    """
    from world.magic.models import CharacterResonance, Resonance  # noqa: PLC0415

    resonance: Resonance | None = None
    if arg.isdigit():
        resonance = Resonance.objects.filter(pk=int(arg)).first()
    if resonance is None:
        resonance = Resonance.objects.filter(name__iexact=arg).first()
    if resonance is not None:
        return resonance
    claimed_names = list(
        CharacterResonance.objects.filter(character_sheet=sheet).values_list(
            "resonance__name", flat=True
        )
    )
    if claimed_names:
        names_str = ", ".join(sorted(claimed_names))
        msg = f"No resonance '{arg}' found. Your claimed resonances: {names_str}"
        raise CommandError(msg)
    msg = "You have no claimed resonances."
    raise CommandError(msg)


def _resolve_known_technique_id(technique_name: str, sheet: CharacterSheet) -> int:
    """Return the pk of the technique named *technique_name* among *sheet*'s known techniques.

    Case-insensitive match against ``CharacterTechnique`` (mirrors
    ``commands.combat._CombatCommandMixin._find_technique_id``).

    Raises:
        CommandError: If no matching known technique is found.
    """
    from world.magic.models import CharacterTechnique  # noqa: PLC0415

    ct = (
        CharacterTechnique.objects.filter(
            character=sheet,
            technique__name__iexact=technique_name,
        )
        .select_related("technique")
        .first()
    )
    if ct is None:
        msg = f"You don't know a technique called '{technique_name}'."
        raise CommandError(msg)
    return ct.technique_id


def _resolve_target_persona_id_in_room(caller: ObjectDB, target_name: str) -> int:
    """Return the pk of the Persona named *target_name* in the caller's current room.

    Mirrors ``commands.combat.CmdDeclareTechnique._resolve_target_persona_id``'s
    non-combat lookup (the active scene's cached participant personas).

    Raises:
        CommandError: If there is no active scene, or no matching persona is found.
    """
    from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415

    scene = get_active_scene(caller.location)
    if scene is None:
        msg = "There is no active scene here."
        raise CommandError(msg)
    name_lower = target_name.lower()
    for persona in scene.persona_handler.active_participant_personas():
        if persona.name.lower() == name_lower:
            return persona.pk
    msg = f"No persona named '{target_name}' is participating in this scene."
    raise CommandError(msg)


class CmdEnter(ArxCommand):
    """Make a dramatic entrance into the scene.

    Usage:
        enter
        enter <technique>
        enter <technique>=<target>
    """

    key = "enter"
    locks = "cmd:all()"
    action = EntranceAction()

    def resolve_action_args(self) -> dict:
        args = (self.args or "").strip()
        if not args:
            return {}

        technique_part, _, target_part = args.partition("=")
        technique_name = technique_part.strip()
        target_name = target_part.strip()

        sheet = self.caller.sheet_data
        if sheet is None:
            msg = "You don't have a character sheet."
            raise CommandError(msg)

        kwargs: dict = {"technique_id": _resolve_known_technique_id(technique_name, sheet)}
        if target_name:
            kwargs["target_persona_id"] = _resolve_target_persona_id_in_room(
                self.caller, target_name
            )
        return kwargs


class CmdFlourish(ArxCommand):
    """Broadcast a resonance from your pending entry-flourish offer.

    Usage: flourish <resonance name or id>
    """

    key = "flourish"
    locks = "cmd:all()"
    action = ResolveFlourishOfferAction()

    def resolve_action_args(self) -> dict:
        arg = self.require_args("Flourish with which resonance? Usage: flourish <name or id>")
        sheet = self.caller.sheet_data
        if sheet is None:
            msg = "You don't have a character sheet."
            raise CommandError(msg)
        offer = PendingEntryFlourishOffer.objects.filter(character_sheet=sheet).first()
        if offer is None:
            msg = "You have no pending flourish offer."
            raise CommandError(msg)
        resonance = _resolve_resonance(arg, sheet)
        return {"offer": offer, "resonance": resonance}

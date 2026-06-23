from __future__ import annotations

from commands.exceptions import CommandError
from world.magic.audere import PendingAudereOffer
from world.magic.audere_majora import PendingAudereMajoraOffer

_DECLARATION_KEY = "declaration="  # noqa: STRING_LITERAL
_PATH_KEY = "path="  # noqa: STRING_LITERAL


def _resolve_path_by_name(name_fragment: str, paths: list) -> object:
    """Resolve a path by name fragment from an eligible-paths list.

    Raises CommandError when name_fragment is ambiguous or absent with multiple paths.
    Auto-selects when name_fragment is empty and exactly one path is eligible.
    """
    if not name_fragment:
        if len(paths) == 1:
            return paths[0]
        names = ", ".join(p.name for p in paths)
        msg = f"Specify a path: {names}"
        raise CommandError(msg)
    fragment_lower = name_fragment.lower()
    matches = [p for p in paths if fragment_lower in p.name.lower()]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        names = ", ".join(p.name for p in paths)
        msg = f"No path matches '{name_fragment}'. Available: {names}"
        raise CommandError(msg)
    names = ", ".join(p.name for p in matches)
    msg = f"'{name_fragment}' matches more than one path: {names}"
    raise CommandError(msg)


class SurgeOfferHandler:
    keyword = "surge"
    label = "Intensity Surge"

    def pending_for(self, sheet):
        return PendingAudereOffer.objects.filter(character_sheet=sheet).first()

    def describe(self, offer) -> str:
        from world.magic.audere import corruption_advisory_for_character  # noqa: PLC0415

        advisory = corruption_advisory_for_character(offer.character_sheet.character)
        parts = [f"Intensity surge (fired: {offer.fired_intensity})"]
        if advisory:
            parts.append(advisory)
        return ". ".join(parts)

    def accept(self, offer, caller, args: str) -> str:  # noqa: ARG002
        from world.magic.audere import resolve_audere_offer  # noqa: PLC0415
        from world.magic.exceptions import (  # noqa: PLC0415
            AudereOfferNotFoundError,
            AudereOfferStaleError,
        )

        try:
            result = resolve_audere_offer(offer.pk, accept=True)
        except (AudereOfferNotFoundError, AudereOfferStaleError) as exc:
            raise CommandError(str(exc)) from exc
        return (
            f"The surge takes hold. Intensity bonus: +{result.intensity_bonus_applied}. "
            f"Anima pool expanded by {result.anima_pool_expanded_by}."
        )

    def decline(self, offer, caller) -> str:  # noqa: ARG002
        from world.magic.audere import resolve_audere_offer  # noqa: PLC0415
        from world.magic.exceptions import (  # noqa: PLC0415
            AudereOfferNotFoundError,
            AudereOfferStaleError,
        )

        try:
            resolve_audere_offer(offer.pk, accept=False)
        except (AudereOfferNotFoundError, AudereOfferStaleError) as exc:
            raise CommandError(str(exc)) from exc
        return "The surge fades."


class CrossingOfferHandler:
    keyword = "crossing"
    label = "Path Crossing"

    def pending_for(self, sheet):
        return PendingAudereMajoraOffer.objects.filter(character_sheet=sheet).first()

    def describe(self, offer) -> str:
        from world.magic.audere_majora import eligible_paths_for_threshold  # noqa: PLC0415

        character = offer.character_sheet.character
        paths = eligible_paths_for_threshold(character, offer.threshold)
        path_names = ", ".join(p.name for p in paths) if paths else "none"
        return (
            f"Path crossing at level {offer.threshold.boundary_level}. "
            f"Eligible: {path_names}. "
            f"Usage: accept crossing path=<name> declaration=<your words>"
        )

    def accept(self, offer, caller, args: str) -> str:  # noqa: ARG002
        from world.magic.audere_majora import (  # noqa: PLC0415
            eligible_paths_for_threshold,
            resolve_audere_majora_offer,
        )
        from world.magic.exceptions import (  # noqa: PLC0415
            AudereMajoraOfferNotFoundError,
            AudereMajoraOfferStaleError,
            AudereMajoraPathError,
            ProtagonismLockedError,
        )
        from world.magic.types import AlterationGateError  # noqa: PLC0415

        # Parse "path=<name> declaration=<text>" from args.
        # declaration= is greedy to end-of-line; path= precedes it.
        path_name = ""
        declaration = ""
        if _DECLARATION_KEY in args:
            before_decl, _, after_decl = args.partition(_DECLARATION_KEY)
            declaration = after_decl.strip()
            path_part = before_decl.strip()
        else:
            path_part = args.strip()

        if path_part.lower().startswith(_PATH_KEY):
            path_name = path_part[len(_PATH_KEY) :].strip()
        elif path_part:
            path_name = path_part

        if not declaration.strip():
            msg = "A declaration is required: accept crossing path=<name> declaration=<your text>"
            raise CommandError(msg)

        character = offer.character_sheet.character
        paths = eligible_paths_for_threshold(character, offer.threshold)
        chosen = _resolve_path_by_name(path_name, paths)

        try:
            result = resolve_audere_majora_offer(
                offer.pk,
                accept=True,
                path_id=chosen.pk,
                declaration_text=declaration,
            )
        except (
            AudereMajoraOfferNotFoundError,
            AudereMajoraOfferStaleError,
            AudereMajoraPathError,
            ProtagonismLockedError,
            AlterationGateError,
        ) as exc:
            raise CommandError(str(exc)) from exc

        return (
            f"You cross into {result.chosen_path_name} "
            f"(level {result.level_before} -> {result.level_after})."
        )

    def decline(self, offer, caller) -> str:  # noqa: ARG002
        from world.magic.audere_majora import resolve_audere_majora_offer  # noqa: PLC0415
        from world.magic.exceptions import (  # noqa: PLC0415
            AudereMajoraOfferNotFoundError,
            AudereMajoraOfferStaleError,
        )

        try:
            resolve_audere_majora_offer(offer.pk, accept=False)
        except (AudereMajoraOfferNotFoundError, AudereMajoraOfferStaleError) as exc:
            raise CommandError(str(exc)) from exc
        return "You step back from the threshold."

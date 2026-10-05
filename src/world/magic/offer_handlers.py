from __future__ import annotations

from commands.exceptions import CommandError
from world.magic.audere import PendingAudereOffer
from world.magic.audere_majora import PendingAudereMajoraOffer

_ENTRANCE_MARKER_KEY = "entrance"  # noqa: STRING_LITERAL


class SoulfrayPendingHandler:
    """Offer handler for the soulfray consent gate on standalone technique casts.

    When a caster has an active Soulfray stage, the first cast attempt halts and
    registers a ``PendingCast``. This handler routes ``accept soulfray`` /
    ``decline soulfray`` to re-dispatch or discard that pending cast.
    """

    keyword = "soulfray"
    label = "Soulfray Risk"

    def pending_for(self, sheet):
        from commands.pending_actions import peek_pending  # noqa: PLC0415

        return peek_pending(sheet.pk)

    def describe(self, offer) -> str:  # noqa: ARG002
        return "A pending cast would accrue soulfray. Confirm to proceed."

    def accept(self, offer, caller, args: str) -> str:  # noqa: ARG002
        from actions.constants import ActionBackend  # noqa: PLC0415
        from actions.player_interface import dispatch_player_action  # noqa: PLC0415
        from actions.types import ActionRef  # noqa: PLC0415
        from commands.pending_actions import pop_pending  # noqa: PLC0415

        pending = pop_pending(caller.sheet_data.pk)
        if pending is None:
            return "No pending soulfray cast."

        # An entrance-originated halt (#2183) re-dispatches through the "entrance"
        # REGISTRY action, not "cast_technique" — the flourish/suggestion/intervention
        # hooks live only on the entrance path. The marker itself is stripped before
        # forwarding; it isn't a real EntranceAction kwarg.
        if pending.kwargs.get(_ENTRANCE_MARKER_KEY):
            remaining_kwargs = {
                k: v for k, v in pending.kwargs.items() if k != _ENTRANCE_MARKER_KEY
            }
            ref = ActionRef(backend=ActionBackend.REGISTRY, registry_key="entrance")
            result = dispatch_player_action(
                caller,
                ref,
                {
                    **remaining_kwargs,
                    "technique_id": pending.technique_id,
                    "target_persona_id": pending.target_persona_id,
                    "confirm_soulfray_risk": True,
                },
            )
            if result.detail is not None and result.detail.message:
                return result.detail.message
            return "You steel yourself and complete the casting."

        ref = ActionRef(
            backend=ActionBackend.SCENE_ADAPTIVE,
            registry_key="cast_technique",
            technique_id=pending.technique_id,
        )
        result = dispatch_player_action(
            caller,
            ref,
            {
                **pending.kwargs,
                "target_persona_id": pending.target_persona_id,
                "confirm_soulfray_risk": True,
            },
        )
        if result.detail is not None and result.detail.message:
            return result.detail.message
        return "You steel yourself and complete the casting."

    def decline(self, offer, caller) -> str:  # noqa: ARG002
        from commands.pending_actions import pop_pending  # noqa: PLC0415

        pop_pending(caller.sheet_data.pk)
        return "You hold back, the casting unspent."


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
        from world.magic.services.ultimates import ultimate_reveal_for  # noqa: PLC0415

        try:
            result = resolve_audere_offer(offer.pk, accept=True)
        except (AudereOfferNotFoundError, AudereOfferStaleError) as exc:
            raise CommandError(str(exc)) from exc
        message = (
            f"The surge takes hold. Intensity bonus: +{result.intensity_bonus_applied}. "
            f"Anima pool expanded by {result.anima_pool_expanded_by}."
        )
        reveal = ultimate_reveal_for(caller.sheet_data)
        if reveal is not None:
            _store_ultimate_snapshot(caller, reveal)
            message = f"{message}\n{format_ultimate_reveal(reveal)}"
        return message

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

    def accept(self, offer, caller, args: str) -> str:
        from world.magic.audere_majora import (  # noqa: PLC0415
            eligible_paths_for_threshold,
            resolve_audere_majora_offer,
        )
        from world.magic.exceptions import (  # noqa: PLC0415
            AudereMajoraOfferNotFoundError,
            AudereMajoraOfferStaleError,
            AudereMajoraPathError,
            GiftResonanceUnresolvable,
            ProtagonismLockedError,
        )
        from world.magic.services.ultimates import ultimate_reveal_for  # noqa: PLC0415
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
            GiftResonanceUnresolvable,
        ) as exc:
            # str(exc) is empty for every one of these — they're all raised bare
            # (no message args) at their raise sites — so the bare-str idiom
            # silently discarded each exception's own curated ``user_message``
            # and surfaced "" to the telnet player (#2971 final-review fix).
            # Every exception in this tuple declares ``user_message`` (directly
            # or via its base — MagicError/AudereOfferError/CorruptionError chains,
            # or a direct class attribute on AlterationGateError), so plain
            # attribute access is used rather than getattr.
            raise CommandError(exc.user_message) from exc

        message = (
            f"You cross into {result.chosen_path_name} "
            f"(level {result.level_before} -> {result.level_after})."
        )
        reveal = ultimate_reveal_for(caller.sheet_data)
        if reveal is not None:
            _store_ultimate_snapshot(caller, reveal)
            message = f"{message}\n{format_ultimate_reveal(reveal)}"
        return message

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


_ULTIMATE_USAGE = "Choose with: accept ultimate <number>"  # noqa: STRING_LITERAL

# Session-local (non-persistent) snapshot of the choice_keys shown in the last
# printed reveal listing, held on the caller's ``ndb.ultimate_reveal_choice_keys``
# (#4098 fix round 1). Guards against a stale numbered choice: the pools
# backing a reveal can change between the moment a listing is printed and the
# moment the player types a number, and `<n>` always resolves against
# whatever `flat_cards()` returns *right now* — never the list the player
# actually read.


def _ultimate_choice_keys(reveal) -> tuple[str, ...]:
    return tuple(card.choice_key for _group, card in reveal.flat_cards())


def _store_ultimate_snapshot(character, reveal) -> None:
    character.ndb.ultimate_reveal_choice_keys = _ultimate_choice_keys(reveal)


def _clear_ultimate_snapshot(character) -> None:
    del character.ndb.ultimate_reveal_choice_keys


def format_ultimate_reveal(reveal) -> str:
    """Numbered telnet listing; same order as the web reveal (#4098)."""
    from world.magic.constants import UltimateCardKind, UltimateSource  # noqa: PLC0415

    lines = [reveal.framing_text] if reveal.framing_text.strip() else []
    lines.append("Ultimates:")
    for number, (group, card) in enumerate(reveal.flat_cards(), start=1):
        if card.kind == UltimateCardKind.KNOWN:
            text = f"{card.technique.name} (known)"
        elif card.kind == UltimateCardKind.UPGRADE:
            text = f"{card.technique.name} (upgrade of {card.upgrade_of.name})"
        else:
            text = f"{card.label} (undiscovered)"
        if group.source == UltimateSource.PATRON:
            text = text[:-1] + f"; bond: {group.being.name})"
        elif group.source == UltimateSource.COMPANION:
            text = text[:-1] + f"; bond: {group.companion.name})"
        elif group.source == UltimateSource.GIFT:
            text = text[:-1] + f"; gift: {group.gift.name})"
        lines.append(f"  {number}) {text}")
    lines.append(_ULTIMATE_USAGE)
    return "\n".join(lines)


class UltimateRevealHandler:
    """Offer handler for the Audere/Audere Majora ultimate reveal (#4098 decision 16).

    Derived state, not a stored offer row: ``pending_for`` asks the service for
    the open reveal on demand. ``accept`` maps the telnet ``<n>`` ordinal onto
    the reveal's stable card order and hands the resolved ``choice_key`` to
    ``choose_ultimate`` — the service owns every eligibility/locking rule.
    """

    keyword = "ultimate"
    label = "Ultimate Reveal"

    def pending_for(self, sheet):
        from world.magic.services.ultimates import ultimate_reveal_for  # noqa: PLC0415

        return ultimate_reveal_for(sheet)

    def describe(self, offer) -> str:
        """Print the reveal listing, snapshotting its choice_keys as a side effect.

        The snapshot is stored HERE, not in ``accept``, because this is the one
        moment the listing is actually shown to the caller - the ndb snapshot must
        match whatever text just printed, not some earlier or later reveal (#4098
        final review item 11).
        """
        if offer.sheet is not None:
            _store_ultimate_snapshot(offer.sheet.character, offer)
        return format_ultimate_reveal(offer)

    def accept(self, offer, caller, args: str) -> str:
        from world.magic.exceptions import UltimateChoiceError  # noqa: PLC0415
        from world.magic.services.ultimates import choose_ultimate  # noqa: PLC0415

        current_keys = _ultimate_choice_keys(offer)
        shown_keys = caller.ndb.ultimate_reveal_choice_keys
        if shown_keys is None:
            _store_ultimate_snapshot(caller, offer)
            return f"Your reveal listing expired. Choose again:\n{format_ultimate_reveal(offer)}"
        if tuple(shown_keys) != current_keys:
            _store_ultimate_snapshot(caller, offer)
            return f"The choices have changed. Choose again:\n{format_ultimate_reveal(offer)}"

        cards = offer.flat_cards()
        token = args.strip()
        if not token.isdigit() or not 1 <= int(token) <= len(cards):
            raise CommandError(_ULTIMATE_USAGE)
        _group, card = cards[int(token) - 1]
        try:
            known = choose_ultimate(caller.sheet_data, card.choice_key)
        except UltimateChoiceError as exc:
            raise CommandError(exc.user_message) from exc
        _clear_ultimate_snapshot(caller)
        technique = known.technique
        return (
            f"{technique.name}: {technique.description}\n"
            f"Declare it as your action: cast {technique.name} at <target>"
        )

    def decline(self, offer, caller) -> str:  # noqa: ARG002
        return f"The reveal stays open while Audere holds. {_ULTIMATE_USAGE}"

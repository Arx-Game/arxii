"""Telnet ``weave`` command — the thin shell over WeaveThreadAction (#1337, #2033).

Thin telnet face of ``actions.definitions.threads.WeaveThreadAction``. Parses
``weave resonance=<name> <anchor>=<value> [name=<thread name>]`` into the
action's kwargs and delegates; all eligibility/creation logic lives in the
action + the ``weave_thread`` service. The web path uses the same action via
the thread viewset — ``ThreadSerializer._resolve_target``
(``world/magic/serializers.py``) performs the matching target resolution for
the web POST body; this command mirrors its ``TargetKind`` coverage.

Supported anchor kwargs (exactly one required per invocation):
    ``trait=<name or id>``            — TargetKind.TRAIT
    ``track=<partner>/<track name>``  — TargetKind.RELATIONSHIP_TRACK (the
        caller's OWN developed ``RelationshipTrackProgress`` toward the named
        partner; the partner name resolves via Evennia's standard
        ``search()`` — ambiguous names get the usual numbered-disambiguation
        message)
    ``capstone=<id or title>``        — TargetKind.RELATIONSHIP_CAPSTONE (one
        of the caller's OWN recorded capstones)
    ``facet=<name or id>``            — TargetKind.FACET
    ``technique=<name or id>``        — TargetKind.TECHNIQUE (signature
        thread; the caller must already know the technique)
    ``role=<name or id>``             — TargetKind.COVENANT_ROLE
    ``mantle=<name or id>``           — TargetKind.MANTLE

Not reachable from this generic grammar: SANCTUM (woven via ``sanctum
weave``, a room-anchored verb with its own slot grammar — see
``commands/sanctum.py``) and GIFT (committed automatically via
``provision_latent_gift_thread`` / the species-gift pipeline, never authored
freehand by name/id).
"""

from __future__ import annotations

from typing import Any

from actions.definitions.threads import WeaveThreadAction
from commands.command import ArxCommand
from commands.exceptions import CommandError

# Telnet kwarg tokens players type (``key=value``); ``name`` greedily consumes the
# rest of the line so thread names may contain spaces.
_RESONANCE_KWARG = "resonance"
_TRAIT_KWARG = "trait"
_TRACK_KWARG = "track"
_CAPSTONE_KWARG = "capstone"
_FACET_KWARG = "facet"
_TECHNIQUE_KWARG = "technique"
_ROLE_KWARG = "role"
_MANTLE_KWARG = "mantle"
_NAME_KWARG = "name"

# Every recognized anchor-kind kwarg, in the order shown to players on error.
_ANCHOR_KWARGS: tuple[str, ...] = (
    _TRAIT_KWARG,
    _TRACK_KWARG,
    _CAPSTONE_KWARG,
    _FACET_KWARG,
    _TECHNIQUE_KWARG,
    _ROLE_KWARG,
    _MANTLE_KWARG,
)


class CmdWeaveThread(ArxCommand):
    """Weave a new thread anchored to something you are unlocked for.

    Telnet grammar (exactly one anchor kwarg per invocation):
        ``weave resonance=<name> trait=<name or id> [name=<thread name>]``
        ``weave resonance=<name> track=<partner>/<track name> [name=<...>]``
        ``weave resonance=<name> capstone=<id or title> [name=<...>]``
        ``weave resonance=<name> facet=<name or id> [name=<...>]``
        ``weave resonance=<name> technique=<name or id> [name=<...>]``
        ``weave resonance=<name> role=<name or id> [name=<...>]``
        ``weave resonance=<name> mantle=<name or id> [name=<...>]``

    Examples:
        ``weave resonance=Embers trait=Bravery name=Ember of the First Hearth``
        ``weave resonance=Embers trait=5 name=Ember of the First Hearth``
        ``weave resonance=Embers track=Marcus/Trust name=Bound to Marcus``

    ``resonance`` and exactly one anchor kwarg are required; ``name`` is
    optional and captures the rest of the line (so it may contain spaces).
    The thread's resonance and anchor are resolved here; everything else is
    the action's concern.
    """

    key = "weave"
    locks = "cmd:all()"
    action = WeaveThreadAction()

    def resolve_action_args(self) -> dict[str, Any]:
        """Parse ``weave resonance=<name> <anchor>=<value> [name=<...>]`` into action kwargs."""
        from world.magic.models import Resonance  # noqa: PLC0415

        args = self.require_args(
            "Weave what? (weave resonance=<name> "
            "trait=|track=|capstone=|facet=|technique=|role=|mantle=<value> "
            "[name=<thread name>])"
        )
        parsed = self._parse_kwargs(args)

        resonance_name = parsed.get(_RESONANCE_KWARG, "").strip()
        if not resonance_name:
            msg = "Specify a resonance: resonance=<name>."
            raise CommandError(msg)
        resonance = Resonance.objects.filter(name__iexact=resonance_name).first()
        if resonance is None:
            msg = f"There is no resonance called '{resonance_name}'."
            raise CommandError(msg)

        present = [kwarg for kwarg in _ANCHOR_KWARGS if parsed.get(kwarg, "").strip()]
        if not present:
            options = ", ".join(f"{kwarg}=" for kwarg in _ANCHOR_KWARGS)
            msg = f"Specify an anchor: {options}."
            raise CommandError(msg)
        if len(present) > 1:
            msg = f"Specify only one anchor kwarg at a time ({', '.join(present)} given)."
            raise CommandError(msg)
        anchor_kwarg = present[0]
        anchor_value = parsed[anchor_kwarg].strip()
        target_kind, target = self._resolve_anchor(anchor_kwarg, anchor_value)

        return {
            "target_kind": target_kind,
            "target": target,
            "resonance": resonance,
            "name": parsed.get(_NAME_KWARG, "").strip(),
        }

    def _resolve_anchor(self, anchor_kwarg: str, value: str) -> tuple[str, Any]:
        """Dispatch to the per-anchor-kind resolver; returns ``(target_kind, target)``."""
        resolvers = {
            _TRAIT_KWARG: self._resolve_trait_anchor,
            _TRACK_KWARG: self._resolve_track_anchor,
            _CAPSTONE_KWARG: self._resolve_capstone_anchor,
            _FACET_KWARG: self._resolve_facet_anchor,
            _TECHNIQUE_KWARG: self._resolve_technique_anchor,
            _ROLE_KWARG: self._resolve_role_anchor,
            _MANTLE_KWARG: self._resolve_mantle_anchor,
        }
        return resolvers[anchor_kwarg](value)

    def _resolve_trait_anchor(self, value: str) -> tuple[str, Any]:
        from world.magic.constants import TargetKind  # noqa: PLC0415
        from world.traits.models import Trait  # noqa: PLC0415

        trait = self.resolve_by_name_or_id(
            Trait, value, not_found_msg=f"No trait found for '{value}'."
        )
        return TargetKind.TRAIT, trait

    def _resolve_facet_anchor(self, value: str) -> tuple[str, Any]:
        from world.magic.constants import TargetKind  # noqa: PLC0415
        from world.magic.models import Facet  # noqa: PLC0415

        facet = self.resolve_by_name_or_id(
            Facet, value, not_found_msg=f"No facet found for '{value}'."
        )
        return TargetKind.FACET, facet

    def _resolve_technique_anchor(self, value: str) -> tuple[str, Any]:
        from world.magic.constants import TargetKind  # noqa: PLC0415
        from world.magic.models import Technique  # noqa: PLC0415

        technique = self.resolve_by_name_or_id(
            Technique, value, not_found_msg=f"No technique found for '{value}'."
        )
        return TargetKind.TECHNIQUE, technique

    def _resolve_role_anchor(self, value: str) -> tuple[str, Any]:
        from world.covenants.models import CovenantRole  # noqa: PLC0415
        from world.magic.constants import TargetKind  # noqa: PLC0415

        role = self.resolve_by_name_or_id(
            CovenantRole, value, not_found_msg=f"No covenant role found for '{value}'."
        )
        return TargetKind.COVENANT_ROLE, role

    def _resolve_mantle_anchor(self, value: str) -> tuple[str, Any]:
        from world.items.models import Mantle  # noqa: PLC0415
        from world.magic.constants import TargetKind  # noqa: PLC0415

        mantle = self.resolve_by_name_or_id(
            Mantle, value, not_found_msg=f"No mantle found for '{value}'."
        )
        return TargetKind.MANTLE, mantle

    def _resolve_capstone_anchor(self, value: str) -> tuple[str, Any]:
        """Resolve one of the CALLER's OWN recorded ``RelationshipCapstone`` rows."""
        from world.magic.constants import TargetKind  # noqa: PLC0415
        from world.relationships.models import RelationshipCapstone  # noqa: PLC0415

        sheet = self.caller.sheet_data
        capstone = self.resolve_by_name_or_id(
            RelationshipCapstone,
            value,
            field="title",
            not_found_msg=f"You have no recorded capstone matching '{value}'.",
            relationship__source=sheet,
        )
        return TargetKind.RELATIONSHIP_CAPSTONE, capstone

    def _resolve_track_anchor(self, value: str) -> tuple[str, Any]:
        """Resolve the CALLER's OWN ``RelationshipTrackProgress`` toward a named partner.

        Grammar: ``track=<partner>/<track name>`` — a single whitespace-delimited
        token split on the first ``/``. Partner-name ambiguity is reported via
        ``search_or_raise`` — the same Evennia ``search()``
        found/not-found/numbered-disambiguation convention every other
        command uses (e.g. ``CmdRelationship._resolve_target_sheet``).
        """
        from world.magic.constants import TargetKind  # noqa: PLC0415
        from world.relationships.models import RelationshipTrackProgress  # noqa: PLC0415

        partner_token, sep, track_name = value.partition("/")
        partner_token = partner_token.strip()
        track_name = track_name.strip()
        if not sep or not partner_token or not track_name:
            msg = "Specify track=<partner>/<track name>."
            raise CommandError(msg)

        partner = self.search_or_raise(
            partner_token, not_found_msg=f"Could not find '{partner_token}'."
        )
        # Same shape as CmdRelationship._resolve_target_sheet: non-character
        # objects have no sheet_data attribute / row.
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        try:
            partner_sheet = partner.sheet_data
        except (AttributeError, ObjectDoesNotExist) as exc:
            msg = f"'{partner_token}' has no character sheet."
            raise CommandError(msg) from exc
        if partner_sheet is None:
            msg = f"'{partner_token}' has no character sheet."
            raise CommandError(msg)

        sheet = self.caller.sheet_data
        progress = RelationshipTrackProgress.objects.filter(
            relationship__source=sheet,
            relationship__target=partner_sheet,
            track__name__iexact=track_name,
        ).first()
        if progress is None:
            msg = f"You have no developed '{track_name}' track with {partner_token}."
            raise CommandError(msg)
        return TargetKind.RELATIONSHIP_TRACK, progress

    @staticmethod
    def _parse_kwargs(args: str) -> dict[str, str]:
        """Parse ``key=value`` tokens, left to right.

        Every anchor kwarg (``trait``/``track``/``capstone``/``facet``/
        ``technique``/``role``/``mantle``) plus ``resonance`` are single
        whitespace-delimited tokens; once a ``name=`` token is seen, the
        remainder of the line (including spaces) is its value, so thread
        names may contain spaces.
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
            if key == _NAME_KWARG:
                out[_NAME_KWARG] = " ".join([value, *tokens[index + 1 :]]).strip()
                break
            out[key] = value
            index += 1
        return out

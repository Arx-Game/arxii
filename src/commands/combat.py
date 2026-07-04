"""Combat telnet commands — scene-adaptive cast and clash-commit shells.

``CmdDeclareTechnique`` (key ``cast``, alias ``declare``)
---------------------------------------------------------
Routes through the SCENE_ADAPTIVE backend so it works both inside and outside
combat:
- Outside combat: ``dispatch_player_action`` runs ``CastTechniqueAction.execute()``
  immediately (non-combat cast via ``request_technique_cast``).
- Inside a DECLARING combat round: ``dispatch_player_action`` calls
  ``CastTechniqueAction.round_declaration()`` which builds a ``CombatRoundAction``
  declaration row; the round resolves when all participants have declared.

Target resolution is context-sensitive:
- Combat context (``_combat_participant_or_none()`` returns non-None):
  ``at <name>`` is resolved by the technique's own targeting relationship
  (``derive_target_relationship``): ENEMY → ``CombatOpponent`` →
  ``focused_opponent_target_id``; ALLY/SELF → ``CombatParticipant`` →
  ``focused_ally_target_id``.
- Non-combat context: ``at <name>`` is resolved as a ``Persona`` → ``target_persona_id``.

The optional ``secondary`` keyword declares the technique in its derived passive
slot (PHYSICAL → ``passive-physical``, SOCIAL → ``passive-social``, MENTAL →
``passive-mental``) instead of the focused slot.

``CmdClashCommit`` (key ``clash``)
------------------------------------
Commits a technique + optional strain to an active Clash during a DECLARING round.
Routes through the COMBAT backend, wiring the resolved ``Clash.pk`` as
``clash_id`` on the ``ActionRef``.  The dispatcher routes to
``_dispatch_clash_contribution`` which calls ``declare_clash_contribution``.

Syntax: ``clash <opponent> with <technique> [strain=<n>]``
         ``[pull=<thread>[,…] resonance=<name> [tier=N] [beseech=N]]``

The optional pull keywords are parsed by the same mixin helpers used by
``CmdDeclareTechnique`` — no duplicate implementation.  When present, a
``CastPullDeclaration`` is resolved and passed as ``cast_pull`` in the dispatch
kwargs; ``_dispatch_clash_contribution`` commits the pull immediately via
``world.combat.pull_helpers.commit_combat_pull`` so the clash read-path
(``_sum_active_flat_bonuses`` / ``compute_intensity_for_clash``) reflects the
pull during round resolution.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from actions.constants import ActionCategory, CombatActionSlot
from commands.command import DispatchCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from actions.types import ActionRef
    from world.combat.models import CombatParticipant
    from world.magic.types.pull import CastPullDeclaration

# Keyword prefix used to parse effort=<level> from command args.
_EFFORT_PREFIX = "effort="
# Standalone keyword that declares the technique as a passive secondary action.
_SECONDARY_KEYWORD = "secondary"
# Standalone keyword that opts out of gift-technique variant resolution (#1581 Task 8).
_BASE_KEYWORD = "base"
# Keyword prefix used to parse strain=<n> from clash command args.
_STRAIN_PREFIX = "strain="
# Keyword prefixes used to parse fury=<tier> anchor=<name> from cast command args.
# Values are single tokens (a FuryTier name or depth, and the anchor character's
# key); both must be free of spaces.
_FURY_PREFIX = "fury="
_ANCHOR_PREFIX = "anchor="
# Usage hint for the clash command (shared across three error sites in _parse_args).
_CLASH_USAGE = (
    "Usage: clash <opponent> with <technique> [strain=<n>]"
    " [pull=<thread> resonance=<name> [tier=N] [beseech=N]]"
)

# Mapping from ActionCategory to the corresponding passive CombatActionSlot.
_SECONDARY_SLOT: dict[str, str] = {
    ActionCategory.PHYSICAL: CombatActionSlot.PASSIVE_PHYSICAL,
    ActionCategory.SOCIAL: CombatActionSlot.PASSIVE_SOCIAL,
    ActionCategory.MENTAL: CombatActionSlot.PASSIVE_MENTAL,
}


class _CombatCommandMixin:
    """Shared helpers for combat telnet commands.

    Provides ``_combat_participant_or_none``, ``_find_technique_id``, pull-keyword
    parsing (``_extract_pull_keywords``, ``_resolve_cast_pull``, and related statics),
    so that ``CmdDeclareTechnique`` and ``CmdClashCommit`` can reuse the same logic
    without duplicating it.
    """

    # Pull-kwarg prefixes recognised by _extract_pull_keywords.
    _PULL_KWARG_KEYS: frozenset[str] = frozenset({"pull", "resonance", "tier", "beseech"})

    def _combat_participant_or_none(self) -> CombatParticipant | None:
        """Return the caller's active CombatParticipant in a DECLARING encounter, or None.

        Unlike ``_active_participant`` (which raises), this returns ``None`` when the
        caller is not in an active DECLARING combat round so the non-combat path can
        proceed without branching the dispatch regime.
        """
        from world.combat.constants import ParticipantStatus  # noqa: PLC0415
        from world.combat.models import CombatParticipant  # noqa: PLC0415
        from world.scenes.constants import RoundStatus  # noqa: PLC0415

        return (
            CombatParticipant.objects.filter(
                character_sheet=self.caller.sheet_data,
                status=ParticipantStatus.ACTIVE,
                encounter__status=RoundStatus.DECLARING,
            )
            .select_related("encounter")
            .order_by("-encounter__created_at")
            .first()
        )

    def _find_technique_id(self, technique_name: str) -> int:
        """Return the pk of the technique matching *technique_name*.

        Matches case-insensitively against ``Technique.name`` for techniques
        the caller knows (via ``CharacterTechnique``).

        Raises:
            CommandError: If no matching known technique is found.
        """
        from world.magic.models import CharacterTechnique  # noqa: PLC0415

        ct = (
            CharacterTechnique.objects.filter(
                character=self.caller.sheet_data,
                technique__name__iexact=technique_name,
            )
            .select_related("technique")
            .first()
        )
        if ct is None:
            msg = f"You don't know a technique called '{technique_name}'."
            raise CommandError(msg)
        return ct.technique_id

    # -- Pull-keyword parsing --------------------------------------------------

    @staticmethod
    def _is_pull_stop_token(tok: str, pull_keys: frozenset[str]) -> bool:
        """Return True when *tok* marks the start of a non-pull keyword boundary.

        Stops on any ``pull_keys``-prefixed token (``pull=``, ``resonance=``,
        ``tier=``), on ``effort=`` / ``secondary``, and on ``fury=`` / ``anchor=``
        (all handled elsewhere) so a greedy pull value never swallows them.
        """
        lower = tok.lower()
        return (
            any(lower.startswith(k + "=") for k in pull_keys)
            or lower.startswith((_EFFORT_PREFIX, _FURY_PREFIX, _ANCHOR_PREFIX))
            or lower in (_SECONDARY_KEYWORD, _BASE_KEYWORD)
        )

    @staticmethod
    def _greedy_consume(
        tokens: list[str],
        start: int,
        initial: str,
        pull_keys: frozenset[str],
    ) -> tuple[str, int, set[int]]:
        """Greedily extend *initial* with tokens from *start* until a stop boundary.

        Returns ``(value, next_index, consumed_indices)`` where *consumed_indices*
        are the token positions that were merged into *value*.
        """
        consumed: set[int] = set()
        j = start
        while j < len(tokens):
            if _CombatCommandMixin._is_pull_stop_token(tokens[j], pull_keys):
                break
            consumed.add(j)
            initial = initial + " " + tokens[j]
            j += 1
        return initial.strip(), j, consumed

    @staticmethod
    def _validate_pull_tier(tier_val: str | None) -> int:
        """Return the integer tier (default 1) and raise CommandError when invalid."""
        if tier_val is None:
            return 1
        if not tier_val.isdigit() or int(tier_val) not in (1, 2, 3):
            msg = f"Invalid tier '{tier_val}' — choose 1, 2, or 3."
            raise CommandError(msg)
        return int(tier_val)

    @staticmethod
    def _validate_pull_beseech(beseech_val: str | None) -> int:
        """Return the integer emergency-draw bonus (default 0); raise CommandError if invalid.

        Mirrors ``_validate_pull_tier``'s shape: a single optional non-negative
        int token. 0 (absent) means no emergency thread-bond draw was invoked (#1718).
        """
        if beseech_val is None:
            return 0
        if not beseech_val.isdigit():
            msg = f"Invalid beseech amount '{beseech_val}' — must be a non-negative integer."
            raise CommandError(msg)
        return int(beseech_val)

    @classmethod
    def _extract_pull_keywords(
        cls,
        raw: str,
    ) -> tuple[str, str | None, str | None, int, int]:
        """Extract pull=, resonance=, tier=, and beseech= tokens from *raw*.

        Each keyword's value is consumed greedily until the next known keyword
        prefix or end-of-string, so multi-word thread names (e.g. "Ember Strand")
        and comma-separated lists ("Strand A,Strand B") are captured intact.

        Raises:
            CommandError: If ``tier=`` is present but not 1–3, if ``beseech=``
                is present but not a non-negative integer, or if ``pull=`` is
                given without ``resonance=``.

        Returns:
            ``(remainder, pull_val, resonance_val, pull_tier, beseech_bonus)``
            where *remainder* is *raw* with all four keywords stripped out,
            *pull_tier* defaults to 1 when ``tier=`` is absent, and
            *beseech_bonus* defaults to 0 when ``beseech=`` is absent (#1718).
        """
        pull_keys = cls._PULL_KWARG_KEYS
        tokens = raw.split()
        pull_val: str | None = None
        resonance_val: str | None = None
        tier_val: str | None = None
        beseech_val: str | None = None
        skip_indices: set[int] = set()

        i = 0
        while i < len(tokens):
            lower_tok = tokens[i].lower()
            matched_key = next((k for k in pull_keys if lower_tok.startswith(k + "=")), None)
            if matched_key is None:
                i += 1
                continue

            skip_indices.add(i)
            initial = tokens[i][len(matched_key) + 1 :]  # strip "key="
            value, i, consumed = cls._greedy_consume(tokens, i + 1, initial, pull_keys)
            skip_indices.update(consumed)

            if matched_key == "pull":  # noqa: STRING_LITERAL
                pull_val = value or None
            elif matched_key == "resonance":  # noqa: STRING_LITERAL
                resonance_val = value or None
            elif matched_key == "tier":  # noqa: STRING_LITERAL
                tier_val = value or None
            else:
                beseech_val = value or None

        remainder = " ".join(t for idx, t in enumerate(tokens) if idx not in skip_indices)

        pull_tier = cls._validate_pull_tier(tier_val)
        beseech_bonus = cls._validate_pull_beseech(beseech_val)
        if pull_val is not None and resonance_val is None:
            msg = "pull= requires resonance=<name> to be specified as well."
            raise CommandError(msg)

        return remainder, pull_val, resonance_val, pull_tier, beseech_bonus

    def _resolve_cast_pull(
        self,
        pull_thread_str: str | None,
        pull_resonance_str: str | None,
        pull_tier: int,
        beseech_bonus: int = 0,
    ) -> CastPullDeclaration | None:
        """Return a ``CastPullDeclaration`` if *pull_thread_str* is set, else ``None``.

        Resolves threads by name/id owned by the caller's character sheet
        (same resonance, active only) and the resonance by name.

        Args:
            pull_thread_str: Comma-separated thread names/ids, or ``None``.
            pull_resonance_str: Resonance name string, or ``None``.
            pull_tier: Integer tier (1–3).
            beseech_bonus: Emergency thread-bond draw bonus (#1718); 0 means
                no emergency draw was invoked.

        Raises:
            CommandError: If resonance is unknown, any thread is not found /
                does not match the resonance / is retired, or pull= is present
                without resonance=.
        """
        if pull_thread_str is None:
            return None

        from world.magic.models import Resonance, Thread  # noqa: PLC0415
        from world.magic.types.pull import CastPullDeclaration  # noqa: PLC0415

        resonance_val = (pull_resonance_str or "").strip()
        if not resonance_val:
            msg = "pull= requires resonance=<name> to be specified as well."
            raise CommandError(msg)

        resonance_qs = Resonance.objects.filter(name__iexact=resonance_val)
        resonance = resonance_qs.first()
        if resonance is None:
            msg = f"No resonance named '{resonance_val}' found."
            raise CommandError(msg)

        sheet = self.caller.sheet_data
        thread_vals = [t.strip() for t in pull_thread_str.split(",") if t.strip()]
        if not thread_vals:
            msg = "pull= requires at least one thread name or id."
            raise CommandError(msg)

        threads: list[Thread] = []
        for val in thread_vals:
            qs = Thread.objects.filter(owner=sheet, resonance=resonance, retired_at__isnull=True)
            if val.isdigit():
                thread = qs.filter(pk=int(val)).first()
            else:
                thread = qs.filter(name__iexact=val).first()
            if thread is None:
                msg = (
                    f"No active thread '{val}' found for resonance '{resonance_val}'. "
                    "Check that the thread exists, is active, and matches the resonance."
                )
                raise CommandError(msg)
            threads.append(thread)

        return CastPullDeclaration(
            resonance=resonance,
            tier=pull_tier,
            threads=tuple(threads),
            beseech_bonus=beseech_bonus,
        )


class CmdDeclareTechnique(_CombatCommandMixin, DispatchCommand):
    """Cast a technique — works both in and out of combat.

    Usage:
        cast <technique> [at <target>] [effort=<level>] [secondary]
        declare <technique> [at <target>] [effort=<level>] [secondary]

    Outside combat: casts the technique immediately in the active scene.
    In a DECLARING combat round: declares the technique for this round;
    the round resolves once all participants have declared.

    Optionally focus a specific target with ``at <name>`` and set your effort
    level with ``effort=<level>`` (very_low/low/medium/high/extreme;
    defaults to medium).

    Use ``secondary`` to declare the technique as a passive action in its
    arena slot (the technique's action_category decides the slot).
    """

    key = "cast"
    aliases = ["declare"]
    locks = "cmd:all()"

    # -- Parsed state cached on first call to resolve_action_ref ---------------

    _technique_name: str | None = None
    _target_name: str | None = None
    _effort: str = "medium"
    _secondary: bool = False
    _parsed: bool = False
    _participant: CombatParticipant | None = None
    # Pull-related parsed state (None means no pull declared).
    _pull_thread_str: str | None = None
    _pull_resonance_str: str | None = None
    _pull_tier: int = 1
    _beseech_bonus: int = 0
    # Fury-related parsed state (None means no fury declared).
    _fury_str: str | None = None
    _anchor_str: str | None = None
    # Base-form opt-out (#1581 Task 8).
    _use_base_form: bool = False

    # --------------------------------------------------------------------------

    def _parse_args(self) -> None:
        """Parse ``self.args`` once; cache technique name, optional target, effort, secondary.

        Also extracts optional pull=<thread>[,…], resonance=<name>, tier=<1-3>,
        and beseech=<n> keywords for a thread-pull declaration.  All keyword=value
        pairs are order-independent and are stripped before the positional
        ``<technique>`` and ``at <target>`` parsing.
        """
        if self._parsed:
            return

        import re  # noqa: PLC0415

        from world.fatigue.constants import EffortLevel  # noqa: PLC0415

        raw = (self.args or "").strip()
        if not raw:
            msg = "Usage: cast <technique> [at <target>] [effort=<level>] [secondary]"
            raise CommandError(msg)

        # Strip pull=<threads>, resonance=<name>, tier=<1-3> if present FIRST so
        # that effort= and pull keywords are fully order-independent.  (If effort=
        # were split first, any pull keyword that follows effort= in the input string
        # would be silently discarded.)
        # _extract_pull_keywords also validates tier range and pull+resonance pairing.
        raw, pull_thread_str, resonance_str, pull_tier, beseech_bonus = self._extract_pull_keywords(
            raw
        )

        # Strip fury=<tier> and anchor=<name> if present (single-token values).
        # Done before effort=/secondary/at parsing so the keywords are fully
        # order-independent and never swallowed into the technique/target name.
        raw, fury_str, anchor_str = self._extract_fury_keywords(raw)

        # Strip off effort=<level> if present.  After pull keywords are removed,
        # only effort= and positional tokens remain, so a simple split is safe.
        effort_str: str = EffortLevel.MEDIUM
        if _EFFORT_PREFIX in raw.lower():
            # Split case-insensitively so "Effort=HIGH" is handled correctly.
            parts = re.split(re.escape(_EFFORT_PREFIX), raw, flags=re.IGNORECASE)
            raw = parts[0].strip()
            effort_val = parts[1].strip().lower()
            valid_values = {v.value for v in EffortLevel}
            if effort_val not in valid_values:
                choices = "/".join(sorted(valid_values))
                msg = f"Invalid effort level '{effort_val}'. Choose from: {choices}"
                raise CommandError(msg)
            effort_str = effort_val

        # Strip standalone trailing "secondary" and "base" keywords (case-insensitive,
        # whole word).  Must come after effort= stripping so the remaining raw is
        # clean.  Both keywords can coexist on the same command line in any order.
        raw, secondary, use_base_form = self._strip_cast_mode_keywords(raw)

        # Split on the first " at " (case-insensitive) to separate technique from
        # the optional target. A literal search avoids a backtracking-prone regex.
        at_index = raw.lower().find(" at ")
        if at_index != -1:
            self._technique_name = raw[:at_index].strip()
            self._target_name = raw[at_index + len(" at ") :].strip()
        else:
            self._technique_name = raw.strip()
            self._target_name = None

        if not self._technique_name:
            msg = "Usage: cast <technique> [at <target>] [effort=<level>] [secondary]"
            raise CommandError(msg)

        self._effort = effort_str
        self._secondary = secondary
        self._use_base_form = use_base_form
        self._pull_thread_str = pull_thread_str
        self._pull_resonance_str = resonance_str
        self._pull_tier = pull_tier
        self._beseech_bonus = beseech_bonus
        self._fury_str = fury_str
        self._anchor_str = anchor_str
        self._parsed = True

    @staticmethod
    def _strip_trailing_keyword(raw: str, kw: str) -> tuple[str, bool]:
        """Strip a standalone trailing *kw* from *raw* (case-insensitive, whole word).

        Returns ``(remainder, found)`` where *remainder* is the raw string with the
        keyword removed (and trailing whitespace stripped), and *found* is True when
        the keyword was present.  Plain string ops avoid a backtracking-prone regex.
        """
        stripped = raw.rstrip()
        if stripped.lower().endswith(kw) and (
            len(stripped) == len(kw) or stripped[-len(kw) - 1].isspace()
        ):
            return stripped[: -len(kw)].rstrip(), True
        return raw, False

    def _strip_cast_mode_keywords(self, raw: str) -> tuple[str, bool, bool]:
        """Strip trailing ``secondary`` and ``base`` keywords in any order.

        Both keywords are standalone trailing tokens (case-insensitive, whole
        word).  Loops until neither is the trailing token so that ``secondary
        base`` and ``base secondary`` both yield the correct flags — fixing the
        fixed-order stripping bug (#1581 Task 9).

        Returns ``(remainder, secondary, use_base_form)``.
        """
        secondary = False
        use_base_form = False
        changed = True
        while changed:
            changed = False
            raw, found = self._strip_trailing_keyword(raw, _SECONDARY_KEYWORD)
            if found:
                secondary = True
                changed = True
            raw, found = self._strip_trailing_keyword(raw, _BASE_KEYWORD)
            if found:
                use_base_form = True
                changed = True
        return raw, secondary, use_base_form

    @staticmethod
    def _extract_fury_keywords(raw: str) -> tuple[str, str | None, str | None]:
        """Strip ``fury=<tier>`` and ``anchor=<name>`` tokens from *raw*.

        Both values are single tokens (no spaces): ``fury=`` names a FuryTier by
        name or depth; ``anchor=`` names the bonded character whose harm the rage
        answers to. Returns ``(remainder, fury_val, anchor_val)`` with both
        keywords removed; either value is ``None`` when its keyword is absent.
        """
        fury_val: str | None = None
        anchor_val: str | None = None
        kept: list[str] = []
        for token in raw.split():
            lower = token.lower()
            if lower.startswith(_FURY_PREFIX):
                fury_val = token[len(_FURY_PREFIX) :] or None
            elif lower.startswith(_ANCHOR_PREFIX):
                anchor_val = token[len(_ANCHOR_PREFIX) :] or None
            else:
                kept.append(token)
        return " ".join(kept), fury_val, anchor_val

    def _resolve_fury_commitment_id(self) -> int | None:
        """Return the pk of the FuryTier named by ``fury=`` (by name or depth).

        Returns ``None`` when no ``fury=`` was declared.

        Raises:
            CommandError: If a fury tier was named but no matching tier exists.
        """
        if not self._fury_str:
            return None

        from world.magic.models import FuryTier  # noqa: PLC0415

        value = self._fury_str
        qs = FuryTier.objects.filter(name__iexact=value)
        tier = qs.first()
        if tier is None and value.isdigit():
            tier = FuryTier.objects.filter(depth=int(value)).first()
        if tier is None:
            msg = f"No fury tier called '{value}'."
            raise CommandError(msg)
        return tier.pk

    def _inject_fury_kwargs(self, kwargs: dict[str, Any]) -> None:
        """Add ``fury_commitment_id`` / ``fury_anchor_id`` to *kwargs* when declared."""
        fury_commitment_id = self._resolve_fury_commitment_id()
        if fury_commitment_id is not None:
            kwargs["fury_commitment_id"] = fury_commitment_id
        fury_anchor_id = self._resolve_fury_anchor_id()
        if fury_anchor_id is not None:
            kwargs["fury_anchor_id"] = fury_anchor_id

    def _resolve_fury_anchor_id(self) -> int | None:
        """Return the CharacterSheet pk named by ``anchor=`` (bonded character key).

        Returns ``None`` when no ``anchor=`` was declared.

        Raises:
            CommandError: If an anchor name was given but no matching character
                sheet exists.
        """
        if not self._anchor_str:
            return None

        from world.character_sheets.models import CharacterSheet  # noqa: PLC0415

        name = self._anchor_str
        sheet = CharacterSheet.objects.filter(character__db_key__iexact=name).first()
        if sheet is None:
            msg = f"No character named '{name}' to anchor your fury to."
            raise CommandError(msg)
        return sheet.pk

    # -- Resolution helpers ----------------------------------------------------

    def _active_participant(self) -> CombatParticipant:
        """Return the caller's active CombatParticipant in a DECLARING encounter.

        Raises:
            CommandError: If no active DECLARING combat is found.
        """
        participant = self._combat_participant_or_none()
        if participant is None:
            msg = "You are not in an active combat round."
            raise CommandError(msg)
        return participant

    def _resolve_technique_id(self) -> int:
        """Return the pk of the technique named by ``self._technique_name``.

        Delegates to the shared mixin helper.  Keeps the zero-argument call
        signature used by the rest of this class.

        Raises:
            CommandError: If no matching known technique is found.
        """
        return self._find_technique_id(self._technique_name or "")

    def _resolve_technique(self) -> Technique:  # type: ignore[name-defined]  # noqa: F821
        """Return the ``Technique`` object named by ``self._technique_name``.

        Uses the same CharacterTechnique lookup as ``_resolve_technique_id`` but
        returns the full object so callers can read ``action_category`` etc.

        Raises:
            CommandError: If no matching known technique is found.
        """
        from world.magic.models import CharacterTechnique  # noqa: PLC0415

        name = self._technique_name or ""
        ct = (
            CharacterTechnique.objects.filter(
                character=self.caller.sheet_data,
                technique__name__iexact=name,
            )
            .select_related("technique")
            .first()
        )
        if ct is None:
            msg = f"You don't know a technique called '{name}'."
            raise CommandError(msg)
        return ct.technique

    def _resolve_ally_target_id(self, participant: CombatParticipant) -> int | None:
        """Return the pk of the ``CombatParticipant`` named by ``self._target_name``.

        Scoped to the encounter so cross-encounter names cannot be targeted.

        Returns ``None`` when no target name was provided.

        Raises:
            CommandError: If a target name was given but no matching active
                participant was found.
        """
        if not self._target_name:
            return None

        from world.combat.constants import ParticipantStatus  # noqa: PLC0415
        from world.combat.models import CombatParticipant  # noqa: PLC0415

        name = self._target_name
        matches = list(
            CombatParticipant.objects.filter(
                encounter=participant.encounter,
                status=ParticipantStatus.ACTIVE,
                character_sheet__character__db_key__iexact=name,
            )
        )
        if not matches:
            msg = f"No active ally named '{name}' in this encounter."
            raise CommandError(msg)
        if len(matches) > 1:
            msg = f"More than one ally named '{name}' — be more specific."
            raise CommandError(msg)
        return matches[0].pk

    def _resolve_opponent_target_id(self) -> int | None:
        """Return the pk of the CombatOpponent named by ``self._target_name``.

        Scoped to the caller's active encounter so stale/cross-encounter ids
        cannot be targeted.

        Returns ``None`` when no target name was provided (untargeted cast).

        Raises:
            CommandError: If a target name was given but no matching active
                opponent was found.
        """
        if not self._target_name:
            return None

        from world.combat.constants import OpponentStatus  # noqa: PLC0415
        from world.combat.models import CombatOpponent  # noqa: PLC0415

        # Reuse the participant cached by resolve_action_ref; fall back to querying.
        participant = (
            self._participant if self._participant is not None else self._active_participant()
        )
        name = self._target_name
        matches = list(
            CombatOpponent.objects.filter(
                encounter=participant.encounter,
                status=OpponentStatus.ACTIVE,
                name__iexact=name,
            )
        )
        if not matches:
            msg = f"No active opponent named '{name}' in this encounter."
            raise CommandError(msg)
        if len(matches) > 1:
            msg = f"More than one opponent named '{name}' — be more specific."
            raise CommandError(msg)
        return matches[0].pk

    def _resolve_target_persona_id(self) -> int | None:
        """Return the pk of the Persona named by ``self._target_name``, or None.

        Used on the non-combat path when ``at <name>`` names a scene participant.
        The lookup scopes to the active scene's cached participant personas.

        Raises:
            CommandError: If a target name was given but no matching Persona exists
                in the active scene.
        """
        if not self._target_name:
            return None

        from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415

        name = self._target_name.lower()
        scene = get_active_scene(self.caller.location)
        if scene is None:
            msg = "There is no active scene here."
            raise CommandError(msg)

        for persona in scene.persona_handler.active_participant_personas():
            if persona.name.lower() == name:
                return persona.pk

        msg = f"No persona named '{self._target_name}' is participating in this scene."
        raise CommandError(msg)

    def _cast_pull(self) -> CastPullDeclaration | None:
        """Return a ``CastPullDeclaration`` if pull= was declared, else ``None``.

        Delegates to the mixin's ``_resolve_cast_pull`` using cached parsed state.
        """
        return self._resolve_cast_pull(
            self._pull_thread_str,
            self._pull_resonance_str,
            self._pull_tier,
            self._beseech_bonus,
        )

    # -- DispatchCommand interface ---------------------------------------------

    def resolve_action_ref(self) -> ActionRef:
        """Build a SCENE_ADAPTIVE ``ActionRef`` for the named technique.

        Parses args on the first call and caches the results so
        ``resolve_action_args`` can reuse them without re-parsing.

        Routes through the SCENE_ADAPTIVE backend so the dispatcher decides
        whether to run immediately (non-combat) or defer as a round declaration
        (inside a DECLARING combat round) — no gating on active combat here.

        When ``secondary`` was parsed, the action_slot is derived from the
        technique's ``action_category`` and included in the ref so
        ``round_declaration`` routes to the correct passive slot.
        """
        from actions.constants import ActionBackend  # noqa: PLC0415
        from actions.types import ActionRef  # noqa: PLC0415

        self._parse_args()
        technique_id = self._resolve_technique_id()

        action_slot = None
        if self._secondary:
            technique = self._resolve_technique()
            action_slot = _SECONDARY_SLOT.get(technique.action_category)

        return ActionRef(
            backend=ActionBackend.SCENE_ADAPTIVE,
            registry_key="cast_technique",
            technique_id=technique_id,
            action_slot=action_slot,
        )

    def resolve_action_args(self) -> dict[str, Any]:
        """Return dispatch kwargs; routes target resolution by context.

        Always includes ``effort_level``.  If ``at <target>`` was given in a
        combat context the technique's authored target relationship decides
        the kwarg:
        - ``ENEMY`` → ``focused_opponent_target_id`` (CombatOpponent pk).
        - ``ALLY``/``SELF`` → ``focused_ally_target_id`` (CombatParticipant pk).

        In a non-combat context ``at <target>`` resolves as
        ``target_persona_id`` (Persona pk).

        When ``secondary`` was parsed, ``action_slot`` is forwarded so
        ``CastTechniqueAction.round_declaration`` routes to the passive slot.
        """
        self._parse_args()
        kwargs: dict[str, Any] = {"effort_level": self._effort}

        if self._secondary:
            technique = self._resolve_technique()
            slot = _SECONDARY_SLOT.get(technique.action_category)
            if slot is not None:
                kwargs["action_slot"] = slot

        # Resolve an optional thread pull declaration and inject into kwargs.
        cast_pull = self._cast_pull()
        if cast_pull is not None:
            kwargs["cast_pull"] = cast_pull

        # Resolve an optional fury commitment (tier + bonded anchor). Fury is a
        # combat/clash lever; round_declaration forwards these into the
        # CombatRoundAction, where resolve_combat_technique consumes them.
        self._inject_fury_kwargs(kwargs)

        # Base-form opt-out: only inject when explicitly declared to keep the
        # default (variant applied) from polluting kwargs unnecessarily.
        if self._use_base_form:
            kwargs["use_base_form"] = True

        if self._target_name:
            self._inject_target_kwargs(kwargs)

        return kwargs

    def _inject_target_kwargs(self, kwargs: dict[str, Any]) -> None:
        """Resolve ``at <target>`` into the right kwarg based on combat context.

        In a DECLARING combat round the technique's authored target relationship
        decides the kwarg (``ENEMY`` → ``focused_opponent_target_id``;
        ``ALLY``/``SELF`` → ``focused_ally_target_id``). Outside combat it
        resolves as ``target_persona_id``.
        """
        from world.magic.models.techniques import ConditionTargetKind  # noqa: PLC0415
        from world.magic.services.targeting import derive_target_relationship  # noqa: PLC0415

        # Check whether we're in a DECLARING combat round to decide how to
        # resolve the target name. Cache the participant for later helpers.
        participant = self._combat_participant_or_none()
        if participant is not None:
            self._participant = participant
            # Use the technique's authored relationship to route target resolution.
            technique = self._resolve_technique()
            relationship = derive_target_relationship(technique)
            if relationship == ConditionTargetKind.ENEMY:
                opp_id = self._resolve_opponent_target_id()
                if opp_id is not None:
                    kwargs["focused_opponent_target_id"] = opp_id
            else:
                # ALLY or SELF: resolve as a CombatParticipant in this encounter.
                ally_id = self._resolve_ally_target_id(participant)
                if ally_id is not None:
                    kwargs["focused_ally_target_id"] = ally_id
        else:
            persona_id = self._resolve_target_persona_id()
            if persona_id is not None:
                kwargs["target_persona_id"] = persona_id


class CmdClashCommit(_CombatCommandMixin, DispatchCommand):
    """Commit a technique to an active Clash during a DECLARING combat round.

    Usage:
        clash <opponent> with <technique> [strain=<n>]
            [pull=<thread>[,…] resonance=<name> [tier=N] [beseech=N]]

    Identifies the active Clash against the named NPC opponent and declares a
    ClashContributionDeclaration via the COMBAT backend dispatcher.  The round
    resolves when all participants have declared; the clash post-pass then drives
    ``run_clash_round`` and writes ``ClashContribution`` audit rows.

    ``strain=<n>`` commits extra anima beyond the technique's base cost (default 0).

    The optional pull keywords work identically to the cast command: when present,
    ``_dispatch_clash_contribution`` commits a ``CombatPull`` at declaration time so
    the clash read-path (``_sum_active_flat_bonuses`` / ``compute_intensity_for_clash``)
    reflects the pull during round resolution.  The one-pull-per-round cap still
    applies — a player who pulled on a cast this round cannot also pull on a clash.
    """

    key = "clash"
    locks = "cmd:all()"

    # -- Parsed state -----------------------------------------------------------

    _opponent_name: str | None = None
    _technique_name: str | None = None
    _strain: int = 0
    _parsed: bool = False
    # Pull-related parsed state (None means no pull declared).
    _pull_thread_str: str | None = None
    _pull_resonance_str: str | None = None
    _pull_tier: int = 1
    _beseech_bonus: int = 0

    # ---------------------------------------------------------------------------

    def _parse_args(self) -> None:
        """Parse ``self.args`` once; cache opponent, technique, strain, and optional pull."""
        if self._parsed:
            return

        import re  # noqa: PLC0415

        raw = (self.args or "").strip()
        if not raw:
            raise CommandError(_CLASH_USAGE)

        # Strip pull=<threads>, resonance=<name>, tier=<1-3>, beseech=<n> FIRST —
        # order-independent. _extract_pull_keywords also validates tier range and
        # pull+resonance pairing.
        raw, pull_thread_str, resonance_str, pull_tier, beseech_bonus = self._extract_pull_keywords(
            raw
        )

        # Strip off strain=<n> suffix (case-insensitive).
        strain = 0
        if _STRAIN_PREFIX in raw.lower():
            parts = re.split(re.escape(_STRAIN_PREFIX), raw, flags=re.IGNORECASE)
            raw = parts[0].strip()
            strain_str = parts[1].strip()
            if not strain_str.isdigit():
                msg = f"Invalid strain value '{strain_str}' — must be a non-negative integer."
                raise CommandError(msg)
            strain = int(strain_str)

        # Split on " with " (case-insensitive) to separate opponent from technique.
        with_index = raw.lower().find(" with ")
        if with_index == -1:
            raise CommandError(_CLASH_USAGE)

        self._opponent_name = raw[:with_index].strip()
        self._technique_name = raw[with_index + len(" with ") :].strip()

        if not self._opponent_name or not self._technique_name:
            raise CommandError(_CLASH_USAGE)

        self._strain = strain
        self._pull_thread_str = pull_thread_str
        self._pull_resonance_str = resonance_str
        self._pull_tier = pull_tier
        self._beseech_bonus = beseech_bonus
        self._parsed = True

    def _resolve_clash(self, participant: CombatParticipant) -> Any:
        """Return the active Clash for this participant's encounter against the named opponent.

        Raises:
            CommandError: If no active Clash matches or the name is ambiguous.
        """
        from world.combat.constants import ClashStatus  # noqa: PLC0415
        from world.combat.models import Clash  # noqa: PLC0415

        name = self._opponent_name or ""
        matches = list(
            Clash.objects.filter(
                encounter=participant.encounter,
                status=ClashStatus.ACTIVE,
                npc_opponent__name__iexact=name,
            ).select_related("npc_opponent")
        )
        if not matches:
            msg = f"No active Clash against '{name}' in this encounter."
            raise CommandError(msg)
        if len(matches) > 1:
            msg = f"More than one active Clash against '{name}' — be more specific."
            raise CommandError(msg)
        return matches[0]

    # -- DispatchCommand interface ---------------------------------------------

    def resolve_action_ref(self) -> ActionRef:
        """Build a COMBAT ``ActionRef`` carrying the resolved Clash pk.

        Locates the caller's active DECLARING participant, then finds the
        active Clash against the named opponent.  Raises ``CommandError`` when
        the caller is not in a DECLARING round or no matching Clash is found.
        """
        from actions.constants import ActionBackend  # noqa: PLC0415
        from actions.types import ActionRef  # noqa: PLC0415

        self._parse_args()

        participant = self._combat_participant_or_none()
        if participant is None:
            msg = "You are not in an active combat round."
            raise CommandError(msg)

        clash = self._resolve_clash(participant)

        # ClashActionSlot.FOCUSED.value == "FOCUSED" (TextChoices first element).
        # Pass the string literal directly to avoid a ty false-positive on
        # TextChoices value extraction (same pattern used in player_interface.py).
        return ActionRef(
            backend=ActionBackend.COMBAT,
            clash_id=clash.pk,
            clash_action_slot="FOCUSED",
        )

    def resolve_action_args(self) -> dict[str, Any]:
        """Return ``technique_id``, ``strain_commitment``, and optional ``cast_pull``.

        When pull keywords were parsed, resolves a ``CastPullDeclaration`` and
        includes it as ``cast_pull`` — ``_dispatch_clash_contribution`` commits the
        pull via ``world.combat.pull_helpers.commit_combat_pull`` at declaration time.
        """
        self._parse_args()
        technique_id = self._find_technique_id(self._technique_name or "")
        kwargs: dict[str, Any] = {
            "technique_id": technique_id,
            "strain_commitment": self._strain,
        }
        cast_pull = self._resolve_cast_pull(
            self._pull_thread_str,
            self._pull_resonance_str,
            self._pull_tier,
            self._beseech_bonus,
        )
        if cast_pull is not None:
            kwargs["cast_pull"] = cast_pull
        return kwargs

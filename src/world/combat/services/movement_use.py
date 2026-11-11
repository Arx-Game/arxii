"""One use of a movement power: a cast of its technique, or fatigue for anything else (#5066).

Every use of a technique-granted movement power (each automatic dodge, each move on her turn
that needs the power, each blow her smoke form softens) is a cast of the granting technique:
``use_technique`` pays its anima (an overspend goes through the deficit and Soulfray path,
never a refusal), and the resolve function here rolls the technique's own check with the
round's pulls that relate to it. The roll sets the use's **strength**: the grant's value at
this cast's power, scaled by the success level (a failure gives none). The strength is the
dodge's bonus on her defense roll and, through the shared bands
(``traversal.reach_for_strength``), how far she may go. Nothing lasts past the use: the
standing capability is never raised (ADR-0248 stands).

Any other source (trained ability, a condition, species, a distinction) pays physical
fatigue in a fight (``MovementConfig.dodge_fatigue_cost``) and nothing outside one, as
walking; its strength is its value.

Two answers protect her. With ``confirm_soulfray_risk`` False (her dodge plan's "dodge even
into Soulfray" box unticked) a cast that would overspend her anima or deepen her Soulfray
does not go off and costs nothing. And a use she did not choose herself is never lethal for a
player who is not connected ("AFK never kills"): the cast runs non-lethal, so it cannot draw
past her pool or reach a Soulfray stage that can kill.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from world.areas.positioning.constants import ReactionReach
from world.areas.positioning.traversal import reach_for_strength
from world.combat.constants import ActionCategory

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.areas.positioning.traversal import MovementSource
    from world.checks.types import CheckResult
    from world.combat.models import CombatParticipant
    from world.magic.models import Technique, TechniqueCapabilityGrant
    from world.magic.types.magic_skills import CastCheck
    from world.magic.types.power_ledger import PowerLedger


@dataclass
class MovementUse:
    """What one use of a movement power did."""

    went_off: bool
    strength: int
    technique: Technique | None = None
    roll: CheckResult | None = None
    anima_paid: int = 0
    fatigue_paid: int = 0
    soulfray_added: int = 0

    @property
    def reach(self) -> str:
        """How far this use may take her: none when it did not go off."""
        if not self.went_off:
            return ReactionReach.NONE
        return reach_for_strength(self.strength)


def scaled_strength(value: int, success_level: int) -> int:
    """A technique use's strength from its grant's ``value`` and the roll's success level.

    A failure (below 1) gives none; a bare success gives the value; each level above adds
    ``MovementConfig.strength_per_success_level_percent`` of it.
    """
    from world.combat.models import MovementConfig  # noqa: PLC0415

    if success_level < 1 or value <= 0:
        return 0
    row = MovementConfig.objects.cached_singleton() or MovementConfig()
    percent = 100 + row.strength_per_success_level_percent * (success_level - 1)
    return value * percent // 100


def roll_technique(
    character: ObjectDB,  # noqa: OBJECTDB_PARAM - the roller's game object, as perform_check
    cast_check: CastCheck,
    *,
    extra_modifiers: int = 0,
) -> CheckResult:
    """The technique roll of one movement use: its cast check, unopposed."""
    from world.checks.services import perform_check  # noqa: PLC0415

    return perform_check(
        character,
        cast_check.check_type,
        target_difficulty=0,
        extra_modifiers=extra_modifiers,
        extra_traits=cast_check.extra_traits,
    )


@dataclass
class MovementCast:
    """The ``resolve_fn`` ``use_technique`` runs once the use is paid: roll and size it.

    The roll is the technique's cast check, unopposed, plus the round's committed FLAT_BONUS
    pull effects that relate to this technique (``round_pull_bonus``); the power is the cast's
    ledger plus the related INTENSITY_BUMP effects. Returns itself; ``check_result`` is the
    roll, which a control mishap reads.
    """

    character: ObjectDB
    technique: Technique
    grant: TechniqueCapabilityGrant
    cast_check: CastCheck
    participant: CombatParticipant | None = None
    check_result: CheckResult | None = None
    strength: int = 0

    def __call__(
        self,
        *,
        power: int,  # noqa: ARG002 - the ledger carries it
        ledger: PowerLedger,
        extra_modifiers: int = 0,  # noqa: ARG002 - the pull is on this roll
    ) -> MovementCast:
        from world.magic.constants import EffectKind  # noqa: PLC0415

        flat = self._pull(EffectKind.FLAT_BONUS)
        effective_power = ledger.total + self._pull(EffectKind.INTENSITY_BUMP)
        self.check_result = roll_technique(self.character, self.cast_check, extra_modifiers=flat)
        value = self.grant.calculate_value(effective_power=effective_power)
        self.strength = scaled_strength(value, self.check_result.success_level)
        return self

    def _pull(self, kind: str) -> int:
        if self.participant is None:
            return 0
        from world.combat.pull_helpers import round_pull_bonus  # noqa: PLC0415

        return round_pull_bonus(
            self.participant,
            kind=kind,
            technique_id=self.technique.pk,
            cast_check=self.cast_check,
        )


def player_is_present(character: ObjectDB) -> bool:  # noqa: OBJECTDB_PARAM - a session check
    """Whether a player is connected to ``character`` right now."""
    return character.sessions.count() > 0


def use_movement_source(  # noqa: PLR0913 - one use and its two consent answers
    character: ObjectDB,  # noqa: OBJECTDB_PARAM - the caster's game object, as use_technique
    movement: MovementSource,
    *,
    participant: CombatParticipant | None = None,
    lethal: bool = False,
    confirm_soulfray_risk: bool = True,
    chosen_by_player: bool = True,
    category: str = ActionCategory.PHYSICAL,
) -> MovementUse:
    """Make one use of ``movement``: a cast of its technique, or fatigue for anything else.

    ``participant`` is set in a fight (the round's pulls reach the roll; fatigue is charged);
    ``lethal`` is the encounter's. ``chosen_by_player`` False marks an automatic use (a
    dodge, a softened blow): for a player not connected it runs non-lethal.
    """
    if movement.technique_id is None:
        return _use_non_technique(character, movement, participant=participant, category=category)
    lethal = lethal and (chosen_by_player or player_is_present(character))
    return _cast_technique(
        character,
        movement,
        participant=participant,
        lethal=lethal,
        confirm_soulfray_risk=confirm_soulfray_risk,
    )


def _use_non_technique(
    character: ObjectDB,  # noqa: OBJECTDB_PARAM - the mover's game object
    movement: MovementSource,
    *,
    participant: CombatParticipant | None,
    category: str,
) -> MovementUse:
    """Physical (or the use's own kind of) fatigue in a fight; free outside one."""
    fatigue = 0
    if participant is not None:
        from world.combat.services.reactions import reaction_tuning  # noqa: PLC0415
        from world.fatigue.constants import EffortLevel  # noqa: PLC0415
        from world.fatigue.services import apply_fatigue  # noqa: PLC0415

        fatigue = reaction_tuning().dodge_fatigue_cost
        apply_fatigue(character.sheet_data, category, fatigue, EffortLevel.LOW)
    return MovementUse(went_off=True, strength=movement.standing_strength, fatigue_paid=fatigue)


def _would_overspend(character: ObjectDB, technique: Technique, *, lethal: bool) -> bool:  # noqa: OBJECTDB_PARAM
    """Whether a cast now would draw past her anima or she is already in Soulfray."""
    from world.magic.services.soulfray import get_soulfray_warning  # noqa: PLC0415
    from world.magic.services.techniques import preview_technique_anima_cost  # noqa: PLC0415

    if get_soulfray_warning(character) is not None:
        return True
    cost = preview_technique_anima_cost(character, technique, lethal=lethal)
    return cost.effective_cost > cost.current_anima


def _cast_technique(
    character: ObjectDB,  # noqa: OBJECTDB_PARAM - the caster's game object
    movement: MovementSource,
    *,
    participant: CombatParticipant | None,
    lethal: bool,
    confirm_soulfray_risk: bool,
) -> MovementUse:
    from world.magic.models import Technique, TechniqueCapabilityGrant  # noqa: PLC0415
    from world.magic.services import use_technique  # noqa: PLC0415
    from world.magic.services.magic_skills import resolve_cast_check  # noqa: PLC0415

    technique = Technique.objects.get(pk=movement.technique_id)
    grant = TechniqueCapabilityGrant.objects.filter(
        technique=technique, capability_id=movement.application.capability_id
    ).first()
    cast_check = resolve_cast_check(character, technique)
    if grant is None or cast_check is None:
        # A technique with no check to roll cannot be cast; the use does not happen.
        return MovementUse(went_off=False, strength=0, technique=technique)
    if not confirm_soulfray_risk and _would_overspend(character, technique, lethal=lethal):
        return MovementUse(went_off=False, strength=0, technique=technique)
    cast = MovementCast(
        character=character,
        technique=technique,
        grant=grant,
        cast_check=cast_check,
        participant=participant,
    )
    situation_ctx = None
    pulled_resonance = None
    if participant is not None:
        from world.combat.pull_helpers import round_pull_resonance  # noqa: PLC0415
        from world.combat.round_context import CombatRoundContext  # noqa: PLC0415

        situation_ctx = CombatRoundContext(participant)
        pulled_resonance = round_pull_resonance(participant)
    use = use_technique(
        character=character,
        technique=technique,
        resolve_fn=cast,
        confirm_soulfray_risk=confirm_soulfray_risk,
        lethal=lethal,
        cast_check=cast_check,
        situation_ctx=situation_ctx,
        pulled_resonance=pulled_resonance,
    )
    if not use.confirmed or cast.check_result is None:
        return MovementUse(went_off=False, strength=0, technique=technique)
    soulfray = use.soulfray_result.severity_added if use.soulfray_result is not None else 0
    return MovementUse(
        went_off=True,
        strength=cast.strength,
        technique=technique,
        roll=cast.check_result,
        anima_paid=use.anima_cost.effective_cost,
        soulfray_added=soulfray,
    )

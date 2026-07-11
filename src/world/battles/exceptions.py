"""Exception hierarchy for the battles system."""

from __future__ import annotations


class BattleError(Exception):
    """Base exception for all battle-system errors.

    Attributes:
        user_message: A human-readable message safe to surface to players.
    """

    def __init__(self, user_message: str = "") -> None:
        super().__init__(user_message)
        self.user_message = user_message


class BattleConcludedError(BattleError):
    """Raised when an operation is attempted on an already-concluded battle."""

    def __init__(self, user_message: str = "This battle has already concluded.") -> None:
        super().__init__(user_message)


class RoundNotOpenError(BattleError):
    """Raised when a declaration is attempted outside a DECLARING round."""

    def __init__(self, user_message: str = "There is no open round for declarations.") -> None:
        super().__init__(user_message)


class NotAParticipantError(BattleError):
    """Raised when a character is not enlisted in the battle."""

    def __init__(self, user_message: str = "You are not a participant in this battle.") -> None:
        super().__init__(user_message)


class CharacterDoesNotKnowTechniqueError(BattleError):
    """Raised when a participant declares a technique they don't know."""

    def __init__(self, user_message: str = "You do not know that technique.") -> None:
        super().__init__(user_message)


class TechniqueNotBattleReadyError(BattleError):
    """Raised when a declared technique has no action_template (not castable)."""

    def __init__(
        self,
        user_message: str = "That technique cannot be used in battle (no action template).",
    ) -> None:
        super().__init__(user_message)


class NoCommandHierarchyError(BattleError):
    """Raised when a PLACE/SIDE-scope declaration targets a side with no covenant."""

    def __init__(self, user_message: str = "This side has no command hierarchy.") -> None:
        super().__init__(user_message)


class InsufficientCommandTierError(BattleError):
    """Raised when a participant lacks the command tier their declared scope requires."""

    def __init__(
        self,
        user_message: str = "You don't hold the command authority for that scope.",
    ) -> None:
        super().__init__(user_message)


class NotVehicleCommanderError(BattleError):
    """Raised when REPOSITION is declared by someone other than the target
    vehicle's BattleUnit.commander (#1714). Vehicle command is independent of
    covenant command_tier — a non-covenant-backed vessel must still be movable."""

    def __init__(
        self, user_message: str = "Only this vehicle's commander may reposition it."
    ) -> None:
        super().__init__(user_message)


class PlacesDoNotOverlapError(BattleError):
    """Raised when a UNIT-scope declaration targets a unit at a different,
    non-overlapping place than the declarer's own, or a BREACH targets a
    vehicle's hull Fortification from a non-overlapping place (#1714) — the
    general cross-place targeting gate that makes boarding/ship-to-ship combat
    range-gated without touching can_perceive, which is room-scoped and must
    stay that way."""

    def __init__(
        self, user_message: str = "That target is out of range — your places don't overlap."
    ) -> None:
        super().__init__(user_message)


class MissingScopeTargetError(BattleError):
    """Raised when a PLACE/SIDE-scope declaration has no matching target set."""

    def __init__(
        self, user_message: str = "That declaration needs a target for its scope."
    ) -> None:
        super().__init__(user_message)


class CannotStrikeOwnSideError(BattleError):
    """Raised when a STRIKE or ROUT declaration's target_side is the caster's own side."""

    def __init__(self, user_message: str = "You cannot target your own side.") -> None:
        super().__init__(user_message)


class NotAChampionError(BattleError):
    """Raised when a non-Champion participant attempts to open a Champion duel."""

    def __init__(self, user_message: str = "You do not hold an engaged Champion role.") -> None:
        super().__init__(user_message)


class PlaceAlreadyDuelingError(BattleError):
    """Raised when a BattlePlace already has a bound CombatEncounter."""

    def __init__(self, user_message: str = "A duel is already underway at this front.") -> None:
        super().__init__(user_message)


class PlaceScopeRequiredError(BattleError):
    """Raised when REPEL/HOLD is declared with a scope other than PLACE (#1712)."""

    def __init__(
        self, user_message: str = "That action can only be declared at a front (place scope)."
    ) -> None:
        super().__init__(user_message)


class InvalidMoveScopeError(BattleError):
    """Raised when MOVE is declared with a scope other than UNIT or PLACE (#2007)."""

    def __init__(
        self,
        user_message: str = "MOVE can only be declared for yourself or as a "
        "commander's order to one unit.",
    ) -> None:
        super().__init__(user_message)


class MoveOrderRequiresTargetUnitError(BattleError):
    """Raised when a PLACE-scope MOVE (a commander's order) has no target_unit (#2007)."""

    def __init__(
        self, user_message: str = "A commander's MOVE order needs a unit to move."
    ) -> None:
        super().__init__(user_message)


class FortificationTargetRequiredError(BattleError):
    """Raised when BREACH/FORTIFY is declared without a target_fortification (#1713)."""

    def __init__(self, user_message: str = "That action needs a target fortification.") -> None:
        super().__init__(user_message)


class FortificationOwnershipMismatchError(BattleError):
    """Raised when BREACH targets your own side's Fortification, or FORTIFY targets
    the enemy's (#1713). Mirrors CannotStrikeOwnSideError's shape."""

    def __init__(
        self,
        user_message: str = "You cannot BREACH your own side's fortification or "
        "FORTIFY the enemy's.",
    ) -> None:
        super().__init__(user_message)


class FortificationAlreadyBreachedError(BattleError):
    """Raised when BREACH/FORTIFY targets a Fortification that is already breached (#1713)."""

    def __init__(self, user_message: str = "That fortification has already been breached.") -> None:
        super().__init__(user_message)


class InvalidEnvironmentScopeError(BattleError):
    """Raised when SET_ENVIRONMENT is declared with a scope other than BATTLE or
    PLACE (#1715)."""

    def __init__(
        self,
        user_message: str = "That action can only be declared battle-wide or at a front.",
    ) -> None:
        super().__init__(user_message)


class MissingEnvironmentTargetError(BattleError):
    """Raised when SET_ENVIRONMENT's technique has no target_weather_type set (#1715)."""

    def __init__(
        self,
        user_message: str = "That technique has no weather it can conjure.",
    ) -> None:
        super().__init__(user_message)


class BattleStagingError(BattleError):
    """Raised when a GM staging operation can't safely proceed (#2010).

    Covers instantiate_battle_blueprint's guard rails: refusing to overwrite
    an already-staged battle map without ``replace=True``, refusing to replace
    once the battle has gone live (a round has opened, or a unit/participant
    is already stationed on a place), and a blueprint fortification whose
    authored ``defending_side_role`` has no matching BattleSide on the battle.
    """

    def __init__(
        self,
        user_message: str = "That battle map can't be staged the way you asked.",
    ) -> None:
        super().__init__(user_message)

"""Typed data structures for the covenants app."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.covenants.models import CovenantRole, VowAddedEffect


@dataclass(frozen=True)
class CovenantFounder:
    """A single founder participating in covenant formation.

    Covenant formation requires at least two distinct founders — see
    `feedback_covenants_are_group_only.md`. The Sequence of founders passed
    to `create_covenant` becomes the initial set of memberships.

    ``is_leader`` marks this founder as the initial top-rank holder. At most
    one founder should be flagged; if none are, ``create_covenant`` defaults
    to the first founder.
    """

    character_sheet: CharacterSheet
    role: CovenantRole
    is_leader: bool = False


@dataclass(frozen=True)
class VowEffectBonuses:
    """The thread-level bonuses one ``VowAddedEffect`` carries at one shown level (#4930).

    ``vow_effect_bonuses`` builds it; the cast (``FiredVowEffect``) and the technique
    power evaluator read the same three figures, so a preview prices what a cast adds.
    """

    severity: int
    duration: int
    damage: int


@dataclass(frozen=True)
class FiredVowEffect:
    """One ``VowAddedEffect`` that fires for a single cast, with its scaled bonuses (#4581).

    ``holder`` is the character whose vow carries the row: the caster for a
    SELF or WHOLE_GROUP row on the caster's own vow, a co-present covenant ally
    for a COVENANT_ALLIES or WHOLE_GROUP row on that ally's vow. ``is_secondary``
    is True when the row came from the holder's SECONDARY vow (#2641); its
    bonuses are then already scaled by ``SecondaryVowConfig.potency_tenths``.

    Each bonus is ``max(0, shown thread level - unlock_thread_level)`` times the
    row's matching ``*_per_thread_level`` column, read off the holder's
    COVENANT_ROLE thread on the vow's anchor role. ``severity_bonus`` and
    ``duration_bonus`` add to every applied condition; ``damage_bonus`` adds to
    every damage profile.
    """

    effect: VowAddedEffect
    holder: CharacterSheet
    is_secondary: bool
    severity_bonus: int
    duration_bonus: int
    damage_bonus: int


@dataclass(frozen=True)
class NewPicks:
    """A pick level an imbue or a joining opened, and the points it gives (#4929).

    The web draws it as "Vow level 2: **4 pts** of new picks."; telnet reads ``line``.
    """

    level: int
    points: int

    @property
    def line(self) -> str:
        unit = "pt" if self.points == 1 else "pts"
        return f"Vow level {self.level}: {self.points} {unit} of new picks."


@dataclass(frozen=True)
class VowPickEntry:
    """One focus pick as its vow holder sees it in the pick catalog (#4929).

    ``effects`` are the plain-words lines of the payload rows the pick carries and
    ``limits`` its limits in one line ("no limits" when it has none). ``locked_reason``
    is blank when the pick can be chosen now, else why not: its level is above the
    shown vow level, or it costs more than its level has left. ``vow`` names the
    catalog the pick comes from: the anchor vow, or the sub-role a holder holds or has
    grown into.
    """

    id: int
    vow: str
    name: str
    description: str
    price: int
    effects: list[str]
    limits: str
    chosen: bool
    locked_reason: str

    @property
    def choosable(self) -> bool:
        return not self.chosen and not self.locked_reason


@dataclass(frozen=True)
class VowPickLevel:
    """One pick level of a vow holder's catalog: its budget, what is spent, its picks.

    The budget is the membership's, shared by the anchor vow's and the sub-role's picks
    at this level (``validate_character_focus_pick`` sums every chosen pick at the level),
    so a level has one spend whichever catalog a pick came from. Its picks run anchor
    vow first, then the sub-role's.
    """

    level: int
    is_open: bool
    budget: int
    spent: int
    picks: list[VowPickEntry]

    @property
    def left(self) -> int:
        return max(0, self.budget - self.spent)


@dataclass(frozen=True)
class VowPickCatalog:
    """Every focus pick one primary vow offers its holder, by pick level (#4929).

    A sub-role holder's catalog holds the anchor vow's picks and the sub-role's
    together, the way ``choosable_role_ids`` lets them choose; ``vows`` names each
    catalog that offers a pick, anchor first, so the sheet and ``vow picks`` group a
    level's picks under one heading each.
    """

    membership_id: int
    covenant_id: int
    covenant: str
    vow: str
    vow_level: int
    vows: list[str]
    levels: list[VowPickLevel]

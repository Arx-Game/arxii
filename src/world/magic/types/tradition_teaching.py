"""Value types for the Tradition teaching rule (#5326)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True)
class TeachingContext:
    """What the teaching rule reads, gathered once and passed down, never stored (#5326).

    ``world.magic.services.tradition_teaching.build_teaching_context`` fills it in a fixed
    number of queries for a whole batch of characters, so a weekly run builds it once and
    asks about every allocation without another query for the Tradition rule. Hold it for
    one call chain only: it is a snapshot, and staff edits after it was built are not in it.

    - ``governed_skill_ids``: every skill a Tradition's list governs (an affinity's skill or
      a fighting style's skill). A skill outside it is taught by any Tradition.
    - ``universal_skill_ids``: the governed skills every Tradition teaches (Reflection, the
      Primal affinity's skill, found by the Primal name constant).
    - ``taught_skill_ids_by_tradition``: for each Tradition id, the governed skills it
      teaches beyond the universal ones: its ``taught_skills`` ticks, and the skill of each
      fighting style that lists it in ``taught_by``.
    - ``active_tradition_by_sheet``: the active Tradition id of each sheet the context was
      built for, ``None`` for a sheet with no active Tradition. A sheet missing from the
      mapping was not built for; asking about it raises (see ``tradition_of``).
    - ``player_by_sheet``: the account id that plays each sheet the context read players for
      (``None`` for a sheet nobody plays). Asking whether two sheets share a player raises for
      a sheet outside it (see ``played_by_one_account``).
    - ``lever_read_sheet_ids``: the sheets the context read the self-teaching lever for (one
      modifier walk each). Asking whether a sheet outside it may teach herself raises (see
      ``may_teach_herself``).
    - ``self_teaching_sheet_ids``: the sheets whose self-teaching lever is positive. Only
      the sheets in ``lever_read_sheet_ids`` can appear.
    """

    governed_skill_ids: frozenset[int]
    universal_skill_ids: frozenset[int]
    taught_skill_ids_by_tradition: Mapping[int, frozenset[int]]
    active_tradition_by_sheet: Mapping[int, int | None]
    player_by_sheet: Mapping[int, int | None]
    lever_read_sheet_ids: frozenset[int]
    self_teaching_sheet_ids: frozenset[int]

    def tradition_of(self, sheet_id: int) -> int | None:
        """The sheet's active Tradition id, or None for no active Tradition.

        Raises ``KeyError`` for a sheet the context was not built for: reading it as "no
        Tradition" would quietly refuse a character who has one. Pass every student and every
        mentor to ``build_teaching_context``.
        """
        try:
            return self.active_tradition_by_sheet[sheet_id]
        except KeyError:
            msg = (
                f"Character sheet {sheet_id} is not in this TeachingContext. Pass every "
                "student and mentor sheet id to build_teaching_context."
            )
            raise KeyError(msg) from None

    def played_by_one_account(self, first_sheet_id: int, second_sheet_id: int) -> bool:
        """Whether one account plays both sheets now (a sheet nobody plays shares none).

        Raises ``KeyError`` for a sheet whose player was not read into the context. Name every
        student and mentor in ``player_sheet_ids`` of ``build_teaching_context``.
        """
        try:
            first = self.player_by_sheet[first_sheet_id]
            second = self.player_by_sheet[second_sheet_id]
        except KeyError as missing:
            msg = (
                f"The player of character sheet {missing.args[0]} was not read into this "
                "TeachingContext. Pass the sheet id in player_sheet_ids to "
                "build_teaching_context."
            )
            raise KeyError(msg) from None
        return first is not None and first == second

    def may_teach_herself(self, sheet_id: int) -> bool:
        """Whether the sheet's self-teaching lever is positive.

        Raises ``KeyError`` for a sheet whose lever was not read into the context: reading it
        as "no lever" would quietly refuse a prodigy. Name every student who may train with
        no mentor in ``lever_sheet_ids`` of ``build_teaching_context``.
        """
        if sheet_id not in self.lever_read_sheet_ids:
            msg = (
                f"The self-teaching lever of character sheet {sheet_id} was not read into this "
                "TeachingContext. Pass the sheet id in lever_sheet_ids to "
                "build_teaching_context."
            )
            raise KeyError(msg)
        return sheet_id in self.self_teaching_sheet_ids

    def teaches(self, tradition_id: int | None, skill_id: int) -> bool:
        """Whether the Tradition teaches the skill; a skill no list governs, any Tradition does.

        ``None`` (no Tradition) teaches only the skills no list governs. The Tradition's state
        (self-taught, teachers gone, living) is never read.
        """
        if skill_id not in self.governed_skill_ids:
            return True
        if tradition_id is None:
            return False
        if skill_id in self.universal_skill_ids:
            return True
        return skill_id in self.taught_skill_ids_by_tradition.get(tradition_id, frozenset())


@dataclass(frozen=True)
class TrainingVerdict:
    """The answer to "may this character train this skill with this mentor".

    ``refusal`` is the full line the player reads (it names the next step), or ``None`` when
    the training is allowed. A caller that refuses raises or sends ``refusal`` as it stands.
    """

    refusal: str | None = None

    @property
    def allowed(self) -> bool:
        """True when nothing refuses the training."""
        return self.refusal is None


class MentorShortfall(StrEnum):
    """Why a character cannot teach a Magic skill (#5326).

    Three facts about the mentor, read by the weekly verdict (which hides which one it is
    behind one line, so a named persona reveals nothing) and by the mentor's own answer to a
    request, which names the one that applies because the facts are hers.
    """

    NO_TRADITION = "no_tradition"
    DOES_NOT_TEACH = "does_not_teach"
    NO_RATING = "no_rating"

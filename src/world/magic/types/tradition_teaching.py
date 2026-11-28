"""Value types for the Tradition teaching rule (#5326)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


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
    - ``self_teaching_sheet_ids``: the sheets whose self-teaching lever is positive. Only
      the sheets the context was told to read the lever for can appear.
    """

    governed_skill_ids: frozenset[int]
    universal_skill_ids: frozenset[int]
    taught_skill_ids_by_tradition: Mapping[int, frozenset[int]]
    active_tradition_by_sheet: Mapping[int, int | None]
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

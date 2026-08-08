"""Discovery ceremony for combos — fired the first time a party triggers a combo in combat.

Writes ``ComboLearning`` rows for each participant, fires the achievement
ceremony (gamewide first-ever + personal thereafter), and grants a flat
resonance reward via ``grant_resonance``.

Modeled on ``fire_variant_discoveries`` (the specialization engine's
discovery ceremony) but for combat combos rather than thread crossings.

**Achievement grant is a single group call, never a per-sheet loop (#3063).**
``world.magic.crossing.ceremony.execute_ceremony_beat`` is the shared
single-sheet ceremony beat (grant + optional codex unlock + announce) used
everywhere else in the codebase — every other caller fires one ``Thread``
owned by one character, so "one sheet per beat" is the right shape there.
Combo discovery is the one ceremony trigger that is inherently a *group*
event (every combo contributor discovers it simultaneously), so it does NOT
route through ``execute_ceremony_beat``: looping that per-sheet helper once
per participant called ``grant_achievement(achievement, [sheet])`` once per
sheet, and the FIRST call claimed the sole ``Discovery`` row before the
others ever ran — co-discoverers got a ``CharacterAchievement`` but never
landed in ``Discovery.shared_with_tenures``. Instead this module calls
``grant_achievement`` and ``announce_achievement`` directly, once each, for
the whole eligible participant group. ``execute_ceremony_beat``'s
``codex_entry`` param is unused here (combos don't unlock codex entries), so
skipping it costs nothing.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from world.combat.constants import COMBO_DISCOVERY_GRANT, ComboLearningMethod
from world.magic.constants import GainSource

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.combat.models import ComboDefinition
    from world.magic.models import Resonance
    from world.scenes.models import Scene

logger = logging.getLogger(__name__)


def fire_combo_discovery(
    *,
    combo: ComboDefinition,
    participant_sheets: list[CharacterSheet],
    scene: Scene | None = None,  # noqa: ARG001  # reserved for future scene-scoped narration
) -> None:
    """Fire the discovery ceremony for a combo first triggered in combat.

    1. Writes ``ComboLearning(combo=combo, learned_via=COMBAT)`` for each
       participant (idempotent via ``get_or_create``).
    2. If ``combo.discovery_achievement`` is set and ceremony copy is authored,
       grants the achievement to the whole group in ONE ``grant_achievement``
       call and announces once (gamewide on first-ever, personal otherwise —
       see the module docstring for why this is not a per-participant loop).
    3. Calls ``grant_resonance`` for each participant using the first slot's
       ``resonance_requirement`` that has one; skips the grant if no slot
       has a resonance requirement.

    Args:
        combo: The discovered ``ComboDefinition``.
        participant_sheets: The character sheets of all combo contributors.
        scene: The scene the discovery happened in (reserved for future use).
    """
    from world.combat.models import ComboLearning  # noqa: PLC0415

    # Step 1: Write ComboLearning for each participant.
    for sheet in participant_sheets:
        ComboLearning.objects.get_or_create(
            combo=combo,
            character_sheet=sheet,
            defaults={"learned_via": ComboLearningMethod.COMBAT},
        )

    # Step 2: Fire the achievement ceremony if configured -- ONE grant for the
    # whole group (see the module docstring for why this doesn't route
    # through execute_ceremony_beat's per-sheet loop, #3063).
    achievement = combo.discovery_achievement
    has_ceremony_copy = bool(combo.discovery_first_body or combo.discovery_personal_body)
    if achievement is not None and has_ceremony_copy:
        from world.achievements.discovery import announce_achievement  # noqa: PLC0415
        from world.achievements.models import CharacterAchievement  # noqa: PLC0415
        from world.achievements.services import grant_achievement  # noqa: PLC0415
        from world.narrative.constants import NarrativeCategory  # noqa: PLC0415

        # Idempotency gate mirrors execute_ceremony_beat's per-sheet re-fire
        # guard: a participant who already earned this achievement (a stale
        # replay of an already-fired combo) sits out the ceremony entirely.
        already_earned_ids = set(
            CharacterAchievement.objects.filter(
                character_sheet__in=participant_sheets, achievement=achievement
            ).values_list("character_sheet_id", flat=True)
        )
        unearned_sheets = [s for s in participant_sheets if s.pk not in already_earned_ids]
        if unearned_sheets:
            result = grant_achievement(achievement, unearned_sheets)
            is_first = result.created_discovery is not None
            announce_achievement(
                unearned_sheets,
                is_first=is_first,
                first_body=combo.discovery_first_body,
                personal_body=combo.discovery_personal_body,
                category=NarrativeCategory.ABILITY,
            )

    # Step 3: Grant resonance to each participant.
    resonance = _combo_resonance(combo)
    if resonance is not None:
        from world.magic.services.resonance import grant_resonance  # noqa: PLC0415

        for sheet in participant_sheets:
            try:
                grant_resonance(
                    sheet,
                    resonance,
                    COMBO_DISCOVERY_GRANT,
                    source=GainSource.COMBO_DISCOVERY,
                )
            except ValueError:
                # Resonance grant failure (e.g. invalid amount) should not
                # break round resolution. The ComboLearning + ceremony are
                # the primary reward; the resonance grant is secondary.
                logger.exception(
                    "Failed to grant combo discovery resonance to sheet %s",
                    sheet.pk,
                )


def _combo_resonance(combo: ComboDefinition) -> Resonance | None:
    """Return the first slot's resonance_requirement that has one, or None.

    Scans the combo's slots in slot_number order. If no slot has a
    resonance_requirement, returns None (the resonance grant is skipped).
    """
    from world.combat.models import ComboSlot  # noqa: PLC0415

    slots = ComboSlot.objects.filter(combo=combo).order_by("slot_number")
    for slot in slots:
        if slot.resonance_requirement_id is not None:
            return slot.resonance_requirement
    return None

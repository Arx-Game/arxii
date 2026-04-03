"""Service module for querying available social actions with technique enhancements."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from actions.models import ActionEnhancement, ActionTemplate
from world.magic.models import CharacterAnima, CharacterTechnique
from world.magic.services import (
    calculate_effective_anima_cost,
    get_runtime_technique_stats,
    get_soulfray_warning,
)
from world.magic.types import SoulfrayWarning

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.magic.models import Technique


@dataclass
class AvailableEnhancement:
    """A technique enhancement option for a social action."""

    enhancement: ActionEnhancement
    technique: Technique
    effective_cost: int
    soulfray_warning: SoulfrayWarning | None = None


@dataclass
class AvailableSceneAction:
    """A social action with its available technique enhancements."""

    action_key: str
    action_template: ActionTemplate
    enhancements: list[AvailableEnhancement] = field(default_factory=list)


def get_available_scene_actions(
    *,
    character: ObjectDB,
) -> list[AvailableSceneAction]:
    """Return available social actions with technique enhancement options.

    Batches queries: known techniques fetched once, runtime stats cached per
    technique, Soulfray warning fetched once.
    """
    templates = list(ActionTemplate.objects.filter(category="social"))

    known_technique_ids = set(
        CharacterTechnique.objects.filter(
            character_id=character.pk,
        ).values_list("technique_id", flat=True)
    )

    all_enhancements = list(
        ActionEnhancement.objects.filter(
            source_type="technique",
            technique_id__in=known_technique_ids,
        ).select_related("technique")
    )

    enhancements_by_action: dict[str, list[ActionEnhancement]] = {}
    for enh in all_enhancements:
        enhancements_by_action.setdefault(enh.base_action_key, []).append(enh)

    soulfray_warning = _get_soulfray_warning_if_magical(character, known_technique_ids)
    anima = _get_character_anima(character)
    stats_cache: dict[int, tuple[int, int]] = {}

    actions: list[AvailableSceneAction] = []
    for template in templates:
        action_key = template.name.lower()
        enhancements = enhancements_by_action.get(action_key, [])

        available_enhancements: list[AvailableEnhancement] = []
        for enh in enhancements:
            technique = enh.technique
            if technique.pk not in stats_cache:
                stats = get_runtime_technique_stats(technique, character)
                stats_cache[technique.pk] = (stats.intensity, stats.control)

            intensity, control = stats_cache[technique.pk]
            if anima is not None:
                cost = calculate_effective_anima_cost(
                    base_cost=technique.anima_cost,
                    runtime_intensity=intensity,
                    runtime_control=control,
                    current_anima=anima.current,
                )
                effective_cost = cost.effective_cost
            else:
                effective_cost = 0

            warning = soulfray_warning if effective_cost > 0 else None

            available_enhancements.append(
                AvailableEnhancement(
                    enhancement=enh,
                    technique=technique,
                    effective_cost=effective_cost,
                    soulfray_warning=warning,
                )
            )

        actions.append(
            AvailableSceneAction(
                action_key=action_key,
                action_template=template,
                enhancements=available_enhancements,
            )
        )

    return actions


def _get_soulfray_warning_if_magical(
    character: ObjectDB,
    known_technique_ids: set[int],
) -> SoulfrayWarning | None:
    if not known_technique_ids:
        return None
    return get_soulfray_warning(character)


def _get_character_anima(character: ObjectDB) -> CharacterAnima | None:
    try:
        return CharacterAnima.objects.get(character=character)
    except CharacterAnima.DoesNotExist:
        return None

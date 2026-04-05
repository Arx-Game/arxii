"""SocialContent — consequence pools wired to social action templates.

Creates a fully playable social action suite:
  - 6 ActionTemplates with CheckTypes and trait weights
  - 6 named social conditions (Shaken, Charmed, …)
  - ConsequencePools for each template (one Consequence per outcome tier)
  - ConsequenceEffects applying conditions to EffectTarget.TARGET on success
  - Check resolution lookup tables (PointConversionRange, CheckRank, charts)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from actions.models.action_templates import ActionTemplate
    from world.checks.models import CheckType
    from world.conditions.models import ConditionTemplate
    from world.traits.models import CheckOutcome

# Maps action_key (lowercase template name) → social condition name.
ACTION_CONDITION_MAP: dict[str, str] = {
    "intimidate": "Shaken",
    "persuade": "Charmed",
    "deceive": "Deceived",
    "flirt": "Smitten",
    "perform": "Captivated",
    "entrance": "Enthralled",
}


@dataclass
class SocialContentResult:
    """Returned by SocialContent.create_all()."""

    templates: dict[str, ActionTemplate]  # action_key → template
    check_types: dict[str, CheckType]  # check_type_name → CheckType
    conditions: dict[str, ConditionTemplate]  # condition_name → template
    outcomes: dict[str, CheckOutcome]  # "success" / "failure" / "partial" / "critical"


class SocialContent:
    """Creates the complete social action content suite for integration tests."""

    @staticmethod
    def create_all() -> SocialContentResult:
        """Build all social action content: check types, templates, conditions, pools.

        Safe to call from setUpTestData across multiple test classes — each class
        runs in an isolated transaction that is rolled back at class teardown.

        Returns:
            SocialContentResult with templates, check_types, conditions, and outcomes.
        """
        from actions.factories import (  # noqa: PLC0415
            ConsequencePoolEntryFactory,
            ConsequencePoolFactory,
        )
        from actions.models import ActionTemplate  # noqa: PLC0415
        from integration_tests.game_content.checks import CheckContent  # noqa: PLC0415
        from integration_tests.game_content.conditions import ConditionContent  # noqa: PLC0415
        from world.checks.constants import EffectTarget, EffectType  # noqa: PLC0415
        from world.checks.factories import (  # noqa: PLC0415
            ConsequenceFactory,
            create_social_action_templates,
        )
        from world.checks.models import ConsequenceEffect  # noqa: PLC0415
        from world.traits.factories import (  # noqa: PLC0415
            CheckRankFactory,
            CheckSystemSetupFactory,
            PointConversionRangeFactory,
        )
        from world.traits.models import ResultChart, TraitType  # noqa: PLC0415

        # --- Check resolution lookup tables ---
        PointConversionRangeFactory(
            trait_type=TraitType.STAT,
            min_value=1,
            max_value=100,
            points_per_level=1,
        )
        CheckRankFactory(rank=0, min_points=0, name="Untrained")
        CheckRankFactory(rank=1, min_points=30, name="Novice")
        CheckRankFactory(rank=2, min_points=60, name="Competent")

        check_system = CheckSystemSetupFactory.create()
        ResultChart.clear_cache()

        outcomes = check_system["outcomes"]

        # --- Action templates (includes check types + trait weights) ---
        action_templates = create_social_action_templates()
        templates_by_key: dict[str, ActionTemplate] = {t.name.lower(): t for t in action_templates}

        # --- Check types (for result access) ---
        check_types = CheckContent.create_check_types()

        # --- Social conditions ---
        conditions = ConditionContent.create_all()

        # --- Consequence pools: one pool per action template ---
        outcome_keys = ["failure", "partial", "success", "critical"]
        success_tiers = {"success", "critical"}

        for action_key, template in templates_by_key.items():
            condition_name = ACTION_CONDITION_MAP[action_key]
            condition_template = conditions[condition_name]

            pool = ConsequencePoolFactory(name=f"{template.name} Pool")

            for outcome_key in outcome_keys:
                outcome = outcomes[outcome_key]
                consequence = ConsequenceFactory(
                    outcome_tier=outcome,
                    label=f"{template.name} {outcome_key.title()}",
                    weight=1,
                    character_loss=False,
                )
                if outcome_key in success_tiers:
                    ConsequenceEffect.objects.create(
                        consequence=consequence,
                        effect_type=EffectType.APPLY_CONDITION,
                        target=EffectTarget.TARGET,
                        condition_template=condition_template,
                        condition_severity=1,
                        execution_order=0,
                    )

                ConsequencePoolEntryFactory(pool=pool, consequence=consequence)

            # Wire the pool to the template
            ActionTemplate.objects.filter(pk=template.pk).update(consequence_pool=pool)
            template.consequence_pool = pool

        return SocialContentResult(
            templates=templates_by_key,
            check_types=check_types,
            conditions=conditions,
            outcomes=outcomes,
        )

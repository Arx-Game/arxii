"""Tests for the summon effect bundle + active CONDITION_APPLIED wiring (#1584, Task 14a).

SQLite-safe: neither angle calls ``apply_condition`` / ``bulk_apply_conditions``
(PG-only DISTINCT ON). Angle (a) inspects the seeded rows directly; angle (b)
exercises the ``summon_ally_on_condition`` adapter against a payload-shaped stub.
The full cast -> CONDITION_APPLIED -> trigger -> summon path is the Task 15 PG E2E.
"""

from types import SimpleNamespace

from django.test import TestCase

from flows.constants import EventName
from flows.consts import FlowActionChoices
from flows.models.flows import FlowStepDefinition
from world.combat.constants import CombatAllegiance, ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.models import CombatOpponent, ThreatPool
from world.conditions.constants import SUMMONING_CONDITION_NAME
from world.conditions.models import ConditionTemplate
from world.magic.effect_palette_content import (
    SUMMON_POOL_NAME,
    SUMMON_TECHNIQUE_NAME,
    ensure_summon_content,
)
from world.magic.models.techniques import (
    ConditionTargetKind,
    Technique,
    TechniqueAppliedCondition,
)
from world.magic.services.effect_handlers import summon_ally_on_condition


class EnsureSummonContentSeedTests(TestCase):
    """ensure_summon_content() seeds the bundle correctly and is idempotent."""

    def test_seed_correctness_and_idempotency(self) -> None:
        """Two calls leave exactly one of each row with the trigger wired on CONDITION_APPLIED."""
        ensure_summon_content()
        ensure_summon_content()  # idempotent: second call creates no duplicates

        # 1. Exactly one Summon Spirit technique.
        techniques = Technique.objects.filter(name=SUMMON_TECHNIQUE_NAME)
        self.assertEqual(techniques.count(), 1)
        technique = techniques.get()

        # 2. Exactly one Summoning condition template, with the trigger wired.
        templates = ConditionTemplate.objects.filter(name=SUMMONING_CONDITION_NAME)
        self.assertEqual(templates.count(), 1)
        template = templates.get()

        triggers = list(template.reactive_triggers.all())
        self.assertEqual(len(triggers), 1)
        trigger = triggers[0]
        self.assertEqual(trigger.event_name, EventName.CONDITION_APPLIED)
        self.assertEqual(
            trigger.base_filter_condition,
            {"path": "target", "op": "==", "value": "self"},
        )

        # 3. Exactly one ThreatPool with at least one entry carrying base_damage.
        pools = ThreatPool.objects.filter(name=SUMMON_POOL_NAME)
        self.assertEqual(pools.count(), 1)
        pool = pools.get()
        entries = list(pool.entries.all())
        self.assertEqual(len(entries), 1)
        self.assertGreater(entries[0].base_damage, 0)

        # 4. The flow's CALL_SERVICE_FUNCTION step carries the ThreatPool pk statically.
        steps = FlowStepDefinition.objects.filter(
            flow=trigger.flow_definition,
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
        )
        self.assertEqual(steps.count(), 1)
        step = steps.get()
        self.assertEqual(
            step.variable_name,
            "world.magic.services.effect_handlers.summon_ally_on_condition",
        )
        self.assertEqual(step.parameters["payload"], "@payload")
        self.assertEqual(step.parameters["threat_pool_name"], pool.name)

        # 5. The technique applies the Summoning condition to SELF.
        applied = TechniqueAppliedCondition.objects.filter(
            technique=technique,
            condition=template,
        )
        self.assertEqual(applied.count(), 1)
        self.assertEqual(applied.get().target_kind, ConditionTargetKind.SELF)


class SummonAllyOnConditionAdapterTests(TestCase):
    """summon_ally_on_condition bridges a CONDITION_APPLIED payload to summon_ally."""

    def test_adapter_creates_ally_opponent(self) -> None:
        """payload.target (the caster) -> an ALLY CombatOpponent in the encounter."""
        ensure_summon_content()
        pool = ThreatPool.objects.get(name=SUMMON_POOL_NAME)

        encounter = CombatEncounterFactory()
        CombatOpponentFactory(encounter=encounter)  # an existing ENEMY
        participant = CombatParticipantFactory(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
        )
        caster_objectdb = participant.character_sheet.character

        # ConditionAppliedPayload-shaped stub (SELF condition: target == caster).
        stub = SimpleNamespace(target=caster_objectdb, instance=None, stage=None)

        before = CombatOpponent.objects.filter(encounter=encounter).count()
        summon_ally_on_condition(payload=stub, threat_pool_name=pool.name, bond_rounds=5)
        after = CombatOpponent.objects.filter(encounter=encounter).count()

        self.assertEqual(after, before + 1)
        summon = CombatOpponent.objects.get(encounter=encounter, allegiance=CombatAllegiance.ALLY)
        self.assertEqual(summon.summoned_by, participant.character_sheet)
        self.assertEqual(summon.threat_pool_id, pool.pk)
        self.assertEqual(summon.bond_expires_round, encounter.round_number + 5)

"""Tests for the Sleeping condition (#2290)."""

from django.test import TestCase

from world.character_sheets.services import create_character_with_sheet
from world.conditions.models import ConditionTemplate
from world.conditions.services import apply_condition, get_condition_instance, has_condition
from world.vitals.constants import SLEEPING_CONDITION_NAME
from world.vitals.seeds import ensure_foundational_capabilities, ensure_sleeping_condition


class SleepingConditionTests(TestCase):
    """Tests for the Sleeping ConditionTemplate and its capability-zeroing effects."""

    def setUp(self):
        ensure_foundational_capabilities()
        ensure_sleeping_condition()
        self.char, self.sheet, _ = create_character_with_sheet(
            character_key="Sleeper",
            primary_persona_name="Sleeper",
        )
        self.template = ConditionTemplate.objects.get(name=SLEEPING_CONDITION_NAME)

    def test_condition_template_exists(self):
        template = ConditionTemplate.objects.get(name=SLEEPING_CONDITION_NAME)
        assert template is not None
        assert template.category.name == "Incapacitation"

    def test_apply_sleeping_zeros_capabilities(self):
        from world.conditions.constants import FoundationalCapability
        from world.conditions.models import CapabilityType
        from world.conditions.services import get_capability_value

        apply_condition(target=self.char, condition=self.template)
        assert has_condition(self.char, self.template)

        awareness_cap = CapabilityType.objects.get(name=FoundationalCapability.AWARENESS)
        awareness = get_capability_value(self.sheet, awareness_cap)
        assert awareness <= 0

    def test_sleeping_has_no_expiration(self):
        """Sleeping condition has no guaranteed-wake deadline (unlike Unconscious)."""
        apply_condition(target=self.char, condition=self.template)
        instance = get_condition_instance(self.char, self.template)
        assert instance is not None
        # Sleeping should not have an expires_at set at application time
        # (the engagement gate stamps it later if dream-engaged)
        assert instance.expires_at is None

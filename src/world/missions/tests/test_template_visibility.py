"""template_visible_to — the unified visibility/eligibility gate (#870).

The spec matrix: OPEN → anyone (rule not consulted); RESTRICTED + passing
rule → eligible; RESTRICTED + failing rule → not eligible; staff bypass
both modes; RESTRICTED + empty rule + non-staff → not eligible (the
emergent staff-only state). Plus the trigger-path staff-bypass regression
(pre-#870 the trigger path ignored the audience gate entirely; #686 NPC-
offer-path consistency is covered in test_686_unified_offer_gates).
"""

from django.test import TestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.missions.constants import GiverKind, MissionVisibility
from world.missions.factories import (
    MissionGiverFactory,
    MissionNodeFactory,
    MissionTemplateFactory,
)
from world.missions.services.trigger_dispatch import maybe_dispatch_on_enter
from world.missions.services.visibility import template_visible_to

# Deterministic always-false LEAFY predicate (fresh sheets are level 0) —
# exercises the evaluate path, unlike a leafless tree which the
# no-actual-gates guard short-circuits.
_ALWAYS_FALSE = {"leaf": "min_character_level", "params": {"level": 99}}
# Deterministic always-true predicate against a fresh level-0 sheet.
_LEVEL_ZERO_OK = {"leaf": "min_character_level", "params": {"level": 0}}


def _pc(*, staff: bool = False):
    character = CharacterFactory()
    CharacterSheetFactory(character=character)
    if staff:
        character.db_account = AccountFactory(is_staff=True)
        character.save(update_fields=["db_account"])
    return character


class TemplateVisibleToTests(TestCase):
    def test_open_visible_to_anyone(self) -> None:
        template = MissionTemplateFactory(visibility=MissionVisibility.OPEN)
        self.assertTrue(template_visible_to(template, _pc()))

    def test_open_does_not_consult_the_rule(self) -> None:
        # A stale always-false rule left on the row must not hide OPEN.
        template = MissionTemplateFactory(
            visibility=MissionVisibility.OPEN, availability_rule=_ALWAYS_FALSE
        )
        self.assertTrue(template_visible_to(template, _pc()))

    def test_restricted_passing_rule_is_eligible(self) -> None:
        template = MissionTemplateFactory(
            visibility=MissionVisibility.RESTRICTED, availability_rule=_LEVEL_ZERO_OK
        )
        self.assertTrue(template_visible_to(template, _pc()))

    def test_restricted_failing_rule_is_not_eligible(self) -> None:
        template = MissionTemplateFactory(
            visibility=MissionVisibility.RESTRICTED, availability_rule=_ALWAYS_FALSE
        )
        self.assertFalse(template_visible_to(template, _pc()))

    def test_restricted_empty_rule_is_emergent_staff_only(self) -> None:
        # No gates authored = no PC admitted (NOT vacuously-true like the
        # raw evaluator) — the safe default for new/in-testing templates.
        template = MissionTemplateFactory(visibility=MissionVisibility.RESTRICTED)
        self.assertFalse(template_visible_to(template, _pc()))

    def test_restricted_leafless_group_is_emergent_staff_only(self) -> None:
        # Adversarial-review regression: the FE builder produces
        # {"op": "AND", "of": []} in one click, and evaluate() treats an
        # empty AND as vacuously True. A leafless tree must read as "no
        # gates authored" (staff-only), not as open-to-everyone.
        for leafless in (
            {"op": "AND", "of": []},
            {"op": "AND", "of": [{"op": "AND", "of": []}]},
            {"op": "NOT", "of": [{}]},
        ):
            template = MissionTemplateFactory(
                name=f"leafless-{leafless!r}",
                visibility=MissionVisibility.RESTRICTED,
                availability_rule=leafless,
            )
            self.assertFalse(template_visible_to(template, _pc()), leafless)

    def test_staff_bypass_restricted_failing_rule(self) -> None:
        template = MissionTemplateFactory(
            visibility=MissionVisibility.RESTRICTED, availability_rule=_ALWAYS_FALSE
        )
        self.assertTrue(template_visible_to(template, _pc(staff=True)))

    def test_staff_bypass_restricted_empty_rule(self) -> None:
        template = MissionTemplateFactory(visibility=MissionVisibility.RESTRICTED)
        self.assertTrue(template_visible_to(template, _pc(staff=True)))


class TriggerDispatchVisibilityTests(TestCase):
    """The trigger path honors visibility + staff bypass (pre-#870 it didn't)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        cls.template = MissionTemplateFactory(
            name="restricted-trigger-mission",
            visibility=MissionVisibility.RESTRICTED,
        )
        MissionNodeFactory(template=cls.template, key="entry", is_entry=True)
        giver = MissionGiverFactory(
            name="restricted-notice-board",
            giver_kind=GiverKind.ROOM_TRIGGER,
            target=cls.room,
        )
        giver.templates.add(cls.template)

    def test_non_staff_not_dispatched_restricted_template(self) -> None:
        self.assertIsNone(maybe_dispatch_on_enter(_pc(), self.room))

    def test_staff_bypass_dispatches_restricted_template(self) -> None:
        instance = maybe_dispatch_on_enter(_pc(staff=True), self.room)
        self.assertIsNotNone(instance)
        self.assertEqual(instance.template_id, self.template.pk)

    def test_restricted_passing_rule_dispatches_non_staff(self) -> None:
        self.template.availability_rule = _LEVEL_ZERO_OK
        self.template.save(update_fields=["availability_rule"])
        instance = maybe_dispatch_on_enter(_pc(), self.room)
        self.assertIsNotNone(instance)

    def test_persona_gated_rule_fires_for_presented_persona(self) -> None:
        # Mission givers gate on the presented persona (#870): the trigger
        # path resolves the character's PRIMARY persona (the npc-offer
        # path's convention) so persona-keyed leaves actually fire. A
        # member's persona passes; a non-member's fails closed.
        from world.societies.factories import (
            OrganizationFactory,
            OrganizationMembershipFactory,
        )

        OrganizationFactory(name="Trigger Guild")
        self.template.availability_rule = {
            "leaf": "is_member_of_org",
            "params": {"org": "Trigger Guild"},
        }
        self.template.save(update_fields=["availability_rule"])

        outsider = _pc()
        self.assertIsNone(maybe_dispatch_on_enter(outsider, self.room))

        member = _pc()
        OrganizationMembershipFactory(
            persona=member.sheet_data.primary_persona,
            organization__name="Trigger Guild",
        )
        instance = maybe_dispatch_on_enter(member, self.room)
        self.assertIsNotNone(instance)
        self.assertEqual(instance.template_id, self.template.pk)

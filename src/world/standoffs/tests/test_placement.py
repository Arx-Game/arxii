"""Placement edits, the spawn snapshot and inherited faction rules (#4361)."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import CauseKind, OpponentTier
from world.combat.encounter_prep import spawn_opponent_lines
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    CreatureTemplateFactory,
    seed_scaling_defaults,
)
from world.mechanics.factories import PropertyFactory
from world.mechanics.models import ObjectProperty
from world.missions.factories import MissionOptionOpponentLineFactory
from world.societies.factories import (
    OrganizationFactory,
    OrganizationMembershipFactory,
    SocietyFactory,
)
from world.standoffs.constants import DriveStrength, RevealKind
from world.standoffs.factories import CreatureDriveFactory, FactionRuleFactory
from world.standoffs.models import OpponentLineDrive, OpponentLineFactionRuleSuppression
from world.standoffs.services.faction_rules import band_shift_toward, faction_rule_matches
from world.standoffs.services.placement import (
    DriveEdit,
    DriveEditState,
    PlacementDraft,
    draft_from_line,
    placement_profile,
    save_placement,
)
from world.standoffs.services.profile import (
    group_cause,
    group_drives,
    group_rules,
    inherited_rules,
)
from world.standoffs.services.state import open_standoff
from world.standoffs.services.verbs import hidden_things
from world.stories.factories import BeatOpponentLineFactory


class _Inheritance(TestCase):
    """A template affiliated with a company, below a parent, inside a society."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.society = SocietyFactory(name="PLACEHOLDER Riverland")
        cls.parent = OrganizationFactory(name="PLACEHOLDER Guilds", society=cls.society)
        cls.company = OrganizationFactory(
            name="PLACEHOLDER Company", parent_org=cls.parent, society=cls.society
        )
        cls.template = CreatureTemplateFactory(
            tier=OpponentTier.MOOK,
            cause=CauseKind.ORDERS,
            cause_margin_percent=10,
            organization=cls.company,
        )
        cls.greedy = PropertyFactory(name="PLACEHOLDER Greedy")
        cls.loyal = PropertyFactory(name="PLACEHOLDER Loyal")
        cls.fearful = PropertyFactory(name="PLACEHOLDER Fearful")
        CreatureDriveFactory(
            creature_template=cls.template, property=cls.greedy, strength=DriveStrength.MAJOR
        )
        CreatureDriveFactory(
            creature_template=cls.template, property=cls.loyal, strength=DriveStrength.MINOR
        )
        CreatureDriveFactory(
            creature_template=cls.template, property=cls.fearful, strength=DriveStrength.MINOR
        )
        cls.template_rule = FactionRuleFactory(creature_template=cls.template, rule={})
        cls.company_rule = FactionRuleFactory(
            creature_template=None, organization=cls.company, rule={}
        )
        cls.parent_rule = FactionRuleFactory(
            creature_template=None, organization=cls.parent, rule={}
        )
        cls.society_rule = FactionRuleFactory(creature_template=None, society=cls.society, rule={})


class InheritanceTests(_Inheritance):
    def test_rules_come_most_specific_first_with_their_source(self) -> None:
        rules = inherited_rules(self.template, self.company)
        self.assertEqual(
            [(e.rule, e.level, e.source) for e in rules],
            [
                (self.template_rule, 0, self.template.name),
                (self.company_rule, 1, self.company.name),
                (self.parent_rule, 2, self.parent.name),
                (self.society_rule, 3, self.society.name),
            ],
        )

    def test_a_suppressed_rule_is_left_out(self) -> None:
        rules = inherited_rules(self.template, self.company, [self.parent_rule.pk])
        self.assertNotIn(self.parent_rule, [e.rule for e in rules])

    def test_no_affiliation_carries_the_template_rules_only(self) -> None:
        self.assertEqual(
            [e.rule for e in inherited_rules(self.template, None)], [self.template_rule]
        )

    def test_a_rule_has_exactly_one_owner(self) -> None:
        rule = FactionRuleFactory.build(
            creature_template=self.template, organization=self.company, rule={}
        )
        with self.assertRaises(ValidationError):
            rule.clean()


class SpawnSnapshotTests(_Inheritance):
    def setUp(self) -> None:
        seed_scaling_defaults()
        self.encounter = CombatEncounterFactory()

    def _spawn(self, line) -> None:
        outcomes = spawn_opponent_lines(self.encounter, [line])
        self.assertTrue(all(o["success"] for o in outcomes), outcomes)

    def test_a_plain_line_stamps_the_template_profile(self) -> None:
        line = BeatOpponentLineFactory(creature_template=self.template, count=2)
        self._spawn(line)
        group = open_standoff(self.encounter)[0]
        self.assertEqual(group_cause(group), (CauseKind.ORDERS, 10))
        self.assertEqual(
            {(d.property_id, d.strength) for d in group_drives(group)},
            {
                (self.greedy.pk, DriveStrength.MAJOR),
                (self.loyal.pk, DriveStrength.MINOR),
                (self.fearful.pk, DriveStrength.MINOR),
            },
        )
        self.assertEqual(len(group_rules(group)), 4)

    def test_line_edits_are_stamped_and_the_template_is_not_read_again(self) -> None:
        other = OrganizationFactory(name="PLACEHOLDER Other", society=SocietyFactory())
        line = BeatOpponentLineFactory(creature_template=self.template, count=1)
        added = PropertyFactory(name="PLACEHOLDER Prudent")
        save_placement(
            line,
            cause_override=CauseKind.PREDATION,
            cause_margin_override=25,
            organization=None,
            drive_edits=[
                DriveEdit(self.greedy, DriveStrength.DEFINING),
                DriveEdit(self.fearful, None),
                DriveEdit(added, DriveStrength.MINOR),
            ],
            suppressed_rule_ids=[self.society_rule.pk],
        )
        self._spawn(line)
        group = open_standoff(self.encounter)[0]
        # The template changes after the spawn; the encounter keeps its snapshot.
        self.template.cause = CauseKind.NONE
        self.template.organization = other
        self.template.save(update_fields=["cause", "organization"])
        self.assertEqual(group_cause(group), (CauseKind.PREDATION, 25))
        self.assertEqual(
            {(d.property_id, d.strength) for d in group_drives(group)},
            {
                (self.greedy.pk, DriveStrength.DEFINING),
                (self.loyal.pk, DriveStrength.MINOR),
                (added.pk, DriveStrength.MINOR),
            },
        )
        self.assertNotIn(self.society_rule, [e.rule for e in group_rules(group)])
        opponent = self.encounter.opponents.get()
        self.assertEqual(opponent.organization, self.company)
        self.assertTrue(
            ObjectProperty.objects.filter(object_id=opponent.objectdb_id, property=added).exists()
        )

    def test_a_mission_option_line_carries_edits_too(self) -> None:
        line = MissionOptionOpponentLineFactory(creature_template=self.template)
        save_placement(
            line,
            cause_override="",
            cause_margin_override=None,
            organization=self.parent,
            drive_edits=[],
            suppressed_rule_ids=[],
        )
        self._spawn(line)
        opponent = self.encounter.opponents.get()
        self.assertEqual(opponent.organization, self.parent)
        group = open_standoff(self.encounter)[0]
        self.assertNotIn(self.company_rule, [e.rule for e in group_rules(group)])

    def test_a_drive_the_placement_added_can_be_read(self) -> None:
        line = BeatOpponentLineFactory(creature_template=self.template)
        added = PropertyFactory(name="PLACEHOLDER Added")
        save_placement(
            line,
            cause_override="",
            cause_margin_override=None,
            organization=None,
            drive_edits=[DriveEdit(added, DriveStrength.DEFINING)],
            suppressed_rule_ids=[],
        )
        self._spawn(line)
        group = open_standoff(self.encounter)[0]
        participant = CombatParticipantFactory(encounter=self.encounter)
        hidden = hidden_things(group, [participant])
        drives = [d for kind, d, _ in hidden if kind == RevealKind.DRIVE]
        self.assertEqual(drives[0].property_id, added.pk)


class SavePlacementTests(_Inheritance):
    def test_an_edit_matching_the_template_is_not_stored(self) -> None:
        line = BeatOpponentLineFactory(creature_template=self.template)
        save_placement(
            line,
            cause_override="",
            cause_margin_override=None,
            organization=None,
            drive_edits=[
                DriveEdit(self.greedy, DriveStrength.MAJOR),
                DriveEdit(self.loyal, None),
            ],
            suppressed_rule_ids=[self.company_rule.pk],
        )
        self.assertEqual(
            list(OpponentLineDrive.objects.values_list("property_id", "strength")),
            [(self.loyal.pk, None)],
        )
        self.assertEqual(
            list(OpponentLineFactionRuleSuppression.objects.values_list("faction_rule", flat=True)),
            [self.company_rule.pk],
        )
        profile = placement_profile(self.template, draft_from_line(line))
        states = {d.property_id: d.state for d in profile.drives}
        self.assertEqual(states[self.loyal.pk], DriveEditState.REMOVED)
        self.assertEqual(states[self.greedy.pk], DriveEditState.SAME)
        self.assertIn("3 faction rules", profile.summary(line.count))

    def test_only_an_inherited_rule_can_be_switched_off(self) -> None:
        line = BeatOpponentLineFactory(creature_template=self.template)
        stranger = FactionRuleFactory(rule={})
        with self.assertRaises(ValidationError):
            save_placement(
                line,
                cause_override="",
                cause_margin_override=None,
                organization=None,
                drive_edits=[],
                suppressed_rule_ids=[stranger.pk],
            )

    def test_a_draft_previews_without_saving(self) -> None:
        profile = placement_profile(
            self.template,
            PlacementDraft(cause_override=CauseKind.PREDATION, organization=self.parent),
        )
        self.assertTrue(profile.cause_edited)
        self.assertTrue(profile.organization_edited)
        self.assertNotIn(self.company_rule.pk, [e.inherited.rule.pk for e in profile.rules])


class PrecedenceTests(_Inheritance):
    """Where two matched rules shift the same thing, the most specific owner wins."""

    def setUp(self) -> None:
        seed_scaling_defaults()
        self.encounter = CombatEncounterFactory()
        spawn_opponent_lines(
            self.encounter, [BeatOpponentLineFactory(creature_template=self.template)]
        )
        self.group = open_standoff(self.encounter)[0]
        self.sheet = CharacterSheetFactory(character=CharacterFactory())

    def test_the_template_rule_beats_the_organization_rule(self) -> None:
        self.template_rule.difficulty_shift_bands = 1
        self.template_rule.save(update_fields=["difficulty_shift_bands"])
        self.company_rule.difficulty_shift_bands = -2
        self.company_rule.save(update_fields=["difficulty_shift_bands"])
        self.assertEqual(band_shift_toward(self.group, self.sheet), 1)

    def test_a_society_rule_counts_when_nothing_more_specific_shifts(self) -> None:
        self.society_rule.difficulty_shift_bands = -1
        self.society_rule.save(update_fields=["difficulty_shift_bands"])
        self.assertEqual(band_shift_toward(self.group, self.sheet), -1)

    def test_an_association_rule_on_the_organization_matches_a_former_member(self) -> None:
        from datetime import timedelta

        from django.utils import timezone

        rule = FactionRuleFactory(
            creature_template=None,
            organization=self.company,
            rule={"leaf": "associated_with_org", "params": {"org": self.company.name}},
        )
        self.assertNotIn(rule, [m.rule for m in faction_rule_matches(self.group, self.sheet)])
        membership = OrganizationMembershipFactory(
            persona=self.sheet.primary_persona, organization=self.company
        )
        membership.left_at = timezone.now() - timedelta(days=60)
        membership.save(update_fields=["left_at"])
        matches = faction_rule_matches(self.group, self.sheet)
        match = next(m for m in matches if m.rule == rule)
        self.assertEqual((match.level, match.source), (1, self.company.name))

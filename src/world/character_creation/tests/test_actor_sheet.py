"""The Actor's Sheet (#3621): pricing, offers, and what finalize writes.

Three answers on the profile, numbered goals with a horizon, one priced enemy (a person
by power or a group by reach, at a degree) that seeds the group's opinion, marks the
character at the worst two degrees, and seeds heat where the character starts; and the
three Introductions as white journals, the Whispers' lines as Level-1 secrets with
gossip heat.
"""

from django.test import TestCase
from evennia.accounts.models import AccountDB

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.character_creation.constants import (
    ENEMY_PRICE_PENDING,
    WHISPERS_SEED_HEAT,
)
from world.character_creation.enemies import (
    EnemyOffer,
    enemy_offers,
    enemy_price,
    resolve_enemy,
)
from world.character_creation.factories import (
    GroupPromptFactory,
    OriginTemplateFactory,
    OriginTemplateSlotFactory,
)
from world.character_creation.models import BeginningEnemyOffer
from world.character_creation.services import finalize_character
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin
from world.character_sheets.models import CharacterEnemy
from world.character_sheets.types import EnemyDegree, EnemyKind, EnemyPowerTier, EnemyStatus
from world.distinctions.factories import DistinctionFactory
from world.distinctions.models import CharacterDistinction
from world.goals.constants import GoalHorizon
from world.goals.factories import GoalDomainFactory
from world.goals.models import CharacterGoal
from world.journals.constants import JournalKind
from world.journals.models import JournalEntry
from world.justice.models import PersonaHeat
from world.secrets.models import Secret, SecretGossip
from world.societies.constants import EnemyReach
from world.societies.factories import (
    OrganizationFactory,
    OrganizationTypeFactory,
    SocietyFactory,
)
from world.societies.models import OrganizationReputation


class EnemyPriceTests(TestCase):
    def test_group_scale_corners(self):
        assert enemy_price(EnemyKind.GROUP, EnemyReach.HOUSEHOLD, EnemyDegree.ANNOYED) == 3
        assert enemy_price(EnemyKind.GROUP, EnemyReach.REALM, EnemyDegree.DESTROY) == 150
        assert enemy_price(EnemyKind.GROUP, EnemyReach.HOUSE, EnemyDegree.THWARTED) == 16

    def test_person_scale_corners(self):
        assert enemy_price(EnemyKind.PERSON, EnemyPowerTier.QUIESCENT, EnemyDegree.ANNOYED) == 1
        assert enemy_price(EnemyKind.PERSON, EnemyPowerTier.GRAND, EnemyDegree.DESTROY) == 90
        assert enemy_price(EnemyKind.PERSON, EnemyPowerTier.PROSPECT, EnemyDegree.RUINED) == 8

    def test_unplaced_prices_pending(self):
        assert enemy_price(EnemyKind.GROUP, "", EnemyDegree.DESTROY) == ENEMY_PRICE_PENDING
        assert enemy_price(EnemyKind.PERSON, "", EnemyDegree.RUINED) == ENEMY_PRICE_PENDING


class EnemyOffersTests(FinalizationTestMixin, TestCase):
    def setUp(self) -> None:
        self._flush_common_caches()
        self.account = AccountDB.objects.create(username="enemy_offers")
        self._setup_finalization_base(self, prefix="Enemy Offers", height_min=700, height_max=800)
        self.crime = OrganizationTypeFactory(name="crime_family", reach=EnemyReach.HOUSE)
        self.realm_type = OrganizationTypeFactory(name="realm", reach=EnemyReach.REALM)

    def _draft_with_lineage(self):
        template = OriginTemplateFactory(
            beginning=self.beginnings, allows_name_family=False, allows_no_family=True
        )
        crew = OrganizationFactory(name="the Rouault", org_type=self.crime)
        group_q = GroupPromptFactory(template=template, sort_order=0, name="Family")
        group_q.anchor_orgs.add(crew)
        person_q = OriginTemplateSlotFactory(
            template=template,
            sort_order=1,
            name="Who",
            kind="person",
            same_anchor_as=group_q,
            follow_up_to=group_q,
        )
        draft = self._create_base_draft(
            origin_anchors={str(group_q.id): crew.id},
            origin_figures={str(person_q.id): "The woman who asked twice"},
        )
        draft.selected_origin_template = template
        draft.save()
        return draft, crew

    def test_lineage_groups_and_persons_are_offered_with_beginning_offers(self):
        draft, crew = self._draft_with_lineage()
        republic = OrganizationFactory(name="The Republic of Luxen", org_type=self.realm_type)
        BeginningEnemyOffer.objects.create(
            beginning=self.beginnings, organization=republic, why="it does not keep the Gifted"
        )
        BeginningEnemyOffer.objects.create(
            beginning=self.beginnings,
            figure_name="The Lacquerer",
            power_tier=EnemyPowerTier.PUISSANT,
            why="counted you once",
        )

        offers = enemy_offers(draft)

        by_name = {o.name: o for o in offers}
        assert by_name["the Rouault"] == EnemyOffer(
            kind=EnemyKind.GROUP,
            organization_id=crew.id,
            name="the Rouault",
            reach=EnemyReach.HOUSE,
            power_tier="",
            why="",
            source="lineage",
        )
        assert by_name["The woman who asked twice"].kind == EnemyKind.PERSON
        assert by_name["The woman who asked twice"].organization_id == crew.id
        assert by_name["The Republic of Luxen"].reach == EnemyReach.REALM
        assert by_name["The Republic of Luxen"].source == "beginning"
        assert by_name["The Lacquerer"].power_tier == EnemyPowerTier.PUISSANT

    def test_reach_override_on_an_offer_wins(self):
        draft = self._create_base_draft()
        umbral = OrganizationFactory(name="The Umbral houses", org_type=self.realm_type)
        BeginningEnemyOffer.objects.create(
            beginning=self.beginnings,
            organization=umbral,
            reach_override=EnemyReach.SOCIETY,
            why="want the titles back",
        )
        (offer,) = enemy_offers(draft)
        assert offer.reach == EnemyReach.SOCIETY

    def test_resolve_prices_an_offered_group_and_a_free_written_one(self):
        draft, crew = self._draft_with_lineage()
        draft.draft_data["enemy"] = {
            "kind": "group",
            "organization_id": crew.id,
            "name": "",
            "power_tier": "",
            "degree": "thwarted",
            "why": "I opened a door for them once.",
            "public_line": "There are people in the Cumberwards who would rather I had stayed.",
        }
        resolved = resolve_enemy(draft)
        assert resolved.price == 16
        assert resolved.status == EnemyStatus.PLACED
        assert resolved.reach == EnemyReach.HOUSE

        draft.draft_data["enemy"] = {
            "kind": "group",
            "organization_id": None,
            "name": "The Sept-Lanternes",
            "power_tier": "",
            "degree": "destroy",
            "why": "",
            "public_line": "",
        }
        pending = resolve_enemy(draft)
        assert pending.price == ENEMY_PRICE_PENDING
        assert pending.status == EnemyStatus.PENDING


class ActorSheetFinalizeTests(FinalizationTestMixin, TestCase):
    def setUp(self) -> None:
        self._flush_common_caches()
        self.account = AccountDB.objects.create(username="actor_sheet")
        self._setup_finalization_base(self, prefix="Actor Sheet", height_min=700, height_max=800)
        self.realm.name = "Arx"
        self.realm.save()
        self.bonds = GoalDomainFactory(name="Bonds")
        self.wealth = GoalDomainFactory(name="Wealth")
        # A start room inside a region whose dominant society is the enemy's.
        self.society = SocietyFactory(name="The Republic", realm=self.realm)
        self.region = AreaFactory(level=AreaLevel.REGION, dominant_society=self.society)
        self.ward = AreaFactory(level=AreaLevel.WARD, parent=self.region)
        room_profile = RoomProfileFactory(area=self.ward)
        self.area.default_starting_room = room_profile
        self.area.save()
        self.realm_type = OrganizationTypeFactory(name="realm", reach=EnemyReach.REALM)
        self.republic = OrganizationFactory(
            name="The Republic of Luxen", org_type=self.realm_type, society=self.society
        )
        BeginningEnemyOffer.objects.create(
            beginning=self.beginnings, organization=self.republic, why="does not keep the Gifted"
        )
        DistinctionFactory(name="Hunted")

    def _full_draft(self, **extra):
        data = {
            "never_do": "Tell a house what its servants say about it.",
            "protect": "Tessaline.",
            "fear": "Being counted.",
            "goals": [
                {
                    "domain_id": self.bonds.id,
                    "points": 12,
                    "notes": "Pay.",
                    "horizon": "short_term",
                },
                {
                    "domain_id": self.wealth.id,
                    "points": 6,
                    "notes": "A door.",
                    "horizon": "short_term",
                },
                {
                    "domain_id": self.bonds.id,
                    "points": 12,
                    "notes": "Doors.",
                    "horizon": "long_term",
                },
            ],
            "enemy": {
                "kind": "group",
                "organization_id": self.republic.id,
                "name": "",
                "power_tier": "",
                "degree": "destroy",
                "why": "It does not keep the Gifted.",
                "public_line": "The Republic and I are not on speaking terms.",
            },
            "introductions": {
                "first_journal": ["Not seen.", "The night the glass stopped falling.", ""],
                "application": ["Someone unprotected.", "Knives.", "Being thanked."],
                "whispers": "They say the keys walked.\nThey say the gate was paid for.",
            },
        }
        data.update(extra)
        return self._create_base_draft(**data)

    def test_finalize_writes_the_whole_table(self):
        draft = self._full_draft()
        character = finalize_character(draft, add_to_roster=True)
        sheet = character.sheet_data

        assert sheet.never_do == "Tell a house what its servants say about it."
        assert sheet.protect == "Tessaline."
        assert sheet.fear == "Being counted."

        goals = list(CharacterGoal.objects.filter(character=sheet).order_by("horizon", "ordinal"))
        assert [(g.horizon, g.ordinal, g.domain.name, g.points) for g in goals] == [
            (GoalHorizon.LONG_TERM, 1, "Bonds", 12),
            (GoalHorizon.SHORT_TERM, 1, "Bonds", 12),
            (GoalHorizon.SHORT_TERM, 2, "Wealth", 6),
        ]

        enemy = CharacterEnemy.objects.get(character=sheet)
        assert enemy.organization == self.republic
        assert enemy.reach == EnemyReach.REALM
        assert enemy.degree == EnemyDegree.DESTROY
        assert enemy.price == 150
        assert enemy.status == EnemyStatus.PLACED
        assert enemy.public_line == "The Republic and I are not on speaking terms."

        persona = sheet.primary_persona
        rep = OrganizationReputation.objects.get(persona=persona, organization=self.republic)
        assert rep.value < 0
        assert CharacterDistinction.objects.filter(
            character=sheet, distinction__name="Hunted"
        ).exists()
        heat = PersonaHeat.objects.get(persona=persona, society=self.society)
        assert heat.value == 60
        assert heat.pinned_until is not None

        entries = {e.kind: e for e in JournalEntry.objects.filter(author=sheet)}
        assert set(entries) == {
            JournalKind.FIRST_JOURNAL,
            JournalKind.APPLICATION,
            JournalKind.WHISPERS,
        }
        assert entries[JournalKind.FIRST_JOURNAL].title == "Test's First Journal"
        assert entries[JournalKind.FIRST_JOURNAL].is_public
        first = entries[JournalKind.FIRST_JOURNAL].body
        assert "What should the world know of you first?" in first
        assert "What do you think of the City of Arx?" not in first
        assert entries[JournalKind.APPLICATION].title == "An Application to Shroudwatch Academy"
        assert "What are thy talents?" in entries[JournalKind.APPLICATION].body

        secrets = list(Secret.objects.filter(subject_sheet=sheet).order_by("id"))
        assert [s.content for s in secrets] == [
            "They say the keys walked.",
            "They say the gate was paid for.",
        ]
        assert all(s.level == 1 for s in secrets)
        heats = SecretGossip.objects.filter(secret__in=secrets, region=self.region)
        assert heats.count() == 2
        assert all(h.heat == WHISPERS_SEED_HEAT for h in heats)

    def test_thwarted_grants_nothing_and_seeds_no_heat(self):
        draft = self._full_draft(
            enemy={
                "kind": "group",
                "organization_id": self.republic.id,
                "name": "",
                "power_tier": "",
                "degree": "thwarted",
                "why": "",
                "public_line": "",
            }
        )
        character = finalize_character(draft, add_to_roster=True)
        sheet = character.sheet_data
        assert CharacterEnemy.objects.get(character=sheet).price == 50
        assert not CharacterDistinction.objects.filter(character=sheet).exists()
        assert not PersonaHeat.objects.filter(persona=sheet.primary_persona).exists()

    def test_skipping_everything_writes_nothing(self):
        draft = self._create_base_draft()
        character = finalize_character(draft, add_to_roster=True)
        sheet = character.sheet_data
        assert sheet.never_do == ""
        assert not CharacterEnemy.objects.filter(character=sheet).exists()
        assert not JournalEntry.objects.filter(author=sheet).exists()
        assert not Secret.objects.filter(subject_sheet=sheet).exists()

    def test_first_journal_is_not_offered_outside_arx(self):
        self.realm.name = "Luxen"
        self.realm.save()
        draft = self._full_draft()
        character = finalize_character(draft, add_to_roster=True)
        entries = JournalEntry.objects.filter(author=character.sheet_data)
        kinds = set(entries.values_list("kind", flat=True))
        assert kinds == {JournalKind.APPLICATION, JournalKind.WHISPERS}

    def test_destroy_seeds_the_group_opinion_to_the_floor(self):
        draft = self._full_draft()
        character = finalize_character(draft, add_to_roster=True)
        persona = character.sheet_data.primary_persona
        rep = OrganizationReputation.objects.get(persona=persona, organization=self.republic)
        assert rep.value == -1000

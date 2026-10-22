"""Journeys for a technique's Paths and a Tradition's techniques (#4555).

A Path's list for a Gift (``PathGiftGrant.starter_techniques``) holds the techniques for
that Path and Gift; a Tradition's list (``TraditionGiftGrant.special_techniques``) keeps a
technique for that Tradition's members. These journeys read each place the rule shows: the
character creation pickers a player calls, a Ritual of the Durance crossing typed at
telnet, and a cast made the way the web client makes it.
"""

from __future__ import annotations

from decimal import Decimal
from unittest import mock

from actions.factories import ActionTemplateFactory
from integration_tests.harness import JourneyCase
from world.character_creation.factories import CharacterDraftFactory
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.checks.test_helpers import force_check_outcome
from world.checks.types import ExtraTraitTerm
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory, PathFactory
from world.classes.models import PathStage
from world.magic.factories import (
    BinaryEffectTypeFactory,
    CharacterAnimaFactory,
    CharacterTraditionFactory,
    GiftFactory,
    PathGiftGrantFactory,
    ResonanceFactory,
    RitualOfTheDuranceFactory,
    TechniqueFactory,
    TraditionFactory,
    TraditionGiftGrantFactory,
)
from world.magic.models import CharacterTechnique
from world.magic.models.sessions import RitualSession
from world.magic.seeds_cast import get_standalone_cast_template
from world.progression.factories import CharacterPathHistoryFactory
from world.progression.models.unlocks import CharacterUnlock, ClassLevelUnlock
from world.progression.selectors import current_path_for_character
from world.scenes.factories import SceneFactory
from world.scenes.tests.cast_test_helpers import grant_technique
from world.skills.factories import SkillFactory
from world.traits.factories import CheckSystemSetupFactory, StatTraitFactory
from world.traits.models import CheckOutcome
from world.vitals.models import CharacterVitals

# The Durance's legend gate, patched open as the Durance journeys do.
_DURANCE_GATE = "world.progression.services.spends.check_requirements_for_unlock"


class ChoosingTechniquesAtCreation(JourneyCase):
    """A Lamplighter and a Warden each pick techniques from Ashen Voice."""

    def setUp(self) -> None:
        super().setUp()
        ready = get_standalone_cast_template()
        self.embers = PathFactory(name="Path of Embers", stage=PathStage.PROSPECT)
        self.salt = PathFactory(name="Path of Salt", stage=PathStage.PROSPECT)
        self.voice = GiftFactory(name="Ashen Voice")
        self.cinder = TechniqueFactory(name="Cinder Word", gift=self.voice, action_template=ready)
        self.hymn = TechniqueFactory(name="Lamp Hymn", gift=self.voice, action_template=ready)
        self.vigil = TechniqueFactory(name="Salt Vigil", gift=self.voice, action_template=ready)
        PathGiftGrantFactory(path=self.embers, gift=self.voice).starter_techniques.add(
            self.cinder, self.hymn
        )
        PathGiftGrantFactory(path=self.salt, gift=self.voice).starter_techniques.add(self.vigil)
        self.lamplighters = TraditionFactory(name="Lamplighters")
        self.wardens = TraditionFactory(name="Wardens of the Ford")
        TraditionGiftGrantFactory(
            tradition=self.lamplighters, gift=self.voice
        ).special_techniques.add(self.hymn, self.vigil)
        TraditionGiftGrantFactory(tradition=self.wardens, gift=self.voice)

    def offered(self, tradition, path) -> tuple[list[int], dict[str, bool]]:
        """A player on ``tradition`` and ``path`` asks for gifts, then Ashen Voice's options."""
        draft = CharacterDraftFactory(selected_tradition=tradition, selected_path=path)
        client = self.api(draft.account)
        gifts = client.get("/api/character-creation/gifts/", {"draft_id": draft.pk})
        self.assertEqual(gifts.status_code, 200)
        options = client.get(
            "/api/character-creation/technique-options/",
            {"draft_id": draft.pk, "gift_id": self.voice.pk},
        )
        self.assertEqual(options.status_code, 200)
        rows = options.data["results"] if isinstance(options.data, dict) else options.data
        return (
            [row["id"] for row in gifts.data],
            {row["name"]: row["is_tradition_technique"] for row in rows},
        )

    def test_a_tradition_technique_is_offered_to_its_members_on_its_path(self) -> None:
        gifts, techniques = self.offered(self.lamplighters, self.embers)

        self.assertEqual(gifts, [self.voice.pk])
        self.assertEqual(techniques, {"Cinder Word": False, "Lamp Hymn": True})

    def test_an_open_technique_is_offered_to_every_tradition_on_its_path(self) -> None:
        gifts, techniques = self.offered(self.wardens, self.embers)

        self.assertEqual(gifts, [self.voice.pk])
        self.assertEqual(techniques, {"Cinder Word": False})

    def test_a_tradition_technique_stays_on_its_own_path(self) -> None:
        _, lamplighter = self.offered(self.lamplighters, self.salt)
        warden_gifts, warden = self.offered(self.wardens, self.salt)

        self.assertEqual(lamplighter, {"Salt Vigil": True})
        # Salt's only Ashen Voice technique is kept by the Lamplighters.
        self.assertEqual(warden_gifts, [])
        self.assertEqual(warden, {})


class CrossingIntoAPath(JourneyCase):
    """Wren, a Warden, crosses into the Potential path in a Ritual of the Durance."""

    def setUp(self) -> None:
        super().setUp()
        hall = self.make_room("The Durance Hall")
        SceneFactory(room=hall, is_active=True)
        prospect = PathFactory(name="Path of Reeds", stage=PathStage.PROSPECT)
        self.potential = PathFactory(name="Path of the Ford", stage=PathStage.POTENTIAL)
        self.potential.parent_paths.add(prospect)

        self.officiant = self.make_player("Maren", room=hall)
        self.wren = self.make_player("Wren", room=hall)
        CharacterClassLevelFactory(
            character=self.officiant.sheet_data, character_class=CharacterClassFactory(), level=10
        )
        warden_class = CharacterClassFactory()
        CharacterClassLevelFactory(
            character=self.wren.sheet_data, character_class=warden_class, level=2
        )
        ClassLevelUnlock.objects.create(character_class=warden_class, target_level=3)
        CharacterUnlock.objects.create(
            character=self.wren.sheet_data, character_class=warden_class, target_level=3
        )
        for character in (self.officiant, self.wren):
            CharacterPathHistoryFactory(character=character.sheet_data, path=prospect)

        river = GiftFactory(name="River Tongue")
        river.resonances.add(ResonanceFactory())
        self.ford_word = TechniqueFactory(name="Ford Word", gift=river)
        self.lamp_hymn = TechniqueFactory(name="Lamp Hymn", gift=river)
        PathGiftGrantFactory(path=self.potential, gift=river).starter_techniques.add(
            self.ford_word, self.lamp_hymn
        )
        wardens = TraditionFactory(name="Wardens of the Ford")
        CharacterTraditionFactory(character=self.wren.sheet_data, tradition=wardens)
        TraditionGiftGrantFactory(
            tradition=TraditionFactory(name="Lamplighters"), gift=river
        ).special_techniques.add(self.lamp_hymn)
        self.ritual = RitualOfTheDuranceFactory()

    def test_a_crossing_does_not_grant_another_traditions_technique(self) -> None:
        with mock.patch(_DURANCE_GATE, return_value=(True, [])):
            self.telnet(self.officiant, "ritual draft Ritual of the Durance invite=Wren")
            session = RitualSession.objects.get(ritual=self.ritual)
            self.telnet(
                self.wren,
                f"ritual join {session.pk} path=Path of the Ford "
                "testament=I have stood in the crucible and I am ready.",
            )
            self.telnet(self.officiant, f"ritual fire {session.pk}")

        self.assertEqual(current_path_for_character(self.wren), self.potential)
        known = set(
            CharacterTechnique.objects.filter(character=self.wren.sheet_data).values_list(
                "technique__name", flat=True
            )
        )
        self.assertEqual(known, {"Ford Word"})


class CastingAfterACrossing(JourneyCase):
    """Ysmay learned Cinder Word on the Path of Embers and now walks the Path of Ash."""

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        self.embers_skill = SkillFactory()
        self.ash_skill = SkillFactory()
        embers = PathFactory(name="Path of Embers", technique_skill=self.embers_skill)
        ash = PathFactory(
            name="Path of Ash", stage=PathStage.POTENTIAL, technique_skill=self.ash_skill
        )
        room = self.make_room("The Lantern")
        SceneFactory(room=room)
        check_type = CheckTypeFactory()
        CheckTypeTraitFactory(check_type=check_type, trait=StatTraitFactory(), weight=1)
        voice = GiftFactory()

        def technique(name: str):
            return TechniqueFactory(
                name=name,
                gift=voice,
                anima_cost=1,
                effect_type=BinaryEffectTypeFactory(),
                damage_profile=False,
                action_template=self.template,
            )

        self.template = ActionTemplateFactory(check_type=check_type)
        self.cinder = technique("Cinder Word")
        self.smoke = technique("Smoke Veil")
        PathGiftGrantFactory(path=embers, gift=voice).starter_techniques.add(self.cinder)
        PathGiftGrantFactory(path=ash, gift=voice).starter_techniques.add(self.smoke)

        self.ysmay = self.make_player("Ysmay", room=room)
        sheet = self.ysmay.sheet_data
        CharacterPathHistoryFactory(character=sheet, path=embers)
        CharacterPathHistoryFactory(character=sheet, path=ash)
        for known in (self.cinder, self.smoke):
            grant_technique(sheet.primary_persona, known)
        CharacterAnimaFactory(character=sheet, current=20, maximum=30)
        CharacterVitals.objects.create(
            character_sheet=sheet, health=50, max_health=50, base_max_health=50
        )

    def cast_terms(self, technique) -> tuple[ExtraTraitTerm, ...]:
        with force_check_outcome(CheckOutcome.objects.get(name="Success")) as capture:
            outcome = self.web(self.ysmay, "cast_technique", technique_id=technique.pk)
        self.assertTrue(outcome.detail.success, outcome.detail.message)
        return capture.extra_traits

    def test_a_technique_from_her_old_path_adds_that_paths_skill(self) -> None:
        self.assertEqual(
            self.cast_terms(self.cinder),
            (ExtraTraitTerm(trait=self.embers_skill.trait, weight=Decimal("1.00")),),
        )

    def test_a_technique_of_her_current_path_adds_its_skill(self) -> None:
        self.assertEqual(
            self.cast_terms(self.smoke),
            (ExtraTraitTerm(trait=self.ash_skill.trait, weight=Decimal("1.00")),),
        )

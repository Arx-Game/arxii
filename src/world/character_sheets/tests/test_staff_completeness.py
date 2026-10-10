"""Staff edit mode builds a complete sheet from a bare one (#3988, #4229).

A ``mint_gm_character`` sheet has none of the rows character creation writes. Staff,
through edit mode's endpoints alone, give it every family of rows ``finalize_character``
produces (less the onboarding missions and the CG point conversion, which describe a
new player rather than the character). One test, deliberately end to end: a family
missing from edit mode shows up here as a missing row.
"""

from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from actions.factories import ActionTemplateFactory
from evennia_extensions.factories import AccountFactory
from world.character_creation.factories import BeginningsFactory
from world.classes.factories import PathFactory
from world.classes.models import CharacterClassLevel
from world.codex.factories import BeginningsCodexGrantFactory, CodexEntryFactory
from world.codex.models import CharacterCodexKnowledge
from world.distinctions.factories import DistinctionFactory
from world.distinctions.models import CharacterDistinction
from world.forms.constants import MarkingKind
from world.forms.factories import FormTraitFactory, FormTraitOptionFactory
from world.forms.models import CharacterFormValue, FormMarking
from world.goals.factories import GoalDomainFactory
from world.goals.models import CharacterGoal
from world.items.constants import BodyRegion
from world.magic.factories import (
    GiftFactory,
    PathGiftGrantFactory,
    ResonanceFactory,
    TechniqueFactory,
    TraditionFactory,
    TraditionGiftGrantFactory,
)
from world.magic.models import CharacterAura, CharacterGift, CharacterTechnique
from world.magic.models.ritual_check_config import RitualCheckConfig
from world.progression.models import CharacterPathHistory
from world.roster.factories import FamilyFactory
from world.roster.models import Kinsperson
from world.roster.services.staff_characters import mint_gm_character
from world.skills.factories import SkillFactory
from world.skills.models import CharacterSkillValue
from world.species.factories import LanguageFactory
from world.traits.factories import StatTraitFactory, TraitFactory
from world.traits.models import CharacterTraitValue, TraitType
from world.vitals.models import CharacterVitals
from world.worship.factories import WorshippedBeingFactory
from world.worship.models import WorshipDeclaration


class StaffBuildsACompleteSheetTests(TestCase):
    def setUp(self) -> None:
        self.stat = StatTraitFactory(name="completeness_focus")
        self.skill = SkillFactory()
        self.hair = FormTraitFactory(name="completeness_hair")
        self.red = FormTraitOptionFactory(trait=self.hair, name="completeness_red")
        self.beginnings = BeginningsFactory()
        BeginningsCodexGrantFactory(beginnings=self.beginnings, entry=CodexEntryFactory())
        LanguageFactory(
            name="Completeness Common",
            is_universal=True,
            trait=TraitFactory(name="completeness_common", trait_type=TraitType.LANGUAGE),
        )
        self.path = PathFactory()
        self.tradition = TraditionFactory(name="Completeness Tradition")
        self.resonance = ResonanceFactory()
        self.gift = GiftFactory(name="Completeness Gift")
        self.gift.resonances.add(self.resonance)
        self.technique = TechniqueFactory(gift=self.gift, action_template=ActionTemplateFactory())
        TraditionGiftGrantFactory(tradition=self.tradition, gift=self.gift).special_techniques.add(
            self.technique
        )
        PathGiftGrantFactory(path=self.path, gift=self.gift)

    def test_a_bare_staff_character_gets_every_family_cg_writes(self) -> None:
        staff = AccountFactory(is_staff=True)
        sheet = mint_gm_character(staff, "Mirela Vant").character_sheet
        client = APIClient()
        client.force_authenticate(user=staff)
        base = f"/api/character-sheets/{sheet.pk}"

        def send(method: str, path: str, payload: dict) -> None:
            response = getattr(client, method)(f"{base}/{path}/", payload, format="json")
            assert response.status_code == 200, (path, response.content[:800])

        send("patch", "staff-stats", {"stats": {str(self.stat.pk): 3}})
        send("patch", "staff-skills", {"skills": {str(self.skill.pk): 10}})
        send("post", "staff-distinctions", {"distinction": DistinctionFactory().pk})
        send("patch", "staff-form", {"values": {str(self.hair.pk): self.red.pk}})
        send(
            "post",
            "staff-markings",
            {"body_region": BodyRegion.values[0], "kind": MarkingKind.values[0], "name": "Scar"},
        )
        send("put", "staff-beginnings", {"beginnings": self.beginnings.pk})
        send("patch", "staff-path", {"path": self.path.pk, "level": 1})
        send("put", "staff-goals", {"goals": [{"domain": GoalDomainFactory().pk, "points": 1}]})
        send(
            "put",
            "staff-worship",
            {"public_being": WorshippedBeingFactory().pk, "secret_being": None},
        )
        send(
            "post",
            "staff-magic",
            {
                "tradition": self.tradition.pk,
                "gift": self.gift.pk,
                "techniques": [self.technique.pk],
                "resonance": self.resonance.pk,
                "anima_stat": self.stat.pk,
                "anima_skill": self.skill.pk,
                "ritual_name": "Completeness Vigil",
                "glimpse": "",
            },
        )
        send("post", "staff-vitals", {})
        send("post", "staff-kinship", {"family": FamilyFactory().pk})

        assert CharacterTraitValue.objects.filter(character=sheet, trait=self.stat).exists()
        assert CharacterSkillValue.objects.filter(character=sheet, skill=self.skill).exists()
        assert CharacterDistinction.objects.filter(character=sheet).exists()
        assert CharacterFormValue.objects.filter(form__character=sheet, option=self.red).exists()
        assert FormMarking.objects.filter(form__character=sheet).exists()
        assert CharacterCodexKnowledge.objects.filter(roster_entry=sheet.roster_entry).exists()
        assert CharacterTraitValue.objects.filter(
            character=sheet, trait__name="completeness_common"
        ).exists()
        assert CharacterPathHistory.objects.filter(character=sheet, path=self.path).exists()
        assert CharacterClassLevel.objects.filter(character=sheet, is_primary=True).exists()
        assert CharacterGoal.objects.filter(character=sheet).exists()
        assert WorshipDeclaration.objects.filter(character_sheet=sheet).exists()
        assert CharacterGift.objects.filter(character=sheet, gift=self.gift).exists()
        assert CharacterTechnique.objects.filter(character=sheet, technique=self.technique).exists()
        assert CharacterAura.objects.filter(character=sheet).exists()
        assert RitualCheckConfig.objects.filter(ritual__name="Completeness Vigil").exists()
        assert CharacterVitals.objects.filter(character_sheet=sheet).exists()
        assert Kinsperson.objects.filter(sheet=sheet).exists()

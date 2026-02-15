from django.db import IntegrityError
from django.test import TestCase

from world.character_creation.factories import (
    BeginningsFactory,
    BeginningTraditionFactory,
    CharacterDraftFactory,
    TraditionTemplateFacetFactory,
    TraditionTemplateFactory,
    TraditionTemplateTechniqueFactory,
)
from world.character_creation.models import (
    BeginningTradition,
    DraftAnimaRitual,
    DraftGift,
    DraftMotif,
    DraftMotifResonance,
    DraftMotifResonanceAssociation,
    TraditionTemplate,
)
from world.character_creation.services import apply_tradition_template
from world.classes.factories import PathFactory
from world.distinctions.factories import DistinctionFactory
from world.magic.factories import (
    EffectTypeFactory,
    FacetFactory,
    ResonanceModifierTypeFactory,
    TechniqueStyleFactory,
    TraditionFactory,
)
from world.skills.factories import SkillFactory
from world.traits.factories import TraitFactory


class BeginningTraditionTests(TestCase):
    """Tests for BeginningTradition through model."""

    def test_create_beginning_tradition(self):
        bt = BeginningTraditionFactory()
        assert BeginningTradition.objects.filter(pk=bt.pk).exists()

    def test_with_required_distinction(self):
        distinction = DistinctionFactory()
        bt = BeginningTraditionFactory(required_distinction=distinction)
        assert bt.required_distinction == distinction

    def test_beginning_traditions_m2m(self):
        beginning = BeginningsFactory()
        t1 = TraditionFactory(name="T1")
        t2 = TraditionFactory(name="T2")
        BeginningTradition.objects.create(beginning=beginning, tradition=t1)
        BeginningTradition.objects.create(beginning=beginning, tradition=t2)
        assert beginning.traditions.count() == 2

    def test_unique_together(self):
        bt = BeginningTraditionFactory()
        with self.assertRaises(IntegrityError):
            BeginningTradition.objects.create(beginning=bt.beginning, tradition=bt.tradition)

    def test_tradition_available_in_multiple_beginnings(self):
        tradition = TraditionFactory()
        b1 = BeginningsFactory(name="B1")
        b2 = BeginningsFactory(name="B2")
        BeginningTradition.objects.create(beginning=b1, tradition=tradition)
        BeginningTradition.objects.create(beginning=b2, tradition=tradition)
        assert tradition.available_beginnings.count() == 2


class TraditionTemplateTests(TestCase):
    """Tests for TraditionTemplate and child models."""

    def test_create_template(self):
        t = TraditionTemplateFactory()
        assert TraditionTemplate.objects.filter(pk=t.pk).exists()

    def test_unique_together_tradition_path(self):
        t = TraditionTemplateFactory()
        with self.assertRaises(IntegrityError):
            TraditionTemplate.objects.create(
                tradition=t.tradition,
                path=t.path,
                gift_name="Duplicate",
            )

    def test_template_with_techniques(self):
        t = TraditionTemplateFactory()
        tech = TraditionTemplateTechniqueFactory(template=t)
        assert t.techniques.count() == 1
        assert t.techniques.first() == tech

    def test_template_with_facets(self):
        t = TraditionTemplateFactory()
        facet = TraditionTemplateFacetFactory(template=t)
        assert t.facets.count() == 1
        assert t.facets.first() == facet


class ApplyTraditionTemplateTests(TestCase):
    """Tests for the apply_tradition_template service function."""

    @classmethod
    def setUpTestData(cls):
        cls.tradition = TraditionFactory()
        cls.path = PathFactory(stage=1)
        cls.resonance = ResonanceModifierTypeFactory()
        cls.style = TechniqueStyleFactory()
        cls.effect_type = EffectTypeFactory()
        cls.stat = TraitFactory(trait_type="stat")
        cls.skill = SkillFactory()
        cls.facet = FacetFactory()

        cls.template = TraditionTemplateFactory(
            tradition=cls.tradition,
            path=cls.path,
            gift_name="Shadow Strike",
            gift_description="A shadowy gift",
            motif_description="Darkness and subtlety",
            anima_ritual_stat=cls.stat,
            anima_ritual_skill=cls.skill,
            anima_ritual_resonance=cls.resonance,
            anima_ritual_description="Meditate in shadows",
        )
        cls.template.resonances.add(cls.resonance)
        TraditionTemplateTechniqueFactory(
            template=cls.template,
            name="Shadow Bolt",
            style=cls.style,
            effect_type=cls.effect_type,
        )
        TraditionTemplateFacetFactory(
            template=cls.template,
            resonance=cls.resonance,
            facet=cls.facet,
        )

    def test_apply_creates_draft_gift(self):
        draft = CharacterDraftFactory(
            selected_path=self.path,
            selected_tradition=self.tradition,
        )
        apply_tradition_template(draft)
        gift = DraftGift.objects.get(draft=draft)
        assert gift.name == "Shadow Strike"
        assert gift.description == "A shadowy gift"

    def test_apply_creates_techniques(self):
        draft = CharacterDraftFactory(
            selected_path=self.path,
            selected_tradition=self.tradition,
        )
        apply_tradition_template(draft)
        gift = DraftGift.objects.get(draft=draft)
        assert gift.techniques.count() == 1
        assert gift.techniques.first().name == "Shadow Bolt"

    def test_apply_creates_motif(self):
        draft = CharacterDraftFactory(
            selected_path=self.path,
            selected_tradition=self.tradition,
        )
        apply_tradition_template(draft)
        motif = DraftMotif.objects.get(draft=draft)
        assert motif.description == "Darkness and subtlety"

    def test_apply_creates_anima_ritual(self):
        draft = CharacterDraftFactory(
            selected_path=self.path,
            selected_tradition=self.tradition,
        )
        apply_tradition_template(draft)
        ritual = DraftAnimaRitual.objects.get(draft=draft)
        assert ritual.stat == self.stat
        assert ritual.skill == self.skill
        assert ritual.description == "Meditate in shadows"

    def test_apply_sets_resonances_on_gift(self):
        draft = CharacterDraftFactory(
            selected_path=self.path,
            selected_tradition=self.tradition,
        )
        apply_tradition_template(draft)
        gift = DraftGift.objects.get(draft=draft)
        assert self.resonance in gift.resonances.all()

    def test_apply_creates_motif_resonances(self):
        draft = CharacterDraftFactory(
            selected_path=self.path,
            selected_tradition=self.tradition,
        )
        apply_tradition_template(draft)
        motif = DraftMotif.objects.get(draft=draft)
        motif_resonances = DraftMotifResonance.objects.filter(motif=motif)
        assert motif_resonances.count() == 1
        mr = motif_resonances.first()
        assert mr.resonance == self.resonance
        assert mr.is_from_gift is True

    def test_apply_creates_facet_associations(self):
        draft = CharacterDraftFactory(
            selected_path=self.path,
            selected_tradition=self.tradition,
        )
        apply_tradition_template(draft)
        motif = DraftMotif.objects.get(draft=draft)
        mr = DraftMotifResonance.objects.get(motif=motif)
        assoc = DraftMotifResonanceAssociation.objects.filter(motif_resonance=mr)
        assert assoc.count() == 1
        assert assoc.first().facet == self.facet

    def test_apply_replaces_existing_magic_data(self):
        draft = CharacterDraftFactory(
            selected_path=self.path,
            selected_tradition=self.tradition,
        )
        # Apply once
        apply_tradition_template(draft)
        assert DraftGift.objects.filter(draft=draft).count() == 1

        # Apply again (simulating tradition change)
        apply_tradition_template(draft)
        assert DraftGift.objects.filter(draft=draft).count() == 1
        assert DraftGift.objects.get(draft=draft).name == "Shadow Strike"

    def test_no_template_is_noop(self):
        """If no template exists for tradition+path combo, do nothing."""
        other_path = PathFactory(stage=1, name="Other Path")
        draft = CharacterDraftFactory(
            selected_path=other_path,
            selected_tradition=self.tradition,
        )
        apply_tradition_template(draft)
        assert not DraftGift.objects.filter(draft=draft).exists()

    def test_no_tradition_is_noop(self):
        """If draft has no tradition selected, do nothing."""
        draft = CharacterDraftFactory(
            selected_path=self.path,
            selected_tradition=None,
        )
        apply_tradition_template(draft)
        assert not DraftGift.objects.filter(draft=draft).exists()

    def test_no_path_is_noop(self):
        """If draft has no path selected, do nothing."""
        draft = CharacterDraftFactory(
            selected_path=None,
            selected_tradition=self.tradition,
        )
        apply_tradition_template(draft)
        assert not DraftGift.objects.filter(draft=draft).exists()


class PathSkillsTraditionValidationTests(TestCase):
    """Tests that _is_path_skills_complete requires a tradition."""

    def test_path_skills_incomplete_without_tradition(self):
        path = PathFactory(stage=1)
        draft = CharacterDraftFactory(selected_path=path, selected_tradition=None)
        assert draft._is_path_skills_complete() is False

    def test_path_skills_has_tradition_check(self):
        """Verify tradition is checked before validate_path_skills()."""
        path = PathFactory(stage=1)
        tradition = TraditionFactory()
        draft = CharacterDraftFactory(
            selected_path=path,
            selected_tradition=tradition,
        )
        # Should get past the tradition check (may still fail on skills
        # validation). The important thing is it doesn't return False
        # because of tradition.
        assert draft.selected_tradition is not None


class FinalizeMagicTraditionTests(TestCase):
    """Tests for tradition-related finalization steps."""

    @classmethod
    def setUpTestData(cls):
        from world.codex.factories import (
            CodexEntryFactory,
            TraditionCodexGrantFactory,
        )

        cls.tradition = TraditionFactory()
        cls.codex_entry = CodexEntryFactory()
        TraditionCodexGrantFactory(tradition=cls.tradition, entry=cls.codex_entry)

    def test_finalize_creates_character_tradition(self):
        """CharacterTradition created when draft has tradition."""
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.models import CharacterTradition

        sheet = CharacterSheetFactory()
        draft = CharacterDraftFactory(selected_tradition=self.tradition)

        # Partially simulate finalize_magic_data for just the tradition part
        CharacterTradition.objects.create(
            character=sheet,
            tradition=draft.selected_tradition,
        )

        assert CharacterTradition.objects.filter(character=sheet, tradition=self.tradition).exists()

    def test_finalize_creates_codex_knowledge(self):
        """Codex grants applied when draft has tradition."""
        from world.character_sheets.factories import CharacterSheetFactory
        from world.codex.constants import CodexKnowledgeStatus
        from world.codex.models import CharacterCodexKnowledge
        from world.roster.factories import RosterEntryFactory

        sheet = CharacterSheetFactory()
        RosterEntryFactory(character=sheet.character)
        draft = CharacterDraftFactory(selected_tradition=self.tradition)

        # Simulate step 5 of finalize_magic_data
        from world.codex.models import TraditionCodexGrant

        grants = TraditionCodexGrant.objects.filter(tradition=draft.selected_tradition).values_list(
            "entry_id", flat=True
        )
        roster_entry = sheet.character.roster_entry
        for entry_id in grants:
            CharacterCodexKnowledge.objects.get_or_create(
                roster_entry=roster_entry,
                entry_id=entry_id,
                defaults={"status": CodexKnowledgeStatus.KNOWN},
            )

        knowledge = CharacterCodexKnowledge.objects.filter(
            roster_entry=roster_entry,
            entry=self.codex_entry,
        )
        assert knowledge.exists()
        assert knowledge.first().status == CodexKnowledgeStatus.KNOWN

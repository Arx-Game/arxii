"""Copying NPC sections and whole NPCs; authoring regard and preferences (#4418)."""

from django.test import TestCase

from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory, seed_default_gm_level_caps
from world.npc_services.models import NpcPreference, NpcRegard, NpcRegardEvent, PersonalityTrait
from world.npc_services.personality import set_npc_preferences
from world.npc_services.regard import author_npc_regard, get_regard
from world.relationships.models import CharacterRelationship
from world.roster.constants import NPCSection
from world.roster.services.npc_copy import copy_npc_as_new, copy_npc_section
from world.roster.services.staff_characters import mint_story_npc
from world.scenes.factories import PersonaFactory
from world.societies.factories import OrganizationFactory


class NpcCopyTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        seed_default_gm_level_caps()
        cls.gm = GMProfileFactory(level=GMLevel.SENIOR).account
        cls.source = mint_story_npc(
            gm_account=cls.gm, name="Old Marrow", description="A stooped smith."
        ).sheet_data.roster_entry
        cls.target = mint_story_npc(
            gm_account=cls.gm, name="Young Fen", description="A bright apprentice."
        ).sheet_data.roster_entry

    def test_copy_description_only(self) -> None:
        profile = self.target.character_sheet.true_profile
        before_background = profile.background if profile is not None else ""

        copy_npc_section(self.source, self.target, NPCSection.DESCRIPTION)

        sheet = self.target.character_sheet
        sheet.refresh_from_db()
        assert sheet.additional_desc == "A stooped smith."
        profile = sheet.true_profile
        assert (profile.background if profile is not None else "") == before_background
        self.source.character_sheet.refresh_from_db()
        assert self.source.character_sheet.additional_desc == "A stooped smith."

    def test_copy_as_new_keeps_the_copier_as_owner(self) -> None:
        borrower = GMProfileFactory(level=GMLevel.JUNIOR).account

        new_entry = copy_npc_as_new(self.source, by=borrower, name="Marrow Twin")

        assert new_entry.created_by_account == borrower
        assert new_entry.current_tenure.player_data.account == borrower
        assert new_entry.character_sheet.additional_desc == "A stooped smith."
        assert not new_entry.story_npc_settings.is_template
        assert self.source.created_by_account == self.gm

    def test_copy_as_new_template_has_no_tenure(self) -> None:
        new_entry = copy_npc_as_new(self.source, by=self.gm, name="Marrow Mold", as_template=True)

        assert new_entry.story_npc_settings.is_template
        assert new_entry.current_tenure is None

    def test_copy_powers_replaces_and_stamps_provenance(self) -> None:
        from world.skills.factories import SkillFactory
        from world.traits.models import (
            CharacterTraitChange,
            CharacterTraitValue,
            TraitChangeSource,
        )

        skill = SkillFactory()
        src = self.source.character_sheet
        tgt = self.target.character_sheet
        CharacterTraitValue.objects.create(character=src, trait=skill.trait, value=30)
        CharacterTraitValue.objects.create(character=tgt, trait=skill.trait, value=10)

        copy_npc_section(self.source, self.target, NPCSection.POWERS)

        assert CharacterTraitValue.objects.get(character=tgt, trait=skill.trait).value == 30
        change = CharacterTraitChange.objects.get(character_sheet=tgt, trait=skill.trait)
        assert (change.old_value, change.new_value) == (10, 30)
        assert change.source == TraitChangeSource.STAFF_EDIT
        assert CharacterTraitValue.objects.get(character=src, trait=skill.trait).value == 30

    def test_copy_powers_grants_gifts_with_their_threads(self) -> None:
        from world.magic.constants import AcquisitionOrigin, TargetKind
        from world.magic.factories import GiftFactory, ResonanceFactory
        from world.magic.models import CharacterGift, Thread
        from world.magic.specialization.services import grant_gift_to_character

        resonance = ResonanceFactory()
        kept, dropped = GiftFactory(), GiftFactory()
        kept.resonances.add(resonance)
        dropped.resonances.add(resonance)
        src = self.source.character_sheet
        tgt = self.target.character_sheet
        grant_gift_to_character(src, kept)
        grant_gift_to_character(tgt, dropped)

        copy_npc_section(self.source, self.target, NPCSection.POWERS)

        assert not CharacterGift.objects.filter(character=tgt, gift=dropped).exists()
        row = CharacterGift.objects.get(character=tgt, gift=kept)
        assert row.origin == AcquisitionOrigin.GM_GRANT
        assert Thread.objects.filter(
            owner=tgt, target_kind=TargetKind.GIFT, target_gift=kept, retired_at=None
        ).exists()
        assert not Thread.objects.filter(owner=tgt, target_gift=dropped, retired_at=None).exists()
        assert CharacterGift.objects.filter(character=src, gift=kept).exists()

    def test_copy_all_includes_notes_for_player(self) -> None:
        settings = self.source.story_npc_settings
        settings.notes_for_player = "Never lets a guest stand."
        settings.save(update_fields=["notes_for_player"])

        copy_npc_section(self.source, self.target, NPCSection.ALL)

        target_settings = self.target.story_npc_settings
        target_settings.refresh_from_db()
        assert target_settings.notes_for_player == "Never lets a guest stand."

    def test_copy_persona_regard_writes_one_event_and_moves_no_gauges(self) -> None:
        pc = PersonaFactory()
        source_persona = self.source.character_sheet.primary_persona
        target_persona = self.target.character_sheet.primary_persona
        author_npc_regard(holder_persona=source_persona, target=pc, value=450)

        copy_npc_section(self.source, self.target, NPCSection.REGARD)

        assert get_regard(target_persona, pc) == 450
        assert NpcRegardEvent.objects.filter(regard__holder_persona=target_persona).count() == 1
        assert not CharacterRelationship.objects.filter(
            source=pc.character_sheet, target=target_persona.character_sheet
        ).exists()

    def test_copy_regard_replaces_target_and_leaves_source(self) -> None:
        org = OrganizationFactory()
        source_persona = self.source.character_sheet.primary_persona
        target_persona = self.target.character_sheet.primary_persona
        author_npc_regard(holder_persona=source_persona, target=org, value=300)
        author_npc_regard(holder_persona=target_persona, target=OrganizationFactory(), value=50)

        copy_npc_section(self.source, self.target, NPCSection.REGARD)

        assert get_regard(target_persona, org) == 300
        assert NpcRegard.objects.filter(holder_persona=target_persona, ended_at=None).count() == 1
        assert get_regard(source_persona, org) == 300


class NpcAuthoringTests(TestCase):
    def test_author_org_regard(self) -> None:
        holder = PersonaFactory()
        org = OrganizationFactory()

        author_npc_regard(holder_persona=holder, target=org, value=600)
        regard = author_npc_regard(holder_persona=holder, target=org, value=5000)

        assert get_regard(holder, org) == 1000
        assert regard.value == 1000

    def test_author_org_regard_value_600(self) -> None:
        holder = PersonaFactory()
        org = OrganizationFactory()

        regard = author_npc_regard(holder_persona=holder, target=org, value=600, reason="Owes us")

        assert regard.value == 600
        assert regard.reason == "Owes us"

    def test_author_persona_regard_is_one_event_and_moves_no_gauges(self) -> None:
        holder = PersonaFactory()
        target = PersonaFactory()

        author_npc_regard(holder_persona=holder, target=target, value=250)
        assert get_regard(holder, target) == 250
        assert NpcRegardEvent.objects.filter(regard__holder_persona=holder).count() == 1
        author_npc_regard(holder_persona=holder, target=target, value=-40)
        assert get_regard(holder, target) == -40
        assert not CharacterRelationship.objects.filter(
            source=target.character_sheet, target=holder.character_sheet
        ).exists()

    def test_set_preferences_replaces(self) -> None:
        persona = PersonaFactory()
        flattery = PersonalityTrait.objects.create(name="Flattery")
        pride = PersonalityTrait.objects.create(name="Pride")
        set_npc_preferences(persona, [(flattery, "likes")])

        set_npc_preferences(persona, [(pride, "dislikes")])

        rows = NpcPreference.objects.filter(persona=persona)
        assert [(r.trait.name, r.valence) for r in rows] == [("Pride", "dislikes")]

"""Shared test fixtures for character-finalization tests (#3268).

Extracted from ``test_services.py`` so both the service-level finalization
tests and the GM-finalize view tests (``test_gm_finalize_view.py``) can build
a submittable ``CharacterDraft`` without hand-rolling a second complete-draft
fixture.
"""

from __future__ import annotations

from decimal import Decimal

from world.character_creation.models import Beginnings, CharacterDraft, StartingArea
from world.character_sheets.models import Gender
from world.classes.factories import PathFactory
from world.classes.models import PathStage
from world.forms.models import Build, HeightBand
from world.magic.factories import (
    EffectTypeFactory,
    GiftFactory,
    PathGiftGrantFactory,
    ResonanceFactory,
    TechniqueFactory,
    TraditionFactory,
    TraditionGiftGrantFactory,
)
from world.realms.models import Realm
from world.roster.seeds import ensure_rosters
from world.skills.factories import SkillFactory
from world.species.models import Species
from world.tarot.constants import ArcanaType
from world.tarot.models import TarotCard
from world.traits.models import CharacterTraitValue, Trait, TraitType

# Shared stats dict used by all finalization tests (12 stats, 1-5 scale, sum=24)
DEFAULT_STATS = {
    "strength": 2,
    "agility": 2,
    "stamina": 2,
    "charm": 2,
    "presence": 2,
    "composure": 2,
    "intellect": 2,
    "wits": 2,
    "stability": 2,
    "luck": 2,
    "perception": 2,
    "willpower": 2,
}


class FinalizationTestMixin:
    """Shared setup and helpers for character finalization test classes."""

    @staticmethod
    def _flush_common_caches() -> None:
        """Flush SharedMemoryModel caches to prevent test pollution."""
        CharacterTraitValue.flush_instance_cache()
        Trait.flush_instance_cache()

    @staticmethod
    def _setup_finalization_base(
        target: object, *, prefix: str, height_min: int, height_max: int
    ) -> None:
        """Create common CG prerequisites on target (cls or self).

        Sets: realm, area, species, gender, tarot_card, beginnings,
        height_band, build, path, effect_type, resonance, tradition.
        """
        slug = prefix.lower().replace(" ", "_")

        # finalize_character()/approve_application() now look up seeded rosters by
        # roster_type (Roster.objects.get — #2728) instead of lazily creating them
        # via ensure_rosters(). Seed all seven shelves here so any finalization test
        # can add_to_roster=True/False or approve without a Roster.DoesNotExist.
        ensure_rosters()

        target.realm = Realm.objects.create(name=f"{prefix} Realm", description="Test")
        target.area = StartingArea.objects.create(
            name=f"{prefix} Area",
            description="Test",
            realm=target.realm,
            access_level=StartingArea.AccessLevel.ALL,
        )
        target.species = Species.objects.create(name=f"{prefix} Species", description="Test")
        target.gender, _ = Gender.objects.get_or_create(
            key=f"{slug}_gender", defaults={"display_name": f"{prefix} Gender"}
        )
        target.tarot_card = TarotCard.objects.create(
            name=f"{prefix} Fool",
            arcana_type=ArcanaType.MAJOR,
            rank=0,
            latin_name="Fatui",
        )
        target.beginnings = Beginnings.objects.create(
            name=f"{prefix} Beginnings",
            description="Test",
            starting_area=target.area,
            trust_required=0,
            is_active=True,
            family_known=False,
        )
        target.beginnings.allowed_species.add(target.species)
        target.height_band = HeightBand.objects.create(
            name=f"{slug}_band",
            display_name=f"{prefix} Band",
            min_inches=height_min,
            max_inches=height_max,
            weight_min=None,
            weight_max=None,
            is_cg_selectable=True,
        )
        target.build = Build.objects.create(
            name=f"{slug}_build",
            display_name=f"{prefix} Build",
            weight_factor=Decimal("1.0"),
            is_cg_selectable=True,
        )
        for stat_name in DEFAULT_STATS:
            Trait.objects.get_or_create(
                name=stat_name,
                defaults={"trait_type": TraitType.STAT, "description": stat_name},
            )
        target.path = PathFactory(name=f"{prefix} Path", stage=PathStage.PROSPECT, minimum_level=1)
        target.effect_type = EffectTypeFactory()
        target.resonance = ResonanceFactory()
        target.tradition = TraditionFactory()

        # Gift-stage validator fixtures (#2426): a gift available for (tradition, path)
        # with a pool technique, plus a Skill for the anima check.
        target.gift = GiftFactory(name=f"{prefix} Gift")
        path_grant = PathGiftGrantFactory(path=target.path, gift=target.gift)
        target.technique = TechniqueFactory(gift=target.gift, effect_type=target.effect_type)
        path_grant.starter_techniques.set([target.technique])
        TraditionGiftGrantFactory(tradition=target.tradition, gift=target.gift)
        target.skill = SkillFactory()
        target.stat_trait = Trait.objects.get(name="strength")

    def _create_complete_magic(self, draft: CharacterDraft) -> None:
        """Create complete magic data for a draft (Gift-stage validators, #2426).

        Populates the keys ``compute_magic_errors`` requires so ``draft.can_submit()``
        (the finalize gate) passes.
        """
        draft.draft_data["selected_gift_id"] = self.gift.id
        draft.draft_data["selected_technique_ids"] = [self.technique.id]
        draft.draft_data["selected_gift_resonance_id"] = self.resonance.id
        draft.draft_data["anima_check_stat_id"] = self.stat_trait.id
        draft.draft_data["anima_check_skill_id"] = self.skill.id
        draft.save(update_fields=["draft_data"])

    def _create_base_draft(
        self,
        *,
        first_name: str = "Test",
        height_inches: int | None = None,
        **extra_draft_data: object,
    ) -> CharacterDraft:
        """Create a complete draft for finalization testing.

        Override draft_data fields via extra_draft_data kwargs (e.g., stats=..., quote=...).
        """
        if height_inches is None:
            height_inches = (self.height_band.min_inches + self.height_band.max_inches) // 2

        base_data = {
            "first_name": first_name,
            "description": "A test character",
            "stats": DEFAULT_STATS,
            "lineage_is_orphan": True,
            "tarot_card_name": self.tarot_card.name,
            "tarot_reversed": False,
            "traits_complete": True,
        }
        base_data.update(extra_draft_data)

        draft = CharacterDraft.objects.create(
            account=self.account,
            selected_area=self.area,
            selected_beginnings=self.beginnings,
            selected_species=self.species,
            selected_gender=self.gender,
            selected_path=self.path,
            selected_tradition=self.tradition,
            age=25,
            birthday_month=6,
            birthday_day=12,
            height_band=self.height_band,
            height_inches=height_inches,
            build=self.build,
            draft_data=base_data,
        )
        self._create_complete_magic(draft)
        return draft

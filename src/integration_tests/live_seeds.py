"""Rows the live-server Playwright specs need, for the real-test CI job's throwaway database.

`.github/workflows/real-test.yml` calls these through `arx manage shell` after
`seed_test_account`, the same way it seeds that account. They write into a database that
exists for one CI run (or a real-testing Form B database of your own), so they build rows
with the test factories; nothing here is ever called by the game. Each seed is idempotent
on the names it writes, so a second run against the same database changes nothing.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MotifFacetSeed:
    """What `frontend/e2e/motif-facets.spec.ts` reads back."""

    roster_entry_id: int
    character_id: int
    draft_id: int
    resonance_name: str
    facet_names: tuple[str, ...]


#: The character, resonance and facets the spec names on screen.
FACET_SPEC_CHARACTER = "Wren Facetbinder"
FACET_SPEC_RESONANCE = "Moonsilver"
FACET_SPEC_FACETS = ("Wolf", "Silk", "Moon")


def seed_motif_facet_spec(*, username: str) -> MotifFacetSeed:
    """A character of *username*'s holding Moonsilver, three facets, and a draft at Gift.

    The character is played by the account (an open tenure, the account's selected
    entry), so the Spellbook shows the Facets panel. The draft sits at the Gift stage with
    Moonsilver as its gift resonance, so the creation page shows "Facets of Moonsilver".
    """
    from evennia.accounts.models import AccountDB  # noqa: PLC0415

    from evennia_extensions.factories import CharacterFactory  # noqa: PLC0415
    from evennia_extensions.models import PlayerData  # noqa: PLC0415
    from world.character_creation.constants import Stage  # noqa: PLC0415
    from world.character_creation.factories import CharacterDraftFactory  # noqa: PLC0415
    from world.character_creation.models import CharacterDraft  # noqa: PLC0415
    from world.character_sheets.factories import CharacterSheetFactory  # noqa: PLC0415
    from world.magic.factories import (  # noqa: PLC0415
        CharacterResonanceFactory,
        FacetFactory,
        ResonanceFactory,
    )
    from world.magic.models import CharacterResonance, Facet, Resonance  # noqa: PLC0415
    from world.roster.factories import (  # noqa: PLC0415
        RosterEntryFactory,
        RosterTenureFactory,
    )
    from world.roster.models import RosterEntry  # noqa: PLC0415
    from world.roster.services.selection import set_selected_entry  # noqa: PLC0415

    account = AccountDB.objects.get(username=username)
    player_data, _ = PlayerData.objects.get_or_create(account=account)

    resonance = Resonance.objects.filter(name=FACET_SPEC_RESONANCE).first()
    if resonance is None:
        resonance = ResonanceFactory(name=FACET_SPEC_RESONANCE)
    for name in FACET_SPEC_FACETS:
        if not Facet.objects.filter(name=name).exists():
            FacetFactory(name=name)

    entry = RosterEntry.objects.filter(
        character_sheet__character__db_key=FACET_SPEC_CHARACTER
    ).first()
    if entry is None:
        character = CharacterFactory(db_key=FACET_SPEC_CHARACTER)
        sheet = CharacterSheetFactory(character=character)
        entry = RosterEntryFactory(character_sheet=sheet)
        RosterTenureFactory(roster_entry=entry, player_data=player_data, end_date=None)
        character.db_account = account
        character.save()
    sheet = entry.character_sheet
    if not CharacterResonance.objects.filter(character_sheet=sheet, resonance=resonance).exists():
        CharacterResonanceFactory(character_sheet=sheet, resonance=resonance)
    set_selected_entry(player_data, entry)

    draft = CharacterDraft.objects.filter(account=account).first()
    if draft is None:
        draft = CharacterDraftFactory(account=account)
    draft.current_stage = Stage.GIFT
    draft.draft_data = {**draft.draft_data, "selected_gift_resonance_id": resonance.pk}
    draft.save()

    return MotifFacetSeed(
        roster_entry_id=entry.pk,
        character_id=sheet.character_id,
        draft_id=draft.pk,
        resonance_name=resonance.name,
        facet_names=FACET_SPEC_FACETS,
    )


@dataclass(frozen=True)
class ThrownStrikeSeed:
    """What `frontend/e2e/thrown-and-enchanted-strike.spec.ts` reads back (#5026)."""

    character_id: int
    encounter_id: int
    archer_id: int
    dagger_id: int
    technique_id: int
    greatsword_template_id: int
    coat_template_id: int
    staff_username: str


#: The names the thrown-strike spec looks for. Invented for the test; no game character.
THROWN_SPEC_CHARACTER = "Strike Tester"
THROWN_SPEC_ARCHER = "Bandit archer"
THROWN_SPEC_TECHNIQUE = "Wreathe the blade"
THROWN_SPEC_STAFF = "strike_staff"
THROWN_SPEC_STAFF_PASSWORD = "Ragged-Lantern-5026!"  # noqa: S105 - a throwaway test database only
THROWN_SPEC_ENCHANT_COST = 4


def seed_thrown_strike_spec(*, username: str) -> ThrownStrikeSeed:  # noqa: PLR0915 - one fight
    """A fight for *username*'s character with a throwable dagger and a fire weapon technique.

    The character stands in the Lane; a bandit archer, weak to fire with 1 soak, stands in
    the Yard, two positions away. The encounter is declaring, round 1, and resolves as soon
    as its one participant is ready. Also writes a two-handed sword template and an armor
    template for the admin half of the spec, and a staff account to open admin with.
    """
    from decimal import Decimal  # noqa: PLC0415

    from allauth.account.models import EmailAddress  # noqa: PLC0415
    from django.test import override_settings  # noqa: PLC0415
    from evennia.accounts.models import AccountDB  # noqa: PLC0415
    from evennia.utils import create  # noqa: PLC0415

    from actions.factories import ActionTemplateFactory  # noqa: PLC0415
    from evennia_extensions.factories import CharacterFactory, ObjectDBFactory  # noqa: PLC0415
    from evennia_extensions.models import PlayerData  # noqa: PLC0415
    from world.areas.positioning.factories import PositionFactory  # noqa: PLC0415
    from world.areas.positioning.plummet_content import ensure_fall_content  # noqa: PLC0415
    from world.areas.positioning.services import (  # noqa: PLC0415
        connect_positions,
        place_in_position,
    )
    from world.character_sheets.factories import CharacterSheetFactory  # noqa: PLC0415
    from world.checks.constants import ModifierLane, ModifierSize  # noqa: PLC0415
    from world.checks.factories import CheckTypeFactory  # noqa: PLC0415
    from world.checks.models import CheckType, CheckTypeTrait  # noqa: PLC0415
    from world.checks.modifier_models import ModifierValue  # noqa: PLC0415
    from world.combat.constants import (  # noqa: PLC0415
        MELEE_STRIKE_CHECK_TYPE_NAME,
        THROWN_STRIKE_CHECK_TYPE_NAME,
        PaceMode,
        ParticipantStatus,
    )
    from world.combat.factories import (  # noqa: PLC0415
        CombatEncounterFactory,
        CombatOpponentFactory,
        CombatParticipantFactory,
    )
    from world.combat.models import CombatOpponent  # noqa: PLC0415
    from world.combat.services import begin_declaration_phase  # noqa: PLC0415
    from world.conditions.factories import (  # noqa: PLC0415
        ConditionInstanceFactory,
        ConditionResistanceModifierFactory,
        ConditionTemplateFactory,
    )
    from world.conditions.models import DamageSuccessLevelMultiplier, DamageType  # noqa: PLC0415
    from world.items.constants import BodyRegion, EquipmentLayer, GearArchetype  # noqa: PLC0415
    from world.items.factories import ItemInstanceFactory, ItemTemplateFactory  # noqa: PLC0415
    from world.items.models import EquippedItem, ItemTemplate  # noqa: PLC0415
    from world.magic.factories import (  # noqa: PLC0415
        CharacterAnimaFactory,
        CharacterTechniqueFactory,
        EffectTypeFactory,
        GiftFactory,
        TechniqueDamageProfileFactory,
        TechniqueFactory,
    )
    from world.magic.models.modifier_level import CastPowerLevel  # noqa: PLC0415
    from world.mechanics.maneuver_effects import ensure_maneuver_effects  # noqa: PLC0415
    from world.roster.factories import RosterEntryFactory, RosterTenureFactory  # noqa: PLC0415
    from world.roster.models import RosterEntry  # noqa: PLC0415
    from world.scenes.constants import RoundStatus  # noqa: PLC0415
    from world.seeds.checks import seed_check_resolution_tables  # noqa: PLC0415
    from world.traits.models import CharacterTraitValue, Trait, TraitType  # noqa: PLC0415
    from world.vitals.models import CharacterVitals  # noqa: PLC0415
    from world.vitals.seeds import ensure_foundational_capabilities  # noqa: PLC0415
    from world.vitals.services import get_vitals_consequence_config  # noqa: PLC0415

    if not AccountDB.objects.filter(username=THROWN_SPEC_STAFF).exists():
        staff = create.create_account(
            THROWN_SPEC_STAFF, "strike_staff@example.com", THROWN_SPEC_STAFF_PASSWORD
        )
        staff.is_staff = True
        staff.is_superuser = True
        staff.save()
        EmailAddress.objects.update_or_create(
            user=staff,
            email="strike_staff@example.com",
            defaults={"primary": True, "verified": True},
        )
    # The available-actions read lists movement too, which needs the foundational
    # capabilities and the fall content an empty database lacks.
    with override_settings(SEED_SAMPLE_CONTENT=True):
        ensure_foundational_capabilities()
        ensure_fall_content()

    existing = RosterEntry.objects.filter(
        character_sheet__character__db_key=THROWN_SPEC_CHARACTER
    ).first()
    if existing is not None:
        return _thrown_seed_for(existing)

    seed_check_resolution_tables()
    ensure_maneuver_effects()
    DamageSuccessLevelMultiplier.objects.get_or_create(
        min_success_level=1, defaults={"multiplier": Decimal("1.00"), "label": "Full"}
    )
    config = get_vitals_consequence_config()
    physical = DamageType.objects.filter(name="Physical").first() or DamageType.objects.create(
        name="Physical"
    )
    if config.physical_damage_type_id is None:
        config.physical_damage_type = physical
        config.save(update_fields=["physical_damage_type"])
    fire = DamageType.objects.filter(name="Fire").first() or DamageType.objects.create(name="Fire")

    def trait(name: str, trait_type: str) -> Trait:
        found = Trait.objects.filter(name__iexact=name).first()
        return found or Trait.objects.create(name=name, trait_type=trait_type)

    strength = trait("strength", TraitType.STAT)
    thrown_skill = trait("Thrown Combat", TraitType.SKILL)
    melee_skill = trait("Melee Combat", TraitType.SKILL)
    willpower = trait("willpower", TraitType.STAT)
    for check_name, skill in (
        (THROWN_STRIKE_CHECK_TYPE_NAME, thrown_skill),
        (MELEE_STRIKE_CHECK_TYPE_NAME, melee_skill),
    ):
        check_type = CheckType.objects.filter(name=check_name).first() or CheckTypeFactory(
            name=check_name
        )
        CheckTypeTrait.objects.get_or_create(check_type=check_type, trait=strength)
        CheckTypeTrait.objects.get_or_create(check_type=check_type, trait=skill)
    magic_check = CheckType.objects.filter(name="Fire Magic Cast").first() or CheckTypeFactory(
        name="Fire Magic Cast"
    )
    CheckTypeTrait.objects.get_or_create(check_type=magic_check, trait=willpower)

    account = AccountDB.objects.get(username=username)
    player_data, _ = PlayerData.objects.get_or_create(account=account)
    room = ObjectDBFactory(db_key="The Steading", db_typeclass_path="typeclasses.rooms.Room")
    character = CharacterFactory(db_key=THROWN_SPEC_CHARACTER, location=room)
    sheet = CharacterSheetFactory(character=character)
    entry = RosterEntryFactory(character_sheet=sheet)
    RosterTenureFactory(roster_entry=entry, player_data=player_data, end_date=None)
    character.db_account = account
    character.save()
    CharacterVitals.objects.create(
        character_sheet=sheet, health=100, max_health=100, base_max_health=100
    )
    CharacterAnimaFactory(character=sheet, current=20, maximum=30)
    for stat_or_skill, value in ((strength, 40), (thrown_skill, 30), (willpower, 30)):
        CharacterTraitValue.objects.create(character=sheet, trait=stat_or_skill, value=value)

    lane = PositionFactory(room=room, name="Lane")
    barn = PositionFactory(room=room, name="Barn")
    yard = PositionFactory(room=room, name="Yard")
    connect_positions(lane, barn)
    connect_positions(barn, yard)
    place_in_position(character, lane)

    encounter = CombatEncounterFactory(
        room=room, round_number=0, status=RoundStatus.BETWEEN_ROUNDS, pace_mode=PaceMode.READY
    )
    CombatParticipantFactory(
        encounter=encounter, character_sheet=sheet, status=ParticipantStatus.ACTIVE
    )
    archer: CombatOpponent = CombatOpponentFactory(
        encounter=encounter, name=THROWN_SPEC_ARCHER, health=200, max_health=200, soak_value=1
    )
    place_in_position(archer.objectdb, yard)
    weak = ConditionTemplateFactory(name="Tinder-dry")
    ConditionResistanceModifierFactory(condition=weak, damage_type=fire, modifier_value=-3)
    ConditionInstanceFactory(condition=weak, target=archer.objectdb)

    dagger_template = ItemTemplateFactory(
        name="Parrying dagger",
        gear_archetype=GearArchetype.MELEE_ONE_HAND,
        base_weapon_damage=8,
        max_durability=20,
        can_be_thrown=True,
    )
    dagger = ItemInstanceFactory(template=dagger_template, durability=20)
    EquippedItem.objects.create(
        character=sheet,
        item_instance=dagger,
        body_region=BodyRegion.RIGHT_HAND,
        equipment_layer=EquipmentLayer.BASE,
    )
    greatsword: ItemTemplate = ItemTemplateFactory(
        name="Greatsword", gear_archetype=GearArchetype.MELEE_TWO_HAND, base_weapon_damage=10
    )
    coat: ItemTemplate = ItemTemplateFactory(
        name="Salamander-hide coat", gear_archetype=GearArchetype.LIGHT_ARMOR, base_armor_soak=2
    )

    CastPowerLevel.objects.get_or_create(min_power=0, defaults={"level": 1})
    ModifierValue.objects.get_or_create(
        lane=ModifierLane.TO_HIT, level=1, size=ModifierSize.MODERATE, defaults={"value": 2}
    )
    technique = TechniqueFactory(
        name=THROWN_SPEC_TECHNIQUE,
        gift=GiftFactory(name="Ember"),
        anima_cost=THROWN_SPEC_ENCHANT_COST,
        intensity=1,
        control=1,
        strike_to_hit_size=ModifierSize.MODERATE,
        effect_type=EffectTypeFactory(base_power=10),
        damage_profile=False,
        action_template=ActionTemplateFactory(check_type=magic_check),
    )
    TechniqueDamageProfileFactory(
        technique=technique,
        base_damage=4,
        damage_type=fire,
        damage_intensity_multiplier=Decimal(0),
        damage_per_extra_sl=0,
        minimum_success_level=1,
        uses_equipped_weapon=True,
    )
    CharacterTechniqueFactory(character=sheet, technique=technique)

    begin_declaration_phase(encounter)

    return ThrownStrikeSeed(
        character_id=character.pk,
        encounter_id=encounter.pk,
        archer_id=archer.pk,
        dagger_id=dagger.pk,
        technique_id=technique.pk,
        greatsword_template_id=greatsword.pk,
        coat_template_id=coat.pk,
        staff_username=THROWN_SPEC_STAFF,
    )


def _thrown_seed_for(entry: object) -> ThrownStrikeSeed:
    """The ids an earlier ``seed_thrown_strike_spec`` run wrote, read back by name."""
    from world.combat.models import CombatOpponent, CombatParticipant  # noqa: PLC0415
    from world.items.models import EquippedItem, ItemTemplate  # noqa: PLC0415
    from world.magic.models import Technique  # noqa: PLC0415

    sheet = entry.character_sheet
    participant = CombatParticipant.objects.filter(character_sheet=sheet).latest("pk")
    return ThrownStrikeSeed(
        character_id=sheet.character_id,
        encounter_id=participant.encounter_id,
        archer_id=CombatOpponent.objects.get(
            encounter_id=participant.encounter_id, name=THROWN_SPEC_ARCHER
        ).pk,
        dagger_id=EquippedItem.objects.filter(character=sheet).first().item_instance_id,
        technique_id=Technique.objects.get(name=THROWN_SPEC_TECHNIQUE).pk,
        greatsword_template_id=ItemTemplate.objects.get(name="Greatsword").pk,
        coat_template_id=ItemTemplate.objects.get(name="Salamander-hide coat").pk,
        staff_username=THROWN_SPEC_STAFF,
    )

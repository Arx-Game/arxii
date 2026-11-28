"""Rows the live-server Playwright specs need, for the real-test CI job's throwaway database.

`.github/workflows/real-test.yml` calls these through `arx manage shell` after
`seed_test_account`, the same way it seeds that account. They write into a database that
exists for one CI run (or a real-testing Form B database of your own), so they build rows
with the test factories; nothing here is ever called by the game. Each seed is idempotent
on the names it writes, so a second run against the same database changes nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
import secrets
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB

    from world.channels.models import Channel
    from world.character_sheets.models import CharacterSheet
    from world.checks.models import CheckOutcome, CheckType
    from world.magic.models import KindledStrengthTier, RecordedAct, Resonance
    from world.missions.models import MissionInstance
    from world.roster.models import RosterTenure
    from world.scenes.models import Scene


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
    from world.character_creation.factories import (  # noqa: PLC0415
        CharacterDraftFactory,
        single_resonance_weights,
    )
    from world.character_creation.models import CharacterDraft  # noqa: PLC0415
    from world.character_sheets.factories import CharacterSheetFactory  # noqa: PLC0415
    from world.magic.constants import AFFINITY_PRIMAL  # noqa: PLC0415
    from world.magic.factories import (  # noqa: PLC0415
        CharacterResonanceFactory,
        FacetFactory,
        primal_resonance,
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
        resonance = primal_resonance(name=FACET_SPEC_RESONANCE)
    elif resonance.affinity.name != AFFINITY_PRIMAL:
        # The spec's character takes this as her one Primal feeling: a row of that name under
        # another affinity would silently fail every creation check that reads it.
        msg = f"Resonance {FACET_SPEC_RESONANCE!r} exists under {resonance.affinity.name}."
        raise ValueError(msg)
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
    draft.draft_data = {
        **draft.draft_data,
        "gift_resonance_weights": single_resonance_weights(resonance),
    }
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
    staff_password: str


#: The names the thrown-strike spec looks for. Invented for the test; no game character.
THROWN_SPEC_CHARACTER = "Strike Tester"
THROWN_SPEC_ARCHER = "Bandit archer"
THROWN_SPEC_TECHNIQUE = "Wreathe the blade"
THROWN_SPEC_STAFF = "strike_staff"
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
    from world.skills.factories import MagicSkillFactory  # noqa: PLC0415
    from world.traits.models import CharacterTraitValue, Trait, TraitType  # noqa: PLC0415
    from world.vitals.models import CharacterVitals  # noqa: PLC0415
    from world.vitals.seeds import ensure_foundational_capabilities  # noqa: PLC0415
    from world.vitals.services import get_vitals_consequence_config  # noqa: PLC0415

    # A fresh random password each run, handed to the spec through the seed's result.
    staff_password = secrets.token_urlsafe(18)
    staff = AccountDB.objects.filter(username=THROWN_SPEC_STAFF).first()
    if staff is None:
        staff = create.create_account(THROWN_SPEC_STAFF, "strike_staff@example.com", staff_password)
    staff.set_password(staff_password)
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
        return _thrown_seed_for(existing, staff_password)

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
    # The playable puppet lock, so the web client can enter the world as her and draw
    # the Strike picker live; a factory character only carries pperm(Developer).
    account.at_post_create_character(character)
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
    fire_magic = MagicSkillFactory(name="Fire Magic")
    CharacterTraitValue.objects.create(character=sheet, trait=fire_magic, value=30)
    technique = TechniqueFactory(
        name=THROWN_SPEC_TECHNIQUE,
        skill=fire_magic,
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
        staff_password=staff_password,
    )


def _thrown_seed_for(entry: object, staff_password: str) -> ThrownStrikeSeed:
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
        staff_password=staff_password,
    )


@dataclass(frozen=True)
class SubstanceSpecSeed:
    """What `frontend/e2e/gift-substance.spec.ts` reads back (#5018)."""

    scene_id: int
    character_id: int
    technique_name: str


#: A shadow caster in an ordinary hall with a scene running that her account also GMs.
SUBSTANCE_SPEC_CHARACTER = "Vesper Shade"
SUBSTANCE_SPEC_ROOM = "The Lamplit Hall"
SUBSTANCE_SPEC_TECHNIQUE = "Veil of Dusk"


def seed_gift_substance_spec(*, username: str) -> SubstanceSpecSeed:  # noqa: PLR0915
    """A level-10 shadow caster of *username*'s, in an ordinary-lit room, scene running.

    Her gift's substance is shadow (the room's lighting falling); she holds 10 of its
    resonance and 30 anima; her technique costs 4 at intensity 6 and control 6, so outside
    a fight her control covers a one-step call-up. The account is also the scene's GM, so
    the Stage tab offers "Present here".
    """
    from django.db import transaction  # noqa: PLC0415
    from evennia.accounts.models import AccountDB  # noqa: PLC0415
    from evennia.utils import create  # noqa: PLC0415

    from evennia_extensions.factories import CharacterFactory  # noqa: PLC0415
    from evennia_extensions.models import PlayerData  # noqa: PLC0415
    from world.character_sheets.factories import CharacterSheetFactory  # noqa: PLC0415
    from world.locations.constants import StatKey  # noqa: PLC0415
    from world.magic.constants import SubstanceDirection, TargetKind  # noqa: PLC0415
    from world.magic.factories import (  # noqa: PLC0415
        CharacterAnimaFactory,
        CharacterResonanceFactory,
        GiftFactory,
        ResonanceFactory,
        ThreadFactory,
        ensure_canonical_affinities,
        seed_primum_tuning,
    )
    from world.magic.models import Substance, Technique  # noqa: PLC0415
    from world.roster.factories import (  # noqa: PLC0415
        RosterEntryFactory,
        RosterTenureFactory,
    )
    from world.roster.models import RosterEntry  # noqa: PLC0415
    from world.roster.services.selection import set_selected_entry  # noqa: PLC0415
    from world.scenes.factories import (  # noqa: PLC0415
        SceneFactory,
        SceneParticipationFactory,
    )
    from world.scenes.models import Scene  # noqa: PLC0415
    from world.scenes.tests.cast_test_helpers import (  # noqa: PLC0415
        grant_technique,
        make_benign_castable_technique,
    )
    from world.traits.factories import CheckSystemSetupFactory  # noqa: PLC0415
    from world.traits.models import ResultChart  # noqa: PLC0415
    from world.vitals.models import CharacterVitals  # noqa: PLC0415

    with transaction.atomic():
        if not ResultChart.objects.exists():
            CheckSystemSetupFactory.create()
        account = AccountDB.objects.get(username=username)
        player_data, _ = PlayerData.objects.get_or_create(account=account)
        _celestial, _primal, abyssal = ensure_canonical_affinities()
        seed_primum_tuning()

        entry = RosterEntry.objects.filter(
            character_sheet__character__db_key=SUBSTANCE_SPEC_CHARACTER
        ).first()
        if entry is None:
            room = create.create_object("typeclasses.rooms.Room", key=SUBSTANCE_SPEC_ROOM)
            character = CharacterFactory(db_key=SUBSTANCE_SPEC_CHARACTER, location=room)
            sheet = CharacterSheetFactory(character=character)
            entry = RosterEntryFactory(character_sheet=sheet)
            RosterTenureFactory(roster_entry=entry, player_data=player_data, end_date=None)
            character.db_account = account
            character.save()
            CharacterAnimaFactory(character=sheet, current=30, maximum=30)
            CharacterVitals.objects.create(
                character_sheet=sheet, health=50, max_health=50, base_max_health=50
            )
            umbral = ResonanceFactory(name="Gloaming", affinity=abyssal)
            shadow, _ = Substance.objects.get_or_create(
                name="shadow",
                defaults={
                    "stat_key": StatKey.LIGHTING,
                    "direction": SubstanceDirection.FALLING,
                },
            )
            gift = GiftFactory(name="Gloamcraft", substance=shadow)
            gift.resonances.add(umbral)
            ThreadFactory(
                owner=sheet,
                target_kind=TargetKind.GIFT,
                target_trait=None,
                target_gift=gift,
                resonance=umbral,
                level=100,
            )
            CharacterResonanceFactory(
                character_sheet=sheet, resonance=umbral, balance=10, lifetime_earned=10
            )
            technique = make_benign_castable_technique()
            technique.name = SUBSTANCE_SPEC_TECHNIQUE
            technique.gift = gift
            technique.anima_cost = 4
            technique.intensity = 6
            technique.control = 6
            technique.save()
            grant_technique(sheet.primary_persona, technique)
            scene = SceneFactory(room=room, is_active=True, name="Shadows in the Hall")
            SceneParticipationFactory(scene=scene, account=account, is_gm=True, is_owner=True)
        character = entry.character_sheet.character
        set_selected_entry(player_data, entry)
        scene = Scene.objects.filter(
            location_id=character.db_location_id, is_active=True
        ).first() or (Scene.objects.filter(participations__account=account).order_by("-pk").first())
        technique = Technique.objects.filter(name=SUBSTANCE_SPEC_TECHNIQUE).first()
    return SubstanceSpecSeed(
        scene_id=scene.pk, character_id=character.pk, technique_name=technique.name
    )


@dataclass(frozen=True)
class ChannelsSeed:
    """What `frontend/e2e/channels.spec.ts` reads back (#3299)."""

    character_id: int
    public_channel_id: int
    org_channel_id: int
    org_name: str
    other_speaker: str
    other_message: str
    blocked_speaker: str


#: Invented names for the channels spec; no game character.
CHANNELS_SPEC_CHARACTER = "Linnea Channelwright"
CHANNELS_SPEC_ROOM = "The Lantern Hall"
CHANNELS_SPEC_ORG = "The Lantern Guild"
CHANNELS_SPEC_OTHER_ACCOUNT = "channels_other_player"
CHANNELS_SPEC_OTHER_CHARACTER = "Odo Brightwater"
CHANNELS_SPEC_OTHER_MESSAGE = "Evening, all. Anyone walking the lantern route tonight?"
CHANNELS_SPEC_BLOCKED_ACCOUNT = "channels_blocked_player"
CHANNELS_SPEC_BLOCKED_CHARACTER = "Mara Thornquill"
CHANNELS_SPEC_BLOCKED_MESSAGE = "This line is from a player the reader has blocked."


def _account_named(name: str) -> AccountDB:
    """The account *name*, made once (AccountFactory's ``_create`` always creates)."""
    from evennia.accounts.models import AccountDB  # noqa: PLC0415

    from evennia_extensions.factories import AccountFactory  # noqa: PLC0415

    return AccountDB.objects.filter(username=name).first() or AccountFactory(username=name)


def _played_character(
    account: AccountDB,
    name: str,
    room: ObjectDB,  # noqa: OBJECTDB_PARAM - a factory character's location; no RoomProfile
) -> RosterTenure:
    """The open first-player tenure of *account* on character *name* in *room*, made once.

    The character carries the playable puppet lock, so the web client can enter the world
    as it; a factory character only carries pperm(Developer).
    """
    from evennia_extensions.factories import CharacterFactory  # noqa: PLC0415
    from evennia_extensions.models import PlayerData  # noqa: PLC0415
    from world.character_sheets.factories import CharacterSheetFactory  # noqa: PLC0415
    from world.roster.factories import (  # noqa: PLC0415
        RosterEntryFactory,
        RosterTenureFactory,
    )
    from world.roster.models import RosterTenure  # noqa: PLC0415

    player_data, _ = PlayerData.objects.get_or_create(account=account)
    tenure = (
        RosterTenure.objects.filter(
            player_data=player_data,
            end_date__isnull=True,
            roster_entry__character_sheet__character__db_key=name,
        )
        .select_related("roster_entry__character_sheet__character")
        .first()
    )
    if tenure is not None:
        return tenure
    character = CharacterFactory(db_key=name, location=room)
    sheet = CharacterSheetFactory(character=character)
    entry = RosterEntryFactory(character_sheet=sheet)
    tenure = RosterTenureFactory(
        roster_entry=entry, player_data=player_data, player_number=1, end_date=None
    )
    character.db_account = account
    character.save()
    account.at_post_create_character(character)
    return tenure


def _speaks_once(account: AccountDB, channel: Channel, tenure: RosterTenure, body: str) -> None:
    """*account* subscribed to *channel* speaking as *tenure*, with *body* posted once."""
    from world.channels.models import ChannelMessage  # noqa: PLC0415
    from world.channels.services import (  # noqa: PLC0415
        post_to_channel,
        subscribe,
        update_subscription,
    )

    subscription = subscribe(account, channel)
    if subscription.display_tenure_id != tenure.pk:
        update_subscription(subscription, display_tenure=tenure)
    if not ChannelMessage.objects.filter(channel=channel, author_tenure=tenure).exists():
        post_to_channel(account=account, channel=channel, body=body)


def seed_channels_spec(*, username: str) -> ChannelsSeed:
    """Public with one visible and one blocked post, and an org channel for *username*.

    *username* plays "Linnea Channelwright" (an open first-player tenure, standing in a
    room, puppetable from the web client) whose primary persona is an active member of
    "The Lantern Guild", whose ORG channel is provisioned. A second account plays "Odo
    Brightwater", is subscribed to Public speaking as him, and has posted once there. A
    third account plays "Mara Thornquill" and has posted once in Public after Odo;
    *username*'s account blocks that player at account level, so the reader's Public lane
    shows Odo's line and a "1 hidden" divider. The account's selected character is left
    alone, so the other live specs keep the character their own seeds chose.
    """
    from django.db import transaction  # noqa: PLC0415
    from evennia.accounts.models import AccountDB  # noqa: PLC0415
    from evennia.objects.models import ObjectDB  # noqa: PLC0415
    from evennia.utils import create  # noqa: PLC0415

    from world.channels.services import (  # noqa: PLC0415
        ensure_public_channel,
        provision_org_channel,
    )
    from world.scenes.block_services import create_block  # noqa: PLC0415
    from world.societies.factories import (  # noqa: PLC0415
        OrganizationFactory,
        OrganizationMembershipFactory,
    )
    from world.societies.models import OrganizationMembership  # noqa: PLC0415

    with transaction.atomic():
        public = ensure_public_channel()
        reader = AccountDB.objects.get(username=username)
        room = ObjectDB.objects.filter(
            db_key=CHANNELS_SPEC_ROOM, db_typeclass_path="typeclasses.rooms.Room"
        ).first() or create.create_object("typeclasses.rooms.Room", key=CHANNELS_SPEC_ROOM)
        mine = _played_character(reader, CHANNELS_SPEC_CHARACTER, room)
        persona = mine.roster_entry.character_sheet.primary_persona

        organization = OrganizationFactory(name=CHANNELS_SPEC_ORG)
        if not OrganizationMembership.objects.filter(
            organization=organization, persona=persona, left_at__isnull=True
        ).exists():
            OrganizationMembershipFactory(organization=organization, persona=persona)
        org_channel = provision_org_channel(organization)
        if org_channel is None:
            msg = f"{CHANNELS_SPEC_ORG} has no ORG channel (covert, or a covenant's org)."
            raise RuntimeError(msg)

        other = _account_named(CHANNELS_SPEC_OTHER_ACCOUNT)
        other_tenure = _played_character(other, CHANNELS_SPEC_OTHER_CHARACTER, room)
        _speaks_once(other, public, other_tenure, CHANNELS_SPEC_OTHER_MESSAGE)

        blocked = _account_named(CHANNELS_SPEC_BLOCKED_ACCOUNT)
        blocked_tenure = _played_character(blocked, CHANNELS_SPEC_BLOCKED_CHARACTER, room)
        _speaks_once(blocked, public, blocked_tenure, CHANNELS_SPEC_BLOCKED_MESSAGE)
        create_block(
            blocker_account=reader,
            blocker_persona=persona,
            blocked_persona=blocked_tenure.roster_entry.character_sheet.primary_persona,
            reason="Seeded for the channels live spec.",
            account_level=True,
        )

    return ChannelsSeed(
        character_id=mine.roster_entry.character_sheet.character_id,
        public_channel_id=public.pk,
        org_channel_id=org_channel.pk,
        org_name=organization.name,
        other_speaker=other_tenure.speaker_name,
        other_message=CHANNELS_SPEC_OTHER_MESSAGE,
        blocked_speaker=blocked_tenure.speaker_name,
    )


@dataclass(frozen=True)
class OneScaleSeed:
    """What `frontend/e2e/one-scale.spec.ts` reads back (#5091)."""

    roster_entry_id: int
    thread_id: int


#: The character the one-scale spec opens; its stats, skill and thread read as stored.
ONE_SCALE_SPEC_CHARACTER = "Odile Onescale"
#: Stored values the sheet must show as-is (strength 30 used to read 3).
ONE_SCALE_SPEC_STATS = {"strength": 30, "agility": 20}
ONE_SCALE_SPEC_THREAD_LEVEL = 30


def seed_one_scale_spec(*, username: str) -> OneScaleSeed:
    """A level-3 character of *username*'s with stats 30/20 and a gift thread at 30.

    The sheet shows strength 30 and agility 20 (stored values, #5091), the thread page
    shows level 30 against a cap of 30, and the band caps are the stored 50/60/110/...
    rows, and the pull-cost catalog is seeded so the thread page's Pull Preview reads real
    costs. The account's creation draft is not touched here: the spec moves it to the
    Attributes stage itself, after the specs that read it at another stage have run.
    """
    from django.db import transaction  # noqa: PLC0415
    from evennia.accounts.models import AccountDB  # noqa: PLC0415

    from evennia_extensions.factories import CharacterFactory  # noqa: PLC0415
    from evennia_extensions.models import PlayerData  # noqa: PLC0415
    from world.character_sheets.factories import CharacterSheetFactory  # noqa: PLC0415
    from world.classes.factories import CharacterClassLevelFactory  # noqa: PLC0415
    from world.magic.constants import TargetKind  # noqa: PLC0415
    from world.magic.factories import (  # noqa: PLC0415
        CharacterResonanceFactory,
        GiftFactory,
        ResonanceFactory,
        ThreadFactory,
    )
    from world.magic.models import Thread  # noqa: PLC0415
    from world.progression.seeds import seed_maturation_stat_caps  # noqa: PLC0415
    from world.roster.factories import (  # noqa: PLC0415
        RosterEntryFactory,
        RosterTenureFactory,
    )
    from world.roster.models import RosterEntry  # noqa: PLC0415
    from world.seeds.game_content.magic import seed_thread_pull_catalog  # noqa: PLC0415
    from world.traits.models import CharacterTraitValue, Trait, TraitType  # noqa: PLC0415

    with transaction.atomic():
        seed_maturation_stat_caps()
        seed_thread_pull_catalog()
        account = AccountDB.objects.get(username=username)
        player_data, _ = PlayerData.objects.get_or_create(account=account)
        entry = RosterEntry.objects.filter(
            character_sheet__character__db_key=ONE_SCALE_SPEC_CHARACTER
        ).first()
        if entry is None:
            character = CharacterFactory(db_key=ONE_SCALE_SPEC_CHARACTER)
            sheet = CharacterSheetFactory(character=character)
            entry = RosterEntryFactory(character_sheet=sheet)
            RosterTenureFactory(roster_entry=entry, player_data=player_data, end_date=None)
            character.db_account = account
            character.save()
            CharacterClassLevelFactory(character=sheet, level=3, is_primary=True)
            for name, value in ONE_SCALE_SPEC_STATS.items():
                trait, _ = Trait.objects.get_or_create(
                    name=name, defaults={"trait_type": TraitType.STAT}
                )
                CharacterTraitValue.objects.create(character=sheet, trait=trait, value=value)
            resonance = ResonanceFactory(name="Quickmarrow")
            CharacterResonanceFactory(
                character_sheet=sheet, resonance=resonance, balance=10, lifetime_earned=10
            )
            ThreadFactory(
                owner=sheet,
                target_kind=TargetKind.GIFT,
                target_trait=None,
                target_gift=GiftFactory(name="Marrowcraft"),
                resonance=resonance,
                level=ONE_SCALE_SPEC_THREAD_LEVEL,
            )
        thread = Thread.objects.get(owner=entry.character_sheet)
    return OneScaleSeed(roster_entry_id=entry.pk, thread_id=thread.pk)


@dataclass(frozen=True)
class MissiveSpecSeed:
    """What `frontend/e2e/missives.spec.ts` reads back (#3289)."""

    character_id: int
    roster_entry_id: int
    received_missive_id: int
    character_name: str
    addressed_face_name: str
    worn_face_name: str
    writer_face_name: str


#: A letter-writer the account plays, and the stranger who has already written to her.
MISSIVE_SPEC_CHARACTER = "Quill Lettersend"
MISSIVE_SPEC_WORN_FACE = "the Inkwell"
MISSIVE_SPEC_ROOM = "The Letter Office"
MISSIVE_SPEC_WRITER = "Marrow Pike"
MISSIVE_SPEC_WRITER_FACE = "the Lantern Man"
MISSIVE_SPEC_METHOD = "Courier"
MISSIVE_SPEC_ITEM = "brass locket"
MISSIVE_SPEC_BODY = "Meet me under the bridge at dusk."
MISSIVE_SPEC_PURSE = 1000
MISSIVE_SPEC_COIN = 25


def seed_missive_spec(*, username: str) -> MissiveSpecSeed:
    """A letter-writer of *username*'s with coin, a locket, and one letter waiting for her.

    "Quill Lettersend" stands in the Letter Office with 1000 coppers and a brass locket in
    hand, wearing her established face "the Inkwell" (so a reply's preselected face, the
    one the letter was written to, differs from the face she wears). "Marrow Pike", played
    by nobody, has the established face "the Lantern Man", who has already written to
    Quill's own name by the instant "Courier" with 25 coppers riding along, sent through
    ``send_missive`` from his own purse so the coin's custody is real, and announced by the
    arrival sweep.
    """
    from django.db import transaction  # noqa: PLC0415
    from evennia.accounts.models import AccountDB  # noqa: PLC0415
    from evennia.utils import create  # noqa: PLC0415

    from evennia_extensions.factories import CharacterFactory, ObjectDBFactory  # noqa: PLC0415
    from evennia_extensions.models import PlayerData  # noqa: PLC0415
    from world.character_sheets.factories import CharacterSheetFactory  # noqa: PLC0415
    from world.currency.services import get_or_create_purse, transfer  # noqa: PLC0415
    from world.items.factories import ItemInstanceFactory, ItemTemplateFactory  # noqa: PLC0415
    from world.messengers.models import Missive, TransmissionMethod  # noqa: PLC0415
    from world.messengers.seeds import ensure_messenger_method  # noqa: PLC0415
    from world.messengers.services import deliver_due_missives, send_missive  # noqa: PLC0415
    from world.roster.factories import (  # noqa: PLC0415
        RosterEntryFactory,
        RosterTenureFactory,
    )
    from world.roster.models import RosterEntry  # noqa: PLC0415
    from world.roster.services.selection import set_selected_entry  # noqa: PLC0415
    from world.scenes.constants import PersonaType  # noqa: PLC0415
    from world.scenes.factories import PersonaFactory  # noqa: PLC0415
    from world.scenes.models import Persona  # noqa: PLC0415
    from world.scenes.services import set_active_persona  # noqa: PLC0415

    with transaction.atomic():
        ensure_messenger_method()
        courier, _ = TransmissionMethod.objects.get_or_create(
            name=MISSIVE_SPEC_METHOD,
            defaults={
                "description": "A courier rides the letter straight to its reader.",
                "ic_delay_minutes": 0,
                "can_carry_items": True,
                "can_carry_coin": True,
                "is_universal": True,
            },
        )
        account = AccountDB.objects.get(username=username)
        player_data, _ = PlayerData.objects.get_or_create(account=account)

        entry = RosterEntry.objects.filter(
            character_sheet__character__db_key=MISSIVE_SPEC_CHARACTER
        ).first()
        if entry is None:
            room = create.create_object("typeclasses.rooms.Room", key=MISSIVE_SPEC_ROOM)
            character = CharacterFactory(db_key=MISSIVE_SPEC_CHARACTER, location=room)
            sheet = CharacterSheetFactory(character=character)
            entry = RosterEntryFactory(character_sheet=sheet)
            RosterTenureFactory(roster_entry=entry, player_data=player_data, end_date=None)
            character.db_account = account
            character.save()
            # The playable puppet lock, so the web client can enter the world as her.
            account.at_post_create_character(character)
            worn = PersonaFactory(
                character_sheet=sheet,
                name=MISSIVE_SPEC_WORN_FACE,
                persona_type=PersonaType.ESTABLISHED,
                thumbnail_url="",
            )
            set_active_persona(sheet, worn)
            transfer(
                amount=MISSIVE_SPEC_PURSE,
                reason="missive spec seed",
                to_purse=get_or_create_purse(sheet),
            )
            ItemInstanceFactory(
                template=ItemTemplateFactory(name=MISSIVE_SPEC_ITEM),
                game_object=ObjectDBFactory(db_key=MISSIVE_SPEC_ITEM, location=character),
                holder_character_sheet=sheet,
            )

            writer = CharacterFactory(db_key=MISSIVE_SPEC_WRITER, location=room)
            writer_sheet = CharacterSheetFactory(character=writer)
            writer_face = PersonaFactory(
                character_sheet=writer_sheet,
                name=MISSIVE_SPEC_WRITER_FACE,
                persona_type=PersonaType.ESTABLISHED,
                thumbnail_url="",
            )
            transfer(
                amount=MISSIVE_SPEC_COIN,
                reason="missive spec seed",
                to_purse=get_or_create_purse(writer_sheet),
            )
            send_missive(
                sender_persona=writer_face,
                recipient_persona=sheet.primary_persona,
                body=MISSIVE_SPEC_BODY,
                method=courier,
                coin_amount=MISSIVE_SPEC_COIN,
            )
        set_selected_entry(player_data, entry)
        # Inside the block, so the letter is never visible to the live server as due but
        # unannounced. The server's own missives.deliver sweep can run while this seed is
        # writing; if it caught the letter in between it would load the account's
        # PlayerData into the server's identity map with the selection as it stood at
        # that moment, and every later page would read that stale selection.
        deliver_due_missives()

    sheet = entry.character_sheet
    writer_face = Persona.objects.get(
        name=MISSIVE_SPEC_WRITER_FACE, persona_type=PersonaType.ESTABLISHED
    )
    received = Missive.objects.get(
        sender_persona=writer_face,
        recipient_persona=sheet.primary_persona,
        body=MISSIVE_SPEC_BODY,
    )
    return MissiveSpecSeed(
        character_id=sheet.character_id,
        roster_entry_id=entry.pk,
        received_missive_id=received.pk,
        character_name=MISSIVE_SPEC_CHARACTER,
        addressed_face_name=sheet.primary_persona.name,
        worn_face_name=MISSIVE_SPEC_WORN_FACE,
        writer_face_name=MISSIVE_SPEC_WRITER_FACE,
    )


@dataclass(frozen=True)
class FamilySeatsSeed:
    """What `frontend/e2e/family-seats.spec.ts` reads back."""

    draft_id: int
    family_id: int
    family_name: str
    closed_family_name: str
    head_name: str
    locked_seat_id: int
    locked_seat_name: str
    open_seat_id: int
    open_seat_name: str


#: The house the seats spec joins, the one it must not be offered, and the people in it.
SEATS_SPEC_HOUSE = "Vellacourt"
SEATS_SPEC_CLOSED_HOUSE = "Brackwater"
SEATS_SPEC_HEAD = "Seraphine"
SEATS_SPEC_LOCKED_SEAT = "Isaura"
SEATS_SPEC_OPEN_SEAT = "Corwin"


def seed_family_seats_spec(*, username: str) -> FamilySeatsSeed:
    """A creation draft of *username*'s at Lineage, and a house with two open seats (#5130).

    House Vellacourt's title is held by "Seraphine". Two seats of the house are open:
    her daughter "Isaura", whose name is fixed, and her nephew "Corwin", whose name the
    player may change. House Brackwater, of the same realm and kind, has a member and no
    seat to take, so character creation must not offer it. The draft's beginning brings a
    route whose only family path is an established family of that kind.
    """
    from django.db import transaction  # noqa: PLC0415
    from evennia.accounts.models import AccountDB  # noqa: PLC0415

    from world.character_creation.constants import Parentage, Stage  # noqa: PLC0415
    from world.character_creation.factories import (  # noqa: PLC0415
        CharacterDraftFactory,
        OriginTemplateFactory,
    )
    from world.character_creation.models import CharacterDraft  # noqa: PLC0415
    from world.roster.constants import NOBLE_KIND_NAME  # noqa: PLC0415
    from world.roster.factories import FamilyFactory, FamilyKindFactory  # noqa: PLC0415
    from world.roster.models import Family, Kinsperson  # noqa: PLC0415
    from world.roster.services import kinship  # noqa: PLC0415
    from world.societies.factories import OrganizationFactory  # noqa: PLC0415
    from world.societies.houses.constants import TitleTier  # noqa: PLC0415
    from world.societies.houses.models import Title  # noqa: PLC0415

    account = AccountDB.objects.get(username=username)
    with transaction.atomic():
        family = Family.objects.filter(name=SEATS_SPEC_HOUSE).first()
        if family is None:
            kind = FamilyKindFactory(name=NOBLE_KIND_NAME)
            template = OriginTemplateFactory(
                name="Born to a house",
                allows_claim_family=True,
                allows_name_family=False,
                allows_no_family=False,
                parentage=Parentage.KNOWN,
            )
            template.claimable_kinds.add(kind)
            area = template.beginning.starting_area
            family = FamilyFactory(name=SEATS_SPEC_HOUSE, kind=kind, origin_realm=area.realm)
            house = OrganizationFactory(name=f"House {SEATS_SPEC_HOUSE}", family=family)
            elder = kinship.create_person(name="Odalric", family=family)
            head = kinship.create_person(name=SEATS_SPEC_HEAD, family=family)
            brother = kinship.create_person(name="Aldous", family=family)
            for child in (head, brother):
                kinship.record_parentage(child=child, parent=elder)
            Title.objects.create(
                name=f"County of {SEATS_SPEC_HOUSE}",
                tier=TitleTier.COUNTY,
                realm=area.realm,
                house=house,
                holder=head,
            )
            for name, parent, locked in (
                (SEATS_SPEC_LOCKED_SEAT, head, True),
                (SEATS_SPEC_OPEN_SEAT, brother, False),
            ):
                seat = kinship.create_person(name=name, family=family)
                seat.is_appable = True
                seat.name_locked = locked
                seat.save(update_fields=["is_appable", "name_locked"])
                kinship.record_parentage(child=seat, parent=parent)
            closed = FamilyFactory(name=SEATS_SPEC_CLOSED_HOUSE, kind=kind, origin_realm=area.realm)
            kinship.create_person(name="Ysmae", family=closed)

            draft = CharacterDraft.objects.filter(account=account).first()
            if draft is None:
                draft = CharacterDraftFactory(account=account)
            draft.selected_area = area
            draft.selected_beginnings = template.beginning
            draft.selected_origin_template = template
            draft.family = None
            draft.claimed_kin_slot = None
            draft.claimed_kin_pool = None
            draft.current_stage = Stage.LINEAGE
            draft.draft_data = {**draft.draft_data, "first_name": SEATS_SPEC_LOCKED_SEAT}
            draft.save()

    draft = CharacterDraft.objects.get(account=account)
    seats = {seat.name: seat for seat in Kinsperson.objects.filter(family=family, is_appable=True)}
    return FamilySeatsSeed(
        draft_id=draft.pk,
        family_id=family.pk,
        family_name=SEATS_SPEC_HOUSE,
        closed_family_name=SEATS_SPEC_CLOSED_HOUSE,
        head_name=SEATS_SPEC_HEAD,
        locked_seat_id=seats[SEATS_SPEC_LOCKED_SEAT].pk,
        locked_seat_name=SEATS_SPEC_LOCKED_SEAT,
        open_seat_id=seats[SEATS_SPEC_OPEN_SEAT].pk,
        open_seat_name=SEATS_SPEC_OPEN_SEAT,
    )


@dataclass(frozen=True)
class LifePointsSeed:
    """What `frontend/e2e/life-points.spec.ts` reads back."""

    draft_id: int
    costly_card: str
    costly_price: int
    paying_card: str
    paying_price: int
    later_card: str


#: The life-points spec's own route, beat and the two cards on it.
LIFE_POINTS_AREA = "Ledger Road"
LIFE_POINTS_BEGINNING = "Road-born"
LIFE_POINTS_ROUTE = "Raised on the ledger road"
LIFE_POINTS_BEAT = "What the road taught you"
LIFE_POINTS_COSTLY_CARD = "Counting-house clerk"
LIFE_POINTS_COSTLY_PRICE = 15
LIFE_POINTS_PAYING_CARD = "Owes the road"
LIFE_POINTS_PAYING_PRICE = 10
#: A second beat in a later life stage, with one card (#5160): the life page opens with
#: every stage and section expanded, which one beat in one stage cannot show.
LIFE_POINTS_LATER_BEAT = "What the road cost you"
LIFE_POINTS_LATER_CARD = "Left someone behind"
LIFE_POINTS_LATER_PRICE = 5


def seed_life_points_spec(*, username: str) -> LifePointsSeed:
    """A creation draft of *username*'s at Lineage with two life beats (#5141, #5160).

    The beats are offered to this draft's beginning alone, so no other account's draft
    meets them. The childhood beat has two cards: one costs 15 CG points and the world
    pays 10 for the other. The youth beat has one card, so the life has two stages and
    two sections. The draft holds no pick and is stamped as having loaded its suggested
    life, so the page opens with nothing chosen.
    """
    from django.db import transaction  # noqa: PLC0415
    from django.utils.text import slugify  # noqa: PLC0415
    from evennia.accounts.models import AccountDB  # noqa: PLC0415

    from world.character_creation.constants import (  # noqa: PLC0415
        BeatAudience,
        BeatSelection,
        LifeStage,
        OfferChapter,
        Parentage,
        Stage,
    )
    from world.character_creation.factories import (  # noqa: PLC0415
        BeginningsFactory,
        CharacterDraftFactory,
        DistinctionOfferFactory,
        LifeBeatExclusionFactory,
        LifeBeatFactory,
        OriginTemplateFactory,
        RealmFactory,
        StartingAreaFactory,
    )
    from world.character_creation.models import CharacterDraft, LifeBeat  # noqa: PLC0415
    from world.distinctions.factories import (  # noqa: PLC0415
        DistinctionCategoryFactory,
        DistinctionFactory,
    )

    account = AccountDB.objects.get(username=username)
    with transaction.atomic():
        if not LifeBeat.objects.filter(name=LIFE_POINTS_BEAT).exists():
            # Every row is named here. Each seed runs in its own process, so a factory's
            # counter starts again at 0 and its default name is one another seed already
            # used: an insert collides, and a get-or-create factory hands back the other
            # seed's row with these arguments dropped.
            area = StartingAreaFactory(
                name=LIFE_POINTS_AREA, realm=RealmFactory(name=LIFE_POINTS_AREA)
            )
            beginning = BeginningsFactory(name=LIFE_POINTS_BEGINNING, starting_area=area)
            template = OriginTemplateFactory(
                beginning=beginning,
                name=LIFE_POINTS_ROUTE,
                allows_claim_family=False,
                allows_name_family=False,
                allows_no_family=True,
                parentage=Parentage.UNKNOWN,
            )
            category = DistinctionCategoryFactory(name="Road life", slug="road-life")
            beat = LifeBeatFactory(
                name=LIFE_POINTS_BEAT,
                prompt="What did the road make of you.",
                selection=BeatSelection.ANY,
                offered_to=BeatAudience.ONLY_LISTED,
            )
            LifeBeatExclusionFactory(beat=beat, beginning=beginning)
            later = LifeBeatFactory(
                name=LIFE_POINTS_LATER_BEAT,
                life_stage=LifeStage.YOUTH,
                prompt="What did the road take from you.",
                selection=BeatSelection.ANY,
                offered_to=BeatAudience.ONLY_LISTED,
            )
            LifeBeatExclusionFactory(beat=later, beginning=beginning)
            for on_beat, name, price in (
                (beat, LIFE_POINTS_COSTLY_CARD, LIFE_POINTS_COSTLY_PRICE),
                (beat, LIFE_POINTS_PAYING_CARD, -LIFE_POINTS_PAYING_PRICE),
                (later, LIFE_POINTS_LATER_CARD, LIFE_POINTS_LATER_PRICE),
            ):
                DistinctionOfferFactory(
                    chapter=OfferChapter.BACKGROUNDS,
                    beat=on_beat,
                    appearance_section=None,
                    prompt="",
                    distinction=DistinctionFactory(
                        name=name,
                        slug=slugify(name),
                        category=category,
                        cost_per_rank=price,
                        max_rank=1,
                    ),
                )

            draft = CharacterDraft.objects.filter(account=account).first()
            if draft is None:
                draft = CharacterDraftFactory(account=account, selected_area=area)
            draft.selected_area = area
            draft.selected_beginnings = beginning
            draft.selected_origin_template = template
            draft.current_stage = Stage.LINEAGE
            draft.draft_data = {
                **draft.draft_data,
                "first_name": "Maren",
                "life_loaded_for": beginning.pk,
                "distinctions": [],
            }
            draft.save()

    draft = CharacterDraft.objects.get(account=account)
    return LifePointsSeed(
        draft_id=draft.pk,
        costly_card=LIFE_POINTS_COSTLY_CARD,
        costly_price=LIFE_POINTS_COSTLY_PRICE,
        paying_card=LIFE_POINTS_PAYING_CARD,
        paying_price=LIFE_POINTS_PAYING_PRICE,
        later_card=LIFE_POINTS_LATER_CARD,
    )


@dataclass(frozen=True)
class StrengthSpecSeed:
    """What `frontend/e2e/strength-and-cast-resonance.spec.ts` reads back (#5231)."""

    draft_id: int
    #: The feeling the creation picks start from, the second pick and the other one the
    #: step's slider is moved to, and the feeling whose colour the admin step changes.
    feeling_name: str
    second_feeling_name: str
    outward_name: str
    second_outward_name: str
    admin_feeling_id: int
    admin_feeling_name: str
    caster_id: int
    scene_id: int
    scene_name: str
    technique_name: str
    usual_name: str
    kindled_name: str
    #: The caster's resonance rows, so staff can read her corruption in admin.
    usual_row_id: int
    kindled_row_id: int
    #: The staff pages the spec pictures: the Abyssal affinity, the kindling configuration
    #: (whose strength rows carry the cast power), and the corruption and drift configurations.
    abyssal_affinity_id: int
    kindling_config_id: int
    corruption_config_id: int
    drift_config_id: int
    staff_username: str
    staff_password: str


#: The eight Primal, eight Celestial and eight Abyssal resonances of the approved demo, each
#: with its one-word description and colour. Invented scaffolding for a throwaway database.
STRENGTH_SPEC_PRIMAL = (
    ("Arderi", "burning", "#F3680F"),
    ("Sereni", "serene", "#67C0D5"),
    ("Audax", "bold", "#F14445"),
    ("Medita", "contemplative", "#7973CA"),
    # Fera keeps the default grey: the admin step gives it a colour of its own.
    ("Fera", "wild", None),
    ("Civitas", "civil", "#CDA448"),
    ("Firma", "steadfast", "#9B673B"),
    ("Vola", "restless", "#0DCBC3"),
)
STRENGTH_SPEC_CELESTIAL = (
    ("Bene", "giving", "#FFEFB1"),
    ("Liberare", "freeing", "#BCF8FE"),
    ("Fidelis", "faithful", "#D2E9FF"),
    ("Misera", "merciful", "#FFDBF1"),
    ("Fortis", "brave", "#FFE897"),
    ("Honoris", "honourable", "#F6F3DC"),
    ("Verax", "truthful", "#E8F8FF"),
    ("Copperi", "renewing", "#C0FDCC"),
)
STRENGTH_SPEC_ABYSSAL = (
    ("Praedari", "preying", "#3D0005"),
    ("Dominari", "dominating", "#1D0638"),
    ("Perfidus", "betraying", "#00280B"),
    ("Maligna", "malicious", "#2F0118"),
    ("Tremora", "terrifying", "#03102C"),
    ("Saevus", "cruel", "#490000"),
    ("Insidia", "deceiving", "#002225"),
    ("Despari", "despairing", "#080B14"),
)
STRENGTH_SPEC_CASTER = "Ysmay Vale"
STRENGTH_SPEC_ROOM = "The Ember Hall"
STRENGTH_SPEC_SCENE = "Embers in the Hall"
STRENGTH_SPEC_TECHNIQUE = "Ember Veil"
STRENGTH_SPEC_STAFF = "strength_staff"


def _strength_spec_resonances() -> None:
    """The 24 resonances, each named once under its own affinity (idempotent by name)."""
    from world.magic.models import Resonance  # noqa: PLC0415

    celestial, primal, abyssal = _canonical_affinities()
    for affinity, rows in (
        (primal, STRENGTH_SPEC_PRIMAL),
        (celestial, STRENGTH_SPEC_CELESTIAL),
        (abyssal, STRENGTH_SPEC_ABYSSAL),
    ):
        for name, description, colour in rows:
            defaults = {"description": description, "affinity": affinity}
            if colour is not None:
                defaults["color_hex"] = colour
            resonance, _ = Resonance.objects.get_or_create(name=name, defaults=defaults)
            if resonance.affinity_id != affinity.pk:
                msg = f"Resonance {name!r} exists under {resonance.affinity.name}."
                raise ValueError(msg)


def _canonical_affinities() -> tuple[object, object, object]:
    from world.magic.factories import ensure_canonical_affinities  # noqa: PLC0415

    return ensure_canonical_affinities()


def _strength_spec_draft(account: AccountDB) -> int:
    """The account's creation draft at the Gift stage, tradition, gift and techniques chosen.

    Everything the stages before the resonance step ask for is filled, and the anima check is
    picked, so the draft's only open question is the resonance. Its picks are cleared on every
    run, so a second run starts the step from nothing.
    """
    from decimal import Decimal  # noqa: PLC0415

    from world.character_creation.constants import Stage  # noqa: PLC0415
    from world.character_creation.factories import (  # noqa: PLC0415
        make_unknown_upbringing,
    )
    from world.character_creation.models import (  # noqa: PLC0415
        Beginnings,
        CharacterDraft,
        StartingArea,
    )
    from world.character_creation.tests.finalization_fixtures import DEFAULT_STATS  # noqa: PLC0415
    from world.character_sheets.models import Gender  # noqa: PLC0415
    from world.classes.factories import PathFactory  # noqa: PLC0415
    from world.classes.models import PathStage  # noqa: PLC0415
    from world.forms.models import Build, HeightBand  # noqa: PLC0415
    from world.magic.factories import (  # noqa: PLC0415
        EffectTypeFactory,
        GiftFactory,
        PathGiftGrantFactory,
        TechniqueFactory,
        TraditionFactory,
        TraditionGiftGrantFactory,
    )
    from world.magic.seeds_cast import get_standalone_cast_template  # noqa: PLC0415
    from world.realms.models import Realm  # noqa: PLC0415
    from world.roster.seeds import ensure_rosters  # noqa: PLC0415
    from world.seeds.modifier_values import seed_pool_and_cap_lanes  # noqa: PLC0415
    from world.skills.factories import SkillFactory  # noqa: PLC0415
    from world.species.models import Species  # noqa: PLC0415
    from world.tarot.constants import ArcanaType  # noqa: PLC0415
    from world.tarot.models import TarotCard  # noqa: PLC0415
    from world.traits.models import Trait, TraitType  # noqa: PLC0415

    draft = CharacterDraft.objects.filter(account=account).first()
    if draft is not None and "selected_gift_id" in draft.draft_data:
        draft.current_stage = Stage.GIFT
        draft.draft_data = {
            key: value for key, value in draft.draft_data.items() if key != "gift_resonance_weights"
        }
        draft.save()
        return draft.pk

    ensure_rosters()
    seed_pool_and_cap_lanes()
    realm = Realm.objects.create(name="Strength Realm", description="A place to begin.")
    area = StartingArea.objects.create(
        name="Strength Area",
        description="A place to begin.",
        realm=realm,
        access_level=StartingArea.AccessLevel.ALL,
    )
    species = Species.objects.create(name="Strength Species", description="People.")
    gender, _ = Gender.objects.get_or_create(
        key="strength_gender", defaults={"display_name": "Strength Gender"}
    )
    tarot = TarotCard.objects.create(
        name="Strength Fool", arcana_type=ArcanaType.MAJOR, rank=0, latin_name="Fatui"
    )
    beginnings = Beginnings.objects.create(
        name="Strength Beginnings", description="A start.", starting_area=area, is_active=True
    )
    beginnings.allowed_species.add(species)
    upbringing = make_unknown_upbringing(beginnings)
    band = HeightBand.objects.create(
        name="strength_band",
        display_name="Strength Band",
        min_inches=700,
        max_inches=800,
        weight_min=None,
        weight_max=None,
        is_cg_selectable=True,
    )
    build = Build.objects.create(
        name="strength_build",
        display_name="Strength Build",
        weight_factor=Decimal("1.0"),
        is_cg_selectable=True,
    )
    stats = dict(DEFAULT_STATS)
    for stat_name in stats:
        Trait.objects.get_or_create(
            name=stat_name, defaults={"trait_type": TraitType.STAT, "description": stat_name}
        )
    path = PathFactory(name="Strength Path", stage=PathStage.PROSPECT, minimum_level=1)
    tradition = TraditionFactory(name="Strength Tradition")
    gift = GiftFactory(name="Strength Gift")
    path_grant = PathGiftGrantFactory(path=path, gift=gift)
    technique = TechniqueFactory(
        name="Strength Pool Technique",
        gift=gift,
        effect_type=EffectTypeFactory(name="Strength Effect Type"),
        action_template=get_standalone_cast_template(),
    )
    path_grant.starter_techniques.set([technique])
    TraditionGiftGrantFactory(tradition=tradition, gift=gift)
    skill = SkillFactory(name="Strength Skill")

    draft = CharacterDraft.objects.create(
        account=account,
        selected_area=area,
        selected_beginnings=beginnings,
        selected_origin_template=upbringing,
        selected_species=species,
        selected_gender=gender,
        selected_path=path,
        selected_tradition=tradition,
        age=25,
        birthday_month=6,
        birthday_day=12,
        height_band=band,
        height_inches=750,
        build=build,
        current_stage=Stage.GIFT,
        draft_data={
            "first_name": "Strength",
            "description": "A character who draws on a feeling.",
            "stats": stats,
            "tarot_card_name": tarot.name,
            "tarot_reversed": False,
            "selected_gift_id": gift.pk,
            "selected_technique_ids": [technique.pk],
            "anima_check_stat_id": Trait.objects.get(name="strength").pk,
            "anima_check_skill_id": skill.pk,
        },
    )
    return draft.pk


def seed_strength_spec(*, username: str) -> StrengthSpecSeed:  # noqa: PLR0915 - draft and caster
    """A Gift-stage creation draft and a kindled Abyssal caster, both *username*'s (#5231).

    The 24 resonances of the approved demo exist, Fera with the default grey colour. The
    account's draft is at the Gift stage with its tradition, gift and techniques chosen and
    no resonance picked. The account also plays Ysmay Vale, in the Ember Hall with a scene
    running. Her aura is 80 percent Primal and 20 percent Abyssal. Her Gift's thread holds
    Sereni (Primal, leading, her usual resonance) and Praedari (Abyssal), and Praedari is
    kindled at the third strength row. Numbers set here: Abyssal's kindled boost 150 and earn
    rate 150, the third strength row's cast power 6, light corruption 10 percent below an
    Abyssal share of 50. Her technique is tier 1 at intensity 20 and control 40.

    Worked by hand from those numbers (the expectations of the live spec):

    * Power: a kindled cast adds cast power times the boost percent over 100, rounded down,
      6 * 150 // 100 = 9, so a cast worked in Praedari lists a kindled line of 9 and one
      worked in Sereni lists none.
    * Corruption: a cast worked in a resonance puts its whole intensity (20) on it, then
      20 * (Abyssal coefficient 10 / 10) * (tier 1 coefficient 10 / 10) = 20. She is 20
      percent Abyssal, under the 50 share, so she takes the light 10 percent, 20 * 10 / 100 =
      2, which is already whole. A cast worked in Sereni (coefficient 0) adds none.

    A staff account is made for the admin half: the colour of a resonance and her corruption.
    """
    from allauth.account.models import EmailAddress  # noqa: PLC0415
    from django.db import transaction  # noqa: PLC0415
    from evennia.accounts.models import AccountDB  # noqa: PLC0415
    from evennia.utils import create  # noqa: PLC0415

    from evennia_extensions.factories import CharacterFactory  # noqa: PLC0415
    from evennia_extensions.models import PlayerData  # noqa: PLC0415
    from world.character_sheets.factories import CharacterSheetFactory  # noqa: PLC0415
    from world.conditions.factories import (  # noqa: PLC0415
        ConditionStageFactory,
        ConditionTemplateFactory,
    )
    from world.magic.factories import (  # noqa: PLC0415
        CharacterAnimaFactory,
        CharacterAuraFactory,
        CharacterResonanceFactory,
        CharacterTechniqueFactory,
        GiftFactory,
        KindlingConfigFactory,
        ensure_conversion_pairs,
        kindle_resonance,
    )
    from world.magic.models import (  # noqa: PLC0415
        Affinity,
        CharacterResonance,
        KindledDeedAward,
        KindledStrengthTier,
        KindlingConfig,
        Resonance,
        Technique,
    )
    from world.magic.services.corruption import get_corruption_config  # noqa: PLC0415
    from world.magic.services.drift import get_drift_config  # noqa: PLC0415
    from world.magic.specialization.services import provision_latent_gift_thread  # noqa: PLC0415
    from world.roster.factories import (  # noqa: PLC0415
        RosterEntryFactory,
        RosterTenureFactory,
    )
    from world.roster.models import RosterEntry  # noqa: PLC0415
    from world.roster.services.selection import set_selected_entry  # noqa: PLC0415
    from world.scenes.factories import (  # noqa: PLC0415
        SceneFactory,
        SceneParticipationFactory,
    )
    from world.scenes.models import Scene  # noqa: PLC0415
    from world.scenes.tests.cast_test_helpers import (  # noqa: PLC0415
        grant_technique,
        make_benign_castable_technique,
    )
    from world.traits.constants import CANONICAL_OUTCOME_LEVELS  # noqa: PLC0415
    from world.traits.factories import CheckSystemSetupFactory  # noqa: PLC0415
    from world.traits.models import ResultChart  # noqa: PLC0415
    from world.traits.services import ensure_canonical_check_outcome  # noqa: PLC0415
    from world.vitals.models import CharacterVitals  # noqa: PLC0415

    staff_password = secrets.token_urlsafe(18)
    staff = AccountDB.objects.filter(username=STRENGTH_SPEC_STAFF).first()
    if staff is None:
        staff = create.create_account(
            STRENGTH_SPEC_STAFF, "strength_staff@example.com", staff_password
        )
    staff.set_password(staff_password)
    staff.is_staff = True
    staff.is_superuser = True
    staff.save()
    EmailAddress.objects.update_or_create(
        user=staff,
        email="strength_staff@example.com",
        defaults={"primary": True, "verified": True},
    )

    account = AccountDB.objects.get(username=username)
    with transaction.atomic():
        _strength_spec_resonances()
        draft_id = _strength_spec_draft(account)

        if not ResultChart.objects.exists():
            CheckSystemSetupFactory.create()
        player_data, _ = PlayerData.objects.get_or_create(account=account)
        _celestial, primal, abyssal = ensure_conversion_pairs()
        for affinity, boost, rate, coefficient in (
            (primal, 100, 100, 0),
            (abyssal, 150, 150, 10),
        ):
            affinity.kindled_boost_percent = boost
            affinity.earn_rate_percent = rate
            affinity.corruption_coefficient = coefficient
            affinity.save()
        Affinity.objects.clear_cache()
        corruption = get_corruption_config()
        corruption.tier_1_coefficient = 10
        corruption.light_corruption_percent = 10
        corruption.full_corruption_from_share = 50
        corruption.save()
        drift = get_drift_config()
        drift.own_side_tolerance_percent = 15
        drift.save()
        usual = Resonance.objects.get(name="Sereni")
        kindled = Resonance.objects.get(name="Praedari")

        entry = RosterEntry.objects.filter(
            character_sheet__character__db_key=STRENGTH_SPEC_CASTER
        ).first()
        if entry is None:
            # The three strengths a migration seeds on a real database; a database built
            # from the models (CI's, a real-testing one) has none, so they are written here.
            for rank, tier_name in ((1, "Faint"), (2, "Strong"), (3, "Blazing")):
                KindledStrengthTier.objects.get_or_create(rank=rank, defaults={"name": tier_name})
            blazing = KindledStrengthTier.objects.get(rank=3)
            blazing.cast_power = 6
            blazing.earn_percent = 100
            blazing.save()
            # A live roll lands on any of the five canonical tiers, so every tier earns the
            # deed: the spec's "You earned" line then does not depend on the dice. The tiers
            # are written here, because a roll writes a missing one only when it lands on it.
            for tier_name in CANONICAL_OUTCOME_LEVELS:
                KindledDeedAward.objects.update_or_create(
                    outcome_tier=ensure_canonical_check_outcome(tier_name),
                    defaults={"amount": 10},
                )
            KindlingConfigFactory()
            template = ConditionTemplateFactory(
                name="Corruption (Praedari)",
                has_progression=True,
                corruption_resonance=kindled,
            )
            for order, threshold in enumerate([50, 200, 500, 1000, 1500], start=1):
                ConditionStageFactory(
                    condition=template, stage_order=order, severity_threshold=threshold
                )

            room = create.create_object("typeclasses.rooms.Room", key=STRENGTH_SPEC_ROOM)
            character = CharacterFactory(db_key=STRENGTH_SPEC_CASTER, location=room)
            sheet = CharacterSheetFactory(character=character)
            entry = RosterEntryFactory(character_sheet=sheet)
            RosterTenureFactory(roster_entry=entry, player_data=player_data, end_date=None)
            character.db_account = account
            character.save()
            CharacterAnimaFactory(character=sheet, current=50, maximum=50)
            CharacterVitals.objects.create(
                character_sheet=sheet, health=50, max_health=50, base_max_health=50
            )
            CharacterAuraFactory(character=sheet, celestial="0", primal="80", abyssal="20")
            CharacterResonanceFactory(
                character_sheet=sheet, resonance=usual, balance=10, lifetime_earned=80
            )
            CharacterResonanceFactory(
                character_sheet=sheet, resonance=kindled, balance=10, lifetime_earned=20
            )
            gift = GiftFactory(name="Cinderheart")
            technique = make_benign_castable_technique()
            technique.name = STRENGTH_SPEC_TECHNIQUE
            technique.gift = gift
            technique.anima_cost = 1
            technique.intensity = 20
            technique.control = 40
            technique.save()
            if technique.tier != 1:
                msg = f"The technique is tier {technique.tier}; the hand-worked numbers are tier 1."
                raise ValueError(msg)
            grant_technique(sheet.primary_persona, technique)
            CharacterTechniqueFactory(character=sheet, technique=technique)
            # Sereni is listed first, so it leads the Gift's thread.
            provision_latent_gift_thread(sheet, gift, resonances=[usual, kindled])
            kindle_resonance(sheet, kindled, blazing)
            scene = SceneFactory(room=room, is_active=True, name=STRENGTH_SPEC_SCENE)
            SceneParticipationFactory(scene=scene, account=account, is_gm=True, is_owner=True)
        character = entry.character_sheet.character
        set_selected_entry(player_data, entry)
        sheet = entry.character_sheet
        scene = Scene.objects.get(name=STRENGTH_SPEC_SCENE)
        technique = Technique.objects.get(name=STRENGTH_SPEC_TECHNIQUE)
        usual_row = CharacterResonance.objects.get(character_sheet=sheet, resonance=usual)
        kindled_row = CharacterResonance.objects.get(character_sheet=sheet, resonance=kindled)

    return StrengthSpecSeed(
        draft_id=draft_id,
        feeling_name="Arderi",
        second_feeling_name="Audax",
        outward_name="Praedari",
        second_outward_name="Dominari",
        admin_feeling_id=Resonance.objects.get(name="Fera").pk,
        admin_feeling_name="Fera",
        caster_id=character.pk,
        scene_id=scene.pk,
        scene_name=scene.name,
        technique_name=technique.name,
        usual_name=usual.name,
        kindled_name=kindled.name,
        usual_row_id=usual_row.pk,
        kindled_row_id=kindled_row.pk,
        abyssal_affinity_id=abyssal.pk,
        kindling_config_id=KindlingConfig.objects.get().pk,
        corruption_config_id=corruption.pk,
        drift_config_id=drift.pk,
        staff_username=STRENGTH_SPEC_STAFF,
        staff_password=staff_password,
    )


@dataclass(frozen=True)
class StrengthFightSeed:
    """What the fight test of `frontend/e2e/strength-and-cast-resonance.spec.ts` reads (#5231)."""

    character_id: int
    character_name: str
    encounter_id: int
    participant_id: int
    opponent_name: str
    technique_name: str
    usual_name: str
    kindled_name: str
    staff_username: str
    staff_password: str


#: A second caster, in a fight of her own, so the scene caster's numbers are never touched.
STRENGTH_FIGHT_CHARACTER = "Corin Vale"
STRENGTH_FIGHT_OPPONENT = "Hollow drover"
STRENGTH_FIGHT_TECHNIQUE = "Cinder Lance"
STRENGTH_FIGHT_STAFF = "strength_fight_staff"


def _strength_spec_world() -> None:
    """The resonances, affinity numbers and kindling rows a kindled caster needs, if absent.

    The same numbers the scene caster's seed sets (Abyssal's boost 150, earn rate 150 and
    coefficient 10; the third strength row at cast power 6), written without anything the
    scene seed has already written being written twice.
    """
    from world.magic.factories import (  # noqa: PLC0415
        KindlingConfigFactory,
        KindlingSituationFactory,
        ensure_conversion_pairs,
    )
    from world.magic.models import (  # noqa: PLC0415
        Affinity,
        KindledStrengthTier,
        KindlingSituation,
        Resonance,
    )
    from world.mechanics.factories import PropertyFactory  # noqa: PLC0415

    _strength_spec_resonances()
    _celestial, primal, abyssal = ensure_conversion_pairs()
    for affinity, boost, rate, coefficient in (
        (primal, 100, 100, 0),
        (abyssal, 150, 150, 10),
    ):
        affinity.kindled_boost_percent = boost
        affinity.earn_rate_percent = rate
        affinity.corruption_coefficient = coefficient
        affinity.save()
    Affinity.objects.clear_cache()
    for rank, tier_name in ((1, "Faint"), (2, "Strong"), (3, "Blazing")):
        KindledStrengthTier.objects.get_or_create(rank=rank, defaults={"name": tier_name})
    blazing = KindledStrengthTier.objects.get(rank=3)
    if blazing.min_severity == 0:
        blazing.min_severity = blazing.rank
    blazing.cast_power = 6
    blazing.earn_percent = 100
    blazing.save()
    KindlingConfigFactory()
    kindled = Resonance.objects.get(name="Praedari")
    if kindled.feeling is None:
        kindled.feeling = PropertyFactory(name="Praedari feeling")
        kindled.save(update_fields=["feeling"])
    if not KindlingSituation.objects.filter(resonance=kindled, situation="own_feeling").exists():
        KindlingSituationFactory(resonance=kindled, situation="own_feeling", strength=None)


def seed_strength_fight_spec(*, username: str) -> StrengthFightSeed:  # noqa: PLR0915 - one fight
    """A fight for *username*'s kindled caster, Corin Vale, in her declaring phase (#5231).

    Corin's Gift thread holds Sereni (Primal, leading, her usual) and Praedari (Abyssal,
    kindled at the third strength row), as the scene caster's does. She stands in a yard with
    a Hollow drover; the round is open and her technique Cinder Lance is ready, so the fight's
    cast picker offers both resonances. A staff account of its own is made so the spec can read
    the declared action back from admin without touching the scene spec's staff password.
    """
    from allauth.account.models import EmailAddress  # noqa: PLC0415
    from django.db import transaction  # noqa: PLC0415
    from django.test import override_settings  # noqa: PLC0415
    from evennia.accounts.models import AccountDB  # noqa: PLC0415
    from evennia.utils import create  # noqa: PLC0415

    from actions.factories import ActionTemplateFactory  # noqa: PLC0415
    from evennia_extensions.factories import CharacterFactory, ObjectDBFactory  # noqa: PLC0415
    from evennia_extensions.models import PlayerData  # noqa: PLC0415
    from world.areas.positioning.factories import PositionFactory  # noqa: PLC0415
    from world.areas.positioning.plummet_content import ensure_fall_content  # noqa: PLC0415
    from world.areas.positioning.services import place_in_position  # noqa: PLC0415
    from world.character_sheets.factories import CharacterSheetFactory  # noqa: PLC0415
    from world.checks.factories import CheckTypeFactory  # noqa: PLC0415
    from world.checks.models import CheckType, CheckTypeTrait  # noqa: PLC0415
    from world.combat.constants import PaceMode, ParticipantStatus  # noqa: PLC0415
    from world.combat.factories import (  # noqa: PLC0415
        CombatEncounterFactory,
        CombatOpponentFactory,
        CombatParticipantFactory,
    )
    from world.combat.models import CombatParticipant, ThreatPool  # noqa: PLC0415
    from world.combat.services import begin_declaration_phase  # noqa: PLC0415
    from world.conditions.factories import (  # noqa: PLC0415
        ConditionInstanceFactory,
        ConditionTemplateFactory,
    )
    from world.conditions.models import DamageSuccessLevelMultiplier  # noqa: PLC0415
    from world.magic.factories import (  # noqa: PLC0415
        CharacterAnimaFactory,
        CharacterAuraFactory,
        CharacterResonanceFactory,
        CharacterTechniqueFactory,
        EffectTypeFactory,
        GiftFactory,
        TechniqueFactory,
    )
    from world.magic.models import KindledStrengthTier, Resonance  # noqa: PLC0415
    from world.magic.models.modifier_level import CastPowerLevel  # noqa: PLC0415
    from world.magic.specialization.services import provision_latent_gift_thread  # noqa: PLC0415
    from world.mechanics.maneuver_effects import ensure_maneuver_effects  # noqa: PLC0415
    from world.roster.factories import RosterEntryFactory, RosterTenureFactory  # noqa: PLC0415
    from world.roster.models import RosterEntry  # noqa: PLC0415
    from world.scenes.constants import RoundStatus  # noqa: PLC0415
    from world.seeds.checks import seed_check_resolution_tables  # noqa: PLC0415
    from world.skills.factories import MagicSkillFactory  # noqa: PLC0415
    from world.traits.models import CharacterTraitValue, Trait, TraitType  # noqa: PLC0415
    from world.vitals.models import CharacterVitals  # noqa: PLC0415
    from world.vitals.seeds import ensure_foundational_capabilities  # noqa: PLC0415
    from world.vitals.services import get_vitals_consequence_config  # noqa: PLC0415

    staff_password = secrets.token_urlsafe(18)
    staff = AccountDB.objects.filter(username=STRENGTH_FIGHT_STAFF).first()
    if staff is None:
        staff = create.create_account(
            STRENGTH_FIGHT_STAFF, "strength_fight_staff@example.com", staff_password
        )
    staff.set_password(staff_password)
    staff.is_staff = True
    staff.is_superuser = True
    staff.save()
    EmailAddress.objects.update_or_create(
        user=staff,
        email="strength_fight_staff@example.com",
        defaults={"primary": True, "verified": True},
    )

    account = AccountDB.objects.get(username=username)
    with override_settings(SEED_SAMPLE_CONTENT=True):
        ensure_foundational_capabilities()
        ensure_fall_content()
    with transaction.atomic():
        _strength_spec_world()
        entry = RosterEntry.objects.filter(
            character_sheet__character__db_key=STRENGTH_FIGHT_CHARACTER
        ).first()
        if entry is None:
            seed_check_resolution_tables()
            ensure_maneuver_effects()
            DamageSuccessLevelMultiplier.objects.get_or_create(
                min_success_level=1, defaults={"multiplier": 1, "label": "Full"}
            )
            get_vitals_consequence_config()
            CastPowerLevel.objects.get_or_create(min_power=0, defaults={"level": 1})
            willpower, _ = Trait.objects.get_or_create(
                name="willpower", defaults={"trait_type": TraitType.STAT}
            )
            magic_check = CheckType.objects.filter(name="Cinder Magic Cast").first()
            if magic_check is None:
                magic_check = CheckTypeFactory(name="Cinder Magic Cast")
            CheckTypeTrait.objects.get_or_create(check_type=magic_check, trait=willpower)

            player_data, _ = PlayerData.objects.get_or_create(account=account)
            room = ObjectDBFactory(
                db_key="The Ember Yard", db_typeclass_path="typeclasses.rooms.Room"
            )
            character = CharacterFactory(db_key=STRENGTH_FIGHT_CHARACTER, location=room)
            sheet = CharacterSheetFactory(character=character)
            entry = RosterEntryFactory(character_sheet=sheet)
            RosterTenureFactory(roster_entry=entry, player_data=player_data, end_date=None)
            character.db_account = account
            character.save()
            # The playable puppet lock, so the web client can enter the world as her.
            account.at_post_create_character(character)
            CharacterVitals.objects.create(
                character_sheet=sheet, health=100, max_health=100, base_max_health=100
            )
            CharacterAnimaFactory(character=sheet, current=50, maximum=50)
            CharacterTraitValue.objects.create(character=sheet, trait=willpower, value=30)
            cinder_magic = MagicSkillFactory(name="Cinder Magic")
            CharacterTraitValue.objects.create(character=sheet, trait=cinder_magic, value=30)

            usual = Resonance.objects.get(name="Sereni")
            kindled = Resonance.objects.get(name="Praedari")
            CharacterAuraFactory(character=sheet, celestial="0", primal="80", abyssal="20")
            CharacterResonanceFactory(
                character_sheet=sheet, resonance=usual, balance=10, lifetime_earned=80
            )
            CharacterResonanceFactory(
                character_sheet=sheet, resonance=kindled, balance=10, lifetime_earned=20
            )
            gift = GiftFactory(name="Embercrown")
            technique = TechniqueFactory(
                name=STRENGTH_FIGHT_TECHNIQUE,
                skill=cinder_magic,
                gift=gift,
                anima_cost=1,
                intensity=20,
                control=40,
                effect_type=EffectTypeFactory(name="Cinder effect", base_power=10),
                # Named: a template is found by its name, and the factory's counter names
                # ("Template0") are shared with every other seed's first template.
                action_template=ActionTemplateFactory(
                    name="Cinder Lance cast", check_type=magic_check
                ),
            )
            CharacterTechniqueFactory(character=sheet, technique=technique)
            provision_latent_gift_thread(sheet, gift, resonances=[usual, kindled])
            # Kindled at the third strength row: a condition carrying her Praedari feeling at
            # the severity that row is reached at.
            blazing = KindledStrengthTier.objects.get(rank=3)
            carrier = ConditionTemplateFactory(name="Praedari feeling carrier")
            carrier.properties.add(kindled.feeling)
            ConditionInstanceFactory(
                target=character, condition=carrier, severity=blazing.min_severity
            )

            yard = PositionFactory(room=room, name="Yard")
            place_in_position(character, yard)
            encounter = CombatEncounterFactory(
                room=room,
                round_number=0,
                status=RoundStatus.BETWEEN_ROUNDS,
                pace_mode=PaceMode.READY,
            )
            CombatParticipantFactory(
                encounter=encounter, character_sheet=sheet, status=ParticipantStatus.ACTIVE
            )
            # Its own pool by name: the factory's default pool is named by a per-process
            # counter ("Threat Pool 0"), which the thrown-strike seed's archer already took in
            # this database, and a pool's name is unique.
            drover_pool, _ = ThreatPool.objects.get_or_create(name="Ember Yard Drover Pool")
            drover = CombatOpponentFactory(
                encounter=encounter,
                threat_pool=drover_pool,
                name=STRENGTH_FIGHT_OPPONENT,
                health=200,
                max_health=200,
                soak_value=1,
            )
            place_in_position(drover.objectdb, yard)
            begin_declaration_phase(encounter)
        sheet = entry.character_sheet
        participant = CombatParticipant.objects.filter(character_sheet=sheet).latest("pk")
    return StrengthFightSeed(
        character_id=sheet.character_id,
        character_name=STRENGTH_FIGHT_CHARACTER,
        encounter_id=participant.encounter_id,
        participant_id=participant.pk,
        opponent_name=STRENGTH_FIGHT_OPPONENT,
        technique_name=STRENGTH_FIGHT_TECHNIQUE,
        usual_name="Sereni",
        kindled_name="Praedari",
        staff_username=STRENGTH_FIGHT_STAFF,
        staff_password=staff_password,
    )


@dataclass(frozen=True)
class AttestedResonanceSeed:
    """What `frontend/e2e/evidence/attested-resonance-5327.spec.ts` reads back (#5327).

    Daven, Hale, Ilsa, Brannoc and Marek live in the main scene. Each frame that needs a state
    the others would change (a worn target, a week of marks already made, a Primal gain, an
    ephemeral scene, a refused journal mark) has a cast of its own, with the same names, so every
    frame is taken from its own untouched state. A cast's accounts all log in with
    ``player_password``.
    """

    scene_id: int
    scene_name: str
    daven_name: str
    daven_sheet_id: int
    #: Daven's two acts that wait to be marked: one with a Cruelty suggestion, one without.
    act_intimidated_id: int
    act_cellar_id: int
    #: The Mercy reward on a marked pose of Daven's, which the scene's GM undoes in the spec.
    marked_grant_id: int
    marked_pose_text: str
    bell_pose_text: str
    moment_type_label: str
    mission_instance_id: int
    mission_name: str
    abyssal_affinity_id: int
    cruelty_id: int
    cruelty_description: str
    mercy_description: str
    fury_description: str
    weekly_row_count: int
    kindling_config_id: int
    gain_source_stat_id: int
    player_password: str
    #: Hale of the main scene, who reads the line a target reads.
    hale_username: str
    #: The witness (Ilsa, a scene co-owner who is not its GM) and the poser of the bell pose.
    witness_username: str
    bell_poser_username: str
    gm_username: str
    gm_password: str
    staff_username: str
    staff_password: str
    #: A Daven whose target has 3 of fatigue room left (a shrunk gain), and that target's account.
    shrunk_poser_username: str
    shrunk_target_username: str
    shrunk_act_id: int
    #: A Daven whose target has no room left (a refused mark).
    refused_poser_username: str
    refused_act_id: int
    #: A Daven who has already marked four acts this game week (the fifth pays less).
    week_poser_username: str
    week_act_id: int
    #: Tamsin, who struck a raider while surrounded (a Primal mark that tires her).
    tamsin_username: str
    tamsin_act_id: int
    #: Wren on the road in an ephemeral scene, with two acts a journal entry can point at.
    wren_username: str
    wren_tended_act_id: int
    wren_fine_act_id: int
    #: A Wren whose week of marks is spent (a journal mark that is refused).
    wren_refused_username: str
    wren_refused_act_id: int


#: Invented names for the #5327 evidence run. No game character, resonance or place.
ATTESTED_PASSWORD = "TestPass123!"  # noqa: S105 - the public password of every seeded e2e player
ATTESTED_ROOM = "The Lantern"
ATTESTED_SCENE = "Supper at the Lantern"
ATTESTED_POSER = "Daven"
ATTESTED_TARGET = "Hale"
ATTESTED_WITNESS = "Ilsa"
ATTESTED_BELL_POSER = "Brannoc"
ATTESTED_GM = "Marek"
ATTESTED_ACCOUNTS = {
    ATTESTED_TARGET: "attested_hale",
    ATTESTED_WITNESS: "attested_ilsa",
    ATTESTED_BELL_POSER: "attested_brannoc",
}
ATTESTED_GM_ACCOUNT = "attested_gm"
ATTESTED_STAFF = "attested_staff"
ATTESTED_MISSION = "The smugglers at the tollgate"
ATTESTED_MOMENT_TYPE = "Defiant stand"
ATTESTED_BELL_POSE = "sets the cracked bell back on its hook and does not look at the empty pew."
ATTESTED_MARKED_POSE = "catches the child by the collar and lets her see the knife, then laughs."
#: The people the evidence run seeds, by name, so a second run clears all of them.
ATTESTED_CAST = ("Daven", "Hale", "Ilsa", "Brannoc", "Marek", "Tamsin", "Wren")
#: The scenes it seeds, so a second run clears the poses written in each.
ATTESTED_SCENE_NAMES = (
    ATTESTED_SCENE,
    "Supper at the Lantern, shrunk table",
    "Supper at the Lantern, refused table",
    "Supper at the Lantern, week table",
    "Raiders at the Cinder Gate",
    "Wren on the road",
)
#: Each resonance with its affinity and the description that reads as help text under the picker.
ATTESTED_RESONANCES = (
    (
        "Cruelty",
        "Abyssal",
        "Pleasure taken from another person's fear or pain. Mark it when your character hurts "
        "someone on purpose and enjoys it. Do not mark it for a fight that was forced on her "
        "or a hard choice she regretted.",
    ),
    (
        "Dread",
        "Abyssal",
        "The cold weight of what is about to happen. Mark it when your character makes others "
        "feel it coming. Do not mark it for a fear she feels herself.",
    ),
    (
        "Mercy",
        "Celestial",
        "Help given to someone who cannot repay it, at a cost to your character. Mark it when "
        "she gives freely. Do not mark it for a favor she expects returned.",
    ),
    (
        "Valor",
        "Celestial",
        "Courage shown for someone else's sake. Mark it when your character steps forward "
        "while afraid. Do not mark it for a risk taken for her own gain.",
    ),
    (
        "Fury",
        "Primal",
        "What your character feels when she is cornered and will not go down. Mark it when "
        "the feeling drives the act. Do not mark it for a plan she made calmly.",
    ),
    (
        "Grief",
        "Primal",
        "The ache of a loss still being felt. Mark it when the loss drives what she does. "
        "Do not mark it for a sad scene she only watches.",
    ),
)
#: The seven rows of the demo's weekly table: gained at least, percent paid.
ATTESTED_WEEKLY_TABLE = ((0, 100), (9, 85), (18, 70), (27, 55), (36, 40), (54, 20), (72, 0))


def _refuse_unless_rt_database() -> None:
    """Refuse unless both ``DATABASE_URL`` and the live connection name an ``rt_`` database."""
    import os  # noqa: PLC0415
    from urllib.parse import urlparse  # noqa: PLC0415

    from django.db import connection  # noqa: PLC0415

    named = {
        "DATABASE_URL": urlparse(os.environ.get("DATABASE_URL", "")).path.lstrip("/"),
        "the connected database": str(connection.settings_dict["NAME"]),
    }
    for source, name in named.items():
        if not name.startswith("rt_"):
            msg = f"Refusing to seed: {source} names {name!r}, not a throwaway rt_ database."
            raise RuntimeError(msg)


def _attested_player_account(username: str) -> AccountDB:
    """A pre-verified player account that logs in with the shared e2e password."""
    from evennia.accounts.models import AccountDB  # noqa: PLC0415

    from world.seeds.test_account import seed_test_account  # noqa: PLC0415

    seed_test_account(
        username=username, email=f"{username}@example.com", password=ATTESTED_PASSWORD
    )
    return AccountDB.objects.get(username=username)


def _attested_privileged_account(username: str, *, staff: bool) -> tuple[AccountDB, str]:
    """An account with a fresh password: a staff superuser, or a player who is only a GM."""
    from evennia.accounts.models import AccountDB  # noqa: PLC0415

    from world.seeds.test_account import seed_test_account  # noqa: PLC0415

    password = secrets.token_urlsafe(18)
    seed_test_account(username=username, email=f"{username}@example.com", password=password)
    account = AccountDB.objects.get(username=username)
    account.set_password(password)
    account.is_staff = staff
    account.is_superuser = staff
    account.save()
    return account, password


def _attested_affinities_and_resonances() -> dict[str, Resonance]:
    """The three affinities with a verb, a gain fatigue and a skill each, and the six resonances.

    Abyssal reads "gloat" and costs 6, Celestial "inspire" and 5, Primal "blaze" and 4, each
    with its skill (Villainy, Heroism, Reflection) and an earn rate of 100 percent. Returns the
    resonances by name.
    """
    from world.magic.models import Affinity, Resonance  # noqa: PLC0415
    from world.skills.models import Skill  # noqa: PLC0415
    from world.traits.models import TraitCategory  # noqa: PLC0415

    celestial, primal, abyssal = _canonical_affinities()
    by_name = {row.name: row for row in (celestial, primal, abyssal)}
    for affinity, verb, fatigue, skill_name, tooltip in (
        (abyssal, "gloat", 6, "Villainy", "Magic worked at another's cost."),
        (celestial, "inspire", 5, "Heroism", "Magic worked for those who cannot repay it."),
        (primal, "blaze", 4, "Reflection", "Magic worked from what the caster feels."),
    ):
        skill = Skill.objects.filter(name=skill_name).first() or Skill.objects.create(
            name=skill_name, category=TraitCategory.MAGIC, tooltip=tooltip
        )
        affinity.claim_verb = verb
        affinity.gain_fatigue = fatigue
        affinity.earn_rate_percent = 100
        affinity.skill = skill
        affinity.save()
    Affinity.objects.clear_cache()
    resonances: dict[str, Resonance] = {}
    for name, affinity_name, description in ATTESTED_RESONANCES:
        resonance, _ = Resonance.objects.update_or_create(
            name=name, defaults={"affinity": by_name[affinity_name], "description": description}
        )
        resonances[name] = resonance
    return resonances


def _attested_awards_and_tables() -> tuple[CheckOutcome, KindledStrengthTier, int]:
    """Strength tiers, what an act is worth, the weekly table and the days an act stays listed.

    Faint pays half of an award, Strong three quarters, Blazing all of it. A Partial Success is
    worth 3, a Success 7 and a Critical Success 12. Returns the Success tier, the Blazing
    strength tier and the kindling configuration's id.
    """
    from world.magic.models import (  # noqa: PLC0415
        KindledDeedAward,
        KindledStrengthTier,
        KindlingConfig,
        WeeklyMarkReturn,
    )
    from world.traits.services import ensure_canonical_check_outcome  # noqa: PLC0415

    tiers: dict[str, KindledStrengthTier] = {}
    for rank, name, earn in ((1, "Faint", 50), (2, "Strong", 75), (3, "Blazing", 100)):
        tier, _ = KindledStrengthTier.objects.update_or_create(
            rank=rank, defaults={"name": name, "earn_percent": earn}
        )
        tiers[name] = tier
    for outcome_name, amount in (("Partial Success", 3), ("Success", 7), ("Critical Success", 12)):
        KindledDeedAward.objects.update_or_create(
            outcome_tier=ensure_canonical_check_outcome(outcome_name),
            defaults={"amount": amount},
        )
    for gained_at_least, percent_paid in ATTESTED_WEEKLY_TABLE:
        WeeklyMarkReturn.objects.update_or_create(
            gained_at_least=gained_at_least, defaults={"percent_paid": percent_paid}
        )
    config, _ = KindlingConfig.objects.update_or_create(pk=1, defaults={"recorded_act_days": 90})
    return ensure_canonical_check_outcome("Success"), tiers["Blazing"], config.pk


def _attested_bonus_check() -> tuple[CheckType, CheckType, CheckType, int]:
    """The bonus check, what each result adds to a gain, and the stat a marked act rolls.

    The bonus check weighs Presence alone; every one of the five results adds 30 percent to a
    gain, so a player always reads "Your Villainy check added 30 percent". An act with no check
    of its own rolls Presence too, through the gain source stat row. Returns the bonus check
    type, the Intimidate check type, the Persuasion check type and the source stat row's id.
    """
    from decimal import Decimal  # noqa: PLC0415

    from world.checks.models import CheckCategory, CheckType, CheckTypeTrait  # noqa: PLC0415
    from world.magic.constants import GainSource  # noqa: PLC0415
    from world.magic.models import ResonanceCheckAward, ResonanceGainSourceStat  # noqa: PLC0415
    from world.traits.constants import CANONICAL_OUTCOME_LEVELS  # noqa: PLC0415
    from world.traits.models import Trait, TraitCategory, TraitType  # noqa: PLC0415
    from world.traits.services import ensure_canonical_check_outcome  # noqa: PLC0415

    presence, _ = Trait.objects.get_or_create(
        name="presence",
        defaults={
            "trait_type": TraitType.STAT,
            "category": TraitCategory.SOCIAL,
            "description": "Force of personality.",
        },
    )
    magic, _ = CheckCategory.objects.get_or_create(name="Magic")
    social, _ = CheckCategory.objects.get_or_create(name="Social")
    checks: dict[str, CheckType] = {}
    for name, category in (
        ("Resonance bonus", magic),
        ("Intimidate", social),
        ("Persuasion", social),
    ):
        check, _ = CheckType.objects.get_or_create(name=name, category=category)
        CheckTypeTrait.objects.update_or_create(
            check_type=check, trait=presence, defaults={"weight": Decimal("1.0")}
        )
        checks[name] = check
    for outcome_name in CANONICAL_OUTCOME_LEVELS:
        ResonanceCheckAward.objects.update_or_create(
            outcome_tier=ensure_canonical_check_outcome(outcome_name),
            defaults={"gain_bonus_percent": 30, "spend_worth_percent": 100},
        )
    source_stat, _ = ResonanceGainSourceStat.objects.update_or_create(
        source=GainSource.MARKED_ACT, defaults={"stat": presence}
    )
    return checks["Resonance bonus"], checks["Intimidate"], checks["Persuasion"], source_stat.pk


def _attested_player(
    name: str,
    account: AccountDB,
    room: ObjectDB,  # noqa: OBJECTDB_PARAM - a factory character's location; no RoomProfile
) -> CharacterSheet:
    """The sheet of *name*, played by *account* in *room*, and the account's selected character."""
    from evennia_extensions.models import PlayerData  # noqa: PLC0415
    from world.roster.services.selection import set_selected_entry  # noqa: PLC0415

    tenure = _played_character(account, name, room)
    set_selected_entry(PlayerData.objects.get(account=account), tenure.roster_entry)
    return tenure.roster_entry.character_sheet


def _attested_scene(
    room: ObjectDB,  # noqa: OBJECTDB_PARAM - the room a factory scene is attached to
    seats: tuple[tuple[AccountDB, bool, bool], ...],
    *,
    name: str = ATTESTED_SCENE,
    ephemeral: bool = False,
) -> Scene:
    """The live scene *name* in *room*, with one seat per (account, GM, owner).

    A scene stores its poses unless it is ephemeral, which stores nothing and warns a player who
    reaches for a resonance in it.
    """
    from world.scenes.constants import ScenePrivacyMode  # noqa: PLC0415
    from world.scenes.factories import SceneFactory  # noqa: PLC0415
    from world.scenes.interaction_services import invalidate_active_scene_cache  # noqa: PLC0415
    from world.scenes.models import Scene, SceneParticipation  # noqa: PLC0415

    scene = Scene.objects.filter(name=name).first() or SceneFactory(
        room=room, name=name, description="Supper in a lamplit room.", is_active=True
    )
    scene.privacy_mode = ScenePrivacyMode.EPHEMERAL if ephemeral else ScenePrivacyMode.PUBLIC
    scene.is_active = True
    scene.save(update_fields=["privacy_mode", "is_active"])
    invalidate_active_scene_cache(room)
    for account, is_gm, is_owner in seats:
        SceneParticipation.objects.update_or_create(
            scene=scene,
            account=account,
            defaults={"is_gm": is_gm, "is_owner": is_owner, "left_at": None},
        )
    return scene


def _attested_room(name: str) -> ObjectDB:  # noqa: OBJECTDB_PARAM - a room has no narrower model
    """The room *name*, made once."""
    from evennia.objects.models import ObjectDB  # noqa: PLC0415
    from evennia.utils import create  # noqa: PLC0415

    return ObjectDB.objects.filter(
        db_key=name, db_typeclass_path="typeclasses.rooms.Room"
    ).first() or create.create_object("typeclasses.rooms.Room", key=name)


def _attested_wipe() -> None:
    """Clear what an earlier run left behind for every character the run seeds.

    Poses (and the endorsements and tags on them), journal entries, acts, grants, resonances,
    the stored private lines and their deliveries, the week's journal counter and the mission
    run all go, so a second run starts exactly like the first. The rows are removed through the
    model's own delete, which reaches the identity map; the characters, rooms, scenes and
    accounts stay.
    """
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
    from world.journals.models import JournalEntry, WeeklyJournalXP  # noqa: PLC0415
    from world.magic.models import (  # noqa: PLC0415
        CharacterResonance,
        DramaticMomentTag,
        RecordedAct,
        ResonanceGrant,
    )
    from world.missions.models import MissionInstance  # noqa: PLC0415
    from world.narrative.models import NarrativeMessage, NarrativeMessageDelivery  # noqa: PLC0415
    from world.scenes.models import Interaction, Scene  # noqa: PLC0415

    sheets = list(CharacterSheet.objects.filter(character__db_key__in=ATTESTED_CAST))
    scenes = list(Scene.objects.filter(name__in=ATTESTED_SCENE_NAMES))
    # The acts go before the grants they hold, and the grants before the tags that paid them.
    MissionInstance.objects.filter(participants__character__in=sheets).delete()
    RecordedAct.objects.filter(character_sheet__in=sheets).delete()
    ResonanceGrant.objects.filter(character_sheet__in=sheets).delete()
    DramaticMomentTag.objects.filter(character_sheet__in=sheets).delete()
    Interaction.objects.filter(scene__in=scenes).delete()
    JournalEntry.objects.filter(author__in=sheets).delete()
    WeeklyJournalXP.objects.filter(character_sheet__in=sheets).delete()
    CharacterResonance.objects.filter(character_sheet__in=sheets).delete()
    NarrativeMessageDelivery.objects.filter(recipient_character_sheet__in=sheets).delete()
    NarrativeMessage.objects.filter(deliveries__isnull=True).delete()


def _attested_fatigue(sheet: CharacterSheet, *, stat: str, category: str, room: int | None) -> None:
    """Give *sheet* 100 in the *stat* that sets the *category* pool, and every pool to start empty.

    With *room* given, the *category* pool is worn until exactly that much more can be added
    before it reaches Exhausted (capacity minus current minus 1), as a target who had little
    left (or nothing, at 0) stands.
    """
    from actions.constants import ActionCategory  # noqa: PLC0415
    from world.fatigue.services import get_or_create_fatigue_pool  # noqa: PLC0415
    from world.traits.models import CharacterTraitValue  # noqa: PLC0415
    from world.traits.services import ensure_stat_trait  # noqa: PLC0415

    capacity = 100
    CharacterTraitValue.objects.update_or_create(
        character=sheet, trait=ensure_stat_trait(stat), defaults={"value": capacity}
    )
    pool = get_or_create_fatigue_pool(sheet)
    for pool_category in (ActionCategory.PHYSICAL, ActionCategory.SOCIAL, ActionCategory.MENTAL):
        pool.set_current(pool_category, 0)
    if room is not None:
        pool.set_current(category, capacity - 1 - room)
    pool.save()


def _attested_act(  # noqa: PLR0913 - one act: whose, what, how worth, aimed at whom, suggested
    sheet: CharacterSheet,
    label: str,
    *,
    category: str,
    success: CheckOutcome,
    minutes_ago: int,
    act_phrase: str = "",
    check_type: CheckType | None = None,
    target: CharacterSheet | None = None,
    suggestion: tuple[Resonance, KindledStrengthTier, str] | None = None,
) -> RecordedAct:
    """One act of *sheet*'s that waits to be marked, written *minutes_ago* minutes ago.

    *suggestion* is the (resonance, strength, reason) a situation suggested for it, if any.
    """
    from datetime import timedelta  # noqa: PLC0415

    from django.utils import timezone  # noqa: PLC0415

    from world.magic.models import RecordedAct, RecordedActSuggestion  # noqa: PLC0415

    act = RecordedAct.objects.create(
        character_sheet=sheet,
        label=label,
        act_phrase=act_phrase,
        outcome=success,
        check_type=check_type,
        target_sheet=target,
        fatigue_category=category,
    )
    if suggestion is not None:
        resonance, strength, reason = suggestion
        RecordedActSuggestion.objects.create(
            act=act, resonance=resonance, strength=strength, reason=reason
        )
    # created_at is set once on creation; the instances are idmapped, so they are saved.
    act.created_at = timezone.now() - timedelta(minutes=minutes_ago)
    act.save(update_fields=["created_at"])
    return act


def _attested_earlier_pose(sheet: CharacterSheet, scene: Scene, text: str) -> None:
    """A pose *sheet* wrote in *scene* before the one the spec posts, so the next is no entrance."""
    from world.scenes.constants import InteractionMode  # noqa: PLC0415
    from world.scenes.interaction_services import create_interaction  # noqa: PLC0415

    create_interaction(  # noqa: UNDELIVERED - a seed row, read from the feed
        persona=sheet.primary_persona, content=text, mode=InteractionMode.POSE, scene=scene
    )


def _attested_week_marks(
    sheet: CharacterSheet, resonance: Resonance, amounts: tuple[int, ...]
) -> None:
    """Marks *sheet* already made this game week, one grant of each amount.

    Written through ``grant_resonance`` with the bonus check off, so each is exactly its amount
    and the weekly table counts them. Run while the bonus check is off.
    """
    from world.magic.constants import GainSource  # noqa: PLC0415
    from world.magic.services.resonance import grant_resonance  # noqa: PLC0415

    for amount in amounts:
        grant_resonance(
            sheet,
            resonance,
            amount,
            source=GainSource.MARKED_ACT,
            deed_label="An earlier mark this week",
        )


def _attested_duel(  # noqa: PLR0913 - one cast: who, how worn the target is, the week so far
    tag: str,
    resonances: dict[str, Resonance],
    success: CheckOutcome,
    blazing: KindledStrengthTier,
    intimidate: CheckType,
    *,
    target_room: int | None,
    week_marks: tuple[int, ...],
) -> tuple[AccountDB, AccountDB, RecordedAct]:
    """A Daven and a Hale of their own in a scene of their own, and Daven's act against Hale.

    *target_room* is how much social fatigue Hale can still take (None: all of it) and
    *week_marks* the marks Daven already made this game week. Returns the two accounts and
    Intimidated Hale, which carries a Cruelty suggestion.
    """
    from actions.constants import ActionCategory  # noqa: PLC0415

    poser_account = _attested_player_account(f"attested_daven_{tag}")
    target_account = _attested_player_account(f"attested_hale_{tag}")
    room = _attested_room(f"The Lantern, {tag} table")
    daven = _attested_player(ATTESTED_POSER, poser_account, room)
    hale = _attested_player(ATTESTED_TARGET, target_account, room)
    scene = _attested_scene(
        room,
        ((poser_account, False, False), (target_account, False, False)),
        name=f"Supper at the Lantern, {tag} table",
    )
    _attested_earlier_pose(daven, scene, "pulls out a chair and sits down across from Hale.")
    _attested_fatigue(hale, stat="composure", category=ActionCategory.SOCIAL, room=target_room)
    act = _attested_act(
        daven,
        "Intimidated Hale",
        act_phrase="Intimidated",
        category=ActionCategory.SOCIAL,
        success=success,
        minutes_ago=2,
        check_type=intimidate,
        target=hale,
        suggestion=(resonances["Cruelty"], blazing, "You left Hale in the grip of Terror."),
    )
    _attested_week_marks(daven, resonances["Dread"], week_marks)
    return poser_account, target_account, act


def _attested_tamsin(
    resonances: dict[str, Resonance], success: CheckOutcome, blazing: KindledStrengthTier
) -> tuple[AccountDB, RecordedAct]:
    """Tamsin in a scene of her own, who struck a raider while surrounded.

    Her act is physical and suggests Fury ("You are surrounded."). Primal tires the character
    who gains, so she has the stamina to pay for it.
    """
    from actions.constants import ActionCategory  # noqa: PLC0415

    account = _attested_player_account("attested_tamsin")
    room = _attested_room("The Cinder Gate")
    tamsin = _attested_player("Tamsin", account, room)
    scene = _attested_scene(room, ((account, False, False),), name="Raiders at the Cinder Gate")
    _attested_earlier_pose(tamsin, scene, "plants her feet in the gateway and draws her knife.")
    _attested_fatigue(tamsin, stat="stamina", category=ActionCategory.PHYSICAL, room=None)
    act = _attested_act(
        tamsin,
        "Struck the raider",
        category=ActionCategory.PHYSICAL,
        success=success,
        minutes_ago=1,
        suggestion=(resonances["Fury"], blazing, "You are surrounded."),
    )
    return account, act


def _attested_wren(  # noqa: PLR0913 - one Wren: her account, place, week and acts
    username: str,
    room_name: str,
    resonances: dict[str, Resonance],
    success: CheckOutcome,
    blazing: KindledStrengthTier,
    *,
    ephemeral_scene: bool,
    week_marks: tuple[int, ...],
) -> tuple[AccountDB, RecordedAct, RecordedAct]:
    """A Wren on the road, with two acts her journal can point at.

    Tended the stranger (two days ago, physical) suggests Mercy ("Someone here is in trouble.")
    and Paid the tollgate fine (five days ago) suggests nothing. Celestial tires the character
    who acted, so she has the stamina to pay. With *ephemeral_scene* the road holds a scene that
    stores nothing; *week_marks* are the marks she already made this game week.
    """
    from actions.constants import ActionCategory  # noqa: PLC0415

    account = _attested_player_account(username)
    room = _attested_room(room_name)
    wren = _attested_player("Wren", account, room)
    if ephemeral_scene:
        # A scene that stores nothing cannot be held in a room anyone can enter.
        from world.areas.services import get_room_profile  # noqa: PLC0415

        profile = get_room_profile(room)
        profile.is_public = False
        profile.save(update_fields=["is_public"])
        _attested_scene(room, ((account, False, False),), name="Wren on the road", ephemeral=True)
    _attested_fatigue(wren, stat="stamina", category=ActionCategory.PHYSICAL, room=None)
    tended = _attested_act(
        wren,
        "Tended the stranger",
        category=ActionCategory.PHYSICAL,
        success=success,
        minutes_ago=2 * 24 * 60,
        suggestion=(resonances["Mercy"], blazing, "Someone here is in trouble."),
    )
    fine = _attested_act(
        wren,
        "Paid the tollgate fine",
        category=ActionCategory.SOCIAL,
        success=success,
        minutes_ago=5 * 24 * 60,
    )
    _attested_week_marks(wren, resonances["Mercy"], week_marks)
    return account, tended, fine


def _attested_mission(
    daven: CharacterSheet, mercy: Resonance, persuasion: CheckType
) -> MissionInstance:
    """A mission Daven is on, whose beat has an option that pays Mercy at once.

    The first option ("Let the smugglers go and pay their fine yourself", Persuasion, risk 2)
    carries a theme that names Mercy, so the beat says what it pays before he picks; the second
    ("Turn them in to the tollwarden", Law, no risk) carries none.
    """
    from world.checks.models import CheckCategory, CheckType, Consequence  # noqa: PLC0415
    from world.covenants.perks.constants import Situation  # noqa: PLC0415
    from world.magic.models import KindlingSituation  # noqa: PLC0415
    from world.missions.constants import (  # noqa: PLC0415
        ConflictMode,
        MissionVisibility,
        OptionKind,
        OptionSource,
    )
    from world.missions.factories import (  # noqa: PLC0415
        MissionNodeFactory,
        MissionOptionFactory,
        MissionOptionRouteFactory,
        MissionTemplateFactory,
    )
    from world.missions.models import (  # noqa: PLC0415
        MissionInstance,
        MissionOptionRoute,
        MissionTheme,
    )
    from world.missions.services.run import staff_assign_mission  # noqa: PLC0415
    from world.traits.constants import CANONICAL_OUTCOME_LEVELS  # noqa: PLC0415
    from world.traits.services import ensure_canonical_check_outcome  # noqa: PLC0415

    theme, _ = MissionTheme.objects.update_or_create(
        name="Mercy to the desperate",
        defaults={
            "description": "Sparing people who cannot pay for what they did.",
            "player_text": "This option is about sparing them.",
        },
    )
    KindlingSituation.objects.update_or_create(
        resonance=mercy,
        situation=Situation.MISSION_THEME,
        mission_theme=theme,
        defaults={"strength": 2, "is_active": True},
    )
    social, _ = CheckCategory.objects.get_or_create(name="Social")
    law, _ = CheckType.objects.get_or_create(name="Law", category=social)
    template = MissionTemplateFactory(
        name=ATTESTED_MISSION,
        summary="Smugglers are caught at the tollgate and cannot pay the fine.",
        level_band_min=0,
        level_band_max=99,
        risk_tier=1,
        visibility=MissionVisibility.OPEN,
    )
    if not template.nodes.exists():
        entry = MissionNodeFactory(
            template=template,
            key="entry",
            is_entry=True,
            conflict_mode=ConflictMode.GROUP_VOTE,
            flavor_text=(
                "Four smugglers sit in the road beside a tipped cart, and the tollwarden's "
                "lantern is coming up the hill. They cannot pay the fine."
            ),
        )
        done = MissionNodeFactory(
            template=template,
            key="done",
            conflict_mode=ConflictMode.GROUP_VOTE,
            flavor_text="The road is quiet again.",
        )
        for order, key, label, check_type, risk in (
            (
                0,
                "let-them-go",
                "Let the smugglers go and pay their fine yourself",
                persuasion,
                2,
            ),
            (1, "turn-them-in", "Turn them in to the tollwarden", law, 0),
        ):
            option = MissionOptionFactory(
                node=entry,
                order=order,
                key=key,
                option_kind=OptionKind.CHECK,
                source_kind=OptionSource.AUTHORED,
                authored_check_type=check_type,
                authored_base_risk=risk,
                authored_ic_framing=label,
            )
            if order == 0:
                option.themes.add(theme)
            for tier_name in CANONICAL_OUTCOME_LEVELS:
                tier = ensure_canonical_check_outcome(tier_name)
                consequence, _ = Consequence.objects.get_or_create(
                    outcome_tier=tier, label=f"The tollgate goes quiet ({tier_name})"
                )
                MissionOptionRouteFactory(
                    option=option, outcome_tier=tier, target_node=done, consequence=consequence
                )
    outcome_texts = {
        "let-them-go": (
            "You pay the smugglers' fine from your own purse, and they are gone before the "
            "tollwarden's lantern reaches the cart."
        ),
        "turn-them-in": "The tollwarden takes the smugglers away, and the road is quiet again.",
    }
    for route in MissionOptionRoute.objects.filter(option__node__template=template).select_related(
        "option"
    ):
        route.outcome_text = outcome_texts[route.option.key]
        route.save(update_fields=["outcome_text"])
    instance = MissionInstance.objects.filter(
        template=template, participants__character=daven
    ).first()
    return instance or staff_assign_mission(template, daven.character)


def _attested_daven_state(  # noqa: PLR0913 - Daven's world: scene, target, resonances, checks
    daven: CharacterSheet,
    hale: CharacterSheet,
    scene: Scene,
    resonances: dict[str, Resonance],
    success: CheckOutcome,
    blazing: KindledStrengthTier,
    intimidate: CheckType,
) -> tuple[RecordedAct, RecordedAct, RecordedAct]:
    """Daven's aura, his two acts that wait, and a pose of his that already carries a Mercy mark.

    Intimidated Hale (Success, aimed at Hale) carries a Cruelty suggestion; Searched the cellar
    carries none. The marked pose is "catches the child ...", its act Frightened the child, its
    reward 8 Mercy written through ``grant_resonance`` while the bonus check is off, so it adds
    nothing. Returns the two waiting acts and the marked one.
    """
    from actions.constants import ActionCategory  # noqa: PLC0415
    from world.magic.constants import GainSource  # noqa: PLC0415
    from world.magic.factories import CharacterAuraFactory  # noqa: PLC0415
    from world.magic.models import (  # noqa: PLC0415
        CharacterAura,
        CharacterResonance,
        RecordedAct,
        ResonanceGrant,
    )
    from world.magic.services.resonance import grant_resonance  # noqa: PLC0415
    from world.roster.models import RosterEntry  # noqa: PLC0415
    from world.scenes.constants import InteractionMode  # noqa: PLC0415
    from world.scenes.interaction_services import create_interaction  # noqa: PLC0415

    if not CharacterAura.objects.filter(character=daven).exists():
        CharacterAuraFactory(character=daven, celestial="0", primal="40", abyssal="60")
    CharacterResonance.objects.create(
        character_sheet=daven, resonance=resonances["Cruelty"], balance=20, lifetime_earned=20
    )

    intimidated = _attested_act(
        daven,
        "Intimidated Hale",
        act_phrase="Intimidated",
        category=ActionCategory.SOCIAL,
        success=success,
        minutes_ago=2,
        check_type=intimidate,
        target=hale,
        suggestion=(resonances["Cruelty"], blazing, "You left Hale in the grip of Terror."),
    )
    cellar = _attested_act(
        daven,
        "Searched the cellar",
        category=ActionCategory.MENTAL,
        success=success,
        minutes_ago=9,
    )
    child = RecordedAct.objects.create(
        character_sheet=daven,
        label="Frightened the child",
        outcome=success,
        fatigue_category=ActionCategory.SOCIAL,
    )

    # Brannoc's pose first, so the feed reads in the order the demo draws it.
    bell_poser = RosterEntry.objects.get(character_sheet__character__db_key=ATTESTED_BELL_POSER)
    create_interaction(  # noqa: UNDELIVERED - a seed row; the spec's pages read it from the feed
        persona=bell_poser.character_sheet.primary_persona,
        content=ATTESTED_BELL_POSE,
        mode=InteractionMode.POSE,
        scene=scene,
    )
    marked_pose = create_interaction(  # noqa: UNDELIVERED - a seed row, read from the feed
        persona=daven.primary_persona,
        content=ATTESTED_MARKED_POSE,
        mode=InteractionMode.POSE,
        scene=scene,
    )
    ledger: list[ResonanceGrant] = []
    grant_resonance(
        daven,
        resonances["Mercy"],
        8,
        source=GainSource.MARKED_ACT,
        deed_label=child.label,
        ledger_out=ledger,
    )
    child.marked_grant = ledger[-1]
    child.marked_interaction = marked_pose
    child.save(update_fields=["marked_grant", "marked_interaction"])
    return intimidated, cellar, child


def seed_attested_resonance_spec(*, username: str) -> AttestedResonanceSeed:  # noqa: PLR0915
    """The rows `attested-resonance-5327.spec.ts` photographs, in an `rt_` database only (#5327).

    Run on a fresh `rt_5327` database (schema and *username*'s account already there); it
    refuses any other. Written from explicit values in the shape the approved demo draws, and
    safe to run twice: rows are found by name, and everything a run leaves behind for the
    characters it seeds (poses and what hangs on them, journal entries, acts, grants,
    resonances, stored private lines and their deliveries, the mission run, fatigue) is wiped
    and written again.

    Staff set: Abyssal reads "gloat" and costs 6, Celestial "inspire" and 5, Primal "blaze" and
    4, each with its skill; the six resonances carry help text; an act is worth 3, 7 or 12 at
    Partial Success, Success or Critical Success, and Faint, Strong and Blazing pay half, three
    quarters and all of it; the weekly table has the demo's seven rows; an act stays listed for
    90 days; the bonus check adds 30 percent at every result.

    *username*'s account plays Daven, in The Lantern with a live scene that stores its poses.
    Hale (the target, with room to pay 6 social fatigue), Ilsa (a witness and scene co-owner),
    Brannoc (whose pose names no resonance) and Marek (the scene's GM) are played by their own
    accounts. Daven holds Cruelty in his aura and has three acts: Intimidated Hale (a Cruelty
    suggestion), Searched the cellar (none) and Frightened the child (already marked Mercy on
    a pose, worth 8). He is on a mission whose first option pays Mercy at once, and his staff
    roll modifier is +100, so the roll of that option's check lands on the best result its
    chart has and the option pays whatever it can.

    Worked by hand: marking Intimidated Hale as Cruelty is Success 7 at Blazing (100 percent) =
    7, no weekly step applies below 9 gained, Abyssal's earn rate is 100 percent, and the bonus
    check adds 7 * 30 // 100 = 2, so Daven reads "grows by 9" and Hale takes 6 social fatigue.

    The frames that need another state have a cast of their own, with the same names:

    * shrunk: Hale has 3 of room, so the same mark pays 7 * 3 // 6 = 3 of its 9;
    * refused: Hale has none, so it pays nothing and the act stays on Daven's list;
    * week: Daven made four marks of 9 this game week (36 gained), so the table's 40 percent
      row pays 7 * 40 // 100 = 2, as his fifth mark;
    * Tamsin: a physical Fury mark of 9 that tires her by 4;
    * Wren: a Mercy mark from a journal entry (9, tiring her by 5), whose road holds a scene that
      stores nothing; and a Wren whose week of 72 is spent, so her journal mark is refused.
    """
    from django.db import transaction  # noqa: PLC0415
    from evennia.accounts.models import AccountDB  # noqa: PLC0415

    from actions.constants import ActionCategory  # noqa: PLC0415
    from world.game_clock.week_services import get_current_game_week  # noqa: PLC0415
    from world.gm.constants import GMLevel  # noqa: PLC0415
    from world.gm.models import GMProfile  # noqa: PLC0415
    from world.magic.models import Affinity, DramaticMomentType  # noqa: PLC0415
    from world.magic.services.gain import get_resonance_gain_config  # noqa: PLC0415
    from world.traits.factories import CheckSystemSetupFactory  # noqa: PLC0415
    from world.traits.models import CharacterTraitValue, ResultChart, Trait  # noqa: PLC0415

    _refuse_unless_rt_database()
    staff, staff_password = _attested_privileged_account(ATTESTED_STAFF, staff=True)
    gm_account, gm_password = _attested_privileged_account(ATTESTED_GM_ACCOUNT, staff=False)
    daven_account = AccountDB.objects.get(username=username)
    players = {name: _attested_player_account(user) for name, user in ATTESTED_ACCOUNTS.items()}
    with transaction.atomic():
        get_current_game_week()
        if not ResultChart.objects.exists():
            CheckSystemSetupFactory.create()
        resonances = _attested_affinities_and_resonances()
        success, blazing, kindling_config_id = _attested_awards_and_tables()
        bonus_check, intimidate, persuasion, source_stat_id = _attested_bonus_check()
        _attested_wipe()
        # Every grant seeded below is exactly its amount: the bonus check goes on at the end.
        config = get_resonance_gain_config()
        config.bonus_check_type = None
        config.save(update_fields=["bonus_check_type"])

        room = _attested_room(ATTESTED_ROOM)
        daven = _attested_player(ATTESTED_POSER, daven_account, room)
        hale = _attested_player(ATTESTED_TARGET, players[ATTESTED_TARGET], room)
        _attested_player(ATTESTED_WITNESS, players[ATTESTED_WITNESS], room)
        _attested_player(ATTESTED_BELL_POSER, players[ATTESTED_BELL_POSER], room)
        _attested_player(ATTESTED_GM, gm_account, room)
        GMProfile.objects.update_or_create(
            account=gm_account, defaults={"level": GMLevel.GM, "approved_by": staff}
        )
        scene = _attested_scene(
            room,
            (
                (daven_account, False, False),
                (players[ATTESTED_TARGET], False, False),
                (players[ATTESTED_BELL_POSER], False, False),
                (players[ATTESTED_WITNESS], False, True),
                (gm_account, True, False),
            ),
        )

        # What the characters can do: Hale has room to pay social fatigue; Daven can pay the
        # fatigue of a tag, has a Villainy rating, and a staff roll modifier of +100.
        _attested_fatigue(hale, stat="composure", category=ActionCategory.SOCIAL, room=None)
        _attested_fatigue(daven, stat="composure", category=ActionCategory.SOCIAL, room=None)
        CharacterTraitValue.objects.update_or_create(
            character=daven, trait=Trait.objects.get(name="Villainy"), defaults={"value": 20}
        )
        daven.rollmod = 100
        daven.save(update_fields=["rollmod"])

        intimidated, cellar, child = _attested_daven_state(
            daven, hale, scene, resonances, success, blazing, intimidate
        )
        shrunk_poser, shrunk_target, shrunk_act = _attested_duel(
            "shrunk", resonances, success, blazing, intimidate, target_room=3, week_marks=()
        )
        refused_poser, _refused_target, refused_act = _attested_duel(
            "refused", resonances, success, blazing, intimidate, target_room=0, week_marks=()
        )
        week_poser, _week_target, week_act = _attested_duel(
            "week", resonances, success, blazing, intimidate, target_room=None, week_marks=(9,) * 4
        )
        tamsin_account, tamsin_act = _attested_tamsin(resonances, success, blazing)
        wren_account, tended, fine = _attested_wren(
            "attested_wren",
            "The Road",
            resonances,
            success,
            blazing,
            ephemeral_scene=True,
            week_marks=(),
        )
        wren_spent, spent_tended, _spent_fine = _attested_wren(
            "attested_wren_refused",
            "The Road, a week spent",
            resonances,
            success,
            blazing,
            ephemeral_scene=False,
            week_marks=(72,),
        )
        config.bonus_check_type = bonus_check
        config.bonus_difficulty_level = 0
        config.save(update_fields=["bonus_check_type", "bonus_difficulty_level"])

        DramaticMomentType.objects.update_or_create(
            label=ATTESTED_MOMENT_TYPE,
            defaults={
                "description": "A character holds her ground when she should have fled.",
                "resonance": None,
                "resonance_amount": 10,
                "per_scene_cap": 1,
            },
        )
        instance = _attested_mission(daven, resonances["Mercy"], persuasion)
    return AttestedResonanceSeed(
        scene_id=scene.pk,
        scene_name=scene.name,
        daven_name=ATTESTED_POSER,
        daven_sheet_id=daven.pk,
        act_intimidated_id=intimidated.pk,
        act_cellar_id=cellar.pk,
        marked_grant_id=child.marked_grant_id,
        marked_pose_text=ATTESTED_MARKED_POSE,
        bell_pose_text=ATTESTED_BELL_POSE,
        moment_type_label=ATTESTED_MOMENT_TYPE,
        mission_instance_id=instance.pk,
        mission_name=ATTESTED_MISSION,
        abyssal_affinity_id=Affinity.objects.get(name="Abyssal").pk,
        cruelty_id=resonances["Cruelty"].pk,
        cruelty_description=resonances["Cruelty"].description,
        mercy_description=resonances["Mercy"].description,
        fury_description=resonances["Fury"].description,
        weekly_row_count=len(ATTESTED_WEEKLY_TABLE),
        kindling_config_id=kindling_config_id,
        gain_source_stat_id=source_stat_id,
        player_password=ATTESTED_PASSWORD,
        hale_username=ATTESTED_ACCOUNTS[ATTESTED_TARGET],
        witness_username=ATTESTED_ACCOUNTS[ATTESTED_WITNESS],
        bell_poser_username=ATTESTED_ACCOUNTS[ATTESTED_BELL_POSER],
        gm_username=gm_account.username,
        gm_password=gm_password,
        staff_username=staff.username,
        staff_password=staff_password,
        shrunk_poser_username=shrunk_poser.username,
        shrunk_target_username=shrunk_target.username,
        shrunk_act_id=shrunk_act.pk,
        refused_poser_username=refused_poser.username,
        refused_act_id=refused_act.pk,
        week_poser_username=week_poser.username,
        week_act_id=week_act.pk,
        tamsin_username=tamsin_account.username,
        tamsin_act_id=tamsin_act.pk,
        wren_username=wren_account.username,
        wren_tended_act_id=tended.pk,
        wren_fine_act_id=fine.pk,
        wren_refused_username=wren_spent.username,
        wren_refused_act_id=spent_tended.pk,
    )

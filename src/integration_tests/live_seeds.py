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
    from world.roster.models import RosterTenure


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
            KindlingConfigFactory(instant_percent=100, claim_percent=50)
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
    KindlingConfigFactory(instant_percent=100, claim_percent=50)
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
class TraditionTeachingSeed:
    """What `frontend/e2e/evidence/tradition-teaching-5326.spec.ts` reads back (#5326)."""

    good_tradition_id: int
    good_tradition_name: str
    evil_tradition_id: int
    evil_tradition_name: str
    config_id: int
    modifier_target_id: int
    distinction_id: int
    evil_role_id: int
    evil_course_id: int
    #: A Villainy course on a role whose Tradition does not teach it (authored before the rule).
    lantern_course_id: int
    trainer_name: str
    entry_id: int
    character_id: int
    character_name: str
    draft_id: int
    mentor_good: str
    mentor_unrated: str
    mentor_rated: str
    staff_username: str
    staff_password: str
    #: Wren's own other character, played by the same account (a refused mentor).
    own_alt_name: str
    #: The account that plays Drusa Kell and Aldric Voss, who answers their requests.
    mentor_username: str
    mentor_password: str
    mentor_entry_id: int
    #: The game master account: it plays gm_character_name and holds two NPCs.
    gm_username: str
    gm_password: str
    gm_entry_id: int
    gm_character_name: str
    npc_cannot_teach: str
    npc_declined: str
    #: Students of the mentors and the game master, and the allocation each one's row answers.
    student_of_aldric: str
    student_taught: str
    student_of_vey: str
    student_of_ilsa: str
    wren_allocation_id: int
    aldric_allocation_id: int
    taught_allocation_id: int
    vey_allocation_id: int
    ilsa_allocation_id: int


#: Invented names for the #5326 evidence run. No game character, Tradition or trainer.
TEACHING_GOOD = "The Lantern Concord"
TEACHING_EVIL = "The Cinder Court"
TEACHING_CHARACTER = "Wren Alder"
TEACHING_TRAINER = "Magister Corvin Hale"
TEACHING_MENTOR_GOOD = "Aldric Voss"
TEACHING_MENTOR_UNRATED = "Ysolde Marsh"
TEACHING_MENTOR_RATED = "Drusa Kell"
TEACHING_ROOM = "The Cinder Hall"
TEACHING_STAFF = "teaching_staff"
TEACHING_COURSE = "Villainy course"
TEACHING_OWN_ALT = "Mira Alder"
TEACHING_MENTOR_ACCOUNT = "teaching_mentor"
TEACHING_GM_ACCOUNT = "teaching_gm"
TEACHING_GM_CHARACTER = "Nessa Pryor"
#: Two NPCs the game master account holds: one has no Occult rating, one is declined.
TEACHING_NPC_CANNOT_TEACH = "Magister Vey"
TEACHING_NPC_DECLINED = "Warden Ilsa Tarn"
TEACHING_STUDENT_OF_ALDRIC = "Tamsin Reeve"
TEACHING_STUDENT_TAUGHT = "Marek Tolle"
TEACHING_STUDENT_OF_VEY = "Odalys Fenn"
TEACHING_STUDENT_OF_ILSA = "Bram Sorrel"
#: The rating a mentor holds in the skill, and the AP the weekly purse holds.
TEACHING_MENTOR_RATING = 11
TEACHING_WEEKLY_AP = 6


def _require_throwaway_database() -> None:
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


def _teaching_staff_account() -> tuple[AccountDB, str]:
    """The staff superuser for the admin screens, with a fresh password, linked to a contributor.

    The Distinction Builder shows setup guidance, not its form, to an account with no
    linked contributor, so the account gets one.
    """
    from allauth.account.models import EmailAddress  # noqa: PLC0415
    from evennia.accounts.models import AccountDB  # noqa: PLC0415
    from evennia.utils import create  # noqa: PLC0415

    from evennia_extensions.models import PlayerData  # noqa: PLC0415
    from world.contributors.models import ContentContributor  # noqa: PLC0415

    staff_password = secrets.token_urlsafe(18)
    staff = AccountDB.objects.filter(username=TEACHING_STAFF).first()
    if staff is None:
        staff = create.create_account(TEACHING_STAFF, "teaching_staff@example.com", staff_password)
    staff.set_password(staff_password)
    staff.is_staff = True
    staff.is_superuser = True
    staff.save()
    EmailAddress.objects.update_or_create(
        user=staff,
        email="teaching_staff@example.com",
        defaults={"primary": True, "verified": True},
    )
    contributor, _ = ContentContributor.objects.get_or_create(name="Teaching Staff")
    player_data, _ = PlayerData.objects.get_or_create(account=staff)
    if player_data.contributor_id != contributor.pk:
        player_data.contributor = contributor
        player_data.save(update_fields=["contributor"])
    return staff, staff_password


def _teaching_skills() -> dict[str, object]:
    """Heroism, Reflection and Villainy as Magic skills linked to their affinities, and Occult.

    Explicit rows: Heroism to Celestial, Reflection to Primal, Villainy to Abyssal; Occult is
    an ordinary Magic skill every Tradition offers. Observation is a General skill for the
    Anima Check, which never takes a Magic skill.
    """
    from world.magic.models import Affinity  # noqa: PLC0415
    from world.skills.models import Skill  # noqa: PLC0415
    from world.traits.models import TraitCategory  # noqa: PLC0415

    celestial, primal, abyssal = _canonical_affinities()
    skills: dict[str, object] = {}
    rows = (
        ("Heroism", TraitCategory.MAGIC, celestial, "Magic worked for those who cannot repay it."),
        ("Reflection", TraitCategory.MAGIC, primal, "Magic worked from what the caster feels."),
        ("Villainy", TraitCategory.MAGIC, abyssal, "Magic worked at another's cost."),
        ("Occult", TraitCategory.MAGIC, None, "The ordinary study of hidden things."),
        ("Observation", TraitCategory.GENERAL, None, "Noticing what is in front of you."),
    )
    for name, category, affinity, tooltip in rows:
        skill = Skill.objects.filter(name=name).first()
        if skill is None:
            skill = Skill.objects.create(name=name, category=category, tooltip=tooltip)
        skills[name] = skill
        if affinity is not None and affinity.skill_id != skill.pk:
            affinity.skill = skill
            affinity.save()
    Affinity.objects.clear_cache()
    return skills


def _teaching_traditions(skills: dict[str, object]) -> tuple[object, object]:
    """The Good Tradition (teaches Heroism) and the Evil one (teaches Villainy)."""
    from world.magic.models import Tradition  # noqa: PLC0415

    rows = (
        (
            TEACHING_GOOD,
            "Lantern-keepers hold that a flame is lit to be carried to someone else. "
            "Their teachers insist the student carry it first.",
            0,
            skills["Heroism"],
        ),
        (
            TEACHING_EVIL,
            "The Cinder Court teaches that a fire is only worth what it burns. "
            "Its masters take no student who flinches.",
            1,
            skills["Villainy"],
        ),
    )
    made = []
    for name, description, sort_order, taught in rows:
        tradition = Tradition.objects.filter(name=name).first()
        if tradition is None:
            tradition = Tradition.objects.create(
                name=name, description=description, sort_order=sort_order
            )
        tradition.taught_skills.set([taught])
        made.append(tradition)
    return made[0], made[1]


def _teaching_levers_and_training() -> tuple[object, object]:
    """The self-teaching target and its distinction, and the Tradition Training distinction.

    Returns (target, prodigy distinction). The Tradition Training distinction carries the
    Magic training points the creation step spends (30 a rank).
    """
    from world.character_creation.constants import (  # noqa: PLC0415
        CG_MODIFIER_CATEGORY,
        MAGIC_TRAINING_POINTS_TARGET,
    )
    from world.distinctions.models import (  # noqa: PLC0415
        Distinction,
        DistinctionCategory,
        DistinctionEffect,
    )
    from world.mechanics.constants import (  # noqa: PLC0415
        SELF_TEACHING_CATEGORY_NAME,
        SELF_TEACHING_TARGET_NAME,
    )
    from world.mechanics.models import ModifierCategory, ModifierTarget  # noqa: PLC0415

    teaching = (
        "Teaching herself magic: a positive total lets the character allocate weekly "
        "training on a Magic skill with no mentor. Yes or no; a larger value adds nothing."
    )
    lever_category, _ = ModifierCategory.objects.get_or_create(
        name=SELF_TEACHING_CATEGORY_NAME, defaults={"description": teaching}
    )
    target, _ = ModifierTarget.objects.get_or_create(
        category=lever_category,
        name=SELF_TEACHING_TARGET_NAME,
        defaults={"description": teaching},
    )
    training_category, _ = ModifierCategory.objects.get_or_create(
        name=CG_MODIFIER_CATEGORY,
        defaults={"description": "Numbers a character-creation pick adds to a stage."},
    )
    training_target, _ = ModifierTarget.objects.get_or_create(
        category=training_category,
        name=MAGIC_TRAINING_POINTS_TARGET,
        defaults={"description": "Magic skill points a stance adds to the Gift stage."},
    )
    category, _ = DistinctionCategory.objects.get_or_create(
        name="Magical Gifts", defaults={"slug": "magical-gifts", "description": "Gifts."}
    )
    prodigy, _ = Distinction.objects.get_or_create(
        name="Hedge-born Prodigy",
        defaults={
            "slug": "hedge-born-prodigy",
            "category": category,
            "description": "She taught herself magic before anyone could tell her not to.",
            "cost_per_rank": 5,
            "max_rank": 1,
        },
    )
    DistinctionEffect.objects.get_or_create(
        distinction=prodigy, target=target, defaults={"value_per_rank": 1}
    )
    training, _ = Distinction.objects.get_or_create(
        name="Tradition Training",
        defaults={
            "slug": "tradition-training",
            "category": category,
            "description": "Years of schooling under a Tradition's masters.",
            "cost_per_rank": 1,
            "max_rank": 2,
        },
    )
    DistinctionEffect.objects.get_or_create(
        distinction=training, target=training_target, defaults={"value_per_rank": 30}
    )
    return target, prodigy


def _teaching_trainer(skills: dict[str, object], good: object, evil: object) -> dict[str, object]:
    """Two Academy master roles, a Villainy course on each, and the Cinder one placed in a room.

    The Cinder Court master teaches in the Cinder Hall. The Lantern Concord master carries a
    Villainy course written before the Tradition rule (made past the form's check, as a row
    authored earlier is): its admin page is refused on save.
    """
    from evennia.objects.models import ObjectDB  # noqa: PLC0415
    from evennia.utils import create  # noqa: PLC0415

    from world.areas.services import get_room_profile  # noqa: PLC0415
    from world.checks.models import CheckCategory, CheckType  # noqa: PLC0415
    from world.npc_services.constants import OfferKind  # noqa: PLC0415
    from world.npc_services.models import (  # noqa: PLC0415
        Functionary,
        NPCRole,
        NPCServiceOffer,
        SkillCourseOfferDetails,
    )

    check_category, _ = CheckCategory.objects.get_or_create(name="Magic")
    check_type = CheckType.objects.filter(name="Study a magical skill").first()
    if check_type is None:
        check_type = CheckType.objects.create(name="Study a magical skill", category=check_category)
    room = ObjectDB.objects.filter(
        db_key=TEACHING_ROOM, db_typeclass_path="typeclasses.rooms.Room"
    ).first() or create.create_object("typeclasses.rooms.Room", key=TEACHING_ROOM)

    courses: dict[str, object] = {}
    for key, tradition in (("evil", evil), ("lantern", good)):
        role, _ = NPCRole.objects.update_or_create(
            name=f"Academy master of {tradition.name}",
            defaults={
                "description": f"A master who teaches in the manner of {tradition.name}.",
                "teaches_tradition": tradition,
            },
        )
        offer, _ = NPCServiceOffer.objects.update_or_create(
            role=role,
            label=TEACHING_COURSE,
            defaults={"kind": OfferKind.SKILL_COURSE, "is_final": True, "ap_cost": 0},
        )
        course, _ = SkillCourseOfferDetails.objects.update_or_create(
            offer=offer,
            defaults={
                "skill": skills["Villainy"],
                "total_development": 60,
                "session_development": 10,
                "session_ap_cost": 2,
                "coin_cost": 100,
                "check_type": check_type,
                "check_difficulty_level": 2,
            },
        )
        courses[key] = course
        courses[f"{key}_role"] = role
    Functionary.objects.update_or_create(
        role=courses["evil_role"],
        room=get_room_profile(room),
        defaults={"name_override": TEACHING_TRAINER},
    )
    courses["room"] = room
    return courses


def _teaching_character(
    name: str,
    *,
    pronoun: str = "them",
    player: AccountDB | None = None,
    npc: bool = False,
) -> object:
    """The roster entry of the character *name*, made once, with her object pronoun set.

    With *player* the account holds her open tenure (and, unless *npc*, plays her: the
    account is her puppeting account and she carries the playable lock). With *npc* she
    stands on the NPC shelf, as a character a game master holds does. Safe to run twice: an
    entry found by name is kept, and a tenure held by another account is handed to *player*.
    """
    from evennia_extensions.factories import CharacterFactory  # noqa: PLC0415
    from evennia_extensions.models import PlayerData  # noqa: PLC0415
    from world.character_sheets.factories import CharacterSheetFactory  # noqa: PLC0415
    from world.roster.factories import (  # noqa: PLC0415
        RosterEntryFactory,
        RosterTenureFactory,
    )
    from world.roster.models import RosterEntry, RosterTenure  # noqa: PLC0415
    from world.roster.models.choices import RosterType  # noqa: PLC0415
    from world.roster.seeds import ensure_rosters  # noqa: PLC0415

    entry = RosterEntry.objects.filter(character_sheet__character__db_key=name).first()
    if entry is None:
        character = CharacterFactory(db_key=name)
        entry = RosterEntryFactory(character_sheet=CharacterSheetFactory(character=character))
    sheet = entry.character_sheet
    sheet.pronoun_object = pronoun
    sheet.save(update_fields=["pronoun_object"])
    if npc and entry.roster.roster_type != RosterType.NPC:
        entry.roster = ensure_rosters()[RosterType.NPC]
        entry.save(update_fields=["roster"])
    if player is not None:
        player_data, _ = PlayerData.objects.get_or_create(account=player)
        tenure = RosterTenure.objects.filter(roster_entry=entry, end_date__isnull=True).first()
        if tenure is None:
            RosterTenureFactory(
                roster_entry=entry, player_data=player_data, player_number=1, end_date=None
            )
            if not npc:
                character = sheet.character
                character.db_account = player
                character.save()
                player.at_post_create_character(character)
        elif tenure.player_data_id != player_data.pk:
            tenure.player_data = player_data
            tenure.save(update_fields=["player_data"])
    return entry


def _teaching_mentor(
    name: str,
    tradition: object,
    rating: tuple[object, int] | None,
    *,
    player: AccountDB | None = None,
    npc: bool = False,
) -> object:
    """A character called *name* in *tradition*, holding *rating* (a skill and a value) or none.

    Returns her roster entry. *player* and *npc* are as in ``_teaching_character``.
    """
    from world.magic.models import CharacterTradition  # noqa: PLC0415
    from world.traits.models import CharacterTraitValue  # noqa: PLC0415

    entry = _teaching_character(name, player=player, npc=npc)
    sheet = entry.character_sheet
    CharacterTradition.objects.get_or_create(character=sheet, tradition=tradition, left_at=None)
    if rating is not None:
        skill, value = rating
        CharacterTraitValue.objects.update_or_create(
            character=sheet, trait=skill, defaults={"value": value}
        )
    return entry


def _teaching_player_account(username: str) -> tuple[AccountDB, str]:
    """A player account with a verified email and a fresh password, made once.

    The password is reset on every run and returned, so the spec reads it from the seed's
    result. The account is not staff: what it may answer for comes from the characters it plays.
    """
    from allauth.account.models import EmailAddress  # noqa: PLC0415
    from evennia.accounts.models import AccountDB  # noqa: PLC0415
    from evennia.utils import create  # noqa: PLC0415

    from evennia_extensions.models import PlayerData  # noqa: PLC0415

    password = secrets.token_urlsafe(18)
    email = f"{username}@example.com"
    account = AccountDB.objects.filter(username=username).first()
    if account is None:
        account = create.create_account(username, email, password)
    account.set_password(password)
    account.save()
    PlayerData.objects.get_or_create(account=account)
    EmailAddress.objects.update_or_create(
        user=account, email=email, defaults={"primary": True, "verified": True}
    )
    return account, password


def _teaching_request(
    student: object, skill: object, mentor_entry: object, ap: int, *, agreed: bool
) -> int:
    """One training allocation of *student* naming *mentor_entry*'s character; returns its id.

    Reset to the asked state (or, with *agreed*, the agreed one) on every run, so a mentor's
    answer in an earlier spec run does not leave the row decided.
    """
    from django.utils import timezone  # noqa: PLC0415

    from world.skills.models import TrainingAllocation  # noqa: PLC0415

    allocation, _ = TrainingAllocation.objects.update_or_create(
        character=student,
        skill=skill,
        defaults={
            "mentor": mentor_entry.character_sheet.primary_persona,
            "ap_amount": ap,
            "mentor_accepted_at": timezone.now() if agreed else None,
        },
    )
    return allocation.pk


def _teaching_trainee(account: AccountDB, room: object, good: object) -> object:
    """Wren Alder: played by *account* in the Cinder Hall, of the Good Tradition, 6 AP to spend.

    *account* also plays Mira Alder, whom Wren may not name as a mentor. Returns Wren's roster
    entry, her selected character. Her weekly training starts empty on every run.
    """
    from evennia_extensions.models import PlayerData  # noqa: PLC0415
    from world.action_points.models import ActionPointConfig, ActionPointPool  # noqa: PLC0415
    from world.magic.models import CharacterTradition  # noqa: PLC0415
    from world.roster.services.selection import set_selected_entry  # noqa: PLC0415
    from world.skills.models import TrainingAllocation  # noqa: PLC0415

    tenure = _played_character(account, TEACHING_CHARACTER, room)
    entry = tenure.roster_entry
    sheet = entry.character_sheet
    sheet.pronoun_subject = "she"
    sheet.pronoun_object = "her"
    sheet.pronoun_possessive = "her"
    sheet.save(update_fields=["pronoun_subject", "pronoun_object", "pronoun_possessive"])
    # Her player's other character, for the mentor she may not name.
    _played_character(account, TEACHING_OWN_ALT, room)
    set_selected_entry(PlayerData.objects.get(account=account), entry)
    CharacterTradition.objects.get_or_create(character=sheet, tradition=good, left_at=None)
    ActionPointConfig.objects.update_or_create(
        name="Default", defaults={"is_active": True, "weekly_regen": TEACHING_WEEKLY_AP}
    )
    pool = ActionPointPool.get_or_create_for_character(sheet.character)
    pool.current = TEACHING_WEEKLY_AP
    pool.save()
    TrainingAllocation.objects.filter(character=sheet).delete()
    return entry


def _teaching_draft(  # noqa: PLR0915 - the whole Gift stage world, one row after another
    account: AccountDB,
    skills: dict[str, object],
    good: object,
    evil: object,
) -> int:
    """The account's creation draft at the Gift stage, the Good Tradition chosen and offered.

    Both Traditions are offered by the draft's Beginning. The draft holds a gift, a technique,
    one Primal feeling and the Tradition Training distinction, with 10 points each on
    Reflection and Heroism, so the training step is open with points left to spend. Reset on
    every run.
    """
    from decimal import Decimal  # noqa: PLC0415

    from world.character_creation.constants import Stage, TraditionState  # noqa: PLC0415
    from world.character_creation.factories import (  # noqa: PLC0415
        make_unknown_upbringing,
        single_resonance_weights,
    )
    from world.character_creation.models import (  # noqa: PLC0415
        Beginnings,
        BeginningTradition,
        CharacterDraft,
        OriginTemplate,
        StartingArea,
        TraditionStateLine,
    )
    from world.character_creation.tests.finalization_fixtures import DEFAULT_STATS  # noqa: PLC0415
    from world.character_sheets.models import Gender  # noqa: PLC0415
    from world.classes.factories import PathFactory  # noqa: PLC0415
    from world.classes.models import Path, PathStage  # noqa: PLC0415
    from world.distinctions.models import Distinction  # noqa: PLC0415
    from world.distinctions.types import build_distinction_entry  # noqa: PLC0415
    from world.forms.models import Build, HeightBand  # noqa: PLC0415
    from world.magic.factories import (  # noqa: PLC0415
        EffectTypeFactory,
        GiftFactory,
        PathGiftGrantFactory,
        TechniqueFactory,
        TraditionGiftGrantFactory,
        primal_resonance,
    )
    from world.magic.models import Gift, Resonance, Technique  # noqa: PLC0415
    from world.magic.models.grants import PathGiftGrant, TraditionGiftGrant  # noqa: PLC0415
    from world.magic.seeds_cast import get_standalone_cast_template  # noqa: PLC0415
    from world.realms.models import Realm  # noqa: PLC0415
    from world.roster.seeds import ensure_rosters  # noqa: PLC0415
    from world.seeds.modifier_values import seed_pool_and_cap_lanes  # noqa: PLC0415
    from world.species.models import Species  # noqa: PLC0415
    from world.tarot.constants import ArcanaType  # noqa: PLC0415
    from world.tarot.models import TarotCard  # noqa: PLC0415
    from world.traits.models import Trait, TraitType  # noqa: PLC0415

    ensure_rosters()
    seed_pool_and_cap_lanes()
    realm, _ = Realm.objects.get_or_create(
        name="Lantern Marches", defaults={"description": "A place to begin."}
    )
    area, _ = StartingArea.objects.get_or_create(
        name="Lantern Marches Area",
        defaults={
            "description": "A place to begin.",
            "realm": realm,
            "access_level": StartingArea.AccessLevel.ALL,
        },
    )
    species, _ = Species.objects.get_or_create(
        name="Marchfolk", defaults={"description": "People."}
    )
    gender, _ = Gender.objects.get_or_create(
        key="teaching_gender", defaults={"display_name": "Teaching Gender"}
    )
    tarot, _ = TarotCard.objects.get_or_create(
        name="Lantern Fool",
        defaults={"arcana_type": ArcanaType.MAJOR, "rank": 0, "latin_name": "Fatui"},
    )
    beginnings, _ = Beginnings.objects.get_or_create(
        name="Marchborn",
        starting_area=area,
        defaults={"description": "A start.", "is_active": True},
    )
    beginnings.allowed_species.add(species)
    upbringing = OriginTemplate.objects.filter(
        beginning=beginnings, name="Unknown"
    ).first() or make_unknown_upbringing(beginnings)
    band, _ = HeightBand.objects.get_or_create(
        name="teaching_band",
        defaults={
            "display_name": "Teaching Band",
            "min_inches": 700,
            "max_inches": 800,
            "weight_min": None,
            "weight_max": None,
            "is_cg_selectable": True,
        },
    )
    build, _ = Build.objects.get_or_create(
        name="teaching_build",
        defaults={
            "display_name": "Teaching Build",
            "weight_factor": Decimal("1.0"),
            "is_cg_selectable": True,
        },
    )
    stats = dict(DEFAULT_STATS)
    for stat_name in stats:
        Trait.objects.get_or_create(
            name=stat_name, defaults={"trait_type": TraitType.STAT, "description": stat_name}
        )
    path = Path.objects.filter(name="Lantern Path").first() or PathFactory(
        name="Lantern Path", stage=PathStage.PROSPECT, minimum_level=1
    )
    gift = Gift.objects.filter(name="Lantern Gift").first() or GiftFactory(name="Lantern Gift")
    path_grant = PathGiftGrant.objects.filter(path=path, gift=gift).first() or PathGiftGrantFactory(
        path=path, gift=gift
    )
    technique = Technique.objects.filter(name="Lantern Pool Technique").first() or TechniqueFactory(
        name="Lantern Pool Technique",
        gift=gift,
        effect_type=EffectTypeFactory(name="Lantern Effect Type"),
        action_template=get_standalone_cast_template(),
    )
    path_grant.starter_techniques.set([technique])
    TraditionStateLine.objects.get_or_create(
        state=TraditionState.LIVING_MASTERS, defaults={"entry_line": "Living masters"}
    )
    for order, tradition in enumerate((good, evil)):
        if not TraditionGiftGrant.objects.filter(tradition=tradition, gift=gift).exists():
            TraditionGiftGrantFactory(tradition=tradition, gift=gift)
        BeginningTradition.objects.get_or_create(
            beginning=beginnings,
            tradition=tradition,
            defaults={"sort_order": order, "state": TraditionState.LIVING_MASTERS},
        )
    resonance = Resonance.objects.filter(name="Hearthlight").first() or primal_resonance(
        name="Hearthlight"
    )
    training = Distinction.objects.get(name="Tradition Training")

    draft = CharacterDraft.objects.filter(account=account).first()
    if draft is None:
        draft = CharacterDraft(account=account)
    draft.selected_area = area
    draft.selected_beginnings = beginnings
    draft.selected_origin_template = upbringing
    draft.selected_species = species
    draft.selected_gender = gender
    draft.selected_path = path
    draft.selected_tradition = good
    draft.age = 25
    draft.birthday_month = 6
    draft.birthday_day = 12
    draft.height_band = band
    draft.height_inches = 750
    draft.build = build
    draft.current_stage = Stage.GIFT
    draft.draft_data = {
        "first_name": "Wren",
        "description": "A character whose Tradition names its skills.",
        "stats": stats,
        "tarot_card_name": tarot.name,
        "tarot_reversed": False,
        "selected_gift_id": gift.pk,
        "selected_technique_ids": [technique.pk],
        "anima_check_stat_id": Trait.objects.get(name="strength").pk,
        "anima_check_skill_id": skills["Observation"].pk,
        "gift_resonance_weights": single_resonance_weights(resonance),
        "distinctions": [build_distinction_entry(training, 1)],
        "magic_skills": {str(skills["Reflection"].pk): 10, str(skills["Heroism"].pk): 10},
    }
    draft.save()
    return draft.pk


def seed_tradition_teaching_spec(*, username: str) -> TraditionTeachingSeed:
    """The rows `tradition-teaching-5326.spec.ts` photographs, in an `rt_` database only (#5326).

    Written from explicit values, in the shape the demo draws. Heroism, Reflection and
    Villainy are Magic skills linked to the Celestial, Primal and Abyssal affinities. The
    Lantern Concord (Good) teaches Heroism and the Cinder Court (Evil) teaches Villainy. Staff
    set an other-Tradition course difficulty of 3, the self-teaching target exists with a
    distinction carrying one effect on it, and the Cinder Court's Academy master teaches a
    Villainy course in the Cinder Hall. *username*'s account plays Wren Alder (of the
    Lantern Concord, 6 action points to spend) in that hall, and holds a creation draft at
    the Gift stage with the Lantern Concord chosen, and also plays Mira Alder.

    Mentoring (the mentor's agreement): Wren has asked Drusa Kell (Cinder Court, Villainy at
    11) to teach her Villainy and waits. A mentor account plays Drusa Kell and Aldric Voss
    (Lantern Concord, which does not teach Villainy), so its Mentoring card holds Wren's
    request, Tamsin Reeve's request to Aldric Voss, and Marek Tolle, whom Drusa already
    teaches. A game master account plays Nessa Pryor and holds two NPCs: Magister Vey (no
    Occult rating, asked by Odalys Fenn) and Warden Ilsa Tarn (asked by Bram Sorrel).
    Ysolde Marsh (Cinder Court, no Villainy rating) has no player. Safe to run twice: rows
    are found by name, the three accounts' passwords are reset, and every request above is
    put back to the state it is described in.
    """
    from django.db import transaction  # noqa: PLC0415
    from evennia.accounts.models import AccountDB  # noqa: PLC0415

    from evennia_extensions.models import PlayerData  # noqa: PLC0415
    from world.magic.services.teaching_fit import get_teaching_config  # noqa: PLC0415
    from world.roster.services.selection import set_selected_entry  # noqa: PLC0415

    _require_throwaway_database()
    staff, staff_password = _teaching_staff_account()
    account = AccountDB.objects.get(username=username)
    with transaction.atomic():
        skills = _teaching_skills()
        good, evil = _teaching_traditions(skills)
        target, prodigy = _teaching_levers_and_training()
        config = get_teaching_config()
        config.other_tradition_course_difficulty = 3
        config.save(update_fields=["other_tradition_course_difficulty"])
        trainer = _teaching_trainer(skills, good, evil)
        mentor_account, mentor_password = _teaching_player_account(TEACHING_MENTOR_ACCOUNT)
        gm_account, gm_password = _teaching_player_account(TEACHING_GM_ACCOUNT)
        villainy, heroism, occult = skills["Villainy"], skills["Heroism"], skills["Occult"]
        # Aldric Voss (his Tradition does not teach Villainy) and Drusa Kell (it does, and she
        # is rated) are both played by the mentor account. Ysolde Marsh has no player.
        aldric = _teaching_mentor(TEACHING_MENTOR_GOOD, good, None, player=mentor_account)
        _teaching_mentor(TEACHING_MENTOR_UNRATED, evil, None)
        drusa = _teaching_mentor(
            TEACHING_MENTOR_RATED,
            evil,
            (villainy, TEACHING_MENTOR_RATING),
            player=mentor_account,
        )
        # The game master plays one ordinary character and holds two NPCs. Magister Vey has no
        # Occult rating, so she cannot agree. Warden Ilsa Tarn is rated in Heroism.
        gm_entry = _teaching_character(TEACHING_GM_CHARACTER, pronoun="her", player=gm_account)
        vey = _teaching_mentor(TEACHING_NPC_CANNOT_TEACH, good, None, player=gm_account, npc=True)
        ilsa = _teaching_mentor(
            TEACHING_NPC_DECLINED,
            good,
            (heroism, TEACHING_MENTOR_RATING),
            player=gm_account,
            npc=True,
        )
        entry = _teaching_trainee(account, trainer["room"], good)
        wren = entry.character_sheet
        students = {
            name: _teaching_character(name, pronoun=pronoun).character_sheet
            for name, pronoun in (
                (TEACHING_STUDENT_OF_ALDRIC, "her"),
                (TEACHING_STUDENT_TAUGHT, "him"),
                (TEACHING_STUDENT_OF_VEY, "her"),
                (TEACHING_STUDENT_OF_ILSA, "him"),
            )
        }
        # Wren asked Drusa Kell and waits. The other rows are the requests the mentor
        # and the game master read: all asked, except one student Drusa already teaches.
        wren_allocation = _teaching_request(wren, villainy, drusa, 3, agreed=False)
        aldric_allocation = _teaching_request(
            students[TEACHING_STUDENT_OF_ALDRIC], villainy, aldric, 2, agreed=False
        )
        taught_allocation = _teaching_request(
            students[TEACHING_STUDENT_TAUGHT], villainy, drusa, 2, agreed=True
        )
        vey_allocation = _teaching_request(
            students[TEACHING_STUDENT_OF_VEY], occult, vey, 2, agreed=False
        )
        ilsa_allocation = _teaching_request(
            students[TEACHING_STUDENT_OF_ILSA], heroism, ilsa, 2, agreed=False
        )
        # Each answering account opens on one ordinary character of its own.
        for player, chosen in ((mentor_account, drusa), (gm_account, gm_entry)):
            set_selected_entry(PlayerData.objects.get(account=player), chosen)
        draft_id = _teaching_draft(account, skills, good, evil)
    return TraditionTeachingSeed(
        good_tradition_id=good.pk,
        good_tradition_name=good.name,
        evil_tradition_id=evil.pk,
        evil_tradition_name=evil.name,
        config_id=config.pk,
        modifier_target_id=target.pk,
        distinction_id=prodigy.pk,
        evil_role_id=trainer["evil_role"].pk,
        evil_course_id=trainer["evil"].pk,
        lantern_course_id=trainer["lantern"].pk,
        trainer_name=TEACHING_TRAINER,
        entry_id=entry.pk,
        character_id=entry.character_sheet.character_id,
        character_name=TEACHING_CHARACTER,
        draft_id=draft_id,
        mentor_good=TEACHING_MENTOR_GOOD,
        mentor_unrated=TEACHING_MENTOR_UNRATED,
        mentor_rated=TEACHING_MENTOR_RATED,
        staff_username=staff.username,
        staff_password=staff_password,
        own_alt_name=TEACHING_OWN_ALT,
        mentor_username=mentor_account.username,
        mentor_password=mentor_password,
        mentor_entry_id=drusa.pk,
        gm_username=gm_account.username,
        gm_password=gm_password,
        gm_entry_id=gm_entry.pk,
        gm_character_name=TEACHING_GM_CHARACTER,
        npc_cannot_teach=TEACHING_NPC_CANNOT_TEACH,
        npc_declined=TEACHING_NPC_DECLINED,
        student_of_aldric=TEACHING_STUDENT_OF_ALDRIC,
        student_taught=TEACHING_STUDENT_TAUGHT,
        student_of_vey=TEACHING_STUDENT_OF_VEY,
        student_of_ilsa=TEACHING_STUDENT_OF_ILSA,
        wren_allocation_id=wren_allocation,
        aldric_allocation_id=aldric_allocation,
        taught_allocation_id=taught_allocation,
        vey_allocation_id=vey_allocation,
        ilsa_allocation_id=ilsa_allocation,
    )

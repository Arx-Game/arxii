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
class GiftSubstanceSeed:
    """What `frontend/e2e/gift-substance.spec.ts` reads back (#5018)."""

    scene_id: int
    character_id: int
    technique_name: str


#: A shadow caster in an ordinary hall with a scene running that her account also GMs.
SUBSTANCE_SPEC_CHARACTER = "Vesper Shade"
SUBSTANCE_SPEC_ROOM = "The Lamplit Hall"
SUBSTANCE_SPEC_TECHNIQUE = "Veil of Dusk"


def seed_gift_substance_spec(*, username: str) -> GiftSubstanceSeed:  # noqa: PLR0915
    """A level-10 shadow caster of *username*'s, in an ordinary-lit room, scene running.

    Her gift's substance is shadow (lighting falling, full at 2 steps); she holds 10 of its
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
    )
    from world.magic.models import GiftSubstance, Technique  # noqa: PLC0415
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
            gift = GiftFactory(name="Gloamcraft")
            gift.resonances.add(umbral)
            GiftSubstance.objects.get_or_create(
                gift=gift,
                defaults={
                    "label": "shadow",
                    "stat_key": StatKey.LIGHTING,
                    "direction": SubstanceDirection.FALLING,
                    "full_at": 2,
                    "arrival_line": "The shadows in the room deepen.",
                },
            )
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
    return GiftSubstanceSeed(
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

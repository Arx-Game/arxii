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

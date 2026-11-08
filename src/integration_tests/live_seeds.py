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

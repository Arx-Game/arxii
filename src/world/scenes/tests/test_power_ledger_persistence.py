from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import LedgerOp, PowerStage
from world.magic.types.power_ledger import PowerLedgerBuilder
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import InteractionMode
from world.scenes.factories import InteractionFactory, PersonaFactory
from world.scenes.models import InteractionPowerLedgerEntry
from world.scenes.power_ledger_services import (
    load_persisted_ledger,
    persist_power_ledger,
    viewer_can_see_ledger,
)


class InteractionPowerLedgerEntryModelTests(TestCase):
    def test_entries_round_trip_in_order(self) -> None:
        interaction = InteractionFactory(mode=InteractionMode.ACTION)
        InteractionPowerLedgerEntry.objects.create(
            interaction=interaction,
            ordering=1,
            stage=PowerStage.ENVIRONMENT,
            source_label="resonance environment",
            op=LedgerOp.ADD,
            amount=7,
            running_total=12,
        )
        InteractionPowerLedgerEntry.objects.create(
            interaction=interaction,
            ordering=0,
            stage=PowerStage.BASE,
            source_label="channeled intensity",
            op=LedgerOp.SET,
            amount=5,
            running_total=5,
        )
        rows = list(interaction.power_ledger_entries.all())
        assert [r.ordering for r in rows] == [0, 1]
        assert rows[0].stage == PowerStage.BASE
        assert rows[1].running_total == 12


class PersistAndLoadLedgerTests(TestCase):
    def _ledger(self):
        return (
            PowerLedgerBuilder(base=5)
            .add(PowerStage.ENVIRONMENT, "resonance environment", 7)
            .build()
        )

    def test_persist_then_load_round_trips(self) -> None:
        interaction = InteractionFactory(mode=InteractionMode.ACTION)
        persist_power_ledger(interaction=interaction, ledger=self._ledger())
        loaded = load_persisted_ledger(interaction.pk)
        assert loaded is not None
        assert loaded.total == 12
        assert [e.stage for e in loaded.entries] == [PowerStage.BASE, PowerStage.ENVIRONMENT]
        assert loaded.entries[1].amount == 7

    def test_persist_empty_is_noop(self) -> None:
        interaction = InteractionFactory(mode=InteractionMode.ACTION)
        persist_power_ledger(interaction=interaction, ledger=None)
        assert load_persisted_ledger(interaction.pk) is None


class ViewerGateTests(TestCase):
    def test_staff_sees(self) -> None:
        staff = AccountFactory(is_staff=True)
        interaction = InteractionFactory(mode=InteractionMode.ACTION)
        assert viewer_can_see_ledger(interaction, staff) is True

    def test_non_caster_blocked(self) -> None:
        outsider = AccountFactory()
        interaction = InteractionFactory(mode=InteractionMode.ACTION)
        assert viewer_can_see_ledger(interaction, outsider) is False

    def test_caster_sees_own(self) -> None:
        # CharacterFactory creates no account and CharacterSheetFactory wires
        # no tenure, so we build the account->sheet membership explicitly: a
        # current RosterTenure (end_date=None) is what populates the account's
        # ``played_character_sheet_ids`` set. The interaction's persona points
        # at that same sheet, so the gate must return True.
        sheet = CharacterSheetFactory()
        account = AccountFactory()
        entry = RosterEntryFactory(character_sheet=sheet)
        RosterTenureFactory(
            roster_entry=entry,
            player_data=PlayerDataFactory(account=account),
        )
        interaction = InteractionFactory(
            mode=InteractionMode.ACTION,
            persona=PersonaFactory(character_sheet=sheet),
        )
        assert sheet.pk in account.played_character_sheet_ids
        assert viewer_can_see_ledger(interaction, account) is True

    def test_caster_of_other_character_blocked(self) -> None:
        # An authenticated account that plays a *different* sheet than the one
        # behind the interaction's persona must not see the ledger.
        own_sheet = CharacterSheetFactory()
        account = AccountFactory()
        RosterTenureFactory(
            roster_entry=RosterEntryFactory(character_sheet=own_sheet),
            player_data=PlayerDataFactory(account=account),
        )
        other_interaction = InteractionFactory(
            mode=InteractionMode.ACTION,
            persona=PersonaFactory(character_sheet=CharacterSheetFactory()),
        )
        assert viewer_can_see_ledger(other_interaction, account) is False

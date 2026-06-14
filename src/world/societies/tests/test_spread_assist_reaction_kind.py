"""SPREAD_ASSIST as a reaction-window kind (#915)."""

from decimal import Decimal

from django.test import TestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.progression.models import KudosTransaction
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import ReactionWindowKind, ScenePrivacyMode
from world.scenes.factories import (
    InteractionFactory,
    SceneFactory,
    SceneParticipationFactory,
)
from world.scenes.reaction_models import ReactionWindow, WindowReaction
from world.scenes.reaction_services import get_reaction_kind, settle_windows_for_scene
from world.societies.factories import LegendEntryFactory
from world.societies.models import LegendSpread, SpreadAssistTarget, SpreadingConfig
from world.societies.reaction_kinds import SPREAD_ASSIST_KIND


def make_participant(scene, *, link_account=True):
    """Account-backed persona participating in ``scene`` (full roster chain)."""
    account = AccountFactory()
    character = CharacterFactory()
    roster_entry = RosterEntryFactory(character_sheet__character=character)
    player_data = PlayerDataFactory(account=account)
    RosterTenureFactory(player_data=player_data, roster_entry=roster_entry)
    SceneParticipationFactory(scene=scene, account=account)
    if link_account:
        character.db_account = account
        character.save()
    return roster_entry.character_sheet.primary_persona


class SpreadAssistReactionKindTests(TestCase):
    def setUp(self) -> None:
        self.scene = SceneFactory(privacy_mode=ScenePrivacyMode.PUBLIC)
        self.teller = make_participant(self.scene)
        self.interaction = InteractionFactory(persona=self.teller, scene=self.scene)
        self.deed = LegendEntryFactory(base_value=100)
        self.window = ReactionWindow.objects.create(
            interaction=self.interaction,
            kind=ReactionWindowKind.SPREAD_ASSIST,
            timestamp=self.interaction.timestamp,
            scene=self.scene,
        )
        SpreadAssistTarget.objects.create(
            window=self.window, legend_entry=self.deed, original_value=100
        )

    def _acclaim(self, n: int) -> list:
        reactors = [make_participant(self.scene) for _ in range(n)]
        for reactor in reactors:
            WindowReaction.objects.create(
                window=self.window, reactor_persona=reactor, choice="acclaim"
            )
        return reactors

    def test_kind_is_registered_and_explicit_open(self) -> None:
        config = get_reaction_kind(ReactionWindowKind.SPREAD_ASSIST)
        assert config is SPREAD_ASSIST_KIND
        assert config.lazy_open is False  # only tellings grow these windows
        assert config.on_settle is not None

    def test_acclaim_adds_one_bonus_spread(self) -> None:
        self._acclaim(3)  # default fraction 0.10 → 100 * 0.10 * 3 = 30

        settle_windows_for_scene(self.scene)

        spreads = LegendSpread.objects.filter(legend_entry=self.deed, method="spread_assist")
        assert spreads.count() == 1
        assert spreads.first().value_added == 30

    def test_no_acclaim_no_bonus_spread(self) -> None:
        settle_windows_for_scene(self.scene)

        assert not LegendSpread.objects.filter(
            legend_entry=self.deed, method="spread_assist"
        ).exists()

    def test_bonus_respects_per_scene_cap(self) -> None:
        config = SpreadingConfig.get_active_config()
        config.spread_assist_per_scene_cap = 10
        config.save(update_fields=["spread_assist_per_scene_cap"])
        self._acclaim(3)  # uncapped would be 30

        settle_windows_for_scene(self.scene)

        spread = LegendSpread.objects.get(legend_entry=self.deed, method="spread_assist")
        assert spread.value_added == 10

    def test_bonus_clamped_to_remaining_capacity(self) -> None:
        # A near-full deed: its own window's would-be bonus is clamped to the
        # remaining capacity by spread_deed. Formula-independent — we capture
        # the remaining headroom before settle and assert the bonus matches it.
        small = LegendEntryFactory(base_value=10, spread_multiplier=1)
        LegendSpread.objects.create(legend_entry=small, spreader_persona=self.teller, value_added=8)
        headroom = small.remaining_spread_capacity
        assert 0 < headroom < 100  # the would-be bonus (100) overshoots it

        interaction2 = InteractionFactory(persona=self.teller, scene=self.scene)
        window2 = ReactionWindow.objects.create(
            interaction=interaction2,
            kind=ReactionWindowKind.SPREAD_ASSIST,
            timestamp=interaction2.timestamp,
            scene=self.scene,
        )
        SpreadAssistTarget.objects.create(window=window2, legend_entry=small, original_value=1000)
        WindowReaction.objects.create(
            window=window2, reactor_persona=make_participant(self.scene), choice="acclaim"
        )

        settle_windows_for_scene(self.scene)

        bonus = LegendSpread.objects.get(legend_entry=small, method="spread_assist")
        assert bonus.value_added == headroom

    def test_acclaiming_reactors_are_rewarded(self) -> None:
        reactors = self._acclaim(2)

        settle_windows_for_scene(self.scene)

        for reactor in reactors:
            account = reactor.character_sheet.character.db_account
            assert KudosTransaction.objects.filter(account=account).exists()

    def test_settled_value_uses_fraction_config(self) -> None:
        config = SpreadingConfig.get_active_config()
        config.spread_assist_fraction = Decimal("0.25")
        config.save(update_fields=["spread_assist_fraction"])
        self._acclaim(2)  # 100 * 0.25 * 2 = 50

        settle_windows_for_scene(self.scene)

        spread = LegendSpread.objects.get(legend_entry=self.deed, method="spread_assist")
        assert spread.value_added == 50

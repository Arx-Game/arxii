"""Invoking favor on mission option checks (#4333 slice 1, walkthrough B).

The invocation check is pinned through ``world.checks.services.
perform_check_with_modifiers`` (what ``invoke_favor`` rolls) and the option's own
check through ``world.missions.services.resolution.perform_check``, which also
records the ``extra_modifiers`` the option rolled with: the bonus must land
there, labelled with the being in the result.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory, ConsequenceFactory
from world.checks.types import CheckResult
from world.missions.constants import ConflictMode, JointCombine, OptionKind, OptionSource
from world.missions.factories import (
    MissionNodeFactory,
    MissionOptionFactory,
    MissionOptionRouteFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionGroupBallot
from world.missions.services.play import (
    BeatActionError,
    beat_for,
    resolve_beat_option,
    submit_group_pick,
)
from world.missions.services.run import share_mission, staff_assign_mission
from world.narrative.models import NarrativeMessageDelivery
from world.traits.factories import CheckOutcomeFactory, CheckRankFactory
from world.worship.constants import FavorAwardKind
from world.worship.factories import (
    DevotionConfigFactory,
    DevotionStandingFactory,
    FavorOutcomeAwardFactory,
    WorshipDeclarationFactory,
    WorshippedBeingFactory,
)
from world.worship.favor_services import ensure_being_modifier_targets
from world.worship.models import FavorInvocation, PatronageValence
from world.worship.types import InvocationChoice

_OPTION_CHECK = "world.missions.services.resolution.perform_check"
_INVOCATION_CHECK = "world.checks.services.perform_check_with_modifiers"


def _pc():
    character = CharacterFactory()
    CharacterSheetFactory(character=character)
    return character


def _result(check_type, outcome, *, total_points=0, roller_rank=None, target_rank=None):
    return CheckResult(
        check_type=check_type,
        outcome=outcome,
        chart=None,
        roller_rank=roller_rank,
        target_rank=target_rank,
        rank_difference=0,
        trait_points=total_points,
        aspect_bonus=0,
        total_points=total_points,
    )


class MissionInvocationBase(TestCase):
    def setUp(self) -> None:
        self.success = CheckOutcomeFactory(name="Success", success_level=1)
        self.partial = CheckOutcomeFactory(name="Partial Success", success_level=0)
        self.invocation_type = CheckTypeFactory(name="Invocation")
        config = DevotionConfigFactory(invocation_check_type=self.invocation_type)
        FavorOutcomeAwardFactory(
            config=config, kind=FavorAwardKind.INVOCATION, outcome_tier=self.success, amount=10
        )
        FavorOutcomeAwardFactory(
            config=config, kind=FavorAwardKind.INVOCATION, outcome_tier=self.partial, amount=5
        )
        self.being = WorshippedBeingFactory(name="Ombrin")
        ensure_being_modifier_targets(self.being)
        self.investigation = CheckTypeFactory(name="Perception + Investigation")

    def _check_graph(self, name, *, conflict_mode=None):
        template = MissionTemplateFactory(name=name)
        entry_kwargs = {"template": template, "key": "entry", "is_entry": True}
        if conflict_mode is not None:
            entry_kwargs.update(conflict_mode=conflict_mode, joint_combine=JointCombine.ANY)
        entry = MissionNodeFactory(**entry_kwargs)
        dest = MissionNodeFactory(template=template, key="dest")
        option = MissionOptionFactory(
            node=entry,
            order=0,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=self.investigation,
            authored_ic_framing="[option label]",
        )
        MissionOptionRouteFactory(
            option=option,
            outcome_tier=self.success,
            target_node=dest,
            consequence=ConsequenceFactory(outcome_tier=self.success),
        )
        branch = MissionOptionFactory(
            node=entry,
            order=1,
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AUTHORED,
            authored_ic_framing="[branch label]",
            branch_target=dest,
        )
        return template, option, branch


class SoloMissionInvocationTests(MissionInvocationBase):
    def setUp(self) -> None:
        super().setUp()
        self.character = _pc()
        self.sheet = self.character.sheet_data
        # Ysmay: Ombrin's Chosen with favor 44.
        DevotionStandingFactory(
            character_sheet=self.sheet,
            being=self.being,
            favor=44,
            valence=PatronageValence.DEVOTIONAL,
            established_at=timezone.now(),
        )
        template, self.option, self.branch = self._check_graph("solo-invoke")
        self.instance = staff_assign_mission(template, self.character)

    def test_mission_solo_journey(self) -> None:
        beat = beat_for(self.instance, self.character)
        rolls = {o.option_id: o.rolls_check for o in beat.options}
        self.assertEqual(rolls, {self.option.pk: True, self.branch.pk: False})

        CheckRankFactory(name="Competent", rank=2, min_points=25)
        expert = CheckRankFactory(name="Expert", rank=3, min_points=50)
        option_results = []

        def _option_check(character, check_type, **kwargs):
            option_results.append(kwargs["extra_modifiers"])
            return _result(
                check_type, self.success, total_points=58, roller_rank=expert, target_rank=expert
            )

        with (
            patch(
                _INVOCATION_CHECK,
                return_value=_result(self.invocation_type, self.success),
            ) as invocation_check,
            patch(_OPTION_CHECK, side_effect=_option_check),
            self.captureOnCommitCallbacks(execute=True),
        ):
            result = resolve_beat_option(
                self.instance,
                self.character,
                option_id=self.option.pk,
                invoke=InvocationChoice(being_id=self.being.pk, player_line="[player line]"),
            )

        # The invocation rolled first, at 75 - 30 (Chosen) - 15 (favor 44) = 30.
        self.assertEqual(invocation_check.call_args.kwargs["target_difficulty"], 30)
        # The option's check rolled with the +10 bonus.
        self.assertEqual(option_results, [10])
        invocation = result.invocation
        self.assertEqual(
            invocation.call_line, f"{self.character.key} calls on Ombrin: [player line]"
        )
        self.assertEqual(invocation.outcome_line, f"{self.character.key}'s invocation: Success.")
        self.assertEqual(invocation.bonus, 10)
        self.assertEqual(invocation.bonus_label, "Ombrin's favor (invocation: Success)")
        self.assertEqual((invocation.points_before_bonus, invocation.total_points), (48, 58))
        self.assertEqual(
            (invocation.roller_rank, invocation.target_rank),
            ("Expert (rank 3)", "Expert (rank 3)"),
        )
        # 48 alone is Competent: the bonus moved the total across the Expert threshold.
        self.assertEqual(invocation.rank_difference_without_bonus, -1)

        row = FavorInvocation.objects.get(character_sheet=self.sheet)
        self.assertEqual((row.mission_instance, row.bonus), (self.instance, 10))
        # Favor is unchanged.
        self.assertEqual(self.sheet.devotion_standings.get(being=self.being).favor, 44)
        # The mission log carries the two lines.
        bodies = list(
            NarrativeMessageDelivery.objects.filter(
                recipient_character_sheet=self.sheet
            ).values_list("message__body", flat=True)
        )
        self.assertIn(
            f"{invocation.call_line}\n{invocation.outcome_line}\n"
            "Perception + Investigation: 48 + 10 Ombrin's favor (invocation: Success) = 58, "
            "Expert (rank 3) against Expert (rank 3) (rank difference 0, -1 without the bonus).",
            bodies,
        )

    def test_refused_on_an_option_with_no_roll(self) -> None:
        with self.assertRaises(BeatActionError) as refused:
            resolve_beat_option(
                self.instance,
                self.character,
                option_id=self.branch.pk,
                invoke=InvocationChoice(being_id=self.being.pk),
            )
        self.assertIn("rolls no check", refused.exception.user_message)
        self.assertFalse(FavorInvocation.objects.exists())

    def test_refused_without_favor(self) -> None:
        stranger = WorshippedBeingFactory(name="The Fenwright Dead")
        with self.assertRaises(BeatActionError) as refused:
            resolve_beat_option(
                self.instance,
                self.character,
                option_id=self.option.pk,
                invoke=InvocationChoice(being_id=stranger.pk),
            )
        self.assertEqual(
            refused.exception.user_message, "You have no favor with The Fenwright Dead to call on."
        )
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.current_node.key, "entry")

    def test_without_invocation_no_breakdown(self) -> None:
        with patch(_OPTION_CHECK, return_value=_result(self.investigation, self.success)):
            result = resolve_beat_option(self.instance, self.character, option_id=self.option.pk)
        self.assertIsNone(result.invocation)


class GroupMissionInvocationTests(MissionInvocationBase):
    def test_mission_group_journey(self) -> None:
        holder = _pc()
        partner = _pc()
        DevotionStandingFactory(character_sheet=holder.sheet_data, being=self.being, favor=12)
        # The partner's secret faith: the party sees "calls on something.".
        river = WorshippedBeingFactory(name="River Spirit")
        WorshipDeclarationFactory(
            character_sheet=partner.sheet_data,
            public_being=WorshippedBeingFactory(name="A Public God"),
            secret_being=river,
        )
        DevotionStandingFactory(character_sheet=partner.sheet_data, being=river, favor=8)
        template, option, _ = self._check_graph("group-invoke", conflict_mode=ConflictMode.JOINT)
        instance = staff_assign_mission(template, holder)
        share_mission(instance, partner)

        invocation_outcomes = iter([self.success, self.partial])
        option_bonuses = {}

        def _invocation_check(character, check_type, **_kwargs):
            return _result(check_type, next(invocation_outcomes))

        def _option_check(character, check_type, **kwargs):
            option_bonuses[character.pk] = kwargs["extra_modifiers"]
            return _result(check_type, self.success)

        with (
            patch(_INVOCATION_CHECK, side_effect=_invocation_check),
            patch(_OPTION_CHECK, side_effect=_option_check),
            self.captureOnCommitCallbacks(execute=True),
        ):
            submit_group_pick(
                instance,
                holder,
                option_id=option.pk,
                invoke=InvocationChoice(being_id=self.being.pk, player_line="[holder line]"),
            )
            ballot = MissionGroupBallot.objects.get(participant__character=holder.sheet_data)
            self.assertEqual(
                (ballot.invoke_being, ballot.invoke_line), (self.being, "[holder line]")
            )
            # Nothing rolls at pick time.
            self.assertFalse(FavorInvocation.objects.exists())
            res = submit_group_pick(
                instance,
                partner,
                option_id=option.pk,
                invoke=InvocationChoice(being_id=river.pk, player_line="[partner line]"),
            )

        self.assertIsNotNone(res.resolved)
        # JOINT resolves by participant pk: the holder rolled first (Success, +10),
        # then the partner (Partial Success, +5); each bonus landed on its own check.
        self.assertEqual(option_bonuses, {holder.pk: 10, partner.pk: 5})
        self.assertEqual(FavorInvocation.objects.count(), 2)

        holder_bodies = list(
            NarrativeMessageDelivery.objects.filter(
                recipient_character_sheet=holder.sheet_data
            ).values_list("message__body", flat=True)
        )
        partner_bodies = list(
            NarrativeMessageDelivery.objects.filter(
                recipient_character_sheet=partner.sheet_data
            ).values_list("message__body", flat=True)
        )
        partner_public = (
            f"{partner.key} calls on something.\n{partner.key}'s invocation: Partial Success."
        )
        self.assertIn(partner_public, holder_bodies)
        self.assertFalse(any("[partner line]" in body for body in holder_bodies))
        self.assertTrue(
            any(
                body.startswith(
                    f"{partner.key} calls on River Spirit: [partner line]\n"
                    f"{partner.key}'s invocation: Partial Success.\n"
                )
                for body in partner_bodies
            ),
            partner_bodies,
        )


class FavorInvocationApiTests(MissionInvocationBase):
    """The web path: the picker endpoint and the resolve endpoint, as a player."""

    def setUp(self) -> None:
        from rest_framework.test import APIClient

        from world.roster.factories import RosterEntryFactory, RosterTenureFactory

        super().setUp()
        self.character = _pc()
        self.sheet = self.character.sheet_data
        entry = RosterEntryFactory(character_sheet=self.sheet)
        tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
        self.entry_id = entry.pk
        self.client = APIClient()
        self.client.force_authenticate(tenure.player_data.account)
        DevotionStandingFactory(
            character_sheet=self.sheet,
            being=self.being,
            favor=44,
            valence=PatronageValence.DEVOTIONAL,
            established_at=timezone.now(),
        )
        template, self.option, _ = self._check_graph("api-invoke")
        self.instance = staff_assign_mission(template, self.character)

    def test_invocation_options_endpoint(self) -> None:
        response = self.client.get(
            f"/api/worship/beings/invocation-options/?entry_id={self.entry_id}"
        )
        self.assertEqual(response.status_code, 200, response.content)
        (ombrin,) = response.json()["beings"]
        self.assertEqual(
            (ombrin["being_name"], ombrin["favor"], ombrin["can_invoke"], ombrin["uses_left"]),
            ("Ombrin", 44, True, 3),
        )
        difficulty = ombrin["difficulty"]
        self.assertEqual((difficulty["points"], difficulty["band_label"]), (30, "Easy"))
        self.assertEqual(
            [(e["label"], e["points"]) for e in difficulty["eases"]],
            [
                ("You are Ombrin's Chosen", 30),
                ("Favor 44 (30 or more)", 15),
                ("Favor invocation modifiers for Ombrin", 0),
            ],
        )
        bonuses = {row["outcome_name"]: row["bonus"] for row in response.json()["bonuses"]}
        self.assertEqual(bonuses, {"Success": 10, "Partial Success": 5})

    def test_resolve_endpoint_with_invocation(self) -> None:
        with (
            patch(_INVOCATION_CHECK, return_value=_result(self.invocation_type, self.success)),
            patch(
                _OPTION_CHECK,
                return_value=_result(self.investigation, self.success, total_points=58),
            ),
        ):
            response = self.client.post(
                f"/api/missions/journal/{self.instance.pk}/resolve/?entry_id={self.entry_id}",
                {
                    "option_id": self.option.pk,
                    "invoke_being_id": self.being.pk,
                    "invoke_line": "[player line]",
                },
                format="json",
            )
        self.assertEqual(response.status_code, 200, response.content)
        invocation = response.json()["invocation"]
        self.assertEqual(invocation["bonus"], 10)
        self.assertEqual(invocation["bonus_label"], "Ombrin's favor (invocation: Success)")
        self.assertTrue(invocation["call_line"].endswith("calls on Ombrin: [player line]"))
        self.assertEqual(FavorInvocation.objects.get().mission_instance, self.instance)

    def test_resolve_endpoint_refusal_is_a_400_with_the_reason(self) -> None:
        stranger = WorshippedBeingFactory(name="River Spirit")
        response = self.client.post(
            f"/api/missions/journal/{self.instance.pk}/resolve/?entry_id={self.entry_id}",
            {"option_id": self.option.pk, "invoke_being_id": stranger.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("You have no favor with River Spirit to call on.", str(response.json()))


class GroupInvokerBreakdownTests(MissionInvocationBase):
    def test_the_group_invoker_gets_their_breakdown_in_the_log(self) -> None:
        holder = _pc()
        partner = _pc()
        DevotionStandingFactory(character_sheet=holder.sheet_data, being=self.being, favor=12)
        template, option, _ = self._check_graph("group-log", conflict_mode=ConflictMode.JOINT)
        instance = staff_assign_mission(template, holder)
        share_mission(instance, partner)

        with (
            patch(_INVOCATION_CHECK, return_value=_result(self.invocation_type, self.success)),
            patch(
                _OPTION_CHECK,
                side_effect=lambda _character, check_type, **kw: _result(
                    check_type, self.success, total_points=kw["extra_modifiers"] + 40
                ),
            ),
            self.captureOnCommitCallbacks(execute=True),
        ):
            submit_group_pick(
                instance,
                holder,
                option_id=option.pk,
                invoke=InvocationChoice(being_id=self.being.pk),
            )
            submit_group_pick(instance, partner, option_id=option.pk)

        holder_bodies = list(
            NarrativeMessageDelivery.objects.filter(
                recipient_character_sheet=holder.sheet_data
            ).values_list("message__body", flat=True)
        )
        self.assertTrue(
            any(
                "Perception + Investigation: 40 + 10 Ombrin's favor (invocation: Success) = 50."
                in body
                for body in holder_bodies
            ),
            holder_bodies,
        )
        partner_bodies = " ".join(
            NarrativeMessageDelivery.objects.filter(
                recipient_character_sheet=partner.sheet_data
            ).values_list("message__body", flat=True)
        )
        self.assertNotIn("+ 10", partner_bodies)

"""Tests for the base Action class and types."""

from dataclasses import dataclass

from django.test import TestCase

from actions.base import Action
from actions.prerequisites import Prerequisite
from actions.registry import ACTIONS_BY_KEY, get_action, get_actions_for_target_type
from actions.types import ActionContext, ActionResult, TargetType
from evennia_extensions.factories import ObjectDBFactory


@dataclass
class AlwaysFailsPrerequisite(Prerequisite):
    reason: str = "Not available"

    def is_met(
        self,
        actor: object,
        target: object = None,
        context: object = None,
    ) -> tuple[bool, str]:
        return False, self.reason


@dataclass
class AlwaysPassesPrerequisite(Prerequisite):
    def is_met(
        self,
        actor: object,
        target: object = None,
        context: object = None,
    ) -> tuple[bool, str]:
        return True, ""


@dataclass
class SimpleTestAction(Action):
    key: str = "test"
    name: str = "Test"
    icon: str = "test"
    category: str = "test"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: object,
        context: ActionContext | None = None,
        **kwargs: object,
    ) -> ActionResult:
        return ActionResult(success=True, message="done")


@dataclass
class GatedTestAction(Action):
    key: str = "gated"
    name: str = "Gated"
    icon: str = "lock"
    category: str = "test"
    target_type: TargetType = TargetType.SINGLE

    def get_prerequisites(self) -> list[Prerequisite]:
        return [AlwaysFailsPrerequisite(reason="You need the key")]

    def execute(
        self,
        actor: object,
        context: ActionContext | None = None,
        **kwargs: object,
    ) -> ActionResult:
        return ActionResult(success=True, message="unlocked")


class ActionBaseTests(TestCase):
    def test_action_run_calls_execute(self):
        action = SimpleTestAction()
        actor = ObjectDBFactory(db_key="Alice")
        result = action.run(actor)
        assert result.success is True
        assert result.message == "done"

    def test_check_availability_passes_when_no_prerequisites(self):
        action = SimpleTestAction()
        actor = ObjectDBFactory(db_key="Alice")
        avail = action.check_availability(actor)
        assert avail.available is True
        assert avail.reasons == []

    def test_check_availability_fails_with_reason(self):
        action = GatedTestAction()
        actor = ObjectDBFactory(db_key="Alice")
        target = ObjectDBFactory(db_key="Door")
        avail = action.check_availability(actor, target=target)
        assert avail.available is False
        assert "You need the key" in avail.reasons

    def test_check_availability_with_multiple_prerequisites(self):
        @dataclass
        class MultiGatedAction(Action):
            key: str = "multi"
            name: str = "Multi"
            icon: str = "lock"
            category: str = "test"
            target_type: TargetType = TargetType.SELF

            def get_prerequisites(self) -> list[Prerequisite]:
                return [
                    AlwaysFailsPrerequisite(reason="Missing A"),
                    AlwaysPassesPrerequisite(),
                    AlwaysFailsPrerequisite(reason="Missing B"),
                ]

            def execute(
                self,
                actor: object,
                context: ActionContext | None = None,
                **kwargs: object,
            ) -> ActionResult:
                return ActionResult(success=True)

        action = MultiGatedAction()
        actor = ObjectDBFactory(db_key="Alice")
        avail = action.check_availability(actor)
        assert avail.available is False
        assert len(avail.reasons) == 2
        assert "Missing A" in avail.reasons
        assert "Missing B" in avail.reasons


class ActionRegistryTests(TestCase):
    def test_get_action_by_key(self):
        action = get_action("look")
        assert action is not None
        assert action.key == "look"

    def test_get_action_returns_none_for_unknown(self):
        assert get_action("nonexistent") is None

    def test_all_expected_actions_registered(self):
        expected_keys = {
            "look",
            "look_at_item",
            "inventory",
            "search",
            "say",
            "pose",
            "emit",
            "whisper",
            "pemit",
            "mutter",
            "get",
            "drop",
            "give",
            "equip",
            "unequip",
            "edit_room",
            "dig_room",
            "resize_room",
            "remove_room",
            "link_rooms",
            "unlink_rooms",
            "rename_exit",
            "place_room",
            "set_building_style",
            "place_room_fixture",
            "remove_room_fixture",
            "assign_room_tenant",
            "end_room_tenancy",
            "set_primary_home",
            "commission_decoration",
            "start_building_extension",
            "project_donate",
            "project_check",
            "project_story",
            "put_in",
            "take_out",
            "apply_outfit",
            "undress",
            "present_outfit",
            "judge_presentation",
            "traverse_exit",
            "home",
            "activate_permit",
            "use_item",
            "move_to_position",
            "set_the_stage",
            "start_round",
            "join_round",
            "leave_round",
            "end_round",
            "disarm_trap",
            "pass_round",
            "force_resolve_round",
            "set_round_mode",
            "scene_succor",
            "scene_interpose",
            "intimidate",
            "persuade",
            "deceive",
            "flirt",
            "seduce",
            "perform",
            "entrance",
            "challenge",
            "accept",
            "decline",
            "withdraw",
            "yield",
            "acknowledge_risk",
            "restore_sense",
            "resolve_entry_flourish",
            "perform_ritual",
            "imbue_thread",
            "weave_thread",
            "endorse_pose",
            "endorse_scene_entry",
            "endorse_style_presentation",
            "cast_technique",
            "combat_flee",
            "combat_cover",
            "combat_interpose",
            "combat_succor",
            "combat_ready",
            "combat_combo",
            "combat_revert",
            "combat_join",
            "combat_leave",
            "start_scene",
            "finish_scene",
            "add_encounter_participant",
            "add_opponent",
            "begin_encounter_round",
            "end_encounter",
            "pause_encounter",
            "preview_opponent_defaults",
            "remove_encounter_participant",
            "resolve_encounter_round",
            "set_active_persona",
            "shift_form",
            "revert_form",
            "set_social_consent_preference",
            "set_social_consent_category_rule",
            "add_social_consent_whitelist",
            "remove_social_consent_whitelist",
            "add_social_consent_blacklist",
            "remove_social_consent_blacklist",
            "resolve_alteration",
            "rest",
            "spread_tale",
            "save_deed_story",
            "complete_story",
            "resolve_episode",
            "promote_episode",
            "mark_beat",
            "declare_stakes",
            "manage_training",
            "purchase_unlock",
            "toggle_interaction_favorite",
            "toggle_interaction_reaction",
            "react_to_window",
            "npc_start",
            "npc_resolve",
            "npc_end",
            "org_invite",
            "org_apply",
            "org_join",
            "org_leave",
            "org_promote",
            "org_demote",
            "org_expel",
            "treat_condition",
            "create_first_impression",
            "create_development",
            "create_capstone",
            "redistribute_points",
            "create_journal_entry",
            "respond_to_journal",
            "edit_journal_entry",
            "set_character_goals",
            "log_goal_progress",
            "claim_kudos",
            "cast_vote",
            "remove_vote",
            "claim_random_scene",
            "reroll_random_scene",
            "set_path_intent",
            "clear_path_intent",
            "give_writeup_kudos",
            "file_writeup_complaint",
            "author_technique",
            "engage_covenant_membership",
            "disengage_covenant_membership",
            "leave_covenant",
            "kick_covenant_member",
            "assign_covenant_rank",
            "transfer_covenant_top_rank",
            "stand_down_battle_covenant",
            "event_create",
            "event_schedule",
            "event_start",
            "event_complete",
            "event_cancel",
            "event_invite",
            "respond_invitation",
            "sanctum_install",
            "sanctum_homecoming",
            "sanctum_purging",
            "sanctum_weave",
            "sanctum_dissolve",
            "sanctum_absorb",
            "sanctum_sever",
            "begin_battle_round",
            "resolve_battle_round",
            "conclude_battle",
            "declare_battle_action",
            "challenge_champion_duel",
            "signature_set",
            "signature_clear",
            "signature_list",
            "start_room_feature_project",
            "repair_lab_station",
            "commission_ship",
            "upgrade_ship",
            "repair_ship",
            "ship_status",
        }
        assert set(ACTIONS_BY_KEY.keys()) == expected_keys

    def test_get_actions_for_target_type(self):
        self_actions = get_actions_for_target_type(TargetType.SELF)
        self_keys = {a.key for a in self_actions}
        assert "inventory" in self_keys
        assert "home" in self_keys

    def test_single_target_actions(self):
        single_actions = get_actions_for_target_type(TargetType.SINGLE)
        single_keys = {a.key for a in single_actions}
        assert "look" in single_keys
        assert "get" in single_keys
        assert "whisper" in single_keys

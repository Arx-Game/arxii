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
            "identify",
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
            "tag_room_resonance",
            "untag_room_resonance",
            "commission_decoration",
            "start_building_extension",
            "start_building_renovation",
            "settle_building_arrears",
            "refurbish_building",
            "prepare_building",
            "toggle_ultra_upkeep",
            "project_donate",
            "project_check",
            "project_story",
            "launch_propaganda_campaign",
            "put_in",
            "take_out",
            "steal",
            "set_container_policy",
            "withdraw_coins",
            "deposit_coins",
            "give_coins",
            "apply_outfit",
            "undress",
            "save_outfit",
            "rename_outfit",
            "delete_outfit",
            "add_outfit_slot",
            "remove_outfit_slot",
            "present_outfit",
            "judge_presentation",
            "traverse_exit",
            "travel_to",
            "stop_travel",
            "home",
            "activate_permit",
            "use_item",
            "grant_item",
            "gm_award_distinction",
            # #2183 — dramatic-moment suggestion confirm/dismiss (account-authorized GM inbox).
            "confirm_dramatic_moment_suggestion",
            "dismiss_dramatic_moment_suggestion",
            "craft_attach_facet",
            "craft_detach_facet",
            "craft_attach_style",
            "craft_create_item",
            "move_to_position",
            "take_position",
            "gm_place_in_position",
            "set_the_stage",
            "set_situation",
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
            "blackmail",
            "coerce",
            "mint_accusation",
            "reveal_secret",
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
            "resolve_crossing_offer",
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
            "combat_charge",
            "combat_joust",
            "combat_use",
            "combat_engage",
            "combat_disengage",
            "combat_rally",
            "combat_demoralize",
            "combat_taunt",
            "combat_parley",
            "combat_ready",
            "combat_combo",
            "combat_revert",
            "combat_join",
            "combat_leave",
            "start_scene",
            "finish_scene",
            "grant_scene_gm",
            "add_encounter_participant",
            "add_opponent",
            "begin_encounter_round",
            "end_encounter",
            "pause_encounter",
            "preview_opponent_defaults",
            "remove_encounter_participant",
            "resolve_encounter_round",
            "set_active_persona",
            "join_place",
            "leave_place",
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
            "relationship_bump",
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
            "select_path",
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
            "open_place_encounter",
            "join_place_encounter",
            "signature_set",
            "signature_clear",
            "signature_list",
            "bind_motif_style",
            "unbind_motif_style",
            "list_motif_styles",
            "start_room_feature_project",
            "repair_lab_station",
            "market_buy_stock",
            "market_buy_ware",
            "market_list_ware",
            "market_finish_ware",
            "market_set_service_offer",
            "market_service_craft",
            "commission_ship",
            "upgrade_ship",
            "repair_ship",
            "ship_status",
            "bind_companion",
            "companion_fight",
            "deploy_companion",
            "release_companion",
            "order_companion",
            "mount_companion",
            "dismount_companion",
            "lock_exit",
            "unlock_exit",
            "pick_lock",
            "break_exit",
            "open_window",
            "close_window",
            # #2116 — gift/technique/thread-weaving acquisition surface.
            "purchase_gift_unlock",
            "accept_technique_offer",
            "accept_thread_weaving_offer",
            # #2119 — player-GM recruitment loop: GroupStoryRequest lifecycle.
            "request_gm_for_covenant",
            "claim_group_story_request",
            "withdraw_group_story_request",
            # #2118 — GM adjudication toolkit: catalog check invocation, awards, conditions.
            "gm_invoke_check",
            "gm_award_progression",
            "gm_apply_condition",
            # #2127 — GM scenario catalog: situation find/browse + suggestion inbox.
            "gm_find_situation",
            "gm_submit_catalog_suggestion",
            # #2010 — GM battle staging: JUNIOR-gated catalog-pick-to-live-Battle actions.
            "create_battle",
            "stage_battle_map",
            "spawn_battle_units",
            "enlist_battle_participant",
            "browse_battle_catalog",
            "collect_food",
            # #2222 — portal anchor install/dissolve.
            "portal_anchor_install",
            "portal_anchor_dissolve",
            # #2179 — vault access-list management.
            "vault_access_add",
            "vault_access_remove",
            "vault_access_list",
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

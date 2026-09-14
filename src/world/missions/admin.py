"""Admin for the mission graph's authored config tables (#3831).

Missions are normally authored through the Mission Studio React editor
(``world/missions/services`` + the frontend graph canvas), not through this
admin - the graph's cross-row invariants (route-set completeness, single
entry node, etc.) are enforced by the Studio's authoring/resolution service,
not by these `ModelAdmin` pages. These registrations exist so staff without
Studio access still have a table-level view of every authored row, and so
there is a fallback editor when the Studio is unavailable or a fixture needs
a one-off correction. Runtime/play-state models (``MissionInstance``,
``MissionParticipant``, ``MissionInvite``, etc.) are intentionally NOT
registered here - they are per-run rows, not staff-authored config.
"""

from django.contrib import admin

from world.missions.models import (
    MissionAssistPattern,
    MissionCategory,
    MissionGiver,
    MissionNode,
    MissionNodeSupportOption,
    MissionOption,
    MissionOptionOpponentLine,
    MissionOptionRoute,
    MissionOptionRouteCandidate,
    MissionOptionRouteReward,
    MissionRenownAward,
    MissionTemplate,
)


@admin.register(MissionCategory)
class MissionCategoryAdmin(admin.ModelAdmin):
    """#3831 - the content-type tag catalog (assassination, heist, courtly, ...)."""

    list_display = ["name", "display_order"]
    search_fields = ["name", "description"]
    list_editable = ["display_order"]


@admin.register(MissionTemplate)
class MissionTemplateAdmin(admin.ModelAdmin):
    """#3831 - an authored mission: the static graph plus its availability metadata."""

    list_display = [
        "name",
        "level_band_min",
        "level_band_max",
        "risk_tier",
        "arc_scope",
        "visibility",
        "is_active",
    ]
    list_filter = ["arc_scope", "visibility", "is_active", "risk_tier"]
    search_fields = ["name", "summary"]
    list_select_related = ["created_in_era", "report_to_role"]
    autocomplete_fields = ["created_in_era", "report_to_role"]
    filter_horizontal = ["categories"]


@admin.register(MissionNode)
class MissionNodeAdmin(admin.ModelAdmin):
    """#3831 - one decision point in a mission graph."""

    list_display = ["template", "key", "is_entry", "conflict_mode", "location_mode"]
    list_filter = ["is_entry", "conflict_mode", "location_mode"]
    search_fields = ["key", "template__name"]
    list_select_related = ["template", "target_area"]
    autocomplete_fields = [
        "template",
        "target_area",
        "track_success_target",
        "track_failure_target",
    ]


@admin.register(MissionOption)
class MissionOptionAdmin(admin.ModelAdmin):
    """#3831 - one choice available at a MissionNode."""

    list_display = ["node", "order", "key", "option_kind", "source_kind"]
    list_filter = ["option_kind", "source_kind", "encounter_risk_level"]
    search_fields = ["key", "node__key", "authored_ic_framing"]
    list_select_related = ["node", "authored_check_type", "branch_target", "challenge"]
    autocomplete_fields = [
        "node",
        "authored_check_type",
        "branch_target",
        "challenge",
        "opposition_sheet",
        "opposition_check_type",
    ]


@admin.register(MissionOptionOpponentLine)
class MissionOptionOpponentLineAdmin(admin.ModelAdmin):
    """#3831 - an authored opponent an ENCOUNTER option spawns."""

    list_display = ["option", "creature_template", "count", "position_name", "order"]
    list_select_related = ["option", "creature_template"]
    autocomplete_fields = ["option", "creature_template"]
    search_fields = ["option__key", "creature_template__name"]


@admin.register(MissionOptionRoute)
class MissionOptionRouteAdmin(admin.ModelAdmin):
    """#3831 - where a MissionOption leads (one row per resolved outcome tier)."""

    list_display = ["option", "outcome_tier", "target_node", "is_random_set", "beat_outcome"]
    list_filter = ["is_random_set", "beat_outcome"]
    search_fields = ["option__key", "option__node__key"]
    list_select_related = ["option", "outcome_tier", "target_node"]
    autocomplete_fields = ["option", "outcome_tier", "target_node", "consequence"]


@admin.register(MissionOptionRouteCandidate)
class MissionOptionRouteCandidateAdmin(admin.ModelAdmin):
    """#3831 - one weighted destination in a randomized MissionOptionRoute."""

    list_display = ["route", "target_node", "weight"]
    search_fields = ["route__option__key", "target_node__key"]
    list_select_related = ["route", "target_node"]
    autocomplete_fields = ["route", "target_node", "consequence"]


@admin.register(MissionOptionRouteReward)
class MissionOptionRouteRewardAdmin(admin.ModelAdmin):
    """#3831 - authored reward template attached to a route or a route candidate."""

    list_display = ["kind", "sink", "route", "candidate", "amount", "contract_holder_only"]
    list_filter = ["kind", "sink", "contract_holder_only"]
    list_select_related = ["route", "candidate"]
    autocomplete_fields = ["route", "candidate", "resonance", "item_template", "followon_offer"]


@admin.register(MissionRenownAward)
class MissionRenownAwardAdmin(admin.ModelAdmin):
    """#3831 - authored Renown award bundle attached to a route."""

    list_display = ["route", "magnitude", "risk", "reach_override", "contract_holder_only"]
    list_filter = ["magnitude", "risk", "contract_holder_only"]
    list_select_related = ["route"]
    autocomplete_fields = ["route"]
    filter_horizontal = ["archetypes"]


@admin.register(MissionAssistPattern)
class MissionAssistPatternAdmin(admin.ModelAdmin):
    """#3831 - catalog row auto-offering support moves wherever context + qualifier match."""

    list_display = ["name", "support_check_type", "difficulty", "easing", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name"]
    list_select_related = ["capability", "support_check_type"]
    autocomplete_fields = ["capability", "support_check_type", "complication_consequence"]
    filter_horizontal = ["check_types", "challenge_categories"]


@admin.register(MissionNodeSupportOption)
class MissionNodeSupportOptionAdmin(admin.ModelAdmin):
    """#3831 - authored gem: a per-node support move adding to or suppressing patterns."""

    list_display = ["node", "flavor_template", "difficulty", "easing", "suppress_patterns"]
    list_filter = ["suppress_patterns"]
    search_fields = ["node__key", "flavor_template"]
    list_select_related = ["node", "capability", "support_check_type"]
    autocomplete_fields = ["node", "capability", "support_check_type", "complication_consequence"]


@admin.register(MissionGiver)
class MissionGiverAdmin(admin.ModelAdmin):
    """#3831 - an abstracted offer point publishing a curated set of mission templates."""

    list_display = ["name", "giver_kind", "org", "is_active"]
    list_filter = ["giver_kind", "is_active"]
    search_fields = ["name"]
    raw_id_fields = ["target"]
    autocomplete_fields = ["org"]
    filter_horizontal = ["templates"]

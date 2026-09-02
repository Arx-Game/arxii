# Arx II Model Introspection Report
# Generated for CLAUDE.md enrichment


## actions

### ActionEnhancement
**Foreign Keys:**
  - distinction -> distinctions.Distinction [FK] (nullable)
  - condition -> conditions.ConditionTemplate [FK] (nullable)
  - technique -> magic.Technique [FK] (nullable)
**Pointed to by:**
  - modifykwargsconfig_configs <- actions.ModifyKwargsConfig
  - addmodifierconfig_configs <- actions.AddModifierConfig
  - conditiononcheckconfig_configs <- actions.ConditionOnCheckConfig
  - removeconditiononcheckconfig_configs <- actions.RemoveConditionOnCheckConfig

### ActionTemplate
**Foreign Keys:**
  - check_type -> checks.CheckType [FK]
  - consequence_pool -> actions.ConsequencePool [FK] (nullable)
  - consent_category -> consent.SocialConsentCategory [FK] (nullable)
**Pointed to by:**
  - gates <- actions.ActionTemplateGate
  - challenge_approaches <- mechanics.ChallengeApproach
  - techniques <- magic.Technique
  - scene_action_requests <- scenes.SceneActionRequest

### ActionTemplateGate
**Foreign Keys:**
  - action_template -> actions.ActionTemplate [FK]
  - check_type -> checks.CheckType [FK]
  - consequence_pool -> actions.ConsequencePool [FK] (nullable)

### AddModifierConfig
**Foreign Keys:**
  - enhancement -> actions.ActionEnhancement [FK]

### ConditionOnCheckConfig
**Foreign Keys:**
  - enhancement -> actions.ActionEnhancement [FK]
  - check_type -> checks.CheckType [FK]
  - resistance_check_type -> checks.CheckType [FK] (nullable)
  - condition -> conditions.ConditionTemplate [FK]
  - immunity_condition -> conditions.ConditionTemplate [FK] (nullable)

### ConsequencePool
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - parent -> actions.ConsequencePool [FK] (nullable)
**Pointed to by:**
  - children <- actions.ConsequencePool
  - entries <- actions.ConsequencePoolEntry
  - action_templates <- actions.ActionTemplate
  - action_template_gates <- actions.ActionTemplateGate
  - consequence_outcomes <- checks.ConsequenceOutcome
  - wound_pool_damage_types <- conditions.DamageType
  - death_pool_damage_types <- conditions.DamageType
  - condition_stages <- conditions.ConditionStage
  - property_detonations <- mechanics.PropertyDetonation
  - situation_trap_links <- mechanics.SituationTrapLink
  - context_attachments <- mechanics.ContextConsequencePool
  - resonance_interactions <- magic.AffinityInteraction
  - mishap_tiers <- magic.MishapPoolTier
  - situation_guides <- gm.ConsequencePoolGuide
  - traps <- room_features.Trap
  - success_beats <- stories.Beat
  - failure_beats <- stories.Beat
  - expired_beats <- stories.Beat
  - task_templates <- tasking.TaskTemplate

### ConsequencePoolEntry
**Foreign Keys:**
  - pool -> actions.ConsequencePool [FK]
  - consequence -> checks.Consequence [FK]

### ModifyKwargsConfig
**Foreign Keys:**
  - enhancement -> actions.ActionEnhancement [FK]

### RemoveConditionOnCheckConfig
**Foreign Keys:**
  - enhancement -> actions.ActionEnhancement [FK]
  - check_type -> checks.CheckType [FK]
  - resistance_check_type -> checks.CheckType [FK] (nullable)
  - condition -> conditions.ConditionTemplate [FK]

### Service Functions
- `advance_resolution(pending: 'PendingActionResolution', context: 'ResolutionContext', player_decision: 'str | None' = None) -> 'PendingActionResolution' - Resume a paused pipeline after player decision.`
- `apply_resolution(pending: 'PendingResolution', context: 'ResolutionContext') -> 'list[AppliedEffect]' - Apply all effects from the selected consequence.`
- `get_effective_consequences(pool: 'ConsequencePool') -> 'list[WeightedConsequence]' - Resolve pool inheritance into a flat list of weighted consequences.`
- `perform_check(character: 'ObjectDB', check_type: 'CheckType', target_difficulty: int = 0, extra_modifiers: int = 0, effort_level: str | None = None, fatigue_penalty: int = 0, specialization: 'Specialization | None' = None, *, situation_ctx: 'SituationContext | None' = None, level_override: int | None = None, stat_override: str | int | None = None) -> world.checks.types.CheckResult - Main check resolution function.`
- `resolve_scene_action(*, character: 'ObjectDB', action_template: 'ActionTemplate | None', action_key: 'str', difficulty: 'int') -> 'SceneActionResult' - Resolve a scene-based action check using an ActionTemplate.`
- `select_consequence_from_result(character: 'ObjectDB', check_result: 'CheckResult', consequences: 'list[WeightedConsequence]') -> 'PendingResolution' - Select a consequence using an existing check result.`
- `start_action_resolution(character: 'ObjectDB', template: 'ActionTemplate', target_difficulty: 'int', context: 'ResolutionContext', extra_modifiers: 'int' = 0, *, check_type: 'CheckType | None' = None, effort_level: 'str | None' = None) -> 'PendingActionResolution' - Start an action resolution pipeline and run it to completion or pause.`


## behaviors

### BehaviorPackageDefinition
**Pointed to by:**
  - instances <- behaviors.BehaviorPackageInstance

### BehaviorPackageInstance
**Foreign Keys:**
  - definition -> behaviors.BehaviorPackageDefinition [FK]
  - obj -> evennia.ObjectDB [FK]


## evennia_extensions

### Artist
**Foreign Keys:**
  - player_data -> evennia_extensions.PlayerData [OneToOne]
**Pointed to by:**
  - created_media <- evennia_extensions.Media

### ExitProfile
**Foreign Keys:**
  - objectdb -> evennia.ObjectDB [OneToOne]
**Pointed to by:**
  - bars_details <- room_features.ExitBarsDetails
  - defense_progression_projects <- room_features.DefenseProgressionDetails

### Media
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - player_data -> evennia_extensions.PlayerData [FK] (nullable)
  - created_by -> evennia_extensions.Artist [FK] (nullable)
**Pointed to by:**
  - tenure_links <- roster.TenureMedia
  - condition_template_thumbnails <- conditions.ConditionTemplate
  - condition_stage_thumbnails <- conditions.ConditionStage
  - starting_area_crests <- character_creation.StartingArea
  - beginnings_art <- character_creation.Beginnings
  - codex_entries <- codex.CodexEntry
  - profile_for_players <- evennia_extensions.PlayerData
  - page_backgrounds <- evennia_extensions.PageBackground
  - thumbnailed_objects <- evennia_extensions.ObjectDisplayData
  - combat_opponent_portraits <- combat.CombatOpponent
  - alternate_self_thumbnails <- forms.AlternateSelf
  - item_templates <- items.ItemTemplate
  - item_instances <- items.ItemInstance
  - persona_thumbnails <- scenes.Persona

### ObjectDisplayData
**Foreign Keys:**
  - object -> evennia.ObjectDB [OneToOne]
  - thumbnail -> evennia_extensions.Media [FK] (nullable)

### PageBackground
**Foreign Keys:**
  - art -> evennia_extensions.Media [FK] (nullable)

### PlayerAllowList
**Foreign Keys:**
  - owner -> evennia_extensions.PlayerData [FK]
  - allowed_player -> evennia_extensions.PlayerData [FK]

### PlayerData
**Foreign Keys:**
  - account -> evennia.AccountDB [OneToOne]
  - profile_picture -> evennia_extensions.Media [FK] (nullable)
  - contributor -> contributors.ContentContributor [OneToOne] (nullable)
  - selected_entry -> roster.RosterEntry [FK] (nullable)
**Pointed to by:**
  - applications <- roster.RosterApplication
  - reviewed_applications <- roster.RosterApplication
  - sent_invites <- roster.GameInvite
  - tenures <- roster.RosterTenure
  - approved_tenures <- roster.RosterTenure
  - content_boundaries <- boundaries.PlayerBoundary
  - artist_profile <- evennia_extensions.Artist
  - media <- evennia_extensions.Media
  - allow_list <- evennia_extensions.PlayerAllowList
  - allowed_by <- evennia_extensions.PlayerAllowList
  - blocks_made <- scenes.Block
  - blocks_received <- scenes.Block
  - mutes_made <- scenes.Mute
  - mutes_received <- scenes.Mute
  - treasured_signoffs <- stories.TreasuredSignoff

### RoomDescVariant
**Foreign Keys:**
  - room_profile -> evennia_extensions.RoomProfile [FK]

### RoomProfile
**Foreign Keys:**
  - objectdb -> evennia.ObjectDB [OneToOne]
  - area -> areas.Area [FK] (nullable)
  - size -> evennia_extensions.RoomSizeTier [FK] (nullable)
  - default_blueprint -> areas.PositionBlueprint [FK] (nullable)
**Pointed to by:**
  - boards <- boards.Board
  - entry_for_buildings <- buildings.Building
  - design_details <- buildings.InteriorDesignDetails
  - polish_by_category <- buildings.RoomPolish
  - decorations <- buildings.RoomDecoration
  - held_captivities <- captivity.Captivity
  - ceremonies <- ceremonies.Ceremony
  - starting_area_default <- character_creation.StartingArea
  - beginnings_start <- character_creation.Beginnings
  - residents <- character_sheets.CharacterSheet
  - hidden_clues <- clues.RoomClue
  - clue_triggers <- clues.ClueTrigger
  - desc_variants <- evennia_extensions.RoomDescVariant
  - durance_training_sites <- progression.DuranceTrainingSite
  - resonance_grants <- magic.ResonanceGrant
  - portal_anchors <- magic.PortalAnchor
  - dream_reflection <- dreams.DreamReflection
  - reflection_of <- dreams.DreamReflection
  - descent_source <- dreams.DreamReflection
  - events <- events.Event
  - story_grants <- gm.StoryRoomGrant
  - summon_offers <- gm.GMSummonOffer
  - instance_data <- instances.InstancedRoom
  - placed_items <- items.RoomItem
  - feature_instance <- room_features.RoomFeatureInstance
  - feature_progression_projects <- room_features.RoomFeatureProgressionDetails
  - traps <- room_features.Trap
  - prepared_grounds <- room_features.PreparedGround
  - ward_details <- room_features.RoomWardDetails
  - alarm_details <- room_features.RoomAlarmDetails
  - defense_progression_projects <- room_features.DefenseProgressionDetails
  - functionaries <- npc_services.Functionary
  - npc_assignments <- npc_services.NPCAssignment
  - expulsion_bars <- npc_services.ExpulsionBar
  - crafting_service_offers <- items.CraftingServiceOffer
  - crime_evidence <- justice.CrimeEvidence
  - stat_overrides <- locations.LocationValueOverride
  - stat_modifiers <- locations.LocationValueModifier
  - ownership_records <- locations.LocationOwnership
  - tenancy_records <- locations.LocationTenancy
  - ambient_emote_lines <- narrative.AmbientEmoteLine
  - ambient_emits <- narrative.AmbientEmit
  - scene_rounds <- scenes.SceneRound
  - places <- scenes.Place
  - speaker_queues <- scenes.SpeakerQueue
  - travel_hub <- travel.TravelHub

### RoomSizeTier
**Pointed to by:**
  - rooms <- evennia_extensions.RoomProfile


## flows

### FlowDefinition
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
**Pointed to by:**
  - steps <- flows.FlowStepDefinition
  - triggerdefinition_set <- flows.TriggerDefinition
  - consequence_effects <- checks.ConsequenceEffect
  - rituals <- magic.Ritual

### FlowStepDefinition
**Foreign Keys:**
  - flow -> flows.FlowDefinition [FK]
  - parent -> flows.FlowStepDefinition [FK] (nullable)
**Pointed to by:**
  - children <- flows.FlowStepDefinition

### Trigger
**Foreign Keys:**
  - trigger_definition -> flows.TriggerDefinition [FK]
  - obj -> evennia.ObjectDB [FK]
  - source_condition -> conditions.ConditionInstance [FK] (nullable)
  - source_stage -> conditions.ConditionStage [FK] (nullable)
**Pointed to by:**
  - data <- flows.TriggerData

### TriggerData
**Foreign Keys:**
  - trigger -> flows.Trigger [FK]

### TriggerDefinition
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - flow_definition -> flows.FlowDefinition [FK]
**Pointed to by:**
  - trigger_set <- flows.Trigger
  - installing_templates <- conditions.ConditionTemplate


## web.admin

### AdminExcludedModel

### AdminPinnedModel

### Service Functions
- `analyze_fixture(fixture_data: 'str') -> 'FixtureAnalysis' - Dry-run analysis comparing fixture JSON against the current database.`
- `count_natural_key_args(model: 'type', _seen: 'set[type] | None' = None) -> 'int' - Recursively count how many args a model's natural key consumes.`
- `execute_import(fixture_data: 'str', model_actions: 'dict[str, str]') -> 'ImportResult' - Execute an atomic import of fixture data.`
- `resolve_model_by_name(model_key: 'str') -> 'type[models.Model]' - Resolve ``"<label>.<model_name>"`` (or a bare ``"<model_name>"``), mostly ignoring the label.`


## world.achievements

### Achievement
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - prerequisite -> achievements.Achievement [FK] (nullable)
**Pointed to by:**
  - next_in_chain <- achievements.Achievement
  - requirements <- achievements.AchievementStatRequirement
  - discovery <- achievements.Discovery
  - character_achievements <- achievements.CharacterAchievement
  - rewards <- achievements.AchievementReward
  - achievementrequirement_set <- progression.AchievementRequirement
  - aura_affinity_thresholds <- magic.AuraAffinityThreshold
  - crossing_options <- magic.CrossingOption

### AchievementReward
**Foreign Keys:**
  - achievement -> achievements.Achievement [FK]
  - reward -> achievements.RewardDefinition [FK]

### AchievementStatRequirement
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - achievement -> achievements.Achievement [FK]
  - stat -> achievements.StatDefinition [FK]

### CharacterAchievement
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - achievement -> achievements.Achievement [FK]
  - earned_by_tenure -> roster.RosterTenure [FK]

### ConditionStatRule
**Foreign Keys:**
  - stat -> achievements.StatDefinition [FK]
  - condition -> conditions.ConditionTemplate [FK]

### Discovery
**Foreign Keys:**
  - achievement -> achievements.Achievement [OneToOne]
  - discovered_by_tenure -> roster.RosterTenure [FK]
  - shared_with_tenures -> roster.RosterTenure [M2M]

### PersonaTitle
**Foreign Keys:**
  - persona -> scenes.Persona [FK]
  - reward -> achievements.RewardDefinition [FK] (nullable)
  - legend_entry -> societies.LegendEntry [FK] (nullable)

### RewardDefinition
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - modifier_target -> mechanics.ModifierTarget [FK] (nullable)
  - distinction -> distinctions.Distinction [FK] (nullable)
**Pointed to by:**
  - achievement_rewards <- achievements.AchievementReward
  - persona_titles <- achievements.PersonaTitle

### StatDefinition
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
**Pointed to by:**
  - trackers <- achievements.StatTracker
  - requirements <- achievements.AchievementStatRequirement
  - condition_rules <- achievements.ConditionStatRule

### StatTracker
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - stat -> achievements.StatDefinition [FK]

### Service Functions
- `apply_achievement_rewards(character_sheet: 'CharacterSheet', achievement: 'Achievement') -> 'None' - Apply an achievement's rewards to a character — title / bonus / prestige / distinction`
- `can_earn_achievements(character_sheet: 'CharacterSheet') -> 'bool' - Whether ``character_sheet`` may earn achievements at all (#3024).`
- `get_stat(character_sheet: 'CharacterSheet', stat: 'StatDefinition') -> 'int' - Return current value of a stat tracker, 0 if it doesn't exist.`
- `grant_achievement(achievement: 'Achievement', character_sheets: 'list[CharacterSheet]') -> 'AchievementGrantResult' - Grant an achievement to one or more characters simultaneously.`
- `increment_stat(character_sheet: 'CharacterSheet', stat: 'StatDefinition', amount: 'int' = 1) -> 'int' - Increment a stat tracker (create if needed) and check for achievements.`
- `increment_stat_for_group(character_sheets: 'list[CharacterSheet]', stat: 'StatDefinition', amount: 'int' = 1) -> 'None' - Increment a stat for several sheets as one simultaneous group moment.`
- `maybe_grant_deed_title(deed: 'LegendEntry') -> 'PersonaTitle | None' - Mint a title when a deed crosses its station's threshold (#3466).`


## world.action_points

### ActionPointConfig

### ActionPointPool
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [OneToOne]


## world.agriculture

### CropType
**Pointed to by:**
  - fields <- agriculture.FieldDetails

### FieldDetails
**Foreign Keys:**
  - feature_instance -> room_features.RoomFeatureInstance [OneToOne]
  - crop_type -> agriculture.CropType [FK]

### FoodConfig

### FoodStockpile
**Foreign Keys:**
  - domain -> societies.Domain [OneToOne]

### FoodTransfer
**Foreign Keys:**
  - source_domain -> societies.Domain [FK]
  - target_domain -> societies.Domain [FK]
  - acting_persona -> scenes.Persona [FK] (nullable)

### GranaryDetails
**Foreign Keys:**
  - feature_instance -> room_features.RoomFeatureInstance [OneToOne]

### Service Functions
- `collect_field_food(character, field_instance) -> 'FoodCollectionResult' - One active collection dispatch from a Field's uncollected pool.`
- `domain_consumption_tick() -> 'dict[str, int]' - Weekly cron: each domain's population consumes food from its stockpile.`
- `field_production_tick() -> 'dict[str, int]' - Daily cron: accrue food into every active Field's uncollected pool.`
- `get_food_config() -> 'FoodConfig' - Lazy-create and return the FoodConfig singleton (pk=1).`
- `handle_field_progression(project: 'Project', target_level: 'int', outcome_tier: 'CheckOutcome | None' = None) -> 'None' - FIELD strategy: install or level the feature instance + create FieldDetails.`
- `handle_granary_progression(project: 'Project', target_level: 'int', outcome_tier: 'CheckOutcome | None' = None) -> 'None' - GRANARY strategy: install or level the feature instance + create GranaryDetails.`
- `max_food_capacity(domain: 'Domain') -> 'int' - Sum the capacity contribution of all active Granaries in the domain.`
- `provision_army(covenant) -> 'float' - Compute and deduct army food provisioning at mobilization.`
- `provision_ship_leg(voyage) -> 'float' - Compute and deduct ship crew food for one voyage leg.`
- `resolve_domain_for_feature(room_feature_instance: 'RoomFeatureInstance') -> 'Domain | None' - Walk the Area parent chain to find the Domain for a room feature.`
- `transfer_food(*, source_domain, target_domain, amount: 'int', acting_persona=None, character=None) -> 'FoodTransferResult' - Move food from source stockpile to target stockpile (#2219).`


## world.areas

### Area
**Foreign Keys:**
  - parent -> areas.Area [FK] (nullable)
  - realm -> realms.Realm [FK] (nullable)
  - climate -> weather.Climate [FK] (nullable)
  - art -> evennia_extensions.Media [FK] (nullable)
  - dominant_society -> societies.Society [FK] (nullable)
  - exile_destination -> evennia_extensions.RoomProfile [FK] (nullable)
  - allowed_building_kinds -> buildings.BuildingKind [M2M]
**Pointed to by:**
  - children <- areas.Area
  - quality <- areas.AreaQuality
  - cleanup_projects <- areas.CleanupProjectDetails
  - weather_state <- weather.RegionWeatherState
  - battles <- battles.Battle
  - city_defense_projects <- battles.CityDefenseDetails
  - property_grant_profiles <- buildings.PropertyGrantProfile
  - building_profile <- buildings.Building
  - building_permits_valid_in <- buildings.BuildingPermitDetails
  - construction_projects <- buildings.BuildingConstructionDetails
  - rooms <- evennia_extensions.RoomProfile
  - turf <- societies.NeighborhoodTurf
  - gang_turf_projects <- societies.GangTurfDetails
  - domain_profile <- societies.Domain
  - income_streams <- currency.OrgIncomeStream
  - build_grants <- gm.AreaBuildGrant
  - story_ownership <- gm.StoryArea
  - name_cultures <- npc_services.NameCulture
  - default_permits_offered <- npc_services.PermitOfferDetails
  - market_squares <- items.MarketSquare
  - laws <- justice.AreaLaw
  - heat_rows <- justice.PersonaHeat
  - lie_low_states <- justice.LieLowState
  - pardons <- justice.PardonGrant
  - guard_encounters <- justice.GuardEncounter
  - justice_cases <- justice.JusticeCase
  - exile_decrees <- justice.ExileDecree
  - stat_overrides <- locations.LocationValueOverride
  - stat_modifiers <- locations.LocationValueModifier
  - ownership_records <- locations.LocationOwnership
  - tenancy_records <- locations.LocationTenancy
  - ambient_emote_lines <- narrative.AmbientEmoteLine
  - ambient_emits <- narrative.AmbientEmit
  - predator_bands <- predators.PredatorBand
  - gossip_heat <- secrets.SecretGossip

### AreaClosure
**Foreign Keys:**
  - ancestor -> areas.Area [FK]
  - descendant -> areas.Area [FK]

### AreaQuality
**Foreign Keys:**
  - area -> areas.Area [OneToOne]

### BlueprintEdge
**Foreign Keys:**
  - blueprint -> areas.PositionBlueprint [FK]
  - position_a -> areas.BlueprintPosition [FK]
  - position_b -> areas.BlueprintPosition [FK]
  - gating_challenge_template -> mechanics.ChallengeTemplate [FK] (nullable)

### BlueprintPosition
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - blueprint -> areas.PositionBlueprint [FK]
**Pointed to by:**
  - edges_as_a <- areas.BlueprintEdge
  - edges_as_b <- areas.BlueprintEdge
  - shelters <- areas.BlueprintPositionShelter

### BlueprintPositionShelter
**Foreign Keys:**
  - blueprint_position -> areas.BlueprintPosition [FK]
  - damage_type -> conditions.DamageType [FK]

### CleanupProjectDetails
**Foreign Keys:**
  - project -> projects.Project [OneToOne]
  - target_area -> areas.Area [FK]
**Pointed to by:**
  - tier_thresholds <- areas.CleanupTierThreshold

### CleanupTierThreshold
**Foreign Keys:**
  - details -> areas.CleanupProjectDetails [FK]
  - outcome_tier -> traits.CheckOutcome [FK]

### ObjectPosition
**Foreign Keys:**
  - objectdb -> evennia.ObjectDB [OneToOne]
  - position -> areas.Position [FK]

### Position
**Foreign Keys:**
  - room -> evennia.ObjectDB [FK]
  - elevation_anchor -> areas.Position [FK] (nullable)
**Pointed to by:**
  - elevated_over <- areas.Position
  - edges_as_a <- areas.PositionEdge
  - edges_as_b <- areas.PositionEdge
  - occupants <- areas.ObjectPosition
  - shelters <- areas.PositionShelter
  - rampart <- areas.Rampart
  - cast_destination_instances <- conditions.ConditionInstance
  - cast_position_a_instances <- conditions.ConditionInstance
  - cast_position_b_instances <- conditions.ConditionInstance
  - traps <- room_features.Trap

### PositionBlueprint
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
**Pointed to by:**
  - positions <- areas.BlueprintPosition
  - edges <- areas.BlueprintEdge
  - rooms_defaulting <- evennia_extensions.RoomProfile

### PositionEdge
**Foreign Keys:**
  - position_a -> areas.Position [FK]
  - position_b -> areas.Position [FK]
  - gating_challenge -> mechanics.ChallengeInstance [FK] (nullable)
  - created_by_sheet -> character_sheets.CharacterSheet [FK] (nullable)

### PositionShelter
**Foreign Keys:**
  - position -> areas.Position [FK]
  - damage_type -> conditions.DamageType [FK]

### Rampart
**Foreign Keys:**
  - position -> areas.Position [OneToOne]
  - element_profile -> areas.RampartElementProfile [FK]
  - created_by_sheet -> character_sheets.CharacterSheet [FK] (nullable)

### RampartElementProfile
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - signature_damage_type -> conditions.DamageType [FK] (nullable)
  - signature_condition -> conditions.ConditionTemplate [FK] (nullable)
**Pointed to by:**
  - resistances <- areas.RampartElementResistance
  - rampart_set <- areas.Rampart

### RampartElementResistance
**Foreign Keys:**
  - profile -> areas.RampartElementProfile [FK]
  - damage_type -> conditions.DamageType [FK]

### Service Functions
- `area_for_scene(scene: 'Scene | None') -> 'Area | None' - Resolve the Area for a scene's location, or None.`
- `area_grid_path(area: 'Area') -> 'list[tuple[int | None, int | None]]' - Return the chain of parent-local (grid_x, grid_y) pairs from root to ``area``.`
- `area_subtree_pks(area: 'Area') -> 'list[int]' - Return pks of ``area`` and all its descendants.`
- `colored_area_path(room: 'ObjectDB') -> 'str' - Render a room's full area-hierarchy path with per-area colours (#1463).`
- `get_ancestor_at_level(area: 'Area', target_level: 'AreaLevel') -> 'Area | None' - Walk the ancestry to find the ancestor at the given AreaLevel.`
- `get_ancestry(area: 'Area') -> 'list[Area]' - Return the full ancestor chain from root down to this area.`
- `get_descendant_areas(area: 'Area') -> 'list[Area]' - Return all areas in the subtree below this area.`
- `get_effective_realm(area: 'Area') -> 'Realm | None' - Walk up the hierarchy to find the nearest realm assignment.`
- `get_room_profile(room_obj: 'ObjectDB') -> 'RoomProfile' - Get or create the RoomProfile for a room ObjectDB instance.`
- `get_rooms_in_area(area: 'Area') -> 'list[RoomProfile]' - Return all RoomProfiles in this area and everything beneath it.`
- `reparent_area(area: 'Area', new_parent: 'Area | None') -> 'None' - Move an area under a new parent.`
- `societies_for_area(area: 'Area | None') -> 'list[Society]' - Nearest-first ancestor walk: dominant society wins, else realm societies.`
- `societies_for_scene(scene: 'Scene') -> 'list[Society]' - Resolve which societies are relevant at a scene's location (#1464 walk fix).`
- `where_listing(viewer_account: 'object | None' = None) -> 'list[WhereEntry]' - Characters currently in PUBLIC rooms, with their coloured location paths (#1463).`


## world.assets

### AssetTaskIntelDetails
**Foreign Keys:**
  - offer -> npc_services.NPCServiceOffer [OneToOne]
  - clue_pool -> assets.CluePool [FK]

### CluePool
**Pointed to by:**
  - intel_task_offers <- assets.AssetTaskIntelDetails
  - entries <- assets.CluePoolEntry

### CluePoolEntry
**Foreign Keys:**
  - pool -> assets.CluePool [FK]
  - clue -> clues.Clue [FK]

### DistinctionAssetGrant
**Foreign Keys:**
  - distinction -> distinctions.Distinction [FK]
  - npc_role -> npc_services.NPCRole [FK]
**Pointed to by:**
  - granted_assets <- assets.NPCAsset

### NPCAsset
**Foreign Keys:**
  - promoter_persona -> scenes.Persona [FK] (nullable)
  - promoter_org -> societies.Organization [FK] (nullable)
  - asset_persona -> scenes.Persona [FK]
  - source_functionary -> npc_services.Functionary [FK] (nullable)
  - source_distinction_grant -> assets.DistinctionAssetGrant [FK] (nullable)
**Pointed to by:**
  - assignments <- npc_services.NPCAssignment
  - task_fulfillments <- tasking.TaskFulfillment

### Service Functions
- `charm_into_asset(*, charmer_persona: 'Persona', target_persona: 'Persona', role_context: 'str') -> 'NPCAsset' - Extract a charmed NPC as a CHARM ``NPCAsset`` (#2502).`
- `coerce_into_asset(*, coercer_persona: 'Persona', target_persona: 'Persona', role_context: 'str') -> 'NPCAsset' - Extract a blackmailed NPC as a COERCION ``NPCAsset`` (#1680).`
- `draw_clue_from_pool(pool: 'CluePool', roster_entry: 'RosterEntry') -> 'Clue | None' - Draw a weighted random clue from the pool, excluding held clues (#2293).`
- `extract_asset(asset: 'NPCAsset', extractor) -> 'int' - Pull a recruited NPC out of their public job (#2827 phase 3).`
- `introduce_asset(*, introducer_persona: 'Persona', ally_persona: 'Persona', asset: 'NPCAsset') -> 'NPCAsset' - Introduce an owned asset to a co-present ally, creating co-ownership (#2295).`
- `reconcile_distinction_asset_grants(character_distinction: 'CharacterDistinction') -> 'None' - Reconcile a ``CharacterDistinction`` into starting NPCAssets.`
- `transfer_asset_to_org(asset: 'NPCAsset', organization) -> 'NPCAsset' - Convert a personally-held asset row into an org-held one (#2820 phase 2).`
- `transition_asset_status(asset: 'NPCAsset', new_status: 'str', *, reason: 'str' = AssetTransitionReason.CONSEQUENCE) -> 'None' - Transition an NPCAsset's status, enforcing the legal-transition matrix.`
- `transition_assets_for_dead_character(dead_character) -> 'None' - Transition all ACTIVE assets belonging to a dead character to LOST.`


## world.battles

### Battle
**Foreign Keys:**
  - scene -> scenes.Scene [OneToOne]
  - campaign_story -> stories.Story [FK] (nullable)
  - region -> areas.Area [FK] (nullable)
  - weather_override -> weather.WeatherType [FK] (nullable)
  - story_beat -> stories.Beat [FK] (nullable)
**Pointed to by:**
  - sides <- battles.BattleSide
  - places <- battles.BattlePlace
  - units <- battles.BattleUnit
  - rounds <- battles.BattleRound
  - participants <- battles.BattleParticipant
  - companion_deployments <- companions.CompanionDeployment
  - companion_orders <- companions.CompanionOrder
  - ship_deployments <- ships.ShipDeployment

### BattleActionDeclaration
**Foreign Keys:**
  - battle_round -> battles.BattleRound [FK]
  - participant -> battles.BattleParticipant [FK]
  - technique -> magic.Technique [FK]
  - target_unit -> battles.BattleUnit [FK] (nullable)
  - target_ally -> battles.BattleParticipant [FK] (nullable)
  - target_place -> battles.BattlePlace [FK] (nullable)
  - target_side -> battles.BattleSide [FK] (nullable)
  - target_fortification -> battles.Fortification [FK] (nullable)

### BattleMapBlueprint
**Pointed to by:**
  - places <- battles.BlueprintBattlePlace

### BattleOutcomeMapping
**Foreign Keys:**
  - check_outcome -> traits.CheckOutcome [FK]

### BattleParticipant
**Foreign Keys:**
  - battle -> battles.Battle [FK]
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - side -> battles.BattleSide [FK]
  - place -> battles.BattlePlace [FK] (nullable)
  - transit_target_place -> battles.BattlePlace [FK] (nullable)
**Pointed to by:**
  - declarations <- battles.BattleActionDeclaration
  - support_declarations <- battles.BattleActionDeclaration

### BattlePlace
**Foreign Keys:**
  - battle -> battles.Battle [FK]
  - combat_encounter -> combat.CombatEncounter [FK] (nullable)
  - controlled_by -> battles.BattleSide [FK] (nullable)
  - weather_override -> weather.WeatherType [FK] (nullable)
**Pointed to by:**
  - fortifications <- battles.Fortification
  - units <- battles.BattleUnit
  - units_in_transit <- battles.BattleUnit
  - participants <- battles.BattleParticipant
  - participants_in_transit <- battles.BattleParticipant
  - scoped_declarations <- battles.BattleActionDeclaration
  - vehicle <- battles.BattleVehicle

### BattleRound
**Foreign Keys:**
  - battle -> battles.Battle [FK]
**Pointed to by:**
  - declarations <- battles.BattleActionDeclaration

### BattleSide
**Foreign Keys:**
  - battle -> battles.Battle [FK]
  - covenant -> covenants.Covenant [FK] (nullable)
**Pointed to by:**
  - controlled_places <- battles.BattlePlace
  - fortifications <- battles.Fortification
  - units <- battles.BattleUnit
  - participants <- battles.BattleParticipant
  - scoped_declarations <- battles.BattleActionDeclaration

### BattleUnit
**Foreign Keys:**
  - battle -> battles.Battle [FK]
  - side -> battles.BattleSide [FK]
  - place -> battles.BattlePlace [FK] (nullable)
  - transit_target_place -> battles.BattlePlace [FK] (nullable)
  - military_unit -> military.MilitaryUnit [FK]
**Pointed to by:**
  - declarations <- battles.BattleActionDeclaration
  - vehicle <- battles.BattleVehicle

### BattleUnitTemplate
**Foreign Keys:**
  - properties -> mechanics.Property [M2M]
  - capabilities -> conditions.CapabilityType [M2M]
**Pointed to by:**
  - capability_values <- battles.BattleUnitTemplateCapability

### BattleUnitTemplateCapability
**Foreign Keys:**
  - template -> battles.BattleUnitTemplate [FK]
  - capability -> conditions.CapabilityType [FK]

### BattleVehicle
**Foreign Keys:**
  - unit -> battles.BattleUnit [OneToOne]
  - place -> battles.BattlePlace [OneToOne]
**Pointed to by:**
  - companion_deployment <- companions.CompanionDeployment
  - ship_deployment <- ships.ShipDeployment

### BlueprintBattlePlace
**Foreign Keys:**
  - blueprint -> battles.BattleMapBlueprint [FK]
**Pointed to by:**
  - fortifications <- battles.BlueprintFortification

### BlueprintFortification
**Foreign Keys:**
  - blueprint_place -> battles.BlueprintBattlePlace [FK]

### CityDefenseDetails
**Foreign Keys:**
  - project -> projects.Project [OneToOne]
  - area -> areas.Area [FK]
  - outcome_tier -> traits.CheckOutcome [FK] (nullable)
**Pointed to by:**
  - tier_thresholds <- battles.CityDefenseTierThreshold

### CityDefenseIntegrityBonus
**Foreign Keys:**
  - outcome_tier -> traits.CheckOutcome [OneToOne]

### CityDefenseTierThreshold
**Foreign Keys:**
  - details -> battles.CityDefenseDetails [FK]
  - outcome_tier -> traits.CheckOutcome [FK]

### CovenantMilitaryReadiness
**Foreign Keys:**
  - covenant -> covenants.Covenant [OneToOne]

### Fortification
**Foreign Keys:**
  - place -> battles.BattlePlace [FK]
  - defending_side -> battles.BattleSide [FK]
  - building -> buildings.Building [FK] (nullable)
**Pointed to by:**
  - declarations <- battles.BattleActionDeclaration

### ReadinessThreshold

### TechniquePropertyAffinity
**Foreign Keys:**
  - technique -> magic.Technique [FK]
  - property -> mechanics.Property [FK]

### TerrainPropertyEffect
**Foreign Keys:**
  - property -> mechanics.Property [FK]

### WarFundingDetails
**Foreign Keys:**
  - project -> projects.Project [OneToOne]
  - covenant -> covenants.Covenant [FK]
  - outcome_tier -> traits.CheckOutcome [FK] (nullable)
**Pointed to by:**
  - tier_thresholds <- battles.WarFundingTierThreshold

### WarFundingTierBonus
**Foreign Keys:**
  - outcome_tier -> traits.CheckOutcome [OneToOne]

### WarFundingTierThreshold
**Foreign Keys:**
  - details -> battles.WarFundingDetails [FK]
  - outcome_tier -> traits.CheckOutcome [FK]

### WeatherTypeCapabilityChallenge
**Foreign Keys:**
  - weather_type -> weather.WeatherType [FK]
  - capability -> conditions.CapabilityType [FK]

### WeatherTypePropertyEffect
**Foreign Keys:**
  - weather_type -> weather.WeatherType [FK]
  - property -> mechanics.Property [FK]

### Service Functions
- `activate_stakes_for_battle(battle: 'Battle') -> 'None' - Lock any staked beats' contracts for this battle's enlisted party.`
- `add_place(*, battle: 'Battle', name: 'str', terrain_type: 'str' = TerrainType.OPEN, movement_cost: 'int' = 1, x: 'Decimal' = Decimal('0'), y: 'Decimal' = Decimal('0'), footprint_radius: 'Decimal' = Decimal('1')) -> 'BattlePlace' - Add a named front/zone to a battle.`
- `add_side(*, battle: 'Battle', role: 'str', victory_threshold: 'int' = 100, covenant: 'Covenant | None' = None) -> 'BattleSide' - Add a side (attacker or defender) to a battle.`
- `add_unit(*, battle: 'Battle', side: 'BattleSide', name: 'str', descriptor: 'str' = '', quality: 'str' = UnitQuality.TRAINED, commander: 'CharacterSheet | None' = None, summoned_by: 'CharacterSheet | None' = None, strength: 'int' = 100, morale: 'int' = 70, place: 'BattlePlace | None' = None, properties: 'Iterable[Property]' = (), capability_values: 'Iterable[tuple[CapabilityType, int]]' = (), individual_count: 'int | None' = None) -> 'BattleUnit' - Add an abstract typed unit to a battle side.`
- `assign_unit_commander(*, unit: 'BattleUnit', commander: 'CharacterSheet | None') -> 'BattleUnit' - Assign (or clear, with ``commander=None``) a unit's commander (#1711).`
- `begin_battle_round(*, battle: 'Battle') -> 'BattleRound' - Close any open round and open a new DECLARING round.`
- `check_victory(*, battle: 'Battle') -> 'BattleOutcome | None' - Check whether any side has reached its victory threshold.`
- `conclude_battle(*, battle: 'Battle', outcome: 'str') -> 'Battle' - Set the battle's outcome, end the backing scene, and resolve the one`
- `create_battle(*, name: 'str', campaign_story: 'Story | None' = None, round_limit: 'int' = 10, risk_level: 'str' = RiskLevel.LOW) -> 'Battle' - Create a new Battle (and its backing Scene).`
- `create_battle_vehicle(*, battle: 'Battle', side: 'BattleSide', place_name: 'str', vehicle_kind: 'str' = VehicleKind.SHIP, is_structural: 'bool' = True) -> 'BattleVehicle' - Create a vessel/mount: a paired BattleUnit + BattlePlace, plus a hull`
- `create_fortification(*, place: 'BattlePlace', defending_side: 'BattleSide', kind: 'str' = FortificationKind.WALL, building: 'Building | None' = None, max_integrity: 'int | None' = None) -> 'Fortification' - Create a Fortification at *place*, snapshotting its integrity ceiling (#1713).`
- `declare_battle_action(*, participant: 'BattleParticipant', action_kind: 'str', technique: 'Technique', target_unit: 'BattleUnit | None' = None, target_ally: 'BattleParticipant | None' = None, scope: 'str' = BattleActionScope.UNIT, target_place: 'BattlePlace | None' = None, target_side: 'BattleSide | None' = None, target_fortification: 'Fortification | None' = None, reposition_dx: 'Decimal | None' = None, reposition_dy: 'Decimal | None' = None) -> 'BattleActionDeclaration' - Record or update the participant's action declaration for the current round.`
- `eject_vehicle_occupants(*, vehicle: 'BattleVehicle') -> 'None' - Eject every unit/participant embedded on *vehicle*'s place, applying the`
- `enlist_participant(*, battle: 'Battle', character_sheet: 'CharacterSheet', side: 'BattleSide', place: 'BattlePlace | None' = None) -> 'BattleParticipant' - Enlist a player character in a battle on one side.`
- `maybe_conclude_on_timer(*, battle: 'Battle') -> 'BattleOutcome | None' - Conclude the battle when the round limit is exhausted.`
- `maybe_pause_battle_for_disconnect(character_sheet: 'CharacterSheet') -> 'None' - Pause the character's live Battle on disconnect, unless it's large-scale`
- `notify_battle_state_changed(battle: 'Battle') -> 'None' - Slim BATTLE_STATE ping -> connected participants; clients refetch the REST aggregate.`
- `open_champion_duel(*, battle_place: 'BattlePlace', challenger_participant: 'BattleParticipant', opponent_kwargs: 'dict', tier: 'str' = OpponentTier.BOSS) -> 'CombatEncounter' - Bind *battle_place* to a new lethal PC-vs-boss duel (#1710).`
- `open_place_encounter(*, battle_place: 'BattlePlace') -> 'CombatEncounter' - Bind *battle_place* to a new general party-scale combat encounter (#2008).`
- `open_siege_engine_encounter(*, battle_place: 'BattlePlace', participant: 'BattleParticipant', opponent_kwargs: 'dict', tier: 'str' = OpponentTier.ELITE) -> 'CombatEncounter' - Bind *battle_place* to a discrete siege-engine skirmish (#1713).`
- `places_overlap(place_a: 'BattlePlace', place_b: 'BattlePlace') -> 'bool' - Whether two BattlePlaces' footprints intersect on the battle map (#1714).`
- `resolve_battle_beats(battle: 'Battle') -> 'None' - Resolve the one beat linked to a concluded battle (#3559).`
- `run_battle_conclusion_hooks(battle: 'Battle') -> 'None' - Invoke every registered conclusion hook with ``battle``.`
- `set_battle_side_posture(*, side: 'BattleSide', posture: 'str') -> 'BattleSide' - Set a battle side's tactical posture (#1711).`


## world.beta_reset

### ReleaseLatch
**Foreign Keys:**
  - released_by -> evennia.AccountDB [FK]

### Service Functions
- `check_backup_verified(backup_verified_at: 'datetime | None', *, now: 'datetime | None' = None) -> 'None' - Guard 4: the operator asserts a backup was verified recently.`
- `check_beta_reset_enabled() -> 'None' - Guard 1: the hardcoded constant. Raises ``BetaResetDisabledError`` if flipped off.`
- `check_confirmation_phrase(typed: 'str | None') -> 'None' - Guard 3: the typed confirmation phrase must match exactly.`
- `check_release_latch() -> 'None' - Guard 2: the one-way DB latch. Raises ``ReleaseLatchedError`` if any row exists.`
- `mark_released(*, released_by: 'AccountDB', note: 'str' = '') -> 'ReleaseLatch' - Write the one-way ``ReleaseLatch`` row. Refuses if one already exists.`
- `preview_pristine_world_wipe() -> 'WipeReport' - Dry-run: count what ``wipe_pristine_world(execute=True)`` would delete.`
- `refresh_legend_views() -> None - Refresh all legend materialized views concurrently.`
- `wipe_pristine_world(*, execute: 'bool' = False, confirm: 'str | None' = None, backup_verified_at: 'datetime | None' = None) -> 'WipeReport' - Dry-run (default) or execute the guarded beta-reset wipe.`


## world.boards

### Board
**Foreign Keys:**
  - room_profile -> evennia_extensions.RoomProfile [FK] (nullable)
  - organization -> societies.Organization [FK] (nullable)
**Pointed to by:**
  - posts <- boards.BoardPost

### BoardPost
**Foreign Keys:**
  - board -> boards.Board [FK]
  - author_persona -> scenes.Persona [FK]
  - removed_by_persona -> scenes.Persona [FK] (nullable)

### Service Functions
- `can_moderate_board(persona: 'Persona', board: 'Board', *, is_staff: 'bool' = False) -> 'bool' - Whether ``persona`` may remove ANY post on ``board`` (not just their own).`
- `can_post_to_board(persona: 'Persona', board: 'Board', *, actor_room_profile: 'RoomProfile | None') -> 'bool' - Whether ``persona`` may post a new notice to ``board`` right now.`
- `create_board_post(*, board: 'Board', author_persona: 'Persona', title: 'str', body: 'str', actor_room_profile: 'RoomProfile | None' = None) -> 'BoardPost' - Pin a new notice to ``board`` as ``author_persona`` (#3286).`
- `edit_board_post(*, post: 'BoardPost', editor_persona: 'Persona', title: 'str', body: 'str') -> 'BoardPost' - Edit a notice's title/body — author-only, regardless of board kind (#3286).`
- `exclude_blocked_and_muted_board_authors(queryset: 'QuerySet[BoardPost]', *, viewer_account) -> 'QuerySet[BoardPost]' - Exclude blocked/muted authors' posts from a board read (mirrors journals #2996).`
- `get_or_create_location_board(room_profile: 'RoomProfile') -> 'Board' - Get or create the LOCATION board anchored to this room (#3286).`
- `get_or_create_org_board(organization: 'Organization') -> 'Board' - Get or create the ORG board anchored to this organization (#3286).`
- `remove_board_post(*, post: 'BoardPost', remover_persona: 'Persona', actor_room_profile: 'RoomProfile | None' = None, is_staff: 'bool' = False) -> 'BoardPost' - Soft-delete a notice: stamp ``removed_by_persona``/``removed_at`` (#3286).`
- `visible_posts_for_board(board: 'Board') -> 'QuerySet[BoardPost]' - Active posts on ``board``, newest-first, capped to ``max_active_posts``.`


## world.boundaries

### ContentTheme
**Pointed to by:**
  - player_boundaries <- boundaries.PlayerBoundary
  - stake_templates <- stories.StakeTemplate

### PlayerBoundary
**Foreign Keys:**
  - owner -> evennia_extensions.PlayerData [FK]
  - theme -> boundaries.ContentTheme [FK] (nullable)
  - visible_to_tenures -> roster.RosterTenure [M2M]
  - visible_to_groups -> consent.ConsentGroup [M2M]
  - excluded_tenures -> roster.RosterTenure [M2M]

### TreasuredSubject
**Foreign Keys:**
  - owner -> roster.RosterTenure [FK]
  - subject_sheet -> character_sheets.CharacterSheet [FK] (nullable)
  - subject_item -> items.ItemInstance [FK] (nullable)
  - subject_society -> societies.Society [FK] (nullable)
  - subject_organization -> societies.Organization [FK] (nullable)
  - visible_to_tenures -> roster.RosterTenure [M2M]
  - visible_to_groups -> consent.ConsentGroup [M2M]
  - excluded_tenures -> roster.RosterTenure [M2M]
**Pointed to by:**
  - signoffs <- stories.TreasuredSignoff

### Service Functions
- `scene_lines_and_veils(scene: 'Scene', viewer_tenure: 'RosterTenure') -> 'SceneLinesAndVeils' - A scene's shared "lines & veils" aggregate for ``viewer_tenure``.`


## world.buildings

### ArchitecturalStyle
**Foreign Keys:**
  - codex_subject -> codex.CodexSubject [FK] (nullable)
**Pointed to by:**
  - buildings <- buildings.Building
  - affinities <- buildings.StyleAffinity

### Building
**Foreign Keys:**
  - area -> areas.Area [OneToOne]
  - owner_persona -> scenes.Persona [FK] (nullable)
  - kind -> buildings.BuildingKind [FK]
  - architectural_style -> buildings.ArchitecturalStyle [FK] (nullable)
  - entry_room -> evennia_extensions.RoomProfile [FK] (nullable)
  - constructed_by_persona -> scenes.Persona [FK] (nullable)
  - source_project -> projects.Project [OneToOne] (nullable)
  - granted_via_profile -> buildings.PropertyGrantProfile [FK] (nullable)
**Pointed to by:**
  - battle_fortifications <- battles.Fortification
  - listing <- buildings.BuildingListing
  - materials_used <- buildings.BuildingMaterial
  - extension_details <- buildings.BuildingExtensionDetails
  - fortification_upgrade_details <- buildings.FortificationUpgradeDetails
  - renovation_details <- buildings.BuildingRenovationDetails
  - activation_details <- buildings.BuildingActivationDetails
  - preparation_details <- buildings.BuildingPreparationDetails
  - upgrade_details <- buildings.BuildingUpgradeDetails
  - design_details <- buildings.InteriorDesignDetails
  - polish_by_category <- buildings.BuildingPolish
  - project_instances <- buildings.BuildingProjectInstance
  - mothballed_room_states <- buildings.MothballedRoomState
  - bequests <- estates.Bequest
  - ship_details <- ships.ShipDetails

### BuildingActivationDetails
**Foreign Keys:**
  - project -> projects.Project [OneToOne]
  - building -> buildings.Building [FK]

### BuildingConstructionDetails
**Foreign Keys:**
  - project -> projects.Project [OneToOne]
  - permit_details -> buildings.BuildingPermitDetails [FK]
  - ward -> areas.Area [FK]
  - constructed_by_persona -> scenes.Persona [FK] (nullable)

### BuildingExtensionDetails
**Foreign Keys:**
  - project -> projects.Project [OneToOne]
  - building -> buildings.Building [FK]

### BuildingKind
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
**Pointed to by:**
  - allowed_in_wards <- areas.Area
  - property_grant_profiles <- buildings.PropertyGrantProfile
  - buildings <- buildings.Building
  - permits <- buildings.BuildingPermitDetails
  - renovation_targets <- buildings.BuildingRenovationDetails
  - installable_features <- room_features.RoomFeatureKind
  - staffing_profile <- npc_services.StaffingProfile
  - offered_by <- npc_services.PermitOfferDetails

### BuildingListing
**Foreign Keys:**
  - building -> buildings.Building [OneToOne]
  - organization -> societies.Organization [FK] (nullable)
  - sold_to_persona -> scenes.Persona [FK] (nullable)

### BuildingMaterial
**Foreign Keys:**
  - building -> buildings.Building [FK]
  - item_template -> items.ItemTemplate [FK]
  - quality_tier -> items.QualityTier [FK] (nullable)
  - contributed_by_persona -> scenes.Persona [FK] (nullable)

### BuildingPermitDetails
**Foreign Keys:**
  - item_instance -> items.ItemInstance [OneToOne]
  - building_kind -> buildings.BuildingKind [FK]
  - issued_by_role -> npc_services.NPCRole [FK] (nullable)
  - consumed_by_persona -> scenes.Persona [FK] (nullable)
  - approved_wards -> areas.Area [M2M]
**Pointed to by:**
  - construction_projects <- buildings.BuildingConstructionDetails

### BuildingPolish
**Foreign Keys:**
  - building -> buildings.Building [FK]
  - category -> buildings.PolishCategory [FK]

### BuildingPreparationDetails
**Foreign Keys:**
  - project -> projects.Project [OneToOne]
  - building -> buildings.Building [FK]

### BuildingProjectInstance
**Foreign Keys:**
  - building -> buildings.Building [FK]
  - template -> buildings.ProjectTemplate [FK]
  - source_project -> projects.Project [OneToOne] (nullable)
**Pointed to by:**
  - polish_by_category <- buildings.BuildingProjectInstancePolish

### BuildingProjectInstancePolish
**Foreign Keys:**
  - instance -> buildings.BuildingProjectInstance [FK]
  - category -> buildings.PolishCategory [FK]

### BuildingRenovationDetails
**Foreign Keys:**
  - project -> projects.Project [OneToOne]
  - building -> buildings.Building [FK]
  - target_kind -> buildings.BuildingKind [FK]

### BuildingSizeTier

### BuildingUpgradeDetails
**Foreign Keys:**
  - project -> projects.Project [OneToOne]
  - building -> buildings.Building [FK]

### DecorationAffinity
**Foreign Keys:**
  - kind -> buildings.DecorationKind [FK]

### DecorationKind
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - crafted_item_template -> items.ItemTemplate [FK] (nullable)
**Pointed to by:**
  - affinities <- buildings.DecorationAffinity
  - placements <- buildings.RoomDecoration

### FortificationUpgradeDetails
**Foreign Keys:**
  - project -> projects.Project [OneToOne]
  - building -> buildings.Building [FK]

### InteriorDesignDetails
**Foreign Keys:**
  - project -> projects.Project [OneToOne]
  - template -> buildings.ProjectTemplate [FK]
  - building -> buildings.Building [FK]
  - room -> evennia_extensions.RoomProfile [FK] (nullable)

### MaterialLoreEffect
**Foreign Keys:**
  - template -> items.ItemTemplate [FK]

### MothballedRoomState
**Foreign Keys:**
  - building -> buildings.Building [FK]
  - room_profile -> evennia_extensions.RoomProfile [FK]

### PolishCategory
**Pointed to by:**
  - tier_thresholds <- buildings.TierThreshold
  - building_polish_rows <- buildings.BuildingPolish
  - room_polish_rows <- buildings.RoomPolish
  - polish_increment_rows <- buildings.ProjectTemplatePolishIncrement
  - instance_polish_rows <- buildings.BuildingProjectInstancePolish
  - item_templates <- items.ItemTemplate

### ProjectTemplate
**Foreign Keys:**
  - tier_prerequisites -> buildings.TierThreshold [M2M]
**Pointed to by:**
  - design_details <- buildings.InteriorDesignDetails
  - polish_increment_rows <- buildings.ProjectTemplatePolishIncrement
  - instances <- buildings.BuildingProjectInstance

### ProjectTemplatePolishIncrement
**Foreign Keys:**
  - template -> buildings.ProjectTemplate [FK]
  - category -> buildings.PolishCategory [FK]

### PropertyGrantProfile
**Foreign Keys:**
  - building_kind -> buildings.BuildingKind [FK]
  - ward_area -> areas.Area [FK] (nullable)
**Pointed to by:**
  - granted_buildings <- buildings.Building
  - beginnings <- character_creation.Beginnings

### RoomDecoration
**Foreign Keys:**
  - room_profile -> evennia_extensions.RoomProfile [FK]
  - kind -> buildings.DecorationKind [FK]
  - source_item_instance -> items.ItemInstance [OneToOne] (nullable)

### RoomPolish
**Foreign Keys:**
  - room -> evennia_extensions.RoomProfile [FK]
  - category -> buildings.PolishCategory [FK]

### StyleAffinity
**Foreign Keys:**
  - style -> buildings.ArchitecturalStyle [FK]

### TierThreshold
**Foreign Keys:**
  - category -> buildings.PolishCategory [FK]
**Pointed to by:**
  - gated_project_templates <- buildings.ProjectTemplate

### Service Functions
- `activate_permit(permit_details: 'BuildingPermitDetails', site_room, acting_persona: 'Persona', target_size: 'int', target_grandeur: 'int') -> 'Project' - Consume a permit + spawn a BUILDING_CONSTRUCTION project.`
- `can_build_style(persona: 'Persona', style: 'ArchitecturalStyle') -> 'bool' - Whether this persona may build in this style (#1469).`
- `complete_building_construction(project: 'Project', outcome_tier: 'object | None' = None) -> 'Building' - Spawn a Building from a completed BUILDING_CONSTRUCTION project.`
- `contribution_value_for_construction(contribution: 'Contribution') -> 'int' - How much a single contribution is worth toward a BUILDING_CONSTRUCTION project.`
- `crafted_decoration_amenity(kind: 'DecorationKind', quality_tier: 'QualityTier | None') -> 'int' - The amenity a crafted-furniture placement contributes (#2991 amendment, ADR-0192).`
- `create_entry_room(building: 'Building', name: 'str') -> 'RoomProfile' - Create one Evennia Room ObjectDB + ``RoomProfile`` for *building*, named *name*.`
- `issue_permit(offer: 'NPCServiceOffer', persona: 'Persona') -> 'EffectResult' - Real PERMIT effect handler — creates the BuildingPermit ItemInstance + details.`
- `place_decoration(room_profile, kind: 'DecorationKind', *, buyer_persona: 'Persona | None' = None, item_instance: 'ItemInstance | None' = None) -> 'RoomDecoration' - Place a decoration in a room and materialize its comfort modifiers (#1514, priced #2991).`
- `purchase_building(*, persona: 'Persona', listing: 'BuildingListing') -> 'BuildingListing' - Buy a listed ``Building`` with coin (#2991): deed transfer + treasury sink.`
- `remove_decoration(decoration: 'RoomDecoration') -> 'None' - Remove a placed decoration and delete its comfort modifiers (#1514).`
- `set_building_style(building: 'Building', style: 'ArchitecturalStyle | None') -> 'Building' - Assign (or clear) a building's architectural style and re-sync its climate modifiers.`
- `sync_building_style_modifiers(building: 'Building') -> 'None' - Re-materialize a building's architectural-style affinities as cascade modifiers (#1514).`
- `validate_permit_site(permit_details: 'BuildingPermitDetails', site_room, acting_persona: 'Persona', target_size: 'int') -> 'ValidationResult' - Validate a permit can be used at this site for this size.`


## world.captivity

### Captivity
**Foreign Keys:**
  - captive -> character_sheets.CharacterSheet [FK]
  - cell -> instances.InstancedRoom [FK] (nullable)
  - holding_room -> evennia_extensions.RoomProfile [FK] (nullable)
  - return_location -> evennia.ObjectDB [FK] (nullable)
  - captor_organization -> societies.Organization [FK] (nullable)
  - ransom_project -> projects.Project [FK] (nullable)
  - rescue_template -> missions.MissionTemplate [FK] (nullable)
**Pointed to by:**
  - rescue_clues <- clues.Clue
  - justice_cases <- justice.JusticeCase

### CaptivityConfig
**Foreign Keys:**
  - captive_template -> missions.MissionTemplate [FK] (nullable)
  - rescue_template -> missions.MissionTemplate [FK] (nullable)

### Service Functions
- `capture_character(*, captive: 'CharacterSheet', captor_organization: 'Organization | None' = None, return_location: 'ObjectDB | None' = None, offscreen_loss_allowed: 'bool' = False, cell: 'InstancedRoom | None' = None, group_key: 'str | None' = None, cell_name: 'str | None' = None, cell_description: 'str | None' = None, holding_room: 'RoomProfile | None' = None) -> 'Captivity' - Take one character into a cell and record the captivity.`
- `capture_party(*, captives: 'Iterable[CharacterSheet]', captor_organization: 'Organization | None' = None, return_location: 'ObjectDB | None' = None, offscreen_loss_allowed: 'bool' = False, cell_name: 'str | None' = None, cell_description: 'str | None' = None) -> 'list[Captivity]' - Capture several characters into one shared cell (the default).`
- `complete_instanced_room(room: evennia.objects.models.ObjectDB) -> None - Mark room completed, relocate occupants, delete if no history.`
- `escape_captivity(captive: 'CharacterSheet') -> 'bool' - Free a captive by their own hand (#931 Phase 4) — the escape loop's verb.`
- `rescue_captive(captive: 'CharacterSheet') -> 'bool' - Free a captive via rescue (#931 Phase 4) — a rescue run's terminal verb.`
- `resolve_captivity(captivity: 'Captivity', *, status: 'str') -> 'None' - End a captivity and free the captive.`
- `resolve_capture_setup(*, captive_template: 'MissionTemplate | None' = None, rescue_template: 'MissionTemplate | None' = None, cell_name: 'str' = '', cell_description: 'str' = '', clue_name: 'str' = '', clue_description: 'str' = '', clue_detect_difficulty: 'int | None' = None) -> 'CaptureSetup' - Resolve one capture's loops + cell flavor: per-capture override, else default.`
- `spawn_instanced_room(name: str, description: str, owner: world.character_sheets.models.CharacterSheet | None, return_location: evennia.objects.models.ObjectDB | None, source_key: str = '', gm_owner: world.gm.models.GMProfile | None = None) -> evennia.objects.models.ObjectDB - Create a temporary instanced room, its RoomProfile, and lifecycle record.`


## world.ceremonies

### Ceremony
**Foreign Keys:**
  - ceremony_type -> ceremonies.CeremonyType [FK]
  - officiant -> scenes.Persona [FK]
  - being -> worship.WorshippedBeing [FK]
  - presented_being -> worship.WorshippedBeing [FK]
  - location -> evennia_extensions.RoomProfile [FK]
  - scene -> scenes.Scene [FK] (nullable)
  - event -> events.Event [FK] (nullable)
  - title -> societies.Title [FK] (nullable)
**Pointed to by:**
  - honorees <- ceremonies.CeremonyHonoree
  - offerings <- ceremonies.CeremonyOffering
  - speeches <- ceremonies.CeremonySpeech
  - coronation <- ceremonies.Coronation

### CeremonyConfig

### CeremonyHonoree
**Foreign Keys:**
  - ceremony -> ceremonies.Ceremony [FK]
  - honoree_sheet -> character_sheets.CharacterSheet [FK]
**Pointed to by:**
  - speeches <- ceremonies.CeremonySpeech
  - seance_offer <- ceremonies.SeanceManifestationOffer
  - conversion_offer <- ceremonies.WorshipConversionOffer
  - wedding_consent_offer <- ceremonies.WeddingConsentOffer

### CeremonyOffering
**Foreign Keys:**
  - ceremony -> ceremonies.Ceremony [FK]
  - worship_grant -> worship.WorshipGrant [FK] (nullable)
  - offered_by -> scenes.Persona [FK]

### CeremonySpeech
**Foreign Keys:**
  - ceremony -> ceremonies.Ceremony [FK]
  - speaker -> scenes.Persona [FK]
  - target_honoree -> ceremonies.CeremonyHonoree [FK] (nullable)

### CeremonyType
**Pointed to by:**
  - ceremonies <- ceremonies.Ceremony

### Coronation
**Foreign Keys:**
  - ceremony -> ceremonies.Ceremony [OneToOne]
  - honoree_sheet -> character_sheets.CharacterSheet [FK]
  - title -> societies.Title [FK]

### SeanceManifestationOffer
**Foreign Keys:**
  - ceremony_honoree -> ceremonies.CeremonyHonoree [OneToOne]

### WeddingConsentOffer
**Foreign Keys:**
  - ceremony_honoree -> ceremonies.CeremonyHonoree [OneToOne]

### WorshipConversionOffer
**Foreign Keys:**
  - ceremony_honoree -> ceremonies.CeremonyHonoree [OneToOne]

### Service Functions
- `abandon_ceremony(*, ceremony: world.ceremonies.models.Ceremony) -> world.ceremonies.models.Ceremony - Decision 12: close the rite awarding nothing; frees the location + ghost window.`
- `execute_will(character_sheet: 'CharacterSheet') -> None - Execute the deceased's estate — the funeral door of #1985.`
- `finish_ceremony(*, ceremony: world.ceremonies.models.Ceremony, sincere: bool | None = None) -> world.ceremonies.models.Ceremony - Close the rite: quality roll, renown tallies, worship, funeral effects.`
- `get_ceremony_config() -> world.ceremonies.models.CeremonyConfig - Get-or-create the first CeremonyConfig row (singleton-by-convention).`
- `open_ceremony(*, officiant_persona: 'Persona', type_key: str, honoree_sheets: 'list[CharacterSheet]', location_profile, being: 'WorshippedBeing | None' = None, scene=None, event=None, title=None, is_staff_fiat: bool = False) -> world.ceremonies.models.Ceremony - Open a ceremony at a location, recognizing zero or more honorees.`
- `open_funeral_for(character_sheet: 'CharacterSheet') -> world.ceremonies.models.Ceremony | None - The OPEN funeral honoring this character, if any (the ghost container).`
- `pending_conversion_offers_for_account(account: object) -> 'QuerySet[WorshipConversionOffer]' - PENDING conversion offers addressed to any character this account has ever held.`
- `pending_seance_offers_for_account(account: object) -> 'QuerySet[SeanceManifestationOffer]' - PENDING seance offers addressed to any character this account has ever held (#2393).`
- `pending_wedding_consent_offers_for_account(account: object) -> 'QuerySet[WeddingConsentOffer]' - PENDING wedding consent offers addressed to any character this account holds (#2358).`
- `record_offering(*, ceremony: world.ceremonies.models.Ceremony, item_instances: 'list[ItemInstance]') -> list[world.ceremonies.models.CeremonyOffering] - Sacrifice items: destroy them, feed the being's pool, log offerings.`
- `record_speech(*, ceremony: world.ceremonies.models.Ceremony, speaker_persona: 'Persona', target_honoree: world.ceremonies.models.CeremonyHonoree | None = None) -> world.ceremonies.models.CeremonySpeech - Recognize a speaker; their Performance/Oratory roll shapes the tally.`
- `respond_to_conversion_offer(offer: 'WorshipConversionOffer', *, account: object, accept: bool, sincere: bool = True) -> 'WorshipConversionOffer' - Accept or decline a pending public-conversion offer (#2361, Ratified amendment #1a).`
- `respond_to_seance_offer(offer: 'SeanceManifestationOffer', *, account: object, accept: bool) -> 'SeanceManifestationOffer' - Accept or decline a pending seance manifestation offer (#2393).`
- `respond_to_wedding_consent_offer(offer: 'WeddingConsentOffer', *, account: object, accept: bool) -> 'WeddingConsentOffer' - Accept or decline a pending wedding consent offer (#2358).`
- `revoke_seance_manifestations(ceremony: world.ceremonies.models.Ceremony) -> None - Force-unpuppet any manifested RETIRED honoree when a Seance closes (#2393).`


## world.character_creation

### BeginningTradition
**Foreign Keys:**
  - beginning -> character_creation.Beginnings [FK]
  - tradition -> magic.Tradition [FK]
  - required_distinction -> distinctions.Distinction [FK] (nullable)

### Beginnings
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - art -> evennia_extensions.Media [FK] (nullable)
  - starting_area -> character_creation.StartingArea [FK]
  - heritage -> character_sheets.Heritage [FK] (nullable)
  - starting_room_override -> evennia_extensions.RoomProfile [FK] (nullable)
  - property_grant_profile -> buildings.PropertyGrantProfile [FK] (nullable)
  - prelude_mission -> missions.MissionTemplate [FK] (nullable)
  - allowed_species -> species.Species [M2M]
  - starting_languages -> species.Language [M2M]
  - societies -> societies.Society [M2M]
  - traditions -> magic.Tradition [M2M]
**Pointed to by:**
  - beginning_traditions <- character_creation.BeginningTradition
  - origin_templates <- character_creation.OriginTemplate
  - drafts <- character_creation.CharacterDraft
  - codex_grants <- codex.BeginningsCodexGrant
  - ritual_grants <- magic.BeginningsRitualGrant

### CGExplanation
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)

### CGPointBudget

### CharacterDraft
**Foreign Keys:**
  - account -> evennia.AccountDB [FK]
  - selected_area -> character_creation.StartingArea [FK] (nullable)
  - selected_beginnings -> character_creation.Beginnings [FK] (nullable)
  - selected_species -> species.Species [FK] (nullable)
  - selected_gender -> character_sheets.Gender [FK] (nullable)
  - public_worship -> worship.WorshippedBeing [FK] (nullable)
  - secret_worship -> worship.WorshippedBeing [FK] (nullable)
  - family -> roster.Family [FK] (nullable)
  - claimed_kin_slot -> roster.Kinsperson [FK] (nullable)
  - claimed_kin_pool -> roster.KinSlotPool [FK] (nullable)
  - second_parent_species -> species.Species [FK] (nullable)
  - selected_path -> classes.Path [FK] (nullable)
  - selected_tradition -> magic.Tradition [FK] (nullable)
  - height_band -> forms.HeightBand [FK] (nullable)
  - build -> forms.Build [FK] (nullable)
  - target_table -> gm.GMTable [FK] (nullable)
**Pointed to by:**
  - markings <- character_creation.DraftMarking
  - application <- character_creation.DraftApplication
  - house_claim <- societies.HouseClaim

### CharacterOriginSlot
**Foreign Keys:**
  - sheet -> character_sheets.CharacterSheet [FK]
  - slot -> character_creation.OriginTemplateSlot [FK]

### DraftApplication
**Foreign Keys:**
  - draft -> character_creation.CharacterDraft [OneToOne] (nullable)
  - player_account -> evennia.AccountDB [FK] (nullable)
  - reviewer -> evennia.AccountDB [FK] (nullable)
  - invited_via -> roster.GameInvite [FK] (nullable)
**Pointed to by:**
  - comments <- character_creation.DraftApplicationComment

### DraftApplicationComment
**Foreign Keys:**
  - application -> character_creation.DraftApplication [FK]
  - author -> evennia.AccountDB [FK] (nullable)

### DraftMarking
**Foreign Keys:**
  - draft -> character_creation.CharacterDraft [FK]

### OriginTemplate
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - beginning -> character_creation.Beginnings [FK]
**Pointed to by:**
  - slots <- character_creation.OriginTemplateSlot

### OriginTemplateSlot
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - template -> character_creation.OriginTemplate [FK]
**Pointed to by:**
  - character_rows <- character_creation.CharacterOriginSlot

### StartingArea
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - realm -> realms.Realm [FK] (nullable)
  - crest_art -> evennia_extensions.Media [FK] (nullable)
  - default_starting_room -> evennia_extensions.RoomProfile [FK] (nullable)
**Pointed to by:**
  - beginnings <- character_creation.Beginnings
  - drafts <- character_creation.CharacterDraft

### Service Functions
- `add_application_comment(application: 'DraftApplication', *, author: 'AbstractBaseUser | AnonymousUser', text: 'str') -> 'DraftApplicationComment' - Add a message comment to an application.`
- `approve_application(application: 'DraftApplication', *, reviewer: 'AbstractBaseUser | AnonymousUser', comment: 'str' = '') -> 'None' - Approve an application and finalize the character.`
- `assemble_origin_prose(sheet: 'CharacterSheet') -> 'str' - Compose the frame narrative + slot answers into prose.`
- `calculate_weight(height_inches: 'int', build: 'Build') -> 'int' - Calculate weight in pounds from height and build.`
- `can_create_character(account: 'AbstractBaseUser | AnonymousUser') -> 'tuple[bool, str]' - Check if an account can create a new character.`
- `claim_application(application: 'DraftApplication', *, reviewer: 'AbstractBaseUser | AnonymousUser') -> 'None' - Claim a submitted application for staff review.`
- `clear_origin_slot(sheet: 'CharacterSheet', slot: 'OriginTemplateSlot') -> 'None' - Delete a slot answer and recompute state.`
- `create_character_with_sheet(*, character_key: 'str', primary_persona_name: 'str', typeclass: 'str' = 'typeclasses.characters.Character', home: 'ObjectDB | None' = None, **sheet_kwargs: 'Any') -> 'tuple[ObjectDB, CharacterSheet, Persona]' - Atomically create a Character + CharacterSheet + PRIMARY Persona.`
- `deny_application(application: 'DraftApplication', *, reviewer: 'AbstractBaseUser | AnonymousUser', comment: 'str') -> 'None' - Deny an application.`
- `finalize_character(draft: 'CharacterDraft', *, add_to_roster: 'bool' = False, created_by_account: 'AccountDB | None' = None) -> 'ObjectDB' - Create a Character from a completed CharacterDraft.`
- `finalize_gm_character(draft: 'CharacterDraft', *, claim_as_npc: 'bool' = False) -> 'tuple[RosterEntry, Story]' - Finalize a GM-initiated draft into a roster character + story.`
- `finalize_magic_data(draft: 'CharacterDraft', sheet: 'CharacterSheet') -> 'None' - Create magic models from the CG-chosen catalog Gift/Techniques during finalization.`
- `get_accessible_starting_areas(account: 'AbstractBaseUser | AnonymousUser') -> 'QuerySet' - Get all starting areas accessible to an account.`
- `refresh_origin_story_state(sheet: 'CharacterSheet') -> 'OriginStoryState' - Recompute and persist ``origin_story_state`` from slot rows + prose.`
- `request_revisions(application: 'DraftApplication', *, reviewer: 'AbstractBaseUser | AnonymousUser', comment: 'str') -> 'None' - Request revisions on an application.`
- `require_draft_complete(draft: 'CharacterDraft') -> 'None' - Raise DraftIncompleteError unless every non-Review stage is complete.`
- `resubmit_draft(application: 'DraftApplication', *, comment: 'str' = '') -> 'None' - Resubmit a draft application after revisions.`
- `set_origin_slot(sheet: 'CharacterSheet', slot: 'OriginTemplateSlot', value: 'str') -> 'None' - Upsert a character's slot answer, then refresh state.`
- `submit_draft_for_review(draft: 'CharacterDraft', *, submission_notes: 'str' = '') -> 'DraftApplication' - Submit a character draft for staff review.`
- `unsubmit_draft(application: 'DraftApplication') -> 'None' - Un-submit a draft application, returning it to editable state.`
- `withdraw_draft(application: 'DraftApplication') -> 'None' - Withdraw a draft application.`


## world.character_sheets

### CharacterSheet
**Foreign Keys:**
  - character -> evennia.ObjectDB [OneToOne]
  - build -> forms.Build [FK] (nullable)
  - gender -> character_sheets.Gender [FK] (nullable)
  - pronouns -> character_sheets.Pronouns [FK] (nullable)
  - species -> species.Species [FK] (nullable)
  - current_language -> species.Language [FK] (nullable)
  - current_mood -> character_sheets.MoodOption [FK] (nullable)
  - current_residence -> evennia_extensions.RoomProfile [FK] (nullable)
  - true_profile -> character_sheets.Profile [OneToOne] (nullable)
  - active_persona -> scenes.Persona [FK] (nullable)
  - created_by -> evennia.AccountDB [FK] (nullable)
  - durance_cohort -> progression.DuranceCohort [FK] (nullable)
**Pointed to by:**
  - applications <- roster.RosterApplication
  - kinsperson <- roster.Kinsperson
  - deferred_kin <- roster.Kinsperson
  - roster_entry <- roster.RosterEntry
  - stat_trackers <- achievements.StatTracker
  - achievements <- achievements.CharacterAchievement
  - action_points <- action_points.ActionPointPool
  - conjured_obstacles <- areas.PositionEdge
  - ramparts <- areas.Rampart
  - consequence_outcomes <- checks.ConsequenceOutcome
  - owned_check_types <- checks.CheckType
  - check_call_targets <- checks.CheckCallTarget
  - detected_concealments <- conditions.ConditionInstance
  - treatment_attempts_as_helper <- conditions.TreatmentAttempt
  - treatment_attempts_as_target <- conditions.TreatmentAttempt
  - modifiers <- mechanics.CharacterModifier
  - challenge_records <- mechanics.CharacterChallengeRecord
  - engagement <- mechanics.CharacterEngagement
  - battle_participations <- battles.BattleParticipant
  - treasured_by <- boundaries.TreasuredSubject
  - captivities <- captivity.Captivity
  - ceremony_honors <- ceremonies.CeremonyHonoree
  - coronations <- ceremonies.Coronation
  - trait_values <- traits.CharacterTraitValue
  - trait_changes <- traits.CharacterTraitChange
  - character_class_levels <- classes.CharacterClassLevel
  - origin_slots <- character_creation.CharacterOriginSlot
  - audere_offers <- magic.PendingAudereOffer
  - legend_contributions <- societies.LegendContribution
  - org_obligations <- societies.OrganizationObligation
  - created_gifts <- magic.Gift
  - character_gifts <- magic.CharacterGift
  - character_traditions <- magic.CharacterTradition
  - authored_techniques <- magic.Technique
  - character_techniques <- magic.CharacterTechnique
  - class_level_advancements <- progression.ClassLevelAdvancement
  - officiated_advancements <- progression.ClassLevelAdvancement
  - durance_training_roles <- progression.DuranceTrainingSite
  - character_xp <- progression.CharacterXP
  - character_xp_transactions <- progression.CharacterXPTransaction
  - kudos_transactions <- progression.KudosTransaction
  - maturation_spends <- progression.MaturationSpend
  - path_intent <- progression.PathIntent
  - path_history <- progression.CharacterPathHistory
  - xptransaction_set <- progression.XPTransaction
  - development_points <- progression.DevelopmentPoints
  - development_transactions <- progression.DevelopmentTransaction
  - weekly_skill_usage <- progression.WeeklySkillUsage
  - level_stat_point_spends <- progression.LevelStatPointSpend
  - unlocks <- progression.CharacterUnlock
  - audere_majora_offers <- magic.PendingAudereMajoraOffer
  - audere_majora_crossings <- magic.AudereMajoraCrossing
  - entry_flourish_offers <- magic.PendingEntryFlourishOffer
  - pending_alterations <- magic.PendingAlteration
  - alteration_events <- magic.MagicalAlterationEvent
  - anima <- magic.CharacterAnima
  - anima_ritual_participations <- magic.AnimaRitualPerformance
  - appetite_upkeep_receipts <- magic.AppetiteUpkeepReceipt
  - feedings_taken <- magic.FeedingRecord
  - feedings_suffered <- magic.FeedingRecord
  - aura <- magic.CharacterAura
  - resonances <- magic.CharacterResonance
  - dramatic_moment_tags <- magic.DramaticMomentTag
  - dramatic_moment_suggestions <- magic.DramaticMomentSuggestion
  - poseendorsement_given <- magic.PoseEndorsement
  - poseendorsement_received <- magic.PoseEndorsement
  - sceneentryendorsement_given <- magic.SceneEntryEndorsement
  - sceneentryendorsement_received <- magic.SceneEntryEndorsement
  - presentationendorsement_given <- magic.PresentationEndorsement
  - presentationendorsement_received <- magic.PresentationEndorsement
  - stylepresentationendorsement_given <- magic.StylePresentationEndorsement
  - stylepresentationendorsement_received <- magic.StylePresentationEndorsement
  - entry_flourish_records <- magic.EntryFlourishRecord
  - fall_redemption_records <- magic.FallRedemptionRecord
  - ghost_tutelages <- magic.GhostTutelage
  - gift_unlocks <- magic.CharacterGiftUnlock
  - resonance_grants <- magic.ResonanceGrant
  - motif <- magic.Motif
  - reincarnations <- magic.Reincarnation
  - ritual_anima_contributions <- magic.RitualAnimaContribution
  - ritual_sacrifices_suffered <- magic.RitualAnimaContribution
  - pending_ritual_effects <- magic.PendingRitualEffect
  - founded_sanctums <- magic.SanctumDetails
  - sanctum_pending_payouts <- magic.SanctumPendingPayout
  - led_courts <- covenants.Covenant
  - covenant_role_assignments <- covenants.CharacterCovenantRole
  - covenant_rite_instances <- covenants.CovenantRiteInstance
  - mentor_bonds_as_mentor <- covenants.MentorBond
  - mentor_bonds_as_sidekick <- covenants.MentorBond
  - court_pacts <- covenants.CourtPact
  - ritualsession_set <- magic.RitualSession
  - ritualsessionparticipant_set <- magic.RitualSessionParticipant
  - sineating_offers_sent <- magic.SineatingPendingOffer
  - sineating_offers_received <- magic.SineatingPendingOffer
  - stage_advance_offers_sent <- magic.PendingStageAdvanceOffer
  - stage_advance_offers_received <- magic.PendingStageAdvanceOffer
  - sineatings_as_sinner <- magic.Sineating
  - sineatings_as_sineater <- magic.Sineating
  - rescues_as_sinner <- magic.SoulTetherRescue
  - rescues_as_sineater <- magic.SoulTetherRescue
  - technique_draft <- magic.TechniqueDraft
  - technique_progress <- magic.TechniqueProgress
  - technique_progress_weekly <- magic.TechniqueProgressWeekly
  - threads <- magic.Thread
  - thread_weaving_unlocks <- magic.CharacterThreadWeavingUnlock
  - duels_won <- combat.CombatEncounter
  - summoned_combatants <- combat.CombatOpponent
  - combo_learnings <- combat.ComboLearning
  - combat_participations <- combat.CombatParticipant
  - combat_risk_acknowledgements <- combat.EncounterRiskAcknowledgement
  - duel_challenges_issued <- combat.DuelChallenge
  - duel_challenges_received <- combat.DuelChallenge
  - companions <- companions.Companion
  - ridden_companion <- companions.Companion
  - purse <- currency.CharacterPurse
  - employments <- currency.CharacterEmployment
  - purse_drain_weeks <- currency.PurseDrainWeek
  - distinctions <- distinctions.CharacterDistinction
  - distinction_other_entries <- distinctions.CharacterDistinctionOther
  - sheet_update_requests <- distinctions.SheetUpdateRequest
  - dreamwalk_presence <- dreams.DreamwalkPresence
  - dream_visitors <- dreams.DreamwalkPresence
  - will <- estates.Will
  - estate_settlement <- estates.EstateSettlement
  - fatigue <- fatigue.FatiguePool
  - forms <- forms.CharacterForm
  - form_state <- forms.CharacterFormState
  - alternate_selves <- forms.AlternateSelf
  - active_alternate_self <- forms.ActiveAlternateSelf
  - temporary_form_changes <- forms.TemporaryFormChange
  - known_styles <- forms.CharacterKnownStyle
  - story_room_grants <- gm.StoryRoomGrant
  - summon_offers <- gm.GMSummonOffer
  - goals <- goals.CharacterGoal
  - goal_journals <- goals.GoalJournal
  - goal_revision <- goals.GoalRevision
  - owned_instances <- instances.InstancedRoom
  - owned_items <- items.ItemInstance
  - crafted_items <- items.ItemInstance
  - attuned_touchstones <- items.ItemInstance
  - designed_items <- items.ItemInstance
  - equipped_items <- items.EquippedItem
  - items_given_away <- items.OwnershipEvent
  - items_received <- items.OwnershipEvent
  - recycle_requests <- items.RecycleRequest
  - outfits <- items.Outfit
  - fashion_presentations <- items.FashionPresentation
  - cachet_wallet <- items.CachetWallet
  - showcase_state <- items.ShowcaseState
  - fashion_showings <- items.FashionShowing
  - mantle_clearances <- items.MantleLevelClearance
  - conjured_hazards <- room_features.Trap
  - detected_traps <- room_features.Trap
  - prepared_ground <- room_features.PreparedGround
  - recipe_knowledge <- items.CharacterRecipeKnowledge
  - expulsion_bars <- npc_services.ExpulsionBar
  - material_buckets <- items.MaterialBucket
  - vault_transits <- items.VaultTransit
  - trade_sessions_initiated <- items.TradeSession
  - trade_sessions_received <- items.TradeSession
  - trade_stakes <- items.TradeItemStake
  - reclamation_claims <- items.ReclamationClaim
  - original_reclamation_claims <- items.ReclamationClaim
  - journal_entries <- journals.JournalEntry
  - weekly_journal_xp <- journals.WeeklyJournalXP
  - journal_bequests_received <- journals.JournalBequestGrant
  - journal_bequests_granted <- journals.JournalBequestGrant
  - frame_jobs_against <- justice.FrameJobDetails
  - denouncements_made <- justice.DenounceRecord
  - commanded_military_units <- military.MilitaryUnit
  - summoned_military_units <- military.MilitaryUnit
  - commanded_armies <- military.Army
  - narrative_message_deliveries <- narrative.NarrativeMessageDelivery
  - petitions_about <- player_submissions.Petition
  - relationships_as_source <- relationships.CharacterRelationship
  - relationships_as_target <- relationships.CharacterRelationship
  - relationshipupdate_set <- relationships.RelationshipUpdate
  - relationshipdevelopment_set <- relationships.RelationshipDevelopment
  - relationshipcapstone_set <- relationships.RelationshipCapstone
  - relationshipchange_set <- relationships.RelationshipChange
  - unseen_observations <- scenes.SceneUnseenObserver
  - personas <- scenes.Persona
  - persona_discoveries <- scenes.PersonaDiscovery
  - scene_round_participations <- scenes.SceneRoundParticipant
  - pending_sudden_harm <- scenes.PendingSuddenHarm
  - secrets <- secrets.Secret
  - secret_grievances <- secrets.SecretGrievance
  - leverage_held <- secrets.Leverage
  - leverage_against <- secrets.Leverage
  - accusation_rebuttals <- secrets.AccusationRebuttal
  - skill_values <- skills.CharacterSkillValue
  - specialization_values <- skills.CharacterSpecializationValue
  - training_allocations <- skills.TrainingAllocation
  - character_stories <- stories.Story
  - story_participations <- stories.StoryParticipation
  - aggregate_contributions <- stories.AggregateBeatContribution
  - beat_completions <- stories.BeatCompletion
  - episode_resolutions <- stories.EpisodeResolution
  - story_progress <- stories.StoryProgress
  - gambling_loss_ledgers <- tavern_games.GamblingLossLedger
  - vitals <- vitals.CharacterVitals
  - carrying_body <- vitals.CarriedBody
  - carried_by <- vitals.CarriedBody
  - avatar_of_being <- worship.WorshippedBeing
  - worship_grants <- worship.WorshipGrant
  - devotion_standings <- worship.DevotionStanding
  - worship_declaration <- worship.WorshipDeclaration
  - miracle_performances <- worship.MiraclePerformance

### Gender
**Pointed to by:**
  - kinspeople <- roster.Kinsperson
  - drafts <- character_creation.CharacterDraft
  - character_sheets <- character_sheets.CharacterSheet

### Heritage
**Pointed to by:**
  - beginnings <- character_creation.Beginnings
  - profiles <- character_sheets.Profile

### MoodOption
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)

### Profile
**Foreign Keys:**
  - heritage -> character_sheets.Heritage [FK] (nullable)
  - origin_realm -> realms.Realm [FK] (nullable)
  - family -> roster.Family [FK] (nullable)
  - tarot_card -> tarot.TarotCard [FK] (nullable)
**Pointed to by:**
  - text_versions <- character_sheets.ProfileTextVersion
  - owning_sheet <- character_sheets.CharacterSheet
  - personas <- scenes.Persona

### ProfileTextVersion
**Foreign Keys:**
  - profile -> character_sheets.Profile [FK]
  - era -> stories.Era [FK] (nullable)
  - edited_by -> evennia.AccountDB [FK] (nullable)
**Pointed to by:**
  - applied_by_request_details <- gm.ProfileTextRequestDetails

### Pronouns
**Pointed to by:**
  - character_sheets <- character_sheets.CharacterSheet

### Service Functions
- `can_edit_character_sheet(user: 'AbstractBaseUser | AnonymousUser', roster_entry: 'RosterEntry') -> 'bool' - True if the user is the original creator (player_number=1) or staff.`
- `count_active_ocs(account: 'AbstractBaseUser') -> 'int' - Count OCs an account currently holds against its cap.`
- `create_character_with_sheet(*, character_key: 'str', primary_persona_name: 'str', typeclass: 'str' = 'typeclasses.characters.Character', home: 'ObjectDB | None' = None, **sheet_kwargs: 'Any') -> 'tuple[ObjectDB, CharacterSheet, Persona]' - Atomically create a Character + CharacterSheet + PRIMARY Persona.`
- `enforce_oc_cap(account: 'AbstractBaseUser', *, cap: 'int' = 3) -> 'None' - Raise OCCapError if creating another OC would exceed ``cap``.`
- `set_physical_description(sheet: 'CharacterSheet', text: 'str') -> 'None' - THE seam for setting a character's free-text physical description (#2632).`
- `update_profile_text(profile: 'Profile', field: 'str', text: 'str', *, edited_by: 'Any | None' = None, previous_text: 'str | None' = None) -> 'ProfileTextVersion' - Write a versioned Profile prose field — the ONLY sanctioned write path (#2631).`


## world.checks

### CheckCall
**Foreign Keys:**
  - scene -> scenes.Scene [FK]
  - caller_persona -> scenes.Persona [FK]
  - check_type -> checks.CheckType [FK]
**Pointed to by:**
  - targets <- checks.CheckCallTarget

### CheckCallTarget
**Foreign Keys:**
  - call -> checks.CheckCall [FK]
  - target_sheet -> character_sheets.CharacterSheet [FK]

### CheckCategory
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
**Pointed to by:**
  - check_types <- checks.CheckType
  - condition_check_modifiers <- conditions.ConditionCheckModifier

### CheckType
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - category -> checks.CheckCategory [FK]
  - owner_sheet -> character_sheets.CharacterSheet [FK] (nullable)
**Pointed to by:**
  - action_templates <- actions.ActionTemplate
  - action_template_gates <- actions.ActionTemplateGate
  - consequence_outcomes <- checks.ConsequenceOutcome
  - traits <- checks.CheckTypeTrait
  - capability_modifiers <- checks.CheckTypeCapabilityModifier
  - aspects <- checks.CheckTypeAspect
  - specializations <- checks.CheckTypeSpecialization
  - check_calls <- checks.CheckCall
  - cures_conditions <- conditions.ConditionTemplate
  - resists_condition_applications <- conditions.ConditionTemplate
  - breaks_free_conditions <- conditions.ConditionTemplate
  - conditionstage_set <- conditions.ConditionStage
  - conditioncheckmodifier_set <- conditions.ConditionCheckModifier
  - treatmenttemplate_set <- conditions.TreatmentTemplate
  - modifier_target <- mechanics.ModifierTarget
  - challenge_approaches <- mechanics.ChallengeApproach
  - detect_situation_traps <- mechanics.SituationTrapLink
  - disarm_situation_traps <- mechanics.SituationTrapLink
  - context_consequence_pools <- mechanics.ContextConsequencePool
  - legend_contributions <- societies.LegendContribution
  - situational_perks <- covenants.VowSituationalPerk
  - soulfrayconfig_set <- magic.SoulfrayConfig
  - threat_pool_entries <- combat.ThreatPoolEntry
  - escalation_curves <- combat.EscalationCurve
  - professions <- currency.Profession
  - dream_peril_configs <- dreams.DreamPerilConfig
  - situation_fits <- gm.CheckTypeSituationFit
  - item_check_modifiers <- items.ItemCheckModifier
  - detect_traps <- room_features.Trap
  - disarm_traps <- room_features.Trap
  - assist_patterns <- missions.MissionAssistPattern
  - project_contribution_methods <- projects.ContributionMethod
  - scene_check_modifiers <- scenes.SceneCheckModifier
  - task_templates <- tasking.TaskTemplate

### CheckTypeAspect
**Foreign Keys:**
  - check_type -> checks.CheckType [FK]
  - aspect -> classes.Aspect [FK]

### CheckTypeCapabilityModifier
**Foreign Keys:**
  - check_type -> checks.CheckType [FK]
  - capability -> conditions.CapabilityType [FK]

### CheckTypeSpecialization
**Foreign Keys:**
  - check_type -> checks.CheckType [FK]
  - specialization -> skills.Specialization [FK]

### CheckTypeTrait
**Foreign Keys:**
  - check_type -> checks.CheckType [FK]
  - trait -> traits.Trait [FK]

### Consequence
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - outcome_tier -> traits.CheckOutcome [FK]
**Pointed to by:**
  - pool_entries <- actions.ConsequencePoolEntry
  - consequence_outcomes <- checks.ConsequenceOutcome
  - effects <- checks.ConsequenceEffect
  - challenge_templates <- mechanics.ChallengeTemplate
  - challenge_template_consequences <- mechanics.ChallengeTemplateConsequence
  - approach_consequences <- mechanics.ApproachConsequence
  - challenge_records <- mechanics.CharacterChallengeRecord

### ConsequenceEffect
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - consequence -> checks.Consequence [FK]
  - condition_template -> conditions.ConditionTemplate [FK] (nullable)
  - relationship_condition -> relationships.RelationshipCondition [FK] (nullable)
  - property -> mechanics.Property [FK] (nullable)
  - distinction -> distinctions.Distinction [FK] (nullable)
  - damage_type -> conditions.DamageType [FK] (nullable)
  - flow_definition -> flows.FlowDefinition [FK] (nullable)
  - codex_entry -> codex.CodexEntry [FK] (nullable)
  - secret -> secrets.Secret [FK] (nullable)
  - legend_source_type -> societies.LegendSourceType [FK] (nullable)
  - capture_captor_organization -> societies.Organization [FK] (nullable)
  - capture_captive_template -> missions.MissionTemplate [FK] (nullable)
  - capture_rescue_template -> missions.MissionTemplate [FK] (nullable)
**Pointed to by:**
  - affection_shifts <- relationships.AffectionShift

### ConsequenceOutcome
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - check_type -> checks.CheckType [FK]
  - pool -> actions.ConsequencePool [FK] (nullable)
  - selected_consequence -> checks.Consequence [FK] (nullable)
  - combat_interaction -> scenes.Interaction [FK] (nullable)
  - challenge_record -> mechanics.CharacterChallengeRecord [FK] (nullable)
**Pointed to by:**
  - modifiers <- checks.ConsequenceOutcomeModifier

### ConsequenceOutcomeModifier
**Foreign Keys:**
  - outcome -> checks.ConsequenceOutcome [FK]

### Service Functions
- `award_check_development(character_sheet: 'CharacterSheet', check_type: 'CheckType', effort_level: 'str | None', path_level: 'int') -> 'list[tuple[str, int, int]]' - Award dp to traits used in a check.`
- `chart_has_success_outcomes(rank_difference: int) -> bool - Check if the ResultChart for this rank difference has any success outcomes.`
- `collect_check_modifiers(character_sheet: 'CharacterSheet', check_type: 'CheckType', *, scene: 'Scene | None' = None, extra_contributions: list[world.checks.types.ModifierContribution] | None = None, skip_fashion: bool = False) -> world.checks.types.ModifierBreakdown - Aggregate all modifier contributions for a check into a ModifierBreakdown.`
- `compute_check_rating(character: 'ObjectDB', check_type: 'CheckType', extra_modifiers: int = 0, *, level_override: int | None = None, stat_override: str | int | None = None) -> int - Return *character*'s pre-roll rating (total points) for *check_type* — no dice roll.`
- `compute_resist_increment(defender_character: 'ObjectDB', resist_effort_level: str, *, level_override: int | None = None, stat_override: str | int | None = None, award_development: bool = False) -> int - Compute how much a defender's active resistance raises difficulty.`
- `get_character_path_level(character: 'ObjectDB') -> 'int' - Return the character's primary class level (or highest, or 1).`
- `get_rollmod(character: 'ObjectDB') -> int - Sum character.sheet_data.rollmod + character.account.player_data.rollmod.`
- `level_opposition(check_type: 'CheckType', *, level: int, character: 'ObjectDB | None' = None) -> int - Difficulty an opposing entity of *level* adds to *check_type* (#2707).`
- `perform_check(character: 'ObjectDB', check_type: 'CheckType', target_difficulty: int = 0, extra_modifiers: int = 0, effort_level: str | None = None, fatigue_penalty: int = 0, specialization: 'Specialization | None' = None, *, situation_ctx: 'SituationContext | None' = None, level_override: int | None = None, stat_override: str | int | None = None) -> world.checks.types.CheckResult - Main check resolution function.`
- `perform_check_with_modifiers(character: 'ObjectDB', check_type: 'CheckType', target_difficulty: int = 0, extra_modifiers: int = 0, effort_level: str | None = None, fatigue_penalty: int = 0, specialization: 'Specialization | None' = None, *, situation_ctx: 'SituationContext | None' = None, level_override: int | None = None, scene: 'Scene | None' = None, extra_contributions: 'list[ModifierContribution] | None' = None, skip_fashion: bool = False, stat_override: str | int | None = None) -> world.checks.types.CheckResult - Run a check with all character modifiers gathered automatically.`
- `preview_check_difficulty(character: 'ObjectDB', check_type: 'CheckType', target_difficulty: int = 0, extra_modifiers: int = 0, *, stat_override: str | int | None = None) -> int - Preview the rank difference for a check without rolling.`
- `record_consequence_outcome(character_sheet: 'CharacterSheet', check_type: 'CheckType', pool, selected_consequence: 'Consequence | None', breakdown: world.checks.types.ModifierBreakdown, *, combat_interaction: 'Interaction | None' = None, challenge_record: 'CharacterChallengeRecord | None' = None, summary: str = '') -> world.checks.outcome_models.ConsequenceOutcome - Persist one consequence-resolution event as a ConsequenceOutcome + modifier rows.`


## world.classes

### Aspect
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
**Pointed to by:**
  - check_type_aspects <- checks.CheckTypeAspect
  - path_aspects <- classes.PathAspect

### CharacterClass
**Foreign Keys:**
  - core_traits -> traits.Trait [M2M]
**Pointed to by:**
  - character_assignments <- classes.CharacterClassLevel
  - stage_health_rates <- classes.ClassStageHealthRate
  - durance_advancements <- progression.ClassLevelAdvancement
  - xp_costs <- progression.ClassXPCost
  - level_unlocks <- progression.ClassLevelUnlock
  - classlevelrequirement_set <- progression.ClassLevelRequirement
  - multi_requirements <- progression.MultiClassRequirement
  - multiclasslevel_set <- progression.MultiClassLevel
  - character_unlocks <- progression.CharacterUnlock

### CharacterClassLevel
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - character_class -> classes.CharacterClass [FK]

### ClassStageHealthRate
**Foreign Keys:**
  - character_class -> classes.CharacterClass [FK]

### Path
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - style -> magic.TechniqueStyle [FK] (nullable)
  - parent_paths -> classes.Path [M2M]
**Pointed to by:**
  - child_paths <- classes.Path
  - path_aspects <- classes.PathAspect
  - drafts <- character_creation.CharacterDraft
  - codex_grants <- codex.PathCodexGrant
  - durance_training_sites <- progression.DuranceTrainingSite
  - path_intents <- progression.PathIntent
  - character_selections <- progression.CharacterPathHistory
  - traitrequirement_requirements <- progression.TraitRequirement
  - levelrequirement_requirements <- progression.LevelRequirement
  - classlevelrequirement_requirements <- progression.ClassLevelRequirement
  - multiclassrequirement_requirements <- progression.MultiClassRequirement
  - achievementrequirement_requirements <- progression.AchievementRequirement
  - relationshiprequirement_requirements <- progression.RelationshipRequirement
  - legendrequirement_requirements <- progression.LegendRequirement
  - tierrequirement_requirements <- progression.TierRequirement
  - itemrequirement_requirements <- progression.ItemRequirement
  - majorgifttechniquerequirement_requirements <- progression.MajorGiftTechniqueRequirement
  - codexknowledgerequirement_requirements <- progression.CodexKnowledgeRequirement
  - audere_majora_crossings <- magic.AudereMajoraCrossing
  - gift_unlocks <- magic.GiftUnlock
  - glimpse_trigger_tags <- magic.GlimpseTag
  - ritual_grants <- magic.PathRitualGrant
  - gift_grants <- magic.PathGiftGrant
  - thread_weaving_unlocks <- magic.ThreadWeavingUnlock
  - skill_suggestions <- skills.PathSkillSuggestion

### PathAspect
**Foreign Keys:**
  - character_path -> classes.Path [FK]
  - aspect -> classes.Aspect [FK]

### Service Functions
- `ensure_class_stage_health_rates() -> int - Seed per-stage health rates for every CharacterClass (#3001).`
- `ensure_default_character_class() -> world.classes.models.CharacterClass - Get or create the single shared default CharacterClass (#3038).`
- `is_crossing_level(level: int) -> bool - Return True if ``level`` is a PathStage crossing boundary.`
- `set_primary_class_level(character: object, character_class: object, level: int) -> object - Set the character's primary class level and recompute level-derived health.`
- `stage_for_level(level: int) -> int - Map a class level to its PathStage value (clamps <1 to PROSPECT).`


## world.clues

### CharacterClue
**Foreign Keys:**
  - roster_entry -> roster.RosterEntry [FK]
  - clue -> clues.Clue [FK]

### Clue
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - target_codex_entry -> codex.CodexEntry [FK] (nullable)
  - target_mission -> missions.MissionTemplate [FK] (nullable)
  - target_captivity -> captivity.Captivity [FK] (nullable)
  - target_secret -> secrets.Secret [FK] (nullable)
  - target_persona -> scenes.Persona [FK] (nullable)
  - target_persona_linked -> scenes.Persona [FK] (nullable)
  - target_item_template -> items.ItemTemplate [FK] (nullable)
  - target_item_instance -> items.ItemInstance [FK] (nullable)
**Pointed to by:**
  - pool_entries <- assets.CluePoolEntry
  - held_by <- clues.CharacterClue
  - research_projects <- clues.ResearchProjectDetails
  - room_placements <- clues.RoomClue
  - trigger_placements <- clues.ClueTrigger
  - item_trigger_placements <- clues.ItemClueTrigger
  - npc_reveal_offers <- npc_services.ClueRevealOfferDetails

### ClueTrigger
**Foreign Keys:**
  - room_profile -> evennia_extensions.RoomProfile [FK]
  - clue -> clues.Clue [FK]

### ItemClueTrigger
**Foreign Keys:**
  - item_template -> items.ItemTemplate [FK]
  - clue -> clues.Clue [FK]

### ResearchProjectDetails
**Foreign Keys:**
  - project -> projects.Project [OneToOne]
  - clue -> clues.Clue [FK]

### RoomClue
**Foreign Keys:**
  - room_profile -> evennia_extensions.RoomProfile [FK]
  - clue -> clues.Clue [FK]

### Service Functions
- `acquire_clue(roster_entry: 'RosterEntry', clue: 'Clue') -> 'CharacterClue' - Record that a character has found a clue (idempotent).`
- `clear_rescue_clues(captivity: 'Captivity') -> 'None' - Delete a captivity's rescue clues (and their placements) when it resolves (#931).`
- `create_accusation_counter_clue(secret: 'Secret', *, region: 'Area', difficulty: 'int') -> 'Clue' - Plant the investigable trail an accusation leaves behind (#1825). Idempotent.`
- `grant_clue_target(clue: 'Clue', roster_entry: 'RosterEntry') -> 'None' - AUTOMATIC resolution — grant a clue's target to the character on the spot.`
- `maybe_grant_clue_triggers(character: 'ObjectDB', room: 'ObjectDB') -> 'list[Clue]' - Grant clues triggered passively by entering ``room`` (#1160).`
- `maybe_grant_item_acquisition_clues(character: 'ObjectDB', item: 'ItemInstance') -> 'list[Clue]' - Grant clues triggered passively by ``character`` acquiring ``item`` (#1160).`
- `plant_rescue_clue(captivity: 'Captivity', room_profile: 'RoomProfile', *, name: 'str', description: 'str', detect_difficulty: 'int' = 0) -> 'RoomClue' - Plant a discoverable rescue clue at a location for a held captive (#931 Phase 4).`
- `search_room(character: 'ObjectDB', room_profile: 'RoomProfile', search_check_type: 'CheckType') -> 'list[Clue]' - Search a room: roll ``search_check_type`` against each hidden clue's difficulty.`
- `target_already_known(clue: 'Clue', roster_entry: 'RosterEntry') -> 'bool' - Whether the character already has what this clue points at.`


## world.codex

### BeginningsCodexGrant
**Foreign Keys:**
  - beginnings -> character_creation.Beginnings [FK]
  - entry -> codex.CodexEntry [FK]

### CharacterCodexKnowledge
**Foreign Keys:**
  - roster_entry -> roster.RosterEntry [FK]
  - entry -> codex.CodexEntry [FK]
  - learned_from -> roster.RosterTenure [FK] (nullable)

### CodexCategory
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
**Pointed to by:**
  - subjects <- codex.CodexSubject

### CodexEntry
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - discovery_achievement -> achievements.Achievement [FK] (nullable)
  - subject -> codex.CodexSubject [FK]
  - modifier_target -> mechanics.ModifierTarget [OneToOne] (nullable)
  - art -> evennia_extensions.Media [FK] (nullable)
  - subject_item_template -> items.ItemTemplate [FK] (nullable)
  - subject_item_instance -> items.ItemInstance [FK] (nullable)
  - prerequisites -> codex.CodexEntry [M2M]
**Pointed to by:**
  - consequence_effects <- checks.ConsequenceEffect
  - clues <- clues.Clue
  - unlocks <- codex.CodexEntry
  - character_knowledge <- codex.CharacterCodexKnowledge
  - teaching_offers <- codex.CodexTeachingOffer
  - beginnings_grants <- codex.BeginningsCodexGrant
  - path_grants <- codex.PathCodexGrant
  - distinction_grants <- codex.DistinctionCodexGrant
  - tradition_grants <- codex.TraditionCodexGrant
  - house_aspect_options <- societies.HouseAspectOption
  - resonances <- magic.Resonance
  - gifts <- magic.Gift
  - techniques <- magic.Technique
  - codex_knowledge_requirements <- progression.CodexKnowledgeRequirement
  - crossing_options <- magic.CrossingOption
  - ritual_grants <- magic.CodexEntryRitualGrant
  - progression_milestones <- magic.MagicProgressionMilestone
  - species <- species.Species
  - mantle_level_gates <- items.MantleLevelDefinition

### CodexSubject
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - category -> codex.CodexCategory [FK]
  - parent -> codex.CodexSubject [FK] (nullable)
**Pointed to by:**
  - climates <- weather.Climate
  - weather_types <- weather.WeatherType
  - architectural_styles <- buildings.ArchitecturalStyle
  - children <- codex.CodexSubject
  - breadcrumb_cache <- codex.CodexSubjectBreadcrumb
  - entries <- codex.CodexEntry

### CodexSubjectBreadcrumb
**Foreign Keys:**
  - subject -> codex.CodexSubject [OneToOne]

### CodexTeachingOffer
**Foreign Keys:**
  - teacher -> roster.RosterTenure [FK]
  - entry -> codex.CodexEntry [FK]
  - visible_to_tenures -> roster.RosterTenure [M2M]
  - visible_to_groups -> consent.ConsentGroup [M2M]
  - excluded_tenures -> roster.RosterTenure [M2M]

### DistinctionCodexGrant
**Foreign Keys:**
  - distinction -> distinctions.Distinction [FK]
  - entry -> codex.CodexEntry [FK]

### PathCodexGrant
**Foreign Keys:**
  - path -> classes.Path [FK]
  - entry -> codex.CodexEntry [FK]

### TraditionCodexGrant
**Foreign Keys:**
  - tradition -> magic.Tradition [FK]
  - entry -> codex.CodexEntry [FK]

### Service Functions
- `grant_codex_entry(roster_entry: 'RosterEntry', entry: 'CodexEntry', *, learned_from: 'RosterTenure | None' = None) -> 'tuple[CharacterCodexKnowledge, bool]' - Grant ``entry`` to ``roster_entry`` as fully KNOWN. Idempotent.`
- `resolve_codex_links(content: 'str | None', subject: 'CodexSubject', roster_entries: 'Sequence[RosterEntry]') -> 'list[dict]' - Parse ``[[Entry Name]]`` wikilinks from content and resolve to link refs.`


## world.combat

### BossPhase
**Foreign Keys:**
  - threat_pool -> combat.ThreatPool [FK] (nullable)
  - reinforcement_template -> combat.CreatureTemplate [FK] (nullable)
  - opponent -> combat.CombatOpponent [FK]

### BreakBarConfig
**Foreign Keys:**
  - boss_phase -> combat.CreaturePhaseTemplate [OneToOne]

### BreakBarContribution
**Foreign Keys:**
  - opponent -> combat.CombatOpponent [FK]
  - participant -> combat.CombatParticipant [FK] (nullable)
  - effect_type -> magic.EffectType [FK] (nullable)

### Clash
**Foreign Keys:**
  - encounter -> combat.CombatEncounter [FK]
  - npc_opponent -> combat.CombatOpponent [FK]
  - initiator -> character_sheets.CharacterSheet [FK] (nullable)
  - resolution_consequence_pool -> actions.ConsequencePool [FK]
  - per_round_consequence_pool -> actions.ConsequencePool [FK] (nullable)
  - triggering_threat_entry -> combat.ThreatPoolEntry [FK] (nullable)
  - rampart -> areas.Rampart [FK] (nullable)
**Pointed to by:**
  - rounds <- combat.ClashRound
  - declarations <- combat.ClashContributionDeclaration
  - engagement_locks <- combat.EngagementLock

### ClashConfig
**Foreign Keys:**
  - updated_by -> evennia.AccountDB [FK] (nullable)

### ClashContribution
**Foreign Keys:**
  - clash_round -> combat.ClashRound [FK]
  - character -> character_sheets.CharacterSheet [FK]
  - technique -> magic.Technique [FK] (nullable)
  - check_outcome -> traits.CheckOutcome [FK]
  - interaction -> scenes.Interaction [FK] (nullable)

### ClashContributionDeclaration
**Foreign Keys:**
  - fury_commitment -> magic.FuryTier [FK] (nullable)
  - fury_anchor -> character_sheets.CharacterSheet [FK] (nullable)
  - encounter -> combat.CombatEncounter [FK]
  - participant -> combat.CombatParticipant [FK]
  - clash -> combat.Clash [FK]
  - technique -> magic.Technique [FK]

### ClashRound
**Foreign Keys:**
  - clash -> combat.Clash [FK]
**Pointed to by:**
  - contributions <- combat.ClashContribution

### CombatEncounter
**Foreign Keys:**
  - scene -> scenes.Scene [FK]
  - room -> evennia.ObjectDB [FK] (nullable)
  - escalation_curve -> combat.EscalationCurve [FK] (nullable)
  - duel_winner -> character_sheets.CharacterSheet [FK] (nullable)
  - story_beat -> stories.Beat [FK] (nullable)
  - scenario_deed -> missions.MissionDeedRecord [FK] (nullable)
**Pointed to by:**
  - battle_places <- battles.BattlePlace
  - covenant_rite_instances <- covenants.CovenantRiteInstance
  - opponents <- combat.CombatOpponent
  - participants <- combat.CombatParticipant
  - pending_opponent_attacks <- combat.PendingOpponentAttack
  - sustained_actions <- combat.SustainedAction
  - combat_pulls <- combat.CombatPull
  - challenge_declarations <- combat.RoundChallengeDeclaration
  - clashes <- combat.Clash
  - clash_declarations <- combat.ClashContributionDeclaration
  - risk_acknowledgements <- combat.EncounterRiskAcknowledgement
  - dramatic_surges <- combat.DramaticSurgeRecord
  - duel_challenge <- combat.DuelChallenge
  - threat_records <- combat.ThreatRecord
  - engagement_locks <- combat.EngagementLock
  - pending_selections <- combat.PendingSelection
  - marks <- combat.CombatMark
  - companion_orders <- companions.CompanionOrder

### CombatMark
**Foreign Keys:**
  - encounter -> combat.CombatEncounter [FK]
  - participant -> combat.CombatParticipant [FK]
  - opponent -> combat.CombatOpponent [FK]
  - source_technique -> magic.Technique [FK] (nullable)

### CombatOpponent
**Foreign Keys:**
  - encounter -> combat.CombatEncounter [FK]
  - threat_pool -> combat.ThreatPool [FK] (nullable)
  - creature_template -> combat.CreatureTemplate [FK] (nullable)
  - persona -> scenes.Persona [FK] (nullable)
  - portrait -> evennia_extensions.Media [FK] (nullable)
  - objectdb -> evennia.ObjectDB [FK] (nullable)
  - mirrors_participant -> combat.CombatParticipant [FK] (nullable)
  - summoned_by -> character_sheets.CharacterSheet [FK] (nullable)
  - barrier_break_pool -> actions.ConsequencePool [FK] (nullable)
  - aftermath_pool -> actions.ConsequencePool [FK] (nullable)
  - wall_breaker_combo -> combat.ComboDefinition [FK] (nullable)
  - reinforces -> combat.CombatOpponent [FK] (nullable)
**Pointed to by:**
  - reinforced_by <- combat.CombatOpponent
  - phases <- combat.BossPhase
  - action_targets <- combat.CombatRoundActionTarget
  - round_actions <- combat.CombatOpponentAction
  - incoming_opponent_attacks <- combat.CombatOpponentAction
  - pending_attacks <- combat.PendingOpponentAttack
  - clashes <- combat.Clash
  - break_contributions <- combat.BreakBarContribution
  - threat_records <- combat.ThreatRecord
  - engagement_locks <- combat.EngagementLock
  - pending_selections <- combat.PendingSelection
  - marks <- combat.CombatMark
  - consider_readings <- combat.ConsiderReading

### CombatOpponentAction
**Foreign Keys:**
  - opponent -> combat.CombatOpponent [FK]
  - threat_entry -> combat.ThreatPoolEntry [FK]
  - targets -> combat.CombatParticipant [M2M]
  - opponent_targets -> combat.CombatOpponent [M2M]
**Pointed to by:**
  - npc_regard_events <- npc_services.NpcRegardEvent

### CombatParticipant
**Foreign Keys:**
  - encounter -> combat.CombatEncounter [FK]
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - covenant_role -> covenants.CovenantRole [FK] (nullable)
**Pointed to by:**
  - mirror_surface <- combat.CombatOpponent
  - round_actions <- combat.CombatRoundAction
  - incoming_attacks <- combat.CombatOpponentAction
  - sustained_actions <- combat.SustainedAction
  - combat_pulls <- combat.CombatPull
  - challenge_declarations <- combat.RoundChallengeDeclaration
  - break_contributions <- combat.BreakBarContribution
  - clash_declarations <- combat.ClashContributionDeclaration
  - dramatic_surges <- combat.DramaticSurgeRecord
  - threat_records <- combat.ThreatRecord
  - engagement_locks <- combat.EngagementLock
  - pending_selections <- combat.PendingSelection
  - marks <- combat.CombatMark
  - consider_readings <- combat.ConsiderReading

### CombatPull
**Foreign Keys:**
  - participant -> combat.CombatParticipant [FK]
  - encounter -> combat.CombatEncounter [FK]
  - resonance -> magic.Resonance [FK]
  - threads -> magic.Thread [M2M]
**Pointed to by:**
  - resolved_effects <- combat.CombatPullResolvedEffect

### CombatPullResolvedEffect
**Foreign Keys:**
  - pull -> combat.CombatPull [FK]
  - source_thread -> magic.Thread [FK]
  - granted_capability -> conditions.CapabilityType [FK] (nullable)
  - resistance_damage_type -> conditions.DamageType [FK] (nullable)

### CombatRoundAction
**Foreign Keys:**
  - fury_commitment -> magic.FuryTier [FK] (nullable)
  - fury_anchor -> character_sheets.CharacterSheet [FK] (nullable)
  - participant -> combat.CombatParticipant [FK]
  - focused_action -> magic.Technique [FK] (nullable)
  - focused_opponent_target -> combat.CombatOpponent [FK] (nullable)
  - focused_ally_target -> combat.CombatParticipant [FK] (nullable)
  - item_instance -> items.ItemInstance [FK] (nullable)
  - physical_passive -> magic.Technique [FK] (nullable)
  - social_passive -> magic.Technique [FK] (nullable)
  - mental_passive -> magic.Technique [FK] (nullable)
  - combo_upgrade -> combat.ComboDefinition [FK] (nullable)
  - cast_destination -> areas.Position [FK] (nullable)
  - cast_position_a -> areas.Position [FK] (nullable)
  - cast_position_b -> areas.Position [FK] (nullable)
  - redirect_opponent_target -> combat.CombatOpponent [FK] (nullable)
  - redirect_object_target -> evennia.ObjectDB [FK] (nullable)
  - interaction -> scenes.Interaction [FK] (nullable)
**Pointed to by:**
  - extra_targets <- combat.CombatRoundActionTarget
  - npc_regard_events <- npc_services.NpcRegardEvent

### CombatRoundActionTarget
**Foreign Keys:**
  - action -> combat.CombatRoundAction [FK]
  - opponent -> combat.CombatOpponent [FK] (nullable)

### ComboDefinition
**Foreign Keys:**
  - discovery_achievement -> achievements.Achievement [FK] (nullable)
  - required_clash_window_condition -> conditions.ConditionTemplate [FK] (nullable)
**Pointed to by:**
  - wall_breaker_for_opponents <- combat.CombatOpponent
  - slots <- combat.ComboSlot
  - learnings <- combat.ComboLearning
  - signatures <- combat.ComboSignature
  - round_actions <- combat.CombatRoundAction

### ComboLearning
**Foreign Keys:**
  - combo -> combat.ComboDefinition [FK]
  - character_sheet -> character_sheets.CharacterSheet [FK]

### ComboSignature
**Foreign Keys:**
  - covenant -> covenants.Covenant [FK]
  - combo -> combat.ComboDefinition [FK]

### ComboSlot
**Foreign Keys:**
  - combo -> combat.ComboDefinition [FK]
  - required_action_type -> magic.EffectType [FK]
  - resonance_requirement -> magic.Resonance [FK] (nullable)

### ConsiderReading
**Foreign Keys:**
  - participant -> combat.CombatParticipant [FK]
  - opponent -> combat.CombatOpponent [FK]

### CreaturePhaseTemplate
**Foreign Keys:**
  - threat_pool -> combat.ThreatPool [FK] (nullable)
  - reinforcement_template -> combat.CreatureTemplate [FK] (nullable)
  - creature_template -> combat.CreatureTemplate [FK]
**Pointed to by:**
  - break_bar <- combat.BreakBarConfig

### CreatureTemplate
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - threat_pool -> combat.ThreatPool [FK] (nullable)
**Pointed to by:**
  - weakness_pool_entries <- covenants.WeaknessPoolEntry
  - spawned_opponents <- combat.CombatOpponent
  - bossphase_set <- combat.BossPhase
  - creaturephasetemplate_set <- combat.CreaturePhaseTemplate
  - phase_templates <- combat.CreaturePhaseTemplate
  - mission_option_opponent_lines <- missions.MissionOptionOpponentLine
  - beat_opponent_lines <- stories.BeatOpponentLine

### DramaticSurgeRecord
**Foreign Keys:**
  - encounter -> combat.CombatEncounter [FK]
  - participant -> combat.CombatParticipant [FK]
  - subject_sheet -> character_sheets.CharacterSheet [FK] (nullable)
  - subject_opponent -> combat.CombatOpponent [FK] (nullable)

### DuelChallenge
**Foreign Keys:**
  - challenger_sheet -> character_sheets.CharacterSheet [FK] (nullable)
  - challenged_sheet -> character_sheets.CharacterSheet [FK]
  - room -> evennia.ObjectDB [FK] (nullable)
  - threat_pool -> combat.ThreatPool [FK] (nullable)
  - resulting_encounter -> combat.CombatEncounter [FK] (nullable)

### EncounterAftermathRule
**Foreign Keys:**
  - check_type -> checks.CheckType [FK]
  - consequence_pool -> actions.ConsequencePool [FK] (nullable)

### EncounterOutcomeMapping
**Foreign Keys:**
  - check_outcome -> traits.CheckOutcome [FK]

### EncounterRiskAcknowledgement
**Foreign Keys:**
  - encounter -> combat.CombatEncounter [FK]
  - character_sheet -> character_sheets.CharacterSheet [FK]

### EncounterScalingConfig
**Foreign Keys:**
  - updated_by -> evennia.AccountDB [FK] (nullable)

### EngagementLock
**Foreign Keys:**
  - encounter -> combat.CombatEncounter [FK]
  - opponent -> combat.CombatOpponent [FK]
  - participant -> combat.CombatParticipant [FK]
  - clash -> combat.Clash [FK] (nullable)
  - break_in_consequence_pool -> actions.ConsequencePool [FK] (nullable)

### EscalationCurve
**Foreign Keys:**
  - pace_check_type -> checks.CheckType [FK]
**Pointed to by:**
  - encounters <- combat.CombatEncounter

### FleeConfig
**Foreign Keys:**
  - check_type -> checks.CheckType [FK]
  - consequence_pool -> actions.ConsequencePool [FK] (nullable)
  - updated_by -> evennia.AccountDB [FK] (nullable)

### FleeTierModifier

### OpponentTierTemplate

### PendingOpponentAttack
**Foreign Keys:**
  - encounter -> combat.CombatEncounter [FK]
  - opponent -> combat.CombatOpponent [FK]
  - threat_entry -> combat.ThreatPoolEntry [FK]
  - target -> combat.CombatParticipant [FK] (nullable)

### PendingSelection
**Foreign Keys:**
  - participant -> combat.CombatParticipant [FK]
  - encounter -> combat.CombatEncounter [FK]
  - source_content_type -> django.ContentType [FK] (nullable)
  - target_opponent -> combat.CombatOpponent [FK] (nullable)

### RiskScalingModifier

### RoundChallengeDeclaration
**Foreign Keys:**
  - encounter -> combat.CombatEncounter [FK]
  - participant -> combat.CombatParticipant [FK]
  - challenge_instance -> mechanics.ChallengeInstance [FK]
  - challenge_approach -> mechanics.ChallengeApproach [FK]

### StakesEscalationModifier
**Foreign Keys:**
  - default_curve -> combat.EscalationCurve [FK] (nullable)

### StakesLevelRequirement

### StrainConfig
**Foreign Keys:**
  - updated_by -> evennia.AccountDB [FK] (nullable)

### SustainedAction
**Foreign Keys:**
  - encounter -> combat.CombatEncounter [FK]
  - participant -> combat.CombatParticipant [FK]
  - ritual -> magic.Ritual [FK] (nullable)
  - technique -> magic.Technique [FK] (nullable)
  - declared_action -> combat.CombatRoundAction [FK] (nullable)
  - outcome_snapshot -> traits.CheckOutcome [FK] (nullable)

### ThreatPool
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
**Pointed to by:**
  - entries <- combat.ThreatPoolEntry
  - opponents <- combat.CombatOpponent
  - bossphase_set <- combat.BossPhase
  - creature_templates <- combat.CreatureTemplate
  - creaturephasetemplate_set <- combat.CreaturePhaseTemplate
  - lethal_duel_challenges <- combat.DuelChallenge

### ThreatPoolEntry
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - pool -> combat.ThreatPool [FK]
  - damage_type -> conditions.DamageType [FK] (nullable)
  - on_hit_consequence_pool -> actions.ConsequencePool [FK] (nullable)
  - defense_check_type -> checks.CheckType [FK] (nullable)
  - clash_resolution_pool -> actions.ConsequencePool [FK] (nullable)
  - clash_per_round_pool -> actions.ConsequencePool [FK] (nullable)
  - conditions_applied -> conditions.ConditionTemplate [M2M]
  - effect_properties -> mechanics.Property [M2M]

### ThreatRecord
**Foreign Keys:**
  - encounter -> combat.CombatEncounter [FK]
  - opponent -> combat.CombatOpponent [FK]
  - participant -> combat.CombatParticipant [FK]

### Service Functions
- `accumulate_soulfray(*, character: 'ObjectDB', anima: 'CharacterAnima', deficit: 'int', soulfray_config: 'SoulfrayConfig | None', check_result: 'CheckResult | None', lethal: 'bool' = True) -> 'SoulfrayResult | None' - Accumulate Soulfray severity from the pool state and apply stage consequences.`
- `accumulate_threat(encounter: 'CombatEncounter', opponent: 'CombatOpponent', participant: 'CombatParticipant', amount: 'int') -> 'None' - Increment the threat value for an (opponent, participant) pairing (#2020).`
- `acknowledge_encounter_risk(encounter: 'CombatEncounter', character_sheet: 'CharacterSheet') -> 'EncounterRiskAcknowledgement' - Idempotently record that a character acknowledged the encounter's risk (#777).`
- `active_combat_engagement_for(character: 'ObjectDB') -> 'CharacterEngagement | None' - The character's live COMBAT ``CharacterEngagement`` (``source`` is the encounter), or None.`
- `add_opponent(encounter: 'CombatEncounter', *, name: 'str', tier: 'str', threat_pool: 'ThreatPool | None', max_health: 'int | None' = None, description: 'str' = '', soak_value: 'int | None' = None, probing_threshold: 'int | None' = None, swarm_count: 'int | None' = None, body_toughness: 'int | None' = None, bodies_per_attack: 'int | None' = None, barrier_strength: 'int | None' = None, auto_phases: 'bool' = True, persona: 'Persona | None' = None, existing_objectdb: 'ObjectDB | None' = None, acting_account: 'AccountDB | None' = None, position: 'Position | None' = None, level: 'int | None' = None) -> 'CombatOpponent' - Create a CombatOpponent. Three sources for the ObjectDB:`
- `add_participant(encounter: 'CombatEncounter', character_sheet: 'CharacterSheet', *, covenant_role: 'CovenantRole | None' = None) -> 'CombatParticipant' - Create a CombatParticipant linking a PC to an encounter.`
- `apply_damage_to_opponent(opponent: 'CombatOpponent', raw_damage: 'int', *, bypass_soak: 'bool' = False, bypass_pre_apply: 'bool' = False, damage_type: 'DamageType | None' = None, source_sheet: 'CharacterSheet | None' = None, skip_guardian_shield: 'bool' = False, execute_missing_health_multiplier: 'Decimal' = Decimal('0')) -> 'OpponentDamageResult' - Apply damage to an NPC opponent, accounting for soak, probing,`
- `apply_damage_to_participant(participant: 'CombatParticipant', damage: 'int', *, force_death: 'bool' = False, bypass_pre_apply: 'bool' = False, damage_type: 'DamageType | None' = None, source: 'object | None' = None, source_sheet: 'CharacterSheet | None' = None, on_hit_pool: 'ConsequencePool | None' = None, delivery: 'str' = StrikeDelivery.MELEE, is_area: 'bool' = False, execute_missing_health_multiplier: 'Decimal' = Decimal('0')) -> 'ParticipantDamageResult' - Apply damage to a PC via their CharacterVitals.`
- `apply_equipped_armor_soak(character: 'Character', damage: 'int') -> 'int' - Reduce ``damage`` by role-gated equipped-armor soak (#1174, #2533).`
- `apply_fatigue(character_sheet: 'CharacterSheet', category: 'str', base_cost: 'int', effort_level: 'str') -> 'int' - Add fatigue to the pool.`
- `apply_interpose_outcome(pre_payload: 'DamagePreApplyPayload', result: 'ChallengeResolutionResult', *, interposer: 'object | None' = None) -> 'None' - Map a graded interpose resolution onto *pre_payload*.`
- `apply_position_cover(character: 'Character', damage: 'int', damage_type: 'DamageType | None') -> 'int' - Subtract attack-cover from damage.`
- `apply_rampart_interception(character_or_opponent: 'Character', damage: 'int', damage_type: 'DamageType | None', *, attacker_ref: 'object | None', delivery: 'str' = StrikeDelivery.MELEE, is_area: 'bool' = False) -> 'int' - Intercept a strike against a rampart-covered position (#2209).`
- `assess_break_bar(encounter: 'CombatEncounter', action_outcomes: 'list[ActionOutcome]') -> 'None' - Assess break-bar depletion for all boss opponents with a break bar (#2642).`
- `begin_declaration_phase(encounter: 'CombatEncounter') -> 'None' - Advance round_number by 1 and set status to DECLARING.`
- `check_and_advance_boss_phase(opponent: 'CombatOpponent') -> 'BossPhase | None' - Check whether a boss should advance to the next phase and apply it.`
- `classify_source(source: object | None) -> flows.events.payloads.DamageSource - Return a ``DamageSource`` describing *source*'s origin.`
- `cleanup_completed_encounter(encounter: 'CombatEncounter') -> 'None' - Delete encounter-ephemeral CombatNPC ObjectDBs. Persistent NPCs and PCs`
- `collect_check_modifiers(character_sheet: 'CharacterSheet', check_type: 'CheckType', *, scene: 'Scene | None' = None, extra_contributions: list[world.checks.types.ModifierContribution] | None = None, skip_fashion: bool = False) -> world.checks.types.ModifierBreakdown - Aggregate all modifier contributions for a check into a ModifierBreakdown.`
- `combatants_hostile_to(actor: 'CombatParticipant | CombatOpponent') -> 'dict[str, list]' - Return the combatants *actor* may attack, grouped by kind.`
- `complete_encounter(encounter: 'CombatEncounter', *, outcome: 'EncounterOutcome') -> 'None' - Single completion seam for round resolution and the GM end endpoint (#876).`
- `compute_intensity_for_clash(participant: 'CombatParticipant', action: 'CombatRoundAction') -> 'int' - Return technique.intensity + active INTENSITY_BUMP pull bonuses for the clash floor gate.`
- `declare_action(participant: 'CombatParticipant', *, focused_action: 'Technique | None' = None, focused_category: 'str | None' = None, effort_level: 'str', focused_opponent_target: 'CombatOpponent | None' = None, focused_ally_target: 'CombatParticipant | None' = None, physical_passive: 'Technique | None' = None, social_passive: 'Technique | None' = None, mental_passive: 'Technique | None' = None, confirm_soulfray_risk: 'bool' = False, strain_commitment: 'int' = 0, fury_commitment: 'FuryTier | None' = None, fury_anchor: 'CharacterSheet | None' = None, cast_destination: 'Position | None' = None, cast_position_a: 'Position | None' = None, cast_position_b: 'Position | None' = None) -> 'CombatRoundAction' - Declare a PC's action for the current round.`
- `declare_charge(participant: 'CombatParticipant', technique: 'Technique', opponent: 'CombatOpponent') -> 'CombatRoundAction' - Declare a mounted charge — closes distance to *opponent*, then attacks (#1843).`
- `declare_clash_contribution(*, participant: 'CombatParticipant', clash: 'Clash', action_slot: 'str', technique: 'Technique', strain_commitment: 'int') -> 'ClashContributionDeclaration' - Write (or overwrite) a PC's clash contribution declaration for the current round.`
- `declare_cover(participant: 'CombatParticipant', ally: 'CombatParticipant') -> 'CombatRoundAction' - Declare a covering maneuver for an ally -- passives-only, auto-ready.`
- `declare_demoralize(participant: 'CombatParticipant', opponent: 'CombatOpponent') -> 'CombatRoundAction' - Declare a demoralizing maneuver — break an opponent's nerve, auto-ready (#2015).`
- `declare_flee(participant: 'CombatParticipant') -> 'CombatRoundAction' - Declare intent to flee -- passives-only maneuver, auto-ready.`
- `declare_interpose(participant: 'CombatParticipant', ally: 'CombatParticipant | None' = None, technique: 'Technique | None' = None, redirect_opponent_target: 'CombatOpponent | None' = None, redirect_object_target: 'ObjectDB | None' = None, *, confirm_soulfray_risk: 'bool' = False) -> 'CombatRoundAction' - Declare an interposing maneuver — passives-only, auto-ready.`
- `declare_joust(participant: 'CombatParticipant', technique: 'Technique') -> 'CombatRoundAction' - Declare a joust — a mounted, lance-armed opposed pass (#1843).`
- `declare_mark(participant: 'CombatParticipant', opponent: 'CombatOpponent', *, technique: 'Technique | None' = None) -> 'CombatMark' - Declare a mark — a directed, round-scoped combatant reference (#2664).`
- `declare_parley(participant: 'CombatParticipant', opponent: 'CombatOpponent') -> 'CombatRoundAction' - Declare a parley maneuver — talk a foe down mid-fight, auto-ready (#2015).`
- `declare_rally(participant: 'CombatParticipant', ally: 'CombatParticipant') -> 'CombatRoundAction' - Declare a rallying maneuver — inspire an ally, auto-ready (#2015).`
- `declare_succor(participant: 'CombatParticipant', ally: 'CombatParticipant') -> 'CombatRoundAction' - Declare a sheltering maneuver for a specific ally — passives-only, auto-ready.`
- `declare_taunt(participant: 'CombatParticipant', opponent: 'CombatOpponent') -> 'CombatRoundAction' - Declare a taunting maneuver — draw an NPC's aggro, auto-ready (#2015).`
- `declare_use_item(participant: 'CombatParticipant', item_instance: 'ItemInstance', *, target: 'CombatParticipant | CombatOpponent | None' = None) -> 'CombatRoundAction' - Declare using a held on-use item as this round's action (#2023, #2120).`
- `deduct_anima(character: 'ObjectDB', effective_cost: 'int', *, lethal: 'bool' = True) -> 'int' - Deduct anima from character, returning the overburn deficit.`
- `detect_available_combos(encounter: 'CombatEncounter', round_number: 'int') -> 'list[AvailableCombo]' - Scan declared actions to find combos whose slots are all satisfied.`
- `dispatch_interpose(interposer: 'ObjectDB', protected: 'ObjectDB', pre_payload: 'DamagePreApplyPayload', *, approach: 'str | None', extra_modifiers: 'int' = 0, select_best_check_rating: 'bool' = False) -> 'ChallengeResolutionResult | None' - Resolve *interposer*'s interpose attempt and apply the graded outcome.`
- `dispatch_succor(succorer: 'ObjectDB', protected: 'ObjectDB', *, approach: 'str | None', extra_modifiers: 'int' = 0) -> 'float' - Resolve *succorer*'s Succor attempt against *protected* and return the multiplier.`
- `drain_reactive_upkeep(encounter: 'CombatEncounter') -> 'None' - Debit per-round upkeep from each active participant's sustained conditions.`
- `effective_soak_from_armor(character: 'Character') -> 'int' - Sum effective armor soak across the character's equipped armor pieces.`
- `effective_weapon_profile(character: 'Character') -> 'WeaponContribution | None' - The character's strongest equipped weapon as a combat contribution.`
- `elevation_bonus(attacker_sheet: 'CharacterSheet', attacker_pos: 'Position', target_pos: 'Position') -> 'int' - Flat to-hit bonus when attacker is elevated/aerial and target is not.`
- `emit_event(event_name: str, payload: Any, location: Any, *, parent_stack: flows.flow_stack.FlowStack | None = None) -> flows.flow_stack.FlowStack - Dispatch ``event_name`` to every handler in ``location`` + contents.`
- `end_encounter(encounter: 'CombatEncounter') -> 'CombatEncounter' - GM force-end: completes as ABANDONED (#876 §8).`
- `expire_pulls_for_round(encounter: 'CombatEncounter') -> 'None' - Delete all CombatPull rows from prior rounds and recompute affected max_health.`
- `finalize_new_encounter(encounter: 'CombatEncounter') -> 'None' - Apply the post-creation defaults every "scene-anchored, no explicit room" creation`
- `get_clash_config() -> 'ClashConfig' - Get-or-create the ClashConfig singleton (pk=1).`
- `get_concentration_check_type() -> 'CheckType' - Return the seeded 'Concentration' CheckType rolled at sustained-action`
- `get_fatigue_penalty(character_sheet: 'CharacterSheet', category: 'str') -> 'int' - Return the check penalty for the current fatigue zone.`
- `get_flee_config() -> 'FleeConfig' - Return the seeded FleeConfig singleton (#878).`
- `get_or_create_threat_record(encounter: 'CombatEncounter', opponent: 'CombatOpponent', participant: 'CombatParticipant') -> 'ThreatRecord' - Get or create the ThreatRecord for an (opponent, participant) pairing (#2020).`
- `get_penetration_check_type() -> 'CheckType' - Return the seeded 'penetration' CheckType for the ward contest (#639).`
- `get_resolution_order(encounter: 'CombatEncounter') -> 'list[tuple[str, CombatParticipant | CombatOpponent]]' - Build the resolution order for a combat round.`
- `get_strain_config() -> 'StrainConfig' - Get-or-create the StrainConfig singleton (pk=1).`
- `has_persistent_identity_references(objectdb: 'ObjectDB') -> 'bool' - Return True if this ObjectDB is referenced by any model that signals`
- `increment_probing(opponent: 'CombatOpponent', amount: 'int') -> 'None' - Add ``amount`` to an opponent's probing counter (clamped at zero) and persist.`
- `is_combat_npc_typeclass(objectdb: 'ObjectDB') -> 'bool' - Return True iff the ObjectDB's typeclass is the CombatNPC class.`
- `join_encounter(encounter: 'CombatEncounter', character_sheet: 'CharacterSheet', *, covenant_role: 'CovenantRole | None' = None) -> 'CombatParticipant' - Allow a PC to join an active combat encounter.`
- `leave_encounter(participant: 'CombatParticipant') -> 'None' - Allow a participant to voluntarily leave an Open Encounter between rounds.`
- `level_opposition(check_type: 'CheckType', *, level: int, character: 'ObjectDB | None' = None) -> int - Difficulty an opposing entity of *level* adds to *check_type* (#2707).`
- `maybe_pause_encounter_for_disconnect(character_sheet: 'CharacterSheet') -> 'None' - Pause the character's live CombatEncounter, if any, on disconnect (#1899).`
- `maybe_resolve_on_ready(encounter: 'CombatEncounter') -> 'RoundResolutionResult | None' - Resolve the round early when every ACTIVE participant is ready (#2120).`
- `minimum_break_bar_threshold() -> 'int' - Pacing floor for a boss's break-bar threshold (#2642, batch-3 F-7a).`
- `perform_check(character: 'ObjectDB', check_type: 'CheckType', target_difficulty: int = 0, extra_modifiers: int = 0, effort_level: str | None = None, fatigue_penalty: int = 0, specialization: 'Specialization | None' = None, *, situation_ctx: 'SituationContext | None' = None, level_override: int | None = None, stat_override: str | int | None = None) -> world.checks.types.CheckResult - Main check resolution function.`
- `perform_check_with_modifiers(character: 'ObjectDB', check_type: 'CheckType', target_difficulty: int = 0, extra_modifiers: int = 0, effort_level: str | None = None, fatigue_penalty: int = 0, specialization: 'Specialization | None' = None, *, situation_ctx: 'SituationContext | None' = None, level_override: int | None = None, scene: 'Scene | None' = None, extra_contributions: 'list[ModifierContribution] | None' = None, skip_fashion: bool = False, stat_override: str | int | None = None) -> world.checks.types.CheckResult - Run a check with all character modifiers gathered automatically.`
- `remove_opponent(opponent: 'CombatOpponent') -> 'None' - Pull an opponent out of a live encounter (GM action, #3382).`
- `remove_participant(participant: 'CombatParticipant') -> 'None' - Remove a participant: status write + combat engagement teardown (#872).`
- `resolve_cast_position_params(participant: 'CombatParticipant', technique: 'Technique', position_params: 'dict[str, int]') -> 'dict[str, Position | None]' - Validate declared cast positions against the encounter's room + technique reach.`
- `resolve_combat_technique(*, participant: 'CombatParticipant', action: 'CombatRoundAction', fatigue_category: 'str', offense_check_type: 'CheckType', offense_check_fn: 'PerformCheckFn | None') -> 'CombatTechniqueResult' - Route a damage-path combat technique through use_technique.`
- `resolve_npc_attack(opponent_action: 'CombatOpponentAction', participant: 'CombatParticipant', check_type: 'CheckType', *, perform_check_fn: 'PerformCheckFn | None' = None) -> 'DefenseResult' - Resolve one NPC attack against one PC via a defensive check.`
- `resolve_round(encounter: 'CombatEncounter', *, defense_check_fn: 'PerformCheckFn | None' = None, defense_check_type: 'CheckType | None' = None, offense_check_fn: 'PerformCheckFn | None' = None) -> 'RoundResolutionResult' - Orchestrate a full combat round: detect combos -> resolve -> consequences.`
- `revert_combo_upgrade(action: 'CombatRoundAction') -> 'None' - Remove a combo upgrade from a round action, reverting to normal.`
- `roll_sustained_absorption_budget(participant: 'CombatParticipant') -> 'tuple[int, CheckOutcome | None]' - Roll Concentration once to set a sustained action's absorption budget (#2705).`
- `run_combo_detection(encounter: 'CombatEncounter', round_number: 'int') -> 'list[AvailableCombo]' - Public entry point for combo detection during the DECLARING phase.`
- `select_npc_actions(encounter: 'CombatEncounter') -> 'list[CombatOpponentAction]' - Select and create NPC actions for the current round.`
- `spawn_from_creature_template(encounter: 'CombatEncounter', template: 'CreatureTemplate', *, position: 'Position | None' = None, acting_account: 'AccountDB | None' = None) -> 'CombatOpponent' - Spawn a CombatOpponent from a CreatureTemplate bestiary entry (#2016).`
- `swarm_attack_count(swarm_count: 'int', bodies_per_attack: 'int', active_pc_count: 'int') -> 'int' - Attacks a swarm makes this round — scales with remaining bodies (#875).`
- `swarm_kills(raw_damage: 'int', body_toughness: 'int') -> 'int' - Bodies a single landing attack clears from a swarm (#875).`
- `toggle_action_ready(action: 'CombatRoundAction') -> 'CombatRoundAction' - Flip the ready flag on a round action and persist it.`
- `try_declare_sustained_ritual(*, sheet: 'CharacterSheet', ritual: 'Ritual', kwargs: 'dict[str, Any]') -> 'SustainedAction | None' - Defer a combat-cast ritual across rounds instead of dispatching now (#2705, Task 5).`
- `update_encounter_settings(encounter: 'CombatEncounter', *, stakes_level: 'str | None' = None, risk_level: 'str | None' = None, pace_mode: 'str | None' = None, pace_timer_minutes: 'int | None' = None) -> 'CombatEncounter' - GM-driven mid-encounter settings change (#3383).`
- `upgrade_action_to_combo(action: 'CombatRoundAction', combo: 'ComboDefinition') -> 'None' - Mark a PC's round action as upgraded to a combo.`
- `wind_penalty(felt: int) -> int - The missile check penalty for a room's felt WIND exposure (#1555).`
- `windup_damage_scale(downgrades: 'int') -> 'float' - The downgrade ladder: x(1 - 0.25*downgrades), floored at x0.25 (#2637 design 3).`


## world.companions

### Companion
**Foreign Keys:**
  - owner -> character_sheets.CharacterSheet [FK]
  - archetype -> companions.CompanionArchetype [FK]
  - granting_gift -> magic.Gift [FK]
  - objectdb -> evennia.ObjectDB [FK] (nullable)
  - ridden_by -> character_sheets.CharacterSheet [FK] (nullable)
**Pointed to by:**
  - deployments <- companions.CompanionDeployment
  - orders <- companions.CompanionOrder

### CompanionAbility
**Foreign Keys:**
  - archetype -> companions.CompanionArchetype [FK]
  - damage_type -> conditions.DamageType [FK] (nullable)
  - grants_property -> mechanics.Property [FK] (nullable)
  - technique -> magic.Technique [FK] (nullable)
  - conditions_applied -> conditions.ConditionTemplate [M2M]
  - effect_properties -> mechanics.Property [M2M]
**Pointed to by:**
  - function_tags <- companions.CompanionAbilityFunctionTag
  - orders <- companions.CompanionOrder

### CompanionAbilityFunctionTag
**Foreign Keys:**
  - ability -> companions.CompanionAbility [FK]

### CompanionArchetype
**Pointed to by:**
  - abilities <- companions.CompanionAbility
  - companions <- companions.Companion

### CompanionDeployment
**Foreign Keys:**
  - companion -> companions.Companion [FK]
  - battle -> battles.Battle [FK]
  - vehicle -> battles.BattleVehicle [OneToOne]

### CompanionOrder
**Foreign Keys:**
  - companion -> companions.Companion [FK]
  - encounter -> combat.CombatEncounter [FK] (nullable)
  - battle -> battles.Battle [FK] (nullable)
  - ability -> companions.CompanionAbility [FK] (nullable)
  - target_opponent -> combat.CombatOpponent [FK] (nullable)
  - target_unit -> battles.BattleUnit [FK] (nullable)
  - defending_participant -> combat.CombatParticipant [FK] (nullable)
  - target_ally -> battles.BattleParticipant [FK] (nullable)

### StablesDetails
**Foreign Keys:**
  - feature_instance -> room_features.RoomFeatureInstance [OneToOne]

### Service Functions
- `bind_companion(*, owner: 'CharacterSheet', archetype: 'CompanionArchetype', granting_gift: 'Gift', name: 'str') -> 'Companion' - Create a bonded Companion + its live CompanionObject in owner's current room.`
- `companion_capacity(character_sheet: 'CharacterSheet', gift: 'Gift') -> 'int' - Total Companion Capacity character_sheet has via gift's Thread level.`
- `dismount_companion(sheet: 'CharacterSheet') -> 'Companion' - Dismount *sheet* from whichever companion it is currently riding.`
- `get_pull_effects_for_thread(thread: 'Thread', **filters: 'object') -> 'list[ThreadPullEffect]' - Return ThreadPullEffect rows for ``thread`` with gift-specific preference.`
- `handle_stables_progression(project: 'Project', target_level: 'int', outcome_tier: 'CheckOutcome | None' = None) -> 'None' - STABLES strategy: row-only install/level + create StablesDetails (#1863).`
- `materialize_companion_as_battle_vehicle(companion: 'Companion', battle: 'Battle', side: 'BattleSide') -> 'BattleVehicle' - Bridge a persistent Companion into a battle-scale BattleVehicle (#1873).`
- `materialize_companion_as_combat_opponent(companion: 'Companion', encounter: 'CombatEncounter', *, threat_pool: 'ThreatPool | None' = None) -> 'CombatOpponent' - Bridge a persistent Companion into a duel-scale CombatOpponent (#1873).`
- `mount_companion(sheet: 'CharacterSheet', companion: 'Companion') -> 'Companion' - Mount *sheet* on *companion* — applies the Mounted condition to the rider.`
- `order_companion(*, companion: 'Companion', order_kind: 'str', round_number: 'int', encounter: 'CombatEncounter | None' = None, battle: 'Battle | None' = None, target_opponent=None, target_unit=None, ability=None, defending_participant=None, target_ally=None) - Validate and upsert a CompanionOrder directive (#1921).`
- `promote_summon_to_companion(*, caster_sheet: 'CharacterSheet', combat_opponent: 'CombatOpponent', archetype: 'CompanionArchetype', granting_gift: 'Gift', name: 'str') -> 'Companion' - Promote an ephemeral summon or charmed enemy into a persistent Companion (#2502).`
- `release_companion(companion: 'Companion') -> 'None' - Release a bonded companion: destroy its live object, keep the row.`
- `resolve_companion_defeat(companion: 'Companion', risk_level: 'str') -> 'bool' - Resolve a bridged companion's defeat consequence (#1873).`
- `stables_capacity_bonus_for_sheet(character_sheet: 'CharacterSheet') -> 'int' - Flat Companion Capacity bonus from all Stables the sheet has standing in.`
- `used_companion_capacity(character_sheet: 'CharacterSheet', gift: 'Gift') -> 'int' - Companion Capacity currently consumed by character_sheet's active companions via gift.`


## world.conditions

### CapabilityType
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - prerequisite -> mechanics.Prerequisite [FK] (nullable)
**Pointed to by:**
  - check_type_modifiers <- checks.CheckTypeCapabilityModifier
  - conditioncapabilityeffect_set <- conditions.ConditionCapabilityEffect
  - modifier_target <- mechanics.ModifierTarget
  - applications <- mechanics.Application
  - trait_derivations <- mechanics.TraitCapabilityDerivation
  - blocking_challenges <- mechanics.ChallengeTemplate
  - battle_weather_challenges <- battles.WeatherTypeCapabilityChallenge
  - battle_unit_template_values <- battles.BattleUnitTemplateCapability
  - techniquecapabilitygrant_grants <- magic.TechniqueCapabilityGrant
  - technique_requirements <- magic.TechniqueCapabilityRequirement
  - style_requirements <- magic.StyleCapabilityRequirement
  - techniquevariantcapabilitygrant_grants <- magic.TechniqueVariantCapabilityGrant
  - granted_by_roles <- covenants.CovenantRole
  - techniquedraftcapabilitygrant_grants <- magic.TechniqueDraftCapabilityGrant
  - thread_pull_effects <- magic.ThreadPullEffect
  - combat_pull_grants <- combat.CombatPullResolvedEffect
  - military_units <- military.MilitaryUnit
  - military_unit_values <- military.MilitaryUnitCapability
  - assist_patterns <- missions.MissionAssistPattern

### ConditionCapabilityEffect
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK] (nullable)
  - stage -> conditions.ConditionStage [FK] (nullable)
  - capability -> conditions.CapabilityType [FK]

### ConditionCategory
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
**Pointed to by:**
  - conditions <- conditions.ConditionTemplate

### ConditionCheckModifier
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK] (nullable)
  - stage -> conditions.ConditionStage [FK] (nullable)
  - check_type -> checks.CheckType [FK] (nullable)
  - check_category -> checks.CheckCategory [FK] (nullable)

### ConditionConditionInteraction
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK]
  - other_condition -> conditions.ConditionTemplate [FK]
  - result_condition -> conditions.ConditionTemplate [FK] (nullable)

### ConditionDamageInteraction
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - condition -> conditions.ConditionTemplate [FK]
  - damage_type -> conditions.DamageType [FK]
  - applies_condition -> conditions.ConditionTemplate [FK] (nullable)

### ConditionDamageOverTime
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK] (nullable)
  - stage -> conditions.ConditionStage [FK] (nullable)
  - damage_type -> conditions.DamageType [FK]

### ConditionInstance
**Foreign Keys:**
  - target -> evennia.ObjectDB [FK]
  - condition -> conditions.ConditionTemplate [FK]
  - current_stage -> conditions.ConditionStage [FK] (nullable)
  - source_character -> evennia.ObjectDB [FK] (nullable)
  - source_technique -> magic.Technique [FK] (nullable)
  - source_vow -> covenants.CovenantRole [FK] (nullable)
  - cast_destination -> areas.Position [FK] (nullable)
  - cast_position_a -> areas.Position [FK] (nullable)
  - cast_position_b -> areas.Position [FK] (nullable)
  - detected_by -> character_sheets.CharacterSheet [M2M]
**Pointed to by:**
  - triggers <- flows.Trigger
  - treatment_attempts_targeting_instance <- conditions.TreatmentAttempt
  - hazard_response <- conditions.HazardResponseState
  - granted_properties <- mechanics.ObjectProperty
  - alteration_events <- magic.MagicalAlterationEvent
  - treatment_action_requests <- scenes.SceneActionRequest
  - wound_details <- vitals.WoundDetails

### ConditionModifierEffect
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK] (nullable)
  - stage -> conditions.ConditionStage [FK] (nullable)
  - modifier_target -> mechanics.ModifierTarget [FK]

### ConditionResistanceModifier
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK] (nullable)
  - stage -> conditions.ConditionStage [FK] (nullable)
  - damage_type -> conditions.DamageType [FK] (nullable)

### ConditionStage
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - condition -> conditions.ConditionTemplate [FK]
  - resist_check_type -> checks.CheckType [FK] (nullable)
  - consequence_pool -> actions.ConsequencePool [FK] (nullable)
  - thumbnail -> evennia_extensions.Media [FK] (nullable)
  - properties -> mechanics.Property [M2M]
  - on_entry_conditions -> conditions.ConditionTemplate [M2M]
**Pointed to by:**
  - stage_triggers <- flows.Trigger
  - on_entry_assocs <- conditions.ConditionStageOnEntry
  - conditioncapabilityeffect_set <- conditions.ConditionCapabilityEffect
  - conditionmodifiereffect_set <- conditions.ConditionModifierEffect
  - conditioncheckmodifier_set <- conditions.ConditionCheckModifier
  - conditionresistancemodifier_set <- conditions.ConditionResistanceModifier
  - conditiondamageovertime_set <- conditions.ConditionDamageOverTime
  - conditioninstance_set <- conditions.ConditionInstance
  - auderethreshold_set <- magic.AudereThreshold

### ConditionStageOnEntry
**Foreign Keys:**
  - stage -> conditions.ConditionStage [FK]
  - condition -> conditions.ConditionTemplate [FK]

### ConditionTemplate
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - category -> conditions.ConditionCategory [FK]
  - cure_check_type -> checks.CheckType [FK] (nullable)
  - resist_check_type -> checks.CheckType [FK] (nullable)
  - break_free_check_type -> checks.CheckType [FK] (nullable)
  - thumbnail -> evennia_extensions.Media [FK] (nullable)
  - parent_condition -> conditions.ConditionTemplate [FK] (nullable)
  - corruption_resonance -> magic.Resonance [FK] (nullable)
  - properties -> mechanics.Property [M2M]
  - reactive_triggers -> flows.TriggerDefinition [M2M]
**Pointed to by:**
  - action_enhancements <- actions.ActionEnhancement
  - stat_rules_for <- achievements.ConditionStatRule
  - rampart_signature_profiles <- areas.RampartElementProfile
  - consequence_effects <- checks.ConsequenceEffect
  - aftermath_children <- conditions.ConditionTemplate
  - stages <- conditions.ConditionStage
  - applied_on_entry_of <- conditions.ConditionStage
  - conditionstageonentry_set <- conditions.ConditionStageOnEntry
  - conditioncapabilityeffect_set <- conditions.ConditionCapabilityEffect
  - conditionmodifiereffect_set <- conditions.ConditionModifierEffect
  - conditioncheckmodifier_set <- conditions.ConditionCheckModifier
  - conditionresistancemodifier_set <- conditions.ConditionResistanceModifier
  - conditiondamageovertime_set <- conditions.ConditionDamageOverTime
  - damage_interactions <- conditions.ConditionDamageInteraction
  - applied_by_damage_interaction <- conditions.ConditionDamageInteraction
  - interactions_as_primary <- conditions.ConditionConditionInteraction
  - interactions_as_secondary <- conditions.ConditionConditionInteraction
  - created_by_interaction <- conditions.ConditionConditionInteraction
  - conditioninstance_set <- conditions.ConditionInstance
  - treatments <- conditions.TreatmentTemplate
  - treatment_backlash_source <- conditions.TreatmentTemplate
  - techniques_applying <- magic.Technique
  - techniqueappliedcondition_applied <- magic.TechniqueAppliedCondition
  - techniqueremovedcondition_applied <- magic.TechniqueRemovedCondition
  - auderemajorafaithvariantappliedcondition_applied <- magic.AudereMajoraFaithVariantAppliedCondition
  - magical_alteration <- magic.MagicalAlterationTemplate
  - crossing_options <- magic.CrossingOption
  - resonance_alignment_tiers <- magic.ResonanceAlignmentBoonTier
  - techniquevariantappliedcondition_applied <- magic.TechniqueVariantAppliedCondition
  - insight_entries <- covenants.InsightTableEntry
  - weakness_pool_entries <- covenants.WeaknessPoolEntry
  - signaturemotifbonusappliedcondition_applied <- magic.SignatureMotifBonusAppliedCondition
  - techniquedraftappliedcondition_applied <- magic.TechniqueDraftAppliedCondition
  - techniquedraftremovedcondition_applied <- magic.TechniqueDraftRemovedCondition
  - threat_pool_entries <- combat.ThreatPoolEntry
  - companion_abilities <- companions.CompanionAbility
  - species_gift_drawbacks <- species.SpeciesGiftGrant
  - species_gift_benefits <- species.SpeciesGiftGrant
  - ward_reactions <- room_features.RoomWardDetails
  - defense_progression_projects <- room_features.DefenseProgressionDetails
  - miracleappliedcondition_applied <- worship.MiracleAppliedCondition

### DamageSuccessLevelMultiplier

### DamageType
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - resonance -> magic.Resonance [OneToOne] (nullable)
  - wound_pool -> actions.ConsequencePool [FK] (nullable)
  - death_pool -> actions.ConsequencePool [FK] (nullable)
**Pointed to by:**
  - position_shelters <- areas.PositionShelter
  - blueprint_position_shelters <- areas.BlueprintPositionShelter
  - rampart_signature_profiles <- areas.RampartElementProfile
  - rampart_resistances <- areas.RampartElementResistance
  - consequence_effects <- checks.ConsequenceEffect
  - conditionresistancemodifier_set <- conditions.ConditionResistanceModifier
  - conditiondamageovertime_set <- conditions.ConditionDamageOverTime
  - conditiondamageinteraction_set <- conditions.ConditionDamageInteraction
  - modifier_target <- mechanics.ModifierTarget
  - property_damage_modifiers <- mechanics.PropertyDamageModifier
  - weather_shelters <- weather.WeatherTypeShelter
  - techniquedamageprofile_damage_profiles <- magic.TechniqueDamageProfile
  - alteration_weaknesses <- magic.MagicalAlterationTemplate
  - techniquevariantdamageprofile_damage_profiles <- magic.TechniqueVariantDamageProfile
  - signaturemotifbonusdamageprofile_damage_profiles <- magic.SignatureMotifBonusDamageProfile
  - techniquedraftdamageprofile_damage_profiles <- magic.TechniqueDraftDamageProfile
  - thread_pull_resistances <- magic.ThreadPullEffect
  - threat_pool_entries <- combat.ThreatPoolEntry
  - combat_pull_resistances <- combat.CombatPullResolvedEffect
  - companion_abilities <- companions.CompanionAbility
  - weapon_templates <- items.ItemTemplate
  - cascade_overrides <- locations.LocationValueOverride
  - cascade_modifiers <- locations.LocationValueModifier
  - pending_sudden_harm_entries <- scenes.PendingSuddenHarm
  - miracledamageprofile_damage_profiles <- worship.MiracleDamageProfile

### HazardResponseState
**Foreign Keys:**
  - condition_instance -> conditions.ConditionInstance [OneToOne]

### PenetrationOutcomeFactor

### TreatmentAttempt
**Foreign Keys:**
  - helper -> character_sheets.CharacterSheet [FK]
  - target -> character_sheets.CharacterSheet [FK]
  - scene -> scenes.Scene [FK]
  - treatment -> conditions.TreatmentTemplate [FK]
  - thread_used -> magic.Thread [FK] (nullable)
  - target_condition_instance -> conditions.ConditionInstance [FK] (nullable)
  - target_pending_alteration -> magic.PendingAlteration [FK] (nullable)
  - outcome -> traits.CheckOutcome [FK]

### TreatmentTemplate
**Foreign Keys:**
  - target_condition -> conditions.ConditionTemplate [FK]
  - check_type -> checks.CheckType [FK]
  - backlash_target_condition -> conditions.ConditionTemplate [FK] (nullable)
**Pointed to by:**
  - attempts <- conditions.TreatmentAttempt
  - technique_payloads <- magic.TechniqueTreatment
  - draft_technique_payloads <- magic.TechniqueDraftTreatment
  - action_requests <- scenes.SceneActionRequest

### Service Functions
- `active_concealments(target: 'ObjectDB') -> django.db.models.query.QuerySet`
- `advance_condition_severity(instance: world.conditions.models.ConditionInstance, amount: int) -> world.conditions.types.SeverityAdvanceResult - Increment a condition's severity and advance stage if threshold crossed.`
- `advance_condition_stage(*, payload: object, condition_name: str) -> int | None - Advance the bearer's condition by one stage *now*, on this event (#3416).`
- `apply_condition(target: 'ObjectDB', condition: world.conditions.models.ConditionTemplate, *, severity: int = 1, duration_rounds: int | None = None, source_character: 'ObjectDB | None' = None, source_technique: 'Technique | None' = None, source_description: str = '') -> world.conditions.types.ApplyConditionResult - Apply a condition to a target, handling stacking and interactions.`
- `apply_condition_by_name(*, payload: object, condition_name: str) -> None - Apply a named condition to the character carried by the event payload.`
- `apply_stage_entry_aftermath(payload: flows.events.payloads.ConditionStageChangedPayload) -> None - On ascending stage changes, apply the stage's on_entry_conditions.`
- `attempt_break_free(instance: world.conditions.models.ConditionInstance, *, extra_modifiers: int = 0, helper_bonus: int = 0, in_combat_tick: bool = False, level_override: int | None = None) -> world.conditions.types.BreakFreeResult - Resolve a single break-free attempt against an applied condition.`
- `batch_chronic_effect_tick() -> world.conditions.types.ChronicTickSummary - Scheduler entry point. Advance long-term (chronic) DoT by one tick.`
- `bulk_apply_conditions(applications: list[world.conditions.types.BulkConditionApplication], *, source_character: 'ObjectDB | None' = None, source_technique: 'Technique | None' = None, source_description: str = '', soulfray_consented: bool = False) -> list[world.conditions.types.ApplyConditionResult] - Apply multiple conditions in a single transaction with batched queries.`
- `can_perceive(actor: 'ObjectDB', target: 'ObjectDB') -> bool - Whether *actor* can perceive *target*.`
- `clear_all_conditions(target: 'ObjectDB', *, only_negative: bool = False, only_category: 'ConditionCategory | None' = None) -> int - Remove all conditions from a target.`
- `condition_contributions(character_sheet: 'CharacterSheet', check_type: world.checks.models.CheckType) -> list[world.checks.types.ModifierContribution] - Adapt get_check_modifier's breakdown into a list of ModifierContribution.`
- `decay_all_conditions_tick() -> world.conditions.types.DecayTickSummary - Scheduler entry point. Decays all opt-in conditions by one tick.`
- `decay_condition_severity(instance: world.conditions.models.ConditionInstance, amount: int, *, _skip_corruption_sync: bool = False) -> world.conditions.types.SeverityDecayResult - Inverse of advance_condition_severity. Walks stage down if threshold crossed.`
- `emit_event(event_name: str, payload: Any, location: Any, *, parent_stack: flows.flow_stack.FlowStack | None = None) -> flows.flow_stack.FlowStack - Dispatch ``event_name`` to every handler in ``location`` + contents.`
- `ensure_conditions_content() -> None - Idempotently seed all core conditions content.`
- `ensure_poison_content() -> None - Idempotently seed poison content (#1050).`
- `expire_end_of_combat_conditions(targets: collections.abc.Iterable['ObjectDB']) -> list[world.conditions.models.ConditionTemplate] - Remove all UNTIL_END_OF_COMBAT conditions from the given targets.`
- `expire_scene_scoped_conditions(targets: collections.abc.Iterable['ObjectDB']) -> list[world.conditions.models.ConditionTemplate] - Remove all SCENE-duration conditions from the given targets.`
- `get_active_conditions(target: 'ObjectDB', *, category: 'ConditionCategory | None' = None, condition: world.conditions.models.ConditionTemplate | None = None, include_suppressed: bool = False) -> django.db.models.query.QuerySet - Get active condition instances on a target.`
- `get_aggro_priority(character_sheet: 'CharacterSheet') -> int - Get the total aggro priority from all conditions.`
- `get_all_capability_values(character_sheet: 'CharacterSheet') -> dict[int, int] - Get all capability values for a character.`
- `get_capability_status(character_sheet: 'CharacterSheet', capability: world.conditions.models.CapabilityType) -> world.conditions.types.CapabilityStatus - Get the status of a capability for a target based on active conditions.`
- `get_capability_value(character_sheet: 'CharacterSheet', capability: world.conditions.models.CapabilityType) -> int - Get the total value of a capability for a character.`
- `get_check_modifier(character_sheet: 'CharacterSheet', check_type: world.checks.models.CheckType) -> world.conditions.types.CheckModifierResult - Get the total modifier for a check type from active conditions.`
- `get_condition_control_percent_modifier(character_sheet: 'CharacterSheet', condition_name: str) -> int - Get percentage modifier to control loss rate for a condition.`
- `get_condition_instance(target: 'ObjectDB', condition: world.conditions.models.ConditionTemplate, *, include_suppressed: bool = False) -> world.conditions.models.ConditionInstance | None - Get a specific condition instance on a target.`
- `get_condition_intensity_percent_modifier(character_sheet: 'CharacterSheet', condition_name: str) -> int - Get percentage modifier to intensity gain for a condition.`
- `get_condition_modifier_breakdown(character_sheet: 'CharacterSheet', modifier_target: 'ModifierTarget') -> list[tuple[str, int]] - Per-source sibling of get_condition_modifier_total (#639 power ledger).`
- `get_condition_modifier_total(character_sheet: 'CharacterSheet', modifier_target: 'ModifierTarget') -> int - Sum active-condition contributions to a mechanics ModifierTarget (#636).`
- `get_condition_modifier_vow_contributions(character_sheet: 'CharacterSheet', modifier_target: 'ModifierTarget') -> list['ConditionModifierVowContribution'] - Vow-keyed sibling of get_condition_modifier_breakdown (#2643).`
- `get_condition_penalty_percent_modifier(character_sheet: 'CharacterSheet', condition_name: str) -> int - Get percentage modifier to check penalties for a condition.`
- `get_damage_multiplier(success_level: int) -> decimal.Decimal - Look up the damage multiplier for a given success level.`
- `get_effective_capability_value(character_sheet: 'CharacterSheet', capability: world.conditions.models.CapabilityType, *, action_ctx: 'PullActionContext | None' = None) -> int - Effective capability value = innate baseline + CharacterModifier contributions`
- `get_ic_now(*, real_now: datetime.datetime | None = None) -> datetime.datetime | None - Return the current IC datetime, or None if no clock exists.`
- `get_penetration_factor(success_level: int) -> decimal.Decimal - Look up the penetration power factor for a given success level (#639).`
- `get_resistance_modifier(character_sheet: 'CharacterSheet', damage_type: world.conditions.models.DamageType | None = None) -> world.conditions.types.ResistanceModifierResult - Get the total resistance modifier for a damage type from active conditions.`
- `get_treatment_candidates(helper_sheet: 'CharacterSheet', target_sheet: 'CharacterSheet', scene: 'Scene') -> list[dict[str, typing.Any]] - Return valid (treatment, target_effect) pairs for helper to attempt on target.`
- `get_turn_order_modifier(character_sheet: 'CharacterSheet') -> int - Get the total turn order modifier from all conditions.`
- `has_condition(target: 'ObjectDB', condition: world.conditions.models.ConditionTemplate, *, include_suppressed: bool = False) -> bool - Check if target has a specific condition.`
- `has_death_deferred(character: 'ObjectDB') -> bool - Return True if the character has any active condition granting death_deferred.`
- `is_concealed(target: 'ObjectDB') -> bool - True if *target* holds any active perception-concealing condition.`
- `is_untargetable(target: 'ObjectDB') -> bool - True if *target* holds any active intangibility condition.`
- `opponent_condition_opposition(objectdb: 'ObjectDB', check_type: world.checks.models.CheckType) -> int - Difficulty delta an opposing entity's active conditions contribute (#3384).`
- `perform_check_with_modifiers(character: 'ObjectDB', check_type: 'CheckType', target_difficulty: int = 0, extra_modifiers: int = 0, effort_level: str | None = None, fatigue_penalty: int = 0, specialization: 'Specialization | None' = None, *, situation_ctx: 'SituationContext | None' = None, level_override: int | None = None, scene: 'Scene | None' = None, extra_contributions: 'list[ModifierContribution] | None' = None, skip_fashion: bool = False, stat_override: str | int | None = None) -> world.checks.types.CheckResult - Run a check with all character modifiers gathered automatically.`
- `perform_treatment(helper_sheet: 'CharacterSheet', target_sheet: 'CharacterSheet', scene: 'Scene', treatment: world.conditions.models.TreatmentTemplate, target_effect: 'ConditionInstance | PendingAlteration', bond_thread: 'Thread | None' = None, skip_engagement_gate: bool = False, power_intensity: int = 0) -> world.conditions.types.TreatmentOutcome - Resolve a TreatmentTemplate against an effect instance.`
- `priced_percent_severity(*, eff_intensity: int, target: 'ObjectDB') -> int - Apply-time percent severity for the bounded team-damage-percent lane (#2643).`
- `process_action_tick(target: 'ObjectDB') -> world.conditions.types.RoundTickResult - Process on-action damage for conditions (when target takes an action).`
- `process_break_free_tick() -> list[world.conditions.types.BreakFreeResult] - Process periodic break-free attempts for NPC targets (#2706).`
- `process_damage_interactions(target: 'ObjectDB', damage_type: world.conditions.models.DamageType) -> world.conditions.types.DamageInteractionResult - Process condition interactions when target takes damage.`
- `process_round_end(target: 'ObjectDB') -> world.conditions.types.RoundTickResult - Process end-of-round effects for all conditions on a target.`
- `process_round_start(target: 'ObjectDB') -> world.conditions.types.RoundTickResult - Process start-of-round effects for all conditions on a target.`
- `register_detection(observer_sheet: 'CharacterSheet', target: 'ObjectDB') -> None - Record that observer_sheet has pierced target's active concealment(s) (#1225).`
- `remove_condition(target: 'ObjectDB', condition: world.conditions.models.ConditionTemplate, *, remove_all_stacks: bool = True, include_suppressed: bool = False) -> bool - Remove a condition from a target.`
- `remove_condition_by_name(*, payload: object, condition_name: str) -> bool - Remove a named condition from the character carried by the payload.`
- `remove_conditions_by_category(target: 'ObjectDB', category: 'ConditionCategory') -> list[world.conditions.models.ConditionTemplate] - Remove all conditions in a category from a target.`
- `resolve_damage_type_resistance(character: 'ObjectDB', damage_amount: int, damage_type: 'DamageType | None') -> int - Net damage-type resistance (condition + gift-thread) and return reduced damage (>=0).`
- `suppress_condition(target: 'ObjectDB', condition: world.conditions.models.ConditionTemplate, *, duration_rounds: int | None = None) -> bool - Temporarily suppress a condition's effects.`
- `unsuppress_condition(target: 'ObjectDB', condition: world.conditions.models.ConditionTemplate) -> bool - Remove suppression from a condition.`


## world.consent

### ConsentGroup
**Foreign Keys:**
  - owner -> roster.RosterTenure [FK]
**Pointed to by:**
  - members <- consent.ConsentGroupMember
  - playerboundary_visible <- boundaries.PlayerBoundary
  - treasuredsubject_visible <- boundaries.TreasuredSubject
  - codexteachingoffer_visible <- codex.CodexTeachingOffer

### ConsentGroupMember
**Foreign Keys:**
  - group -> consent.ConsentGroup [FK]
  - tenure -> roster.RosterTenure [FK]

### SocialConsentBlacklist
**Foreign Keys:**
  - owner_tenure -> roster.RosterTenure [FK]
  - blocked_tenure -> roster.RosterTenure [FK]
  - category -> consent.SocialConsentCategory [FK]

### SocialConsentCategory
**Foreign Keys:**
  - parent -> consent.SocialConsentCategory [FK] (nullable)
**Pointed to by:**
  - action_templates <- actions.ActionTemplate
  - children <- consent.SocialConsentCategory
  - rules <- consent.SocialConsentCategoryRule
  - whitelist_entries <- consent.SocialConsentWhitelist
  - blacklist_entries <- consent.SocialConsentBlacklist

### SocialConsentCategoryRule
**Foreign Keys:**
  - preference -> consent.SocialConsentPreference [FK]
  - category -> consent.SocialConsentCategory [FK]

### SocialConsentPreference
**Foreign Keys:**
  - tenure -> roster.RosterTenure [OneToOne]
**Pointed to by:**
  - category_rules <- consent.SocialConsentCategoryRule

### SocialConsentWhitelist
**Foreign Keys:**
  - owner_tenure -> roster.RosterTenure [FK]
  - allowed_tenure -> roster.RosterTenure [FK]
  - category -> consent.SocialConsentCategory [FK]

### Service Functions
- `add_social_consent_blacklist(owner_tenure: 'RosterTenure', blocked_tenure: 'RosterTenure', category: 'SocialConsentCategory') -> 'SocialConsentBlacklist' - Bar *blocked_tenure* from targeting *owner_tenure* in *category* (#1698).`
- `add_social_consent_whitelist(owner_tenure: 'RosterTenure', allowed_tenure: 'RosterTenure', category: 'SocialConsentCategory') -> 'SocialConsentWhitelist'`
- `body_handling_category() -> 'SocialConsentCategory' - Lazy seeded row for the body-handling gate (#2852) — default-deny.`
- `consent_blocks_targeting(*, owner_tenure: 'RosterTenure', category: 'SocialConsentCategory | None', actor_tenure: 'RosterTenure | None') -> 'bool' - True if *owner_tenure*'s consent excludes *actor_tenure* for *category* (#1909/#2170).`
- `decide_consent_block(rule_mode: 'str | None', *, actor_present: 'bool', whitelisted: 'bool', blacklisted: 'bool', is_friend: 'bool', is_rival: 'bool') -> 'bool' - Per-category consent decision, given a pref exists with the master switch on.`
- `effective_consent_mode(pref: 'SocialConsentPreference | None', category: 'SocialConsentCategory') -> 'str' - The ConsentMode governing *(pref, category)* after tree inheritance (#2170).`
- `get_social_consent_summary(tenure: 'RosterTenure') -> 'dict'`
- `makeover_category() -> 'SocialConsentCategory' - Lazy seeded row for the makeover/styling gate (#2632) — default-deny.`
- `receiving_stolen_goods_category() -> 'SocialConsentCategory' - Lazy seeded row for the hot-goods receipt gate (#1985) — default-deny.`
- `remove_social_consent_blacklist(owner_tenure: 'RosterTenure', blocked_tenure: 'RosterTenure', category: 'SocialConsentCategory') -> 'bool'`
- `remove_social_consent_category_rule(preference: 'SocialConsentPreference', category: 'SocialConsentCategory') -> 'bool'`
- `remove_social_consent_whitelist(owner_tenure: 'RosterTenure', allowed_tenure: 'RosterTenure', category: 'SocialConsentCategory') -> 'bool'`
- `set_social_consent_category_rule(preference: 'SocialConsentPreference', category: 'SocialConsentCategory', mode: 'str') -> 'SocialConsentCategoryRule'`
- `set_social_consent_preference(tenure: 'RosterTenure', allow_social_actions: 'bool') -> 'SocialConsentPreference'`
- `theft_category() -> 'SocialConsentCategory' - Lazy seeded row for the theft/antagonism gate (#1909) — default-deny.`


## world.contributors

### ContentContributor
**Pointed to by:**
  - player_data <- evennia_extensions.PlayerData


## world.covenants

### CharacterCovenantRole
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - covenant_role -> covenants.CovenantRole [FK]
  - covenant -> covenants.Covenant [FK]
  - rank -> covenants.CovenantRank [FK]
**Pointed to by:**
  - granted_techniques <- magic.CharacterTechnique

### CourtGrantConfig
**Foreign Keys:**
  - summons_refusal_escalation_pool -> actions.ConsequencePool [FK] (nullable)
  - petition_check_type -> checks.CheckType [FK] (nullable)
  - escalation_consequence_pool -> actions.ConsequencePool [FK] (nullable)

### CourtPact
**Foreign Keys:**
  - covenant -> covenants.Covenant [FK]
  - servant_sheet -> character_sheets.CharacterSheet [FK]

### Covenant
**Foreign Keys:**
  - organization -> societies.Organization [OneToOne]
  - campaign_story -> stories.Story [FK] (nullable)
  - leader -> character_sheets.CharacterSheet [FK] (nullable)
  - court_grant_role -> npc_services.NPCRole [FK] (nullable)
**Pointed to by:**
  - battle_sides <- battles.BattleSide
  - war_funding_projects <- battles.WarFundingDetails
  - military_readiness <- battles.CovenantMilitaryReadiness
  - legend_credits <- societies.CovenantLegendCredit
  - legend_summary <- societies.CovenantLegendSummary
  - ranks <- covenants.CovenantRank
  - memberships <- covenants.CharacterCovenantRole
  - rite_instances <- covenants.CovenantRiteInstance
  - mentor_bonds <- covenants.MentorBond
  - court_pacts <- covenants.CourtPact
  - ritualsessionreference_set <- magic.RitualSessionReference
  - combo_signatures <- combat.ComboSignature
  - court_grant_offer_details <- npc_services.CourtGrantOfferDetails
  - armies <- military.Army
  - constructed_ships <- ships.ShipConstructionDetails
  - storylines <- stories.Story
  - gm_requests <- stories.GroupStoryRequest

### CovenantLevelBonus
**Foreign Keys:**
  - modifier_target -> mechanics.ModifierTarget [FK]

### CovenantLevelThreshold

### CovenantRank
**Foreign Keys:**
  - covenant -> covenants.Covenant [FK]
**Pointed to by:**
  - memberships <- covenants.CharacterCovenantRole

### CovenantRite
**Foreign Keys:**
  - ritual -> magic.Ritual [OneToOne]
  - granted_condition -> conditions.ConditionTemplate [FK]
**Pointed to by:**
  - role_packages <- covenants.CovenantRiteRolePackage
  - instances <- covenants.CovenantRiteInstance

### CovenantRiteInstance
**Foreign Keys:**
  - rite -> covenants.CovenantRite [FK]
  - covenant -> covenants.Covenant [FK]
  - scene -> scenes.Scene [FK]
  - combat_encounter -> combat.CombatEncounter [FK] (nullable)
  - participants -> character_sheets.CharacterSheet [M2M]
**Pointed to by:**
  - participant_records <- covenants.CovenantRiteParticipant

### CovenantRiteParticipant
**Foreign Keys:**
  - instance -> covenants.CovenantRiteInstance [FK]
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - granted_condition -> conditions.ConditionTemplate [FK]

### CovenantRiteRolePackage
**Foreign Keys:**
  - rite -> covenants.CovenantRite [FK]
  - covenant_role -> covenants.CovenantRole [FK]
  - condition_template -> conditions.ConditionTemplate [FK]

### CovenantRole
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - resonance -> magic.Resonance [FK] (nullable)
  - discovery_achievement -> achievements.Achievement [FK] (nullable)
  - codex_entry -> codex.CodexEntry [FK] (nullable)
  - parent_role -> covenants.CovenantRole [FK] (nullable)
  - granted_gifts -> magic.Gift [M2M]
  - granted_capabilities -> conditions.CapabilityType [M2M]
**Pointed to by:**
  - sub_roles <- covenants.CovenantRole
  - gear_compatibilities <- covenants.GearArchetypeCompatibility
  - character_assignments <- covenants.CharacterCovenantRole
  - vow_stat_scalings <- covenants.VowStatScaling
  - action_scalings <- covenants.CovenantRoleActionScaling
  - technique_specialties <- covenants.CovenantRoleTechniqueSpecialty
  - defense_profile <- covenants.CovenantRoleDefenseProfile
  - gift_grants <- covenants.CovenantRoleGiftGrant
  - role_bonuses <- covenants.CovenantRoleBonus
  - situational_perks <- covenants.VowSituationalPerk
  - ritualsessionreference_set <- magic.RitualSessionReference
  - anchored_threads <- magic.Thread
  - combat_participations <- combat.CombatParticipant

### CovenantRoleActionScaling
**Foreign Keys:**
  - covenant_role -> covenants.CovenantRole [FK]

### CovenantRoleBonus
**Foreign Keys:**
  - covenant_role -> covenants.CovenantRole [FK]
  - modifier_target -> mechanics.ModifierTarget [FK]

### CovenantRoleDefenseProfile
**Foreign Keys:**
  - covenant_role -> covenants.CovenantRole [OneToOne]

### CovenantRoleGiftGrant
**Foreign Keys:**
  - covenant_role -> covenants.CovenantRole [FK]
  - gift -> magic.Gift [FK]

### CovenantRoleTechniqueSpecialty
**Foreign Keys:**
  - covenant_role -> covenants.CovenantRole [FK]

### GearArchetypeCompatibility
**Foreign Keys:**
  - covenant_role -> covenants.CovenantRole [FK]

### InsightTableEntry
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - condition -> conditions.ConditionTemplate [FK]

### MentorBond
**Foreign Keys:**
  - covenant -> covenants.Covenant [FK]
  - mentor_sheet -> character_sheets.CharacterSheet [FK]
  - sidekick_sheet -> character_sheets.CharacterSheet [FK]

### MentorBondConfig
**Foreign Keys:**
  - updated_by -> evennia.AccountDB [FK] (nullable)

### SecondaryVowConfig
**Foreign Keys:**
  - updated_by -> evennia.AccountDB [FK] (nullable)

### VowSituationalPerk
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - covenant_role -> covenants.CovenantRole [FK]
  - check_type -> checks.CheckType [FK] (nullable)
  - mission_category -> missions.MissionCategory [FK] (nullable)
  - mission_template -> missions.MissionTemplate [FK] (nullable)
**Pointed to by:**
  - situations <- covenants.VowSituationalPerkSituation
  - rungs <- covenants.VowSituationalPerkRung

### VowSituationalPerkRung
**Foreign Keys:**
  - perk -> covenants.VowSituationalPerk [FK]

### VowSituationalPerkSituation
**Foreign Keys:**
  - perk -> covenants.VowSituationalPerk [FK]

### VowStatScaling
**Foreign Keys:**
  - covenant_role -> covenants.CovenantRole [FK]
  - modifier_target -> mechanics.ModifierTarget [FK]

### WeaknessPoolEntry
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - creature_template -> combat.CreatureTemplate [FK]
  - condition -> conditions.ConditionTemplate [FK]

### Service Functions
- `active_court_pact_for(*, covenant: 'Covenant', servant_sheet: 'CharacterSheet') -> 'CourtPact | None' - Return the single active CourtPact for (covenant, servant_sheet), or None.`
- `add_member(*, covenant: 'Covenant', character_sheet: 'CharacterSheet', role: 'CovenantRole', standing: 'str' = MembershipStanding.CORE) -> 'CharacterCovenantRole' - Create a new active membership row. Atomic.`
- `assert_initiator_can_induct(*, session: 'RitualSession') -> 'None' - Draft-time gate for INDUCTION rituals: the initiator must hold a can_invite`
- `assign_covenant_role(*, character_sheet: 'CharacterSheet', covenant: 'Covenant', covenant_role: 'CovenantRole', rank: 'CovenantRank | None' = None) -> 'CharacterCovenantRole' - Create a new active CharacterCovenantRole row. Atomic.`
- `assign_rank(*, membership: 'CharacterCovenantRole', actor: 'CharacterCovenantRole', rank: 'CovenantRank') -> 'CharacterCovenantRole' - Assign a new rank to a member. Requires can_manage_ranks.`
- `can_invite_to_covenant(covenant: 'Covenant', *, character_sheet: 'CharacterSheet | None' = None, account: 'AccountDB | None' = None) -> 'bool' - Return True if an active member with a can_invite rank grants invite authority.`
- `can_request_gm_for_covenant(covenant: 'Covenant', *, character_sheet: 'CharacterSheet | None' = None, account: 'AccountDB | None' = None) -> 'bool' - Return True if an active member with a can_request_gm rank grants that authority.`
- `change_role(*, membership: 'CharacterCovenantRole', new_role: 'CovenantRole') -> 'CharacterCovenantRole' - Close the existing membership row; create a new active row in the same covenant.`
- `clear_engaged_for_type(*, character_sheet: 'CharacterSheet', covenant_type: 'str') -> 'None' - Un-engage every engaged active membership of the given type for the character.`
- `clear_engaged_membership(*, membership: 'CharacterCovenantRole') -> 'None' - Un-engage this membership. Idempotent.`
- `complete_rites_for_encounter(*, encounter: 'CombatEncounter') -> 'None' - Sweep covenant rite buffs when a combat encounter ends.`
- `covenant_members_present(*, covenant: 'Covenant', room: 'ObjectDB') -> 'list[CharacterSheet]' - CharacterSheets of active `covenant` members present in `room`.`
- `covenant_role_action_scaling_bonus(character: 'object', action_key: 'str') -> 'float' - Return the per-role scaling bonus for a combat action (#2529, was #2022).`
- `create_covenant(*, name: 'str', covenant_type: 'str', sworn_objective: 'str', founders: 'Sequence[CovenantFounder]', battle_binding: 'str' = '', campaign_story: 'Story | None' = None, leader: 'CharacterSheet | None' = None, flat: 'bool' = False) -> 'Covenant' - Create a covenant with its initial set of founder memberships. Atomic.`
- `create_covenant_via_session(*, session: 'RitualSession') -> 'Covenant' - Dispatched on FORMATION fire. Unpacks the session into create_covenant args.`
- `create_rank(*, covenant: 'Covenant', actor: 'CharacterCovenantRole', name: 'str', tier: 'int', can_invite: 'bool' = False, can_kick: 'bool' = False, can_manage_ranks: 'bool' = False, can_lead_rituals: 'bool' = False) -> 'CovenantRank' - Create a new rank in the covenant's ladder. Requires can_manage_ranks.`
- `delete_rank(*, rank: 'CovenantRank', actor: 'CharacterCovenantRole', reassign_to: 'CovenantRank') -> 'None' - Delete a rank after reassigning all active members to ``reassign_to``.`
- `dissolve_covenant(*, covenant: 'Covenant') -> 'None' - End all active memberships of the covenant; mark covenant dissolved.`
- `end_covenant_role(*, assignment: 'CharacterCovenantRole') -> 'None' - Mark an active assignment as ended. Idempotent. Un-engages first.`
- `establish_mentor_bond_via_session(*, session: 'RitualSession') -> 'MentorBond' - Dispatched on Mentor's Vow BILATERAL fire. Wraps establish_mentor_bond.`
- `evaluate_scene_engagement(*, character_sheet: 'CharacterSheet', room: 'ObjectDB') -> 'None' - Auto-engage a Durance covenant if co-presence prerequisites met, then`
- `fold_arrival_into_active_rites(*, character_sheet: 'CharacterSheet', room: 'ObjectDB') -> 'None' - When an engaged member arrives in a room with an active CovenantRiteInstance,`
- `gear_additive_fraction(character: 'object') -> 'Decimal' - MAX gear-additive fraction across engaged PRIMARY roles' defense profiles (#2533).`
- `get_court_grant_config() -> 'CourtGrantConfig' - Get-or-create the Court grant negotiation config singleton (pk=1).`
- `get_mentor_bond_config() -> 'MentorBondConfig' - Return the seeded MentorBondConfig singleton (#1165).`
- `induct_member_via_session(*, session: 'RitualSession') -> 'CharacterCovenantRole' - Dispatched on INDUCTION fire. Unpacks the session into add_member args.`
- `is_gear_compatible(role: 'CovenantRole', archetype: 'str') -> 'bool' - Return True if a row exists in GearArchetypeCompatibility for this pair.`
- `kick_member(*, target: 'CharacterCovenantRole', actor: 'CharacterCovenantRole') -> 'None' - Remove a member by rank authority. Soft-ends the target. Covenants never`
- `leave_covenant(*, membership: 'CharacterCovenantRole') -> 'None' - A member voluntarily leaves a covenant. Soft-ends the membership. Covenants`
- `perform_covenant_rite(*, session: 'RitualSession') -> 'CovenantRiteInstance' - Dispatched on fire of a RitualSession whose Ritual has a CovenantRite sidecar.`
- `precedence_role_for_combat(character_sheet: 'CharacterSheet') -> 'CovenantRole | None' - Pick the single covenant role that governs combat for a character.`
- `recompute_covenant_level(*, covenant: 'Covenant') -> 'int | None' - Look up the covenant's current legend total, find the max satisfied`
- `release_court_pact(*, pact: 'CourtPact') -> 'None' - Soft-release an active CourtPact by setting released_at to now.`
- `rename_rank(*, rank: 'CovenantRank', actor: 'CharacterCovenantRole', name: 'str') -> 'CovenantRank' - Rename a rank. Requires can_manage_ranks.`
- `reorder_ranks(*, covenant: 'Covenant', actor: 'CharacterCovenantRole', ordered_rank_ids: 'list[int]') -> 'list[CovenantRank]' - Rewrite tiers for the given ranks atomically and uniquely.`
- `resolve_effective_role(*, character: 'Character', role: 'CovenantRole') -> 'CovenantRole' - Return the resonance-specialized sub-role for ``role`` (one-line shim over`
- `revalidate_engagements(*, character_sheet: 'CharacterSheet', room: 'ObjectDB') -> 'None' - Re-check co-presence for all engaged covenant roles; dim vows that no longer hold.`
- `rise_battle_covenant_via_session(*, session: 'RitualSession') -> 'Covenant' - Dispatched on a 'call the banners' rise ritual fire.`
- `secondary_vow_config() -> 'SecondaryVowConfig' - Lazy-create and return the SecondaryVowConfig singleton (pk=1, #2641).`
- `set_engaged_membership(*, membership: 'CharacterCovenantRole', as_secondary: 'bool' = False) -> 'None' - Engage this membership; un-engage other same-type-and-standing rows (#2641).`
- `set_rank_capabilities(*, rank: 'CovenantRank', actor: 'CharacterCovenantRole', can_invite: 'bool | None' = None, can_kick: 'bool | None' = None, can_manage_ranks: 'bool | None' = None, can_lead_rituals: 'bool | None' = None) -> 'CovenantRank' - Update capability flags on a rank. Requires can_manage_ranks.`
- `stand_down_battle_covenant(*, covenant: 'Covenant') -> 'None' - Stand a STANDING battle covenant down to dormant; clear engagement.`
- `step_back_to_minor(*, membership: 'CharacterCovenantRole') -> 'None' - A core member unilaterally steps back to MINOR standing (#2992).`
- `swear_core(*, membership: 'CharacterCovenantRole') -> 'None' - Upgrade a MINOR membership to CORE (#2992). Runs the level-band gate`
- `swear_court_pact(*, covenant: 'Covenant', servant_sheet: 'CharacterSheet', granted_pull_cap: 'int') -> 'CourtPact' - Create an active CourtPact binding servant_sheet to covenant.`
- `transfer_top(*, covenant: 'Covenant', actor: 'CharacterCovenantRole', new_top_membership: 'CharacterCovenantRole') -> 'None' - Transfer the top rank (tier=1) from the actor to ``new_top_membership``.`
- `validate_secondary_engage_rules(membership: 'CharacterCovenantRole') -> 'None' - Secondary-vow engage-time validation (#2641).`


## world.currency

### Business
**Foreign Keys:**
  - owner_persona -> scenes.Persona [FK]
**Pointed to by:**
  - bequests <- estates.Bequest

### CharacterEmployment
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - profession -> currency.Profession [FK]

### CharacterPurse
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [OneToOne]
**Pointed to by:**
  - transfers_out <- currency.CurrencyTransfer
  - transfers_in <- currency.CurrencyTransfer

### Contract
**Foreign Keys:**
  - proposer_persona -> scenes.Persona [FK] (nullable)
  - proposer_organization -> societies.Organization [FK] (nullable)
  - counterparty_persona -> scenes.Persona [FK] (nullable)
  - counterparty_organization -> societies.Organization [FK] (nullable)
  - notary_organization -> societies.Organization [FK] (nullable)
  - garnish_stream -> currency.OrgIncomeStream [FK] (nullable)
**Pointed to by:**
  - payment_terms <- currency.ContractTerm

### ContractTerm
**Foreign Keys:**
  - contract -> currency.Contract [FK]

### ContributionRecord
**Foreign Keys:**
  - persona -> scenes.Persona [FK]
  - organization -> societies.Organization [FK]
  - transfer -> currency.CurrencyTransfer [FK] (nullable)

### CurrencyInstrumentDetails
**Foreign Keys:**
  - item_instance -> items.ItemInstance [OneToOne]

### CurrencyTransfer
**Foreign Keys:**
  - from_purse -> currency.CharacterPurse [FK] (nullable)
  - from_treasury -> currency.OrganizationTreasury [FK] (nullable)
  - to_purse -> currency.CharacterPurse [FK] (nullable)
  - to_treasury -> currency.OrganizationTreasury [FK] (nullable)
**Pointed to by:**
  - contribution_records <- currency.ContributionRecord

### DebtInstrument
**Foreign Keys:**
  - debtor_organization -> societies.Organization [FK]
  - creditor_organization -> societies.Organization [FK]

### DistinctionPurseDrain
**Foreign Keys:**
  - distinction -> distinctions.Distinction [OneToOne]

### FavorTokenDetails
**Foreign Keys:**
  - item_instance -> items.ItemInstance [OneToOne]
  - issuing_organization -> societies.Organization [FK]
**Pointed to by:**
  - honors <- societies.LegendHonor
  - settled_obligations <- societies.OrganizationObligation

### IncomeDeclaration
**Foreign Keys:**
  - stream -> currency.OrgIncomeStream [FK]

### OrgEconomicsProfile
**Foreign Keys:**
  - organization -> societies.Organization [OneToOne]

### OrgIncomeStream
**Foreign Keys:**
  - organization -> societies.Organization [FK]
  - area -> areas.Area [FK] (nullable)
**Pointed to by:**
  - domain_holding <- societies.DomainHolding
  - declarations <- currency.IncomeDeclaration
  - garnishing_contracts <- currency.Contract
  - pending_rare_finds <- items.PendingRareFind
  - material_pools <- items.StreamMaterialPool

### OrgObligation
**Foreign Keys:**
  - from_organization -> societies.Organization [FK]
  - to_organization -> societies.Organization [FK]
**Pointed to by:**
  - pact_commitment <- societies.PactCommitment
  - pact <- societies.OrgPact

### OrganizationTreasury
**Foreign Keys:**
  - organization -> societies.Organization [OneToOne]
**Pointed to by:**
  - transfers_out <- currency.CurrencyTransfer
  - transfers_in <- currency.CurrencyTransfer

### Profession
**Foreign Keys:**
  - chore_check_type -> checks.CheckType [FK] (nullable)
**Pointed to by:**
  - employees <- currency.CharacterEmployment

### PurseDrainWeek
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - game_week -> game_clock.GameWeek [FK]

### Service Functions
- `accrue_income_stream(stream: 'OrgIncomeStream') -> 'int' - One weekly cycle: the gross amasses in the uncollected pool (#930).`
- `accrue_monthly_interest(organization: 'Organization') -> 'int' - One month's interest lands in arrears (#927). Returns total accrued.`
- `auto_sell_excess_materials(*, organization: 'Organization') -> 'int' - Liquidate any ``OrgMaterialStock`` row over ``MATERIAL_AUTO_SELL_THRESHOLD`` (#2540 slice 2).`
- `can_spend_treasury(treasury: 'OrganizationTreasury', persona: 'Persona') -> 'bool' - Spend authority: an active membership at tier <= spend_rank_max.`
- `collect_and_distribute(*, organization: 'Organization', character, success_level_override: 'int | None' = None) -> 'DistributionResult' - The full collection-distribution dispatch (#2540, ruled 2026-07-20).`
- `collect_asset_income(*, asset, character_sheet) -> 'CollectionResult' - One active collection of a personal asset's accumulated income (#2294).`
- `collect_org_income(*, organization: 'Organization', character, success_level_override: 'int | None' = None) -> 'CollectionResult' - One active collection dispatch across every pooled stream of ``organization`` (#930).`
- `count_unredeemed_favor_tokens(*, sheet: 'CharacterSheet', org: 'Organization') -> 'int' - How many of ``org``'s unredeemed Golden Hares ``sheet`` holds (#3466).`
- `deliver_mission_money(*, recipient_sheet: 'CharacterSheet', amount: 'int', ref: 'str', reason_label: 'str' = 'mission reward') -> 'None' - Reward money lands in the purse (#932 — replaces the Phase 5b stub).`
- `distribute_allowance(*, organization: 'Organization', surplus: 'int') -> 'AllowanceResult' - Auto-split a share of ``surplus`` among the org's active piloted members (#2540).`
- `distribute_material_allowance(*, organization: 'Organization', landed_by_category: 'list[tuple[MaterialCategory, int]]') -> 'MaterialAllowanceResult' - Auto-split a share of newly landed materials among active piloted members (#2540 slice 2).`
- `extend_loan(*, creditor: 'Organization', debtor: 'Organization', principal: 'int', interest_bps_monthly: 'int' = 50, fiat: 'bool' = False) -> 'DebtInstrument' - Create a loan: principal moves creditor→debtor, instrument records it (#927).`
- `format_coppers(amount: int) -> str - Canonical mixed display: ``1234`` → ``"12g 3s 4c"``.`
- `fund_fame_display(persona: 'Persona', *, amount: 'int') -> 'int' - Spend money maintaining fame against decay (#932 fame churn).`
- `get_or_create_economics(organization: 'Organization') -> 'OrgEconomicsProfile'`
- `get_or_create_purse(character_sheet: 'CharacterSheet') -> 'CharacterPurse'`
- `get_or_create_treasury(organization: 'Organization') -> 'OrganizationTreasury'`
- `improve_org_domain(*, organization: 'Organization', character) -> 'ImprovementResult' - One domain-investment attempt (#930): Scholarship/Economics against the ledgers.`
- `invest_in_business(business: 'Business', *, amount: 'int') -> 'Business' - Sink owner money into a venture (#929); investment raises the level.`
- `mint_favor_token(org: 'Organization', recipient_character: 'CharacterSheet', *, provenance_note: 'str') -> 'FavorTokenDetails' - Mint a Golden Hare: one deed done for ``org``, now a physical coin (#2428).`
- `mint_instrument(*, denomination: 'str', holder_sheet: 'CharacterSheet', from_purse: 'CharacterPurse | None' = None, from_treasury: 'OrganizationTreasury | None' = None) -> 'ItemInstance' - Convert ledger money into a physical coin (face value + mint fee).`
- `mint_loose_cache(*, amount: 'int', holder_sheet: 'CharacterSheet', from_purse: 'CharacterPurse | None' = None, from_treasury: 'OrganizationTreasury | None' = None) -> 'ItemInstance' - Convert ledger money into a loose-coin cache item (#1909).`
- `process_income_stream(stream: 'OrgIncomeStream', amount: 'int', *, declared_amount: 'int | None' = None) -> 'IncomeDeclaration' - Land ``amount`` collected coppers from one stream (#926, reshaped by #930).`
- `record_contribution(*, persona: 'Persona', organization: 'Organization', amount: 'int', reason: 'str' = '') -> 'ContributionRecord' - A member pays into the org treasury, on the books (#926).`
- `redeem_favor_token(token: 'FavorTokenDetails', *, redeemer_org: 'Organization') -> 'None' - Surrender a Golden Hare: the deed is called in, once (#2428).`
- `redeem_instrument(*, instance: 'ItemInstance', to_purse: 'CharacterPurse | None' = None, to_treasury: 'OrganizationTreasury | None' = None) -> 'CurrencyTransfer' - Convert a physical coin back into ledger money (fee-free).`
- `repay_principal(debt: 'DebtInstrument', amount: 'int') -> 'CurrencyTransfer' - Pay down (or off) a debt's principal, treasury→treasury (#927).`
- `resolve_unredeemed_favor_tokens(*, sheet: 'CharacterSheet', org: 'Organization', count: 'int') -> 'list[FavorTokenDetails]' - The holder's ``count`` unredeemed tokens issued by ``org``, locked (#3466).`
- `run_business_week(business: 'Business', *, fortune: 'int') -> 'int' - One week's business result (#929). ``fortune`` is -100..100.`
- `run_purse_drains() -> 'int' - DRAIN band: empty each holder's purse down to this week's income (#2613).`
- `run_weekly_economy() -> 'dict[str, int]' - The Sunday-rollover economy pass (#932, reshaped by #930). Per-phase counts.`
- `run_weekly_employment(employment: 'CharacterEmployment', *, was_active: 'bool') -> 'int' - One week's automated wages for a held job (#929).`
- `service_debt_principal(*, organization: 'Organization', basis: 'int') -> 'int' - Pay a flat share of ``basis`` (the collection's gross) toward debt principal.`
- `settle_contract_cycle(contract: 'Contract') -> 'list[CurrencyTransfer]' - Run one settlement cycle for an ACTIVE notarized contract (#928).`
- `settle_obligations(organization: 'Organization') -> 'list[CurrencyTransfer]' - Settle all active obligations against unsettled declared income (#926).`
- `sign_contract(contract: 'Contract') -> 'Contract' - The consent moment (#928): counterparty accepts the fixed terms.`
- `snapshot_purse_drains() -> 'int' - SNAPSHOT band: record each drain-holder's opening balance (#2613).`
- `transfer(*, amount: 'int', reason: 'str', from_purse: 'CharacterPurse | None' = None, from_treasury: 'OrganizationTreasury | None' = None, to_purse: 'CharacterPurse | None' = None, to_treasury: 'OrganizationTreasury | None' = None) -> 'CurrencyTransfer' - Move ``amount`` coppers; null source = mint (faucet), null dest = sink.`
- `treat_servants(organization: 'Organization', *, payment: 'int', graft_reduction: 'int') -> 'OrgEconomicsProfile' - Spend treasury money treating servants to buy graft down (#926).`
- `withdraw_from_treasury(*, organization: 'Organization', persona: 'Persona', amount: 'int', reason: 'str' = '') -> 'CurrencyTransfer' - A spend-authorized member draws ``amount`` coppers from the org treasury to their purse.`
- `work_chore(employment: 'CharacterEmployment', *, ap_spent: 'int') -> 'int' - Active on-grid chore work (#929): spend AP now, roll, earn up to 2×.`


## world.distinctions

### CharacterDistinction
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - distinction -> distinctions.Distinction [FK]
  - secret -> secrets.Secret [OneToOne] (nullable)
  - from_glimpse -> magic.CharacterAura [FK] (nullable)
**Pointed to by:**
  - modifier_sources <- mechanics.ModifierSource
  - resonance_grants <- magic.ResonanceGrant
  - remove_sheet_update_requests <- distinctions.SheetUpdateRequest
  - table_update_request_details <- gm.DistinctionChangeRequestDetails

### CharacterDistinctionOther
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - parent_distinction -> distinctions.Distinction [FK]
  - staff_mapped_distinction -> distinctions.Distinction [FK] (nullable)

### Distinction
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - category -> distinctions.DistinctionCategory [FK]
  - parent_distinction -> distinctions.Distinction [FK] (nullable)
  - trust_category -> stories.TrustCategory [FK] (nullable)
  - mutually_exclusive_with -> distinctions.Distinction [M2M]
  - tags -> distinctions.DistinctionTag [M2M]
**Pointed to by:**
  - action_enhancements <- actions.ActionEnhancement
  - reward_definitions <- achievements.RewardDefinition
  - asset_grants <- assets.DistinctionAssetGrant
  - consequence_effects <- checks.ConsequenceEffect
  - codex_grants <- codex.DistinctionCodexGrant
  - appetite_upkeep <- magic.AppetiteUpkeep
  - glimpse_tag_suggestions <- magic.GlimpseTagDistinctionSuggestion
  - ritual_grants <- magic.DistinctionRitualGrant
  - resonance_grants <- magic.DistinctionResonanceGrant
  - resonance_rank_thresholds <- magic.DistinctionResonanceRankThreshold
  - purse_drain <- currency.DistinctionPurseDrain
  - variants <- distinctions.Distinction
  - prerequisites <- distinctions.DistinctionPrerequisite
  - effects <- distinctions.DistinctionEffect
  - character_grants <- distinctions.CharacterDistinction
  - other_entries <- distinctions.CharacterDistinctionOther
  - mapped_from_other <- distinctions.CharacterDistinctionOther
  - add_sheet_update_requests <- distinctions.SheetUpdateRequest
  - species_gift_drawbacks <- species.SpeciesGiftGrant
  - table_update_request_details <- gm.DistinctionChangeRequestDetails
  - npc_regard_seeds <- npc_services.DistinctionRegardSeed

### DistinctionCategory
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
**Pointed to by:**
  - distinctions <- distinctions.Distinction

### DistinctionEffect
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - distinction -> distinctions.Distinction [FK]
  - target -> mechanics.ModifierTarget [FK]
**Pointed to by:**
  - modifier_sources <- mechanics.ModifierSource

### DistinctionPrerequisite
**Foreign Keys:**
  - distinction -> distinctions.Distinction [FK]

### DistinctionTag
**Pointed to by:**
  - distinctions <- distinctions.Distinction

### SheetUpdateRequest
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - target_distinction -> distinctions.Distinction [FK] (nullable)
  - target_character_distinction -> distinctions.CharacterDistinction [FK] (nullable)
  - reviewed_by -> evennia.AccountDB [FK] (nullable)
  - submitted_by -> evennia.AccountDB [FK] (nullable)
**Pointed to by:**
  - table_update_request_details <- gm.DistinctionChangeRequestDetails

### Service Functions
- `approve_sheet_update_request(request: 'SheetUpdateRequest', gm_account: 'object') -> 'None' - Approve a PENDING SheetUpdateRequest: XP debit + change firing.`
- `cancel_sheet_update_request(request: 'SheetUpdateRequest', account: 'object') -> 'None' - Player-initiated cancellation of their own pending request.`
- `clear_distinction_secret(character_distinction: 'CharacterDistinction') -> 'None' - Make a relocated distinction public again by deleting its Secret (#1334).`
- `compute_distinction_change_xp_cost(request_type: 'str', distinction: 'Distinction', rank: 'int') -> 'int' - Compute the XP cost for a sheet-update request.`
- `compute_sheet_update_xp_cost(request_type: 'str', distinction: 'Distinction', rank: 'int') -> 'int' - Compute the XP cost for a sheet-update request.`
- `create_sheet_update_request(character_sheet: 'CharacterSheet', request_type: 'str', *, justification: 'str', target_distinction: 'Distinction | None' = None, target_character_distinction: 'CharacterDistinction | None' = None, submitted_by: 'object | None' = None, origin: 'str' = DistinctionOrigin.UNLOCK_PURCHASE) -> 'SheetUpdateRequest' - Create a PENDING SheetUpdateRequest.`
- `deny_sheet_update_request(request: 'SheetUpdateRequest', gm_account: 'object') -> 'None' - Deny a PENDING SheetUpdateRequest. No XP debit, no change.`
- `grant_distinction(character: 'CharacterSheet', distinction: 'Distinction', *, origin: 'str', rank: 'int | None' = None, source_description: 'str' = '') -> 'CharacterDistinction' - Grant a Distinction, or rank one up, through the single acquisition seam (#2037).`
- `mint_distinction_secret(character_distinction: 'CharacterDistinction', *, level: 'int | None' = None, provenance: 'str' = SecretProvenance.GM_AUTHORED, author_persona: 'Persona | None' = None, content: 'str' = '') -> 'Secret' - Relocate a distinction into a Secret, returning it (#1334).`
- `remove_distinction(character_distinction: 'CharacterDistinction', *, sheet_update_request: 'SheetUpdateRequest') -> 'None' - Remove a CharacterDistinction, reconciling all dependent systems.`


## world.downtime

### DowntimeWindow
**Foreign Keys:**
  - created_by -> evennia.AccountDB [FK] (nullable)

### Service Functions
- `get_next_downtime() -> world.downtime.types.PlannedDowntime | None - Return the soonest upcoming (or in-progress) downtime, if any.`


## world.dreams

### DreamPerilConfig
**Foreign Keys:**
  - resist_check_type -> checks.CheckType [FK] (nullable)

### DreamReflection
**Foreign Keys:**
  - waking_room -> evennia_extensions.RoomProfile [OneToOne]
  - dream_room -> evennia_extensions.RoomProfile [OneToOne]
  - descent_target -> evennia_extensions.RoomProfile [FK] (nullable)

### DreamwalkPresence
**Foreign Keys:**
  - dreamer -> character_sheets.CharacterSheet [OneToOne]
  - host -> character_sheets.CharacterSheet [FK]

### Service Functions
- `co_dreamers_for(sheet: 'CharacterSheet') -> 'list[CharacterSheet]' - Other dreamside sheets resolving to the same dreamspace as ``sheet``.`
- `dreamspace_for(sheet: 'CharacterSheet | None') -> 'ObjectDB | None' - The dreamspace this sheet perceives, honouring an active dreamwalk.`
- `dreamwalk_candidates_for(sheet: 'CharacterSheet') -> 'list[CharacterSheet]' - Bonded characters ``sheet`` could dreamwalk to right now (#3003).`
- `end_dreamwalk(sheet: 'CharacterSheet') -> 'ObjectDB | None' - Clear any dreamwalk and return the host's location (the wake escape lever).`
- `get_dream_space(*, room: 'ObjectDB') -> 'ObjectDB | None' - Return the dream room for a physical waking room.`
- `has_dream_bond(source_sheet: 'CharacterSheet', target_sheet: 'CharacterSheet') -> 'bool' - Check if the source has a thread or soul tether bond to the target.`
- `start_dreamwalk(*, dreamer: 'CharacterSheet', host: 'CharacterSheet') -> 'DreamwalkPresence' - Anchor ``dreamer``'s perception to ``host``'s dreamspace (idempotent).`


## world.estates

### Bequest
**Foreign Keys:**
  - will -> estates.Will [FK]
  - item -> items.ItemInstance [FK] (nullable)
  - building -> buildings.Building [FK] (nullable)
  - business -> currency.Business [FK] (nullable)
  - recipient_persona -> scenes.Persona [FK] (nullable)
  - recipient_organization -> societies.Organization [FK] (nullable)

### EstateClaim
**Foreign Keys:**
  - settlement -> estates.EstateSettlement [FK]
  - item -> items.ItemInstance [FK]
  - claimant_persona -> scenes.Persona [FK] (nullable)
  - claimant_organization -> societies.Organization [FK] (nullable)
**Pointed to by:**
  - reclamation_claims <- items.ReclamationClaim

### EstateConfig

### EstateSettlement
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [OneToOne]
**Pointed to by:**
  - claims <- estates.EstateClaim
  - revealed_journal_entries <- journals.JournalEntry
  - journal_bequest_grants <- journals.JournalBequestGrant

### Will
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [OneToOne]
**Pointed to by:**
  - executors <- estates.WillExecutor
  - bequests <- estates.Bequest

### WillExecutor
**Foreign Keys:**
  - will -> estates.Will [FK]
  - persona -> scenes.Persona [FK]

### Service Functions
- `execute_settlement(character_sheet: 'CharacterSheet', *, via: 'str') -> 'EstateSettlement | None' - The ONE execution path (spec Decision 2) — idempotent, first door wins.`
- `get_estate_config() -> world.estates.models.EstateConfig - Get-or-create the first EstateConfig row (singleton-by-convention).`
- `open_settlement(character_sheet: 'CharacterSheet') -> 'EstateSettlement' - Open the settlement window at death; idempotent per sheet.`
- `resolve_escheat_org(character_sheet: 'CharacterSheet') - The regional controlling org: primary-home region's Domain owner, else`
- `resolve_intestate_heir(character_sheet: 'CharacterSheet') - The Decision-6 cascade: family-org head, then public-record next of kin.`
- `will_is_frozen(character_sheet: 'CharacterSheet') -> 'bool' - True once a settlement window exists — the will can no longer be edited.`


## world.events

### Event
**Foreign Keys:**
  - location -> evennia_extensions.RoomProfile [FK]
  - host_society -> societies.Society [FK] (nullable)
**Pointed to by:**
  - ceremonies <- ceremonies.Ceremony
  - hosts <- events.EventHost
  - invitations <- events.EventInvitation
  - modification <- events.EventModification
  - catering <- events.EventCatering
  - grandeur_contributions <- events.EventGrandeurContribution
  - fashion_presentations <- items.FashionPresentation
  - scenes <- scenes.Scene
  - session_requests <- stories.SessionRequest
  - crossover_invites <- stories.CrossoverInvite

### EventCatering
**Foreign Keys:**
  - event -> events.Event [FK]
  - item_instance -> items.ItemInstance [FK]
  - contributed_by -> scenes.Persona [FK] (nullable)

### EventGrandeurContribution
**Foreign Keys:**
  - event -> events.Event [FK]
  - contributed_by -> scenes.Persona [FK]
  - transfer -> currency.CurrencyTransfer [FK]

### EventHost
**Foreign Keys:**
  - event -> events.Event [FK]
  - persona -> scenes.Persona [FK] (nullable)

### EventInvitation
**Foreign Keys:**
  - event -> events.Event [FK]
  - target_persona -> scenes.Persona [FK] (nullable)
  - target_organization -> societies.Organization [FK] (nullable)
  - target_society -> societies.Society [FK] (nullable)
  - invited_by -> scenes.Persona [FK] (nullable)

### EventModification
**Foreign Keys:**
  - event -> events.Event [OneToOne]

### Service Functions
- `add_host(event: world.events.models.Event, persona: world.scenes.models.Persona, *, is_primary: bool = False) -> world.events.models.EventHost - Add a host to an event.`
- `cancel_event(event: world.events.models.Event) -> world.events.models.Event - Cancel an event from DRAFT or SCHEDULED status.`
- `catering_event_for_container(container_instance: 'ItemInstance') -> world.events.models.Event | None - The open event this container is currently catering, if any (#2869).`
- `catering_history(item_instance: 'ItemInstance') -> list[world.events.models.EventCatering] - Every event this item has served at, newest first (#2869) — the souvenir.`
- `complete_event(event: world.events.models.Event) -> world.events.models.Event - Transition an event from ACTIVE to COMPLETED, finish linked scenes, and revert room.`
- `contribute_grandeur(event: world.events.models.Event, persona: world.scenes.models.Persona, *, category: str, amount: int, from_purse: 'CharacterPurse | None' = None, from_treasury: 'OrganizationTreasury | None' = None) -> world.events.models.EventGrandeurContribution - Spend on an event's grandeur budget — a currency sink tagged per category (#2357).`
- `create_event(*, name: str, location_id: int, scheduled_real_time: datetime.datetime, host_persona: world.scenes.models.Persona, description: str = '', is_public: bool = True, scheduled_ic_time: datetime.datetime | None = None, time_phase: str = TimePhase.DAY, status: str = EventStatus.DRAFT) -> world.events.models.Event - Create an event with a primary host.`
- `derive_ic_time_from_real(real_time: datetime.datetime) -> datetime.datetime | None - Derive an IC datetime from a real datetime using the game clock.`
- `designate_catering_container(event: world.events.models.Event, contributor: 'ObjectDB', container_instance: 'ItemInstance') -> world.events.models.EventCatering - Flag a container as catering for *event* (#2869).`
- `get_visible_events(persona: world.scenes.models.Persona | None = None, *, include_public: bool = True) -> django.db.models.query.QuerySet - Return events visible to a persona.`
- `invite_organization(event: world.events.models.Event, organization: world.societies.models.Organization, *, invited_by: world.scenes.models.Persona | None = None) -> world.events.models.EventInvitation - Invite an organization to an event.`
- `invite_persona(event: world.events.models.Event, target_persona: world.scenes.models.Persona, *, invited_by: world.scenes.models.Persona | None = None) -> world.events.models.EventInvitation - Invite a persona to an event.`
- `invite_society(event: world.events.models.Event, society: world.societies.models.Society, *, invited_by: world.scenes.models.Persona | None = None) -> world.events.models.EventInvitation - Invite a society to an event.`
- `on_scene_finished(scene: world.scenes.models.Scene) -> None - Grant scene completion rewards and settle reaction windows.`
- `respond_to_invitation(invitation: world.events.models.EventInvitation, persona: world.scenes.models.Persona, *, response: str) -> world.events.models.EventInvitation - Record an invitee's RSVP (ACCEPTED / DECLINED) on a PERSONA invitation.`
- `schedule_event(event: world.events.models.Event) -> world.events.models.Event - Transition an event from DRAFT to SCHEDULED.`
- `set_room_description_overlay(event: world.events.models.Event, overlay_text: str) -> world.events.models.EventModification - Set or update the room description overlay for an event.`
- `start_event(event: world.events.models.Event) -> world.events.models.Event - Transition an event from SCHEDULED to ACTIVE and create a linked Scene.`
- `tag_catered_provision(item_instance: 'ItemInstance', container_instance: 'ItemInstance', contributor: 'ObjectDB | None' = None) -> world.events.models.EventCatering | None - Tag a consumable set out in a catering vessel (#2869).`
- `validate_location_gap(location_id: int, scheduled_real_time: datetime.datetime, exclude_event_id: int | None = None) -> bool - Check that no other event at this location is within LOCATION_GAP_HOURS.`


## world.fatigue

### FatiguePool
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [OneToOne]

### Service Functions
- `apply_exhaustion_damage(character_sheet: 'CharacterSheet', amount: 'int') -> 'None' - Apply fatigue-collapse strain as actual health damage.`
- `apply_fatigue(character_sheet: 'CharacterSheet', category: 'str', base_cost: 'int', effort_level: 'str') -> 'int' - Add fatigue to the pool.`
- `apply_technique_fatigue(character_sheet: 'CharacterSheet', category: 'str', effective_anima_cost: 'int', strain_commitment: 'int', *, immune_to_fatigue_collapse: 'bool' = False) -> 'int' - Accrue fatigue from a technique cast and conditionally check collapse.`
- `attempt_endurance_check(character_sheet: 'CharacterSheet', category: 'str') -> 'bool' - Endurance check against fatigue via the unified check system.`
- `attempt_power_through(character_sheet: 'CharacterSheet', category: 'str') -> 'tuple[bool, int]' - Willpower check to power through collapse via the unified check system.`
- `ensure_stat_trait(name: 'str') -> 'Trait' - Ensure the named STAT Trait exists, creating it from STAT_TRAIT_DEFAULTS if not.`
- `get_fatigue_capacity(character_sheet: 'CharacterSheet', category: 'str', *, well_rested: 'bool | None' = None) -> 'int' - Calculate max fatigue capacity for a category.`
- `get_fatigue_penalty(character_sheet: 'CharacterSheet', category: 'str') -> 'int' - Return the check penalty for the current fatigue zone.`
- `get_fatigue_percentage(character_sheet: 'CharacterSheet', category: 'str') -> 'float' - Return current fatigue as a percentage of capacity.`
- `get_fatigue_zone(character_sheet: 'CharacterSheet', category: 'str') -> 'str' - Return the FatigueZone based on current fatigue percentage.`
- `get_full_status(character_sheet: 'CharacterSheet', *, pool: 'FatiguePool | None') -> 'dict' - Get fatigue status for all three categories in one pass.`
- `get_or_create_fatigue_pool(character_sheet: 'CharacterSheet') -> 'FatiguePool' - Get or create a FatiguePool for a character sheet.`
- `perform_check_with_modifiers(character: 'ObjectDB', check_type: 'CheckType', target_difficulty: int = 0, extra_modifiers: int = 0, effort_level: str | None = None, fatigue_penalty: int = 0, specialization: 'Specialization | None' = None, *, situation_ctx: 'SituationContext | None' = None, level_override: int | None = None, scene: 'Scene | None' = None, extra_contributions: 'list[ModifierContribution] | None' = None, skip_fashion: bool = False, stat_override: str | int | None = None) -> world.checks.types.CheckResult - Run a check with all character modifiers gathered automatically.`
- `recover_fatigue(character_sheet: 'CharacterSheet', category: 'str', amount: 'int') -> 'int' - Reduce one fatigue pool by up to *amount*, floored at zero (#2852).`
- `reset_fatigue(character_sheet: 'CharacterSheet') -> 'None' - Reset all fatigue pools to 0.`
- `resolve_fatigue_collapse(character_sheet: 'CharacterSheet', category: 'str') -> 'FatigueCollapseResult' - Run the fatigue collapse sequence for one category and apply strain damage.`
- `rest(character_sheet: 'CharacterSheet') -> 'RestResult' - Spend AP to rest, gaining well_rested for the next dawn reset.`
- `should_check_collapse(character_sheet: 'CharacterSheet', category: 'str', effort_level: 'str') -> 'bool' - Return True if a collapse check is needed.`
- `tick_fatigue_collapse_for_targets(targets: 'Iterable[ObjectDB]') -> 'None' - Evaluate non-cast over-capacity fatigue collapse for each target.`


## world.forms

### ActiveAlternateSelf
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [OneToOne]
  - alternate_self -> forms.AlternateSelf [FK] (nullable)
  - return_form -> forms.CharacterForm [FK] (nullable)
  - return_persona -> scenes.Persona [FK] (nullable)

### AlternateSelf
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - form -> forms.CharacterForm [FK] (nullable)
  - persona -> scenes.Persona [FK] (nullable)
  - combat_profile -> forms.FormCombatProfile [FK] (nullable)
  - thumbnail -> evennia_extensions.Media [FK] (nullable)
  - resonance -> magic.Resonance [FK] (nullable)
  - techniques -> magic.Technique [M2M]
**Pointed to by:**
  - active_for <- forms.ActiveAlternateSelf

### AppearanceChangeLog
**Foreign Keys:**
  - form -> forms.CharacterForm [FK]
  - persona -> scenes.Persona [FK] (nullable)
  - trait -> forms.FormTrait [FK]
  - from_option -> forms.FormTraitOption [FK] (nullable)
  - to_option -> forms.FormTraitOption [FK] (nullable)
  - actor_persona -> scenes.Persona [FK] (nullable)

### Build
**Pointed to by:**
  - drafts <- character_creation.CharacterDraft
  - character_sheets <- character_sheets.CharacterSheet

### CharacterForm
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
**Pointed to by:**
  - pull_effect_targets <- magic.ThreadPullEffect
  - values <- forms.CharacterFormValue
  - markings <- forms.FormMarking
  - active_for <- forms.CharacterFormState
  - overlay_for <- forms.CharacterFormState
  - combat_profiles <- forms.FormCombatProfile
  - alternate_self_grants <- forms.AlternateSelf
  - return_for_active <- forms.ActiveAlternateSelf
  - appearance_changes <- forms.AppearanceChangeLog

### CharacterFormState
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [OneToOne]
  - active_form -> forms.CharacterForm [FK] (nullable)
  - active_fake_overlay -> forms.CharacterForm [FK] (nullable)
  - applied_kit_instance -> items.ItemInstance [FK] (nullable)

### CharacterFormValue
**Foreign Keys:**
  - form -> forms.CharacterForm [FK]
  - trait -> forms.FormTrait [FK]
  - option -> forms.FormTraitOption [FK]
  - natural_option -> forms.FormTraitOption [FK] (nullable)
**Pointed to by:**
  - components <- forms.FormValueComponent

### CharacterKnownStyle
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - option -> forms.FormTraitOption [FK]

### FormCombatProfile
**Foreign Keys:**
  - form -> forms.CharacterForm [FK]
**Pointed to by:**
  - modifier_sources <- mechanics.ModifierSource
  - effects <- forms.FormCombatProfileEffect
  - grants <- forms.AlternateSelf

### FormCombatProfileEffect
**Foreign Keys:**
  - profile -> forms.FormCombatProfile [FK]
  - target -> mechanics.ModifierTarget [FK]

### FormMarking
**Foreign Keys:**
  - form -> forms.CharacterForm [FK]

### FormTrait
**Foreign Keys:**
  - composite_option -> forms.FormTraitOption [FK] (nullable)
**Pointed to by:**
  - kinsperson_values <- roster.KinspersonTraitValue
  - options <- forms.FormTraitOption
  - species_links <- forms.SpeciesFormTrait
  - character_values <- forms.CharacterFormValue
  - temporary_changes <- forms.TemporaryFormChange
  - persona_descriptors <- forms.PersonaTraitDescriptor
  - appearance_changes <- forms.AppearanceChangeLog
  - item_template_effects <- items.ItemTemplateAppearanceEffect
  - styling_offers <- npc_services.StylingOfferDetails

### FormTraitOption
**Foreign Keys:**
  - trait -> forms.FormTrait [FK]
**Pointed to by:**
  - kinsperson_values <- roster.KinspersonTraitValue
  - composite_for_traits <- forms.FormTrait
  - species_restrictions <- forms.SpeciesFormTrait
  - character_values <- forms.CharacterFormValue
  - natural_for_values <- forms.CharacterFormValue
  - temporary_changes <- forms.TemporaryFormChange
  - component_of_values <- forms.FormValueComponent
  - knowers <- forms.CharacterKnownStyle
  - item_template_effects <- items.ItemTemplateAppearanceEffect
  - styling_offers <- npc_services.StylingOfferDetails

### FormValueComponent
**Foreign Keys:**
  - value -> forms.CharacterFormValue [FK]
  - option -> forms.FormTraitOption [FK]

### HeightBand
**Pointed to by:**
  - drafts <- character_creation.CharacterDraft

### PersonaTraitDescriptor
**Foreign Keys:**
  - persona -> scenes.Persona [FK]
  - trait -> forms.FormTrait [FK]

### SpeciesFormTrait
**Foreign Keys:**
  - species -> species.Species [FK]
  - trait -> forms.FormTrait [FK]
  - allowed_options -> forms.FormTraitOption [M2M]

### TemporaryFormChange
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - trait -> forms.FormTrait [FK]
  - option -> forms.FormTraitOption [FK]

### Service Functions
- `apply_disguise(character: 'Any', disguise_form: 'CharacterForm', *, kind: 'DisguiseKind' = DisguiseKind.MUNDANE, concealment_level: 'ConcealmentLevel' = ConcealmentLevel.NONE, kit_instance: 'Any' = None) -> 'CharacterFormState' - Paint a fake overlay over the character's real form (#1110).`
- `assume_alternate_self(sheet: 'CharacterSheet', alt: 'AlternateSelf', instance_value: 'float' = 1.0) -> 'ActiveAlternateSelf' - Assume an alternate self — swap in form/persona facets, create the`
- `calculate_weight(height_inches: 'int', build: 'Build') -> 'int' - Calculate weight in pounds from height and build.`
- `change_appearance(character: 'Any', trait: 'FormTrait', new_option: 'FormTraitOption', *, persona: 'Persona', descriptor: 'str | None' = None, note: 'str' = '', actor_persona: 'Persona | None' = None, blend: 'bool' = False) -> 'CharacterFormValue' - Cosmetically edit one trait of the character's real form (hair dye, restyle).`
- `create_true_form(character: 'Any', selections: 'dict[FormTrait, FormTraitOption]') -> 'CharacterForm' - Create the true form for a character during character creation.`
- `get_apparent_build(character: 'Any') -> 'Build | None' - Get the apparent build for a character.`
- `get_apparent_form(character: 'Any') -> 'dict[FormTrait, FormTraitOption]' - Get the apparent form for a character, combining active form with temporaries.`
- `get_apparent_height(character: 'Any') -> 'tuple[int, HeightBand | None]' - Get the apparent height for a character including trait modifiers.`
- `get_cg_builds() -> 'QuerySet[Build]' - Get builds available in character creation.`
- `get_cg_form_options(species: 'Species') -> 'dict[FormTrait, list[FormTraitOption]]' - Get available form trait options for character creation.`
- `get_cg_height_bands() -> 'QuerySet[HeightBand]' - Get height bands available in character creation.`
- `get_height_band(height_inches: 'int') -> 'HeightBand | None' - Get the HeightBand for a given height in inches.`
- `get_presented_appearance(character: 'Any', *, pierced: 'bool' = False) -> 'list[PresentedTrait]' - Compose what a viewer sees: the presented form's normalized traits overlaid with the`
- `knows_style(character_sheet: 'Any', option: 'FormTraitOption') -> 'bool' - True when the sheet may produce ``option`` (ungated options always may).`
- `learn_style(character_sheet: 'Any', option: 'FormTraitOption', *, taught_by_label: 'str' = '') -> 'None' - Grant knowledge of an exotic option — 'learned by having it done' (#2632).`
- `remove_disguise(character: 'Any') -> 'None' - Drop the active fake overlay — the real form presents again (#1110). Idempotent.`
- `reset_trait_to_natural(character: 'Any', trait: 'FormTrait', *, persona: 'Persona', actor_persona: 'Persona | None' = None, note: 'str' = '') -> 'CharacterFormValue' - Restore one trait to its natural (origin) value — "wash out the dye.`
- `revert_alternate_self(sheet: 'CharacterSheet') -> 'None' - Revert the active alternate self — restore return anchors, delete the`
- `revert_to_true_form(character: 'Any') -> 'None' - Revert a character to their true form.`
- `switch_form(character: 'Any', target_form: 'CharacterForm') -> 'None' - Switch a character to a different form.`


## world.game_clock

### GameClock

### GameClockHistory
**Foreign Keys:**
  - changed_by -> evennia.AccountDB [FK] (nullable)

### GameSeason
**Pointed to by:**
  - weeks <- game_clock.GameWeek

### GameWeek
**Foreign Keys:**
  - season -> game_clock.GameSeason [FK]
**Pointed to by:**
  - standing_declarations <- societies.StandingDeclaration
  - social_engagement_trackers <- progression.WeeklySocialEngagement
  - random_scene_targets <- progression.RandomSceneTarget
  - development_transactions <- progression.DevelopmentTransaction
  - skill_usages <- progression.WeeklySkillUsage
  - vote_budgets <- progression.WeeklyVoteBudget
  - votes <- progression.WeeklyVote
  - technique_progress_weekly <- magic.TechniqueProgressWeekly
  - purse_drain_weeks <- currency.PurseDrainWeek
  - gm_reward_trackers <- gm.GMWeeklyRewardTracker
  - goal_journals <- goals.GoalJournal
  - journal_xp_trackers <- journals.WeeklyJournalXP
  - relationships <- relationships.CharacterRelationship
  - gambling_loss_ledgers <- tavern_games.GamblingLossLedger

### ScheduledTaskRecord

### Service Functions
- `get_ic_date_for_real_time(real_dt: datetime.datetime) -> datetime.datetime | None - Convert a real datetime to IC datetime, or None if no clock exists.`
- `get_ic_now(*, real_now: datetime.datetime | None = None) -> datetime.datetime | None - Return the current IC datetime, or None if no clock exists.`
- `get_ic_phase(*, real_now: datetime.datetime | None = None) -> world.game_clock.constants.TimePhase | None - Return the current time-of-day phase, or None if no clock exists.`
- `get_ic_season(*, real_now: datetime.datetime | None = None) -> world.game_clock.constants.Season | None - Return the current IC season, or None if no clock exists.`
- `get_light_level(*, real_now: datetime.datetime | None = None) -> float | None - Return a smooth 0.0-1.0 light level, or None if no clock exists.`
- `get_moon_illumination(*, real_now: datetime.datetime | None = None) -> float | None - Return the current 0.0-1.0 lunar illumination, or None if no clock exists.`
- `get_moon_phase(*, real_now: datetime.datetime | None = None) -> world.game_clock.constants.MoonPhase | None - Return the current lunar phase, or None if no clock exists.`
- `get_real_time_for_ic_date(ic_dt: datetime.datetime) -> datetime.datetime | None - Convert an IC datetime to real datetime, or None if no clock exists.`
- `light_level_from_ic_time(ic_now: datetime.datetime) -> float - Derive a smooth 0.0-1.0 light level from a concrete IC datetime.`
- `moon_cycle_fraction_from_ic_time(ic_now: datetime.datetime) -> float - Position in the synodic cycle for a concrete IC datetime, in [0, 1).`
- `moon_illumination_from_ic_time(ic_now: datetime.datetime) -> float - Smooth 0.0-1.0 illuminated fraction (0 = new, 1 = full).`
- `moon_phase_from_ic_time(ic_now: datetime.datetime) -> world.game_clock.constants.MoonPhase - Derive the lunar phase from a concrete IC datetime (8 centered bins).`
- `pause_clock(*, changed_by: evennia.accounts.models.AccountDB, reason: str = '') -> world.game_clock.models.GameClock - Pause the game clock, freezing IC time at its current value.`
- `phase_from_ic_time(ic_now: datetime.datetime) -> world.game_clock.constants.TimePhase - Derive the time-of-day phase from a concrete IC datetime.`
- `season_from_ic_time(ic_now: datetime.datetime) -> world.game_clock.constants.Season - Derive the IC season from a concrete IC datetime.`
- `set_clock(*, new_ic_time: datetime.datetime, changed_by: evennia.accounts.models.AccountDB, reason: str = '') -> world.game_clock.models.GameClock - Set the game clock IC time, creating it if it doesn't exist.`
- `set_time_ratio(*, ratio: float, changed_by: evennia.accounts.models.AccountDB, reason: str = '') -> world.game_clock.models.GameClock - Change the time ratio, re-anchoring IC time to preserve continuity.`
- `unpause_clock(*, changed_by: evennia.accounts.models.AccountDB, reason: str = '') -> world.game_clock.models.GameClock - Unpause the game clock, resuming IC time from where it was paused.`


## world.gm

### AreaBuildGrant
**Foreign Keys:**
  - account -> evennia.AccountDB [FK]
  - area -> areas.Area [FK]
  - granted_by -> evennia.AccountDB [FK]

### CatalogSuggestion
**Foreign Keys:**
  - submitted_by -> evennia.AccountDB [FK]
  - situation_kind -> gm.SituationKind [FK] (nullable)
  - reviewer -> evennia.AccountDB [FK] (nullable)

### CheckTypeSituationFit
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - check_type -> checks.CheckType [FK]
  - situation_kind -> gm.SituationKind [FK]

### ConsequencePoolGuide
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - situation_kind -> gm.SituationKind [FK]
  - pool -> actions.ConsequencePool [FK]

### DistinctionChangeRequestDetails
**Foreign Keys:**
  - request -> gm.TableUpdateRequest [OneToOne]
  - distinction -> distinctions.Distinction [FK] (nullable)
  - character_distinction -> distinctions.CharacterDistinction [FK] (nullable)
  - sheet_update_request -> distinctions.SheetUpdateRequest [FK] (nullable)

### GMApplication
**Foreign Keys:**
  - account -> evennia.AccountDB [FK]
  - reviewed_by -> evennia.AccountDB [FK] (nullable)

### GMLevelCap

### GMLevelChange
**Foreign Keys:**
  - profile -> gm.GMProfile [FK]
  - changed_by -> evennia.AccountDB [FK]

### GMProfile
**Foreign Keys:**
  - account -> evennia.AccountDB [OneToOne]
  - approved_by -> evennia.AccountDB [FK]
**Pointed to by:**
  - tables <- gm.GMTable
  - invites_created <- gm.GMRosterInvite
  - level_changes <- gm.GMLevelChange
  - story_areas <- gm.StoryArea
  - story_grants_issued <- gm.StoryRoomGrant
  - summon_offers_issued <- gm.GMSummonOffer
  - weekly_reward_tracker <- gm.GMWeeklyRewardTracker
  - resolved_update_requests <- gm.TableUpdateRequest
  - owned_instances <- instances.InstancedRoom
  - resolved_recycle_requests <- items.RecycleRequest
  - summonses_created <- npc_services.OfferSummons
  - active_stories <- stories.Story
  - episode_resolutions <- stories.EpisodeResolution
  - group_progress_resolved <- stories.GroupStoryProgress
  - global_progress_resolved <- stories.GlobalStoryProgress
  - character_progress_resolved <- stories.StoryProgress
  - assistant_claims_made <- stories.AssistantGMClaim
  - assistant_claims_approved <- stories.AssistantGMClaim
  - assigned_session_requests <- stories.SessionRequest
  - story_offers_received <- stories.StoryGMOffer
  - crossover_invites_sent <- stories.CrossoverInvite
  - stake_outcomes <- stories.StakeOutcome
  - custody_requests <- stories.CustodyClearance

### GMRewardConfig

### GMRosterInvite
**Foreign Keys:**
  - roster_entry -> roster.RosterEntry [FK]
  - created_by -> gm.GMProfile [FK]
  - claimed_by -> evennia.AccountDB [FK] (nullable)

### GMSummonOffer
**Foreign Keys:**
  - target_sheet -> character_sheets.CharacterSheet [FK]
  - invited_by -> gm.GMProfile [FK] (nullable)
  - room -> evennia_extensions.RoomProfile [FK]
  - scene -> scenes.Scene [FK] (nullable)

### GMTable
**Foreign Keys:**
  - gm -> gm.GMProfile [FK]
**Pointed to by:**
  - authored_roster_entries <- roster.RosterEntry
  - draft_characters <- character_creation.CharacterDraft
  - memberships <- gm.GMTableMembership
  - primary_stories <- stories.Story
  - beat_completions <- stories.BeatCompletion
  - ran_beat_completions <- stories.BeatCompletion
  - episode_resolutions <- stories.EpisodeResolution
  - story_progress <- stories.GroupStoryProgress
  - bulletin_posts <- stories.TableBulletinPost

### GMTableMembership
**Foreign Keys:**
  - table -> gm.GMTable [FK]
  - persona -> scenes.Persona [FK]
**Pointed to by:**
  - update_requests <- gm.TableUpdateRequest

### GMWeeklyRewardTracker
**Foreign Keys:**
  - gm_profile -> gm.GMProfile [OneToOne]
  - game_week -> game_clock.GameWeek [FK] (nullable)

### ProfileTextRequestDetails
**Foreign Keys:**
  - request -> gm.TableUpdateRequest [OneToOne]
  - applied_version -> character_sheets.ProfileTextVersion [FK] (nullable)

### SituationDifficultyGuide
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - situation_kind -> gm.SituationKind [FK]

### SituationKind
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
**Pointed to by:**
  - check_fits <- gm.CheckTypeSituationFit
  - difficulty_guides <- gm.SituationDifficultyGuide
  - pool_guides <- gm.ConsequencePoolGuide
  - suggestions <- gm.CatalogSuggestion

### StoryArea
**Foreign Keys:**
  - gm -> gm.GMProfile [FK]
  - area -> areas.Area [OneToOne]

### StoryRoomGrant
**Foreign Keys:**
  - room -> evennia_extensions.RoomProfile [FK]
  - character -> character_sheets.CharacterSheet [FK]
  - granted_by -> gm.GMProfile [FK]
  - return_location -> evennia_extensions.RoomProfile [FK] (nullable)

### TableUpdateRequest
**Foreign Keys:**
  - membership -> gm.GMTableMembership [FK]
  - resolved_by -> gm.GMProfile [FK] (nullable)
**Pointed to by:**
  - profile_text_details <- gm.ProfileTextRequestDetails
  - distinction_details <- gm.DistinctionChangeRequestDetails

### Service Functions
- `approve_application_as_gm(gm: 'GMProfile', application: 'RosterApplication') -> 'None' - Approve a roster application on behalf of the overseeing GM.`
- `archive_table(table: 'GMTable') -> 'None' - Mark a table archived. Sets archived_at timestamp.`
- `award_gm_story_reward(*, gm_profile: 'GMProfile', players_served: 'int', per_player_xp: 'int', event_cap: 'int', description: 'str') -> 'XPTransaction | None' - Award GM Story Reward XP to ``gm_profile.account`` (#2123).`
- `cap_for_profile(profile: 'GMProfile') -> 'GMLevelCap | None' - The ``GMLevelCap`` row for ``profile.level``, or None when unseeded.`
- `claim_invite(invite: 'GMRosterInvite', account: 'AccountDB') -> 'RosterApplication' - Mark an invite claimed and create (or reuse) a RosterApplication.`
- `create_invite(gm: 'GMProfile', roster_entry: 'RosterEntry', is_public: 'bool' = False, invited_email: 'str' = '', expires_at: 'datetime | None' = None) -> 'GMRosterInvite' - Create a GMRosterInvite. Callers must validate GM oversight.`
- `create_table(gm: 'GMProfile', name: 'str', description: 'str' = '') -> 'GMTable' - Create a new GM table owned by the given GM.`
- `deny_application_as_gm(gm: 'GMProfile', application: 'RosterApplication', review_notes: 'str' = '') -> 'None' - Deny an application on behalf of the overseeing GM.`
- `get_notification_target_for_gm(gm_profile: 'GMProfile') -> 'CharacterSheet | None' - Resolve the CharacterSheet to use as the notification recipient for a GM.`
- `gm_application_queue(gm: 'GMProfile') -> 'QuerySet[RosterApplication]' - Pending applications for characters at tables this GM owns.`
- `gm_evidence_summary(profile: 'GMProfile') -> 'GMEvidenceSummary' - Aggregate a GM's track record for staff reviewing a level change.`
- `gm_max_risk(user) -> 'str' - RenownRisk ceiling for a non-staff author: their GMLevelCap.max_beat_risk.`
- `gm_may_review_for_persona(gm_profile: 'GMProfile', persona: 'Persona') -> 'bool' - The review-pool rule (#2631 ruling): staff, or a GM with table access.`
- `has_build_warrant(account: 'AccountDB | None', *, area: 'Area', level: 'int') -> 'bool' - Whether ``account`` may build-author at ``level`` within ``area``'s subtree.`
- `has_room_budget_capacity(account: 'AccountDB | None', *, area: 'Area', rooms_needed: 'int' = 1) -> 'bool' - Whether digging ``rooms_needed`` more room(s) under ``area`` fits some`
- `idle_tables(threshold_days: 'int' = 14) -> 'QuerySet[GMTable]' - ACTIVE tables whose GM's ``last_active_at`` is older than the threshold (#2004).`
- `join_table(table: 'GMTable', persona: 'Persona') -> 'GMTableMembership' - Add a persona to a table. Idempotent — returns existing active`
- `leave_table(membership: 'GMTableMembership') -> 'None' - Soft-leave a membership. No-op if already left.`
- `offer_gm_summon(gm_profile: 'GMProfile | None', target_sheet: 'CharacterSheet', *, room: 'RoomProfile', scene: 'Scene | None' = None, gm_display_name: 'str' = '') -> 'GMSummonOffer' - Create or replace a pending GM summon offer for ``target_sheet`` (#3071).`
- `promote_gm(profile: 'GMProfile', new_level: 'str', *, changed_by: 'AccountDB', reason: 'str') -> 'GMLevelChange' - Set profile.level (promotion OR demotion), writing the audit row.`
- `resolve_gm_summon_offer(offer: 'GMSummonOffer', *, accept: 'bool') -> 'None' - Resolve a pending summon offer: move the target on accept, always clear it (#3071).`
- `revoke_invite(invite: 'GMRosterInvite') -> 'None' - Revoke an invite by setting expires_at to now.`
- `set_looking_for_table(player_data: 'PlayerData', looking: 'bool') -> 'None' - Set or clear the looking-for-table flag on a player's profile (#2431).`
- `signoff_table_update_request(request: 'TableUpdateRequest', gm_profile: 'GMProfile', *, approve: 'bool', notes: 'str' = '') -> 'TableUpdateRequest' - Approve or reject a PENDING request — the GM's yes/no judgment call (#2631).`
- `soft_leave_memberships_for_retired_persona(persona: 'Persona') -> 'int' - Future integration hook: called when a persona is retired.`
- `submit_catalog_suggestion(account: 'AccountDB', *, proposal_kind: 'str', proposal_text: 'str', situation_kind: 'SituationKind | None' = None) -> 'CatalogSuggestion' - Create a ``CatalogSuggestion`` row, routed to the staff inbox (#2127).`
- `submit_distinction_change_request(membership: 'GMTableMembership', *, action: 'str', reasoning: 'str', distinction: 'Distinction | None' = None, character_distinction: 'CharacterDistinction | None' = None) -> 'TableUpdateRequest' - Submit a distinction add/rank-up/remove for table-GM sign-off (#2631).`
- `submit_profile_text_request(membership: 'GMTableMembership', *, field: 'str', proposed_text: 'str', reasoning: 'str') -> 'TableUpdateRequest' - Submit a profile prose rewrite for the table GM's sign-off (#2631).`
- `surrender_character_story(gm: 'GMProfile', story: 'Story') -> 'None' - GM surrenders oversight of a story.`
- `touch_gm_activity(gm_profile: 'GMProfile') -> 'None' - Stamp ``GMProfile.last_active_at`` to now (#2004).`
- `transfer_ownership(table: 'GMTable', new_gm: 'GMProfile') -> 'None' - Reassign a table to a different GM. Staff-only action.`
- `withdraw_table_update_request(request: 'TableUpdateRequest') -> 'None' - Withdraw a PENDING request (player-initiated).`


## world.goals

### CharacterGoal
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - domain -> mechanics.ModifierTarget [FK]
**Pointed to by:**
  - instances <- goals.GoalInstance
  - applications <- goals.GoalApplication

### GoalApplication
**Foreign Keys:**
  - goal -> goals.CharacterGoal [FK]

### GoalInstance
**Foreign Keys:**
  - goal -> goals.CharacterGoal [FK]

### GoalJournal
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - domain -> mechanics.ModifierTarget [FK] (nullable)
  - game_week -> game_clock.GameWeek [FK] (nullable)

### GoalRevision
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [OneToOne]

### Service Functions
- `apply_goal(goal: world.goals.models.CharacterGoal, *, context: str = '') -> int - Owner-claimed goal application (#940): spend one daily use, get the bonus.`
- `get_daily_application_budget(character: 'CharacterSheet') -> int - How many goal applications this character gets per cron day.`
- `get_goal_bonus(character: 'CharacterSheet', domain: 'ModifierTarget') -> int - Get the goal bonus for a specific domain, applying percentage modifiers.`
- `get_goal_bonuses_breakdown(character: 'CharacterSheet') -> dict[str, world.goals.types.GoalBonusBreakdown] - Get breakdown of all goal bonuses for a character.`
- `get_total_goal_points(character: 'CharacterSheet') -> int - Get the total goal points available for a character to distribute.`
- `log_goal_progress(*, character: 'CharacterSheet', domain: 'ModifierTarget | None', title: str, content: str, is_public: bool = False) -> 'GoalJournal' - Create a goal-progress journal entry and grant weekly-capped XP.`
- `set_character_goals(*, character: 'CharacterSheet', goals: list['GoalInputData']) -> list[world.goals.models.CharacterGoal] - Replace a character's goal allocations, enforcing the weekly revision limit.`


## world.instances

### InstancedRoom
**Foreign Keys:**
  - room -> evennia_extensions.RoomProfile [OneToOne]
  - owner -> character_sheets.CharacterSheet [FK] (nullable)
  - gm_owner -> gm.GMProfile [FK] (nullable)
  - return_location -> evennia.ObjectDB [FK] (nullable)
**Pointed to by:**
  - captivities <- captivity.Captivity

### Service Functions
- `complete_instanced_room(room: evennia.objects.models.ObjectDB) -> None - Mark room completed, relocate occupants, delete if no history.`
- `spawn_instanced_room(name: str, description: str, owner: world.character_sheets.models.CharacterSheet | None, return_location: evennia.objects.models.ObjectDB | None, source_key: str = '', gm_owner: world.gm.models.GMProfile | None = None) -> evennia.objects.models.ObjectDB - Create a temporary instanced room, its RoomProfile, and lifecycle record.`


## world.items

### AccentArchetypeAllowance
**Foreign Keys:**
  - target -> mechanics.ModifierTarget [FK]

### AccentExclusion
**Foreign Keys:**
  - target_a -> mechanics.ModifierTarget [FK]
  - target_b -> mechanics.ModifierTarget [FK]

### AccentLevel
**Pointed to by:**
  - item_accents <- items.ItemAccent

### Adornment
**Foreign Keys:**
  - host_instance -> items.ItemInstance [FK]
  - gem_instance -> items.ItemInstance [OneToOne]
  - set_by_account -> evennia.AccountDB [FK] (nullable)

### AudacityTuning

### CachetWallet
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [OneToOne]

### CharacterRecipeKnowledge
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - recipe -> items.CraftingRecipe [FK]

### ClaimTraceStep
**Foreign Keys:**
  - claim -> items.ReclamationClaim [FK]
  - ownership_event -> items.OwnershipEvent [FK]

### CraftedItemRecipe
**Foreign Keys:**
  - item_instance -> items.ItemInstance [FK]
  - recipe -> items.CraftingRecipe [FK]
  - quality_tier -> items.QualityTier [FK]

### CraftingMaterialRequirement
**Foreign Keys:**
  - recipe -> items.CraftingRecipe [FK]
  - item_template -> items.ItemTemplate [FK] (nullable)
  - material_category -> items.MaterialCategory [FK] (nullable)
  - min_quality_tier -> items.QualityTier [FK] (nullable)

### CraftingRecipe
**Foreign Keys:**
  - check_type -> checks.CheckType [FK] (nullable)
  - skill_trait -> traits.Trait [FK] (nullable)
  - specialization -> skills.Specialization [FK] (nullable)
  - required_feature_kind -> room_features.RoomFeatureKind [FK] (nullable)
  - output_item_template -> items.ItemTemplate [FK] (nullable)
**Pointed to by:**
  - material_requirements <- items.CraftingMaterialRequirement
  - skill_caps <- items.CraftingSkillCap
  - consequence_rows <- items.CraftingRecipeConsequence
  - modifier_outcomes <- items.CraftingRecipeModifier
  - crafted_items <- items.CraftedItemRecipe
  - known_by <- items.CharacterRecipeKnowledge

### CraftingRecipeConsequence
**Foreign Keys:**
  - recipe -> items.CraftingRecipe [FK]
  - consequence -> checks.Consequence [FK]

### CraftingRecipeModifier
**Foreign Keys:**
  - recipe -> items.CraftingRecipe [FK]
  - target -> mechanics.ModifierTarget [FK]

### CraftingServiceOffer
**Foreign Keys:**
  - crafter_persona -> scenes.Persona [FK]
  - shop_room -> evennia_extensions.RoomProfile [FK]

### CraftingSkillCap
**Foreign Keys:**
  - recipe -> items.CraftingRecipe [FK]
  - max_quality_tier -> items.QualityTier [FK]

### DisguiseKitEffect
**Foreign Keys:**
  - item_template -> items.ItemTemplate [FK]

### EquippedItem
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - item_instance -> items.ItemInstance [FK]

### FacetVogueMomentum
**Foreign Keys:**
  - society -> societies.Society [FK]
  - facet -> magic.Facet [FK]

### FashionPresentation
**Foreign Keys:**
  - event -> events.Event [FK]
  - presenter -> character_sheets.CharacterSheet [FK]
  - outfit -> items.Outfit [FK] (nullable)
  - perceiving_society -> societies.Society [FK]
**Pointed to by:**
  - endorsements <- magic.PresentationEndorsement
  - showings <- items.FashionShowing

### FashionShowing
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - scene -> scenes.Scene [FK] (nullable)
  - presentation -> items.FashionPresentation [FK] (nullable)
  - statement_item -> items.ItemInstance [FK] (nullable)
  - statement_outfit -> items.Outfit [FK] (nullable)
  - statement_style -> items.Style [FK] (nullable)
  - statement_silhouette -> items.Silhouette [FK] (nullable)

### FashionStyle
**Foreign Keys:**
  - in_vogue_facets -> magic.Facet [M2M]
  - in_vogue_styles -> items.Style [M2M]
**Pointed to by:**
  - societies_current <- societies.Society
  - bonuses <- items.FashionStyleBonus
  - trendsetter_crownings <- items.Trendsetter

### FashionStyleBonus
**Foreign Keys:**
  - fashion_style -> items.FashionStyle [FK]
  - target -> mechanics.ModifierTarget [FK]

### FinishingPass
**Foreign Keys:**
  - listing -> items.WareListing [OneToOne]
  - buyer_persona -> scenes.Persona [FK]

### GarmentMitigation
**Foreign Keys:**
  - item_template -> items.ItemTemplate [FK]
  - resonance -> magic.Resonance [FK] (nullable)

### GemDetails
**Foreign Keys:**
  - item_template -> items.ItemTemplate [OneToOne]

### GemGrade

### GemInstanceDetails
**Foreign Keys:**
  - item_instance -> items.ItemInstance [OneToOne]
  - size_grade -> items.GemGrade [FK]
  - purity_grade -> items.GemGrade [FK]
  - cut_grade -> items.GemGrade [FK]

### InteractionType
**Pointed to by:**
  - templates <- items.ItemTemplate
  - template_bindings <- items.TemplateInteraction

### ItemAccent
**Foreign Keys:**
  - item_instance -> items.ItemInstance [FK]
  - target -> mechanics.ModifierTarget [FK]
  - level -> items.AccentLevel [FK]

### ItemCheckModifier
**Foreign Keys:**
  - template -> items.ItemTemplate [FK]
  - check_type -> checks.CheckType [FK]

### ItemFacet
**Foreign Keys:**
  - applied_by_account -> evennia.AccountDB [FK] (nullable)
  - attachment_quality_tier -> items.QualityTier [FK]
  - item_instance -> items.ItemInstance [FK]
  - facet -> magic.Facet [FK]
**Pointed to by:**
  - resonance_grants <- magic.ResonanceGrant

### ItemInstance
**Foreign Keys:**
  - template -> items.ItemTemplate [FK]
  - game_object -> evennia.ObjectDB [OneToOne] (nullable)
  - quality_tier -> items.QualityTier [FK] (nullable)
  - silhouette -> items.Silhouette [FK] (nullable)
  - holder_character_sheet -> character_sheets.CharacterSheet [FK] (nullable)
  - crafter_character_sheet -> character_sheets.CharacterSheet [FK] (nullable)
  - attuned_to_character_sheet -> character_sheets.CharacterSheet [FK] (nullable)
  - crafter_persona_display -> scenes.Persona [FK] (nullable)
  - designer_character_sheet -> character_sheets.CharacterSheet [FK] (nullable)
  - designer_persona_display -> scenes.Persona [FK] (nullable)
  - contained_in -> items.ItemInstance [FK] (nullable)
  - image -> evennia_extensions.Media [FK] (nullable)
  - legend_deeds -> societies.LegendEntry [M2M]
**Pointed to by:**
  - building_permit_details <- buildings.BuildingPermitDetails
  - placed_as_decoration <- buildings.RoomDecoration
  - clues_about <- clues.Clue
  - codex_entries_about <- codex.CodexEntry
  - currency_instrument <- currency.CurrencyInstrumentDetails
  - favor_token <- currency.FavorTokenDetails
  - bequests <- estates.Bequest
  - estate_claims <- estates.EstateClaim
  - catering_uses <- events.EventCatering
  - applied_disguise_overlays <- forms.CharacterFormState
  - contents <- items.ItemInstance
  - equipped_slots <- items.EquippedItem
  - room_placement <- items.RoomItem
  - ownership_events <- items.OwnershipEvent
  - recycle_requests <- items.RecycleRequest
  - item_facets <- items.ItemFacet
  - item_styles <- items.ItemStyle
  - stored_outfits <- items.Outfit
  - outfit_slots <- items.OutfitSlot
  - showcases <- items.ShowcaseState
  - statement_showings <- items.FashionShowing
  - mantle <- items.Mantle
  - crafted_recipes <- items.CraftedItemRecipe
  - accents <- items.ItemAccent
  - refinement_projects <- items.ItemRefinementDetails
  - gem_instance_details <- items.GemInstanceDetails
  - adornments <- items.Adornment
  - adorned_on <- items.Adornment
  - pending_rare_find <- items.PendingRareFind
  - ware_listing <- items.WareListing
  - market_sales <- items.MarketSale
  - vault_holding <- items.VaultHolding
  - vault_transit <- items.VaultTransit
  - org_vault_events <- items.OrgVaultEvent
  - trade_stakes <- items.TradeItemStake
  - reclamation_claims <- items.ReclamationClaim
  - crime_evidence <- justice.CrimeEvidence
  - project_contributions <- projects.Contribution
  - secrets_about <- secrets.Secret

### ItemRefinementDetails
**Foreign Keys:**
  - project -> projects.Project [OneToOne]
  - item_instance -> items.ItemInstance [FK]
  - accent_target -> mechanics.ModifierTarget [FK] (nullable)

### ItemStyle
**Foreign Keys:**
  - applied_by_account -> evennia.AccountDB [FK] (nullable)
  - attachment_quality_tier -> items.QualityTier [FK]
  - item_instance -> items.ItemInstance [FK]
  - style -> items.Style [FK]

### ItemTemplate
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - material_category -> items.MaterialCategory [FK] (nullable)
  - on_use_pool -> actions.ConsequencePool [FK] (nullable)
  - on_use_check_type -> checks.CheckType [FK] (nullable)
  - minimum_quality_tier -> items.QualityTier [FK] (nullable)
  - tied_resonance -> magic.Resonance [FK] (nullable)
  - resonance_tier -> magic.ResonanceTier [FK] (nullable)
  - image -> evennia_extensions.Media [FK] (nullable)
  - silhouette -> items.Silhouette [FK] (nullable)
  - weapon_class -> items.WeaponClass [FK] (nullable)
  - weapon_damage_type -> conditions.DamageType [FK] (nullable)
  - polish_category -> buildings.PolishCategory [FK] (nullable)
  - interactions -> items.InteractionType [M2M]
**Pointed to by:**
  - lore_effects <- buildings.MaterialLoreEffect
  - building_uses <- buildings.BuildingMaterial
  - furniture_decoration_kinds <- buildings.DecorationKind
  - clues_about <- clues.Clue
  - clue_triggers <- clues.ItemClueTrigger
  - codex_entries_about <- codex.CodexEntry
  - class_level_item_requirements <- progression.ItemRequirement
  - ritual_requirements <- magic.RitualComponentRequirement
  - technique_grants <- magic.TechniqueGrant
  - default_properties <- items.ItemTemplateProperty
  - slots <- items.TemplateSlot
  - instances <- items.ItemInstance
  - interaction_bindings <- items.TemplateInteraction
  - appearance_effects <- items.ItemTemplateAppearanceEffect
  - disguise_kit_effects <- items.DisguiseKitEffect
  - check_modifiers <- items.ItemCheckModifier
  - garment_mitigations <- items.GarmentMitigation
  - gem_details <- items.GemDetails
  - stock_listings <- items.StockListing
  - secrets_about <- secrets.Secret

### ItemTemplateAppearanceEffect
**Foreign Keys:**
  - item_template -> items.ItemTemplate [FK]
  - trait -> forms.FormTrait [FK]
  - target_option -> forms.FormTraitOption [FK] (nullable)

### ItemTemplateProperty
**Foreign Keys:**
  - item_template -> items.ItemTemplate [FK]
  - property -> mechanics.Property [FK]

### LabStationDetails
**Foreign Keys:**
  - feature_instance -> room_features.RoomFeatureInstance [OneToOne]

### Mantle
**Foreign Keys:**
  - item_instance -> items.ItemInstance [OneToOne]
**Pointed to by:**
  - anchored_threads <- magic.Thread
  - level_defs <- items.MantleLevelDefinition
  - clearances <- items.MantleLevelClearance

### MantleLevelClearance
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - mantle -> items.Mantle [FK]

### MantleLevelDefinition
**Foreign Keys:**
  - mantle -> items.Mantle [FK]
  - codex_entry_required -> codex.CodexEntry [FK]

### MarketSale
**Foreign Keys:**
  - buyer_persona -> scenes.Persona [FK] (nullable)
  - seller_persona -> scenes.Persona [FK] (nullable)
  - item_instance -> items.ItemInstance [FK] (nullable)

### MarketSquare
**Foreign Keys:**
  - area -> areas.Area [FK]
  - realm -> realms.Realm [FK] (nullable)
**Pointed to by:**
  - stalls <- items.MarketStall

### MarketStall
**Foreign Keys:**
  - square -> items.MarketSquare [FK]
  - owner_persona -> scenes.Persona [FK] (nullable)
  - shopkeeper_persona -> scenes.Persona [FK] (nullable)
  - host_org -> societies.Organization [FK] (nullable)
**Pointed to by:**
  - stock_listings <- items.StockListing
  - ware_listings <- items.WareListing

### MaterialBucket
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - material_category -> items.MaterialCategory [FK]

### MaterialCategory
**Pointed to by:**
  - templates <- items.ItemTemplate
  - material_buckets <- items.MaterialBucket

### OrgMaterialStock
**Foreign Keys:**
  - organization -> societies.Organization [FK]
  - material_category -> items.MaterialCategory [FK]

### OrgVaultEvent
**Foreign Keys:**
  - vault -> items.OrganizationVault [FK]
  - item_instance -> items.ItemInstance [FK] (nullable)
  - actor_persona -> scenes.Persona [FK] (nullable)

### OrganizationVault
**Foreign Keys:**
  - organization -> societies.Organization [OneToOne]
**Pointed to by:**
  - holdings <- items.VaultHolding
  - transits <- items.VaultTransit
  - events <- items.OrgVaultEvent

### Outfit
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - wardrobe -> items.ItemInstance [FK]
**Pointed to by:**
  - slots <- items.OutfitSlot
  - presentations <- items.FashionPresentation
  - showcases <- items.ShowcaseState
  - statement_showings <- items.FashionShowing

### OutfitSlot
**Foreign Keys:**
  - outfit -> items.Outfit [FK]
  - item_instance -> items.ItemInstance [FK]

### OwnershipEvent
**Foreign Keys:**
  - item_instance -> items.ItemInstance [FK] (nullable)
  - from_character_sheet -> character_sheets.CharacterSheet [FK] (nullable)
  - to_character_sheet -> character_sheets.CharacterSheet [FK] (nullable)
  - from_persona_display -> scenes.Persona [FK] (nullable)
  - to_persona_display -> scenes.Persona [FK] (nullable)
**Pointed to by:**
  - trace_steps <- items.ClaimTraceStep

### PendingRareFind
**Foreign Keys:**
  - income_stream -> currency.OrgIncomeStream [FK]
  - gem_instance -> items.ItemInstance [OneToOne]

### QualityTier
**Pointed to by:**
  - minimum_for_templates <- items.ItemTemplate
  - item_instances <- items.ItemInstance
  - itemfacet_attachments <- items.ItemFacet
  - itemstyle_attachments <- items.ItemStyle
  - crafted_item_recipes <- items.CraftedItemRecipe

### ReclamationClaim
**Foreign Keys:**
  - item_instance -> items.ItemInstance [FK]
  - claimant_sheet -> character_sheets.CharacterSheet [FK]
  - original_claimant_sheet -> character_sheets.CharacterSheet [FK]
  - estate_claim -> estates.EstateClaim [FK] (nullable)
  - acquired_from -> items.ReclamationClaim [FK] (nullable)
**Pointed to by:**
  - assignments <- items.ReclamationClaim
  - trace_steps <- items.ClaimTraceStep

### RecycleRequest
**Foreign Keys:**
  - item_instance -> items.ItemInstance [FK]
  - requested_by -> character_sheets.CharacterSheet [FK]
  - resolved_by -> gm.GMProfile [FK] (nullable)

### RoomItem
**Foreign Keys:**
  - room -> evennia_extensions.RoomProfile [FK]
  - item_instance -> items.ItemInstance [OneToOne]

### ShowcaseState
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [OneToOne]
  - outfit -> items.Outfit [FK] (nullable)
  - item -> items.ItemInstance [FK] (nullable)

### Silhouette
**Foreign Keys:**
  - parent -> items.Silhouette [FK] (nullable)
**Pointed to by:**
  - templates <- items.ItemTemplate
  - instances <- items.ItemInstance
  - statement_showings <- items.FashionShowing
  - vogue_momentum <- items.SilhouetteVogueMomentum
  - children <- items.Silhouette

### SilhouetteVogueMomentum
**Foreign Keys:**
  - silhouette -> items.Silhouette [OneToOne]

### StockListing
**Foreign Keys:**
  - stall -> items.MarketStall [FK]
  - template -> items.ItemTemplate [FK]

### StreamMaterialPool
**Foreign Keys:**
  - income_stream -> currency.OrgIncomeStream [FK]
  - material_category -> items.MaterialCategory [FK]

### Style
**Foreign Keys:**
  - founder -> scenes.Persona [FK] (nullable)
  - axis_lean -> mechanics.ModifierTarget [FK] (nullable)
**Pointed to by:**
  - motif_usages <- magic.MotifResonanceStyle
  - item_attachments <- items.ItemStyle
  - vogue_in <- items.FashionStyle
  - statement_showings <- items.FashionShowing
  - vogue_momentum_row <- items.StyleVogueMomentum

### StyleVogueMomentum
**Foreign Keys:**
  - style -> items.Style [OneToOne]

### TemplateInteraction
**Foreign Keys:**
  - template -> items.ItemTemplate [FK]
  - interaction_type -> items.InteractionType [FK]

### TemplateSlot
**Foreign Keys:**
  - template -> items.ItemTemplate [FK]

### TradeItemStake
**Foreign Keys:**
  - session -> items.TradeSession [FK]
  - offered_by_sheet -> character_sheets.CharacterSheet [FK]
  - item_instance -> items.ItemInstance [FK]

### TradeSession
**Foreign Keys:**
  - initiator_sheet -> character_sheets.CharacterSheet [FK]
  - counterparty_sheet -> character_sheets.CharacterSheet [FK]
**Pointed to by:**
  - item_stakes <- items.TradeItemStake

### Trendsetter
**Foreign Keys:**
  - society -> societies.Society [FK]
  - persona -> scenes.Persona [FK]
  - fashion_style -> items.FashionStyle [FK]

### VaultHolding
**Foreign Keys:**
  - vault -> items.OrganizationVault [FK]
  - item_instance -> items.ItemInstance [OneToOne]
  - deposited_by -> scenes.Persona [FK] (nullable)

### VaultTransit
**Foreign Keys:**
  - vault -> items.OrganizationVault [FK]
  - item_instance -> items.ItemInstance [OneToOne]
  - carrier_character_sheet -> character_sheets.CharacterSheet [FK]

### WareListing
**Foreign Keys:**
  - stall -> items.MarketStall [FK]
  - item_instance -> items.ItemInstance [OneToOne]
  - seller_persona -> scenes.Persona [FK]
**Pointed to by:**
  - finishing_pass <- items.FinishingPass

### WeaponClass
**Pointed to by:**
  - item_templates <- items.ItemTemplate

### Service Functions
- `attach_facet_to_item(*, crafter: 'AccountDB', item_instance: 'ItemInstance', facet: 'Facet', attachment_quality_tier: 'QualityTier') -> 'ItemFacet' - Attach ``facet`` to ``item_instance``.`
- `consume_item_charges(*, item_instance: 'ItemInstance', amount: 'int' = 1) -> 'ItemInstance' - Spend ``amount`` charges atomically (row-locked). Logs ACTIVATED; at 0`
- `equip_item(*, character_sheet: 'object', item_instance: 'ItemInstance', body_region: 'str', equipment_layer: 'str') -> 'EquippedItem' - Place ``item_instance`` on ``character_sheet``'s slot.`
- `get_max_cleared_mantle_level(sheet: 'CharacterSheet', mantle: 'Mantle') -> 'int' - Return the highest cleared level for (sheet, mantle), or 0 if none.`
- `grant_mantle_clearance(sheet: 'CharacterSheet', mantle: 'Mantle', level: 'int') -> 'MantleLevelClearance' - Staff override: record a clearance at ``level`` without the codex check.`
- `record_mantle_clearances(sheet: 'CharacterSheet', mantle: 'Mantle') -> 'list[MantleLevelClearance]' - Idempotently record codex-gated mantle clearances for ``sheet``.`
- `remove_facet_from_item(*, item_facet: 'ItemFacet') -> 'None' - Remove a facet attachment and invalidate wearers' handler caches.`
- `unequip_item(*, equipped_item: 'EquippedItem') -> 'None' - Remove an EquippedItem and invalidate the character's handler cache.`
- `use_item(*, item_instance: 'ItemInstance', user: 'ObjectDB', target: 'ObjectDB | None' = None, descriptor: 'str | None' = None, option_id: 'int | None' = None, blend: 'bool' = False) -> 'UseItemResult' - Use an item with an on-use pool: apply its effects (deterministic when the`
- `visible_worn_items_for(character: 'ObjectDB', observer: 'object | None' = None) -> 'list[VisibleWornItem]' - Return ``character``'s worn items visible to ``observer``.`


## world.journals

### JournalBequestGrant
**Foreign Keys:**
  - recipient_sheet -> character_sheets.CharacterSheet [FK]
  - deceased_sheet -> character_sheets.CharacterSheet [FK]
  - created_by_settlement -> estates.EstateSettlement [FK]

### JournalEntry
**Foreign Keys:**
  - author -> character_sheets.CharacterSheet [FK]
  - parent -> journals.JournalEntry [FK] (nullable)
  - revealed_by_settlement -> estates.EstateSettlement [FK] (nullable)
  - related_threads -> magic.Thread [M2M]
**Pointed to by:**
  - legend_honors <- societies.LegendHonor
  - responses <- journals.JournalEntry
  - tags <- journals.JournalTag

### JournalTag
**Foreign Keys:**
  - entry -> journals.JournalEntry [FK]

### WeeklyJournalXP
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [OneToOne]
  - game_week -> game_clock.GameWeek [FK] (nullable)

### Service Functions
- `award_xp(account: 'AccountDB', amount: 'int', reason: 'str' = ProgressionReason.SYSTEM_AWARD, description: 'str' = '', gm: 'AccountDB | None' = None) -> 'XPTransaction' - Award XP to an account.`
- `base_entries_queryset() -> 'QuerySet[JournalEntry]' - The annotated/prefetched base queryset every list-style journal read builds on.`
- `create_journal_entry(*, author: 'CharacterSheet', title: 'str', body: 'str', is_public: 'bool', tags: 'list[str] | None' = None, posthumous_override: 'str' = PosthumousOverride.INHERIT, award_weekly_xp: 'bool' = True) -> 'JournalEntry' - Create a journal entry, optionally awarding weekly XP.`
- `create_journal_response(*, author: 'CharacterSheet', parent: 'JournalEntry', response_type: 'ResponseType', title: 'str', body: 'str') -> 'JournalEntry' - Create a praise or retort response to a journal entry.`
- `edit_journal_entry(*, entry: 'JournalEntry', title: 'str | None' = None, body: 'str | None' = None, posthumous_override: 'str | None' = None) -> 'JournalEntry' - Edit an existing journal entry. Sets edited_at timestamp for title/body edits.`
- `entry_visible_via_bequest(entry: 'JournalEntry', viewer_sheet: 'CharacterSheet | None') -> 'bool' - Whether ``viewer_sheet`` may read ``entry`` under a bequest grant (retrieve path).`
- `exclude_blocked_and_muted_authors(queryset: 'QuerySet[JournalEntry]', *, viewer_account: 'Any') -> 'QuerySet[JournalEntry]' - Exclude blocked/muted authors' entries from a journal feed queryset (#2996 Decision 2).`
- `grant_journal_bequest(*, recipient_sheet: 'CharacterSheet', deceased_sheet: 'CharacterSheet', settlement: 'EstateSettlement') -> 'JournalBequestGrant' - Grant read access to a deceased sheet's non-sealed private entries (#3287 Decision 3).`
- `has_journal_bequest_grant(*, recipient_sheet: 'CharacterSheet', deceased_sheet_id: 'int') -> 'bool' - Whether ``recipient_sheet`` holds a bequest grant over ``deceased_sheet_id``'s writings.`
- `increment_stat(character_sheet: 'CharacterSheet', stat: 'StatDefinition', amount: 'int' = 1) -> 'int' - Increment a stat tracker (create if needed) and check for achievements.`
- `player_for_sheet(sheet: 'CharacterSheet') -> 'PlayerData | None' - The PlayerData currently playing this character sheet, or None (#2996).`
- `reveal_journals_for_settlement(sheet: 'CharacterSheet', settlement: 'EstateSettlement') -> 'int' - Stamp ``revealed_at``/``revealed_by_settlement`` on the sheet's REVEAL-effective`
- `sealed_effective_q() -> 'Q' - A ``Q`` matching ``JournalEntry`` rows whose EFFECTIVE posthumous disposition is SEAL.`
- `set_sheet_posthumous_disposition(*, sheet: 'CharacterSheet', disposition: 'str') -> 'CharacterSheet' - Set a character's sheet-level default posthumous journal disposition (#3287).`


## world.justice

### AccusationCrimeClaim
**Foreign Keys:**
  - secret -> secrets.Secret [OneToOne]
  - crime_kind -> justice.CrimeKind [FK]
  - real_deed -> societies.LegendEntry [FK] (nullable)

### AccusationNullification
**Foreign Keys:**
  - secret -> secrets.Secret [OneToOne]
  - authorship_secret -> secrets.Secret [OneToOne] (nullable)

### AreaLaw
**Foreign Keys:**
  - area -> areas.Area [FK]
  - crime_kind -> justice.CrimeKind [FK]

### CrimeEvidence
**Foreign Keys:**
  - deed -> societies.LegendEntry [OneToOne]
  - room_profile -> evennia_extensions.RoomProfile [FK]
  - item_instance -> items.ItemInstance [OneToOne] (nullable)
**Pointed to by:**
  - frame_jobs <- justice.FrameJobDetails

### CrimeKind
**Pointed to by:**
  - laws <- justice.AreaLaw
  - deed_tags <- justice.DeedCrimeTag
  - accusation_claims <- justice.AccusationCrimeClaim
  - frame_jobs <- justice.FrameJobDetails

### DeedCrimeTag
**Foreign Keys:**
  - deed -> societies.LegendEntry [FK]
  - crime_kind -> justice.CrimeKind [FK]

### DenounceRecord
**Foreign Keys:**
  - authorship_secret -> secrets.Secret [FK]
  - denouncer_sheet -> character_sheets.CharacterSheet [FK]

### ExculpatoryEvidence
**Foreign Keys:**
  - case -> justice.JusticeCase [FK]
  - submitter_persona -> scenes.Persona [FK]

### ExileDecree
**Foreign Keys:**
  - case -> justice.JusticeCase [FK] (nullable)
  - persona -> scenes.Persona [FK]
  - area -> areas.Area [FK]
  - society -> societies.Society [FK]

### FrameJobDetails
**Foreign Keys:**
  - project -> projects.Project [OneToOne]
  - evidence -> justice.CrimeEvidence [FK]
  - subject_sheet -> character_sheets.CharacterSheet [FK]
  - crime_kind -> justice.CrimeKind [FK]

### GuardEncounter
**Foreign Keys:**
  - persona -> scenes.Persona [FK]
  - area -> areas.Area [FK]

### HeatSource
**Foreign Keys:**
  - heat -> justice.PersonaHeat [FK]
  - deed -> societies.LegendEntry [FK] (nullable)

### JusticeCase
**Foreign Keys:**
  - persona -> scenes.Persona [FK]
  - area -> areas.Area [FK]
  - society -> societies.Society [FK]
  - captivity -> captivity.Captivity [FK] (nullable)
**Pointed to by:**
  - exculpatory_evidence <- justice.ExculpatoryEvidence
  - exile_decrees <- justice.ExileDecree

### LieLowState
**Foreign Keys:**
  - persona -> scenes.Persona [FK]
  - area -> areas.Area [FK]

### PardonGrant
**Foreign Keys:**
  - granter_persona -> scenes.Persona [FK]
  - target_persona -> scenes.Persona [FK]
  - area -> areas.Area [FK]
  - society -> societies.Society [FK]

### PersonaHeat
**Foreign Keys:**
  - persona -> scenes.Persona [FK]
  - area -> areas.Area [FK]
  - society -> societies.Society [FK]
**Pointed to by:**
  - sources <- justice.HeatSource

### SentenceLadderRung
**Foreign Keys:**
  - society -> societies.Society [FK]

### Service Functions
- `accrue_accusation_heat(*, secret: 'Secret', area: 'Area | None', scale: 'int' = 1) -> 'PersonaHeat | None' - Mint pursuit heat on an accusation's subject, where the allegation landed.`
- `accrue_for_deed_knowledge(*, deed: 'LegendEntry', room: 'ObjectDB', new_knower_count: 'int') -> 'None' - The deed-knowledge accrual writer: word landed at ``room`` for ``new_knower_count`` ears.`
- `accrue_heat(*, persona: 'Persona', crime_kind: 'CrimeKind', area: 'Area | None', deed: 'LegendEntry | None' = None, scale: 'int' = 1) -> 'PersonaHeat | None' - Mint pursuit heat for ``persona`` at ``area``, if the act is criminal there.`
- `area_for_room(room: 'ObjectDB') -> 'Area | None'`
- `associate_heat(*, from_persona: 'Persona', to_persona: 'Persona') -> 'int' - Re-apply one persona's heat onto another — the outing/identification seam.`
- `enforcing_society_for(area: 'Area | None') -> 'Society | None' - Nearest ``dominant_society`` walking up from ``area`` (self first).`
- `file_criminal_accusation(*, accuser_persona: 'Persona', subject_sheet: 'CharacterSheet', content: 'str', crime_kind: 'CrimeKind', level: 'int' = SecretLevel.WHISPERS, real_deed: 'LegendEntry | None' = None, area: 'Area | None' = None, scale: 'int' = 1) -> 'Secret' - Author a criminal accusation and land its heat in one move.`
- `heat_decay_tick() -> 'int' - Daily tick: decay every heat row toward zero and drop the cold ones.`
- `heat_for(persona: 'Persona', room: 'ObjectDB', *, include_sources: 'bool' = False) -> 'HeatReading' - The pursuit picture for ``persona`` standing in ``room`` — the one read seam.`
- `law_for(area: 'Area | None', crime_kind: 'CrimeKind') -> 'AreaLaw | None' - The law governing ``crime_kind`` at ``area`` — most-specific-wins.`
- `record_accusation_crime(*, secret: 'Secret', crime_kind: 'CrimeKind', real_deed: 'LegendEntry | None' = None) -> 'AccusationCrimeClaim' - Attach the alleged crime to an accusation secret — the heat bridge's data.`
- `tag_deed_crimes(deed: 'LegendEntry', crime_kinds: 'Iterable[CrimeKind]') -> 'int' - Idempotently mark ``deed`` as an instance of each crime kind; returns rows created.`
- `tier_for_value(value: int) -> world.justice.constants.HeatTier - Map a summed heat value onto its display tier.`


## world.locations

### LocationOwnership
**Foreign Keys:**
  - area -> areas.Area [FK] (nullable)
  - room_profile -> evennia_extensions.RoomProfile [FK] (nullable)
  - holder_persona -> scenes.Persona [FK] (nullable)
  - holder_organization -> societies.Organization [FK] (nullable)

### LocationTenancy
**Foreign Keys:**
  - area -> areas.Area [FK] (nullable)
  - room_profile -> evennia_extensions.RoomProfile [FK] (nullable)
  - tenant_persona -> scenes.Persona [FK] (nullable)
  - tenant_organization -> societies.Organization [FK] (nullable)

### LocationValueModifier
**Foreign Keys:**
  - area -> areas.Area [FK] (nullable)
  - room_profile -> evennia_extensions.RoomProfile [FK] (nullable)
  - resonance -> magic.Resonance [FK] (nullable)
  - damage_type -> conditions.DamageType [FK] (nullable)

### LocationValueOverride
**Foreign Keys:**
  - area -> areas.Area [FK] (nullable)
  - room_profile -> evennia_extensions.RoomProfile [FK] (nullable)
  - resonance -> magic.Resonance [FK] (nullable)
  - damage_type -> conditions.DamageType [FK] (nullable)

### Service Functions
- `ap_regen_multiplier_pct(level: 'int') -> 'int' - The AP-regen percentage adjustment for a comfort level (#1514) — 0 at neutral (5).`
- `area_stat_total(area: 'Area | None', stat_key: 'str') -> 'int' - Summed area-level modifier rows for *stat_key* on *area* + ancestors (#2862).`
- `assign_room_tenant(*, persona: 'Persona', room: 'DefaultObject', tenant_persona: 'Persona', ends_at: 'datetime | None' = None, notes: 'str' = '') -> 'LocationTenancy' - Owner-gated grant of a room tenancy (#670) — the player seam over grant_tenancy.`
- `cleanup_decayed_modifiers(now: 'datetime | None' = None) -> 'int' - Delete LocationValueModifier rows whose current_value() has`
- `climate_exposure_base(climate: 'Climate | None', stat_key: 'StatKey', *, temperature_shift: 'int' = 0) -> 'int' - A climate's contribution to one exposure axis, before local modifiers/floor (#1522).`
- `comfort_level(room: 'DefaultObject', *, comfort_offset: 'int' = 0) -> 'int' - A room's comfort level (1–10) for an occupant (#1514).`
- `comfort_level_for_points(points: 'int') -> 'int' - Map raw comfort points to a 1–10 comfort level (#1514).`
- `comfort_points(room: 'DefaultObject') -> 'int' - A room's raw comfort points (#1514): ``amenities − felt discomfort``.`
- `comfort_summary(room: 'DefaultObject') -> 'ComfortSummary' - Resolve a room's comfort readout (#1514): level, points, the biting exposures, amenity.`
- `current_temperature_shift(*, real_now: 'datetime | None' = None) -> 'int' - The current global seasonal temperature shift from the IC clock (#1522).`
- `current_tenants(room: 'DefaultObject') -> 'QuerySet[LocationTenancy]' - Return all currently-active tenancies that apply to a room.`
- `effective_enclosure_for_room(room_obj: 'ObjectDB') -> 'RoomEnclosure' - Return the room's effective enclosure, treating open windows as a breach.`
- `effective_owner(room: 'DefaultObject') -> 'LocationOwnership | None' - Cascade-resolve the most-specific active owner of a room.`
- `effective_owners_for_rooms(rooms: 'Iterable[DefaultObject]') -> 'dict[int, LocationOwnership | None]' - Bulk-resolve owners for many rooms in one pass.`
- `effective_stats_for_rooms(rooms: 'Iterable[DefaultObject]', stat_keys: 'Iterable[StatKey]') -> 'dict[int, dict[StatKey, int]]' - Bulk-resolve stats for many rooms in one pass.`
- `effective_value(room: 'DefaultObject', *, stat_key: 'StatKey | None' = None, resonance: 'Resonance | None' = None, damage_type: 'DamageType | None' = None) -> 'int' - Cascade-resolve a single axis value (stat, resonance, or damage-type shelter) for a room.`
- `effective_values_for_rooms(rooms: 'Iterable[DefaultObject]', *, stat_keys: 'Iterable[StatKey] | None' = None, resonances: 'Iterable[Resonance] | None' = None) -> 'dict[int, dict[StatKey | Resonance, int]]' - Bulk-resolve cascade values across many rooms for one axis.`
- `end_room_tenancy(*, persona: 'Persona', tenancy: 'LocationTenancy') -> 'LocationTenancy' - End a room tenancy (#670): the room's owner (eviction) or the tenant (departure).`
- `end_tenancy(tenancy: 'LocationTenancy', *, ended_at: 'datetime | None' = None) -> 'LocationTenancy' - End a tenancy by setting ``ends_at``.`
- `felt_exposure(room: 'DefaultObject', *, stat_key: 'StatKey') -> 'int' - A room's *felt* exposure on one axis, after enclosure sheltering (#1514, #1522).`
- `get_effective_climate(area: 'Area | None') -> 'Climate | None' - Walk up the area hierarchy to the nearest climate assignment (#1522).`
- `grant_tenancy(*, area: 'Area | None' = None, room_profile: 'RoomProfile | None' = None, tenant_persona: 'Persona | None' = None, tenant_organization: 'Organization | None' = None, ends_at: 'datetime | None' = None, notes: 'str' = '') -> 'LocationTenancy' - Create a new LocationTenancy row.`
- `hazard_is_covered(room: 'DefaultObject', damage_type: 'DamageType', *, threshold: 'int' = 1) -> 'bool' - Whether *room* grants shelter against *damage_type* (#1744).`
- `hazard_is_covered_for(character: 'DefaultObject', room: 'DefaultObject | None', damage_type: 'DamageType', *, threshold: 'int' = 1) -> 'bool' - Whether *character* in *room* is sheltered against *damage_type*.`
- `is_owner(persona: 'Persona', room: 'DefaultObject') -> 'bool' - True when ``ownership_for(persona, room)`` returns a row.`
- `is_tenant(persona: 'Persona', room: 'DefaultObject') -> 'bool' - True when ``tenancies_for(persona, room)`` has any rows.`
- `maybe_default_residence(persona: 'Persona | None', room_profile: 'RoomProfile | None') -> 'None' - Default a persona's character home to this room when it has none yet (#1514, #2036).`
- `ownership_for(persona: 'Persona', room: 'DefaultObject') -> 'LocationOwnership | None' - Return the LocationOwnership row that gives this persona standing`
- `ownership_history_for(*, area: 'Area | None' = None, room_profile: 'RoomProfile | None' = None) -> 'QuerySet[LocationOwnership]' - Return ALL LocationOwnership rows (active and ended) for a`
- `resolve_area_art(room_profile: 'RoomProfile | None', *, thumbnail_url: 'object' = <object object>) -> 'str | None' - The room's effective art URL (#3477): thumbnail-first, then area cascade.`
- `room_discomfort(room: 'DefaultObject') -> 'int' - Total residual environmental discomfort at a room (#1514, #1522).`
- `room_enclosure(room: 'DefaultObject') -> 'RoomEnclosure' - The room's enclosure level (#1514); ``WALLED`` (a normal indoor room) if no profile.`
- `room_exposure_breakdown(room: 'DefaultObject') -> 'list[AxisBreakdown]' - Per-axis pressure/mitigation/net for a room — the build-HUD's engine (#1514).`
- `set_primary_home(*, persona: 'Persona', room: 'DefaultObject', notes: 'str' = '') -> 'LocationTenancy' - Designate one of the persona's active room tenancies as their home (#670, #2036).`
- `set_residence(*, character: 'DefaultObject', room: 'DefaultObject') -> 'None' - Set a character's primary residence (#1514).`
- `set_room_display_data(*, room: 'DefaultObject', persona: 'Persona | None' = None, name: 'str | None' = None, description: 'str | None' = None, is_public: 'bool | None' = None, bypass_ownership: 'bool' = False) -> 'None' - Owner-or-tenant-gated edit of a room's display name, description, and public listing.`
- `set_room_stat_modifier(room_profile: 'RoomProfile', stat_key: 'StatKey', *, source: 'str', value: 'int') -> 'LocationValueModifier | None' - Set the room-level ``(room_profile, stat_key, source)`` cascade row to ``value``.`
- `tenancies_for(persona: 'Persona', room: 'DefaultObject') -> 'QuerySet[LocationTenancy]' - Return the QuerySet of currently-active tenancies that give this`
- `tenancies_for_rooms(rooms: 'Iterable[DefaultObject]') -> 'dict[int, list[LocationTenancy]]' - Bulk-resolve currently-active tenancies for many rooms.`
- `tenancy_history_for(*, area: 'Area | None' = None, room_profile: 'RoomProfile | None' = None) -> 'QuerySet[LocationTenancy]' - Return ALL LocationTenancy rows (active and ended) for a`
- `transfer_ownership(*, area: 'Area | None' = None, room_profile: 'RoomProfile | None' = None, to_persona: 'Persona | None' = None, to_organization: 'Organization | None' = None, notes: 'str' = '', transferred_at: 'datetime | None' = None) -> 'LocationOwnership' - Atomically transfer (or claim) ownership of a location.`
- `upsert_room_resonance_modifier(room_profile: 'RoomProfile', resonance: 'Resonance', *, source: 'str', delta: 'int') -> 'LocationValueModifier' - Get-or-create the room-level (room_profile, resonance, source) cascade row and`


## world.magic

### Affinity
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
**Pointed to by:**
  - modifier_target <- mechanics.ModifierTarget
  - resonances <- magic.Resonance
  - alteration_templates <- magic.MagicalAlterationTemplate
  - pending_alteration_origins <- magic.PendingAlteration
  - glimpse_tags <- magic.GlimpseTag
  - interactions_as_source <- magic.AffinityInteraction
  - interactions_as_environment <- magic.AffinityInteraction

### AffinityInteraction
**Foreign Keys:**
  - source_affinity -> magic.Affinity [FK]
  - environment_affinity -> magic.Affinity [FK]
  - consequence_pool -> actions.ConsequencePool [FK] (nullable)
**Pointed to by:**
  - alignment_boon_tiers <- magic.ResonanceAlignmentBoonTier

### AnimaConfig

### AnimaRitualBudgetAward
**Foreign Keys:**
  - outcome_tier -> traits.CheckOutcome [OneToOne]

### AnimaRitualPerformance
**Foreign Keys:**
  - ritual -> magic.Ritual [FK]
  - target_character -> character_sheets.CharacterSheet [FK] (nullable)
  - scene -> scenes.Scene [FK] (nullable)
  - outcome -> traits.CheckOutcome [FK] (nullable)

### AppetiteUpkeep
**Foreign Keys:**
  - distinction -> distinctions.Distinction [OneToOne]
**Pointed to by:**
  - receipts <- magic.AppetiteUpkeepReceipt

### AppetiteUpkeepReceipt
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - upkeep -> magic.AppetiteUpkeep [FK]

### AudereMajoraCrossing
**Foreign Keys:**
  - scene -> scenes.Scene [FK] (nullable)
  - declaration_interaction -> scenes.Interaction [FK] (nullable)
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - threshold -> magic.AudereMajoraThreshold [FK]
  - chosen_path -> classes.Path [FK]
  - legend_entry -> societies.LegendEntry [OneToOne] (nullable)

### AudereMajoraFaithVariant
**Foreign Keys:**
  - threshold -> magic.AudereMajoraThreshold [FK]
  - being -> worship.WorshippedBeing [FK]
**Pointed to by:**
  - pending_offers <- magic.PendingAudereMajoraOffer
  - condition_applications <- magic.AudereMajoraFaithVariantAppliedCondition

### AudereMajoraFaithVariantAppliedCondition
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK]
  - faith_variant -> magic.AudereMajoraFaithVariant [FK]

### AudereMajoraThreshold
**Foreign Keys:**
  - minimum_intensity_tier -> magic.IntensityTier [FK]
  - minimum_warp_stage -> conditions.ConditionStage [FK]
  - archetypes -> societies.PhilosophicalArchetype [M2M]
**Pointed to by:**
  - pending_offers <- magic.PendingAudereMajoraOffer
  - crossings <- magic.AudereMajoraCrossing
  - faith_variants <- magic.AudereMajoraFaithVariant

### AudereThreshold
**Foreign Keys:**
  - minimum_intensity_tier -> magic.IntensityTier [FK]
  - minimum_warp_stage -> conditions.ConditionStage [FK]

### AuraAffinityThreshold
**Foreign Keys:**
  - discovery_achievement -> achievements.Achievement [FK] (nullable)

### AuraPowerConfig

### BeginningsRitualGrant
**Foreign Keys:**
  - beginnings -> character_creation.Beginnings [FK]
  - ritual -> magic.Ritual [FK]

### CapabilityPowerConfig

### CharacterAnima
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [OneToOne]

### CharacterAura
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [OneToOne]
**Pointed to by:**
  - glimpse_tags <- magic.CharacterGlimpseTag
  - glimpse_born_distinctions <- distinctions.CharacterDistinction

### CharacterGift
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - gift -> magic.Gift [FK]

### CharacterGiftUnlock
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - unlock -> magic.GiftUnlock [FK]
  - teacher -> roster.RosterTenure [FK] (nullable)

### CharacterGlimpseTag
**Foreign Keys:**
  - aura -> magic.CharacterAura [FK]
  - tag -> magic.GlimpseTag [FK]

### CharacterResonance
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - resonance -> magic.Resonance [FK]

### CharacterRitualKnowledge
**Foreign Keys:**
  - roster_entry -> roster.RosterEntry [FK]
  - ritual -> magic.Ritual [FK]
  - learned_from -> roster.RosterTenure [FK] (nullable)

### CharacterTechnique
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - technique -> magic.Technique [FK]
  - source -> mechanics.ModifierSource [FK] (nullable)
  - role_source -> covenants.CharacterCovenantRole [FK] (nullable)

### CharacterThreadWeavingUnlock
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - unlock -> magic.ThreadWeavingUnlock [FK]
  - teacher -> roster.RosterTenure [FK] (nullable)

### CharacterTradition
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - tradition -> magic.Tradition [FK]

### CodexEntryRitualGrant
**Foreign Keys:**
  - codex_entry -> codex.CodexEntry [FK]
  - ritual -> magic.Ritual [FK]

### CompromiseActType
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - target_resonance -> magic.Resonance [FK]

### CorruptionConfig
**Foreign Keys:**
  - updated_by -> evennia.AccountDB [FK] (nullable)

### CovenantRoleBlendConfig

### CrossingChoice
**Foreign Keys:**
  - thread -> magic.Thread [FK]
  - option -> magic.CrossingOption [FK]

### CrossingOption
**Foreign Keys:**
  - resonance -> magic.Resonance [FK]
  - condition_template -> conditions.ConditionTemplate [FK]
  - discovery_achievement -> achievements.Achievement [FK] (nullable)
  - codex_entry -> codex.CodexEntry [FK] (nullable)
**Pointed to by:**
  - choices <- magic.CrossingChoice

### DistinctionResonanceGrant
**Foreign Keys:**
  - distinction -> distinctions.Distinction [FK]
  - resonance -> magic.Resonance [FK]

### DistinctionResonanceRankThreshold
**Foreign Keys:**
  - distinction -> distinctions.Distinction [FK]
  - resonance -> magic.Resonance [FK]

### DistinctionRitualGrant
**Foreign Keys:**
  - distinction -> distinctions.Distinction [FK]
  - ritual -> magic.Ritual [FK]

### DramaticMomentSuggestion
**Foreign Keys:**
  - moment_type -> magic.DramaticMomentType [FK]
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - scene -> scenes.Scene [FK] (nullable)
  - interaction -> scenes.Interaction [FK] (nullable)
  - technique -> magic.Technique [FK] (nullable)
  - resolved_by -> evennia.AccountDB [FK] (nullable)
  - confirmed_tag -> magic.DramaticMomentTag [OneToOne] (nullable)

### DramaticMomentTag
**Foreign Keys:**
  - moment_type -> magic.DramaticMomentType [FK]
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - scene -> scenes.Scene [FK] (nullable)
  - tagged_by -> evennia.AccountDB [FK]
  - interaction -> scenes.Interaction [FK] (nullable)
**Pointed to by:**
  - source_suggestion <- magic.DramaticMomentSuggestion
  - resonance_grants <- magic.ResonanceGrant

### DramaticMomentType
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - resonance -> magic.Resonance [FK] (nullable)
  - archetypes -> societies.PhilosophicalArchetype [M2M]
**Pointed to by:**
  - tags <- magic.DramaticMomentTag
  - suggestions <- magic.DramaticMomentSuggestion

### EffectType
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
**Pointed to by:**
  - available_restrictions <- magic.Restriction
  - techniques <- magic.Technique
  - enhanced_by_techniques <- magic.Technique
  - technique_drafts <- magic.TechniqueDraft
  - combo_slots <- combat.ComboSlot

### EntryFlourishRecord
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - resonance -> magic.Resonance [FK]
  - scene -> scenes.Scene [FK] (nullable)
**Pointed to by:**
  - resonance_grants <- magic.ResonanceGrant

### Facet
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - parent -> magic.Facet [FK] (nullable)
**Pointed to by:**
  - children <- magic.Facet
  - motif_usages <- magic.MotifResonanceAssociation
  - signature_bonuses <- magic.SignatureMotifBonus
  - anchored_threads <- magic.Thread
  - item_attachments <- items.ItemFacet
  - vogue_momentum <- items.FacetVogueMomentum
  - fashion_styles <- items.FashionStyle

### FallRedemptionConfig

### FallRedemptionRecord
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - scene -> scenes.Scene [FK] (nullable)

### FeedingRecord
**Foreign Keys:**
  - feeder_sheet -> character_sheets.CharacterSheet [FK]
  - victim_sheet -> character_sheets.CharacterSheet [FK]
  - scene -> scenes.Scene [FK] (nullable)

### FuryConfig

### FuryTier

### GhostTutelage
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - tradition -> magic.Tradition [FK]

### Gift
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - parent -> magic.Gift [FK] (nullable)
  - creator -> character_sheets.CharacterSheet [FK] (nullable)
  - codex_entry -> codex.CodexEntry [FK] (nullable)
  - style -> magic.TechniqueStyle [FK] (nullable)
  - resonances -> magic.Resonance [M2M]
**Pointed to by:**
  - organization_grants <- societies.OrganizationGiftGrant
  - children <- magic.Gift
  - character_grants <- magic.CharacterGift
  - techniques <- magic.Technique
  - gift_unlocks <- magic.GiftUnlock
  - path_grants <- magic.PathGiftGrant
  - tradition_grants <- magic.TraditionGiftGrant
  - reincarnation <- magic.Reincarnation
  - granted_by_roles <- covenants.CovenantRole
  - role_grants <- covenants.CovenantRoleGiftGrant
  - technique_drafts <- magic.TechniqueDraft
  - thread_pull_effects <- magic.ThreadPullEffect
  - anchored_threads <- magic.Thread
  - thread_weaving_unlocks <- magic.ThreadWeavingUnlock
  - granted_companions <- companions.Companion
  - species_grants <- species.SpeciesGiftGrant
  - capability_project_details <- societies.OrganizationCapabilityProjectDetails

### GiftAcquisitionConfig

### GiftUnlock
**Foreign Keys:**
  - gift -> magic.Gift [FK]
  - paths -> classes.Path [M2M]
**Pointed to by:**
  - character_purchases <- magic.CharacterGiftUnlock

### GlimpseTag
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - affinity -> magic.Affinity [FK] (nullable)
  - paths -> classes.Path [M2M]
**Pointed to by:**
  - character_rows <- magic.CharacterGlimpseTag
  - distinction_suggestions <- magic.GlimpseTagDistinctionSuggestion

### GlimpseTagDistinctionSuggestion
**Foreign Keys:**
  - tag -> magic.GlimpseTag [FK]
  - distinction -> distinctions.Distinction [FK]

### ImbuingProseTemplate
**Foreign Keys:**
  - resonance -> magic.Resonance [FK] (nullable)

### IntensityTier
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
**Pointed to by:**
  - auderethreshold_set <- magic.AudereThreshold

### LevelPowerConfig

### MagicProgressionMilestone
**Foreign Keys:**
  - codex_entry -> codex.CodexEntry [FK] (nullable)

### MagicalAlterationEvent
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - alteration_template -> magic.MagicalAlterationTemplate [FK]
  - active_condition -> conditions.ConditionInstance [FK] (nullable)
  - triggering_scene -> scenes.Scene [FK] (nullable)
  - triggering_technique -> magic.Technique [FK] (nullable)

### MagicalAlterationTemplate
**Foreign Keys:**
  - condition_template -> conditions.ConditionTemplate [OneToOne]
  - origin_affinity -> magic.Affinity [FK]
  - origin_resonance -> magic.Resonance [FK]
  - weakness_damage_type -> conditions.DamageType [FK] (nullable)
  - authored_by -> evennia.AccountDB [FK] (nullable)
  - parent_template -> magic.MagicalAlterationTemplate [FK] (nullable)
  - resonance -> magic.Resonance [FK] (nullable)
**Pointed to by:**
  - variants <- magic.MagicalAlterationTemplate
  - resolved_pending <- magic.PendingAlteration
  - application_events <- magic.MagicalAlterationEvent

### MishapPoolTier
**Foreign Keys:**
  - consequence_pool -> actions.ConsequencePool [FK]

### Motif
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [OneToOne]
**Pointed to by:**
  - resonances <- magic.MotifResonance

### MotifResonance
**Foreign Keys:**
  - motif -> magic.Motif [FK]
  - resonance -> magic.Resonance [FK]
**Pointed to by:**
  - facet_assignments <- magic.MotifResonanceAssociation
  - style_assignments <- magic.MotifResonanceStyle

### MotifResonanceAssociation
**Foreign Keys:**
  - motif_resonance -> magic.MotifResonance [FK]
  - facet -> magic.Facet [FK]

### MotifResonanceStyle
**Foreign Keys:**
  - motif_resonance -> magic.MotifResonance [FK]
  - style -> items.Style [FK]

### PathGiftGrant
**Foreign Keys:**
  - path -> classes.Path [FK]
  - gift -> magic.Gift [FK]
  - starter_techniques -> magic.Technique [M2M]

### PathRitualGrant
**Foreign Keys:**
  - path -> classes.Path [FK]
  - ritual -> magic.Ritual [FK]

### PendingAlteration
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - triggering_scene -> scenes.Scene [FK] (nullable)
  - triggering_technique -> magic.Technique [FK] (nullable)
  - origin_affinity -> magic.Affinity [FK]
  - origin_resonance -> magic.Resonance [FK]
  - resolved_alteration -> magic.MagicalAlterationTemplate [FK] (nullable)
  - resolved_by -> evennia.AccountDB [FK] (nullable)
**Pointed to by:**
  - treatment_attempts_targeting_alteration <- conditions.TreatmentAttempt
  - treatment_action_requests <- scenes.SceneActionRequest

### PendingAudereMajoraOffer
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - threshold -> magic.AudereMajoraThreshold [FK]
  - faith_variant -> magic.AudereMajoraFaithVariant [FK] (nullable)

### PendingAudereOffer
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]

### PendingCrossingOffer
**Foreign Keys:**
  - thread -> magic.Thread [FK]

### PendingEntryFlourishOffer
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - scene -> scenes.Scene [FK] (nullable)

### PendingRitualEffect
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - ritual -> magic.Ritual [FK]

### PendingStageAdvanceOffer
**Foreign Keys:**
  - sinner_sheet -> character_sheets.CharacterSheet [FK]
  - sineater_sheet -> character_sheets.CharacterSheet [FK]
  - relationship -> relationships.CharacterRelationship [FK]
  - scene -> scenes.Scene [FK]
  - resonance -> magic.Resonance [FK]

### PortalAnchor
**Foreign Keys:**
  - room_profile -> evennia_extensions.RoomProfile [FK]
  - kind -> magic.PortalAnchorKind [FK]
  - installed_by -> scenes.Persona [FK] (nullable)

### PortalAnchorKind
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
**Pointed to by:**
  - travel_techniques <- magic.Technique
  - anchors <- magic.PortalAnchor

### PoseEndorsement
**Foreign Keys:**
  - endorser_sheet -> character_sheets.CharacterSheet [FK]
  - endorsee_sheet -> character_sheets.CharacterSheet [FK]
  - persona_snapshot -> scenes.Persona [FK] (nullable)
  - interaction -> scenes.Interaction [FK]
  - resonance -> magic.Resonance [FK]
**Pointed to by:**
  - resonance_grants <- magic.ResonanceGrant

### PresentationEndorsement
**Foreign Keys:**
  - endorser_sheet -> character_sheets.CharacterSheet [FK]
  - endorsee_sheet -> character_sheets.CharacterSheet [FK]
  - persona_snapshot -> scenes.Persona [FK] (nullable)
  - presentation -> items.FashionPresentation [FK]

### Reincarnation
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - gift -> magic.Gift [OneToOne]

### RelationshipBondPullTuning

### Resonance
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - affinity -> magic.Affinity [FK]
  - opposite -> magic.Resonance [OneToOne] (nullable)
  - codex_entry -> codex.CodexEntry [FK] (nullable)
  - properties -> mechanics.Property [M2M]
**Pointed to by:**
  - damage_type <- conditions.DamageType
  - corruption_condition_templates <- conditions.ConditionTemplate
  - modifier_target <- mechanics.ModifierTarget
  - opposite_of <- magic.Resonance
  - gifts <- magic.Gift
  - alteration_templates <- magic.MagicalAlterationTemplate
  - corruption_twist_templates <- magic.MagicalAlterationTemplate
  - pending_alteration_origins <- magic.PendingAlteration
  - character_resonances <- magic.CharacterResonance
  - crossing_options <- magic.CrossingOption
  - dramatic_moment_types <- magic.DramaticMomentType
  - poseendorsement_set <- magic.PoseEndorsement
  - sceneentryendorsement_set <- magic.SceneEntryEndorsement
  - stylepresentationendorsement_set <- magic.StylePresentationEndorsement
  - entry_flourish_records <- magic.EntryFlourishRecord
  - compromise_act_types <- magic.CompromiseActType
  - conversion_sources <- magic.ResonanceConversion
  - conversion_targets <- magic.ResonanceConversion
  - resonancegrant_set <- magic.ResonanceGrant
  - distinction_grants <- magic.DistinctionResonanceGrant
  - distinction_rank_thresholds <- magic.DistinctionResonanceRankThreshold
  - motif_resonances <- magic.MotifResonance
  - imbuing_prose <- magic.ImbuingProseTemplate
  - sanctums <- magic.SanctumDetails
  - techniquevariant_subrole <- magic.TechniqueVariant
  - covenantrole_subrole <- covenants.CovenantRole
  - signature_bonuses <- magic.SignatureMotifBonus
  - sineating_pending_offers <- magic.SineatingPendingOffer
  - pending_stage_advance_offers <- magic.PendingStageAdvanceOffer
  - sineatings <- magic.Sineating
  - rescues <- magic.SoulTetherRescue
  - pull_effects <- magic.ThreadPullEffect
  - threads <- magic.Thread
  - combo_slots <- combat.ComboSlot
  - combat_pulls <- combat.CombatPull
  - alternate_self_grants <- forms.AlternateSelf
  - tied_item_templates <- items.ItemTemplate
  - garment_mitigations <- items.GarmentMitigation
  - wards <- room_features.RoomWardDetails
  - defense_progression_projects <- room_features.DefenseProgressionDetails
  - cascade_overrides <- locations.LocationValueOverride
  - cascade_modifiers <- locations.LocationValueModifier
  - mission_route_rewards <- missions.MissionOptionRouteReward
  - projects <- projects.Project

### ResonanceAlignmentBoonTier
**Foreign Keys:**
  - affinity_interaction -> magic.AffinityInteraction [FK]
  - condition_template -> conditions.ConditionTemplate [FK]

### ResonanceConversion
**Foreign Keys:**
  - source_resonance -> magic.Resonance [FK]
  - target_resonance -> magic.Resonance [FK]

### ResonanceEnvironmentConfig
**Foreign Keys:**
  - updated_by -> evennia.AccountDB [FK] (nullable)

### ResonanceGainConfig
**Foreign Keys:**
  - updated_by -> evennia.AccountDB [FK] (nullable)

### ResonanceGrant
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - resonance -> magic.Resonance [FK]
  - source_room_profile -> evennia_extensions.RoomProfile [FK] (nullable)
  - source_staff_account -> evennia.AccountDB [FK] (nullable)
  - source_pose_endorsement -> magic.PoseEndorsement [FK] (nullable)
  - source_scene_entry_endorsement -> magic.SceneEntryEndorsement [FK] (nullable)
  - outfit_item_facet -> items.ItemFacet [FK] (nullable)
  - source_sanctum_details -> magic.SanctumDetails [FK] (nullable)
  - source_project -> projects.Project [FK] (nullable)
  - source_entry_flourish -> magic.EntryFlourishRecord [FK] (nullable)
  - source_dramatic_moment -> magic.DramaticMomentTag [FK] (nullable)
  - source_style_presentation_endorsement -> magic.StylePresentationEndorsement [FK] (nullable)
  - source_mission_deed_reward_line -> missions.MissionDeedRewardLine [FK] (nullable)
  - source_character_distinction -> distinctions.CharacterDistinction [FK] (nullable)

### ResonanceTier

### Restriction
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - allowed_effect_types -> magic.EffectType [M2M]
**Pointed to by:**
  - techniques <- magic.Technique
  - technique_drafts <- magic.TechniqueDraft

### Ritual
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - flow -> flows.FlowDefinition [FK] (nullable)
  - author_account -> evennia.AccountDB [FK] (nullable)
  - site_property -> mechanics.Property [FK] (nullable)
**Pointed to by:**
  - class_level_advancements <- progression.ClassLevelAdvancement
  - performances <- magic.AnimaRitualPerformance
  - known_by_records <- magic.CharacterRitualKnowledge
  - liturgy <- magic.RitualLiturgy
  - check_config <- magic.RitualCheckConfig
  - anima_contributions <- magic.RitualAnimaContribution
  - requirements <- magic.RitualComponentRequirement
  - pending_effects <- magic.PendingRitualEffect
  - covenant_rite <- covenants.CovenantRite
  - ritualsession_set <- magic.RitualSession
  - technique_grants <- magic.TechniqueGrant
  - installs_room_features <- room_features.RoomFeatureKindInstallRitual
  - capstone_events <- relationships.RelationshipCapstone

### RitualAnimaContribution
**Foreign Keys:**
  - session -> magic.RitualSession [FK] (nullable)
  - ritual -> magic.Ritual [FK]
  - contributor -> character_sheets.CharacterSheet [FK]
  - victim -> character_sheets.CharacterSheet [FK] (nullable)

### RitualCheckConfig
**Foreign Keys:**
  - ritual -> magic.Ritual [OneToOne]
  - stat -> traits.Trait [FK]
  - skill -> skills.Skill [FK]
  - specialization -> skills.Specialization [FK] (nullable)
  - resonance -> magic.Resonance [FK] (nullable)
  - check_type -> checks.CheckType [FK] (nullable)

### RitualComponentRequirement
**Foreign Keys:**
  - ritual -> magic.Ritual [FK]
  - item_template -> items.ItemTemplate [FK] (nullable)
  - min_touchstone_tier -> magic.ResonanceTier [FK] (nullable)
  - min_quality_tier -> items.QualityTier [FK] (nullable)

### RitualLiturgy
**Foreign Keys:**
  - ritual -> magic.Ritual [OneToOne]

### RitualSession
**Foreign Keys:**
  - ritual -> magic.Ritual [FK]
  - initiator -> character_sheets.CharacterSheet [FK]
  - scene -> scenes.Scene [FK] (nullable)
**Pointed to by:**
  - anima_contributions <- magic.RitualAnimaContribution
  - participants <- magic.RitualSessionParticipant
  - references <- magic.RitualSessionReference

### RitualSessionParticipant
**Foreign Keys:**
  - session -> magic.RitualSession [FK]
  - character_sheet -> character_sheets.CharacterSheet [FK]
**Pointed to by:**
  - references <- magic.RitualSessionReference

### RitualSessionReference
**Foreign Keys:**
  - session -> magic.RitualSession [FK]
  - participant -> magic.RitualSessionParticipant [FK] (nullable)
  - ref_covenant -> covenants.Covenant [FK] (nullable)
  - ref_covenant_role -> covenants.CovenantRole [FK] (nullable)
  - ref_organization -> societies.Organization [FK] (nullable)

### SanctumDetails
**Foreign Keys:**
  - feature_instance -> room_features.RoomFeatureInstance [OneToOne]
  - resonance_type -> magic.Resonance [FK]
  - founder_character_sheet -> character_sheets.CharacterSheet [FK] (nullable)
**Pointed to by:**
  - resonance_grants <- magic.ResonanceGrant
  - pending_payouts <- magic.SanctumPendingPayout
  - anchored_threads <- magic.Thread

### SanctumDissolutionRecoveryAward
**Foreign Keys:**
  - outcome_tier -> traits.CheckOutcome [OneToOne]

### SanctumHomecomingGainAward
**Foreign Keys:**
  - outcome_tier -> traits.CheckOutcome [OneToOne]

### SanctumPendingPayout
**Foreign Keys:**
  - sanctum -> magic.SanctumDetails [FK]
  - weaver_character_sheet -> character_sheets.CharacterSheet [FK]

### SanctumPurgingRetentionAward
**Foreign Keys:**
  - outcome_tier -> traits.CheckOutcome [OneToOne]

### SceneEntryEndorsement
**Foreign Keys:**
  - endorser_sheet -> character_sheets.CharacterSheet [FK]
  - endorsee_sheet -> character_sheets.CharacterSheet [FK]
  - persona_snapshot -> scenes.Persona [FK] (nullable)
  - scene -> scenes.Scene [FK]
  - entry_interaction -> scenes.Interaction [FK] (nullable)
  - resonance -> magic.Resonance [FK]
**Pointed to by:**
  - resonance_grants <- magic.ResonanceGrant

### SignatureMotifBonus
**Foreign Keys:**
  - discovery_achievement -> achievements.Achievement [FK] (nullable)
  - required_facet -> magic.Facet [FK] (nullable)
  - required_resonance -> magic.Resonance [FK] (nullable)
**Pointed to by:**
  - damage_profiles <- magic.SignatureMotifBonusDamageProfile
  - condition_applications <- magic.SignatureMotifBonusAppliedCondition

### SignatureMotifBonusAppliedCondition
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK]
  - signature_bonus -> magic.SignatureMotifBonus [FK]

### SignatureMotifBonusDamageProfile
**Foreign Keys:**
  - damage_type -> conditions.DamageType [FK] (nullable)
  - signature_bonus -> magic.SignatureMotifBonus [FK]

### Sineating
**Foreign Keys:**
  - sinner_sheet -> character_sheets.CharacterSheet [FK]
  - sineater_sheet -> character_sheets.CharacterSheet [FK]
  - relationship -> relationships.CharacterRelationship [FK]
  - scene -> scenes.Scene [FK] (nullable)
  - resonance -> magic.Resonance [FK]

### SineatingPendingOffer
**Foreign Keys:**
  - sinner_sheet -> character_sheets.CharacterSheet [FK]
  - sineater_sheet -> character_sheets.CharacterSheet [FK]
  - relationship -> relationships.CharacterRelationship [FK]
  - scene -> scenes.Scene [FK]
  - resonance -> magic.Resonance [FK]

### SoulTetherConfig
**Foreign Keys:**
  - updated_by -> evennia.AccountDB [FK] (nullable)

### SoulTetherRescue
**Foreign Keys:**
  - sinner_sheet -> character_sheets.CharacterSheet [FK]
  - sineater_sheet -> character_sheets.CharacterSheet [FK]
  - relationship -> relationships.CharacterRelationship [FK]
  - scene -> scenes.Scene [FK] (nullable)
  - resonance -> magic.Resonance [FK]
  - check_outcome -> traits.CheckOutcome [FK]

### SoulfrayConfig
**Foreign Keys:**
  - resilience_check_type -> checks.CheckType [FK]

### StandingCapBand

### StyleCapabilityRequirement
**Foreign Keys:**
  - style -> magic.TechniqueStyle [FK]
  - capability -> conditions.CapabilityType [FK]

### StylePresentationEndorsement
**Foreign Keys:**
  - endorser_sheet -> character_sheets.CharacterSheet [FK]
  - endorsee_sheet -> character_sheets.CharacterSheet [FK]
  - persona_snapshot -> scenes.Persona [FK] (nullable)
  - scene -> scenes.Scene [FK]
  - resonance -> magic.Resonance [FK]
**Pointed to by:**
  - resonance_grants <- magic.ResonanceGrant

### Technique
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - discovery_achievement -> achievements.Achievement [FK] (nullable)
  - gift -> magic.Gift [FK]
  - effect_type -> magic.EffectType [FK]
  - enhances_effect_type -> magic.EffectType [FK] (nullable)
  - clash_resolution_pool -> actions.ConsequencePool [FK] (nullable)
  - clash_per_round_pool -> actions.ConsequencePool [FK] (nullable)
  - creator -> character_sheets.CharacterSheet [FK] (nullable)
  - action_template -> actions.ActionTemplate [FK] (nullable)
  - target_weather_type -> weather.WeatherType [FK] (nullable)
  - travel_anchor_kind -> magic.PortalAnchorKind [FK] (nullable)
  - codex_entry -> codex.CodexEntry [FK] (nullable)
  - restrictions -> magic.Restriction [M2M]
  - applied_conditions -> conditions.ConditionTemplate [M2M]
  - properties -> mechanics.Property [M2M]
  - target_prerequisites -> mechanics.Prerequisite [M2M]
**Pointed to by:**
  - action_enhancements <- actions.ActionEnhancement
  - conditions_caused <- conditions.ConditionInstance
  - battle_declarations <- battles.BattleActionDeclaration
  - battle_property_affinities <- battles.TechniquePropertyAffinity
  - function_tags <- magic.TechniqueFunctionTag
  - capability_grants <- magic.TechniqueCapabilityGrant
  - capability_requirements <- magic.TechniqueCapabilityRequirement
  - character_grants <- magic.CharacterTechnique
  - condition_applications <- magic.TechniqueAppliedCondition
  - removed_conditions <- magic.TechniqueRemovedCondition
  - treatments <- magic.TechniqueTreatment
  - damage_profiles <- magic.TechniqueDamageProfile
  - pendingalteration_set <- magic.PendingAlteration
  - magicalalterationevent_set <- magic.MagicalAlterationEvent
  - dramatic_moment_suggestions <- magic.DramaticMomentSuggestion
  - teaching_offers <- magic.TechniqueTeachingOffer
  - granted_by_path_gifts <- magic.PathGiftGrant
  - granted_by_tradition_gifts <- magic.TraditionGiftGrant
  - variants <- magic.TechniqueVariant
  - grants <- magic.TechniqueGrant
  - progress_records <- magic.TechniqueProgress
  - progress_weekly <- magic.TechniqueProgressWeekly
  - anchored_threads <- magic.Thread
  - companion_abilities <- companions.CompanionAbility
  - alternate_self_grants <- forms.AlternateSelf
  - train_offers <- npc_services.TrainOfferDetails
  - scene_action_requests <- scenes.SceneActionRequest

### TechniqueAppliedCondition
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK]
  - technique -> magic.Technique [FK]

### TechniqueBudgetConfig

### TechniqueCapabilityGrant
**Foreign Keys:**
  - capability -> conditions.CapabilityType [FK]
  - technique -> magic.Technique [FK]
  - prerequisite -> mechanics.Prerequisite [FK] (nullable)

### TechniqueCapabilityRequirement
**Foreign Keys:**
  - technique -> magic.Technique [FK]
  - capability -> conditions.CapabilityType [FK]

### TechniqueDamageProfile
**Foreign Keys:**
  - damage_type -> conditions.DamageType [FK] (nullable)
  - technique -> magic.Technique [FK]

### TechniqueDraft
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [OneToOne]
  - gift -> magic.Gift [FK] (nullable)
  - effect_type -> magic.EffectType [FK] (nullable)
  - consequence_pool -> actions.ConsequencePool [FK] (nullable)
  - restrictions -> magic.Restriction [M2M]
**Pointed to by:**
  - capability_grants <- magic.TechniqueDraftCapabilityGrant
  - damage_profiles <- magic.TechniqueDraftDamageProfile
  - applied_conditions <- magic.TechniqueDraftAppliedCondition
  - removed_conditions <- magic.TechniqueDraftRemovedCondition
  - treatments <- magic.TechniqueDraftTreatment

### TechniqueDraftAppliedCondition
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK]
  - draft -> magic.TechniqueDraft [FK]

### TechniqueDraftCapabilityGrant
**Foreign Keys:**
  - capability -> conditions.CapabilityType [FK]
  - draft -> magic.TechniqueDraft [FK]

### TechniqueDraftDamageProfile
**Foreign Keys:**
  - damage_type -> conditions.DamageType [FK] (nullable)
  - draft -> magic.TechniqueDraft [FK]

### TechniqueDraftRemovedCondition
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK]
  - draft -> magic.TechniqueDraft [FK]

### TechniqueDraftTreatment
**Foreign Keys:**
  - draft -> magic.TechniqueDraft [FK]
  - treatment_template -> conditions.TreatmentTemplate [FK]

### TechniqueFunctionTag
**Foreign Keys:**
  - technique -> magic.Technique [FK]

### TechniqueGrant
**Foreign Keys:**
  - technique -> magic.Technique [FK]
  - item_template -> items.ItemTemplate [FK] (nullable)
  - ritual -> magic.Ritual [FK] (nullable)

### TechniqueOutcomeModifier
**Foreign Keys:**
  - outcome -> traits.CheckOutcome [OneToOne]

### TechniqueProgress
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - technique -> magic.Technique [FK]
  - teacher_tenure -> roster.RosterTenure [FK] (nullable)

### TechniqueProgressWeekly
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - technique -> magic.Technique [FK]
  - game_week -> game_clock.GameWeek [FK]

### TechniqueRemovedCondition
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK]
  - technique -> magic.Technique [FK]

### TechniqueStyle
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
**Pointed to by:**
  - paths <- classes.Path
  - gifts <- magic.Gift
  - capability_requirements <- magic.StyleCapabilityRequirement

### TechniqueTeachingOffer
**Foreign Keys:**
  - teacher -> roster.RosterTenure [FK]
  - technique -> magic.Technique [FK]

### TechniqueTierBudget

### TechniqueTreatment
**Foreign Keys:**
  - technique -> magic.Technique [FK]
  - treatment_template -> conditions.TreatmentTemplate [FK]

### TechniqueVariant
**Foreign Keys:**
  - resonance -> magic.Resonance [FK] (nullable)
  - discovery_achievement -> achievements.Achievement [FK] (nullable)
  - codex_entry -> codex.CodexEntry [FK] (nullable)
  - parent_technique -> magic.Technique [FK]
**Pointed to by:**
  - capability_grants <- magic.TechniqueVariantCapabilityGrant
  - damage_profiles <- magic.TechniqueVariantDamageProfile
  - condition_applications <- magic.TechniqueVariantAppliedCondition

### TechniqueVariantAppliedCondition
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK]
  - variant -> magic.TechniqueVariant [FK]

### TechniqueVariantCapabilityGrant
**Foreign Keys:**
  - capability -> conditions.CapabilityType [FK]
  - variant -> magic.TechniqueVariant [FK]
  - prerequisite -> mechanics.Prerequisite [FK] (nullable)

### TechniqueVariantDamageProfile
**Foreign Keys:**
  - damage_type -> conditions.DamageType [FK] (nullable)
  - variant -> magic.TechniqueVariant [FK]

### Thread
**Foreign Keys:**
  - owner -> character_sheets.CharacterSheet [FK]
  - resonance -> magic.Resonance [FK]
  - target_trait -> traits.Trait [FK] (nullable)
  - target_technique -> magic.Technique [FK] (nullable)
  - target_relationship_track -> relationships.RelationshipTrackProgress [FK] (nullable)
  - target_capstone -> relationships.RelationshipCapstone [FK] (nullable)
  - target_facet -> magic.Facet [FK] (nullable)
  - target_covenant_role -> covenants.CovenantRole [FK] (nullable)
  - target_gift -> magic.Gift [FK] (nullable)
  - target_mantle -> items.Mantle [FK] (nullable)
  - target_sanctum_details -> magic.SanctumDetails [FK] (nullable)
  - target_organization -> societies.Organization [FK] (nullable)
  - signature_bonus -> magic.SignatureMotifBonus [FK] (nullable)
**Pointed to by:**
  - treatment_attempts <- conditions.TreatmentAttempt
  - crossing_choices <- magic.CrossingChoice
  - pending_crossing_offers <- magic.PendingCrossingOffer
  - level_unlocks <- magic.ThreadLevelUnlock
  - combat_pulls <- combat.CombatPull
  - resolved_pull_effects <- combat.CombatPullResolvedEffect
  - related_journal_entries <- journals.JournalEntry
  - treatment_action_requests <- scenes.SceneActionRequest
  - action_pull_declarations <- scenes.SceneActionPullDeclaration

### ThreadCrossingThreshold
**Pointed to by:**
  - traitrequirement_requirements <- progression.TraitRequirement
  - levelrequirement_requirements <- progression.LevelRequirement
  - classlevelrequirement_requirements <- progression.ClassLevelRequirement
  - multiclassrequirement_requirements <- progression.MultiClassRequirement
  - achievementrequirement_requirements <- progression.AchievementRequirement
  - relationshiprequirement_requirements <- progression.RelationshipRequirement
  - legendrequirement_requirements <- progression.LegendRequirement
  - tierrequirement_requirements <- progression.TierRequirement
  - itemrequirement_requirements <- progression.ItemRequirement
  - majorgifttechniquerequirement_requirements <- progression.MajorGiftTechniqueRequirement
  - codexknowledgerequirement_requirements <- progression.CodexKnowledgeRequirement

### ThreadLevelUnlock
**Foreign Keys:**
  - thread -> magic.Thread [FK]

### ThreadPullCost

### ThreadPullEffect
**Foreign Keys:**
  - resonance -> magic.Resonance [FK]
  - capability_grant -> conditions.CapabilityType [FK] (nullable)
  - target_form -> forms.CharacterForm [FK] (nullable)
  - resistance_damage_type -> conditions.DamageType [FK] (nullable)
  - target_gift -> magic.Gift [FK] (nullable)

### ThreadSurvivabilityTuning

### ThreadWeavingTeachingOffer
**Foreign Keys:**
  - teacher -> roster.RosterTenure [FK]
  - unlock -> magic.ThreadWeavingUnlock [FK]

### ThreadWeavingUnlock
**Foreign Keys:**
  - unlock_trait -> traits.Trait [FK] (nullable)
  - unlock_gift -> magic.Gift [FK] (nullable)
  - unlock_track -> relationships.RelationshipTrack [FK] (nullable)
  - paths -> classes.Path [M2M]
**Pointed to by:**
  - character_purchases <- magic.CharacterThreadWeavingUnlock
  - teaching_offers <- magic.ThreadWeavingTeachingOffer

### ThreadXPLockedLevel

### TouchstoneCastConfig

### Tradition
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
**Pointed to by:**
  - available_beginnings <- character_creation.Beginnings
  - beginning_traditions <- character_creation.BeginningTradition
  - codex_grants <- codex.TraditionCodexGrant
  - teaching_organizations <- societies.Organization
  - character_traditions <- magic.CharacterTradition
  - ghost_tutelages <- magic.GhostTutelage
  - gift_grants <- magic.TraditionGiftGrant
  - ritual_grants <- magic.TraditionRitualGrant
  - teaching_npc_roles <- npc_services.NPCRole

### TraditionGiftGrant
**Foreign Keys:**
  - tradition -> magic.Tradition [FK]
  - gift -> magic.Gift [FK]
  - special_techniques -> magic.Technique [M2M]

### TraditionRitualGrant
**Foreign Keys:**
  - tradition -> magic.Tradition [FK]
  - ritual -> magic.Ritual [FK]

### TrainingOutcomeAward
**Foreign Keys:**
  - outcome_tier -> traits.CheckOutcome [OneToOne]

### Service Functions
- `accept_thread_weaving_unlock(learner: 'CharacterSheet', offer: 'ThreadWeavingTeachingOffer') -> 'CharacterThreadWeavingUnlock' - Accept a ThreadWeavingTeachingOffer on behalf of a learner (Spec A §6.1).`
- `apply_damage_reduction_from_threads(character: 'ObjectDB', incoming_damage: 'int') -> 'int' - Reduce incoming damage by thread-derived DAMAGE_TAKEN_REDUCTION.`
- `attune_touchstone(*, character_sheet: 'CharacterSheet', ritual: 'Ritual | None', item_instance: 'ItemInstance', **kwargs: 'Any') -> 'ItemInstance' - Bind ``item_instance`` to ``character_sheet`` as a personal touchstone.`
- `calculate_effective_anima_cost(*, base_cost: 'int', runtime_intensity: 'int', runtime_control: 'int', current_anima: 'int', strain_commitment: 'int' = 0, lethal: 'bool' = True) -> 'AnimaCostResult' - Calculate effective anima cost using the delta formula.`
- `calculate_soulfray_severity(current_anima: 'int', max_anima: 'int', deficit: 'int', config: 'SoulfrayConfig', *, lethal: 'bool' = True) -> 'int' - Compute Soulfray severity contribution from post-deduction anima state.`
- `coherence_cache_scope() - Context manager that memoizes ``motif_coherence_bonus`` per (sheet, resonance).`
- `compute_anchor_cap(thread: 'Thread') -> 'int' - Return the anchor-side cap for this thread (Spec A §2.4).`
- `compute_effective_cap(thread: 'Thread') -> 'int' - Return min(path cap, anchor cap) — the binding limit on this thread (Spec A §2.4).`
- `compute_path_cap(character_sheet: 'CharacterSheet') -> 'int' - Return the path-side cap for a character (Spec A §2.4).`
- `compute_thread_weaving_xp_cost(unlock: 'ThreadWeavingUnlock', learner: 'CharacterSheet') -> 'int' - Compute the XP cost for a learner to acquire a ThreadWeavingUnlock (Spec A §6.2).`
- `create_pending_alteration(*, character: 'CharacterSheet', tier: 'int', origin_affinity: 'Affinity', origin_resonance: 'ResonanceModel', scene: 'Scene | None', triggering_technique: 'Technique | None' = None, triggering_intensity: 'int | None' = None, triggering_control: 'int | None' = None, triggering_anima_cost: 'int | None' = None, triggering_anima_deficit: 'int | None' = None, triggering_soulfray_stage: 'int | None' = None, audere_active: 'bool' = False) -> 'PendingAlterationResult' - Create or escalate a PendingAlteration for a character.`
- `cross_thread_xp_lock(character_sheet: 'CharacterSheet', thread: 'Thread', boundary_level: 'int') -> 'ThreadLevelUnlock' - Pay XP to unlock an XP-locked level boundary on a thread.`
- `deduct_anima(character: 'ObjectDB', effective_cost: 'int', *, lethal: 'bool' = True) -> 'int' - Deduct anima from character, returning the overburn deficit.`
- `get_character_anima_ritual(character) - The character's authored SCENE_ACTION ritual (with check_config), or None.`
- `get_character_cast_check(character) - The CheckType a character's technique casts roll, or None for fallback.`
- `get_imbue_cost_multiplier(target_kind: 'str | None') -> 'int' - Resolve the imbue dp cost multiplier for a thread kind (ADR-0051).`
- `get_library_entries(*, tier: 'int', character_affinity_id: 'int | None' = None) -> 'QuerySet[MagicalAlterationTemplate]' - Return library entries matching the given tier.`
- `get_pull_cost(tier: 'int', target_kind: 'str | None') -> 'ThreadPullCost' - Resolve the pull cost row for (tier, target_kind).`
- `get_runtime_technique_stats(technique: 'Technique', character: 'ObjectDB | None', *, apply_variant: 'bool' = True, character_technique=None, preferred_resonance=None) -> 'RuntimeTechniqueStats' - Calculate runtime intensity and control for a technique.`
- `get_soulfray_warning(character: 'ObjectDB') -> 'SoulfrayWarning | None' - Return the current Soulfray stage warning for the safety checkpoint.`
- `get_thread_survivability_tuning(vital_target: 'str') -> "'ThreadSurvivabilityTuning | None'" - Return the tuning row for a target, or None if unseeded (baseline 0).`
- `gift_thread_resistance(character: 'ObjectDB', damage_type: 'DamageType') -> 'int' - Total damage-type-specific resistance from gift threads (#1580).`
- `grant_resonance(character_sheet: 'CharacterSheet', resonance: 'ResonanceModel', amount: 'int', *, source: 'str', pose_endorsement: 'PoseEndorsement | None' = None, scene_entry_endorsement: 'SceneEntryEndorsement | None' = None, room_profile: 'RoomProfile | None' = None, staff_account: 'AccountDB | None' = None, outfit_item_facet: 'ItemFacet | None' = None, sanctum_details: 'SanctumDetails | None' = None, project: 'Project | None' = None, entry_flourish: 'EntryFlourishRecord | None' = None, dramatic_moment: 'DramaticMomentTag | None' = None, style_presentation_endorsement: 'StylePresentationEndorsement | None' = None, mission_deed_reward_line: 'MissionDeedRewardLine | None' = None, source_character_distinction: 'CharacterDistinction | None' = None) -> 'CharacterResonance' - Atomically grant resonance AND write the ResonanceGrant ledger row.`
- `has_pending_alterations(character: 'CharacterSheet') -> 'bool' - Check if this character has any unresolved Mage Scars.`
- `imbue_ready_threads(character_sheet: 'CharacterSheet') -> 'list[Thread]' - Return threads that have matching CharacterResonance balance > 0 and level < cap.`
- `near_xp_lock_threads(character_sheet: 'CharacterSheet', within: 'int' = 100) -> 'list[ThreadXPLockProspect]' - Return threads whose dev_points are within `within` of the next XP-locked boundary.`
- `preview_resonance_pull(character_sheet: 'CharacterSheet', resonance: 'ResonanceModel', tier: 'int', threads: 'list[Thread]', *, combat_encounter: 'CombatEncounter | None' = None, scene_id: 'int | None' = None, excluded_kinds: 'frozenset[str] | None' = None, target: 'ObjectDB | None' = None) -> 'PullPreviewResult' - Read-only preview of a resonance pull (Spec A §5.6).`
- `provision_player_anima_ritual(account: 'AccountDB', character_sheet: 'CharacterSheet', roster_entry: 'RosterEntry', *, ritual_name: 'str', stat: 'Trait | None' = None, skill: 'Skill | None' = None, resonance: 'Resonance | None' = None) -> 'Ritual | None' - Create a SCENE_ACTION Ritual + sidecar + CharacterRitualKnowledge for a player.`
- `recompute_max_health_with_threads(character_sheet: 'CharacterSheet') -> 'int' - Recompute max_health folding in thread-derived VITAL_BONUS addends.`
- `reconcile_ritual_knowledge(roster_entry: 'RosterEntry') -> None - Ensure CharacterRitualKnowledge rows exist for all granted rituals.`
- `resolve_and_consume_ritual_components(*, ritual: 'Ritual', components: 'list[ItemInstance]', performer_sheet: 'CharacterSheet', resonance_context: 'Resonance | None' = None) -> 'None' - Validate and atomically consume ``ritual``'s components from ``components``.`
- `resolve_cast_check_type(character, template) - The CheckType a technique cast rolls, for EVERY cast path (ADR-0096).`
- `resolve_pending_alteration(*, pending: 'PendingAlteration', name: 'str', player_description: 'str', observer_description: 'str', weakness_damage_type: 'DamageType | None' = None, weakness_magnitude: 'int' = 0, resonance_bonus_magnitude: 'int' = 0, social_reactivity_magnitude: 'int' = 0, is_visible_at_rest: 'bool', resolved_by: 'AccountDB | None', parent_template: 'MagicalAlterationTemplate | None' = None, is_library_entry: 'bool' = False, library_template: 'MagicalAlterationTemplate | None' = None) -> 'AlterationResolutionResult' - Resolve a PendingAlteration by creating or selecting a template.`
- `resolve_pull_effects(threads: 'list[Thread]', tier: 'int', *, in_combat: 'bool', target: 'ObjectDB | None' = None, beseech_bonus_thread_id: 'int | None' = None, beseech_bonus: 'int' = 0, character_sheet: 'CharacterSheet | None' = None) -> 'list[ResolvedPullEffect]' - Resolve every (thread × effect_tier 0..tier) pair into ResolvedPullEffect rows.`
- `seed_thread_survivability_tuning() -> 'None' - Idempotently author the default ThreadSurvivabilityTuning rows (#1175).`
- `select_mishap_pool(control_deficit: 'int') -> 'ConsequencePool | None' - Select a control mishap consequence pool based on deficit magnitude.`
- `spend_resonance_for_imbuing(character_sheet: 'CharacterSheet', thread: 'Thread', amount: 'int') -> 'ThreadImbueResult' - Deduct resonance balance and greedily advance thread level.`
- `spend_resonance_for_pull(character_sheet: 'CharacterSheet', resonance: 'ResonanceModel', tier: 'int', threads: 'list[Thread]', action_context: 'PullActionContext', beseech_bonus_thread_id: 'int | None' = None, beseech_bonus: 'int' = 0, anima_cost_override: 'int | None' = None) -> 'ResonancePullResult' - Atomic pull commit (Spec A §5.4 + §7.4).`
- `staff_clear_alteration(*, pending: 'PendingAlteration', staff_account: 'AccountDB | None', notes: 'str' = '') -> 'None' - Clear a PendingAlteration without resolving it. Staff escape hatch.`
- `survivability_baseline(character: 'ObjectDB', vital_target: 'str') -> 'int' - Universal soft-capped survivability baseline from thread investment (#1175),`
- `survivability_save_baselines(character: 'ObjectDB') -> 'ThreadSurvivabilitySaves' - Per-tier survivability save modifiers from thread investment (#1250).`
- `threads_blocked_by_cap(character_sheet: 'CharacterSheet') -> 'list[Thread]' - Return threads that are at their effective cap (no further imbuing helps).`
- `update_thread_narrative(thread: 'Thread', *, name: 'str | None' = None, description: 'str | None' = None) -> 'Thread' - Update the narrative name and/or description of a thread.`
- `use_technique(*, character: 'ObjectDB', technique: 'Technique', resolve_fn: 'Callable[..., Any]', confirm_soulfray_risk: 'bool' = True, check_result: 'CheckResult | None' = None, targets: 'list | None' = None, strain_commitment: 'int' = 0, applicable_threads: 'Sequence[ApplicableThread] | None' = None, cast_pull: 'CastPullDeclaration | None' = None, pull_target: 'ObjectDB | None' = None, power_intensity_bonus: 'int' = 0, lethal: 'bool' = True, control_penalty: 'int' = 0, apply_variant: 'bool' = True, preferred_resonance=None, situation_ctx: 'object | None' = None, target_sheet: 'CharacterSheet | None' = None) -> 'TechniqueUseResult' - Orchestrate technique use: cost -> checkpoint -> resolve -> soulfray -> mishap.`
- `validate_alteration_resolution(*, pending_tier: 'int', pending_affinity_id: 'int', pending_resonance_id: 'int', payload: 'dict', is_staff: 'bool', character_sheet: 'CharacterSheet | None' = None) -> 'list[str]' - Validate a resolution payload against the pending's tier and origin.`
- `weave_thread(character_sheet: 'CharacterSheet', target_kind: 'str', target: 'object', resonance: 'ResonanceModel', *, name: 'str' = '', description: 'str' = '') -> 'Thread' - Create a new Thread anchored to the given target.`



## world.mechanics

### AestheticAxisConfig

### Application
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - capability -> conditions.CapabilityType [FK]
  - target_property -> mechanics.Property [FK]
  - required_effect_property -> mechanics.Property [FK] (nullable)
  - default_template -> mechanics.ChallengeTemplate [FK] (nullable)
**Pointed to by:**
  - challenge_approaches <- mechanics.ChallengeApproach

### ApproachConsequence
**Foreign Keys:**
  - approach -> mechanics.ChallengeApproach [FK]
  - consequence -> checks.Consequence [FK]

### ChallengeApproach
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - challenge_template -> mechanics.ChallengeTemplate [FK]
  - application -> mechanics.Application [FK]
  - check_type -> checks.CheckType [FK]
  - required_effect_property -> mechanics.Property [FK] (nullable)
  - action_template -> actions.ActionTemplate [FK] (nullable)
**Pointed to by:**
  - consequences <- mechanics.ApproachConsequence
  - character_records <- mechanics.CharacterChallengeRecord
  - combat_declarations <- combat.RoundChallengeDeclaration
  - scene_declarations <- scenes.SceneActionDeclaration

### ChallengeCategory
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
**Pointed to by:**
  - challenge_templates <- mechanics.ChallengeTemplate
  - situation_templates <- mechanics.SituationTemplate
  - assist_patterns <- missions.MissionAssistPattern

### ChallengeInstance
**Foreign Keys:**
  - situation_instance -> mechanics.SituationInstance [FK] (nullable)
  - template -> mechanics.ChallengeTemplate [FK]
  - location -> evennia.ObjectDB [FK]
  - target_object -> evennia.ObjectDB [FK]
**Pointed to by:**
  - gated_position_edges <- areas.PositionEdge
  - granted_properties <- mechanics.ObjectProperty
  - character_records <- mechanics.CharacterChallengeRecord
  - combat_declarations <- combat.RoundChallengeDeclaration
  - scene_declarations <- scenes.SceneActionDeclaration

### ChallengeTemplate
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - category -> mechanics.ChallengeCategory [FK]
  - blocked_capability -> conditions.CapabilityType [FK] (nullable)
  - properties -> mechanics.Property [M2M]
  - consequences -> checks.Consequence [M2M]
**Pointed to by:**
  - challenge_template_properties <- mechanics.ChallengeTemplateProperty
  - default_for_applications <- mechanics.Application
  - challenge_consequences <- mechanics.ChallengeTemplateConsequence
  - approaches <- mechanics.ChallengeApproach
  - situation_templates <- mechanics.SituationTemplate
  - situation_links <- mechanics.SituationChallengeLink
  - instances <- mechanics.ChallengeInstance
  - beat_staged_lines <- stories.BeatStagedTemplate

### ChallengeTemplateConsequence
**Foreign Keys:**
  - challenge_template -> mechanics.ChallengeTemplate [FK]
  - consequence -> checks.Consequence [FK]

### ChallengeTemplateProperty
**Foreign Keys:**
  - challenge_template -> mechanics.ChallengeTemplate [FK]
  - property -> mechanics.Property [FK]

### CharacterChallengeRecord
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - challenge_instance -> mechanics.ChallengeInstance [FK]
  - approach -> mechanics.ChallengeApproach [FK]
  - outcome -> traits.CheckOutcome [FK] (nullable)
  - consequence -> checks.Consequence [FK] (nullable)
**Pointed to by:**
  - consequence_outcomes <- checks.ConsequenceOutcome

### CharacterEngagement
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [OneToOne]
  - source_content_type -> django.ContentType [FK]

### CharacterModifier
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - target -> mechanics.ModifierTarget [FK]
  - source -> mechanics.ModifierSource [FK]

### ContextConsequencePool
**Foreign Keys:**
  - property -> mechanics.Property [FK]
  - consequence_pool -> actions.ConsequencePool [FK]
  - check_type -> checks.CheckType [FK] (nullable)

### ModifierCategory
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
**Pointed to by:**
  - targets <- mechanics.ModifierTarget

### ModifierSource
**Foreign Keys:**
  - distinction_effect -> distinctions.DistinctionEffect [FK] (nullable)
  - character_distinction -> distinctions.CharacterDistinction [FK] (nullable)
  - form_combat_profile -> forms.FormCombatProfile [FK] (nullable)
**Pointed to by:**
  - modifiers <- mechanics.CharacterModifier
  - granted_techniques <- magic.CharacterTechnique

### ModifierTarget
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - category -> mechanics.ModifierCategory [FK]
  - target_trait -> traits.Trait [FK] (nullable)
  - target_affinity -> magic.Affinity [OneToOne] (nullable)
  - target_resonance -> magic.Resonance [OneToOne] (nullable)
  - target_capability -> conditions.CapabilityType [OneToOne] (nullable)
  - target_check_type -> checks.CheckType [OneToOne] (nullable)
  - target_damage_type -> conditions.DamageType [OneToOne] (nullable)
**Pointed to by:**
  - reward_definitions <- achievements.RewardDefinition
  - conditionmodifiereffect_set <- conditions.ConditionModifierEffect
  - character_modifiers <- mechanics.CharacterModifier
  - codex_entry <- codex.CodexEntry
  - covenant_level_bonuses <- covenants.CovenantLevelBonus
  - vow_stat_scalings <- covenants.VowStatScaling
  - covenant_role_bonuses <- covenants.CovenantRoleBonus
  - distinction_effects <- distinctions.DistinctionEffect
  - form_effects <- forms.FormCombatProfileEffect
  - character_goals <- goals.CharacterGoal
  - goal_journals <- goals.GoalJournal
  - leaning_styles <- items.Style
  - fashion_style_bonuses <- items.FashionStyleBonus
  - item_accents <- items.ItemAccent
  - accent_exclusions_a <- items.AccentExclusion
  - accent_exclusions_b <- items.AccentExclusion
  - accent_archetype_allowances <- items.AccentArchetypeAllowance
  - refinement_projects <- items.ItemRefinementDetails
  - gated_by_conditions <- relationships.RelationshipCondition

### ObjectProperty
**Foreign Keys:**
  - object -> evennia.ObjectDB [FK]
  - property -> mechanics.Property [FK]
  - source_condition -> conditions.ConditionInstance [FK] (nullable)
  - source_challenge -> mechanics.ChallengeInstance [FK] (nullable)

### Prerequisite
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - property -> mechanics.Property [FK]
**Pointed to by:**
  - capability_types <- conditions.CapabilityType
  - gated_techniques <- magic.Technique
  - technique_grants <- magic.TechniqueCapabilityGrant
  - technique_variant_grants <- magic.TechniqueVariantCapabilityGrant

### Property
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - category -> mechanics.PropertyCategory [FK]
**Pointed to by:**
  - consequence_effects <- checks.ConsequenceEffect
  - condition_templates <- conditions.ConditionTemplate
  - condition_stages_carrying <- conditions.ConditionStage
  - prerequisites <- mechanics.Prerequisite
  - challenge_template_properties <- mechanics.ChallengeTemplateProperty
  - object_properties <- mechanics.ObjectProperty
  - damage_modifiers <- mechanics.PropertyDamageModifier
  - detonation <- mechanics.PropertyDetonation
  - applications <- mechanics.Application
  - required_by_applications <- mechanics.Application
  - challenge_templates <- mechanics.ChallengeTemplate
  - required_by_approaches <- mechanics.ChallengeApproach
  - context_consequence_pools <- mechanics.ContextConsequencePool
  - battle_technique_affinities <- battles.TechniquePropertyAffinity
  - battle_terrain_effects <- battles.TerrainPropertyEffect
  - battle_weather_effects <- battles.WeatherTypePropertyEffect
  - resonances <- magic.Resonance
  - techniques <- magic.Technique
  - ritual_sites <- magic.Ritual
  - threat_pool_entries <- combat.ThreatPoolEntry
  - granted_by_companion_abilities <- companions.CompanionAbility
  - companion_abilities <- companions.CompanionAbility
  - item_template_defaults <- items.ItemTemplateProperty
  - military_units <- military.MilitaryUnit
  - personas <- scenes.Persona

### PropertyCategory
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
**Pointed to by:**
  - properties <- mechanics.Property

### PropertyDamageModifier
**Foreign Keys:**
  - property -> mechanics.Property [FK]
  - damage_type -> conditions.DamageType [FK] (nullable)

### PropertyDetonation
**Foreign Keys:**
  - property -> mechanics.Property [OneToOne]
  - consequence_pool -> actions.ConsequencePool [FK]

### SituationChallengeLink
**Foreign Keys:**
  - situation_template -> mechanics.SituationTemplate [FK]
  - challenge_template -> mechanics.ChallengeTemplate [FK]
  - depends_on -> mechanics.SituationChallengeLink [FK] (nullable)
**Pointed to by:**
  - dependents <- mechanics.SituationChallengeLink

### SituationInstance
**Foreign Keys:**
  - template -> mechanics.SituationTemplate [FK]
  - location -> evennia.ObjectDB [FK]
  - created_by -> evennia.AccountDB [FK] (nullable)
  - scene -> scenes.Scene [FK] (nullable)
**Pointed to by:**
  - challenge_instances <- mechanics.ChallengeInstance

### SituationTemplate
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - category -> mechanics.ChallengeCategory [FK]
  - challenges -> mechanics.ChallengeTemplate [M2M]
**Pointed to by:**
  - challenge_links <- mechanics.SituationChallengeLink
  - trap_links <- mechanics.SituationTrapLink
  - instances <- mechanics.SituationInstance
  - beat_staged_lines <- stories.BeatStagedTemplate

### SituationTrapLink
**Foreign Keys:**
  - situation_template -> mechanics.SituationTemplate [FK]
  - consequence_pool -> actions.ConsequencePool [FK]
  - detect_check_type -> checks.CheckType [FK]
  - disarm_check_type -> checks.CheckType [FK]

### TraitCapabilityDerivation
**Foreign Keys:**
  - trait -> traits.Trait [FK]
  - capability -> conditions.CapabilityType [FK]

### Service Functions
- `begin_engagement(character: 'ObjectDB', engagement_type: 'str', *, source: 'object') -> 'CharacterEngagement' - Ensure the character has an engagement; create one if none exists.`
- `chart_has_success_outcomes(rank_difference: int) -> bool - Check if the ResultChart for this rank difference has any success outcomes.`
- `coherence_cache_scope() - Context manager that memoizes ``motif_coherence_bonus`` per (sheet, resonance).`
- `covenant_level_bonus(sheet: 'object', target: 'ModifierTarget') -> 'int' - Sum the authored covenant-level passive bonus across engaged PRIMARY`
- `covenant_role_base_total(sheet: 'object', target: 'ModifierTarget') -> 'int' - Raw engaged-PRIMARY-covenant-role bonus for ``target`` — no per-gear marginal`
- `covenant_role_bonus(sheet: 'object', target: 'ModifierTarget', level_override: 'int | None' = None) -> 'int' - Sum covenant-role contributions across equipped items, gated on engagement.`
- `create_distinction_modifiers(character_distinction: 'CharacterDistinction') -> 'list[CharacterModifier]' - Create ModifierSource + CharacterModifier records for all effects of a distinction.`
- `delete_distinction_modifiers(character_distinction: 'CharacterDistinction') -> 'int' - Delete all modifier records for a distinction.`
- `end_engagement(character: 'ObjectDB', engagement_type: 'str', *, source: 'object') -> 'None' - Delete the character's engagement iff it matches type AND source.`
- `equipment_walk_total(character: 'object', target: 'ModifierTarget', level_override: 'int | None' = None) -> 'int' - Sum facet + covenant-role + covenant-level + mantle passive bonuses (Spec D §5.5).`
- `equipment_walk_total_unblended(sheet: 'object', target: 'ModifierTarget') -> 'int' - ``equipment_walk_total`` with the covenant-role component as its raw base (#1174).`
- `fashion_outfit_bonus(sheet: 'object', target: 'ModifierTarget', society: 'object') -> 'int' - Perception-relative outfit bonus vs. a society's current fashion (#513).`
- `get_aesthetic_config() -> 'AestheticAxisConfig' - Lazy-create and return the singleton aesthetic-axis config (pk=1).`
- `get_all_capability_values(character_sheet: 'CharacterSheet') -> dict[int, int] - Get all capability values for a character.`
- `get_available_actions(character: 'ObjectDB', location: 'ObjectDB', capability_sources: 'list[CapabilitySource] | None' = None) -> 'list[AvailableAction]' - Generate available Actions for a character at a location.`
- `get_capability_sources_for_character(character: 'ObjectDB') -> 'list[CapabilitySource]' - Collect all Capability sources for a character (per-source, not aggregated).`
- `get_modifier_breakdown(character, modifier_target: 'ModifierTarget') -> 'ModifierBreakdown' - Get detailed breakdown of all modifiers for a target.`
- `get_modifier_total(character, modifier_target: 'ModifierTarget', *, perceiving_society: 'object | None' = None, level_override: 'int | None' = None) -> 'int' - Get total modifier value for a target.`
- `item_mundane_stat_for_target(item: 'ItemInstance', target: 'ModifierTarget') -> 'int' - Mundane combat stat an equipped item contributes to ``target`` (#985, §5.6).`
- `motif_coherence_bonus(sheet: 'object', resonance_id: 'int') -> 'int' - Per-resonance fashion-coherence bonus from worn styles bound to the character's Motif.`
- `passive_facet_bonuses(sheet: 'object', target: 'ModifierTarget') -> 'int' - Sum tier-0 FLAT_BONUS contributions from equipped item facets (Spec D §5.2).`
- `passive_facet_crossing_bonuses(sheet: 'object', target: 'ModifierTarget') -> 'int' - Sum ConditionModifierEffect from FACET thread crossing choices (wear-gated).`
- `passive_mantle_bonuses(sheet: 'object', target: 'ModifierTarget') -> 'int' - Sum tier-0 FLAT_BONUS contributions from attuned mantle threads (Spec D §5.2).`
- `passive_mantle_crossing_bonuses(sheet: 'object', target: 'ModifierTarget') -> 'int' - Sum ConditionModifierEffect from MANTLE thread crossing choices (always-on).`
- `passive_motif_style_bonuses(sheet: 'object', target: 'ModifierTarget') -> 'int' - Coherence bonus for ``target``'s resonance (Spec D §5.3). Thin wrapper over`
- `power_flat_bonus_for_resonance(sheet: 'object', resonance_id: 'int') -> 'int' - Sum POWER-category flat modifiers (distinctions) applicable to ``resonance_id``.`
- `prerequisites_met(prereqs: 'Iterable[Prerequisite]', caster: 'ObjectDB', target: 'ObjectDB') -> 'bool' - True if target satisfies every one of prereqs (all() semantics; empty = True).`
- `preview_check_difficulty(character: 'ObjectDB', check_type: 'CheckType', target_difficulty: int = 0, extra_modifiers: int = 0, *, stat_override: str | int | None = None) -> int - Preview the rank difference for a check without rolling.`
- `property_damage_bonus(target: 'ObjectDB', damage_type: 'DamageType | None') -> 'int' - Sum PropertyDamageModifier.modifier_value for target's active Properties.`
- `role_base_bonus_for_target(role: 'CovenantRole', target: 'ModifierTarget', character_level: 'int') -> 'int' - Authored covenant-role bonus for ``target``, scaled by character level (#985).`
- `stage_property(target: 'ObjectDB', property_: 'Property', value: 'int' = 1) -> 'ObjectProperty' - GM improv: attach or refresh a Property on ``target`` (#2503).`
- `update_distinction_rank(character_distinction: 'CharacterDistinction') -> 'None' - Update CharacterModifier values when rank changes.`
- `volatile_object_property(target: 'ObjectDB') -> 'ObjectProperty | None' - Return the ``ObjectProperty`` making *target* volatile (detonatable), or None.`
- `vow_stat_scaling_bonus(sheet: 'object', target: 'ModifierTarget') -> 'int' - Sum the vow-driven stat scaling across engaged PRIMARY roles (#2022).`
- `worn_quality_aggregate(rows: 'Iterable[object]') -> 'Decimal' - Sum (item_quality_multiplier × attachment_quality_multiplier) over worn rows.`



## world.military

### Army
**Foreign Keys:**
  - commander -> character_sheets.CharacterSheet [FK] (nullable)
  - campaign_story -> stories.Story [FK] (nullable)
  - covenant -> covenants.Covenant [FK] (nullable)
  - units -> military.MilitaryUnit [M2M]
**Pointed to by:**
  - army_memberships <- military.ArmyMembership

### ArmyMembership
**Foreign Keys:**
  - army -> military.Army [FK]
  - military_unit -> military.MilitaryUnit [FK]

### MilitaryUnit
**Foreign Keys:**
  - owner_org -> societies.Organization [FK] (nullable)
  - commander -> character_sheets.CharacterSheet [FK] (nullable)
  - summoned_by -> character_sheets.CharacterSheet [FK] (nullable)
  - properties -> mechanics.Property [M2M]
  - capabilities -> conditions.CapabilityType [M2M]
**Pointed to by:**
  - battle_units <- battles.BattleUnit
  - capability_values <- military.MilitaryUnitCapability
  - armies <- military.Army
  - army_memberships <- military.ArmyMembership

### MilitaryUnitCapability
**Foreign Keys:**
  - unit -> military.MilitaryUnit [FK]
  - capability -> conditions.CapabilityType [FK]

### Service Functions
- `add_unit_to_army(*, army: 'Army', military_unit: 'MilitaryUnit') -> 'ArmyMembership' - Add a MilitaryUnit to an Army.`
- `create_military_unit(*, name: 'str', descriptor: 'str' = '', owner_org=None, commander=None, quality: 'str' = 'trained', strength: 'int' = 100, morale: 'int' = 70, individual_count: 'int | None' = None) -> 'MilitaryUnit' - Create a persistent MilitaryUnit.`
- `disband_army(*, army: 'Army') -> 'None' - Disband an army: mark all active memberships as left, set disbanded_at.`
- `form_army(*, name: 'str', commander=None, campaign_story=None, covenant=None, units: 'list[MilitaryUnit] | None' = None) -> 'Army' - Create an Army and optionally add units to it.`
- `remove_unit_from_army(*, army: 'Army', military_unit: 'MilitaryUnit') -> 'None' - Remove a MilitaryUnit from an Army (set left_at).`


## world.missions

### MissionAssistPattern
**Foreign Keys:**
  - capability -> conditions.CapabilityType [FK] (nullable)
  - support_check_type -> checks.CheckType [FK]
  - complication_consequence -> checks.Consequence [FK] (nullable)
  - check_types -> checks.CheckType [M2M]
  - challenge_categories -> mechanics.ChallengeCategory [M2M]

### MissionCategory
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
**Pointed to by:**
  - situational_perks <- covenants.VowSituationalPerk
  - templates <- missions.MissionTemplate

### MissionDeedRecord
**Foreign Keys:**
  - instance -> missions.MissionInstance [FK]
  - actor -> character_sheets.CharacterSheet [FK]
  - node -> missions.MissionNode [FK]
  - option -> missions.MissionOption [FK]
  - outcome -> traits.CheckOutcome [FK] (nullable)
  - route_candidate -> missions.MissionOptionRouteCandidate [FK] (nullable)
  - legend_entries -> societies.LegendEntry [M2M]
**Pointed to by:**
  - encounters <- combat.CombatEncounter
  - reward_lines <- missions.MissionDeedRewardLine
  - queued_rewards <- missions.MissionRewardQueue
  - explaining_secrets <- secrets.Secret

### MissionDeedRewardLine
**Foreign Keys:**
  - deed -> missions.MissionDeedRecord [FK]
  - recipient -> character_sheets.CharacterSheet [FK]
  - resonance -> magic.Resonance [FK] (nullable)
  - item_template -> items.ItemTemplate [FK] (nullable)
  - followon_offer -> npc_services.NPCServiceOffer [FK] (nullable)
  - project_contribution -> projects.Contribution [FK] (nullable)
**Pointed to by:**
  - resonance_grants <- magic.ResonanceGrant

### MissionGiver
**Foreign Keys:**
  - target -> evennia.ObjectDB [FK] (nullable)
  - org -> societies.Organization [FK] (nullable)
  - templates -> missions.MissionTemplate [M2M]
**Pointed to by:**
  - cooldowns <- missions.MissionGiverCooldown

### MissionGiverCooldown
**Foreign Keys:**
  - giver -> missions.MissionGiver [FK]
  - character -> character_sheets.CharacterSheet [FK]

### MissionGroupBallot
**Foreign Keys:**
  - instance -> missions.MissionInstance [FK]
  - node -> missions.MissionNode [FK]
  - participant -> missions.MissionParticipant [FK]
  - picked_option -> missions.MissionOption [FK]
  - picked_approach -> mechanics.ChallengeApproach [FK] (nullable)
  - voted_option -> missions.MissionOption [FK] (nullable)

### MissionInstance
**Foreign Keys:**
  - template -> missions.MissionTemplate [FK]
  - current_node -> missions.MissionNode [FK] (nullable)
  - spawned_room -> evennia_extensions.RoomProfile [FK] (nullable)
  - anchor_room -> evennia_extensions.RoomProfile [FK] (nullable)
  - source_beat -> stories.Beat [FK] (nullable)
  - source_offer -> npc_services.NPCServiceOffer [FK] (nullable)
  - accepted_as_persona -> scenes.Persona [FK] (nullable)
  - rescue_target -> character_sheets.CharacterSheet [FK] (nullable)
  - target_project -> projects.Project [FK] (nullable)
**Pointed to by:**
  - source_crisis <- societies.DomainCrisis
  - participants <- missions.MissionParticipant
  - invites <- missions.MissionInvite
  - snapshots <- missions.MissionNodeSnapshot
  - group_ballots <- missions.MissionGroupBallot
  - deeds <- missions.MissionDeedRecord
  - support_declarations <- missions.MissionSupportDeclaration
  - tales <- missions.MissionRunTale
  - task_fulfillments <- tasking.TaskFulfillment

### MissionInvite
**Foreign Keys:**
  - instance -> missions.MissionInstance [FK]
  - target_persona -> scenes.Persona [FK]
  - invited_by -> scenes.Persona [FK] (nullable)

### MissionNode
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - template -> missions.MissionTemplate [FK]
  - target_area -> areas.Area [FK] (nullable)
  - allowed_riders -> checks.Consequence [M2M]
  - locations -> evennia_extensions.RoomProfile [M2M]
**Pointed to by:**
  - options <- missions.MissionOption
  - support_options <- missions.MissionNodeSupportOption

### MissionNodeSnapshot
**Foreign Keys:**
  - instance -> missions.MissionInstance [FK]
  - node -> missions.MissionNode [FK]
  - participant -> missions.MissionParticipant [FK]
**Pointed to by:**
  - support_declaration <- missions.MissionSupportDeclaration

### MissionNodeSupportOption
**Foreign Keys:**
  - node -> missions.MissionNode [FK]
  - capability -> conditions.CapabilityType [FK] (nullable)
  - support_check_type -> checks.CheckType [FK]
  - complication_consequence -> checks.Consequence [FK] (nullable)

### MissionOption
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - node -> missions.MissionNode [FK]
  - authored_check_type -> checks.CheckType [FK] (nullable)
  - branch_target -> missions.MissionNode [FK] (nullable)
  - challenge -> mechanics.ChallengeTemplate [FK] (nullable)
  - locations -> evennia_extensions.RoomProfile [M2M]
**Pointed to by:**
  - opponent_lines <- missions.MissionOptionOpponentLine
  - routes <- missions.MissionOptionRoute

### MissionOptionOpponentLine
**Foreign Keys:**
  - option -> missions.MissionOption [FK]
  - creature_template -> combat.CreatureTemplate [FK]

### MissionOptionRoute
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - option -> missions.MissionOption [FK]
  - outcome_tier -> traits.CheckOutcome [FK] (nullable)
  - target_node -> missions.MissionNode [FK] (nullable)
  - consequence -> checks.Consequence [FK] (nullable)
**Pointed to by:**
  - candidates <- missions.MissionOptionRouteCandidate
  - reward_templates <- missions.MissionOptionRouteReward
  - renown_awards <- missions.MissionRenownAward

### MissionOptionRouteCandidate
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - route -> missions.MissionOptionRoute [FK]
  - target_node -> missions.MissionNode [FK]
  - consequence -> checks.Consequence [FK] (nullable)
**Pointed to by:**
  - reward_templates <- missions.MissionOptionRouteReward

### MissionOptionRouteReward
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - route -> missions.MissionOptionRoute [FK] (nullable)
  - candidate -> missions.MissionOptionRouteCandidate [FK] (nullable)
  - resonance -> magic.Resonance [FK] (nullable)
  - item_template -> items.ItemTemplate [FK] (nullable)
  - followon_offer -> npc_services.NPCServiceOffer [FK] (nullable)

### MissionParticipant
**Foreign Keys:**
  - instance -> missions.MissionInstance [FK]
  - character -> character_sheets.CharacterSheet [FK]
**Pointed to by:**
  - group_ballots <- missions.MissionGroupBallot
  - support_declarations <- missions.MissionSupportDeclaration
  - tales <- missions.MissionRunTale

### MissionRenownAward
**Foreign Keys:**
  - route -> missions.MissionOptionRoute [FK]
  - archetypes -> societies.PhilosophicalArchetype [M2M]

### MissionRewardQueue
**Foreign Keys:**
  - deed -> missions.MissionDeedRecord [FK]
  - line -> missions.MissionDeedRewardLine [FK]

### MissionRiskAcknowledgement
**Foreign Keys:**
  - offer -> npc_services.NPCServiceOffer [FK]
  - persona -> scenes.Persona [FK]

### MissionRunTale
**Foreign Keys:**
  - instance -> missions.MissionInstance [FK]
  - participant -> missions.MissionParticipant [FK]

### MissionSupportDeclaration
**Foreign Keys:**
  - instance -> missions.MissionInstance [FK]
  - snapshot -> missions.MissionNodeSnapshot [FK]
  - participant -> missions.MissionParticipant [FK]
  - pattern -> missions.MissionAssistPattern [FK] (nullable)
  - support_option -> missions.MissionNodeSupportOption [FK] (nullable)
  - outcome -> traits.CheckOutcome [FK] (nullable)

### MissionTemplate
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - created_in_era -> stories.Era [FK] (nullable)
  - report_to_role -> npc_services.NPCRole [FK] (nullable)
  - categories -> missions.MissionCategory [M2M]
**Pointed to by:**
  - clues <- clues.Clue
  - crisis_options <- societies.DomainCrisisTypeOption
  - situational_perks <- covenants.VowSituationalPerk
  - offer_details <- npc_services.MissionOfferDetails
  - nodes <- missions.MissionNode
  - instances <- missions.MissionInstance
  - givers <- missions.MissionGiver
  - story_scenario <- stories.StoryScenario
  - task_templates <- tasking.TaskTemplate

### Service Functions
- `apply_deed_rewards(deed: 'MissionDeedRecord', *, skip_unbuilt: 'bool' = False, room: 'ObjectDB | None' = None, skip_criminal: 'bool' = False) -> 'ApplyDeedRewardsResult' - Route every emitted :class:`MissionDeedRewardLine` on ``deed`` downstream.`
- `apply_mission_reward_batch() -> 'RewardBatchResult' - Walk every ``applied=False`` :class:`MissionRewardQueue` row and try to grant it.`
- `beat_for(instance: 'MissionInstance', character: 'ObjectDB') -> 'BeatView | None' - The current beat as ``character`` sees it; None when the run is done.`
- `build_group_option_list(instance: 'MissionInstance', node: 'MissionNode') -> 'list[PresentedOption]' - Union of every participant's Phase-3 option list at ``node``.`
- `build_option_list(instance: 'MissionInstance', node: 'MissionNode', viewer: 'MissionParticipant') -> 'list[PresentedOption]' - Surface the options the acting ``viewer`` can take at ``node``.`
- `contract_holder(instance: 'MissionInstance') -> 'MissionParticipant' - Return the instance's single contract-holding participant.`
- `emit_candidate_rewards(instance: 'MissionInstance', candidate: 'MissionOptionRouteCandidate', deed: 'MissionDeedRecord') -> 'list[MissionDeedRewardLine]' - Emit a fired random-set candidate's own reward bundle (#941).`
- `emit_terminal_rewards(instance: 'MissionInstance', route: 'MissionOptionRoute', deed: 'MissionDeedRecord') -> 'list[MissionDeedRewardLine]' - Emit one :class:`MissionDeedRewardLine` per (template × recipient).`
- `enter_node(instance: 'MissionInstance', node: 'MissionNode') -> 'None' - Record entry into ``node`` and advance the run's position.`
- `invite_to_mission(instance: 'MissionInstance', holder_persona: 'Persona', invitee_persona: 'Persona') -> 'MissionInvite' - Create a PENDING invite for ``invitee_persona`` to join ``instance``.`
- `journal_for(character: 'ObjectDB') -> 'list[JournalEntry]' - Return one :class:`JournalEntry` per mission this character is in.`
- `on_mission_complete_for_beat(instance: 'MissionInstance', *, route: 'MissionOptionRoute | None' = None, option: 'MissionOption | None' = None) -> 'MissionBeatTriggerRecord | None' - Record a Mission → Beat terminal trigger and complete the linked Beat.`
- `resolve_beat_option(instance: 'MissionInstance', character: 'ObjectDB', *, option_id: 'int', approach_id: 'int | None' = None) -> 'ResolvedBeat' - Resolve the chosen option for ``character``; deliver both narratives.`
- `resolve_group_node(instance: 'MissionInstance', node: 'MissionNode') -> 'list[MissionDeedRecord]' - Resolve a group ``node`` from its collected ``MissionGroupBallot`` rows (#1036).`
- `resolve_option(instance: 'MissionInstance', node: 'MissionNode', option: 'MissionOption', actor: 'MissionParticipant', *, chosen_approach: 'ChallengeApproach | None' = None, advance: 'bool' = True, extra_modifiers: 'int' = 0) -> 'MissionDeedRecord' - Resolve ``actor`` taking ``option`` at ``node``; return its deed.`
- `respond_to_mission_invite(invite: 'MissionInvite', decision: 'MissionInvite.Response') -> 'MissionParticipant | None' - Resolve a PENDING invite. On ACCEPT, calls ``share_mission``.`
- `share_mission(instance: 'MissionInstance', other_character: 'ObjectDB') -> 'MissionParticipant' - Add ``other_character`` as a non-holder participant to ``instance``.`
- `staff_assign_mission(template: 'MissionTemplate', character: 'ObjectDB', *, project: 'Project | None' = None, persona: 'Persona | None' = None) -> 'MissionInstance' - Staff-power: drop a mission on a character without a giver context.`
- `validate_mission_option(option: 'MissionOption') -> 'None' - Validate post-save invariants for ``option``.`


## world.narrative

### AmbientEmit
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - area -> areas.Area [FK] (nullable)
  - room_profile -> evennia_extensions.RoomProfile [FK] (nullable)

### AmbientEmoteCondition
**Foreign Keys:**
  - line -> narrative.AmbientEmoteLine [FK]
  - species -> species.Species [FK] (nullable)
  - resonance -> magic.Resonance [FK] (nullable)
  - distinction -> distinctions.Distinction [FK] (nullable)
  - perceiving_society -> societies.Society [FK] (nullable)

### AmbientEmoteLine
**Foreign Keys:**
  - area -> areas.Area [FK] (nullable)
  - room_profile -> evennia_extensions.RoomProfile [FK] (nullable)
**Pointed to by:**
  - conditions <- narrative.AmbientEmoteCondition

### AmbientStirLine

### Gemit
**Foreign Keys:**
  - sender_account -> evennia.AccountDB [FK] (nullable)
  - related_era -> stories.Era [FK] (nullable)
  - related_story -> stories.Story [FK] (nullable)
  - reach_societies -> societies.Society [M2M]
  - reach_organizations -> societies.Organization [M2M]

### NarrativeMessage
**Foreign Keys:**
  - sender_account -> evennia.AccountDB [FK] (nullable)
  - related_story -> stories.Story [FK] (nullable)
  - related_beat_completion -> stories.BeatCompletion [FK] (nullable)
  - related_episode_resolution -> stories.EpisodeResolution [FK] (nullable)
**Pointed to by:**
  - deliveries <- narrative.NarrativeMessageDelivery

### NarrativeMessageDelivery
**Foreign Keys:**
  - message -> narrative.NarrativeMessage [FK]
  - recipient_character_sheet -> character_sheets.CharacterSheet [FK]

### UserCategoryMute
**Foreign Keys:**
  - account -> evennia.AccountDB [FK]

### UserStoryMute
**Foreign Keys:**
  - account -> evennia.AccountDB [FK]
  - story -> stories.Story [FK]

### Service Functions
- `broadcast_gemit(*, body: 'str', sender_account: 'AccountDB', reach: 'str' = GemitReach.GAME_WIDE, societies: 'Iterable[Society] | None' = None, organizations: 'Iterable[Organization] | None' = None, related_era: 'Era | None' = None, related_story: 'Story | None' = None) -> 'Gemit' - Create a Gemit and push it to its ``reach`` audience in green (#1450).`
- `deliver_queued_messages(character_sheet: 'CharacterSheet') -> 'int' - Push all undelivered messages for this character and mark delivered.`
- `emit_ambient_room_stir(room: 'ObjectDB', *, exclude: 'ObjectDB | None' = None) -> 'None' - Send a source-ambiguous ambient line to a room's bystanders (#885).`
- `is_category_muted(*, account: 'AccountDB', category: 'str') -> 'bool' - Whether an account has muted a narrative category's live push.`
- `send_narrative_message(*, recipients: 'Iterable[CharacterSheet]', body: 'str', category: 'str', sender_account: 'AccountDB | None' = None, ooc_note: 'str' = '', related_story: 'Story | None' = None, related_beat_completion: 'BeatCompletion | None' = None, related_episode_resolution: 'EpisodeResolution | None' = None) -> 'NarrativeMessage' - Create a NarrativeMessage and fan out deliveries to each recipient.`
- `send_story_ooc_message(*, story: 'Story', sender_account: 'AccountDB', body: 'str', ooc_note: 'str' = '') -> 'NarrativeMessage' - Lead GM or staff sends an OOC notice to all participants of a story.`
- `set_category_mute(*, account: 'AccountDB', category: 'str', muted: 'bool') -> 'None' - Mute or unmute a narrative category's real-time push for an account (#1522).`


## world.npc_services

### ClueRevealOfferDetails
**Foreign Keys:**
  - offer -> npc_services.NPCServiceOffer [OneToOne]
  - clue -> clues.Clue [FK]

### CourtGrantOfferDetails
**Foreign Keys:**
  - offer -> npc_services.NPCServiceOffer [OneToOne]
  - covenant -> covenants.Covenant [FK]

### DistinctionRegardSeed
**Foreign Keys:**
  - distinction -> distinctions.Distinction [FK]
  - npc_persona -> scenes.Persona [FK]

### ExpulsionBar
**Foreign Keys:**
  - room -> evennia_extensions.RoomProfile [FK]
  - barred_sheet -> character_sheets.CharacterSheet [FK]
  - imposed_by -> scenes.Persona [FK]

### Functionary
**Foreign Keys:**
  - role -> npc_services.NPCRole [FK]
  - room -> evennia_extensions.RoomProfile [FK]
  - persona -> scenes.Persona [FK] (nullable)
**Pointed to by:**
  - kinspeople <- roster.Kinsperson
  - promotions <- assets.NPCAsset
  - assignments <- npc_services.NPCAssignment
  - reaction_lines <- npc_services.NPCReactionLine

### LoanOfferDetails
**Foreign Keys:**
  - offer -> npc_services.NPCServiceOffer [OneToOne]
  - creditor_organization -> societies.Organization [FK] (nullable)

### MissionOfferDetails
**Foreign Keys:**
  - offer -> npc_services.NPCServiceOffer [OneToOne]
  - role -> npc_services.NPCRole [FK]
  - mission_template -> missions.MissionTemplate [FK]
  - source_beat -> stories.Beat [FK] (nullable)
  - target_project -> projects.Project [FK] (nullable)

### NPCAssignment
**Foreign Keys:**
  - functionary -> npc_services.Functionary [FK] (nullable)
  - npc_asset -> assets.NPCAsset [FK] (nullable)
  - room -> evennia_extensions.RoomProfile [FK]
  - assigned_by -> scenes.Persona [FK]
**Pointed to by:**
  - listener_post <- tasking.ListenerPost

### NPCReactionLine
**Foreign Keys:**
  - role -> npc_services.NPCRole [FK]
  - functionary -> npc_services.Functionary [FK] (nullable)

### NPCRole
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - faction_affiliation -> societies.Organization [FK] (nullable)
  - teaches_tradition -> magic.Tradition [FK] (nullable)
**Pointed to by:**
  - distinction_grants <- assets.DistinctionAssetGrant
  - permits_issued <- buildings.BuildingPermitDetails
  - functionaries <- npc_services.Functionary
  - staffing_lines <- npc_services.StaffingProfileLine
  - offers <- npc_services.NPCServiceOffer
  - role_cooldowns <- npc_services.NPCRoleCooldown
  - reaction_lines <- npc_services.NPCReactionLine
  - missions_reported_to <- missions.MissionTemplate

### NPCRoleCooldown
**Foreign Keys:**
  - role -> npc_services.NPCRole [FK]
  - persona -> scenes.Persona [FK]

### NPCServiceOffer
**Foreign Keys:**
  - role -> npc_services.NPCRole [FK]
  - check_type -> checks.CheckType [FK] (nullable)
**Pointed to by:**
  - asset_task_intel_details <- assets.AssetTaskIntelDetails
  - cooldowns <- npc_services.OfferCooldown
  - mission_offer_details <- npc_services.MissionOfferDetails
  - permit_offer_details <- npc_services.PermitOfferDetails
  - loan_offer_details <- npc_services.LoanOfferDetails
  - train_offer_details <- npc_services.TrainOfferDetails
  - court_grant_offer_details <- npc_services.CourtGrantOfferDetails
  - summonses <- npc_services.OfferSummons
  - styling_offer_details <- npc_services.StylingOfferDetails
  - profile_recording_offer_details <- npc_services.ProfileRecordingOfferDetails
  - clue_reveal_offer_details <- npc_services.ClueRevealOfferDetails
  - mission_risk_acknowledgements <- missions.MissionRiskAcknowledgement

### NPCStanding
**Foreign Keys:**
  - persona -> scenes.Persona [FK]
  - npc_persona -> scenes.Persona [FK]

### NameCulture
**Foreign Keys:**
  - area -> areas.Area [FK] (nullable)
  - society -> societies.Society [FK] (nullable)
**Pointed to by:**
  - entries <- npc_services.NameCultureEntry

### NameCultureEntry
**Foreign Keys:**
  - culture -> npc_services.NameCulture [FK]

### NpcPreference
**Foreign Keys:**
  - persona -> scenes.Persona [FK]
  - trait -> npc_services.PersonalityTrait [FK]

### NpcRegard
**Foreign Keys:**
  - holder_persona -> scenes.Persona [FK]
  - target_persona -> scenes.Persona [FK] (nullable)
  - target_organization -> societies.Organization [FK] (nullable)
  - target_society -> societies.Society [FK] (nullable)
**Pointed to by:**
  - events <- npc_services.NpcRegardEvent

### NpcRegardEvent
**Foreign Keys:**
  - regard -> npc_services.NpcRegard [FK]
  - source_pc_combat_action -> combat.CombatRoundAction [FK] (nullable)
  - source_npc_combat_action -> combat.CombatOpponentAction [FK] (nullable)
  - source_scene -> scenes.Scene [FK] (nullable)
  - source_stake_resolution -> stories.StakeResolution [FK] (nullable)

### OfferCooldown
**Foreign Keys:**
  - offer -> npc_services.NPCServiceOffer [FK]
  - persona -> scenes.Persona [FK]

### OfferSummons
**Foreign Keys:**
  - offer -> npc_services.NPCServiceOffer [FK]
  - target_persona -> scenes.Persona [FK]
  - created_by -> gm.GMProfile [FK] (nullable)

### PermitOfferDetails
**Foreign Keys:**
  - offer -> npc_services.NPCServiceOffer [OneToOne]
  - building_kind -> buildings.BuildingKind [FK] (nullable)
  - default_approved_wards -> areas.Area [M2M]

### PersonalityTrait
**Foreign Keys:**
  - eased_check -> checks.CheckType [FK] (nullable)
**Pointed to by:**
  - holders <- npc_services.NpcPreference

### ProfileRecordingOfferDetails
**Foreign Keys:**
  - offer -> npc_services.NPCServiceOffer [OneToOne]

### RecordedProfile
**Foreign Keys:**
  - persona -> scenes.Persona [FK]
  - era -> stories.Era [FK] (nullable)

### RegardEventConfig

### StaffingProfile
**Foreign Keys:**
  - building_kind -> buildings.BuildingKind [OneToOne]
**Pointed to by:**
  - lines <- npc_services.StaffingProfileLine

### StaffingProfileLine
**Foreign Keys:**
  - profile -> npc_services.StaffingProfile [FK]
  - role -> npc_services.NPCRole [FK]

### StylingOfferDetails
**Foreign Keys:**
  - offer -> npc_services.NPCServiceOffer [OneToOne]
  - trait -> forms.FormTrait [FK]
  - target_option -> forms.FormTraitOption [FK]

### TrainOfferDetails
**Foreign Keys:**
  - offer -> npc_services.NPCServiceOffer [OneToOne]
  - technique -> magic.Technique [FK]

### Service Functions
- `adjust_npc_affection(pc_persona, npc_persona, *, delta: 'int') -> 'int' - Apply a disposition ``delta`` to the (pc_persona, npc_persona) standing.`
- `available_offers(session: 'InteractionSession', *, pool_count: 'int | None' = None) -> 'list[NPCServiceOffer]' - Return offers the PC can currently see/select, in stable order.`
- `complete_recorded_profile(profile: 'RecordedProfile', text: 'str') -> 'RecordedProfile' - Finalize a COMMISSIONED sitting: the write-up arrives (#2632).`
- `dispatch_offer_effect(offer: 'NPCServiceOffer', persona: 'Persona') -> 'EffectResult' - Look up the registered handler for ``offer.kind`` and invoke it.`
- `end_interaction(session: 'InteractionSession') -> 'None' - Close the session and persist final affection for class 2-4 NPCs.`
- `evaluate(rule: 'dict', ctx: 'PredicateContext') -> 'bool' - Evaluate a predicate rule tree against an acting-character context.`
- `incur_npc_debt(standing: 'NPCStanding', amount: 'int', *, current_affection: 'int', current_missions_completed: 'int') -> 'NPCStanding' - Add ``amount`` to ``standing.debt`` and re-stamp the repayment baseline.`
- `mission_pool_count(*, role: 'NPCRole', persona: 'Persona', npc_persona: 'Persona | None') -> 'int' - POOL offer count to surface for ``persona`` at this NPC (#726, #1020).`
- `outstanding_debt(standing: 'NPCStanding', *, current_affection: 'int', current_missions_completed: 'int', affection_divisor: 'int', mission_divisor: 'int') -> 'int' - Derive-on-read: net ``standing.debt`` against progress since the baseline.`
- `perform_check_with_modifiers(character: 'ObjectDB', check_type: 'CheckType', target_difficulty: int = 0, extra_modifiers: int = 0, effort_level: str | None = None, fatigue_penalty: int = 0, specialization: 'Specialization | None' = None, *, situation_ctx: 'SituationContext | None' = None, level_override: int | None = None, scene: 'Scene | None' = None, extra_contributions: 'list[ModifierContribution] | None' = None, skip_fashion: bool = False, stat_override: str | int | None = None) -> world.checks.types.CheckResult - Run a check with all character modifiers gathered automatically.`
- `record_petition_outcome(standing: 'NPCStanding', *, succeeded: 'bool', escalation_threshold: 'int') -> 'bool' - Increment/reset ``consecutive_failed_petitions``; report threshold crossing.`
- `resolve_offer(session: 'InteractionSession', offer: 'NPCServiceOffer') -> 'EffectResult' - Grant ``offer`` in ``session`` — dispatch its effect, update rapport.`
- `serialize_npc_session_state(session: 'InteractionSession', *, last_result_message: 'str' = '') -> 'dict' - Compose the response payload from a (live or freshly-closed) session.`
- `start_interaction(*, role: 'NPCRole', persona: 'Persona', character: 'Character', npc_persona: 'Persona | None' = None) -> 'InteractionSession' - Begin an interaction with an NPC of ``role``.`
- `template_visible_to(template: 'MissionTemplate', character: 'ObjectDB', *, persona: 'Persona | None' = None) -> 'bool' - True if ``character`` may see / be offered ``template``.`


## world.player_submissions

### BugReport
**Foreign Keys:**
  - reporter_account -> evennia.AccountDB [FK]
  - reporter_persona -> scenes.Persona [FK]
  - location -> evennia.ObjectDB [FK] (nullable)

### CheckProposal
**Foreign Keys:**
  - submitted_by_account -> evennia.AccountDB [FK]
  - submitted_by_persona -> scenes.Persona [FK]
  - scene -> scenes.Scene [FK] (nullable)
  - reviewer -> evennia.AccountDB [FK] (nullable)

### Petition
**Foreign Keys:**
  - account -> evennia.AccountDB [FK]
  - scene -> scenes.Scene [FK] (nullable)
  - subject_character -> character_sheets.CharacterSheet [FK] (nullable)

### PlayerFeedback
**Foreign Keys:**
  - reporter_account -> evennia.AccountDB [FK]
  - reporter_persona -> scenes.Persona [FK]
  - location -> evennia.ObjectDB [FK] (nullable)

### PlayerReport
**Foreign Keys:**
  - reporter_account -> evennia.AccountDB [FK]
  - reported_account -> evennia.AccountDB [FK]
  - reporter_persona -> scenes.Persona [FK]
  - reported_persona -> scenes.Persona [FK]
  - scene -> scenes.Scene [FK] (nullable)
  - interaction -> scenes.Interaction [FK] (nullable)
  - location -> evennia.ObjectDB [FK] (nullable)

### SubmitterStanding
**Foreign Keys:**
  - account -> evennia.AccountDB [OneToOne]

### SystemErrorReport
**Foreign Keys:**
  - actor_persona -> scenes.Persona [FK] (nullable)

### Service Functions
- `kudos_total_for(account: 'AccountDB') -> 'int' - The sender's kudos total — the staff inbox's sort key (#2288).`
- `record_resolution(account: 'AccountDB', status: 'str') -> 'SubmitterStanding' - Stamp the submitter's track record when staff resolve their submission.`
- `report_error(exc: 'BaseException', *, label: 'str', actor: 'ObjectDB | None' = None) -> 'None' - Capture an exception as a deduplicated ``SystemErrorReport`` + a structured log.`
- `report_hidden_presence(*, reporter_account: 'AccountDB', reporter_persona: 'Persona', behavior_description: 'str', category: 'str') -> 'list[PlayerReport]' - File PlayerReports against the concealed occupants of the reporter's room (#3288).`
- `resolve_petition(petition: 'Petition', *, status: 'str', staff_notes: 'str' = '') -> 'Petition' - Staff close a petition; the outcome feeds the track record.`
- `run_safely(label: 'str', fn: 'Callable[[], object]', *, actor: 'ObjectDB | None' = None) -> 'object' - Run an optional / best-effort callable; on failure capture + notify, never raise.`
- `sender_context(account: 'AccountDB') -> 'dict' - Kudos + standing columns shown beside every submission.`
- `set_ignored(account: 'AccountDB', *, ignored: 'bool') -> 'SubmitterStanding' - The perma-ignore bit: submissions persist but never surface. Silent.`
- `standing_for(account: 'AccountDB') -> 'SubmitterStanding'`
- `submit_check_proposal(account: 'AccountDB', persona: 'Persona', *, proposed_name: 'str', intent: 'str', situation_text: 'str', suggested_traits_text: 'str' = '', scene: 'Scene | None' = None) -> 'CheckProposal' - Create a ``CheckProposal`` row, routed to the staff inbox (#3295).`
- `submit_petition(account: 'AccountDB', *, category: 'str', description: 'str', scene: 'Scene | None' = None, subject_character: 'ObjectDB | None' = None) -> 'Petition' - File the one open petition an account may hold — emergency-only.`


## world.predators

### AfflictionSign
**Foreign Keys:**
  - domain -> societies.Domain [FK]
  - crisis_type -> societies.DomainCrisisType [FK]

### MenaceEvent
**Foreign Keys:**
  - band -> predators.PredatorBand [FK]

### PredatorBand
**Foreign Keys:**
  - kind -> predators.PredatorKind [FK]
  - home_region -> areas.Area [FK]
  - prey -> societies.Organization [FK] (nullable)
**Pointed to by:**
  - authored_crises <- societies.DomainCrisis
  - events <- predators.MenaceEvent
  - org_tasks_targeting <- tasking.OrgTask

### PredatorKind
**Pointed to by:**
  - bands <- predators.PredatorBand

### Service Functions
- `has_regional_peace(org: 'Organization', band: 'PredatorBand') -> 'bool' - Consort-derived regional peace (#3091 ruling): a house whose family holds`
- `sabotage_band(band: 'PredatorBand') -> 'PredatorBand' - The spy payout's knife in the dark — smaller burn, same ladder knockdown.`
- `select_prey(band: 'PredatorBand') -> 'Organization | None' - The weakest-PERCEIVED landed org in reach, honoring regional peace.`
- `strike_band(band: 'PredatorBand', *, strength_burn: 'int' = 25, stages: 'int' = 1) -> 'PredatorBand' - Counterplay landed: burn strength, knock the ladder down, maybe break them.`
- `weekly_affliction_tick(*, rng: 'random.Random | None' = None) -> 'dict[str, int]'`
- `weekly_menace_tick(*, rng: 'random.Random | None' = None) -> 'dict[str, int]' - The weekly heartbeat: spawn, stalk, pressure, and (slowly) escalate.`



## world.progression

### AchievementRequirement
**Foreign Keys:**
  - class_level_unlock -> progression.ClassLevelUnlock [FK] (nullable)
  - thread_crossing_threshold -> magic.ThreadCrossingThreshold [FK] (nullable)
  - path -> classes.Path [FK] (nullable)
  - achievement -> achievements.Achievement [FK]

### CharacterPathHistory
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - path -> classes.Path [FK]

### CharacterUnlock
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - character_class -> classes.CharacterClass [FK]

### CharacterXP
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]

### CharacterXPTransaction
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]

### ClassLevelAdvancement
**Foreign Keys:**
  - scene -> scenes.Scene [FK] (nullable)
  - declaration_interaction -> scenes.Interaction [FK] (nullable)
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - character_class -> classes.CharacterClass [FK]
  - officiant -> character_sheets.CharacterSheet [FK] (nullable)
  - ritual -> magic.Ritual [FK] (nullable)
  - witnesses -> scenes.Persona [M2M]

### ClassLevelRequirement
**Foreign Keys:**
  - class_level_unlock -> progression.ClassLevelUnlock [FK] (nullable)
  - thread_crossing_threshold -> magic.ThreadCrossingThreshold [FK] (nullable)
  - path -> classes.Path [FK] (nullable)
  - character_class -> classes.CharacterClass [FK]

### ClassLevelUnlock
**Foreign Keys:**
  - character_class -> classes.CharacterClass [FK]
**Pointed to by:**
  - traitrequirement_requirements <- progression.TraitRequirement
  - levelrequirement_requirements <- progression.LevelRequirement
  - classlevelrequirement_requirements <- progression.ClassLevelRequirement
  - multiclassrequirement_requirements <- progression.MultiClassRequirement
  - achievementrequirement_requirements <- progression.AchievementRequirement
  - relationshiprequirement_requirements <- progression.RelationshipRequirement
  - legendrequirement_requirements <- progression.LegendRequirement
  - tierrequirement_requirements <- progression.TierRequirement
  - itemrequirement_requirements <- progression.ItemRequirement
  - majorgifttechniquerequirement_requirements <- progression.MajorGiftTechniqueRequirement
  - codexknowledgerequirement_requirements <- progression.CodexKnowledgeRequirement

### ClassXPCost
**Foreign Keys:**
  - character_class -> classes.CharacterClass [FK]
  - cost_chart -> progression.XPCostChart [FK]

### CodexKnowledgeRequirement
**Foreign Keys:**
  - class_level_unlock -> progression.ClassLevelUnlock [FK] (nullable)
  - thread_crossing_threshold -> magic.ThreadCrossingThreshold [FK] (nullable)
  - path -> classes.Path [FK] (nullable)
  - codex_entry -> codex.CodexEntry [FK]

### CohortEnrollment
**Foreign Keys:**
  - cohort -> progression.DuranceCohort [FK]
  - persona -> scenes.Persona [FK]
  - enrollment_scene -> scenes.Scene [FK] (nullable)

### DevelopmentPoints
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - trait -> traits.Trait [FK]

### DevelopmentTransaction
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - trait -> traits.Trait [FK]
  - scene -> scenes.Scene [FK] (nullable)
  - gm -> evennia.AccountDB [FK] (nullable)
  - game_week -> game_clock.GameWeek [FK] (nullable)

### DuranceCohort
**Foreign Keys:**
  - organization -> societies.Organization [FK]
  - enrollment_scene -> scenes.Scene [FK] (nullable)
**Pointed to by:**
  - members <- character_sheets.CharacterSheet
  - enrollments <- progression.CohortEnrollment

### DuranceTrainingSite
**Foreign Keys:**
  - room_profile -> evennia_extensions.RoomProfile [FK]
  - officiant -> character_sheets.CharacterSheet [FK]
  - training_path -> classes.Path [FK] (nullable)

### ExperiencePointsData
**Foreign Keys:**
  - account -> evennia.AccountDB [OneToOne]

### ItemRequirement
**Foreign Keys:**
  - class_level_unlock -> progression.ClassLevelUnlock [FK] (nullable)
  - thread_crossing_threshold -> magic.ThreadCrossingThreshold [FK] (nullable)
  - path -> classes.Path [FK] (nullable)
  - item_template -> items.ItemTemplate [FK] (nullable)
  - min_touchstone_tier -> magic.ResonanceTier [FK] (nullable)
  - min_quality_tier -> items.QualityTier [FK] (nullable)

### KudosClaimCategory
**Pointed to by:**
  - transactions <- progression.KudosTransaction

### KudosDifficultyWeight

### KudosPointsData
**Foreign Keys:**
  - account -> evennia.AccountDB [OneToOne]

### KudosSourceCategory
**Pointed to by:**
  - transactions <- progression.KudosTransaction

### KudosTransaction
**Foreign Keys:**
  - account -> evennia.AccountDB [FK]
  - source_category -> progression.KudosSourceCategory [FK] (nullable)
  - claim_category -> progression.KudosClaimCategory [FK] (nullable)
  - awarded_by -> evennia.AccountDB [FK] (nullable)
  - character -> character_sheets.CharacterSheet [FK] (nullable)

### LegendRequirement
**Foreign Keys:**
  - class_level_unlock -> progression.ClassLevelUnlock [FK] (nullable)
  - thread_crossing_threshold -> magic.ThreadCrossingThreshold [FK] (nullable)
  - path -> classes.Path [FK] (nullable)

### LevelRequirement
**Foreign Keys:**
  - class_level_unlock -> progression.ClassLevelUnlock [FK] (nullable)
  - thread_crossing_threshold -> magic.ThreadCrossingThreshold [FK] (nullable)
  - path -> classes.Path [FK] (nullable)

### LevelStatPointSpend
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - trait -> traits.Trait [FK]

### MajorGiftTechniqueRequirement
**Foreign Keys:**
  - class_level_unlock -> progression.ClassLevelUnlock [FK] (nullable)
  - thread_crossing_threshold -> magic.ThreadCrossingThreshold [FK] (nullable)
  - path -> classes.Path [FK] (nullable)

### MaturationSpend
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - trait -> traits.Trait [FK]

### MaturationStatCap

### MultiClassLevel
**Foreign Keys:**
  - multi_class_requirement -> progression.MultiClassRequirement [FK]
  - character_class -> classes.CharacterClass [FK]

### MultiClassRequirement
**Foreign Keys:**
  - class_level_unlock -> progression.ClassLevelUnlock [FK] (nullable)
  - thread_crossing_threshold -> magic.ThreadCrossingThreshold [FK] (nullable)
  - path -> classes.Path [FK] (nullable)
  - required_classes -> classes.CharacterClass [M2M]
**Pointed to by:**
  - class_levels <- progression.MultiClassLevel

### PathIntent
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [OneToOne]
  - intended_path -> classes.Path [FK]

### RandomSceneCompletion
**Foreign Keys:**
  - account -> evennia.AccountDB [FK]
  - claimer_entry -> roster.RosterEntry [FK]
  - target_persona -> scenes.Persona [FK]

### RandomSceneTarget
**Foreign Keys:**
  - account -> evennia.AccountDB [FK]
  - target_persona -> scenes.Persona [FK]
  - game_week -> game_clock.GameWeek [FK]

### RelationshipRequirement
**Foreign Keys:**
  - class_level_unlock -> progression.ClassLevelUnlock [FK] (nullable)
  - thread_crossing_threshold -> magic.ThreadCrossingThreshold [FK] (nullable)
  - path -> classes.Path [FK] (nullable)
  - required_track_kind -> relationships.RelationshipTrack [FK] (nullable)

### TierRequirement
**Foreign Keys:**
  - class_level_unlock -> progression.ClassLevelUnlock [FK] (nullable)
  - thread_crossing_threshold -> magic.ThreadCrossingThreshold [FK] (nullable)
  - path -> classes.Path [FK] (nullable)

### TraitRatingUnlock
**Foreign Keys:**
  - trait -> traits.Trait [FK]

### TraitRequirement
**Foreign Keys:**
  - class_level_unlock -> progression.ClassLevelUnlock [FK] (nullable)
  - thread_crossing_threshold -> magic.ThreadCrossingThreshold [FK] (nullable)
  - path -> classes.Path [FK] (nullable)
  - trait -> traits.Trait [FK]

### TraitXPCost
**Foreign Keys:**
  - trait -> traits.Trait [FK]
  - cost_chart -> progression.XPCostChart [FK]

### WeeklyEngagementInitiator
**Foreign Keys:**
  - ledger -> progression.WeeklySocialEngagement [FK]
  - initiator_account -> evennia.AccountDB [FK]

### WeeklySkillUsage
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - trait -> traits.Trait [FK]
  - game_week -> game_clock.GameWeek [FK]

### WeeklySocialEngagement
**Foreign Keys:**
  - account -> evennia.AccountDB [OneToOne]
  - game_week -> game_clock.GameWeek [FK] (nullable)
**Pointed to by:**
  - initiators <- progression.WeeklyEngagementInitiator

### WeeklyVote
**Foreign Keys:**
  - voter -> evennia.AccountDB [FK]
  - game_week -> game_clock.GameWeek [FK]
  - author_account -> evennia.AccountDB [FK]

### WeeklyVoteBudget
**Foreign Keys:**
  - account -> evennia.AccountDB [FK]
  - game_week -> game_clock.GameWeek [FK]

### XPCostChart
**Pointed to by:**
  - cost_entries <- progression.XPCostEntry
  - class_costs <- progression.ClassXPCost
  - trait_costs <- progression.TraitXPCost

### XPCostEntry
**Foreign Keys:**
  - chart -> progression.XPCostChart [FK]

### XPTransaction
**Foreign Keys:**
  - account -> evennia.AccountDB [FK]
  - character -> character_sheets.CharacterSheet [FK] (nullable)
  - gm -> evennia.AccountDB [FK] (nullable)

### Service Functions
- `award_cg_conversion_xp(character: evennia.objects.models.ObjectDB, *, remaining_cg_points: int, conversion_rate: int) -> None - Award locked XP to a character for unspent CG points.`
- `award_check_development(character_sheet: 'CharacterSheet', check_type: 'CheckType', effort_level: 'str | None', path_level: 'int') -> 'list[tuple[str, int, int]]' - Award dp to traits used in a check.`
- `award_development_points(character_sheet: 'CharacterSheet', trait: 'Trait', source: 'str', amount: 'int', scene: 'Scene | None' = None, reason: 'str' = ProgressionReason.SCENE_AWARD, description: 'str' = '', gm: 'AccountDB | None' = None) -> 'DevelopmentTransaction' - Award development points to a character and automatically apply them.`
- `award_kudos(account: evennia.accounts.models.AccountDB, amount: int, source_category: world.progression.models.kudos.KudosSourceCategory, description: str, awarded_by: evennia.accounts.models.AccountDB | None = None, character: world.character_sheets.models.CharacterSheet | None = None) -> world.progression.types.AwardResult - Award kudos to an account with full audit trail.`
- `award_xp(account: 'AccountDB', amount: 'int', reason: 'str' = ProgressionReason.SYSTEM_AWARD, description: 'str' = '', gm: 'AccountDB | None' = None) -> 'XPTransaction' - Award XP to an account.`
- `calculate_check_dev_points(effort_level: 'str', path_level: 'int') -> 'int' - Calculate dp earned from a single check.`
- `calculate_level_up_requirements(character: 'ObjectDB', character_class: 'CharacterClass', target_level: 'int') -> 'LevelUpRequirements | dict[str, str]' - Calculate what's required to level up a character in a specific class.`
- `cast_vote(voter_account: evennia.accounts.models.AccountDB, target_type: str, target_id: int, author_account: evennia.accounts.models.AccountDB) -> world.progression.models.voting.WeeklyVote - Cast a vote on a piece of content.`
- `check_requirements_for_unlock(character: 'ObjectDB', unlock_target: 'ClassLevelUnlock') -> 'tuple[bool, list[str]]' - Check if a character meets all requirements for an unlock.`
- `claim_kudos(account: evennia.accounts.models.AccountDB, amount: int, claim_category: world.progression.models.kudos.KudosClaimCategory, description: str) -> world.progression.types.ClaimResult - Claim kudos from an account for conversion to rewards.`
- `claim_kudos_for_xp(account: evennia.accounts.models.AccountDB, amount: int, claim_category: world.progression.models.kudos.KudosClaimCategory, description: str = '') -> world.progression.types.KudosXPResult - Claim kudos and convert the reward to account-level XP.`
- `get_available_unlocks_for_character(character: 'ObjectDB') -> 'AvailableUnlocks' - Get all unlocks that a character could potentially purchase.`
- `get_development_suggestions_for_character(character: 'ObjectDB') -> 'dict[str, list[str]]' - Get development suggestions for a character based on their current traits.`
- `get_or_create_vote_budget(account: evennia.accounts.models.AccountDB, game_week: world.game_clock.models.GameWeek | None = None) -> world.progression.models.voting.WeeklyVoteBudget - Return the vote budget for the current week, creating with defaults if needed.`
- `get_or_create_xp_tracker(account: 'AccountDB') -> 'ExperiencePointsData' - Get or create XP tracker for an account.`
- `get_vote_state(voter_account: evennia.accounts.models.AccountDB, target_type: str, target_id: int) -> bool - Return whether the voter has an unprocessed vote for this target this week.`
- `get_votes_by_voter(voter_account: evennia.accounts.models.AccountDB) -> django.db.models.query.QuerySet - Return all unprocessed votes for the current week.`
- `increment_scene_bonus(account: evennia.accounts.models.AccountDB) -> None - Add 1 to scene_bonus_votes for the current week's budget (capped at 7).`
- `on_scene_finished(scene: world.scenes.models.Scene) -> None - Grant scene completion rewards and settle reaction windows.`
- `remove_vote(voter_account: evennia.accounts.models.AccountDB, target_type: str, target_id: int) -> None - Remove an unprocessed vote for the current week.`
- `spend_xp_on_unlock(character: 'ObjectDB', unlock_target: 'ClassLevelUnlock', gm: 'AccountDB | None' = None) -> 'tuple[bool, str, CharacterUnlock | None]' - Spend XP to unlock something for a character.`


## world.projects

### Contribution
**Foreign Keys:**
  - project -> projects.Project [FK]
  - contributor_persona -> scenes.Persona [FK]
  - item_instance -> items.ItemInstance [FK] (nullable)
  - check_outcome -> traits.CheckOutcome [FK] (nullable)
  - contribution_method -> projects.ContributionMethod [FK] (nullable)

### ContributionMethod
**Foreign Keys:**
  - check_type -> checks.CheckType [FK]
**Pointed to by:**
  - contributions <- projects.Contribution

### Project
**Foreign Keys:**
  - owner_persona -> scenes.Persona [FK]
  - outcome_tier -> traits.CheckOutcome [FK] (nullable)
  - resonance -> magic.Resonance [FK] (nullable)
**Pointed to by:**
  - cleanup_details <- areas.CleanupProjectDetails
  - city_defense_details <- battles.CityDefenseDetails
  - war_funding_details <- battles.WarFundingDetails
  - resulting_building <- buildings.Building
  - building_extension_details <- buildings.BuildingExtensionDetails
  - fortification_upgrade_details <- buildings.FortificationUpgradeDetails
  - building_renovation_details <- buildings.BuildingRenovationDetails
  - building_activation_details <- buildings.BuildingActivationDetails
  - building_preparation_details <- buildings.BuildingPreparationDetails
  - building_upgrade_details <- buildings.BuildingUpgradeDetails
  - interior_design_details <- buildings.InteriorDesignDetails
  - building_construction_details <- buildings.BuildingConstructionDetails
  - resulting_building_project_instance <- buildings.BuildingProjectInstance
  - ransom_captivities <- captivity.Captivity
  - research_details <- clues.ResearchProjectDetails
  - organization_gift_grants <- societies.OrganizationGiftGrant
  - gang_turf_details <- societies.GangTurfDetails
  - propaganda_details <- societies.PropagandaDetails
  - domain_improvement_details <- societies.DomainImprovementDetails
  - resonance_grants <- magic.ResonanceGrant
  - room_feature_progression_details <- room_features.RoomFeatureProgressionDetails
  - defense_progression_details <- room_features.DefenseProgressionDetails
  - item_refinement_details <- items.ItemRefinementDetails
  - frame_job_details <- justice.FrameJobDetails
  - contributions <- projects.Contribution
  - ship_upgrade_details <- ships.ShipUpgradeDetails
  - ship_construction_details <- ships.ShipConstructionDetails
  - ship_repair_details <- ships.ShipRepairDetails
  - org_capability_details <- societies.OrganizationCapabilityProjectDetails

### ProjectKindResonanceAward

### Service Functions
- `add_contribution(*, project: 'Project', contributor_persona: 'Persona', kind: 'str', ap_amount: 'int | None' = None, money_amount: 'int | None' = None, item_instance: 'ItemInstance | None' = None, check_outcome: 'CheckOutcome | None' = None, contribution_method: 'ContributionMethod | None' = None, intent_text: 'str' = '', privacy_setting: 'str' = 'PRIVATE') -> 'Contribution' - Add a contribution to an ACTIVE Project and advance current_progress.`
- `clear_instant_completion_kinds() -> 'None' - Test-only: clear the instant-completion registry.`
- `clear_kind_handlers() -> 'None' - Test-only: clear the handler registry.`
- `clear_tiered_resolvers() -> 'None' - Test-only: clear the tiered-resolver registry.`
- `contribute_check_to_project(project: 'Project', *, actor: 'ObjectDB', contributor_persona: 'Persona', method: 'ContributionMethod') -> 'Contribution' - Make a check-based contribution: spend AP, roll the check, advance on success (#1574).`
- `donate_to_project(project: 'Project', *, donor_persona: 'Persona', amount: 'int') -> 'Contribution' - Debit ``amount`` coppers from the donor's purse and record a MONEY contribution.`
- `get_kind_handler(kind: 'str') -> 'KindHandler' - Return the registered handler for `kind`, or raise LookupError.`
- `get_tiered_resolver(kind: 'str') -> 'TieredResolver' - Return the registered tiered resolver for ``kind``, or raise LookupError.`
- `maybe_complete_immediately(project: 'Project') -> 'bool' - Resolve an instant-completion project the moment its threshold is funded (#1500).`
- `register_instant_completion_kind(kind: 'str') -> 'None' - Mark a ProjectKind as completing immediately on threshold (re-register safe).`
- `register_kind_handler(kind: 'str', handler: 'KindHandler') -> 'None' - Register a per-kind resolution handler. Re-registration overwrites.`
- `register_tiered_resolver(kind: 'str', resolver: 'TieredResolver') -> 'None' - Register a TIERED_PERIOD kind's tier-grading resolver. Re-registration overwrites.`
- `resolve_project(project: 'Project', *, outcome_tier: 'CheckOutcome') -> 'None' - Finalize a RESOLVING project: dispatch to per-kind handler, set outcome.`
- `restore_registries(snapshot: 'tuple[dict[str, KindHandler], dict[str, TieredResolver]]') -> 'None' - Test-only: reset both registries to a snapshot_registries() copy.`
- `scan_active_projects() -> 'int' - Cron tick: scan ACTIVE projects, transition completion-ready ones to RESOLVING.`
- `set_contribution_story(project: 'Project', *, contributor_persona: 'Persona', text: 'str') -> 'Contribution | None' - Attach the narrative of how a contributor helped to their most recent contribution (#1574).`
- `snapshot_registries() -> 'tuple[dict[str, KindHandler], dict[str, TieredResolver]]' - Test-only: copy both registries for restore_registries().`


## world.realms

### Realm
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
**Pointed to by:**
  - families <- roster.Family
  - union_kinds <- roster.UnionKind
  - areas <- areas.Area
  - starting_areas <- character_creation.StartingArea
  - profiles <- character_sheets.Profile
  - societies <- societies.Society
  - nobiliary_particles <- societies.NobiliaryParticle
  - recognition_rules <- societies.HouseRecognitionRule
  - titles <- societies.Title
  - house_templates <- societies.HouseTemplate
  - market_squares <- items.MarketSquare


## world.registration

### AccountInvite
**Foreign Keys:**
  - invited_by -> evennia.AccountDB [FK]
  - redeemed_by -> evennia.AccountDB [FK] (nullable)

### AccountMailFailure

### RegistrationConfig
**Foreign Keys:**
  - updated_by -> evennia.AccountDB [FK] (nullable)

### Service Functions
- `build_verification_link(email: str) -> str - Return the email-verification URL for an unverified account address (#3193).`
- `issue_invite(email: str, invited_by: evennia.accounts.models.AccountDB, note: str = '') -> world.registration.models.AccountInvite - Issue an invite for ``email`` and email the redemption link to it.`
- `record_mail_failure(email: str, template_prefix: str, error: Exception) -> world.registration.models.AccountMailFailure - Persist a failed account-mail send so staff can see the outage (#3193).`
- `redeem_invite(token: str, email: str, account: evennia.accounts.models.AccountDB) -> world.registration.models.AccountInvite | None - Validate + stamp redemption for the invite backing this signup.`
- `revoke_invite(invite: world.registration.models.AccountInvite, by: evennia.accounts.models.AccountDB) -> world.registration.models.AccountInvite - Revoke an un-redeemed invite. ``by`` is accepted for future audit-log use.`
- `send_invite_email(invite: world.registration.models.AccountInvite) -> bool - Mail ``invite``'s redemption link to the address it is bound to.`
- `signup_allowed(email: str, token: str) -> bool - True when ``token`` is a currently-redeemable invite bound to ``email``.`


## world.relationships

### AffectionShift
**Foreign Keys:**
  - relationship -> relationships.CharacterRelationship [FK]
  - scene -> scenes.Scene [FK]
  - effect -> checks.ConsequenceEffect [FK] (nullable)
  - boon -> scenes.Boon [OneToOne] (nullable)

### BondCombatConfig
**Foreign Keys:**
  - updated_by -> evennia.AccountDB [FK] (nullable)

### CharacterRelationship
**Foreign Keys:**
  - source -> character_sheets.CharacterSheet [FK]
  - target -> character_sheets.CharacterSheet [FK]
  - displayed_track -> relationships.RelationshipTrack [FK] (nullable)
  - displayed_tier -> relationships.RelationshipTier [FK] (nullable)
  - game_week -> game_clock.GameWeek [FK] (nullable)
  - conditions -> relationships.RelationshipCondition [M2M]
**Pointed to by:**
  - sineating_pending_offers <- magic.SineatingPendingOffer
  - pending_stage_advance_offers <- magic.PendingStageAdvanceOffer
  - sineatings <- magic.Sineating
  - rescues <- magic.SoulTetherRescue
  - track_progress <- relationships.RelationshipTrackProgress
  - updates <- relationships.RelationshipUpdate
  - developments <- relationships.RelationshipDevelopment
  - capstones <- relationships.RelationshipCapstone
  - bumps <- relationships.RelationshipBump
  - affection_shifts <- relationships.AffectionShift
  - changes <- relationships.RelationshipChange
  - temporary_conditions <- relationships.TemporaryRelationshipCondition

### GrievanceOption
**Foreign Keys:**
  - track -> relationships.RelationshipTrack [FK]

### HybridRelationshipType
**Pointed to by:**
  - requirements <- relationships.HybridRequirement

### HybridRequirement
**Foreign Keys:**
  - hybrid_type -> relationships.HybridRelationshipType [FK]
  - track -> relationships.RelationshipTrack [FK]

### RelationshipBump
**Foreign Keys:**
  - relationship -> relationships.CharacterRelationship [FK]
  - interaction -> scenes.Interaction [FK]
  - source_emoji -> scenes.ReactionEmoji [FK] (nullable)

### RelationshipCapstone
**Foreign Keys:**
  - relationship -> relationships.CharacterRelationship [FK]
  - author -> character_sheets.CharacterSheet [FK]
  - track -> relationships.RelationshipTrack [FK]
  - linked_scene -> scenes.Scene [FK] (nullable)
  - ritual -> magic.Ritual [FK] (nullable)
**Pointed to by:**
  - anchored_threads <- magic.Thread
  - writeupkudos_set <- relationships.WriteupKudos
  - writeupcomplaint_set <- relationships.WriteupComplaint

### RelationshipChange
**Foreign Keys:**
  - relationship -> relationships.CharacterRelationship [FK]
  - author -> character_sheets.CharacterSheet [FK]
  - source_track -> relationships.RelationshipTrack [FK]
  - target_track -> relationships.RelationshipTrack [FK]

### RelationshipCondition
**Foreign Keys:**
  - gates_modifiers -> mechanics.ModifierTarget [M2M]
**Pointed to by:**
  - consequence_effects <- checks.ConsequenceEffect
  - character_relationships <- relationships.CharacterRelationship
  - temporary_applications <- relationships.TemporaryRelationshipCondition

### RelationshipDevelopment
**Foreign Keys:**
  - relationship -> relationships.CharacterRelationship [FK]
  - author -> character_sheets.CharacterSheet [FK]
  - track -> relationships.RelationshipTrack [FK]
  - linked_scene -> scenes.Scene [FK] (nullable)
**Pointed to by:**
  - writeupkudos_set <- relationships.WriteupKudos
  - writeupcomplaint_set <- relationships.WriteupComplaint

### RelationshipTier
**Foreign Keys:**
  - track -> relationships.RelationshipTrack [FK]

### RelationshipTrack
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
**Pointed to by:**
  - thread_weaving_unlocks <- magic.ThreadWeavingUnlock
  - tiers <- relationships.RelationshipTier
  - hybridrequirement_set <- relationships.HybridRequirement
  - grievance_options <- relationships.GrievanceOption
  - relationshiptrackprogress_set <- relationships.RelationshipTrackProgress
  - relationshipupdate_set <- relationships.RelationshipUpdate
  - relationshipdevelopment_set <- relationships.RelationshipDevelopment
  - relationshipcapstone_set <- relationships.RelationshipCapstone
  - changes_from <- relationships.RelationshipChange
  - changes_to <- relationships.RelationshipChange

### RelationshipTrackProgress
**Foreign Keys:**
  - relationship -> relationships.CharacterRelationship [FK]
  - track -> relationships.RelationshipTrack [FK]
**Pointed to by:**
  - anchored_threads <- magic.Thread

### RelationshipUpdate
**Foreign Keys:**
  - relationship -> relationships.CharacterRelationship [FK]
  - author -> character_sheets.CharacterSheet [FK]
  - track -> relationships.RelationshipTrack [FK]
  - linked_scene -> scenes.Scene [FK] (nullable)
  - linked_interaction -> scenes.Interaction [FK] (nullable)
**Pointed to by:**
  - writeupkudos_set <- relationships.WriteupKudos
  - writeupcomplaint_set <- relationships.WriteupComplaint

### TemporaryRelationshipCondition
**Foreign Keys:**
  - relationship -> relationships.CharacterRelationship [FK]
  - condition -> relationships.RelationshipCondition [FK]

### WriteupComplaint
**Foreign Keys:**
  - update -> relationships.RelationshipUpdate [FK] (nullable)
  - development -> relationships.RelationshipDevelopment [FK] (nullable)
  - capstone -> relationships.RelationshipCapstone [FK] (nullable)
  - complainant -> evennia.AccountDB [FK]

### WriteupKudos
**Foreign Keys:**
  - update -> relationships.RelationshipUpdate [FK] (nullable)
  - development -> relationships.RelationshipDevelopment [FK] (nullable)
  - capstone -> relationships.RelationshipCapstone [FK] (nullable)
  - account -> evennia.AccountDB [FK]

### Service Functions
- `add_relationship_condition(*, source: 'CharacterSheet', target: 'CharacterSheet', condition: 'RelationshipCondition', duration: 'timedelta | None' = None) -> 'None' - Add a ``RelationshipCondition`` to the directed ``source → target`` relationship (#1697).`
- `apply_affection_shift(*, source: 'CharacterSheet', target: 'CharacterSheet', scene: 'Scene', effect: 'ConsequenceEffect | None', amount: 'int', boon: 'Boon | None' = None) -> 'AffectionShift | None' - Apply a social action's automatic affection shift (#1697, boon mode #2540).`
- `apply_relationship_bump(*, source: 'CharacterSheet', target: 'CharacterSheet', interaction: 'Interaction', valence: 'int', source_emoji: 'ReactionEmoji | None' = None) -> 'RelationshipBump' - Apply an ambient ±1 bump to source's regard toward target (#1699).`
- `award_kudos(account: evennia.accounts.models.AccountDB, amount: int, source_category: world.progression.models.kudos.KudosSourceCategory, description: str, awarded_by: evennia.accounts.models.AccountDB | None = None, character: world.character_sheets.models.CharacterSheet | None = None) -> world.progression.types.AwardResult - Award kudos to an account with full audit trail.`
- `award_xp(account: 'AccountDB', amount: 'int', reason: 'str' = ProgressionReason.SYSTEM_AWARD, description: 'str' = '', gm: 'AccountDB | None' = None) -> 'XPTransaction' - Award XP to an account.`
- `bond_bonus(actor: 'ObjectDB', protected: 'ObjectDB') -> 'int' - Return the bond bonus for protection checks (INTERPOSE/SUCCOR).`
- `bond_combat_bonus(sheet: 'CharacterSheet', encounter: 'CombatEncounter') -> 'list[ModifierContribution]' - Return ModifierContribution(RELATIONSHIP) entries for each bonded co-combatant.`
- `clear_very_attracted(sheets) -> 'None' - Drop Very Attracted for the given characters — the scene-end early clear (#1697).`
- `create_capstone(*, relationship: 'CharacterRelationship', author: 'CharacterSheet', title: 'str', writeup: 'str', track: 'RelationshipTrack', points: 'int', visibility: 'UpdateVisibility', linked_scene: 'Scene | None' = None) -> 'RelationshipCapstone' - Record a capstone event — adds points to both capacity and developed_points.`
- `create_development(*, relationship: 'CharacterRelationship', author: 'CharacterSheet', title: 'str', writeup: 'str', track: 'RelationshipTrack', points: 'int', xp_awarded: 'int' = 0, visibility: 'UpdateVisibility', linked_scene: 'Scene | None' = None) -> 'RelationshipDevelopment' - Add permanent (developed) points to a track, up to capacity.`
- `create_first_impression(*, source: 'CharacterSheet', target: 'CharacterSheet', title: 'str', writeup: 'str', track: 'RelationshipTrack', points: 'int', coloring: 'FirstImpressionColoring', visibility: 'UpdateVisibility', linked_scene: 'Scene | None' = None) -> 'CharacterRelationship' - Create a pending relationship with an initial update and track progress.`
- `file_writeup_complaint(*, complainant_account: 'AccountDB', writeup, reason: 'str') -> 'WriteupComplaint' - File a bad-faith-RP complaint against a writeup for staff triage.`
- `get_account_for_character(character: 'ObjectDB') -> 'AccountDB | None' - Get the account currently playing this character via roster tenure.`
- `get_bond_combat_config() -> 'BondCombatConfig' - Get-or-create the BondCombatConfig singleton (pk=1).`
- `give_writeup_kudos(*, giver_account: 'AccountDB', writeup) -> 'WriteupKudos' - Award a non-revocable commendation to the writeup author on behalf of the subject.`
- `increment_stat_for_group(character_sheets: 'list[CharacterSheet]', stat: 'StatDefinition', amount: 'int' = 1) -> 'None' - Increment a stat for several sheets as one simultaneous group moment.`
- `mirror_npc_regard_event_to_track(event: 'NpcRegardEvent') -> 'RelationshipTrackProgress | None' - Mirror one NpcRegardEvent onto the PC's Regard/Friction system track (#2039).`
- `redistribute_points(*, relationship: 'CharacterRelationship', author: 'CharacterSheet', title: 'str', writeup: 'str', source_track: 'RelationshipTrack', target_track: 'RelationshipTrack', points: 'int', visibility: 'UpdateVisibility') -> 'RelationshipChange' - Move developed points from one track to another. No new value is added.`
- `register_grievance(*, source: 'CharacterSheet', target: 'CharacterSheet', option: 'GrievanceOption | None' = None, custom_points: 'int | None' = None, custom_track: 'RelationshipTrack | None' = None, writeup: 'str' = '', visibility: 'UpdateVisibility' = UpdateVisibility.PRIVATE) -> 'RelationshipCapstone' - Register a wronged character's one-sided grievance against whoever harmed them (#1429).`
- `relationship_gated_contributions(*, perceiver: 'CharacterSheet', perceived: 'CharacterSheet') -> 'list[ModifierContribution]' - Modifier contributions the perceiver's regard for the perceived injects into a check (#1696).`
- `soul_tether_active(a_sheet: 'CharacterSheet', b_sheet: 'CharacterSheet') -> 'bool' - Check whether two characters have an active Soul Tether bond.`


## world.room_features

### BrigDetails
**Foreign Keys:**
  - feature_instance -> room_features.RoomFeatureInstance [OneToOne]

### DefenseProgressionDetails
**Foreign Keys:**
  - project -> projects.Project [OneToOne]
  - target_exit_profile -> evennia_extensions.ExitProfile [FK] (nullable)
  - target_room_profile -> evennia_extensions.RoomProfile [FK] (nullable)
  - resonance -> magic.Resonance [FK] (nullable)
  - reaction_condition -> conditions.ConditionTemplate [FK] (nullable)

### ExitBarsDetails
**Foreign Keys:**
  - exit_profile -> evennia_extensions.ExitProfile [OneToOne]

### PreparedGround
**Foreign Keys:**
  - room_profile -> evennia_extensions.RoomProfile [FK]
  - prepared_by -> character_sheets.CharacterSheet [OneToOne]

### RoomAlarmDetails
**Foreign Keys:**
  - room_profile -> evennia_extensions.RoomProfile [OneToOne]

### RoomFeatureInstance
**Foreign Keys:**
  - room_profile -> evennia_extensions.RoomProfile [OneToOne]
  - feature_kind -> room_features.RoomFeatureKind [FK]
**Pointed to by:**
  - field_details <- agriculture.FieldDetails
  - granary_details <- agriculture.GranaryDetails
  - sanctum_details <- magic.SanctumDetails
  - stables_details <- companions.StablesDetails
  - vault_details <- room_features.VaultDetails
  - brig_details <- room_features.BrigDetails
  - lab_station_details <- items.LabStationDetails

### RoomFeatureKind
**Foreign Keys:**
  - allowed_building_kinds -> buildings.BuildingKind [M2M]
**Pointed to by:**
  - install_rituals <- room_features.RoomFeatureKindInstallRitual
  - required_building_owner_types <- room_features.RoomFeatureKindOwnerType
  - instances <- room_features.RoomFeatureInstance
  - progression_projects <- room_features.RoomFeatureProgressionDetails
  - gated_recipes <- items.CraftingRecipe

### RoomFeatureKindInstallRitual
**Foreign Keys:**
  - feature_kind -> room_features.RoomFeatureKind [FK]
  - ritual -> magic.Ritual [FK]

### RoomFeatureKindOwnerType
**Foreign Keys:**
  - feature_kind -> room_features.RoomFeatureKind [FK]

### RoomFeatureProgressionDetails
**Foreign Keys:**
  - project -> projects.Project [OneToOne]
  - target_room_profile -> evennia_extensions.RoomProfile [FK]
  - target_feature_kind -> room_features.RoomFeatureKind [FK]

### RoomWardDetails
**Foreign Keys:**
  - room_profile -> evennia_extensions.RoomProfile [OneToOne]
  - resonance -> magic.Resonance [FK]
  - reaction_condition -> conditions.ConditionTemplate [FK] (nullable)

### Trap
**Foreign Keys:**
  - room_profile -> evennia_extensions.RoomProfile [FK]
  - position -> areas.Position [FK] (nullable)
  - consequence_pool -> actions.ConsequencePool [FK]
  - detect_check_type -> checks.CheckType [FK]
  - disarm_check_type -> checks.CheckType [FK]
  - created_by_sheet -> character_sheets.CharacterSheet [FK] (nullable)
  - detected_by -> character_sheets.CharacterSheet [M2M]

### VaultAccessEntry
**Foreign Keys:**
  - vault_details -> room_features.VaultDetails [FK]
  - holder_persona -> scenes.Persona [FK] (nullable)
  - holder_organization -> societies.Organization [FK] (nullable)
  - added_by -> scenes.Persona [FK]

### VaultDetails
**Foreign Keys:**
  - feature_instance -> room_features.RoomFeatureInstance [OneToOne]
  - founder_persona -> scenes.Persona [FK]
**Pointed to by:**
  - access_entries <- room_features.VaultAccessEntry

### Service Functions
- `active_captains_quarters_in(room_profile: 'RoomProfile') -> 'RoomFeatureInstance | None' - The room's active Captain's Quarters feature, or None.`
- `active_hub_feature(room_profile: 'RoomProfile') -> 'RoomFeatureInstance | None' - The room's active civic-hub feature (Notice Board or Town Crier), or None.`
- `active_library_in(room_profile: 'RoomProfile') -> 'RoomFeatureInstance | None' - The room's active Library feature, or None.`
- `active_siege_deck_in(room_profile: 'RoomProfile') -> 'RoomFeatureInstance | None' - The room's active Siege Deck feature, or None.`
- `active_social_hub_in(room_profile: 'RoomProfile') -> 'RoomFeatureInstance | None' - The room's active Social Hub feature, or None (#1694).`
- `active_training_room_in(room_profile: 'RoomProfile') -> 'RoomFeatureInstance | None' - The room's active Training Room feature, or None.`
- `can_modify_room_features(persona: 'Persona', room: 'DefaultObject') -> 'bool' - Standing required to install or upgrade a feature in this room.`
- `complete_defense_installation(project: 'Project', outcome_tier: 'CheckOutcome | None' = None) -> 'None' - Handle resolution of a ROOM_DEFENSE_INSTALLATION project (#2177).`
- `complete_room_feature_progression(project: 'Project', outcome_tier: 'CheckOutcome | None' = None) -> 'None' - Handle resolution of a ROOM_FEATURE_PROGRESSION project.`
- `handle_bank_progression(project: 'Project', target_level: 'int', outcome_tier: 'CheckOutcome | None' = None) -> 'None' - BANK strategy (#2540 Layer 4): row-only install.`
- `handle_captains_quarters_progression(project: 'Project', target_level: 'int', outcome_tier: 'CheckOutcome | None' = None) -> 'None' - CAPTAINS_QUARTERS strategy (#675): row-only install.`
- `handle_command_center_progression(project: 'Project', target_level: 'int', outcome_tier: 'CheckOutcome | None' = None) -> 'None' - COMMAND_CENTER strategy (#930): install or level the feature instance.`
- `handle_library_progression(project: 'Project', target_level: 'int', outcome_tier: 'CheckOutcome | None' = None) -> 'None' - LIBRARY strategy (#675): row-only install/level.`
- `handle_notice_board_progression(project: 'Project', target_level: 'int', outcome_tier: 'CheckOutcome | None' = None) -> 'None' - NOTICE_BOARD strategy (#1450): row-only install.`
- `handle_siege_deck_progression(project: 'Project', target_level: 'int', outcome_tier: 'CheckOutcome | None' = None) -> 'None' - SIEGE_DECK strategy (#675): row-only install/level.`
- `handle_social_hub_progression(project: 'Project', target_level: 'int', outcome_tier: 'CheckOutcome | None' = None) -> 'None' - SOCIAL_HUB strategy (#1694): install/level the feature, mark the hub, draw crowds.`
- `handle_town_crier_progression(project: 'Project', target_level: 'int', outcome_tier: 'CheckOutcome | None' = None) -> 'None' - TOWN_CRIER strategy (#1450): install the row AND place the crier NPC.`
- `handle_training_room_progression(project: 'Project', target_level: 'int', outcome_tier: 'CheckOutcome | None' = None) -> 'None' - TRAINING_ROOM strategy (#675): row-only install/level.`
- `handle_workshop_of_iniquity_progression(project: 'Project', target_level: 'int', outcome_tier: 'CheckOutcome | None' = None) -> 'None' - WORKSHOP_OF_INIQUITY strategy (#1825): row-only install/level.`
- `react_to_unauthorized_entry(actor, room) -> 'None' - React to `actor` entering `room` when an active ward/alarm is present`
- `register_room_feature_strategy(strategy_key: 'str', handler: 'RoomFeatureStrategyHandler', *, as_default: 'bool' = False) -> 'None' - Register/override the strategy handler for ``strategy_key``.`
- `reset_room_feature_strategies() -> 'None' - Restore the at-ready baseline registrations. Test-only escape hatch.`
- `room_ward_upkeep_tick() -> 'None' - Drain each active ward's resonance_reserve; lapse it if depleted (#2177).`
- `staff_dissolve_feature(room_profile: 'RoomProfile') -> 'str | None' - Dissolve the room's active feature by staff fiat (#3269 Phase B).`
- `staff_install_feature(room_profile: 'RoomProfile', feature_kind, *, owner_persona: 'Persona', target_level: 'int' = 1) -> 'str | None' - Install/level a room feature by staff fiat (#3269 Phase B).`
- `sync_social_hub_traffic(room_profile: 'RoomProfile') -> 'None' - Reconcile the room's crowd-draw TRAFFIC modifier to its hub's current level.`


## world.roster

### Family
**Foreign Keys:**
  - created_by -> evennia.AccountDB [FK] (nullable)
  - origin_realm -> realms.Realm [FK] (nullable)
**Pointed to by:**
  - members <- roster.Kinsperson
  - memberships <- roster.FamilyMembership
  - kin_slot_pools <- roster.KinSlotPool
  - character_drafts <- character_creation.CharacterDraft
  - profiles <- character_sheets.Profile
  - organizations <- societies.Organization

### FamilyMembership
**Foreign Keys:**
  - kinsperson -> roster.Kinsperson [FK]
  - family -> roster.Family [FK]

### GameInvite
**Foreign Keys:**
  - inviter -> evennia_extensions.PlayerData [FK]
  - invited_account -> evennia.AccountDB [FK] (nullable)
  - revoked_by -> evennia.AccountDB [FK] (nullable)
**Pointed to by:**
  - applications <- character_creation.DraftApplication

### KinSlotPool
**Foreign Keys:**
  - family -> roster.Family [FK]
  - parents -> roster.Kinsperson [M2M]
  - allowed_genders -> character_sheets.Gender [M2M]
**Pointed to by:**
  - drafts <- character_creation.CharacterDraft

### Kinsperson
**Foreign Keys:**
  - gender -> character_sheets.Gender [FK] (nullable)
  - sheet -> character_sheets.CharacterSheet [OneToOne] (nullable)
  - functionary -> npc_services.Functionary [FK] (nullable)
  - family -> roster.Family [FK] (nullable)
  - species -> species.Species [FK] (nullable)
  - deferred_definer -> character_sheets.CharacterSheet [FK] (nullable)
  - created_by -> evennia.AccountDB [FK] (nullable)
  - allowed_genders -> character_sheets.Gender [M2M]
**Pointed to by:**
  - trait_values <- roster.KinspersonTraitValue
  - family_memberships <- roster.FamilyMembership
  - unions <- roster.Union
  - parentage_up <- roster.ParentageEdge
  - parentage_down <- roster.ParentageEdge
  - incarnations <- roster.SoulIncarnation
  - kin_slot_pools <- roster.KinSlotPool
  - drafts <- character_creation.CharacterDraft
  - titles_held <- societies.Title
  - pact_commitments <- societies.PactCommitment
  - betrothals_as_a <- societies.Betrothal
  - betrothals_as_b <- societies.Betrothal

### KinspersonTraitValue
**Foreign Keys:**
  - kinsperson -> roster.Kinsperson [FK]
  - trait -> forms.FormTrait [FK]
  - option -> forms.FormTraitOption [FK]

### NPCPresetSkillLine
**Foreign Keys:**
  - preset -> roster.NPCStatlinePreset [FK]
  - skill -> skills.Skill [FK]

### NPCPresetTraitLine
**Foreign Keys:**
  - preset -> roster.NPCStatlinePreset [FK]
  - trait -> traits.Trait [FK]

### NPCStatlinePreset
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
**Pointed to by:**
  - trait_lines <- roster.NPCPresetTraitLine
  - skill_lines <- roster.NPCPresetSkillLine

### ParentageEdge
**Foreign Keys:**
  - child -> roster.Kinsperson [FK]
  - parent -> roster.Kinsperson [FK]
  - born_within_union -> roster.Union [FK] (nullable)
  - secret -> secrets.Secret [FK] (nullable)

### PlayerMail
**Foreign Keys:**
  - sender_tenure -> roster.RosterTenure [FK] (nullable)
  - recipient_tenure -> roster.RosterTenure [FK]
  - in_reply_to -> roster.PlayerMail [FK] (nullable)
**Pointed to by:**
  - replies <- roster.PlayerMail

### Roster
**Pointed to by:**
  - entries <- roster.RosterEntry
  - former_entries <- roster.RosterEntry

### RosterApplication
**Foreign Keys:**
  - player_data -> evennia_extensions.PlayerData [FK]
  - character -> character_sheets.CharacterSheet [FK]
  - reviewed_by -> evennia_extensions.PlayerData [FK] (nullable)

### RosterEntry
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [OneToOne]
  - roster -> roster.Roster [FK]
  - profile_picture -> roster.TenureMedia [FK] (nullable)
  - previous_roster -> roster.Roster [FK] (nullable)
  - created_by_account -> evennia.AccountDB [FK] (nullable)
  - created_for_table -> gm.GMTable [FK] (nullable)
**Pointed to by:**
  - tenures <- roster.RosterTenure
  - clues_held <- clues.CharacterClue
  - codex_knowledge <- codex.CharacterCodexKnowledge
  - random_scene_claimed_as <- progression.RandomSceneCompletion
  - known_rituals <- magic.CharacterRitualKnowledge
  - invites <- gm.GMRosterInvite
  - favorited_interactions <- scenes.InteractionFavorite
  - secrets_known <- secrets.SecretKnowledge
  - aggregatebeatcontribution_set <- stories.AggregateBeatContribution
  - beatcompletion_set <- stories.BeatCompletion

### RosterTenure
**Foreign Keys:**
  - player_data -> evennia_extensions.PlayerData [FK]
  - roster_entry -> roster.RosterEntry [FK]
  - approved_by -> evennia_extensions.PlayerData [FK] (nullable)
**Pointed to by:**
  - sent_mail <- roster.PlayerMail
  - received_mail <- roster.PlayerMail
  - display_settings <- roster.TenureDisplaySettings
  - galleries <- roster.TenureGallery
  - shared_galleries <- roster.TenureGallery
  - media <- roster.TenureMedia
  - discoveries <- achievements.Discovery
  - shared_discoveries <- achievements.Discovery
  - earned_achievements <- achievements.CharacterAchievement
  - consent_groups <- consent.ConsentGroup
  - consent_memberships <- consent.ConsentGroupMember
  - social_consent_preference <- consent.SocialConsentPreference
  - social_consent_whitelist_owned <- consent.SocialConsentWhitelist
  - social_consent_whitelist_allowed <- consent.SocialConsentWhitelist
  - social_consent_blacklist_owned <- consent.SocialConsentBlacklist
  - social_consent_blacklist_blocked <- consent.SocialConsentBlacklist
  - playerboundary_visible <- boundaries.PlayerBoundary
  - playerboundary_excluded <- boundaries.PlayerBoundary
  - treasured_subjects <- boundaries.TreasuredSubject
  - treasuredsubject_visible <- boundaries.TreasuredSubject
  - treasuredsubject_excluded <- boundaries.TreasuredSubject
  - granted_trait_changes <- traits.CharacterTraitChange
  - codex_taught <- codex.CharacterCodexKnowledge
  - codex_teaching_offers <- codex.CodexTeachingOffer
  - codexteachingoffer_visible <- codex.CodexTeachingOffer
  - codexteachingoffer_excluded <- codex.CodexTeachingOffer
  - gift_unlocks_taught <- magic.CharacterGiftUnlock
  - technique_teaching_offers <- magic.TechniqueTeachingOffer
  - taught_rituals <- magic.CharacterRitualKnowledge
  - technique_progress_taught <- magic.TechniqueProgress
  - thread_weaving_unlocks_taught <- magic.CharacterThreadWeavingUnlock
  - thread_weaving_offers <- magic.ThreadWeavingTeachingOffer
  - friendships_made <- scenes.Friendship
  - friendships_received <- scenes.Friendship
  - rivalries_made <- scenes.Rivalry
  - rivalries_received <- scenes.Rivalry

### Soul
**Pointed to by:**
  - incarnations <- roster.SoulIncarnation

### SoulIncarnation
**Foreign Keys:**
  - soul -> roster.Soul [FK]
  - kinsperson -> roster.Kinsperson [FK]
  - secret -> secrets.Secret [FK] (nullable)

### TenureDisplaySettings
**Foreign Keys:**
  - tenure -> roster.RosterTenure [OneToOne]

### TenureGallery
**Foreign Keys:**
  - tenure -> roster.RosterTenure [FK]
  - allowed_viewers -> roster.RosterTenure [M2M]
**Pointed to by:**
  - media <- roster.TenureMedia

### TenureMedia
**Foreign Keys:**
  - tenure -> roster.RosterTenure [FK]
  - media -> evennia_extensions.Media [FK]
  - gallery -> roster.TenureGallery [FK] (nullable)
**Pointed to by:**
  - profile_for_entries <- roster.RosterEntry

### Union
**Foreign Keys:**
  - kind -> roster.UnionKind [FK]
  - secret -> secrets.Secret [FK] (nullable)
  - members -> roster.Kinsperson [M2M]
**Pointed to by:**
  - births <- roster.ParentageEdge
  - marriage_pact <- societies.MarriagePact

### UnionKind
**Foreign Keys:**
  - realm -> realms.Realm [FK] (nullable)
**Pointed to by:**
  - unions <- roster.Union


## world.scenes

### Block
**Foreign Keys:**
  - owner -> evennia_extensions.PlayerData [FK]
  - blocked_player -> evennia_extensions.PlayerData [FK]
  - blocker_persona -> scenes.Persona [FK] (nullable)
  - blocked_persona -> scenes.Persona [FK] (nullable)

### BlockContactFlag
**Foreign Keys:**
  - blocker_account -> evennia.AccountDB [FK]
  - blocked_account -> evennia.AccountDB [FK]
  - initiator_persona -> scenes.Persona [FK]
  - target_persona -> scenes.Persona [FK]
  - scene -> scenes.Scene [FK] (nullable)

### Boon
**Foreign Keys:**
  - action_request -> scenes.SceneActionRequest [OneToOne]
  - item_instance -> items.ItemInstance [FK] (nullable)
  - material_category -> items.MaterialCategory [FK] (nullable)
**Pointed to by:**
  - affection_shift <- relationships.AffectionShift

### DecisiveCheckMarker
**Foreign Keys:**
  - scene -> scenes.Scene [FK]
  - beat -> stories.Beat [FK]
  - created_by -> evennia.AccountDB [FK] (nullable)
  - resolved_outcome_tier -> traits.CheckOutcome [FK] (nullable)

### Friendship
**Foreign Keys:**
  - friender_tenure -> roster.RosterTenure [FK]
  - friend_tenure -> roster.RosterTenure [FK]

### Interaction
**Foreign Keys:**
  - persona -> scenes.Persona [FK]
  - writer_account -> evennia.AccountDB [FK] (nullable)
  - scene -> scenes.Scene [FK] (nullable)
  - place -> scenes.Place [FK] (nullable)
  - language -> species.Language [FK] (nullable)
  - fury_committed -> magic.FuryTier [FK] (nullable)
  - attributed_companion -> companions.Companion [FK] (nullable)
  - target_personas -> scenes.Persona [M2M]
**Pointed to by:**
  - consequence_outcomes <- checks.ConsequenceOutcome
  - dramatic_moment_tags <- magic.DramaticMomentTag
  - dramatic_moment_suggestions <- magic.DramaticMomentSuggestion
  - endorsements <- magic.PoseEndorsement
  - sceneentryendorsement_set <- magic.SceneEntryEndorsement
  - combat_round_actions <- combat.CombatRoundAction
  - clash_contributions <- combat.ClashContribution
  - referencing_updates <- relationships.RelationshipUpdate
  - relationship_bumps <- relationships.RelationshipBump
  - favorites <- scenes.InteractionFavorite
  - reactions <- scenes.InteractionReaction
  - interaction_targets <- scenes.InteractionTargetPersona
  - action_links <- scenes.InteractionAction
  - pose_links <- scenes.InteractionAction
  - power_ledger_entries <- scenes.InteractionPowerLedgerEntry
  - action_request_result <- scenes.SceneActionRequest
  - action_request_action <- scenes.SceneActionRequest
  - receivers <- scenes.InteractionReceiver
  - reaction_windows <- scenes.ReactionWindow

### InteractionAction
**Foreign Keys:**
  - pose -> scenes.Interaction [FK]
  - action_interaction -> scenes.Interaction [FK]

### InteractionFavorite
**Foreign Keys:**
  - interaction -> scenes.Interaction [FK]
  - roster_entry -> roster.RosterEntry [FK]

### InteractionPowerLedgerEntry
**Foreign Keys:**
  - interaction -> scenes.Interaction [FK]

### InteractionReaction
**Foreign Keys:**
  - interaction -> scenes.Interaction [FK]
  - account -> evennia.AccountDB [FK]

### InteractionReceiver
**Foreign Keys:**
  - interaction -> scenes.Interaction [FK]
  - persona -> scenes.Persona [FK]
  - account -> evennia.AccountDB [FK] (nullable)

### InteractionTargetPersona
**Foreign Keys:**
  - interaction -> scenes.Interaction [FK]
  - persona -> scenes.Persona [FK]

### Mute
**Foreign Keys:**
  - owner -> evennia_extensions.PlayerData [FK]
  - muted_persona -> scenes.Persona [FK]
  - muted_player -> evennia_extensions.PlayerData [FK] (nullable)

### PendingSuddenHarm
**Foreign Keys:**
  - target_sheet -> character_sheets.CharacterSheet [FK]
  - scene_round -> scenes.SceneRound [FK]
  - damage_type -> conditions.DamageType [FK] (nullable)

### Persona
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - profile -> character_sheets.Profile [FK] (nullable)
  - thumbnail -> evennia_extensions.Media [FK] (nullable)
  - properties -> mechanics.Property [M2M]
**Pointed to by:**
  - titles <- achievements.PersonaTitle
  - food_transfers_initiated <- agriculture.FoodTransfer
  - promoted_assets <- assets.NPCAsset
  - asset_ownerships <- assets.NPCAsset
  - check_calls_issued <- checks.CheckCall
  - board_posts <- boards.BoardPost
  - board_posts_removed <- boards.BoardPost
  - owned_buildings <- buildings.Building
  - buildings_constructed <- buildings.Building
  - purchased_building_listings <- buildings.BuildingListing
  - materials_contributed <- buildings.BuildingMaterial
  - permits_consumed <- buildings.BuildingPermitDetails
  - construction_projects_led <- buildings.BuildingConstructionDetails
  - ceremonies_officiated <- ceremonies.Ceremony
  - ceremony_offerings <- ceremonies.CeremonyOffering
  - ceremony_speeches <- ceremonies.CeremonySpeech
  - sent_org_membership_offers <- societies.OrganizationMembershipOffer
  - received_org_membership_offers <- societies.OrganizationMembershipOffer
  - organization_memberships <- societies.OrganizationMembership
  - offices_held <- societies.OrganizationOffice
  - lodged_org_appeals <- societies.OrgAppeal
  - org_appeal_signons <- societies.OrgAppealSignon
  - society_reputations <- societies.SocietyReputation
  - organization_reputations <- societies.OrganizationReputation
  - standing_declarations_received <- societies.StandingDeclaration
  - standing_declarations_made <- societies.StandingDeclaration
  - legend_entries <- societies.LegendEntry
  - legend_spreads <- societies.LegendSpread
  - legend_stories_written <- societies.LegendDeedStory
  - honors_given <- societies.LegendHonor
  - deed_knowledge <- societies.PersonaDeedKnowledge
  - proclamations <- societies.Proclamation
  - edicts_enacted <- societies.DomainEdict
  - witnessed_advancements <- progression.ClassLevelAdvancement
  - cohort_enrollments <- progression.CohortEnrollment
  - targeted_for_random_scene <- progression.RandomSceneTarget
  - random_scene_completed_by <- progression.RandomSceneCompletion
  - poseendorsement_set <- magic.PoseEndorsement
  - sceneentryendorsement_set <- magic.SceneEntryEndorsement
  - presentationendorsement_set <- magic.PresentationEndorsement
  - stylepresentationendorsement_set <- magic.StylePresentationEndorsement
  - combat_opponents <- combat.CombatOpponent
  - org_contributions <- currency.ContributionRecord
  - contracts_proposed <- currency.Contract
  - contracts_received <- currency.Contract
  - businesses <- currency.Business
  - executor_duties <- estates.WillExecutor
  - bequests_received <- estates.Bequest
  - estate_claims <- estates.EstateClaim
  - hosted_events <- events.EventHost
  - event_invitations <- events.EventInvitation
  - invitations_sent <- events.EventInvitation
  - catering_contributions <- events.EventCatering
  - grandeur_contributions <- events.EventGrandeurContribution
  - alternate_self_grants <- forms.AlternateSelf
  - return_for_active <- forms.ActiveAlternateSelf
  - trait_descriptors <- forms.PersonaTraitDescriptor
  - appearance_changes <- forms.AppearanceChangeLog
  - appearance_changes_made <- forms.AppearanceChangeLog
  - gm_table_memberships <- gm.GMTableMembership
  - founded_styles <- items.Style
  - trendsetter_crownings <- items.Trendsetter
  - founded_vaults <- room_features.VaultDetails
  - vault_access_entries <- room_features.VaultAccessEntry
  - vault_access_granted <- room_features.VaultAccessEntry
  - npc_standings <- npc_services.NPCStanding
  - standings_held_by <- npc_services.NPCStanding
  - functionary_placements <- npc_services.Functionary
  - npc_preferences <- npc_services.NpcPreference
  - offer_cooldowns <- npc_services.OfferCooldown
  - role_cooldowns <- npc_services.NPCRoleCooldown
  - regards_held <- npc_services.NpcRegard
  - regards_as_target <- npc_services.NpcRegard
  - summonses_received <- npc_services.OfferSummons
  - regard_seeds_from_distinctions <- npc_services.DistinctionRegardSeed
  - npc_assignments_made <- npc_services.NPCAssignment
  - expulsion_bars_imposed <- npc_services.ExpulsionBar
  - recorded_profiles <- npc_services.RecordedProfile
  - market_stalls <- items.MarketStall
  - shopkeeper_of_stalls <- items.MarketStall
  - ware_listings <- items.WareListing
  - finishing_passes <- items.FinishingPass
  - crafting_service_offers <- items.CraftingServiceOffer
  - market_purchases <- items.MarketSale
  - market_sales <- items.MarketSale
  - vault_deposits <- items.VaultHolding
  - org_vault_events <- items.OrgVaultEvent
  - heat_rows <- justice.PersonaHeat
  - lie_low_states <- justice.LieLowState
  - pardons_granted <- justice.PardonGrant
  - pardons_received <- justice.PardonGrant
  - guard_encounters <- justice.GuardEncounter
  - justice_cases <- justice.JusticeCase
  - exculpatory_submissions <- justice.ExculpatoryEvidence
  - exile_decrees <- justice.ExileDecree
  - ownership_records <- locations.LocationOwnership
  - tenancies <- locations.LocationTenancy
  - mission_invites_received <- missions.MissionInvite
  - mission_invites_sent <- missions.MissionInvite
  - mission_risk_acknowledgements <- missions.MissionRiskAcknowledgement
  - feedback_submissions <- player_submissions.PlayerFeedback
  - bug_reports <- player_submissions.BugReport
  - reports_submitted <- player_submissions.PlayerReport
  - reports_against <- player_submissions.PlayerReport
  - check_proposals <- player_submissions.CheckProposal
  - projects_owned <- projects.Project
  - project_contributions <- projects.Contribution
  - discoveries_as_subject <- scenes.PersonaDiscovery
  - discoveries_as_linked <- scenes.PersonaDiscovery
  - blocks_from <- scenes.Block
  - blocks_against <- scenes.Block
  - muted_by <- scenes.Mute
  - interactions_written <- scenes.Interaction
  - interactions_targeted <- scenes.Interaction
  - targeted_in_interactions <- scenes.InteractionTargetPersona
  - summary_revisions <- scenes.SceneSummaryRevision
  - targeted_scene_declarations <- scenes.SceneActionDeclaration
  - initiated_action_requests <- scenes.SceneActionRequest
  - received_action_requests <- scenes.SceneActionRequest
  - delivery_scoped_action_requests <- scenes.SceneActionRequest
  - action_target_rows <- scenes.SceneActionTarget
  - place_presences <- scenes.PlacePresence
  - interactions_received <- scenes.InteractionReceiver
  - window_reactions <- scenes.WindowReaction
  - opened_speaker_queues <- scenes.SpeakerQueue
  - speaker_queue_entries <- scenes.SpeakerQueueEntry
  - authored_secrets <- secrets.Secret
  - secret_victimhoods <- secrets.SecretVictim
  - constructed_ships <- ships.ShipConstructionDetails
  - mentored_allocations <- skills.TrainingAllocation
  - table_bulletin_posts <- stories.TableBulletinPost
  - table_bulletin_replies <- stories.TableBulletinReply
  - org_tasks_issued <- tasking.OrgTask
  - org_tasks_targeting <- tasking.OrgTask
  - task_aptitudes <- tasking.NpcTaskAptitude
  - listener_posts_handled <- tasking.ListenerPost
  - flipped_listener_posts <- tasking.ListenerPost
  - task_fulfillments_handled <- tasking.TaskFulfillment
  - opened_tavern_game_sessions <- tavern_games.GameSession
  - tavern_game_seats <- tavern_games.GameSeat
  - led_voyages <- travel.Voyage
  - voyage_participations <- travel.VoyageParticipant
  - voyage_invites_received <- travel.VoyageInvite
  - voyage_invites_sent <- travel.VoyageInvite

### PersonaDiscovery
**Foreign Keys:**
  - persona -> scenes.Persona [FK]
  - linked_to -> scenes.Persona [FK]
  - discovered_by -> character_sheets.CharacterSheet [FK]

### Place
**Foreign Keys:**
  - room -> evennia_extensions.RoomProfile [FK] (nullable)
**Pointed to by:**
  - interactions <- scenes.Interaction
  - presences <- scenes.PlacePresence
  - tavern_game_sessions <- tavern_games.GameSession

### PlacePresence
**Foreign Keys:**
  - place -> scenes.Place [FK]
  - persona -> scenes.Persona [FK]

### PrecaptureConsentRequest
**Foreign Keys:**
  - scene -> scenes.Scene [FK]
  - account -> evennia.AccountDB [FK]

### ReactionEmoji

### ReactionWindow
**Foreign Keys:**
  - interaction -> scenes.Interaction [FK]
  - scene -> scenes.Scene [FK]
**Pointed to by:**
  - spread_assist_target <- societies.SpreadAssistTarget
  - reactions <- scenes.WindowReaction

### Rivalry
**Foreign Keys:**
  - rivaler_tenure -> roster.RosterTenure [FK]
  - rival_tenure -> roster.RosterTenure [FK]

### Scene
**Foreign Keys:**
  - location -> evennia.ObjectDB [FK] (nullable)
  - event -> events.Event [FK] (nullable)
  - running_beat -> stories.Beat [FK] (nullable)
  - participants -> evennia.AccountDB [M2M]
**Pointed to by:**
  - check_calls <- checks.CheckCall
  - treatment_attempts <- conditions.TreatmentAttempt
  - situation_instances <- mechanics.SituationInstance
  - battle <- battles.Battle
  - ceremonies <- ceremonies.Ceremony
  - legend_events <- societies.LegendEvent
  - legend_entries <- societies.LegendEntry
  - legend_spreads <- societies.LegendSpread
  - durance_cohorts_opened_here <- progression.DuranceCohort
  - cohort_enrollments_here <- progression.CohortEnrollment
  - developmenttransaction_set <- progression.DevelopmentTransaction
  - entry_flourish_offers <- magic.PendingEntryFlourishOffer
  - triggered_alterations <- magic.PendingAlteration
  - magicalalterationevent_set <- magic.MagicalAlterationEvent
  - anima_ritual_performances <- magic.AnimaRitualPerformance
  - feedings <- magic.FeedingRecord
  - dramatic_moment_tags <- magic.DramaticMomentTag
  - dramatic_moment_suggestions <- magic.DramaticMomentSuggestion
  - entry_endorsements <- magic.SceneEntryEndorsement
  - style_presentation_endorsements <- magic.StylePresentationEndorsement
  - entry_flourish_records <- magic.EntryFlourishRecord
  - fall_redemption_records <- magic.FallRedemptionRecord
  - covenant_rite_instances <- covenants.CovenantRiteInstance
  - ritual_sessions <- magic.RitualSession
  - sineating_pending_offers <- magic.SineatingPendingOffer
  - pending_stage_advance_offers <- magic.PendingStageAdvanceOffer
  - sineatings <- magic.Sineating
  - rescues <- magic.SoulTetherRescue
  - combat_encounters <- combat.CombatEncounter
  - summon_offers <- gm.GMSummonOffer
  - fashion_showings <- items.FashionShowing
  - npc_regard_events <- npc_services.NpcRegardEvent
  - petitions <- player_submissions.Petition
  - check_proposals <- player_submissions.CheckProposal
  - relationshipupdate_set <- relationships.RelationshipUpdate
  - relationshipdevelopment_set <- relationships.RelationshipDevelopment
  - relationshipcapstone_set <- relationships.RelationshipCapstone
  - affection_shifts <- relationships.AffectionShift
  - participations <- scenes.SceneParticipation
  - unseen_observers <- scenes.SceneUnseenObserver
  - interactions <- scenes.Interaction
  - summary_revisions <- scenes.SceneSummaryRevision
  - check_modifiers <- scenes.SceneCheckModifier
  - scene_rounds <- scenes.SceneRound
  - decisive_markers <- scenes.DecisiveCheckMarker
  - action_requests <- scenes.SceneActionRequest
  - precapture_consent_requests <- scenes.PrecaptureConsentRequest
  - reaction_windows <- scenes.ReactionWindow
  - speaker_queues <- scenes.SpeakerQueue
  - explaining_secrets <- secrets.Secret
  - story_episodes <- stories.EpisodeScene
  - deaths <- vitals.CharacterVitals
  - miracle_performances <- worship.MiraclePerformance

### SceneActionDeclaration
**Foreign Keys:**
  - scene_round -> scenes.SceneRound [FK]
  - participant -> scenes.SceneRoundParticipant [FK]
  - challenge_instance -> mechanics.ChallengeInstance [FK] (nullable)
  - challenge_approach -> mechanics.ChallengeApproach [FK] (nullable)
  - target_persona -> scenes.Persona [FK] (nullable)
  - succor_target -> scenes.SceneRoundParticipant [FK] (nullable)
  - interpose_target -> scenes.SceneRoundParticipant [FK] (nullable)

### SceneActionPullDeclaration
**Foreign Keys:**
  - request -> scenes.SceneActionRequest [OneToOne]
  - resonance -> magic.Resonance [FK]
  - threads -> magic.Thread [M2M]

### SceneActionRequest
**Foreign Keys:**
  - fury_commitment -> magic.FuryTier [FK] (nullable)
  - fury_anchor -> character_sheets.CharacterSheet [FK] (nullable)
  - scene -> scenes.Scene [FK]
  - initiator_persona -> scenes.Persona [FK]
  - target_persona -> scenes.Persona [FK] (nullable)
  - spread_deed_target -> societies.LegendEntry [FK] (nullable)
  - action_template -> actions.ActionTemplate [FK] (nullable)
  - treatment -> conditions.TreatmentTemplate [FK] (nullable)
  - target_condition_instance -> conditions.ConditionInstance [FK] (nullable)
  - target_pending_alteration -> magic.PendingAlteration [FK] (nullable)
  - thread_used -> magic.Thread [FK] (nullable)
  - technique -> magic.Technique [FK] (nullable)
  - snapshot_ritual -> magic.Ritual [FK] (nullable)
  - snapshot_stat -> traits.Trait [FK] (nullable)
  - snapshot_skill -> skills.Skill [FK] (nullable)
  - snapshot_specialization -> skills.Specialization [FK] (nullable)
  - snapshot_resonance -> magic.Resonance [FK] (nullable)
  - snapshot_check_type -> checks.CheckType [FK] (nullable)
  - result_interaction -> scenes.Interaction [OneToOne] (nullable)
  - action_interaction -> scenes.Interaction [OneToOne] (nullable)
  - delivery_receivers -> scenes.Persona [M2M]
  - target_personas -> scenes.Persona [M2M]
**Pointed to by:**
  - additional_targets <- scenes.SceneActionTarget
  - pull_declaration <- scenes.SceneActionPullDeclaration
  - boon <- scenes.Boon

### SceneActionTarget
**Foreign Keys:**
  - action_request -> scenes.SceneActionRequest [FK]
  - target_persona -> scenes.Persona [FK]
  - result_interaction -> scenes.Interaction [OneToOne] (nullable)

### SceneCheckModifier
**Foreign Keys:**
  - scene -> scenes.Scene [FK]
  - check_type -> checks.CheckType [FK]

### SceneParticipation
**Foreign Keys:**
  - scene -> scenes.Scene [FK]
  - account -> evennia.AccountDB [FK]

### SceneRound
**Foreign Keys:**
  - room -> evennia_extensions.RoomProfile [FK]
  - scene -> scenes.Scene [FK] (nullable)
**Pointed to by:**
  - participants <- scenes.SceneRoundParticipant
  - action_declarations <- scenes.SceneActionDeclaration
  - pending_sudden_harms <- scenes.PendingSuddenHarm

### SceneRoundDefaultsConfig
**Foreign Keys:**
  - updated_by -> evennia.AccountDB [FK] (nullable)

### SceneRoundParticipant
**Foreign Keys:**
  - scene_round -> scenes.SceneRound [FK]
  - character_sheet -> character_sheets.CharacterSheet [FK]
**Pointed to by:**
  - action_declarations <- scenes.SceneActionDeclaration
  - succor_declarations <- scenes.SceneActionDeclaration
  - interpose_declarations <- scenes.SceneActionDeclaration

### SceneSummaryRevision
**Foreign Keys:**
  - scene -> scenes.Scene [FK]
  - persona -> scenes.Persona [FK]

### SceneUnseenObserver
**Foreign Keys:**
  - scene -> scenes.Scene [FK]
  - observer -> character_sheets.CharacterSheet [FK]

### SpeakerQueue
**Foreign Keys:**
  - room -> evennia_extensions.RoomProfile [FK]
  - scene -> scenes.Scene [FK] (nullable)
  - opened_by -> scenes.Persona [FK] (nullable)
**Pointed to by:**
  - entries <- scenes.SpeakerQueueEntry

### SpeakerQueueEntry
**Foreign Keys:**
  - speaker_queue -> scenes.SpeakerQueue [FK]
  - persona -> scenes.Persona [FK]

### WindowReaction
**Foreign Keys:**
  - window -> scenes.ReactionWindow [FK]
  - reactor_persona -> scenes.Persona [FK]

### Service Functions
- `active_persona_for_sheet(sheet: 'CharacterSheet') -> 'Persona' - The face a character is currently presenting as (#981).`
- `broadcast_scene_message(scene: 'Scene', action: 'ActionType') -> 'None' - Send scene information to all accounts in the scene's location.`
- `clear_unseen_observer(scene: 'Scene', observer: 'CharacterSheet') -> 'None' - Clear observer's unseen-observation grant on scene; broadcast if it changed`
- `create_mask(sheet: 'CharacterSheet', *, name: 'str', disguise_form: 'CharacterForm | None' = None, disguise_kind: 'str | None' = None) -> 'Persona' - Create a TEMPORARY anonymous **mask** — the "put on a mask" path (#1127).`
- `create_persona(sheet: 'CharacterSheet', *, name: 'str', persona_type: 'str', is_fake_name: 'bool' = False, bypass_cap: 'bool' = False) -> 'Persona' - Create a new ESTABLISHED or TEMPORARY persona for a character (#1127).`
- `has_unseen_observers(scene: 'Scene') -> 'bool' - Whether any unseen-observation grant is currently active on scene (#1225).`
- `invalidate_active_scene_cache(location: 'ObjectDB') -> 'None' - Clear the cached active scene for a location.`
- `persona_discovery_between(persona: 'Persona | None', linked: 'Persona | None', discovered_by: 'CharacterSheet') -> 'PersonaDiscovery | None' - The existing ``PersonaDiscovery`` row for this (unordered) persona pair + discoverer, if`
- `persona_for_character(character: 'Character') -> 'Persona' - Return the PC's PRIMARY persona; raise loud on missing sheet/persona.`
- `record_persona_discovery(persona: 'Persona | None', linked: 'Persona | None', discovered_by: 'CharacterSheet') -> 'PersonaDiscovery | None' - Record that ``discovered_by`` learned ``persona`` and ``linked`` are the same person.`
- `register_unseen_observer(scene: 'Scene', observer: 'CharacterSheet', source_label: 'str') -> 'None' - Record that observer can unseen-witness scene; broadcast the OOC state if new.`
- `set_active_persona(sheet: 'CharacterSheet', persona: 'Persona') -> 'None' - Set the character's active face (#981) — the ONLY mutator.`
- `set_persona_profile(persona: 'Persona', *, concept: 'str | None' = None, quote: 'str | None' = None, personality: 'str | None' = None, background: 'str | None' = None) -> 'Profile' - Author the fabricated bio a non-primary persona presents — its **Guise Sheet** (#1270).`


## world.secrets

### AccusationRebuttal
**Foreign Keys:**
  - secret -> secrets.Secret [FK]
  - refuter_sheet -> character_sheets.CharacterSheet [FK]

### Leverage
**Foreign Keys:**
  - holder_sheet -> character_sheets.CharacterSheet [FK]
  - subject_sheet -> character_sheets.CharacterSheet [FK]
  - founded_on -> secrets.Secret [FK]

### Secret
**Foreign Keys:**
  - subject_sheet -> character_sheets.CharacterSheet [FK]
  - category -> secrets.SecretCategory [FK] (nullable)
  - author_persona -> scenes.Persona [FK] (nullable)
  - legend_deed -> societies.LegendEntry [FK] (nullable)
  - mission_deed -> missions.MissionDeedRecord [FK] (nullable)
  - scene -> scenes.Scene [FK] (nullable)
  - subject_item_template -> items.ItemTemplate [FK] (nullable)
  - subject_item_instance -> items.ItemInstance [FK] (nullable)
  - archetypes -> societies.PhilosophicalArchetype [M2M]
  - societies_exposed -> societies.Society [M2M]
**Pointed to by:**
  - consequence_effects <- checks.ConsequenceEffect
  - clues <- clues.Clue
  - distinction <- distinctions.CharacterDistinction
  - accusation_crime_claim <- justice.AccusationCrimeClaim
  - nullification <- justice.AccusationNullification
  - nullification_authorship <- justice.AccusationNullification
  - denouncements <- justice.DenounceRecord
  - victims <- secrets.SecretVictim
  - grievances <- secrets.SecretGrievance
  - known_by <- secrets.SecretKnowledge
  - gossip_heat <- secrets.SecretGossip
  - leverage <- secrets.Leverage
  - rebuttals <- secrets.AccusationRebuttal

### SecretCategory
**Pointed to by:**
  - secrets <- secrets.Secret

### SecretGossip
**Foreign Keys:**
  - secret -> secrets.Secret [FK]
  - region -> areas.Area [FK]

### SecretGrievance
**Foreign Keys:**
  - secret -> secrets.Secret [FK]
  - victim_sheet -> character_sheets.CharacterSheet [FK]
  - capstone -> relationships.RelationshipCapstone [FK] (nullable)

### SecretKnowledge
**Foreign Keys:**
  - roster_entry -> roster.RosterEntry [FK]
  - secret -> secrets.Secret [FK]

### SecretVictim
**Foreign Keys:**
  - secret -> secrets.Secret [FK]
  - organization -> societies.Organization [FK] (nullable)
  - persona -> scenes.Persona [FK] (nullable)

### Service Functions
- `accusation_permitted(*, framer_sheet: 'CharacterSheet', target_sheet: 'CharacterSheet') -> 'bool' - Target-side consent gate for a frame-job (#1825) — may *framer* accuse *target*?`
- `author_player_flavor_secret(*, subject_sheet: 'CharacterSheet', author_persona: 'Persona', content: 'str', category: 'SecretCategory | None' = None) -> 'Secret' - Author a Level-1 player-flavor secret (the only tier a player may free-write).`
- `author_secret(*, subject_sheet: 'CharacterSheet', provenance: 'str', level: 'int' = SecretLevel.UNCOMMON_KNOWLEDGE, content: 'str' = '', category: 'SecretCategory | None' = None, consequences: 'str' = '', subject_aware: 'bool' = True, author_persona: 'Persona | None' = None, legend_deed: 'LegendEntry | None' = None, mission_deed: 'MissionDeedRecord | None' = None, scene: 'Scene | None' = None) -> 'Secret' - Author a secret about ``subject_sheet``, enforcing the anchor-scales-with-level rule.`
- `character_knows_secret(*, knower_sheet: 'CharacterSheet', secret: 'Secret') -> 'bool' - True if the character (by current tenure) holds knowledge of ``secret`` (#1680).`
- `expose_secret(secret: 'Secret', *, societies: 'Iterable[Society]') -> 'SecretExposureResult' - Fire the reputation consequences of a secret becoming known to ``societies`` (#1429).`
- `grant_secret_knowledge(*, roster_entry: 'RosterEntry', secret: 'Secret', knows_category: 'bool' = False, knows_consequences: 'bool' = False) -> 'SecretKnowledge' - Record that a character knows a secret, unlocking the given layers (idempotent).`
- `has_leverage(*, holder_sheet: 'CharacterSheet', subject_sheet: 'CharacterSheet') -> 'bool' - True if ``holder_sheet`` holds any standing leverage over ``subject_sheet`` (#1680).`
- `known_secrets_for(roster_entry: 'RosterEntry', *, subject_sheet: 'CharacterSheet | None' = None, sort: 'str' = 'recent') -> 'QuerySet[SecretKnowledge]' - The secrets a character has **learned about others** — held records (#1334).`
- `mint_accusation(*, accuser_persona: 'Persona', subject_sheet: 'CharacterSheet', content: 'str', level: 'int' = SecretLevel.UNCOMMON_KNOWLEDGE, category: 'SecretCategory | None' = None, legend_deed: 'LegendEntry | None' = None, mission_deed: 'MissionDeedRecord | None' = None, scene: 'Scene | None' = None) -> 'Secret' - Mint a player-authored ACCUSATION — a false scandal about *someone else* (#1825).`
- `mint_leverage(*, holder_sheet: 'CharacterSheet', subject_sheet: 'CharacterSheet', founded_on: 'Secret') -> 'Leverage' - Record standing leverage ``holder_sheet`` holds over ``subject_sheet`` (#1680).`
- `register_secret_grievance(*, roster_entry: 'RosterEntry', secret: 'Secret', option: 'GrievanceOption | None' = None, custom_points: 'int | None' = None, custom_track: 'RelationshipTrack | None' = None, writeup: 'str' = '') -> 'RelationshipCapstone' - A secret's victim registers a grievance against its subject (#1429).`
- `reveal_leveraged_secret(*, revealer_sheet: 'CharacterSheet', secret: 'Secret') -> 'bool' - Play the blackmail card: expose ``secret`` and spend the leverage founded on it (#1680).`
- `reverse_secret_exposure(secret: 'Secret', *, numerator: 'int' = 1, denominator: 'int' = 1) -> 'None' - Apply compensating reputation bumps for a secret's prior exposure (#1825).`
- `secret_known_to(secret: 'Secret', roster_entry: 'RosterEntry') -> 'bool' - Whether this character already holds the fact of this secret (#1334).`
- `secrets_explaining(*, roster_entry: 'RosterEntry', legend_deed: 'LegendEntry | None' = None, mission_deed: 'MissionDeedRecord | None' = None, scene: 'Scene | None' = None) -> 'QuerySet[SecretKnowledge]' - The secrets a viewer KNOWS that are the hidden truth behind a given act (#1573).`
- `secrets_owned_by(sheet: 'CharacterSheet', *, sort: 'str' = 'level') -> 'QuerySet[Secret]' - The secrets a character **owns** — its own shelf (#1334).`
- `set_secret_act_anchor(secret: 'Secret', *, legend_deed: 'LegendEntry | None' = None, mission_deed: 'MissionDeedRecord | None' = None, scene: 'Scene | None' = None) -> 'Secret' - Set (or clear) the recorded act a secret is the hidden truth behind (#1573).`



## world.ships

### ShipConstructionDetails
**Foreign Keys:**
  - project -> projects.Project [OneToOne]
  - ship_type -> ships.ShipType [FK]
  - owner_persona -> scenes.Persona [FK] (nullable)
  - owner_covenant -> covenants.Covenant [FK] (nullable)
  - resulting_ship -> ships.ShipDetails [OneToOne] (nullable)

### ShipDeployment
**Foreign Keys:**
  - ship -> ships.ShipDetails [FK]
  - battle -> battles.Battle [FK]
  - vehicle -> battles.BattleVehicle [OneToOne]

### ShipDetails
**Foreign Keys:**
  - building -> buildings.Building [OneToOne]
  - ship_type -> ships.ShipType [FK]
**Pointed to by:**
  - deployments <- ships.ShipDeployment
  - upgrade_details <- ships.ShipUpgradeDetails
  - source_construction <- ships.ShipConstructionDetails
  - repair_details <- ships.ShipRepairDetails
  - voyage <- travel.Voyage

### ShipRepairDetails
**Foreign Keys:**
  - project -> projects.Project [OneToOne]
  - ship -> ships.ShipDetails [FK]

### ShipType
**Pointed to by:**
  - ships <- ships.ShipDetails
  - construction_details <- ships.ShipConstructionDetails
  - travel_methods <- travel.TravelMethod

### ShipUpgradeDetails
**Foreign Keys:**
  - project -> projects.Project [OneToOne]
  - ship -> ships.ShipDetails [FK]

### Service Functions
- `complete_ship_construction(project: 'Project', outcome_tier: 'object | None' = None) -> 'ShipDetails' - Kind handler: spawn the ``Building`` + deck room + ``ShipDetails`` exactly once.`
- `complete_ship_repair(project: 'Project', outcome_tier: 'object | None' = None) -> 'None' - Kind handler: clear the ship's ``needs_repair`` flag, exactly once.`
- `complete_ship_upgrade(project: 'Project', outcome_tier: 'object | None' = None) -> 'None' - Kind handler: raise the ship's stat level, exactly once, never downward.`
- `ensure_ship_kind() -> 'BuildingKind' - Get-or-create the ``Vessel`` maritime ``BuildingKind`` row.`
- `start_ship_construction(*, persona: 'Persona', ship_type: 'ShipType', name: 'str', covenant: 'Covenant | None' = None) -> 'Project' - Open a ``SHIP_CONSTRUCTION`` Project commissioning a new ship.`
- `start_ship_hull_upgrade(*, persona: 'Persona', ship: 'ShipDetails', target_level: 'int') -> 'Project' - Open a hull upgrade for *ship*, reusing ``FORTIFICATION_UPGRADE``.`
- `start_ship_repair(*, persona: 'Persona', ship: 'ShipDetails') -> 'Project' - Open a ``SHIP_REPAIR`` Project clearing *ship*'s ``needs_repair`` flag.`
- `start_ship_upgrade(*, persona: 'Persona', ship: 'ShipDetails', stat: 'str', target_level: 'int') -> 'Project' - Open a ``SHIP_UPGRADE`` Project raising *ship*'s *stat* to *target_level*.`


## world.skills

### CharacterSkillValue
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - skill -> skills.Skill [FK]

### CharacterSpecializationValue
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - specialization -> skills.Specialization [FK]

### PathSkillSuggestion
**Foreign Keys:**
  - character_path -> classes.Path [FK]
  - skill -> skills.Skill [FK]

### Skill
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - trait -> traits.Trait [OneToOne]
**Pointed to by:**
  - npc_preset_skill_lines <- roster.NPCPresetSkillLine
  - legend_spreads <- societies.LegendSpread
  - specializations <- skills.Specialization
  - character_values <- skills.CharacterSkillValue
  - path_suggestions <- skills.PathSkillSuggestion
  - training_allocations <- skills.TrainingAllocation

### SkillPointBudget
**Foreign Keys:**
  - teaching_skill -> skills.Skill [FK] (nullable)

### Specialization
**Foreign Keys:**
  - parent_skill -> skills.Skill [FK]
**Pointed to by:**
  - check_type_specializations <- checks.CheckTypeSpecialization
  - character_values <- skills.CharacterSpecializationValue
  - training_allocations <- skills.TrainingAllocation
  - worship_traditions <- worship.WorshipTradition

### TrainingAllocation
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - skill -> skills.Skill [FK] (nullable)
  - specialization -> skills.Specialization [FK] (nullable)
  - mentor -> scenes.Persona [FK] (nullable)

### Service Functions
- `apply_weekly_rust(trained_skills: 'dict[int, set[int]]') -> 'None' - Apply weekly rust to all untrained skills.`
- `calculate_training_development(allocation: 'TrainingAllocation', *, _teaching_skill: 'Skill | None' = <object object>, _path_levels: 'dict[int, int] | None' = None) -> 'int' - Calculate development points earned from a training allocation.`
- `create_training_allocation(character: 'ObjectDB', ap_amount: 'int', *, skill: 'Skill | None' = None, specialization: 'Specialization | None' = None, mentor: 'Persona | None' = None) -> 'TrainingAllocation' - Create a new training allocation for a character.`
- `get_relationship_tier(character_a: evennia.objects.models.ObjectDB, character_b: evennia.objects.models.ObjectDB) -> int - Highest relationship tier character_a holds toward character_b (0 = none).`
- `get_specialization_value(character: 'ObjectDB', specialization: 'Specialization') -> 'int' - A character's raw value for a specialization, 0 if unowned (#1688).`
- `has_specialization(character: 'ObjectDB', specialization: 'Specialization', *, minimum_rank: 'int' = 1) -> 'bool' - Whether a character owns a specialization at ``minimum_rank`` or better (#1688).`
- `is_skill_at_xp_boundary(value: 'int') -> 'bool' - Public wrapper for :func:`_is_at_xp_boundary` (#2115).`
- `process_weekly_training() -> 'dict[int, set[int]]' - Process all training allocations for the weekly tick.`
- `purchase_skill_breakthrough(character: 'ObjectDB', skill: 'Skill') -> 'tuple[bool, str]' - Spend XP to break through a skill's XP-boundary plateau (#2115).`
- `remove_training_allocation(allocation: 'TrainingAllocation') -> 'None' - Delete a training allocation.`
- `run_weekly_skill_cron() -> 'None' - Run the full weekly skill development cycle.`
- `skills_at_boundary(character: 'ObjectDB') -> 'list[SkillBreakthroughProspect]' - Return the character's skills currently parked at an XP boundary (#2115).`
- `update_training_allocation(allocation: 'TrainingAllocation', *, ap_amount: 'int | None' = None, mentor: 'Persona | None' = <object object>) -> 'TrainingAllocation' - Update an existing training allocation.`


## world.societies

### Betrothal
**Foreign Keys:**
  - kinsperson_a -> roster.Kinsperson [FK]
  - kinsperson_b -> roster.Kinsperson [FK]
  - senior_house -> societies.Organization [FK]
  - junior_house -> societies.Organization [FK]
**Pointed to by:**
  - terms <- societies.BetrothalTerm

### BetrothalTerm
**Foreign Keys:**
  - betrothal -> societies.Betrothal [FK]
  - committed_person -> roster.Kinsperson [FK] (nullable)

### CharacterLegendSummary
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [OneToOne]

### CovenantLegendCredit
**Foreign Keys:**
  - entry -> societies.LegendEntry [FK]
  - covenant -> covenants.Covenant [FK]

### CovenantLegendSummary
**Foreign Keys:**
  - covenant -> covenants.Covenant [OneToOne]

### CrisisIntel
**Foreign Keys:**
  - crisis -> societies.DomainCrisis [FK]
  - org -> societies.Organization [FK]

### Domain
**Foreign Keys:**
  - area -> areas.Area [OneToOne]
  - owner_org -> societies.Organization [FK]
**Pointed to by:**
  - food_stockpile <- agriculture.FoodStockpile
  - food_transfers_out <- agriculture.FoodTransfer
  - food_transfers_in <- agriculture.FoodTransfer
  - seat_of <- societies.Title
  - holdings <- societies.DomainHolding
  - improvement_details <- societies.DomainImprovementDetails
  - edicts <- societies.DomainEdict
  - crises <- societies.DomainCrisis
  - affliction_signs <- predators.AfflictionSign

### DomainCrisis
**Foreign Keys:**
  - domain -> societies.Domain [FK] (nullable)
  - org -> societies.Organization [FK] (nullable)
  - crisis_type -> societies.DomainCrisisType [FK] (nullable)
  - chosen_option -> societies.DomainCrisisTypeOption [FK] (nullable)
  - minted_mission -> missions.MissionInstance [FK] (nullable)
  - aggressor_band -> predators.PredatorBand [FK] (nullable)
**Pointed to by:**
  - intel <- societies.CrisisIntel
  - org_tasks_targeting <- tasking.OrgTask

### DomainCrisisType
**Pointed to by:**
  - options <- societies.DomainCrisisTypeOption
  - crises <- societies.DomainCrisis
  - signs <- predators.AfflictionSign

### DomainCrisisTypeOption
**Foreign Keys:**
  - crisis_type -> societies.DomainCrisisType [FK]
  - mission_template -> missions.MissionTemplate [FK] (nullable)
**Pointed to by:**
  - chosen_on <- societies.DomainCrisis

### DomainEdict
**Foreign Keys:**
  - domain -> societies.Domain [FK]
  - kind -> societies.EdictKind [FK]
  - proclamation -> societies.Proclamation [FK] (nullable)
  - enacted_by -> scenes.Persona [FK]

### DomainHolding
**Foreign Keys:**
  - domain -> societies.Domain [FK]
  - kind -> societies.HoldingKind [FK]
  - income_stream -> currency.OrgIncomeStream [OneToOne] (nullable)
**Pointed to by:**
  - material_sources <- societies.HoldingMaterialSource
  - improvement_details <- societies.DomainImprovementDetails

### DomainImprovementDetails
**Foreign Keys:**
  - project -> projects.Project [OneToOne]
  - domain -> societies.Domain [FK]
  - holding -> societies.DomainHolding [FK] (nullable)

### EdictKind
**Foreign Keys:**
  - stance -> societies.StanceArchetype [FK]
**Pointed to by:**
  - enactments <- societies.DomainEdict

### FealtyEdge
**Foreign Keys:**
  - vassal -> societies.Organization [OneToOne]
  - liege -> societies.Organization [FK]

### GangTurfDetails
**Foreign Keys:**
  - project -> projects.Project [OneToOne]
  - organization -> societies.Organization [FK]
  - target_area -> areas.Area [FK] (nullable)
**Pointed to by:**
  - tier_thresholds <- societies.GangTurfTierThreshold

### GangTurfReputationAward
**Foreign Keys:**
  - outcome_tier -> traits.CheckOutcome [OneToOne]

### GangTurfTierThreshold
**Foreign Keys:**
  - details -> societies.GangTurfDetails [FK]
  - outcome_tier -> traits.CheckOutcome [FK]

### HoldingKind
**Pointed to by:**
  - holdings <- societies.DomainHolding
  - house_templates <- societies.HouseTemplate

### HoldingMaterialSource
**Foreign Keys:**
  - holding -> societies.DomainHolding [FK]
  - material_category -> items.MaterialCategory [FK]

### HouseAspectDefinition
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
**Pointed to by:**
  - templates <- societies.HouseTemplate
  - options <- societies.HouseAspectOption

### HouseAspectOption
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - definition -> societies.HouseAspectDefinition [FK]
  - codex_entry -> codex.CodexEntry [FK] (nullable)

### HouseClaim
**Foreign Keys:**
  - draft -> character_creation.CharacterDraft [OneToOne]
  - title -> societies.Title [FK]
  - template -> societies.HouseTemplate [FK]
  - reviewed_by -> evennia.AccountDB [FK] (nullable)
**Pointed to by:**
  - aspects <- societies.HouseClaimAspect

### HouseClaimAspect
**Foreign Keys:**
  - claim -> societies.HouseClaim [FK]
  - definition -> societies.HouseAspectDefinition [FK]
  - option -> societies.HouseAspectOption [FK]

### HouseFeature
**Pointed to by:**
  - templates <- societies.HouseTemplate
  - organization_features <- societies.OrganizationFeature

### HouseRecognitionRule
**Foreign Keys:**
  - realm -> realms.Realm [FK]

### HouseStature
**Foreign Keys:**
  - organization -> societies.Organization [OneToOne]
  - band -> societies.StatureBand [FK] (nullable)
  - previous_band -> societies.StatureBand [FK] (nullable)

### HouseTemplate
**Foreign Keys:**
  - realm -> realms.Realm [FK]
  - society -> societies.Society [FK]
  - liege -> societies.Organization [FK]
  - default_succession_law -> societies.SuccessionLaw [FK]
  - holdings -> societies.HoldingKind [M2M]
  - aspect_definitions -> societies.HouseAspectDefinition [M2M]
  - features -> societies.HouseFeature [M2M]
**Pointed to by:**
  - claims <- societies.HouseClaim

### LegendContribution
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - activation -> stories.StakeContractActivation [FK]
  - check_type -> checks.CheckType [FK]
  - stake -> stories.Stake [FK] (nullable)

### LegendDeedStory
**Foreign Keys:**
  - deed -> societies.LegendEntry [FK]
  - author -> scenes.Persona [FK]
**Pointed to by:**
  - legend_honors <- societies.LegendHonor

### LegendEntry
**Foreign Keys:**
  - persona -> scenes.Persona [FK]
  - event -> societies.LegendEvent [FK] (nullable)
  - source_type -> societies.LegendSourceType [FK] (nullable)
  - scene -> scenes.Scene [FK] (nullable)
  - story -> stories.Story [FK] (nullable)
  - societies_aware -> societies.Society [M2M]
  - archetypes -> societies.PhilosophicalArchetype [M2M]
**Pointed to by:**
  - titles <- achievements.PersonaTitle
  - spread_assist_targets <- societies.SpreadAssistTarget
  - spreads <- societies.LegendSpread
  - deed_stories <- societies.LegendDeedStory
  - honors <- societies.LegendHonor
  - knowledge_rows <- societies.PersonaDeedKnowledge
  - covenant_credits <- societies.CovenantLegendCredit
  - audere_majora_crossing <- magic.AudereMajoraCrossing
  - linked_items <- items.ItemInstance
  - crime_tags <- justice.DeedCrimeTag
  - heat_sources <- justice.HeatSource
  - frame_claims <- justice.AccusationCrimeClaim
  - crime_evidence <- justice.CrimeEvidence
  - mission_deeds <- missions.MissionDeedRecord
  - spread_action_requests <- scenes.SceneActionRequest
  - explaining_secrets <- secrets.Secret

### LegendEvent
**Foreign Keys:**
  - source_type -> societies.LegendSourceType [FK]
  - scene -> scenes.Scene [FK] (nullable)
  - story -> stories.Story [FK] (nullable)
  - created_by -> evennia.AccountDB [FK] (nullable)
**Pointed to by:**
  - deeds <- societies.LegendEntry

### LegendHonor
**Foreign Keys:**
  - deed -> societies.LegendEntry [FK]
  - honorer -> scenes.Persona [FK]
  - journal_entry -> journals.JournalEntry [FK]
  - deed_story -> societies.LegendDeedStory [FK] (nullable)
  - hares -> currency.FavorTokenDetails [M2M]

### LegendLevelCalibration

### LegendSettlementConfig

### LegendSourceType
**Pointed to by:**
  - consequence_effects <- checks.ConsequenceEffect
  - events <- societies.LegendEvent
  - deeds <- societies.LegendEntry

### LegendSpread
**Foreign Keys:**
  - legend_entry -> societies.LegendEntry [FK]
  - spreader_persona -> scenes.Persona [FK]
  - skill -> skills.Skill [FK] (nullable)
  - scene -> scenes.Scene [FK] (nullable)
  - societies_reached -> societies.Society [M2M]

### MarriagePact
**Foreign Keys:**
  - union -> roster.Union [OneToOne]
  - senior_house -> societies.Organization [FK]
  - junior_house -> societies.Organization [FK]
**Pointed to by:**
  - commitments <- societies.PactCommitment

### NeighborhoodTurf
**Foreign Keys:**
  - area -> areas.Area [OneToOne]
  - controlling_org -> societies.Organization [FK] (nullable)

### NobiliaryParticle
**Foreign Keys:**
  - realm -> realms.Realm [FK]

### OrgAppeal
**Foreign Keys:**
  - organization -> societies.Organization [FK]
  - petitioner_persona -> scenes.Persona [FK]
  - resolved_by_persona -> scenes.Persona [FK] (nullable)
**Pointed to by:**
  - signons <- societies.OrgAppealSignon

### OrgAppealSignon
**Foreign Keys:**
  - appeal -> societies.OrgAppeal [FK]
  - member_persona -> scenes.Persona [FK]

### OrgPact
**Foreign Keys:**
  - kind -> societies.PactKind [FK]
  - party_a -> societies.Organization [FK]
  - party_b -> societies.Organization [FK]
  - proposed_by -> scenes.Persona [FK] (nullable)
  - obligation -> currency.OrgObligation [OneToOne] (nullable)

### OrgPrestigeRank
**Foreign Keys:**
  - organization -> societies.Organization [OneToOne]

### Organization
**Foreign Keys:**
  - family -> roster.Family [FK] (nullable)
  - parent_org -> societies.Organization [FK] (nullable)
  - tradition -> magic.Tradition [FK] (nullable)
  - default_succession_law -> societies.SuccessionLaw [FK] (nullable)
  - society -> societies.Society [FK] (nullable)
  - org_type -> societies.OrganizationType [FK]
**Pointed to by:**
  - held_assets <- assets.NPCAsset
  - capture_consequence_effects <- checks.ConsequenceEffect
  - boards <- boards.Board
  - building_listings <- buildings.BuildingListing
  - captives <- captivity.Captivity
  - child_orgs <- societies.Organization
  - ranks <- societies.OrganizationRank
  - gift_grants <- societies.OrganizationGiftGrant
  - membership_offers <- societies.OrganizationMembershipOffer
  - memberships <- societies.OrganizationMembership
  - offices <- societies.OrganizationOffice
  - appeals <- societies.OrgAppeal
  - reputations <- societies.OrganizationReputation
  - standing_declarations <- societies.StandingDeclaration
  - proclamations <- societies.Proclamation
  - held_turf <- societies.NeighborhoodTurf
  - gang_turf_projects <- societies.GangTurfDetails
  - personal_obligations_owed <- societies.OrganizationObligation
  - fealty <- societies.FealtyEdge
  - vassal_edges <- societies.FealtyEdge
  - titles <- societies.Title
  - domains <- societies.Domain
  - org_crises <- societies.DomainCrisis
  - crisis_intel <- societies.CrisisIntel
  - pacts_as_senior <- societies.MarriagePact
  - pacts_as_junior <- societies.MarriagePact
  - house_templates <- societies.HouseTemplate
  - aspects <- societies.OrganizationAspect
  - features <- societies.OrganizationFeature
  - stature <- societies.HouseStature
  - stature_shifts <- societies.StatureShift
  - prestige_rank_row <- societies.OrgPrestigeRank
  - pacts_as_party_a <- societies.OrgPact
  - pacts_as_party_b <- societies.OrgPact
  - betrothals_as_senior <- societies.Betrothal
  - betrothals_as_junior <- societies.Betrothal
  - durance_cohorts <- progression.DuranceCohort
  - covenant <- covenants.Covenant
  - ritualsessionreference_set <- magic.RitualSessionReference
  - anchored_threads <- magic.Thread
  - treasury <- currency.OrganizationTreasury
  - issued_favor_tokens <- currency.FavorTokenDetails
  - economics <- currency.OrgEconomicsProfile
  - income_streams <- currency.OrgIncomeStream
  - obligations_owed <- currency.OrgObligation
  - obligations_due <- currency.OrgObligation
  - contributions <- currency.ContributionRecord
  - debts <- currency.DebtInstrument
  - loans_extended <- currency.DebtInstrument
  - contracts_proposed <- currency.Contract
  - contracts_received <- currency.Contract
  - contracts_notarized <- currency.Contract
  - bequests_received <- estates.Bequest
  - estate_claims <- estates.EstateClaim
  - event_invitations <- events.EventInvitation
  - vault_access_entries <- room_features.VaultAccessEntry
  - npc_roles <- npc_services.NPCRole
  - loan_offers <- npc_services.LoanOfferDetails
  - regards_as_target <- npc_services.NpcRegard
  - hosted_stalls <- items.MarketStall
  - material_stocks <- items.OrgMaterialStock
  - item_vault <- items.OrganizationVault
  - ownership_records <- locations.LocationOwnership
  - tenancies <- locations.LocationTenancy
  - military_units <- military.MilitaryUnit
  - gemits <- narrative.Gemit
  - stalking_predators <- predators.PredatorBand
  - secret_victimhoods <- secrets.SecretVictim
  - org_tasks <- tasking.OrgTask
  - org_tasks_targeting <- tasking.OrgTask
  - capability_projects <- societies.OrganizationCapabilityProjectDetails

### OrganizationAspect
**Foreign Keys:**
  - organization -> societies.Organization [FK]
  - definition -> societies.HouseAspectDefinition [FK]
  - option -> societies.HouseAspectOption [FK]

### OrganizationCapabilityProjectDetails
**Foreign Keys:**
  - project -> projects.Project [OneToOne]
  - gift -> magic.Gift [FK]
  - organization -> societies.Organization [FK]

### OrganizationFeature
**Foreign Keys:**
  - organization -> societies.Organization [FK]
  - feature -> societies.HouseFeature [FK]

### OrganizationGiftGrant
**Foreign Keys:**
  - organization -> societies.Organization [FK]
  - gift -> magic.Gift [FK]
  - project -> projects.Project [FK] (nullable)

### OrganizationMembership
**Foreign Keys:**
  - organization -> societies.Organization [FK]
  - persona -> scenes.Persona [FK]
  - rank -> societies.OrganizationRank [FK] (nullable)
  - covert_secret -> secrets.Secret [FK] (nullable)

### OrganizationMembershipOffer
**Foreign Keys:**
  - organization -> societies.Organization [FK]
  - from_persona -> scenes.Persona [FK]
  - to_persona -> scenes.Persona [FK] (nullable)

### OrganizationObligation
**Foreign Keys:**
  - debtor -> character_sheets.CharacterSheet [FK]
  - creditor -> societies.Organization [FK]
  - settled_by_token -> currency.FavorTokenDetails [FK] (nullable)

### OrganizationOffice
**Foreign Keys:**
  - organization -> societies.Organization [FK]
  - holder -> scenes.Persona [FK] (nullable)
  - feeds_check -> traits.Trait [FK] (nullable)

### OrganizationRank
**Foreign Keys:**
  - organization -> societies.Organization [FK]
**Pointed to by:**
  - memberships <- societies.OrganizationMembership

### OrganizationReputation
**Foreign Keys:**
  - persona -> scenes.Persona [FK]
  - organization -> societies.Organization [FK]

### OrganizationType
**Pointed to by:**
  - organizations <- societies.Organization

### PactCommitment
**Foreign Keys:**
  - pact -> societies.MarriagePact [FK]
  - committed_person -> roster.Kinsperson [FK] (nullable)
  - obligation -> currency.OrgObligation [OneToOne] (nullable)

### PactKind
**Pointed to by:**
  - pacts <- societies.OrgPact

### PersonaDeedKnowledge
**Foreign Keys:**
  - persona -> scenes.Persona [FK]
  - deed -> societies.LegendEntry [FK]

### PersonaLegendSummary
**Foreign Keys:**
  - persona -> scenes.Persona [OneToOne]

### PhilosophicalArchetype
**Pointed to by:**
  - legend_entries <- societies.LegendEntry
  - propagandacampaigntier_renown_configs <- societies.PropagandaCampaignTier
  - propagandadetails_renown_configs <- societies.PropagandaDetails
  - auderemajorathreshold_renown_configs <- magic.AudereMajoraThreshold
  - dramaticmomenttype_renown_configs <- magic.DramaticMomentType
  - mission_awards <- missions.MissionRenownAward
  - secrets <- secrets.Secret

### PrestigeRankBand

### Proclamation
**Foreign Keys:**
  - issuer -> scenes.Persona [FK]
  - org -> societies.Organization [FK] (nullable)
  - stance -> societies.StanceArchetype [FK]
  - check_outcome -> traits.CheckOutcome [FK] (nullable)
**Pointed to by:**
  - edicts <- societies.DomainEdict

### PropagandaCampaignTier
**Foreign Keys:**
  - archetypes -> societies.PhilosophicalArchetype [M2M]
**Pointed to by:**
  - campaigns <- societies.PropagandaDetails

### PropagandaDetails
**Foreign Keys:**
  - project -> projects.Project [OneToOne]
  - source_tier -> societies.PropagandaCampaignTier [FK] (nullable)
  - archetypes -> societies.PhilosophicalArchetype [M2M]

### RankingBandLabel
**Foreign Keys:**
  - society -> societies.Society [FK] (nullable)

### RankingDisplay
**Foreign Keys:**
  - display_object -> evennia.ObjectDB [OneToOne]
  - scope_society -> societies.Society [FK] (nullable)

### RenownMagnitudeAward

### Society
**Foreign Keys:**
  - realm -> realms.Realm [FK]
  - current_fashion_style -> items.FashionStyle [FK] (nullable)
**Pointed to by:**
  - dominant_areas <- areas.Area
  - connected_beginnings <- character_creation.Beginnings
  - organizations <- societies.Organization
  - reputations <- societies.SocietyReputation
  - known_legend_entries <- societies.LegendEntry
  - heard_legend_spreads <- societies.LegendSpread
  - ranking_displays <- societies.RankingDisplay
  - ranking_band_labels <- societies.RankingBandLabel
  - house_templates <- societies.HouseTemplate
  - hosted_events <- events.Event
  - event_invitations <- events.EventInvitation
  - fashion_presentations <- items.FashionPresentation
  - facet_momentum <- items.FacetVogueMomentum
  - trendsetters <- items.Trendsetter
  - name_cultures <- npc_services.NameCulture
  - regards_as_target <- npc_services.NpcRegard
  - heat_rows <- justice.PersonaHeat
  - pardons <- justice.PardonGrant
  - justice_cases <- justice.JusticeCase
  - exile_decrees <- justice.ExileDecree
  - sentence_ladder <- justice.SentenceLadderRung
  - gemits <- narrative.Gemit
  - exposed_secrets <- secrets.Secret

### SocietyReputation
**Foreign Keys:**
  - persona -> scenes.Persona [FK]
  - society -> societies.Society [FK]

### SpreadAssistTarget
**Foreign Keys:**
  - window -> scenes.ReactionWindow [OneToOne]
  - legend_entry -> societies.LegendEntry [FK]

### SpreadingConfig

### StanceArchetype
**Pointed to by:**
  - proclamations <- societies.Proclamation
  - edict_kinds <- societies.EdictKind

### StandingDeclaration
**Foreign Keys:**
  - organization -> societies.Organization [FK]
  - target_persona -> scenes.Persona [FK]
  - declared_by_persona -> scenes.Persona [FK]
  - game_week -> game_clock.GameWeek [FK]

### StatureBand
**Pointed to by:**
  - current_orgs <- societies.HouseStature

### StatureShift
**Foreign Keys:**
  - organization -> societies.Organization [FK]
  - subject_kinsperson -> roster.Kinsperson [FK] (nullable)
  - subject_persona -> scenes.Persona [FK] (nullable)

### SuccessionLaw
**Foreign Keys:**
  - chosen_heir -> roster.Kinsperson [FK] (nullable)
**Pointed to by:**
  - houses_defaulting <- societies.Organization
  - titles <- societies.Title
  - house_templates <- societies.HouseTemplate

### Title
**Foreign Keys:**
  - realm -> realms.Realm [FK]
  - house -> societies.Organization [FK] (nullable)
  - holder -> roster.Kinsperson [FK] (nullable)
  - seat_domain -> societies.Domain [FK] (nullable)
  - succession_law -> societies.SuccessionLaw [FK] (nullable)
**Pointed to by:**
  - coronation_ceremonies <- ceremonies.Ceremony
  - coronations <- ceremonies.Coronation
  - claims <- societies.HouseClaim

### Service Functions
- `create_legend_event(title: 'str', source_type: 'LegendSourceType', base_value: 'int', personas: 'list[Persona]', *, description: 'str' = '', scene: 'Scene | None' = None, story: 'Story | None' = None, created_by: 'AccountDB | None' = None, crime_kinds: 'list | None' = None, archetypes: 'list | None' = None, concealed: 'bool' = False, containment_approach: 'str | None' = None, stations_by_persona: 'dict[int, int] | None' = None) -> 'tuple[LegendEvent, list[LegendEntry]]' - Create a shared event and individual deeds for each participant.`
- `create_solo_deed(persona: 'Persona', title: 'str', source_type: 'LegendSourceType', base_value: 'int', *, description: 'str' = '', scene: 'Scene | None' = None, story: 'Story | None' = None, crime_kinds: 'list | None' = None, archetypes: 'list | None' = None, concealed: 'bool' = False, containment_approach: 'str | None' = None, earned_at_level: 'int' = 0, event: 'LegendEvent | None' = None) -> 'LegendEntry' - Create a solo legend deed, optionally anchored to a shared event's ceiling.`
- `credit_engaged_covenants(*, entry: 'LegendEntry') -> 'list[CovenantLegendCredit]' - Snapshot the persona's currently-engaged covenants and create credit rows.`
- `get_character_legend_total(character: 'ObjectDB') -> 'int' - Fast lookup of a character's total legend from materialized view.`
- `get_character_role_legend(*, character_sheet: 'CharacterSheet', role: 'CovenantRole', covenant_ids: 'list[int] | None' = None) -> 'int' - Sum the legend this character earned that was credited to covenants where they held ``role``.`
- `get_covenant_legend_total(covenant: 'Covenant') -> 'int' - Return the covenant's total legend from the materialized view.`
- `get_covenant_legend_totals(covenant_ids: 'list[int]') -> 'dict[int, int]' - Bulk sibling of ``get_covenant_legend_total`` — one query for a page of covenants.`
- `get_persona_legend_total(persona: 'Persona') -> 'int' - Per-persona legend lookup from materialized view.`
- `refresh_legend_views() -> None - Refresh all legend materialized views concurrently.`
- `spread_deed(deed: 'LegendEntry', spreader_persona: 'Persona', value_added: 'int', *, description: 'str' = '', method: 'str' = '', skill: 'Skill | None' = None, audience_factor: 'Decimal' = Decimal('1.0'), scene: 'Scene | None' = None, societies_reached: 'list[Society] | None' = None) -> 'LegendSpread' - Record a spreading action and add legend value, clamped to capacity.`
- `spread_event(event: 'LegendEvent', spreader_persona: 'Persona', value_per_deed: 'int', *, description: 'str' = '', method: 'str' = '', skill: 'Skill | None' = None, audience_factor: 'Decimal' = Decimal('1.0'), scene: 'Scene | None' = None, societies_reached: 'list[Society] | None' = None) -> 'list[LegendSpread]' - Spread all active deeds linked to an event at once.`


## world.species

### Language
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - trait -> traits.Trait [OneToOne] (nullable)
**Pointed to by:**
  - beginnings <- character_creation.Beginnings
  - native_species <- species.Species

### Species
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - parent -> species.Species [FK] (nullable)
  - codex_entry -> codex.CodexEntry [FK] (nullable)
  - starting_languages -> species.Language [M2M]
**Pointed to by:**
  - kinspeople <- roster.Kinsperson
  - beginnings <- character_creation.Beginnings
  - drafts <- character_creation.CharacterDraft
  - character_sheets <- character_sheets.CharacterSheet
  - children <- species.Species
  - stat_bonuses <- species.SpeciesStatBonus
  - gift_grants <- species.SpeciesGiftGrant
  - form_traits <- forms.SpeciesFormTrait

### SpeciesGiftGrant
**Foreign Keys:**
  - species -> species.Species [FK]
  - gift -> magic.Gift [FK]
  - drawback_condition -> conditions.ConditionTemplate [FK] (nullable)
  - benefit_condition -> conditions.ConditionTemplate [FK] (nullable)
  - drawback_distinction -> distinctions.Distinction [FK] (nullable)

### SpeciesStatBonus
**Foreign Keys:**
  - species -> species.Species [FK]

### Service Functions
- `advance_condition_severity(instance: world.conditions.models.ConditionInstance, amount: int) -> world.conditions.types.SeverityAdvanceResult - Increment a condition's severity and advance stage if threshold crossed.`
- `apply_condition(target: 'ObjectDB', condition: world.conditions.models.ConditionTemplate, *, severity: int = 1, duration_rounds: int | None = None, source_character: 'ObjectDB | None' = None, source_technique: 'Technique | None' = None, source_description: str = '') -> world.conditions.types.ApplyConditionResult - Apply a condition to a target, handling stacking and interactions.`
- `decay_condition_severity(instance: world.conditions.models.ConditionInstance, amount: int, *, _skip_corruption_sync: bool = False) -> world.conditions.types.SeverityDecayResult - Inverse of advance_condition_severity. Walks stage down if threshold crossed.`
- `ensure_round_for_acute_condition(character_sheet: 'CharacterSheet') -> 'SceneRound | None' - Ensure an active scene round exists for the character's room and enrol all present`
- `has_condition(target: 'ObjectDB', condition: world.conditions.models.ConditionTemplate, *, include_suppressed: bool = False) -> bool - Check if target has a specific condition.`
- `provision_species_gifts(sheet: 'CharacterSheet', *, resonance=None) -> 'list[CharacterGift]' - Mint the species' Minor Gift(s) + latent GIFT thread + any drawback. Idempotent.`
- `provision_starting_languages(sheet: 'CharacterSheet', *, beginnings: 'Beginnings | None') -> 'list[Language]' - Grant CG starting languages as fluent CharacterTraitValue rows. Idempotent.`
- `reconcile_sun_exposure_safely(character) -> 'None' - Best-effort sun reconcile for hook/cron call sites (#2846).`
- `reconcile_sunlight_exposure(character, room) -> 'None' - Reconcile the Sunlight Exposure condition to the character's felt sun exposure`
- `remove_condition(target: 'ObjectDB', condition: world.conditions.models.ConditionTemplate, *, remove_all_stacks: bool = True, include_suppressed: bool = False) -> bool - Remove a condition from a target.`
- `run_reconcile_safely(character, reconcile, label: 'str') -> 'None' - Best-effort celestial reconcile for hook/cron call sites (#2846/#2845).`
- `species_innate_distinction_ids(species) -> 'set[int]' - Distinction pks the species (or inheritable ancestors) stamps at finalize (#2846).`
- `total_species_gift_cost(species) -> 'int' - Total CG-point cost of a species' gift grants, summed over it and its ancestors.`


## world.staff_inbox

### Service Functions
- `get_account_submission_history(account_id: 'int') -> 'dict[str, dict[str, Any]]' - Return all submissions related to an account.`
- `get_staff_inbox(*, categories: 'list[str] | None' = None, include_ignored: 'bool' = False) -> 'list[InboxItem]' - Aggregate open items from all submission sources.`
- `sender_context(account: 'AccountDB') -> 'dict' - Kudos + standing columns shown beside every submission.`


## world.stealth

### Service Functions
- `concealed_template() -> 'ConditionTemplate | None' - The seeded Concealed ConditionTemplate, or None when unseeded.`
- `is_sneaking(character: 'ObjectDB') -> 'bool' - Whether the character currently holds sneak-sourced concealment.`
- `mark_room_rolled(character: 'ObjectDB') -> 'None' - Stamp the per-room anti-spam token: one sneak roll per room per visit.`
- `refresh_room_state(character: 'ObjectDB') -> 'None' - Re-broadcast room_state at the character's location.`
- `reroll_on_arrival(character: 'ObjectDB') -> 'bool' - Per-room re-roll as a sneaking character arrives somewhere new.`
- `roll_sneak(character: 'ObjectDB') -> 'CheckResult' - One concealment roll — the SNEAK security oracle vs the base difficulty.`
- `room_already_rolled(character: 'ObjectDB') -> 'bool' - Whether this room's one sneak roll has already happened this visit.`
- `sneak_instance(character: 'ObjectDB') -> 'ConditionInstance | None' - The character's active sneak-sourced Concealed instance, or None.`
- `start_sneaking(character: 'ObjectDB') -> 'bool' - Apply sneak-sourced concealment after a passed roll. Returns success.`
- `stop_sneaking(character: 'ObjectDB') -> 'bool' - Remove sneak-sourced concealment (unsneak / guard strip / failed arrival).`


## world.stories

### AggregateBeatContribution
**Foreign Keys:**
  - beat -> stories.Beat [FK]
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - roster_entry -> roster.RosterEntry [FK] (nullable)
  - era -> stories.Era [FK] (nullable)

### AssistantGMClaim
**Foreign Keys:**
  - beat -> stories.Beat [FK]
  - assistant_gm -> gm.GMProfile [FK]
  - approved_by -> gm.GMProfile [FK] (nullable)

### Beat
**Foreign Keys:**
  - episode -> stories.Episode [FK]
  - required_achievement -> achievements.Achievement [FK] (nullable)
  - required_condition_template -> conditions.ConditionTemplate [FK] (nullable)
  - required_codex_entry -> codex.CodexEntry [FK] (nullable)
  - referenced_story -> stories.Story [FK] (nullable)
  - referenced_chapter -> stories.Chapter [FK] (nullable)
  - referenced_episode -> stories.Episode [FK] (nullable)
  - required_society -> societies.Society [FK] (nullable)
  - required_organization -> societies.Organization [FK] (nullable)
  - required_mission -> missions.MissionTemplate [FK] (nullable)
  - success_consequences -> actions.ConsequencePool [FK] (nullable)
  - failure_consequences -> actions.ConsequencePool [FK] (nullable)
  - expired_consequences -> actions.ConsequencePool [FK] (nullable)
**Pointed to by:**
  - resolving_battles <- battles.Battle
  - resolving_encounters <- combat.CombatEncounter
  - running_scenes <- scenes.Scene
  - decisive_markers <- scenes.DecisiveCheckMarker
  - opponent_lines <- stories.BeatOpponentLine
  - staged_templates <- stories.BeatStagedTemplate
  - gating_for_episodes <- stories.EpisodeProgressionRequirement
  - routing_for_transitions <- stories.TransitionRequiredOutcome
  - aggregate_contributions <- stories.AggregateBeatContribution
  - completions <- stories.BeatCompletion
  - assistant_claims <- stories.AssistantGMClaim
  - stakes <- stories.Stake
  - stake_activations <- stories.StakeContractActivation
  - treasured_signoffs <- stories.TreasuredSignoff
  - protected_subjects <- stories.StoryProtectedSubject

### BeatCompletion
**Foreign Keys:**
  - beat -> stories.Beat [FK]
  - character_sheet -> character_sheets.CharacterSheet [FK] (nullable)
  - gm_table -> gm.GMTable [FK] (nullable)
  - ran_by_table -> gm.GMTable [FK] (nullable)
  - roster_entry -> roster.RosterEntry [FK] (nullable)
  - outcome_tier -> traits.CheckOutcome [FK] (nullable)
  - era -> stories.Era [FK] (nullable)
**Pointed to by:**
  - narrative_messages <- narrative.NarrativeMessage

### BeatOpponentLine
**Foreign Keys:**
  - beat -> stories.Beat [FK]
  - creature_template -> combat.CreatureTemplate [FK]

### BeatStagedTemplate
**Foreign Keys:**
  - beat -> stories.Beat [FK]
  - situation_template -> mechanics.SituationTemplate [FK] (nullable)
  - challenge_template -> mechanics.ChallengeTemplate [FK] (nullable)

### CanonReview
**Foreign Keys:**
  - story -> stories.Story [FK]
  - reviewer -> evennia.AccountDB [FK] (nullable)

### Chapter
**Foreign Keys:**
  - story -> stories.Story [FK]
**Pointed to by:**
  - episodes <- stories.Episode

### CrossoverInvite
**Foreign Keys:**
  - event -> events.Event [FK]
  - from_gm -> gm.GMProfile [FK]
  - to_story -> stories.Story [FK]
  - proposed_episode -> stories.Episode [FK] (nullable)
  - accepted_episode -> stories.Episode [FK] (nullable)

### CustodyClearance
**Foreign Keys:**
  - protected_subject -> stories.StoryProtectedSubject [FK]
  - requested_by -> gm.GMProfile [FK]
  - requesting_story -> stories.Story [FK] (nullable)
  - requesting_beat -> stories.Beat [FK] (nullable)
  - granted_by -> gm.GMProfile [FK] (nullable)
  - staff_resolver -> evennia.AccountDB [FK] (nullable)

### Episode
**Foreign Keys:**
  - chapter -> stories.Chapter [FK]
**Pointed to by:**
  - episode_scenes <- stories.EpisodeScene
  - outbound_transitions <- stories.Transition
  - inbound_transitions <- stories.Transition
  - beats <- stories.Beat
  - progression_requirements <- stories.EpisodeProgressionRequirement
  - resolutions <- stories.EpisodeResolution
  - active_group_progress_records <- stories.GroupStoryProgress
  - active_global_progress_records <- stories.GlobalStoryProgress
  - active_progress_records <- stories.StoryProgress
  - session_requests <- stories.SessionRequest
  - crossover_invites <- stories.CrossoverInvite
  - crossover_invites_accepted <- stories.CrossoverInvite

### EpisodeProgressionRequirement
**Foreign Keys:**
  - episode -> stories.Episode [FK]
  - beat -> stories.Beat [FK]

### EpisodeResolution
**Foreign Keys:**
  - episode -> stories.Episode [FK]
  - character_sheet -> character_sheets.CharacterSheet [FK] (nullable)
  - gm_table -> gm.GMTable [FK] (nullable)
  - chosen_transition -> stories.Transition [FK] (nullable)
  - resolved_by -> gm.GMProfile [FK] (nullable)
  - era -> stories.Era [FK] (nullable)
**Pointed to by:**
  - narrative_messages <- narrative.NarrativeMessage

### EpisodeScene
**Foreign Keys:**
  - episode -> stories.Episode [FK]
  - scene -> scenes.Scene [FK]

### Era
**Pointed to by:**
  - profile_text_versions <- character_sheets.ProfileTextVersion
  - recorded_profiles <- npc_services.RecordedProfile
  - gemits <- narrative.Gemit
  - stories_created_in_era <- stories.Story
  - aggregate_contributions <- stories.AggregateBeatContribution
  - beat_completions <- stories.BeatCompletion
  - episode_resolutions <- stories.EpisodeResolution

### GlobalStoryProgress
**Foreign Keys:**
  - story -> stories.Story [OneToOne]
  - current_episode -> stories.Episode [FK] (nullable)
  - resolved_by -> gm.GMProfile [FK] (nullable)

### GroupStoryProgress
**Foreign Keys:**
  - story -> stories.Story [FK]
  - gm_table -> gm.GMTable [FK]
  - current_episode -> stories.Episode [FK] (nullable)
  - resolved_by -> gm.GMProfile [FK] (nullable)

### GroupStoryRequest
**Foreign Keys:**
  - covenant -> covenants.Covenant [FK]
  - requested_by_account -> evennia.AccountDB [FK]
  - claimed_by -> gm.GMProfile [FK] (nullable)
  - created_story -> stories.Story [FK] (nullable)

### PlayerTrust
**Foreign Keys:**
  - account -> evennia.AccountDB [OneToOne]
  - trust_categories -> stories.TrustCategory [M2M]
**Pointed to by:**
  - trust_levels <- stories.PlayerTrustLevel

### PlayerTrustLevel
**Foreign Keys:**
  - player_trust -> stories.PlayerTrust [FK]
  - trust_category -> stories.TrustCategory [FK]

### RiskCalibration

### SessionRequest
**Foreign Keys:**
  - episode -> stories.Episode [FK]
  - event -> events.Event [FK] (nullable)
  - assigned_gm -> gm.GMProfile [FK] (nullable)
  - initiated_by_account -> evennia.AccountDB [FK] (nullable)

### Stake
**Foreign Keys:**
  - subject_sheet -> character_sheets.CharacterSheet [FK] (nullable)
  - subject_item -> items.ItemInstance [FK] (nullable)
  - subject_society -> societies.Society [FK] (nullable)
  - subject_organization -> societies.Organization [FK] (nullable)
  - subject_asset -> assets.NPCAsset [FK] (nullable)
  - beat -> stories.Beat [FK]
  - template -> stories.StakeTemplate [FK] (nullable)
**Pointed to by:**
  - legend_contributions <- societies.LegendContribution
  - routing_for_transitions <- stories.TransitionRequiredOutcome
  - resolutions <- stories.StakeResolution
  - outcomes <- stories.StakeOutcome

### StakeContractActivation
**Foreign Keys:**
  - beat -> stories.Beat [FK]
**Pointed to by:**
  - legend_contributions <- societies.LegendContribution
  - stake_outcomes <- stories.StakeOutcome

### StakeOutcome
**Foreign Keys:**
  - stake -> stories.Stake [FK]
  - activation -> stories.StakeContractActivation [FK] (nullable)
  - resolution -> stories.StakeResolution [FK] (nullable)
  - resolved_by -> gm.GMProfile [FK] (nullable)

### StakeResolution
**Foreign Keys:**
  - stake -> stories.Stake [FK]
  - consequence_pool -> actions.ConsequencePool [FK] (nullable)
**Pointed to by:**
  - npc_regard_events <- npc_services.NpcRegardEvent
  - reward_lines <- stories.StakeRewardLine

### StakeRewardLine
**Foreign Keys:**
  - resolution -> stories.StakeResolution [FK]
  - resonance -> magic.Resonance [FK] (nullable)

### StakeTemplate
**Foreign Keys:**
  - content_themes -> boundaries.ContentTheme [M2M]
**Pointed to by:**
  - stakes <- stories.Stake

### Story
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK] (nullable)
  - created_in_era -> stories.Era [FK] (nullable)
  - covenant -> covenants.Covenant [FK] (nullable)
  - primary_table -> gm.GMTable [FK] (nullable)
  - owners -> evennia.AccountDB [M2M]
  - active_gms -> gm.GMProfile [M2M]
  - required_trust_categories -> stories.TrustCategory [M2M]
**Pointed to by:**
  - battles <- battles.Battle
  - legend_events <- societies.LegendEvent
  - legend_entries <- societies.LegendEntry
  - ended_campaigns <- covenants.Covenant
  - armies <- military.Army
  - narrative_messages <- narrative.NarrativeMessage
  - gemits <- narrative.Gemit
  - muted_by <- narrative.UserStoryMute
  - trust_requirements <- stories.StoryTrustRequirement
  - participants <- stories.StoryParticipation
  - chapters <- stories.Chapter
  - feedback <- stories.StoryFeedback
  - referenced_by_beats <- stories.Beat
  - scenarios <- stories.StoryScenario
  - group_progress_records <- stories.GroupStoryProgress
  - global_progress <- stories.GlobalStoryProgress
  - progress_records <- stories.StoryProgress
  - notes <- stories.StoryNote
  - gm_offers <- stories.StoryGMOffer
  - crossover_invites_received <- stories.CrossoverInvite
  - bulletin_posts <- stories.TableBulletinPost
  - protected_subjects <- stories.StoryProtectedSubject
  - canon_reviews <- stories.CanonReview

### StoryFeedback
**Foreign Keys:**
  - story -> stories.Story [FK]
  - reviewer -> evennia.AccountDB [FK]
  - reviewed_player -> evennia.AccountDB [FK]
  - trust_categories -> stories.TrustCategory [M2M]
**Pointed to by:**
  - category_ratings <- stories.TrustCategoryFeedbackRating

### StoryGMOffer
**Foreign Keys:**
  - story -> stories.Story [FK]
  - offered_to -> gm.GMProfile [FK]
  - offered_by_account -> evennia.AccountDB [FK]

### StoryNote
**Foreign Keys:**
  - story -> stories.Story [FK]
  - author_account -> evennia.AccountDB [FK] (nullable)

### StoryParticipation
**Foreign Keys:**
  - story -> stories.Story [FK]
  - character -> character_sheets.CharacterSheet [FK]

### StoryProgress
**Foreign Keys:**
  - story -> stories.Story [FK]
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - current_episode -> stories.Episode [FK] (nullable)
  - resolved_by -> gm.GMProfile [FK] (nullable)

### StoryProtectedSubject
**Foreign Keys:**
  - subject_sheet -> character_sheets.CharacterSheet [FK] (nullable)
  - subject_item -> items.ItemInstance [FK] (nullable)
  - subject_society -> societies.Society [FK] (nullable)
  - subject_organization -> societies.Organization [FK] (nullable)
  - subject_asset -> assets.NPCAsset [FK] (nullable)
  - story -> stories.Story [FK]
  - beat -> stories.Beat [FK] (nullable)
**Pointed to by:**
  - clearances <- stories.CustodyClearance

### StoryScenario
**Foreign Keys:**
  - story -> stories.Story [FK]
  - template -> missions.MissionTemplate [OneToOne]

### StoryTrustRequirement
**Foreign Keys:**
  - story -> stories.Story [FK]
  - trust_category -> stories.TrustCategory [FK]
  - created_by -> evennia.AccountDB [FK] (nullable)

### TableBulletinPost
**Foreign Keys:**
  - table -> gm.GMTable [FK]
  - story -> stories.Story [FK] (nullable)
  - author_persona -> scenes.Persona [FK] (nullable)
**Pointed to by:**
  - replies <- stories.TableBulletinReply

### TableBulletinReply
**Foreign Keys:**
  - post -> stories.TableBulletinPost [FK]
  - author_persona -> scenes.Persona [FK] (nullable)

### Transition
**Foreign Keys:**
  - source_episode -> stories.Episode [FK]
  - target_episode -> stories.Episode [FK] (nullable)
**Pointed to by:**
  - required_outcomes <- stories.TransitionRequiredOutcome
  - resolutions_using <- stories.EpisodeResolution

### TransitionRequiredOutcome
**Foreign Keys:**
  - transition -> stories.Transition [FK]
  - beat -> stories.Beat [FK]
  - stake -> stories.Stake [FK] (nullable)

### TreasuredSignoff
**Foreign Keys:**
  - beat -> stories.Beat [FK]
  - player_data -> evennia_extensions.PlayerData [FK]
  - treasured_subject -> boundaries.TreasuredSubject [FK]

### TrustCategory
**Foreign Keys:**
  - created_by -> evennia.AccountDB [FK] (nullable)
**Pointed to by:**
  - gated_distinctions <- distinctions.Distinction
  - story_set <- stories.Story
  - storytrustrequirement_set <- stories.StoryTrustRequirement
  - playertrust_set <- stories.PlayerTrust
  - player_trust_levels <- stories.PlayerTrustLevel
  - storyfeedback_set <- stories.StoryFeedback
  - trustcategoryfeedbackrating_set <- stories.TrustCategoryFeedbackRating

### TrustCategoryFeedbackRating
**Foreign Keys:**
  - feedback -> stories.StoryFeedback [FK]
  - trust_category -> stories.TrustCategory [FK]


## world.tarot

### NamingRitualConfig
**Foreign Keys:**
  - codex_entry -> codex.CodexEntry [FK] (nullable)

### TarotCard
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
**Pointed to by:**
  - profiles <- character_sheets.Profile


## world.tasking

### ListenerHarvest
**Foreign Keys:**
  - post -> tasking.ListenerPost [FK]
  - secret -> secrets.Secret [FK] (nullable)
  - planted_clue -> clues.Clue [FK] (nullable)

### ListenerPost
**Foreign Keys:**
  - assignment -> npc_services.NPCAssignment [OneToOne]
  - handler -> scenes.Persona [FK]
  - check_type -> checks.CheckType [FK] (nullable)
  - flipped_controller -> scenes.Persona [FK] (nullable)
  - pending_plant -> clues.Clue [FK] (nullable)
**Pointed to by:**
  - harvests <- tasking.ListenerHarvest

### NpcTaskAptitude
**Foreign Keys:**
  - persona -> scenes.Persona [FK]

### OrgTask
**Foreign Keys:**
  - template -> tasking.TaskTemplate [FK]
  - org -> societies.Organization [FK]
  - issued_by -> scenes.Persona [FK]
  - target_room -> evennia_extensions.RoomProfile [FK] (nullable)
  - target_org -> societies.Organization [FK] (nullable)
  - target_domain -> societies.Domain [FK] (nullable)
  - target_persona -> scenes.Persona [FK] (nullable)
  - target_crisis -> societies.DomainCrisis [FK] (nullable)
  - target_band -> predators.PredatorBand [FK] (nullable)
**Pointed to by:**
  - fulfillments <- tasking.TaskFulfillment

### TaskFulfillment
**Foreign Keys:**
  - task -> tasking.OrgTask [FK]
  - npc_asset -> assets.NPCAsset [FK] (nullable)
  - mission_instance -> missions.MissionInstance [FK] (nullable)
  - handler -> scenes.Persona [FK]
  - handler_check_outcome -> traits.CheckOutcome [FK] (nullable)
  - resolved_outcome -> traits.CheckOutcome [FK] (nullable)

### TaskOutcomeRoute
**Foreign Keys:**
  - template -> tasking.TaskTemplate [FK]
  - outcome_tier -> traits.CheckOutcome [FK]
  - clue_pool -> assets.CluePool [FK] (nullable)

### TaskTemplate
**Foreign Keys:**
  - check_type -> checks.CheckType [FK]
  - mission_template -> missions.MissionTemplate [FK] (nullable)
  - consequence_pool -> actions.ConsequencePool [FK] (nullable)
**Pointed to by:**
  - outcome_routes <- tasking.TaskOutcomeRoute
  - tasks <- tasking.OrgTask

### Service Functions
- `accept_task(task: 'OrgTask', handler: 'Persona') -> 'TaskFulfillment' - A member picks up a PC-fulfillable task as a mission (#2820 phase 5).`
- `aptitude_band(persona, category: 'str') -> 'int' - The agent's band for a job family, minted lazily on first read.`
- `assign_agent(task: 'OrgTask', npc_asset: 'NPCAsset', handler: 'Persona') -> 'TaskFulfillment' - Dispatch an owned, active agent on an OPEN task.`
- `create_task(template: 'TaskTemplate', org: 'Organization', issued_by: 'Persona', *, target_room=None, target_org=None, target_domain=None, target_persona=None, target_crisis=None) -> 'OrgTask' - Create an OPEN task instance. Caller (view/action) gates leadership.`
- `resolve_due_tasks() -> 'int' - Game-clock sweep: resolve every ASSIGNED task whose deadline has passed.`
- `resolve_task(task: 'OrgTask') -> 'TaskFulfillment' - Resolve an ASSIGNED task now: agent check -> route payouts + risk pool.`
- `resolve_task_for_mission(instance, route=None) -> 'None' - Terminal-completion seam (#2820 phase 5) — mirrors the crisis seam.`
- `target_label(task: 'OrgTask') -> 'str'`


## world.tavern_games

### GamblingLossLedger
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - game_week -> game_clock.GameWeek [FK]

### GameSeat
**Foreign Keys:**
  - session -> tavern_games.GameSession [FK]
  - persona -> scenes.Persona [FK]

### GameSession
**Foreign Keys:**
  - place -> scenes.Place [FK]
  - game -> tavern_games.TavernGame [FK]
  - opened_by -> scenes.Persona [FK]
**Pointed to by:**
  - seats <- tavern_games.GameSeat

### TavernGamblingConfig

### TavernGame
**Pointed to by:**
  - sessions <- tavern_games.GameSession

### Service Functions
- `join_session(*, session: 'GameSession', persona: 'Persona') -> 'GameSeat' - Ante in and take a seat at an OPEN session.`
- `leave_session(*, session: 'GameSession', persona: 'Persona') -> 'None' - Leave the table: refund this seat's ante. Closes the session when it's empty.`
- `open_session(*, place: 'Place', game: 'TavernGame', persona: 'Persona', ante: 'int') -> 'GameSession' - Open a new table at ``place``: the opener seats and antes in immediately.`
- `roll(*, session: 'GameSession', persona: 'Persona') -> 'GameSeat' - Roll the dice for this hand. Auto-resolves once every seat has rolled.`



## world.tidings

### Service Functions
- `house_feed_for(organization, *, limit: 'int' = 30) -> 'list[PublicFeedItem]' - The house feed (#1884): what the household hears about its own people.`
- `hub_feed_for_room(room: 'ObjectDB | None', *, limit: 'int' = 30) -> 'list[PublicFeedItem]' - The civic-hub scope (#1450): the local slice of awareness at ``room``.`
- `public_feed_for(persona: 'Persona', *, limit: 'int' = 30) -> 'list[PublicFeedItem]' - Recent public events the persona's societies are aware of, newest first (viewer scope).`
- `public_feed_for_societies(society_ids: 'Iterable[int]', *, limit: 'int' = 30) -> 'list[PublicFeedItem]' - The core read: recent deeds + scandals known to ``society_ids``, newest first.`


## world.traits

### CharacterTraitChange
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - trait -> traits.Trait [FK]
  - granting_tenure -> roster.RosterTenure [FK] (nullable)

### CharacterTraitValue
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - trait -> traits.Trait [FK]

### CheckOutcome
**Pointed to by:**
  - cleanup_thresholds <- areas.CleanupTierThreshold
  - consequences <- checks.Consequence
  - treatment_attempts <- conditions.TreatmentAttempt
  - challenge_records <- mechanics.CharacterChallengeRecord
  - battle_outcome_mappings <- battles.BattleOutcomeMapping
  - city_defense_projects <- battles.CityDefenseDetails
  - city_defense_thresholds <- battles.CityDefenseTierThreshold
  - arxii_citydefenseintegritybonus <- battles.CityDefenseIntegrityBonus
  - war_funding_projects <- battles.WarFundingDetails
  - war_funding_thresholds <- battles.WarFundingTierThreshold
  - arxii_warfundingtierbonus <- battles.WarFundingTierBonus
  - resultchartoutcome_set <- traits.ResultChartOutcome
  - gang_turf_thresholds <- societies.GangTurfTierThreshold
  - arxii_gangturfreputationaward <- societies.GangTurfReputationAward
  - technique_warp_modifier <- magic.TechniqueOutcomeModifier
  - anima_ritual_performances <- magic.AnimaRitualPerformance
  - arxii_sanctumhomecominggainaward <- magic.SanctumHomecomingGainAward
  - arxii_sanctumpurgingretentionaward <- magic.SanctumPurgingRetentionAward
  - arxii_sanctumdissolutionrecoveryaward <- magic.SanctumDissolutionRecoveryAward
  - arxii_animaritualbudgetaward <- magic.AnimaRitualBudgetAward
  - arxii_trainingoutcomeaward <- magic.TrainingOutcomeAward
  - encounter_outcome_mappings <- combat.EncounterOutcomeMapping
  - project_outcomes <- projects.Project
  - project_contributions <- projects.Contribution
  - beat_completions <- stories.BeatCompletion

### CheckRank

### PointConversionRange

### ResultChart
**Pointed to by:**
  - outcomes <- traits.ResultChartOutcome

### ResultChartOutcome
**Foreign Keys:**
  - chart -> traits.ResultChart [FK]
  - outcome -> traits.CheckOutcome [FK]

### Trait
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
**Pointed to by:**
  - npc_preset_trait_lines <- roster.NPCPresetTraitLine
  - check_type_traits <- checks.CheckTypeTrait
  - modifier_targets <- mechanics.ModifierTarget
  - capability_derivations <- mechanics.TraitCapabilityDerivation
  - rank_descriptions <- traits.TraitRankDescription
  - character_values <- traits.CharacterTraitValue
  - character_changes <- traits.CharacterTraitChange
  - classes_requiring_trait <- classes.CharacterClass
  - maturation_spends <- progression.MaturationSpend
  - development_points <- progression.DevelopmentPoints
  - development_transactions <- progression.DevelopmentTransaction
  - weekly_skill_usage <- progression.WeeklySkillUsage
  - level_stat_point_spends <- progression.LevelStatPointSpend
  - xp_costs <- progression.TraitXPCost
  - rating_unlocks <- progression.TraitRatingUnlock
  - trait_requirements <- progression.TraitRequirement
  - anchored_threads <- magic.Thread
  - thread_weaving_unlocks <- magic.ThreadWeavingUnlock
  - language <- species.Language
  - skill <- skills.Skill

### TraitRankDescription
**Foreign Keys:**
  - trait -> traits.Trait [FK]

### Service Functions
- `ensure_stat_trait(name: 'str') -> 'Trait' - Ensure the named STAT Trait exists, creating it from STAT_TRAIT_DEFAULTS if not.`


## world.travel

### TravelHub
**Foreign Keys:**
  - room_profile -> evennia_extensions.RoomProfile [OneToOne]
**Pointed to by:**
  - outbound_routes <- travel.TravelRoute
  - inbound_routes <- travel.TravelRoute
  - voyages_from <- travel.Voyage
  - voyages_to <- travel.Voyage

### TravelMethod
**Foreign Keys:**
  - ship_type -> ships.ShipType [FK] (nullable)
**Pointed to by:**
  - voyages <- travel.Voyage

### TravelRoute
**Foreign Keys:**
  - origin_hub -> travel.TravelHub [FK]
  - destination_hub -> travel.TravelHub [FK]

### Voyage
**Foreign Keys:**
  - leader -> scenes.Persona [FK]
  - travel_method -> travel.TravelMethod [FK]
  - origin_hub -> travel.TravelHub [FK] (nullable)
  - destination_hub -> travel.TravelHub [FK] (nullable)
  - ship -> ships.ShipDetails [OneToOne] (nullable)
**Pointed to by:**
  - participants <- travel.VoyageParticipant
  - invites <- travel.VoyageInvite

### VoyageInvite
**Foreign Keys:**
  - voyage -> travel.Voyage [FK]
  - target_persona -> scenes.Persona [FK]
  - invited_by -> scenes.Persona [FK] (nullable)

### VoyageParticipant
**Foreign Keys:**
  - voyage -> travel.Voyage [FK]
  - persona -> scenes.Persona [FK]

### Service Functions
- `abandon_voyage(voyage: 'Voyage', caller) -> 'None' - End voyage at current hub. Participants stay where they are.`
- `advance_leg(voyage: 'Voyage', caller) -> 'None' - Pay AP for next leg, move all participants to next hub room.`
- `complete_voyage(voyage: 'Voyage', caller) -> 'None' - Pay all remaining AP, move group directly to destination hub.`
- `compute_ap_cost(ic_hours: 'float') -> 'int' - AP cost for a given IC travel time.`
- `compute_remaining_ap(voyage: 'Voyage', character_sheet: 'CharacterSheet', travel_method: 'TravelMethod', ship: 'ShipDetails | None' = None) -> 'int' - Total AP to fast-forward from current hub to destination for this character.`
- `compute_travel_time(route: 'TravelRoute', travel_method: 'TravelMethod', character_sheet: 'CharacterSheet', ship: 'ShipDetails | None' = None) -> 'float' - Compute IC hours for one leg for a specific character.`
- `depart_voyage(voyage: 'Voyage', caller) -> 'Voyage' - Transition a DRAFT voyage to IN_TRANSIT.`
- `find_overworld_route(origin_hub: 'TravelHub', destination_hub: 'TravelHub', travel_mode: 'str') -> 'list[TravelRoute] | None' - BFS over TravelRoute edges filtered by travel_mode.`
- `invite_to_voyage(voyage: 'Voyage', leader_persona, invitee_persona) -> 'VoyageInvite' - Create a PENDING invite for ``invitee_persona`` to join ``voyage``.`
- `respond_to_voyage_invite(invite: 'VoyageInvite', decision: 'VoyageInvite.Response') -> 'None' - Resolve a PENDING invite. Sets response + responded_at.`
- `start_voyage(leader, destination_hub: 'TravelHub', travel_method: 'TravelMethod', ship: 'ShipDetails | None' = None) -> 'Voyage' - Create a DRAFT Voyage, enroll leader as participant.`


## world.vitals

### CarriedBody
**Foreign Keys:**
  - carrier -> character_sheets.CharacterSheet [OneToOne]
  - carried -> character_sheets.CharacterSheet [OneToOne]

### CharacterVitals
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [OneToOne]
  - died_in_scene -> scenes.Scene [FK] (nullable)

### VitalsConsequenceConfig
**Foreign Keys:**
  - knockout_pool -> actions.ConsequencePool [FK] (nullable)
  - default_wound_pool -> actions.ConsequencePool [FK] (nullable)
  - default_death_pool -> actions.ConsequencePool [FK] (nullable)

### WoundDetails
**Foreign Keys:**
  - condition_instance -> conditions.ConditionInstance [OneToOne]

### Service Functions
- `advance_bleed_out(character_sheet: 'CharacterSheet | None') -> 'bool' - Advance staged bleed-out conditions toward death.`
- `advance_surrounded(character_sheet: 'CharacterSheet | None', *, battle: 'Battle') -> 'bool' - Advance staged Surrounded (battle acute-peril) conditions toward death (#1733).`
- `apply_clamped_chronic_damage(character_sheet: 'CharacterSheet', amount: 'int') -> 'int' - Reduce health by ``amount`` but never to/below the knockout floor, never increasing it.`
- `attempt_wake(character_sheet: 'CharacterSheet | None', *, in_combat_tick: 'bool' = False, destination_room: 'ObjectDB | None' = None) -> 'WakeResult' - Attempt to wake from Unconscious: one Endurance check per round.`
- `calculate_death_difficulty(*, health_pct: 'float') -> 'int' - Scale death check difficulty by depth of negative health.`
- `calculate_knockout_difficulty(*, health_pct: 'float') -> 'int' - Scale knockout check difficulty by how far below 20% health.`
- `calculate_wake_difficulty(*, health_pct: 'float', rounds_elapsed: 'int') -> 'int' - Difficulty of the per-round wake check.`
- `calculate_wound_difficulty(*, damage: 'int', max_health: 'int') -> 'int' - Scale wound check difficulty by how far damage exceeds 50% threshold.`
- `can_act(character_sheet: 'CharacterSheet | None') -> 'bool' - Coarse 'can engage at all' gate: not dead AND has awareness.`
- `collect_check_modifiers(character_sheet: 'CharacterSheet', check_type: 'CheckType', *, scene: 'Scene | None' = None, extra_contributions: list[world.checks.types.ModifierContribution] | None = None, skip_fashion: bool = False) -> world.checks.types.ModifierBreakdown - Aggregate all modifier contributions for a check into a ModifierBreakdown.`
- `conscious_bystander_present(room: 'ObjectDB | None', *, subject_id: 'int', exclude_ids: 'frozenset[int]' = frozenset()) -> 'bool' - True if anyone but ``subject_id`` present in ``room`` is conscious (can_act).`
- `covenant_role_health(character: 'object', level: 'int') -> 'int' - Level-scaled covenant-role 'armor': sum of level * bonus_per_level over engaged`
- `derive_base_max_health(character_sheet: 'CharacterSheet') -> 'int' - Derive base_max_health = class stage-rate sum + stamina term + covenant-role armor.`
- `derive_character_status(character_sheet: 'CharacterSheet | None') -> 'str' - Derive a coarse, read-only life-status string for the wire/API.`
- `frailty_floor_reached(character_sheet: 'CharacterSheet') -> 'bool' - True when age-bled max health has crossed the dying floor (#2756).`
- `get_dream_room() -> 'ObjectDB | None' - Return the liminal dream room (seeded by the survivability cluster).`
- `get_vitals_consequence_config() -> 'VitalsConsequenceConfig' - Return the VitalsConsequenceConfig singleton (pk=1), creating it lazily on first call.`
- `is_alive(character_sheet: 'CharacterSheet | None') -> 'bool' - Return True if the character is not dead.`
- `is_dead(character_sheet: 'CharacterSheet | None') -> 'bool' - Return True if the character's mortality marker is DEAD.`
- `is_retired(character_sheet: 'CharacterSheet | None') -> 'bool' - True when the dead character has been released (retire fired, #2287).`
- `mark_fed_to_death(victim_sheet: 'CharacterSheet') -> 'bool' - Kill an NPC drained past empty by feeding (#2853). Returns True on death.`
- `mend_wound(healer_sheet: 'CharacterSheet', target_sheet: 'CharacterSheet', wound_instance: 'ConditionInstance', amount: 'int') -> 'int' - Raise a wounded target's health, double-bounded (#2644 — the attrition invariant).`
- `perceives_dreamside(character_sheet: 'CharacterSheet | None') -> 'bool' - True when the character's perception is relocated to the dream side (#2287).`
- `perform_check_with_modifiers(character: 'ObjectDB', check_type: 'CheckType', target_difficulty: int = 0, extra_modifiers: int = 0, effort_level: str | None = None, fatigue_penalty: int = 0, specialization: 'Specialization | None' = None, *, situation_ctx: 'SituationContext | None' = None, level_override: int | None = None, scene: 'Scene | None' = None, extra_contributions: 'list[ModifierContribution] | None' = None, skip_fashion: bool = False, stat_override: str | int | None = None) -> world.checks.types.CheckResult - Run a check with all character modifiers gathered automatically.`
- `process_damage_consequences(character_sheet: 'CharacterSheet | None', damage_dealt: 'int', damage_type: 'DamageType | None', *, extra_modifiers: 'int' = 0, combat_interaction_factory: 'Callable[[], Interaction] | None' = None, source_character: 'ObjectDB | None' = None) -> 'DamageConsequenceResult' - Process survivability consequences after damage is applied.`
- `recompute_max_health(character_sheet: 'CharacterSheet', *, thread_addend: 'int' = 0) -> 'int' - Derive max_health from base_max_health plus a thread-derived addend.`
- `resolve_abandonment(character_sheet: 'CharacterSheet | None') -> 'bool' - Resolve an abandoned downed victim's fate through the abandonment pool (#1479 T8).`
- `resolve_vitals_consequence(character_sheet: 'CharacterSheet', check_type: 'CheckTypeHint', target_difficulty: 'int', pool: 'ConsequencePool', *, extra_modifiers: 'int' = 0, source_character: 'ObjectDB | None' = None) -> 'PendingResolution' - Resolve one survivability consequence through the consequence-pool pipeline.`
- `retire_character(character_sheet: 'CharacterSheet', *, forced_by: 'object | None' = None) -> 'None' - Release a dead character: the final lock of the ghost interlude (#2287).`
- `tick_round_for_targets(targets: 'Iterable[ObjectDB]', *, timing: "Literal['start', 'end']" = 'end') -> 'None' - Apply one round's worth of per-target effects for a set of targets.`
- `unconscious_instance(character_sheet: 'CharacterSheet | None') -> 'ConditionInstance | None' - Return the character's active Unconscious ConditionInstance, if any.`


## world.weather

### Climate
**Foreign Keys:**
  - codex_subject -> codex.CodexSubject [FK] (nullable)
**Pointed to by:**
  - areas <- areas.Area

### FeastDay
**Foreign Keys:**
  - weather_type -> weather.WeatherType [FK]

### RegionWeatherState
**Foreign Keys:**
  - area -> areas.Area [OneToOne]
  - weather_type -> weather.WeatherType [FK]

### WeatherEmit
**Foreign Keys:**
  - written_by -> contributors.ContentContributor [FK] (nullable)
  - reviewed_by -> contributors.ContentContributor [FK] (nullable)
  - weather_type -> weather.WeatherType [FK]

### WeatherTransition
**Foreign Keys:**
  - from_type -> weather.WeatherType [FK]
  - to_type -> weather.WeatherType [FK]

### WeatherType
**Foreign Keys:**
  - codex_subject -> codex.CodexSubject [FK] (nullable)
**Pointed to by:**
  - exposures <- weather.WeatherTypeExposure
  - transitions_out <- weather.WeatherTransition
  - transitions_in <- weather.WeatherTransition
  - shelters <- weather.WeatherTypeShelter
  - emits <- weather.WeatherEmit
  - active_in_regions <- weather.RegionWeatherState
  - feast_days <- weather.FeastDay
  - overriding_battles <- battles.Battle
  - overriding_battle_places <- battles.BattlePlace
  - battle_property_effects <- battles.WeatherTypePropertyEffect
  - battle_capability_challenges <- battles.WeatherTypeCapabilityChallenge
  - conjuring_techniques <- magic.Technique

### WeatherTypeExposure
**Foreign Keys:**
  - weather_type -> weather.WeatherType [FK]

### WeatherTypeShelter
**Foreign Keys:**
  - weather_type -> weather.WeatherType [FK]
  - damage_type -> conditions.DamageType [FK]

### Service Functions
- `apply_weather_exposure(state: 'RegionWeatherState') -> 'None' - Re-materialize a region's weather as decaying source-tagged cascade modifiers (#1522).`
- `clear_region_weather(area: 'Area') -> 'None' - Remove a region's weather state and its weather-sourced exposure modifiers (#1522).`
- `climate_exposure_base(climate: 'Climate | None', stat_key: 'StatKey', *, temperature_shift: 'int' = 0) -> 'int' - A climate's contribution to one exposure axis, before local modifiers/floor (#1522).`
- `current_conditions(room: 'DefaultObject') -> 'ConditionsSummary' - IC time + the weather holding at a room, for the ``time`` command and frontend (#1522).`
- `current_temperature_shift(*, real_now: 'datetime | None' = None) -> 'int' - The current global seasonal temperature shift from the IC clock (#1522).`
- `eligible_weather_types(area: 'Area | None') -> 'list[WeatherType]' - Automated, active weather types whose temperature band fits the region's climate (#1522).`
- `get_effective_climate(area: 'Area | None') -> 'Climate | None' - Walk up the area hierarchy to the nearest climate assignment (#1522).`
- `get_effective_weather(area: 'Area | None') -> 'RegionWeatherState | None' - Walk up the area hierarchy to the nearest current-weather state (#1522).`
- `get_ic_now(*, real_now: datetime.datetime | None = None) -> datetime.datetime | None - Return the current IC datetime, or None if no clock exists.`
- `get_ic_phase(*, real_now: datetime.datetime | None = None) -> world.game_clock.constants.TimePhase | None - Return the current time-of-day phase, or None if no clock exists.`
- `get_ic_season(*, real_now: datetime.datetime | None = None) -> world.game_clock.constants.Season | None - Return the current IC season, or None if no clock exists.`
- `get_moon_phase(*, real_now: datetime.datetime | None = None) -> world.game_clock.constants.MoonPhase | None - Return the current lunar phase, or None if no clock exists.`
- `month_temperature_shift(month: 'int') -> 'int' - The global temperature shift for an IC month (1–12); 0 if out of range.`
- `roll_region_weather(area: 'Area', *, weather_type: 'WeatherType | None' = None) -> 'RegionWeatherState | None' - Set (or roll) a region's current weather and re-apply its exposure modifiers (#1522).`
- `select_weather_emit(area: 'Area | None', *, season: 'Season | None' = None, phase: 'TimePhase | None' = None) -> 'WeatherEmit | None' - Pick a weighted-random atmospheric emit for a region's current weather (#1522).`
- `special_weather_for_today(*, real_now: 'datetime | None' = None) -> 'WeatherType | None' - The special weather forced by a feast day on the current IC date, if any (#1522).`


## world.worship

### ChosenFavorConfig

### DevotionStanding
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - being -> worship.WorshippedBeing [FK]

### DivineInterventionConfig

### Miracle
**Foreign Keys:**
  - being -> worship.WorshippedBeing [FK]
**Pointed to by:**
  - condition_applications <- worship.MiracleAppliedCondition
  - damage_profiles <- worship.MiracleDamageProfile
  - performances <- worship.MiraclePerformance

### MiracleAppliedCondition
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK]
  - miracle -> worship.Miracle [FK]

### MiracleDamageProfile
**Foreign Keys:**
  - damage_type -> conditions.DamageType [FK] (nullable)
  - miracle -> worship.Miracle [FK]

### MiraclePerformance
**Foreign Keys:**
  - miracle -> worship.Miracle [FK]
  - being -> worship.WorshippedBeing [FK]
  - target_character -> character_sheets.CharacterSheet [FK] (nullable)
  - scene -> scenes.Scene [FK] (nullable)

### WorshipDeclaration
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [OneToOne]
  - public_being -> worship.WorshippedBeing [FK] (nullable)
  - secret_being -> worship.WorshippedBeing [FK] (nullable)
  - secret -> secrets.Secret [FK] (nullable)

### WorshipGrant
**Foreign Keys:**
  - being -> worship.WorshippedBeing [FK]
  - granted_by -> character_sheets.CharacterSheet [FK] (nullable)

### WorshipTradition
**Foreign Keys:**
  - rites_specialization -> skills.Specialization [FK]
**Pointed to by:**
  - beings <- worship.WorshippedBeing

### WorshippedBeing
**Foreign Keys:**
  - tradition -> worship.WorshipTradition [FK]
  - avatar_sheet -> character_sheets.CharacterSheet [OneToOne] (nullable)
**Pointed to by:**
  - ceremonies <- ceremonies.Ceremony
  - audere_majora_faith_variants <- magic.AudereMajoraFaithVariant
  - grants <- worship.WorshipGrant
  - devotion_standings <- worship.DevotionStanding
  - public_worshippers <- worship.WorshipDeclaration
  - secret_worshippers <- worship.WorshipDeclaration
  - miracles <- worship.Miracle
  - miracle_performances <- worship.MiraclePerformance

### Service Functions
- `active_patronage_for(sheet: 'CharacterSheet') -> list[world.worship.models.DevotionStanding] - Return all active patronages for a character, ordered by favor descending.`
- `best_patronage_favor(sheet: 'CharacterSheet') -> int - Return the favor of the highest-favor active patronage, or 0.`
- `bump_devotion(character_sheet: 'CharacterSheet', being: world.worship.models.WorshippedBeing, amount: int) -> world.worship.models.DevotionStanding - Upsert the (sheet, being) standing and run the God's Favorite check.`
- `convert_public_worship(character_sheet: 'CharacterSheet', new_being: world.worship.models.WorshippedBeing, *, is_sincere: bool = True) -> world.worship.models.WorshipDeclaration - Repoint a character's PUBLIC worship declaration (#2361).`
- `establish_patronage(sheet: 'CharacterSheet', being: world.worship.models.WorshippedBeing, *, valence: world.worship.models.PatronageValence) -> world.worship.models.DevotionStanding - Get-or-create a DevotionStanding and mark it as a patronage.`
- `get_chosen_favor_config() -> world.worship.models.ChosenFavorConfig - Lazy-create the ChosenFavorConfig singleton (pk=1).`
- `get_divine_intervention_config() -> 'DivineInterventionConfig' - Lazy-create the singleton (pk=1) divine intervention config (#2360).`
- `gods_favorite_achievement_for(character_sheet: 'CharacterSheet') -> 'Achievement | None' - Resolve the gender-matched God's Favorite achievement row (Decision 6).`
- `grant_worship(being: world.worship.models.WorshippedBeing, amount: int, *, granted_by: 'CharacterSheet | None' = None, reason: str = '') -> world.worship.models.WorshipGrant - Add worship to a being's pool and record the audit ledger row.`
- `install_divine_intervention_trigger(character_sheet: 'CharacterSheet', being: world.worship.models.WorshippedBeing) -> None - Install the divine intervention Trigger on the character's ObjectDB.`
- `maybe_fire_divine_intervention(character, payload=None) -> None - Trigger handler: fire a divine miracle when a high-devotion PC is incapacitated.`
- `perform_divine_intervention(character_sheet: 'CharacterSheet', being: world.worship.models.WorshippedBeing, miracle: 'Miracle', *, scene=None) -> 'MiraclePerformance' - Commit seam for a divine intervention: spend pool, apply conditions, audit.`
- `release_patronage(standing: world.worship.models.DevotionStanding) -> None - Mark a patronage as released (dormant).`
- `remove_divine_intervention_trigger(character_sheet: 'CharacterSheet', being: world.worship.models.WorshippedBeing) -> None - Remove the divine intervention trigger when favor drops below threshold.`
- `spend_worship_pool(being: world.worship.models.WorshippedBeing, amount: int, *, reason: str = '') -> bool - Deduct ``amount`` from ``being.resonance_pool`` (the spend counterpart to ``grant_worship``).`

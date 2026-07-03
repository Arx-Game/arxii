# Arx II Model Introspection Report
# Generated for CLAUDE.md enrichment


## actions

### ConsequencePool
**Foreign Keys:**
  - parent -> actions.ConsequencePool [FK] (nullable)
**Pointed to by:**
  - children <- actions.ConsequencePool
  - entries <- actions.ConsequencePoolEntry
  - action_templates <- actions.ActionTemplate
  - action_template_gates <- actions.ActionTemplateGate
  - resonance_interactions <- magic.AffinityInteraction
  - mishap_tiers <- magic.MishapPoolTier
  - success_beats <- stories.Beat
  - failure_beats <- stories.Beat
  - expired_beats <- stories.Beat
  - wound_pool_damage_types <- conditions.DamageType
  - death_pool_damage_types <- conditions.DamageType
  - condition_stages <- conditions.ConditionStage
  - context_attachments <- mechanics.ContextConsequencePool
  - consequence_outcomes <- checks.ConsequenceOutcome
  - traps <- room_features.Trap

### ConsequencePoolEntry
**Foreign Keys:**
  - pool -> actions.ConsequencePool [FK]
  - consequence -> checks.Consequence [FK]

### ActionTemplate
**Foreign Keys:**
  - check_type -> checks.CheckType [FK]
  - consequence_pool -> actions.ConsequencePool [FK] (nullable)
  - consent_category -> consent.SocialConsentCategory [FK] (nullable)
**Pointed to by:**
  - gates <- actions.ActionTemplateGate
  - techniques <- magic.Technique
  - scene_action_requests <- scenes.SceneActionRequest
  - challenge_approaches <- mechanics.ChallengeApproach

### ActionTemplateGate
**Foreign Keys:**
  - action_template -> actions.ActionTemplate [FK]
  - check_type -> checks.CheckType [FK]
  - consequence_pool -> actions.ConsequencePool [FK] (nullable)

### ModifyKwargsConfig
**Foreign Keys:**
  - enhancement -> actions.ActionEnhancement [FK]

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

### RemoveConditionOnCheckConfig
**Foreign Keys:**
  - enhancement -> actions.ActionEnhancement [FK]
  - check_type -> checks.CheckType [FK]
  - resistance_check_type -> checks.CheckType [FK] (nullable)
  - condition -> conditions.ConditionTemplate [FK]

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

### Service Functions
- `advance_resolution(pending: 'PendingActionResolution', context: 'ResolutionContext', player_decision: 'str | None' = None) -> 'PendingActionResolution' — Resume a paused pipeline after player decision.`
- `apply_resolution(pending: 'PendingResolution', context: 'ResolutionContext') -> 'list[AppliedEffect]' — Apply all effects from the selected consequence.`
- `get_effective_consequences(pool: 'ConsequencePool') -> 'list[WeightedConsequence]' — Resolve pool inheritance into a flat list of weighted consequences.`
- `perform_check(character: 'ObjectDB', check_type: 'CheckType', target_difficulty: int = 0, extra_modifiers: int = 0, effort_level: str | None = None, fatigue_penalty: int = 0, specialization: 'Specialization | None' = None) -> world.checks.types.CheckResult — Main check resolution function.`
- `resolve_scene_action(*, character: 'ObjectDB', action_template: 'ActionTemplate | None', action_key: 'str', difficulty: 'int') -> 'SceneActionResult' — Resolve a scene-based action check using an ActionTemplate.`
- `select_consequence_from_result(character: 'ObjectDB', check_result: 'CheckResult', consequences: 'list[WeightedConsequence]') -> 'PendingResolution' — Select a consequence using an existing check result.`
- `start_action_resolution(character: 'ObjectDB', template: 'ActionTemplate', target_difficulty: 'int', context: 'ResolutionContext', extra_modifiers: 'int' = 0, *, check_type: 'CheckType | None' = None) -> 'PendingActionResolution' — Start an action resolution pipeline and run it to completion or pause.`


## behaviors

### BehaviorPackageDefinition
**Pointed to by:**
  - instances <- behaviors.BehaviorPackageInstance

### BehaviorPackageInstance
**Foreign Keys:**
  - definition -> behaviors.BehaviorPackageDefinition [FK]
  - obj -> objects.ObjectDB [FK]


## conditions

### ConditionCategory
**Pointed to by:**
  - conditions <- conditions.ConditionTemplate

### CapabilityType
**Foreign Keys:**
  - prerequisite -> mechanics.Prerequisite [FK] (nullable)
**Pointed to by:**
  - techniquecapabilitygrant_grants <- magic.TechniqueCapabilityGrant
  - technique_requirements <- magic.TechniqueCapabilityRequirement
  - techniquevariantcapabilitygrant_grants <- magic.TechniqueVariantCapabilityGrant
  - signaturemotifbonuscapabilitygrant_grants <- magic.SignatureMotifBonusCapabilityGrant
  - techniquedraftcapabilitygrant_grants <- magic.TechniqueDraftCapabilityGrant
  - thread_pull_effects <- magic.ThreadPullEffect
  - conditioncapabilityeffect_set <- conditions.ConditionCapabilityEffect
  - modifier_target <- mechanics.ModifierTarget
  - applications <- mechanics.Application
  - trait_derivations <- mechanics.TraitCapabilityDerivation
  - blocking_challenges <- mechanics.ChallengeTemplate
  - combat_pull_grants <- combat.CombatPullResolvedEffect
  - battle_units <- battles.BattleUnit
  - battle_unit_values <- battles.BattleUnitCapability
  - battle_weather_challenges <- battles.WeatherTypeCapabilityChallenge

### DamageType
**Foreign Keys:**
  - resonance -> magic.Resonance [OneToOne] (nullable)
  - wound_pool -> actions.ConsequencePool [FK] (nullable)
  - death_pool -> actions.ConsequencePool [FK] (nullable)
**Pointed to by:**
  - techniquedamageprofile_damage_profiles <- magic.TechniqueDamageProfile
  - alteration_weaknesses <- magic.MagicalAlterationTemplate
  - techniquevariantdamageprofile_damage_profiles <- magic.TechniqueVariantDamageProfile
  - signaturemotifbonusdamageprofile_damage_profiles <- magic.SignatureMotifBonusDamageProfile
  - techniquedraftdamageprofile_damage_profiles <- magic.TechniqueDraftDamageProfile
  - thread_pull_resistances <- magic.ThreadPullEffect
  - pending_sudden_harm_entries <- scenes.PendingSuddenHarm
  - conditionresistancemodifier_set <- conditions.ConditionResistanceModifier
  - conditiondamageovertime_set <- conditions.ConditionDamageOverTime
  - conditiondamageinteraction_set <- conditions.ConditionDamageInteraction
  - modifier_target <- mechanics.ModifierTarget
  - property_damage_modifiers <- mechanics.PropertyDamageModifier
  - consequence_effects <- checks.ConsequenceEffect
  - cascade_overrides <- locations.LocationValueOverride
  - cascade_modifiers <- locations.LocationValueModifier
  - weapon_templates <- items.ItemTemplate
  - threat_pool_entries <- combat.ThreatPoolEntry
  - combat_pull_resistances <- combat.CombatPullResolvedEffect

### ConditionTemplate
**Foreign Keys:**
  - category -> conditions.ConditionCategory [FK]
  - cure_check_type -> checks.CheckType [FK] (nullable)
  - resist_check_type -> checks.CheckType [FK] (nullable)
  - parent_condition -> conditions.ConditionTemplate [FK] (nullable)
  - corruption_resonance -> magic.Resonance [FK] (nullable)
  - properties -> mechanics.Property [M2M]
  - reactive_triggers -> flows.TriggerDefinition [M2M]
**Pointed to by:**
  - action_enhancements <- actions.ActionEnhancement
  - species_gift_drawbacks <- species.SpeciesGiftGrant
  - species_gift_benefits <- species.SpeciesGiftGrant
  - techniques_applying <- magic.Technique
  - techniqueappliedcondition_applied <- magic.TechniqueAppliedCondition
  - techniqueremovedcondition_applied <- magic.TechniqueRemovedCondition
  - magical_alteration <- magic.MagicalAlterationTemplate
  - resonance_alignment_tiers <- magic.ResonanceAlignmentBoonTier
  - techniquevariantappliedcondition_applied <- magic.TechniqueVariantAppliedCondition
  - signaturemotifbonusappliedcondition_applied <- magic.SignatureMotifBonusAppliedCondition
  - techniquedraftappliedcondition_applied <- magic.TechniqueDraftAppliedCondition
  - techniquedraftremovedcondition_applied <- magic.TechniqueDraftRemovedCondition
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
  - consequence_effects <- checks.ConsequenceEffect
  - stat_rules_for <- achievements.ConditionStatRule
  - threat_pool_entries <- combat.ThreatPoolEntry

### ConditionStage
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK]
  - resist_check_type -> checks.CheckType [FK] (nullable)
  - consequence_pool -> actions.ConsequencePool [FK] (nullable)
  - properties -> mechanics.Property [M2M]
  - on_entry_conditions -> conditions.ConditionTemplate [M2M]
**Pointed to by:**
  - stage_triggers <- flows.Trigger
  - auderethreshold_set <- magic.AudereThreshold
  - on_entry_assocs <- conditions.ConditionStageOnEntry
  - conditioncapabilityeffect_set <- conditions.ConditionCapabilityEffect
  - conditionmodifiereffect_set <- conditions.ConditionModifierEffect
  - conditioncheckmodifier_set <- conditions.ConditionCheckModifier
  - conditionresistancemodifier_set <- conditions.ConditionResistanceModifier
  - conditiondamageovertime_set <- conditions.ConditionDamageOverTime
  - conditioninstance_set <- conditions.ConditionInstance

### ConditionStageOnEntry
**Foreign Keys:**
  - stage -> conditions.ConditionStage [FK]
  - condition -> conditions.ConditionTemplate [FK]

### ConditionCapabilityEffect
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK] (nullable)
  - stage -> conditions.ConditionStage [FK] (nullable)
  - capability -> conditions.CapabilityType [FK]

### ConditionModifierEffect
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK] (nullable)
  - stage -> conditions.ConditionStage [FK] (nullable)
  - modifier_target -> mechanics.ModifierTarget [FK]

### ConditionCheckModifier
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK] (nullable)
  - stage -> conditions.ConditionStage [FK] (nullable)
  - check_type -> checks.CheckType [FK]

### ConditionResistanceModifier
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK] (nullable)
  - stage -> conditions.ConditionStage [FK] (nullable)
  - damage_type -> conditions.DamageType [FK] (nullable)

### ConditionDamageOverTime
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK] (nullable)
  - stage -> conditions.ConditionStage [FK] (nullable)
  - damage_type -> conditions.DamageType [FK]

### ConditionDamageInteraction
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK]
  - damage_type -> conditions.DamageType [FK]
  - applies_condition -> conditions.ConditionTemplate [FK] (nullable)

### ConditionConditionInteraction
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK]
  - other_condition -> conditions.ConditionTemplate [FK]
  - result_condition -> conditions.ConditionTemplate [FK] (nullable)

### ConditionInstance
**Foreign Keys:**
  - target -> objects.ObjectDB [FK]
  - condition -> conditions.ConditionTemplate [FK]
  - current_stage -> conditions.ConditionStage [FK] (nullable)
  - source_character -> objects.ObjectDB [FK] (nullable)
  - source_technique -> magic.Technique [FK] (nullable)
**Pointed to by:**
  - triggers <- flows.Trigger
  - alteration_events <- magic.MagicalAlterationEvent
  - treatment_action_requests <- scenes.SceneActionRequest
  - treatment_attempts_targeting_instance <- conditions.TreatmentAttempt
  - granted_properties <- mechanics.ObjectProperty

### TreatmentTemplate
**Foreign Keys:**
  - target_condition -> conditions.ConditionTemplate [FK]
  - check_type -> checks.CheckType [FK]
  - backlash_target_condition -> conditions.ConditionTemplate [FK] (nullable)
**Pointed to by:**
  - action_requests <- scenes.SceneActionRequest
  - attempts <- conditions.TreatmentAttempt

### TreatmentAttempt
**Foreign Keys:**
  - helper -> objects.ObjectDB [FK]
  - target -> objects.ObjectDB [FK]
  - scene -> scenes.Scene [FK]
  - treatment -> conditions.TreatmentTemplate [FK]
  - thread_used -> magic.Thread [FK] (nullable)
  - target_condition_instance -> conditions.ConditionInstance [FK] (nullable)
  - target_pending_alteration -> magic.PendingAlteration [FK] (nullable)
  - outcome -> traits.CheckOutcome [FK]

### DamageSuccessLevelMultiplier

### PenetrationOutcomeFactor


## evennia_extensions

### PlayerData
**Foreign Keys:**
  - account -> accounts.AccountDB [OneToOne]
  - profile_picture -> evennia_extensions.PlayerMedia [FK] (nullable)
**Pointed to by:**
  - applications <- roster.RosterApplication
  - reviewed_applications <- roster.RosterApplication
  - tenures <- roster.RosterTenure
  - approved_tenures <- roster.RosterTenure
  - blocks_made <- scenes.Block
  - blocks_received <- scenes.Block
  - mutes_made <- scenes.Mute
  - artist_profile <- evennia_extensions.Artist
  - media <- evennia_extensions.PlayerMedia
  - allow_list <- evennia_extensions.PlayerAllowList
  - allowed_by <- evennia_extensions.PlayerAllowList

### Artist
**Foreign Keys:**
  - player_data -> evennia_extensions.PlayerData [OneToOne]
**Pointed to by:**
  - created_media <- evennia_extensions.PlayerMedia

### PlayerMedia
**Foreign Keys:**
  - player_data -> evennia_extensions.PlayerData [FK]
  - created_by -> evennia_extensions.Artist [FK] (nullable)
**Pointed to by:**
  - tenure_links <- roster.TenureMedia
  - persona_thumbnails <- scenes.Persona
  - item_templates <- items.ItemTemplate
  - item_instances <- items.ItemInstance
  - combat_opponent_portraits <- combat.CombatOpponent
  - profile_for_players <- evennia_extensions.PlayerData
  - thumbnailed_objects <- evennia_extensions.ObjectDisplayData

### ObjectDisplayData
**Foreign Keys:**
  - object -> objects.ObjectDB [OneToOne]
  - thumbnail -> evennia_extensions.PlayerMedia [FK] (nullable)

### PlayerAllowList
**Foreign Keys:**
  - owner -> evennia_extensions.PlayerData [FK]
  - allowed_player -> evennia_extensions.PlayerData [FK]

### RoomSizeTier
**Pointed to by:**
  - rooms <- evennia_extensions.RoomProfile

### RoomProfile
**Foreign Keys:**
  - objectdb -> objects.ObjectDB [OneToOne]
  - area -> areas.Area [FK] (nullable)
  - size -> evennia_extensions.RoomSizeTier [FK] (nullable)
  - default_blueprint -> areas.PositionBlueprint [FK] (nullable)
**Pointed to by:**
  - residents <- character_sheets.CharacterSheet
  - durance_training_sites <- progression.DuranceTrainingSite
  - resonance_grants <- magic.ResonanceGrant
  - fame_reaction_lines <- societies.FameReactionLine
  - fame_reaction_cooldowns <- societies.FameReactionCooldown
  - hidden_clues <- clues.RoomClue
  - clue_triggers <- clues.ClueTrigger
  - stat_overrides <- locations.LocationValueOverride
  - stat_modifiers <- locations.LocationValueModifier
  - ownership_records <- locations.LocationOwnership
  - tenancy_records <- locations.LocationTenancy
  - placed_items <- items.RoomItem
  - events <- events.Event
  - functionaries <- npc_services.Functionary
  - entry_for_buildings <- buildings.Building
  - design_details <- buildings.InteriorDesignDetails
  - polish_by_category <- buildings.RoomPolish
  - decorations <- buildings.RoomDecoration
  - feature_instance <- room_features.RoomFeatureInstance
  - feature_progression_projects <- room_features.RoomFeatureProgressionDetails
  - traps <- room_features.Trap


## flows

### FlowDefinition
**Pointed to by:**
  - steps <- flows.FlowStepDefinition
  - triggerdefinition_set <- flows.TriggerDefinition
  - rituals <- magic.Ritual
  - consequence_effects <- checks.ConsequenceEffect

### FlowStepDefinition
**Foreign Keys:**
  - flow -> flows.FlowDefinition [FK]
  - parent -> flows.FlowStepDefinition [FK] (nullable)
**Pointed to by:**
  - children <- flows.FlowStepDefinition

### TriggerDefinition
**Foreign Keys:**
  - flow_definition -> flows.FlowDefinition [FK]
**Pointed to by:**
  - trigger_set <- flows.Trigger
  - installing_templates <- conditions.ConditionTemplate

### Trigger
**Foreign Keys:**
  - trigger_definition -> flows.TriggerDefinition [FK]
  - obj -> objects.ObjectDB [FK]
  - source_condition -> conditions.ConditionInstance [FK] (nullable)
  - source_stage -> conditions.ConditionStage [FK] (nullable)
**Pointed to by:**
  - data <- flows.TriggerData

### TriggerData
**Foreign Keys:**
  - trigger -> flows.Trigger [FK]


## typeclasses

### Attribute
**Pointed to by:**
  - accountdb_set <- accounts.AccountDB
  - objectdb_set <- objects.ObjectDB
  - channeldb_set <- comms.ChannelDB
  - scriptdb_set <- scripts.ScriptDB

### Tag
**Pointed to by:**
  - accountdb_set <- accounts.AccountDB
  - objectdb_set <- objects.ObjectDB
  - msg_set <- comms.Msg
  - channeldb_set <- comms.ChannelDB
  - helpentry_set <- help.HelpEntry
  - scriptdb_set <- scripts.ScriptDB


## world.areas

### Area
**Foreign Keys:**
  - parent -> areas.Area [FK] (nullable)
  - realm -> realms.Realm [FK] (nullable)
  - climate -> weather.Climate [FK] (nullable)
  - dominant_society -> societies.Society [FK] (nullable)
  - allowed_building_kinds -> buildings.BuildingKind [M2M]
**Pointed to by:**
  - income_streams <- currency.OrgIncomeStream
  - gossip_heat <- secrets.SecretGossip
  - children <- areas.Area
  - laws <- justice.AreaLaw
  - heat_rows <- justice.PersonaHeat
  - stat_overrides <- locations.LocationValueOverride
  - stat_modifiers <- locations.LocationValueModifier
  - ownership_records <- locations.LocationOwnership
  - tenancy_records <- locations.LocationTenancy
  - weather_state <- weather.RegionWeatherState
  - battles <- battles.Battle
  - default_permits_offered <- npc_services.PermitOfferDetails
  - building_profile <- buildings.Building
  - building_permits_valid_in <- buildings.BuildingPermitDetails
  - construction_projects <- buildings.BuildingConstructionDetails
  - rooms <- evennia_extensions.RoomProfile

### AreaClosure
**Foreign Keys:**
  - ancestor -> areas.Area [FK]
  - descendant -> areas.Area [FK]

### Position
**Foreign Keys:**
  - room -> objects.ObjectDB [FK]
  - elevation_anchor -> areas.Position [FK] (nullable)
**Pointed to by:**
  - elevated_over <- areas.Position
  - edges_as_a <- areas.PositionEdge
  - edges_as_b <- areas.PositionEdge
  - occupants <- areas.ObjectPosition
  - traps <- room_features.Trap

### PositionEdge
**Foreign Keys:**
  - position_a -> areas.Position [FK]
  - position_b -> areas.Position [FK]
  - gating_challenge -> mechanics.ChallengeInstance [FK] (nullable)

### PositionBlueprint
**Pointed to by:**
  - positions <- areas.BlueprintPosition
  - edges <- areas.BlueprintEdge
  - rooms_defaulting <- evennia_extensions.RoomProfile

### BlueprintPosition
**Foreign Keys:**
  - blueprint -> areas.PositionBlueprint [FK]
**Pointed to by:**
  - edges_as_a <- areas.BlueprintEdge
  - edges_as_b <- areas.BlueprintEdge

### BlueprintEdge
**Foreign Keys:**
  - blueprint -> areas.PositionBlueprint [FK]
  - position_a -> areas.BlueprintPosition [FK]
  - position_b -> areas.BlueprintPosition [FK]
  - gating_challenge_template -> mechanics.ChallengeTemplate [FK] (nullable)

### ObjectPosition
**Foreign Keys:**
  - objectdb -> objects.ObjectDB [OneToOne]
  - position -> areas.Position [FK]

### Service Functions
- `colored_area_path(room: 'ObjectDB') -> 'str' — Render a room's full area-hierarchy path with per-area colours (#1463).`
- `get_ancestor_at_level(area: 'Area', target_level: 'AreaLevel') -> 'Area | None' — Walk the ancestry to find the ancestor at the given AreaLevel.`
- `get_ancestry(area: 'Area') -> 'list[Area]' — Return the full ancestor chain from root down to this area.`
- `get_descendant_areas(area: 'Area') -> 'list[Area]' — Return all areas in the subtree below this area.`
- `get_effective_realm(area: 'Area') -> 'Realm | None' — Walk up the hierarchy to find the nearest realm assignment.`
- `get_room_profile(room_obj: 'ObjectDB') -> 'RoomProfile' — Get or create the RoomProfile for a room ObjectDB instance.`
- `get_rooms_in_area(area: 'Area') -> 'list[RoomProfile]' — Return all RoomProfiles in this area and everything beneath it.`
- `reparent_area(area: 'Area', new_parent: 'Area | None') -> 'None' — Move an area under a new parent.`
- `societies_for_area(area: 'Area | None') -> 'list[Society]' — Nearest-first ancestor walk: dominant society wins, else realm societies.`
- `societies_for_scene(scene: 'Scene') -> 'list[Society]' — Resolve which societies are relevant at a scene's location (#1464 walk fix).`
- `where_listing(viewer_account: 'object | None' = None) -> 'list[WhereEntry]' — Characters currently in PUBLIC rooms, with their coloured location paths (#1463).`


## world.battles

### Battle
**Foreign Keys:**
  - scene -> scenes.Scene [OneToOne]
  - campaign_story -> stories.Story [FK] (nullable)
  - region -> areas.Area [FK] (nullable)
  - weather_override -> weather.WeatherType [FK] (nullable)
**Pointed to by:**
  - sides <- battles.BattleSide
  - places <- battles.BattlePlace
  - units <- battles.BattleUnit
  - rounds <- battles.BattleRound
  - participants <- battles.BattleParticipant

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

### BattlePlace
**Foreign Keys:**
  - battle -> battles.Battle [FK]
  - combat_encounter -> combat.CombatEncounter [FK] (nullable)
  - controlled_by -> battles.BattleSide [FK] (nullable)
  - weather_override -> weather.WeatherType [FK] (nullable)
**Pointed to by:**
  - fortifications <- battles.Fortification
  - units <- battles.BattleUnit
  - participants <- battles.BattleParticipant
  - scoped_declarations <- battles.BattleActionDeclaration

### Fortification
**Foreign Keys:**
  - place -> battles.BattlePlace [FK]
  - defending_side -> battles.BattleSide [FK]
  - building -> buildings.Building [FK] (nullable)
**Pointed to by:**
  - declarations <- battles.BattleActionDeclaration

### BattleUnit
**Foreign Keys:**
  - battle -> battles.Battle [FK]
  - side -> battles.BattleSide [FK]
  - place -> battles.BattlePlace [FK] (nullable)
  - commander -> character_sheets.CharacterSheet [FK] (nullable)
  - summoned_by -> character_sheets.CharacterSheet [FK] (nullable)
  - properties -> mechanics.Property [M2M]
  - capabilities -> conditions.CapabilityType [M2M]
**Pointed to by:**
  - capability_values <- battles.BattleUnitCapability
  - declarations <- battles.BattleActionDeclaration

### BattleUnitCapability
**Foreign Keys:**
  - unit -> battles.BattleUnit [FK]
  - capability -> conditions.CapabilityType [FK]

### BattleRound
**Foreign Keys:**
  - battle -> battles.Battle [FK]
**Pointed to by:**
  - declarations <- battles.BattleActionDeclaration

### BattleParticipant
**Foreign Keys:**
  - battle -> battles.Battle [FK]
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - side -> battles.BattleSide [FK]
  - place -> battles.BattlePlace [FK] (nullable)
**Pointed to by:**
  - declarations <- battles.BattleActionDeclaration
  - support_declarations <- battles.BattleActionDeclaration

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

### TechniquePropertyAffinity
**Foreign Keys:**
  - technique -> magic.Technique [FK]
  - property -> mechanics.Property [FK]

### TerrainPropertyEffect
**Foreign Keys:**
  - property -> mechanics.Property [FK]

### WeatherTypePropertyEffect
**Foreign Keys:**
  - weather_type -> weather.WeatherType [FK]
  - property -> mechanics.Property [FK]

### WeatherTypeCapabilityChallenge
**Foreign Keys:**
  - weather_type -> weather.WeatherType [FK]
  - capability -> conditions.CapabilityType [FK]

### BattleOutcomeMapping
**Foreign Keys:**
  - check_outcome -> traits.CheckOutcome [FK] (nullable)

### Service Functions
- `activate_stakes_for_battle(battle: 'Battle') -> 'None' — Lock any staked beats' contracts for this battle's enlisted party.`
- `add_place(*, battle: 'Battle', name: 'str', terrain_type: 'str' = TerrainType.OPEN, movement_cost: 'int' = 1) -> 'BattlePlace' — Add a named front/zone to a battle.`
- `add_side(*, battle: 'Battle', role: 'str', victory_threshold: 'int' = 100, covenant: 'Covenant | None' = None) -> 'BattleSide' — Add a side (attacker or defender) to a battle.`
- `add_unit(*, battle: 'Battle', side: 'BattleSide', name: 'str', descriptor: 'str' = '', quality: 'str' = UnitQuality.TRAINED, commander: 'CharacterSheet | None' = None, summoned_by: 'CharacterSheet | None' = None, strength: 'int' = 100, place: 'BattlePlace | None' = None, properties: 'Iterable[Property]' = (), capability_values: 'Iterable[tuple[CapabilityType, int]]' = (), individual_count: 'int | None' = None) -> 'BattleUnit' — Add an abstract typed unit to a battle side.`
- `assign_unit_commander(*, unit: 'BattleUnit', commander: 'CharacterSheet | None') -> 'BattleUnit' — Assign (or clear, with ``commander=None``) a unit's commander (#1711).`
- `begin_battle_round(*, battle: 'Battle') -> 'BattleRound' — Close any open round and open a new DECLARING round.`
- `check_victory(*, battle: 'Battle') -> 'BattleOutcome | None' — Check whether any side has reached its victory threshold.`
- `conclude_battle(*, battle: 'Battle', outcome: 'str') -> 'Battle' — Set the battle's outcome, end the backing scene, and resolve any linked`
- `create_battle(*, name: 'str', campaign_story: 'Story | None' = None, round_limit: 'int' = 10) -> 'Battle' — Create a new Battle (and its backing Scene).`
- `create_fortification(*, place: 'BattlePlace', defending_side: 'BattleSide', kind: 'str' = FortificationKind.WALL, building: 'Building | None' = None) -> 'Fortification' — Create a Fortification at *place*, snapshotting its integrity ceiling (#1713).`
- `declare_battle_action(*, participant: 'BattleParticipant', action_kind: 'str', technique: 'Technique', target_unit: 'BattleUnit | None' = None, target_ally: 'BattleParticipant | None' = None, scope: 'str' = BattleActionScope.UNIT, target_place: 'BattlePlace | None' = None, target_side: 'BattleSide | None' = None, target_fortification: 'Fortification | None' = None) -> 'BattleActionDeclaration' — Record or update the participant's action declaration for the current round.`
- `enlist_participant(*, battle: 'Battle', character_sheet: 'CharacterSheet', side: 'BattleSide', place: 'BattlePlace | None' = None) -> 'BattleParticipant' — Enlist a player character in a battle on one side.`
- `maybe_conclude_on_timer(*, battle: 'Battle') -> 'BattleOutcome | None' — Conclude the battle when the round limit is exhausted.`
- `open_champion_duel(*, battle_place: 'BattlePlace', challenger_participant: 'BattleParticipant', opponent_kwargs: 'dict', tier: 'str' = OpponentTier.BOSS) -> 'CombatEncounter' — Bind *battle_place* to a new lethal PC-vs-boss duel (#1710).`
- `open_siege_engine_encounter(*, battle_place: 'BattlePlace', participant: 'BattleParticipant', opponent_kwargs: 'dict', tier: 'str' = OpponentTier.ELITE) -> 'CombatEncounter' — Bind *battle_place* to a discrete siege-engine skirmish (#1713).`
- `resolve_battle_beats(battle: 'Battle') -> 'None' — Resolve every UNSATISFIED OUTCOME_TIER beat linked to a concluded battle.`
- `set_battle_side_posture(*, side: 'BattleSide', posture: 'str') -> 'BattleSide' — Set a battle side's tactical posture (#1711).`


## world.buildings

### BuildingKind
**Pointed to by:**
  - allowed_in_wards <- areas.Area
  - offered_by <- npc_services.PermitOfferDetails
  - buildings <- buildings.Building
  - permits <- buildings.BuildingPermitDetails
  - installable_features <- room_features.RoomFeatureKind

### BuildingSizeTier

### MaterialLoreEffect
**Foreign Keys:**
  - template -> items.ItemTemplate [FK]

### Building
**Foreign Keys:**
  - area -> areas.Area [OneToOne]
  - owner_persona -> scenes.Persona [FK] (nullable)
  - kind -> buildings.BuildingKind [FK]
  - architectural_style -> buildings.ArchitecturalStyle [FK] (nullable)
  - entry_room -> evennia_extensions.RoomProfile [FK] (nullable)
  - constructed_by_persona -> scenes.Persona [FK] (nullable)
  - source_project -> projects.Project [OneToOne] (nullable)
**Pointed to by:**
  - battle_fortifications <- battles.Fortification
  - materials_used <- buildings.BuildingMaterial
  - extension_details <- buildings.BuildingExtensionDetails
  - fortification_upgrade_details <- buildings.FortificationUpgradeDetails
  - design_details <- buildings.InteriorDesignDetails
  - polish_by_category <- buildings.BuildingPolish
  - project_instances <- buildings.BuildingProjectInstance

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

### BuildingExtensionDetails
**Foreign Keys:**
  - project -> projects.Project [OneToOne]
  - building -> buildings.Building [FK]

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

### BuildingConstructionDetails
**Foreign Keys:**
  - project -> projects.Project [OneToOne]
  - permit_details -> buildings.BuildingPermitDetails [FK]
  - ward -> areas.Area [FK]
  - constructed_by_persona -> scenes.Persona [FK] (nullable)

### PolishCategory
**Pointed to by:**
  - item_templates <- items.ItemTemplate
  - tier_thresholds <- buildings.TierThreshold
  - building_polish_rows <- buildings.BuildingPolish
  - room_polish_rows <- buildings.RoomPolish
  - polish_increment_rows <- buildings.ProjectTemplatePolishIncrement
  - instance_polish_rows <- buildings.BuildingProjectInstancePolish

### TierThreshold
**Foreign Keys:**
  - category -> buildings.PolishCategory [FK]
**Pointed to by:**
  - gated_project_templates <- buildings.ProjectTemplate

### BuildingPolish
**Foreign Keys:**
  - building -> buildings.Building [FK]
  - category -> buildings.PolishCategory [FK]

### RoomPolish
**Foreign Keys:**
  - room -> evennia_extensions.RoomProfile [FK]
  - category -> buildings.PolishCategory [FK]

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

### ArchitecturalStyle
**Foreign Keys:**
  - codex_subject -> codex.CodexSubject [FK] (nullable)
**Pointed to by:**
  - buildings <- buildings.Building
  - affinities <- buildings.StyleAffinity

### StyleAffinity
**Foreign Keys:**
  - style -> buildings.ArchitecturalStyle [FK]

### DecorationKind
**Pointed to by:**
  - affinities <- buildings.DecorationAffinity
  - placements <- buildings.RoomDecoration

### DecorationAffinity
**Foreign Keys:**
  - kind -> buildings.DecorationKind [FK]

### RoomDecoration
**Foreign Keys:**
  - room_profile -> evennia_extensions.RoomProfile [FK]
  - kind -> buildings.DecorationKind [FK]

### Service Functions
- `activate_permit(permit_details: 'BuildingPermitDetails', site_room, acting_persona: 'Persona', target_size: 'int', target_grandeur: 'int') -> 'Project' — Consume a permit + spawn a BUILDING_CONSTRUCTION project.`
- `can_build_style(persona: 'Persona', style: 'ArchitecturalStyle') -> 'bool' — Whether this persona may build in this style (#1469).`
- `complete_building_construction(project: 'Project', outcome_tier: 'object | None' = None) -> 'Building' — Spawn a Building from a completed BUILDING_CONSTRUCTION project.`
- `contribution_value_for_construction(contribution: 'Contribution') -> 'int' — How much a single contribution is worth toward a BUILDING_CONSTRUCTION project.`
- `issue_permit(offer: 'NPCServiceOffer', persona: 'Persona') -> 'EffectResult' — Real PERMIT effect handler — creates the BuildingPermit ItemInstance + details.`
- `place_decoration(room_profile, kind: 'DecorationKind') -> 'RoomDecoration' — Place a decoration in a room and materialize its comfort modifiers (#1514).`
- `remove_decoration(decoration: 'RoomDecoration') -> 'None' — Remove a placed decoration and delete its comfort modifiers (#1514).`
- `set_building_style(building: 'Building', style: 'ArchitecturalStyle | None') -> 'Building' — Assign (or clear) a building's architectural style and re-sync its climate modifiers.`
- `sync_building_style_modifiers(building: 'Building') -> 'None' — Re-materialize a building's architectural-style affinities as cascade modifiers (#1514).`
- `validate_permit_site(permit_details: 'BuildingPermitDetails', site_room, acting_persona: 'Persona', target_size: 'int') -> 'ValidationResult' — Validate a permit can be used at this site for this size.`


## world.captivity

### Captivity
**Foreign Keys:**
  - captive -> character_sheets.CharacterSheet [FK]
  - cell -> instances.InstancedRoom [FK] (nullable)
  - captor_organization -> societies.Organization [FK] (nullable)
  - ransom_project -> projects.Project [FK] (nullable)
  - rescue_template -> missions.MissionTemplate [FK] (nullable)
**Pointed to by:**
  - rescue_clues <- clues.Clue

### CaptivityConfig
**Foreign Keys:**
  - captive_template -> missions.MissionTemplate [FK] (nullable)
  - rescue_template -> missions.MissionTemplate [FK] (nullable)

### Service Functions
- `capture_character(*, captive: 'CharacterSheet', captor_organization: 'Organization | None' = None, return_location: 'ObjectDB | None' = None, offscreen_loss_allowed: 'bool' = False, cell: 'InstancedRoom | None' = None, group_key: 'str | None' = None, cell_name: 'str | None' = None, cell_description: 'str | None' = None) -> 'Captivity' — Take one character into a cell and record the captivity.`
- `capture_party(*, captives: 'Iterable[CharacterSheet]', captor_organization: 'Organization | None' = None, return_location: 'ObjectDB | None' = None, offscreen_loss_allowed: 'bool' = False, cell_name: 'str | None' = None, cell_description: 'str | None' = None) -> 'list[Captivity]' — Capture several characters into one shared cell (the default).`
- `complete_instanced_room(room: evennia.objects.models.ObjectDB) -> None — Mark room completed, relocate occupants, delete if no history.`
- `escape_captivity(captive: 'CharacterSheet') -> 'bool' — Free a captive by their own hand (#931 Phase 4) — the escape loop's verb.`
- `rescue_captive(captive: 'CharacterSheet') -> 'bool' — Free a captive via rescue (#931 Phase 4) — a rescue run's terminal verb.`
- `resolve_captivity(captivity: 'Captivity', *, status: 'str') -> 'None' — End a captivity and free the captive.`
- `resolve_capture_setup(*, captive_template: 'MissionTemplate | None' = None, rescue_template: 'MissionTemplate | None' = None, cell_name: 'str' = '', cell_description: 'str' = '', clue_name: 'str' = '', clue_description: 'str' = '', clue_detect_difficulty: 'int | None' = None) -> 'CaptureSetup' — Resolve one capture's loops + cell flavor: per-capture override, else default.`
- `spawn_instanced_room(name: str, description: str, owner: world.character_sheets.models.CharacterSheet, return_location: evennia.objects.models.ObjectDB | None, source_key: str = '') -> evennia.objects.models.ObjectDB — Create a temporary instanced room and its lifecycle record.`


## world.character_creation

### CGPointBudget

### StartingArea
**Foreign Keys:**
  - realm -> realms.Realm [FK] (nullable)
  - default_starting_room -> objects.ObjectDB [FK] (nullable)
**Pointed to by:**
  - beginnings <- character_creation.Beginnings
  - drafts <- character_creation.CharacterDraft

### Beginnings
**Foreign Keys:**
  - starting_area -> character_creation.StartingArea [FK]
  - heritage -> character_sheets.Heritage [FK] (nullable)
  - starting_room_override -> objects.ObjectDB [FK] (nullable)
  - allowed_species -> species.Species [M2M]
  - starting_languages -> species.Language [M2M]
  - societies -> societies.Society [M2M]
  - traditions -> magic.Tradition [M2M]
**Pointed to by:**
  - beginning_traditions <- character_creation.BeginningTradition
  - drafts <- character_creation.CharacterDraft
  - ritual_grants <- magic.BeginningsRitualGrant
  - codex_grants <- codex.BeginningsCodexGrant

### BeginningTradition
**Foreign Keys:**
  - beginning -> character_creation.Beginnings [FK]
  - tradition -> magic.Tradition [FK]
  - required_distinction -> distinctions.Distinction [FK] (nullable)

### CharacterDraft
**Foreign Keys:**
  - account -> accounts.AccountDB [FK]
  - selected_area -> character_creation.StartingArea [FK] (nullable)
  - selected_beginnings -> character_creation.Beginnings [FK] (nullable)
  - selected_species -> species.Species [FK] (nullable)
  - selected_gender -> character_sheets.Gender [FK] (nullable)
  - family -> roster.Family [FK] (nullable)
  - family_member -> roster.FamilyMember [FK] (nullable)
  - selected_path -> classes.Path [FK] (nullable)
  - selected_tradition -> magic.Tradition [FK] (nullable)
  - height_band -> forms.HeightBand [FK] (nullable)
  - build -> forms.Build [FK] (nullable)
  - target_table -> gm.GMTable [FK] (nullable)
**Pointed to by:**
  - application <- character_creation.DraftApplication

### DraftApplication
**Foreign Keys:**
  - draft -> character_creation.CharacterDraft [OneToOne] (nullable)
  - player_account -> accounts.AccountDB [FK] (nullable)
  - reviewer -> accounts.AccountDB [FK] (nullable)
**Pointed to by:**
  - comments <- character_creation.DraftApplicationComment

### DraftApplicationComment
**Foreign Keys:**
  - application -> character_creation.DraftApplication [FK]
  - author -> accounts.AccountDB [FK] (nullable)

### CGExplanation

### Service Functions
- `add_application_comment(application: 'DraftApplication', *, author: 'AbstractBaseUser | AnonymousUser', text: 'str') -> 'DraftApplicationComment' — Add a message comment to an application.`
- `approve_application(application: 'DraftApplication', *, reviewer: 'AbstractBaseUser | AnonymousUser', comment: 'str' = '') -> 'None' — Approve an application and finalize the character.`
- `calculate_weight(height_inches: 'int', build: 'Build') -> 'int' — Calculate weight in pounds from height and build.`
- `can_create_character(account: 'AbstractBaseUser | AnonymousUser') -> 'tuple[bool, str]' — Check if an account can create a new character.`
- `claim_application(application: 'DraftApplication', *, reviewer: 'AbstractBaseUser | AnonymousUser') -> 'None' — Claim a submitted application for staff review.`
- `create_character_with_sheet(*, character_key: 'str', primary_persona_name: 'str', typeclass: 'str' = 'typeclasses.characters.Character', home: 'ObjectDB | None' = None, **sheet_kwargs: 'Any') -> 'tuple[ObjectDB, CharacterSheet, Persona]' — Atomically create a Character + CharacterSheet + PRIMARY Persona.`
- `deny_application(application: 'DraftApplication', *, reviewer: 'AbstractBaseUser | AnonymousUser', comment: 'str') -> 'None' — Deny an application.`
- `finalize_character(draft: 'CharacterDraft', *, add_to_roster: 'bool' = False, created_by_account: 'AccountDB | None' = None) -> 'ObjectDB' — Create a Character from a completed CharacterDraft.`
- `finalize_gm_character(draft: 'CharacterDraft') -> 'tuple[RosterEntry, Story]' — Finalize a GM-initiated draft into a roster character + story.`
- `finalize_magic_data(draft: 'CharacterDraft', sheet: 'CharacterSheet') -> 'None' — Create magic models from cantrip selection during finalization.`
- `get_accessible_starting_areas(account: 'AbstractBaseUser | AnonymousUser') -> 'QuerySet' — Get all starting areas accessible to an account.`
- `request_revisions(application: 'DraftApplication', *, reviewer: 'AbstractBaseUser | AnonymousUser', comment: 'str') -> 'None' — Request revisions on an application.`
- `resubmit_draft(application: 'DraftApplication', *, comment: 'str' = '') -> 'None' — Resubmit a draft application after revisions.`
- `submit_draft_for_review(draft: 'CharacterDraft', *, submission_notes: 'str' = '') -> 'DraftApplication' — Submit a character draft for staff review.`
- `unsubmit_draft(application: 'DraftApplication') -> 'None' — Un-submit a draft application, returning it to editable state.`
- `withdraw_draft(application: 'DraftApplication') -> 'None' — Withdraw a draft application.`


## world.character_sheets

### Heritage
**Pointed to by:**
  - profiles <- character_sheets.Profile
  - beginnings <- character_creation.Beginnings

### Profile
**Foreign Keys:**
  - heritage -> character_sheets.Heritage [FK] (nullable)
  - origin_realm -> realms.Realm [FK] (nullable)
  - family -> roster.Family [FK] (nullable)
  - tarot_card -> tarot.TarotCard [FK] (nullable)
**Pointed to by:**
  - owning_sheet <- character_sheets.CharacterSheet
  - personas <- scenes.Persona

### CharacterSheet
**Foreign Keys:**
  - character -> objects.ObjectDB [OneToOne]
  - build -> forms.Build [FK] (nullable)
  - gender -> character_sheets.Gender [FK] (nullable)
  - pronouns -> character_sheets.Pronouns [FK] (nullable)
  - species -> species.Species [FK] (nullable)
  - current_residence -> evennia_extensions.RoomProfile [FK] (nullable)
  - true_profile -> character_sheets.Profile [OneToOne] (nullable)
  - active_persona -> scenes.Persona [FK] (nullable)
  - created_by -> accounts.AccountDB [FK] (nullable)
**Pointed to by:**
  - roster_entry <- roster.RosterEntry
  - class_level_advancements <- progression.ClassLevelAdvancement
  - officiated_advancements <- progression.ClassLevelAdvancement
  - durance_training_roles <- progression.DuranceTrainingSite
  - path_intent <- progression.PathIntent
  - development_points <- progression.DevelopmentPoints
  - development_transactions <- progression.DevelopmentTransaction
  - weekly_skill_usage <- progression.WeeklySkillUsage
  - audere_offers <- magic.PendingAudereOffer
  - audere_majora_offers <- magic.PendingAudereMajoraOffer
  - audere_majora_crossings <- magic.AudereMajoraCrossing
  - entry_flourish_offers <- magic.PendingEntryFlourishOffer
  - created_gifts <- magic.Gift
  - character_gifts <- magic.CharacterGift
  - character_traditions <- magic.CharacterTradition
  - authored_techniques <- magic.Technique
  - character_techniques <- magic.CharacterTechnique
  - pending_alterations <- magic.PendingAlteration
  - alteration_events <- magic.MagicalAlterationEvent
  - anima_ritual_participations <- magic.AnimaRitualPerformance
  - resonances <- magic.CharacterResonance
  - affinity_totals <- magic.CharacterAffinityTotal
  - dramatic_moment_tags <- magic.DramaticMomentTag
  - poseendorsement_given <- magic.PoseEndorsement
  - poseendorsement_received <- magic.PoseEndorsement
  - sceneentryendorsement_given <- magic.SceneEntryEndorsement
  - sceneentryendorsement_received <- magic.SceneEntryEndorsement
  - presentationendorsement_given <- magic.PresentationEndorsement
  - presentationendorsement_received <- magic.PresentationEndorsement
  - stylepresentationendorsement_given <- magic.StylePresentationEndorsement
  - stylepresentationendorsement_received <- magic.StylePresentationEndorsement
  - entry_flourish_records <- magic.EntryFlourishRecord
  - gift_unlocks <- magic.CharacterGiftUnlock
  - resonance_grants <- magic.ResonanceGrant
  - motif <- magic.Motif
  - reincarnations <- magic.Reincarnation
  - pending_ritual_effects <- magic.PendingRitualEffect
  - founded_sanctums <- magic.SanctumDetails
  - sanctum_pending_payouts <- magic.SanctumPendingPayout
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
  - threads <- magic.Thread
  - thread_weaving_unlocks <- magic.CharacterThreadWeavingUnlock
  - personas <- scenes.Persona
  - persona_discoveries <- scenes.PersonaDiscovery
  - scene_round_participations <- scenes.SceneRoundParticipant
  - pending_sudden_harm <- scenes.PendingSuddenHarm
  - character_stories <- stories.Story
  - aggregate_contributions <- stories.AggregateBeatContribution
  - beat_completions <- stories.BeatCompletion
  - episode_resolutions <- stories.EpisodeResolution
  - story_progress <- stories.StoryProgress
  - alternate_selves <- forms.AlternateSelf
  - active_alternate_self <- forms.ActiveAlternateSelf
  - purse <- currency.CharacterPurse
  - employments <- currency.CharacterEmployment
  - secrets <- secrets.Secret
  - secret_grievances <- secrets.SecretGrievance
  - modifiers <- mechanics.CharacterModifier
  - consequence_outcomes <- checks.ConsequenceOutcome
  - relationships_as_source <- relationships.CharacterRelationship
  - relationships_as_target <- relationships.CharacterRelationship
  - relationshipupdate_set <- relationships.RelationshipUpdate
  - relationshipdevelopment_set <- relationships.RelationshipDevelopment
  - relationshipcapstone_set <- relationships.RelationshipCapstone
  - relationshipchange_set <- relationships.RelationshipChange
  - stat_trackers <- achievements.StatTracker
  - achievements <- achievements.CharacterAchievement
  - titles <- achievements.CharacterTitle
  - owned_instances <- instances.InstancedRoom
  - captivities <- captivity.Captivity
  - journal_entries <- journals.JournalEntry
  - weekly_journal_xp <- journals.WeeklyJournalXP
  - owned_items <- items.ItemInstance
  - crafted_items <- items.ItemInstance
  - items_given_away <- items.OwnershipEvent
  - items_received <- items.OwnershipEvent
  - outfits <- items.Outfit
  - fashion_presentations <- items.FashionPresentation
  - mantle_clearances <- items.MantleLevelClearance
  - fatigue <- fatigue.FatiguePool
  - led_courts <- covenants.Covenant
  - covenant_role_assignments <- covenants.CharacterCovenantRole
  - covenant_rite_instances <- covenants.CovenantRiteInstance
  - mentor_bonds_as_mentor <- covenants.MentorBond
  - mentor_bonds_as_sidekick <- covenants.MentorBond
  - court_pacts <- covenants.CourtPact
  - vitals <- vitals.CharacterVitals
  - duels_won <- combat.CombatEncounter
  - summoned_combatants <- combat.CombatOpponent
  - combo_learnings <- combat.ComboLearning
  - combat_participations <- combat.CombatParticipant
  - combat_risk_acknowledgements <- combat.EncounterRiskAcknowledgement
  - duel_challenges_issued <- combat.DuelChallenge
  - duel_challenges_received <- combat.DuelChallenge
  - commanded_battle_units <- battles.BattleUnit
  - summoned_battle_units <- battles.BattleUnit
  - battle_participations <- battles.BattleParticipant
  - narrative_message_deliveries <- narrative.NarrativeMessageDelivery
  - detected_traps <- room_features.Trap

### Gender
**Pointed to by:**
  - character_sheets <- character_sheets.CharacterSheet
  - drafts <- character_creation.CharacterDraft

### Pronouns
**Pointed to by:**
  - character_sheets <- character_sheets.CharacterSheet

### Service Functions
- `can_edit_character_sheet(user: 'AbstractBaseUser | AnonymousUser', roster_entry: 'RosterEntry') -> 'bool' — True if the user is the original creator (player_number=1) or staff.`
- `count_active_ocs(account: 'AbstractBaseUser') -> 'int' — Count OCs an account currently holds against its cap.`
- `create_character_with_sheet(*, character_key: 'str', primary_persona_name: 'str', typeclass: 'str' = 'typeclasses.characters.Character', home: 'ObjectDB | None' = None, **sheet_kwargs: 'Any') -> 'tuple[ObjectDB, CharacterSheet, Persona]' — Atomically create a Character + CharacterSheet + PRIMARY Persona.`
- `enforce_oc_cap(account: 'AbstractBaseUser', *, cap: 'int' = 3) -> 'None' — Raise OCCapError if creating another OC would exceed ``cap``.`


## world.checks

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

### CheckCategory
**Pointed to by:**
  - check_types <- checks.CheckType

### CheckType
**Foreign Keys:**
  - category -> checks.CheckCategory [FK]
**Pointed to by:**
  - action_templates <- actions.ActionTemplate
  - action_template_gates <- actions.ActionTemplateGate
  - soulfrayconfig_set <- magic.SoulfrayConfig
  - scene_check_modifiers <- scenes.SceneCheckModifier
  - professions <- currency.Profession
  - cures_conditions <- conditions.ConditionTemplate
  - resists_condition_applications <- conditions.ConditionTemplate
  - conditionstage_set <- conditions.ConditionStage
  - conditioncheckmodifier_set <- conditions.ConditionCheckModifier
  - treatmenttemplate_set <- conditions.TreatmentTemplate
  - modifier_target <- mechanics.ModifierTarget
  - challenge_approaches <- mechanics.ChallengeApproach
  - context_consequence_pools <- mechanics.ContextConsequencePool
  - consequence_outcomes <- checks.ConsequenceOutcome
  - traits <- checks.CheckTypeTrait
  - aspects <- checks.CheckTypeAspect
  - specializations <- checks.CheckTypeSpecialization
  - item_check_modifiers <- items.ItemCheckModifier
  - escalation_curves <- combat.EscalationCurve
  - project_contribution_methods <- projects.ContributionMethod
  - detect_traps <- room_features.Trap
  - disarm_traps <- room_features.Trap

### CheckTypeTrait
**Foreign Keys:**
  - check_type -> checks.CheckType [FK]
  - trait -> traits.Trait [FK]

### CheckTypeAspect
**Foreign Keys:**
  - check_type -> checks.CheckType [FK]
  - aspect -> classes.Aspect [FK]

### CheckTypeSpecialization
**Foreign Keys:**
  - check_type -> checks.CheckType [FK]
  - specialization -> skills.Specialization [FK]

### Consequence
**Foreign Keys:**
  - outcome_tier -> traits.CheckOutcome [FK]
**Pointed to by:**
  - pool_entries <- actions.ConsequencePoolEntry
  - challenge_templates <- mechanics.ChallengeTemplate
  - challenge_template_consequences <- mechanics.ChallengeTemplateConsequence
  - approach_consequences <- mechanics.ApproachConsequence
  - challenge_records <- mechanics.CharacterChallengeRecord
  - consequence_outcomes <- checks.ConsequenceOutcome
  - effects <- checks.ConsequenceEffect

### ConsequenceEffect
**Foreign Keys:**
  - consequence -> checks.Consequence [FK]
  - condition_template -> conditions.ConditionTemplate [FK] (nullable)
  - relationship_condition -> relationships.RelationshipCondition [FK] (nullable)
  - property -> mechanics.Property [FK] (nullable)
  - damage_type -> conditions.DamageType [FK] (nullable)
  - flow_definition -> flows.FlowDefinition [FK] (nullable)
  - codex_entry -> codex.CodexEntry [FK] (nullable)
  - legend_source_type -> societies.LegendSourceType [FK] (nullable)
  - capture_captor_organization -> societies.Organization [FK] (nullable)
  - capture_captive_template -> missions.MissionTemplate [FK] (nullable)
  - capture_rescue_template -> missions.MissionTemplate [FK] (nullable)

### Service Functions
- `chart_has_success_outcomes(rank_difference: int) -> bool — Check if the ResultChart for this rank difference has any success outcomes.`
- `collect_check_modifiers(character_sheet: 'CharacterSheet', check_type: 'CheckType', *, scene: 'Scene | None' = None, extra_contributions: list[world.checks.types.ModifierContribution] | None = None) -> world.checks.types.ModifierBreakdown — Aggregate all modifier contributions for a check into a ModifierBreakdown.`
- `compute_resist_increment(defender_character: 'ObjectDB', resist_effort_level: str) -> int — Compute how much a defender's active resistance raises difficulty.`
- `get_rollmod(character: 'ObjectDB') -> int — Sum character.sheet_data.rollmod + character.account.player_data.rollmod.`
- `perform_check(character: 'ObjectDB', check_type: 'CheckType', target_difficulty: int = 0, extra_modifiers: int = 0, effort_level: str | None = None, fatigue_penalty: int = 0, specialization: 'Specialization | None' = None) -> world.checks.types.CheckResult — Main check resolution function.`
- `preview_check_difficulty(character: 'ObjectDB', check_type: 'CheckType', target_difficulty: int = 0, extra_modifiers: int = 0) -> int — Preview the rank difference for a check without rolling.`
- `record_consequence_outcome(character_sheet: 'CharacterSheet', check_type: 'CheckType', pool, selected_consequence: 'Consequence | None', breakdown: world.checks.types.ModifierBreakdown, *, combat_interaction: 'Interaction | None' = None, challenge_record: 'CharacterChallengeRecord | None' = None, summary: str = '') -> world.checks.outcome_models.ConsequenceOutcome — Persist one consequence-resolution event as a ConsequenceOutcome + modifier rows.`


## world.classes

### Path
**Foreign Keys:**
  - parent_paths -> classes.Path [M2M]
**Pointed to by:**
  - skill_suggestions <- skills.PathSkillSuggestion
  - drafts <- character_creation.CharacterDraft
  - child_paths <- classes.Path
  - path_aspects <- classes.PathAspect
  - durance_training_sites <- progression.DuranceTrainingSite
  - path_intents <- progression.PathIntent
  - character_selections <- progression.CharacterPathHistory
  - audere_majora_crossings <- magic.AudereMajoraCrossing
  - allowed_styles <- magic.TechniqueStyle
  - gift_unlocks <- magic.GiftUnlock
  - ritual_grants <- magic.PathRitualGrant
  - gift_grants <- magic.PathGiftGrant
  - thread_weaving_unlocks <- magic.ThreadWeavingUnlock
  - codex_grants <- codex.PathCodexGrant

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
  - character -> objects.ObjectDB [FK]
  - character_class -> classes.CharacterClass [FK]

### ClassStageHealthRate
**Foreign Keys:**
  - character_class -> classes.CharacterClass [FK]

### Aspect
**Pointed to by:**
  - path_aspects <- classes.PathAspect
  - check_type_aspects <- checks.CheckTypeAspect

### PathAspect
**Foreign Keys:**
  - character_path -> classes.Path [FK]
  - aspect -> classes.Aspect [FK]

### Service Functions
- `set_primary_class_level(character: object, character_class: object, level: int) -> object — Set the character's primary class level and recompute level-derived health.`
- `stage_for_level(level: int) -> int — Map a class level to its PathStage value (clamps <1 to PROSPECT).`


## world.clues

### Clue
**Foreign Keys:**
  - target_codex_entry -> codex.CodexEntry [FK] (nullable)
  - target_mission -> missions.MissionTemplate [FK] (nullable)
  - target_captivity -> captivity.Captivity [FK] (nullable)
  - target_secret -> secrets.Secret [FK] (nullable)
**Pointed to by:**
  - held_by <- clues.CharacterClue
  - research_projects <- clues.ResearchProjectDetails
  - room_placements <- clues.RoomClue
  - trigger_placements <- clues.ClueTrigger
  - item_trigger_placements <- clues.ItemClueTrigger

### CharacterClue
**Foreign Keys:**
  - roster_entry -> roster.RosterEntry [FK]
  - clue -> clues.Clue [FK]

### ResearchProjectDetails
**Foreign Keys:**
  - project -> projects.Project [OneToOne]
  - clue -> clues.Clue [FK]

### RoomClue
**Foreign Keys:**
  - room_profile -> evennia_extensions.RoomProfile [FK]
  - clue -> clues.Clue [FK]

### ClueTrigger
**Foreign Keys:**
  - room_profile -> evennia_extensions.RoomProfile [FK]
  - clue -> clues.Clue [FK]

### ItemClueTrigger
**Foreign Keys:**
  - item_template -> items.ItemTemplate [FK]
  - clue -> clues.Clue [FK]

### Service Functions
- `acquire_clue(roster_entry: 'RosterEntry', clue: 'Clue') -> 'CharacterClue' — Record that a character has found a clue (idempotent).`
- `clear_rescue_clues(captivity: 'Captivity') -> 'None' — Delete a captivity's rescue clues (and their placements) when it resolves (#931).`
- `grant_clue_target(clue: 'Clue', roster_entry: 'RosterEntry') -> 'None' — AUTOMATIC resolution — grant a clue's target to the character on the spot.`
- `maybe_grant_clue_triggers(character: 'ObjectDB', room: 'ObjectDB') -> 'list[Clue]' — Grant clues triggered passively by entering ``room`` (#1160).`
- `maybe_grant_item_acquisition_clues(character: 'ObjectDB', item: 'ItemInstance') -> 'list[Clue]' — Grant clues triggered passively by ``character`` acquiring ``item`` (#1160).`
- `plant_rescue_clue(captivity: 'Captivity', room_profile: 'RoomProfile', *, name: 'str', description: 'str', detect_difficulty: 'int' = 0) -> 'RoomClue' — Plant a discoverable rescue clue at a location for a held captive (#931 Phase 4).`
- `search_room(character: 'ObjectDB', room_profile: 'RoomProfile', search_check_type: 'CheckType') -> 'list[Clue]' — Search a room: roll ``search_check_type`` against each hidden clue's difficulty.`
- `target_already_known(clue: 'Clue', roster_entry: 'RosterEntry') -> 'bool' — Whether the character already has what this clue points at.`


## world.codex

### CodexCategory
**Pointed to by:**
  - subjects <- codex.CodexSubject

### CodexSubject
**Foreign Keys:**
  - category -> codex.CodexCategory [FK]
  - parent -> codex.CodexSubject [FK] (nullable)
**Pointed to by:**
  - children <- codex.CodexSubject
  - breadcrumb_cache <- codex.CodexSubjectBreadcrumb
  - entries <- codex.CodexEntry
  - climates <- weather.Climate
  - weather_types <- weather.WeatherType
  - architectural_styles <- buildings.ArchitecturalStyle

### CodexSubjectBreadcrumb
**Foreign Keys:**
  - subject -> codex.CodexSubject [OneToOne]

### CodexEntry
**Foreign Keys:**
  - subject -> codex.CodexSubject [FK]
  - modifier_target -> mechanics.ModifierTarget [OneToOne] (nullable)
  - prerequisites -> codex.CodexEntry [M2M]
**Pointed to by:**
  - ritual_grants <- magic.CodexEntryRitualGrant
  - progression_milestones <- magic.MagicProgressionMilestone
  - unlocks <- codex.CodexEntry
  - character_knowledge <- codex.CharacterCodexKnowledge
  - teaching_offers <- codex.CodexTeachingOffer
  - beginnings_grants <- codex.BeginningsCodexGrant
  - path_grants <- codex.PathCodexGrant
  - distinction_grants <- codex.DistinctionCodexGrant
  - tradition_grants <- codex.TraditionCodexGrant
  - clues <- clues.Clue
  - consequence_effects <- checks.ConsequenceEffect
  - mantle_level_gates <- items.MantleLevelDefinition

### CharacterCodexKnowledge
**Foreign Keys:**
  - roster_entry -> roster.RosterEntry [FK]
  - entry -> codex.CodexEntry [FK]
  - learned_from -> roster.RosterTenure [FK] (nullable)

### CodexTeachingOffer
**Foreign Keys:**
  - teacher -> roster.RosterTenure [FK]
  - entry -> codex.CodexEntry [FK]
  - visible_to_tenures -> roster.RosterTenure [M2M]
  - visible_to_groups -> consent.ConsentGroup [M2M]
  - excluded_tenures -> roster.RosterTenure [M2M]

### BeginningsCodexGrant
**Foreign Keys:**
  - beginnings -> character_creation.Beginnings [FK]
  - entry -> codex.CodexEntry [FK]

### PathCodexGrant
**Foreign Keys:**
  - path -> classes.Path [FK]
  - entry -> codex.CodexEntry [FK]

### DistinctionCodexGrant
**Foreign Keys:**
  - distinction -> distinctions.Distinction [FK]
  - entry -> codex.CodexEntry [FK]

### TraditionCodexGrant
**Foreign Keys:**
  - tradition -> magic.Tradition [FK]
  - entry -> codex.CodexEntry [FK]


## world.conditions

### ConditionCategory
**Pointed to by:**
  - conditions <- conditions.ConditionTemplate

### CapabilityType
**Foreign Keys:**
  - prerequisite -> mechanics.Prerequisite [FK] (nullable)
**Pointed to by:**
  - techniquecapabilitygrant_grants <- magic.TechniqueCapabilityGrant
  - technique_requirements <- magic.TechniqueCapabilityRequirement
  - techniquevariantcapabilitygrant_grants <- magic.TechniqueVariantCapabilityGrant
  - signaturemotifbonuscapabilitygrant_grants <- magic.SignatureMotifBonusCapabilityGrant
  - techniquedraftcapabilitygrant_grants <- magic.TechniqueDraftCapabilityGrant
  - thread_pull_effects <- magic.ThreadPullEffect
  - conditioncapabilityeffect_set <- conditions.ConditionCapabilityEffect
  - modifier_target <- mechanics.ModifierTarget
  - applications <- mechanics.Application
  - trait_derivations <- mechanics.TraitCapabilityDerivation
  - blocking_challenges <- mechanics.ChallengeTemplate
  - combat_pull_grants <- combat.CombatPullResolvedEffect
  - battle_units <- battles.BattleUnit
  - battle_unit_values <- battles.BattleUnitCapability
  - battle_weather_challenges <- battles.WeatherTypeCapabilityChallenge

### DamageType
**Foreign Keys:**
  - resonance -> magic.Resonance [OneToOne] (nullable)
  - wound_pool -> actions.ConsequencePool [FK] (nullable)
  - death_pool -> actions.ConsequencePool [FK] (nullable)
**Pointed to by:**
  - techniquedamageprofile_damage_profiles <- magic.TechniqueDamageProfile
  - alteration_weaknesses <- magic.MagicalAlterationTemplate
  - techniquevariantdamageprofile_damage_profiles <- magic.TechniqueVariantDamageProfile
  - signaturemotifbonusdamageprofile_damage_profiles <- magic.SignatureMotifBonusDamageProfile
  - techniquedraftdamageprofile_damage_profiles <- magic.TechniqueDraftDamageProfile
  - thread_pull_resistances <- magic.ThreadPullEffect
  - pending_sudden_harm_entries <- scenes.PendingSuddenHarm
  - conditionresistancemodifier_set <- conditions.ConditionResistanceModifier
  - conditiondamageovertime_set <- conditions.ConditionDamageOverTime
  - conditiondamageinteraction_set <- conditions.ConditionDamageInteraction
  - modifier_target <- mechanics.ModifierTarget
  - property_damage_modifiers <- mechanics.PropertyDamageModifier
  - consequence_effects <- checks.ConsequenceEffect
  - cascade_overrides <- locations.LocationValueOverride
  - cascade_modifiers <- locations.LocationValueModifier
  - weapon_templates <- items.ItemTemplate
  - threat_pool_entries <- combat.ThreatPoolEntry
  - combat_pull_resistances <- combat.CombatPullResolvedEffect

### ConditionTemplate
**Foreign Keys:**
  - category -> conditions.ConditionCategory [FK]
  - cure_check_type -> checks.CheckType [FK] (nullable)
  - resist_check_type -> checks.CheckType [FK] (nullable)
  - parent_condition -> conditions.ConditionTemplate [FK] (nullable)
  - corruption_resonance -> magic.Resonance [FK] (nullable)
  - properties -> mechanics.Property [M2M]
  - reactive_triggers -> flows.TriggerDefinition [M2M]
**Pointed to by:**
  - action_enhancements <- actions.ActionEnhancement
  - species_gift_drawbacks <- species.SpeciesGiftGrant
  - species_gift_benefits <- species.SpeciesGiftGrant
  - techniques_applying <- magic.Technique
  - techniqueappliedcondition_applied <- magic.TechniqueAppliedCondition
  - techniqueremovedcondition_applied <- magic.TechniqueRemovedCondition
  - magical_alteration <- magic.MagicalAlterationTemplate
  - resonance_alignment_tiers <- magic.ResonanceAlignmentBoonTier
  - techniquevariantappliedcondition_applied <- magic.TechniqueVariantAppliedCondition
  - signaturemotifbonusappliedcondition_applied <- magic.SignatureMotifBonusAppliedCondition
  - techniquedraftappliedcondition_applied <- magic.TechniqueDraftAppliedCondition
  - techniquedraftremovedcondition_applied <- magic.TechniqueDraftRemovedCondition
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
  - consequence_effects <- checks.ConsequenceEffect
  - stat_rules_for <- achievements.ConditionStatRule
  - threat_pool_entries <- combat.ThreatPoolEntry

### ConditionStage
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK]
  - resist_check_type -> checks.CheckType [FK] (nullable)
  - consequence_pool -> actions.ConsequencePool [FK] (nullable)
  - properties -> mechanics.Property [M2M]
  - on_entry_conditions -> conditions.ConditionTemplate [M2M]
**Pointed to by:**
  - stage_triggers <- flows.Trigger
  - auderethreshold_set <- magic.AudereThreshold
  - on_entry_assocs <- conditions.ConditionStageOnEntry
  - conditioncapabilityeffect_set <- conditions.ConditionCapabilityEffect
  - conditionmodifiereffect_set <- conditions.ConditionModifierEffect
  - conditioncheckmodifier_set <- conditions.ConditionCheckModifier
  - conditionresistancemodifier_set <- conditions.ConditionResistanceModifier
  - conditiondamageovertime_set <- conditions.ConditionDamageOverTime
  - conditioninstance_set <- conditions.ConditionInstance

### ConditionStageOnEntry
**Foreign Keys:**
  - stage -> conditions.ConditionStage [FK]
  - condition -> conditions.ConditionTemplate [FK]

### ConditionCapabilityEffect
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK] (nullable)
  - stage -> conditions.ConditionStage [FK] (nullable)
  - capability -> conditions.CapabilityType [FK]

### ConditionModifierEffect
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK] (nullable)
  - stage -> conditions.ConditionStage [FK] (nullable)
  - modifier_target -> mechanics.ModifierTarget [FK]

### ConditionCheckModifier
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK] (nullable)
  - stage -> conditions.ConditionStage [FK] (nullable)
  - check_type -> checks.CheckType [FK]

### ConditionResistanceModifier
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK] (nullable)
  - stage -> conditions.ConditionStage [FK] (nullable)
  - damage_type -> conditions.DamageType [FK] (nullable)

### ConditionDamageOverTime
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK] (nullable)
  - stage -> conditions.ConditionStage [FK] (nullable)
  - damage_type -> conditions.DamageType [FK]

### ConditionDamageInteraction
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK]
  - damage_type -> conditions.DamageType [FK]
  - applies_condition -> conditions.ConditionTemplate [FK] (nullable)

### ConditionConditionInteraction
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK]
  - other_condition -> conditions.ConditionTemplate [FK]
  - result_condition -> conditions.ConditionTemplate [FK] (nullable)

### ConditionInstance
**Foreign Keys:**
  - target -> objects.ObjectDB [FK]
  - condition -> conditions.ConditionTemplate [FK]
  - current_stage -> conditions.ConditionStage [FK] (nullable)
  - source_character -> objects.ObjectDB [FK] (nullable)
  - source_technique -> magic.Technique [FK] (nullable)
**Pointed to by:**
  - triggers <- flows.Trigger
  - alteration_events <- magic.MagicalAlterationEvent
  - treatment_action_requests <- scenes.SceneActionRequest
  - treatment_attempts_targeting_instance <- conditions.TreatmentAttempt
  - granted_properties <- mechanics.ObjectProperty

### TreatmentTemplate
**Foreign Keys:**
  - target_condition -> conditions.ConditionTemplate [FK]
  - check_type -> checks.CheckType [FK]
  - backlash_target_condition -> conditions.ConditionTemplate [FK] (nullable)
**Pointed to by:**
  - action_requests <- scenes.SceneActionRequest
  - attempts <- conditions.TreatmentAttempt

### TreatmentAttempt
**Foreign Keys:**
  - helper -> objects.ObjectDB [FK]
  - target -> objects.ObjectDB [FK]
  - scene -> scenes.Scene [FK]
  - treatment -> conditions.TreatmentTemplate [FK]
  - thread_used -> magic.Thread [FK] (nullable)
  - target_condition_instance -> conditions.ConditionInstance [FK] (nullable)
  - target_pending_alteration -> magic.PendingAlteration [FK] (nullable)
  - outcome -> traits.CheckOutcome [FK]

### DamageSuccessLevelMultiplier

### PenetrationOutcomeFactor

### Service Functions
- `advance_condition_severity(instance: world.conditions.models.ConditionInstance, amount: int) -> world.conditions.types.SeverityAdvanceResult — Increment a condition's severity and advance stage if threshold crossed.`
- `apply_condition(target: 'ObjectDB', condition: world.conditions.models.ConditionTemplate, *, severity: int = 1, duration_rounds: int | None = None, source_character: 'ObjectDB | None' = None, source_technique: 'Technique | None' = None, source_description: str = '') -> world.conditions.types.ApplyConditionResult — Apply a condition to a target, handling stacking and interactions.`
- `apply_condition_by_name(*, payload: object, condition_name: str) -> None — Apply a named condition to the character carried by the event payload.`
- `apply_stage_entry_aftermath(payload: flows.events.payloads.ConditionStageChangedPayload) -> None — On ascending stage changes, apply the stage's on_entry_conditions.`
- `batch_chronic_effect_tick() -> world.conditions.types.ChronicTickSummary — Scheduler entry point. Advance long-term (chronic) DoT by one tick.`
- `bulk_apply_conditions(applications: list[world.conditions.types.BulkConditionApplication], *, source_character: 'ObjectDB | None' = None, source_technique: 'Technique | None' = None, source_description: str = '') -> list[world.conditions.types.ApplyConditionResult] — Apply multiple conditions in a single transaction with batched queries.`
- `clear_all_conditions(target: 'ObjectDB', *, only_negative: bool = False, only_category: 'ConditionCategory | None' = None) -> int — Remove all conditions from a target.`
- `condition_contributions(character_sheet: 'CharacterSheet', check_type: world.checks.models.CheckType) -> list[world.checks.types.ModifierContribution] — Adapt get_check_modifier's breakdown into a list of ModifierContribution.`
- `decay_all_conditions_tick() -> world.conditions.types.DecayTickSummary — Scheduler entry point. Decays all opt-in conditions by one tick.`
- `decay_condition_severity(instance: world.conditions.models.ConditionInstance, amount: int, *, _skip_corruption_sync: bool = False) -> world.conditions.types.SeverityDecayResult — Inverse of advance_condition_severity. Walks stage down if threshold crossed.`
- `emit_event(event_name: str, payload: Any, location: Any, *, parent_stack: flows.flow_stack.FlowStack | None = None) -> flows.flow_stack.FlowStack — Dispatch ``event_name`` to every handler in ``location`` + contents.`
- `ensure_conditions_content() -> None — Idempotently seed all core conditions content.`
- `ensure_poison_content() -> None — Idempotently seed poison content (#1050).`
- `expire_end_of_combat_conditions(targets: collections.abc.Iterable['ObjectDB']) -> list[world.conditions.models.ConditionTemplate] — Remove all UNTIL_END_OF_COMBAT conditions from the given targets.`
- `get_active_conditions(target: 'ObjectDB', *, category: 'ConditionCategory | None' = None, condition: world.conditions.models.ConditionTemplate | None = None, include_suppressed: bool = False) -> django.db.models.query.QuerySet — Get active condition instances on a target.`
- `get_aggro_priority(character_sheet: 'CharacterSheet') -> int — Get the total aggro priority from all conditions.`
- `get_all_capability_values(character_sheet: 'CharacterSheet') -> dict[int, int] — Get all capability values for a character.`
- `get_capability_status(character_sheet: 'CharacterSheet', capability: world.conditions.models.CapabilityType) -> world.conditions.types.CapabilityStatus — Get the status of a capability for a target based on active conditions.`
- `get_capability_value(character_sheet: 'CharacterSheet', capability: world.conditions.models.CapabilityType) -> int — Get the total value of a capability for a character.`
- `get_check_modifier(character_sheet: 'CharacterSheet', check_type: world.checks.models.CheckType) -> world.conditions.types.CheckModifierResult — Get the total modifier for a check type from active conditions.`
- `get_condition_control_percent_modifier(character_sheet: 'CharacterSheet', condition_name: str) -> int — Get percentage modifier to control loss rate for a condition.`
- `get_condition_instance(target: 'ObjectDB', condition: world.conditions.models.ConditionTemplate, *, include_suppressed: bool = False) -> world.conditions.models.ConditionInstance | None — Get a specific condition instance on a target.`
- `get_condition_intensity_percent_modifier(character_sheet: 'CharacterSheet', condition_name: str) -> int — Get percentage modifier to intensity gain for a condition.`
- `get_condition_modifier_breakdown(character_sheet: 'CharacterSheet', modifier_target: 'ModifierTarget') -> list[tuple[str, int]] — Per-source sibling of get_condition_modifier_total (#639 power ledger).`
- `get_condition_modifier_total(character_sheet: 'CharacterSheet', modifier_target: 'ModifierTarget') -> int — Sum active-condition contributions to a mechanics ModifierTarget (#636).`
- `get_condition_penalty_percent_modifier(character_sheet: 'CharacterSheet', condition_name: str) -> int — Get percentage modifier to check penalties for a condition.`
- `get_damage_multiplier(success_level: int) -> decimal.Decimal — Look up the damage multiplier for a given success level.`
- `get_effective_capability_value(character_sheet: 'CharacterSheet', capability: world.conditions.models.CapabilityType) -> int — Effective capability value = innate baseline + CharacterModifier contributions`
- `get_ic_now(*, real_now: datetime.datetime | None = None) -> datetime.datetime | None — Return the current IC datetime, or None if no clock exists.`
- `get_penetration_factor(success_level: int) -> decimal.Decimal — Look up the penetration power factor for a given success level (#639).`
- `get_resistance_modifier(character_sheet: 'CharacterSheet', damage_type: world.conditions.models.DamageType | None = None) -> world.conditions.types.ResistanceModifierResult — Get the total resistance modifier for a damage type from active conditions.`
- `get_treatment_candidates(helper_sheet: 'CharacterSheet', target_sheet: 'CharacterSheet', scene: 'Scene') -> list[dict[str, typing.Any]] — Return valid (treatment, target_effect) pairs for helper to attempt on target.`
- `get_turn_order_modifier(character_sheet: 'CharacterSheet') -> int — Get the total turn order modifier from all conditions.`
- `has_condition(target: 'ObjectDB', condition: world.conditions.models.ConditionTemplate, *, include_suppressed: bool = False) -> bool — Check if target has a specific condition.`
- `has_death_deferred(character: 'ObjectDB') -> bool — Return True if the character has any active condition granting death_deferred.`
- `is_untargetable(target: 'ObjectDB') -> bool — True if *target* holds any active intangibility condition.`
- `perform_check(character: 'ObjectDB', check_type: 'CheckType', target_difficulty: int = 0, extra_modifiers: int = 0, effort_level: str | None = None, fatigue_penalty: int = 0, specialization: 'Specialization | None' = None) -> world.checks.types.CheckResult — Main check resolution function.`
- `perform_treatment(helper_sheet: 'CharacterSheet', target_sheet: 'CharacterSheet', scene: 'Scene', treatment: world.conditions.models.TreatmentTemplate, target_effect: 'ConditionInstance | PendingAlteration', bond_thread: 'Thread | None' = None) -> world.conditions.types.TreatmentOutcome — Resolve a TreatmentTemplate against an effect instance.`
- `process_action_tick(target: 'ObjectDB') -> world.conditions.types.RoundTickResult — Process on-action damage for conditions (when target takes an action).`
- `process_damage_interactions(target: 'ObjectDB', damage_type: world.conditions.models.DamageType) -> world.conditions.types.DamageInteractionResult — Process condition interactions when target takes damage.`
- `process_round_end(target: 'ObjectDB') -> world.conditions.types.RoundTickResult — Process end-of-round effects for all conditions on a target.`
- `process_round_start(target: 'ObjectDB') -> world.conditions.types.RoundTickResult — Process start-of-round effects for all conditions on a target.`
- `remove_condition(target: 'ObjectDB', condition: world.conditions.models.ConditionTemplate, *, remove_all_stacks: bool = True, include_suppressed: bool = False) -> bool — Remove a condition from a target.`
- `remove_conditions_by_category(target: 'ObjectDB', category: 'ConditionCategory') -> list[world.conditions.models.ConditionTemplate] — Remove all conditions in a category from a target.`
- `resolve_damage_type_resistance(character: 'ObjectDB', damage_amount: int, damage_type: 'DamageType | None') -> int — Net damage-type resistance (condition + gift-thread) and return reduced damage (>=0).`
- `suppress_condition(target: 'ObjectDB', condition: world.conditions.models.ConditionTemplate, *, duration_rounds: int | None = None) -> bool — Temporarily suppress a condition's effects.`
- `unsuppress_condition(target: 'ObjectDB', condition: world.conditions.models.ConditionTemplate) -> bool — Remove suppression from a condition.`


## world.consent

### ConsentGroup
**Foreign Keys:**
  - owner -> roster.RosterTenure [FK]
**Pointed to by:**
  - members <- consent.ConsentGroupMember
  - codexteachingoffer_visible <- codex.CodexTeachingOffer

### ConsentGroupMember
**Foreign Keys:**
  - group -> consent.ConsentGroup [FK]
  - tenure -> roster.RosterTenure [FK]

### SocialConsentCategory
**Pointed to by:**
  - action_templates <- actions.ActionTemplate
  - rules <- consent.SocialConsentCategoryRule
  - whitelist_entries <- consent.SocialConsentWhitelist
  - blacklist_entries <- consent.SocialConsentBlacklist

### SocialConsentPreference
**Foreign Keys:**
  - tenure -> roster.RosterTenure [OneToOne]
**Pointed to by:**
  - category_rules <- consent.SocialConsentCategoryRule

### SocialConsentCategoryRule
**Foreign Keys:**
  - preference -> consent.SocialConsentPreference [FK]
  - category -> consent.SocialConsentCategory [FK]

### SocialConsentWhitelist
**Foreign Keys:**
  - owner_tenure -> roster.RosterTenure [FK]
  - allowed_tenure -> roster.RosterTenure [FK]
  - category -> consent.SocialConsentCategory [FK]

### SocialConsentBlacklist
**Foreign Keys:**
  - owner_tenure -> roster.RosterTenure [FK]
  - blocked_tenure -> roster.RosterTenure [FK]
  - category -> consent.SocialConsentCategory [FK]

### Service Functions
- `add_social_consent_blacklist(owner_tenure: 'RosterTenure', blocked_tenure: 'RosterTenure', category: 'SocialConsentCategory') -> 'SocialConsentBlacklist' — Bar *blocked_tenure* from targeting *owner_tenure* in *category* (#1698).`
- `add_social_consent_whitelist(owner_tenure: 'RosterTenure', allowed_tenure: 'RosterTenure', category: 'SocialConsentCategory') -> 'SocialConsentWhitelist'`
- `get_social_consent_summary(tenure: 'RosterTenure') -> 'dict'`
- `remove_social_consent_blacklist(owner_tenure: 'RosterTenure', blocked_tenure: 'RosterTenure', category: 'SocialConsentCategory') -> 'bool'`
- `remove_social_consent_category_rule(preference: 'SocialConsentPreference', category: 'SocialConsentCategory') -> 'bool'`
- `remove_social_consent_whitelist(owner_tenure: 'RosterTenure', allowed_tenure: 'RosterTenure', category: 'SocialConsentCategory') -> 'bool'`
- `set_social_consent_category_rule(preference: 'SocialConsentPreference', category: 'SocialConsentCategory', mode: 'str') -> 'SocialConsentCategoryRule'`
- `set_social_consent_preference(tenure: 'RosterTenure', allow_social_actions: 'bool') -> 'SocialConsentPreference'`


## world.covenants

### Covenant
**Foreign Keys:**
  - organization -> societies.Organization [OneToOne]
  - campaign_story -> stories.Story [FK] (nullable)
  - leader -> character_sheets.CharacterSheet [FK] (nullable)
**Pointed to by:**
  - ritualsessionreference_set <- magic.RitualSessionReference
  - storylines <- stories.Story
  - legend_credits <- societies.CovenantLegendCredit
  - legend_summary <- societies.CovenantLegendSummary
  - ranks <- covenants.CovenantRank
  - memberships <- covenants.CharacterCovenantRole
  - rite_instances <- covenants.CovenantRiteInstance
  - mentor_bonds <- covenants.MentorBond
  - court_pacts <- covenants.CourtPact
  - battle_sides <- battles.BattleSide

### CovenantRole
**Foreign Keys:**
  - resonance -> magic.Resonance [FK] (nullable)
  - discovery_achievement -> achievements.Achievement [FK] (nullable)
  - codex_entry -> codex.CodexEntry [FK] (nullable)
  - parent_role -> covenants.CovenantRole [FK] (nullable)
**Pointed to by:**
  - ritualsessionreference_set <- magic.RitualSessionReference
  - anchored_threads <- magic.Thread
  - sub_roles <- covenants.CovenantRole
  - gear_compatibilities <- covenants.GearArchetypeCompatibility
  - character_assignments <- covenants.CharacterCovenantRole
  - role_bonuses <- covenants.CovenantRoleBonus
  - combat_participations <- combat.CombatParticipant

### GearArchetypeCompatibility
**Foreign Keys:**
  - covenant_role -> covenants.CovenantRole [FK]

### CovenantRank
**Foreign Keys:**
  - covenant -> covenants.Covenant [FK]
**Pointed to by:**
  - memberships <- covenants.CharacterCovenantRole

### CharacterCovenantRole
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - covenant_role -> covenants.CovenantRole [FK]
  - covenant -> covenants.Covenant [FK]
  - rank -> covenants.CovenantRank [FK]

### CovenantLevelThreshold

### CovenantLevelBonus
**Foreign Keys:**
  - modifier_target -> mechanics.ModifierTarget [FK]

### CovenantRoleBonus
**Foreign Keys:**
  - covenant_role -> covenants.CovenantRole [FK]
  - modifier_target -> mechanics.ModifierTarget [FK]

### CovenantRite
**Foreign Keys:**
  - ritual -> magic.Ritual [OneToOne]
  - granted_condition -> conditions.ConditionTemplate [FK]
**Pointed to by:**
  - role_packages <- covenants.CovenantRiteRolePackage
  - instances <- covenants.CovenantRiteInstance

### CovenantRiteRolePackage
**Foreign Keys:**
  - rite -> covenants.CovenantRite [FK]
  - covenant_role -> covenants.CovenantRole [FK]
  - condition_template -> conditions.ConditionTemplate [FK]

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

### MentorBondConfig
**Foreign Keys:**
  - updated_by -> accounts.AccountDB [FK] (nullable)

### MentorBond
**Foreign Keys:**
  - covenant -> covenants.Covenant [FK]
  - mentor_sheet -> character_sheets.CharacterSheet [FK]
  - sidekick_sheet -> character_sheets.CharacterSheet [FK]

### CourtPact
**Foreign Keys:**
  - covenant -> covenants.Covenant [FK]
  - servant_sheet -> character_sheets.CharacterSheet [FK]

### Service Functions
- `active_court_pact_for(*, covenant: 'Covenant', servant_sheet: 'CharacterSheet') -> 'CourtPact | None' — Return the single active CourtPact for (covenant, servant_sheet), or None.`
- `add_member(*, covenant: 'Covenant', character_sheet: 'CharacterSheet', role: 'CovenantRole') -> 'CharacterCovenantRole' — Create a new active membership row. Atomic.`
- `assert_initiator_can_induct(*, session: 'RitualSession') -> 'None' — Draft-time gate for INDUCTION rituals: the initiator must hold a can_invite`
- `assign_covenant_role(*, character_sheet: 'CharacterSheet', covenant: 'Covenant', covenant_role: 'CovenantRole', rank: 'CovenantRank | None' = None) -> 'CharacterCovenantRole' — Create a new active CharacterCovenantRole row. Atomic.`
- `assign_rank(*, membership: 'CharacterCovenantRole', actor: 'CharacterCovenantRole', rank: 'CovenantRank') -> 'CharacterCovenantRole' — Assign a new rank to a member. Requires can_manage_ranks.`
- `can_invite_to_covenant(covenant: 'Covenant', *, character_sheet: 'CharacterSheet | None' = None, account: 'AccountDB | None' = None) -> 'bool' — Return True if an active member with a can_invite rank grants invite authority.`
- `change_role(*, membership: 'CharacterCovenantRole', new_role: 'CovenantRole') -> 'CharacterCovenantRole' — Close the existing membership row; create a new active row in the same covenant.`
- `clear_engaged_for_type(*, character_sheet: 'CharacterSheet', covenant_type: 'str') -> 'None' — Un-engage every engaged active membership of the given type for the character.`
- `clear_engaged_membership(*, membership: 'CharacterCovenantRole') -> 'None' — Un-engage this membership. Idempotent.`
- `complete_rites_for_encounter(*, encounter: 'CombatEncounter') -> 'None' — Sweep covenant rite buffs when a combat encounter ends.`
- `covenant_members_present(*, covenant: 'Covenant', room: 'ObjectDB') -> 'list[CharacterSheet]' — CharacterSheets of active `covenant` members present in `room`.`
- `create_covenant(*, name: 'str', covenant_type: 'str', sworn_objective: 'str', founders: 'Sequence[CovenantFounder]', battle_binding: 'str' = '', campaign_story: 'Story | None' = None, leader: 'CharacterSheet | None' = None, flat: 'bool' = False) -> 'Covenant' — Create a covenant with its initial set of founder memberships. Atomic.`
- `create_covenant_via_session(*, session: 'RitualSession') -> 'Covenant' — Dispatched on FORMATION fire. Unpacks the session into create_covenant args.`
- `create_rank(*, covenant: 'Covenant', actor: 'CharacterCovenantRole', name: 'str', tier: 'int', can_invite: 'bool' = False, can_kick: 'bool' = False, can_manage_ranks: 'bool' = False) -> 'CovenantRank' — Create a new rank in the covenant's ladder. Requires can_manage_ranks.`
- `delete_rank(*, rank: 'CovenantRank', actor: 'CharacterCovenantRole', reassign_to: 'CovenantRank') -> 'None' — Delete a rank after reassigning all active members to ``reassign_to``.`
- `dissolve_covenant(*, covenant: 'Covenant') -> 'None' — End all active memberships of the covenant; mark covenant dissolved.`
- `end_covenant_role(*, assignment: 'CharacterCovenantRole') -> 'None' — Mark an active assignment as ended. Idempotent. Un-engages first.`
- `establish_mentor_bond_via_session(*, session: 'RitualSession') -> 'MentorBond' — Dispatched on Mentor's Vow BILATERAL fire. Wraps establish_mentor_bond.`
- `evaluate_scene_engagement(*, character_sheet: 'CharacterSheet', room: 'ObjectDB') -> 'None' — Auto-engage a Durance covenant if co-presence prerequisites met, then`
- `fold_arrival_into_active_rites(*, character_sheet: 'CharacterSheet', room: 'ObjectDB') -> 'None' — When an engaged member arrives in a room with an active CovenantRiteInstance,`
- `get_mentor_bond_config() -> 'MentorBondConfig' — Return the seeded MentorBondConfig singleton (#1165).`
- `induct_member_via_session(*, session: 'RitualSession') -> 'CharacterCovenantRole' — Dispatched on INDUCTION fire. Unpacks the session into add_member args.`
- `is_gear_compatible(role: 'CovenantRole', archetype: 'str') -> 'bool' — Return True if a row exists in GearArchetypeCompatibility for this pair.`
- `kick_member(*, target: 'CharacterCovenantRole', actor: 'CharacterCovenantRole') -> 'None' — Remove a member by rank authority. Soft-ends the target, then`
- `leave_covenant(*, membership: 'CharacterCovenantRole') -> 'None' — A member voluntarily leaves a covenant. Soft-ends the membership, then`
- `perform_covenant_rite(*, session: 'RitualSession') -> 'CovenantRiteInstance' — Dispatched on fire of a RitualSession whose Ritual has a CovenantRite sidecar.`
- `precedence_role_for_combat(character_sheet: 'CharacterSheet') -> 'CovenantRole | None' — Pick the single covenant role that governs combat for a character.`
- `recompute_covenant_level(*, covenant: 'Covenant') -> 'int | None' — Look up the covenant's current legend total, find the max satisfied`
- `release_court_pact(*, pact: 'CourtPact') -> 'None' — Soft-release an active CourtPact by setting released_at to now.`
- `rename_rank(*, rank: 'CovenantRank', actor: 'CharacterCovenantRole', name: 'str') -> 'CovenantRank' — Rename a rank. Requires can_manage_ranks.`
- `reorder_ranks(*, covenant: 'Covenant', actor: 'CharacterCovenantRole', ordered_rank_ids: 'list[int]') -> 'list[CovenantRank]' — Rewrite tiers for the given ranks atomically and uniquely.`
- `resolve_effective_role(*, character: 'Character', role: 'CovenantRole') -> 'CovenantRole' — Return the resonance-specialized sub-role for ``role`` (one-line shim over`
- `rise_battle_covenant_via_session(*, session: 'RitualSession') -> 'Covenant' — Dispatched on a 'call the banners' rise ritual fire.`
- `set_engaged_membership(*, membership: 'CharacterCovenantRole') -> 'None' — Engage this membership; un-engage other same-type rows for the same character.`
- `set_rank_capabilities(*, rank: 'CovenantRank', actor: 'CharacterCovenantRole', can_invite: 'bool | None' = None, can_kick: 'bool | None' = None, can_manage_ranks: 'bool | None' = None) -> 'CovenantRank' — Update capability flags on a rank. Requires can_manage_ranks.`
- `stand_down_battle_covenant(*, covenant: 'Covenant') -> 'None' — Stand a STANDING battle covenant down to dormant; clear engagement.`
- `swear_court_pact(*, covenant: 'Covenant', servant_sheet: 'CharacterSheet', granted_pull_cap: 'int') -> 'CourtPact' — Create an active CourtPact binding servant_sheet to covenant.`
- `transfer_top(*, covenant: 'Covenant', actor: 'CharacterCovenantRole', new_top_membership: 'CharacterCovenantRole') -> 'None' — Transfer the top rank (tier=1) from the actor to ``new_top_membership``.`


## world.forms

### HeightBand
**Pointed to by:**
  - drafts <- character_creation.CharacterDraft

### Build
**Pointed to by:**
  - character_sheets <- character_sheets.CharacterSheet
  - drafts <- character_creation.CharacterDraft

### FormTrait
**Pointed to by:**
  - options <- forms.FormTraitOption
  - species_links <- forms.SpeciesFormTrait
  - character_values <- forms.CharacterFormValue
  - temporary_changes <- forms.TemporaryFormChange
  - persona_descriptors <- forms.PersonaTraitDescriptor
  - appearance_changes <- forms.AppearanceChangeLog

### FormTraitOption
**Foreign Keys:**
  - trait -> forms.FormTrait [FK]
**Pointed to by:**
  - species_restrictions <- forms.SpeciesFormTrait
  - character_values <- forms.CharacterFormValue
  - natural_for_values <- forms.CharacterFormValue
  - temporary_changes <- forms.TemporaryFormChange

### SpeciesFormTrait
**Foreign Keys:**
  - species -> species.Species [FK]
  - trait -> forms.FormTrait [FK]
  - allowed_options -> forms.FormTraitOption [M2M]

### CharacterForm
**Foreign Keys:**
  - character -> objects.ObjectDB [FK]
**Pointed to by:**
  - pull_effect_targets <- magic.ThreadPullEffect
  - values <- forms.CharacterFormValue
  - active_for <- forms.CharacterFormState
  - overlay_for <- forms.CharacterFormState
  - combat_profiles <- forms.FormCombatProfile
  - alternate_self_grants <- forms.AlternateSelf
  - return_for_active <- forms.ActiveAlternateSelf
  - appearance_changes <- forms.AppearanceChangeLog

### CharacterFormValue
**Foreign Keys:**
  - form -> forms.CharacterForm [FK]
  - trait -> forms.FormTrait [FK]
  - option -> forms.FormTraitOption [FK]
  - natural_option -> forms.FormTraitOption [FK] (nullable)

### CharacterFormState
**Foreign Keys:**
  - character -> objects.ObjectDB [OneToOne]
  - active_form -> forms.CharacterForm [FK] (nullable)
  - active_fake_overlay -> forms.CharacterForm [FK] (nullable)

### FormCombatProfile
**Foreign Keys:**
  - form -> forms.CharacterForm [FK]
**Pointed to by:**
  - effects <- forms.FormCombatProfileEffect
  - grants <- forms.AlternateSelf
  - modifier_sources <- mechanics.ModifierSource

### FormCombatProfileEffect
**Foreign Keys:**
  - profile -> forms.FormCombatProfile [FK]
  - target -> mechanics.ModifierTarget [FK]

### AlternateSelf
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - form -> forms.CharacterForm [FK] (nullable)
  - persona -> scenes.Persona [FK] (nullable)
  - combat_profile -> forms.FormCombatProfile [FK] (nullable)
  - techniques -> magic.Technique [M2M]
**Pointed to by:**
  - active_for <- forms.ActiveAlternateSelf

### ActiveAlternateSelf
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [OneToOne]
  - alternate_self -> forms.AlternateSelf [FK] (nullable)
  - return_form -> forms.CharacterForm [FK] (nullable)
  - return_persona -> scenes.Persona [FK] (nullable)

### TemporaryFormChange
**Foreign Keys:**
  - character -> objects.ObjectDB [FK]
  - trait -> forms.FormTrait [FK]
  - option -> forms.FormTraitOption [FK]

### PersonaTraitDescriptor
**Foreign Keys:**
  - persona -> scenes.Persona [FK]
  - trait -> forms.FormTrait [FK]

### AppearanceChangeLog
**Foreign Keys:**
  - form -> forms.CharacterForm [FK]
  - persona -> scenes.Persona [FK] (nullable)
  - trait -> forms.FormTrait [FK]
  - from_option -> forms.FormTraitOption [FK] (nullable)
  - to_option -> forms.FormTraitOption [FK] (nullable)
  - actor_persona -> scenes.Persona [FK] (nullable)

### Service Functions
- `apply_disguise(character, disguise_form: 'CharacterForm', *, kind: 'DisguiseKind' = DisguiseKind.MUNDANE) -> 'CharacterFormState' — Paint a fake overlay over the character's real form (#1110).`
- `assume_alternate_self(sheet: 'CharacterSheet', alt: 'AlternateSelf', instance_value: 'float' = 1.0) -> 'ActiveAlternateSelf' — Assume an alternate self — swap in form/persona facets, create the`
- `calculate_weight(height_inches: 'int', build: 'Build') -> 'int' — Calculate weight in pounds from height and build.`
- `change_appearance(character, trait: 'FormTrait', new_option: 'FormTraitOption', *, persona: 'Persona', descriptor: 'str | None' = None, note: 'str' = '', actor_persona: 'Persona | None' = None) -> 'CharacterFormValue' — Cosmetically edit one trait of the character's real form (hair dye, restyle).`
- `create_true_form(character, selections: 'dict[FormTrait, FormTraitOption]') -> 'CharacterForm' — Create the true form for a character during character creation.`
- `get_apparent_build(character) -> 'Build | None' — Get the apparent build for a character.`
- `get_apparent_form(character) -> 'dict[FormTrait, FormTraitOption]' — Get the apparent form for a character, combining active form with temporaries.`
- `get_apparent_height(character) -> 'tuple[int, HeightBand | None]' — Get the apparent height for a character including trait modifiers.`
- `get_cg_builds() -> 'QuerySet[Build]' — Get builds available in character creation.`
- `get_cg_form_options(species: 'Species') -> 'dict[FormTrait, list[FormTraitOption]]' — Get available form trait options for character creation.`
- `get_cg_height_bands() -> 'QuerySet[HeightBand]' — Get height bands available in character creation.`
- `get_height_band(height_inches: 'int') -> 'HeightBand | None' — Get the HeightBand for a given height in inches.`
- `get_presented_appearance(character, *, pierced: 'bool' = False) -> 'list[PresentedTrait]' — Compose what a viewer sees: the presented form's normalized traits overlaid with the`
- `remove_disguise(character) -> 'None' — Drop the active fake overlay — the real form presents again (#1110). Idempotent.`
- `reset_trait_to_natural(character, trait: 'FormTrait', *, persona: 'Persona', actor_persona: 'Persona | None' = None, note: 'str' = '') -> 'CharacterFormValue' — Restore one trait to its natural (origin) value — "wash out the dye.`
- `revert_alternate_self(sheet: 'CharacterSheet') -> 'None' — Revert the active alternate self — restore return anchors, delete the`
- `revert_to_true_form(character) -> 'None' — Revert a character to their true form.`
- `switch_form(character, target_form: 'CharacterForm') -> 'None' — Switch a character to a different form.`


## world.goals

### CharacterGoal
**Foreign Keys:**
  - character -> objects.ObjectDB [FK]
  - domain -> mechanics.ModifierTarget [FK]
**Pointed to by:**
  - instances <- goals.GoalInstance
  - applications <- goals.GoalApplication

### GoalJournal
**Foreign Keys:**
  - character -> objects.ObjectDB [FK]
  - domain -> mechanics.ModifierTarget [FK] (nullable)

### GoalRevision
**Foreign Keys:**
  - character -> objects.ObjectDB [OneToOne]

### GoalInstance
**Foreign Keys:**
  - goal -> goals.CharacterGoal [FK]

### GoalApplication
**Foreign Keys:**
  - goal -> goals.CharacterGoal [FK]

### Service Functions
- `apply_goal(goal: world.goals.models.CharacterGoal, *, context: str = '') -> int — Owner-claimed goal application (#940): spend one daily use, get the bonus.`
- `get_daily_application_budget(character: 'CharacterSheet') -> int — How many goal applications this character gets per cron day.`
- `get_goal_bonus(character: 'CharacterSheet', domain: 'ModifierTarget') -> int — Get the goal bonus for a specific domain, applying percentage modifiers.`
- `get_goal_bonuses_breakdown(character: 'CharacterSheet') -> dict[str, world.goals.types.GoalBonusBreakdown] — Get breakdown of all goal bonuses for a character.`
- `get_total_goal_points(character: 'CharacterSheet') -> int — Get the total goal points available for a character to distribute.`
- `log_goal_progress(*, character: 'ObjectDB', domain: 'ModifierTarget | None', title: str, content: str, is_public: bool = False) -> 'GoalJournal' — Create a goal-progress journal entry (records 1 XP on the row).`
- `set_character_goals(*, character: 'ObjectDB', goals: list['GoalInputData']) -> list[world.goals.models.CharacterGoal] — Replace a character's goal allocations, enforcing the weekly revision limit.`


## world.items

### QualityTier
**Pointed to by:**
  - minimum_for_templates <- items.ItemTemplate
  - item_instances <- items.ItemInstance
  - itemfacet_attachments <- items.ItemFacet
  - itemstyle_attachments <- items.ItemStyle

### InteractionType
**Pointed to by:**
  - templates <- items.ItemTemplate
  - template_bindings <- items.TemplateInteraction

### ItemTemplate
**Foreign Keys:**
  - on_use_pool -> actions.ConsequencePool [FK] (nullable)
  - on_use_check_type -> checks.CheckType [FK] (nullable)
  - minimum_quality_tier -> items.QualityTier [FK] (nullable)
  - image -> evennia_extensions.PlayerMedia [FK] (nullable)
  - weapon_damage_type -> conditions.DamageType [FK] (nullable)
  - polish_category -> buildings.PolishCategory [FK] (nullable)
  - interactions -> items.InteractionType [M2M]
**Pointed to by:**
  - ritual_requirements <- magic.RitualComponentRequirement
  - technique_grants <- magic.TechniqueGrant
  - clue_triggers <- clues.ItemClueTrigger
  - slots <- items.TemplateSlot
  - instances <- items.ItemInstance
  - interaction_bindings <- items.TemplateInteraction
  - check_modifiers <- items.ItemCheckModifier
  - garment_mitigations <- items.GarmentMitigation
  - lore_effects <- buildings.MaterialLoreEffect
  - building_uses <- buildings.BuildingMaterial

### TemplateSlot
**Foreign Keys:**
  - template -> items.ItemTemplate [FK]

### ItemInstance
**Foreign Keys:**
  - template -> items.ItemTemplate [FK]
  - game_object -> objects.ObjectDB [OneToOne] (nullable)
  - quality_tier -> items.QualityTier [FK] (nullable)
  - holder_character_sheet -> character_sheets.CharacterSheet [FK] (nullable)
  - crafter_character_sheet -> character_sheets.CharacterSheet [FK] (nullable)
  - crafter_persona_display -> scenes.Persona [FK] (nullable)
  - contained_in -> items.ItemInstance [FK] (nullable)
  - image -> evennia_extensions.PlayerMedia [FK] (nullable)
**Pointed to by:**
  - currency_instrument <- currency.CurrencyInstrumentDetails
  - contents <- items.ItemInstance
  - equipped_slots <- items.EquippedItem
  - room_placement <- items.RoomItem
  - ownership_events <- items.OwnershipEvent
  - item_facets <- items.ItemFacet
  - item_styles <- items.ItemStyle
  - stored_outfits <- items.Outfit
  - outfit_slots <- items.OutfitSlot
  - mantle <- items.Mantle
  - project_contributions <- projects.Contribution
  - building_permit_details <- buildings.BuildingPermitDetails

### TemplateInteraction
**Foreign Keys:**
  - template -> items.ItemTemplate [FK]
  - interaction_type -> items.InteractionType [FK]

### EquippedItem
**Foreign Keys:**
  - character -> objects.ObjectDB [FK]
  - item_instance -> items.ItemInstance [FK]

### RoomItem
**Foreign Keys:**
  - room -> evennia_extensions.RoomProfile [FK]
  - item_instance -> items.ItemInstance [OneToOne]

### OwnershipEvent
**Foreign Keys:**
  - item_instance -> items.ItemInstance [FK] (nullable)
  - from_character_sheet -> character_sheets.CharacterSheet [FK] (nullable)
  - to_character_sheet -> character_sheets.CharacterSheet [FK] (nullable)
  - from_persona_display -> scenes.Persona [FK] (nullable)
  - to_persona_display -> scenes.Persona [FK] (nullable)

### CurrencyBalance
**Foreign Keys:**
  - character -> objects.ObjectDB [OneToOne]

### ItemFacet
**Foreign Keys:**
  - applied_by_account -> accounts.AccountDB [FK] (nullable)
  - attachment_quality_tier -> items.QualityTier [FK]
  - item_instance -> items.ItemInstance [FK]
  - facet -> magic.Facet [FK]
**Pointed to by:**
  - resonance_grants <- magic.ResonanceGrant

### ItemStyle
**Foreign Keys:**
  - applied_by_account -> accounts.AccountDB [FK] (nullable)
  - attachment_quality_tier -> items.QualityTier [FK]
  - item_instance -> items.ItemInstance [FK]
  - style -> items.Style [FK]

### Outfit
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - wardrobe -> items.ItemInstance [FK]
**Pointed to by:**
  - slots <- items.OutfitSlot
  - presentations <- items.FashionPresentation

### OutfitSlot
**Foreign Keys:**
  - outfit -> items.Outfit [FK]
  - item_instance -> items.ItemInstance [FK]

### FashionPresentation
**Foreign Keys:**
  - event -> events.Event [FK]
  - presenter -> character_sheets.CharacterSheet [FK]
  - outfit -> items.Outfit [FK] (nullable)
  - perceiving_society -> societies.Society [FK]
**Pointed to by:**
  - endorsements <- magic.PresentationEndorsement

### FacetVogueMomentum
**Foreign Keys:**
  - society -> societies.Society [FK]
  - facet -> magic.Facet [FK]

### ItemCheckModifier
**Foreign Keys:**
  - template -> items.ItemTemplate [FK]
  - check_type -> checks.CheckType [FK]

### FashionStyle
**Foreign Keys:**
  - in_vogue_facets -> magic.Facet [M2M]
  - in_vogue_styles -> items.Style [M2M]
**Pointed to by:**
  - societies_current <- societies.Society
  - bonuses <- items.FashionStyleBonus
  - trendsetter_crownings <- items.Trendsetter

### Style
**Pointed to by:**
  - motif_usages <- magic.MotifResonanceStyle
  - item_attachments <- items.ItemStyle
  - vogue_in <- items.FashionStyle

### FashionStyleBonus
**Foreign Keys:**
  - fashion_style -> items.FashionStyle [FK]
  - target -> mechanics.ModifierTarget [FK]

### Mantle
**Foreign Keys:**
  - item_instance -> items.ItemInstance [OneToOne]
**Pointed to by:**
  - anchored_threads <- magic.Thread
  - level_defs <- items.MantleLevelDefinition
  - clearances <- items.MantleLevelClearance

### MantleLevelDefinition
**Foreign Keys:**
  - mantle -> items.Mantle [FK]
  - codex_entry_required -> codex.CodexEntry [FK]

### MantleLevelClearance
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - mantle -> items.Mantle [FK]

### Trendsetter
**Foreign Keys:**
  - society -> societies.Society [FK]
  - persona -> scenes.Persona [FK]
  - fashion_style -> items.FashionStyle [FK]

### GarmentMitigation
**Foreign Keys:**
  - item_template -> items.ItemTemplate [FK]
  - resonance -> magic.Resonance [FK] (nullable)

### CraftingRecipe
**Foreign Keys:**
  - check_type -> checks.CheckType [FK] (nullable)
  - skill_trait -> traits.Trait [FK] (nullable)
**Pointed to by:**
  - material_requirements <- items.CraftingMaterialRequirement
  - skill_caps <- items.CraftingSkillCap
  - consequence_rows <- items.CraftingRecipeConsequence

### CraftingMaterialRequirement
**Foreign Keys:**
  - recipe -> items.CraftingRecipe [FK]
  - item_template -> items.ItemTemplate [FK]
  - min_quality_tier -> items.QualityTier [FK] (nullable)

### CraftingSkillCap
**Foreign Keys:**
  - recipe -> items.CraftingRecipe [FK]
  - max_quality_tier -> items.QualityTier [FK]

### CraftingRecipeConsequence
**Foreign Keys:**
  - recipe -> items.CraftingRecipe [FK]
  - consequence -> checks.Consequence [FK]

### LabStationDetails
**Foreign Keys:**
  - feature_instance -> room_features.RoomFeatureInstance [OneToOne]

### Service Functions
- `attach_facet_to_item(*, crafter: 'AccountDB', item_instance: 'ItemInstance', facet: 'Facet', attachment_quality_tier: 'QualityTier') -> 'ItemFacet' — Attach ``facet`` to ``item_instance``.`
- `consume_item_charges(*, item_instance: 'ItemInstance', amount: 'int' = 1) -> 'ItemInstance' — Spend ``amount`` charges atomically (row-locked). Logs ACTIVATED; at 0`
- `equip_item(*, character_sheet: 'object', item_instance: 'ItemInstance', body_region: 'str', equipment_layer: 'str') -> 'EquippedItem' — Place ``item_instance`` on ``character_sheet``'s slot.`
- `get_max_cleared_mantle_level(sheet: 'CharacterSheet', mantle: 'Mantle') -> 'int' — Return the highest cleared level for (sheet, mantle), or 0 if none.`
- `grant_mantle_clearance(sheet: 'CharacterSheet', mantle: 'Mantle', level: 'int') -> 'MantleLevelClearance' — Staff override: record a clearance at ``level`` without the codex check.`
- `record_mantle_clearances(sheet: 'CharacterSheet', mantle: 'Mantle') -> 'list[MantleLevelClearance]' — Idempotently record codex-gated mantle clearances for ``sheet``.`
- `remove_facet_from_item(*, item_facet: 'ItemFacet') -> 'None' — Remove a facet attachment and invalidate wearers' handler caches.`
- `unequip_item(*, equipped_item: 'EquippedItem') -> 'None' — Remove an EquippedItem and invalidate the character's handler cache.`
- `use_item(*, item_instance: 'ItemInstance', user: 'ObjectDB', target: 'ObjectDB | None' = None) -> 'UseItemResult' — Use an item with an on-use pool: apply its effects (deterministic when the`
- `visible_worn_items_for(character: 'ObjectDB', observer: 'object | None' = None) -> 'list[VisibleWornItem]' — Return ``character``'s worn items visible to ``observer``.`


## world.locations

### LocationValueOverride
**Foreign Keys:**
  - area -> areas.Area [FK] (nullable)
  - room_profile -> evennia_extensions.RoomProfile [FK] (nullable)
  - resonance -> magic.Resonance [FK] (nullable)
  - damage_type -> conditions.DamageType [FK] (nullable)

### LocationValueModifier
**Foreign Keys:**
  - area -> areas.Area [FK] (nullable)
  - room_profile -> evennia_extensions.RoomProfile [FK] (nullable)
  - resonance -> magic.Resonance [FK] (nullable)
  - damage_type -> conditions.DamageType [FK] (nullable)

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

### Service Functions
- `ap_regen_multiplier_pct(level: 'int') -> 'int' — The AP-regen percentage adjustment for a comfort level (#1514) — 0 at neutral (5).`
- `assign_room_tenant(*, persona: 'Persona', room: 'DefaultObject', tenant_persona: 'Persona', ends_at: 'datetime | None' = None, notes: 'str' = '') -> 'LocationTenancy' — Owner-gated grant of a room tenancy (#670) — the player seam over grant_tenancy.`
- `cleanup_decayed_modifiers(now: 'datetime | None' = None) -> 'int' — Delete LocationValueModifier rows whose current_value() has`
- `climate_exposure_base(climate: 'Climate | None', stat_key: 'StatKey', *, temperature_shift: 'int' = 0) -> 'int' — A climate's contribution to one exposure axis, before local modifiers/floor (#1522).`
- `comfort_level(room: 'DefaultObject', *, comfort_offset: 'int' = 0) -> 'int' — A room's comfort level (1–10) for an occupant (#1514).`
- `comfort_level_for_points(points: 'int') -> 'int' — Map raw comfort points to a 1–10 comfort level (#1514).`
- `comfort_points(room: 'DefaultObject') -> 'int' — A room's raw comfort points (#1514): ``amenities − felt discomfort``.`
- `comfort_summary(room: 'DefaultObject') -> 'ComfortSummary' — Resolve a room's comfort readout (#1514): level, points, the biting exposures, amenity.`
- `current_temperature_shift(*, real_now: 'datetime | None' = None) -> 'int' — The current global seasonal temperature shift from the IC clock (#1522).`
- `current_tenants(room: 'DefaultObject') -> 'QuerySet[LocationTenancy]' — Return all currently-active tenancies that apply to a room.`
- `effective_owner(room: 'DefaultObject') -> 'LocationOwnership | None' — Cascade-resolve the most-specific active owner of a room.`
- `effective_owners_for_rooms(rooms: 'Iterable[DefaultObject]') -> 'dict[int, LocationOwnership | None]' — Bulk-resolve owners for many rooms in one pass.`
- `effective_stats_for_rooms(rooms: 'Iterable[DefaultObject]', stat_keys: 'Iterable[StatKey]') -> 'dict[int, dict[StatKey, int]]' — Bulk-resolve stats for many rooms in one pass.`
- `effective_value(room: 'DefaultObject', *, stat_key: 'StatKey | None' = None, resonance: 'Resonance | None' = None, damage_type: 'DamageType | None' = None) -> 'int' — Cascade-resolve a single axis value (stat, resonance, or damage-type shelter) for a room.`
- `effective_values_for_rooms(rooms: 'Iterable[DefaultObject]', *, stat_keys: 'Iterable[StatKey] | None' = None, resonances: 'Iterable[Resonance] | None' = None) -> 'dict[int, dict[StatKey | Resonance, int]]' — Bulk-resolve cascade values across many rooms for one axis.`
- `end_room_tenancy(*, persona: 'Persona', tenancy: 'LocationTenancy') -> 'LocationTenancy' — End a room tenancy (#670): the room's owner (eviction) or the tenant (departure).`
- `end_tenancy(tenancy: 'LocationTenancy', *, ended_at: 'datetime | None' = None) -> 'LocationTenancy' — End a tenancy by setting ``ends_at``.`
- `felt_exposure(room: 'DefaultObject', *, stat_key: 'StatKey') -> 'int' — A room's *felt* exposure on one axis, after enclosure sheltering (#1514, #1522).`
- `get_effective_climate(area: 'Area | None') -> 'Climate | None' — Walk up the area hierarchy to the nearest climate assignment (#1522).`
- `grant_tenancy(*, area: 'Area | None' = None, room_profile: 'RoomProfile | None' = None, tenant_persona: 'Persona | None' = None, tenant_organization: 'Organization | None' = None, ends_at: 'datetime | None' = None, notes: 'str' = '') -> 'LocationTenancy' — Create a new LocationTenancy row.`
- `hazard_is_covered(room: 'DefaultObject', damage_type: 'DamageType', *, threshold: 'int' = 1) -> 'bool' — Whether *room* grants shelter against *damage_type* (#1744).`
- `is_owner(persona: 'Persona', room: 'DefaultObject') -> 'bool' — True when ``ownership_for(persona, room)`` returns a row.`
- `is_tenant(persona: 'Persona', room: 'DefaultObject') -> 'bool' — True when ``tenancies_for(persona, room)`` has any rows.`
- `maybe_default_residence(persona: 'Persona | None', room_profile: 'RoomProfile | None') -> 'None' — Default a persona's character home to this room when it has none yet (#1514).`
- `ownership_for(persona: 'Persona', room: 'DefaultObject') -> 'LocationOwnership | None' — Return the LocationOwnership row that gives this persona standing`
- `ownership_history_for(*, area: 'Area | None' = None, room_profile: 'RoomProfile | None' = None) -> 'QuerySet[LocationOwnership]' — Return ALL LocationOwnership rows (active and ended) for a`
- `room_discomfort(room: 'DefaultObject') -> 'int' — Total residual environmental discomfort at a room (#1514, #1522).`
- `room_enclosure(room: 'DefaultObject') -> 'RoomEnclosure' — The room's enclosure level (#1514); ``WALLED`` (a normal indoor room) if no profile.`
- `room_exposure_breakdown(room: 'DefaultObject') -> 'list[AxisBreakdown]' — Per-axis pressure/mitigation/net for a room — the build-HUD's engine (#1514).`
- `set_primary_home(*, persona: 'Persona', room: 'DefaultObject') -> 'LocationTenancy' — Designate one of the persona's active room tenancies as their home (#670).`
- `set_residence(*, character: 'DefaultObject', room: 'DefaultObject') -> 'None' — Set a character's primary residence (#1514).`
- `set_room_display_data(*, room: 'DefaultObject', persona: 'Persona', name: 'str | None' = None, description: 'str | None' = None, is_public: 'bool | None' = None) -> 'None' — Owner-gated edit of a room's display name, description, and public listing.`
- `tenancies_for(persona: 'Persona', room: 'DefaultObject') -> 'QuerySet[LocationTenancy]' — Return the QuerySet of currently-active tenancies that give this`
- `tenancies_for_rooms(rooms: 'Iterable[DefaultObject]') -> 'dict[int, list[LocationTenancy]]' — Bulk-resolve currently-active tenancies for many rooms.`
- `tenancy_history_for(*, area: 'Area | None' = None, room_profile: 'RoomProfile | None' = None) -> 'QuerySet[LocationTenancy]' — Return ALL LocationTenancy rows (active and ended) for a`
- `transfer_ownership(*, area: 'Area | None' = None, room_profile: 'RoomProfile | None' = None, to_persona: 'Persona | None' = None, to_organization: 'Organization | None' = None, notes: 'str' = '', transferred_at: 'datetime | None' = None) -> 'LocationOwnership' — Atomically transfer (or claim) ownership of a location.`
- `upsert_room_resonance_modifier(room_profile: 'RoomProfile', resonance: 'Resonance', *, source: 'str', delta: 'int') -> 'LocationValueModifier' — Get-or-create the room-level (room_profile, resonance, source) cascade row and`


## world.magic

### AudereThreshold
**Foreign Keys:**
  - minimum_intensity_tier -> magic.IntensityTier [FK]
  - minimum_warp_stage -> conditions.ConditionStage [FK]

### PendingAudereOffer
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]

### AudereMajoraThreshold
**Foreign Keys:**
  - minimum_intensity_tier -> magic.IntensityTier [FK]
  - minimum_warp_stage -> conditions.ConditionStage [FK]
  - archetypes -> societies.PhilosophicalArchetype [M2M]
**Pointed to by:**
  - pending_offers <- magic.PendingAudereMajoraOffer
  - crossings <- magic.AudereMajoraCrossing

### PendingAudereMajoraOffer
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - threshold -> magic.AudereMajoraThreshold [FK]

### AudereMajoraCrossing
**Foreign Keys:**
  - scene -> scenes.Scene [FK] (nullable)
  - declaration_interaction -> scenes.Interaction [FK] (nullable)
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - threshold -> magic.AudereMajoraThreshold [FK]
  - chosen_path -> classes.Path [FK]
  - legend_entry -> societies.LegendEntry [OneToOne] (nullable)

### PendingEntryFlourishOffer
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - scene -> scenes.Scene [FK] (nullable)

### Affinity
**Pointed to by:**
  - resonances <- magic.Resonance
  - alteration_templates <- magic.MagicalAlterationTemplate
  - pending_alteration_origins <- magic.PendingAlteration
  - character_totals <- magic.CharacterAffinityTotal
  - interactions_as_source <- magic.AffinityInteraction
  - interactions_as_environment <- magic.AffinityInteraction
  - modifier_target <- mechanics.ModifierTarget

### Resonance
**Foreign Keys:**
  - affinity -> magic.Affinity [FK]
  - opposite -> magic.Resonance [OneToOne] (nullable)
  - properties -> mechanics.Property [M2M]
**Pointed to by:**
  - opposite_of <- magic.Resonance
  - gifts <- magic.Gift
  - alteration_templates <- magic.MagicalAlterationTemplate
  - corruption_twist_templates <- magic.MagicalAlterationTemplate
  - pending_alteration_origins <- magic.PendingAlteration
  - character_resonances <- magic.CharacterResonance
  - dramatic_moment_types <- magic.DramaticMomentType
  - poseendorsement_set <- magic.PoseEndorsement
  - sceneentryendorsement_set <- magic.SceneEntryEndorsement
  - stylepresentationendorsement_set <- magic.StylePresentationEndorsement
  - entry_flourish_records <- magic.EntryFlourishRecord
  - resonancegrant_set <- magic.ResonanceGrant
  - motif_resonances <- magic.MotifResonance
  - imbuing_prose <- magic.ImbuingProseTemplate
  - sanctums <- magic.SanctumDetails
  - techniquevariant_subrole <- magic.TechniqueVariant
  - signature_bonuses <- magic.SignatureMotifBonus
  - sineating_pending_offers <- magic.SineatingPendingOffer
  - pending_stage_advance_offers <- magic.PendingStageAdvanceOffer
  - sineatings <- magic.Sineating
  - rescues <- magic.SoulTetherRescue
  - pull_effects <- magic.ThreadPullEffect
  - threads <- magic.Thread
  - damage_type <- conditions.DamageType
  - corruption_condition_templates <- conditions.ConditionTemplate
  - modifier_target <- mechanics.ModifierTarget
  - cascade_overrides <- locations.LocationValueOverride
  - cascade_modifiers <- locations.LocationValueModifier
  - garment_mitigations <- items.GarmentMitigation
  - covenantrole_subrole <- covenants.CovenantRole
  - combo_slots <- combat.ComboSlot
  - combat_pulls <- combat.CombatPull
  - mission_route_rewards <- missions.MissionOptionRouteReward
  - projects <- projects.Project

### Gift
**Foreign Keys:**
  - creator -> character_sheets.CharacterSheet [FK] (nullable)
  - resonances -> magic.Resonance [M2M]
**Pointed to by:**
  - species_grants <- species.SpeciesGiftGrant
  - character_grants <- magic.CharacterGift
  - techniques <- magic.Technique
  - gift_unlocks <- magic.GiftUnlock
  - path_grants <- magic.PathGiftGrant
  - reincarnation <- magic.Reincarnation
  - technique_drafts <- magic.TechniqueDraft
  - thread_pull_effects <- magic.ThreadPullEffect
  - anchored_threads <- magic.Thread
  - thread_weaving_unlocks <- magic.ThreadWeavingUnlock

### CharacterGift
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - gift -> magic.Gift [FK]

### Tradition
**Foreign Keys:**
  - society -> societies.Society [FK] (nullable)
**Pointed to by:**
  - available_beginnings <- character_creation.Beginnings
  - beginning_traditions <- character_creation.BeginningTradition
  - character_traditions <- magic.CharacterTradition
  - ritual_grants <- magic.TraditionRitualGrant
  - codex_grants <- codex.TraditionCodexGrant

### CharacterTradition
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - tradition -> magic.Tradition [FK]

### EffectType
**Pointed to by:**
  - available_restrictions <- magic.Restriction
  - techniques <- magic.Technique
  - cantrips <- magic.Cantrip
  - technique_drafts <- magic.TechniqueDraft
  - combo_slots <- combat.ComboSlot

### TechniqueStyle
**Foreign Keys:**
  - allowed_paths -> classes.Path [M2M]
**Pointed to by:**
  - techniques <- magic.Technique
  - cantrips <- magic.Cantrip
  - technique_drafts <- magic.TechniqueDraft

### Restriction
**Foreign Keys:**
  - allowed_effect_types -> magic.EffectType [M2M]
**Pointed to by:**
  - techniques <- magic.Technique
  - technique_drafts <- magic.TechniqueDraft

### IntensityTier
**Pointed to by:**
  - auderethreshold_set <- magic.AudereThreshold

### Technique
**Foreign Keys:**
  - discovery_achievement -> achievements.Achievement [FK] (nullable)
  - gift -> magic.Gift [FK]
  - style -> magic.TechniqueStyle [FK]
  - effect_type -> magic.EffectType [FK]
  - clash_resolution_pool -> actions.ConsequencePool [FK] (nullable)
  - clash_per_round_pool -> actions.ConsequencePool [FK] (nullable)
  - source_cantrip -> magic.Cantrip [FK] (nullable)
  - creator -> character_sheets.CharacterSheet [FK] (nullable)
  - action_template -> actions.ActionTemplate [FK] (nullable)
  - target_weather_type -> weather.WeatherType [FK] (nullable)
  - restrictions -> magic.Restriction [M2M]
  - applied_conditions -> conditions.ConditionTemplate [M2M]
  - properties -> mechanics.Property [M2M]
  - target_prerequisites -> mechanics.Prerequisite [M2M]
**Pointed to by:**
  - action_enhancements <- actions.ActionEnhancement
  - capability_grants <- magic.TechniqueCapabilityGrant
  - capability_requirements <- magic.TechniqueCapabilityRequirement
  - character_grants <- magic.CharacterTechnique
  - condition_applications <- magic.TechniqueAppliedCondition
  - removed_conditions <- magic.TechniqueRemovedCondition
  - damage_profiles <- magic.TechniqueDamageProfile
  - pendingalteration_set <- magic.PendingAlteration
  - magicalalterationevent_set <- magic.MagicalAlterationEvent
  - teaching_offers <- magic.TechniqueTeachingOffer
  - granted_by_path_gifts <- magic.PathGiftGrant
  - variants <- magic.TechniqueVariant
  - grants <- magic.TechniqueGrant
  - anchored_threads <- magic.Thread
  - scene_action_requests <- scenes.SceneActionRequest
  - alternate_self_grants <- forms.AlternateSelf
  - conditions_caused <- conditions.ConditionInstance
  - battle_declarations <- battles.BattleActionDeclaration
  - battle_property_affinities <- battles.TechniquePropertyAffinity

### TechniqueCapabilityGrant
**Foreign Keys:**
  - capability -> conditions.CapabilityType [FK]
  - technique -> magic.Technique [FK]
  - prerequisite -> mechanics.Prerequisite [FK] (nullable)

### TechniqueCapabilityRequirement
**Foreign Keys:**
  - technique -> magic.Technique [FK]
  - capability -> conditions.CapabilityType [FK]

### CharacterTechnique
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - technique -> magic.Technique [FK]
  - source -> mechanics.ModifierSource [FK] (nullable)

### TechniqueOutcomeModifier
**Foreign Keys:**
  - outcome -> traits.CheckOutcome [OneToOne]

### TechniqueAppliedCondition
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK]
  - technique -> magic.Technique [FK]

### TechniqueRemovedCondition
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK]
  - technique -> magic.Technique [FK]

### TechniqueDamageProfile
**Foreign Keys:**
  - damage_type -> conditions.DamageType [FK] (nullable)
  - technique -> magic.Technique [FK]

### MagicalAlterationTemplate
**Foreign Keys:**
  - condition_template -> conditions.ConditionTemplate [OneToOne]
  - origin_affinity -> magic.Affinity [FK]
  - origin_resonance -> magic.Resonance [FK]
  - weakness_damage_type -> conditions.DamageType [FK] (nullable)
  - authored_by -> accounts.AccountDB [FK] (nullable)
  - parent_template -> magic.MagicalAlterationTemplate [FK] (nullable)
  - resonance -> magic.Resonance [FK] (nullable)
**Pointed to by:**
  - variants <- magic.MagicalAlterationTemplate
  - resolved_pending <- magic.PendingAlteration
  - application_events <- magic.MagicalAlterationEvent

### PendingAlteration
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - triggering_scene -> scenes.Scene [FK] (nullable)
  - triggering_technique -> magic.Technique [FK] (nullable)
  - origin_affinity -> magic.Affinity [FK]
  - origin_resonance -> magic.Resonance [FK]
  - resolved_alteration -> magic.MagicalAlterationTemplate [FK] (nullable)
  - resolved_by -> accounts.AccountDB [FK] (nullable)
**Pointed to by:**
  - treatment_action_requests <- scenes.SceneActionRequest
  - treatment_attempts_targeting_alteration <- conditions.TreatmentAttempt

### MagicalAlterationEvent
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - alteration_template -> magic.MagicalAlterationTemplate [FK]
  - active_condition -> conditions.ConditionInstance [FK] (nullable)
  - triggering_scene -> scenes.Scene [FK] (nullable)
  - triggering_technique -> magic.Technique [FK] (nullable)

### CharacterAnima
**Foreign Keys:**
  - character -> objects.ObjectDB [OneToOne]

### AnimaRitualPerformance
**Foreign Keys:**
  - ritual -> magic.Ritual [FK]
  - target_character -> character_sheets.CharacterSheet [FK] (nullable)
  - scene -> scenes.Scene [FK] (nullable)
  - outcome -> traits.CheckOutcome [FK] (nullable)

### AnimaConfig

### CharacterAura
**Foreign Keys:**
  - character -> objects.ObjectDB [OneToOne]

### CharacterResonance
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - resonance -> magic.Resonance [FK]

### CharacterAffinityTotal
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - affinity -> magic.Affinity [FK]

### AuraAffinityThreshold
**Foreign Keys:**
  - discovery_achievement -> achievements.Achievement [FK] (nullable)

### Cantrip
**Foreign Keys:**
  - effect_type -> magic.EffectType [FK]
  - style -> magic.TechniqueStyle [FK]
  - allowed_facets -> magic.Facet [M2M]
**Pointed to by:**
  - created_techniques <- magic.Technique

### CorruptionConfig
**Foreign Keys:**
  - updated_by -> accounts.AccountDB [FK] (nullable)

### DramaticMomentType
**Foreign Keys:**
  - resonance -> magic.Resonance [FK]
  - archetypes -> societies.PhilosophicalArchetype [M2M]
**Pointed to by:**
  - tags <- magic.DramaticMomentTag

### DramaticMomentTag
**Foreign Keys:**
  - moment_type -> magic.DramaticMomentType [FK]
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - scene -> scenes.Scene [FK] (nullable)
  - tagged_by -> accounts.AccountDB [FK]
  - interaction -> scenes.Interaction [FK] (nullable)
**Pointed to by:**
  - resonance_grants <- magic.ResonanceGrant

### PoseEndorsement
**Foreign Keys:**
  - endorser_sheet -> character_sheets.CharacterSheet [FK]
  - endorsee_sheet -> character_sheets.CharacterSheet [FK]
  - persona_snapshot -> scenes.Persona [FK] (nullable)
  - interaction -> scenes.Interaction [FK]
  - resonance -> magic.Resonance [FK]
**Pointed to by:**
  - resonance_grants <- magic.ResonanceGrant

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

### PresentationEndorsement
**Foreign Keys:**
  - endorser_sheet -> character_sheets.CharacterSheet [FK]
  - endorsee_sheet -> character_sheets.CharacterSheet [FK]
  - persona_snapshot -> scenes.Persona [FK] (nullable)
  - presentation -> items.FashionPresentation [FK]

### StylePresentationEndorsement
**Foreign Keys:**
  - endorser_sheet -> character_sheets.CharacterSheet [FK]
  - endorsee_sheet -> character_sheets.CharacterSheet [FK]
  - persona_snapshot -> scenes.Persona [FK] (nullable)
  - scene -> scenes.Scene [FK]
  - resonance -> magic.Resonance [FK]
**Pointed to by:**
  - resonance_grants <- magic.ResonanceGrant

### EntryFlourishRecord
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - resonance -> magic.Resonance [FK]
  - scene -> scenes.Scene [FK] (nullable)
**Pointed to by:**
  - resonance_grants <- magic.ResonanceGrant

### FuryTier

### FuryConfig

### ResonanceGainConfig
**Foreign Keys:**
  - updated_by -> accounts.AccountDB [FK] (nullable)

### GiftUnlock
**Foreign Keys:**
  - gift -> magic.Gift [FK]
  - paths -> classes.Path [M2M]
**Pointed to by:**
  - character_purchases <- magic.CharacterGiftUnlock

### CharacterGiftUnlock
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - unlock -> magic.GiftUnlock [FK]
  - teacher -> roster.RosterTenure [FK] (nullable)

### TechniqueTeachingOffer
**Foreign Keys:**
  - teacher -> roster.RosterTenure [FK]
  - technique -> magic.Technique [FK]

### GiftAcquisitionConfig

### ResonanceGrant
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - resonance -> magic.Resonance [FK]
  - source_room_profile -> evennia_extensions.RoomProfile [FK] (nullable)
  - source_staff_account -> accounts.AccountDB [FK] (nullable)
  - source_pose_endorsement -> magic.PoseEndorsement [FK] (nullable)
  - source_scene_entry_endorsement -> magic.SceneEntryEndorsement [FK] (nullable)
  - outfit_item_facet -> items.ItemFacet [FK] (nullable)
  - source_sanctum_details -> magic.SanctumDetails [FK] (nullable)
  - source_project -> projects.Project [FK] (nullable)
  - source_entry_flourish -> magic.EntryFlourishRecord [FK] (nullable)
  - source_dramatic_moment -> magic.DramaticMomentTag [FK] (nullable)
  - source_style_presentation_endorsement -> magic.StylePresentationEndorsement [FK] (nullable)
  - source_mission_deed_reward_line -> missions.MissionDeedRewardLine [FK] (nullable)

### BeginningsRitualGrant
**Foreign Keys:**
  - beginnings -> character_creation.Beginnings [FK]
  - ritual -> magic.Ritual [FK]

### PathRitualGrant
**Foreign Keys:**
  - path -> classes.Path [FK]
  - ritual -> magic.Ritual [FK]

### PathGiftGrant
**Foreign Keys:**
  - path -> classes.Path [FK]
  - gift -> magic.Gift [FK]
  - starter_techniques -> magic.Technique [M2M]

### DistinctionRitualGrant
**Foreign Keys:**
  - distinction -> distinctions.Distinction [FK]
  - ritual -> magic.Ritual [FK]

### TraditionRitualGrant
**Foreign Keys:**
  - tradition -> magic.Tradition [FK]
  - ritual -> magic.Ritual [FK]

### CodexEntryRitualGrant
**Foreign Keys:**
  - codex_entry -> codex.CodexEntry [FK]
  - ritual -> magic.Ritual [FK]

### CharacterRitualKnowledge
**Foreign Keys:**
  - roster_entry -> roster.RosterEntry [FK]
  - ritual -> magic.Ritual [FK]
  - learned_from -> roster.RosterTenure [FK] (nullable)

### RitualLiturgy
**Foreign Keys:**
  - ritual -> magic.Ritual [OneToOne]

### Facet
**Foreign Keys:**
  - parent -> magic.Facet [FK] (nullable)
**Pointed to by:**
  - cantrips <- magic.Cantrip
  - children <- magic.Facet
  - motif_usages <- magic.MotifResonanceAssociation
  - signature_bonuses <- magic.SignatureMotifBonus
  - anchored_threads <- magic.Thread
  - item_attachments <- items.ItemFacet
  - vogue_momentum <- items.FacetVogueMomentum
  - fashion_styles <- items.FashionStyle

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

### LevelPowerConfig

### AuraPowerConfig

### StandingCapBand

### MagicProgressionMilestone
**Foreign Keys:**
  - codex_entry -> codex.CodexEntry [FK] (nullable)

### Reincarnation
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - gift -> magic.Gift [OneToOne]

### AffinityInteraction
**Foreign Keys:**
  - source_affinity -> magic.Affinity [FK]
  - environment_affinity -> magic.Affinity [FK]
  - consequence_pool -> actions.ConsequencePool [FK] (nullable)
**Pointed to by:**
  - alignment_boon_tiers <- magic.ResonanceAlignmentBoonTier

### ResonanceEnvironmentConfig
**Foreign Keys:**
  - updated_by -> accounts.AccountDB [FK] (nullable)

### ResonanceAlignmentBoonTier
**Foreign Keys:**
  - affinity_interaction -> magic.AffinityInteraction [FK]
  - condition_template -> conditions.ConditionTemplate [FK]

### RitualCheckConfig
**Foreign Keys:**
  - ritual -> magic.Ritual [OneToOne]
  - stat -> traits.Trait [FK]
  - skill -> skills.Skill [FK]
  - specialization -> skills.Specialization [FK] (nullable)
  - resonance -> magic.Resonance [FK] (nullable)
  - check_type -> checks.CheckType [FK] (nullable)

### ImbuingProseTemplate
**Foreign Keys:**
  - resonance -> magic.Resonance [FK] (nullable)

### Ritual
**Foreign Keys:**
  - flow -> flows.FlowDefinition [FK] (nullable)
  - author_account -> accounts.AccountDB [FK] (nullable)
  - site_property -> mechanics.Property [FK] (nullable)
**Pointed to by:**
  - class_level_advancements <- progression.ClassLevelAdvancement
  - performances <- magic.AnimaRitualPerformance
  - known_by_records <- magic.CharacterRitualKnowledge
  - liturgy <- magic.RitualLiturgy
  - check_config <- magic.RitualCheckConfig
  - requirements <- magic.RitualComponentRequirement
  - pending_effects <- magic.PendingRitualEffect
  - ritualsession_set <- magic.RitualSession
  - technique_grants <- magic.TechniqueGrant
  - capstone_events <- relationships.RelationshipCapstone
  - covenant_rite <- covenants.CovenantRite
  - installs_room_features <- room_features.RoomFeatureKindInstallRitual

### RitualComponentRequirement
**Foreign Keys:**
  - ritual -> magic.Ritual [FK]
  - item_template -> items.ItemTemplate [FK]
  - min_quality_tier -> items.QualityTier [FK] (nullable)

### PendingRitualEffect
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - ritual -> magic.Ritual [FK]

### SanctumDetails
**Foreign Keys:**
  - feature_instance -> room_features.RoomFeatureInstance [OneToOne]
  - resonance_type -> magic.Resonance [FK]
  - founder_character_sheet -> character_sheets.CharacterSheet [FK] (nullable)
**Pointed to by:**
  - resonance_grants <- magic.ResonanceGrant
  - pending_payouts <- magic.SanctumPendingPayout
  - anchored_threads <- magic.Thread

### SanctumPendingPayout
**Foreign Keys:**
  - sanctum -> magic.SanctumDetails [FK]
  - weaver_character_sheet -> character_sheets.CharacterSheet [FK]

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

### TechniqueVariantCapabilityGrant
**Foreign Keys:**
  - capability -> conditions.CapabilityType [FK]
  - variant -> magic.TechniqueVariant [FK]
  - prerequisite -> mechanics.Prerequisite [FK] (nullable)

### TechniqueVariantDamageProfile
**Foreign Keys:**
  - damage_type -> conditions.DamageType [FK] (nullable)
  - variant -> magic.TechniqueVariant [FK]

### TechniqueVariantAppliedCondition
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK]
  - variant -> magic.TechniqueVariant [FK]

### RitualSession
**Foreign Keys:**
  - ritual -> magic.Ritual [FK]
  - initiator -> character_sheets.CharacterSheet [FK]
**Pointed to by:**
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

### SignatureMotifBonus
**Foreign Keys:**
  - required_facet -> magic.Facet [FK] (nullable)
  - required_resonance -> magic.Resonance [FK] (nullable)
**Pointed to by:**
  - capability_grants <- magic.SignatureMotifBonusCapabilityGrant
  - damage_profiles <- magic.SignatureMotifBonusDamageProfile
  - condition_applications <- magic.SignatureMotifBonusAppliedCondition

### SignatureMotifBonusCapabilityGrant
**Foreign Keys:**
  - capability -> conditions.CapabilityType [FK]
  - signature_bonus -> magic.SignatureMotifBonus [FK]

### SignatureMotifBonusDamageProfile
**Foreign Keys:**
  - damage_type -> conditions.DamageType [FK] (nullable)
  - signature_bonus -> magic.SignatureMotifBonus [FK]

### SignatureMotifBonusAppliedCondition
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK]
  - signature_bonus -> magic.SignatureMotifBonus [FK]

### SineatingPendingOffer
**Foreign Keys:**
  - sinner_sheet -> character_sheets.CharacterSheet [FK]
  - sineater_sheet -> character_sheets.CharacterSheet [FK]
  - relationship -> relationships.CharacterRelationship [FK]
  - scene -> scenes.Scene [FK]
  - resonance -> magic.Resonance [FK]

### PendingStageAdvanceOffer
**Foreign Keys:**
  - sinner_sheet -> character_sheets.CharacterSheet [FK]
  - sineater_sheet -> character_sheets.CharacterSheet [FK]
  - relationship -> relationships.CharacterRelationship [FK]
  - scene -> scenes.Scene [FK]
  - resonance -> magic.Resonance [FK]

### Sineating
**Foreign Keys:**
  - sinner_sheet -> character_sheets.CharacterSheet [FK]
  - sineater_sheet -> character_sheets.CharacterSheet [FK]
  - relationship -> relationships.CharacterRelationship [FK]
  - scene -> scenes.Scene [FK] (nullable)
  - resonance -> magic.Resonance [FK]

### SoulTetherRescue
**Foreign Keys:**
  - sinner_sheet -> character_sheets.CharacterSheet [FK]
  - sineater_sheet -> character_sheets.CharacterSheet [FK]
  - relationship -> relationships.CharacterRelationship [FK]
  - scene -> scenes.Scene [FK] (nullable)
  - resonance -> magic.Resonance [FK]
  - check_outcome -> traits.CheckOutcome [FK]

### SoulTetherConfig
**Foreign Keys:**
  - updated_by -> accounts.AccountDB [FK] (nullable)

### SoulfrayConfig
**Foreign Keys:**
  - resilience_check_type -> checks.CheckType [FK]

### MishapPoolTier
**Foreign Keys:**
  - consequence_pool -> actions.ConsequencePool [FK]

### TechniqueBudgetConfig

### TechniqueTierBudget

### TechniqueDraft
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [OneToOne]
  - gift -> magic.Gift [FK] (nullable)
  - style -> magic.TechniqueStyle [FK] (nullable)
  - effect_type -> magic.EffectType [FK] (nullable)
  - consequence_pool -> actions.ConsequencePool [FK] (nullable)
  - restrictions -> magic.Restriction [M2M]
**Pointed to by:**
  - capability_grants <- magic.TechniqueDraftCapabilityGrant
  - damage_profiles <- magic.TechniqueDraftDamageProfile
  - applied_conditions <- magic.TechniqueDraftAppliedCondition
  - removed_conditions <- magic.TechniqueDraftRemovedCondition

### TechniqueDraftCapabilityGrant
**Foreign Keys:**
  - capability -> conditions.CapabilityType [FK]
  - draft -> magic.TechniqueDraft [FK]

### TechniqueDraftDamageProfile
**Foreign Keys:**
  - damage_type -> conditions.DamageType [FK] (nullable)
  - draft -> magic.TechniqueDraft [FK]

### TechniqueDraftAppliedCondition
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK]
  - draft -> magic.TechniqueDraft [FK]

### TechniqueDraftRemovedCondition
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK]
  - draft -> magic.TechniqueDraft [FK]

### TechniqueGrant
**Foreign Keys:**
  - technique -> magic.Technique [FK]
  - item_template -> items.ItemTemplate [FK] (nullable)
  - ritual -> magic.Ritual [FK] (nullable)

### ThreadPullCost

### ThreadXPLockedLevel

### ThreadPullEffect
**Foreign Keys:**
  - resonance -> magic.Resonance [FK]
  - capability_grant -> conditions.CapabilityType [FK] (nullable)
  - target_form -> forms.CharacterForm [FK] (nullable)
  - resistance_damage_type -> conditions.DamageType [FK] (nullable)
  - target_gift -> magic.Gift [FK] (nullable)

### ThreadSurvivabilityTuning

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
  - signature_bonus -> magic.SignatureMotifBonus [FK] (nullable)
**Pointed to by:**
  - level_unlocks <- magic.ThreadLevelUnlock
  - treatment_action_requests <- scenes.SceneActionRequest
  - cast_pull_declarations <- scenes.SceneCastPullDeclaration
  - treatment_attempts <- conditions.TreatmentAttempt
  - related_journal_entries <- journals.JournalEntry
  - combat_pulls <- combat.CombatPull
  - resolved_pull_effects <- combat.CombatPullResolvedEffect

### ThreadLevelUnlock
**Foreign Keys:**
  - thread -> magic.Thread [FK]

### ThreadWeavingUnlock
**Foreign Keys:**
  - unlock_trait -> traits.Trait [FK] (nullable)
  - unlock_gift -> magic.Gift [FK] (nullable)
  - unlock_track -> relationships.RelationshipTrack [FK] (nullable)
  - paths -> classes.Path [M2M]
**Pointed to by:**
  - character_purchases <- magic.CharacterThreadWeavingUnlock
  - teaching_offers <- magic.ThreadWeavingTeachingOffer

### CharacterThreadWeavingUnlock
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - unlock -> magic.ThreadWeavingUnlock [FK]
  - teacher -> roster.RosterTenure [FK] (nullable)

### ThreadWeavingTeachingOffer
**Foreign Keys:**
  - teacher -> roster.RosterTenure [FK]
  - unlock -> magic.ThreadWeavingUnlock [FK]

### Service Functions
- `accept_thread_weaving_unlock(learner: 'CharacterSheet', offer: 'ThreadWeavingTeachingOffer') -> 'CharacterThreadWeavingUnlock' — Accept a ThreadWeavingTeachingOffer on behalf of a learner (Spec A §6.1).`
- `apply_damage_reduction_from_threads(character: 'ObjectDB', incoming_damage: 'int') -> 'int' — Reduce incoming damage by thread-derived DAMAGE_TAKEN_REDUCTION.`
- `calculate_affinity_breakdown(resonances: 'QuerySet[ResonanceModel]') -> 'dict[str, int]' — Derive affinity counts from a set of resonances.`
- `calculate_effective_anima_cost(*, base_cost: 'int', runtime_intensity: 'int', runtime_control: 'int', current_anima: 'int', strain_commitment: 'int' = 0, lethal: 'bool' = True) -> 'AnimaCostResult' — Calculate effective anima cost using the delta formula.`
- `calculate_soulfray_severity(current_anima: 'int', max_anima: 'int', deficit: 'int', config: 'SoulfrayConfig', *, lethal: 'bool' = True) -> 'int' — Compute Soulfray severity contribution from post-deduction anima state.`
- `compute_anchor_cap(thread: 'Thread') -> 'int' — Return the anchor-side cap for this thread (Spec A §2.4).`
- `compute_effective_cap(thread: 'Thread') -> 'int' — Return min(path cap, anchor cap) — the binding limit on this thread (Spec A §2.4).`
- `compute_path_cap(character_sheet: 'CharacterSheet') -> 'int' — Return the path-side cap for a character (Spec A §2.4).`
- `compute_thread_weaving_xp_cost(unlock: 'ThreadWeavingUnlock', learner: 'CharacterSheet') -> 'int' — Compute the XP cost for a learner to acquire a ThreadWeavingUnlock (Spec A §6.2).`
- `create_pending_alteration(*, character: 'CharacterSheet', tier: 'int', origin_affinity: 'Affinity', origin_resonance: 'ResonanceModel', scene: 'Scene | None', triggering_technique: 'Technique | None' = None, triggering_intensity: 'int | None' = None, triggering_control: 'int | None' = None, triggering_anima_cost: 'int | None' = None, triggering_anima_deficit: 'int | None' = None, triggering_soulfray_stage: 'int | None' = None, audere_active: 'bool' = False) -> 'PendingAlterationResult' — Create or escalate a PendingAlteration for a character.`
- `cross_thread_xp_lock(character_sheet: 'CharacterSheet', thread: 'Thread', boundary_level: 'int') -> 'ThreadLevelUnlock' — Pay XP to unlock an XP-locked level boundary on a thread.`
- `deduct_anima(character: 'ObjectDB', effective_cost: 'int', *, lethal: 'bool' = True) -> 'int' — Deduct anima from character, returning the overburn deficit.`
- `get_aura_percentages(character_sheet: 'CharacterSheet') -> 'AuraPercentages' — Calculate aura percentages from affinity totals and resonance-targeting modifiers.`
- `get_character_anima_ritual(character) — The character's authored SCENE_ACTION ritual (with check_config), or None.`
- `get_character_cast_check(character) — The CheckType a character's technique casts roll, or None for fallback.`
- `get_imbue_cost_multiplier(target_kind: 'str | None') -> 'int' — Resolve the imbue dp cost multiplier for a thread kind (ADR-0051).`
- `get_library_entries(*, tier: 'int', character_affinity_id: 'int | None' = None) -> 'QuerySet[MagicalAlterationTemplate]' — Return library entries matching the given tier.`
- `get_pull_cost(tier: 'int', target_kind: 'str | None') -> 'ThreadPullCost' — Resolve the pull cost row for (tier, target_kind).`
- `get_runtime_technique_stats(technique: 'Technique', character: 'ObjectDB | None', *, apply_variant: 'bool' = True) -> 'RuntimeTechniqueStats' — Calculate runtime intensity and control for a technique.`
- `get_soulfray_warning(character: 'ObjectDB') -> 'SoulfrayWarning | None' — Return the current Soulfray stage warning for the safety checkpoint.`
- `get_thread_survivability_tuning(vital_target: 'str') -> "'ThreadSurvivabilityTuning | None'" — Return the tuning row for a target, or None if unseeded (baseline 0).`
- `gift_thread_resistance(character: 'ObjectDB', damage_type: 'DamageType') -> 'int' — Total damage-type-specific resistance from gift threads (#1580).`
- `grant_resonance(character_sheet: 'CharacterSheet', resonance: 'ResonanceModel', amount: 'int', *, source: 'str', pose_endorsement: 'PoseEndorsement | None' = None, scene_entry_endorsement: 'SceneEntryEndorsement | None' = None, room_profile: 'RoomProfile | None' = None, staff_account: 'AccountDB | None' = None, outfit_item_facet: 'ItemFacet | None' = None, sanctum_details: 'SanctumDetails | None' = None, project: 'Project | None' = None, entry_flourish: 'EntryFlourishRecord | None' = None, dramatic_moment: 'DramaticMomentTag | None' = None, style_presentation_endorsement: 'StylePresentationEndorsement | None' = None, mission_deed_reward_line: 'MissionDeedRewardLine | None' = None) -> 'CharacterResonance' — Atomically grant resonance AND write the ResonanceGrant ledger row.`
- `has_pending_alterations(character: 'CharacterSheet') -> 'bool' — Check if this character has any unresolved Mage Scars.`
- `imbue_ready_threads(character_sheet: 'CharacterSheet') -> 'list[Thread]' — Return threads that have matching CharacterResonance balance > 0 and level < cap.`
- `near_xp_lock_threads(character_sheet: 'CharacterSheet', within: 'int' = 100) -> 'list[ThreadXPLockProspect]' — Return threads whose dev_points are within `within` of the next XP-locked boundary.`
- `preview_resonance_pull(character_sheet: 'CharacterSheet', resonance: 'ResonanceModel', tier: 'int', threads: 'list[Thread]', *, combat_encounter: 'CombatEncounter | None' = None) -> 'PullPreviewResult' — Read-only preview of a resonance pull (Spec A §5.6).`
- `provision_player_anima_ritual(account: 'AccountDB', character_sheet: 'CharacterSheet', roster_entry: 'RosterEntry', *, ritual_name: 'str') -> 'Ritual | None' — Create a SCENE_ACTION Ritual + sidecar + CharacterRitualKnowledge for a player.`
- `recompute_max_health_with_threads(character_sheet: 'CharacterSheet') -> 'int' — Recompute max_health folding in thread-derived VITAL_BONUS addends.`
- `reconcile_ritual_knowledge(roster_entry: 'RosterEntry') -> None — Ensure CharacterRitualKnowledge rows exist for all granted rituals.`
- `resolve_pending_alteration(*, pending: 'PendingAlteration', name: 'str', player_description: 'str', observer_description: 'str', weakness_damage_type: 'DamageType | None' = None, weakness_magnitude: 'int' = 0, resonance_bonus_magnitude: 'int' = 0, social_reactivity_magnitude: 'int' = 0, is_visible_at_rest: 'bool', resolved_by: 'AccountDB | None', parent_template: 'MagicalAlterationTemplate | None' = None, is_library_entry: 'bool' = False, library_template: 'MagicalAlterationTemplate | None' = None) -> 'AlterationResolutionResult' — Resolve a PendingAlteration by creating or selecting a template.`
- `resolve_pull_effects(threads: 'list[Thread]', tier: 'int', *, in_combat: 'bool') -> 'list[ResolvedPullEffect]' — Resolve every (thread × effect_tier 0..tier) pair into ResolvedPullEffect rows.`
- `seed_thread_survivability_tuning() -> 'None' — Idempotently author the default ThreadSurvivabilityTuning rows (#1175).`
- `select_mishap_pool(control_deficit: 'int') -> 'ConsequencePool | None' — Select a control mishap consequence pool based on deficit magnitude.`
- `spend_resonance_for_imbuing(character_sheet: 'CharacterSheet', thread: 'Thread', amount: 'int') -> 'ThreadImbueResult' — Deduct resonance balance and greedily advance thread level.`
- `spend_resonance_for_pull(character_sheet: 'CharacterSheet', resonance: 'ResonanceModel', tier: 'int', threads: 'list[Thread]', action_context: 'PullActionContext') -> 'ResonancePullResult' — Atomic pull commit (Spec A §5.4 + §7.4).`
- `staff_clear_alteration(*, pending: 'PendingAlteration', staff_account: 'AccountDB | None', notes: 'str' = '') -> 'None' — Clear a PendingAlteration without resolving it. Staff escape hatch.`
- `survivability_baseline(character: 'ObjectDB', vital_target: 'str') -> 'int' — Universal soft-capped survivability baseline from thread investment (#1175),`
- `survivability_save_baselines(character: 'ObjectDB') -> 'ThreadSurvivabilitySaves' — Per-tier survivability save modifiers from thread investment (#1250).`
- `threads_blocked_by_cap(character_sheet: 'CharacterSheet') -> 'list[Thread]' — Return threads that are at their effective cap (no further imbuing helps).`
- `update_thread_narrative(thread: 'Thread', *, name: 'str | None' = None, description: 'str | None' = None) -> 'Thread' — Update the narrative name and/or description of a thread.`
- `use_technique(*, character: 'ObjectDB', technique: 'Technique', resolve_fn: 'Callable[..., Any]', confirm_soulfray_risk: 'bool' = True, check_result: 'CheckResult | None' = None, targets: 'list | None' = None, strain_commitment: 'int' = 0, applicable_threads: 'Sequence[ApplicableThread] | None' = None, cast_pull: 'CastPullDeclaration | None' = None, power_intensity_bonus: 'int' = 0, lethal: 'bool' = True, control_penalty: 'int' = 0, apply_variant: 'bool' = True) -> 'TechniqueUseResult' — Orchestrate technique use: cost -> checkpoint -> resolve -> soulfray -> mishap.`
- `validate_alteration_resolution(*, pending_tier: 'int', pending_affinity_id: 'int', pending_resonance_id: 'int', payload: 'dict', is_staff: 'bool', character_sheet: 'CharacterSheet | None' = None) -> 'list[str]' — Validate a resolution payload against the pending's tier and origin.`
- `weave_thread(character_sheet: 'CharacterSheet', target_kind: 'str', target: 'object', resonance: 'ResonanceModel', *, name: 'str' = '', description: 'str' = '') -> 'Thread' — Create a new Thread anchored to the given target.`


## world.mechanics

### ModifierCategory
**Pointed to by:**
  - targets <- mechanics.ModifierTarget

### ModifierTarget
**Foreign Keys:**
  - category -> mechanics.ModifierCategory [FK]
  - target_trait -> traits.Trait [FK] (nullable)
  - target_affinity -> magic.Affinity [OneToOne] (nullable)
  - target_resonance -> magic.Resonance [OneToOne] (nullable)
  - target_capability -> conditions.CapabilityType [OneToOne] (nullable)
  - target_check_type -> checks.CheckType [OneToOne] (nullable)
  - target_damage_type -> conditions.DamageType [OneToOne] (nullable)
**Pointed to by:**
  - form_effects <- forms.FormCombatProfileEffect
  - distinction_effects <- distinctions.DistinctionEffect
  - character_goals <- goals.CharacterGoal
  - goal_journals <- goals.GoalJournal
  - codex_entry <- codex.CodexEntry
  - conditionmodifiereffect_set <- conditions.ConditionModifierEffect
  - character_modifiers <- mechanics.CharacterModifier
  - gated_by_conditions <- relationships.RelationshipCondition
  - reward_definitions <- achievements.RewardDefinition
  - fashion_style_bonuses <- items.FashionStyleBonus
  - covenant_level_bonuses <- covenants.CovenantLevelBonus
  - covenant_role_bonuses <- covenants.CovenantRoleBonus

### ModifierSource
**Foreign Keys:**
  - distinction_effect -> distinctions.DistinctionEffect [FK] (nullable)
  - character_distinction -> distinctions.CharacterDistinction [FK] (nullable)
  - form_combat_profile -> forms.FormCombatProfile [FK] (nullable)
**Pointed to by:**
  - granted_techniques <- magic.CharacterTechnique
  - modifiers <- mechanics.CharacterModifier

### CharacterModifier
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - target -> mechanics.ModifierTarget [FK]
  - source -> mechanics.ModifierSource [FK]

### Prerequisite
**Foreign Keys:**
  - property -> mechanics.Property [FK]
**Pointed to by:**
  - gated_techniques <- magic.Technique
  - technique_grants <- magic.TechniqueCapabilityGrant
  - technique_variant_grants <- magic.TechniqueVariantCapabilityGrant
  - capability_types <- conditions.CapabilityType

### PropertyCategory
**Pointed to by:**
  - properties <- mechanics.Property

### Property
**Foreign Keys:**
  - category -> mechanics.PropertyCategory [FK]
**Pointed to by:**
  - resonances <- magic.Resonance
  - techniques <- magic.Technique
  - ritual_sites <- magic.Ritual
  - personas <- scenes.Persona
  - condition_templates <- conditions.ConditionTemplate
  - condition_stages_carrying <- conditions.ConditionStage
  - prerequisites <- mechanics.Prerequisite
  - challenge_template_properties <- mechanics.ChallengeTemplateProperty
  - object_properties <- mechanics.ObjectProperty
  - damage_modifiers <- mechanics.PropertyDamageModifier
  - applications <- mechanics.Application
  - required_by_applications <- mechanics.Application
  - challenge_templates <- mechanics.ChallengeTemplate
  - required_by_approaches <- mechanics.ChallengeApproach
  - context_consequence_pools <- mechanics.ContextConsequencePool
  - consequence_effects <- checks.ConsequenceEffect
  - threat_pool_entries <- combat.ThreatPoolEntry
  - battle_units <- battles.BattleUnit
  - battle_technique_affinities <- battles.TechniquePropertyAffinity
  - battle_terrain_effects <- battles.TerrainPropertyEffect
  - battle_weather_effects <- battles.WeatherTypePropertyEffect

### ChallengeTemplateProperty
**Foreign Keys:**
  - challenge_template -> mechanics.ChallengeTemplate [FK]
  - property -> mechanics.Property [FK]

### ObjectProperty
**Foreign Keys:**
  - object -> objects.ObjectDB [FK]
  - property -> mechanics.Property [FK]
  - source_condition -> conditions.ConditionInstance [FK] (nullable)
  - source_challenge -> mechanics.ChallengeInstance [FK] (nullable)

### PropertyDamageModifier
**Foreign Keys:**
  - property -> mechanics.Property [FK]
  - damage_type -> conditions.DamageType [FK] (nullable)

### Application
**Foreign Keys:**
  - capability -> conditions.CapabilityType [FK]
  - target_property -> mechanics.Property [FK]
  - required_effect_property -> mechanics.Property [FK] (nullable)
**Pointed to by:**
  - challenge_approaches <- mechanics.ChallengeApproach

### TraitCapabilityDerivation
**Foreign Keys:**
  - trait -> traits.Trait [FK]
  - capability -> conditions.CapabilityType [FK]

### ChallengeCategory
**Pointed to by:**
  - challenge_templates <- mechanics.ChallengeTemplate
  - situation_templates <- mechanics.SituationTemplate

### ChallengeTemplate
**Foreign Keys:**
  - category -> mechanics.ChallengeCategory [FK]
  - blocked_capability -> conditions.CapabilityType [FK] (nullable)
  - properties -> mechanics.Property [M2M]
  - consequences -> checks.Consequence [M2M]
**Pointed to by:**
  - challenge_template_properties <- mechanics.ChallengeTemplateProperty
  - challenge_consequences <- mechanics.ChallengeTemplateConsequence
  - approaches <- mechanics.ChallengeApproach
  - situation_templates <- mechanics.SituationTemplate
  - situation_links <- mechanics.SituationChallengeLink
  - instances <- mechanics.ChallengeInstance

### ChallengeTemplateConsequence
**Foreign Keys:**
  - challenge_template -> mechanics.ChallengeTemplate [FK]
  - consequence -> checks.Consequence [FK]

### ChallengeApproach
**Foreign Keys:**
  - challenge_template -> mechanics.ChallengeTemplate [FK]
  - application -> mechanics.Application [FK]
  - check_type -> checks.CheckType [FK]
  - required_effect_property -> mechanics.Property [FK] (nullable)
  - action_template -> actions.ActionTemplate [FK] (nullable)
**Pointed to by:**
  - scene_declarations <- scenes.SceneActionDeclaration
  - consequences <- mechanics.ApproachConsequence
  - character_records <- mechanics.CharacterChallengeRecord
  - combat_declarations <- combat.RoundChallengeDeclaration

### ApproachConsequence
**Foreign Keys:**
  - approach -> mechanics.ChallengeApproach [FK]
  - consequence -> checks.Consequence [FK]

### SituationTemplate
**Foreign Keys:**
  - category -> mechanics.ChallengeCategory [FK]
  - challenges -> mechanics.ChallengeTemplate [M2M]
**Pointed to by:**
  - challenge_links <- mechanics.SituationChallengeLink
  - instances <- mechanics.SituationInstance

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
  - location -> objects.ObjectDB [FK]
  - created_by -> accounts.AccountDB [FK] (nullable)
  - scene -> scenes.Scene [FK] (nullable)
**Pointed to by:**
  - challenge_instances <- mechanics.ChallengeInstance

### ChallengeInstance
**Foreign Keys:**
  - situation_instance -> mechanics.SituationInstance [FK] (nullable)
  - template -> mechanics.ChallengeTemplate [FK]
  - location -> objects.ObjectDB [FK]
  - target_object -> objects.ObjectDB [FK]
**Pointed to by:**
  - scene_declarations <- scenes.SceneActionDeclaration
  - granted_properties <- mechanics.ObjectProperty
  - character_records <- mechanics.CharacterChallengeRecord
  - gated_position_edges <- areas.PositionEdge
  - combat_declarations <- combat.RoundChallengeDeclaration

### CharacterChallengeRecord
**Foreign Keys:**
  - character -> objects.ObjectDB [FK]
  - challenge_instance -> mechanics.ChallengeInstance [FK]
  - approach -> mechanics.ChallengeApproach [FK]
  - outcome -> traits.CheckOutcome [FK] (nullable)
  - consequence -> checks.Consequence [FK] (nullable)
**Pointed to by:**
  - consequence_outcomes <- checks.ConsequenceOutcome

### ContextConsequencePool
**Foreign Keys:**
  - property -> mechanics.Property [FK]
  - consequence_pool -> actions.ConsequencePool [FK]
  - check_type -> checks.CheckType [FK] (nullable)

### AestheticAxisConfig

### CharacterEngagement
**Foreign Keys:**
  - character -> objects.ObjectDB [OneToOne]
  - source_content_type -> contenttypes.ContentType [FK]

### Service Functions
- `begin_engagement(character: 'ObjectDB', engagement_type: 'str', *, source: 'object') -> 'CharacterEngagement' — Ensure the character has an engagement; create one if none exists.`
- `chart_has_success_outcomes(rank_difference: int) -> bool — Check if the ResultChart for this rank difference has any success outcomes.`
- `covenant_level_bonus(sheet: 'object', target: 'ModifierTarget') -> 'int' — Sum the authored covenant-level passive bonus across engaged memberships (#762).`
- `covenant_role_base_total(sheet: 'object', target: 'ModifierTarget') -> 'int' — Raw engaged-covenant-role bonus for ``target`` — no per-gear marginal blend (#1174).`
- `covenant_role_bonus(sheet: 'object', target: 'ModifierTarget', level_override: 'int | None' = None) -> 'int' — Sum covenant-role contributions across equipped items, gated on engagement.`
- `create_distinction_modifiers(character_distinction: 'CharacterDistinction') -> 'list[CharacterModifier]' — Create ModifierSource + CharacterModifier records for all effects of a distinction.`
- `delete_distinction_modifiers(character_distinction: 'CharacterDistinction') -> 'int' — Delete all modifier records for a distinction.`
- `end_engagement(character: 'ObjectDB', engagement_type: 'str', *, source: 'object') -> 'None' — Delete the character's engagement iff it matches type AND source.`
- `equipment_walk_total(character: 'object', target: 'ModifierTarget', level_override: 'int | None' = None) -> 'int' — Sum facet + covenant-role + covenant-level + mantle passive bonuses (Spec D §5.5).`
- `equipment_walk_total_unblended(sheet: 'object', target: 'ModifierTarget') -> 'int' — ``equipment_walk_total`` with the covenant-role component as its raw base (#1174).`
- `fashion_outfit_bonus(sheet: 'object', target: 'ModifierTarget', society: 'object') -> 'int' — Perception-relative outfit bonus vs. a society's current fashion (#513).`
- `get_aesthetic_config() -> 'AestheticAxisConfig' — Lazy-create and return the singleton aesthetic-axis config (pk=1).`
- `get_all_capability_values(character_sheet: 'CharacterSheet') -> dict[int, int] — Get all capability values for a character.`
- `get_available_actions(character: 'ObjectDB', location: 'ObjectDB', capability_sources: 'list[CapabilitySource] | None' = None) -> 'list[AvailableAction]' — Generate available Actions for a character at a location.`
- `get_capability_sources_for_character(character: 'ObjectDB') -> 'list[CapabilitySource]' — Collect all Capability sources for a character (per-source, not aggregated).`
- `get_modifier_breakdown(character, modifier_target: 'ModifierTarget') -> 'ModifierBreakdown' — Get detailed breakdown of all modifiers for a target.`
- `get_modifier_total(character, modifier_target: 'ModifierTarget', *, perceiving_society: 'object | None' = None, level_override: 'int | None' = None) -> 'int' — Get total modifier value for a target.`
- `item_mundane_stat_for_target(item: 'ItemInstance', target: 'ModifierTarget') -> 'int' — Mundane combat stat an equipped item contributes to ``target`` (#985, §5.6).`
- `motif_coherence_bonus(sheet: 'object', resonance_id: 'int') -> 'int' — Per-resonance fashion-coherence bonus from worn styles bound to the character's Motif.`
- `passive_facet_bonuses(sheet: 'object', target: 'ModifierTarget') -> 'int' — Sum tier-0 FLAT_BONUS contributions from equipped item facets (Spec D §5.2).`
- `passive_mantle_bonuses(sheet: 'object', target: 'ModifierTarget') -> 'int' — Sum tier-0 FLAT_BONUS contributions from attuned mantle threads (Spec D §5.2).`
- `passive_motif_style_bonuses(sheet: 'object', target: 'ModifierTarget') -> 'int' — Coherence bonus for ``target``'s resonance (Spec D §5.3). Thin wrapper over`
- `prerequisites_met(prereqs: 'Iterable[Prerequisite]', caster: 'ObjectDB', target: 'ObjectDB') -> 'bool' — True if target satisfies every one of prereqs (all() semantics; empty = True).`
- `preview_check_difficulty(character: 'ObjectDB', check_type: 'CheckType', target_difficulty: int = 0, extra_modifiers: int = 0) -> int — Preview the rank difference for a check without rolling.`
- `property_damage_bonus(target: 'ObjectDB', damage_type: 'DamageType | None') -> 'int' — Sum PropertyDamageModifier.modifier_value for target's active Properties.`
- `role_base_bonus_for_target(role: 'CovenantRole', target: 'ModifierTarget', character_level: 'int') -> 'int' — Authored covenant-role bonus for ``target``, scaled by character level (#985).`
- `update_distinction_rank(character_distinction: 'CharacterDistinction') -> 'None' — Update CharacterModifier values when rank changes.`
- `worn_quality_aggregate(rows: 'Iterable[object]') -> 'Decimal' — Sum (item_quality_multiplier × attachment_quality_multiplier) over worn rows.`


## world.missions

### MissionCategory
**Pointed to by:**
  - templates <- missions.MissionTemplate

### MissionTemplate
**Foreign Keys:**
  - created_in_era -> stories.Era [FK] (nullable)
  - report_to_role -> npc_services.NPCRole [FK] (nullable)
  - categories -> missions.MissionCategory [M2M]
**Pointed to by:**
  - clues <- clues.Clue
  - nodes <- missions.MissionNode
  - instances <- missions.MissionInstance
  - givers <- missions.MissionGiver
  - offer_details <- npc_services.MissionOfferDetails

### MissionNode
**Foreign Keys:**
  - template -> missions.MissionTemplate [FK]
  - allowed_riders -> checks.Consequence [M2M]
  - locations -> evennia_extensions.RoomProfile [M2M]
**Pointed to by:**
  - options <- missions.MissionOption

### MissionOption
**Foreign Keys:**
  - node -> missions.MissionNode [FK]
  - authored_check_type -> checks.CheckType [FK] (nullable)
  - branch_target -> missions.MissionNode [FK] (nullable)
  - challenge -> mechanics.ChallengeTemplate [FK] (nullable)
  - locations -> evennia_extensions.RoomProfile [M2M]
**Pointed to by:**
  - routes <- missions.MissionOptionRoute

### MissionOptionRoute
**Foreign Keys:**
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
  - route -> missions.MissionOptionRoute [FK]
  - target_node -> missions.MissionNode [FK]
  - consequence -> checks.Consequence [FK] (nullable)
**Pointed to by:**
  - reward_templates <- missions.MissionOptionRouteReward

### MissionOptionRouteReward
**Foreign Keys:**
  - route -> missions.MissionOptionRoute [FK] (nullable)
  - candidate -> missions.MissionOptionRouteCandidate [FK] (nullable)
  - resonance -> magic.Resonance [FK] (nullable)

### MissionRenownAward
**Foreign Keys:**
  - route -> missions.MissionOptionRoute [FK]
  - archetypes -> societies.PhilosophicalArchetype [M2M]

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
**Pointed to by:**
  - participants <- missions.MissionParticipant
  - snapshots <- missions.MissionNodeSnapshot
  - group_ballots <- missions.MissionGroupBallot
  - deeds <- missions.MissionDeedRecord

### MissionParticipant
**Foreign Keys:**
  - instance -> missions.MissionInstance [FK]
  - character -> objects.ObjectDB [FK]
**Pointed to by:**
  - group_ballots <- missions.MissionGroupBallot

### MissionNodeSnapshot
**Foreign Keys:**
  - instance -> missions.MissionInstance [FK]
  - node -> missions.MissionNode [FK]
  - participant -> missions.MissionParticipant [FK]

### MissionGroupBallot
**Foreign Keys:**
  - instance -> missions.MissionInstance [FK]
  - node -> missions.MissionNode [FK]
  - participant -> missions.MissionParticipant [FK]
  - picked_option -> missions.MissionOption [FK]
  - picked_approach -> mechanics.ChallengeApproach [FK] (nullable)
  - voted_option -> missions.MissionOption [FK] (nullable)

### MissionDeedRecord
**Foreign Keys:**
  - instance -> missions.MissionInstance [FK]
  - actor -> objects.ObjectDB [FK]
  - node -> missions.MissionNode [FK]
  - option -> missions.MissionOption [FK]
  - outcome -> traits.CheckOutcome [FK] (nullable)
  - route_candidate -> missions.MissionOptionRouteCandidate [FK] (nullable)
**Pointed to by:**
  - explaining_secrets <- secrets.Secret
  - reward_lines <- missions.MissionDeedRewardLine
  - queued_rewards <- missions.MissionRewardQueue

### MissionGiver
**Foreign Keys:**
  - target -> objects.ObjectDB [FK] (nullable)
  - org -> societies.Organization [FK] (nullable)
  - templates -> missions.MissionTemplate [M2M]
**Pointed to by:**
  - cooldowns <- missions.MissionGiverCooldown

### MissionGiverCooldown
**Foreign Keys:**
  - giver -> missions.MissionGiver [FK]
  - character -> objects.ObjectDB [FK]

### MissionDeedRewardLine
**Foreign Keys:**
  - deed -> missions.MissionDeedRecord [FK]
  - recipient -> objects.ObjectDB [FK]
  - resonance -> magic.Resonance [FK] (nullable)
**Pointed to by:**
  - resonance_grants <- magic.ResonanceGrant

### MissionRewardQueue
**Foreign Keys:**
  - deed -> missions.MissionDeedRecord [FK]
  - line -> missions.MissionDeedRewardLine [FK]

### MissionRiskAcknowledgement
**Foreign Keys:**
  - offer -> npc_services.NPCServiceOffer [FK]
  - persona -> scenes.Persona [FK]

### Service Functions
- `apply_deed_rewards(deed: 'MissionDeedRecord', *, skip_unbuilt: 'bool' = False, room: 'ObjectDB | None' = None, skip_criminal: 'bool' = False) -> 'ApplyDeedRewardsResult' — Route every emitted :class:`MissionDeedRewardLine` on ``deed`` downstream.`
- `apply_mission_reward_batch() -> 'RewardBatchResult' — Walk every ``applied=False`` :class:`MissionRewardQueue` row and try to grant it.`
- `beat_for(instance: 'MissionInstance', character: 'ObjectDB') -> 'BeatView | None' — The current beat as ``character`` sees it; None when the run is done.`
- `build_group_option_list(instance: 'MissionInstance', node: 'MissionNode') -> 'list[PresentedOption]' — Union of every participant's Phase-3 option list at ``node``.`
- `build_option_list(instance: 'MissionInstance', node: 'MissionNode', viewer: 'MissionParticipant') -> 'list[PresentedOption]' — Surface the options the acting ``viewer`` can take at ``node``.`
- `contract_holder(instance: 'MissionInstance') -> 'MissionParticipant' — Return the instance's single contract-holding participant.`
- `emit_candidate_rewards(instance: 'MissionInstance', candidate: 'MissionOptionRouteCandidate', deed: 'MissionDeedRecord') -> 'list[MissionDeedRewardLine]' — Emit a fired random-set candidate's own reward bundle (#941).`
- `emit_terminal_rewards(instance: 'MissionInstance', route: 'MissionOptionRoute', deed: 'MissionDeedRecord') -> 'list[MissionDeedRewardLine]' — Emit one :class:`MissionDeedRewardLine` per (template × recipient).`
- `enter_node(instance: 'MissionInstance', node: 'MissionNode') -> 'None' — Record entry into ``node`` and advance the run's position.`
- `journal_for(character: 'ObjectDB') -> 'list[JournalEntry]' — Return one :class:`JournalEntry` per mission this character is in.`
- `on_mission_complete_for_beat(instance: 'MissionInstance', *, route: 'MissionOptionRoute | None' = None) -> 'MissionBeatTriggerRecord | None' — Record a Mission → Beat terminal trigger and complete the linked Beat.`
- `resolve_beat_option(instance: 'MissionInstance', character: 'ObjectDB', *, option_id: 'int', approach_id: 'int | None' = None) -> 'ResolvedBeat' — Resolve the chosen option for ``character``; deliver both narratives.`
- `resolve_group_node(instance: 'MissionInstance', node: 'MissionNode') -> 'list[MissionDeedRecord]' — Resolve a group ``node`` from its collected ``MissionGroupBallot`` rows (#1036).`
- `resolve_option(instance: 'MissionInstance', node: 'MissionNode', option: 'MissionOption', actor: 'MissionParticipant', *, chosen_approach: 'ChallengeApproach | None' = None, advance: 'bool' = True) -> 'MissionDeedRecord' — Resolve ``actor`` taking ``option`` at ``node``; return its deed.`
- `share_mission(instance: 'MissionInstance', other_character: 'ObjectDB') -> 'MissionParticipant' — Add ``other_character`` as a non-holder participant to ``instance``.`
- `staff_assign_mission(template: 'MissionTemplate', character: 'ObjectDB') -> 'MissionInstance' — Staff-power: drop a mission on a character without a giver context.`
- `validate_mission_option(option: 'MissionOption') -> 'None' — Validate post-save invariants for ``option``.`


## world.narrative

### NarrativeMessage
**Foreign Keys:**
  - sender_account -> accounts.AccountDB [FK] (nullable)
  - related_story -> stories.Story [FK] (nullable)
  - related_beat_completion -> stories.BeatCompletion [FK] (nullable)
  - related_episode_resolution -> stories.EpisodeResolution [FK] (nullable)
**Pointed to by:**
  - deliveries <- narrative.NarrativeMessageDelivery

### AmbientStirLine

### NarrativeMessageDelivery
**Foreign Keys:**
  - message -> narrative.NarrativeMessage [FK]
  - recipient_character_sheet -> character_sheets.CharacterSheet [FK]

### Gemit
**Foreign Keys:**
  - sender_account -> accounts.AccountDB [FK] (nullable)
  - related_era -> stories.Era [FK] (nullable)
  - related_story -> stories.Story [FK] (nullable)
  - reach_societies -> societies.Society [M2M]
  - reach_organizations -> societies.Organization [M2M]

### UserStoryMute
**Foreign Keys:**
  - account -> accounts.AccountDB [FK]
  - story -> stories.Story [FK]

### UserCategoryMute
**Foreign Keys:**
  - account -> accounts.AccountDB [FK]

### Service Functions
- `broadcast_gemit(*, body: 'str', sender_account: 'AccountDB', reach: 'str' = GemitReach.GAME_WIDE, societies: 'Iterable[Society] | None' = None, organizations: 'Iterable[Organization] | None' = None, related_era: 'Era | None' = None, related_story: 'Story | None' = None) -> 'Gemit' — Create a Gemit and push it to its ``reach`` audience in green (#1450).`
- `deliver_queued_messages(character_sheet: 'CharacterSheet') -> 'int' — Push all undelivered messages for this character and mark delivered.`
- `emit_ambient_room_stir(room: 'ObjectDB', *, exclude: 'ObjectDB | None' = None) -> 'None' — Send a source-ambiguous ambient line to a room's bystanders (#885).`
- `is_category_muted(*, account: 'AccountDB', category: 'str') -> 'bool' — Whether an account has muted a narrative category's live push.`
- `send_narrative_message(*, recipients: 'Iterable[CharacterSheet]', body: 'str', category: 'str', sender_account: 'AccountDB | None' = None, ooc_note: 'str' = '', related_story: 'Story | None' = None, related_beat_completion: 'BeatCompletion | None' = None, related_episode_resolution: 'EpisodeResolution | None' = None) -> 'NarrativeMessage' — Create a NarrativeMessage and fan out deliveries to each recipient.`
- `send_story_ooc_message(*, story: 'Story', sender_account: 'AccountDB', body: 'str', ooc_note: 'str' = '') -> 'NarrativeMessage' — Lead GM or staff sends an OOC notice to all participants of a story.`
- `set_category_mute(*, account: 'AccountDB', category: 'str', muted: 'bool') -> 'None' — Mute or unmute a narrative category's real-time push for an account (#1522).`


## world.npc_services

### NPCStanding
**Foreign Keys:**
  - persona -> scenes.Persona [FK]
  - npc_persona -> scenes.Persona [FK]

### NPCRole
**Foreign Keys:**
  - faction_affiliation -> societies.Organization [FK] (nullable)
**Pointed to by:**
  - missions_reported_to <- missions.MissionTemplate
  - functionaries <- npc_services.Functionary
  - offers <- npc_services.NPCServiceOffer
  - role_cooldowns <- npc_services.NPCRoleCooldown
  - permits_issued <- buildings.BuildingPermitDetails

### Functionary
**Foreign Keys:**
  - role -> npc_services.NPCRole [FK]
  - room -> evennia_extensions.RoomProfile [FK]

### NPCServiceOffer
**Foreign Keys:**
  - role -> npc_services.NPCRole [FK]
  - check_type -> checks.CheckType [FK] (nullable)
**Pointed to by:**
  - mission_risk_acknowledgements <- missions.MissionRiskAcknowledgement
  - cooldowns <- npc_services.OfferCooldown
  - mission_offer_details <- npc_services.MissionOfferDetails
  - permit_offer_details <- npc_services.PermitOfferDetails
  - loan_offer_details <- npc_services.LoanOfferDetails

### OfferCooldown
**Foreign Keys:**
  - offer -> npc_services.NPCServiceOffer [FK]
  - persona -> scenes.Persona [FK]

### NPCRoleCooldown
**Foreign Keys:**
  - role -> npc_services.NPCRole [FK]
  - persona -> scenes.Persona [FK]

### MissionOfferDetails
**Foreign Keys:**
  - offer -> npc_services.NPCServiceOffer [OneToOne]
  - role -> npc_services.NPCRole [FK]
  - mission_template -> missions.MissionTemplate [FK]

### PermitOfferDetails
**Foreign Keys:**
  - offer -> npc_services.NPCServiceOffer [OneToOne]
  - building_kind -> buildings.BuildingKind [FK] (nullable)
  - default_approved_wards -> areas.Area [M2M]

### LoanOfferDetails
**Foreign Keys:**
  - offer -> npc_services.NPCServiceOffer [OneToOne]
  - creditor_organization -> societies.Organization [FK] (nullable)

### Service Functions
- `adjust_npc_affection(pc_persona, npc_persona, *, delta: 'int') -> 'int' — Apply a disposition ``delta`` to the (pc_persona, npc_persona) standing.`
- `available_offers(session: 'InteractionSession', *, pool_count: 'int | None' = None) -> 'list[NPCServiceOffer]' — Return offers the PC can currently see/select, in stable order.`
- `dispatch_offer_effect(offer: 'NPCServiceOffer', persona: 'Persona') -> 'EffectResult' — Look up the registered handler for ``offer.kind`` and invoke it.`
- `end_interaction(session: 'InteractionSession') -> 'None' — Close the session and persist final affection for class 2-4 NPCs.`
- `evaluate(rule: 'dict', ctx: 'PredicateContext') -> 'bool' — Evaluate a predicate rule tree against an acting-character context.`
- `mission_pool_count(*, role: 'NPCRole', persona: 'Persona', npc_persona: 'Persona | None') -> 'int' — POOL offer count to surface for ``persona`` at this NPC (#726, #1020).`
- `perform_check(character: 'ObjectDB', check_type: 'CheckType', target_difficulty: int = 0, extra_modifiers: int = 0, effort_level: str | None = None, fatigue_penalty: int = 0, specialization: 'Specialization | None' = None) -> world.checks.types.CheckResult — Main check resolution function.`
- `resolve_offer(session: 'InteractionSession', offer: 'NPCServiceOffer') -> 'EffectResult' — Grant ``offer`` in ``session`` — dispatch its effect, update rapport.`
- `serialize_npc_session_state(session: 'InteractionSession', *, last_result_message: 'str' = '') -> 'dict' — Compose the response payload from a (live or freshly-closed) session.`
- `start_interaction(*, role: 'NPCRole', persona: 'Persona', character: 'Character', npc_persona: 'Persona | None' = None) -> 'InteractionSession' — Begin an interaction with an NPC of ``role``.`
- `template_visible_to(template: 'MissionTemplate', character: 'ObjectDB', *, persona: 'Persona | None' = None) -> 'bool' — True if ``character`` may see / be offered ``template``.`


## world.progression

### ClassLevelAdvancement
**Foreign Keys:**
  - scene -> scenes.Scene [FK] (nullable)
  - declaration_interaction -> scenes.Interaction [FK] (nullable)
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - character_class -> classes.CharacterClass [FK]
  - officiant -> character_sheets.CharacterSheet [FK] (nullable)
  - ritual -> magic.Ritual [FK] (nullable)
  - witnesses -> scenes.Persona [M2M]

### DuranceTrainingSite
**Foreign Keys:**
  - room_profile -> evennia_extensions.RoomProfile [FK]
  - officiant -> character_sheets.CharacterSheet [FK]
  - training_path -> classes.Path [FK] (nullable)

### CharacterXP
**Foreign Keys:**
  - character -> objects.ObjectDB [FK]

### CharacterXPTransaction
**Foreign Keys:**
  - character -> objects.ObjectDB [FK]

### WeeklySocialEngagement
**Foreign Keys:**
  - account -> accounts.AccountDB [OneToOne]
  - game_week -> game_clock.GameWeek [FK] (nullable)
**Pointed to by:**
  - initiators <- progression.WeeklyEngagementInitiator

### WeeklyEngagementInitiator
**Foreign Keys:**
  - ledger -> progression.WeeklySocialEngagement [FK]
  - initiator_account -> accounts.AccountDB [FK]

### KudosSourceCategory
**Pointed to by:**
  - transactions <- progression.KudosTransaction

### KudosClaimCategory
**Pointed to by:**
  - transactions <- progression.KudosTransaction

### KudosPointsData
**Foreign Keys:**
  - account -> accounts.AccountDB [OneToOne]

### KudosTransaction
**Foreign Keys:**
  - account -> accounts.AccountDB [FK]
  - source_category -> progression.KudosSourceCategory [FK] (nullable)
  - claim_category -> progression.KudosClaimCategory [FK] (nullable)
  - awarded_by -> accounts.AccountDB [FK] (nullable)
  - character -> objects.ObjectDB [FK] (nullable)

### KudosDifficultyWeight

### PathIntent
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [OneToOne]
  - intended_path -> classes.Path [FK]

### CharacterPathHistory
**Foreign Keys:**
  - character -> objects.ObjectDB [FK]
  - path -> classes.Path [FK]

### RandomSceneTarget
**Foreign Keys:**
  - account -> accounts.AccountDB [FK]
  - target_persona -> scenes.Persona [FK]
  - game_week -> game_clock.GameWeek [FK]

### RandomSceneCompletion
**Foreign Keys:**
  - account -> accounts.AccountDB [FK]
  - claimer_entry -> roster.RosterEntry [FK]
  - target_persona -> scenes.Persona [FK]

### ExperiencePointsData
**Foreign Keys:**
  - account -> accounts.AccountDB [OneToOne]

### XPTransaction
**Foreign Keys:**
  - account -> accounts.AccountDB [FK]
  - character -> objects.ObjectDB [FK] (nullable)
  - gm -> accounts.AccountDB [FK] (nullable)

### DevelopmentPoints
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - trait -> traits.Trait [FK]

### DevelopmentTransaction
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - trait -> traits.Trait [FK]
  - scene -> scenes.Scene [FK] (nullable)
  - gm -> accounts.AccountDB [FK] (nullable)
  - game_week -> game_clock.GameWeek [FK] (nullable)

### WeeklySkillUsage
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - trait -> traits.Trait [FK]
  - game_week -> game_clock.GameWeek [FK]

### XPCostChart
**Pointed to by:**
  - cost_entries <- progression.XPCostEntry
  - class_costs <- progression.ClassXPCost
  - trait_costs <- progression.TraitXPCost

### XPCostEntry
**Foreign Keys:**
  - chart -> progression.XPCostChart [FK]

### ClassXPCost
**Foreign Keys:**
  - character_class -> classes.CharacterClass [FK]
  - cost_chart -> progression.XPCostChart [FK]

### TraitXPCost
**Foreign Keys:**
  - trait -> traits.Trait [FK]
  - cost_chart -> progression.XPCostChart [FK]

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

### TraitRatingUnlock
**Foreign Keys:**
  - trait -> traits.Trait [FK]

### TraitRequirement
**Foreign Keys:**
  - class_level_unlock -> progression.ClassLevelUnlock [FK]
  - trait -> traits.Trait [FK]

### LevelRequirement
**Foreign Keys:**
  - class_level_unlock -> progression.ClassLevelUnlock [FK]

### ClassLevelRequirement
**Foreign Keys:**
  - class_level_unlock -> progression.ClassLevelUnlock [FK]
  - character_class -> classes.CharacterClass [FK]

### MultiClassRequirement
**Foreign Keys:**
  - class_level_unlock -> progression.ClassLevelUnlock [FK]
  - required_classes -> classes.CharacterClass [M2M]
**Pointed to by:**
  - class_levels <- progression.MultiClassLevel

### MultiClassLevel
**Foreign Keys:**
  - multi_class_requirement -> progression.MultiClassRequirement [FK]
  - character_class -> classes.CharacterClass [FK]

### AchievementRequirement
**Foreign Keys:**
  - class_level_unlock -> progression.ClassLevelUnlock [FK]
  - achievement -> achievements.Achievement [FK]

### RelationshipRequirement
**Foreign Keys:**
  - class_level_unlock -> progression.ClassLevelUnlock [FK]

### LegendRequirement
**Foreign Keys:**
  - class_level_unlock -> progression.ClassLevelUnlock [FK]

### TierRequirement
**Foreign Keys:**
  - class_level_unlock -> progression.ClassLevelUnlock [FK]

### CharacterUnlock
**Foreign Keys:**
  - character -> objects.ObjectDB [FK]
  - character_class -> classes.CharacterClass [FK]

### WeeklyVoteBudget
**Foreign Keys:**
  - account -> accounts.AccountDB [FK]
  - game_week -> game_clock.GameWeek [FK]

### WeeklyVote
**Foreign Keys:**
  - voter -> accounts.AccountDB [FK]
  - game_week -> game_clock.GameWeek [FK]
  - author_account -> accounts.AccountDB [FK]

### Service Functions
- `award_cg_conversion_xp(character: evennia.objects.models.ObjectDB, *, remaining_cg_points: int, conversion_rate: int) -> None — Award locked XP to a character for unspent CG points.`
- `award_check_development(character_sheet: 'CharacterSheet', check_type: 'CheckType', effort_level: 'str | None', path_level: 'int') -> 'list[tuple[str, int, int]]' — Award dp to traits used in a check.`
- `award_combat_development(characters: list, combat_actions: dict[str, list[str]]) -> dict[str, dict[str, int]] — Award development points for combat actions.`
- `award_crafting_development(characters: list, crafting_actions: dict[str, str]) -> dict[str, dict[str, int]] — Award development points for crafting actions.`
- `award_development_points(character_sheet: 'CharacterSheet', trait: 'Trait', source: 'str', amount: 'int', scene: 'Scene | None' = None, reason: 'str' = ProgressionReason.SCENE_AWARD, description: 'str' = '', gm: 'AccountDB | None' = None) -> 'DevelopmentTransaction' — Award development points to a character and automatically apply them.`
- `award_kudos(account: evennia.accounts.models.AccountDB, amount: int, source_category: world.progression.models.kudos.KudosSourceCategory, description: str, awarded_by: evennia.accounts.models.AccountDB | None = None, character: evennia.objects.models.ObjectDB | None = None) -> world.progression.types.AwardResult — Award kudos to an account with full audit trail.`
- `award_scene_development_points(scene: world.scenes.models.Scene, participants: list, awards: dict[str, dict]) -> None — Award development points to scene participants.`
- `award_social_development(characters: list, social_actions: dict[str, list[str]]) -> dict[str, dict[str, int]] — Award development points for social actions.`
- `award_xp(account: 'AccountDB', amount: 'int', reason: 'str' = ProgressionReason.SYSTEM_AWARD, description: 'str' = '', gm: 'AccountDB | None' = None) -> 'XPTransaction' — Award XP to an account.`
- `calculate_automatic_scene_awards(scene: world.scenes.models.Scene, participants: list) -> dict[str, dict] — Calculate automatic development point awards based on scene content.`
- `calculate_check_dev_points(effort_level: 'str', path_level: 'int') -> 'int' — Calculate dp earned from a single check.`
- `calculate_level_up_requirements(character: 'ObjectDB', character_class: 'CharacterClass', target_level: 'int') -> 'LevelUpRequirements | dict[str, str]' — Calculate what's required to level up a character in a specific class.`
- `cast_vote(voter_account: evennia.accounts.models.AccountDB, target_type: str, target_id: int, author_account: evennia.accounts.models.AccountDB) -> world.progression.models.voting.WeeklyVote — Cast a vote on a piece of content.`
- `check_requirements_for_unlock(character: 'ObjectDB', unlock_target: 'ClassLevelUnlock') -> 'tuple[bool, list[str]]' — Check if a character meets all requirements for an unlock.`
- `claim_kudos(account: evennia.accounts.models.AccountDB, amount: int, claim_category: world.progression.models.kudos.KudosClaimCategory, description: str) -> world.progression.types.ClaimResult — Claim kudos from an account for conversion to rewards.`
- `claim_kudos_for_xp(account: evennia.accounts.models.AccountDB, amount: int, claim_category: world.progression.models.kudos.KudosClaimCategory, description: str = '') -> world.progression.types.KudosXPResult — Claim kudos and convert the reward to account-level XP.`
- `get_available_unlocks_for_character(character: 'ObjectDB') -> 'AvailableUnlocks' — Get all unlocks that a character could potentially purchase.`
- `get_development_suggestions_for_character(character: 'ObjectDB') -> 'dict[str, list[str]]' — Get development suggestions for a character based on their current traits.`
- `get_or_create_vote_budget(account: evennia.accounts.models.AccountDB, game_week: world.game_clock.models.GameWeek | None = None) -> world.progression.models.voting.WeeklyVoteBudget — Return the vote budget for the current week, creating with defaults if needed.`
- `get_or_create_xp_tracker(account: 'AccountDB') -> 'ExperiencePointsData' — Get or create XP tracker for an account.`
- `get_vote_state(voter_account: evennia.accounts.models.AccountDB, target_type: str, target_id: int) -> bool — Return whether the voter has an unprocessed vote for this target this week.`
- `get_votes_by_voter(voter_account: evennia.accounts.models.AccountDB) -> django.db.models.query.QuerySet — Return all unprocessed votes for the current week.`
- `increment_scene_bonus(account: evennia.accounts.models.AccountDB) -> None — Add 1 to scene_bonus_votes for the current week's budget (capped at 7).`
- `on_scene_finished(scene: world.scenes.models.Scene) -> None — Grant scene completion rewards and settle reaction windows.`
- `remove_vote(voter_account: evennia.accounts.models.AccountDB, target_type: str, target_id: int) -> None — Remove an unprocessed vote for the current week.`
- `spend_xp_on_unlock(character: 'ObjectDB', unlock_target: 'ClassLevelUnlock', gm: 'AccountDB | None' = None) -> 'tuple[bool, str, CharacterUnlock | None]' — Spend XP to unlock something for a character.`


## world.projects

### Project
**Foreign Keys:**
  - owner_persona -> scenes.Persona [FK]
  - outcome_tier -> traits.CheckOutcome [FK] (nullable)
  - resonance -> magic.Resonance [FK] (nullable)
**Pointed to by:**
  - resonance_grants <- magic.ResonanceGrant
  - research_details <- clues.ResearchProjectDetails
  - ransom_captivities <- captivity.Captivity
  - contributions <- projects.Contribution
  - resulting_building <- buildings.Building
  - building_extension_details <- buildings.BuildingExtensionDetails
  - fortification_upgrade_details <- buildings.FortificationUpgradeDetails
  - interior_design_details <- buildings.InteriorDesignDetails
  - building_construction_details <- buildings.BuildingConstructionDetails
  - resulting_building_project_instance <- buildings.BuildingProjectInstance
  - room_feature_progression_details <- room_features.RoomFeatureProgressionDetails

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

### Service Functions
- `add_contribution(*, project: 'Project', contributor_persona: 'Persona', kind: 'str', ap_amount: 'int | None' = None, money_amount: 'int | None' = None, item_instance: 'ItemInstance | None' = None, check_outcome: 'CheckOutcome | None' = None, contribution_method: 'ContributionMethod | None' = None, intent_text: 'str' = '', privacy_setting: 'str' = 'PRIVATE') -> 'Contribution' — Add a contribution to an ACTIVE Project and advance current_progress.`
- `clear_instant_completion_kinds() -> 'None' — Test-only: clear the instant-completion registry.`
- `clear_kind_handlers() -> 'None' — Test-only: clear the handler registry.`
- `contribute_check_to_project(project: 'Project', *, actor: 'ObjectDB', contributor_persona: 'Persona', method: 'ContributionMethod') -> 'Contribution' — Make a check-based contribution: spend AP, roll the check, advance on success (#1574).`
- `donate_to_project(project: 'Project', *, donor_persona: 'Persona', amount: 'int') -> 'Contribution' — Debit ``amount`` coppers from the donor's purse and record a MONEY contribution.`
- `get_kind_handler(kind: 'str') -> 'KindHandler' — Return the registered handler for `kind`, or raise LookupError.`
- `maybe_complete_immediately(project: 'Project') -> 'bool' — Resolve an instant-completion project the moment its threshold is funded (#1500).`
- `register_instant_completion_kind(kind: 'str') -> 'None' — Mark a ProjectKind as completing immediately on threshold (re-register safe).`
- `register_kind_handler(kind: 'str', handler: 'KindHandler') -> 'None' — Register a per-kind resolution handler. Re-registration overwrites.`
- `resolve_project(project: 'Project', *, outcome_tier: 'CheckOutcome') -> 'None' — Finalize a RESOLVING project: dispatch to per-kind handler, set outcome.`
- `scan_active_projects() -> 'int' — Cron tick: scan ACTIVE projects, transition completion-ready ones to RESOLVING.`
- `set_contribution_story(project: 'Project', *, contributor_persona: 'Persona', text: 'str') -> 'Contribution | None' — Attach the narrative of how a contributor helped to their most recent contribution (#1574).`


## world.realms

### Realm
**Pointed to by:**
  - families <- roster.Family
  - profiles <- character_sheets.Profile
  - starting_areas <- character_creation.StartingArea
  - societies <- societies.Society
  - areas <- areas.Area


## world.relationships

### RelationshipCondition
**Foreign Keys:**
  - gates_modifiers -> mechanics.ModifierTarget [M2M]
**Pointed to by:**
  - consequence_effects <- checks.ConsequenceEffect
  - character_relationships <- relationships.CharacterRelationship
  - temporary_applications <- relationships.TemporaryRelationshipCondition

### RelationshipTrack
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

### RelationshipTier
**Foreign Keys:**
  - track -> relationships.RelationshipTrack [FK]

### HybridRelationshipType
**Pointed to by:**
  - requirements <- relationships.HybridRequirement

### HybridRequirement
**Foreign Keys:**
  - hybrid_type -> relationships.HybridRelationshipType [FK]
  - track -> relationships.RelationshipTrack [FK]

### GrievanceOption
**Foreign Keys:**
  - track -> relationships.RelationshipTrack [FK]

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
  - changes <- relationships.RelationshipChange
  - temporary_conditions <- relationships.TemporaryRelationshipCondition

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

### RelationshipDevelopment
**Foreign Keys:**
  - relationship -> relationships.CharacterRelationship [FK]
  - author -> character_sheets.CharacterSheet [FK]
  - track -> relationships.RelationshipTrack [FK]
  - linked_scene -> scenes.Scene [FK] (nullable)
**Pointed to by:**
  - writeupkudos_set <- relationships.WriteupKudos
  - writeupcomplaint_set <- relationships.WriteupComplaint

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

### WriteupKudos
**Foreign Keys:**
  - update -> relationships.RelationshipUpdate [FK] (nullable)
  - development -> relationships.RelationshipDevelopment [FK] (nullable)
  - capstone -> relationships.RelationshipCapstone [FK] (nullable)
  - account -> accounts.AccountDB [FK]

### WriteupComplaint
**Foreign Keys:**
  - update -> relationships.RelationshipUpdate [FK] (nullable)
  - development -> relationships.RelationshipDevelopment [FK] (nullable)
  - capstone -> relationships.RelationshipCapstone [FK] (nullable)
  - complainant -> accounts.AccountDB [FK]

### TemporaryRelationshipCondition
**Foreign Keys:**
  - relationship -> relationships.CharacterRelationship [FK]
  - condition -> relationships.RelationshipCondition [FK]

### Service Functions
- `add_relationship_condition(*, source: 'CharacterSheet', target: 'CharacterSheet', condition: 'RelationshipCondition', duration: 'timedelta | None' = None) -> 'None' — Add a ``RelationshipCondition`` to the directed ``source → target`` relationship (#1697).`
- `award_kudos(account: evennia.accounts.models.AccountDB, amount: int, source_category: world.progression.models.kudos.KudosSourceCategory, description: str, awarded_by: evennia.accounts.models.AccountDB | None = None, character: evennia.objects.models.ObjectDB | None = None) -> world.progression.types.AwardResult — Award kudos to an account with full audit trail.`
- `award_xp(account: 'AccountDB', amount: 'int', reason: 'str' = ProgressionReason.SYSTEM_AWARD, description: 'str' = '', gm: 'AccountDB | None' = None) -> 'XPTransaction' — Award XP to an account.`
- `clear_very_attracted(sheets) -> 'None' — Drop Very Attracted for the given characters — the scene-end early clear (#1697).`
- `create_capstone(*, relationship: 'CharacterRelationship', author: 'CharacterSheet', title: 'str', writeup: 'str', track: 'RelationshipTrack', points: 'int', visibility: 'UpdateVisibility', linked_scene: 'Scene | None' = None) -> 'RelationshipCapstone' — Record a capstone event — adds points to both capacity and developed_points.`
- `create_development(*, relationship: 'CharacterRelationship', author: 'CharacterSheet', title: 'str', writeup: 'str', track: 'RelationshipTrack', points: 'int', xp_awarded: 'int' = 0, visibility: 'UpdateVisibility', linked_scene: 'Scene | None' = None) -> 'RelationshipDevelopment' — Add permanent (developed) points to a track, up to capacity.`
- `create_first_impression(*, source: 'CharacterSheet', target: 'CharacterSheet', title: 'str', writeup: 'str', track: 'RelationshipTrack', points: 'int', coloring: 'FirstImpressionColoring', visibility: 'UpdateVisibility', linked_scene: 'Scene | None' = None) -> 'CharacterRelationship' — Create a pending relationship with an initial update and track progress.`
- `file_writeup_complaint(*, complainant_account: 'AccountDB', writeup, reason: 'str') -> 'WriteupComplaint' — File a bad-faith-RP complaint against a writeup for staff triage.`
- `get_account_for_character(character: 'ObjectDB') -> 'AccountDB | None' — Get the account currently playing this character via roster tenure.`
- `give_writeup_kudos(*, giver_account: 'AccountDB', writeup) -> 'WriteupKudos' — Award a non-revocable commendation to the writeup author on behalf of the subject.`
- `increment_stat(character_sheet: 'CharacterSheet', stat: 'StatDefinition', amount: 'int' = 1) -> 'int' — Increment a stat tracker (create if needed) and check for achievements.`
- `redistribute_points(*, relationship: 'CharacterRelationship', author: 'CharacterSheet', title: 'str', writeup: 'str', source_track: 'RelationshipTrack', target_track: 'RelationshipTrack', points: 'int', visibility: 'UpdateVisibility') -> 'RelationshipChange' — Move developed points from one track to another. No new value is added.`
- `register_grievance(*, source: 'CharacterSheet', target: 'CharacterSheet', option: 'GrievanceOption | None' = None, custom_points: 'int | None' = None, custom_track: 'RelationshipTrack | None' = None, writeup: 'str' = '', visibility: 'UpdateVisibility' = UpdateVisibility.PRIVATE) -> 'RelationshipCapstone' — Register a wronged character's one-sided grievance against whoever harmed them (#1429).`
- `relationship_gated_contributions(*, perceiver: 'CharacterSheet', perceived: 'CharacterSheet') -> 'list[ModifierContribution]' — Modifier contributions the perceiver's regard for the perceived injects into a check (#1696).`


## world.roster

### RosterApplication
**Foreign Keys:**
  - player_data -> evennia_extensions.PlayerData [FK]
  - character -> objects.ObjectDB [FK]
  - reviewed_by -> evennia_extensions.PlayerData [FK] (nullable)

### Family
**Foreign Keys:**
  - created_by -> accounts.AccountDB [FK] (nullable)
  - origin_realm -> realms.Realm [FK] (nullable)
**Pointed to by:**
  - tree_members <- roster.FamilyMember
  - profiles <- character_sheets.Profile
  - character_drafts <- character_creation.CharacterDraft

### FamilyMember
**Foreign Keys:**
  - family -> roster.Family [FK]
  - character -> objects.ObjectDB [OneToOne] (nullable)
  - mother -> roster.FamilyMember [FK] (nullable)
  - father -> roster.FamilyMember [FK] (nullable)
  - created_by -> accounts.AccountDB [FK] (nullable)
**Pointed to by:**
  - children_as_mother <- roster.FamilyMember
  - children_as_father <- roster.FamilyMember
  - drafts <- character_creation.CharacterDraft

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

### RosterEntry
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [OneToOne]
  - roster -> roster.Roster [FK]
  - profile_picture -> roster.TenureMedia [FK] (nullable)
  - previous_roster -> roster.Roster [FK] (nullable)
  - created_by_account -> accounts.AccountDB [FK] (nullable)
  - created_for_table -> gm.GMTable [FK] (nullable)
**Pointed to by:**
  - tenures <- roster.RosterTenure
  - random_scene_claimed_as <- progression.RandomSceneCompletion
  - known_rituals <- magic.CharacterRitualKnowledge
  - favorited_interactions <- scenes.InteractionFavorite
  - aggregatebeatcontribution_set <- stories.AggregateBeatContribution
  - beatcompletion_set <- stories.BeatCompletion
  - codex_knowledge <- codex.CharacterCodexKnowledge
  - clues_held <- clues.CharacterClue
  - secrets_known <- secrets.SecretKnowledge
  - invites <- gm.GMRosterInvite

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
  - media -> evennia_extensions.PlayerMedia [FK]
  - gallery -> roster.TenureGallery [FK] (nullable)
**Pointed to by:**
  - profile_for_entries <- roster.RosterEntry

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
  - gift_unlocks_taught <- magic.CharacterGiftUnlock
  - technique_teaching_offers <- magic.TechniqueTeachingOffer
  - taught_rituals <- magic.CharacterRitualKnowledge
  - thread_weaving_unlocks_taught <- magic.CharacterThreadWeavingUnlock
  - thread_weaving_offers <- magic.ThreadWeavingTeachingOffer
  - friendships_made <- scenes.Friendship
  - friendships_received <- scenes.Friendship
  - consent_groups <- consent.ConsentGroup
  - consent_memberships <- consent.ConsentGroupMember
  - social_consent_preference <- consent.SocialConsentPreference
  - social_consent_whitelist_owned <- consent.SocialConsentWhitelist
  - social_consent_whitelist_allowed <- consent.SocialConsentWhitelist
  - social_consent_blacklist_owned <- consent.SocialConsentBlacklist
  - social_consent_blacklist_blocked <- consent.SocialConsentBlacklist
  - codex_taught <- codex.CharacterCodexKnowledge
  - codex_teaching_offers <- codex.CodexTeachingOffer
  - codexteachingoffer_visible <- codex.CodexTeachingOffer
  - codexteachingoffer_excluded <- codex.CodexTeachingOffer


## world.scenes

### Scene
**Foreign Keys:**
  - location -> objects.ObjectDB [FK] (nullable)
  - event -> events.Event [FK] (nullable)
  - participants -> accounts.AccountDB [M2M]
**Pointed to by:**
  - developmenttransaction_set <- progression.DevelopmentTransaction
  - entry_flourish_offers <- magic.PendingEntryFlourishOffer
  - triggered_alterations <- magic.PendingAlteration
  - magicalalterationevent_set <- magic.MagicalAlterationEvent
  - anima_ritual_performances <- magic.AnimaRitualPerformance
  - dramatic_moment_tags <- magic.DramaticMomentTag
  - entry_endorsements <- magic.SceneEntryEndorsement
  - style_presentation_endorsements <- magic.StylePresentationEndorsement
  - entry_flourish_records <- magic.EntryFlourishRecord
  - sineating_pending_offers <- magic.SineatingPendingOffer
  - pending_stage_advance_offers <- magic.PendingStageAdvanceOffer
  - sineatings <- magic.Sineating
  - rescues <- magic.SoulTetherRescue
  - participations <- scenes.SceneParticipation
  - interactions <- scenes.Interaction
  - summary_revisions <- scenes.SceneSummaryRevision
  - check_modifiers <- scenes.SceneCheckModifier
  - scene_rounds <- scenes.SceneRound
  - action_requests <- scenes.SceneActionRequest
  - reaction_windows <- scenes.ReactionWindow
  - story_episodes <- stories.EpisodeScene
  - legend_events <- societies.LegendEvent
  - legend_entries <- societies.LegendEntry
  - legend_spreads <- societies.LegendSpread
  - explaining_secrets <- secrets.Secret
  - treatment_attempts <- conditions.TreatmentAttempt
  - situation_instances <- mechanics.SituationInstance
  - relationshipupdate_set <- relationships.RelationshipUpdate
  - relationshipdevelopment_set <- relationships.RelationshipDevelopment
  - relationshipcapstone_set <- relationships.RelationshipCapstone
  - covenant_rite_instances <- covenants.CovenantRiteInstance
  - combat_encounters <- combat.CombatEncounter
  - battle <- battles.Battle

### SceneParticipation
**Foreign Keys:**
  - scene -> scenes.Scene [FK]
  - account -> accounts.AccountDB [FK]

### Persona
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - profile -> character_sheets.Profile [FK] (nullable)
  - thumbnail -> evennia_extensions.PlayerMedia [FK] (nullable)
  - properties -> mechanics.Property [M2M]
**Pointed to by:**
  - mentored_allocations <- skills.TrainingAllocation
  - feedback_submissions <- player_submissions.PlayerFeedback
  - bug_reports <- player_submissions.BugReport
  - reports_submitted <- player_submissions.PlayerReport
  - reports_against <- player_submissions.PlayerReport
  - witnessed_advancements <- progression.ClassLevelAdvancement
  - targeted_for_random_scene <- progression.RandomSceneTarget
  - random_scene_completed_by <- progression.RandomSceneCompletion
  - poseendorsement_set <- magic.PoseEndorsement
  - sceneentryendorsement_set <- magic.SceneEntryEndorsement
  - presentationendorsement_set <- magic.PresentationEndorsement
  - stylepresentationendorsement_set <- magic.StylePresentationEndorsement
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
  - table_bulletin_posts <- stories.TableBulletinPost
  - table_bulletin_replies <- stories.TableBulletinReply
  - alternate_self_grants <- forms.AlternateSelf
  - return_for_active <- forms.ActiveAlternateSelf
  - trait_descriptors <- forms.PersonaTraitDescriptor
  - appearance_changes <- forms.AppearanceChangeLog
  - appearance_changes_made <- forms.AppearanceChangeLog
  - sent_org_membership_offers <- societies.OrganizationMembershipOffer
  - received_org_membership_offers <- societies.OrganizationMembershipOffer
  - organization_memberships <- societies.OrganizationMembership
  - society_reputations <- societies.SocietyReputation
  - organization_reputations <- societies.OrganizationReputation
  - legend_entries <- societies.LegendEntry
  - legend_spreads <- societies.LegendSpread
  - legend_stories_written <- societies.LegendDeedStory
  - deed_knowledge <- societies.PersonaDeedKnowledge
  - fame_reaction_cooldowns <- societies.FameReactionCooldown
  - org_contributions <- currency.ContributionRecord
  - contracts_proposed <- currency.Contract
  - contracts_received <- currency.Contract
  - businesses <- currency.Business
  - authored_secrets <- secrets.Secret
  - secret_victimhoods <- secrets.SecretVictim
  - heat_rows <- justice.PersonaHeat
  - ownership_records <- locations.LocationOwnership
  - tenancies <- locations.LocationTenancy
  - trendsetter_crownings <- items.Trendsetter
  - hosted_events <- events.EventHost
  - event_invitations <- events.EventInvitation
  - invitations_sent <- events.EventInvitation
  - combat_opponents <- combat.CombatOpponent
  - gm_table_memberships <- gm.GMTableMembership
  - mission_risk_acknowledgements <- missions.MissionRiskAcknowledgement
  - projects_owned <- projects.Project
  - project_contributions <- projects.Contribution
  - npc_standings <- npc_services.NPCStanding
  - standings_held_by <- npc_services.NPCStanding
  - offer_cooldowns <- npc_services.OfferCooldown
  - role_cooldowns <- npc_services.NPCRoleCooldown
  - owned_buildings <- buildings.Building
  - buildings_constructed <- buildings.Building
  - materials_contributed <- buildings.BuildingMaterial
  - permits_consumed <- buildings.BuildingPermitDetails
  - construction_projects_led <- buildings.BuildingConstructionDetails

### PersonaDiscovery
**Foreign Keys:**
  - persona -> scenes.Persona [FK]
  - linked_to -> scenes.Persona [FK]
  - discovered_by -> character_sheets.CharacterSheet [FK]

### Block
**Foreign Keys:**
  - owner -> evennia_extensions.PlayerData [FK]
  - blocked_player -> evennia_extensions.PlayerData [FK]
  - blocker_persona -> scenes.Persona [FK] (nullable)
  - blocked_persona -> scenes.Persona [FK] (nullable)

### Friendship
**Foreign Keys:**
  - friender_tenure -> roster.RosterTenure [FK]
  - friend_tenure -> roster.RosterTenure [FK]

### Mute
**Foreign Keys:**
  - owner -> evennia_extensions.PlayerData [FK]
  - muted_persona -> scenes.Persona [FK]

### BlockContactFlag
**Foreign Keys:**
  - blocker_account -> accounts.AccountDB [FK]
  - blocked_account -> accounts.AccountDB [FK]
  - initiator_persona -> scenes.Persona [FK]
  - target_persona -> scenes.Persona [FK]
  - scene -> scenes.Scene [FK] (nullable)

### Interaction
**Foreign Keys:**
  - persona -> scenes.Persona [FK]
  - writer_account -> accounts.AccountDB [FK] (nullable)
  - scene -> scenes.Scene [FK] (nullable)
  - place -> scenes.Place [FK] (nullable)
  - fury_committed -> magic.FuryTier [FK] (nullable)
  - target_personas -> scenes.Persona [M2M]
**Pointed to by:**
  - dramatic_moment_tags <- magic.DramaticMomentTag
  - endorsements <- magic.PoseEndorsement
  - sceneentryendorsement_set <- magic.SceneEntryEndorsement
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
  - consequence_outcomes <- checks.ConsequenceOutcome
  - referencing_updates <- relationships.RelationshipUpdate
  - combat_round_actions <- combat.CombatRoundAction
  - clash_contributions <- combat.ClashContribution

### InteractionFavorite
**Foreign Keys:**
  - interaction -> scenes.Interaction [FK]
  - roster_entry -> roster.RosterEntry [FK]

### InteractionReaction
**Foreign Keys:**
  - interaction -> scenes.Interaction [FK]
  - account -> accounts.AccountDB [FK]

### InteractionTargetPersona
**Foreign Keys:**
  - interaction -> scenes.Interaction [FK]
  - persona -> scenes.Persona [FK]

### InteractionAction
**Foreign Keys:**
  - pose -> scenes.Interaction [FK]
  - action_interaction -> scenes.Interaction [FK]

### InteractionPowerLedgerEntry
**Foreign Keys:**
  - interaction -> scenes.Interaction [FK]

### SceneSummaryRevision
**Foreign Keys:**
  - scene -> scenes.Scene [FK]
  - persona -> scenes.Persona [FK]

### SceneCheckModifier
**Foreign Keys:**
  - scene -> scenes.Scene [FK]
  - check_type -> checks.CheckType [FK]

### SceneRound
**Foreign Keys:**
  - room -> objects.ObjectDB [FK]
  - scene -> scenes.Scene [FK] (nullable)
**Pointed to by:**
  - participants <- scenes.SceneRoundParticipant
  - action_declarations <- scenes.SceneActionDeclaration
  - pending_sudden_harms <- scenes.PendingSuddenHarm

### SceneRoundDefaultsConfig
**Foreign Keys:**
  - updated_by -> accounts.AccountDB [FK] (nullable)

### SceneRoundParticipant
**Foreign Keys:**
  - scene_round -> scenes.SceneRound [FK]
  - character_sheet -> character_sheets.CharacterSheet [FK]
**Pointed to by:**
  - action_declarations <- scenes.SceneActionDeclaration
  - succor_declarations <- scenes.SceneActionDeclaration
  - interpose_declarations <- scenes.SceneActionDeclaration

### SceneActionDeclaration
**Foreign Keys:**
  - scene_round -> scenes.SceneRound [FK]
  - participant -> scenes.SceneRoundParticipant [FK]
  - challenge_instance -> mechanics.ChallengeInstance [FK] (nullable)
  - challenge_approach -> mechanics.ChallengeApproach [FK] (nullable)
  - target_persona -> scenes.Persona [FK] (nullable)
  - succor_target -> scenes.SceneRoundParticipant [FK] (nullable)
  - interpose_target -> scenes.SceneRoundParticipant [FK] (nullable)

### PendingSuddenHarm
**Foreign Keys:**
  - target_sheet -> character_sheets.CharacterSheet [FK]
  - scene_round -> scenes.SceneRound [FK]
  - damage_type -> conditions.DamageType [FK] (nullable)

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
  - pull_declaration <- scenes.SceneCastPullDeclaration

### SceneActionTarget
**Foreign Keys:**
  - action_request -> scenes.SceneActionRequest [FK]
  - target_persona -> scenes.Persona [FK]
  - result_interaction -> scenes.Interaction [OneToOne] (nullable)

### SceneCastPullDeclaration
**Foreign Keys:**
  - request -> scenes.SceneActionRequest [OneToOne]
  - resonance -> magic.Resonance [FK]
  - threads -> magic.Thread [M2M]

### Place
**Foreign Keys:**
  - room -> objects.ObjectDB [FK] (nullable)
**Pointed to by:**
  - interactions <- scenes.Interaction
  - presences <- scenes.PlacePresence

### PlacePresence
**Foreign Keys:**
  - place -> scenes.Place [FK]
  - persona -> scenes.Persona [FK]

### InteractionReceiver
**Foreign Keys:**
  - interaction -> scenes.Interaction [FK]
  - persona -> scenes.Persona [FK]
  - account -> accounts.AccountDB [FK] (nullable)

### ReactionWindow
**Foreign Keys:**
  - interaction -> scenes.Interaction [FK]
  - scene -> scenes.Scene [FK]
**Pointed to by:**
  - reactions <- scenes.WindowReaction
  - spread_assist_target <- societies.SpreadAssistTarget

### WindowReaction
**Foreign Keys:**
  - window -> scenes.ReactionWindow [FK]
  - reactor_persona -> scenes.Persona [FK]

### Service Functions
- `active_persona_for_sheet(sheet: 'CharacterSheet') -> 'Persona' — The face a character is currently presenting as (#981).`
- `broadcast_scene_message(scene: 'Scene', action: 'ActionType') -> 'None' — Send scene information to all accounts in the scene's location.`
- `create_mask(sheet: 'CharacterSheet', *, name: 'str', disguise_form: 'CharacterForm | None' = None, disguise_kind: 'str | None' = None) -> 'Persona' — Create a TEMPORARY anonymous **mask** — the "put on a mask" path (#1127).`
- `create_persona(sheet: 'CharacterSheet', *, name: 'str', persona_type: 'str', is_fake_name: 'bool' = False, bypass_cap: 'bool' = False) -> 'Persona' — Create a new ESTABLISHED or TEMPORARY persona for a character (#1127).`
- `invalidate_active_scene_cache(location: 'ObjectDB') -> 'None' — Clear the cached active scene for a location.`
- `persona_for_character(character: 'Character') -> 'Persona' — Return the PC's PRIMARY persona; raise loud on missing sheet/persona.`
- `set_active_persona(sheet: 'CharacterSheet', persona: 'Persona') -> 'None' — Set the character's active face (#981) — the ONLY mutator.`
- `set_persona_profile(persona: 'Persona', *, concept: 'str | None' = None, quote: 'str | None' = None, personality: 'str | None' = None, background: 'str | None' = None) -> 'Profile' — Author the fabricated bio a non-primary persona presents — its **Guise Sheet** (#1270).`


## world.secrets

### SecretCategory
**Pointed to by:**
  - secrets <- secrets.Secret

### Secret
**Foreign Keys:**
  - subject_sheet -> character_sheets.CharacterSheet [FK]
  - category -> secrets.SecretCategory [FK] (nullable)
  - author_persona -> scenes.Persona [FK] (nullable)
  - legend_deed -> societies.LegendEntry [FK] (nullable)
  - mission_deed -> missions.MissionDeedRecord [FK] (nullable)
  - scene -> scenes.Scene [FK] (nullable)
  - archetypes -> societies.PhilosophicalArchetype [M2M]
  - societies_exposed -> societies.Society [M2M]
**Pointed to by:**
  - distinction <- distinctions.CharacterDistinction
  - clues <- clues.Clue
  - victims <- secrets.SecretVictim
  - grievances <- secrets.SecretGrievance
  - known_by <- secrets.SecretKnowledge
  - gossip_heat <- secrets.SecretGossip

### SecretVictim
**Foreign Keys:**
  - secret -> secrets.Secret [FK]
  - organization -> societies.Organization [FK] (nullable)
  - persona -> scenes.Persona [FK] (nullable)

### SecretGrievance
**Foreign Keys:**
  - secret -> secrets.Secret [FK]
  - victim_sheet -> character_sheets.CharacterSheet [FK]
  - capstone -> relationships.RelationshipCapstone [FK] (nullable)

### SecretKnowledge
**Foreign Keys:**
  - roster_entry -> roster.RosterEntry [FK]
  - secret -> secrets.Secret [FK]

### SecretGossip
**Foreign Keys:**
  - secret -> secrets.Secret [FK]
  - region -> areas.Area [FK]

### Service Functions
- `author_player_flavor_secret(*, subject_sheet: 'CharacterSheet', author_persona: 'Persona', content: 'str', category: 'SecretCategory | None' = None) -> 'Secret' — Author a Level-1 player-flavor secret (the only tier a player may free-write).`
- `author_secret(*, subject_sheet: 'CharacterSheet', provenance: 'str', level: 'int' = SecretLevel.UNCOMMON_KNOWLEDGE, content: 'str' = '', category: 'SecretCategory | None' = None, consequences: 'str' = '', author_persona: 'Persona | None' = None, legend_deed: 'LegendEntry | None' = None, mission_deed: 'MissionDeedRecord | None' = None, scene: 'Scene | None' = None) -> 'Secret' — Author a secret about ``subject_sheet``, enforcing the anchor-scales-with-level rule.`
- `expose_secret(secret: 'Secret', *, societies: 'Iterable[Society]') -> 'SecretExposureResult' — Fire the reputation consequences of a secret becoming known to ``societies`` (#1429).`
- `grant_secret_knowledge(*, roster_entry: 'RosterEntry', secret: 'Secret', knows_category: 'bool' = False, knows_consequences: 'bool' = False) -> 'SecretKnowledge' — Record that a character knows a secret, unlocking the given layers (idempotent).`
- `known_secrets_for(roster_entry: 'RosterEntry', *, subject_sheet: 'CharacterSheet | None' = None, sort: 'str' = 'recent') -> 'QuerySet[SecretKnowledge]' — The secrets a character has **learned about others** — held records (#1334).`
- `register_secret_grievance(*, roster_entry: 'RosterEntry', secret: 'Secret', option: 'GrievanceOption | None' = None, custom_points: 'int | None' = None, custom_track: 'RelationshipTrack | None' = None, writeup: 'str' = '') -> 'RelationshipCapstone' — A secret's victim registers a grievance against its subject (#1429).`
- `secret_known_to(secret: 'Secret', roster_entry: 'RosterEntry') -> 'bool' — Whether this character already holds the fact of this secret (#1334).`
- `secrets_explaining(*, roster_entry: 'RosterEntry', legend_deed: 'LegendEntry | None' = None, mission_deed: 'MissionDeedRecord | None' = None, scene: 'Scene | None' = None) -> 'QuerySet[SecretKnowledge]' — The secrets a viewer KNOWS that are the hidden truth behind a given act (#1573).`
- `secrets_owned_by(sheet: 'CharacterSheet', *, sort: 'str' = 'level') -> 'QuerySet[Secret]' — The secrets a character **owns** — its own shelf (#1334).`
- `set_secret_act_anchor(secret: 'Secret', *, legend_deed: 'LegendEntry | None' = None, mission_deed: 'MissionDeedRecord | None' = None, scene: 'Scene | None' = None) -> 'Secret' — Set (or clear) the recorded act a secret is the hidden truth behind (#1573).`


## world.skills

### Skill
**Foreign Keys:**
  - trait -> traits.Trait [OneToOne]
**Pointed to by:**
  - specializations <- skills.Specialization
  - character_values <- skills.CharacterSkillValue
  - path_suggestions <- skills.PathSkillSuggestion
  - training_allocations <- skills.TrainingAllocation
  - legend_spreads <- societies.LegendSpread

### Specialization
**Foreign Keys:**
  - parent_skill -> skills.Skill [FK]
**Pointed to by:**
  - character_values <- skills.CharacterSpecializationValue
  - training_allocations <- skills.TrainingAllocation
  - check_type_specializations <- checks.CheckTypeSpecialization

### CharacterSkillValue
**Foreign Keys:**
  - character -> objects.ObjectDB [FK]
  - skill -> skills.Skill [FK]

### CharacterSpecializationValue
**Foreign Keys:**
  - character -> objects.ObjectDB [FK]
  - specialization -> skills.Specialization [FK]

### SkillPointBudget
**Foreign Keys:**
  - teaching_skill -> skills.Skill [FK] (nullable)

### PathSkillSuggestion
**Foreign Keys:**
  - character_path -> classes.Path [FK]
  - skill -> skills.Skill [FK]

### TrainingAllocation
**Foreign Keys:**
  - character -> objects.ObjectDB [FK]
  - skill -> skills.Skill [FK] (nullable)
  - specialization -> skills.Specialization [FK] (nullable)
  - mentor -> scenes.Persona [FK] (nullable)

### Service Functions
- `apply_weekly_rust(trained_skills: 'dict[int, set[int]]') -> 'None' — Apply weekly rust to all untrained skills.`
- `calculate_training_development(allocation: 'TrainingAllocation', *, _teaching_skill: 'Skill | None' = <object object>, _path_levels: 'dict[int, int] | None' = None) -> 'int' — Calculate development points earned from a training allocation.`
- `create_training_allocation(character: 'ObjectDB', ap_amount: 'int', *, skill: 'Skill | None' = None, specialization: 'Specialization | None' = None, mentor: 'Persona | None' = None) -> 'TrainingAllocation' — Create a new training allocation for a character.`
- `get_relationship_tier(character_a: evennia.objects.models.ObjectDB, character_b: evennia.objects.models.ObjectDB) -> int — Highest relationship tier character_a holds toward character_b (0 = none).`
- `get_specialization_value(character: 'ObjectDB', specialization: 'Specialization') -> 'int' — A character's raw value for a specialization, 0 if unowned (#1688).`
- `has_specialization(character: 'ObjectDB', specialization: 'Specialization', *, minimum_rank: 'int' = 1) -> 'bool' — Whether a character owns a specialization at ``minimum_rank`` or better (#1688).`
- `process_weekly_training() -> 'dict[int, set[int]]' — Process all training allocations for the weekly tick.`
- `remove_training_allocation(allocation: 'TrainingAllocation') -> 'None' — Delete a training allocation.`
- `run_weekly_skill_cron() -> 'None' — Run the full weekly skill development cycle.`
- `update_training_allocation(allocation: 'TrainingAllocation', *, ap_amount: 'int | None' = None, mentor: 'Persona | None' = <object object>) -> 'TrainingAllocation' — Update an existing training allocation.`


## world.societies

### Society
**Foreign Keys:**
  - realm -> realms.Realm [FK]
  - current_fashion_style -> items.FashionStyle [FK] (nullable)
**Pointed to by:**
  - connected_beginnings <- character_creation.Beginnings
  - traditions <- magic.Tradition
  - organizations <- societies.Organization
  - reputations <- societies.SocietyReputation
  - known_legend_entries <- societies.LegendEntry
  - heard_legend_spreads <- societies.LegendSpread
  - ranking_displays <- societies.RankingDisplay
  - ranking_band_labels <- societies.RankingBandLabel
  - fame_reaction_lines <- societies.FameReactionLine
  - exposed_secrets <- secrets.Secret
  - dominant_areas <- areas.Area
  - heat_rows <- justice.PersonaHeat
  - fashion_presentations <- items.FashionPresentation
  - facet_momentum <- items.FacetVogueMomentum
  - trendsetters <- items.Trendsetter
  - hosted_events <- events.Event
  - event_invitations <- events.EventInvitation
  - gemits <- narrative.Gemit

### OrganizationType
**Pointed to by:**
  - organizations <- societies.Organization

### Organization
**Foreign Keys:**
  - society -> societies.Society [FK] (nullable)
  - org_type -> societies.OrganizationType [FK]
**Pointed to by:**
  - ranks <- societies.OrganizationRank
  - membership_offers <- societies.OrganizationMembershipOffer
  - memberships <- societies.OrganizationMembership
  - reputations <- societies.OrganizationReputation
  - treasury <- currency.OrganizationTreasury
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
  - secret_victimhoods <- secrets.SecretVictim
  - capture_consequence_effects <- checks.ConsequenceEffect
  - ownership_records <- locations.LocationOwnership
  - tenancies <- locations.LocationTenancy
  - captives <- captivity.Captivity
  - event_invitations <- events.EventInvitation
  - covenant <- covenants.Covenant
  - gemits <- narrative.Gemit
  - npc_roles <- npc_services.NPCRole
  - loan_offers <- npc_services.LoanOfferDetails

### OrganizationRank
**Foreign Keys:**
  - organization -> societies.Organization [FK]
**Pointed to by:**
  - memberships <- societies.OrganizationMembership

### OrganizationMembershipOffer
**Foreign Keys:**
  - organization -> societies.Organization [FK]
  - from_persona -> scenes.Persona [FK]
  - to_persona -> scenes.Persona [FK] (nullable)

### OrganizationMembership
**Foreign Keys:**
  - organization -> societies.Organization [FK]
  - persona -> scenes.Persona [FK]
  - rank -> societies.OrganizationRank [FK] (nullable)

### SocietyReputation
**Foreign Keys:**
  - persona -> scenes.Persona [FK]
  - society -> societies.Society [FK]

### OrganizationReputation
**Foreign Keys:**
  - persona -> scenes.Persona [FK]
  - organization -> societies.Organization [FK]

### LegendSourceType
**Pointed to by:**
  - events <- societies.LegendEvent
  - deeds <- societies.LegendEntry
  - consequence_effects <- checks.ConsequenceEffect

### SpreadingConfig

### SpreadAssistTarget
**Foreign Keys:**
  - window -> scenes.ReactionWindow [OneToOne]
  - legend_entry -> societies.LegendEntry [FK]

### LegendEvent
**Foreign Keys:**
  - source_type -> societies.LegendSourceType [FK]
  - scene -> scenes.Scene [FK] (nullable)
  - story -> stories.Story [FK] (nullable)
  - created_by -> accounts.AccountDB [FK] (nullable)
**Pointed to by:**
  - deeds <- societies.LegendEntry

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
  - audere_majora_crossing <- magic.AudereMajoraCrossing
  - spread_action_requests <- scenes.SceneActionRequest
  - spread_assist_targets <- societies.SpreadAssistTarget
  - spreads <- societies.LegendSpread
  - deed_stories <- societies.LegendDeedStory
  - knowledge_rows <- societies.PersonaDeedKnowledge
  - covenant_credits <- societies.CovenantLegendCredit
  - explaining_secrets <- secrets.Secret
  - crime_tags <- justice.DeedCrimeTag
  - heat_sources <- justice.HeatSource

### LegendSpread
**Foreign Keys:**
  - legend_entry -> societies.LegendEntry [FK]
  - spreader_persona -> scenes.Persona [FK]
  - skill -> skills.Skill [FK] (nullable)
  - scene -> scenes.Scene [FK] (nullable)
  - societies_reached -> societies.Society [M2M]

### LegendDeedStory
**Foreign Keys:**
  - deed -> societies.LegendEntry [FK]
  - author -> scenes.Persona [FK]

### PersonaDeedKnowledge
**Foreign Keys:**
  - persona -> scenes.Persona [FK]
  - deed -> societies.LegendEntry [FK]

### CharacterLegendSummary
**Foreign Keys:**
  - character -> objects.ObjectDB [OneToOne]

### PersonaLegendSummary
**Foreign Keys:**
  - persona -> scenes.Persona [OneToOne]

### RankingDisplay
**Foreign Keys:**
  - display_object -> objects.ObjectDB [OneToOne]
  - scope_society -> societies.Society [FK] (nullable)

### RankingBandLabel
**Foreign Keys:**
  - society -> societies.Society [FK] (nullable)

### FameReactionLine
**Foreign Keys:**
  - room -> evennia_extensions.RoomProfile [FK]
  - society -> societies.Society [FK] (nullable)

### FameReactionCooldown
**Foreign Keys:**
  - persona -> scenes.Persona [FK]
  - room -> evennia_extensions.RoomProfile [FK]

### CovenantLegendCredit
**Foreign Keys:**
  - entry -> societies.LegendEntry [FK]
  - covenant -> covenants.Covenant [FK]

### CovenantLegendSummary
**Foreign Keys:**
  - covenant -> covenants.Covenant [OneToOne]

### PhilosophicalArchetype
**Pointed to by:**
  - auderemajorathreshold_renown_configs <- magic.AudereMajoraThreshold
  - dramaticmomenttype_renown_configs <- magic.DramaticMomentType
  - legend_entries <- societies.LegendEntry
  - secrets <- secrets.Secret
  - mission_awards <- missions.MissionRenownAward

### Service Functions
- `create_legend_event(title: 'str', source_type: 'LegendSourceType', base_value: 'int', personas: 'list[Persona]', *, description: 'str' = '', scene: 'Scene | None' = None, story: 'Story | None' = None, created_by: 'AccountDB | None' = None, crime_kinds: 'list | None' = None, archetypes: 'list | None' = None) -> 'tuple[LegendEvent, list[LegendEntry]]' — Create a shared event and individual deeds for each participant.`
- `create_solo_deed(persona: 'Persona', title: 'str', source_type: 'LegendSourceType', base_value: 'int', *, description: 'str' = '', scene: 'Scene | None' = None, story: 'Story | None' = None, crime_kinds: 'list | None' = None, archetypes: 'list | None' = None) -> 'LegendEntry' — Create a legend deed not tied to a shared event.`
- `credit_engaged_covenants(*, entry: 'LegendEntry') -> 'list[CovenantLegendCredit]' — Snapshot the persona's currently-engaged covenants and create credit rows.`
- `get_character_legend_total(character: 'ObjectDB') -> 'int' — Fast lookup of a character's total legend from materialized view.`
- `get_character_role_legend(*, character_sheet: 'CharacterSheet', role: 'CovenantRole', covenant_ids: 'list[int] | None' = None) -> 'int' — Sum the legend this character earned that was credited to covenants where they held ``role``.`
- `get_covenant_legend_total(covenant: 'Covenant') -> 'int' — Return the covenant's total legend from the materialized view.`
- `get_persona_legend_total(persona: 'Persona') -> 'int' — Per-persona legend lookup from materialized view.`
- `refresh_legend_views() -> None — Refresh all legend materialized views concurrently.`
- `spread_deed(deed: 'LegendEntry', spreader_persona: 'Persona', value_added: 'int', *, description: 'str' = '', method: 'str' = '', skill: 'Skill | None' = None, audience_factor: 'Decimal' = Decimal('1.0'), scene: 'Scene | None' = None, societies_reached: 'list[Society] | None' = None) -> 'LegendSpread' — Record a spreading action and add legend value, clamped to capacity.`
- `spread_event(event: 'LegendEvent', spreader_persona: 'Persona', value_per_deed: 'int', *, description: 'str' = '', method: 'str' = '', skill: 'Skill | None' = None, audience_factor: 'Decimal' = Decimal('1.0'), scene: 'Scene | None' = None, societies_reached: 'list[Society] | None' = None) -> 'list[LegendSpread]' — Spread all active deeds linked to an event at once.`


## world.stories

### TrustCategory
**Foreign Keys:**
  - created_by -> accounts.AccountDB [FK] (nullable)
**Pointed to by:**
  - story_set <- stories.Story
  - storytrustrequirement_set <- stories.StoryTrustRequirement
  - playertrust_set <- stories.PlayerTrust
  - player_trust_levels <- stories.PlayerTrustLevel
  - storyfeedback_set <- stories.StoryFeedback
  - trustcategoryfeedbackrating_set <- stories.TrustCategoryFeedbackRating
  - gated_distinctions <- distinctions.Distinction

### Story
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK] (nullable)
  - created_in_era -> stories.Era [FK] (nullable)
  - covenant -> covenants.Covenant [FK] (nullable)
  - primary_table -> gm.GMTable [FK] (nullable)
  - owners -> accounts.AccountDB [M2M]
  - active_gms -> gm.GMProfile [M2M]
  - required_trust_categories -> stories.TrustCategory [M2M]
**Pointed to by:**
  - trust_requirements <- stories.StoryTrustRequirement
  - participants <- stories.StoryParticipation
  - chapters <- stories.Chapter
  - feedback <- stories.StoryFeedback
  - referenced_by_beats <- stories.Beat
  - group_progress_records <- stories.GroupStoryProgress
  - global_progress <- stories.GlobalStoryProgress
  - progress_records <- stories.StoryProgress
  - notes <- stories.StoryNote
  - gm_offers <- stories.StoryGMOffer
  - bulletin_posts <- stories.TableBulletinPost
  - legend_events <- societies.LegendEvent
  - legend_entries <- societies.LegendEntry
  - ended_campaigns <- covenants.Covenant
  - battles <- battles.Battle
  - narrative_messages <- narrative.NarrativeMessage
  - gemits <- narrative.Gemit
  - muted_by <- narrative.UserStoryMute

### StoryTrustRequirement
**Foreign Keys:**
  - story -> stories.Story [FK]
  - trust_category -> stories.TrustCategory [FK]
  - created_by -> accounts.AccountDB [FK] (nullable)

### StoryParticipation
**Foreign Keys:**
  - story -> stories.Story [FK]
  - character -> objects.ObjectDB [FK]

### Chapter
**Foreign Keys:**
  - story -> stories.Story [FK]
**Pointed to by:**
  - episodes <- stories.Episode

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

### EpisodeScene
**Foreign Keys:**
  - episode -> stories.Episode [FK]
  - scene -> scenes.Scene [FK]

### PlayerTrust
**Foreign Keys:**
  - account -> accounts.AccountDB [OneToOne]
  - trust_categories -> stories.TrustCategory [M2M]
**Pointed to by:**
  - trust_levels <- stories.PlayerTrustLevel

### PlayerTrustLevel
**Foreign Keys:**
  - player_trust -> stories.PlayerTrust [FK]
  - trust_category -> stories.TrustCategory [FK]

### StoryFeedback
**Foreign Keys:**
  - story -> stories.Story [FK]
  - reviewer -> accounts.AccountDB [FK]
  - reviewed_player -> accounts.AccountDB [FK]
  - trust_categories -> stories.TrustCategory [M2M]
**Pointed to by:**
  - category_ratings <- stories.TrustCategoryFeedbackRating

### TrustCategoryFeedbackRating
**Foreign Keys:**
  - feedback -> stories.StoryFeedback [FK]
  - trust_category -> stories.TrustCategory [FK]

### Era
**Pointed to by:**
  - stories_created_in_era <- stories.Story
  - aggregate_contributions <- stories.AggregateBeatContribution
  - beat_completions <- stories.BeatCompletion
  - episode_resolutions <- stories.EpisodeResolution
  - gemits <- narrative.Gemit

### Transition
**Foreign Keys:**
  - source_episode -> stories.Episode [FK]
  - target_episode -> stories.Episode [FK] (nullable)
**Pointed to by:**
  - required_outcomes <- stories.TransitionRequiredOutcome
  - resolutions_using <- stories.EpisodeResolution

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
  - gating_for_episodes <- stories.EpisodeProgressionRequirement
  - routing_for_transitions <- stories.TransitionRequiredOutcome
  - aggregate_contributions <- stories.AggregateBeatContribution
  - completions <- stories.BeatCompletion
  - assistant_claims <- stories.AssistantGMClaim
  - stakes <- stories.Stake
  - stake_activations <- stories.StakeContractActivation
  - resolving_encounters <- combat.CombatEncounter

### EpisodeProgressionRequirement
**Foreign Keys:**
  - episode -> stories.Episode [FK]
  - beat -> stories.Beat [FK]

### TransitionRequiredOutcome
**Foreign Keys:**
  - transition -> stories.Transition [FK]
  - beat -> stories.Beat [FK]
  - stake -> stories.Stake [FK] (nullable)

### AggregateBeatContribution
**Foreign Keys:**
  - beat -> stories.Beat [FK]
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - roster_entry -> roster.RosterEntry [FK] (nullable)
  - era -> stories.Era [FK] (nullable)

### BeatCompletion
**Foreign Keys:**
  - beat -> stories.Beat [FK]
  - character_sheet -> character_sheets.CharacterSheet [FK] (nullable)
  - gm_table -> gm.GMTable [FK] (nullable)
  - roster_entry -> roster.RosterEntry [FK] (nullable)
  - outcome_tier -> traits.CheckOutcome [FK] (nullable)
  - era -> stories.Era [FK] (nullable)
**Pointed to by:**
  - narrative_messages <- narrative.NarrativeMessage

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

### GroupStoryProgress
**Foreign Keys:**
  - story -> stories.Story [FK]
  - gm_table -> gm.GMTable [FK]
  - current_episode -> stories.Episode [FK] (nullable)

### GlobalStoryProgress
**Foreign Keys:**
  - story -> stories.Story [OneToOne]
  - current_episode -> stories.Episode [FK] (nullable)

### StoryProgress
**Foreign Keys:**
  - story -> stories.Story [FK]
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - current_episode -> stories.Episode [FK] (nullable)

### StoryNote
**Foreign Keys:**
  - story -> stories.Story [FK]
  - author_account -> accounts.AccountDB [FK] (nullable)

### AssistantGMClaim
**Foreign Keys:**
  - beat -> stories.Beat [FK]
  - assistant_gm -> gm.GMProfile [FK]
  - approved_by -> gm.GMProfile [FK] (nullable)

### SessionRequest
**Foreign Keys:**
  - episode -> stories.Episode [FK]
  - event -> events.Event [FK] (nullable)
  - assigned_gm -> gm.GMProfile [FK] (nullable)
  - initiated_by_account -> accounts.AccountDB [FK] (nullable)

### StoryGMOffer
**Foreign Keys:**
  - story -> stories.Story [FK]
  - offered_to -> gm.GMProfile [FK]
  - offered_by_account -> accounts.AccountDB [FK]

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

### RiskCalibration

### StakeTemplate
**Pointed to by:**
  - stakes <- stories.Stake

### Stake
**Foreign Keys:**
  - beat -> stories.Beat [FK]
  - template -> stories.StakeTemplate [FK] (nullable)
  - subject_sheet -> character_sheets.CharacterSheet [FK] (nullable)
  - subject_item -> items.ItemInstance [FK] (nullable)
  - subject_society -> societies.Society [FK] (nullable)
  - subject_organization -> societies.Organization [FK] (nullable)
**Pointed to by:**
  - routing_for_transitions <- stories.TransitionRequiredOutcome
  - resolutions <- stories.StakeResolution
  - outcomes <- stories.StakeOutcome

### StakeResolution
**Foreign Keys:**
  - stake -> stories.Stake [FK]
  - consequence_pool -> actions.ConsequencePool [FK] (nullable)
**Pointed to by:**
  - reward_lines <- stories.StakeRewardLine

### StakeRewardLine
**Foreign Keys:**
  - resolution -> stories.StakeResolution [FK]
  - resonance -> magic.Resonance [FK] (nullable)

### StakeContractActivation
**Foreign Keys:**
  - beat -> stories.Beat [FK]
**Pointed to by:**
  - stake_outcomes <- stories.StakeOutcome

### StakeOutcome
**Foreign Keys:**
  - stake -> stories.Stake [FK]
  - activation -> stories.StakeContractActivation [FK] (nullable)
  - resolution -> stories.StakeResolution [FK] (nullable)
  - resolved_by -> gm.GMProfile [FK] (nullable)


## world.traits

### Trait
**Pointed to by:**
  - rank_descriptions <- traits.TraitRankDescription
  - character_values <- traits.CharacterTraitValue
  - skill <- skills.Skill
  - classes_requiring_trait <- classes.CharacterClass
  - development_points <- progression.DevelopmentPoints
  - development_transactions <- progression.DevelopmentTransaction
  - weekly_skill_usage <- progression.WeeklySkillUsage
  - xp_costs <- progression.TraitXPCost
  - rating_unlocks <- progression.TraitRatingUnlock
  - trait_requirements <- progression.TraitRequirement
  - anchored_threads <- magic.Thread
  - thread_weaving_unlocks <- magic.ThreadWeavingUnlock
  - modifier_targets <- mechanics.ModifierTarget
  - capability_derivations <- mechanics.TraitCapabilityDerivation
  - check_type_traits <- checks.CheckTypeTrait

### TraitRankDescription
**Foreign Keys:**
  - trait -> traits.Trait [FK]

### CharacterTraitValue
**Foreign Keys:**
  - character -> objects.ObjectDB [FK]
  - trait -> traits.Trait [FK]

### PointConversionRange

### CheckRank

### CheckOutcome
**Pointed to by:**
  - resultchartoutcome_set <- traits.ResultChartOutcome
  - technique_warp_modifier <- magic.TechniqueOutcomeModifier
  - anima_ritual_performances <- magic.AnimaRitualPerformance
  - beat_completions <- stories.BeatCompletion
  - treatment_attempts <- conditions.TreatmentAttempt
  - challenge_records <- mechanics.CharacterChallengeRecord
  - consequences <- checks.Consequence
  - encounter_outcome_mappings <- combat.EncounterOutcomeMapping
  - battle_outcome_mappings <- battles.BattleOutcomeMapping
  - project_outcomes <- projects.Project
  - project_contributions <- projects.Contribution

### ResultChart
**Pointed to by:**
  - outcomes <- traits.ResultChartOutcome

### ResultChartOutcome
**Foreign Keys:**
  - chart -> traits.ResultChart [FK]
  - outcome -> traits.CheckOutcome [FK]


## world.weather

### Climate
**Foreign Keys:**
  - codex_subject -> codex.CodexSubject [FK] (nullable)
**Pointed to by:**
  - areas <- areas.Area

### WeatherType
**Foreign Keys:**
  - codex_subject -> codex.CodexSubject [FK] (nullable)
**Pointed to by:**
  - conjuring_techniques <- magic.Technique
  - exposures <- weather.WeatherTypeExposure
  - emits <- weather.WeatherEmit
  - active_in_regions <- weather.RegionWeatherState
  - feast_days <- weather.FeastDay
  - overriding_battles <- battles.Battle
  - overriding_battle_places <- battles.BattlePlace
  - battle_property_effects <- battles.WeatherTypePropertyEffect
  - battle_capability_challenges <- battles.WeatherTypeCapabilityChallenge

### WeatherTypeExposure
**Foreign Keys:**
  - weather_type -> weather.WeatherType [FK]

### WeatherEmit
**Foreign Keys:**
  - weather_type -> weather.WeatherType [FK]

### RegionWeatherState
**Foreign Keys:**
  - area -> areas.Area [OneToOne]
  - weather_type -> weather.WeatherType [FK]

### FeastDay
**Foreign Keys:**
  - weather_type -> weather.WeatherType [FK]

### Service Functions
- `apply_weather_exposure(state: 'RegionWeatherState') -> 'None' — Re-materialize a region's weather as decaying source-tagged cascade modifiers (#1522).`
- `clear_region_weather(area: 'Area') -> 'None' — Remove a region's weather state and its weather-sourced exposure modifiers (#1522).`
- `climate_exposure_base(climate: 'Climate | None', stat_key: 'StatKey', *, temperature_shift: 'int' = 0) -> 'int' — A climate's contribution to one exposure axis, before local modifiers/floor (#1522).`
- `current_conditions(room: 'DefaultObject') -> 'ConditionsSummary' — IC time + the weather holding at a room, for the ``time`` command and frontend (#1522).`
- `current_temperature_shift(*, real_now: 'datetime | None' = None) -> 'int' — The current global seasonal temperature shift from the IC clock (#1522).`
- `eligible_weather_types(area: 'Area | None') -> 'list[WeatherType]' — Automated, active weather types whose temperature band fits the region's climate (#1522).`
- `get_effective_climate(area: 'Area | None') -> 'Climate | None' — Walk up the area hierarchy to the nearest climate assignment (#1522).`
- `get_effective_weather(area: 'Area | None') -> 'RegionWeatherState | None' — Walk up the area hierarchy to the nearest current-weather state (#1522).`
- `get_ic_now(*, real_now: datetime.datetime | None = None) -> datetime.datetime | None — Return the current IC datetime, or None if no clock exists.`
- `get_ic_phase(*, real_now: datetime.datetime | None = None) -> world.game_clock.constants.TimePhase | None — Return the current time-of-day phase, or None if no clock exists.`
- `get_ic_season(*, real_now: datetime.datetime | None = None) -> world.game_clock.constants.Season | None — Return the current IC season, or None if no clock exists.`
- `month_temperature_shift(month: 'int') -> 'int' — The global temperature shift for an IC month (1–12); 0 if out of range.`
- `roll_region_weather(area: 'Area', *, weather_type: 'WeatherType | None' = None) -> 'RegionWeatherState | None' — Set (or roll) a region's current weather and re-apply its exposure modifiers (#1522).`
- `select_weather_emit(area: 'Area | None', *, season: 'Season | None' = None, phase: 'TimePhase | None' = None) -> 'WeatherEmit | None' — Pick a weighted-random atmospheric emit for a region's current weather (#1522).`
- `special_weather_for_today(*, real_now: 'datetime | None' = None) -> 'WeatherType | None' — The special weather forced by a feast day on the current IC date, if any (#1522).`

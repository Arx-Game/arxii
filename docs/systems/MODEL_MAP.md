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
  - mishap_tiers <- magic.MishapPoolTier
  - condition_stages <- conditions.ConditionStage
  - context_attachments <- mechanics.ContextConsequencePool

### ConsequencePoolEntry
**Foreign Keys:**
  - pool -> actions.ConsequencePool [FK]
  - consequence -> checks.Consequence [FK]

### ActionTemplate
**Foreign Keys:**
  - check_type -> checks.CheckType [FK]
  - consequence_pool -> actions.ConsequencePool [FK] (nullable)
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

### ActionEnhancement
**Foreign Keys:**
  - distinction -> distinctions.Distinction [FK] (nullable)
  - condition -> conditions.ConditionTemplate [FK] (nullable)
  - technique -> magic.Technique [FK] (nullable)
**Pointed to by:**
  - modifykwargsconfig_configs <- actions.ModifyKwargsConfig
  - addmodifierconfig_configs <- actions.AddModifierConfig
  - conditiononcheckconfig_configs <- actions.ConditionOnCheckConfig

### Service Functions
- `advance_resolution(pending: 'PendingActionResolution', context: 'ResolutionContext', player_decision: 'str | None' = None) -> 'PendingActionResolution' — Resume a paused pipeline after player decision.`
- `apply_resolution(pending: 'PendingResolution', context: 'ResolutionContext') -> 'list[AppliedEffect]' — Apply all effects from the selected consequence.`
- `get_effective_consequences(pool: 'ConsequencePool') -> 'list[WeightedConsequence]' — Resolve pool inheritance into a flat list of weighted consequences.`
- `perform_check(character: 'ObjectDB', check_type: 'CheckType', target_difficulty: int = 0, extra_modifiers: int = 0, effort_level: str | None = None, fatigue_penalty: int = 0) -> world.checks.types.CheckResult — Main check resolution function.`
- `resolve_scene_action(*, character: 'ObjectDB', action_template: 'ActionTemplate | None', action_key: 'str', difficulty: 'int') -> 'SceneActionResult' — Resolve a scene-based action check using an ActionTemplate.`
- `select_consequence_from_result(character: 'ObjectDB', check_result: 'CheckResult', consequences: 'list[WeightedConsequence]') -> 'PendingResolution' — Select a consequence using an existing check result.`
- `start_action_resolution(character: 'ObjectDB', template: 'ActionTemplate', target_difficulty: 'int', context: 'ResolutionContext') -> 'PendingActionResolution' — Start an action resolution pipeline and run it to completion or pause.`


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
  - modifier_target -> mechanics.ModifierTarget [OneToOne] (nullable)
  - prerequisite -> mechanics.Prerequisite [FK] (nullable)
**Pointed to by:**
  - technique_grants <- magic.TechniqueCapabilityGrant
  - thread_pull_effects <- magic.ThreadPullEffect
  - conditioncapabilityeffect_set <- conditions.ConditionCapabilityEffect
  - applications <- mechanics.Application
  - trait_derivations <- mechanics.TraitCapabilityDerivation
  - blocking_challenges <- mechanics.ChallengeTemplate
  - combat_pull_grants <- combat.CombatPullResolvedEffect

### DamageType
**Foreign Keys:**
  - modifier_target -> mechanics.ModifierTarget [OneToOne] (nullable)
  - resonance -> magic.Resonance [OneToOne] (nullable)
**Pointed to by:**
  - alteration_weaknesses <- magic.MagicalAlterationTemplate
  - conditionresistancemodifier_set <- conditions.ConditionResistanceModifier
  - conditiondamageovertime_set <- conditions.ConditionDamageOverTime
  - conditiondamageinteraction_set <- conditions.ConditionDamageInteraction
  - consequence_effects <- checks.ConsequenceEffect

### ConditionTemplate
**Foreign Keys:**
  - magical_alteration -> magic.MagicalAlterationTemplate [OneToOne] (nullable)
  - category -> conditions.ConditionCategory [FK]
  - cure_check_type -> checks.CheckType [FK] (nullable)
**Pointed to by:**
  - action_enhancements <- actions.ActionEnhancement
  - stages <- conditions.ConditionStage
  - conditioncapabilityeffect_set <- conditions.ConditionCapabilityEffect
  - conditioncheckmodifier_set <- conditions.ConditionCheckModifier
  - conditionresistancemodifier_set <- conditions.ConditionResistanceModifier
  - conditiondamageovertime_set <- conditions.ConditionDamageOverTime
  - damage_interactions <- conditions.ConditionDamageInteraction
  - applied_by_damage_interaction <- conditions.ConditionDamageInteraction
  - interactions_as_primary <- conditions.ConditionConditionInteraction
  - interactions_as_secondary <- conditions.ConditionConditionInteraction
  - created_by_interaction <- conditions.ConditionConditionInteraction
  - conditioninstance_set <- conditions.ConditionInstance
  - consequence_effects <- checks.ConsequenceEffect
  - threat_pool_entries <- combat.ThreatPoolEntry

### ConditionStage
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK]
  - resist_check_type -> checks.CheckType [FK] (nullable)
  - consequence_pool -> actions.ConsequencePool [FK] (nullable)
**Pointed to by:**
  - stage_triggers <- flows.Trigger
  - auderethreshold_set <- magic.AudereThreshold
  - conditioncapabilityeffect_set <- conditions.ConditionCapabilityEffect
  - conditioncheckmodifier_set <- conditions.ConditionCheckModifier
  - conditionresistancemodifier_set <- conditions.ConditionResistanceModifier
  - conditiondamageovertime_set <- conditions.ConditionDamageOverTime
  - conditioninstance_set <- conditions.ConditionInstance

### ConditionCapabilityEffect
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK] (nullable)
  - stage -> conditions.ConditionStage [FK] (nullable)
  - capability -> conditions.CapabilityType [FK]

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
  - granted_properties <- mechanics.ObjectProperty


## evennia_extensions

### PlayerData
**Foreign Keys:**
  - artist_profile -> evennia_extensions.Artist [OneToOne] (nullable)
  - account -> accounts.AccountDB [OneToOne]
  - profile_picture -> evennia_extensions.PlayerMedia [FK] (nullable)
**Pointed to by:**
  - applications <- roster.RosterApplication
  - reviewed_applications <- roster.RosterApplication
  - tenures <- roster.RosterTenure
  - approved_tenures <- roster.RosterTenure
  - media <- evennia_extensions.PlayerMedia
  - allow_list <- evennia_extensions.PlayerAllowList
  - allowed_by <- evennia_extensions.PlayerAllowList
  - block_list <- evennia_extensions.PlayerBlockList
  - blocked_by <- evennia_extensions.PlayerBlockList

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

### PlayerBlockList
**Foreign Keys:**
  - owner -> evennia_extensions.PlayerData [FK]
  - blocked_player -> evennia_extensions.PlayerData [FK]

### RoomProfile
**Foreign Keys:**
  - objectdb -> objects.ObjectDB [OneToOne]
  - area -> areas.Area [FK] (nullable)
**Pointed to by:**
  - events <- events.Event


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

### Trigger
**Foreign Keys:**
  - trigger_definition -> flows.TriggerDefinition [FK]
  - obj -> objects.ObjectDB [FK]
  - source_condition -> conditions.ConditionInstance [FK]
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
**Pointed to by:**
  - beginning_traditions <- character_creation.BeginningTradition
  - drafts <- character_creation.CharacterDraft
  - codex_grants <- codex.BeginningsCodexGrant

### BeginningTradition
**Foreign Keys:**
  - beginning -> character_creation.Beginnings [FK]
  - tradition -> magic.Tradition [FK]
  - required_distinction -> distinctions.Distinction [FK] (nullable)

### CharacterDraft
**Foreign Keys:**
  - application -> character_creation.DraftApplication [OneToOne] (nullable)
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
- `calculate_weight(height_inches: int, build: world.forms.models.Build) -> int — Calculate weight in pounds from height and build.`
- `can_create_character(account: 'AbstractBaseUser | AnonymousUser') -> 'tuple[bool, str]' — Check if an account can create a new character.`
- `claim_application(application: 'DraftApplication', *, reviewer: 'AbstractBaseUser | AnonymousUser') -> 'None' — Claim a submitted application for staff review.`
- `create_character_with_sheet(*, character_key: 'str', primary_persona_name: 'str', typeclass: 'str' = 'typeclasses.characters.Character', home: 'ObjectDB | None' = None, **sheet_kwargs: 'Any') -> 'tuple[ObjectDB, CharacterSheet, Persona]' — Atomically create a Character + CharacterSheet + PRIMARY Persona.`
- `deny_application(application: 'DraftApplication', *, reviewer: 'AbstractBaseUser | AnonymousUser', comment: 'str') -> 'None' — Deny an application.`
- `finalize_character(draft: 'CharacterDraft', *, add_to_roster: 'bool' = False) -> 'ObjectDB' — Create a Character from a completed CharacterDraft.`
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
  - character_sheets <- character_sheets.CharacterSheet
  - beginnings <- character_creation.Beginnings

### CharacterSheet
**Foreign Keys:**
  - roster_entry -> roster.RosterEntry [OneToOne] (nullable)
  - anima_ritual -> magic.CharacterAnimaRitual [OneToOne] (nullable)
  - motif -> magic.Motif [OneToOne] (nullable)
  - weekly_journal_xp -> journals.WeeklyJournalXP [OneToOne] (nullable)
  - fatigue -> fatigue.FatiguePool [OneToOne] (nullable)
  - vitals -> vitals.CharacterVitals [OneToOne] (nullable)
  - character -> objects.ObjectDB [OneToOne]
  - build -> forms.Build [FK] (nullable)
  - gender -> character_sheets.Gender [FK] (nullable)
  - pronouns -> character_sheets.Pronouns [FK] (nullable)
  - heritage -> character_sheets.Heritage [FK] (nullable)
  - origin_realm -> realms.Realm [FK] (nullable)
  - species -> species.Species [FK] (nullable)
  - family -> roster.Family [FK] (nullable)
  - tarot_card -> tarot.TarotCard [FK] (nullable)
**Pointed to by:**
  - characteristic_values <- character_sheets.CharacterSheetValue
  - development_points <- progression.DevelopmentPoints
  - development_transactions <- progression.DevelopmentTransaction
  - weekly_skill_usage <- progression.WeeklySkillUsage
  - resonances <- magic.CharacterResonance
  - created_gifts <- magic.Gift
  - character_gifts <- magic.CharacterGift
  - character_traditions <- magic.CharacterTradition
  - anima_ritual_participations <- magic.AnimaRitualPerformance
  - authored_techniques <- magic.Technique
  - character_techniques <- magic.CharacterTechnique
  - character_facets <- magic.CharacterFacet
  - affinity_totals <- magic.CharacterAffinityTotal
  - reincarnations <- magic.Reincarnation
  - pending_alterations <- magic.PendingAlteration
  - alteration_events <- magic.MagicalAlterationEvent
  - threads <- magic.Thread
  - thread_weaving_unlocks <- magic.CharacterThreadWeavingUnlock
  - personas <- scenes.Persona
  - persona_discoveries <- scenes.PersonaDiscovery
  - character_stories <- stories.Story
  - beat_completions <- stories.BeatCompletion
  - episode_resolutions <- stories.EpisodeResolution
  - story_progress <- stories.StoryProgress
  - modifiers <- mechanics.CharacterModifier
  - relationships_as_source <- relationships.CharacterRelationship
  - relationships_as_target <- relationships.CharacterRelationship
  - relationshipupdate_set <- relationships.RelationshipUpdate
  - relationshipdevelopment_set <- relationships.RelationshipDevelopment
  - relationshipcapstone_set <- relationships.RelationshipCapstone
  - relationshipchange_set <- relationships.RelationshipChange
  - stat_trackers <- achievements.StatTracker
  - achievements <- achievements.CharacterAchievement
  - owned_instances <- instances.InstancedRoom
  - journal_entries <- journals.JournalEntry
  - combo_learnings <- combat.ComboLearning
  - combat_participations <- combat.CombatParticipant

### Characteristic
**Pointed to by:**
  - values <- character_sheets.CharacteristicValue

### CharacteristicValue
**Foreign Keys:**
  - characteristic -> character_sheets.Characteristic [FK]
**Pointed to by:**
  - character_sheets <- character_sheets.CharacterSheetValue

### CharacterSheetValue
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - characteristic_value -> character_sheets.CharacteristicValue [FK]

### Gender
**Pointed to by:**
  - character_sheets <- character_sheets.CharacterSheet
  - drafts <- character_creation.CharacterDraft

### Pronouns
**Pointed to by:**
  - character_sheets <- character_sheets.CharacterSheet

### Service Functions
- `can_edit_character_sheet(user: 'AbstractBaseUser | AnonymousUser', roster_entry: 'RosterEntry') -> 'bool' — True if the user is the original creator (player_number=1) or staff.`
- `create_character_with_sheet(*, character_key: 'str', primary_persona_name: 'str', typeclass: 'str' = 'typeclasses.characters.Character', home: 'ObjectDB | None' = None, **sheet_kwargs: 'Any') -> 'tuple[ObjectDB, CharacterSheet, Persona]' — Atomically create a Character + CharacterSheet + PRIMARY Persona.`
- `create_object(*args, **kwargs) — Create a new in-game object.`


## world.checks

### CheckCategory
**Pointed to by:**
  - check_types <- checks.CheckType

### CheckType
**Foreign Keys:**
  - modifier_target -> mechanics.ModifierTarget [OneToOne] (nullable)
  - category -> checks.CheckCategory [FK]
**Pointed to by:**
  - action_templates <- actions.ActionTemplate
  - action_template_gates <- actions.ActionTemplateGate
  - soulfrayconfig_set <- magic.SoulfrayConfig
  - cures_conditions <- conditions.ConditionTemplate
  - conditionstage_set <- conditions.ConditionStage
  - conditioncheckmodifier_set <- conditions.ConditionCheckModifier
  - challenge_approaches <- mechanics.ChallengeApproach
  - context_consequence_pools <- mechanics.ContextConsequencePool
  - traits <- checks.CheckTypeTrait
  - aspects <- checks.CheckTypeAspect

### CheckTypeTrait
**Foreign Keys:**
  - check_type -> checks.CheckType [FK]
  - trait -> traits.Trait [FK]

### CheckTypeAspect
**Foreign Keys:**
  - check_type -> checks.CheckType [FK]
  - aspect -> classes.Aspect [FK]

### Consequence
**Foreign Keys:**
  - outcome_tier -> traits.CheckOutcome [FK]
**Pointed to by:**
  - pool_entries <- actions.ConsequencePoolEntry
  - challenge_templates <- mechanics.ChallengeTemplate
  - challenge_template_consequences <- mechanics.ChallengeTemplateConsequence
  - approach_consequences <- mechanics.ApproachConsequence
  - challenge_records <- mechanics.CharacterChallengeRecord
  - effects <- checks.ConsequenceEffect

### ConsequenceEffect
**Foreign Keys:**
  - consequence -> checks.Consequence [FK]
  - condition_template -> conditions.ConditionTemplate [FK] (nullable)
  - property -> mechanics.Property [FK] (nullable)
  - damage_type -> conditions.DamageType [FK] (nullable)
  - flow_definition -> flows.FlowDefinition [FK] (nullable)
  - codex_entry -> codex.CodexEntry [FK] (nullable)

### Service Functions
- `cast(typ, val) — Cast a value to a type.`
- `chart_has_success_outcomes(rank_difference: int) -> bool — Check if the ResultChart for this rank difference has any success outcomes.`
- `get_rollmod(character: 'ObjectDB') -> int — Sum character.sheet_data.rollmod + character.account.player_data.rollmod.`
- `perform_check(character: 'ObjectDB', check_type: 'CheckType', target_difficulty: int = 0, extra_modifiers: int = 0, effort_level: str | None = None, fatigue_penalty: int = 0) -> world.checks.types.CheckResult — Main check resolution function.`
- `preview_check_difficulty(character: 'ObjectDB', check_type: 'CheckType', target_difficulty: int = 0, extra_modifiers: int = 0) -> int — Preview the rank difference for a check without rolling.`


## world.classes

### Path
**Pointed to by:**
  - skill_suggestions <- skills.PathSkillSuggestion
  - drafts <- character_creation.CharacterDraft
  - child_paths <- classes.Path
  - path_aspects <- classes.PathAspect
  - character_selections <- progression.CharacterPathHistory
  - allowed_styles <- magic.TechniqueStyle
  - thread_weaving_unlocks <- magic.ThreadWeavingUnlock
  - codex_grants <- codex.PathCodexGrant

### CharacterClass
**Pointed to by:**
  - character_assignments <- classes.CharacterClassLevel
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

### Aspect
**Pointed to by:**
  - path_aspects <- classes.PathAspect
  - check_type_aspects <- checks.CheckTypeAspect

### PathAspect
**Foreign Keys:**
  - character_path -> classes.Path [FK]
  - aspect -> classes.Aspect [FK]


## world.codex

### CodexCategory
**Pointed to by:**
  - subjects <- codex.CodexSubject

### CodexSubject
**Foreign Keys:**
  - breadcrumb_cache -> codex.CodexSubjectBreadcrumb [OneToOne] (nullable)
  - category -> codex.CodexCategory [FK]
  - parent -> codex.CodexSubject [FK] (nullable)
**Pointed to by:**
  - children <- codex.CodexSubject
  - entries <- codex.CodexEntry

### CodexSubjectBreadcrumb
**Foreign Keys:**
  - subject -> codex.CodexSubject [OneToOne]

### CodexEntry
**Foreign Keys:**
  - subject -> codex.CodexSubject [FK]
  - modifier_target -> mechanics.ModifierTarget [OneToOne] (nullable)
**Pointed to by:**
  - unlocks <- codex.CodexEntry
  - character_knowledge <- codex.CharacterCodexKnowledge
  - clues <- codex.CodexClue
  - teaching_offers <- codex.CodexTeachingOffer
  - beginnings_grants <- codex.BeginningsCodexGrant
  - path_grants <- codex.PathCodexGrant
  - distinction_grants <- codex.DistinctionCodexGrant
  - tradition_grants <- codex.TraditionCodexGrant
  - consequence_effects <- checks.ConsequenceEffect

### CharacterCodexKnowledge
**Foreign Keys:**
  - roster_entry -> roster.RosterEntry [FK]
  - entry -> codex.CodexEntry [FK]
  - learned_from -> roster.RosterTenure [FK] (nullable)

### CodexClue
**Foreign Keys:**
  - entry -> codex.CodexEntry [FK]
**Pointed to by:**
  - character_knowledge <- codex.CharacterClueKnowledge

### CharacterClueKnowledge
**Foreign Keys:**
  - roster_entry -> roster.RosterEntry [FK]
  - clue -> codex.CodexClue [FK]

### CodexTeachingOffer
**Foreign Keys:**
  - teacher -> roster.RosterTenure [FK]
  - entry -> codex.CodexEntry [FK]

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
  - modifier_target -> mechanics.ModifierTarget [OneToOne] (nullable)
  - prerequisite -> mechanics.Prerequisite [FK] (nullable)
**Pointed to by:**
  - technique_grants <- magic.TechniqueCapabilityGrant
  - thread_pull_effects <- magic.ThreadPullEffect
  - conditioncapabilityeffect_set <- conditions.ConditionCapabilityEffect
  - applications <- mechanics.Application
  - trait_derivations <- mechanics.TraitCapabilityDerivation
  - blocking_challenges <- mechanics.ChallengeTemplate
  - combat_pull_grants <- combat.CombatPullResolvedEffect

### DamageType
**Foreign Keys:**
  - modifier_target -> mechanics.ModifierTarget [OneToOne] (nullable)
  - resonance -> magic.Resonance [OneToOne] (nullable)
**Pointed to by:**
  - alteration_weaknesses <- magic.MagicalAlterationTemplate
  - conditionresistancemodifier_set <- conditions.ConditionResistanceModifier
  - conditiondamageovertime_set <- conditions.ConditionDamageOverTime
  - conditiondamageinteraction_set <- conditions.ConditionDamageInteraction
  - consequence_effects <- checks.ConsequenceEffect

### ConditionTemplate
**Foreign Keys:**
  - magical_alteration -> magic.MagicalAlterationTemplate [OneToOne] (nullable)
  - category -> conditions.ConditionCategory [FK]
  - cure_check_type -> checks.CheckType [FK] (nullable)
**Pointed to by:**
  - action_enhancements <- actions.ActionEnhancement
  - stages <- conditions.ConditionStage
  - conditioncapabilityeffect_set <- conditions.ConditionCapabilityEffect
  - conditioncheckmodifier_set <- conditions.ConditionCheckModifier
  - conditionresistancemodifier_set <- conditions.ConditionResistanceModifier
  - conditiondamageovertime_set <- conditions.ConditionDamageOverTime
  - damage_interactions <- conditions.ConditionDamageInteraction
  - applied_by_damage_interaction <- conditions.ConditionDamageInteraction
  - interactions_as_primary <- conditions.ConditionConditionInteraction
  - interactions_as_secondary <- conditions.ConditionConditionInteraction
  - created_by_interaction <- conditions.ConditionConditionInteraction
  - conditioninstance_set <- conditions.ConditionInstance
  - consequence_effects <- checks.ConsequenceEffect
  - threat_pool_entries <- combat.ThreatPoolEntry

### ConditionStage
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK]
  - resist_check_type -> checks.CheckType [FK] (nullable)
  - consequence_pool -> actions.ConsequencePool [FK] (nullable)
**Pointed to by:**
  - stage_triggers <- flows.Trigger
  - auderethreshold_set <- magic.AudereThreshold
  - conditioncapabilityeffect_set <- conditions.ConditionCapabilityEffect
  - conditioncheckmodifier_set <- conditions.ConditionCheckModifier
  - conditionresistancemodifier_set <- conditions.ConditionResistanceModifier
  - conditiondamageovertime_set <- conditions.ConditionDamageOverTime
  - conditioninstance_set <- conditions.ConditionInstance

### ConditionCapabilityEffect
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK] (nullable)
  - stage -> conditions.ConditionStage [FK] (nullable)
  - capability -> conditions.CapabilityType [FK]

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
  - granted_properties <- mechanics.ObjectProperty

### Service Functions
- `advance_condition_severity(instance: world.conditions.models.ConditionInstance, amount: int) -> world.conditions.types.SeverityAdvanceResult — Increment a condition's severity and advance stage if threshold crossed.`
- `apply_condition(target: 'ObjectDB', condition: world.conditions.models.ConditionTemplate, *, severity: int = 1, duration_rounds: int | None = None, source_character: 'ObjectDB | None' = None, source_technique: 'Technique | None' = None, source_description: str = '') -> world.conditions.types.ApplyConditionResult — Apply a condition to a target, handling stacking and interactions.`
- `bulk_apply_conditions(applications: list[tuple['ObjectDB', world.conditions.models.ConditionTemplate]], *, severity: int = 1, duration_rounds: int | None = None, source_character: 'ObjectDB | None' = None, source_technique: 'Technique | None' = None, source_description: str = '') -> list[world.conditions.types.ApplyConditionResult] — Apply multiple conditions in a single transaction with batched queries.`
- `clear_all_conditions(target: 'ObjectDB', *, only_negative: bool = False, only_category: 'ConditionCategory | None' = None) -> int — Remove all conditions from a target.`
- `dataclass(cls=None, /, *, init=True, repr=True, eq=True, order=False, unsafe_hash=False, frozen=False, match_args=True, kw_only=False, slots=False, weakref_slot=False) — Add dunder methods based on the fields defined in the class.`
- `emit_event(event_name: str, payload: Any, location: Any, *, parent_stack: flows.flow_stack.FlowStack | None = None) -> flows.flow_stack.FlowStack — Dispatch ``event_name`` to every handler in ``location`` + contents.`
- `field(*, default=<dataclasses._MISSING_TYPE object at 0x000002060835A120>, default_factory=<dataclasses._MISSING_TYPE object at 0x000002060835A120>, init=True, repr=True, hash=None, compare=True, metadata=None, kw_only=<dataclasses._MISSING_TYPE object at 0x000002060835A120>) — Return an object to identify dataclass fields.`
- `get_active_conditions(target: 'ObjectDB', *, category: 'ConditionCategory | None' = None, condition: world.conditions.models.ConditionTemplate | None = None, include_suppressed: bool = False) -> django.db.models.query.QuerySet — Get active condition instances on a target.`
- `get_aggro_priority(target: 'ObjectDB') -> int — Get the total aggro priority from all conditions.`
- `get_all_capability_values(target: 'ObjectDB') -> dict[int, int] — Get all capability values for a character.`
- `get_capability_status(target: 'ObjectDB', capability: world.conditions.models.CapabilityType) -> world.conditions.types.CapabilityStatus — Get the status of a capability for a target based on active conditions.`
- `get_capability_value(target: 'ObjectDB', capability: world.conditions.models.CapabilityType) -> int — Get the total value of a capability for a character.`
- `get_check_modifier(target: 'ObjectDB', check_type: world.checks.models.CheckType) -> world.conditions.types.CheckModifierResult — Get the total modifier for a check type from active conditions.`
- `get_condition_control_percent_modifier(target: 'ObjectDB', condition_name: str) -> int — Get percentage modifier to control loss rate for a condition.`
- `get_condition_instance(target: 'ObjectDB', condition: world.conditions.models.ConditionTemplate, *, include_suppressed: bool = False) -> world.conditions.models.ConditionInstance | None — Get a specific condition instance on a target.`
- `get_condition_intensity_percent_modifier(target: 'ObjectDB', condition_name: str) -> int — Get percentage modifier to intensity gain for a condition.`
- `get_condition_penalty_percent_modifier(target: 'ObjectDB', condition_name: str) -> int — Get percentage modifier to check penalties for a condition.`
- `get_resistance_modifier(target: 'ObjectDB', damage_type: world.conditions.models.DamageType | None = None) -> world.conditions.types.ResistanceModifierResult — Get the total resistance modifier for a damage type from active conditions.`
- `get_turn_order_modifier(target: 'ObjectDB') -> int — Get the total turn order modifier from all conditions.`
- `has_condition(target: 'ObjectDB', condition: world.conditions.models.ConditionTemplate, *, include_suppressed: bool = False) -> bool — Check if target has a specific condition.`
- `process_action_tick(target: 'ObjectDB') -> world.conditions.types.RoundTickResult — Process on-action damage for conditions (when target takes an action).`
- `process_damage_interactions(target: 'ObjectDB', damage_type: world.conditions.models.DamageType) -> world.conditions.types.DamageInteractionResult — Process condition interactions when target takes damage.`
- `process_round_end(target: 'ObjectDB') -> world.conditions.types.RoundTickResult — Process end-of-round effects for all conditions on a target.`
- `process_round_start(target: 'ObjectDB') -> world.conditions.types.RoundTickResult — Process start-of-round effects for all conditions on a target.`
- `remove_condition(target: 'ObjectDB', condition: world.conditions.models.ConditionTemplate, *, remove_all_stacks: bool = True) -> bool — Remove a condition from a target.`
- `remove_conditions_by_category(target: 'ObjectDB', category: 'ConditionCategory') -> list[world.conditions.models.ConditionTemplate] — Remove all conditions in a category from a target.`
- `suppress_condition(target: 'ObjectDB', condition: world.conditions.models.ConditionTemplate, *, duration_rounds: int | None = None) -> bool — Temporarily suppress a condition's effects.`
- `unsuppress_condition(target: 'ObjectDB', condition: world.conditions.models.ConditionTemplate) -> bool — Remove suppression from a condition.`


## world.goals

### CharacterGoal
**Foreign Keys:**
  - character -> objects.ObjectDB [FK]
  - domain -> mechanics.ModifierTarget [FK]
**Pointed to by:**
  - instances <- goals.GoalInstance

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

### Service Functions
- `get_goal_bonus(character: 'CharacterSheet', domain: 'ModifierTarget') -> int — Get the goal bonus for a specific domain, applying percentage modifiers.`
- `get_goal_bonuses_breakdown(character: 'CharacterSheet') -> dict[str, world.goals.types.GoalBonusBreakdown] — Get breakdown of all goal bonuses for a character.`
- `get_total_goal_points(character: 'CharacterSheet') -> int — Get the total goal points available for a character to distribute.`


## world.magic

### EffectType
**Pointed to by:**
  - available_restrictions <- magic.Restriction
  - techniques <- magic.Technique
  - cantrips <- magic.Cantrip
  - combo_slots <- combat.ComboSlot

### TechniqueStyle
**Pointed to by:**
  - techniques <- magic.Technique
  - cantrips <- magic.Cantrip

### Affinity
**Foreign Keys:**
  - modifier_target -> mechanics.ModifierTarget [OneToOne] (nullable)
**Pointed to by:**
  - resonances <- magic.Resonance
  - character_totals <- magic.CharacterAffinityTotal
  - alteration_templates <- magic.MagicalAlterationTemplate
  - pending_alteration_origins <- magic.PendingAlteration

### Resonance
**Foreign Keys:**
  - opposite_of -> magic.Resonance [OneToOne] (nullable)
  - damage_type -> conditions.DamageType [OneToOne] (nullable)
  - modifier_target -> mechanics.ModifierTarget [OneToOne] (nullable)
  - affinity -> magic.Affinity [FK]
  - opposite -> magic.Resonance [OneToOne] (nullable)
**Pointed to by:**
  - character_resonances <- magic.CharacterResonance
  - gifts <- magic.Gift
  - anima_rituals <- magic.CharacterAnimaRitual
  - character_facets <- magic.CharacterFacet
  - motif_resonances <- magic.MotifResonance
  - alteration_templates <- magic.MagicalAlterationTemplate
  - pending_alteration_origins <- magic.PendingAlteration
  - pull_effects <- magic.ThreadPullEffect
  - imbuing_prose <- magic.ImbuingProseTemplate
  - threads <- magic.Thread
  - combo_slots <- combat.ComboSlot
  - combat_pulls <- combat.CombatPull

### CharacterAura
**Foreign Keys:**
  - character -> objects.ObjectDB [OneToOne]

### CharacterResonance
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - resonance -> magic.Resonance [FK]

### Gift
**Foreign Keys:**
  - reincarnation -> magic.Reincarnation [OneToOne] (nullable)
  - creator -> character_sheets.CharacterSheet [FK] (nullable)
**Pointed to by:**
  - character_grants <- magic.CharacterGift
  - techniques <- magic.Technique
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
  - codex_grants <- codex.TraditionCodexGrant

### CharacterTradition
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - tradition -> magic.Tradition [FK]

### CharacterAnima
**Foreign Keys:**
  - character -> objects.ObjectDB [OneToOne]

### CharacterAnimaRitual
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [OneToOne]
  - stat -> traits.Trait [FK]
  - skill -> skills.Skill [FK]
  - specialization -> skills.Specialization [FK] (nullable)
  - resonance -> magic.Resonance [FK]
**Pointed to by:**
  - performances <- magic.AnimaRitualPerformance

### AnimaRitualPerformance
**Foreign Keys:**
  - ritual -> magic.CharacterAnimaRitual [FK]
  - target_character -> character_sheets.CharacterSheet [FK] (nullable)
  - scene -> scenes.Scene [FK] (nullable)

### Restriction
**Pointed to by:**
  - techniques <- magic.Technique

### IntensityTier
**Pointed to by:**
  - auderethreshold_set <- magic.AudereThreshold

### Technique
**Foreign Keys:**
  - gift -> magic.Gift [FK]
  - style -> magic.TechniqueStyle [FK]
  - effect_type -> magic.EffectType [FK]
  - source_cantrip -> magic.Cantrip [FK] (nullable)
  - creator -> character_sheets.CharacterSheet [FK] (nullable)
  - action_template -> actions.ActionTemplate [FK] (nullable)
**Pointed to by:**
  - action_enhancements <- actions.ActionEnhancement
  - capability_grants <- magic.TechniqueCapabilityGrant
  - character_grants <- magic.CharacterTechnique
  - pendingalteration_set <- magic.PendingAlteration
  - magicalalterationevent_set <- magic.MagicalAlterationEvent
  - anchored_threads <- magic.Thread
  - scene_action_requests <- scenes.SceneActionRequest
  - conditions_caused <- conditions.ConditionInstance

### TechniqueCapabilityGrant
**Foreign Keys:**
  - technique -> magic.Technique [FK]
  - capability -> conditions.CapabilityType [FK]
  - prerequisite -> mechanics.Prerequisite [FK] (nullable)

### CharacterTechnique
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - technique -> magic.Technique [FK]

### Facet
**Foreign Keys:**
  - parent -> magic.Facet [FK] (nullable)
**Pointed to by:**
  - children <- magic.Facet
  - character_assignments <- magic.CharacterFacet
  - motif_usages <- magic.MotifResonanceAssociation
  - cantrips <- magic.Cantrip

### CharacterFacet
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - facet -> magic.Facet [FK]
  - resonance -> magic.Resonance [FK]

### CharacterAffinityTotal
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - affinity -> magic.Affinity [FK]

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

### MotifResonanceAssociation
**Foreign Keys:**
  - motif_resonance -> magic.MotifResonance [FK]
  - facet -> magic.Facet [FK]

### Reincarnation
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - gift -> magic.Gift [OneToOne]

### Cantrip
**Foreign Keys:**
  - effect_type -> magic.EffectType [FK]
  - style -> magic.TechniqueStyle [FK]
**Pointed to by:**
  - created_techniques <- magic.Technique

### SoulfrayConfig
**Foreign Keys:**
  - resilience_check_type -> checks.CheckType [FK]

### MishapPoolTier
**Foreign Keys:**
  - consequence_pool -> actions.ConsequencePool [FK]

### TechniqueOutcomeModifier
**Foreign Keys:**
  - outcome -> traits.CheckOutcome [OneToOne]

### MagicalAlterationTemplate
**Foreign Keys:**
  - condition_template -> conditions.ConditionTemplate [OneToOne]
  - origin_affinity -> magic.Affinity [FK]
  - origin_resonance -> magic.Resonance [FK]
  - weakness_damage_type -> conditions.DamageType [FK] (nullable)
  - authored_by -> accounts.AccountDB [FK] (nullable)
  - parent_template -> magic.MagicalAlterationTemplate [FK] (nullable)
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

### MagicalAlterationEvent
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - alteration_template -> magic.MagicalAlterationTemplate [FK]
  - active_condition -> conditions.ConditionInstance [FK] (nullable)
  - triggering_scene -> scenes.Scene [FK] (nullable)
  - triggering_technique -> magic.Technique [FK] (nullable)

### ThreadPullCost

### ThreadXPLockedLevel

### ThreadPullEffect
**Foreign Keys:**
  - resonance -> magic.Resonance [FK]
  - capability_grant -> conditions.CapabilityType [FK] (nullable)

### ImbuingProseTemplate
**Foreign Keys:**
  - resonance -> magic.Resonance [FK] (nullable)

### Ritual
**Foreign Keys:**
  - flow -> flows.FlowDefinition [FK] (nullable)
  - site_property -> mechanics.Property [FK] (nullable)
**Pointed to by:**
  - requirements <- magic.RitualComponentRequirement

### RitualComponentRequirement
**Foreign Keys:**
  - ritual -> magic.Ritual [FK]
  - item_template -> items.ItemTemplate [FK]
  - min_quality_tier -> items.QualityTier [FK] (nullable)

### Thread
**Foreign Keys:**
  - owner -> character_sheets.CharacterSheet [FK]
  - resonance -> magic.Resonance [FK]
  - target_trait -> traits.Trait [FK] (nullable)
  - target_technique -> magic.Technique [FK] (nullable)
  - target_object -> objects.ObjectDB [FK] (nullable)
  - target_relationship_track -> relationships.RelationshipTrackProgress [FK] (nullable)
  - target_capstone -> relationships.RelationshipCapstone [FK] (nullable)
**Pointed to by:**
  - level_unlocks <- magic.ThreadLevelUnlock
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
  - unlock_room_property -> mechanics.Property [FK] (nullable)
  - unlock_track -> relationships.RelationshipTrack [FK] (nullable)
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

### AudereThreshold
**Foreign Keys:**
  - minimum_intensity_tier -> magic.IntensityTier [FK]
  - minimum_warp_stage -> conditions.ConditionStage [FK]

### Service Functions
- `accept_thread_weaving_unlock(learner: 'CharacterSheet', offer: 'ThreadWeavingTeachingOffer') -> 'CharacterThreadWeavingUnlock' — Accept a ThreadWeavingTeachingOffer on behalf of a learner (Spec A §6.1).`
- `apply_damage_reduction_from_threads(character: 'ObjectDB', incoming_damage: 'int') -> 'int' — Reduce incoming damage by thread-derived DAMAGE_TAKEN_REDUCTION.`
- `calculate_affinity_breakdown(resonances: 'QuerySet[ResonanceModel]') -> 'dict[str, int]' — Derive affinity counts from a set of resonances.`
- `calculate_effective_anima_cost(*, base_cost: 'int', runtime_intensity: 'int', runtime_control: 'int', current_anima: 'int') -> 'AnimaCostResult' — Calculate effective anima cost using the delta formula.`
- `calculate_soulfray_severity(current_anima: 'int', max_anima: 'int', deficit: 'int', config: 'SoulfrayConfig') -> 'int' — Compute Soulfray severity contribution from post-deduction anima state.`
- `compute_anchor_cap(thread: 'Thread') -> 'int' — Return the anchor-side cap for this thread (Spec A §2.4).`
- `compute_effective_cap(thread: 'Thread') -> 'int' — Return min(path cap, anchor cap) — the binding limit on this thread (Spec A §2.4).`
- `compute_path_cap(character_sheet: 'CharacterSheet') -> 'int' — Return the path-side cap for a character (Spec A §2.4).`
- `compute_thread_weaving_xp_cost(unlock: 'ThreadWeavingUnlock', learner: 'CharacterSheet') -> 'int' — Compute the XP cost for a learner to acquire a ThreadWeavingUnlock (Spec A §6.2).`
- `create_pending_alteration(*, character: 'CharacterSheet', tier: 'int', origin_affinity: 'Affinity', origin_resonance: 'ResonanceModel', scene: 'Scene | None', triggering_technique: 'Technique | None' = None, triggering_intensity: 'int | None' = None, triggering_control: 'int | None' = None, triggering_anima_cost: 'int | None' = None, triggering_anima_deficit: 'int | None' = None, triggering_soulfray_stage: 'int | None' = None, audere_active: 'bool' = False) -> 'PendingAlterationResult' — Create or escalate a PendingAlteration for a character.`
- `cross_thread_xp_lock(character_sheet: 'CharacterSheet', thread: 'Thread', boundary_level: 'int') -> 'ThreadLevelUnlock' — Pay XP to unlock an XP-locked level boundary on a thread.`
- `deduct_anima(character: 'ObjectDB', effective_cost: 'int') -> 'int' — Deduct anima from character, returning the overburn deficit.`
- `emit_event(event_name: str, payload: Any, location: Any, *, parent_stack: flows.flow_stack.FlowStack | None = None) -> flows.flow_stack.FlowStack — Dispatch ``event_name`` to every handler in ``location`` + contents.`
- `get_aura_percentages(character_sheet: 'CharacterSheet') -> 'AuraPercentages' — Calculate aura percentages from affinity totals and resonance-targeting modifiers.`
- `get_library_entries(*, tier: 'int', character_affinity_id: 'int | None' = None) -> 'QuerySet[MagicalAlterationTemplate]' — Return library entries matching the given tier.`
- `get_runtime_technique_stats(technique: 'Technique', character: 'ObjectDB | None') -> 'RuntimeTechniqueStats' — Calculate runtime intensity and control for a technique.`
- `get_soulfray_warning(character: 'ObjectDB') -> 'SoulfrayWarning | None' — Return the current Soulfray stage warning for the safety checkpoint.`
- `grant_resonance(character_sheet: 'CharacterSheet', resonance: 'ResonanceModel', amount: 'int', source: 'str', source_ref: 'int | None' = None) -> 'CharacterResonance' — Lazily create CharacterResonance and credit balance + lifetime_earned.`
- `has_pending_alterations(character: 'CharacterSheet') -> 'bool' — Check if this character has any unresolved Mage Scars.`
- `imbue_ready_threads(character_sheet: 'CharacterSheet') -> 'list[Thread]' — Return threads that have matching CharacterResonance balance > 0 and level < cap.`
- `near_xp_lock_threads(character_sheet: 'CharacterSheet', within: 'int' = 100) -> 'list[ThreadXPLockProspect]' — Return threads whose dev_points are within `within` of the next XP-locked boundary.`
- `preview_resonance_pull(character_sheet: 'CharacterSheet', resonance: 'ResonanceModel', tier: 'int', threads: 'list[Thread]', *, combat_encounter: 'CombatEncounter | None' = None) -> 'PullPreviewResult' — Read-only preview of a resonance pull (Spec A §5.6).`
- `recompute_max_health_with_threads(character_sheet: 'CharacterSheet') -> 'int' — Recompute max_health folding in thread-derived VITAL_BONUS addends.`
- `resolve_pending_alteration(*, pending: 'PendingAlteration', name: 'str', player_description: 'str', observer_description: 'str', weakness_damage_type: 'DamageType | None' = None, weakness_magnitude: 'int' = 0, resonance_bonus_magnitude: 'int' = 0, social_reactivity_magnitude: 'int' = 0, is_visible_at_rest: 'bool', resolved_by: 'AccountDB | None', parent_template: 'MagicalAlterationTemplate | None' = None, is_library_entry: 'bool' = False, library_template: 'MagicalAlterationTemplate | None' = None) -> 'AlterationResolutionResult' — Resolve a PendingAlteration by creating or selecting a template.`
- `resolve_pull_effects(threads: 'list[Thread]', tier: 'int', *, in_combat: 'bool') -> 'list[ResolvedPullEffect]' — Resolve every (thread × effect_tier 0..tier) pair into ResolvedPullEffect rows.`
- `select_mishap_pool(control_deficit: 'int') -> 'ConsequencePool | None' — Select a control mishap consequence pool based on deficit magnitude.`
- `spend_resonance_for_imbuing(character_sheet: 'CharacterSheet', thread: 'Thread', amount: 'int') -> 'ThreadImbueResult' — Deduct resonance balance and greedily advance thread level.`
- `spend_resonance_for_pull(character_sheet: 'CharacterSheet', resonance: 'ResonanceModel', tier: 'int', threads: 'list[Thread]', action_context: 'PullActionContext') -> 'ResonancePullResult' — Atomic pull commit (Spec A §5.4 + §7.4).`
- `staff_clear_alteration(*, pending: 'PendingAlteration', staff_account: 'AccountDB | None', notes: 'str' = '') -> 'None' — Clear a PendingAlteration without resolving it. Staff escape hatch.`
- `threads_blocked_by_cap(character_sheet: 'CharacterSheet') -> 'list[Thread]' — Return threads that are at their effective cap (no further imbuing helps).`
- `update_thread_narrative(thread: 'Thread', *, name: 'str | None' = None, description: 'str | None' = None) -> 'Thread' — Update the narrative name and/or description of a thread.`
- `use_technique(*, character: 'ObjectDB', technique: 'Technique', resolve_fn: 'Callable[..., Any]', confirm_soulfray_risk: 'bool' = True, check_result: 'CheckResult | None' = None, targets: 'list | None' = None) -> 'TechniqueUseResult' — Orchestrate technique use: cost -> checkpoint -> resolve -> soulfray -> mishap.`
- `validate_alteration_resolution(*, pending_tier: 'int', pending_affinity_id: 'int', pending_resonance_id: 'int', payload: 'dict', is_staff: 'bool', character_sheet: 'CharacterSheet | None' = None) -> 'list[str]' — Validate a resolution payload against the pending's tier and origin.`
- `weave_thread(character_sheet: 'CharacterSheet', target_kind: 'str', target: 'object', resonance: 'ResonanceModel', *, name: 'str' = '', description: 'str' = '') -> 'Thread' — Create a new Thread anchored to the given target.`


## world.mechanics

### ModifierCategory
**Pointed to by:**
  - targets <- mechanics.ModifierTarget

### ModifierTarget
**Foreign Keys:**
  - codex_entry -> codex.CodexEntry [OneToOne] (nullable)
  - category -> mechanics.ModifierCategory [FK]
  - target_trait -> traits.Trait [FK] (nullable)
  - target_affinity -> magic.Affinity [OneToOne] (nullable)
  - target_resonance -> magic.Resonance [OneToOne] (nullable)
  - target_capability -> conditions.CapabilityType [OneToOne] (nullable)
  - target_check_type -> checks.CheckType [OneToOne] (nullable)
  - target_damage_type -> conditions.DamageType [OneToOne] (nullable)
**Pointed to by:**
  - distinction_effects <- distinctions.DistinctionEffect
  - character_goals <- goals.CharacterGoal
  - goal_journals <- goals.GoalJournal
  - character_modifiers <- mechanics.CharacterModifier
  - gated_by_conditions <- relationships.RelationshipCondition

### ModifierSource
**Foreign Keys:**
  - distinction_effect -> distinctions.DistinctionEffect [FK] (nullable)
  - character_distinction -> distinctions.CharacterDistinction [FK] (nullable)
**Pointed to by:**
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
  - technique_grants <- magic.TechniqueCapabilityGrant
  - capability_types <- conditions.CapabilityType

### PropertyCategory
**Pointed to by:**
  - properties <- mechanics.Property

### Property
**Foreign Keys:**
  - category -> mechanics.PropertyCategory [FK]
**Pointed to by:**
  - resonances <- magic.Resonance
  - ritual_sites <- magic.Ritual
  - thread_weaving_unlocks <- magic.ThreadWeavingUnlock
  - condition_templates <- conditions.ConditionTemplate
  - prerequisites <- mechanics.Prerequisite
  - challenge_template_properties <- mechanics.ChallengeTemplateProperty
  - object_properties <- mechanics.ObjectProperty
  - applications <- mechanics.Application
  - required_by_applications <- mechanics.Application
  - challenge_templates <- mechanics.ChallengeTemplate
  - required_by_approaches <- mechanics.ChallengeApproach
  - context_consequence_pools <- mechanics.ContextConsequencePool
  - consequence_effects <- checks.ConsequenceEffect

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
  - consequences <- mechanics.ApproachConsequence
  - character_records <- mechanics.CharacterChallengeRecord

### ApproachConsequence
**Foreign Keys:**
  - approach -> mechanics.ChallengeApproach [FK]
  - consequence -> checks.Consequence [FK]

### SituationTemplate
**Foreign Keys:**
  - category -> mechanics.ChallengeCategory [FK]
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
  - granted_properties <- mechanics.ObjectProperty
  - character_records <- mechanics.CharacterChallengeRecord

### CharacterChallengeRecord
**Foreign Keys:**
  - character -> objects.ObjectDB [FK]
  - challenge_instance -> mechanics.ChallengeInstance [FK]
  - approach -> mechanics.ChallengeApproach [FK]
  - outcome -> traits.CheckOutcome [FK] (nullable)
  - consequence -> checks.Consequence [FK] (nullable)

### ContextConsequencePool
**Foreign Keys:**
  - property -> mechanics.Property [FK]
  - consequence_pool -> actions.ConsequencePool [FK]
  - check_type -> checks.CheckType [FK] (nullable)

### CharacterEngagement
**Foreign Keys:**
  - character -> objects.ObjectDB [OneToOne]
  - source_content_type -> contenttypes.ContentType [FK]

### Service Functions
- `chart_has_success_outcomes(rank_difference: int) -> bool — Check if the ResultChart for this rank difference has any success outcomes.`
- `create_distinction_modifiers(character_distinction: 'CharacterDistinction') -> 'list[CharacterModifier]' — Create ModifierSource + CharacterModifier records for all effects of a distinction.`
- `delete_distinction_modifiers(character_distinction: 'CharacterDistinction') -> 'int' — Delete all modifier records for a distinction.`
- `get_all_capability_values(target: 'ObjectDB') -> dict[int, int] — Get all capability values for a character.`
- `get_available_actions(character: 'ObjectDB', location: 'ObjectDB', capability_sources: 'list[CapabilitySource] | None' = None) -> 'list[AvailableAction]' — Generate available Actions for a character at a location.`
- `get_capability_sources_for_character(character: 'ObjectDB') -> 'list[CapabilitySource]' — Collect all Capability sources for a character (per-source, not aggregated).`
- `get_modifier_breakdown(character, modifier_target: 'ModifierTarget') -> 'ModifierBreakdown' — Get detailed breakdown of all modifiers for a target.`
- `get_modifier_total(character, modifier_target: 'ModifierTarget') -> 'int' — Get total modifier value for a target.`
- `preview_check_difficulty(character: 'ObjectDB', check_type: 'CheckType', target_difficulty: int = 0, extra_modifiers: int = 0) -> int — Preview the rank difference for a check without rolling.`
- `update_distinction_rank(character_distinction: 'CharacterDistinction') -> 'None' — Update CharacterModifier values when rank changes.`


## world.progression

### CharacterXP
**Foreign Keys:**
  - character -> objects.ObjectDB [FK]

### CharacterXPTransaction
**Foreign Keys:**
  - character -> objects.ObjectDB [FK]

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
- `on_scene_finished(scene: world.scenes.models.Scene) -> None — Grant scene completion rewards to all participants.`
- `remove_vote(voter_account: evennia.accounts.models.AccountDB, target_type: str, target_id: int) -> None — Remove an unprocessed vote for the current week.`
- `spend_xp_on_unlock(character: 'ObjectDB', unlock_target: 'ClassLevelUnlock', gm: 'AccountDB | None' = None) -> 'tuple[bool, str, CharacterUnlock | None]' — Spend XP to unlock something for a character.`


## world.realms

### Realm
**Pointed to by:**
  - families <- roster.Family
  - character_sheets <- character_sheets.CharacterSheet
  - starting_areas <- character_creation.StartingArea
  - societies <- societies.Society
  - areas <- areas.Area


## world.relationships

### RelationshipCondition
**Pointed to by:**
  - character_relationships <- relationships.CharacterRelationship

### RelationshipTrack
**Pointed to by:**
  - thread_weaving_unlocks <- magic.ThreadWeavingUnlock
  - tiers <- relationships.RelationshipTier
  - hybridrequirement_set <- relationships.HybridRequirement
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

### CharacterRelationship
**Foreign Keys:**
  - source -> character_sheets.CharacterSheet [FK]
  - target -> character_sheets.CharacterSheet [FK]
  - displayed_track -> relationships.RelationshipTrack [FK] (nullable)
  - displayed_tier -> relationships.RelationshipTier [FK] (nullable)
  - game_week -> game_clock.GameWeek [FK] (nullable)
**Pointed to by:**
  - track_progress <- relationships.RelationshipTrackProgress
  - updates <- relationships.RelationshipUpdate
  - developments <- relationships.RelationshipDevelopment
  - capstones <- relationships.RelationshipCapstone
  - changes <- relationships.RelationshipChange

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

### RelationshipDevelopment
**Foreign Keys:**
  - relationship -> relationships.CharacterRelationship [FK]
  - author -> character_sheets.CharacterSheet [FK]
  - track -> relationships.RelationshipTrack [FK]
  - linked_scene -> scenes.Scene [FK] (nullable)

### RelationshipCapstone
**Foreign Keys:**
  - relationship -> relationships.CharacterRelationship [FK]
  - author -> character_sheets.CharacterSheet [FK]
  - track -> relationships.RelationshipTrack [FK]
  - linked_scene -> scenes.Scene [FK] (nullable)
**Pointed to by:**
  - anchored_threads <- magic.Thread

### RelationshipChange
**Foreign Keys:**
  - relationship -> relationships.CharacterRelationship [FK]
  - author -> character_sheets.CharacterSheet [FK]
  - source_track -> relationships.RelationshipTrack [FK]
  - target_track -> relationships.RelationshipTrack [FK]

### Service Functions
- `award_xp(account: 'AccountDB', amount: 'int', reason: 'str' = ProgressionReason.SYSTEM_AWARD, description: 'str' = '', gm: 'AccountDB | None' = None) -> 'XPTransaction' — Award XP to an account.`
- `create_capstone(*, relationship: 'CharacterRelationship', author: 'CharacterSheet', title: 'str', writeup: 'str', track: 'RelationshipTrack', points: 'int', visibility: 'UpdateVisibility', linked_scene: 'Scene | None' = None) -> 'RelationshipCapstone' — Record a capstone event — adds points to both capacity and developed_points.`
- `create_development(*, relationship: 'CharacterRelationship', author: 'CharacterSheet', title: 'str', writeup: 'str', track: 'RelationshipTrack', points: 'int', xp_awarded: 'int' = 0, visibility: 'UpdateVisibility', linked_scene: 'Scene | None' = None) -> 'RelationshipDevelopment' — Add permanent (developed) points to a track, up to capacity.`
- `create_first_impression(*, source: 'CharacterSheet', target: 'CharacterSheet', title: 'str', writeup: 'str', track: 'RelationshipTrack', points: 'int', coloring: 'FirstImpressionColoring', visibility: 'UpdateVisibility', linked_scene: 'Scene | None' = None) -> 'CharacterRelationship' — Create a pending relationship with an initial update and track progress.`
- `get_account_for_character(character: 'ObjectDB') -> 'AccountDB | None' — Get the account currently playing this character via roster tenure.`
- `increment_stat(character_sheet: 'CharacterSheet', stat: 'StatDefinition', amount: 'int' = 1) -> 'int' — Increment a stat tracker (create if needed) and check for achievements.`
- `redistribute_points(*, relationship: 'CharacterRelationship', author: 'CharacterSheet', title: 'str', writeup: 'str', source_track: 'RelationshipTrack', target_track: 'RelationshipTrack', points: 'int', visibility: 'UpdateVisibility') -> 'RelationshipChange' — Move developed points from one track to another. No new value is added.`


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
  - members <- character_sheets.CharacterSheet
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
**Pointed to by:**
  - tenures <- roster.RosterTenure
  - random_scene_claimed_as <- progression.RandomSceneCompletion
  - favorited_interactions <- scenes.InteractionFavorite
  - beatcompletion_set <- stories.BeatCompletion
  - codex_knowledge <- codex.CharacterCodexKnowledge
  - clue_knowledge <- codex.CharacterClueKnowledge
  - invites <- gm.GMRosterInvite

### TenureDisplaySettings
**Foreign Keys:**
  - tenure -> roster.RosterTenure [OneToOne]

### TenureGallery
**Foreign Keys:**
  - tenure -> roster.RosterTenure [FK]
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
  - display_settings -> roster.TenureDisplaySettings [OneToOne] (nullable)
  - player_data -> evennia_extensions.PlayerData [FK]
  - roster_entry -> roster.RosterEntry [FK]
  - approved_by -> evennia_extensions.PlayerData [FK] (nullable)
**Pointed to by:**
  - sent_mail <- roster.PlayerMail
  - received_mail <- roster.PlayerMail
  - galleries <- roster.TenureGallery
  - shared_galleries <- roster.TenureGallery
  - media <- roster.TenureMedia
  - thread_weaving_unlocks_taught <- magic.CharacterThreadWeavingUnlock
  - thread_weaving_offers <- magic.ThreadWeavingTeachingOffer
  - consent_groups <- consent.ConsentGroup
  - consent_memberships <- consent.ConsentGroupMember
  - codex_taught <- codex.CharacterCodexKnowledge
  - codex_teaching_offers <- codex.CodexTeachingOffer
  - codexteachingoffer_visible <- codex.CodexTeachingOffer
  - codexteachingoffer_excluded <- codex.CodexTeachingOffer


## world.scenes

### Scene
**Foreign Keys:**
  - location -> objects.ObjectDB [FK] (nullable)
  - event -> events.Event [FK] (nullable)
**Pointed to by:**
  - developmenttransaction_set <- progression.DevelopmentTransaction
  - anima_ritual_performances <- magic.AnimaRitualPerformance
  - triggered_alterations <- magic.PendingAlteration
  - magicalalterationevent_set <- magic.MagicalAlterationEvent
  - participations <- scenes.SceneParticipation
  - interactions <- scenes.Interaction
  - summary_revisions <- scenes.SceneSummaryRevision
  - action_requests <- scenes.SceneActionRequest
  - story_episodes <- stories.EpisodeScene
  - legend_events <- societies.LegendEvent
  - legend_entries <- societies.LegendEntry
  - legend_spreads <- societies.LegendSpread
  - situation_instances <- mechanics.SituationInstance
  - relationshipupdate_set <- relationships.RelationshipUpdate
  - relationshipdevelopment_set <- relationships.RelationshipDevelopment
  - relationshipcapstone_set <- relationships.RelationshipCapstone
  - combat_encounters <- combat.CombatEncounter

### SceneParticipation
**Foreign Keys:**
  - scene -> scenes.Scene [FK]
  - account -> accounts.AccountDB [FK]

### Persona
**Foreign Keys:**
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - thumbnail -> evennia_extensions.PlayerMedia [FK] (nullable)
**Pointed to by:**
  - mentored_allocations <- skills.TrainingAllocation
  - feedback_submissions <- player_submissions.PlayerFeedback
  - bug_reports <- player_submissions.BugReport
  - reports_submitted <- player_submissions.PlayerReport
  - reports_against <- player_submissions.PlayerReport
  - targeted_for_random_scene <- progression.RandomSceneTarget
  - random_scene_completed_by <- progression.RandomSceneCompletion
  - discoveries_as_subject <- scenes.PersonaDiscovery
  - discoveries_as_linked <- scenes.PersonaDiscovery
  - interactions_written <- scenes.Interaction
  - interactions_targeted <- scenes.Interaction
  - targeted_in_interactions <- scenes.InteractionTargetPersona
  - summary_revisions <- scenes.SceneSummaryRevision
  - initiated_action_requests <- scenes.SceneActionRequest
  - received_action_requests <- scenes.SceneActionRequest
  - place_presences <- scenes.PlacePresence
  - interactions_received <- scenes.InteractionReceiver
  - organization_memberships <- societies.OrganizationMembership
  - society_reputations <- societies.SocietyReputation
  - organization_reputations <- societies.OrganizationReputation
  - legend_entries <- societies.LegendEntry
  - legend_spreads <- societies.LegendSpread
  - legend_stories_written <- societies.LegendDeedStory
  - hosted_events <- events.EventHost
  - event_invitations <- events.EventInvitation
  - invitations_sent <- events.EventInvitation
  - combat_opponents <- combat.CombatOpponent
  - gm_table_memberships <- gm.GMTableMembership

### PersonaDiscovery
**Foreign Keys:**
  - persona -> scenes.Persona [FK]
  - linked_to -> scenes.Persona [FK]
  - discovered_by -> character_sheets.CharacterSheet [FK]

### Interaction
**Foreign Keys:**
  - action_request_result -> scenes.SceneActionRequest [OneToOne] (nullable)
  - persona -> scenes.Persona [FK]
  - scene -> scenes.Scene [FK] (nullable)
  - place -> scenes.Place [FK] (nullable)
**Pointed to by:**
  - favorites <- scenes.InteractionFavorite
  - reactions <- scenes.InteractionReaction
  - interaction_targets <- scenes.InteractionTargetPersona
  - receivers <- scenes.InteractionReceiver
  - referencing_updates <- relationships.RelationshipUpdate

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

### SceneSummaryRevision
**Foreign Keys:**
  - scene -> scenes.Scene [FK]
  - persona -> scenes.Persona [FK]

### SceneActionRequest
**Foreign Keys:**
  - scene -> scenes.Scene [FK]
  - initiator_persona -> scenes.Persona [FK]
  - target_persona -> scenes.Persona [FK]
  - action_template -> actions.ActionTemplate [FK] (nullable)
  - technique -> magic.Technique [FK] (nullable)
  - result_interaction -> scenes.Interaction [OneToOne] (nullable)

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

### Service Functions
- `broadcast_scene_message(scene: 'Scene', action: 'ActionType') -> 'None' — Send scene information to all accounts in the scene's location.`
- `cast(typ, val) — Cast a value to a type.`
- `invalidate_active_scene_cache(location: 'ObjectDB') -> 'None' — Clear the cached active scene for a location.`


## world.skills

### Skill
**Foreign Keys:**
  - trait -> traits.Trait [OneToOne]
**Pointed to by:**
  - specializations <- skills.Specialization
  - character_values <- skills.CharacterSkillValue
  - path_suggestions <- skills.PathSkillSuggestion
  - training_allocations <- skills.TrainingAllocation
  - anima_rituals <- magic.CharacterAnimaRitual
  - legend_spreads <- societies.LegendSpread

### Specialization
**Foreign Keys:**
  - parent_skill -> skills.Skill [FK]
**Pointed to by:**
  - character_values <- skills.CharacterSpecializationValue
  - training_allocations <- skills.TrainingAllocation
  - anima_rituals <- magic.CharacterAnimaRitual

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
- `calculate_training_development(allocation: 'TrainingAllocation', *, _teaching_skill: 'Skill | None' = <object object at 0x000002060AF8C6B0>, _path_levels: 'dict[int, int] | None' = None) -> 'int' — Calculate development points earned from a training allocation.`
- `create_training_allocation(character: 'ObjectDB', ap_amount: 'int', *, skill: 'Skill | None' = None, specialization: 'Specialization | None' = None, mentor: 'Persona | None' = None) -> 'TrainingAllocation' — Create a new training allocation for a character.`
- `get_relationship_tier(character_a: evennia.objects.models.ObjectDB, character_b: evennia.objects.models.ObjectDB) -> int — Get the relationship tier between two characters.`
- `process_weekly_training() -> 'dict[int, set[int]]' — Process all training allocations for the weekly tick.`
- `remove_training_allocation(allocation: 'TrainingAllocation') -> 'None' — Delete a training allocation.`
- `run_weekly_skill_cron() -> 'None' — Run the full weekly skill development cycle.`
- `update_training_allocation(allocation: 'TrainingAllocation', *, ap_amount: 'int | None' = None, mentor: 'Persona | None' = <object object at 0x000002060AF8C6B0>) -> 'TrainingAllocation' — Update an existing training allocation.`


## world.societies

### Society
**Foreign Keys:**
  - realm -> realms.Realm [FK]
**Pointed to by:**
  - connected_beginnings <- character_creation.Beginnings
  - traditions <- magic.Tradition
  - organizations <- societies.Organization
  - reputations <- societies.SocietyReputation
  - known_legend_entries <- societies.LegendEntry
  - heard_legend_spreads <- societies.LegendSpread
  - event_invitations <- events.EventInvitation

### OrganizationType
**Pointed to by:**
  - organizations <- societies.Organization

### Organization
**Foreign Keys:**
  - society -> societies.Society [FK]
  - org_type -> societies.OrganizationType [FK]
**Pointed to by:**
  - memberships <- societies.OrganizationMembership
  - reputations <- societies.OrganizationReputation
  - event_invitations <- events.EventInvitation

### OrganizationMembership
**Foreign Keys:**
  - organization -> societies.Organization [FK]
  - persona -> scenes.Persona [FK]

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

### SpreadingConfig

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
**Pointed to by:**
  - spreads <- societies.LegendSpread
  - deed_stories <- societies.LegendDeedStory

### LegendSpread
**Foreign Keys:**
  - legend_entry -> societies.LegendEntry [FK]
  - spreader_persona -> scenes.Persona [FK]
  - skill -> skills.Skill [FK] (nullable)
  - scene -> scenes.Scene [FK] (nullable)

### LegendDeedStory
**Foreign Keys:**
  - deed -> societies.LegendEntry [FK]
  - author -> scenes.Persona [FK]

### CharacterLegendSummary
**Foreign Keys:**
  - character -> objects.ObjectDB [OneToOne]

### PersonaLegendSummary
**Foreign Keys:**
  - persona -> scenes.Persona [OneToOne]

### Service Functions
- `create_legend_event(title: str, source_type: world.societies.models.LegendSourceType, base_value: int, personas: list[world.scenes.models.Persona], *, description: str = '', scene: world.scenes.models.Scene | None = None, story: world.stories.models.Story | None = None, created_by: evennia.accounts.models.AccountDB | None = None) -> tuple[world.societies.models.LegendEvent, list[world.societies.models.LegendEntry]] — Create a shared event and individual deeds for each participant.`
- `create_solo_deed(persona: world.scenes.models.Persona, title: str, source_type: world.societies.models.LegendSourceType, base_value: int, *, description: str = '', scene: world.scenes.models.Scene | None = None, story: world.stories.models.Story | None = None) -> world.societies.models.LegendEntry — Create a legend deed not tied to a shared event.`
- `get_character_legend_total(character: evennia.objects.models.ObjectDB) -> int — Fast lookup of a character's total legend from materialized view.`
- `get_persona_legend_total(persona: world.scenes.models.Persona) -> int — Per-persona legend lookup from materialized view.`
- `refresh_legend_views() -> None — Refresh both legend materialized views concurrently.`
- `spread_deed(deed: world.societies.models.LegendEntry, spreader_persona: world.scenes.models.Persona, value_added: int, *, description: str = '', method: str = '', skill: world.skills.models.Skill | None = None, audience_factor: decimal.Decimal = Decimal('1.0'), scene: world.scenes.models.Scene | None = None, societies_reached: list[world.societies.models.Society] | None = None) -> world.societies.models.LegendSpread — Record a spreading action and add legend value, clamped to capacity.`
- `spread_event(event: world.societies.models.LegendEvent, spreader_persona: world.scenes.models.Persona, value_per_deed: int, *, description: str = '', method: str = '', skill: world.skills.models.Skill | None = None, audience_factor: decimal.Decimal = Decimal('1.0'), scene: world.scenes.models.Scene | None = None, societies_reached: list[world.societies.models.Society] | None = None) -> list[world.societies.models.LegendSpread] — Spread all active deeds linked to an event at once.`


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
  - primary_table -> gm.GMTable [FK] (nullable)
  - personal_story_character -> objects.ObjectDB [FK] (nullable)
**Pointed to by:**
  - trust_requirements <- stories.StoryTrustRequirement
  - participants <- stories.StoryParticipation
  - chapters <- stories.Chapter
  - feedback <- stories.StoryFeedback
  - progress_records <- stories.StoryProgress
  - legend_events <- societies.LegendEvent
  - legend_entries <- societies.LegendEntry

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
  - active_progress_records <- stories.StoryProgress

### EpisodeScene
**Foreign Keys:**
  - episode -> stories.Episode [FK]
  - scene -> scenes.Scene [FK]

### PlayerTrust
**Foreign Keys:**
  - account -> accounts.AccountDB [OneToOne]
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
**Pointed to by:**
  - category_ratings <- stories.TrustCategoryFeedbackRating

### TrustCategoryFeedbackRating
**Foreign Keys:**
  - feedback -> stories.StoryFeedback [FK]
  - trust_category -> stories.TrustCategory [FK]

### Era
**Pointed to by:**
  - stories_created_in_era <- stories.Story
  - beat_completions <- stories.BeatCompletion
  - episoderesolution_set <- stories.EpisodeResolution

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
**Pointed to by:**
  - gating_for_episodes <- stories.EpisodeProgressionRequirement
  - routing_for_transitions <- stories.TransitionRequiredOutcome
  - completions <- stories.BeatCompletion

### EpisodeProgressionRequirement
**Foreign Keys:**
  - episode -> stories.Episode [FK]
  - beat -> stories.Beat [FK]

### TransitionRequiredOutcome
**Foreign Keys:**
  - transition -> stories.Transition [FK]
  - beat -> stories.Beat [FK]

### BeatCompletion
**Foreign Keys:**
  - beat -> stories.Beat [FK]
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - roster_entry -> roster.RosterEntry [FK] (nullable)
  - era -> stories.Era [FK] (nullable)

### EpisodeResolution
**Foreign Keys:**
  - episode -> stories.Episode [FK]
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - chosen_transition -> stories.Transition [FK] (nullable)
  - resolved_by -> gm.GMProfile [FK] (nullable)
  - era -> stories.Era [FK] (nullable)

### StoryProgress
**Foreign Keys:**
  - story -> stories.Story [FK]
  - character_sheet -> character_sheets.CharacterSheet [FK]
  - current_episode -> stories.Episode [FK] (nullable)


## world.traits

### Trait
**Foreign Keys:**
  - skill -> skills.Skill [OneToOne] (nullable)
**Pointed to by:**
  - rank_descriptions <- traits.TraitRankDescription
  - character_values <- traits.CharacterTraitValue
  - classes_requiring_trait <- classes.CharacterClass
  - development_points <- progression.DevelopmentPoints
  - development_transactions <- progression.DevelopmentTransaction
  - weekly_skill_usage <- progression.WeeklySkillUsage
  - xp_costs <- progression.TraitXPCost
  - rating_unlocks <- progression.TraitRatingUnlock
  - trait_requirements <- progression.TraitRequirement
  - anima_rituals <- magic.CharacterAnimaRitual
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
**Foreign Keys:**
  - technique_warp_modifier -> magic.TechniqueOutcomeModifier [OneToOne] (nullable)
**Pointed to by:**
  - resultchartoutcome_set <- traits.ResultChartOutcome
  - challenge_records <- mechanics.CharacterChallengeRecord
  - consequences <- checks.Consequence

### ResultChart
**Pointed to by:**
  - outcomes <- traits.ResultChartOutcome

### ResultChartOutcome
**Foreign Keys:**
  - chart -> traits.ResultChart [FK]
  - outcome -> traits.CheckOutcome [FK]

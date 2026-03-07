# Arx II Model Introspection Report
# Generated for CLAUDE.md enrichment


## actions

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
**Pointed to by:**
  - conditioncapabilityeffect_set <- conditions.ConditionCapabilityEffect
  - bypasscapabilityrequirement_set <- obstacles.BypassCapabilityRequirement
  - obstacletemplate_set <- obstacles.ObstacleTemplate

### CheckType
**Pointed to by:**
  - cures_conditions <- conditions.ConditionTemplate
  - conditionstage_set <- conditions.ConditionStage
  - conditioncheckmodifier_set <- conditions.ConditionCheckModifier

### DamageType
**Foreign Keys:**
  - resonance -> magic.Resonance [OneToOne] (nullable)
**Pointed to by:**
  - conditionresistancemodifier_set <- conditions.ConditionResistanceModifier
  - conditiondamageovertime_set <- conditions.ConditionDamageOverTime
  - conditiondamageinteraction_set <- conditions.ConditionDamageInteraction

### ConditionTemplate
**Foreign Keys:**
  - category -> conditions.ConditionCategory [FK]
  - cure_check_type -> conditions.CheckType [FK] (nullable)
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

### ConditionStage
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK]
  - resist_check_type -> conditions.CheckType [FK] (nullable)
**Pointed to by:**
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
  - check_type -> conditions.CheckType [FK]

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
  - guise_thumbnails <- character_sheets.Guise
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


## flows

### Event
**Pointed to by:**
  - triggerdefinition_set <- flows.TriggerDefinition

### FlowDefinition
**Pointed to by:**
  - steps <- flows.FlowStepDefinition
  - triggerdefinition_set <- flows.TriggerDefinition

### FlowStepDefinition
**Foreign Keys:**
  - flow -> flows.FlowDefinition [FK]
  - parent -> flows.FlowStepDefinition [FK] (nullable)
**Pointed to by:**
  - children <- flows.FlowStepDefinition

### TriggerDefinition
**Foreign Keys:**
  - event -> flows.Event [FK]
  - flow_definition -> flows.FlowDefinition [FK]
**Pointed to by:**
  - trigger_set <- flows.Trigger

### Trigger
**Foreign Keys:**
  - trigger_definition -> flows.TriggerDefinition [FK]
  - obj -> objects.ObjectDB [FK]
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


## world.attempts

### AttemptCategory
**Pointed to by:**
  - templates <- attempts.AttemptTemplate

### AttemptTemplate
**Foreign Keys:**
  - category -> attempts.AttemptCategory [FK]
  - check_type -> checks.CheckType [FK]
**Pointed to by:**
  - consequences <- attempts.AttemptConsequence

### AttemptConsequence
**Foreign Keys:**
  - attempt_template -> attempts.AttemptTemplate [FK]
  - outcome_tier -> traits.CheckOutcome [FK]

### Service Functions
- `get_rollmod(character: 'ObjectDB') -> int — Sum character.sheet_data.rollmod + character.account.player_data.rollmod.`
- `perform_check(character: 'ObjectDB', check_type: 'CheckType', target_difficulty: int = 0, extra_modifiers: int = 0) -> world.checks.types.CheckResult — Main check resolution function.`
- `resolve_attempt(character: 'ObjectDB', attempt_template: 'AttemptTemplate', target_difficulty: int = 0, extra_modifiers: int = 0) -> world.attempts.types.AttemptResult — Resolve an attempt: run the check, select a consequence, apply loss filtering.`


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
- `deny_application(application: 'DraftApplication', *, reviewer: 'AbstractBaseUser | AnonymousUser', comment: 'str') -> 'None' — Deny an application.`
- `finalize_character(draft: 'CharacterDraft', *, add_to_roster: 'bool' = False) -> 'ObjectDB' — Create a Character from a completed CharacterDraft.`
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
  - anima_ritual -> magic.CharacterAnimaRitual [OneToOne] (nullable)
  - motif -> magic.Motif [OneToOne] (nullable)
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
  - created_gifts <- magic.Gift
  - character_gifts <- magic.CharacterGift
  - character_traditions <- magic.CharacterTradition
  - anima_ritual_participations <- magic.AnimaRitualPerformance
  - authored_techniques <- magic.Technique
  - character_techniques <- magic.CharacterTechnique
  - character_facets <- magic.CharacterFacet
  - affinity_totals <- magic.CharacterAffinityTotal
  - resonance_totals <- magic.CharacterResonanceTotal
  - reincarnations <- magic.Reincarnation
  - modifiers <- mechanics.CharacterModifier
  - relationships_as_source <- relationships.CharacterRelationship
  - relationships_as_target <- relationships.CharacterRelationship
  - owned_instances <- instances.InstancedRoom

### Guise
**Foreign Keys:**
  - character -> objects.ObjectDB [FK]
  - thumbnail -> evennia_extensions.PlayerMedia [FK] (nullable)
**Pointed to by:**
  - organization_memberships <- societies.OrganizationMembership
  - society_reputations <- societies.SocietyReputation
  - organization_reputations <- societies.OrganizationReputation
  - legend_entries <- societies.LegendEntry
  - legend_spreads <- societies.LegendSpread

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


## world.checks

### CheckCategory
**Pointed to by:**
  - check_types <- checks.CheckType

### CheckType
**Foreign Keys:**
  - category -> checks.CheckCategory [FK]
**Pointed to by:**
  - bypasscheckrequirement_set <- obstacles.BypassCheckRequirement
  - traits <- checks.CheckTypeTrait
  - aspects <- checks.CheckTypeAspect
  - attempt_templates <- attempts.AttemptTemplate

### CheckTypeTrait
**Foreign Keys:**
  - check_type -> checks.CheckType [FK]
  - trait -> traits.Trait [FK]

### CheckTypeAspect
**Foreign Keys:**
  - check_type -> checks.CheckType [FK]
  - aspect -> classes.Aspect [FK]

### Service Functions
- `cast(typ, val) — Cast a value to a type.`
- `get_rollmod(character: 'ObjectDB') -> int — Sum character.sheet_data.rollmod + character.account.player_data.rollmod.`
- `perform_check(character: 'ObjectDB', check_type: 'CheckType', target_difficulty: int = 0, extra_modifiers: int = 0) -> world.checks.types.CheckResult — Main check resolution function.`


## world.classes

### Path
**Pointed to by:**
  - skill_suggestions <- skills.PathSkillSuggestion
  - drafts <- character_creation.CharacterDraft
  - child_paths <- classes.Path
  - path_aspects <- classes.PathAspect
  - character_selections <- progression.CharacterPathHistory
  - allowed_styles <- magic.TechniqueStyle
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
**Pointed to by:**
  - conditioncapabilityeffect_set <- conditions.ConditionCapabilityEffect
  - bypasscapabilityrequirement_set <- obstacles.BypassCapabilityRequirement
  - obstacletemplate_set <- obstacles.ObstacleTemplate

### CheckType
**Pointed to by:**
  - cures_conditions <- conditions.ConditionTemplate
  - conditionstage_set <- conditions.ConditionStage
  - conditioncheckmodifier_set <- conditions.ConditionCheckModifier

### DamageType
**Foreign Keys:**
  - resonance -> magic.Resonance [OneToOne] (nullable)
**Pointed to by:**
  - conditionresistancemodifier_set <- conditions.ConditionResistanceModifier
  - conditiondamageovertime_set <- conditions.ConditionDamageOverTime
  - conditiondamageinteraction_set <- conditions.ConditionDamageInteraction

### ConditionTemplate
**Foreign Keys:**
  - category -> conditions.ConditionCategory [FK]
  - cure_check_type -> conditions.CheckType [FK] (nullable)
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

### ConditionStage
**Foreign Keys:**
  - condition -> conditions.ConditionTemplate [FK]
  - resist_check_type -> conditions.CheckType [FK] (nullable)
**Pointed to by:**
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
  - check_type -> conditions.CheckType [FK]

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

### Service Functions
- `apply_condition(target: 'ObjectDB', condition: world.conditions.models.ConditionTemplate, *, severity: int = 1, duration_rounds: int | None = None, source_character: 'ObjectDB | None' = None, source_technique=None, source_description: str = '') -> world.conditions.types.ApplyConditionResult — Apply a condition to a target, handling stacking and interactions.`
- `clear_all_conditions(target: 'ObjectDB', *, only_negative: bool = False, only_category: 'ConditionCategory | None' = None) -> int — Remove all conditions from a target.`
- `dataclass(cls=None, /, *, init=True, repr=True, eq=True, order=False, unsafe_hash=False, frozen=False, match_args=True, kw_only=False, slots=False, weakref_slot=False) — Add dunder methods based on the fields defined in the class.`
- `get_active_conditions(target: 'ObjectDB', *, category: 'ConditionCategory | None' = None, condition: world.conditions.models.ConditionTemplate | None = None, include_suppressed: bool = False) -> django.db.models.query.QuerySet — Get active condition instances on a target.`
- `get_aggro_priority(target: 'ObjectDB') -> int — Get the total aggro priority from all conditions.`
- `get_all_capability_values(target: 'ObjectDB') -> dict[str, int] — Get all capability values for a character.`
- `get_capability_status(target: 'ObjectDB', capability: world.conditions.models.CapabilityType) -> world.conditions.types.CapabilityStatus — Get the status of a capability for a target based on active conditions.`
- `get_capability_value(target: 'ObjectDB', capability: world.conditions.models.CapabilityType) -> int — Get the total value of a capability for a character.`
- `get_check_modifier(target: 'ObjectDB', check_type: world.conditions.models.CheckType) -> world.conditions.types.CheckModifierResult — Get the total modifier for a check type from active conditions.`
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
- `get_goal_bonus(character: 'CharacterSheet', domain_name: str) -> int — Get the goal bonus for a specific domain, applying percentage modifiers.`
- `get_goal_bonuses_breakdown(character: 'CharacterSheet') -> dict[str, world.goals.types.GoalBonusBreakdown] — Get breakdown of all goal bonuses for a character.`
- `get_total_goal_points(character: 'CharacterSheet') -> int — Get the total goal points available for a character to distribute.`


## world.magic

### EffectType
**Pointed to by:**
  - available_restrictions <- magic.Restriction
  - techniques <- magic.Technique
  - cantrips <- magic.Cantrip

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
  - thread_type_grants <- magic.ThreadType
  - thread_resonances <- magic.ThreadResonance
  - character_facets <- magic.CharacterFacet
  - character_totals <- magic.CharacterResonanceTotal
  - motif_resonances <- magic.MotifResonance

### CharacterAura
**Foreign Keys:**
  - character -> objects.ObjectDB [OneToOne]

### CharacterResonance
**Foreign Keys:**
  - character -> objects.ObjectDB [FK]
  - resonance -> magic.Resonance [FK]

### Gift
**Foreign Keys:**
  - reincarnation -> magic.Reincarnation [OneToOne] (nullable)
  - creator -> character_sheets.CharacterSheet [FK] (nullable)
**Pointed to by:**
  - character_grants <- magic.CharacterGift
  - techniques <- magic.Technique

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

### ThreadType
**Foreign Keys:**
  - grants_resonance -> magic.Resonance [FK] (nullable)

### Thread
**Foreign Keys:**
  - initiator -> objects.ObjectDB [FK]
  - receiver -> objects.ObjectDB [FK]
**Pointed to by:**
  - journal_entries <- magic.ThreadJournal
  - resonances <- magic.ThreadResonance

### ThreadJournal
**Foreign Keys:**
  - thread -> magic.Thread [FK]
  - author -> objects.ObjectDB [FK] (nullable)

### ThreadResonance
**Foreign Keys:**
  - thread -> magic.Thread [FK]
  - resonance -> magic.Resonance [FK]

### Restriction
**Pointed to by:**
  - techniques <- magic.Technique

### IntensityTier

### Technique
**Foreign Keys:**
  - gift -> magic.Gift [FK]
  - style -> magic.TechniqueStyle [FK]
  - effect_type -> magic.EffectType [FK]
  - source_cantrip -> magic.Cantrip [FK] (nullable)
  - creator -> character_sheets.CharacterSheet [FK] (nullable)
**Pointed to by:**
  - action_enhancements <- actions.ActionEnhancement
  - character_grants <- magic.CharacterTechnique
  - conditions_caused <- conditions.ConditionInstance

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

### CharacterResonanceTotal
**Foreign Keys:**
  - character -> character_sheets.CharacterSheet [FK]
  - resonance -> magic.Resonance [FK]

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

### Service Functions
- `add_resonance_total(character_sheet, resonance: 'ResonanceModel', amount: 'int') -> 'None' — Add to a character's resonance total.`
- `calculate_affinity_breakdown(resonances: 'QuerySet[ResonanceModel]') -> 'dict[str, int]' — Derive affinity counts from a set of resonances.`
- `get_aura_percentages(character_sheet) -> 'AuraPercentages' — Calculate aura percentages from affinity and resonance totals.`


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
**Pointed to by:**
  - distinction_effects <- distinctions.DistinctionEffect
  - character_goals <- goals.CharacterGoal
  - goal_journals <- goals.GoalJournal
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
  - source -> mechanics.ModifierSource [FK]

### Service Functions
- `add_resonance_total(character_sheet, resonance: 'ResonanceModel', amount: 'int') -> 'None' — Add to a character's resonance total.`
- `create_distinction_modifiers(character_distinction: world.distinctions.models.CharacterDistinction) -> list[world.mechanics.models.CharacterModifier] — Create ModifierSource + CharacterModifier records for all effects of a distinction.`
- `delete_distinction_modifiers(character_distinction: world.distinctions.models.CharacterDistinction) -> int — Delete all modifier records for a distinction.`
- `get_modifier_breakdown(character, modifier_target: world.mechanics.models.ModifierTarget) -> world.mechanics.types.ModifierBreakdown — Get detailed breakdown of all modifiers for a target.`
- `get_modifier_total(character, modifier_target: world.mechanics.models.ModifierTarget) -> int — Get total modifier value for a target.`
- `update_distinction_rank(character_distinction: world.distinctions.models.CharacterDistinction) -> None — Update CharacterModifier values when rank changes.`


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
  - character -> objects.ObjectDB [FK]
  - trait -> traits.Trait [FK]

### DevelopmentTransaction
**Foreign Keys:**
  - character -> objects.ObjectDB [FK]
  - trait -> traits.Trait [FK]
  - scene -> scenes.Scene [FK] (nullable)
  - gm -> accounts.AccountDB [FK] (nullable)

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

### RelationshipRequirement
**Foreign Keys:**
  - class_level_unlock -> progression.ClassLevelUnlock [FK]

### TierRequirement
**Foreign Keys:**
  - class_level_unlock -> progression.ClassLevelUnlock [FK]

### CharacterUnlock
**Foreign Keys:**
  - character -> objects.ObjectDB [FK]
  - character_class -> classes.CharacterClass [FK]

### Service Functions
- `award_cg_conversion_xp(character: evennia.objects.models.ObjectDB, *, remaining_cg_points: int, conversion_rate: int) -> None — Award locked XP to a character for unspent CG points.`
- `award_combat_development(characters: list, combat_actions: dict[str, list[str]]) -> dict[str, dict[str, int]] — Award development points for combat actions.`
- `award_crafting_development(characters: list, crafting_actions: dict[str, str]) -> dict[str, dict[str, int]] — Award development points for crafting actions.`
- `award_development_points(character: 'ObjectDB', trait: 'Trait', source: 'str', amount: 'int', scene: 'Scene | None' = None, reason: 'str' = ProgressionReason.SCENE_AWARD, description: 'str' = '', gm: 'AccountDB | None' = None) -> 'DevelopmentTransaction' — Award development points to a character and automatically apply them.`
- `award_kudos(account: evennia.accounts.models.AccountDB, amount: int, source_category: world.progression.models.kudos.KudosSourceCategory, description: str, awarded_by: evennia.accounts.models.AccountDB | None = None, character: evennia.objects.models.ObjectDB | None = None) -> world.progression.types.AwardResult — Award kudos to an account with full audit trail.`
- `award_scene_development_points(scene: world.scenes.models.Scene, participants: list, awards: dict[str, dict]) -> None — Award development points to scene participants.`
- `award_social_development(characters: list, social_actions: dict[str, list[str]]) -> dict[str, dict[str, int]] — Award development points for social actions.`
- `award_xp(account: 'AccountDB', amount: 'int', reason: 'str' = ProgressionReason.SYSTEM_AWARD, description: 'str' = '', gm: 'AccountDB | None' = None) -> 'XPTransaction' — Award XP to an account.`
- `calculate_automatic_scene_awards(scene: world.scenes.models.Scene, participants: list) -> dict[str, dict] — Calculate automatic development point awards based on scene content.`
- `calculate_level_up_requirements(character: 'ObjectDB', character_class: 'CharacterClass', target_level: 'int') -> 'LevelUpRequirements | dict[str, str]' — Calculate what's required to level up a character in a specific class.`
- `check_requirements_for_unlock(character: 'ObjectDB', unlock_target: 'ClassLevelUnlock') -> 'tuple[bool, list[str]]' — Check if a character meets all requirements for an unlock.`
- `claim_kudos(account: evennia.accounts.models.AccountDB, amount: int, claim_category: world.progression.models.kudos.KudosClaimCategory, description: str) -> world.progression.types.ClaimResult — Claim kudos from an account for conversion to rewards.`
- `get_available_unlocks_for_character(character: 'ObjectDB') -> 'AvailableUnlocks' — Get all unlocks that a character could potentially purchase.`
- `get_development_suggestions_for_character(character: 'ObjectDB') -> 'dict[str, list[str]]' — Get development suggestions for a character based on their current traits.`
- `get_or_create_xp_tracker(account: 'AccountDB') -> 'ExperiencePointsData' — Get or create XP tracker for an account.`
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

### CharacterRelationship
**Foreign Keys:**
  - source -> character_sheets.CharacterSheet [FK]
  - target -> character_sheets.CharacterSheet [FK]


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
  - character -> objects.ObjectDB [OneToOne]
  - roster -> roster.Roster [FK]
  - profile_picture -> roster.TenureMedia [FK] (nullable)
  - previous_roster -> roster.Roster [FK] (nullable)
**Pointed to by:**
  - tenures <- roster.RosterTenure
  - codex_knowledge <- codex.CharacterCodexKnowledge
  - clue_knowledge <- codex.CharacterClueKnowledge

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
**Pointed to by:**
  - developmenttransaction_set <- progression.DevelopmentTransaction
  - anima_ritual_performances <- magic.AnimaRitualPerformance
  - participations <- scenes.SceneParticipation
  - messages <- scenes.SceneMessage
  - story_episodes <- stories.EpisodeScene

### SceneParticipation
**Foreign Keys:**
  - scene -> scenes.Scene [FK]
  - account -> accounts.AccountDB [FK]
**Pointed to by:**
  - personas <- scenes.Persona

### Persona
**Foreign Keys:**
  - participation -> scenes.SceneParticipation [FK]
  - character -> objects.ObjectDB [FK]
**Pointed to by:**
  - sent_messages <- scenes.SceneMessage
  - received_messages <- scenes.SceneMessage

### SceneMessage
**Foreign Keys:**
  - supplemental_data -> scenes.SceneMessageSupplementalData [OneToOne] (nullable)
  - scene -> scenes.Scene [FK]
  - persona -> scenes.Persona [FK]
**Pointed to by:**
  - reactions <- scenes.SceneMessageReaction

### SceneMessageSupplementalData
**Foreign Keys:**
  - message -> scenes.SceneMessage [OneToOne]

### SceneMessageReaction
**Foreign Keys:**
  - message -> scenes.SceneMessage [FK]
  - account -> accounts.AccountDB [FK]

### Service Functions
- `broadcast_scene_message(scene: 'Scene', action: 'ActionType') -> 'None' — Send scene information to all accounts in the scene's location.`
- `cast(typ, val) — Cast a value to a type.`


## world.skills

### Skill
**Foreign Keys:**
  - trait -> traits.Trait [OneToOne]
**Pointed to by:**
  - specializations <- skills.Specialization
  - character_values <- skills.CharacterSkillValue
  - path_suggestions <- skills.PathSkillSuggestion
  - anima_rituals <- magic.CharacterAnimaRitual

### Specialization
**Foreign Keys:**
  - parent_skill -> skills.Skill [FK]
**Pointed to by:**
  - character_values <- skills.CharacterSpecializationValue
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

### PathSkillSuggestion
**Foreign Keys:**
  - character_path -> classes.Path [FK]
  - skill -> skills.Skill [FK]


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

### OrganizationMembership
**Foreign Keys:**
  - organization -> societies.Organization [FK]
  - guise -> character_sheets.Guise [FK]

### SocietyReputation
**Foreign Keys:**
  - guise -> character_sheets.Guise [FK]
  - society -> societies.Society [FK]

### OrganizationReputation
**Foreign Keys:**
  - guise -> character_sheets.Guise [FK]
  - organization -> societies.Organization [FK]

### LegendEntry
**Foreign Keys:**
  - guise -> character_sheets.Guise [FK]
**Pointed to by:**
  - spreads <- societies.LegendSpread

### LegendSpread
**Foreign Keys:**
  - legend_entry -> societies.LegendEntry [FK]
  - spreader_guise -> character_sheets.Guise [FK]


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
  - personal_story_character -> objects.ObjectDB [FK] (nullable)
**Pointed to by:**
  - trust_requirements <- stories.StoryTrustRequirement
  - participants <- stories.StoryParticipation
  - chapters <- stories.Chapter
  - feedback <- stories.StoryFeedback

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
  - xp_costs <- progression.TraitXPCost
  - rating_unlocks <- progression.TraitRatingUnlock
  - trait_requirements <- progression.TraitRequirement
  - anima_rituals <- magic.CharacterAnimaRitual
  - modifier_targets <- mechanics.ModifierTarget
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
  - attempt_consequences <- attempts.AttemptConsequence

### ResultChart
**Pointed to by:**
  - outcomes <- traits.ResultChartOutcome

### ResultChartOutcome
**Foreign Keys:**
  - chart -> traits.ResultChart [FK]
  - outcome -> traits.CheckOutcome [FK]

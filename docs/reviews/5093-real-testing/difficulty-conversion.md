# Authored difficulty conversion table (#5093, Task 4)

Rule for a standalone difficulty (`*_level`): old points -> old nine-rank ladder rank (thresholds 0/10/25/50/80/115/155/200/250) -> the level whose new baseline (0, then 18 + 8 x (level - 1)) is nearest that rank's old threshold. Ties go to the lower level. A negative value reads as 0.

| Old points | Level |
|---|---|
| 0-9 | 0 |
| 10-24 | 1 |
| 25-49 | 2 |
| 50-79 | 5 |
| 80-114 | 9 |
| 115-154 | 13 |
| 155-199 | 18 |
| 200-249 | 24 |
| 250 and over | 30 |

Rule for an increment (`*_tenths`): tenths = old points x 2 (the old ladder spent 5 points a level, so one point is two tenths of a level; a Decimal or signed column keeps its type and sign). Null stays null. 0 stays 0.

ADR-0237 disposition for every row: RESTRUCTURE. A RunPython in its own migration (0424, 0427, 0430, 0433, and 0445 for batch 5) carries every row across before the old column is dropped (0425, 0428, 0431, 0434, and 0446). The add migrations are 0423, 0426, 0429, 0432 and 0444.

| Batch | Model | Old column | New column | Kind | New default (old default converted) | Nullable |
|---|---|---|---|---|---|---|
| 1 | conditions.ConditionTemplate | cure_difficulty | cure_difficulty_level | level | 1 | no |
| 1 | conditions.ConditionTemplate | resist_difficulty | resist_difficulty_level | level | 1 | no |
| 1 | conditions.ConditionTemplate | break_free_difficulty | break_free_difficulty_tenths | tenths | 20 | no |
| 1 | conditions.ConditionTemplate | subtlety | subtlety_tenths | tenths | 0 | no |
| 1 | conditions.ConditionStage | resist_difficulty | resist_difficulty_level | level | 1 | no |
| 1 | conditions.TreatmentTemplate | target_difficulty | target_difficulty_level | level | 0 | no |
| 1 | conditions.BreathHoldConfig | target_difficulty | target_difficulty_level | level | 1 | no |
| 1 | conditions.Compulsion | base_difficulty | base_difficulty_level | level | none (required) | no |
| 1 | conditions.Compulsion | difficulty_per_severity | difficulty_per_severity_tenths | tenths | 0 | no |
| 1 | conditions.CompulsionForbiddenAction | extra_difficulty | extra_difficulty_tenths | tenths | 0 | no |
| 1 | conditions.ControlLossTrigger | base_difficulty | base_difficulty_level | level | none (required) | no |
| 1 | conditions.ControlLossTrigger | difficulty_per_pull | difficulty_per_pull_tenths | tenths | none (required) | yes |
| 1 | conditions.ControlLossTrigger | relief_per_level | relief_per_level_tenths | tenths | 0 | no |
| 1 | conditions.ControlLossTrigger | relief_per_thread_level | relief_per_thread_level_tenths | tenths | none (required) | yes |
| 1 | conditions.ControlLossTrigger | relief_cap | relief_cap_tenths | tenths | none (required) | yes |
| 1 | vitals.VitalsConsequenceConfig | knockout_base_difficulty | knockout_base_difficulty_level | level | KNOCKOUT_BASE_DIFFICULTY_LEVEL | no |
| 1 | vitals.VitalsConsequenceConfig | knockout_scaling_per_percent | knockout_scaling_per_percent_tenths | tenths | KNOCKOUT_SCALING_PER_PERCENT_TENTHS | no |
| 1 | vitals.VitalsConsequenceConfig | death_base_difficulty | death_base_difficulty_level | level | DEATH_BASE_DIFFICULTY_LEVEL | no |
| 1 | vitals.VitalsConsequenceConfig | death_scaling_per_percent | death_scaling_per_percent_tenths | tenths | DEATH_SCALING_PER_PERCENT_TENTHS | no |
| 1 | vitals.VitalsConsequenceConfig | wound_base_difficulty | wound_base_difficulty_level | level | WOUND_BASE_DIFFICULTY_LEVEL | no |
| 1 | vitals.VitalsConsequenceConfig | wound_scaling_per_percent | wound_scaling_per_percent_tenths | tenths | WOUND_SCALING_PER_PERCENT_TENTHS | no |
| 1 | vitals.VitalsConsequenceConfig | aging_difficulty_per_year | aging_difficulty_per_year_tenths | tenths | AGING_DIFFICULTY_PER_YEAR_TENTHS | no |
| 1 | vitals.VitalsConsequenceConfig | wake_base_difficulty | wake_base_difficulty_level | level | WAKE_BASE_DIFFICULTY_LEVEL | no |
| 1 | vitals.VitalsConsequenceConfig | wake_scaling_per_percent | wake_scaling_per_percent_tenths | tenths | WAKE_SCALING_PER_PERCENT_TENTHS | no |
| 1 | vitals.VitalsConsequenceConfig | wake_ease_per_round | wake_ease_per_round_tenths | tenths | WAKE_EASE_PER_ROUND_TENTHS | no |
| 1 | dreams.DreamPerilConfig | resist_difficulty | resist_difficulty_level | level | 1 | no |
| 1 | items.ItemTemplate | on_use_difficulty | on_use_difficulty_level | level | none (required) | yes |
| 1 | items.CraftingRecipe | base_difficulty | base_difficulty_level | level | 0 | no |
| 1 | codex.CodexEntry | learn_difficulty | learn_difficulty_level | level | 1 | no |
| 2 | magic.FuryTier | base_check_difficulty | base_check_difficulty_level | level | 0 | no |
| 2 | magic.GiftAcquisitionConfig | training_tier_difficulty_step | training_tier_difficulty_step_tenths | tenths | 20 | no |
| 2 | magic.GiftAcquisitionConfig | training_self_study_difficulty_penalty | training_self_study_difficulty_penalty_tenths | tenths | 20 | no |
| 2 | magic.SoulfrayConfig | base_check_difficulty | base_check_difficulty_level | level | none (required) | no |
| 2 | magic.RitualCheckConfig | target_difficulty | target_difficulty_level | level | 0 | no |
| 2 | magic.RitualCheckConfig | non_founder_target_difficulty | non_founder_target_difficulty_level | level | none (required) | yes |
| 2 | magic.DriftConfig | focus_base_difficulty | focus_base_difficulty_level | level | 1 | no |
| 2 | magic.DriftConfig | focus_difficulty_per_step | focus_difficulty_per_step_tenths | tenths | 4 | no |
| 2 | magic.DriftCorrectionConfig | check_difficulty | check_difficulty_level | level | 0 | no |
| 2 | magic.ResonanceEnvironmentConfig | backfire_base_difficulty | backfire_base_difficulty_level | level | 2 | no |
| 2 | magic.ResonanceEnvironmentConfig | backfire_difficulty_per_magnitude | backfire_difficulty_per_magnitude_tenths | tenths | Decimal("1.000") | no |
| 2 | combat.FleeConfig | base_difficulty | base_difficulty_level | level | FLEE_BASE_DIFFICULTY_LEVEL | no |
| 2 | combat.EncounterAftermathRule | base_difficulty | base_difficulty_level | level | none (required) | no |
| 2 | combat.StrainConfig | strain_check_difficulty | strain_check_difficulty_level | level | 0 | no |
| 2 | combat.EscalationCurve | pace_difficulty_base | pace_difficulty_base_level | level | 0 | no |
| 2 | combat.EscalationCurve | pace_difficulty_per_level | pace_difficulty_per_level_tenths | tenths | 0 | no |
| 2 | combat.FleeTierModifier | difficulty_modifier | difficulty_modifier_tenths | tenths | 0 | no |
| 2 | companions.CompanionArchetype | bind_difficulty | bind_difficulty_level | level | none (required) | no |
| 2 | companions.CompanionArchetype | charm_difficulty_reduction | charm_difficulty_reduction_tenths | tenths | 0 | no |
| 3 | mechanics.SituationTrapLink | detect_difficulty | detect_difficulty_level | level | 0 | no |
| 3 | mechanics.SituationTrapLink | disarm_difficulty | disarm_difficulty_level | level | 0 | no |
| 3 | room_features.Trap | detect_difficulty | detect_difficulty_level | level | 0 | no |
| 3 | room_features.Trap | disarm_difficulty | disarm_difficulty_level | level | 0 | no |
| 3 | clues.RoomClue | detect_difficulty | detect_difficulty_level | level | 0 | no |
| 3 | captivity.CaptivityConfig | clue_detect_difficulty | clue_detect_difficulty_level | level | 0 | no |
| 3 | checks.ConsequenceEffect | capture_clue_detect_difficulty | capture_clue_detect_difficulty_level | level | none (required) | yes |
| 3 | ceremonies.CeremonyConfig | leak_detect_difficulty | leak_detect_difficulty_level | level | 2 | no |
| 3 | covenants.CourtGrantConfig | petition_base_difficulty | petition_base_difficulty_level | level | 0 | no |
| 3 | tasking.TaskTemplate | check_difficulty | check_difficulty_level | level | 0 | no |
| 3 | tasking.ListenerPost | check_difficulty | check_difficulty_level | level | 0 | no |
| 3 | npc_services.NPCServiceOffer | check_difficulty | check_difficulty_level | level | 0 | no |
| 3 | npc_services.SkillCourseOfferDetails | check_difficulty | check_difficulty_level | level | none (required) | no |
| 3 | missions.MissionAssistPattern | difficulty | difficulty_level | level | 0 | no |
| 3 | missions.MissionNodeSupportOption | difficulty | difficulty_level | level | 0 | no |
| 4 | mechanics.ChallengeTemplate | severity | severity_level | level | 2 (45 points converted) | no |
| 4 | mechanics.ChallengeInstance | severity_adjustment | severity_adjustment_tenths | tenths | 0 | no |
| 5 | magic.KindledStrengthTier | give_in_ease | give_in_ease_tenths | tenths | 0 | no |

The GM's one-band shift on a placed challenge was +-15 points (one `DifficultyChoice` band) and is now +-30 tenths of a level's width at the template's level, enforced by the instance's one-band CHECK constraint. A shift is refused when the shifted difficulty would leave the ladder (below 0 points or above level 30's baseline), where it used to be refused past the Trivial and Harrowing bands. Seeded and sample challenge severities were converted by the same rule (the Catch the Faller sample 60 points -> level 5, the Interpose challenge 3 -> level 0, the six starter challenges 1-4 -> level 0).

Observed in last night's production dump (arxiidev, at migration 0376): the authored rows hold few distinct values. ConditionTemplate: cure 10 (2 rows at 25) -> level 1 (level 2); resist 10 -> level 1; break_free 10 -> 20 tenths; subtlety 0. ConditionStage resist: 0, 8, 10, 12, 15, 18, 20, 22 -> levels 0, 0, 1, 1, 1, 1, 1, 1 (stage id 47 'Corrupted by Arderi' stage 1 at 8 points converts to level 0). TreatmentTemplate target 15 -> level 1. CraftingRecipe base 20 -> level 1. CodexEntry learn 10 -> level 1. VitalsConsequenceConfig, DreamPerilConfig, SoulfrayConfig 15 -> 1, RitualCheckConfig 10/12/15/20 -> 1 and non-founder 40 -> 2, FleeConfig 15 -> 1, FleeTierModifier -5/0/5/10/20 -> -10/0/10/20/40 tenths, ResonanceEnvironmentConfig 30 -> 2 and 0.500 -> 1.000, TaskTemplate 10 -> 1, NPCServiceOffer 0 -> 0. Every other converted table is empty in the dump.

## Kept in points

- `MovementConfig.reaction_difficulty_step` stays in points because its integer also scales the fatigue and anima cost of each later reaction in the round (`base x (1 + step x reactions)`), so converting it to tenths would change that cost curve as well as the roll penalty.
- The agriculture `pool_difficulty_threshold`, `pool_difficulty_step` and `pool_difficulty_max_bonus` stay in points because they ramp a food-collection roll that is built on the `DifficultyChoice` band values (`DIFFICULTY_VALUES`), which are themselves code constants in points, and the threshold and step are pool sizes, not difficulties.
- Recorded results stay in points because they hold what a roll was made against after the fact: `CeremonyOffering.difficulty_points`, `SceneActionRequest.resolved_difficulty`, `snapshot_target_difficulty` (now the points of the ritual's authored level) and `OrgTask.derived_difficulty`.
- Columns that are already a choice or a band shift stay as they are: `standoffs.difficulty_shift_bands`, `gm.recommended_difficulty`, `worship.base_difficulty` and `travel.difficulty_modifier`.

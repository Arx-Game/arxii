/**
 * Types for the deliberate skill training surface (#3045).
 *
 * Backend: world.skills.views.TrainingAllocationViewSet /
 * world.skills.serializers.training — all re-exports of generated schema
 * components, no hand-rolled shapes needed.
 */

import type { components } from '@/generated/api';

export type SkillListItem = components['schemas']['SkillList'];
export type TrainingAllocation = components['schemas']['TrainingAllocation'];
export type TrainingAllocationList = components['schemas']['TrainingAllocationList'];
export type ManageTrainingAddRequest = components['schemas']['ManageTrainingAddRequest'];
export type PatchedManageTrainingUpdateRequest =
  components['schemas']['PatchedManageTrainingUpdateRequest'];

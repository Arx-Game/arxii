/**
 * Character Creation API functions
 */

import { apiFetch } from '@/evennia_replacements/api';
import type { PaginatedResponse } from '@/shared/types';
import type {
  Affinity,
  AnimaRitualType,
  ApplicationComment,
  Beginnings,
  Build,
  CGPointBudget,
  CGPointsBreakdown,
  CharacterDraft,
  CharacterDraftUpdate,
  DraftAnimaRitual,
  DraftApplication,
  DraftApplicationDetail,
  DraftFacetAssignment,
  DraftGift,
  DraftMotif,
  DraftTechnique,
  EffectType,
  Facet,
  FacetTreeNode,
  Family,
  FamilyMember,
  FamilyTree,
  FormTraitWithOptions,
  GenderOption,
  GiftDetail,
  GiftListItem,
  HeightBand,
  Path,
  PathSkillSuggestion,
  ProjectedResonance,
  Resonance,
  ResonanceAssociation,
  Restriction,
  Skill,
  SkillPointBudget,
  Species,
  StartingArea,
  StatDefinition,
  Technique,
  TechniqueStyle,
} from './types';

const BASE_URL = '/api/character-creation';
const TRAITS_URL = '/api/traits';
const ROSTER_URL = '/api/roster';
const FORMS_URL = '/api/forms';

export async function getStartingAreas(): Promise<StartingArea[]> {
  const res = await apiFetch(`${BASE_URL}/starting-areas/`);
  if (!res.ok) {
    throw new Error('Failed to load starting areas');
  }
  return res.json();
}

export async function getBeginnings(areaId: number): Promise<Beginnings[]> {
  const res = await apiFetch(`${BASE_URL}/beginnings/?starting_area=${areaId}`);
  if (!res.ok) {
    throw new Error('Failed to load beginnings options');
  }
  return res.json();
}

export async function getGenders(): Promise<GenderOption[]> {
  const res = await apiFetch(`${BASE_URL}/genders/`);
  if (!res.ok) {
    throw new Error('Failed to load gender options');
  }
  return res.json();
}

export async function getSpecies(): Promise<Species[]> {
  // Fetch playable species (those without children) for CG selection
  // This includes both top-level playable species (e.g., Human) and subspecies (e.g., Rex'alfar)
  const res = await apiFetch(`${BASE_URL}/species/?is_playable=true`);
  if (!res.ok) {
    throw new Error('Failed to load species');
  }
  return res.json();
}

export async function getPaths(): Promise<Path[]> {
  // Fetch active Prospect-stage paths for CG selection
  const res = await apiFetch(`${BASE_URL}/paths/`);
  if (!res.ok) {
    throw new Error('Failed to load paths');
  }
  return res.json();
}

export async function getFamilies(areaId: number): Promise<Family[]> {
  const res = await apiFetch(`${BASE_URL}/families/?area_id=${areaId}`);
  if (!res.ok) {
    throw new Error('Failed to load families');
  }
  return res.json();
}

export async function getDraft(): Promise<CharacterDraft | null> {
  const res = await apiFetch(`${BASE_URL}/drafts/`);
  if (!res.ok) {
    throw new Error('Failed to load draft');
  }
  const drafts = await res.json();

  // User can only have one draft, return first or null
  if (drafts.length > 1 && import.meta.env.DEV) {
    console.warn(
      `⚠️ Multiple drafts found (${drafts.length}). User should only have one draft.`,
      drafts
    );
  }

  return drafts.length > 0 ? drafts[0] : null;
}

export async function createDraft(): Promise<CharacterDraft> {
  const res = await apiFetch(`${BASE_URL}/drafts/`, {
    method: 'POST',
  });
  if (!res.ok) {
    throw new Error('Failed to create draft');
  }
  return res.json();
}

export async function updateDraft(
  draftId: number,
  data: CharacterDraftUpdate
): Promise<CharacterDraft> {
  const res = await apiFetch(`${BASE_URL}/drafts/${draftId}/`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    throw new Error('Failed to update draft');
  }
  return res.json();
}

export async function deleteDraft(draftId: number): Promise<void> {
  const res = await apiFetch(`${BASE_URL}/drafts/${draftId}/`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    throw new Error('Failed to delete draft');
  }
}

export async function getProjectedResonances(draftId: number): Promise<ProjectedResonance[]> {
  const res = await apiFetch(`${BASE_URL}/drafts/${draftId}/projected-resonances/`);
  if (!res.ok) {
    throw new Error('Failed to load projected resonances');
  }
  return res.json();
}

export async function submitDraftForReview(
  draftId: number,
  submissionNotes: string
): Promise<DraftApplication> {
  const res = await apiFetch(`${BASE_URL}/drafts/${draftId}/submit/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ submission_notes: submissionNotes }),
  });
  if (!res.ok) throw new Error('Failed to submit draft');
  return res.json();
}

export async function addToRoster(
  draftId: number
): Promise<{ character_id: number; message: string }> {
  const res = await apiFetch(`${BASE_URL}/drafts/${draftId}/add-to-roster/`, {
    method: 'POST',
  });
  if (!res.ok) {
    throw new Error('Failed to add to roster');
  }
  return res.json();
}

export async function canCreateCharacter(): Promise<{ can_create: boolean; reason: string }> {
  const res = await apiFetch(`${BASE_URL}/can-create/`);
  if (!res.ok) {
    throw new Error('Failed to check creation eligibility');
  }
  return res.json();
}

// CG Points Budget
export async function getCGPointBudget(): Promise<CGPointBudget> {
  const res = await apiFetch(`${BASE_URL}/cg-budgets/`);
  if (!res.ok) {
    throw new Error('Failed to load CG point budget');
  }
  const budgets = await res.json();
  return budgets.length > 0
    ? budgets[0]
    : { id: 0, name: 'Default', starting_points: 100, is_active: true };
}

export async function getDraftCGPoints(draftId: number): Promise<CGPointsBreakdown> {
  const res = await apiFetch(`${BASE_URL}/drafts/${draftId}/cg-points/`);
  if (!res.ok) {
    throw new Error('Failed to load CG points breakdown');
  }
  return res.json();
}

// NEW: Family Tree Management
export async function getFamiliesWithOpenPositions(areaId?: number): Promise<Family[]> {
  const params = new URLSearchParams({ has_open_positions: 'true' });
  if (areaId) {
    params.append('area_id', areaId.toString());
  }
  const res = await apiFetch(`${ROSTER_URL}/families/?${params}`);
  if (!res.ok) {
    throw new Error('Failed to load families');
  }
  return res.json();
}

export async function getFamilyTree(familyId: number): Promise<FamilyTree> {
  const res = await apiFetch(`${ROSTER_URL}/families/${familyId}/tree/`);
  if (!res.ok) {
    throw new Error('Failed to load family tree');
  }
  return res.json();
}

export async function createFamily(data: {
  name: string;
  family_type: 'commoner' | 'noble';
  description: string;
  origin_realm?: number;
}): Promise<Family> {
  const res = await apiFetch(`${ROSTER_URL}/families/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    throw new Error('Failed to create family');
  }
  return res.json();
}

export async function createFamilyMember(data: {
  family_id: number;
  member_type: 'placeholder' | 'npc';
  name: string;
  description?: string;
  age?: number;
  mother_id?: number | null;
  father_id?: number | null;
}): Promise<FamilyMember> {
  const res = await apiFetch(`${ROSTER_URL}/family-members/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    throw new Error('Failed to create family member');
  }
  return res.json();
}

// NEW: Height Bands and Builds for Appearance stage
export async function getHeightBands(): Promise<HeightBand[]> {
  const res = await apiFetch(`${FORMS_URL}/height-bands/`);
  if (!res.ok) {
    throw new Error('Failed to load height bands');
  }
  return res.json();
}

export async function getBuilds(): Promise<Build[]> {
  const res = await apiFetch(`${FORMS_URL}/builds/`);
  if (!res.ok) {
    throw new Error('Failed to load builds');
  }
  return res.json();
}

export async function getFormOptions(speciesId: number): Promise<FormTraitWithOptions[]> {
  const res = await apiFetch(`${BASE_URL}/form-options/${speciesId}/`);
  if (!res.ok) {
    throw new Error('Failed to load form options');
  }
  return res.json();
}

// Stat definitions for Attributes stage
export async function getStatDefinitions(): Promise<StatDefinition[]> {
  const res = await apiFetch(`${TRAITS_URL}/stat-definitions/`);
  if (!res.ok) {
    throw new Error('Failed to load stat definitions');
  }
  return res.json();
}

// =============================================================================
// Magic System API
// =============================================================================

const MAGIC_URL = '/api/magic';
const MECHANICS_URL = '/api/mechanics';

export async function getAffinities(): Promise<Affinity[]> {
  const res = await apiFetch(`${MECHANICS_URL}/types/?category=affinity`);
  if (!res.ok) {
    throw new Error('Failed to load affinities');
  }
  return res.json();
}

export async function getResonances(): Promise<Resonance[]> {
  const res = await apiFetch(`${MECHANICS_URL}/types/?category=resonance`);
  if (!res.ok) {
    throw new Error('Failed to load resonances');
  }
  return res.json();
}

export async function getGifts(): Promise<GiftListItem[]> {
  const res = await apiFetch(`${MAGIC_URL}/gifts/`);
  if (!res.ok) {
    throw new Error('Failed to load gifts');
  }
  return res.json();
}

export async function getGift(giftId: number): Promise<GiftDetail> {
  const res = await apiFetch(`${MAGIC_URL}/gifts/${giftId}/`);
  if (!res.ok) {
    throw new Error('Failed to load gift details');
  }
  return res.json();
}

export async function getAnimaRitualTypes(): Promise<AnimaRitualType[]> {
  const res = await apiFetch(`${MAGIC_URL}/anima-ritual-types/`);
  if (!res.ok) {
    throw new Error('Failed to load anima ritual types');
  }
  return res.json();
}

// =============================================================================
// NEW Magic System API (Build-Your-Own)
// =============================================================================

/**
 * Get all technique styles.
 */
export async function getTechniqueStyles(): Promise<TechniqueStyle[]> {
  const res = await apiFetch(`${MAGIC_URL}/styles/`);
  if (!res.ok) {
    throw new Error('Failed to load technique styles');
  }
  return res.json();
}

/**
 * Get all effect types.
 */
export async function getEffectTypes(): Promise<EffectType[]> {
  const res = await apiFetch(`${MAGIC_URL}/effect-types/`);
  if (!res.ok) {
    throw new Error('Failed to load effect types');
  }
  return res.json();
}

/**
 * Get all restrictions, optionally filtered by effect type.
 */
export async function getRestrictions(effectTypeId?: number): Promise<Restriction[]> {
  const params = effectTypeId ? `?allowed_effect_types=${effectTypeId}` : '';
  const res = await apiFetch(`${MAGIC_URL}/restrictions/${params}`);
  if (!res.ok) {
    throw new Error('Failed to load restrictions');
  }
  return res.json();
}

/**
 * Get all resonance associations, optionally filtered by category.
 */
export async function getResonanceAssociations(category?: string): Promise<ResonanceAssociation[]> {
  const params = category ? `?category=${category}` : '';
  const res = await apiFetch(`${MAGIC_URL}/resonance-associations/${params}`);
  if (!res.ok) {
    throw new Error('Failed to load resonance associations');
  }
  return res.json();
}

/**
 * Create a new gift.
 */
export async function createGift(data: {
  name: string;
  affinity: number;
  resonance_ids: number[];
  description: string;
}): Promise<GiftDetail> {
  const res = await apiFetch(`${MAGIC_URL}/gifts/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({}));
    throw new Error(error.detail || 'Failed to create gift');
  }
  return res.json();
}

/**
 * Create a new technique.
 */
export async function createTechnique(data: {
  name: string;
  gift: number;
  style: number;
  effect_type: number;
  restriction_ids?: number[];
  level: number;
  description: string;
}): Promise<Technique> {
  const res = await apiFetch(`${MAGIC_URL}/techniques/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({}));
    throw new Error(error.detail || 'Failed to create technique');
  }
  return res.json();
}

/**
 * Update a technique.
 */
export async function updateTechnique(
  techniqueId: number,
  data: Partial<{
    name: string;
    style: number;
    effect_type: number;
    restriction_ids: number[];
    level: number;
    description: string;
  }>
): Promise<Technique> {
  const res = await apiFetch(`${MAGIC_URL}/techniques/${techniqueId}/`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    throw new Error('Failed to update technique');
  }
  return res.json();
}

/**
 * Delete a technique.
 */
export async function deleteTechnique(techniqueId: number): Promise<void> {
  const res = await apiFetch(`${MAGIC_URL}/techniques/${techniqueId}/`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    throw new Error('Failed to delete technique');
  }
}

// =============================================================================
// Skills System API
// =============================================================================

const SKILLS_URL = '/api/skills';

/**
 * Get all skills with their specializations.
 */
export async function getSkillsWithSpecializations(): Promise<Skill[]> {
  const res = await apiFetch(`${SKILLS_URL}/skills/with_specializations/`);
  if (!res.ok) {
    throw new Error('Failed to load skills');
  }
  return res.json();
}

/**
 * Get skill point budget configuration.
 */
export async function getSkillPointBudget(): Promise<SkillPointBudget> {
  const res = await apiFetch(`${SKILLS_URL}/skill-budget/`);
  if (!res.ok) {
    throw new Error('Failed to load skill point budget');
  }
  return res.json();
}

/**
 * Get skill suggestions for a specific path.
 */
export async function getPathSkillSuggestions(pathId: number): Promise<PathSkillSuggestion[]> {
  const res = await apiFetch(`${SKILLS_URL}/path-skill-suggestions/?character_path=${pathId}`);
  if (!res.ok) {
    throw new Error('Failed to load path skill suggestions');
  }
  return res.json();
}

// =============================================================================
// Draft Magic API (Character Creation)
// =============================================================================

// Draft Gift CRUD
export async function getDraftGifts(): Promise<DraftGift[]> {
  const res = await apiFetch(`${BASE_URL}/draft-gifts/`);
  if (!res.ok) throw new Error('Failed to load draft gifts');
  return res.json();
}

export async function getDraftGift(giftId: number): Promise<DraftGift> {
  const res = await apiFetch(`${BASE_URL}/draft-gifts/${giftId}/`);
  if (!res.ok) throw new Error('Failed to load draft gift');
  return res.json();
}

export async function createDraftGift(data: {
  name: string;
  affinity: number;
  resonances?: number[];
  description?: string;
}): Promise<DraftGift> {
  const res = await apiFetch(`${BASE_URL}/draft-gifts/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to create draft gift');
  return res.json();
}

export async function updateDraftGift(
  giftId: number,
  data: Partial<{ name: string; affinity: number; resonances: number[]; description: string }>
): Promise<DraftGift> {
  const res = await apiFetch(`${BASE_URL}/draft-gifts/${giftId}/`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to update draft gift');
  return res.json();
}

export async function deleteDraftGift(giftId: number): Promise<void> {
  const res = await apiFetch(`${BASE_URL}/draft-gifts/${giftId}/`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('Failed to delete draft gift');
}

// Draft Technique CRUD
export async function createDraftTechnique(data: {
  gift: number;
  name: string;
  style: number;
  effect_type: number;
  restrictions?: number[];
  level?: number;
  description?: string;
}): Promise<DraftTechnique> {
  const res = await apiFetch(`${BASE_URL}/draft-techniques/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to create draft technique');
  return res.json();
}

export async function updateDraftTechnique(
  techniqueId: number,
  data: Partial<{
    name: string;
    style: number;
    effect_type: number;
    restrictions: number[];
    level: number;
    description: string;
  }>
): Promise<DraftTechnique> {
  const res = await apiFetch(`${BASE_URL}/draft-techniques/${techniqueId}/`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to update draft technique');
  return res.json();
}

export async function deleteDraftTechnique(techniqueId: number): Promise<void> {
  const res = await apiFetch(`${BASE_URL}/draft-techniques/${techniqueId}/`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('Failed to delete draft technique');
}

// Draft Motif CRUD
export async function getDraftMotif(): Promise<DraftMotif | null> {
  const res = await apiFetch(`${BASE_URL}/draft-motifs/`);
  if (!res.ok) throw new Error('Failed to load draft motif');
  const motifs = await res.json();
  return motifs.length > 0 ? motifs[0] : null;
}

export async function createDraftMotif(data: { description?: string }): Promise<DraftMotif> {
  const res = await apiFetch(`${BASE_URL}/draft-motifs/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to create draft motif');
  return res.json();
}

export async function ensureDraftMotif(): Promise<DraftMotif> {
  const res = await apiFetch(`${BASE_URL}/draft-motifs/ensure/`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error('Failed to ensure draft motif');
  return res.json();
}

export async function updateDraftMotif(
  motifId: number,
  data: Partial<{ description: string }>
): Promise<DraftMotif> {
  const res = await apiFetch(`${BASE_URL}/draft-motifs/${motifId}/`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to update draft motif');
  return res.json();
}

// Draft Anima Ritual CRUD
export async function getDraftAnimaRitual(): Promise<DraftAnimaRitual | null> {
  const res = await apiFetch(`${BASE_URL}/draft-anima-rituals/`);
  if (!res.ok) throw new Error('Failed to load draft anima ritual');
  const rituals = await res.json();
  return rituals.length > 0 ? rituals[0] : null;
}

export async function createDraftAnimaRitual(data: {
  stat: number;
  skill: number;
  specialization?: number | null;
  resonance: number;
  description: string;
}): Promise<DraftAnimaRitual> {
  const res = await apiFetch(`${BASE_URL}/draft-anima-rituals/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to create draft anima ritual');
  return res.json();
}

export async function updateDraftAnimaRitual(
  ritualId: number,
  data: Partial<{
    stat: number;
    skill: number;
    specialization: number | null;
    resonance: number;
    description: string;
  }>
): Promise<DraftAnimaRitual> {
  const res = await apiFetch(`${BASE_URL}/draft-anima-rituals/${ritualId}/`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to update draft anima ritual');
  return res.json();
}

// =============================================================================
// Facet API (Magic System)
// =============================================================================

/**
 * Get all facets (flat list).
 */
export async function getFacets(): Promise<Facet[]> {
  const res = await apiFetch(`${MAGIC_URL}/facets/`);
  if (!res.ok) throw new Error('Failed to load facets');
  return res.json();
}

/**
 * Get facets as nested tree structure.
 */
export async function getFacetTree(): Promise<FacetTreeNode[]> {
  const res = await apiFetch(`${MAGIC_URL}/facets/tree/`);
  if (!res.ok) throw new Error('Failed to load facet tree');
  return res.json();
}

// =============================================================================
// Draft Facet Assignment API (Character Creation)
// =============================================================================

/**
 * Get all draft facet assignments for the current user's draft.
 */
export async function getDraftFacetAssignments(): Promise<DraftFacetAssignment[]> {
  const res = await apiFetch(`${BASE_URL}/draft-facet-assignments/`);
  if (!res.ok) throw new Error('Failed to load draft facet assignments');
  return res.json();
}

/**
 * Create a facet assignment on a draft motif resonance.
 */
export async function createDraftFacetAssignment(data: {
  motif_resonance: number;
  facet: number;
}): Promise<DraftFacetAssignment> {
  const res = await apiFetch(`${BASE_URL}/draft-facet-assignments/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to create draft facet assignment');
  return res.json();
}

/**
 * Delete a facet assignment.
 */
export async function deleteDraftFacetAssignment(assignmentId: number): Promise<void> {
  const res = await apiFetch(`${BASE_URL}/draft-facet-assignments/${assignmentId}/`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('Failed to delete draft facet assignment');
}

// =============================================================================
// Application Review System API
// =============================================================================

// Player-facing
export async function unsubmitDraft(draftId: number): Promise<void> {
  const res = await apiFetch(`${BASE_URL}/drafts/${draftId}/unsubmit/`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to un-submit draft');
}

export async function resubmitDraft(draftId: number, comment?: string): Promise<void> {
  const res = await apiFetch(`${BASE_URL}/drafts/${draftId}/resubmit/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ comment: comment ?? '' }),
  });
  if (!res.ok) throw new Error('Failed to resubmit draft');
}

export async function withdrawDraft(draftId: number): Promise<void> {
  const res = await apiFetch(`${BASE_URL}/drafts/${draftId}/withdraw/`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to withdraw draft');
}

export async function getDraftApplication(draftId: number): Promise<DraftApplicationDetail | null> {
  const res = await apiFetch(`${BASE_URL}/drafts/${draftId}/application/`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error('Failed to load application');
  return res.json();
}

export async function addDraftComment(draftId: number, text: string): Promise<ApplicationComment> {
  const res = await apiFetch(`${BASE_URL}/drafts/${draftId}/application/comments/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) throw new Error('Failed to add comment');
  return res.json();
}

// Staff-facing
export async function getApplications(
  statusFilter?: string
): Promise<PaginatedResponse<DraftApplication>> {
  const params = statusFilter ? `?status=${statusFilter}` : '';
  const res = await apiFetch(`${BASE_URL}/applications/${params}`);
  if (!res.ok) throw new Error('Failed to load applications');
  return res.json();
}

export async function getApplicationDetail(id: number): Promise<DraftApplicationDetail> {
  const res = await apiFetch(`${BASE_URL}/applications/${id}/`);
  if (!res.ok) throw new Error('Failed to load application');
  return res.json();
}

export async function claimApplication(id: number): Promise<void> {
  const res = await apiFetch(`${BASE_URL}/applications/${id}/claim/`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to claim application');
}

export async function approveApplication(id: number, comment?: string): Promise<void> {
  const res = await apiFetch(`${BASE_URL}/applications/${id}/approve/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ comment: comment ?? '' }),
  });
  if (!res.ok) throw new Error('Failed to approve application');
}

export async function requestApplicationRevisions(id: number, comment: string): Promise<void> {
  const res = await apiFetch(`${BASE_URL}/applications/${id}/request-revisions/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ comment }),
  });
  if (!res.ok) throw new Error('Failed to request revisions');
}

export async function denyApplication(id: number, comment: string): Promise<void> {
  const res = await apiFetch(`${BASE_URL}/applications/${id}/deny/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ comment }),
  });
  if (!res.ok) throw new Error('Failed to deny application');
}

export async function addStaffComment(id: number, text: string): Promise<ApplicationComment> {
  const res = await apiFetch(`${BASE_URL}/applications/${id}/comments/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) throw new Error('Failed to add comment');
  return res.json();
}

export async function getPendingApplicationCount(): Promise<number> {
  const res = await apiFetch(`${BASE_URL}/applications/pending-count/`);
  if (!res.ok) return 0;
  const data = await res.json();
  return data.count;
}

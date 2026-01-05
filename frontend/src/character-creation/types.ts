/**
 * Character Creation types
 */

export interface StartingArea {
  id: number;
  name: string;
  description: string;
  crest_image: string | null;
  is_accessible: boolean;
  special_heritages: SpecialHeritage[];
}

export interface SpecialHeritage {
  id: number;
  name: string;
  description: string;
  allows_full_species_list: boolean;
  family_display: string;
}

export interface Species {
  id: number;
  name: string;
  description: string;
}

export interface Family {
  id: number;
  name: string;
  family_type: 'commoner' | 'noble';
  description: string;
}

export type Gender = 'male' | 'female' | 'nonbinary' | 'other';

export interface Pronouns {
  subject: string;
  object: string;
  possessive: string;
}

export const DEFAULT_PRONOUNS: Record<Gender, Pronouns> = {
  male: { subject: 'he', object: 'him', possessive: 'his' },
  female: { subject: 'she', object: 'her', possessive: 'hers' },
  nonbinary: { subject: 'they', object: 'them', possessive: 'theirs' },
  other: { subject: 'they', object: 'them', possessive: 'theirs' },
};

export enum Stage {
  ORIGIN = 1,
  HERITAGE = 2,
  LINEAGE = 3,
  ATTRIBUTES = 4,
  PATH_SKILLS = 5,
  TRAITS = 6,
  IDENTITY = 7,
  REVIEW = 8,
}

export const STAGE_LABELS: Record<Stage, string> = {
  [Stage.ORIGIN]: 'Origin',
  [Stage.HERITAGE]: 'Heritage',
  [Stage.LINEAGE]: 'Lineage',
  [Stage.ATTRIBUTES]: 'Attributes',
  [Stage.PATH_SKILLS]: 'Path & Skills',
  [Stage.TRAITS]: 'Traits',
  [Stage.IDENTITY]: 'Identity',
  [Stage.REVIEW]: 'Review',
};

export interface CharacterDraft {
  id: number;
  current_stage: Stage;
  selected_area: StartingArea | null;
  selected_heritage: SpecialHeritage | null;
  species: string;
  gender: Gender | '';
  pronoun_subject: string;
  pronoun_object: string;
  pronoun_possessive: string;
  age: number | null;
  family: Family | null;
  is_orphan: boolean;
  draft_data: DraftData;
  stage_completion: Record<Stage, boolean>;
}

export interface DraftData {
  first_name?: string;
  description?: string;
  personality?: string;
  background?: string;
  attributes_complete?: boolean;
  path_skills_complete?: boolean;
  traits_complete?: boolean;
  [key: string]: unknown;
}

export interface CharacterDraftUpdate {
  current_stage?: Stage;
  selected_area_id?: number | null;
  selected_heritage_id?: number | null;
  species?: string;
  gender?: Gender | '';
  pronoun_subject?: string;
  pronoun_object?: string;
  pronoun_possessive?: string;
  age?: number | null;
  family_id?: number | null;
  is_orphan?: boolean;
  draft_data?: Partial<DraftData>;
}

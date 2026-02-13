import type { Gender } from '@/world/character_sheets/types';

export interface MyRosterEntry {
  id: number;
  name: CharacterData['name'];
  profile_picture_url: string | null;
}

export interface CharacterGallery {
  name: string;
  url: string;
}

export interface RaceData {
  id: number;
  name: string;
  description: string;
}

export interface SubraceData {
  id: number;
  name: string;
  description: string;
  race: string;
}

export interface CharacterRaceInfo {
  race: RaceData | null;
  subrace: SubraceData | null;
}

export interface CharacterData {
  id: number;
  name: string;
  age?: number | null;
  gender?: Gender | null;
  race?: CharacterRaceInfo | null;
  char_class?: string | null;
  level?: number | null;
  concept?: string;
  family?: string;
  vocation?: string;
  social_rank?: number | null;
  background?: string;
  relationships?: string[];
  galleries: CharacterGallery[];
}

export interface RosterEntryData {
  id: number;
  character: CharacterData;
  profile_picture: TenureMedia | null;
  tenures: RosterTenure[];
  can_apply: boolean;
  fullname: string;
  quote: string;
  description: string;
}

export interface RosterData {
  id: number;
  name: string;
  description: string;
  is_active: boolean;
  available_count: number;
}

export interface Artist {
  id: number;
  name: string;
  description: string;
  commission_notes: string;
  accepting_commissions: boolean;
}

export interface PlayerMedia {
  id: number;
  cloudinary_public_id: string;
  cloudinary_url: string;
  media_type: string;
  title: string;
  description: string;
  created_by: Artist | null;
  uploaded_date: string;
  updated_date: string;
}

export interface PlayerData {
  id: number;
  profile_picture: PlayerMedia | null;
  media: PlayerMedia[];
  max_storage: number;
  max_file_size: number;
}

export interface TenureMedia {
  id: number;
  media: PlayerMedia;
  sort_order: number;
  is_public: boolean;
}

export interface TenureGallery {
  id: number;
  tenure: number;
  name: string;
  is_public: boolean;
  allowed_viewers: number[];
}

export interface RosterTenure {
  id: number;
  player_number: number;
  start_date: string;
  end_date: string | null;
  applied_date: string;
  approved_date: string | null;
  approved_by: PlayerData['id'] | null;
  tenure_notes: string;
  photo_folder: string;
  media: TenureMedia[];
}

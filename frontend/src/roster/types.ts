export interface MyRosterEntry {
  id: number;
  name: CharacterData['name'];
}

export interface CharacterGallery {
  name: string;
  url: string;
}

export interface CharacterData {
  id: number;
  name: string;
  gender?: string | null;
  char_class?: string | null;
  level?: number | null;
  background?: string;
  stats?: Record<string, number>;
  relationships?: string[];
  galleries: CharacterGallery[];
}

export interface RosterEntryData {
  id: number;
  character: CharacterData;
  profile_picture: TenureMedia | null;
  tenures: RosterTenure[];
  can_apply: boolean;
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

export interface TenureMedia {
  id: number;
  media: PlayerMedia;
  sort_order: number;
  is_public: boolean;
}

export interface RosterTenure {
  id: number;
  player_number: number;
  start_date: string;
  end_date: string | null;
  applied_date: string;
  approved_date: string | null;
  approved_by: number | null;
  tenure_notes: string;
  photo_folder: string;
  media: TenureMedia[];
}

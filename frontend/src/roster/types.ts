export interface MyRosterEntry {
  id: number;
  name: string;
}

export interface CharacterGallery {
  name: string;
  url: string;
}

export interface CharacterData {
  id: number;
  name: string;
  portrait: string;
  gender?: string | null;
  class?: string | null;
  level?: number | null;
  background?: string;
  stats?: Record<string, number>;
  relationships?: string[];
  galleries: CharacterGallery[];
}

export interface RosterEntryData {
  id: number;
  character: CharacterData;
  can_apply: boolean;
}

export interface RosterData {
  id: number;
  name: string;
  description: string;
  is_active: boolean;
  available_count: number;
}

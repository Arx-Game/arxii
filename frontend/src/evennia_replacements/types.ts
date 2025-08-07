export interface HomeStats {
  num_accounts_connected: number;
  num_accounts_registered: number;
  num_accounts_registered_recent: number;
  num_accounts_connected_recent: number;
  num_characters: number;
  num_rooms: number;
  num_exits: number;
  num_others: number;
  page_title: string;
  accounts_connected_recent: Array<{ username: string; last_login: string }>;
}

export interface AccountData {
  id: number;
  username: string;
  display_name: string;
  last_login: string | null;
  avatar_url?: string;
}

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

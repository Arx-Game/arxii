export interface AccountData {
  id: number;
  username: string;
  display_name: string;
  last_login: string | null;
  avatar_url?: string;
}

export interface StatusData {
  online: number;
  accounts: number;
  characters: number;
  rooms: number;
  recentPlayers: Array<{ id: number; name: string; avatar_url?: string }>;
  news: Array<{ id: number; title: string }>;
}

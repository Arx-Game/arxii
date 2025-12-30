export interface AccountData {
  id: number;
  username: string;
  display_name: string;
  last_login: string | null;
  email: string;
  email_verified: boolean;
  can_create_characters: boolean;
  is_staff: boolean;
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

export interface AuthFlow {
  id: string;
  is_pending: boolean;
}

export interface SignupResponse {
  data?: {
    flows?: AuthFlow[];
  };
}

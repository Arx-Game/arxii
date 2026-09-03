import type { MyRosterEntry } from '@/roster/types';

export interface PersonaPayload {
  id: number;
  name: string;
  persona_type: 'primary' | 'established';
  display_name: string;
}

export interface AvailableCharacter {
  id: number;
  name: string;
  portrait_url: string | null;
  // Open union — backend may add new typeclasses (NPC, etc.) without
  // requiring a frontend release. Use a switch with a default branch.
  character_type: 'PC' | 'GM' | 'STAFF' | (string & {});
  roster_status: string;
  personas: PersonaPayload[];
  last_location: { id: number; name: string } | null;
  currently_puppeted_in_session: boolean;
}

export interface PendingApplication {
  id: number;
  character_id: number;
  character_name: string;
  status: 'pending';
  applied_date: string;
}

export interface AccountData {
  id: number;
  username: string;
  display_name: string;
  last_login: string | null;
  email: string;
  email_verified: boolean;
  can_create_characters: boolean;
  is_staff: boolean;
  /** Whether this account has an approved GMProfile (#2004). */
  is_gm: boolean;
  avatar_url?: string;
  available_characters: AvailableCharacter[];
  pending_applications: PendingApplication[];
  /**
   * Durable server-side character selection (#3412 state 2.5 substrate) —
   * `PlayerData.selected_entry_id`/`selected_entry`. Selection is NOT
   * presence; this is just the persisted "who am I browsing as" fact, read
   * by `useAccountQuery` to hydrate `gameSlice.active`/`activeEntryId` so a
   * hard reload doesn't lose the active character. Confirmed (api-types
   * regen, #3412 slice 1 task 5) that this stays hand-rolled permanently, not
   * just "until a later regen": `CurrentUserAPIView` is a plain `APIView`
   * with no `serializer_class`/`@extend_schema`, so drf-spectacular can't
   * introspect `/api/user/`'s response and `AccountData` never enters the
   * generated schema at all, unlike `SelectedEntryResult`
   * (`roster/types.ts`), whose serializer IS spectacular-wired.
   */
  selected_entry_id: number | null;
  selected_entry: MyRosterEntry | null;
}

/** Result of `postLogin` — a second factor may be required before the account
 * data is available (#3591). */
export type LoginResult = { kind: 'ok'; account: AccountData } | { kind: 'mfa_required' };

/** Public GET /api/registration/status/ (#3054) — never enumerates invites. */
export interface RegistrationStatus {
  open: boolean;
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

export interface SocialProvider {
  id: string;
  name: string;
}

export interface ConnectedSocialAccount {
  id: number;
  provider: string;
  uid: string;
}
